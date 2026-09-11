from carbonkivy.uix.boxlayout import CBoxLayout
from kivy.properties import ObjectProperty
from Model.browser_model import BrowserModel
from Utility.observer import Observer
from View.EntrypointScreen.entrypoint_screen import SEDropdown


class BrowserAppBar(CBoxLayout, Observer):
    se_dropdown = ObjectProperty()
    _observed_tab = ObjectProperty(None, allownone=True)
    name = "browserappbar"

    def __init__(self, *args, **kwargs):
        super(BrowserAppBar, self).__init__(*args, **kwargs)
        self.se_dropdown = SEDropdown()

    def on_kv_post(self, base_widget):
        self.se_dropdown.master = self.ids.engine_icon

        # Bind buttons
        self.ids.btn_back.bind(on_press=self.on_back)
        self.ids.btn_fwd.bind(on_press=self.on_fwd)
        self.ids.btn_reload.bind(on_press=self.on_reload)
        if "btn_home" in self.ids:
            self.ids.btn_home.bind(on_press=self.on_home)

        return super().on_kv_post(base_widget)

    def model_is_changed(self, *args):
        if not self.view_model:
            return

        active_tab = self.view_model.active_tab

        if self._observed_tab != active_tab:
            if self._observed_tab and self in self._observed_tab._observers:
                self._observed_tab.remove_observer(self)
            self._observed_tab = active_tab
            if self._observed_tab:
                self._observed_tab.add_observer(self)

        from kivy.app import App

        app = App.get_running_app()
        is_home = getattr(app, "is_home", lambda: False)()

        if not active_tab:
            self.ids.btn_back.disabled = is_home
            self.ids.btn_fwd.disabled = True
            self.ids.btn_reload.icon = "renew"
            self.ids.search_input.text = ""
            return

        # Back button is only disabled if we are completely at the home screen
        self.ids.btn_back.disabled = is_home
        self.ids.btn_fwd.disabled = not active_tab.can_go_forward

        if active_tab.is_loading:
            self.ids.btn_reload.icon = "close"
        else:
            self.ids.btn_reload.icon = "renew"

        self.ids.search_input.text = "" if is_home else active_tab.url

    def on_back(self, *args):
        from kivy.app import App

        app = App.get_running_app()

        if (
            self.view_model
            and self.view_model.active_tab
            and self.view_model.active_tab.can_go_back
        ):
            self.view_model.active_tab.go_back()
        else:
            if hasattr(app, "go_home"):
                app.go_home()

    def on_home(self, *args):
        from kivy.app import App

        app = App.get_running_app()
        if hasattr(app, "go_home"):
            app.go_home()

    def on_fwd(self, *args):
        if self.view_model and self.view_model.active_tab:
            self.view_model.active_tab.go_forward()

    def on_reload(self, *args):
        if self.view_model and self.view_model.active_tab:
            if self.view_model.active_tab.is_loading:
                self.view_model.active_tab.stop()
            else:
                self.view_model.active_tab.reload()

    def on_search(self, text):
        if self.view_model:
            if self.view_model.active_tab:
                self.view_model.active_tab.load(text)
            else:
                self.view_model.new_tab(text)
