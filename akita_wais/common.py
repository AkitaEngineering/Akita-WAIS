import logging

# Protocol Version (Informational)
PROTOCOL_VERSION = "0.3.0-beta"

# Reticulum Aspects (Crucial for addressing)
# Used for Announce packets for discovering servers
ASPECT_DISCOVERY = "akita.wais.discovery.v1"
# Used for the server's main service destination (TYPE_SINGLE)
ASPECT_SERVICE = "akita.wais.service.v1"

# Loggers
server_log = logging.getLogger("AkitaServer")
client_log = logging.getLogger("AkitaClient")
common_log = logging.getLogger("AkitaCommon")

# Action types in requests/responses
ACTION_LIST = "list"
ACTION_GET = "get"
ACTION_SEARCH = "search"
ACTION_PEER_LIST = "peer_list" # Renamed from server_list for clarity

# Status codes in responses
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_FILE_META = "file_meta" # Special status for get response metadata

# Max announce app_data size (check Reticulum limits if needed)
MAX_ANNOUNCE_SIZE = 128 # Bytes, adjust as needed
