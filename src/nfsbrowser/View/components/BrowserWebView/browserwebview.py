from carbonkivy.uix.screen import CScreen
from kivy.properties import ObjectProperty
from Utility.observer import Observer


class BrowserWebView(CScreen, Observer):
    name = "browserwebview"
    _current_webview = ObjectProperty(None, allownone=True)
    _observed_tab = ObjectProperty(None, allownone=True)

    def model_is_changed(self, *args):
        if not self.view_model:
            return

        active_tab = self.view_model.active_tab

        from kivy.app import App

        app = App.get_running_app()
        is_home = getattr(app, "is_home", lambda: False)()

        # Track the active tab to receive its property updates (e.g. webview creation)
        if self._observed_tab != active_tab:
            if self._observed_tab and self in self._observed_tab._observers:
                self._observed_tab.remove_observer(self)
            self._observed_tab = active_tab
            if self._observed_tab:
                self._observed_tab.add_observer(self)

        target_webview = (
            None if is_home else (active_tab.webview if active_tab else None)
        )

        # Don't do anything if we are already displaying the correct target webview state
        if self._current_webview == target_webview:
            return

        if self._current_webview:
            self._current_webview.active = False
            self.remove_widget(self._current_webview)
            self._current_webview = None

        if target_webview:
            self._current_webview = target_webview
            self._current_webview.active = True
            self.add_widget(self._current_webview)
