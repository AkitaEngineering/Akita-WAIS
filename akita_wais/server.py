import Reticulum as R
import os
import json
import time
import threading
import zlib
from .common import (
    server_log as log, ASPECT_DISCOVERY, ASPECT_SERVICE, PROTOCOL_VERSION,
    ACTION_LIST, ACTION_GET, ACTION_SEARCH, ACTION_PEER_LIST,
    STATUS_OK, STATUS_ERROR, STATUS_FILE_META, MAX_ANNOUNCE_SIZE,
    MAX_TRANSFER_RAM, calculate_sha256
)

class AkitaWAISServer:
    def __init__(self, config, reticulum_instance):
        self.app_config = config
        self.server_config = config['server']
        
        self.identity_path = self.app_config['identity']['server_identity_path']
        self.rns = reticulum_instance
        self.identity = None
        self.service_destination = None
        self.announce_handler = None
        self.running = False
        self._announce_timer = None
        self._server_peers = {} 
        self._lock = threading.Lock() 

        if not os.path.exists(self.server_config['data_dir']):
            try:
                os.makedirs(self.server_config['data_dir'])
            except OSError:
                log.error(f"Could not create data dir: {self.server_config['data_dir']}")

    def start(self, identity):
        self.identity = identity
        if not self.identity:
            log.critical("Server cannot start without a valid Identity.")
            return False

        self.service_destination = R.Destination(
            self.identity,
            R.Destination.IN,
            R.Destination.TYPE_SINGLE,
            ASPECT_SERVICE,
        )

        self.service_destination.set_link_established_callback(self._link_established)
        self._start_discovery_listener()
        self._start_announcing()

        log.info(f"Akita WAIS Server Service Ready.")
        log.info(f"Address: {R.prettyhexle(self.service_destination.hash)}")
        self.running = True
        return True

    def stop(self):
        self.running = False
        if self._announce_timer: self._announce_timer.cancel()
        if self.announce_handler: self.announce_handler.cancel()
        log.info("Akita WAIS Server stopping.")

    def _start_announcing(self):
        interval = self.server_config.get('announce_interval_sec', 60)
        if interval <= 0: return

        app_data_dict = {
            "name": self.server_config['server_info'].get("name", "Akita Server"),
            "desc": self.server_config['server_info'].get("description", ""),
            "v": PROTOCOL_VERSION,
            "caps": ["zlib", "sha256"]
        }
        app_data_bytes = json.dumps(app_data_dict).encode('utf-8')
        if len(app_data_bytes) > MAX_ANNOUNCE_SIZE:
             app_data_bytes = app_data_bytes[:MAX_ANNOUNCE_SIZE]

        def announce_task():
            if not self.running: return
            try:
                self.service_destination.announce(app_data=app_data_bytes)
            except Exception as e:
                log.error(f"Error during announcement: {e}")
            finally:
                if self.running: 
                    self._announce_timer = threading.Timer(interval, announce_task)
                    self._announce_timer.daemon = True
                    self._announce_timer.start()
        announce_task() 

    def _start_discovery_listener(self):
        # Access discovery aspect from app_config to avoid KeyError
        discovery_aspect = self.app_config['discovery']['aspect']
        self.announce_handler = R.Transport.listen_for_announces(
            callback=self._handle_announce,
            aspect_filter=discovery_aspect
        )

    def _handle_announce(self, destination_hash, announced_identity, app_data):
        dest_aspects = announced_identity.aspects_for_destination_hash(destination_hash)
        if ASPECT_SERVICE not in dest_aspects: return
        if announced_identity.hash == self.identity.hash: return

        server_hash_hex = R.prettyhexle(announced_identity.hash)
        try:
            info = json.loads(app_data.decode('utf-8'))
            with self._lock:
                self._server_peers[server_hash_hex] = {
                    "name": info.get("name", f"Server {server_hash_hex[:6]}"),
                    "description": info.get("desc", ""),
                    "hash": server_hash_hex,
                    "last_seen": time.time()
                }
        except Exception:
            pass

    def _link_established(self, link):
        log.info(f"Link established from {R.prettyhexle(link.destination.hash)}")
        link.set_resource_strategy(R.Resource.ACCEPT_ALL)
        link.set_resource_timeout(15) 
        link.set_request_handler(self._handle_request)

    def _handle_request(self, link, request_id, data):
        try:
            request = json.loads(data.decode('utf-8'))
            action = request.get("action")
            
            if action == ACTION_LIST:
                files = os.listdir(self.server_config['data_dir'])
                files = [f for f in files if not f.startswith('.')]
                link.respond(request_id, json.dumps({"status": STATUS_OK, "files": files}).encode('utf-8'))

            elif action == ACTION_GET:
                filename = request.get("filename")
                self._handle_get_request(link, request_id, filename)

            elif action == ACTION_SEARCH:
                query = request.get("query", "").lower()
                files = os.listdir(self.server_config['data_dir'])
                results = [f for f in files if query in f.lower() and not f.startswith('.')]
                link.respond(request_id, json.dumps({"status": STATUS_OK, "results": results}).encode('utf-8'))

            elif action == ACTION_PEER_LIST:
                 with self._lock:
                     peers = list(self._server_peers.values())
                 link.respond(request_id, json.dumps({"status": STATUS_OK, "peers": peers}).encode('utf-8'))

            else:
                link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": "Unknown action"}).encode('utf-8'))

        except Exception as e:
            log.error(f"Error handling request: {e}")
            link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": "Internal error"}).encode('utf-8'))

    def _handle_get_request(self, link, request_id, filename):
        filepath = os.path.join(self.server_config['data_dir'], filename)
        
        # Security check
        if not os.path.abspath(filepath).startswith(os.path.abspath(self.server_config['data_dir'])):
             link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": "Access denied"}).encode('utf-8'))
             return

        if not filename or not os.path.exists(filepath) or not os.path.isfile(filepath):
            link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": "File not found"}).encode('utf-8'))
            return

        # Threaded processing
        threading.Thread(target=self._process_and_send_file, args=(link, request_id, filepath, filename), daemon=True).start()

    def _process_and_send_file(self, link, request_id, filepath, filename):
        try:
            file_size_original = os.path.getsize(filepath)
            
            if file_size_original > MAX_TRANSFER_RAM:
                log.info(f"File {filename} too large for compression. Sending raw.")
                with open(filepath, 'rb') as f:
                    data_to_send = f.read() 
                compressed = False
            else:
                with open(filepath, 'rb') as f:
                    raw_data = f.read()
                
                compressed_data = zlib.compress(raw_data, level=6)
                
                if len(compressed_data) < len(raw_data):
                    data_to_send = compressed_data
                    compressed = True
                    log.info(f"Compressed {filename}: {(len(compressed_data)/len(raw_data))*100:.1f}% of original")
                else:
                    data_to_send = raw_data
                    compressed = False
            
            if compressed:
                 # Hash the original for integrity verification
                 if 'raw_data' in locals():
                     sha256 = calculate_sha256(raw_data)
                 else:
                     with open(filepath, 'rb') as f:
                         sha256 = calculate_sha256(f.read())
            else:
                 sha256 = calculate_sha256(data_to_send)

            meta_response = {
                "status": STATUS_FILE_META,
                "filename": filename,
                "size": len(data_to_send),
                "original_size": file_size_original,
                "compressed": compressed,
                "sha256": sha256,
                "message": "File data follows"
            }
            
            link.respond(request_id, json.dumps(meta_response).encode('utf-8'))

            # Send Data chunks
            chunk_size = R.Reticulum.MAX_PAYLOAD_SIZE // 2
            for i in range(0, len(data_to_send), chunk_size):
                if link.status != R.Link.ACTIVE: break
                chunk = data_to_send[i:i+chunk_size]
                link.send(chunk)
                time.sleep(0.005) 
            
            log.info(f"Sent {filename}")

        except Exception as e:
            log.error(f"Error sending file {filename}: {e}", exc_info=True)
