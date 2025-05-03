import json
import os
from .common import common_log

DEFAULT_CONFIG = {
  "reticulum": {"config_dir": None },
  "logging": {"level": "INFO"},
  "identity": {
    "server_identity_path": "akita_server.identity",
    "client_identity_path": "akita_client.identity"
  },
  "discovery": {"aspect": "akita.wais.discovery.v1"},
  "server": {
    "data_dir": "wais_data",
    "service_aspect": "akita.wais.service.v1",
    "announce_interval_sec": 60,
    "server_info": {
        "name": "Default Akita Server",
        "description": "Shares files over Reticulum.",
        "keywords": ["files", "akita"]
    }
  },
  "client": {
    "request_timeout_sec": 20,
    "server_cache_path": "known_servers.cache"
  }
}

def load_config(config_path="config.json"):
    """Loads configuration from a JSON file, merging with defaults."""
    config = DEFAULT_CONFIG.copy() # Start with defaults
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                user_config = json.load(f)
                # Simple merge (could be made recursive/deep)
                for section, settings in user_config.items():
                    if section in config:
                        config[section].update(settings)
                    else:
                        config[section] = settings # Add new sections if any
            common_log.info(f"Loaded configuration from {config_path}")
        except Exception as e:
            common_log.error(f"Error loading config file {config_path}: {e}. Using defaults.", exc_info=True)
    else:
        common_log.warning(f"Config file {config_path} not found. Using default configuration.")
    return config
