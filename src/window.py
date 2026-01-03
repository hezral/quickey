# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2021 Adi Hezral <hezral@gmail.com>

import gi
gi.require_version('Handy', '1')
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Handy, GObject

from .mode_switch import ModeSwitch

class helloWindow(Handy.ApplicationWindow):
    __gtype_name__ = 'helloWindow'

    Handy.init()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.app = self.props.application

        light = Gtk.Image().new_from_icon_name("display-brightness-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        dark = Gtk.Image().new_from_icon_name("weather-clear-night-symbolic", Gtk.IconSize.SMALL_TOOLBAR)
        modeswitch = ModeSwitch(light, dark, None, None)
        modeswitch.switch.bind_property("active", self.app.gtk_settings, "gtk_application_prefer_dark_theme", GObject.BindingFlags.SYNC_CREATE)

        header = Handy.HeaderBar()
        header.props.show_close_button = True
        header.props.hexpand = True
        header.props.title = "hello World"
        header.props.decoration_layout = "close:"
        header.pack_end(modeswitch)

        label = Gtk.Label("hello World")
        label.props.expand = True
        label.props.valign = label.props.halign = Gtk.Align.CENTER

        self.grid = Gtk.Grid()
        self.grid.props.expand = True
        self.grid.attach(header, 0, 0, 1, 1)
        self.grid.attach(label, 0, 1, 1, 1)

        window_handle = Handy.WindowHandle() 
        window_handle.add(self.grid)

        self.add(window_handle)
        self.props.default_width = 480
        self.props.default_height = 320
        self.show_all()

        
