import Reticulum as R
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
    def __init__(self, config, reticulum_instance):
        self.config = config['client']
        self.identity_path = config['identity']['client_identity_path']
        self.rns = reticulum_instance
        self.identity = None
        self.announce_handler = None
        self.running = False
        self.servers = {} # Discovered servers { "hash_hex": {"name": ..., "desc": ..., "hash": ..., "last_seen": ...} }
        self.server_cache_path = self.config.get('server_cache_path', 'known_servers.cache')
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
        self._start_discovery_listener(config=self.config)

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
                    # Optionally prune old entries here
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

    def _start_discovery_listener(self, config):
        discovery_aspect = config['discovery']['aspect']
        self.announce_handler = R.Transport.listen_for_announces(
            callback=self._handle_announce,
            aspect_filter=discovery_aspect
        )
        log.info(f"Listening for server announcements on aspect: {discovery_aspect}")

    def _handle_announce(self, destination_hash, announced_identity, app_data):
        # We only care about announcements related to the WAIS service aspect
        dest_aspects = announced_identity.aspects_for_destination_hash(destination_hash)
        if ASPECT_SERVICE not in dest_aspects:
            log.debug(f"Ignoring announce for unrelated service aspect: {dest_aspects}")
            return

        server_hash_hex = R.prettyhexle(announced_identity.hash)
        try:
            info = json.loads(app_data.decode('utf-8'))
            name = info.get("name", f"Server {server_hash_hex[:6]}")
            desc = info.get("desc", "")
            # Only log if new or updated significantly? For now, just log discovery.
            log.info(f"Discovered server: {name} ({server_hash_hex})")
            with self._lock:
                self.servers[server_hash_hex] = {
                    "name": name,
                    "description": desc,
                    "hash": server_hash_hex, # Store the raw hash bytes too
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
            server_list = []
            for i, (hash_hex, info) in enumerate(sorted_servers):
                last_seen_ago = time.time() - info['last_seen']
                print(f"{i+1}. {info['name']} ({hash_hex[:10]}...) - Seen {last_seen_ago:.0f}s ago")
                print(f"   Desc: {info['description']}")
                server_list.append(info) # Return list for selection
        print("-------------------------")
        return server_list

    def select_server(self, server_list, choice_index):
        if not server_list or choice_index < 0 or choice_index >= len(server_list):
            print("Invalid server selection.")
            return False

        selected_server = server_list[choice_index]
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

        # Create destination from stored hash bytes
        server_identity = R.Identity.recall(bytes.fromhex(server_hash_hex))
        if not server_identity:
             log.error(f"Could not reconstruct identity for hash {server_hash_hex}")
             return False

        server_destination = R.Destination(
            server_identity,
            R.Destination.OUT,
            R.Destination.TYPE_SINGLE,
            ASPECT_SERVICE
            # Add same extra aspects as server if any
        )

        log.info(f"Attempting to establish link to {R.prettyhexle(server_destination.hash)}...")
        self._active_link = R.Link(server_destination)
        self._active_link.set_link_established_callback(self._link_established)
        self._active_link.set_link_closed_callback(self._link_closed)
        self._active_link.set_response_handler(self._handle_response)
        self._active_link.set_data_handler(self._handle_data) # Handler for raw data after response

        # Wait for link establishment (with timeout)
        establishment_timeout = self.config.get('request_timeout_sec', 20)
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
         # Status check handled in select_server loop

    def _link_closed(self, link):
         log.warning(f"Link closed to server {R.prettyhexle(link.destination.hash)}")
         if self._active_link == link:
             self._active_link = None
             self._selected_server_hash = None
             # Clear any pending file transfer state for this link
             keys_to_clear = [k for k, v in self._file_transfer_state.items() if v.get('link_id') == link.hash]
             for key in keys_to_clear:
                 del self._file_transfer_state[key]


    def _handle_response(self, link, request_id, data):
         # This handles the JSON response part from link.respond()
         log.debug(f"Received response for request {request_id}")
         try:
             response = json.loads(data.decode('utf-8'))
             # Put response onto queue for synchronous processing in main thread
             self._response_queue.put({"request_id": request_id, "response": response})

             # If this is metadata for a file, prepare to receive raw data
             if response.get("status") == STATUS_FILE_META:
                 filename = response.get("filename")
                 filesize = response.get("size")
                 log.info(f"Expecting file data for {filename} ({filesize} bytes)")
                 self._file_transfer_state[request_id] = {
                     "filename": filename,
                     "expected_size": filesize,
                     "received_size": 0,
                     "file_handle": open(filename, "wb"), # Open file for writing
                     "link_id": link.hash # Associate with this link instance
                 }

         except json.JSONDecodeError:
             log.error("Received invalid JSON response.")
             self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": "Invalid JSON from server"}})
         except Exception as e:
             log.error(f"Error handling response: {e}", exc_info=True)
             self._response_queue.put({"request_id": request_id, "response": {"status": STATUS_ERROR, "message": f"Client error handling response: {e}"}})

    def _handle_data(self, link, raw_data):
         # This handles raw data sent via link.send() AFTER a response
         log.debug(f"Received {len(raw_data)} bytes of raw data.")
         # Try to find which file transfer this belongs to
         # This simple model assumes only one file transfer per link at a time.
         # A more robust approach might use request_id or a transfer ID from metadata.
         transfer_info = None
         request_id_for_transfer = None

         # Find the most recent FILE_META request associated with this link
         # Note: This is a simplification. A robust implementation needs better state mapping.
         possible_transfers = {rid: state for rid, state in self._file_transfer_state.items() if state.get('link_id') == link.hash}
         if not possible_transfers:
             log.warning("Received raw data, but no active file transfer state found for this link.")
             return

         # Heuristic: assume it belongs to the latest one initiated. Needs improvement.
         # A proper implementation should likely clear state once a transfer completes or fails.
         request_id_for_transfer = max(possible_transfers.keys()) # Max assumes request_ids are sequential/timestamped implicitly
         transfer_info = possible_transfers[request_id_for_transfer]


         if transfer_info and transfer_info.get("file_handle"):
             try:
                 fh = transfer_info["file_handle"]
                 bytes_written = fh.write(raw_data)
                 transfer_info["received_size"] += bytes_written
                 log.debug(f"Written {bytes_written} bytes to {transfer_info['filename']}. Total: {transfer_info['received_size']}/{transfer_info['expected_size']}")

                 # Check if transfer is complete
                 if transfer_info["received_size"] >= transfer_info["expected_size"]:
                     log.info(f"File transfer complete for {transfer_info['filename']}")
                     fh.close()
                     # Signal completion via queue
                     self._response_queue.put({"request_id": request_id_for_transfer, "response": {"status": STATUS_OK, "message": f"File '{transfer_info['filename']}' received."}})
                     # Clean up state
                     del self._file_transfer_state[request_id_for_transfer]

             except Exception as e:
                 log.error(f"Error writing file chunk for {transfer_info['filename']}: {e}", exc_info=True)
                 if transfer_info.get("file_handle"):
                     transfer_info["file_handle"].close()
                 # Signal error via queue
                 self._response_queue.put({"request_id": request_id_for_transfer, "response": {"status": STATUS_ERROR, "message": f"Error saving file: {e}"}})
                 # Clean up state
                 if request_id_for_transfer in self._file_transfer_state:
                     del self._file_transfer_state[request_id_for_transfer]
         else:
             log.warning("Received raw data, but could not associate it with an open file transfer.")


    def _send_request_and_wait(self, request):
        if not self._active_link or self._active_link.status != R.Link.ACTIVE:
            print("No active connection to a server.")
            return None

        timeout = self.config.get('request_timeout_sec', 20)
        try:
            request_id = self._active_link.request(json.dumps(request).encode('utf-8'))
            log.debug(f"Sent request (ID: {request_id}): {request}")

            # Wait for the response(s) from the queue
            start_time = time.time()
            while True:
                 try:
                      queued_item = self._response_queue.get(timeout=1.0) # Check queue periodically
                      # Check if this response is for our request_id
                      if queued_item.get("request_id") == request_id:
                           response_data = queued_item["response"]
                           # Check if this is the final status or file metadata
                           if response_data.get("status") != STATUS_FILE_META:
                                return response_data # Final response received
                           else:
                               # It's file metadata, loop continues to wait for completion/error signal
                               log.debug("Received file metadata, waiting for transfer completion signal...")
                               # Reset start time? Or use overall timeout? Using overall for now.
                               # start_time = time.time() # Uncomment to reset timeout after metadata

                      else:
                           # Put it back if it's for a different request (shouldn't happen with simple queue)
                           log.warning(f"Received response for unexpected request ID {queued_item.get('request_id')}")
                           # self._response_queue.put(queued_item) # Be careful with re-queuing

                 except queue.Empty:
                      pass # Just loop and check timeout

                 # Check overall timeout
                 if time.time() - start_time > timeout:
                      log.error(f"Request timed out after {timeout} seconds.")
                      # Clean up potential partial file transfer
                      if request_id in self._file_transfer_state:
                           state = self._file_transfer_state[request_id]
                           if state.get("file_handle"): state["file_handle"].close()
                           log.warning(f"Closed potentially partial file: {state.get('filename')}")
                           del self._file_transfer_state[request_id]
                      return {"status": STATUS_ERROR, "message": "Request timed out"}


        except Exception as e:
            log.error(f"Error sending request or processing response: {e}", exc_info=True)
            return {"status": STATUS_ERROR, "message": f"Client-side error: {e}"}


    # --- Public methods for CLI interaction ---

    def get_server_list(self):
        return self._send_request_and_wait({"action": ACTION_LIST})

    def get_file(self, filename):
        return self._send_request_and_wait({"action": ACTION_GET, "filename": filename})

    def search_files(self, query):
         return self._send_request_and_wait({"action": ACTION_SEARCH, "query": query})

    def get_peer_list(self):
         return self._send_request_and_wait({"action": ACTION_PEER_LIST})
