import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, Pango, GLib, Gio
import json
import os

from .sub_utils.logging_util import get_logger

logger = get_logger("preferences")

class PreferencesWindow(Gtk.Window):
    def __init__(self, application):
        super().__init__(title="Preferences")
        self.set_application(application)
        self.set_default_size(500, 600)
        self.set_modal(True)
        self.set_resizable(False)
        self.set_keep_above(True)
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.get_style_context().add_class("preferences-window")
        self.get_style_context().add_class("rounded")

        self.settings = application.gio_settings
        self.loading = True
        self.buttons = self.load_buttons()

        # Scrolled Window
        self.scrolled_window = Gtk.ScrolledWindow()
        self.scrolled_window.set_hexpand(True)
        self.scrolled_window.set_vexpand(True)
        self.scrolled_window.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.add(self.scrolled_window)

        # Main Box
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.main_box.set_margin_top(20)
        self.main_box.set_margin_bottom(12)
        self.main_box.set_margin_start(20)
        self.main_box.set_margin_end(20)
        self.scrolled_window.add(self.main_box)

        # --- Ring Menu Configuration ---
        self.list_subsettings = SubSettings(
            type="listbox", 
            name="ring-menu-list", 
            label="Buttons", 
            sublabel="Drag to reorder. Icons and actions update in real-time.", 
            separator=True,
            application=application
        )

        add_btn_img = Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.BUTTON)
        self.add_btn_setting = SubSettings(
            type="button",
            name="add-button",
            label="Add Action",
            sublabel="Add a new button to the ring menu",
            separator=False,
            params=("Add Button", add_btn_img)
        )
        self.add_btn_setting.control_widget.connect("clicked", self.on_add_clicked)

        config_group = SettingsGroup("Ring Menu Configuration", (
            self.list_subsettings,
            self.add_btn_setting
        ))
        self.add_btn_setting.control_widget.get_style_context().add_class("suggested-action")
        self.main_box.pack_start(config_group, True, True, 0)

        self.populate_buttons()
        self.show_all()
        self.loading = False

    def load_buttons(self):
        json_str = self.settings.get_string("buttons-json")
        buttons = []
        try:
            buttons = json.loads(json_str)
        except Exception:
            pass
            
        if not buttons:
            return self._get_default_buttons()
            
        # Deduplicate existing buttons (except empty slots)
        unique_buttons = []
        seen_actions = set()
        for b in buttons:
            if not b or not b.get("type"): continue
            
            action = b.get("action")
            # We allow multiple empty slots
            if b.get("type") == "empty" or not action:
                unique_buttons.append(b)
                continue
                
            # Filter duplicates by action (e.g. "preferences")

        if not json_str or json_str == '[]':
            # This generally won't happen if schema default is set correctly
            # But handle it gracefully just in case
            buttons = []
        else:
            try:
                buttons = json.loads(json_str)
            except json.JSONDecodeError:
                logger.error("Failed to decode buttons JSON, starting fresh.")
                buttons = []
            
        if not buttons or not isinstance(buttons, list):
            logger.warning("Loaded buttons data is invalid or empty. Using empty list.")
            buttons = []
        
        # Ensure exactly 8 slots (Pad with Empty if needed)
        while len(buttons) < 8:
            buttons.append({"name": "Empty", "icon": "list-add-symbolic", "type": "empty", "action": ""})
                
        return buttons


    def save_buttons(self):
        json_str = json.dumps(self.buttons)
        self.settings.set_string("buttons-json", json_str)

    def populate_buttons(self):
        self.list_subsettings.populate_ring_buttons(self.buttons, self)

    def on_add_clicked(self, btn):
        picker = ActionPicker(self)
        if picker.run() == Gtk.ResponseType.OK:
            new_btn = picker.get_result()
            if new_btn:
                # 1. Prevent Duplicates
                is_duplicate = False
                for existing in self.buttons:
                    if existing and existing.get("type") == new_btn.get("type") and \
                       existing.get("action") == new_btn.get("action") and \
                       new_btn.get("type") != "empty": # Allow multiple empty
                        is_duplicate = True
                        break
                
                if is_duplicate:
                    logger.info(f"Action '{new_btn.get('name')}' is already in the list.")
                    picker.destroy()
                    return

                # 2. Find first empty slot to replace, or append if none
                replaced = False
                for i in range(len(self.buttons)):
                    btn_data = self.buttons[i]
                    if not btn_data or btn_data.get("type") == "empty" or \
                       not btn_data.get("action") or btn_data.get("name") == "Empty":
                        self.buttons[i] = new_btn
                        replaced = True
                        break
                
                if not replaced:
                    if len(self.buttons) < 8:
                        self.buttons.append(new_btn)
                    else:
                        logger.warning("No empty slots available to add new action.")
                
                # If it's a custom command and we just added it to a slot, maybe it needs editing?
                # The user might want to set name/icon immediately
                if new_btn.get("type") == "command" and not new_btn.get("name"):
                    # Find where we just put it
                    idx = self.buttons.index(new_btn) if new_btn in self.buttons else -1
                    if idx != -1:
                        self.on_edit_button(idx)
                    else:
                        self.save_buttons()
                        self.populate_buttons()
                else:
                    self.save_buttons()
                    self.populate_buttons()
        picker.destroy()

    def on_edit_button(self, index):
        if 0 <= index < len(self.buttons):
            dialog = ActionDialog(self, self.buttons[index])
            if dialog.run() == Gtk.ResponseType.OK:
                self.buttons[index] = dialog.get_result()
                self.save_buttons()
                self.populate_buttons()
            dialog.destroy()

    def on_delete(self, index):
        if 0 <= index < len(self.buttons):
            # Verify it's not the protected Preferences button
            if self.buttons[index].get("action") == "preferences":
                logger.warning("Attempted to delete protected Preferences button")
                return
            
            # Instead of removing the slot (which shifts indices), we replace it with "Empty"
            # This maintains the 8-slot structure
            self.buttons[index] = {"name": "Empty", "icon": "list-add-symbolic", "type": "empty", "action": ""}
            self.save_buttons()
            self.populate_buttons()

    def on_reorder(self, source_idx, dest_idx):
        if source_idx != dest_idx:
            item = self.buttons.pop(source_idx)
            self.buttons.insert(dest_idx, item)
            self.save_buttons()
            # Defer population to avoid segfault during DND operation
            GLib.idle_add(self.populate_buttons)

# --- Reusable UI Components Ported from Whis (GTK 3) ---

class SettingsGroup(Gtk.Box):
    def __init__(self, group_label, subsettings_list, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=8, *args, **kwargs)
        self.get_style_context().add_class("settings-group-container")
        self.subsettings = subsettings_list

        label = Gtk.Label(label=group_label)
        label.set_name("settings-group-label")
        label.set_halign(Gtk.Align.START)
        self.pack_start(label, False, False, 0)

        frame = Gtk.Frame()
        frame.set_name("settings-group-frame")
        
        inner_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        frame.add(inner_box)
        self.pack_start(frame, True, True, 0)

        for subsetting in subsettings_list:
            inner_box.pack_start(subsetting, subsetting.type == "listbox", subsetting.type == "listbox", 0)

class SubSettings(Gtk.Box):
    __gsignals__ = {
        'changed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, type, name, label=None, sublabel=None, separator=True, params=None, application=None, *args, **kwargs):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, *args, **kwargs)
        self.get_style_context().add_class("subsettings-row")
        self.name = name
        self.type = type

        top_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        top_box.get_style_context().add_class("subsettings-content")
        top_box.set_valign(Gtk.Align.CENTER)
        self.pack_start(top_box, False, False, 0)

        text_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        text_box.set_valign(Gtk.Align.CENTER)
        top_box.pack_start(text_box, False, False, 0)

        if label:
            main_label = Gtk.Label(label=label)
            main_label.set_xalign(0)
            text_box.pack_start(main_label, False, False, 0)
        
        if sublabel:
            desc_label = Gtk.Label(label=sublabel)
            desc_label.set_xalign(0)
            desc_label.get_style_context().add_class("settings-sub-label")
            desc_label.set_line_wrap(True)
            desc_label.set_max_width_chars(45)
            text_box.pack_start(desc_label, False, False, 0)

        if type == "switch":
            self.control_widget = Gtk.Switch()
            self.control_widget.set_valign(Gtk.Align.CENTER)
            self.control_widget.set_halign(Gtk.Align.END)
            self.control_widget.set_hexpand(True)
            top_box.pack_start(self.control_widget, True, True, 0)

        elif type == "entry":
            self.control_widget = Gtk.Entry()
            self.control_widget.set_valign(Gtk.Align.CENTER)
            self.control_widget.set_hexpand(True)
            self.control_widget.set_margin_start(12)
            top_box.pack_start(self.control_widget, True, True, 0)

        elif type == "dropdown":
            self.control_widget = Gtk.ComboBoxText()
            for opt in params[0]:
                self.control_widget.append_text(opt)
            self.control_widget.set_active(0)
            self.control_widget.set_valign(Gtk.Align.CENTER)
            self.control_widget.set_halign(Gtk.Align.END)
            self.control_widget.set_hexpand(True)
            top_box.pack_start(self.control_widget, True, True, 0)

        elif type == "button":
            self.control_widget = Gtk.Button(label=params[0])
            if len(params) > 1:
                self.control_widget.set_image(params[1])
                self.control_widget.set_always_show_image(True)
            self.control_widget.set_valign(Gtk.Align.CENTER)
            self.control_widget.set_halign(Gtk.Align.END)
            self.control_widget.set_hexpand(True)
            top_box.pack_start(self.control_widget, True, True, 0)

        elif type == "listbox":
            self.listbox = Gtk.ListBox()
            self.listbox.set_selection_mode(Gtk.SelectionMode.SINGLE)
            self.listbox.set_header_func(self.update_header)
            self.listbox.connect("row-activated", self.on_row_activated)
            
            scrolled = Gtk.ScrolledWindow()
            scrolled.set_hexpand(True)
            scrolled.set_vexpand(True)
            scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
            scrolled.set_min_content_height(350)
            scrolled.add(self.listbox)
            self.pack_start(scrolled, True, True, 0)

        if separator:
            sep = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
            self.pack_start(sep, False, False, 0)

    def on_row_activated(self, listbox, row):
        if hasattr(row, 'window') and hasattr(row, 'get_index'):
            row.window.on_edit_button(row.get_index())

    def update_header(self, row, before):
        if before is not None:
            row.set_header(Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL))

    def populate_ring_buttons(self, buttons_data, window):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
        
        for i, data in enumerate(buttons_data):
            row = ReorderableButtonRow(i, data, window)
            self.listbox.add(row)
        self.listbox.show_all()

class ReorderableButtonRow(Gtk.ListBoxRow):
    def __init__(self, index, data, window):
        super().__init__()
        self.window = window
        self.set_can_focus(True)
        self.set_activatable(True)

        grid = Gtk.Grid()
        grid.props.column_spacing = 12
        grid.props.margin = 10
        self.add(grid)

        # Drag Handle (Most reliable for GTK reordering)
        handle = Gtk.EventBox()
        handle_img = Gtk.Image.new_from_icon_name("list-drag-handle-symbolic", Gtk.IconSize.BUTTON)
        handle_img.get_style_context().add_class("drag-handle")
        handle.add(handle_img)
        grid.attach(handle, 0, 0, 1, 1)

        # Icon
        icon_name = data.get("icon", "system-run-symbolic")
        icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.LARGE_TOOLBAR)
        grid.attach(icon, 1, 0, 1, 1)

        # Labels
        lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        grid.attach(lbl_box, 2, 0, 1, 1)

        name_lbl = Gtk.Label(label=data.get("name", "Empty Slot"))
        name_lbl.set_xalign(0)
        lbl_box.pack_start(name_lbl, False, False, 0)

        type_lbl = Gtk.Label(label=f"{data.get('type', 'none')} • {data.get('action', '')}")
        type_lbl.set_xalign(0)
        type_lbl.get_style_context().add_class("settings-sub-label")
        lbl_box.pack_start(type_lbl, False, False, 0)

        # Delete Button (Only for non-preferences actions and non-empty slots)
        if data.get("action") != "preferences" and data.get("type") != "empty":
            del_btn = Gtk.Button()
            del_btn.set_relief(Gtk.ReliefStyle.NONE)
            del_img = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
            del_btn.set_image(del_img)
            del_btn.get_style_context().add_class("destructive-action") # For red hover
            del_btn.set_valign(Gtk.Align.CENTER)
            del_btn.set_halign(Gtk.Align.END)
            del_btn.set_hexpand(True)
            del_btn.set_tooltip_text("Remove Action")
            del_btn.connect("clicked", lambda x: self.window.on_delete(self.get_index()))
            grid.attach(del_btn, 3, 0, 1, 1)

        # DND signals
        targets = [
            Gtk.TargetEntry.new("GTK_LIST_BOX_ROW", Gtk.TargetFlags.SAME_APP, 0),
            Gtk.TargetEntry.new("text/plain", 0, 1)
        ]
        
        # Source on handle, Dest on the whole row
        handle.drag_source_set(Gdk.ModifierType.BUTTON1_MASK, targets, Gdk.DragAction.MOVE)
        self.drag_dest_set(Gtk.DestDefaults.ALL, targets, Gdk.DragAction.MOVE)
        
        handle.connect("drag-begin", self.on_drag_begin)
        handle.connect("drag-data-get", self.on_drag_data_get)
        self.connect("drag-data-received", self.on_drag_data_received)
        self.connect("drag-drop", self.on_drag_drop)

    def on_drag_begin(self, widget, context):
        logger.debug(f"DND: Drag-Begin at index {self.get_index()}")

    def on_drag_drop(self, widget, context, x, y, time):
        logger.debug(f"DND: Drag-Drop detected at index {self.get_index()}")
        return False # Continue to data-received

    def on_drag_data_get(self, widget, context, data, info, time):
        idx = self.get_index()
        logger.debug(f"DND: Data-Get for index {idx}")
        # Use selection data instead of plain text for better reliability
        data.set(data.get_target(), 8, str(idx).encode('utf-8'))

    def on_drag_data_received(self, widget, context, x, y, data, info, time):
        source_index_bytes = data.get_data()
        if source_index_bytes:
            try:
                source_index = int(source_index_bytes.decode('utf-8'))
                dest_index = self.get_index()
                logger.info(f"DND: Reordering {source_index} -> {dest_index}")
                self.window.on_reorder(source_index, dest_index)
                context.finish(True, False, time)
            except Exception as e:
                logger.error(f"DND Error: {e}")
                context.finish(False, False, time)
        else:
            logger.warning("DND: No data received")
            context.finish(False, False, time)
        return True

class ActionPicker(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="Add Action", transient_for=parent, modal=True)
        self.set_default_size(400, 500)
        self.get_style_context().add_class("action-picker-dialog")
        
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        
        content_area = self.get_content_area()
        main_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10, margin=10)
        content_area.add(main_vbox)
        
        # Search Box
        self.search_entry = Gtk.SearchEntry()
        self.search_entry.set_placeholder_text("Search Actions & Applications")
        self.search_entry.connect("search-changed", self._on_search_changed)
        main_vbox.pack_start(self.search_entry, False, False, 0)
        
        # Compact Toggle Row
        toggle_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        main_vbox.pack_start(toggle_hbox, False, False, 0)
        
        toggle_label = Gtk.Label(label="Show Hidden Apps")
        toggle_label.get_style_context().add_class("settings-sub-label")
        
        self.hidden_toggle = Gtk.Switch()
        self.hidden_toggle.get_style_context().add_class("small-switch")
        self.hidden_toggle.set_valign(Gtk.Align.CENTER)
        self.hidden_toggle.connect("notify::active", self._on_toggle_changed)
        
        toggle_hbox.pack_end(self.hidden_toggle, False, False, 0)
        toggle_hbox.pack_end(toggle_label, False, False, 0)
        
        # Scrolled List
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(350)
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_shadow_type(Gtk.ShadowType.IN)
        main_vbox.pack_start(scrolled, True, True, 0)
        
        self.listbox = Gtk.ListBox()
        self.listbox.set_header_func(self._update_header)
        self.listbox.connect("row-activated", self._on_row_activated)
        scrolled.add(self.listbox)
        main_vbox.pack_start(scrolled, True, True, 0)
        
        # Custom Command Input (Bottom)
        custom_vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        main_vbox.pack_start(custom_vbox, False, False, 0)
        
        custom_lbl = Gtk.Label(label="Custom Command")
        custom_lbl.set_xalign(0)
        custom_lbl.get_style_context().add_class("settings-sub-label")
        custom_vbox.pack_start(custom_lbl, False, False, 0)
        
        custom_hbox = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        custom_vbox.pack_start(custom_hbox, False, False, 0)
        
        self.custom_entry = Gtk.Entry()
        self.custom_entry.set_placeholder_text("e.g. flatpak run org.gnome.Gimp")
        self.custom_entry.connect("activate", self._on_custom_activate)
        custom_hbox.pack_start(self.custom_entry, True, True, 0)
        
        add_btn = Gtk.Button(label="Add")
        add_btn.get_style_context().add_class("suggested-action")
        add_btn.connect("clicked", self._on_custom_activate)
        custom_hbox.pack_start(add_btn, False, False, 0)
        
        # Result placeholder
        self.result = None
        
        # Load Actions
        self.all_actions = self._get_all_actions()
        self._populate_list("")
        
        self.show_all()

    def _get_all_actions(self):
        actions = []
        logger.info("ActionPicker: Starting action discovery...")
        
        # Group: Built-in Actions
        builtins = [
            {"name": "Media", "icon": "multimedia-player", "type": "internal", "action": "media", "group": "Built-in Action", "desc": "Play/Pause and media controls"},
            {"name": "Files", "icon": "system-file-manager", "type": "internal", "action": "files", "group": "Built-in Action", "desc": "Open File Manager"},
            {"name": "Screenshot", "icon": "applets-screenshooter", "type": "internal", "action": "screenshot", "group": "Built-in Action", "desc": "Take a screenshot"},
            {"name": "Quickey Preferences", "icon": "open-menu", "type": "internal", "action": "preferences", "group": "Built-in Action", "desc": "Configure Quickey settings"},
        ]
        actions.extend(builtins)
        
        # Group: Applications
        seen_ids = set()
        
        # 1. Start with Gio discovery
        apps = Gio.AppInfo.get_all()
        logger.info(f"ActionPicker: Gio found {len(apps)} initial apps.")
        for app in apps:
            if app.should_show():
                app_id = app.get_id()
                if app_id:
                    # Strip .desktop if present for normalization
                    norm_id = app_id[:-8] if app_id.endswith(".desktop") else app_id
                    seen_ids.add(norm_id)
                    
                icon = app.get_icon()
                icon_name = icon.to_string() if icon else "system-run-symbolic"
                actions.append({
                    "name": app.get_name(),
                    "icon": icon_name,
                    "type": "app",
                    "action": app_id or app.get_executable() or "",
                    "desc": app.get_description() or "",
                    "group": "Applications"
                })
        
        # 2. Manual Scan Fallback (Bypass sandbox limitations)
        # We look into exports and host paths mapped by flatpak
        scan_paths = [
            # Prioritize Flatpak exports
            "/var/lib/flatpak/exports/share/applications",
            os.path.expanduser("~/.local/share/flatpak/exports/share/applications"),
            # Then host paths
            "/run/host/usr/share/applications",
            "/run/host/usr/local/share/applications",
            os.path.expanduser("~/.local/share/applications"),
            "/usr/share/applications",
        ]
        
        for path in scan_paths:
            if not os.path.exists(path):
                logger.debug(f"ActionPicker: Path {path} does not exist.")
                continue
            
            logger.info(f"ActionPicker: Scanning {path}...")
            try:
                files = os.listdir(path)
                logger.info(f"ActionPicker: Found {len(files)} files in {path}.")
                for file_name in files:
                    if not file_name.endswith(".desktop"):
                        continue
                    
                    norm_id = file_name[:-8]
                    if norm_id in seen_ids:
                        continue
                    
                    full_path = os.path.join(path, file_name)
                    name, icon_name, desc, hidden = None, "system-run-symbolic", "", False
                    
                    try:
                        app = Gio.DesktopAppInfo.new_from_filename(full_path)
                        if app:
                            name = app.get_name()
                            icon = app.get_icon()
                            icon_name = icon.to_string() if icon else "system-run-symbolic"
                            desc = app.get_description() or ""
                            hidden = app.get_nodisplay()
                    except Exception as e:
                        logger.debug(f"ActionPicker: Gio failed for {file_name}: {e}")
                    
                    # Manual fallback if Gio failed or returned None
                    if not name:
                        try:
                            with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                in_desktop_entry = False
                                for line in f:
                                    line = line.strip()
                                    if line == "[Desktop Entry]":
                                        in_desktop_entry = True
                                        continue
                                    if in_desktop_entry and line.startswith("["):
                                        break
                                    if in_desktop_entry:
                                        if line.startswith("Name=") and not name:
                                            name = line[5:].strip()
                                        elif line.startswith("Icon=") and (icon_name == "system-run-symbolic" or not icon_name):
                                            icon_name = line[5:].strip()
                                        elif (line.startswith("GenericName=") or line.startswith("Comment=")) and not desc:
                                            desc = line.split("=", 1)[1].strip()
                                        elif line.startswith("NoDisplay="):
                                            hidden = line[10:].lower() == "true"
                        except Exception as e:
                            logger.debug(f"ActionPicker: Manual parse failed for {file_name}: {e}")
                    
                    if name:
                        # Prefer existing entry if it has better data
                        # But for now, just keep the first one found (which is prioritized by scan_paths)
                        if norm_id not in seen_ids:
                            seen_ids.add(norm_id)
                            is_flatpak = "flatpak" in path.lower()
                            logger.debug(f"ActionPicker: Discovered '{name}' from {path} (Flatpak: {is_flatpak})")
                            actions.append({
                                "name": name,
                                "icon": icon_name,
                                "type": "app",
                                "action": file_name,
                                "desc": desc,
                                "group": "Applications",
                                "hidden": hidden,
                                "is_flatpak": is_flatpak
                            })
            except Exception as e:
                logger.warning(f"ActionPicker: Failed to list {path}: {e}")
        
        # Sort apps by name
        actions[len(builtins):] = sorted(actions[len(builtins):], key=lambda x: x["name"].lower())
        
        # Group: Custom
        actions.append({
            "name": "Custom Command",
            "icon": "utilities-terminal-symbolic",
            "type": "command",
            "action": "",
            "desc": "Type in a custom command",
            "group": "Custom"
        })
        
        logger.info(f"ActionPicker: Total actions prepared: {len(actions)}")
        return actions

    def _populate_list(self, query):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        query = query.lower().strip()
        show_hidden = self.hidden_toggle.get_active()
        count = 0
        for action in self.all_actions:
            # First filter by hidden property
            if action.get("hidden", False) and not show_hidden:
                continue
                
            name_match = query in action["name"].lower()
            desc_match = action.get("desc") and query in action["desc"].lower()
            if name_match or desc_match:
                row = PickerRow(action)
                self.listbox.add(row)
                count += 1
        
        logger.info(f"ActionPicker: Populated list with {count} items (query: '{query}', hidden: {show_hidden})")
        self.listbox.show_all()

    def _update_header(self, row, before):
        action = row.action_data
        if before is None or before.action_data["group"] != action["group"]:
            header = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            lbl = Gtk.Label(label=action["group"])
            lbl.get_style_context().add_class("picker-header-label")
            lbl.set_xalign(0)
            lbl.set_margin_top(12)
            lbl.set_margin_bottom(6)
            lbl.set_margin_start(10)
            header.add(lbl)
            row.set_header(header)
        else:
            row.set_header(None)

    def _on_search_changed(self, entry):
        self._populate_list(entry.get_text())

    def _on_toggle_changed(self, switch, gparam):
        self._populate_list(self.search_entry.get_text())

    def _on_row_activated(self, listbox, row):
        self.result = row.action_data
        self.response(Gtk.ResponseType.OK)

    def _on_custom_activate(self, widget):
        cmd = self.custom_entry.get_text().strip()
        if cmd:
            self.result = {
                "name": cmd.split()[0] if cmd else "Custom",
                "icon": "utilities-terminal-symbolic",
                "type": "command",
                "action": cmd,
                "desc": cmd
            }
            self.response(Gtk.ResponseType.OK)

    def get_result(self):
        return self.result

class PickerRow(Gtk.ListBoxRow):
    def __init__(self, action_data):
        super().__init__()
        self.action_data = action_data
        
        grid = Gtk.Grid(column_spacing=12, margin=8)
        self.add(grid)
        
        icon = Gtk.Image.new_from_icon_name(action_data["icon"], Gtk.IconSize.DND)
        grid.attach(icon, 0, 0, 1, 1)
        
        lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        grid.attach(lbl_box, 1, 0, 1, 1)
        
        name_lbl = Gtk.Label(label=action_data["name"])
        name_lbl.set_xalign(0)
        lbl_box.pack_start(name_lbl, False, False, 0)
        
        # Build subtitle
        sub_items = []
        if action_data.get("is_flatpak"):
            sub_items.append("Flatpak")
        if action_data.get("hidden"):
            sub_items.append("Hidden")
        
        desc = action_data.get("desc", "")
        if sub_items:
            prefix = " • ".join(sub_items)
            desc = f"{prefix} | {desc}" if desc else prefix
            
        if desc:
            desc_lbl = Gtk.Label(label=desc)
            desc_lbl.set_xalign(0)
            desc_lbl.get_style_context().add_class("settings-sub-label")
            desc_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            desc_lbl.set_max_width_chars(50)
            lbl_box.pack_start(desc_lbl, False, False, 0)

class ActionDialog(Gtk.Dialog):
    def __init__(self, parent, data=None):
        title = "Edit Action" if data else "Add Action"
        super().__init__(title=title, transient_for=parent, modal=True)
        self.set_default_size(350, -1)
        self.get_style_context().add_class("action-dialog")
        
        self.add_button("_Cancel", Gtk.ResponseType.CANCEL)
        self.add_button("_Save", Gtk.ResponseType.OK)
        
        content_area = self.get_content_area()
        grid = Gtk.Grid(column_spacing=12, row_spacing=12, margin=15)
        content_area.add(grid)
        
        # Name
        grid.attach(Gtk.Label(label="Name:", xalign=1), 0, 0, 1, 1)
        self.name_entry = Gtk.Entry(text=data.get("name", "") if data else "")
        grid.attach(self.name_entry, 1, 0, 1, 1)
        
        # Icon
        grid.attach(Gtk.Label(label="Icon:", xalign=1), 0, 1, 1, 1)
        icon_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.icon_entry = Gtk.Entry(text=data.get("icon", "system-run-symbolic") if data else "system-run-symbolic")
        self.icon_preview = Gtk.Image.new_from_icon_name(self.icon_entry.get_text(), Gtk.IconSize.BUTTON)
        self.icon_entry.connect("changed", self._on_icon_changed)
        icon_box.pack_start(self.icon_entry, True, True, 0)
        icon_box.pack_start(self.icon_preview, False, False, 0)
        grid.attach(icon_box, 1, 1, 1, 1)
        
        # Type
        grid.attach(Gtk.Label(label="Type:", xalign=1), 0, 2, 1, 1)
        self.type_combo = Gtk.ComboBoxText()
        types = ["command", "app", "internal", "prefix", "empty", "none"]
        for t in types:
            self.type_combo.append(t, t.capitalize())
        
        current_type = data.get("type", "command") if data else "command"
        if current_type not in types:
            current_type = "command"
            
        self.type_combo.set_active(types.index(current_type))
        grid.attach(self.type_combo, 1, 2, 1, 1)
        
        # Action
        grid.attach(Gtk.Label(label="Action:", xalign=1), 0, 3, 1, 1)
        self.action_entry = Gtk.Entry(text=data.get("action", "") if data else "")
        grid.attach(self.action_entry, 1, 3, 1, 1)
        
        self.show_all()

    def _on_icon_changed(self, entry):
        icon_name = entry.get_text()
        self.icon_preview.set_from_icon_name(icon_name, Gtk.IconSize.BUTTON)

    def get_result(self):
        return {
            "name": self.name_entry.get_text(),
            "icon": self.icon_entry.get_text(),
            "type": self.type_combo.get_active_id(),
            "action": self.action_entry.get_text()
        }
