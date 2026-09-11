import ctypes
import platform

from carbonkivy.behaviors import HoverBehavior, SelectableBehavior, StateFocusBehavior
from carbonkivy.uix.boxlayout import CBoxLayout
from carbonkivy.uix.relativelayout import CRelativeLayout
from carbonkivy.uix.tab import CTabHeaderItem
from kivy.app import App
from kivy.properties import ListProperty, ObjectProperty, StringProperty

if platform.system() == "Windows":
    user32 = ctypes.windll.user32

from Utility.observer import Observer


class TabHeaderItem(SelectableBehavior, StateFocusBehavior, HoverBehavior, CBoxLayout):
    source = StringProperty()
    title = StringProperty()
    icon = StringProperty("blank")
    index = ObjectProperty(None)
    view_model = ObjectProperty(None)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and not self.ids.btn_close.collide_point(
            *touch.pos
        ):
            if self.view_model:
                self.view_model.select_tab(self.index)
            return True
        return super(TabHeaderItem, self).on_touch_down(touch)

    def close_tab(self):
        if self.view_model:
            self.view_model.close_tab(self.index)


class BrowserToolbar(CRelativeLayout, Observer):
    name = "browsertoolbar"
    _observed_tabs = ListProperty([])

    def __init__(self, **kwargs):
        super(BrowserToolbar, self).__init__(**kwargs)

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        if "add_tab_btn" in self.ids:
            self.ids.add_tab_btn.bind(on_press=self.on_add_tab)

    def on_add_tab(self, *args):
        if self.view_model:
            self.view_model.new_tab(url="about:blank", load_immediately=False)
            from kivy.app import App

            app = App.get_running_app()
            if hasattr(app, "go_home"):
                app.go_home()

    def model_is_changed(self, *args):
        if not self.view_model or "tab_header" not in self.ids:
            return

        # Update tab observers
        for tab in self._observed_tabs:
            if self in tab._observers:
                tab.remove_observer(self)
        self._observed_tabs = list(self.view_model.tabs)
        for tab in self._observed_tabs:
            tab.add_observer(self)

        header = self.ids.tab_header
        header.clear_widgets()

        from kivy.app import App

        app = App.get_running_app()
        is_home = getattr(app, "is_home", lambda: False)()

        for i, tab_model in enumerate(self.view_model.tabs):
            is_active = i == self.view_model.active_tab_index

            display_title = tab_model.title
            if (
                tab_model.url == "about:blank"
                or tab_model.url == ""
                or display_title == "about:blank"
            ):
                display_title = "New Tab"

            item = TabHeaderItem(
                title=str(display_title)[:36],
                source="data/novfensec24.png",
                selected=is_active,
                index=i,
                view_model=self.view_model,
            )
            header.add_widget(item)

    def on_touch_down(self, touch):
        if super(BrowserToolbar, self).on_touch_down(touch):
            return True

        if self.collide_point(*touch.pos):
            if platform.system() == "Windows":
                if touch.is_double_tap:
                    app = App.get_running_app()
                    if hasattr(app, "toggle_maximize"):
                        app.toggle_maximize()
                    return True
                user32.ReleaseCapture()
                hwnd = user32.GetActiveWindow()
                user32.SendMessageW(hwnd, 0x00A1, 2, 0)
            return True
        return False
