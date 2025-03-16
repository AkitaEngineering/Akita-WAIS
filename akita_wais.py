# akita_wais.py
import Reticulum as R
import os
import json
import threading
import time
import sys

class AkitaWAISServer:
    def __init__(self, interface=None, port=8888, directory="wais_data"):
        self.interface = interface
        self.port = port
        self.directory = directory
        self.servers = {}
        self.lock = threading.Lock()
        self.identity = R.Identity()
        self.destination = R.Destination(self.identity, R.Destination.TYPE_GROUP, "akita.wais.server", reliability=True)
        self.announce_destination = R.Destination(self.identity, R.Destination.TYPE_GROUP, "akita.wais.announce", reliability=False)

        if not os.path.exists(self.directory):
            os.makedirs(self.directory)

        self.register_handlers()
        self.start_discovery()

    def register_handlers(self):
        self.destination.register_incoming(self.handle_request)
        self.announce_destination.register_incoming(self.handle_announce)

    def handle_request(self, destination, packet):
        try:
            request = json.loads(packet["content"].decode("utf-8"))
            action = request.get("action")

            if action == "list":
                self.handle_list(destination)
            elif action == "get":
                self.handle_get(destination, request.get("filename"))
            elif action == "search":
                self.handle_search(destination, request.get("query"))
            elif action == "server_list":
                self.handle_server_list(destination)

        except Exception as e:
            print(f"Server Error handling request: {e}")

    def handle_announce(self, destination, packet):
        try:
            announce = json.loads(packet["content"].decode("utf-8"))
            address = packet["source"]
            name = announce.get("name")
            description = announce.get("description")
            keywords = announce.get("keywords", [])

            with self.lock:
                self.servers[address] = {"name": name, "description": description, "keywords": keywords}
            print(f"Server Discovered server: {name} at {address}")

        except Exception as e:
            print(f"Server Error handling announce: {e}")

    def handle_list(self, destination):
        files = os.listdir(self.directory)
        response = {"files": files}
        self.send_response(destination, response)

    def handle_get(self, destination, filename):
        filepath = os.path.join(self.directory, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                self.send_response(destination, {"content": content})
            except UnicodeDecodeError:
                with open(filepath, "rb") as f:
                    content = f.read().decode('latin-1','ignore')
                self.send_response(destination, {"content": content})

        else:
            self.send_response(destination, {"error": "File not found"})

    def handle_search(self, destination, query):
        results = []
        for filename in os.listdir(self.directory):
            if query.lower() in filename.lower():
                results.append(filename)
        self.send_response(destination, {"results": results})

    def handle_server_list(self, destination):
        with self.lock:
            self.send_response(destination, {"servers": self.servers})

    def send_response(self, destination, response):
        R.Transport.send(destination, json.dumps(response).encode("utf-8"))

    def announce_self(self):
        announce = {
            "name": "My Akita WAIS Server",
            "description": "A Reticulum-based WAIS server.",
            "keywords": ["Reticulum", "WAIS", "Akita"],
        }
        R.Transport.send(self.announce_destination, json.dumps(announce).encode("utf-8"))

    def start_discovery(self):
        def discovery_loop():
            while True:
                self.announce_self()
                time.sleep(30)

        threading.Thread(target=discovery_loop, daemon=True).start()

    def run(self):
        print(f"Akita WAIS Server running on port {self.port}")
        while True:
            time.sleep(1)

class AkitaWAISClient:
    def __init__(self, interface=None):
        self.interface = interface
        self.identity = R.Identity()
        self.server_destination = None
        self.servers = {}
        self.lock = threading.Lock()
        self.announce_destination = R.Destination(self.identity, R.Destination.TYPE_GROUP, "akita.wais.announce", reliability=False)
        self.announce_destination.register_incoming(self.handle_announce)

    def handle_announce(self, destination, packet):
        try:
            announce = json.loads(packet["content"].decode("utf-8"))
            address = packet["source"]
            name = announce.get("name")
            description = announce.get("description")
            keywords = announce.get("keywords", [])

            with self.lock:
                self.servers[address] = {"name": name, "description": description, "keywords": keywords}
            print(f"Client Discovered server: {name} at {address}")

        except Exception as e:
            print(f"Client Error handling announce: {e}")

    def discover_servers(self):
        print("Discovering Akita WAIS servers...")
        time.sleep(5)
        for address, server_info in self.servers.items():
            print(f"Server: {server_info['name']} at {address}")

    def select_server(self):
        if not self.servers:
            print("No servers found.")
            return None

        print("Available servers:")
        for i, (address, server_info) in enumerate(self.servers.items()):
            print(f"{i + 1}. {server_info['name']} ({address})")

        while True:
            try:
                choice = int(input("Select server: ")) - 1
                if 0 <= choice < len(self.servers):
                    address = list(self.servers.keys())[choice]
                    self.server_destination = R.Destination(None, R.Destination.TYPE_SINGLE, address)
                    return True
                else:
                    print("Invalid choice.")
            except ValueError:
                print("Invalid input.")

    def list_files(self):
        if not self.server_destination:
            print("No server selected.")
            return

        request = {"action": "list"}
        R.Transport.send(self.server_destination, json.dumps(request).encode("utf-8"))
        packet = R.Transport.await_packet(self.server_destination, 10)
        if packet:
            response = json.loads(packet["content"].decode("utf-8"))
            if "files" in response:
                print("Files:")
                for file in response["files"]:
                    print(f"- {file}")
            else:
                print(f"Error: {response.get('error')}")
        else:
            print('Server timed out')

    def get_file(self, filename):
        if not self.server_destination:
            print("No server selected.")
            return

        request = {"action": "get", "filename": filename}
        R.Transport.send(self.server_destination, json.dumps(request).encode("utf-8"))
        packet = R.Transport.await_packet(self.server_destination, 10)
        if packet:
            response = json.loads(packet["content"].decode("utf-8"))
            if "content" in response:
                print(response["content"])
            else:
                print(f"Error: {response.get('error')}")
        else:
            print('Server timed out')

    def search_files(self, query):
        if not self.server_destination:
            print("No server selected.")
            return

        request = {"action": "search", "query": query}
        R.Transport.send(self.server_destination, json.dumps(request).encode("utf-8"))
        packet = R.Transport.await_packet(self.server_destination, 10)
        if packet:
            response = json.loads(packet["content"].decode("utf-8"))
            if "results" in response: # Corrected indentation
                print("Search results:")
                for result in response["results"]:
                    print(f"- {result}")
            else: # Corrected indentation
                print(f"Error: {response.get('error')}")
        else:
            print('Server timed out')

    def get_server_list(self):
        if not self.server_destination:
            print("No server selected.")
            return

        request = {"action": "server_list"}
        R.Transport.send(self.server_destination, json.dumps(request).encode("utf-8"))
        packet = R.Transport.await_packet(self.server_destination, 10)
        if packet:
            response = json.loads(packet["content"].decode("utf-8"))
            if "servers" in response:
                print("Connected Server's known Servers:")
                for address, server_info in response["servers"].items():
                    print(f"- {server_info['name']} ({address})")
            else:
                print(f"Error: {response.get('error')}")
        else:
            print('Server timed out')

    def run(self):
        self.discover_servers()
        if self.select_server():
            while True:
                print("\nAkita WAIS Client Menu:")
                print("1. List files")
                print("2. Get file")
                print("3. Search files")
                print("4. Get server list")
                print("5. Select another Server")
                print("0. Exit")

                choice = input("Enter choice: ")
                if choice == "1":
                    self.list_files()
                elif choice == "2":
                    filename = input("Enter filename: ")
                    self.get_file(filename)
                elif choice == "3":
                    query = input("Enter search query: ")
                    self.search_files(query)
                elif choice == "4":
                    self.get_server_list()
                elif choice == "5":
                    self.select_server()
                elif choice == "0":
                    break
                else:
                    print("Invalid choice.")
        else:
            print("Client Exiting.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "server":
        server = AkitaWAISServer()
        server.run()
    else:
        client = AkitaWAISClient()
        client.run()
