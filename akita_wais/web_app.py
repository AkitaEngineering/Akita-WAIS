import os
from flask import Flask, jsonify, request, render_template, send_from_directory
from .common import common_log

app = Flask(__name__, static_folder='static', template_folder='templates')
client_instance = None

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/servers', methods=['GET'])
def get_servers():
    if not client_instance:
        return jsonify({"error": "Client not initialized"}), 500
    servers = client_instance.list_discovered_servers()
    return jsonify({"servers": servers})

@app.route('/api/connect', methods=['POST'])
def connect_server():
    data = request.json
    server_hash = data.get('hash')
    if not server_hash:
        return jsonify({"error": "Hash is required"}), 400
    
    servers = client_instance.list_discovered_servers()
    target_server = next((s for s in servers if s['hash'] == server_hash), None)
    
    if not target_server:
        return jsonify({"error": "Server not found in discovered list"}), 404
        
    success = client_instance.select_server(target_server)
    if success:
        return jsonify({"status": "ok", "message": f"Connected to {target_server['name']}"})
    else:
        return jsonify({"error": "Connection failed"}), 500

@app.route('/api/files', methods=['GET'])
def list_files():
    res = client_instance.get_server_list()
    return jsonify(res)

@app.route('/api/search', methods=['GET'])
def search_files():
    query = request.args.get('q', '')
    res = client_instance.search_files(query)
    return jsonify(res)

@app.route('/api/download', methods=['POST'])
def download_file():
    data = request.json
    filename = data.get('filename')
    if not filename:
        return jsonify({"error": "Filename is required"}), 400
        
    res = client_instance.get_file(filename)
    return jsonify(res)

def start_server(client, host='0.0.0.0', port=5000):
    global client_instance
    client_instance = client
    common_log.info(f"Starting Web UI on http://{host}:{port}")
    # Disable flask reloader in threaded context to prevent crashes
    app.run(host=host, port=port, debug=False, use_reloader=False)
