import logging
import hashlib
import zlib

# Protocol Version
PROTOCOL_VERSION = "0.4.0"

# Reticulum Aspects
ASPECT_DISCOVERY = "akita.wais.discovery.v1"
ASPECT_SERVICE = "akita.wais.service.v1"

# Loggers
server_log = logging.getLogger("AkitaServer")
client_log = logging.getLogger("AkitaClient")
common_log = logging.getLogger("AkitaCommon")

# Action types
ACTION_LIST = "list"
ACTION_GET = "get"
ACTION_SEARCH = "search"
ACTION_PEER_LIST = "peer_list"

# Status codes
STATUS_OK = "ok"
STATUS_ERROR = "error"
STATUS_FILE_META = "file_meta"

# Configuration Constants
MAX_ANNOUNCE_SIZE = 128
MAX_TRANSFER_RAM = 20 * 1024 * 1024  # 20MB limit for in-memory compression

def calculate_sha256(data_bytes):
    """Helper to calculate SHA256 hash of bytes for integrity verification."""
    sha256_hash = hashlib.sha256()
    sha256_hash.update(data_bytes)
    return sha256_hash.hexdigest()
