# akita_wais/client.py

import Reticulum as R # Ensure this is 'Reticiculum', not 'RNS'
import os
import json
import time
import threading
import queue
import pickle # For caching discovered servers easily
from .common import (
    client_log as log, ASPECT_DISCOVERY, ASPECT_SERVICE, PROTOCOL_VERSION,
    ACTION_LIST, ACTION_GET, ACTION_SEARCH, ACTION_PEER_LIST,
    STATUS_OK, STATUS_ERROR, STATUS_FILE_META
)

class AkitaWAISClient:
    def __init__(self, config, reticulum_instance): # 'config' here is the FULL config from cli.py
        self.client_specific_config = config['client'] # For client-only settings like timeout
        self.app_config = config # Store the full application config
        self.identity_path = self.app_config['identity']['client_identity_path'] # Use app_config here
        self.rns = reticulum_instance
        self.identity = None
        self.announce_handler = None
        self.running = False
        self.servers = {} # Discovered servers { "hash_hex": {"name": ..., "desc": ..., "hash": ..., "last_seen": ...} }
        self.server_cache_path = self.client_specific_config.get('server_cache_path', 'known_servers.cache') # Use client_specific_config
        self._lock = threading.Lock() # Lock for accessing self.servers
        self._active_link = None
        self._selected_server_hash = None
        self._response_queue = queue.Queue() # Queue for async responses/data
        self._file_transfer_state = {} # State for ongoing file transfers

    def start(self, identity):
        self.identity = identity
        if not self.identity:
            log.critical("Client cannot start without a valid Identity.")
            return False

        self._load_server_cache()

        # Start listening for server announcements
        self._start_discovery_listener() # No need to pass config if it uses self.app_config

        self.running = True
        log.info("Akita WAIS Client Ready.")
        return True

    def stop(self):
        self.running = False
        if self.announce_handler:
            self.announce_handler.cancel()
            log.info("Stopped discovery listener.")
        if self._active_link and self._active_link.status != R.Link.CLOSED:
            log.info(f"Closing active link to {R.prettyhexle(self._active_link.destination.hash)}")
            self._active_link.teardown()
        self._save_server_cache()
        log.info("Akita WAIS Client stopping.")

    def _load_server_cache(self):
        if os.path.exists(self.server_cache_path):
            try:
                with open(self.server_cache_path, 'rb') as f:
                    self.servers = pickle.load(f)
                    log.info(f"Loaded {len(self.servers)} servers from cache: {self.server_cache_path}")
            except Exception as e:
                log.error(f"Could not load server cache from {self.server_cache_path}: {e}")
                self.servers = {}

    def _save_server_cache(self):
        try:
            with open(self.server_cache_path, 'wb') as f:
                with self._lock:
                    pickle.dump(self.servers, f)
                log.info(f"Saved {len(self.servers)} servers to cache: {self.server_cache_path}")
        except Exception as e:
            log.error(f"Could not save server cache to {self.server_cache_path}: {e}")

    def _start_discovery_listener(self): # Removed 'config' parameter
        # Access the 'discovery' aspect from the stored full application configuration
        discovery_aspect = self.app_config['discovery']['aspect']
        self.announce_handler = R.Transport.listen_for_announces(
            callback=self._handle_announce,
            aspect_filter=discovery_aspect
        )
        log.info(f"Listening for server announcements on aspect: {discovery_aspect}")

    def _handle_announce(self, destination_hash, announced_identity, app_data):
        dest_aspects = announced_identity.aspects_for_destination_hash(destination_hash)
        if ASPECT_SERVICE not in dest_aspects:
            log.debug(f"Ignoring announce for unrelated service aspect: {dest_aspects}")
            return

        server_hash_hex = R.prettyhexle(announced_identity.hash)
        try:
            info = json.loads(app_data.decode('utf-8'))
            name = info.get("name", f"Server {server_hash_hex[:6]}")
            desc = info.get("desc", "")
            log.info(f"Discovered server: {name} ({server_hash_hex})")
            with self._lock:
                self.servers[server_hash_hex] = {
                    "name": name,
                    "description": desc,
                    "hash": server_hash_hex,
                    "last_seen": time.time()
                }
        except Exception as e:
            log.warning(f"Could not parse app_data from announce by {server_hash_hex}: {e}")

    def list_discovered_servers(self):
        print("\n--- Discovered Servers ---")
        with self._lock:
            if not self.servers:
                print("No servers discovered yet. Waiting for announcements...")
                return []

            sorted_servers = sorted(self.servers.items(), key=lambda item: item[1]['last_seen'], reverse=True)
            server_list_for_selection = []
            for i, (hash_hex, info) in enumerate(sorted_servers):
                last_seen_ago = time.time() - info['last_seen']
                print(f"{i+1}. {info['name']} ({hash_hex[:10]}...) - Seen {last_seen_ago:.0f}s ago")
                print(f"   Desc: {info['description']}")
                server_list_for_selection.append(info)
        print("-------------------------")
        return server_list_for_selection

    def select_server(self, server_list_for_selection, choice_index):
        if not server_list_for_selection or choice_index < 0 or choice_index >= len(server_list_for_selection):
            print("Invalid server selection.")
            return False

        selected_server = server_list_for_selection[choice_index]
        server_hash_hex = selected_server['hash']
        log.info(f"Selected server: {selected_server['name']} ({server_hash_hex})")

        if self._active_link and self._active_link.status != R.Link.CLOSED:
            if R.prettyhexle(self._active_link.destination.hash) == server_hash_hex:
                 log.info("Already connected to this server.")
                 return True
            else:
                 log.info("Closing existing link to different server.")
                 self._active_link.teardown()
                 self._active_link = None
                 self._selected_server_hash = None

        server_identity = R.Identity.recall(bytes.fromhex(server_hash_hex))
        if not server_identity:
             log.error(f"Could not reconstruct identity for hash {server_hash_hex}")
             return False

        server_destination = R.Destination(
            server_identity,
            R.Destination.OUT,
            R.Destination.TYPE_SINGLE,
            ASPECT_SERVICE
        )

        log.info(f"Attempting to establish link to {R.prettyhexle(server_destination.hash)}...")
        self._active_link = R.Link(server_destination)
        self._active_link.set_link_established_callback(self._link_established)
        self._active_link.set_link_closed_callback(self._link_closed)
        self._active_link.set_response_handler(self._handle_response)
        self._active_link.set_data_handler(self._handle_data)

        establishment_timeout = self.client_specific_config.get('request_timeout_sec', 20) # Use client_specific_config
        wait_start = time.time()
        while self._active_link.status == R.Link.PENDING:
            if time.time() - wait_start > establishment_timeout:
                log.error("Link establishment timed out.")
                self._active_link.teardown()
                self._active_link = None
                return False
            time.sleep(0.1)

        if self._active_link.status == R.Link.ACTIVE:
            log.info("Link established successfully.")
            self._selected_server_hash = server_hash_hex
            return True
        else:
            log.error(f"Link establishment failed. Status: {self._active_link.status}")
            self._active_link.teardown()
            self._active_link = None
            return False

    def _link_established(self, link):
         log.debug(f"Link established callback fired for {R.prettyhexle(link.destination.hash)}")

    def _link_closed(self, link):
         log.warning(f"Link closed to server {R.prettyhexle(link.destination.hash)}")
         if self._active_link == link:
             self._active_link = None
             self._selected_server_hash = None
             keys_to_clear = [k for k, v in self._file_transfer_state.items() if v.get('link_id') == link.hash]
             for key in keys_to_clear:
                 del self._file_transfer_state[key]

    def _handle_response(self, link, request_id, data):
         log.debug(f"Received response for request {request_id}")
         try:
             response = json.loads(data.decode('utf-8'))
             self._response_queue.put({"request_id": request_id, "response": response})

             if response.get("status") == STATUS_FILE_META:
                 filename = response.get("filename")
                 filesize = response.get("size")
                 log.info(f"Expecting file data for {filename} ({filesize} bytes)")
                 self._file_transfer_state[request_id] = {
                     "filename": filename,
                     "expected_size": filesize,
                     "received_size": 0,
                     "file_handle": open(filename, "wb"),
                     "link_id": link.hash
                 }
         except json.JSONDecodeError:
             log.error("Received invalid JSON response.")
             self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": "Invalid JSON from server"}})
         except Exception as e:
             log.error(f"Error handling response: {e}", exc_info=True)
             self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": f"Client error handling response: {e}"}})

    def _handle_data(self, link, raw_data):
         log.debug(f"Received {len(raw_data)} bytes of raw data.")
         request_id_for_transfer = None
         transfer_info = None

         possible_transfers = {rid: state for rid, state in self._file_transfer_state.items() if state.get('link_id') == link.hash and state.get("file_handle")}
         if not possible_transfers:
             log.warning("Received raw data, but no active file transfer state found for this link with an open file handle.")
             return

         # This heuristic assumes data packets come for the most recently initiated file transfer on this link.
         # A more robust system might involve transfer IDs in the metadata.
         request_id_for_transfer = max(possible_transfers.keys())
         transfer_info = possible_transfers[request_id_for_transfer]

         if transfer_info and transfer_info.get("file_handle"):
             try:
                 fh = transfer_info["file_handle"]
                 bytes_written = fh.write(raw_data)
                 transfer_info["received_size"] += bytes_written
                 log.debug(f"Written {bytes_written} bytes to {transfer_info['filename']}. Total: {transfer_info['received_size']}/{transfer_info['expected_size']}")

                 if transfer_info["received_size"] >= transfer_info["expected_size"]:
                     log.info(f"File transfer complete for {transfer_info['filename']}")
                     fh.close()
                     transfer_info["file_handle"] = None # Mark handle as closed
                     self._response_queue.put({"request_id": request_id_for_transfer, "response": {"status": STATUS_OK, "message": f"File '{transfer_info['filename']}' received."}})
                     # Consider removing from self._file_transfer_state or marking as complete
                     # For now, leaving it and relying on link_closed for full cleanup of older states
             except Exception as e:
                 log.error(f"Error writing file chunk for {transfer_info['filename']}: {e}", exc_info=True)
                 if transfer_info.get("file_handle"):
                     transfer_info["file_handle"].close()
                     transfer_info["file_handle"] = None # Mark handle as closed
                 self._response_queue.put({"request_id": request_id_for_transfer, "response": {"status": STATUS_ERROR, "message": f"Error saving file: {e}"}})
         else:
             log.warning("Received raw data, but could not associate it with an open file transfer state.")

    def _send_request_and_wait(self, request):
        if not self._active_link or self._active_link.status != R.Link.ACTIVE:
            print("No active connection to a server.")
            return None

        timeout = self.client_specific_config.get('request_timeout_sec', 20) # Use client_specific_config
        request_id = None # Initialize request_id
        try:
            request_id = self._active_link.request(json.dumps(request).encode('utf-8'))
            log.debug(f"Sent request (ID: {request_id}): {request}")

            start_time = time.time()
            while True:
                 try:
                      queued_item = self._response_queue.get(timeout=1.0)
                      if queued_item.get("request_id") == request_id:
                           response_data = queued_item["response"]
                           if response_data.get("status") != STATUS_FILE_META:
                                return response_data
                           else:
                                log.debug("Received file metadata, waiting for transfer completion signal...")
                                # Timeout for total file transfer should continue from original start_time
                      else:
                           log.warning(f"Received response for unexpected request ID {queued_item.get('request_id')}, re-queuing if possible or ignoring.")
                           # Simple re-queuing could lead to infinite loops if not handled carefully.
                           # For now, we assume only relevant responses for THIS request_id come for simplicity.
                 except queue.Empty:
                      pass

                 if time.time() - start_time > timeout:
                      log.error(f"Request timed out after {timeout} seconds for request_id {request_id}.")
                      if request_id in self._file_transfer_state:
                           state = self._file_transfer_state[request_id]
                           if state.get("file_handle"):
                               state["file_handle"].close()
                               state["file_handle"] = None # Mark handle as closed
                               log.warning(f"Closed potentially partial file due to timeout: {state.get('filename')}")
                           # Consider removing state[request_id] or marking as failed
                      return {"status": STATUS_ERROR, "message": "Request timed out"}
        except Exception as e:
            log.error(f"Error sending request or processing response for request_id {request_id}: {e}", exc_info=True)
            return {"status": STATUS_ERROR, "message": f"Client-side error: {e}"}

    # --- Public methods for CLI interaction ---
    def get_server_list(self): # Corresponds to ACTION_LIST on server
        return self._send_request_and_wait({"action": ACTION_LIST})

    def get_file(self, filename):
        return self._send_request_and_wait({"action": ACTION_GET, "filename": filename})

    def search_files(self, query):
         return self._send_request_and_wait({"action": ACTION_SEARCH, "query": query})

    def get_peer_list(self):
         return self._send_request_and_wait({"action": ACTION_PEER_LIST})
