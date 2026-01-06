# SPDX-License-Identifier: GPL-3.0-or-later
# Preferences Window
# Ported to GTK 4 with new premium styling

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject
from .config_manager import ConfigManager

class PreferencesWindow(Gtk.Window):
    def __init__(self, parent):
        super().__init__(transient_for=parent)
        self.set_title("Preferences")
        self.set_default_size(500, 600)
        self.set_modal(True)
        self.set_resizable(False)

        self.app = parent.app
        self.loading = True
        self.config_manager = ConfigManager()

        # Scrolled Window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.NEVER)
        self.set_child(self.scrolled_window)

        # Main Box
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.main_box.set_margin_top(20)
        self.main_box.set_margin_bottom(12)
        self.main_box.set_margin_start(20)
        self.main_box.set_margin_end(20)
        self.scrolled_window.set_child(self.main_box)

        # --- Transcription Section ---
        self.provider_setting = SubSettings(
            type="dropdown", 
            name="provider", 
            label="Provider", 
            sublabel="Choose transcription service", 
            separator=True,
            params=(["OpenAI", "Groq Transcription", "Groq Translation"],)
        )

        # OpenAI specific settings
        self.openai_api_key = SubSettings(
            type="entry",
            name="openai-api-key",
            label="OpenAI API Key",
            sublabel="Secret key for OpenAI",
            separator=True
        )

        self.openai_model = SubSettings(
            type="dropdown",
            name="openai-model",
            label="OpenAI Model",
            sublabel="Choose model (whisper-1 is standard)",
            separator=True,
            params=(["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"],)
        )

        # Groq specific settings
        self.groq_api_key = SubSettings(
            type="entry",
            name="groq-api-key",
            label="Groq API Key",
            sublabel="Secret key for Groq",
            separator=True
        )

        self.groq_model = SubSettings(
            type="dropdown",
            name="groq-model",
            label="Groq Model",
            sublabel="Performance vs Speed",
            separator=True,
            params=(["whisper-large-v3", "whisper-large-v3-turbo"],)
        )

        self.language_setting = SubSettings(
            type="entry",
            name="language",
            label="Language",
            sublabel="ISO code (e.g. 'en', 'it') or empty for auto-detect",
            separator=False
        )

        transcription_group = SettingsGroup("Transcription", (
            self.provider_setting, 
            self.openai_api_key, self.openai_model,
            self.groq_api_key, self.groq_model,
            self.language_setting
        ))
        self.main_box.append(transcription_group)

        # Connect provider dropdown
        self.provider_setting.dropdown.connect("notify::selected", self.on_provider_changed)
        # Initial call to set visibility
        self.on_provider_changed(self.provider_setting.dropdown, None)

        # --- Behavior Section ---
        timeout_setting = SubSettings(
            type="spinbutton",
            name="timeout",
            label="Recording Timeout",
            sublabel="Max duration in seconds (0-300)",
            separator=True,
            params=(0, 300, 1) # min, max, step
        )

        injection_mode = SubSettings(
            type="dropdown",
            name="injection-mode",
            label="Injection Mode",
            sublabel="How text is inserted into active window",
            separator=True,
            params=(["fallback", "clipboard", "type"],)
        )

        restore_clipboard = SubSettings(
            type="switch",
            name="restore-clipboard",
            label="Restore Clipboard",
            sublabel="Restore original clipboard after injection",
            separator=False
        )

        behavior_group = SettingsGroup("Behavior", (timeout_setting, injection_mode, restore_clipboard))
        self.main_box.append(behavior_group)

        # --- System Section ---
        notif_setting = SubSettings(
            type="switch",
            name="notifications",
            label="Enable Notifications",
            sublabel="Show desktop notifications for transcription status",
            separator=True
        )

        logging_setting = SubSettings(
            type="switch",
            name="debug-logging",
            label="Debug Logging",
            sublabel="Enable debug output for troubleshooting",
            separator=False
        )

        verbose_logging_setting = SubSettings(
            type="checkbutton",
            name="verbose-logging",
            label=None,
            sublabel=None,
            separator=False,
            params=("Verbose logging",)
        )

        system_group = SettingsGroup("System", (notif_setting, logging_setting, verbose_logging_setting))
        self.main_box.append(system_group)

        # Connect all settings for auto-save
        self.all_subsettings = []
        for group in (transcription_group, behavior_group, system_group):
            for subsetting in group.subsettings:
                self.all_subsettings.append(subsetting)
                subsetting.connect("changed", self.on_setting_changed)

        self.load_settings()
        self.loading = False

    def load_settings(self):
        config = self.config_manager.get_config()
        
        # Helper to get nested config
        def get_val(section, key, default=""):
            return config.get(section, {}).get(key, default)

        # Provider mapping
        p_map = {"openai": 0, "groq-transcription": 1, "groq-translation": 2}
        p_val = get_val("transcription", "provider", "openai")
        self.provider_setting.set_value(p_map.get(p_val, 0))

        # Transcription fields
        openai_key = get_val("transcription", "openai_api_key", "")
        openai_model = get_val("transcription", "openai_model", "whisper-1")
        groq_key = get_val("transcription", "groq_api_key", "")
        groq_model = get_val("transcription", "groq_model", "whisper-large-v3")
        
        # Fallback to general api_key/model if specialized keys are missing
        if not openai_key and p_val == "openai":
            openai_key = get_val("transcription", "api_key", "")
        if not openai_model and p_val == "openai":
            openai_model = get_val("transcription", "model", "whisper-1")
            
        if not groq_key and p_val.startswith("groq"):
            groq_key = get_val("transcription", "api_key", "")
        if not groq_model and p_val.startswith("groq"):
            groq_model = get_val("transcription", "model", "whisper-large-v3")

        self.openai_api_key.set_value(openai_key)
        o_map = {"whisper-1": 0, "gpt-4o-transcribe": 1, "gpt-4o-mini-transcribe": 2}
        self.openai_model.set_value(o_map.get(openai_model, 0))
        self.groq_api_key.set_value(groq_key)
        
        g_map = {"whisper-large-v3": 0, "whisper-large-v3-turbo": 1}
        self.groq_model.set_value(g_map.get(groq_model, 0))
        
        self.language_setting.set_value(get_val("transcription", "language", ""))

        # Behavior
        timeout_str = get_val("recording", "timeout", "10s")
        try:
            # Simple parser for "10s", "5m"
            if timeout_str.endswith("s"):
                t_val = int(timeout_str[:-1])
            elif timeout_str.endswith("m"):
                t_val = int(timeout_str[:-1]) * 60
            else:
                t_val = int(timeout_str)
        except:
            t_val = 10
        
        for s in self.all_subsettings:
            if s.name == "timeout":
                s.set_value(t_val)
            elif s.name == "injection-mode":
                m_map = {"fallback": 0, "clipboard": 1, "type": 2}
                s.set_value(m_map.get(get_val("injection", "mode", "fallback"), 0))
            elif s.name == "restore-clipboard":
                s.set_value(get_val("injection", "restore_clipboard", True))
            elif s.name == "notifications":
                s.set_value(get_val("notifications", "enabled", True))
            elif s.name == "debug-logging":
                s.set_value(get_val("logging", "debug", False))
            elif s.name == "verbose-logging":
                s.set_value(get_val("logging", "verbose", False))

    def on_setting_changed(self, subsetting):
        if self.loading:
            return

        updates = {}
        
        mapping = {
            "provider": ("transcription", "provider"),
            "openai-api-key": ("transcription", "openai_api_key"),
            "openai-model": ("transcription", "openai_model"),
            "groq-api-key": ("transcription", "groq_api_key"),
            "groq-model": ("transcription", "groq_model"),
            "language": ("transcription", "language"),
            "timeout": ("recording", "timeout"),
            "injection-mode": ("injection", "mode"),
            "restore-clipboard": ("injection", "restore_clipboard"),
            "notifications": ("notifications", "enabled"),
            "debug-logging": ("logging", "debug"),
            "verbose-logging": ("logging", "verbose")
        }

        if subsetting.name in mapping:
            section, key = mapping[subsetting.name]
            val = subsetting.get_value()

            # Conversions
            if subsetting.name == "provider":
                p_list = ["openai", "groq-transcription", "groq-translation"]
                val = p_list[val]
            elif subsetting.name == "timeout":
                val = f"{val}s"
            elif subsetting.name == "injection-mode":
                m_list = ["fallback", "clipboard", "type"]
                val = m_list[val]
            elif subsetting.name == "groq-model":
                val = ["whisper-large-v3", "whisper-large-v3-turbo"][val]
            elif subsetting.name == "openai-model":
                val = ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"][val]

            if section not in updates: updates[section] = {}
            updates[section][key] = val

            # Sync logic for the main api_key and model used by the daemon
            if "transcription" not in updates:
                updates["transcription"] = {}

            prov_idx = self.provider_setting.get_value()
            prov = ["openai", "groq-transcription", "groq-translation"][prov_idx]
            
            if prov == "openai":
                updates["transcription"]["api_key"] = self.openai_api_key.get_value()
                o_idx = self.openai_model.get_value()
                updates["transcription"]["model"] = ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"][o_idx]
            else:
                updates["transcription"]["api_key"] = self.groq_api_key.get_value()
                g_idx = self.groq_model.get_value()
                updates["transcription"]["model"] = ["whisper-large-v3", "whisper-large-v3-turbo"][g_idx]

            self.config_manager.save_config(updates)

    def on_provider_changed(self, dropdown, pspec):
        selected_index = dropdown.get_selected()
        is_openai = (selected_index == 0)
        is_groq = (selected_index in [1, 2])

        self.openai_api_key.set_visible(is_openai)
        self.openai_model.set_visible(is_openai)
        self.groq_api_key.set_visible(is_groq)
        self.groq_model.set_visible(is_groq)

        self.on_setting_changed(self.provider_setting)

class SettingsGroup(Gtk.Box):
    def __init__(self, group_label, subsettings_list, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, *args, **kwargs)
        self.add_css_class("settings-group-container")
        self.subsettings = subsettings_list

        label = Gtk.Label(label=group_label)
        label.set_name("settings-group-label")
        label.set_halign(Gtk.Align.START)
        self.append(label)

        frame = Gtk.Frame()
        frame.set_name("settings-group-frame")
        
        inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.set_child(inner_box)
        self.append(frame)

        for subsetting in subsettings_list:
            inner_box.append(subsetting)

class SubSettings(Gtk.Box):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, type, name, label=None, sublabel=None, separator=True, params=None, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.add_css_class("subsettings-row")
        self.name = name
        self.type = type

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top_box.add_css_class("subsettings-content")
        top_box.set_valign(Gtk.Align.CENTER)
        self.append(top_box)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2, hexpand=False)
        text_box.set_valign(Gtk.Align.CENTER)
        top_box.append(text_box)

        if label:
            main_label = Gtk.Label(label=label, xalign=0)
            text_box.append(main_label)
        
        if sublabel:
            desc_label = Gtk.Label(label=sublabel, xalign=0)
            desc_label.add_css_class("settings-sub-label")
            desc_label.set_wrap(True)
            desc_label.set_max_width_chars(45)
            text_box.append(desc_label)

        if type == "switch":
            self.widget = Gtk.Switch()
            self.widget.set_valign(Gtk.Align.CENTER)
            self.widget.set_halign(Gtk.Align.END)
            self.widget.set_hexpand(True)
            self.widget.connect("notify::active", lambda w, p: self.emit("changed"))
            top_box.append(self.widget)

        elif type == "entry":
            self.widget = Gtk.Entry()
            self.widget.set_valign(Gtk.Align.CENTER)
            self.widget.set_hexpand(True)
            self.widget.set_margin_start(12)
            self.widget.connect("changed", lambda w: self.emit("changed"))
            top_box.append(self.widget)

        elif type == "dropdown":
            self.dropdown = Gtk.DropDown.new_from_strings(params[0])
            self.dropdown.set_valign(Gtk.Align.CENTER)
            self.dropdown.set_halign(Gtk.Align.END)
            self.dropdown.set_hexpand(True)
            self.dropdown.connect("notify::selected", lambda w, p: self.emit("changed"))
            top_box.append(self.dropdown)

        elif type == "spinbutton":
            adj = Gtk.Adjustment.new(10, params[0], params[1], params[2], 10, 0)
            self.widget = Gtk.SpinButton.new(adj, 1.0, 0)
            self.widget.set_valign(Gtk.Align.CENTER)
            self.widget.set_halign(Gtk.Align.END)
            self.widget.set_hexpand(True)
            self.widget.set_size_request(-1, 42)
            self.widget.connect("value-changed", lambda w: self.emit("changed"))
            top_box.append(self.widget)

        elif type == "checkbutton":
            self.widget = Gtk.CheckButton(label=params[0] if params else "")
            self.widget.set_valign(Gtk.Align.CENTER)
            self.widget.set_halign(Gtk.Align.END)
            self.widget.set_hexpand(True)
            self.widget.connect("toggled", lambda w: self.emit("changed"))
            top_box.append(self.widget)

        if separator:
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            self.append(sep)

    def get_value(self):
        if self.type == "switch":
            return self.widget.get_active()
        elif self.type == "entry":
            return self.widget.get_text()
        elif self.type == "dropdown":
            return self.dropdown.get_selected()
        elif self.type == "spinbutton":
            return int(self.widget.get_value())
        elif self.type == "checkbutton":
            return self.widget.get_active()
        return None

    def set_value(self, value):
        if self.type == "switch":
            self.widget.set_active(bool(value))
        elif self.type == "entry":
            self.widget.set_text(str(value or ""))
        elif self.type == "dropdown":
            self.dropdown.set_selected(int(value or 0))
        elif self.type == "spinbutton":
            self.widget.set_value(float(value or 0))
        elif self.type == "checkbutton":
            self.widget.set_active(bool(value))
