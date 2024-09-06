import google.generativeai as genai
import os
import json
import time
import magic
import hashlib
import argparse
import pdb
import atexit
from pathlib import Path
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from scraper import firecrawl, jina, magic_markdownify, readability_markdownify, download_pdf, download_file, extract_markdown_images, write_flie
from subtitle_downloader import download_captions
from sqlalchemy import create_engine, Column, String, DateTime, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
CONVERSATION_DB = os.getenv('CONVERSATION_DB', 'sqlite:///summarizer.db')
ENGINE = create_engine(CONVERSATION_DB)

class GeminiSummarizer(Base):
    __tablename__ = 'conversations'

    id = Column(String, primary_key=True)
    timestamp = Column(DateTime, default=datetime.now)
    history = Column(Text)
    uri2path = Column(Text)
    files = Column(Text)
    urls = Column(Text)

    def __init__(self, model="models/gemini-1.5-flash", id=None, files=[], urls=[], overwrite=False, **kwargs):
        super().__init__()
        self.model = genai.GenerativeModel(
            model_name=model,
            safety_settings={
                HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
                HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            }
        )
        self.chat = None
        self.files = files.copy()
        self.urls = urls.copy()
        self.uri2path = {}
        self.ready_files = []
        self.timestamp = datetime.now()
        self.history = kwargs.get('history', [])
        self.Session = sessionmaker(bind=ENGINE)
        self.id = self.generate_id(id)

        Base.metadata.create_all(ENGINE)

        if not overwrite:
            self.load_conversation(self.id)
            if self.history and (self.files or self.urls):
                new_files = list(set(files) - set(self.files))
                new_urls = list(set(urls) - set(self.urls))
                self.get_files_and_urls_ready(new_files, new_urls, **kwargs)
                self.files += new_files
                self.urls += new_urls
            else:
                self.get_files_and_urls_ready(self.files, self.urls, **kwargs)
        else:
            self.get_files_and_urls_ready(self.files, self.urls, **kwargs)

        self.prepare_chat(self.ready_files, self.history)

    def generate_id(self, id=None):
        if not id:
            content = json.dumps(self.files + self.urls)
            id = hashlib.sha256(content.encode()).hexdigest()
        return id

    def load_conversation(self, id):
        session = self.Session()
        stored_conversation = session.query(GeminiSummarizer).filter_by(id=id).first()
        session.close()

        if stored_conversation:
            self.history = json.loads(stored_conversation.history)
            self.uri2path = json.loads(stored_conversation.uri2path)
            self.files = json.loads(stored_conversation.files)
            self.urls = json.loads(stored_conversation.urls)
            print(f"Loaded existing conversation for ID: {self.id}")

    def get_files_and_urls_ready(self, files, urls, extract_images=False, **kwargs):
        if files:
            self.ready_files.extend(self.upload(files))
        if self.urls:
            self.ready_files.extend(self.scrape(urls, **kwargs))

        if extract_images:
            image_urls = sum([extract_markdown_images(f.display_name) for f in self.ready_files if f.display_name.endswith('.md')], [])
            image_files = [download_file(url) for url in image_urls]
            self.ready_files.extend(self.upload(image_files))

    def upload(self, files):
        uploaded_files = []
        for file in files:
            mime = magic.Magic(mime=True)
            mime_type = mime.from_file(file)
            print(f"Uploading file '{file}' as {mime_type}...")
            uploaded_file = genai.upload_file(file, mime_type=mime_type, display_name=file)
            print(f"Uploaded file '{uploaded_file.display_name}' as: {uploaded_file.uri}")
            uploaded_files.append(uploaded_file)
            self.uri2path[uploaded_file.uri] = file
        
        return self.wait_for_files_active(uploaded_files)

    def scrape(self, urls, scraper='jina', **kwargs):
        scraped_files = [self.url2file(url, scraper=scraper, **kwargs) for url in urls]
        return self.upload(scraped_files)

    def url2file(self, url, **kwargs):
        if 'youtube.com' in url:
            return download_captions(url, kwargs.get('cookies', kwargs.get('cookies')), 
                                     convert_to_txt=kwargs.get('srt_to_txt', kwargs.get('srt_to_txt')), 
                                     transcribe=kwargs.get('transcribe', kwargs.get('transcribe', True)))
        elif '.pdf' in url:
            return download_pdf(url, kwargs.get('pdf_to_markdown'))
        else:
            return self.url2markdown(url, **kwargs)

    def url2markdown(self, url, scraper='jina', **kwargs):
        if scraper == 'firecrawl':
            return firecrawl(url, **kwargs)
        elif scraper == 'jina':
            return jina(url, **kwargs)
        elif scraper == 'magic_markdownify':
            return magic_markdownify(url)
        elif scraper == 'readability_markdownify':
            return readability_markdownify(url)

    def wait_for_files_active(self, files):
        ready_files = []
        print("Waiting for file processing...")
        for name in (file.name for file in files):
            file = genai.get_file(name)
            while file.state.name == "PROCESSING":
                print(".", end="", flush=True)
                time.sleep(10)
                file = genai.get_file(name)
            if file.state.name != "ACTIVE":
                raise Exception(f"File {file.name} failed to process")
            else:
                ready_files.append(file)
        print("...all files ready\n")
        return ready_files

    def prepare_chat(self, ready_files=[], history=[]):
        if ready_files:
            history.append({"role": "user", "parts": ready_files})
        self.chat = self.model.start_chat(history=history)

    def send(self, message):
        response = self.chat.send_message(message)
        return response.text

    @property
    def json(self):
        if not self.chat:
            return []
        return self.history2json(self.chat.history)

    @property
    def markdown(self):
        if not self.chat:
            return ""
        return self.history2markdown(self.json)

    @property
    def dict(self):
        if not isinstance(self.uri2path, dict):
            self.from_string()
        return {'id': self.id, 'urls': self.urls, 'files': self.files, 'timestamp': self.timestamp, 'ready_files': self.uri2path}

    def history2json(self, history):
        def format_entry(history_entry):
            return {"role": history_entry.role, "parts": [format_part(part) for part in history_entry.parts]}

        def format_part(part):
            if 'file_data' in part:
                return {"file_data": {"mime_type": part.file_data.mime_type, "file_uri": part.file_data.file_uri}}
            else:
                return part.text
            
        return [format_entry(e) for e in history]

    def history2markdown(self, history):
        def format_part_markdown(part, prefix):
            if 'file_data' in part:
                if self.uri2path:
                    return os.path.basename(self.uri2path[part['file_data']['file_uri']])
                else:
                    return part['file_data']['file_uri']
            else:
                if isinstance(part, str):
                    return prefix + part
                else:    
                    return prefix + part['text']
        
        md = []
        for entry in history:
            if entry['role'] == 'user':
                md.append("-" * 10)
                prefix = "> "
            else:
                prefix = ""
            md.append("\n\n".join([format_part_markdown(part, prefix) for part in entry['parts']]))
        return "\n\n".join(md)

    def save(self):
        if self.chat:
            session = self.Session()
            self.to_string()
            session.merge(self)
            session.commit()
            session.close()
            print(f"Saved conversation with ID: {self.id}")
            self.from_string()

    def to_string(self):
        self.history = json.dumps(self.json)
        self.files = json.dumps(self.files)
        self.urls = json.dumps(self.urls)
        self.uri2path = json.dumps(self.uri2path)

    def from_string(self):
        self.history = json.loads(self.history)
        self.files = json.loads(self.files)
        self.urls = json.loads(self.urls)
        self.uri2path = json.loads(self.uri2path)

    def delete(self):
        session = self.Session()
        try:
            # Check if the object exists in the database
            existing = session.query(GeminiSummarizer).filter_by(id=self.id).first()
            if existing:
                session.delete(existing)
                session.commit()
                print(f"Deleted conversation with ID: {self.id}")
            else:
                print(f"Conversation with ID: {self.id} not found in database, skipping deletion")
        except Exception as e:
            print(f"Error deleting conversation: {e}")
            session.rollback()
        finally:
            session.close()

    def export(self, formats=[]):
        if (self.files is None or len(self.files) == 0) and self.urls:
            dirname = "./"
            basename = "+".join([os.path.basename(v) for v in self.uri2path.values()])
        elif len(self.files) == 1:
            dirname = os.path.dirname(self.files[0])
            basename = "+".join([Path(f).stem for f in self.files])
        else:
            dirname = os.path.commonpath(self.files)
            basename = "+".join([Path(f).stem for f in self.files])

        prefix = os.path.splitext(os.path.join(dirname, basename))[0]

        if 'json' in formats:
            write_flie(prefix + ".history.json", json.dumps(self.json))
        if 'markdown' in formats:
            write_flie(prefix + ".gemini.md", self.markdown)

def query_history(offset, limit):
    session = sessionmaker(bind=ENGINE)()
    result = session.query(GeminiSummarizer).order_by(GeminiSummarizer.timestamp.desc()).offset(offset).limit(limit).all() 
    session.close()
    return result
    

# Usage example:
if __name__ == '__main__':
    genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

    parser = argparse.ArgumentParser(description='Gemini Summarize')
    parser.add_argument('--files', nargs="*", help='Files to upload.', default=[])
    parser.add_argument('--urls', nargs="*", help='url to download.', default=[])
    parser.add_argument("--cookies", help="cookies file path")
    parser.add_argument('--prompt', help='prompt', default="请根据视频字幕总结主持人的主要观点")
    parser.add_argument('--model', help='model', default="models/gemini-1.5-flash")
    parser.add_argument('--srt_to_txt', help='convert srt to txt', action='store_true', default=False)
    parser.add_argument('--question', help='ask question after summarize', action='store_true', default=False)
    parser.add_argument('--load_history', dest='id', help='load history from db', default=None)
    parser.add_argument('--save_history', help='save history to db', action='store_true', default=False)
    parser.add_argument('--overwrite', help='overwrite previous history', action='store_true', default=False)
    parser.add_argument('--scraper', help='URL scraper(jina, firecrawl, magic_markdownify, readability_markdownify)', default='jina')
    parser.add_argument('--onlyMainContent', action='store_true', help='Filter content to main content only(firecrawl option)')
    parser.add_argument('--onlyIncludeTags', action='append', help='Filter content to include only specified tags(firecrawl option)')
    parser.add_argument('--removeTags', action='append', help='Filters content to remove specified tags(firecrawl option)')
    parser.add_argument('--return_format', help='return format(jina scraper option)', default='markdown')
    parser.add_argument('--targe_selector', type=str, help='css selector of the html component(jina scraper option)', default='')
    parser.add_argument('--wait_for_selector', type=str, help='css selector of the html component wait to appear(jina scraper option)', default='')
    parser.add_argument('--timeout', type=int, help='timout (jina scraper option)', default=30)
    parser.add_argument('--pdf_to_markdown', help='convert pdf to markdown', action='store_true', default=False)
    parser.add_argument('--no_transcribe', help="don't transcribe audio files", dest='transcribe', action='store_false', default=True)
    parser.add_argument('--extract_images', help='extract images', action='store_true', default=False)
    parser.add_argument('--export_formats', nargs="*", help='export formats (json, markdown)', default=[])

    args = parser.parse_args()

    # Create a new summarizer instance with files and URLs
    summarizer = GeminiSummarizer(**vars(args))
    if args.save_history:
        atexit.register(summarizer.save)

    if args.export_formats:
        atexit.register(summarizer.export, args.export_formats)

    if summarizer.history:
        print(summarizer.markdown)
        print("-" * 10 + "\n")
        print("> " + args.prompt + "\n")
    
    # Send a message
    response = summarizer.send(args.prompt)
    print(response)
    
    if args.question:
        while True:
            print("-" * 10 + "\n")
            msg = input(">请输入其他问题：")
            if msg == "":
                continue
            response = summarizer.send(msg)
            print("\n" + response)