import argparse
import logging
import time
import sys
import threading
import Reticulum as R
from . import config as Cfg
from . import identity as Id
from . import server as Server
from . import client as Client
from .common import common_log, client_log, server_log, STATUS_OK

def setup_logging(level_str='INFO'):
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Suppress Reticulum's verbose logging unless we are in DEBUG mode
    if level > logging.DEBUG:
        logging.getLogger("RNS").setLevel(logging.WARNING)
        logging.getLogger("Transport").setLevel(logging.WARNING)

def main():
    parser = argparse.ArgumentParser(description="Akita WAIS Server/Client for Reticulum")
    parser.add_argument('--config', type=str, default='config.json', help='Path to configuration file')

    subparsers = parser.add_subparsers(dest='mode', required=True, help='Run mode')

    # Server mode
    parser_server = subparsers.add_parser('server', help='Run as a WAIS server')
    parser_server.add_argument('--no-announce', action='store_true', help='Run server without announcing (useful for testing)')

    # Client mode
    parser_client = subparsers.add_parser('client', help='Run as a WAIS client')

    args = parser.parse_args()

    # Load configuration
    config = Cfg.load_config(args.config)
    setup_logging(config['logging']['level'])

    # Initialize Reticulum
    rns_config_dir = config['reticulum'].get('config_dir') # Can be None
    reticulum = R.Reticulum(configdir=rns_config_dir, loglevel=logging.WARNING) # Use RNS logging level based on our config?
    common_log.info(f"Reticulum checksum: {R.LOG_INIT_MSG}") # Display version/checksum

    instance = None
    identity = None

    try:
        if args.mode == 'server':
            identity_path = config['identity']['server_identity_path']
            identity = Id.load_or_create_identity(identity_path)
            if not identity: sys.exit(1)

            instance = Server.AkitaWAISServer(config=config, reticulum_instance=reticulum)
            if instance.start(identity):
                common_log.info("Server started. Press Ctrl+C to exit.")
                while instance.running:
                    time.sleep(1)
            else:
                common_log.critical("Server failed to start.")

        elif args.mode == 'client':
            identity_path = config['identity']['client_identity_path']
            identity = Id.load_or_create_identity(identity_path)
            if not identity: sys.exit(1)

            instance = Client.AkitaWAISClient(config=config, reticulum_instance=reticulum)
            if instance.start(identity):
                run_client_interface(instance) # Start interactive loop
            else:
                 common_log.critical("Client failed to start.")

    except KeyboardInterrupt:
        common_log.info("Shutdown requested.")
    finally:
        if instance:
            instance.stop()
        # Reticulum cleanup happens automatically at exit if not using daemon mode explicitly
        common_log.info("Exiting.")


def run_client_interface(client: Client.AkitaWAISClient):
    """Runs the interactive command-line menu for the client."""
    print("\nWelcome to Akita WAIS Client!")
    selected_server_info = None

    while client.running:
        print("\n--- Client Menu ---")
        if selected_server_info:
            print(f"Connected to: {selected_server_info['name']} ({selected_server_info['hash'][:10]}...)")
            print("1. List Files (on server)")
            print("2. Get File (from server)")
            print("3. Search Files (on server)")
            print("4. List Peers (known by server)")
            print("5. Disconnect from Server")
            print("--------------------")
            print("6. List Discovered Servers")
            print("7. Select Different Server")

        else:
            print("1. List Discovered Servers")
            print("2. Select Server")

        print("0. Exit")
        choice = input("Enter choice: ")

        try:
            if selected_server_info:
                # Actions when connected
                if choice == "1":
                    print("\nRequesting file list...")
                    response = client.get_server_list()
                    if response and response.get("status") == STATUS_OK:
                        print("Files:")
                        if response.get("files"):
                            for f in response["files"]: print(f"- {f}")
                        else: print("(No files found)")
                    else: print(f"Error: {response.get('message', 'Unknown error')}")
                elif choice == "2":
                    filename = input("Enter filename to get: ")
                    if filename:
                         print(f"\nRequesting file '{filename}'...")
                         response = client.get_file(filename)
                         # Response processing happens async, success/error msg printed by callbacks/waiter
                         if response: # Final status message
                            print(f"Transfer final status: {response.get('status')}, Message: {response.get('message')}")
                         else: print("No final status received (check logs).")

                elif choice == "3":
                    query = input("Enter search query: ")
                    if query:
                         print(f"\nSearching for '{query}'...")
                         response = client.search_files(query)
                         if response and response.get("status") == STATUS_OK:
                              print("Search Results:")
                              if response.get("results"):
                                   for r in response["results"]: print(f"- {r}")
                              else: print("(No matching files found)")
                         else: print(f"Error: {response.get('message', 'Unknown error')}")
                elif choice == "4":
                    print("\nRequesting peer list from server...")
                    response = client.get_peer_list()
                    if response and response.get("status") == STATUS_OK:
                         print("Peers known by server:")
                         if response.get("peers"):
                              for p in response["peers"]: print(f"- {p.get('name', 'Unknown')} ({p.get('hash', 'N/A')[:10]}...)")
                         else: print("(Server knows no peers)")
                    else: print(f"Error: {response.get('message', 'Unknown error')}")

                elif choice == "5":
                    if client._active_link: client._active_link.teardown()
                    selected_server_info = None
                    print("Disconnected.")
                elif choice == "6":
                    client.list_discovered_servers()
                elif choice == "7":
                    server_list = client.list_discovered_servers()
                    if server_list:
                        try:
                            s_choice = int(input("Select server number to connect to: ")) - 1
                            if client.select_server(server_list, s_choice):
                                selected_server_info = server_list[s_choice]
                            else:
                                print("Failed to connect.")
                                selected_server_info = None # Ensure state is cleared
                        except ValueError: print("Invalid input.")
                elif choice == "0":
                    client.stop()
                else:
                    print("Invalid choice.")

            else:
                # Actions when not connected
                if choice == "1":
                     client.list_discovered_servers()
                elif choice == "2":
                     server_list = client.list_discovered_servers()
                     if server_list:
                          try:
                               s_choice = int(input("Select server number to connect to: ")) - 1
                               if client.select_server(server_list, s_choice):
                                    selected_server_info = server_list[s_choice]
                               else:
                                    print("Failed to connect.")
                          except ValueError: print("Invalid input.")
                elif choice == "0":
                     client.stop()
                else:
                     print("Invalid choice.")

        except Exception as e:
            client_log.error(f"Error during client loop: {e}", exc_info=True)
            print(f"An unexpected error occurred: {e}")
