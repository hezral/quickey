import json
import logging
from gi.repository import Gio
from .sub_utils.logging_util import get_logger

logger = get_logger("config_manager")

class ConfigManager:
    """Handles GSettings and Button Configuration Logic"""
    
    def __init__(self, settings: Gio.Settings):
        self.settings = settings
        
    def load_configured_buttons(self):
        """Loads and normalizes button configuration from GSettings"""
        json_str = self.settings.get_string("buttons-json")
        try:
            buttons = json.loads(json_str)
        except Exception:
            buttons = []
        
        # Validation and Padding
        if not buttons or not isinstance(buttons, list):
             logger.warning("Loaded buttons data is invalid or empty. Using empty list.")
             buttons = []

        # Ensure we have exactly 8 slots
        final_buttons = [None] * 8
        
        # Fill with saved config
        for i, btn in enumerate(buttons):
            if i < 8:
                final_buttons[i] = btn

        # Normalize and Fill Empty Slots
        for i in range(8):
            if not final_buttons[i]:
                final_buttons[i] = self._create_empty_slot()
                
        return final_buttons

    def save_buttons(self, buttons):
        """Saves values to GSettings"""
        try:
            # Ensure it's 8 slots before saving, just in case
            while len(buttons) < 8:
                buttons.append(self._create_empty_slot())
            buttons = buttons[:8] # Strict limit
            
            json_str = json.dumps(buttons)
            self.settings.set_string("buttons-json", json_str)
            logger.info("Button configuration saved.")
        except Exception as e:
            logger.error(f"Failed to save buttons: {e}")

    def reset_slot(self, index):
        """Clear a slot by setting it to Empty and saving"""
        buttons = self.load_configured_buttons()
        if 0 <= index < 8:
            buttons[index] = self._create_empty_slot()
            self.save_buttons(buttons)

    def reset_to_defaults(self):
        """Resets buttons to default schema value"""
        logger.info("Resetting buttons to default configuration.")
        self.settings.reset("buttons-json")

    def _create_empty_slot(self):
        return {"name": "Empty", "icon": "list-add-symbolic", "type": "empty", "action": ""}
