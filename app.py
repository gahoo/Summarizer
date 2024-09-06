from flask import Flask, request, jsonify
import atexit
from typing import Dict
import os
import pdb
from werkzeug.utils import secure_filename
from Summarize2 import GeminiSummarizer, genai, query_history

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'


# In-memory storage for active conversations
active_conversations: Dict[str, GeminiSummarizer] = {}

# Load the API key
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))

def save_uploaded_file(file):
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)
    return file_path

@app.route('/conversations', methods=['POST'])
def create_conversation():
    if request.files:
        data = {k:v for k,v in request.form.items()}
        data.update({k:v == 'true' for k,v in data.items() if v.lower() in ['true', 'false']})
        data['files'] = [save_uploaded_file(f) for f in request.files.getlist('files')]
    else:
        data = request.json
    
    summarizer = GeminiSummarizer(**data)
    active_conversations[summarizer.id] = summarizer
    
    return jsonify({"conversation_id": summarizer.id}), 201

@app.route('/conversations', methods=['GET'])
def list_conversations():
    pdb.set_trace()
    offset = int(request.args.get('offset', 0))
    limit = int(request.args.get('limit', 10))
    query_db = request.args.get('db') == 'true'
    activated = [v.dict for v in active_conversations.values()]
    activated_ids = [e['id'] for e in activated]
    if query_db:
        db = [e.dict for e in query_history(offset, limit)]
        db = list(filter(lambda e: e['id'] not in activated_ids, db))
    else:
        db = []
    conversations = activated + db
    return jsonify(conversations[offset:offset+limit]), 200

@app.route('/conversations/<conversation_id>', methods=['PUT'])
def save_conversation(conversation_id):
    summarizer = active_conversations.get(conversation_id)
    if summarizer:
        summarizer.save()
        return jsonify({"message": f"Conversation {conversation_id} saved successfully"}), 200
    else:
        return jsonify({"error": "Conversation not found"}), 404

def get_summarizer(conversation_id, cache=False):
    summarizer = active_conversations.get(conversation_id, GeminiSummarizer(id=conversation_id))
    if summarizer.history:
        if cache and conversation_id not in active_conversations:
            active_conversations[conversation_id] = summarizer
        return summarizer
    else:
        return None
    
@app.route('/conversations/<conversation_id>', methods=['GET'])
def get_conversation(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return summarizer.dict, 200

@app.route('/conversations/<conversation_id>', methods=['DELETE'])
def delete_conversation(conversation_id):
    summarizer = active_conversations.pop(conversation_id, GeminiSummarizer(id=conversation_id))

    if summarizer.history:
        summarizer.delete()
        return '', 204
    else:
        return jsonify({"error": "Conversation not found"}), 404

@app.route('/conversations/<conversation_id>/messages', methods=['POST'])
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
def get_conversation_json(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return jsonify(summarizer.json)

@app.route('/conversations/<conversation_id>/markdown', methods=['GET'])
def get_conversation_markdown(conversation_id):
    summarizer = get_summarizer(conversation_id)
    if not summarizer:
        return jsonify({"error": "Conversation not found"}), 404
    
    return summarizer.markdown, 200, {'Content-Type': 'text/markdown'}

def save_active_conversations():
    for summarizer in active_conversations.values():
        summarizer.save()

atexit.register(save_active_conversations)

if __name__ == '__main__':
    app.run(debug=True)