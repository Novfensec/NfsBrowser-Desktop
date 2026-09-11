from typing import Literal

from carbonkivy.effects.gradient import GradientEffect
from carbonkivy.uix.button import CButtonCircular
from carbonkivy.uix.loading import CLoadingLayout
from carbonkivy.uix.notification import CNotificationInline, CNotificationToast
from carbonkivy.uix.screen import CScreen
from kivy.app import App
from kivy.clock import Clock
from kivy.input.providers.mouse import MouseMotionEvent
from kivy.properties import ObjectProperty
from kivy.uix.boxlayout import BoxLayout
from carbonkivy.uix.boxlayout import CBoxLayout
from Utility.observer import Observer

class GradientLayout(GradientEffect, BoxLayout):
    pass


class ActiveButton(CButtonCircular):
    pass


class BanLayout(CLoadingLayout):

    def __init__(self, **kwargs) -> None:
        super(BanLayout, self).__init__(**kwargs)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            super().on_touch_down(touch)
            return True
        return False

    def on_touch_up(self, touch):
        if self.collide_point(*touch.pos):
            super().on_touch_up(touch)
            return True
        return False


class LoadingLayout(CLoadingLayout):

    def __init__(self, **kwargs) -> None:
        super(LoadingLayout, self).__init__(**kwargs)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos):
            return True
        return super(LoadingLayout, self).on_touch_down(touch)

    def on_touch_move(self, touch: MouseMotionEvent) -> Literal[True] | None:
        if self.collide_point(*touch.pos):
            return True
        return super(LoadingLayout, self).on_touch_move(touch)

    def on_touch_up(self, touch: MouseMotionEvent) -> Literal[True] | None:
        if self.collide_point(*touch.pos):
            return True
        return super(LoadingLayout, self).on_touch_up(touch)


class BaseScreenView(CScreen, Observer):

    manager_screens = ObjectProperty()
    """
    Screen manager object - :class:`~carbonkivy.uix.screenmanager.CScreenManager`.

    :attr:`manager_screens` is an :class:`~kivy.properties.ObjectProperty`
    and defaults to `None`.
    """

    def __init__(self, *args, **kwargs) -> None:
        super(BaseScreenView, self).__init__(*args, **kwargs)
        # Often you need to get access to the application object from the view
        # class. You can do this using this attribute.
        self.app = App.get_running_app()

    def on_kv_post(self, base_widget):
        self.notificationt = CNotificationToast()
        self.notificationl = CNotificationInline()
        return super().on_kv_post(base_widget)

    def notify(
        self,
        variant: str = "Inline",
        title: str = "",
        subtitle: str = "",
        status: str = "Info",
        time_caption_enabled: bool = True,
        *args,
    ) -> None:
        if variant == "Inline":
            notification = self.notificationl
        else:
            notification = self.notificationt
        notification.title = title
        notification.subtitle = subtitle
        notification.status = status
        notification.time_caption_enabled = time_caption_enabled
        notification.open()
