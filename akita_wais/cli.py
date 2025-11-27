import argparse
import logging
import time
import sys
import Reticulum as R
from . import config as Cfg
from . import identity as Id
from . import server as Server
from . import client as Client
from .common import common_log, STATUS_OK

def setup_logging(level_str='INFO'):
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    if level > logging.DEBUG:
        logging.getLogger("RNS").setLevel(logging.WARNING)

def run_client_interface(client):
    print("\n--- Akita WAIS Client (v0.4.0) ---")
    selected_server = None

    while client.running:
        print("\nMain Menu:")
        if selected_server:
            print(f"Connected to: {selected_server['name']}")
            print("1. List Files")
            print("2. Get File")
            print("3. Search Files")
            print("4. Get Peer List")
            print("5. Disconnect")
        else:
            print("1. Discover Servers")
            print("2. Connect to Server")
        print("0. Exit")
        
        choice = input("> ")

        try:
            if selected_server:
                if choice == "1":
                    res = client.get_server_list()
                    if res.get("status") == STATUS_OK:
                        print("Files:", res.get("files", []))
                    else: print("Error:", res.get("message"))
                
                elif choice == "2":
                    fname = input("Filename: ")
                    print("Requesting...")
                    res = client.get_file(fname)
                    print("Result:", res.get("message"))

                elif choice == "3":
                    q = input("Query: ")
                    res = client.search_files(q)
                    print("Results:", res.get("results", []))

                elif choice == "4":
                    res = client.get_peer_list()
                    peers = res.get("peers", [])
                    print(f"Peers ({len(peers)}):")
                    for p in peers: print(f"- {p['name']} ({p['hash'][:8]}...)")

                elif choice == "5":
                    selected_server = None
                    # Client logic handles disconnection internally on next connect

            else:
                if choice == "1":
                    servers = client.list_discovered_servers()
                    for i, s in enumerate(servers):
                        print(f"{i+1}. {s['name']} - Caps: {s.get('caps', [])}")
                
                elif choice == "2":
                    servers = client.list_discovered_servers()
                    if not servers:
                        print("No servers found.")
                        continue
                    try:
                        idx = int(input("Server #: ")) - 1
                        if 0 <= idx < len(servers):
                            if client.select_server(servers[idx]):
                                selected_server = servers[idx]
                                print("Connected!")
                            else: print("Connection failed.")
                        else: print("Invalid number.")
                    except ValueError: print("Invalid input.")

            if choice == "0": 
                client.stop()
                break

        except Exception as e:
            print(f"UI Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="Akita WAIS - Decentralized File System for RNS")
    parser.add_argument('--config', type=str, default='config.json', help='Configuration file path')

    subparsers = parser.add_subparsers(dest='mode', required=True, help='Mode: server or client')
    
    srv_parser = subparsers.add_parser('server', help='Start WAIS Server')
    srv_parser.add_argument('--no-announce', action='store_true', help='Disable announcements')
    
    cli_parser = subparsers.add_parser('client', help='Start WAIS Client')

    args = parser.parse_args()
    config = Cfg.load_config(args.config)
    setup_logging(config['logging']['level'])

    # Init RNS
    rns_config = config['reticulum'].get('config_dir')
    reticulum = R.Reticulum(configdir=rns_config, loglevel=logging.WARNING)
    common_log.info(f"Reticulum Active. Identity: {R.LOG_INIT_MSG}")

    instance = None
    try:
        if args.mode == 'server':
            id_path = config['identity']['server_identity_path']
            identity = Id.load_or_create_identity(id_path)
            if not identity: sys.exit(1)

            instance = Server.AkitaWAISServer(config, reticulum)
            if instance.start(identity):
                common_log.info("Server running. Ctrl+C to stop.")
                while instance.running: time.sleep(1)
            else:
                common_log.error("Server start failed.")

        elif args.mode == 'client':
            id_path = config['identity']['client_identity_path']
            identity = Id.load_or_create_identity(id_path)
            if not identity: sys.exit(1)

            instance = Client.AkitaWAISClient(config, reticulum)
            if instance.start(identity):
                run_client_interface(instance)
            else:
                common_log.error("Client start failed.")

    except KeyboardInterrupt:
        common_log.info("Shutdown requested.")
    finally:
        if instance: instance.stop()
        common_log.info("Exited.")
