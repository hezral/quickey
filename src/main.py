# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 Adi Hezral <hezral@gmail.com>

import sys
import os

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Granite', '1.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gio, Granite, Gdk, GLib

from .window import quickeyWindow
from .preferences import PreferencesWindow
from .sub_utils.logging_util import init_logging, get_logger

logger = get_logger("main")


class Application(Gtk.Application):

    app_id = "com.github.hezral.quickey"
    gio_settings = Gio.Settings(schema_id=app_id)
    gtk_settings = Gtk.Settings().get_default()
    granite_settings = Granite.Settings.get_default()

    def __init__(self):
        super().__init__(application_id=self.app_id,
                         flags=Gio.ApplicationFlags.FLAGS_NONE)
        
        # Add command line options
        self.add_main_option("debug", ord("d"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Enable debug logging", None)
        self.add_main_option("verbose", ord("v"), GLib.OptionFlags.NONE, GLib.OptionArg.NONE, "Enable verbose logging", None)
        self.connect("handle-local-options", self.on_handle_local_options)

    def do_activate(self):
        # Find if we already have a ring menu window
        self.window = next((w for w in self.get_windows() if isinstance(w, quickeyWindow)), None)
        if self.window is None:
            self.window = quickeyWindow(application=self)
        
        # reposition_and_present handles the idle_add or immediate call internally
        self.window.reposition_and_present()

    def do_startup(self):
        Gtk.Application.do_startup(self)
        
        # Support quiting app using Super+Q
        quit_action = Gio.SimpleAction.new("quit", None)
        quit_action.connect("activate", self.on_quit_action)
        self.add_action(quit_action)
        self.set_accels_for_action("app.quit", ["<Ctrl>Q", "Escape"])

        prefers_color_scheme = self.granite_settings.get_prefers_color_scheme()
        self.gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_color_scheme)
        self.granite_settings.connect("notify::prefers-color-scheme", self.on_prefers_color_scheme)

        if "io.elementary.stylesheet" not in self.gtk_settings.props.gtk_theme_name:
            self.gtk_settings.set_property("gtk-theme-name", "io.elementary.stylesheet.blueberry")

        # set CSS provider
        provider = Gtk.CssProvider()
        
        # Robustly find CSS in source tree or installed paths
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "data", "application.css"),      # Installed
            os.path.join(os.path.dirname(__file__), "..", "data", "application.css") # Source Tree
        ]
        
        css_path = None
        for p in possible_paths:
            if os.path.exists(p):
                css_path = p
                break
                
        if css_path:
            logger.info(f"Loading CSS from: {css_path}")
            provider.load_from_path(css_path)
            screen = Gdk.Screen.get_default()
            if screen:
                Gtk.StyleContext.add_provider_for_screen(screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        else:
            logger.warning("Could not find application.css in any standard location")

        # prepend custom path for icon theme
        icon_theme = Gtk.IconTheme.get_default()
        icon_theme.prepend_search_path(os.path.join(os.path.dirname(__file__), "data", "icons"))
        
        # Add Flatpak icon export paths for host applications
        flatpak_icon_paths = [
            "/var/lib/flatpak/exports/share/icons",
            os.path.expanduser("~/.local/share/flatpak/exports/share/icons"),
            # Host-mapped paths via --filesystem=host
            "/run/host/usr/share/icons",
            "/run/host/usr/share/pixmaps",
            os.path.expanduser("/run/host/home/%s/.local/share/icons" % os.getlogin())
        ]
        for p in flatpak_icon_paths:
            if os.path.exists(p) and p not in icon_theme.get_search_path():
                logger.info(f"Adding icon search path: {p}")
                icon_theme.append_search_path(p)

    def on_quit_action(self, action, param):
        if self.window is not None:
            self.window.destroy()

    def on_prefers_color_scheme(self, *args):
        prefers_color_scheme = self.granite_settings.get_prefers_color_scheme()
        self.gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_color_scheme)

    def on_handle_local_options(self, application, options):
        debug = options.contains("debug")
        verbose = options.contains("verbose")
        
        init_logging(debug=debug, verbose_flag=verbose)
        
        return -1 # Continue execution

    def show_preferences(self, parent=None):
        logger.info("show_preferences called. Holding application.")
        self.hold()
        if self.window is not None:
            self.window.set_keep_above(False)
        self.pref_win = PreferencesWindow(application=self)
        if parent:
            self.pref_win.set_transient_for(parent)
        self.pref_win.connect("destroy", self.on_preferences_closed)
        self.pref_win.show_all()
        self.pref_win.present()

    def on_preferences_closed(self, widget):
        logger.info("Preferences closed. Releasing application.")
        if self.window is not None:
            self.window.set_keep_above(True)
        self.release()
        self.pref_win = None

def main(version):
    app = Application()
    print(version)
    return app.run(sys.argv)
