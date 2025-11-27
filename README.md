# Akita WAIS for Reticulum

Akita WAIS is a decentralized Wide Area Information Server (WAIS) implementation designed for the Reticulum network stack. It allows users to discover, browse, search (filenames), and retrieve files from servers across a Reticulum mesh securely and efficiently.

**Organization:** Akita Engineering (www.akitaengineering.com)
**License:** GPLv3

## Features

* **Smart Compression (New):**  Automatically detects if files (like text/logs) can be compressed using Zlib before transmission, significantly reducing bandwidth usage on the mesh.

* **Data Integrity (New):**  Every file transfer includes a SHA-256 hash. The client cryptographically verifies the received file to ensure it matches the original bit-for-bit.

* **Non-Blocking Architecture (New):**  File I/O and network transfers run in background threads, ensuring the server remains responsive to discovery requests even while transferring large files.

* **Decentralized Discovery:**  Servers automatically announce their presence using Reticulum Announce; clients automatically discover them without central servers.

* **Reliable Communication:**  Uses Reticulum Links for robust request/response handling.

* **Filename Search:**  Clients can search for files on servers based on keywords.

* **Persistent Identities:**  Server and client Reticulum identities are saved and loaded.


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
3.  **Ensure Reticulum is Running:** Make sure rnsd is configured with appropriate interfaces (e.g., AutoInterface for LAN or LoRaInterface) and running on your system.
4.  **Configure Akita WAIS (Optional):** Copy config.json (if provided) or modify the default settings in akita_wais/config.py if needed. The default configuration usually works out of the box.d.

## Usage

**Running a Server:**

1.  **Start Server:**
    ```bash
    python run.py server
    ```
    * Note: The wais_data directory will be created automatically. Place files you want to share in this folder.
    * Use `python run.py server --no-announce` to run without announcing (for testing).

**Running a Client:**

1.  **Start Client:**
    ```bash
    python run.py client
    ```
2.  **Follow Menu:**
    * The client listens for announcements in the background
    * Use Option 1 to discover servers.
    * Use Option 2 to connect to a selected server.
    * Once connected, use the menu to List, Get, or Search files.

## Terminal 1: Running the Server

```Bash
user@server-box:~/Akita-WAIS$ python run.py server

2025-05-04 14:00:15 INFO [AkitaCommon] Loaded configuration from config.json
2025-05-04 14:00:15 INFO [AkitaCommon] Reticulum Active. Identity: <Identity: a1b2c3...>
2025-05-04 14:00:16 INFO [AkitaServer] Akita WAIS Server Service Ready.
2025-05-04 14:00:16 INFO [AkitaServer] Address: <80 bytes hash...>
# --- Server sits idle, waiting ---
2025-05-04 14:02:05 INFO [AkitaServer] Link established from <Client Hash>
2025-05-04 14:02:06 INFO [AkitaServer] Received action 'list' from <Client Hash>
2025-05-04 14:02:15 INFO [AkitaServer] Received action 'get' from <Client Hash>
2025-05-04 14:02:15 INFO [AkitaServer] Compressed project_plan.txt: 12345 -> 5555 bytes (45.0% of original)
2025-05-04 14:02:16 INFO [AkitaServer] Sent project_plan.txt..
```
## Terminal 2: Running the Client
```Bash
user@client-box:~/Akita-WAIS$ python run.py client

2025-05-04 14:01:30 INFO [AkitaCommon] Loaded configuration from config.json
2025-05-04 14:01:31 INFO [AkitaClient] Akita WAIS Client Ready.

--- Akita WAIS Client (v0.4.0) ---

Main Menu:
1. Discover Servers
2. Connect to Server
0. Exit
> 1

--- Discovered Servers ---
1. Default Akita Server (<Hash...>) - Caps: ['zlib', 'sha256']
-------------------------

> 2
Server #: 1
2025-05-04 14:02:05 INFO [AkitaClient] Connecting to Default Akita Server...
Connected!

Main Menu:
Connected to: Default Akita Server
1. List Files
2. Get File
3. Search Files
...
> 2
Filename: project_plan.txt
Requesting...
2025-05-04 14:02:15 INFO [AkitaClient] Receiving project_plan.txt (5555 bytes)...
2025-05-04 14:02:16 INFO [AkitaClient] Decompressing data...
2025-05-04 14:02:16 INFO [AkitaClient] Verifying integrity...
2025-05-04 14:02:16 INFO [AkitaClient] Integrity Verified (SHA256).
2025-05-04 14:02:16 INFO [AkitaClient] Saved project_plan.txt (12345 bytes).
Result: File project_plan.txt received & verified
```


## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bug reports or feature requests.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
