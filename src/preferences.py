import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject, Pango, GLib, Gio
import json
import os

from .sub_utils.logging_util import get_logger
from .config_manager import ConfigManager
from .app_scanner import AppScanner

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
        self.config_manager = ConfigManager(self.settings)
        self.loading = True
        self.buttons = self.config_manager.load_configured_buttons()

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
        reset_btn = Gtk.Button(label="Reset to Defaults")
        reset_btn.get_style_context().add_class("destructive-action")
        reset_btn.connect("clicked", self.on_reset_clicked)

        self.list_subsettings = SubSettings(
            type="listbox", 
            name="ring-menu-list", 
            label="Buttons", 
            sublabel="Drag to reorder. Icons and actions update in real-time.", 
            separator=True,
            application=application,
            params=(reset_btn,)
        )

        config_group = SettingsGroup("Ring Menu Configuration", (
            self.list_subsettings,
        ))
        self.main_box.pack_start(config_group, True, True, 0)

        self.populate_buttons()
        self.show_all()
        self.loading = False

    def save_buttons(self):
        self.config_manager.save_buttons(self.buttons)

    def populate_buttons(self):
        self.list_subsettings.populate_ring_buttons(self.buttons, self)

    def on_replace_button(self, index):
        if 0 <= index < len(self.buttons):
            # Open Action Picker to replace this slot
            
            # Identify actions to exclude (singletons like media, screenshot, preferences)
            # But allow keeping the CURRENT action if we are just editing it.
            excluded = []
            singletons = ["media", "screenshot", "preferences"]
            
            for i, btn in enumerate(self.buttons):
                if i == index: continue # Don't exclude the one we are replacing
                
                act = btn.get("action")
                if act in singletons:
                    excluded.append(act)

            picker = ActionPicker(self, excluded_actions=excluded)
            if picker.run() == Gtk.ResponseType.OK:
                result = picker.get_result()
                if result:
                    self.buttons[index] = result
                    self.save_buttons()
                    self.populate_buttons()
            picker.destroy()


    def on_delete(self, index):
        if 0 <= index < len(self.buttons):
            # Verify it's not the protected Preferences button
            if self.buttons[index].get("action") == "preferences":
                logger.warning("Attempted to delete protected Preferences button")
                return
            
            # Instead of removing the slot (which shifts indices), we replace it with "Empty"
            # This maintains the 8-slot structure
            self.config_manager.reset_slot(index)
            self.buttons = self.config_manager.load_configured_buttons()
            self.populate_buttons()

    def on_reset_clicked(self, btn):
        dialog = Gtk.MessageDialog(
            transient_for=self,
            flags=0,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Reset to Defaults?"
        )
        dialog.format_secondary_text(
            "This will remove all custom actions and restore the default button list."
        )
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            self.config_manager.reset_to_defaults()
            self.buttons = self.config_manager.load_configured_buttons()
            self.populate_buttons()
        dialog.destroy()

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
            # Allow an optional header widget (e.g. Reset button) passed in params
            if params and len(params) > 0 and isinstance(params[0], Gtk.Widget):
                self.control_widget = params[0]
                self.control_widget.set_valign(Gtk.Align.CENTER)
                self.control_widget.set_halign(Gtk.Align.END)
                # self.control_widget.set_hexpand(True) # Don't expand, keep it to the right
                top_box.pack_end(self.control_widget, False, False, 0)

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
            row.window.on_replace_button(row.get_index())

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
        self.action_data = data
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
        lbl_box.set_hexpand(True) # Push actions to the right
        grid.attach(lbl_box, 2, 0, 1, 1)

        name_lbl = Gtk.Label(label=data.get("name", "Empty Slot"))
        name_lbl.set_xalign(0)
        lbl_box.pack_start(name_lbl, False, False, 0)

        type_lbl = Gtk.Label(label=f"{data.get('type', 'none')} • {data.get('action', '')}")
        type_lbl.set_xalign(0)
        type_lbl.get_style_context().add_class("settings-sub-label")
        lbl_box.pack_start(type_lbl, False, False, 0)

        if data.get("action") != "preferences" and data.get("type") != "empty":
            # Action Box for Add/Delete
            action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
            grid.attach(action_box, 3, 0, 1, 1)

            # Add Sub-button (For user configured buttons and Files)
            # "User configured" roughly means not Preferences and not Empty.
            # Files is explicitly mentioned.
            # We allow it for everything except Preferences/Empty.
            add_sub_btn = Gtk.Button()
            add_sub_btn.set_relief(Gtk.ReliefStyle.NONE)
            add_sub_img = Gtk.Image.new_from_icon_name("list-add-symbolic", Gtk.IconSize.MENU)
            add_sub_btn.set_image(add_sub_img)
            add_sub_btn.set_tooltip_text("Add Sub-button")
            add_sub_btn.connect("clicked", self.on_add_sub_clicked)
            action_box.pack_start(add_sub_btn, False, False, 0)

            # Delete Button
            del_btn = Gtk.Button()
            del_btn.set_relief(Gtk.ReliefStyle.NONE)
            del_img = Gtk.Image.new_from_icon_name("user-trash-symbolic", Gtk.IconSize.MENU)
            del_btn.set_image(del_img)
            del_btn.get_style_context().add_class("destructive-action") 
            del_btn.set_tooltip_text("Remove Action")
            del_btn.connect("clicked", lambda x: self.window.on_delete(self.get_index()))
            action_box.pack_start(del_btn, False, False, 0)
        
        # Sub-buttons Display
        self.subs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        self.subs_box.set_margin_top(6)
        self.subs_box.set_margin_start(52) # Indent to align with text
        
        # Check if we should show existing sub-buttons
        if data.get("sub_buttons"):
            self._refresh_sub_buttons_ui()
            grid.attach(self.subs_box, 0, 1, 4, 1)

    def on_add_sub_clicked(self, btn):
        action_type = self.action_data.get("action")
        
        if action_type == "files":
            # Files specialized dialog
            dialog = Gtk.FileChooserNative(
                title="Select File or Folder",
                transient_for=self.window,
                action=Gtk.FileChooserAction.OPEN # Allows files. determining valid "files or folders" usually requires trickery or just OPEN and hope for folders?
            )
            # Actually Gtk.FileChooserAction.OPEN usually selects files. SELECT_FOLDER is for folders.
            # If user wants BOTH, it's tricky in GTK3 without standard dialog tricks.
            # But the prompt says "Files button... sub button can only add files OR folders."
            # Maybe we ask user what they want? Or use a generic picker?
            # Let's try to just use OPEN and see if it handles folders? No it doesn't usually.
            # Let's add a filter or just default to Files for now, and maybe a separate "Add Folder"?
            # Or simpler: Just use OPEN, but mention in prompt "Select File".
            # actually better: Create a small popup asking "File or Folder?"
            # OR simpler: Use ActionPicker for Files too? No, "Use the default select file/folder popup dialog".
            
            # Let's use a standard file chooser in OPEN mode, but if they want a folder, they can't selection it easily in OPEN mode usually.
            # I will assume Files for now, and maybe I can add a filter.
            # Wait, "Add File/Folder".
            # Let's do a simple heuristic: Button triggers a menu? "Add File", "Add Folder".
            
            popover = Gtk.Popover()
            popover.set_relative_to(btn)
            vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
            vbox.set_margin_top(5); vbox.set_margin_bottom(5); vbox.set_margin_start(5); vbox.set_margin_end(5)
            
            btn_file = Gtk.Button(label="Add File")
            btn_file.set_relief(Gtk.ReliefStyle.NONE)
            btn_file.connect("clicked", lambda x: (popover.popdown(), self._open_file_chooser(Gtk.FileChooserAction.OPEN)))
            vbox.add(btn_file)
            
            btn_folder = Gtk.Button(label="Add Folder")
            btn_folder.set_relief(Gtk.ReliefStyle.NONE)
            btn_folder.connect("clicked", lambda x: (popover.popdown(), self._open_file_chooser(Gtk.FileChooserAction.SELECT_FOLDER)))
            vbox.add(btn_folder)
            
            vbox.show_all()
            popover.add(vbox)
            popover.popup()
            
        else:
            # Generic Action Picker for other buttons
            picker = ActionPicker(self.window)
            if picker.run() == Gtk.ResponseType.OK:
                result = picker.get_result()
                if result:
                    self._add_sub_button(result)
            picker.destroy()

    def _open_file_chooser(self, action):
        dialog = Gtk.FileChooserNative(
            title="Select Item",
            transient_for=self.window,
            action=action
        )
        
        # Workaround for portal dialog appearing behind keep-above window
        self.window.set_keep_above(False)
        res = dialog.run()
        self.window.set_keep_above(True)
        
        if res == Gtk.ResponseType.ACCEPT:
            filename = dialog.get_filename()
            uri = dialog.get_uri()
            
            # Additional fallback check for Flatpak portal behavior
            if not filename and uri:
                try:
                     filename, _ = GLib.filename_from_uri(uri)
                except Exception:
                     filename = uri # Desperate fallback, or keep None
            
            if not filename:
                logger.error(f"File Chooser returned invalid filename. URI: {uri}")
                dialog.destroy()
                return

            name = os.path.basename(filename)
            
            logger.info(f"File Chooser Selected: {filename} | URI: {uri}")
            
            # 1. Determine base type (File vs Folder)
            is_dir = os.path.isdir(filename)
            logger.info(f"Is Directory: {is_dir}")
            
            # Default to simple safe icons
            icon = "folder" if is_dir else "text-x-generic"
            
            # 2. Try to get more specific icon via Gio
            try:
                f = Gio.File.new_for_uri(uri)
                info = f.query_info("standard::icon,standard::content-type", Gio.FileQueryInfoFlags.NONE, None)
                
                content_type = info.get_content_type()
                logger.info(f"Content Type: {content_type}")
                
                if content_type == "inode/directory":
                     icon = "folder"
                     is_dir = True # Force true if content type says so
                
                gicon = info.get_icon()
                if gicon:
                    detected_icon = None
                    if isinstance(gicon, Gio.ThemedIcon):
                        names = gicon.get_names()
                        logger.info(f"ThemedIcon names: {names}")
                        if names:
                            detected_icon = names[0]
                    else:
                        s = gicon.to_string()
                        logger.info(f"GIcon string: {s}")
                        if " " not in s and "/" not in s: 
                            detected_icon = s
                            
                    if detected_icon:
                        # Verify if this icon exists in current theme, otherwise keep safe fallback
                        theme = Gtk.IconTheme.get_default()
                        if theme.has_icon(detected_icon):
                            icon = detected_icon
                        else:
                            logger.warning(f"Detected icon '{detected_icon}' not found in theme. Keeping '{icon}'.")

            except Exception as e:
                logger.warning(f"Icon detection failed for {uri}: {e}")

            logger.info(f"Final determined icon: {icon}")

            data = {
                "name": name,
                "icon": icon,
                "type": "file", 
                "action": filename 
            }
            self._add_sub_button(data)
        dialog.destroy()

    def _add_sub_button(self, sub_data):
        current_subs = self.action_data.get("sub_buttons", [])
        current_subs.append(sub_data)
        self.action_data["sub_buttons"] = current_subs
        self.window.save_buttons() # Triggers save via preferences window
        self._refresh_sub_buttons_ui()
        
        # Ensure the box is attached if it was the first one
        if len(current_subs) == 1:
            # Find grid and attach
            # We are inside the Grid (self.add(grid)). 
            # self.get_child() should return grid.
            grid = self.get_child()
            if grid and isinstance(grid, Gtk.Grid):
                grid.attach(self.subs_box, 0, 1, 4, 1)
                self.subs_box.show_all()

    def _remove_sub_button(self, index):
        current_subs = self.action_data.get("sub_buttons", [])
        if 0 <= index < len(current_subs):
            current_subs.pop(index)
            self.action_data["sub_buttons"] = current_subs
            self.window.save_buttons()
            self._refresh_sub_buttons_ui()

    def _refresh_sub_buttons_ui(self):
        # Clear existing
        for child in self.subs_box.get_children():
            self.subs_box.remove(child)
            
        subs = self.action_data.get("sub_buttons", [])
        for i, sub in enumerate(subs):
            # Create a small pill/chip
            # Create a composite widget for the sub-button
            # [ Icon | Name | X ]
            
            # Container for the pill
            pill = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            pill.get_style_context().add_class("linked")
            
            # Icon + Name Button (could be just a label, but button gives hover effect)
            # Actually, standard pattern is:
            # [ Icon Label ] [ X ] 
            # represented as two buttons linked, or a Box with style "linked" containing buttons.
            
            # Main part
            main_btn = Gtk.Button()
            main_btn.set_relief(Gtk.ReliefStyle.NONE)
            main_content = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
            icon_img = Gtk.Image.new_from_icon_name(sub.get("icon", "system-run-symbolic"), Gtk.IconSize.MENU)
            lbl = Gtk.Label(label=sub.get("name", ""))
            main_content.pack_start(icon_img, False, False, 0)
            if sub.get("name"):
                main_content.pack_start(lbl, False, False, 0)
            main_btn.add(main_content)
            # main_btn.set_tooltip_text(sub.get("action")) # Optional tooltip
            
            # Delete part
            del_sub_btn = Gtk.Button()
            del_sub_btn.set_relief(Gtk.ReliefStyle.NONE)
            del_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
            del_sub_btn.set_image(del_icon)
            del_sub_btn.get_style_context().add_class("destructive-action")
            del_sub_btn.connect("clicked", lambda x, idx=i: self._remove_sub_button(idx))
            
            pill.add(main_btn)
            pill.add(del_sub_btn)
            
            # Pack into a container that doesn't expand, aligned start
            row_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
            row_box.pack_start(pill, False, False, 0)
            
            self.subs_box.add(row_box)
        
        self.subs_box.show_all()


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
    def __init__(self, parent, excluded_actions=None):
        super().__init__(title="Add Action", transient_for=parent, modal=True)
        self.excluded_actions = excluded_actions or []
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
        self.all_actions = AppScanner.get_all_actions()
        
        # Calculate required width based on longest name to prevent expansion
        max_len = 0
        for action in self.all_actions:
            name_len = len(action.get("name", ""))
            if name_len > max_len:
                max_len = name_len
                
        # Estimate width: (Chars * ~7px) + Icon(32) + Margins(~50) + Buffer
        # Default min 400, cap at reasonable screen width (e.g. 600)
        calc_width = max(400, int(max_len * 7) + 50)
        calc_width = min(calc_width, 600)
        
        self.set_default_size(calc_width, 500)
        
        self._populate_list("")
        
        self.show_all()


    def _populate_list(self, query):
        for child in self.listbox.get_children():
            self.listbox.remove(child)
            
        query = query.lower().strip()
        show_hidden = self.hidden_toggle.get_active()
        count = 0
        for action in self.all_actions:
            # Filter excluded actions (singletons)
            if action.get("action") in self.excluded_actions:
                continue

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
        icon.set_pixel_size(32)
        grid.attach(icon, 0, 0, 1, 1)
        
        lbl_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        grid.attach(lbl_box, 1, 0, 1, 1)
        
        name_lbl = Gtk.Label(label=action_data["name"])
        name_lbl.set_xalign(0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
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
