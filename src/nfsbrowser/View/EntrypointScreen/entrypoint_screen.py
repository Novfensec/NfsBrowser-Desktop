from typing import Any

from carbonkivy.behaviors import SelectableBehavior, SelectionBehavior
from carbonkivy.effects import FrostedGlassEffect
from carbonkivy.uix.dropdown import CDropdown
from carbonkivy.uix.textinput import CTextInput
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.properties import ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.utils import platform
from libs.config_handler import config_handler
from View.base_screen import BaseScreenView
from View.components.RoundedBoxLayout import RoundedBoxLayout


class SEDropdown(SelectionBehavior, CDropdown):

    def __init__(self, **kwargs):
        super(SEDropdown, self).__init__(**kwargs)

    def on_selected_items(self, *args) -> None:
        self.visibility = False


class SEOption(ButtonBehavior, RoundedBoxLayout, SelectableBehavior):

    title = StringProperty()

    source = StringProperty()

    def __init__(self, **kwargs):
        super(SEOption, self).__init__(**kwargs)

    def on_kv_post(self, base_widget):
        super().on_kv_post(base_widget)
        self.selected = self.title.lower() == config_handler.get("search_engine")

    def on_selected(self, *args) -> None:
        if self.selected:
            config_handler.update({"search_engine": self.title.lower()})


class FixedTextInput(CTextInput):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def on_text(self, instance, value):
        if not self.focus:
            Clock.schedule_once(self._reset_cursor_to_start, 0)

    def _reset_cursor_to_start(self, dt):
        if not self.focus:
            self.cursor = (0, 0)
            self.scroll_x = 0


class CTabHeaderCircular(SelectionBehavior, RoundedBoxLayout):

    tab_manager = ObjectProperty()

    def __init__(self, **kwargs) -> None:
        super(CTabHeaderCircular, self).__init__(**kwargs)

    def on_tab_manager(self, *args) -> None:
        for widgets in self.children:
            widgets.tab_manager = self.tab_manager

    def add_widget(self, widget, *args, **kwargs) -> Any:
        if hasattr(widget, "tab_manager"):
            widget.tab_manager = self.tab_manager
        return super().add_widget(widget, *args, **kwargs)


class FrostedGlass(BoxLayout, FrostedGlassEffect):

    def __init__(self, **kwargs) -> None:
        super(FrostedGlass, self).__init__(**kwargs)


class EntrypointScreenView(BaseScreenView):

    current_se = StringProperty()

    se_source = StringProperty()

    se_dropdown = ObjectProperty()

    def __init__(self, *args, **kwargs) -> None:
        self.se_dropdown = SEDropdown()
        super(EntrypointScreenView, self).__init__(*args, **kwargs)
        self.current_se = config_handler.get("search_engine", "google")
        self.app.current_se = config_handler.get("search_engine", "google")

    def on_kv_post(self, base_widget):
        self.se_dropdown.master = self.ids.engine_icon
        return super().on_kv_post(base_widget)
