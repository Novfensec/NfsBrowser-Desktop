import ctypes
import os
import platform
import sys
from ctypes import wintypes
from .root import ROOT

os.environ["KIVY_NO_FILELOG"] = "1"
os.environ["KIVY_NO_CONFIG"] = "1"

from kivy.resources import resource_add_path

sys.path.insert(0, os.path.dirname(__file__))
resource_add_path(os.path.dirname(__file__))

import pybindcef
from kivy.config import Config
from libs.config_handler import config_handler

Config.set("graphics", "width", "800")
Config.set("graphics", "height", "600")
Config.set("graphics", "maxfps", "60")
Config.set("input", "mouse", "mouse,multitouch_on_demand")
Config.set("graphics", "fullscreen", "0")
Config.set("graphics", "borderless", "0")
Config.set("graphics", "resizable", "1")

import registers
from libs.cef_webview import CefWebView  # noqa: E402
from libs.native_frame import NativeFrame
from services.cef_service import cef_service

if platform.system() == "Windows":
    user32 = ctypes.windll.user32
    try:
        if hasattr(ctypes.windll.shcore, "SetProcessDpiAwareness"):
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        else:
            ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

import re
import weakref
import webbrowser
from urllib.parse import quote_plus, urlencode, urlparse

from carbonkivy.app import CarbonApp
from carbonkivy.uix.notification import CNotificationToast
from carbonkivy.uix.screen import CScreen
from carbonkivy.uix.screenmanager import CScreenManager
from carbonkivy.utils import update_system_ui
from kivy.clock import Clock, mainthread
from kivy.core.window import Window
from kivy.logger import Logger
from kivy.properties import DictProperty, ObjectProperty, StringProperty
from kivy.resources import resource_add_path
from libs import REFS
from libs.config_handler import config_handler
from View.base_screen import BanLayout, LoadingLayout

Clock.max_iteration = 60


def set_softinput(*args) -> None:
    Window.keyboard_anim_args = {"d": 0.2, "t": "in_out_expo"}
    Window.softinput_mode = "below_target"


Window.on_restore(Clock.schedule_once(set_softinput, 0.1))


SQueries = {
    "google": "https://www.google.com/search?q=",
    "bing": "https://www.bing.com/search?q=",
}


class UI(CScreenManager):
    def __init__(self, *args, **kwargs):
        super(UI, self).__init__(*args, **kwargs)


class MainScreen(CScreen):

    def __init__(self, **kwargs) -> None:
        super(MainScreen, self).__init__(**kwargs)


class NfsBrowser(CarbonApp):

    current_webview = ObjectProperty()

    tabs = DictProperty()

    current_se = StringProperty()

    se_source = StringProperty()

    def __init__(self, *args, **kwargs):
        self.defaults = False
        self.theme = config_handler.get("theme", "White")
        self.native_frame = NativeFrame(border_width=5)
        self.icon = os.path.join(ROOT, "data", "NfsBrowserDesktop64.png")
        super(NfsBrowser, self).__init__(*args, **kwargs)
        self.load_all_kv_files(os.path.join(self.directory, "View"))
        self.current_se = config_handler.get("search_engine", "google")
        self.manager_screens = UI()
        self.loading_layout = LoadingLayout()
        self.notification = CNotificationToast()
        self.ban_layout = BanLayout()

    def on_current_se(self, *args) -> None:
        self.se_source = REFS.get(self.current_se, "")

    def on_theme(self, *args) -> None:
        config_handler.update({"theme": self.theme})
        super(CarbonApp, self).on_theme(*args)
        self.apply_styles()

    def apply_styles(self, *args) -> None:
        Window.clearcolor = self.background
        icon_style = "Dark" if self.theme in ["White", "Gray10"] else "Light"
        update_system_ui(
            self.background, self.background, icon_style=icon_style, pad_nav=True
        )

    def build(self) -> UI:
        from Model.browser_model import BrowserModel

        self.browser_model = BrowserModel()
        self.browser_model.add_observer(self)

        self.main_screen = MainScreen(name="main screen")
        self.apply_styles()

        cef_service.initialize()

        # Add the first default tab but don't attach webview yet
        self.browser_model.new_tab(load_immediately=False)

        # Wire up the view models
        self.main_screen.ids.toolbar.view_model = self.browser_model
        self.main_screen.ids.app_bar.view_model = self.browser_model

        return self.main_screen

    def build_app(self) -> UI:
        self.main_screen = MainScreen(name="main screen")
        self.apply_styles()
        return self.main_screen

    def generate_application_screens(self, *args) -> None:
        # adds different screen widgets to the screen manager
        import View.screens

        screens = View.screens.screens

        for i, name_screen in enumerate(screens.keys()):
            model = screens[name_screen]["view_model"]()
            view = screens[name_screen]["object"](view_model=model)
            model.add_observer(view)
            view.manager_screens = self.manager_screens
            view.name = name_screen

            self.manager_screens.add_widget(view)

    def on_start(self):
        # lt = AgreementLayout()
        # if not os.path.isfile(os.path.join(self.directory, ".accepted")):
        #     Window.add_widget(lt)

        self.generate_application_screens()

        # Wire up the BrowserWebView inside the EntrypointScreen
        entrypoint = self.manager_screens.get_screen("entrypoint screen")
        if entrypoint and "web_view" in entrypoint.ids:
            entrypoint.ids.web_view.view_model = self.browser_model

        self.main_screen.ids.main_layout.add_widget(self.manager_screens)

        # Restore window state from config
        if config_handler.get("window_state", "normal") == "maximized":

            def _wait_and_maximize(dt):
                # Only maximize AFTER the native frame hook is successfully attached!
                if getattr(self, "native_frame", None) and getattr(
                    self.native_frame, "wndproc_hook", None
                ):
                    # explicitly maximize to avoid toggle bugs if OS started it zoomed
                    btn_max = self.main_screen.ids.toolbar.ids.btn_max
                    if platform.system() == "Windows":
                        hwnd = ctypes.windll.user32.GetActiveWindow()
                        ctypes.windll.user32.ShowWindow(hwnd, 3)
                        btn_max.icon = "minimize"
                    else:
                        Window.maximize()
                        btn_max.icon = "copy"
                else:
                    Clock.schedule_once(_wait_and_maximize, 0.1)

            Clock.schedule_once(_wait_and_maximize, 0.1)

        self._running = True
        self.loading_state(False)

    def model_is_changed(self, *args):
        if not self.browser_model:
            return

        active_tab = self.browser_model.active_tab
        if not active_tab:
            return

        try:
            entrypoint = self.manager_screens.get_screen("entrypoint screen")
            if entrypoint and "manager_screens" in entrypoint.ids:
                if active_tab.url == "about:blank" or active_tab.url == "":
                    entrypoint.ids.manager_screens.current = "home"
                else:
                    entrypoint.ids.manager_screens.current = "webview"
        except Exception as e:
            Logger.error(f"NfsBrowser: Could not sync screen state: {e}")

    def search(self, text, *args) -> None:
        if not text or not isinstance(text, str) or not text.strip():
            self._handle_empty_input()
            return

        query = text.strip()

        if len(query) > 2048:
            self._handle_error("Query exceeds maximum allowed length.")
            return

        if self._is_url(query):
            self._navigate_to_url(query)
            return

        if '"' in query or "site:" in query or "OR" in query:
            self._execute_advanced_search(query)
            return

        self._execute_standard_search(query)

    def _is_url(self, text: str) -> bool:
        """
        Determines if a string is a likely URL.
        Catches explicit (http://) and implicit (example.com) URLs.
        """
        parsed = urlparse(text)
        if parsed.scheme and parsed.netloc:
            return True

        url_pattern = re.compile(
            r"^(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{2,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$"
        )
        return bool(url_pattern.match(text))

    def _navigate_to_url(self, url: str) -> None:
        if not url.startswith(("http://", "https://", "file://", "ftp://")):
            url = f"https://{url}"
        self._load_in_browser(url)
        Logger.info(f"NfsBrowser: [ACTION] Navigating directly to URL: {url}")

    def _execute_standard_search(self, query: str) -> None:
        engine = getattr(self, "current_se", "google")
        prefix = SQueries.get(engine, SQueries["google"])
        url = f"{prefix}{quote_plus(query)}"
        self._load_in_browser(url)
        Logger.info(
            f"NfsBrowser: [ACTION] Executing standard text search for: '{query}'"
        )

    def _execute_advanced_search(self, query: str) -> None:
        engine = getattr(self, "current_se", "google")
        prefix = SQueries.get(engine, SQueries["google"])
        url = f"{prefix}{quote_plus(query)}"
        self._load_in_browser(url)
        Logger.info(
            f"NfsBrowser: [ACTION] Executing advanced text search for: '{query}'"
        )

    def _load_in_browser(self, url: str) -> None:
        if not self.browser_model:
            return

        if self.browser_model.active_tab:
            self.browser_model.active_tab.load(url)
        else:
            self.browser_model.new_tab(url)

        # Switch the inner UI in entrypoint screen to show the webview
        try:
            entrypoint = self.manager_screens.get_screen("entrypoint screen")
            if entrypoint and "manager_screens" in entrypoint.ids:
                entrypoint.ids.manager_screens.current = "webview"
                self.main_screen.ids.app_bar.model_is_changed()
                if "toolbar" in self.main_screen.ids:
                    self.main_screen.ids.toolbar.model_is_changed()
        except Exception as e:
            Logger.error(f"NfsBrowser: Could not switch to webview screen: {e}")

    def go_home(self) -> None:
        try:
            entrypoint = self.manager_screens.get_screen("entrypoint screen")
            if entrypoint and "manager_screens" in entrypoint.ids:
                entrypoint.ids.manager_screens.current = "home"

                if self.browser_model and self.browser_model.active_tab:
                    self.browser_model.active_tab.load("about:blank")

                self.main_screen.ids.app_bar.model_is_changed()
                if "toolbar" in self.main_screen.ids:
                    self.main_screen.ids.toolbar.model_is_changed()
        except Exception as e:
            Logger.error(f"NfsBrowser: Could not switch to home screen: {e}")

    def is_home(self) -> bool:
        try:
            entrypoint = self.manager_screens.get_screen("entrypoint screen")
            if entrypoint and "manager_screens" in entrypoint.ids:
                return entrypoint.ids.manager_screens.current == "home"
        except:
            pass
        return False

    def _handle_empty_input(self) -> None:
        Logger.info("NfsBrowser: [ACTION] Ignored: Input is empty or invalid.")

    def _handle_error(self, message: str) -> None:
        Logger.error(f"NfsBrowser: [ERROR] {message}")

    def on_resume(self):
        return super().on_resume()

    def on_pause(self, *args) -> None:
        return True

    def on_stop(self, *args) -> None:
        if platform.system() == "Windows":
            hwnd = user32.GetActiveWindow()
            if user32.IsZoomed(hwnd):
                config_handler.update({"window_state": "maximized"})
            else:
                config_handler.update({"window_state": "normal"})
        self._running = False
        cef_service.shutdown()

    def close_window(self, *args):
        self.stop()

    def minimize_window(self, *args):
        if platform.system() == "Windows":
            hwnd = user32.GetActiveWindow()
            user32.ShowWindow(hwnd, 6)
        else:
            Window.minimize()

    def toggle_maximize(self, *args):
        Window.fullscreen = False
        btn_max = self.main_screen.ids.toolbar.ids.btn_max
        if platform.system() == "Windows":
            hwnd = user32.GetActiveWindow()
            if user32.IsZoomed(hwnd):
                user32.ShowWindow(hwnd, 9)
                btn_max.icon = "maximize"
            else:
                user32.ShowWindow(hwnd, 3)
                btn_max.icon = "minimize"

            Clock.schedule_once(lambda dt: Window.canvas.ask_update(), 0.05)
        else:
            if Window.fullscreen:
                Window.fullscreen = False
                btn_max.icon = "maximize"
            else:
                Window.maximize()
                btn_max.icon = "copy"

    def _restore_maximize(self, *args):
        try:
            btn_max = self.main_screen.ids.toolbar.ids.btn_max
            if platform.system() == "Windows":
                hwnd = user32.GetActiveWindow()
                user32.ShowWindow(hwnd, 3)
                btn_max.icon = "minimize"
                Clock.schedule_once(lambda dt: Window.canvas.ask_update(), 0.05)
        except Exception as e:
            Logger.error(f"NfsBrowser: Could not restore maximized state: {e}")

    def accept_agreement(self, *args) -> None:
        with open(
            os.path.join(self.directory, ".accepted"), "w", encoding="utf-8"
        ) as agreement_file:
            agreement_file.write("")

    def referrer(self, destination: str = None) -> None:
        if self.manager_screens.current != destination:
            self.manager_screens.current = destination
        # try:
        #         # if not destination in self.manager_screens.upstream_views:
        #         #     self.manager_screens.switch(destination)
        #         # else:
        #         #     self.manager_screens.current = destination
        # except Exception as e:
        #     print(e)

    def notify(
        self,
        title: str = "",
        subtitle: str = "",
        status: str = "Info",
        time_caption_enabled: bool = True,
        *args,
    ) -> None:
        self.notification.title = title
        self.notification.subtitle = subtitle
        self.notification.status = status
        self.notification.time_caption_enabled = time_caption_enabled
        self.notification.open()

    def web_open(self, url: str) -> None:
        webbrowser.open_new_tab(url)

    @mainthread
    def ban_state(self, state: bool = False, master: object = Window, *args) -> None:
        try:
            if state and not (
                hasattr(master, "ban_layout") and master.ban_layout != None
            ):
                master.ban_layout = BanLayout()
                _layout_ref = weakref.ref(master.ban_layout)
                master.add_widget(master.ban_layout)
                _layout_ref = None
            else:
                master.remove_widget(master.ban_layout)
                master.ban_layout = None
        except:
            return None

    @mainthread
    def loading_state(
        self, state: bool = False, master: object = Window, *args
    ) -> None:

        try:
            if state and not (
                hasattr(master, "loading_layout") and master.loading_layout != None
            ):
                master.loading_layout = LoadingLayout()
                _layout_ref = weakref.ref(master.loading_layout)
                master.add_widget(master.loading_layout)
                _layout_ref = None
            else:
                master.remove_widget(master.loading_layout)
                master.loading_layout = None
        except Exception as e:
            Logger.error(f"NfsBrowser: Loading State Error {e}")
            return None


def main(*args) -> None:
    app = NfsBrowser()
    app.run()


if __name__ == "__main__":
    main()
