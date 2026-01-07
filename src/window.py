import math
import logging
import json
import os
import shutil
import gc
from datetime import datetime
import gi
gi.require_version('Handy', '1')
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Handy, GObject, Gdk, GLib, Gio

from .mode_switch import ModeSwitch
from .sub_utils.logging_util import get_logger, log_function_calls
from .config_manager import ConfigManager
from .action_handler import ActionHandler
from .preferences import ActionPicker

logger = get_logger("window")

class quickeyWindow(Handy.ApplicationWindow):
    __gtype_name__ = 'quickeyWindow'

    Handy.init()

    @log_function_calls
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        logger.info(f"Initializing quickeyWindow as Ring Menu. Backend: {Gdk.Screen.get_default().get_display().get_name()}")

        self.app = self.props.application
        self.is_quitting = False
        
        # Initialize Logic Handlers
        self.config_manager = ConfigManager(self.app.gio_settings)
        self.action_handler = ActionHandler(self)
        
        # Window Setup
        self.set_decorated(False)
        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("quickey-window")
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY) # Better focus management
        self.set_accept_focus(True)
        self.set_gravity(Gdk.Gravity.NORTH_WEST)
        self.set_skip_taskbar_hint(True)
        self.set_keep_above(True)
        self.set_position(Gtk.WindowPosition.NONE)
        self.stick() 
        self.set_focus_on_map(True)

        self.props.default_width = 600
        self.props.default_height = 600
        
        screen = self.get_screen()
        visual = screen.get_rgba_visual()
        if visual:
            self.set_visual(visual)

        # Main Container
        self.overlay = Gtk.Overlay()
        self.fixed = Gtk.Fixed()
        self.overlay.add(self.fixed)
        
        # Content Setup
        self.ring_buttons = []
        self.all_label_data = [] # Initialize before setup
        self.radius = 100 # Increased from 80
        self.setup_ring_menu()
        
        self.add(self.overlay)
        
        # Connect signals for initial positioning
        self.map_handler_id = self.connect("map-event", self._on_map_event)
        self.draw_handler_id = self.connect("draw", self._on_draw_event)
        
        # Focus/Click tracking
        self.add_events(Gdk.EventMask.FOCUS_CHANGE_MASK | Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("button-press-event", self._on_button_press)

        # Initial target setup (default to center if triggered during init)
        self.target_x = self.target_y = 0
        
        # Real-time settings sync: Refresh ring when buttons-json changes
        self.app.gio_settings.connect("changed::buttons-json", self._on_settings_buttons_changed)
        
        logger.info("Ring menu shown at cursor with animation")

    def _on_settings_buttons_changed(self, settings, key):
        logger.info("Settings changed: refreshing ring menu buttons")
        GLib.idle_add(self.refresh_all_ring_buttons)

    def load_configured_buttons(self):
        return self.config_manager.load_configured_buttons()

    def on_remove_action(self, button, index):
        self.config_manager.reset_slot(index)
        self.refresh_button_ui(index, self.config_manager._create_empty_slot())


    def refresh_button_ui(self, index, data):
        btn = self.ring_buttons[index]
        label_data = self.all_label_data[index]
        
        # 0. Rebuild Sub-buttons structure
        self._rebuild_sub_buttons(index, data)
        
        icon_name = data.get("icon", "system-run-symbolic")
        
        # Dynamic Media Icon
        if data.get("action") == "media":
            is_playing = self.action_handler.get_mpris_state()
            icon_name = "media-playback-pause" if is_playing else "media-playback-start"
        
        img = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
        img.set_pixel_size(24)
        btn.set_image(img)
        btn._action_data = data
        
        # Update label text
        label_data['lb'].get_children()[0].set_text(data.get("name", "Empty"))

        if data.get("type") == "empty" or index == 7:
            pass
        else:
            pass

        # Recalculate label position
        lb = label_data['lb']
        lb.show_all()
        
        _, nw = lb.get_preferred_width()
        _, nh = lb.get_preferred_height()
        
        angle = (index * (360 / 8) - 90) * (math.pi / 180)
        
        # Position label further out if there are sub-buttons
        # Main Radius 100. Sub radius 160 + sub size 15 + desired gap 15 = 190
        # _get_label_pos uses: base_radius(100) + button_radius(24) + gap
        # 100 + 24 + 66 = 190. Perfect 15px gap from satellite edge.
        gap = 66 if len(label_data.get('sd', [])) > 0 else 15
        pos = self._get_label_pos(nw, nh, angle, self.radius, gap=gap, button_radius=24) 
        self.fixed.move(lb, pos[0], pos[1])
        
        # Also reposition sub-button labels if any
        for sl_data in label_data.get('sl', []):
            slb = sl_data['lb']
            slb.show_all()
            _, snw = slb.get_preferred_width()
            _, snh = slb.get_preferred_height()
            s_angle = sl_data['angle']
            # Sub labels at 190px total distance.
            s_pos = self._get_label_pos(snw, snh, s_angle, self.radius, gap=66, button_radius=24)
            self.fixed.move(slb, s_pos[0], s_pos[1])
    
    def on_button_clicked(self, button, data=None):
        if data is None:
            data = getattr(button, "_action_data", {})
        
        action_type = data.get("type")
        action = data.get("action")
        
        if action_type == "empty":
             # Find index of this button
             try:
                 index = self.ring_buttons.index(button)
                 self.open_action_picker(index)
             except ValueError:
                 pass
             return

        self.action_handler.execute(action_type, action)

    def open_action_picker(self, index):
        self.is_configuring = True
        self.set_keep_above(False) # Allow dialog to be on top
        
        # Identify excluded actions
        excluded = []
        singletons = ["media", "screenshot", "preferences"]
        buttons = self.config_manager.load_configured_buttons()
        
        for i, btn in enumerate(buttons):
            if i == index: continue
            
            act = btn.get("action")
            if act in singletons:
                excluded.append(act)

        picker = ActionPicker(self, excluded_actions=excluded)
        if picker.run() == Gtk.ResponseType.OK:
            result = picker.get_result()
            if result:
                logger.info(f"Configuring slot {index} with {result['name']}")
                # Load, Update, Save
                buttons = self.config_manager.load_configured_buttons()
                buttons[index] = result
                self.config_manager.save_buttons(buttons)
                self.refresh_all_ring_buttons()
        picker.destroy()
        
        self.is_configuring = False
        self.set_keep_above(True)

    def on_sub_button_clicked(self, widget, data):
        action = data.get("action")
        logger.info(f"Sub-button clicked: {action}")
        
        # Built-in MPRIS overrides for specialized behavior
        if action in ["Previous", "Next", "Backward10", "Forward10", "PlayPause", "Stop"]:
            self.action_handler.handle_mpris_command(action)
            self.refresh_all_ring_buttons()
            return
            
        if "screenshot" in action:
             # Handle screenshot actions: area, window, full, area_5s, window_5s, full_5s
            mode = action.replace("screenshot_", "")
            delay = 5 if "_5s" in mode else 0
            clean_mode = mode.replace("_5s", "")
            
            if delay > 0:
                logger.info(f"Delaying screenshot {clean_mode} by {delay}s")
                self.set_visible(False)
                GLib.timeout_add_seconds(delay, self.action_handler.handle_screenshot_portal, clean_mode)
            else:
                self.action_handler.handle_screenshot_portal(clean_mode)
            return

        # Generic handling
        self.action_handler.execute(data.get("type"), action)

    def refresh_all_ring_buttons(self):
        items_data = self.load_configured_buttons()
        for i, data in enumerate(items_data):
            self.refresh_button_ui(i, data)

    def _get_label_pos(self, nw, nh, angle, base_radius, gap=15, button_radius=24):
        center_x = 300
        center_y = 300
        
        # Normalize angle for easier checks
        norm_angle = angle % (2 * math.pi)
        deg = round(math.degrees(norm_angle)) % 360
        
        dx, dy = math.cos(angle), math.sin(angle)
        
        # Button center
        bx = center_x + base_radius * dx
        by = center_y + base_radius * dy
        
        # Cardinal Checks
        if deg == 270 or deg == 90: # 12 or 6 o'clock
            lx = center_x - nw / 2
            ly = (by - button_radius - gap - nh) if deg == 270 else (by + button_radius + gap)
        elif deg == 0 or deg == 180: # 3 or 9 o'clock
            lx = (bx + button_radius + gap) if deg == 0 else (bx - button_radius - gap - nw)
            ly = center_y - nh / 2
        else:
            # Diagonals - anchor by closest corner
            anchor_x = bx + (button_radius + gap) * dx
            anchor_y = by + (button_radius + gap) * dy
            lx = anchor_x if dx > 0 else anchor_x - nw
            ly = anchor_y if dy > 0 else anchor_y - nh
            
        return (int(round(lx)), int(round(ly)))

    def _create_label(self, text):
        lb = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        lb.get_style_context().add_class("label-box")
        lbl = Gtk.Label(text)
        lbl.set_xalign(0.5)
        lbl.set_halign(Gtk.Align.CENTER)
        lb.add(lbl)
        return lb

    def reposition_all_labels(self):
        """Final positioning pass after window is mapped and CSS is applied"""
        logger.info("Repositioning all labels after map event...")
        for i, label_data in enumerate(self.all_label_data):
            lb = label_data['lb']
            # Re-measure now that CSS is definitely resolved
            _, nw = lb.get_preferred_width()
            _, nh = lb.get_preferred_height()
            
            angle = (i * (360 / 8) - 90) * (math.pi / 180)
            gap = 66 if len(label_data.get('sd', [])) > 0 else 15
            pos = self._get_label_pos(nw, nh, angle, self.radius, gap=gap, button_radius=24)
            self.fixed.move(lb, pos[0], pos[1])
            
            for sl_data in label_data.get('sl', []):
                slb = sl_data['lb']
                _, snw = slb.get_preferred_width()
                _, snh = slb.get_preferred_height()
                s_angle = sl_data['angle']
                s_pos = self._get_label_pos(snw, snh, s_angle, self.radius, gap=66, button_radius=24)
                self.fixed.move(slb, s_pos[0], s_pos[1])

    def _rebuild_sub_buttons(self, index, data):
        """Destroys existing and creates new sub-buttons for a given slot index"""
        label_data = self.all_label_data[index]
        
        # 1. Cleanup existing sub-buttons
        for sb in label_data.get('sd', []):
            sb.destroy()
        for sl_data in label_data.get('sl', []):
            sl_data['lb'].destroy()
            
        label_data['sd'] = []
        label_data['sl'] = []
        
        # 2. Check if new action has sub-buttons
        action_key = data.get("action")
        
        # Build normalized sub_actions list
        sub_actions = []
        
        # 1. Custom User Sub-buttons (Highest Priority)
        user_subs = data.get("sub_buttons", [])
        if user_subs:
            for subs in user_subs:
                 # Standardize tuple format: (icon, action/data, label)
                 # For generic sub-buttons, pass specific dict as action data
                 sub_actions.append((subs.get("icon", "system-run-symbolic"), subs, subs.get("name", "")))
        
        # 2. Built-in Fallbacks (Only if no custom logic overrides perfectly, 
        # but here we usually append or replace. For now, let's say Built-ins apply 
        # normally if no user subs, OR valid for some mix.
        # Current logic: If key in map, use it. PROPOSED: Merge or replace?)
        # Let's simple append for now or use built-in if user config is empty.
        # Actually, "Files" has no built-ins. "Media" does.
        # If user adds to Media, do we keep original controls?
        # User said "add another button... to add sub button". Implies adding TO existing.
        # So we extend.
        elif action_key in self.sub_action_map:
             # Legacy map used tuple: (icon, action_string_key, label)
             for icon, act_key, lbl in self.sub_action_map[action_key]:
                 sub_actions.append((icon, act_key, lbl))
        
        if sub_actions:
            center_x, center_y = 300, 300
            outer_radius = 160
            
            # Calculate angle based on index (same logic as setup_ring_menu)
            angle = (index * (360 / 8) - 90) * (math.pi / 180)
            
            count = len(sub_actions)
            # Dynamic centered spacing
            spacing = 20 # Degrees between buttons
            total_spread = (count - 1) * spacing
            start_offset = -total_spread / 2
            
            for j, (icon, action_payload, label_text) in enumerate(sub_actions):
                sb = Gtk.Button()
                sb.get_style_context().add_class("sub-button") 
                sb.get_style_context().add_class("hidden")
                
                # Legacy mapping: If user config has old names, map to new names
                icon_map = {
                    "grab-area-symbolic": "quickey-grab-area",
                    "grab-window-symbolic": "quickey-grab-window", 
                    "grab-screen-symbolic": "quickey-grab-screen"
                }
                final_icon = icon_map.get(icon, icon)
                
                sb.set_image(Gtk.Image.new_from_icon_name(final_icon, Gtk.IconSize.MENU))
                sb.set_size_request(30, 30) 
                
                # IMPORTANT: Pass action_payload (either dict or string)
                # We need to wrap string in dict for the new handler if it is from built-ins
                final_data = action_payload
                if isinstance(action_payload, str):
                    final_data = {"action": action_payload, "type": "internal" if "screenshot" in action_payload or "Previous" in action_payload else "command"} 
                    # Note: Existing built-ins (Previous/Next) are handled by specific string checks in on_sub_button_clicked
                    # so passing the raw string as 'action' in a dict works best for compatibility if we adjust handler.
                    final_data = {"action": action_payload} 

                sb.connect("clicked", self.on_sub_button_clicked, final_data)
                
                sa = angle + (start_offset + j * spacing) * math.pi / 180
                sx = center_x + outer_radius * math.cos(sa)
                sy = center_y + outer_radius * math.sin(sa)
                
                # Position center of sub-button
                # 30px size -> offset 15
                self.fixed.put(sb, int(sx - 15), int(sy - 15))
                sb.show() # Ensure widget is realized/visible (CSS 'hidden' still applies)
                label_data['sd'].append(sb)
                
                # Create Label
                sub_lb = self._create_label(label_text)
                self.fixed.put(sub_lb, 0, 0) # Will be positioned by refresh_button_ui
                sub_lb.show_all() # Ensure label is visible (CSS controls opacity)
                label_data['sl'].append({'lb': sub_lb, 'angle': sa})

                # Connect hover events
                # We need references to the main label and THIS sub label
                main_lb = label_data['lb']
                main_btn = label_data['btn']
                
                # We use a closure but need to be careful with binding
                # Using functools.partial or default args is safer, but inner execution
                # contexts in python hold 'sb' and 'sub_lb' correctly if defined here.
                
                def on_sub_enter(widget, event, _main_lb=main_lb, _this_sub_lb=sub_lb, _main_btn=main_btn):
                    _main_lb.get_style_context().remove_class("visible")
                    _this_sub_lb.get_style_context().add_class("visible")
                    
                    # Keep main button highlighted
                    _main_btn.get_style_context().add_class("active-parent")
                    
                def on_sub_leave(widget, event, _main_lb=main_lb, _this_sub_lb=sub_lb, _main_btn=main_btn):
                    _this_sub_lb.get_style_context().remove_class("visible")
                    # Do NOT remove active-parent here. Rely on main exit timeout.
                    
                    # Debounce restoring main label (already exists, keeping it separate for now)
                    GLib.timeout_add(50, self._check_restore_label, _main_lb, _main_btn)
                    
                sb.connect("enter-notify-event", on_sub_enter)
                sb.connect("leave-notify-event", on_sub_leave)

    def _check_restore_label(self, main_lb, main_btn):
        # Find label_data for this main_lb
        # Optimization: Pass label_data in if possible, but search is cheap for 8 items
        label_data = next((item for item in self.all_label_data if item['lb'] == main_lb), None)
        any_sub_hovered = False
        if label_data:
            for sub_btn in label_data['sd']:
                if sub_btn.get_state_flags() & Gtk.StateFlags.PRELIGHT:
                    any_sub_hovered = True
                    break
        
        main_hovered = main_btn.get_state_flags() & Gtk.StateFlags.PRELIGHT
        
        if not any_sub_hovered and main_hovered:
            main_lb.get_style_context().add_class("visible")
            
        return False

    def setup_ring_menu(self):
        items_data = self.load_configured_buttons()
        
        center_x = 300
        center_y = 300
        radius = self.radius 
        
        # Center Close Button
        close_btn = Gtk.Button()
        close_btn.get_style_context().add_class("center-button")
        close_icon = Gtk.Image.new_from_icon_name("window-close-symbolic", Gtk.IconSize.MENU)
        close_btn.set_image(close_icon)
        close_btn.set_always_show_image(True)
        close_btn.props.valign = close_btn.props.halign = Gtk.Align.CENTER
        close_btn.set_size_request(40, 40)
        close_btn.connect("clicked", lambda x: self.animate_quit())
        # Use Fixed for absolute centering instead of Overlay
        self.fixed.put(close_btn, center_x - 20, center_y - 20)
        self.close_btn = close_btn
        
        # Define sub-action map once
        self.sub_action_map = {
            "media": [
                ("media-skip-backward-symbolic", "Previous", "Prev"),
                ("media-seek-backward-symbolic", "Backward10", "-10s"),
                ("media-seek-forward-symbolic", "Forward10", "+10s"),
                ("media-skip-forward-symbolic", "Next", "Next"),
            ],
            "screenshot": [
                ("quickey-grab-area", "screenshot_area", "Area"),
                ("quickey-grab-window", "screenshot_window", "Window"),
                ("quickey-grab-screen", "screenshot_full", "Full"),
                ("quickey-grab-area", "screenshot_area_5s", "Area (5s)"),
                ("quickey-grab-window", "screenshot_window_5s", "Window (5s)"),
                ("quickey-grab-screen", "screenshot_full_5s", "Full (5s)"),
            ]
        }

        num_items = len(items_data)
        for i, data in enumerate(items_data):
            name = data.get("name", "Unknown")
            icon_name = data.get("icon", "system-run-symbolic")
            
            angle = (i * (360 / num_items) - 90) * (math.pi / 180)
            x, y = center_x + radius * math.cos(angle), center_y + radius * math.sin(angle)
            
            btn = Gtk.Button()
            btn.get_style_context().add_class("ring-button")
            btn.get_style_context().add_class("hidden")
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            icon.set_pixel_size(24)
            btn.set_image(icon)
            btn.set_always_show_image(True)
            btn.set_size_request(48, 48)
            btn._action_data = data
            btn.connect("clicked", self.on_button_clicked)
            
            # Position calculations: center of btn should be at (x, y)
            # Offset by half of 48px
            self.fixed.put(btn, int(x - 24), int(y - 24))
            self.ring_buttons.append(btn)
            
            # Store for global hiding
            label_box = self._create_label(name)
            
            # Initial Setup
            self.fixed.put(label_box, 0, 0)
            
            # Store widgets for easy access
            this_label_data = {
                'lb': label_box, 
                'btn': btn,
                'sd': [], # sub-buttons
                'sl': []  # sub-button labels
            }
            self.all_label_data.append(this_label_data)
            
            # Generate sub-buttons (reusing the new helper)
            self._rebuild_sub_buttons(i, data)

            # New hover logic for main button
            def on_btn_enter(widget, event, lb, label_data, this_btn=btn):
                # 1. Hide all other elements
                for item in self.all_label_data:
                    item['lb'].get_style_context().remove_class("visible")
                    
                    # Force remove active-parent from ALL other buttons to fix persistence bug
                    if item['btn'] != this_btn:
                         item['btn'].get_style_context().remove_class("active-parent")
                         if hasattr(item['btn'], "_highlight_timeout") and item['btn']._highlight_timeout:
                             GLib.source_remove(item['btn']._highlight_timeout)
                             item['btn']._highlight_timeout = None
                    
                    for sb in item['sd']:
                        sb.get_style_context().add_class("hidden")
                    for sl_data in item.get('sl', []):
                        sl_data['lb'].get_style_context().remove_class("visible")
                        
                lb.get_style_context().add_class("visible")
                
                # Show sub-buttons for THIS button
                for sb in label_data['sd']:
                    sb.get_style_context().remove_class("hidden")
                    
            def on_btn_leave(widget, event, lb, main_btn):
                GLib.timeout_add(400, self._maybe_hide_refined_v5, lb, None, main_btn)

            btn.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK | Gdk.EventMask.LEAVE_NOTIFY_MASK)
            # Pass the DICT (this_label_data) which contains the live list 'sd'
            btn.connect("enter-notify-event", on_btn_enter, label_box, this_label_data)
            btn.connect("leave-notify-event", on_btn_leave, label_box, btn)
            
            # Initial positioning
            self.refresh_button_ui(i, data)

    def _maybe_hide_refined_v5(self, lb, rb, main_btn):
        # Check if mouse is still in main_btn OR sub-buttons
        is_hovered = main_btn.get_state_flags() & Gtk.StateFlags.PRELIGHT
        
        # Check sub-buttons
        label_data = next((item for item in self.all_label_data if item['lb'] == lb), None)
        if not is_hovered and label_data:
            for sb in label_data['sd']:
                if sb.get_state_flags() & Gtk.StateFlags.PRELIGHT:
                    is_hovered = True
                    break

        if not is_hovered:
            lb.get_style_context().remove_class("visible")
            # Clear parent highlight when truly leaving interaction group
            main_btn.get_style_context().remove_class("active-parent")
            
            if label_data:
                for sb in label_data['sd']:
                    sb.get_style_context().add_class("hidden")
                for sl_data in label_data.get('sl', []):
                    sl_data['lb'].get_style_context().remove_class("visible")
            if rb:
                rb.get_style_context().remove_class("visible")
                rb.set_visible(False)
        return False

    def animate_launch(self):
        # Micro-Optimization 1: Disable GC to prevent stutters
        gc.disable()
        
        start_time = None
        duration_us = 450 * 1000 
        num_items = len(self.ring_buttons)
        if num_items == 0: 
            gc.enable()
            return
            
        # Micro-Optimization 2: Pre-calculate constants and deltas
        center_x, center_y = 300, 300
        radius = self.radius
        start_angle = -math.pi / 2
        
        anim_targets = []
        for i, btn in enumerate(self.ring_buttons):
            btn.get_style_context().remove_class("hidden")
            btn.get_style_context().add_class("animating")
            
            target_angle = (i * (360 / num_items) - 90) * (math.pi / 180)
            delta = target_angle - start_angle
            anim_targets.append((btn, delta))

        def cubic_ease_out(t):
            return 1 - (1 - t) ** 3
            
        def animation_tick(widget, frame_clock):
            nonlocal start_time
            now = frame_clock.get_frame_time()
            if start_time is None:
                start_time = now
            
            elapsed = now - start_time
            proc = min(elapsed / duration_us, 1.0)
            
            ease_val = cubic_ease_out(proc)
            
            for btn, delta in anim_targets:
                curr_angle = start_angle + delta * ease_val
                
                x = center_x + radius * math.cos(curr_angle)
                y = center_y + radius * math.sin(curr_angle)
                
                # Micro-Optimization 3: Rounding for stability
                self.fixed.move(btn, int(round(x - 24)), int(round(y - 24)))
                
            if proc < 1.0:
                return True 
            else:
                # Cleanup
                for btn in self.ring_buttons:
                    btn.get_style_context().remove_class("animating")
                gc.enable() # Re-enable GC
                return False 
                
        self.add_tick_callback(animation_tick)

    @log_function_calls
    def reposition_and_present(self):
        # Stealth Sync Strategy (Optimized)
        logger.info("Triggering Stealth Pointer Sync...")
        
        screen = Gdk.Screen.get_default()
        sync_window = Gtk.Window(type=Gtk.WindowType.TOPLEVEL)
        sync_window.set_type_hint(Gdk.WindowTypeHint.DND)
        sync_window.set_visual(screen.get_rgba_visual())
        sync_window.set_decorated(False)
        sync_window.set_opacity(0.0)
        sync_window.set_accept_focus(False)
        
        provider = Gtk.CssProvider()
        provider.load_from_data(b"window { background: transparent; }")
        sync_window.get_style_context().add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        
        # Cover all monitors to be safe
        sync_window.set_default_size(screen.get_width() + 1000, screen.get_height() + 1000)
        sync_window.move(-500, -500)
        
        sync_window.show() 
        
        # Reduced delay (80ms) - slightly bumped for empty desktop reliability
        GLib.timeout_add(80, self._finalize_reposition, sync_window)
        return False

    def _finalize_reposition(self, sync_window):
        # Sync complete, capture the TRUE global position
        display = Gdk.Display.get_default()
        root_window = display.get_default_screen().get_root_window()
        client_pointer = display.get_device_manager().get_client_pointer()
        _, root_x, root_y, _ = root_window.get_device_position(client_pointer)
        
        self.target_x, self.target_y = root_x, root_y
        logger.info(f"Sync Complete. Actual Target: ({self.target_x}, {self.target_y})")

        sync_window.destroy()

        # Place the real window
        self.reposition_to_cursor(self.target_x, self.target_y)
        self.show_all()
        # Final presentation
        Gdk.notify_startup_complete()
        self.present()
        
        # WM placement fixups
        GLib.timeout_add(40, self.reposition_to_cursor, self.target_x, self.target_y)
        GLib.timeout_add(200, self.reposition_to_cursor, self.target_x, self.target_y)
        
        self.animate_launch()
        return False

    def _on_map_event(self, widget, event):
        if self.map_handler_id:
            self.disconnect(self.map_handler_id)
            self.map_handler_id = None
        
        # Recalculate positions now that CSS is fully loaded
        self.reposition_all_labels()

        if hasattr(self, 'target_x'):
            self.reposition_to_cursor(self.target_x, self.target_y)
        return False

    def _on_draw_event(self, widget, cr):
        if self.draw_handler_id:
            self.disconnect(self.draw_handler_id)
            self.draw_handler_id = None
            
        if hasattr(self, 'target_x'):
            self.reposition_to_cursor(self.target_x, self.target_y)
        return False

    def reposition_to_cursor(self, forced_x=None, forced_y=None):
        display = Gdk.Display.get_default()
        if not display:
            logger.error("Could not get default display")
            return
            
        if forced_x is not None and forced_y is not None:
            x, y = forced_x, forced_y
        else:
            seat = display.get_default_seat()
            if not seat:
                logger.error("Could not get default seat")
                return
                
            pointer = seat.get_pointer()
            if not pointer:
                logger.error("Could not get pointer")
                return
                
            screen, x, y = pointer.get_position()
            logger.info(f"Retrieved fresh cursor position: ({x}, {y})")
        
        # Adjusted window size for better boundary management
        width = 600
        height = 600
        
        logger.debug(f"Window sizing for positioning: {width}x{height}")
        
        # Center the window at the cursor
        target_x = x - (width // 2)
        target_y = y - (height // 2)
        
        # Get monitor for this position to handle boundaries
        monitor = display.get_monitor_at_point(x, y)
        if monitor:
            geometry = monitor.get_geometry()
            logger.debug(f"Monitor geometry: {geometry.x, geometry.y, geometry.width, geometry.height}")
            
            target_x = max(geometry.x, min(target_x, geometry.x + geometry.width - width))
            target_y = max(geometry.y, min(target_y, geometry.y + geometry.height - height))

        # logger.info(f"Forcing move to target: ({target_x}, {target_y})")
        self.move(target_x, target_y)
        
        self.set_keep_above(True)
        
        # Verify if move was respected in the next main loop iteration
        if logger.isEnabledFor(logging.DEBUG):
            def log_pos():
                if self.get_window():
                    logger.debug(f"Current reported window position: {self.get_position()}")
                return False
            GLib.idle_add(log_pos)
        
        return False # For timeout_add

    def _on_focus_out(self, widget, event):
        if self.is_quitting or getattr(self, "is_configuring", False):
            logger.info("Focus lost but quitting or configuring, ignoring.")
            return False
            
        # Check if focus moved to another window of the same app (like Preferences)
        def check_focus():
            # If we already destroyed/quitting, bail
            if self.is_quitting:
                return False

            active_window = self.app.get_active_window()
            # If any window in the app is PreferencesWindow, don't quit the ring
            all_windows = self.app.get_windows()
            has_preferences = any(w.__class__.__name__ == "PreferencesWindow" for w in all_windows)
            
            if has_preferences:
                logger.info("Preferences window exists. Keeping ring menu.")
                return False

            if active_window and active_window != self:
                logger.info(f"Focus moved to internal window: {active_window.get_title()}. Keeping ring.")
                return False
            
            logger.info("Focus lost to external app, quitting with animation...")
            self.animate_quit()
            return False

        # Small delay to let active_window update
        GLib.timeout_add(150, check_focus)
        return False

    def _on_button_press(self, widget, event):
        # This will be called if no child (like a button) handled the press
        # or if the click was on empty space within the 600x600 window
        logger.info("Click on empty space, quitting with animation...")
        self.animate_quit()
        return False


    def animate_quit(self, should_quit_app=True):
        if self.is_quitting:
            logger.info("animate_quit called but already in progress.")
            return
        logger.info(f"animate_quit(should_quit_app={should_quit_app}) started.")
        self.is_quitting = True
        self.set_sensitive(False) # Prevent further clicks

        def hide_button(indices):
            if indices:
                idx = indices.pop(0)
                self.ring_buttons[idx].get_style_context().add_class("hidden")
                # Hide sub-buttons too
                for sb in self.all_label_data[idx]['sd']:
                    sb.get_style_context().add_class("hidden")
                for sl_data in self.all_label_data[idx].get('sl', []):
                    sl_data['lb'].get_style_context().remove_class("visible")
                GLib.timeout_add(25, hide_button, indices)
            else:
                self.close_btn.get_style_context().add_class("hidden")
                if should_quit_app:
                    logger.info("Sheduling app.quit")
                    GLib.timeout_add(120, self.app.quit)
                else:
                    logger.info("Scheduling self.destroy (app should stay alive)")
                    GLib.timeout_add(120, self.destroy)
            return False

        num = len(self.ring_buttons)
        if num > 0:
            # Counter-clockwise starting from 12 o'clock (index 0)
            # 0, 7, 6, 5, 4, 3, 2, 1
            indices = [0] + list(range(num - 1, 0, -1))
            hide_button(indices)
        else:
            self.app.quit()
