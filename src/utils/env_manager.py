import os
from pathlib import Path
from dotenv import load_dotenv, set_key

# Define the root .env path
ROOT_DIR = Path(__file__).parent.parent.parent
ENV_PATH = ROOT_DIR / ".env"

def init_env():
    """Ensure .env exists by copying from .env.example if missing."""
    if not ENV_PATH.exists():
        example_path = ROOT_DIR / ".env.example"
        if example_path.exists():
            with open(example_path, "r") as src, open(ENV_PATH, "w") as dst:
                dst.write(src.read())
    load_dotenv(ENV_PATH)

def get_env_var(key, default=None):
    """Retrieve a value from the .env file."""
    return os.environ.get(key, default)

def update_env_vars(updates: dict):
    """
    Update multiple keys in the .env file.
    
    Args:
        updates (dict): Dictionary of key-value pairs to set in .env
    """
    if not ENV_PATH.exists():
        # Create an empty .env if it doesn't exist
        ENV_PATH.touch()

    for key, value in updates.items():
        # Ensure value is a string
        val_str = str(value) if value is not None else ""
        set_key(str(ENV_PATH), key, val_str)
    
    # Reload environment variables after update
    load_dotenv(ENV_PATH, override=True)

def clear_connection_env():
    """Clear all connection-related variables from .env."""
    conn_keys = [
        "DEFAULT_CONN_TYPE",
        "DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASS", "DB_ENGINE", "DB_TABLE",
        "SF_ACCOUNT", "SF_WH", "SF_DB", "SF_SCHEMA", "SF_TABLE", "SF_USER", "SF_PASS",
        "FILE_PATH", "FILE_FORMAT", "FILE_SHEET",
        "API_URL", "API_TOKEN", "API_HKEY", "API_JPATH", "API_METHOD"
    ]
    update_env_vars({k: "" for k in conn_keys})
