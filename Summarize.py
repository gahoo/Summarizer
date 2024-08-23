import google.generativeai as genai
import argparse
import os
import pdb
import atexit
import json
import time
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from scraper import firecrawl, jina, magic_markdownify, readability_markdownify, download_pdf
from dotenv import load_dotenv
from pathlib import Path
from subtitle_downloader import download_captions


def save_history_before_exit(chat, ready_files):
    def history2json(history):
        return [format_entry(e) for e in history]

    def format_entry(history_entry):
        return {"role": history_entry.role, "parts": [format_part(part) for part in history_entry.parts]}

    def format_part(part):
        if 'file_data' in part:
            return {"file_data": {"mime_type": part.file_data.mime_type, "file_uri": part.file_data.file_uri, "file_path": uri2path[part.file_data.file_uri]}}
        else:
            return part.text

    def format_markdown(history):
        md = []
        if args.url:
            md.append("\n\n".join(args.url))
            md.append("-" * 10)
        for entry in history:
            if entry.role == 'user':
                md.append("-" * 10)
                prefix = "> "
            else:
                prefix = ""
            md.append("\n\n".join([format_part_markdown(part, prefix) for part in entry.parts]))
        return "\n\n".join(md)
    
    def format_part_markdown(part, prefix):
        if 'file_data' in part:
            return os.path.basename(uri2path[part.file_data.file_uri])
        else:
            return prefix + part.text

    if args.file is None and args.url:
        dirname = "./"
        basename = "+".join([os.path.basename(f.display_name) for f in ready_files])
    elif len(args.file) > 1:
        dirname = os.path.commonpath(args.file)
        basename = "+".join([Path(f).stem for f in args.file])
    else:
        dirname = os.path.dirname(args.file[0])
        basename = "+".join([Path(f).stem for f in args.file])

    prefix, ext = os.path.splitext(os.path.join(dirname, basename))
    json_file = prefix + ".history.json"
    uri2path = {f.uri:f.display_name for f in ready_files}
    json_history = history2json(chat.history)
    print(f"History written to {json_file}")
    with open(json_file, 'w') as file:
        json.dump(json_history, file)

    md_file = prefix + ".gemini.md"
    print(f"History written to {md_file}")
    md_history = format_markdown(chat.history)
    with open(md_file, 'w') as file:
        file.write(md_history)

def upload_to_gemini(path, mime_type=None):
    """Uploads the given file to Gemini.

    See https://ai.google.dev/gemini-api/docs/prompting_with_media
    """

    if path.endswith('.md'):
        mime_type = "text/markdown"
    elif path.endswith('.srt') or path.endswith('.vtt') or path.endswith('.txt'):
        mime_type = "text/plain"
    elif path.endswith('.pdf'):
        mime_type = "application/pdf"
    else:
        mime_type = None
    print(f"Uploading file '{path}' as {mime_type}...")
    file = genai.upload_file(path, mime_type=mime_type, display_name=path)
    print(f"Uploaded file '{file.display_name}' as: {file.uri}")
    return file

def wait_for_files_active(files):
    """Waits for the given files to be active.

    Some files uploaded to the Gemini API need to be processed before they can be
    used as prompt inputs. The status can be seen by querying the file's "state"
    field.

    This implementation uses a simple blocking polling loop. Production code
    should probably employ a more sophisticated approach.
    """
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

def url2file(url):
    if 'youtube.com' in url:
        return download_captions(url, args.cookies, convert_to_txt=args.srt_to_txt, transcribe=args.transcribe)
    elif '.pdf' in url:
        return download_pdf(url, args.pdf_to_markdown)
    else:
        return url2markdown(url)
        
def url2markdown(url):
    if args.scraper == 'firecrawl':
        return firecrawl(url, onlyMainContent=args.onlyMainContent, onlyIncludeTags=args.onlyIncludeTags, removeTags=args.removeTags)
    elif args.scraper == 'jina':
        return jina(url)
    elif args.scraper == 'magic_markdownify':
        return magic_markdownify(url)
    elif args.scraper == 'readability_markdownify':
        return readability_markdownify(url)

def prepare_gemini_summarize(model_name, files=[], urls=[], save_history=True):
    model = genai.GenerativeModel(
        model_name=model_name,
        # safety_settings = Adjust safety settings
        # See https://ai.google.dev/gemini-api/docs/safety-settings
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    })

    ready_files = prepare_gemini_files(files, urls)
    chat = prepare_gemini_chat(model, ready_files)

    if save_history and ready_files:
        atexit.register(save_history_before_exit, chat, ready_files)

    return chat

def prepare_gemini_files(files, urls):
    uploaded_files = []
    if files:
        uploaded_files += [upload_to_gemini(f) for f in files]
    elif urls:
        uploaded_files += [upload_to_gemini(url2file(url)) for url in urls]
    
    return wait_for_files_active(uploaded_files)
    
    
def prepare_gemini_chat(model, ready_files):
    if ready_files:
        chat = model.start_chat(history=[
            {"role": "user", "parts": ready_files},
    #        {"role": "user", "parts": args.prompt},
        ])
    else:
        chat = model.start_chat(history=[])
    return chat

if __name__ == '__main__':
    load_dotenv()
    GEMINI_API_KEY=os.getenv('GEMINI_API_KEY')
    genai.configure(api_key=GEMINI_API_KEY)

    parser = argparse.ArgumentParser(description='Gemini Summarize')
    parser.add_argument('--file', nargs="*", help='Files to upload.')
    parser.add_argument('--url', nargs="*", help='url to download.')
    parser.add_argument("--cookies", help="cookies file path")
    parser.add_argument('--prompt', help='prompt', default="请根据视频字幕总结主持人的主要观点")
    parser.add_argument('--model', help='model', default="models/gemini-1.5-flash")
    parser.add_argument('--srt_to_txt', help='convert srt to txt', action='store_true', default=False)
    parser.add_argument('--question', help='ask question after summarize', action='store_true', default=False)
    parser.add_argument('--save_history', help='ask question after summarize', action='store_true', default=False)
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

    args = parser.parse_args()

    chat = prepare_gemini_summarize(args.model, args.file, args.url, args.save_history)

    # Make the LLM request.
    print("Making LLM inference request...")
    response = chat.send_message(args.prompt)
    print(response.text)

    if args.question:
        while True:
            print("-" * 10 + "\n")
            msg = input(">请输入其他问题：")
            response = chat.send_message(msg)
            print("\n" + response.text)
