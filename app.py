from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
import google.generativeai as genai
from Summarize import prepare_gemini_summarize, history2json
import os
import atexit
import json

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///conversations.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Load environment variables
from dotenv import load_dotenv
load_dotenv()
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
genai.configure(api_key=GEMINI_API_KEY)

# Define database model
class Conversation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    conversation_id = db.Column(db.String(50), unique=True, nullable=False)
    history = db.Column(db.Text, nullable=False)

# Create tables
with app.app_context():
    db.create_all()

# Global dictionary to store active conversations
active_conversations = {}

@app.route('/start_conversation', methods=['POST'])
def start_conversation():
    data = request.json
    model_name = data.get('model', 'models/gemini-1.5-flash')
    files = data.get('files', [])
    urls = data.get('urls', [])

    chat = prepare_gemini_summarize(model_name, files, urls)
    conversation_id = str(len(active_conversations) + 1)
    active_conversations[conversation_id] = chat

    return jsonify({'conversation_id': conversation_id, 'message': 'Conversation started'})

@app.route('/send_message', methods=['POST'])
def send_message():
    data = request.json
    conversation_id = data.get('conversation_id')
    message = data.get('message')

    if conversation_id not in active_conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    chat = active_conversations[conversation_id]
    response = chat.send_message(message)

    return jsonify({'response': response.text})

@app.route('/get_history', methods=['GET'])
def get_history():
    conversation_id = request.args.get('conversation_id')

    if conversation_id not in active_conversations:
        return jsonify({'error': 'Conversation not found'}), 404

    chat = active_conversations[conversation_id]
    history = history2json(chat.history)

    return jsonify({'history': history})

@app.route('/list_conversations', methods=['GET'])
def list_conversations():
    conversations = Conversation.query.all()
    return jsonify({'conversations': [{'id': c.conversation_id} for c in conversations]})

def save_conversations():
    for conversation_id, chat in active_conversations.items():
        history = json.dumps(history2json(chat.history))
        conversation = Conversation.query.filter_by(conversation_id=conversation_id).first()
        if conversation:
            conversation.history = history
        else:
            new_conversation = Conversation(conversation_id=conversation_id, history=history)
            db.session.add(new_conversation)
    db.session.commit()

atexit.register(save_conversations)

if __name__ == '__main__':
    app.run(debug=True)