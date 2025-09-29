"""
app_dirs.py

Manages application directories in the current user's home directory.

Provides a clean and centralized structure for:

    <base>/
        data/   - persistent data (databases, reports, logs)
        config/ - configuration files (JSON, YAML, TOML)

Automatically creates directories if they do not exist.
Each user gets their own isolated storage.
"""

import os


class AppDirs:
    """
    Encapsulates the writable directory for the application in the current user's home.

    Structure:
        <base>/
            /          - all persistent data (databases, reports, logs, etc.)
            config/    - configuration files
    """

    def __init__(self, tool_name: str):
        self.tool_name = tool_name.lower()
        home = os.path.expanduser("~")
        self.base = os.path.join(home, ".penterep", f".{self.tool_name}")

        self.data_dir = os.path.join(self.base)
        self.config_dir = os.path.join(self.base, "config")

        # Create directories if they don't exist
        for path in [self.data_dir, self.config_dir]:
            os.makedirs(path, exist_ok=True)

    def get_path(self, *parts: str) -> str:
        """
        Build a full path under data_dir and create parent directories if needed.

        Args:
            *parts: sequence of folder names and optional file name

        Returns:
            Full path as string
        """
        full_path = os.path.join(self.data_dir, *parts)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        return full_path

    def get_base_dir(self) -> str:
        return self.base

    def get_data_dir(self) -> str:
        return self.data_dir

    def get_config_dir(self) -> str:
        return self.config_dir