import argparse
import logging
import os
import time
import sys
import RNS as R
from . import config as Cfg
from . import identity as Id
from . import server as Server
from . import client as Client
from .common import common_log, STATUS_OK

def _get_reticulum_config_file(config_dir):
    if config_dir:
        return os.path.join(os.path.expanduser(config_dir), "config")
    return os.path.expanduser("~/.reticulum/config")

def _reticulum_value_is_enabled(value):
    return value.strip().lower() not in {"no", "false", "0", "off", "disabled"}

def _normalize_reticulum_path(path_value):
    return os.path.expandvars(os.path.expanduser(path_value.strip().strip('"').strip("'")))

def _find_missing_reticulum_ports(config_dir):
    config_file = _get_reticulum_config_file(config_dir)
    if not os.path.isfile(config_file):
        return config_file, []

    interfaces = []
    current_interface = None
    in_interfaces_section = False

    def flush_current_interface():
        nonlocal current_interface
        if current_interface:
            interfaces.append(current_interface)
            current_interface = None

    with open(config_file, 'r') as config_handle:
        for raw_line in config_handle:
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue

            if line.startswith("[[") and line.endswith("]]"):
                if in_interfaces_section:
                    flush_current_interface()
                    current_interface = {"name": line[2:-2].strip()}
                continue

            if line.startswith("[") and line.endswith("]") and not line.startswith("[["):
                flush_current_interface()
                in_interfaces_section = line[1:-1].strip().lower() == "interfaces"
                continue

            if in_interfaces_section and current_interface and "=" in line:
                key, value = line.split("=", 1)
                current_interface[key.strip().lower()] = value.strip()

    flush_current_interface()

    missing_ports = []
    for interface in interfaces:
        if not _reticulum_value_is_enabled(interface.get("enabled", "yes")):
            continue

        port = interface.get("port")
        if not port:
            continue

        normalized_port = _normalize_reticulum_path(port)
        if normalized_port.startswith(os.sep) or port.strip().startswith("~"):
            if not os.path.exists(normalized_port):
                missing_ports.append((interface.get("name", "<unnamed>"), normalized_port))

    return config_file, missing_ports

def _format_reticulum_init_error(config_dir, exc):
    config_file = _get_reticulum_config_file(config_dir)
    details = [
        f"Reticulum failed to initialize using {config_file}.",
        f"Underlying error: {exc}",
    ]

    if not config_dir:
        details.append(
            "Akita WAIS is using the default Reticulum config because reticulum.config_dir is not set in the WAIS config."
        )

    details.append(
        "Check the enabled interfaces in that Reticulum config and disable or correct any unavailable devices, or set reticulum.config_dir to a different Reticulum config directory."
    )
    return " ".join(details)

def _get_repo_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def _get_repo_venv_python():
    return os.path.join(_get_repo_root(), "venv", "bin", "python")

def _rerun_web_mode_with_repo_venv():
    venv_python = _get_repo_venv_python()
    current_python = os.path.abspath(sys.executable)
    script_path = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else os.path.join(_get_repo_root(), "run.py")

    if (
        os.path.isfile(venv_python)
        and os.access(venv_python, os.X_OK)
        and os.path.abspath(venv_python) != current_python
        and os.environ.get("AKITA_WAIS_VENV_REEXEC") != "1"
    ):
        common_log.warning(
            f"Flask is not available in {current_python}. Re-running web mode with {venv_python}."
        )
        env = os.environ.copy()
        env["AKITA_WAIS_VENV_REEXEC"] = "1"
        os.execvpe(venv_python, [venv_python, script_path, *sys.argv[1:]], env)

    common_log.error(
        f"Web mode requires Flask in the active Python interpreter ({current_python}). "
        f"Install dependencies with '{current_python} -m pip install -r requirements.txt' or run '{venv_python} {script_path} web'."
    )
    sys.exit(1)

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

    web_parser = subparsers.add_parser('web', help='Start WAIS Web UI Client')

    args = parser.parse_args()
    config = Cfg.load_config(args.config)
    setup_logging(config['logging']['level'])

    # Init RNS
    rns_config = config['reticulum'].get('config_dir')
    rns_config_file, missing_ports = _find_missing_reticulum_ports(rns_config)
    if missing_ports:
        missing_port_list = ", ".join(
            f"{name} -> {port}" for name, port in missing_ports
        )
        message = [
            f"Reticulum config {rns_config_file} enables unavailable device paths: {missing_port_list}.",
            "Disable or correct those interfaces, or set reticulum.config_dir in your WAIS config to a different Reticulum config directory.",
        ]
        if not rns_config:
            message.insert(
                1,
                "Akita WAIS is using the default Reticulum config because reticulum.config_dir is not set in the WAIS config.",
            )
        common_log.error(" ".join(message))
        sys.exit(1)

    try:
        reticulum = R.Reticulum(configdir=rns_config, loglevel=logging.WARNING)
    except Exception as exc:
        common_log.error(_format_reticulum_init_error(rns_config, exc))
        sys.exit(1)
    common_log.info("Reticulum Active.")

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

        elif args.mode == 'web':
            try:
                from . import web_app
            except ModuleNotFoundError as exc:
                if exc.name == 'flask':
                    _rerun_web_mode_with_repo_venv()
                raise
            id_path = config['identity']['client_identity_path']
            identity = Id.load_or_create_identity(id_path)
            if not identity: sys.exit(1)

            instance = Client.AkitaWAISClient(config, reticulum)
            if instance.start(identity):
                web_app.start_server(instance, host='0.0.0.0', port=5000)
            else:
                common_log.error("Web Client start failed.")

    except KeyboardInterrupt:
        common_log.info("Shutdown requested.")
    finally:
        if instance: instance.stop()
        common_log.info("Exited.")
