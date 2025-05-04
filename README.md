# Akita WAIS for Reticulum

Akita WAIS is a decentralized Wide Area Information Server (WAIS) implementation designed for the Reticulum network stack. It allows users to discover, browse, search (filenames), and retrieve files from servers across a Reticulum mesh.

**Organization:** Akita Engineering (www.akitaengineering.com)
**License:** GPLv3

## Features

* **Decentralized Server Discovery:** Servers automatically announce their presence using Reticulum Announce; clients automatically discover them.
* **Reliable Communication:** Uses Reticulum Links for robust request/response handling and file transfers.
* **Peer List Sharing:** Servers can share their list of discovered peers (other servers).
* **Text and Binary File Support:** Handles file transfers correctly using raw byte streams over Links. Supports basic chunking for larger files.
* **Filename Search:** Clients can search for files on servers based on keywords matching filenames.
* **Command-Line Interface:** Simple interactive client menu.
* **Configurable:** Uses a configuration file (`config.json`) and command-line arguments.
* **Persistent Identities:** Server and client Reticulum identities are saved and loaded.
* **Server Caching:** Client caches discovered servers locally.

## Requirements

* Linux Operating System (tested, other OS may work)
* Python 3.7+
* Reticulum Network Stack (`rns`) installed and running (`pip install rns`). See [Reticulum Documentation](https://reticulum.network/manual/) for setup.
* Dependencies: `pip install -r requirements.txt`

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone [https://github.com/AkitaEngineering/Akita-WAIS.git](https://github.com/AkitaEngineering/Akita-WAIS.git)
    cd Akita-WAIS
    ```
2.  **Install Dependencies:**
    ```bash
    pip install -r requirements.txt
    ```
3.  **Ensure Reticulum is Running:** Make sure `rnsd` is configured with appropriate interfaces (e.g., AutoInterface for LAN) and running on your system.
4.  **Configure Akita WAIS:** Copy `config.example.json` to `config.json` and customize settings like server name, data directory, identity paths if desired.

## Usage

**Running a Server:**

1.  **Create Data Directory:** If it doesn't exist, the directory specified in `config.json` (default: `wais_data`) will be created.
2.  **Place Files:** Put files you want to share into the data directory.
3.  **Start Server:**
    ```bash
    python run.py server
    ```
    * Use `python run.py server --no-announce` to run without announcing (for testing).

**Running a Client:**

1.  **Start Client:**
    ```bash
    python run.py client
    ```
2.  **Follow Menu:**
    * The client will automatically listen for server announcements.
    * Use `List Discovered Servers` to see available servers.
    * Use `Select Server` to connect to a server using its number from the list.
    * Once connected, use other options (`List Files`, `Get File`, etc.) to interact with the server.

## Terminal 1: Running the Server

```Bash
user@server-box:~/Akita-WAIS$ python run.py server --config config.json

2025-05-04 14:00:15 INFO [AkitaCommon] Loaded configuration from config.json
2025-05-04 14:00:15 INFO [AkitaCommon] Reticulum checksum: rns-9a8f7b...
2025-05-04 14:00:15 INFO [AkitaCommon] Loaded Identity a1b2c3d4... from akita_server.identity
2025-05-04 14:00:15 INFO [AkitaServer] Creating data directory: wais_data
2025-05-04 14:00:16 INFO [AkitaServer] Listening for peer announcements on aspect: akita.wais.discovery.v1
2025-05-04 14:00:16 INFO [AkitaServer] Akita WAIS Server Service Ready.
2025-05-04 14:00:16 INFO [AkitaServer] Service Destination: a1b2c3d4... (Aspect: akita.wais.service.v1)
2025-05-04 14:00:16 INFO [AkitaServer] Share Directory: /home/user/Akita-WAIS/wais_data
2025-05-04 14:00:16 INFO [AkitaServer] Starting announcements every 60 seconds.
2025-05-04 14:00:16 DEBUG [AkitaServer] Announcing service destination a1b2c3d4...
2025-05-04 14:00:16 INFO [AkitaCommon] Server started. Press Ctrl+C to exit.
# --- Server sits idle, waiting for connections or announces ---
2025-05-04 14:01:16 DEBUG [AkitaServer] Announcing service destination a1b2c3d4...
2025-05-04 14:02:05 INFO [AkitaServer] Link established from e5f6a7b8...
2025-05-04 14:02:06 INFO [AkitaServer] Received action 'list' from e5f6a7b8...
2025-05-04 14:02:06 DEBUG [AkitaServer] Sent response for action 'list'
2025-05-04 14:02:15 INFO [AkitaServer] Received action 'get' from e5f6a7b8...
2025-05-04 14:02:15 DEBUG [AkitaServer] Sent metadata for project_plan.txt, size 12345
2025-05-04 14:02:15 DEBUG [AkitaServer] Sending chunk of size 8192 for project_plan.txt
2025-05-04 14:02:15 DEBUG [AkitaServer] Sending chunk of size 4153 for project_plan.txt
2025-05-04 14:02:15 INFO [AkitaServer] Finished sending file: project_plan.txt
2025-05-04 14:02:20 INFO [AkitaServer] Link closed from e5f6a7b8...
```
## Terminal 2: Running the Client
```Bash
user@client-box:~/Akita-WAIS$ python run.py client --config config.json

2025-05-04 14:01:30 INFO [AkitaCommon] Loaded configuration from config.json
2025-05-04 14:01:30 INFO [AkitaCommon] Reticulum checksum: rns-9a8f7b...
2025-05-04 14:01:31 INFO [AkitaCommon] Loaded Identity e5f6a7b8... from akita_client.identity
2025-05-04 14:01:31 INFO [AkitaClient] Loaded 0 servers from cache: known_servers.cache
2025-05-04 14:01:31 INFO [AkitaClient] Listening for server announcements on aspect: akita.wais.discovery.v1
2025-05-04 14:01:31 INFO [AkitaClient] Akita WAIS Client Ready.

Welcome to Akita WAIS Client!

--- Client Menu ---
1. List Discovered Servers
2. Select Server
0. Exit
Enter choice:  # <-- Waiting for input
# --- An announcement arrives in the background ---
2025-05-04 14:01:45 INFO [AkitaClient] Discovered server: My Akita WAIS Server (a1b2c3d4...)

# --- User types '1' ---
Enter choice: 1

--- Discovered Servers ---
1. My Akita WAIS Server (a1b2c3d4...) - Seen 5s ago
   Desc: Shares files over Reticulum.
-------------------------

--- Client Menu ---
1. List Discovered Servers
2. Select Server
0. Exit
Enter choice: 2
Select server number to connect to: 1
2025-05-04 14:02:05 INFO [AkitaClient] Selected server: My Akita WAIS Server (a1b2c3d4...)
2025-05-04 14:02:05 INFO [AkitaClient] Attempting to establish link to a1b2c3d4... (Aspect: akita.wais.service.v1)
2025-05-04 14:02:05 INFO [AkitaClient] Link established successfully.

--- Client Menu ---
Connected to: My Akita WAIS Server (a1b2c3d4...)
1. List Files (on server)
2. Get File (from server)
3. Search Files (on server)
4. List Peers (known by server)
5. Disconnect from Server
--------------------
6. List Discovered Servers
7. Select Different Server
0. Exit
Enter choice: 1

Requesting file list...
2025-05-04 14:02:06 DEBUG [AkitaClient] Sent request (ID: <req_id_1>): {'action': 'list'}
2025-05-04 14:02:06 DEBUG [AkitaClient] Received response for request <req_id_1>
Files:
- project_plan.txt
- results_data.csv
- image.jpg

--- Client Menu ---
Connected to: My Akita WAIS Server (a1b2c3d4...)
# ... (menu repeats) ...
Enter choice: 2
Enter filename to get: project_plan.txt

Requesting file 'project_plan.txt'...
2025-05-04 14:02:15 DEBUG [AkitaClient] Sent request (ID: <req_id_2>): {'action': 'get', 'filename': 'project_plan.txt'}
2025-05-04 14:02:15 DEBUG [AkitaClient] Received response for request <req_id_2>
2025-05-04 14:02:15 INFO [AkitaClient] Expecting file data for project_plan.txt (12345 bytes)
2025-05-04 14:02:15 DEBUG [AkitaClient] Received 8192 bytes of raw data.
2025-05-04 14:02:15 DEBUG [AkitaClient] Written 8192 bytes to project_plan.txt. Total: 8192/12345
2025-05-04 14:02:15 DEBUG [AkitaClient] Received 4153 bytes of raw data.
2025-05-04 14:02:15 DEBUG [AkitaClient] Written 4153 bytes to project_plan.txt. Total: 12345/12345
2025-05-04 14:02:15 INFO [AkitaClient] File transfer complete for project_plan.txt
2025-05-04 14:02:15 DEBUG [AkitaClient] Received response for request <req_id_2> # This is the completion signal
Transfer final status: ok, Message: File 'project_plan.txt' received.

--- Client Menu ---
Connected to: My Akita WAIS Server (a1b2c3d4...)
# ... (menu repeats) ...
Enter choice: 5
2025-05-04 14:02:20 INFO [AkitaClient] Closing active link to a1b2c3d4...
2025-05-04 14:02:20 WARNING [AkitaClient] Link closed to server a1b2c3d4...
Disconnected.

--- Client Menu ---
1. List Discovered Servers
2. Select Server
0. Exit
Enter choice: 0
2025-05-04 14:02:25 INFO [AkitaCommon] Shutdown requested.
2025-05-04 14:02:25 INFO [AkitaClient] Stopped discovery listener.
2025-05-04 14:02:25 INFO [AkitaClient] Saved 1 servers to cache: known_servers.cache
2025-05-04 14:02:25 INFO [AkitaClient] Akita WAIS Client stopping.
2025-05-04 14:02:25 INFO [AkitaCommon] Exiting.
user@client-box:~/Akita-WAIS$
```

## Notes

* Ensure Reticulum (`rnsd`) is properly configured and running on all participating nodes.
* The `wais_data` directory (or as configured) on the server contains the shared files.
* File transfers send raw binary data. Large files are sent in chunks managed by Reticulum Links.
* Client discovery happens passively in the background. Listing servers shows the current cache.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bug reports or feature requests.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
