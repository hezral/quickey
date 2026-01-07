import gi
from gi.repository import GLib, Gio
import os
import shutil
from datetime import datetime
from .sub_utils.logging_util import get_logger

logger = get_logger("action_handler")

class ActionHandler:
    """Executes actions (Apps, Commands, Portals, MPRIS)"""
    
    def __init__(self, window_instance):
        self.window = window_instance
    
    def execute(self, action_type, action):
        logger.info(f"Executing action: {action} (Type: {action_type})")
        
        if action_type == "empty":
            self.window.app.show_preferences(parent=self.window)
            return

        if action_type == "internal":
            if action == "preferences":
                self.window.app.show_preferences(parent=self.window)
            elif action == "media":
                self.handle_media_portal()
            elif action == "files":
                self.handle_files_portal()
            elif action == "screenshot":
                self.handle_screenshot_portal()
        elif action_type == "command":
            self._run_host_command(action)
        elif action_type == "app":
            self._launch_app(action)
        elif action_type == "file":
            self._open_file(action)
        elif action_type == "prefix":
            logger.info(f"Prefix action triggered: {action} (Placeholder)")
            self.window.animate_quit()

    def _run_host_command(self, cmd):
        try:
            full_cmd = f"flatpak-spawn --host {cmd}"
            GLib.spawn_command_line_async(full_cmd)
            self.window.animate_quit()
        except Exception as e:
            logger.error(f"Failed to run command {cmd}: {e}")

    def _launch_app(self, action):
        try:
            if action.endswith(".desktop"):
                full_cmd = f"flatpak-spawn --host gtk-launch {action}"
            else:
                full_cmd = f"flatpak-spawn --host {action}"
            
            logger.info(f"Executing App: {full_cmd}")
            GLib.spawn_command_line_async(full_cmd)
            self.window.animate_quit()
        except Exception as e:
            logger.error(f"Failed to launch app {action}: {e}")

    def _open_file(self, path):
        try:
            logger.info(f"Opening file via Portal: {path}")
            
            # Use the OpenURI portal
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            proxy = Gio.DBusProxy.new_sync(
                bus,
                Gio.DBusProxyFlags.NONE,
                None,
                "org.freedesktop.portal.Desktop",
                "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.OpenURI",
                None
            )
            
            # Prepare file URI
            f = Gio.File.new_for_path(path)
            uri = f.get_uri()
            
            # Call OpenURI (parent_window, uri, options)
            # parent_window is empty string for now, or handle provided by xdp_parent if available.
            # Using "" works generally.
            proxy.call_sync(
                "OpenURI",
                GLib.Variant("(ssta{sv})", ("", uri, {}, {})),
                Gio.DBusCallFlags.NONE,
                -1,
                None
            )
            
            self.window.animate_quit()
        except Exception as e:
            logger.error(f"Failed to open file via Portal {path}: {e}")
            # Fallback to spawn if portal fails
            try:
                quoted_path = f"'{path}'"
                full_cmd = f"flatpak-spawn --host xdg-open {quoted_path}"
                logger.info(f"Fallback: Opening file via spawn: {full_cmd}")
                GLib.spawn_command_line_async(full_cmd)
                self.window.animate_quit()
            except Exception as e2:
                logger.error(f"Fallback failed: {e2}")

    # --- MPRIS Logic ---
    def handle_media_portal(self):
        self.handle_mpris_command("PlayPause")
        self.window.animate_quit()

    def get_mpris_state(self):
        """Returns True if any MPRIS player is 'Playing'"""
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            names_variant = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames", None, None, Gio.DBusCallFlags.NONE, -1, None)
            mpris_players = [n for n in names_variant.get_child_value(0).unpack() if n.startswith("org.mpris.MediaPlayer2.")]
            
            for player in mpris_players:
                reply = bus.call_sync(
                    player, "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties", "Get",
                    GLib.Variant("(ss)", ("org.mpris.MediaPlayer2.Player", "PlaybackStatus")),
                    GLib.VariantType("(v)"), Gio.DBusCallFlags.NONE, -1, None
                )
                status = reply.get_child_value(0).get_variant().unpack()
                if status == "Playing":
                    return True
        except Exception as e:
            logger.error(f"Failed to get MPRIS state: {e}")
        return False

    def handle_mpris_command(self, cmd):
        try:
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            names_variant = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames", None, None, Gio.DBusCallFlags.NONE, -1, None)
            mpris_players = [n for n in names_variant.get_child_value(0).unpack() if n.startswith("org.mpris.MediaPlayer2.")]
            
            for player in mpris_players:
                if cmd in ["PlayPause", "Next", "Previous", "Stop"]:
                    bus.call(player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", cmd, None, None, Gio.DBusCallFlags.NONE, -1, None, None)
                elif cmd == "Forward10":
                    bus.call(player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Seek", GLib.Variant("(x)", (10 * 1000000,)), None, Gio.DBusCallFlags.NONE, -1, None, None)
                elif cmd == "Backward10":
                    bus.call(player, "/org/mpris/MediaPlayer2", "org.mpris.MediaPlayer2.Player", "Seek", GLib.Variant("(x)", (-10 * 1000000,)), None, Gio.DBusCallFlags.NONE, -1, None, None)
        except Exception as e:
            logger.error(f"MPRIS command {cmd} failed: {e}")

    # --- Portal Logic ---
    def handle_files_portal(self):
        try:
            full_cmd = "flatpak-spawn --host xdg-open ."
            logger.info(f"Executing: {full_cmd}")
            GLib.spawn_command_line_async(full_cmd)
            self.window.animate_quit()
        except Exception as e:
            logger.error(f"Files action failed: {e}")

    def handle_screenshot_portal(self, mode="full"):
        try:
            interactive = mode in ["area", "window"]
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            timestamp = int(GLib.get_real_time() / 1000)
            token = f"quickey_screenshot_{timestamp}"
            sender = bus.get_unique_name().replace(".", "_").replace(":", "")
            handle_path = f"/org/freedesktop/portal/desktop/request/{sender}/{token}"
            
            bus.signal_subscribe(
                "org.freedesktop.portal.Desktop", "org.freedesktop.portal.Request", "Response",
                handle_path, None, Gio.DBusSignalFlags.NONE,
                self._on_screenshot_response, None
            )
            
            options = {
                "interactive": GLib.Variant("b", interactive),
                "handle_token": GLib.Variant("s", token)
            }
            
            # Hide window immediately
            self.window.set_visible(False)
            
            bus.call(
                "org.freedesktop.portal.Desktop", "/org/freedesktop/portal/desktop",
                "org.freedesktop.portal.Screenshot", "Screenshot",
                GLib.Variant("(sa{sv})", ("", options)),
                None, Gio.DBusCallFlags.NONE, -1, None, None
            )
        except Exception as e:
            logger.error(f"Screenshot request failed: {e}")
            self.window.animate_quit()
        return False

    def _on_screenshot_response(self, connection, sender, path, interface, signal, params, user_data):
        try:
            response_code, results = params.unpack()
            if response_code == 0 and "uri" in results:
                uri = results["uri"]
                src_path = uri.replace("file://", "")
                if os.path.exists(src_path):
                    btn_pictures = GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_PICTURES)
                    save_dir = os.path.join(btn_pictures, "Screenshots")
                    os.makedirs(save_dir, exist_ok=True)
                    filename = datetime.now().strftime("Screenshot from %Y-%m-%d %H-%M-%S.png")
                    dest_path = os.path.join(save_dir, filename)
                    shutil.copy(src_path, dest_path)
                    logger.info(f"Saved screenshot to: {dest_path}")
        except Exception as e:
            logger.error(f"Error handling screenshot response: {e}")
        
        self.window.animate_quit(should_quit_app=True)
