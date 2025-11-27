import Reticulum as R
import os
from .common import common_log

def load_or_create_identity(identity_path):
    """Loads a Reticulum Identity or creates a new one."""
    if os.path.exists(identity_path):
        try:
            identity = R.Identity.from_file(identity_path)
            if identity:
                common_log.info(f"Loaded Identity {identity.hash} from {identity_path}")
                return identity
        except Exception as e:
            common_log.error(f"Error loading identity from {identity_path}: {e}")

    common_log.info(f"No valid identity found at {identity_path}, creating new one.")
    try:
        identity = R.Identity()
        identity.to_file(identity_path)
        common_log.info(f"Created and saved new Identity {identity.hash} to {identity_path}")
        return identity
    except Exception as e:
        common_log.error(f"Could not save new identity to {identity_path}: {e}")
        return None
