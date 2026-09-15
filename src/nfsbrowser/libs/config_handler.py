import json
import os

from root import ROOT


class ConfigHandler:
    def __init__(self, filepath=os.path.join(os.path.expanduser("~"), "nfsbrowser", "config.json")):
        """Initializes the handler with a file path."""
        self.filepath = filepath
        self._ensure_file_exists()

    def _ensure_file_exists(self):
        """Creates an empty JSON file if one does not already exist."""
        if not os.path.exists(self.filepath):
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, "w") as f:
                json.dump({}, f)

    def load(self):
        """Loads and returns the current configuration as a dictionary."""
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            return {}

    def save(self, data):
        """Saves the provided dictionary to the JSON file."""
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=4)

    def get(self, key=None, default=None):
        """
        Retrieves a specific key's value.
        If no key is provided, returns the entire configuration dictionary.
        """
        config = self.load()
        if key is None:
            return config
        return config.get(key, default)

    def update(self, new_data):
        """
        Updates the configuration with a dictionary and saves the changes.
        """
        if not isinstance(new_data, dict):
            raise ValueError("Data passed to update() must be a dictionary.")

        config = self.load()
        config.update(new_data)
        self.save(config)


config_handler = ConfigHandler()
