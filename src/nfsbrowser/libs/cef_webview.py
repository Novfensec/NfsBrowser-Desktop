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
from kivy import platform
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.graphics import Color, PopMatrix, PushMatrix, Rectangle, Scale, Translate
from kivy.graphics.texture import Texture
from kivy.properties import (
    BooleanProperty,
    ListProperty,
    NumericProperty,
    ObjectProperty,
    StringProperty,
)
from kivy.uix.widget import Widget

# --------
# CEF modifier flag bitmask constants
# --------
CEF_SHIFT = 1 << 1
CEF_CTRL = 1 << 2
CEF_ALT = 1 << 3
CEF_META = 1 << 7
CEF_CAPSLOCK = 1 << 0
CEF_NUMLOCK = 1 << 8

# Mouse-button held flags (cef_event_flags_t) — used in move events so CEF
# knows a button is pressed and can treat the motion as a drag.
CEF_MB_LEFT = 1 << 4  # EVENTFLAG_LEFT_MOUSE_BUTTON
CEF_MB_MIDDLE = 1 << 5  # EVENTFLAG_MIDDLE_MOUSE_BUTTON
CEF_MB_RIGHT = 1 << 6  # EVENTFLAG_RIGHT_MOUSE_BUTTON

_BUTTON_TO_MB_FLAG = {0: CEF_MB_LEFT, 1: CEF_MB_MIDDLE, 2: CEF_MB_RIGHT}

# --------
# Kivy keycode -> Windows Virtual-Key code map
# --------
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


# AdBlocker — thin wrapper around the `adblock` package (adblock-rust Python
# bindings, the same engine used by Brave / uBlock Origin).
#
# Install once:  pip install adblock
#
# Filter lists (URLs) can be customised via AdBlocker(filter_urls=[...]).
# The compiled filter set is cached to disk so subsequent starts are instant.


_DEFAULT_FILTER_LISTS = [
    # EasyList — primary English ad-blocking list
    "https://easylist.to/easylist/easylist.txt",
    # EasyPrivacy — tracker blocking
    "https://easylist.to/easylist/easyprivacy.txt",
    # uBlock Origin main filters — covers YouTube ad domains & players
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/filters.txt",
    # uBlock Origin privacy filters
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/privacy.txt",
    # uBlock Origin annoyances (cookie banners, overlays)
    "https://raw.githubusercontent.com/uBlockOrigin/uAssets/master/filters/annoyances-cookies.txt",
    # AdGuard Base — additional YouTube ad coverage
    "https://raw.githubusercontent.com/AdguardTeam/FiltersRegistry/master/filters/filter_2_Base/filter.txt",
]

# CEF resource_type values that are meaningful to block
_BLOCKABLE_TYPES = {
    1,  # sub_frame  — iframe ads (YouTube ad iframes, etc.)
    3,  # script
    4,  # image
    5,  # font
    6,  # sub_resource
    7,  # object
    8,  # media
    13,  # xhr
    14,  # ping
}


class AdBlocker:
    """
    Ad / tracker blocker backed by the `adblock` package.

    Parameters
    ----------
    filter_urls : list[str] | None
        URLs of Adblock-Plus-format filter lists to fetch.
        Defaults to EasyList + EasyPrivacy + uBlock Origin + AdGuard Base.
    cache_path : str | None
        Path to store the compiled filter set (.bin).
        Defaults to ``~/.cache/pybindcef_adblock_v<version>.bin``.
        A new version number is used whenever the default filter list changes,
        so old caches are automatically skipped and rebuilt.
    """

    # Bump this when _DEFAULT_FILTER_LISTS changes to force a cache rebuild.
    _CACHE_VERSION = 2

    def __init__(self, filter_urls=None, cache_path=None):
        self._engine = None
        self._filter_urls = filter_urls or _DEFAULT_FILTER_LISTS
        self._cache_path = cache_path or os.path.join(
            os.path.expanduser("~"),
            ".cache",
            f"pybindcef_adblock_v{self._CACHE_VERSION}.bin",
        )

    #
    # Public API
    #

    def load(self):
        """
        Load (or build) the filter engine. Call this once at startup,
        ideally in a thread so it does not block the UI.
        """
        try:
            import adblock
        except ImportError:
            print(
                "[AdBlocker] 'adblock' package not found — run: pip install adblock\n"
                "            Ad blocking will be DISABLED."
            )
            return

        if os.path.exists(self._cache_path):
            try:
                with open(self._cache_path, "rb") as f:
                    data = f.read()
                engine = adblock.Engine(adblock.FilterSet())
                engine.deserialize(data)
                self._engine = engine
                print(f"[AdBlocker] Loaded cached filter set from {self._cache_path}")
                return
            except Exception as e:
                print(f"[AdBlocker] Cache load failed ({e}), rebuilding…")

        self._engine = self._build_engine(adblock)

    def should_block(self, url, source_url="", resource_type=6):
        """
        Return True if *url* should be blocked.

        Parameters
        ----------
        url : str
        source_url : str   page URL making the request
        resource_type : int  CEF cef_resource_type_t value
        """
        if self._engine is None:
            return False
        if resource_type not in _BLOCKABLE_TYPES:
            return False
        try:
            rtype = _CEF_TYPE_TO_ADBLOCK.get(resource_type, "other")
            result = self._engine.check_network_urls(url, source_url, rtype)
            return result.matched
        except Exception:
            return False

    #
    # Internal helpers
    #

    def _build_engine(self, adblock):
        import urllib.request

        filter_set = adblock.FilterSet()
        for list_url in self._filter_urls:
            try:
                print(f"[AdBlocker] Fetching {list_url} …")
                with urllib.request.urlopen(list_url, timeout=15) as resp:
                    rules = resp.read().decode("utf-8", errors="replace")
                filter_set.add_filter_list(rules)
                print(f"[AdBlocker] ✓ {list_url}")
            except Exception as e:
                print(f"[AdBlocker] ✗ {list_url}: {e}")

        engine = adblock.Engine(filter_set)

        # Persist the compiled set for fast reloads.
        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with open(self._cache_path, "wb") as f:
                f.write(engine.serialize())
            print(f"[AdBlocker] Saved filter set to {self._cache_path}")
        except Exception as e:
            print(f"[AdBlocker] Could not save cache: {e}")

        return engine


# Map CEF resource_type ints → adblock content-type strings
_CEF_TYPE_TO_ADBLOCK = {
    1: "subdocument",
    3: "script",
    4: "image",
    5: "font",
    6: "other",
    7: "object",
    8: "media",
    13: "xmlhttprequest",
    14: "ping",
}


# JavaScript injected into YouTube pages to skip / remove ads that slip
# through the network-level filter (served from the same domain as content).

_YT_ADSKIP_JS = """
(function() {
    'use strict';
    function skipAds() {
        // 1. Click the skip button as soon as it appears.
        var skip = document.querySelector(
            '.ytp-skip-ad-button, .ytp-ad-skip-button, .ytp-ad-skip-button-modern'
        );
        if (skip) { skip.click(); return; }

        // 2. If an unskippable ad is playing, jump to the end.
        var video = document.querySelector('video');
        if (video && document.querySelector('.ad-showing')) {
            video.currentTime = video.duration;
            video.playbackRate = 16;
            return;
        }

        // 3. Remove overlay / banner ads.
        [
            '.ytp-ad-overlay-container',
            '.ytp-ad-text-overlay',
            'ytd-banner-promo-renderer',
            'ytd-statement-banner-renderer',
            'ytd-ad-slot-renderer',
            'ytd-in-feed-ad-layout-renderer',
            'ytd-primetime-promo-renderer',
            'ytd-promoted-sparkles-web-renderer',
            '#player-ads',
            '#masthead-ad',
        ].forEach(function(sel) {
            document.querySelectorAll(sel).forEach(function(el) { el.remove(); });
        });
    }
    // Poll every 250 ms — ads can appear at any time.
    setInterval(skipAds, 250);
    skipAds();
})();
"""


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

    tex = ObjectProperty(None, allownone=True)
    start_url = StringProperty("https://google.com")
    active = BooleanProperty(True)  # set False to hide and mute input for this tab

    fps = NumericProperty(120)
    initial_zoom = NumericProperty(1.5)
    texture_size = ListProperty([800, 600])
    shared_texture_enabled = BooleanProperty(False)
    scroll_step = NumericProperty(120)

    on_load_start = ObjectProperty(None, allownone=True)
    on_load_end = ObjectProperty(None, allownone=True)
    on_load_error = ObjectProperty(None, allownone=True)
    on_address_change = ObjectProperty(None, allownone=True)
    on_title_change = ObjectProperty(None, allownone=True)
    on_loading_state_change = ObjectProperty(None, allownone=True)
    on_favicon_url_change = ObjectProperty(None, allownone=True)
    on_console_message = ObjectProperty(None, allownone=True)
    on_before_popup = ObjectProperty(None, allownone=True)
    on_before_download = ObjectProperty(None, allownone=True)
    on_download_updated = ObjectProperty(None, allownone=True)
    on_context_menu = ObjectProperty(None, allownone=True)
    on_js_alert = ObjectProperty(None, allownone=True)
    on_js_confirm = ObjectProperty(None, allownone=True)
    on_js_prompt = ObjectProperty(None, allownone=True)
    on_find_result = ObjectProperty(None, allownone=True)
    on_fullscreen_mode_change = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self._current_modifiers = 0
        self._mouse_mods = 0  # bitmask of currently-held mouse buttons
        self.mapped = False
        self.current_handle = 0
        self.tex = Texture.create(size=tuple(self.texture_size), colorfmt="bgra")

        self._cef_focused = False
        self._keyboard = None
        self._active_touches = {}
        self._current_zoom = self.initial_zoom

        w, h = self.texture_size
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
            shared_texture_enabled=self.shared_texture_enabled,
            fps=self.fps,
            on_load_start=self._dispatch_load_start,
            on_load_end=self._dispatch_load_end,
            on_load_error=self._dispatch_load_error,
            on_address_change=self._dispatch_address_change,
            on_title_change=self._dispatch_title_change,
            on_loading_state_change=self._dispatch_loading_state_change,
            on_favicon_url_change=self._dispatch_favicon_url_change,
            on_console_message=self._dispatch_console_message,
            on_before_popup=self._dispatch_before_popup,
            on_before_download=self._dispatch_before_download,
            on_download_updated=self._dispatch_download_updated,
            on_context_menu=self._dispatch_context_menu,
            on_js_alert=self._dispatch_js_alert,
            on_js_confirm=self._dispatch_js_confirm,
            on_js_prompt=self._dispatch_js_prompt,
            on_find_result=self._dispatch_find_result,
            on_fullscreen_mode_change=self._dispatch_fullscreen_mode_change,
        )

        Clock.schedule_once(
            lambda dt: self.browser.set_zoom_level(self._current_zoom), 1.5
        )
        Clock.schedule_interval(self.update_cef, 0)
        Clock.schedule_once(lambda dt: self.browser.load_url(self.start_url))
        self.update_rect()

        Window.bind(on_touch_down=self.on_ceftouch_down)
        Window.bind(mouse_pos=self.on_cefmouse_move)
        Window.bind(on_touch_move=self.on_ceftouch_move)
        Window.bind(on_touch_up=self.on_ceftouch_up)
        Window.bind(on_textinput=self._on_text_input)

    def _dispatch_load_start(self, status, url):
        if self.on_load_start:
            self.on_load_start(status, url)

    def _dispatch_load_end(self, status, url):
        if (
            getattr(self, "_yt_adskip", False)
            and self.browser
            and "youtube.com/watch" in url
        ):
            self.browser.execute_js(_YT_ADSKIP_JS)

        if self.on_load_end:
            self.on_load_end(status, url)

    def _dispatch_load_error(self, code, text, url):
        if self.on_load_error:
            self.on_load_error(code, text, url)

    def _dispatch_address_change(self, url):
        if self.on_address_change:
            self.on_address_change(url)

    def _dispatch_title_change(self, title):
        if self.on_title_change:
            self.on_title_change(title)

    def _dispatch_loading_state_change(self, loading, can_back, can_fwd):
        if self.on_loading_state_change:
            self.on_loading_state_change(loading, can_back, can_fwd)

    def _dispatch_favicon_url_change(self, url):
        if self.on_favicon_url_change:
            self.on_favicon_url_change(url)

    def _dispatch_console_message(self, level, message, source, line):
        if self.on_console_message:
            return bool(self.on_console_message(level, message, source, line))
        return False

    def _dispatch_before_popup(self, url, frame, disposition, user_gesture):
        if self.on_before_popup:
            self.on_before_popup(url, frame, disposition, user_gesture)

    def _dispatch_before_download(self, name, url, mime):
        if self.on_before_download:
            return self.on_before_download(name, url, mime)
        return ""

    def _dispatch_download_updated(self, path, total, received, complete, canceled):
        if self.on_download_updated:
            self.on_download_updated(path, total, received, complete, canceled)

    def _dispatch_context_menu(
        self, x, y, link_url, selection_text, source_url, media_type
    ):
        if self.on_context_menu:
            return bool(
                self.on_context_menu(
                    x, y, link_url, selection_text, source_url, media_type
                )
            )
        return False

    def _dispatch_js_alert(self, msg):
        if self.on_js_alert:
            return bool(self.on_js_alert(msg))
        return False

    def _dispatch_js_confirm(self, msg):
        if self.on_js_confirm:
            return bool(self.on_js_confirm(msg))
        return False

    def _dispatch_js_prompt(self, msg, default_value):
        if self.on_js_prompt:
            return bool(self.on_js_prompt(msg, default_value))
        return False

    def _dispatch_find_result(self, identifier, count, final_update):
        if self.on_find_result:
            self.on_find_result(identifier, count, final_update)

    def _dispatch_fullscreen_mode_change(self, fullscreen):
        if self.on_fullscreen_mode_change:
            self.on_fullscreen_mode_change(fullscreen)

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

        if "ctrl" in modifiers or "meta" in modifiers:
            if key in (61, 43, 270):
                self._current_zoom += 0.2
                self.browser.set_zoom_level(self._current_zoom)
                return True
            elif key in (45, 269):
                self._current_zoom -= 0.2
                self.browser.set_zoom_level(self._current_zoom)
                return True
            elif key in (48, 256):
                self._current_zoom = 0.0
                self.browser.set_zoom_level(self._current_zoom)
                return True

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
        self._active_touches[touch.uid] = touch
        button_map = {"left": 0, "middle": 1, "right": 2}
        button = button_map.get(touch.button, 0)
        click_count = 2 if touch.is_double_tap else 1
        touch.ud["cef_click_count"] = click_count
        self._dispatch_mouse(touch.x, touch.y, 1, False, button, click_count)
        touch.grab(self)
        return True

    def _dispatch_wheel(self, x, y, button):
        cef_x = int(x - self.x)
        cef_y = int(self.height - (y - self.y))

        mods = Window.modifiers
        if "ctrl" in mods or "meta" in mods:
            if button == "scrollup":
                self._current_zoom += 0.1
            elif button == "scrolldown":
                self._current_zoom -= 0.1
            self.browser.set_zoom_level(self._current_zoom)
            return

        step = self.scroll_step
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

    def on_ceftouch_move(self, instance, touch):
        if not self.active:
            return False
        if touch.uid not in self._active_touches:
            return False

        if len(self._active_touches) >= 2:
            touches = list(self._active_touches.values())
            t1, t2 = touches[0], touches[1]
            import math

            curr_dist = math.hypot(t1.x - t2.x, t1.y - t2.y)
            if touch.uid == t1.uid:
                prev_dist = math.hypot(touch.px - t2.x, touch.py - t2.y)
            elif touch.uid == t2.uid:
                prev_dist = math.hypot(t1.x - touch.px, t1.y - touch.py)
            else:
                prev_dist = curr_dist

            dist_delta = curr_dist - prev_dist
            move_dist = math.hypot(touch.dx, touch.dy)

            if abs(dist_delta) > move_dist * 0.5:
                # Mostly zooming
                self._current_zoom += dist_delta * 0.005
                self.browser.set_zoom_level(self._current_zoom)
            else:
                # Two-finger swipe scrolling
                cef_x = int(touch.x - self.x)
                cef_y = int(self.height - (touch.y - self.y))
                dx = int(touch.dx * self.scroll_step)
                dy = int(-touch.dy * self.scroll_step)
                self.browser.send_mouse_wheel(cef_x, cef_y, dx, dy)
            return True
        else:
            # Single-finger touch drag (behaves like mouse move)
            self._dispatch_mouse(touch.x, touch.y, 0, False, 0)
            return True

    def on_ceftouch_up(self, instance, touch):
        self._active_touches.pop(touch.uid, None)
        if not self.active:
            return False
        if self.collide_point(*touch.pos):
            self.browser.set_focus(True)
            button_map = {"left": 0, "middle": 1, "right": 2}
            button = button_map.get(touch.button, 0)
            click_count = touch.ud.get("cef_click_count", 1)
            self._dispatch_mouse(touch.x, touch.y, 1, True, button, click_count)
            touch.ungrab(self)
            return True

    def _dispatch_mouse(self, x, y, event_type, is_up, button_type, click_count=1):
        cef_x = int(x - self.x)
        cef_y = int(self.height - (y - self.y))
        # Keep _mouse_mods in sync so every mouse-move event carries the
        # correct "button held" flags — without this CEF never sees a drag.
        if event_type != 0:  # click event (not move)
            flag = _BUTTON_TO_MB_FLAG.get(button_type, 0)
            if is_up:
                self._mouse_mods &= ~flag
            else:
                self._mouse_mods |= flag
        self.browser.send_mouse_event(
            cef_x,
            cef_y,
            event_type,
            is_up,
            button_type,
            click_count,
            self._mouse_mods,
        )

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
            self.translate.y = self.size[1]

    def _on_gpu_paint(self, handle_id, width, height):
        if handle_id != self.current_handle:
            self.browser.map_gpu_texture(handle_id, self.tex.id, width, height)
            self.current_handle = handle_id
            self.mapped = True
        self.canvas.ask_update()

    def _on_cpu_paint(self, buffer_view, width, height, dirty_rects):
        try:
            tex_resized = False
            if self.tex.width != width or self.tex.height != height:
                self.tex = Texture.create(size=(width, height), colorfmt="bgra")
                self.rect.texture = self.tex
                tex_resized = True

            if tex_resized or not dirty_rects:
                # Full upload on resize or if CEF gives no dirty rects.
                self.tex.blit_buffer(buffer_view, colorfmt="bgra", bufferfmt="ubyte")
            else:
                stride = width * 4
                view = memoryview(buffer_view)

                for rx, ry, rw, rh in dirty_rects:
                    # Clamp to actual texture dimensions.
                    rx = max(0, min(rx, width))
                    ry = max(0, min(ry, height))
                    rw = max(0, min(rw, width - rx))
                    rh = max(0, min(rh, height - ry))
                    if rw == 0 or rh == 0:
                        continue

                    row_len = rw * 4
                    parts = []
                    for y in range(ry, ry + rh):
                        start = y * stride + rx * 4
                        parts.append(view[start : start + row_len])

                    region = b"".join(parts)

                    # The Scale(1,-1,1) canvas transform flips the whole texture
                    # visually. A full blit_buffer maps CEF row N -> texture y=N
                    # with no extra flip, so dirty rects must use the same mapping:
                    # pos y = ry directly.
                    self.tex.blit_buffer(
                        region,
                        size=(rw, rh),
                        pos=(rx, ry),
                        colorfmt="bgra",
                        bufferfmt="ubyte",
                    )

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

    def enable_adblock(self, blocker=None, load_async=True, yt_adskip=True):
        """
        Enable ad / tracker blocking for this browser instance.

        Parameters
        ----------
        blocker : AdBlocker | None
            Pass an already-loaded :class:`AdBlocker` instance to share one
            engine across multiple tabs, or leave ``None`` to create and load
            a private instance automatically.
        load_async : bool
            When *True* (default) the filter list download/compile step runs
            on a daemon thread so the UI is not blocked.  The blocker will
            silently allow all requests until loading completes (~2 s on a
            fast connection if no cache exists).
        yt_adskip : bool
            When *True* (default) injects a JavaScript snippet into every
            YouTube page that auto-skips and removes ads that are served from
            the same domain as regular content and therefore cannot be caught
            by network-level filtering alone.
        """
        if blocker is None:
            blocker = AdBlocker()

        self._adblocker = blocker
        self._yt_adskip = yt_adskip

        def _hook(url, resource_type):
            # The source URL isn't available from this callback, but the
            # blocker still works well using document URL from the browser.
            source = self.browser.get_url() if self.browser else ""
            return self._adblocker.should_block(url, source, resource_type)

        self.browser.on_before_resource_load = _hook

        if blocker._engine is None:
            # Engine not yet loaded — kick it off.
            if load_async:
                import threading

                t = threading.Thread(target=blocker.load, daemon=True)
                t.start()
            else:
                blocker.load()

    def disable_adblock(self):
        """Remove the ad-blocking filter from this browser instance."""
        self.browser.on_before_resource_load = None
        self._adblocker = None
        self._yt_adskip = False

    def on_kv_post(self, *args):
        pass
