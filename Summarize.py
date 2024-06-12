import google.generativeai as genai
import argparse
import os
import pdb
import atexit
import json
from IPython.display import Markdown
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY=os.getenv('GEMINI_API_KEY')

parser = argparse.ArgumentParser(description='Gemini Summarize')
parser.add_argument('--file', help='Files to upload.')
parser.add_argument('--prompt', help='prompt', default="请根据视频字幕总结主持人的主要观点")
parser.add_argument('--model', help='model', default="models/gemini-1.5-flash")
parser.add_argument('--question', help='ask question after summarize', action='store_true', default=False)
parser.add_argument('--save_history', help='ask question after summarize', action='store_true', default=False)
args = parser.parse_args()

def save_history_before_exit():
    filename = args.file + '.history.json'
    with open(filename, 'w') as file:
        json.dump(json_history, file)

if args.save_history:
    atexit.register(save_history_before_exit)

json_history=[]
genai.configure(api_key=GEMINI_API_KEY)

sample_file = genai.upload_file(path=args.file, display_name=args.file)

file = genai.get_file(name=sample_file.name)
print(f"Retrieved file '{file.display_name}' as: {sample_file.uri}")

# The Gemini 1.5 models are versatile and work with multimodal prompts
model = genai.GenerativeModel(model_name=args.model)
chat = model.start_chat(history=[])

# Make the LLM request.
print("Making LLM inference request...")
response = model.generate_content([args.prompt, sample_file],
                                  request_options={"timeout": 600})
print(response.text)

#chat = model.start_chat(history=[args.prompt, sample_file])
if args.question:
    history = [args.prompt, sample_file, response.text]
    json_history.extend([{"content": args.prompt, "type": "prompt"}, {"content": args.file, "type": "file"}, {"content": response.text, "type": "response"}])
    while True:
        print("=" * 10)
        msg = input(">请输入其他问题：")
        history.append(msg),
        json_history.append({"content": msg, "type": "prompt"}),
        response = model.generate_content(history, request_options={"timeout": 600})
        #response = chat.send_message(msg)
        print(response.text)
        history.append(response.text)
        json_history.append({"content": response.text, "type": "response"}),

