from kivy.properties import StringProperty, BooleanProperty, ObjectProperty
from services.cef_service import cef_service
from libs.cef_webview import CefWebView
from Model.base_model import BaseScreenModel


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
                start_url=start_url if start_url else "https://google.com"
            )
            self.webview.size_hint = (1, 1)

            self.webview._cb_title_change = self._on_title
            self.webview._cb_address_change = self._on_address
            self.webview._cb_loading_state_change = self._on_loading_state
            self.webview._cb_load_error = self._on_load_error

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
