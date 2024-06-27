import google.generativeai as genai
import argparse
import os
import pdb
import atexit
import json
import time
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from IPython.display import Markdown
from dotenv import load_dotenv
from pathlib import Path

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
        for entry in history:
            if entry.role == 'user':
                md.append("-" * 10)
                prefix = "> "
            else:
                prefix = ""
            md.append("\n".join([format_part_markdown(part, prefix) for part in entry.parts]))
        return "\n\n".join(md)
    
    def format_part_markdown(part, prefix):
        if 'file_data' in part:
            return os.path.basename(uri2path[part.file_data.file_uri])
        else:
            return prefix + part.text

    if len(args.file) > 1:
        dirname = os.path.commonpath(args.file)
    else:
        dirname = os.path.dirname(args.file[0])
    basename = "+".join([Path(f).stem for f in args.file])

    json_file = os.path.join(dirname, basename) + ".history.json"
    uri2path = {f.uri:f.display_name for f in ready_files}
    json_history = history2json(chat.history)
    print(f"History written to {json_file}")
    with open(json_file, 'w') as file:
        json.dump(json_history, file)

    md_file = os.path.join(dirname, basename) + ".md"
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


if __name__ == '__main__':
    load_dotenv()
    GEMINI_API_KEY=os.getenv('GEMINI_API_KEY')
    genai.configure(api_key=GEMINI_API_KEY)

    parser = argparse.ArgumentParser(description='Gemini Summarize')
    parser.add_argument('--file', nargs="*", help='Files to upload.')
    parser.add_argument('--prompt', help='prompt', default="请根据视频字幕总结主持人的主要观点")
    parser.add_argument('--model', help='model', default="models/gemini-1.5-flash")
    parser.add_argument('--question', help='ask question after summarize', action='store_true', default=False)
    parser.add_argument('--save_history', help='ask question after summarize', action='store_true', default=False)
    args = parser.parse_args()

    model = genai.GenerativeModel(
        model_name=args.model,
        # safety_settings = Adjust safety settings
        # See https://ai.google.dev/gemini-api/docs/safety-settings
        safety_settings={
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
        }
    )
    files = [upload_to_gemini(f) for f in args.file]
    ready_files = wait_for_files_active(files)

    chat = model.start_chat(history=[
        {"role": "user", "parts": ready_files},
#        {"role": "user", "parts": args.prompt},
    ])

    if args.save_history:
        atexit.register(save_history_before_exit, chat, ready_files)

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