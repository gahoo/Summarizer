from flask import Flask, request, jsonify, send_file, render_template, send_from_directory
from flask_httpauth import HTTPTokenAuth
import atexit
from typing import Dict
import os
import pdb
from werkzeug.utils import secure_filename
from Summarize import GeminiSummarizer, genai, query_history
from tokens import tokens


app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
auth = HTTPTokenAuth(scheme='Bearer')


# In-memory storage for active conversations
#active_conversations[db]: Dict[str, GeminiSummarizer] = {}
active_conversations = {db: {} for db in tokens.values()}

# Load the API key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

@auth.verify_token
def verify_token(token):
    if token in tokens:
        return tokens[token]
    return None

def save_uploaded_file(file):
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    return file_path

@app.route('/conversations', methods=['POST'])
@auth.login_required
def create_conversation():
    if request.files:
        data = {k:v for k,v in request.form.items()}
        data.update({k:v == 'true' for k,v in data.items() if v.lower() in ['true', 'false']})
        data['files'] = [save_uploaded_file(f) for f in request.files.getlist('files')]
    else:
        data = request.json
    
    data['db'] = auth.current_user()
    summarizer = GeminiSummarizer(**data)
    active_conversations[data['db']][summarizer.id] = summarizer
    
    return jsonify({"conversation_id": summarizer.id}), 201

@app.route('/conversations', methods=['GET'])
@auth.login_required
def list_conversations():
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 10))
    query_db = request.args.get('db') == 'true'
    filtering = request.args.get('filtering', None)

    if query_db:
        conversations = [e.dict for e in query_history(offset, limit, filtering, db=auth.current_user())]
    else:
        conversations = [v.dict for v in active_conversations[auth.current_user()].values()]
        if filtering:
            conversations = filter(lambda e: filtering in "\n".join(e['urls'] + e['files'] + list(e['ready_files'].values())), conversations)
        conversations = sorted(conversations, key=lambda e: e['timestamp'], reverse=True)[offset:offset+limit]
    return jsonify(conversations), 200

@app.route('/conversations/<conversation_id>', methods=['PUT'])
@auth.login_required
def save_conversation(conversation_id):
    summarizer = active_conversations[auth.current_user()].get(conversation_id)
    if summarizer:
        summarizer.save()
        return jsonify({"message": f"Conversation {conversation_id} saved successfully"}), 200
    else:
        return jsonify({"error": "Conversation not found"}), 404

def get_summarizer(conversation_id, cache=False):
    summarizer = active_conversations[auth.current_user()].get(conversation_id, GeminiSummarizer(id=conversation_id, db=auth.current_user()))
    if summarizer.history:
        if cache and conversation_id not in active_conversations[auth.current_user()]:
            active_conversations[auth.current_user()][conversation_id] = summarizer
        return summarizer
    else:
        return None
    
@app.route('/conversations/<conversation_id>', methods=['GET'])
@auth.login_required
def get_conversation(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return summarizer.dict, 200

@app.route('/conversations/<conversation_id>', methods=['DELETE'])
@auth.login_required
def delete_conversation(conversation_id):
    summarizer = active_conversations[auth.current_user()].pop(conversation_id, GeminiSummarizer(id=conversation_id, db=auth.current_user()))

    if summarizer.history:
        summarizer.delete()
        return '', 204
    else:
        return jsonify({"error": "Conversation not found"}), 404

@app.route('/conversations/<conversation_id>/messages', methods=['POST'])
@auth.login_required
def send_message(conversation_id):
    summarizer = get_summarizer(conversation_id, cache=True)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    message = request.json.get('message')
    if not message:
        return jsonify({"error": "Message is required"}), 400
    else:
        print(message)
    
    response = summarizer.send(message)
    return jsonify({"response": response})

@app.route('/conversations/<conversation_id>/json', methods=['GET'])
@auth.login_required
def get_conversation_json(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return jsonify(summarizer.json)

@app.route('/conversations/<conversation_id>/markdown', methods=['GET'])
@auth.login_required
def get_conversation_markdown(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return summarizer.markdown, 200, {'Content-Type': 'text/markdown'}

@app.route('/')
@app.route('/index.html')
def index():
    urls = request.args.get('urls', '')
    prompt = request.args.get('prompt', '')
    return render_template('index.html', urls=urls, prompt=prompt)

@app.route('/manifest.json')
def manifest():
    return send_file('statics/manifest.json')

@app.route('/statics/<filename>')
def statics(filename):
    return send_from_directory('statics/', filename)

def save_active_conversations():
    for db in active_conversations:
        for summarizer in active_conversations[db].values():
            summarizer.save()

atexit.register(save_active_conversations)

if __name__ == '__main__':
    app.run(debug=True)