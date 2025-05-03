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

## Notes

* Ensure Reticulum (`rnsd`) is properly configured and running on all participating nodes.
* The `wais_data` directory (or as configured) on the server contains the shared files.
* File transfers send raw binary data. Large files are sent in chunks managed by Reticulum Links.
* Client discovery happens passively in the background. Listing servers shows the current cache.

## Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bug reports or feature requests.

## License

This project is licensed under the GNU General Public License v3.0 - see the [LICENSE](LICENSE) file for details.
