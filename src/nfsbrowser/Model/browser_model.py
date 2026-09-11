from kivy.properties import ListProperty, NumericProperty, ObjectProperty

from .base_model import BaseScreenModel
from .tab_model import TabModel


class BrowserModel(BaseScreenModel):
    tabs = ListProperty([])
    active_tab_index = NumericProperty(-1)

    # Expose the currently active tab model
    active_tab = ObjectProperty(None, allownone=True)

    def __init__(self, **kwargs):
        super(BrowserModel, self).__init__(**kwargs)
        self.bind(active_tab_index=self._update_active_tab)
        self.bind(tabs=self.notify_all_observers)

    def notify_all_observers(self, *args):
        from kivy.clock import Clock

        for observer in self._observers:
            Clock.schedule_once(observer.model_is_changed)

    def new_tab(self, url="", load_immediately=True):
        tab = TabModel()
        tab.url = url
        self.tabs.append(tab)
        # Select the new tab
        self.active_tab_index = len(self.tabs) - 1

        if load_immediately:
            tab.load(url)
        return tab

    def close_tab(self, index):
        if 0 <= index < len(self.tabs):
            tab = self.tabs.pop(index)
            tab.destroy()

            if not self.tabs:
                self.active_tab_index = -1
                from kivy.app import App

                App.get_running_app().stop()
            elif self.active_tab_index >= len(self.tabs):
                self.active_tab_index = len(self.tabs) - 1
            else:
                # Force update if the index hasn't changed but the tab at index has
                self._update_active_tab(self, self.active_tab_index)

    def select_tab(self, index):
        if 0 <= index < len(self.tabs):
            self.active_tab_index = index

    def _update_active_tab(self, instance, value):
        if 0 <= value < len(self.tabs):
            self.active_tab = self.tabs[value]
        else:
            self.active_tab = None
        self.notify_all_observers()

    def destroy_all(self):
        for tab in self.tabs:
            tab.destroy()
        self.tabs.clear()
        self.active_tab_index = -1
