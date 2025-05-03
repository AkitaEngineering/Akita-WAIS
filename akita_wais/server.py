import Reticulum as R
import os
import json
import time
import threading
import base64
from .common import (
    server_log as log, ASPECT_DISCOVERY, ASPECT_SERVICE, PROTOCOL_VERSION,
    ACTION_LIST, ACTION_GET, ACTION_SEARCH, ACTION_PEER_LIST,
    STATUS_OK, STATUS_ERROR, STATUS_FILE_META, MAX_ANNOUNCE_SIZE
)

class AkitaWAISServer:
    def __init__(self, config, reticulum_instance):
        self.config = config['server']
        self.identity_path = config['identity']['server_identity_path']
        self.rns = reticulum_instance
        self.identity = None
        self.service_destination = None
        self.announce_handler = None
        self.running = False
        self._announce_timer = None
        self._server_peers = {} # Cache of discovered peers (servers)
        self._lock = threading.Lock() # For thread safety on peer list

        if not os.path.exists(self.config['data_dir']):
            log.info(f"Creating data directory: {self.config['data_dir']}")
            os.makedirs(self.config['data_dir'])

    def start(self, identity):
        self.identity = identity
        if not self.identity:
            log.critical("Server cannot start without a valid Identity.")
            return False

        # Create the main service destination (TYPE_SINGLE)
        self.service_destination = R.Destination(
            self.identity,
            R.Destination.IN,
            R.Destination.TYPE_SINGLE,
            ASPECT_SERVICE,
            # Add more aspects if needed, e.g., 'app.akita'
        )

        # Register callback for incoming Links
        self.service_destination.set_link_established_callback(self._link_established)

        # Start listening for announcements from other servers (to populate peer list)
        self._start_discovery_listener(config=self.config)

        log.info(f"Akita WAIS Server Service Ready.")
        log.info(f"Service Destination: {R.prettyhexle(self.service_destination.hash)}")
        log.info(f"Share Directory: {os.path.abspath(self.config['data_dir'])}")

        # Start announcing periodically
        self._start_announcing()

        self.running = True
        return True

    def stop(self):
        self.running = False
        if self._announce_timer:
            self._announce_timer.cancel()
            log.info("Stopped announcing.")
        if self.announce_handler:
            self.announce_handler.cancel() # Stop listening for announces
            log.info("Stopped discovery listener.")
        # Optionally deregister link callback, though Reticulum handles cleanup
        log.info("Akita WAIS Server stopping.")

    def _start_announcing(self):
        interval = self.config.get('announce_interval_sec', 60)
        if interval <= 0:
            log.warning("Announce interval is <= 0, server announcing disabled.")
            return

        # Prepare app_data for announcement
        app_data_dict = {
            "name": self.config['server_info'].get("name", "Akita Server"),
            "desc": self.config['server_info'].get("description", ""),
            # Add other info like keywords if space permits
            "v": PROTOCOL_VERSION
        }
        app_data_bytes = json.dumps(app_data_dict).encode('utf-8')

        if len(app_data_bytes) > MAX_ANNOUNCE_SIZE:
             log.warning(f"Server info exceeds max announce size ({MAX_ANNOUNCE_SIZE} bytes). Truncating.")
             # Add truncation logic if needed, or reduce info sent
             app_data_bytes = app_data_bytes[:MAX_ANNOUNCE_SIZE]


        def announce_task():
            if not self.running: return
            try:
                log.debug(f"Announcing service destination {R.prettyhexle(self.service_destination.hash)}")
                self.service_destination.announce(app_data=app_data_bytes)
            except Exception as e:
                log.error(f"Error during announcement: {e}", exc_info=True)
            finally:
                if self.running: # Reschedule if still running
                    self._announce_timer = threading.Timer(interval, announce_task)
                    self._announce_timer.daemon = True
                    self._announce_timer.start()

        log.info(f"Starting announcements every {interval} seconds.")
        announce_task() # Start first announcement immediately

    def _start_discovery_listener(self, config):
        # Listen for announcements from other servers
        discovery_aspect = config['discovery']['aspect']
        self.announce_handler = R.Transport.listen_for_announces(
            callback=self._handle_announce,
            aspect_filter=discovery_aspect
        )
        log.info(f"Listening for peer announcements on aspect: {discovery_aspect}")

    def _handle_announce(self, destination_hash, announced_identity, app_data):
        # Received an announcement from another node (potentially a server)
        # We only care about announcements related to the WAIS service aspect
        dest_aspects = announced_identity.aspects_for_destination_hash(destination_hash)
        if ASPECT_SERVICE not in dest_aspects:
            log.debug(f"Ignoring announce for unrelated service aspect: {dest_aspects}")
            return

        server_hash_hex = R.prettyhexle(announced_identity.hash)
        # Don't add self to peer list
        if announced_identity.hash == self.identity.hash:
            return

        try:
            info = json.loads(app_data.decode('utf-8'))
            name = info.get("name", f"Server {server_hash_hex[:6]}")
            desc = info.get("desc", "")
            log.info(f"Discovered potential peer: {name} ({server_hash_hex})")
            with self._lock:
                self._server_peers[server_hash_hex] = {
                    "name": name,
                    "description": desc,
                    "hash": server_hash_hex,
                    "last_seen": time.time()
                }
        except Exception as e:
            log.warning(f"Could not parse app_data from announce by {server_hash_hex}: {e}")


    def _link_established(self, link):
        log.info(f"Link established from {R.prettyhexle(link.destination.hash)}")
        link.set_resource_strategy(R.Resource.ACCEPT_ALL) # Adjust resource limits if needed
        link.set_resource_timeout(15) # Timeout for individual packets/responses
        link.set_request_handler(self._handle_request)
        link.set_link_closed_callback(self._link_closed)
        # Store link or relevant info if needed for tracking active clients

    def _link_closed(self, link):
        log.info(f"Link closed from {R.prettyhexle(link.destination.hash)}")
        # Clean up resources associated with this link if any were stored

    def _handle_request(self, link, request_id, data):
        try:
            request = json.loads(data.decode('utf-8'))
            action = request.get("action")
            log.info(f"Received action '{action}' from {R.prettyhexle(link.destination.hash)}")

            response = {"status": STATUS_ERROR, "message": "Unknown error"}

            if action == ACTION_LIST:
                files = os.listdir(self.config['data_dir'])
                response = {"status": STATUS_OK, "files": files}

            elif action == ACTION_GET:
                filename = request.get("filename")
                if not filename:
                     response = {"status": STATUS_ERROR, "message": "Filename missing"}
                else:
                    filepath = os.path.join(self.config['data_dir'], filename)
                    if not os.path.exists(filepath):
                         response = {"status": STATUS_ERROR, "message": "File not found"}
                    elif not os.path.isfile(filepath):
                         response = {"status": STATUS_ERROR, "message": "Not a file"}
                    else:
                        try:
                            # Send metadata first
                            file_size = os.path.getsize(filepath)
                            meta_response = {
                                "status": STATUS_FILE_META,
                                "filename": filename,
                                "size": file_size,
                                "message": "File data follows"
                            }
                            link.respond(request_id, json.dumps(meta_response).encode('utf-8'))
                            log.debug(f"Sent metadata for {filename}, size {file_size}")

                            # Send raw file data using link.send()
                            with open(filepath, "rb") as f:
                                while True:
                                    chunk = f.read(R.Reticulum.MAX_PAYLOAD_SIZE // 2) # Send reasonably sized chunks
                                    if not chunk:
                                        break
                                    log.debug(f"Sending chunk of size {len(chunk)} for {filename}")
                                    link.send(chunk) # Link handles reliability
                            log.info(f"Finished sending file: {filename}")
                            return # Response already sent (metadata + data)

                        except Exception as e:
                            log.error(f"Error reading/sending file {filename}: {e}", exc_info=True)
                            response = {"status": STATUS_ERROR, "message": f"Error reading file: {e}"}
                            # Need to respond to the original request ID even if metadata was sent
                            link.respond(request_id, json.dumps(response).encode('utf-8'))
                            return

            elif action == ACTION_SEARCH:
                query = request.get("query", "").lower()
                results = []
                if query:
                    for filename in os.listdir(self.config['data_dir']):
                        if query in filename.lower():
                            results.append(filename)
                response = {"status": STATUS_OK, "results": results}

            elif action == ACTION_PEER_LIST:
                 with self._lock:
                     # Simple copy, could add filtering for old peers
                     peers = list(self._server_peers.values())
                 response = {"status": STATUS_OK, "peers": peers}

            else:
                response = {"status": STATUS_ERROR, "message": f"Unknown action: {action}"}

            # Send standard JSON response for actions other than GET
            link.respond(request_id, json.dumps(response).encode('utf-8'))
            log.debug(f"Sent response for action '{action}'")

        except json.JSONDecodeError:
            log.warning(f"Received invalid JSON from {R.prettyhexle(link.destination.hash)}")
            link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": "Invalid JSON request"}).encode('utf-8'))
        except Exception as e:
            log.error(f"Error handling request: {e}", exc_info=True)
            try:
                 link.respond(request_id, json.dumps({"status": STATUS_ERROR, "message": f"Internal server error: {e}"}).encode('utf-8'))
            except Exception as link_err:
                 log.error(f"Could not even send error response over link: {link_err}")
