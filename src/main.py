# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 Adi Hezral <hezral@gmail.com>

import sys
import os

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Granite', '1.0')
gi.require_version('Gst', '1.0')
from gi.repository import Gtk, Gio, Granite, Gdk, GLib

from .window import helloWindow


class Application(Gtk.Application):

    app_id = "com.github.hezral.hello"
    gio_settings = Gio.Settings(schema_id=app_id)
    gtk_settings = Gtk.Settings().get_default()
    granite_settings = Granite.Settings.get_default()

    def __init__(self):
        super().__init__(application_id=self.app_id,
                         flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        self.window = self.props.active_window
        if not self.window:
            self.window = helloWindow(application=self)
        self.window.present()

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
        provider.load_from_path(os.path.join(os.path.dirname(__file__), "data", "application.css"))
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        # prepend custom path for icon theme
        icon_theme = Gtk.IconTheme.get_default()
        icon_theme.prepend_search_path(os.path.join(os.path.dirname(__file__), "data", "icons"))

    def on_quit_action(self, action, param):
        if self.window is not None:
            self.window.destroy()

    def on_prefers_color_scheme(self, *args):
        prefers_color_scheme = self.granite_settings.get_prefers_color_scheme()
        self.gtk_settings.set_property("gtk-application-prefer-dark-theme", prefers_color_scheme)

def main(version):
    app = Application()
    print(version)
    return app.run(sys.argv)
