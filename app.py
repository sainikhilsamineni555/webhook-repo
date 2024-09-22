from flask import Flask, request, jsonify, render_template
from pymongo import MongoClient
from datetime import datetime
from dateutil import parser
import pytz

app = Flask(__name__)

# Connecting to MongoDB
client = MongoClient('mongodb://localhost:27017/')
db = client['github_webhooks']
collection = db['actions']

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/latest_changes', methods=['GET'])
def latest_changes():
    changes = list(collection.find().sort('_id', -1).limit(10)) 
    formatted_changes = []

    for change in changes:
        try:
            timestamp = change['timestamp']
            if 'Z' in timestamp and '+' in timestamp:
                timestamp = timestamp.replace('Z', '')
            parsed_time = parser.isoparse(timestamp)
            formatted_time = parsed_time.strftime('%d %B %Y - %I:%M %p UTC')
        except Exception as e:
            print(f"Error parsing timestamp: {change['timestamp']} - {e}")
            continue
        
        if change['action'] == 'PUSH':
            local_time = datetime.fromisoformat(timestamp)
            utc_time = local_time.astimezone(pytz.utc)
            formatted_date = utc_time.strftime('%d %B %Y - %I:%M %p UTC')
            message = f"\"{change['author']}\" pushed to \"{change['to_branch']}\" on {formatted_date}"
        elif change['action'] == 'PULL REQUEST':
            utc_time = datetime.fromisoformat(timestamp)
            formatted_date = utc_time.strftime('%d %B %Y - %I:%M %p UTC')
            message = f"\"{change['author']}\" submitted a pull request from \"{change['from_branch']}\" to \"{change['to_branch']}\" on {formatted_date}"
        elif change['action'] == 'MERGE':
            utc_time = datetime.fromisoformat(timestamp)
            formatted_date = utc_time.strftime('%d %B %Y - %I:%M %p UTC')
            message = f"\"{change['author']}\" merged branch \"{change['from_branch']}\" to \"{change['to_branch']}\" on {formatted_date}"
        
        formatted_changes.append(message)

    return jsonify(formatted_changes)



@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    print('-'*20)
    print(data)
    print('-'*20)
    if data.get('ref'): 
        return handle_push(data)
    
    if data.get('action') in ['opened', 'edited']: 
        return handle_pull_request(data)
    
    if data.get('action') == 'closed' and data.get('pull_request', {}).get('merged'): 
        return handle_merge(data)
    
    return jsonify({'status': 'event not handled'}), 400

def save_to_db(action, author, from_branch, to_branch, timestamp):
    action_doc = {
        'request_id': action.get('id', ''), 
        'author': author,
        'action': action['action'],
        'from_branch': from_branch,
        'to_branch': to_branch,
        'timestamp': timestamp.isoformat() + 'Z' 
    }
    
    collection.insert_one(action_doc)

def handle_push(data):
    branch = data['ref'].split('/')[-1]
    pusher = data['pusher']['name']
    timestamp = datetime.fromisoformat(data['head_commit']['timestamp'].replace('Z', '+00:00'))
    
    action = {
        'id': data['head_commit']['id'],
        'action': 'PUSH'
    }
    save_to_db(action, pusher, '', branch, timestamp)
    
    return jsonify({'status': 'push handled'}), 200

def handle_pull_request(data):
    user = data['pull_request']['user']['login']
    from_branch = data['pull_request']['head']['ref']
    to_branch = data['pull_request']['base']['ref']
    timestamp = datetime.fromisoformat(data['pull_request']['created_at'].replace('Z', '+00:00'))  # Convert to datetime

    action = {
        'id': data['pull_request']['id'],
        'action': 'PULL REQUEST'
    }
    save_to_db(action, user, from_branch, to_branch, timestamp)
    
    return jsonify({'status': 'pull request handled'}), 200

def handle_merge(data):
    user = data['pull_request']['merged_by']['login']
    from_branch = data['pull_request']['head']['ref']
    to_branch = data['pull_request']['base']['ref']
    timestamp = datetime.fromisoformat(data['pull_request']['updated_at'].replace('Z', '+00:00'))  # Convert to datetime

    action = {
        'id': data['pull_request']['id'],
        'action': 'MERGE'
    }
    save_to_db(action, user, from_branch, to_branch, timestamp)
    
    return jsonify({'status': 'merge handled'}), 200

if __name__ == '__main__':
    app.run(port=5000)
