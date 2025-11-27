import Reticulum as R
import os
import json
import time
import threading
import queue
import pickle
import zlib
from .common import (
    client_log as log, ASPECT_DISCOVERY, ASPECT_SERVICE,
    ACTION_LIST, ACTION_GET, ACTION_SEARCH, ACTION_PEER_LIST,
    STATUS_OK, STATUS_ERROR, STATUS_FILE_META, calculate_sha256
)

class AkitaWAISClient:
    def __init__(self, config, reticulum_instance):
        self.app_config = config
        self.client_config = config['client']
        self.identity_path = self.app_config['identity']['client_identity_path']
        self.rns = reticulum_instance
        self.identity = None
        self.announce_handler = None
        self.running = False
        self.servers = {}
        self.server_cache_path = self.client_config.get('server_cache_path', 'known_servers.cache')
        self._lock = threading.Lock()
        self._active_link = None
        self._response_queue = queue.Queue()
        self._file_transfer_state = {}

    def start(self, identity):
        self.identity = identity
        if not self.identity: return False
        self._load_server_cache()
        self._start_discovery_listener()
        self.running = True
        log.info("Akita WAIS Client Ready.")
        return True

    def stop(self):
        self.running = False
        if self.announce_handler: self.announce_handler.cancel()
        if self._active_link and self._active_link.status != R.Link.CLOSED:
            self._active_link.teardown()
        self._save_server_cache()

    def _load_server_cache(self):
        if os.path.exists(self.server_cache_path):
            try:
                with open(self.server_cache_path, 'rb') as f:
                    self.servers = pickle.load(f)
            except Exception: self.servers = {}

    def _save_server_cache(self):
        try:
            with open(self.server_cache_path, 'wb') as f:
                with self._lock: pickle.dump(self.servers, f)
        except Exception: pass

    def _start_discovery_listener(self):
        # Access discovery aspect from app_config to avoid KeyError
        discovery_aspect = self.app_config['discovery']['aspect']
        self.announce_handler = R.Transport.listen_for_announces(
            callback=self._handle_announce, aspect_filter=discovery_aspect
        )

    def _handle_announce(self, destination_hash, announced_identity, app_data):
        dest_aspects = announced_identity.aspects_for_destination_hash(destination_hash)
        if ASPECT_SERVICE not in dest_aspects: return
        server_hash_hex = R.prettyhexle(announced_identity.hash)
        try:
            info = json.loads(app_data.decode('utf-8'))
            with self._lock:
                self.servers[server_hash_hex] = {
                    "name": info.get("name", f"Server {server_hash_hex[:6]}"),
                    "description": info.get("desc", ""),
                    "caps": info.get("caps", []),
                    "hash": server_hash_hex,
                    "last_seen": time.time()
                }
        except Exception: pass

    def list_discovered_servers(self):
        with self._lock:
            if not self.servers: return []
            sorted_servers = sorted(self.servers.items(), key=lambda item: item[1]['last_seen'], reverse=True)
            return [info for _, info in sorted_servers]

    def select_server(self, server_info):
        server_hash_hex = server_info['hash']
        if self._active_link and self._active_link.status != R.Link.CLOSED:
            if R.prettyhexle(self._active_link.destination.hash) == server_hash_hex: return True
            self._active_link.teardown()

        server_identity = R.Identity.recall(bytes.fromhex(server_hash_hex))
        if not server_identity: return False

        server_destination = R.Destination(
            server_identity, R.Destination.OUT, R.Destination.TYPE_SINGLE, ASPECT_SERVICE
        )

        log.info(f"Connecting to {server_info['name']}...")
        self._active_link = R.Link(server_destination)
        self._active_link.set_link_closed_callback(self._link_closed)
        self._active_link.set_response_handler(self._handle_response)
        self._active_link.set_data_handler(self._handle_data)

        timeout = self.client_config.get('request_timeout_sec', 20)
        start = time.time()
        while self._active_link.status == R.Link.PENDING:
            if time.time() - start > timeout:
                self._active_link.teardown()
                return False
            time.sleep(0.1)

        return self._active_link.status == R.Link.ACTIVE

    def _link_closed(self, link):
        if self._active_link == link:
            self._active_link = None
            for rid in list(self._file_transfer_state.keys()):
                if self._file_transfer_state[rid]['link_id'] == link.hash:
                    del self._file_transfer_state[rid]

    def _handle_response(self, link, request_id, data):
        try:
            response = json.loads(data.decode('utf-8'))
            self._response_queue.put({"request_id": request_id, "response": response})

            if response.get("status") == STATUS_FILE_META:
                filename = response.get("filename")
                filesize = response.get("size")
                log.info(f"Receiving {filename} ({filesize} bytes)...")
                
                self._file_transfer_state[request_id] = {
                    "filename": filename,
                    "expected_size": filesize,
                    "received_size": 0,
                    "buffer": bytearray(), 
                    "meta": response,
                    "link_id": link.hash
                }
        except Exception as e:
            log.error(f"Response error: {e}")
            self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": "Protocol Error"}})

    def _handle_data(self, link, raw_data):
        active_rid = None
        for rid, state in self._file_transfer_state.items():
            if state['link_id'] == link.hash:
                active_rid = rid
                break
        
        if not active_rid: return

        state = self._file_transfer_state[active_rid]
        state['buffer'].extend(raw_data)
        state['received_size'] += len(raw_data)
        
        if state['received_size'] >= state['expected_size']:
            self._finalize_file(active_rid, state)

    def _finalize_file(self, request_id, state):
        try:
            data = state['buffer']
            meta = state['meta']
            filename = state['filename']

            # Decompression
            if meta.get('compressed', False):
                try:
                    log.info("Decompressing data...")
                    final_data = zlib.decompress(data)
                except zlib.error:
                    raise Exception("Decompression failed. Data corrupted.")
            else:
                final_data = data

            # Integrity Check
            if 'sha256' in meta:
                log.info("Verifying integrity...")
                calculated_hash = calculate_sha256(final_data)
                if calculated_hash != meta['sha256']:
                    raise Exception(f"Integrity Mismatch! Server: {meta['sha256']}, Recv: {calculated_hash}")
                log.info("Integrity Verified (SHA256).")

            # Save
            with open(filename, 'wb') as f:
                f.write(final_data)
            
            log.info(f"Saved {filename} ({len(final_data)} bytes).")
            self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_OK, "message": f"File {filename} received & verified."}})

        except Exception as e:
            log.error(f"File verification/save failed: {e}")
            self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": str(e)}})
        
        finally:
            if request_id in self._file_transfer_state:
                del self._file_transfer_state[request_id]

    def _send_request_and_wait(self, request):
        if not self._active_link: return {"status": STATUS_ERROR, "message": "Not connected"}
        
        try:
            req_id = self._active_link.request(json.dumps(request).encode('utf-8'))
            timeout = self.client_config.get('request_timeout_sec', 30)
            start = time.time()
            
            while True:
                try:
                    item = self._response_queue.get(timeout=0.5)
                    if item['request_id'] == req_id:
                        resp = item['response']
                        if resp.get("status") == STATUS_FILE_META:
                            continue # Keep waiting for final
                        return resp
                except queue.Empty:
                    if time.time() - start > timeout:
                        return {"status": STATUS_ERROR, "message": "Timeout"}
        except Exception as e:
            return {"status": STATUS_ERROR, "message": str(e)}

    def get_server_list(self): return self._send_request_and_wait({"action": ACTION_LIST})
    def get_file(self, filename): return self._send_request_and_wait({"action": ACTION_GET, "filename": filename})
    def search_files(self, query): return self._send_request_and_wait({"action": ACTION_SEARCH, "query": query})
    def get_peer_list(self): return self._send_request_and_wait({"action": ACTION_PEER_LIST})
