"""
cef_webview.py
==============

A reusable, self-contained CEF-backed webview widget for Kivy, built on
top of `pybindcef`.

This module only contains the browser widget itself (mouse/keyboard
input forwarding, paint handling, texture mapping, navigation helpers,
and all modern browser event callbacks).

Usage
-----
    from kivy.app import App
    from kivy.uix.boxlayout import BoxLayout
    import pybindcef
    from cef_webview import CefWebView, init_cef

    class MyApp(App):
        def build(self):
            # 1. Initialize CEF once, before creating any CefWebView widgets.
            init_cef(worker_exe="cef_worker.exe", resources_dir="Resources")

            # 2. Create the widget like any other Kivy widget.
            root = BoxLayout()
            self.browser = CefWebView(
                start_url="https://google.com",
                on_title_change=lambda t: print("Title:", t),
                on_address_change=lambda u: print("URL:", u),
                on_load_end=lambda code, url: print("Loaded:", url),
                on_before_popup=lambda url, frame, disp, gesture: print("Popup:", url),
                on_before_download=lambda name, url, mime: "/tmp/" + name,
                on_console_message=lambda lvl, msg, src, ln: print(f"JS: {msg}"),
            )
            root.add_widget(self.browser)
            return root

        def on_stop(self):
            pybindcef.shutdown()

    MyApp().run()
"""

import os

import pybindcef
from kivy.uix.widget import Widget
from kivy.properties import ObjectProperty, StringProperty
from kivy.graphics import Rectangle, Color, PushMatrix, PopMatrix, Scale, Translate
from kivy.graphics.texture import Texture
from kivy.clock import Clock
from kivy.core.window import Window
from kivy import platform

# --------------------------------------------------------------------------
# CEF modifier flag bitmask constants
# --------------------------------------------------------------------------
CEF_SHIFT = 1 << 1
CEF_CTRL = 1 << 2
CEF_ALT = 1 << 3
CEF_META = 1 << 7
CEF_CAPSLOCK = 1 << 0
CEF_NUMLOCK = 1 << 8

# --------------------------------------------------------------------------
# Kivy keycode -> Windows Virtual-Key code map
# --------------------------------------------------------------------------
KIVY_TO_VK = {
    # Special/control keys
    8: 8,  # Backspace
    9: 9,  # Tab
    13: 13,  # Return
    27: 27,  # Escape
    32: 32,  # Space
    127: 46,  # Delete
    273: 38,  # Up
    274: 40,  # Down
    275: 39,  # Right
    276: 37,  # Left
    278: 36,  # Home
    279: 35,  # End
    280: 33,  # Page Up
    281: 34,  # Page Down
    # Function keys
    282: 112,  # F1
    283: 113,  # F2
    284: 114,  # F3
    285: 115,  # F4
    286: 116,  # F5
    287: 117,  # F6
    288: 118,  # F7
    289: 119,  # F8
    290: 120,  # F9
    291: 121,  # F10
    292: 122,  # F11
    293: 123,  # F12
    # OEM symbols — MUST be here or they collide with VK arrow/control codes
    39: 222,  # '  -> VK_OEM_7
    44: 188,  # ,  -> VK_OEM_COMMA
    45: 189,  # -  -> VK_OEM_MINUS
    46: 190,  # .  -> VK_OEM_PERIOD
    47: 191,  # /  -> VK_OEM_2
    59: 186,  # ;  -> VK_OEM_1
    61: 187,  # =  -> VK_OEM_PLUS
    91: 219,  # [  -> VK_OEM_4
    92: 220,  # \  -> VK_OEM_5
    93: 221,  # ]  -> VK_OEM_6
    96: 192,  # `  -> VK_OEM_3
}

NEEDS_CHAR = {8: 8, 13: 13, 9: 9, 27: 27}


def init_cef(worker_exe, resources_dir, base_dir=None):
    """
    Initialize the CEF subprocess. Call this exactly once, before
    creating any CefWebView widgets.

    :param worker_exe: filename of the worker executable
    :param resources_dir: name of the CEF resources directory
    :param base_dir: directory to resolve paths relative to.
                      Defaults to cwd.
    """
    if base_dir is None:
        base_dir = os.getcwd()

    worker_path = worker_exe
    if not os.path.isabs(worker_path):
        worker_path = os.path.join(base_dir, worker_exe)

    res_path = resources_dir
    if not os.path.isabs(res_path):
        res_path = os.path.join(base_dir, resources_dir)

    pybindcef.initialize(worker_path, res_path)


class CefWebView(Widget):
    """
    A Kivy widget that renders a CEF browser instance and forwards
    mouse/keyboard/scroll input to it.

    All browser events are exposed as overridable methods AND as optional
    constructor keyword arguments.  Subclass CefWebView and override the
    on_* methods, or pass lambdas/callables directly to the constructor.

    The underlying pybindcef.Browser instance is available as
    ``self.browser`` for direct API access.

    Example
    -------
    ::

        browser = CefWebView(
            start_url="https://example.com",
            on_title_change=lambda t: title_label.set_text(t),
            on_address_change=lambda u: url_bar.set_text(u),
            on_loading_state_change=lambda loading, back, fwd: ...,
            on_before_popup=lambda url, frame, disp, gesture: ...,
            on_before_download=lambda name, url, mime: "/downloads/" + name,
            on_download_updated=lambda path, total, recv, done, cancel: ...,
            on_console_message=lambda lvl, msg, src, ln: print(f"JS: {msg}"),
        )
    """

    tex = ObjectProperty()
    start_url = StringProperty("https://google.com")
    active = True

    def __init__(
        self,
        start_url=None,
        fps=60,
        initial_zoom=1.0,
        texture_size=(800, 600),
        shared_texture_enabled=False,
        on_load_start=None,
        on_load_end=None,
        on_load_error=None,
        on_address_change=None,
        on_title_change=None,
        on_loading_state_change=None,
        on_favicon_url_change=None,
        on_console_message=None,
        on_before_popup=None,
        on_before_download=None,
        on_download_updated=None,
        on_context_menu=None,
        on_js_alert=None,
        on_js_confirm=None,
        on_js_prompt=None,
        on_find_result=None,
        on_fullscreen_mode_change=None,
        **kwargs,
    ):
        super().__init__(**kwargs)

        if start_url is not None:
            self.start_url = start_url

        self._cb_load_start = on_load_start
        self._cb_load_end = on_load_end
        self._cb_load_error = on_load_error
        self._cb_address_change = on_address_change
        self._cb_title_change = on_title_change
        self._cb_loading_state_change = on_loading_state_change
        self._cb_favicon_url_change = on_favicon_url_change
        self._cb_console_message = on_console_message
        self._cb_before_popup = on_before_popup
        self._cb_before_download = on_before_download
        self._cb_download_updated = on_download_updated
        self._cb_context_menu = on_context_menu
        self._cb_js_alert = on_js_alert
        self._cb_js_confirm = on_js_confirm
        self._cb_js_prompt = on_js_prompt
        self._cb_find_result = on_find_result
        self._cb_fullscreen_mode_change = on_fullscreen_mode_change

        self._current_modifiers = 0
        self.mapped = False
        self.current_handle = 0
        self.tex = Texture.create(size=texture_size, colorfmt="bgra")

        self._cef_focused = False
        self._keyboard = None

        w, h = texture_size
        with self.canvas.after:
            Color(1, 1, 1, 1)
            PushMatrix()
            self.translate = Translate(0, h)
            self.scale = Scale(1, -1, 1)
            self.rect = Rectangle(texture=self.tex, pos=self.pos, size=(w, h))
            PopMatrix()

        self.bind(pos=self.update_rect, size=self.update_rect)

        # Create the browser — returns a pybindcef.Browser instance.
        self.browser = pybindcef.create_browser(
            url=self.start_url,
            on_cpu_paint=self._on_cpu_paint,
            on_gpu_paint=self._on_gpu_paint,
            shared_texture_enabled=shared_texture_enabled,
            fps=fps,
            on_load_start=self._dispatch_load_start,
            on_load_end=self._dispatch_load_end,
            on_load_error=self._dispatch_load_error,
            on_address_change=self._dispatch_address_change,
            on_title_change=self._dispatch_title_change,
            on_loading_state_change=self._dispatch_loading_state_change,
            on_favicon_url_change=self._dispatch_favicon_url_change,
            on_console_message=self._dispatch_console_message,
            on_before_popup=self._dispatch_before_popup,
            on_before_download=(
                self._dispatch_before_download
                if self._cb_before_download
                or type(self).on_before_download != CefWebView.on_before_download
                else None
            ),
            on_download_updated=self._dispatch_download_updated,
            on_context_menu=self._dispatch_context_menu,
            on_js_alert=self._dispatch_js_alert,
            on_js_confirm=self._dispatch_js_confirm,
            on_js_prompt=self._dispatch_js_prompt,
            on_find_result=self._dispatch_find_result,
            on_fullscreen_mode_change=self._dispatch_fullscreen_mode_change,
        )

        Clock.schedule_once(lambda dt: self.browser.set_zoom_level(initial_zoom), 1.5)
        Clock.schedule_interval(self.update_cef, 0)
        Clock.schedule_once(lambda dt: self.browser.load_url(self.start_url))
        self.update_rect()

        Window.bind(on_touch_down=self.on_ceftouch_down)
        Window.bind(mouse_pos=self.on_cefmouse_move)
        Window.bind(on_touch_up=self.on_ceftouch_up)
        Window.bind(on_textinput=self._on_text_input)

    def _dispatch_load_start(self, status, url):
        if self._cb_load_start:
            self._cb_load_start(status, url)
        else:
            self.on_load_start(status, url)

    def _dispatch_load_end(self, status, url):
        if self._cb_load_end:
            self._cb_load_end(status, url)
        else:
            self.on_load_end(status, url)

    def _dispatch_load_error(self, code, text, url):
        if self._cb_load_error:
            self._cb_load_error(code, text, url)
        else:
            self.on_load_error(code, text, url)

    def _dispatch_address_change(self, url):
        if self._cb_address_change:
            self._cb_address_change(url)
        else:
            self.on_address_change(url)

    def _dispatch_title_change(self, title):
        if self._cb_title_change:
            self._cb_title_change(title)
        else:
            self.on_title_change(title)

    def _dispatch_loading_state_change(self, loading, can_back, can_fwd):
        if self._cb_loading_state_change:
            self._cb_loading_state_change(loading, can_back, can_fwd)
        else:
            self.on_loading_state_change(loading, can_back, can_fwd)

    def _dispatch_favicon_url_change(self, url):
        if self._cb_favicon_url_change:
            self._cb_favicon_url_change(url)
        else:
            self.on_favicon_url_change(url)

    def _dispatch_console_message(self, level, message, source, line):
        if self._cb_console_message:
            return bool(self._cb_console_message(level, message, source, line))
        return self.on_console_message(level, message, source, line)

    def _dispatch_before_popup(self, url, frame, disposition, user_gesture):
        if self._cb_before_popup:
            self._cb_before_popup(url, frame, disposition, user_gesture)
        else:
            self.on_before_popup(url, frame, disposition, user_gesture)

    def _dispatch_before_download(self, name, url, mime):
        if self._cb_before_download:
            return self._cb_before_download(name, url, mime)
        return self.on_before_download(name, url, mime)

    def _dispatch_download_updated(self, path, total, received, complete, canceled):
        if self._cb_download_updated:
            self._cb_download_updated(path, total, received, complete, canceled)
        else:
            self.on_download_updated(path, total, received, complete, canceled)

    def _dispatch_context_menu(
        self, x, y, link_url, selection_text, source_url, media_type
    ):
        if self._cb_context_menu:
            return bool(
                self._cb_context_menu(
                    x, y, link_url, selection_text, source_url, media_type
                )
            )
        return self.on_context_menu(
            x, y, link_url, selection_text, source_url, media_type
        )

    def _dispatch_js_alert(self, msg):
        if self._cb_js_alert:
            return bool(self._cb_js_alert(msg))
        return self.on_js_alert(msg)

    def _dispatch_js_confirm(self, msg):
        if self._cb_js_confirm:
            return bool(self._cb_js_confirm(msg))
        return self.on_js_confirm(msg)

    def _dispatch_js_prompt(self, msg, default_value):
        if self._cb_js_prompt:
            return bool(self._cb_js_prompt(msg, default_value))
        return self.on_js_prompt(msg, default_value)

    def _dispatch_find_result(self, identifier, count, final_update):
        if self._cb_find_result:
            self._cb_find_result(identifier, count, final_update)
        else:
            self.on_find_result(identifier, count, final_update)

    def _dispatch_fullscreen_mode_change(self, fullscreen):
        if self._cb_fullscreen_mode_change:
            self._cb_fullscreen_mode_change(fullscreen)
        else:
            self.on_fullscreen_mode_change(fullscreen)

    # Overridable browser event methods
    def on_load_start(self, http_status_code, url):
        """Fired when the main frame starts loading."""

    def on_load_end(self, http_status_code, url):
        """Fired when the main frame finishes loading."""

    def on_load_error(self, error_code, error_text, failed_url):
        """Fired when the main frame fails to load."""

    def on_address_change(self, url):
        """Fired when the browser navigates to a new URL."""

    def on_title_change(self, title):
        """Fired when the page title changes."""

    def on_loading_state_change(self, is_loading, can_go_back, can_go_forward):
        """Fired when the browser loading state changes."""

    def on_favicon_url_change(self, favicon_url):
        """Fired when the page's favicon URL changes."""

    def on_console_message(self, level, message, source, line):
        """
        Fired for console.log / console.error / etc.
        Return True to suppress CEF's own console output.
        level: 0=debug, 1=info, 2=warning, 3=error
        """
        return False

    def on_before_popup(self, url, target_frame_name, disposition, user_gesture):
        """
        Fired when a page tries to open a new tab/window.
        The native popup is always suppressed; load the URL yourself
        (e.g. self.browser.load_url(url)) or open a new CefWebView.
        """

    def on_before_download(self, suggested_name, url, mime_type):
        """
        Fired before a download starts.
        Return an absolute path string to accept the download at that path.
        Return "" to cancel.
        If this callback is NOT set or overridden, the native CEF save dialog will show.
        """
        return ""

    def on_download_updated(
        self, path, total_bytes, received_bytes, is_complete, is_canceled
    ):
        """Fired during download progress and on completion/cancellation."""

    def on_context_menu(self, x, y, link_url, selection_text, source_url, media_type):
        """
        Fired before the right-click context menu is shown.
        Return True to suppress the native menu.
        """
        return False

    def on_js_alert(self, message):
        """
        Fired for JavaScript alert().
        Return True to suppress CEF's native dialog.
        """
        return False

    def on_js_confirm(self, message):
        """
        Fired for JavaScript confirm().
        Return True to suppress CEF's native dialog.
        """
        return False

    def on_js_prompt(self, message, default_value):
        """
        Fired for JavaScript prompt().
        Return True to suppress CEF's native dialog.
        """
        return False

    def on_find_result(self, identifier, count, is_final_update):
        """Fired with find-in-page results from self.find()."""

    def on_fullscreen_mode_change(self, fullscreen):
        """Fired when the page requests fullscreen on/off."""

    def _focus_cef(self):
        """Grabs the keyboard and sets CEF focus to True."""
        if not self.active:
            return
        if not self._cef_focused:
            self._cef_focused = True
            self.browser.set_focus(True)
            self._keyboard = Window.request_keyboard(self._on_keyboard_closed, self)
            if self._keyboard:
                self._keyboard.bind(on_key_down=self._on_keyboard_down)
                self._keyboard.bind(on_key_up=self._on_keyboard_up)

    def _unfocus_cef(self):
        """Releases the keyboard and sets CEF focus to False."""
        if self._cef_focused:
            self._cef_focused = False
            self.browser.set_focus(False)
            if self._keyboard:
                self._keyboard.unbind(on_key_down=self._on_keyboard_down)
                self._keyboard.unbind(on_key_up=self._on_keyboard_up)
                self._keyboard.release()
                self._keyboard = None

    def _on_keyboard_closed(self):
        self._unfocus_cef()

    def _kivy_mods_to_cef(self, modifiers):
        """Convert Kivy modifier string list --> CEF bitmask."""
        flags = 0
        if "shift" in modifiers:
            flags |= CEF_SHIFT
        if "ctrl" in modifiers:
            flags |= CEF_CTRL
        if "alt" in modifiers:
            flags |= CEF_ALT
        if "meta" in modifiers:
            flags |= CEF_META
        if "capslock" in modifiers:
            flags |= CEF_CAPSLOCK
        if "numlock" in modifiers:
            flags |= CEF_NUMLOCK
        return flags

    def _kivy_key_to_vk(self, key):
        """Convert Kivy keycode --> Windows VK code."""
        if key in KIVY_TO_VK:
            return KIVY_TO_VK[key]
        if 97 <= key <= 122:
            return key - 32
        return key

    def _on_text_input(self, window, text):
        """Fires ONLY for printable characters, already correctly shifted."""
        if not self.active or not self._cef_focused:
            return
        if self._current_modifiers & (CEF_CTRL | CEF_ALT):
            return
        for char in text:
            code = ord(char)
            if code >= 32 and code != 127:
                self.browser.send_key_event(code, 0, self._current_modifiers, 2)

    def _on_keyboard_down(self, keyboard, keycode, text, modifiers):
        key = keycode[0]
        vk = self._kivy_key_to_vk(key)
        mods = self._kivy_mods_to_cef(modifiers)
        self._current_modifiers = mods
        native = 0 if platform == "linux" else vk
        self.browser.send_key_event(vk, native, self._current_modifiers, 0)
        if key in NEEDS_CHAR:
            self.browser.send_key_event(NEEDS_CHAR[key], native, mods, 2)
        return True

    def _on_keyboard_up(self, keyboard, keycode):
        key = keycode[0]
        vk = self._kivy_key_to_vk(key)
        native = 0 if platform == "linux" else vk
        self.browser.send_key_event(vk, native, self._current_modifiers, 1)
        return True

    def on_ceftouch_down(self, instance, touch):
        if not self.active:
            return False
        if not self.collide_point(*touch.pos):
            self._unfocus_cef()
            return False
        self._focus_cef()
        if "scroll" in touch.button:
            self._dispatch_wheel(touch.x, touch.y, touch.button)
            return True
        button_map = {"left": 0, "middle": 1, "right": 2}
        button = button_map.get(touch.button, 0)
        self._dispatch_mouse(touch.x, touch.y, 1, False, button)
        touch.grab(self)
        return True

    def _dispatch_wheel(self, x, y, button):
        cef_x = int(x - self.x)
        cef_y = int(self.height - (y - self.y))
        step = 120
        dx, dy = 0, 0
        if button == "scrollup":
            dy = -step
        elif button == "scrolldown":
            dy = step
        elif button == "scrollleft":
            dx = step
        elif button == "scrollright":
            dx = -step
        self.browser.send_mouse_wheel(cef_x, cef_y, dx, dy)

    def on_cefmouse_move(self, instance, pos):
        if not self.active:
            return False
        if self.collide_point(*pos):
            self._dispatch_mouse(pos[0], pos[1], 0, False, 0)
            return True

    def on_ceftouch_up(self, instance, touch):
        if not self.active:
            return False
        if self.collide_point(*touch.pos):
            self.browser.set_focus(True)
            button_map = {"left": 0, "middle": 1, "right": 2}
            button = button_map.get(touch.button, 0)
            self._dispatch_mouse(touch.x, touch.y, 1, True, button)
            touch.ungrab(self)
            return True

    def _dispatch_mouse(self, x, y, event_type, is_up, button_type):
        cef_x = int(x - self.x)
        cef_y = int(self.height - (y - self.y))
        self.browser.send_mouse_event(cef_x, cef_y, event_type, is_up, button_type)

    def update_rect(self, *args):
        if not hasattr(self, "browser") or not hasattr(self, "rect"):
            return
        w, h = int(self.size[0]), int(self.size[1])
        if w > 0 and h > 0 and self.browser:
            self.browser.resize(w, h)
        if hasattr(self, "rect"):
            self.rect.pos = self.pos
            self.rect.size = self.size
        if hasattr(self, "translate"):
            self.translate.y = 2 * self.y + self.size[1]

    def _on_gpu_paint(self, handle_id, width, height):
        if handle_id != self.current_handle:
            self.browser.map_gpu_texture(handle_id, self.tex.id, width, height)
            self.current_handle = handle_id
            self.mapped = True
        self.canvas.ask_update()

    def _on_cpu_paint(self, buffer_view, width, height):
        try:
            if self.tex.width != width or self.tex.height != height:
                self.tex = Texture.create(size=(width, height), colorfmt="bgra")
                self.rect.texture = self.tex
            self.tex.blit_buffer(buffer_view, colorfmt="bgra", bufferfmt="ubyte")
            self.canvas.ask_update()
        except Exception as e:
            print(f"Paint error: {e}")

    def update_cef(self, dt):
        pybindcef.do_work()

    def load(self, url, *args):
        """Load a URL."""
        self.browser.load_url(url)

    def go_back(self):
        self.browser.go_back()

    def go_forward(self):
        self.browser.go_forward()

    def reload(self):
        self.browser.reload()

    def stop(self):
        """Stop the current page load."""
        self.browser.stop_load()

    def is_loading(self):
        return self.browser.is_loading()

    def can_go_back(self):
        return self.browser.can_go_back()

    def can_go_forward(self):
        return self.browser.can_go_forward()

    def get_url(self):
        return self.browser.get_url()

    def execute_js(self, code):
        """Execute arbitrary JavaScript in the current page."""
        self.browser.execute_js(code)

    def find(self, text, forward=True, case_sensitive=False):
        """Start a find-in-page search.  Results arrive via on_find_result."""
        self.browser.find(0, text, forward, case_sensitive)

    def stop_find(self):
        """Stop a running find-in-page search and clear highlights."""
        self.browser.stop_find()

    def open_dev_tools(self):
        """Open the Chromium DevTools panel."""
        self.browser.open_dev_tools()

    def close_dev_tools(self):
        """Close the DevTools panel."""
        self.browser.close_dev_tools()

    def close(self):
        """Close this browser instance."""
        self.browser.close()

    def on_kv_post(self, *args):
        pass
