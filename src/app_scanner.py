import os
from gi.repository import Gio
from .sub_utils.logging_util import get_logger

logger = get_logger("app_scanner")

class AppScanner:
    """Scans for installed applications and actions"""
    
    @staticmethod
    def get_all_actions():
        actions = []
        logger.info("AppScanner: Starting action discovery...")
        
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
        logger.info(f"AppScanner: Gio found {len(apps)} initial apps.")
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
                continue
            
            try:
                files = os.listdir(path)
                for file_name in files:
                    if not file_name.endswith(".desktop"):
                        continue
                    
                    norm_id = file_name[:-8]
                    if norm_id in seen_ids:
                        continue
                    
                    actions.append(AppScanner._parse_desktop_file(path, file_name))
                    seen_ids.add(norm_id)
                    
            except Exception as e:
                logger.warning(f"AppScanner: Failed to list {path}: {e}")
        
        # Sort apps by name (skipping builtins)
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
        
        logger.info(f"AppScanner: Total actions prepared: {len(actions)}")
        return actions

    @staticmethod
    def _parse_desktop_file(path, file_name):
        full_path = os.path.join(path, file_name)
        name, icon_name, desc, hidden = None, "system-run-symbolic", "", False
        
        # Try Gio first
        try:
            app = Gio.DesktopAppInfo.new_from_filename(full_path)
            if app:
                name = app.get_name()
                icon = app.get_icon()
                icon_name = icon.to_string() if icon else "system-run-symbolic"
                desc = app.get_description() or ""
                hidden = app.get_nodisplay()
        except Exception:
            pass
        
        # Manual fallback
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
            except Exception:
                pass
                
        return {
            "name": name or file_name,
            "icon": icon_name or "system-run-symbolic",
            "type": "app",
            "action": file_name,
            "desc": desc,
            "group": "Applications",
            "hidden": hidden,
            "is_flatpak": "flatpak" in path.lower()
        }
