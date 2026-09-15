from kivy.app import App
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty
from libs.cef_webview import AdBlocker, CefWebView
from Model.base_model import BaseScreenModel
from services.cef_service import cef_service

SHARED_ADBLOCKER = AdBlocker()


class TabModel(BaseScreenModel):
    title = StringProperty("New Tab")
    url = StringProperty("https://google.com")
    is_loading = BooleanProperty(False)
    can_go_back = BooleanProperty(False)
    can_go_forward = BooleanProperty(False)

    webview = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super(TabModel, self).__init__(**kwargs)
        self.webview = None
        self.app = App.get_running_app()

        self.bind(
            title=self.notify_all_observers,
            url=self.notify_all_observers,
            is_loading=self.notify_all_observers,
            can_go_back=self.notify_all_observers,
            can_go_forward=self.notify_all_observers,
            webview=self.notify_all_observers,
        )

    def _ensure_webview(self, start_url=None):
        if self.webview is None:
            self.webview = CefWebView(
                start_url=start_url if start_url else "https://google.com",
                initial_zoom=1.5,
            )
            self.webview.size_hint = (1, 1)

            # Enable adblock using the shared engine. (Loads asynchronously in the background)
            self.webview.enable_adblock(blocker=SHARED_ADBLOCKER)

            self.webview.on_title_change = self._on_title
            self.webview.on_address_change = self._on_address
            self.webview.on_loading_state_change = self._on_loading_state
            self.webview.on_load_error = self._on_load_error
            self.webview.on_before_popup = self._on_before_popup
            self.webview.on_fullscreen_mode_change = self._on_fullscreen

    def notify_all_observers(self, *args):
        from kivy.clock import Clock

        for observer in self._observers:
            Clock.schedule_once(observer.model_is_changed)

    def load(self, url: str):
        self._ensure_webview(start_url=url)
        if self.webview:
            self.webview.load(url)

    def reload(self):
        if self.webview:
            self.webview.reload()

    def go_back(self):
        if self.webview and self.can_go_back:
            self.webview.go_back()

    def go_forward(self):
        if self.webview and self.can_go_forward:
            self.webview.go_forward()

    def stop(self):
        if self.webview:
            self.webview.stop()

    def _on_title(self, title):
        self.title = title

    def _on_address(self, url):
        self.url = url

    def _on_before_popup(self, url, frame, disposition, user_gesture):
        if self.app and hasattr(self.app, "browser_model"):
            self.app.browser_model.new_tab(url=url)
        return True  # Cancel native popup

    def _on_fullscreen(self, fullscreen):
        if self.app and hasattr(self.app, "toggle_fullscreen"):
            self.app.toggle_fullscreen(webview=self.webview, force=fullscreen)

    def _on_loading_state(self, is_loading, can_back, can_fwd):
        self.is_loading = is_loading
        self.can_go_back = can_back
        self.can_go_forward = can_fwd

    def _on_load_error(self, code, text, url):
        print(f"[TabModel] Load error {code} on {url}: {text}")

    def destroy(self):
        if self.webview:
            self.webview.load("about:blank")
            self.webview.close()
            self.webview = None
