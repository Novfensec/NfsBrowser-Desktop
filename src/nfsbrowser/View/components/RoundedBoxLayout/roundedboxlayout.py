from __future__ import annotations

__all__ = ("RoundedBoxLayout",)

from carbonkivy.behaviors import (
    AdaptiveBehavior,
    BackgroundColorBehaviorCircular,
    DeclarativeBehavior,
    ElevationBehavior,
)
from kivy.uix.boxlayout import BoxLayout


class RoundedBoxLayout(
    AdaptiveBehavior,
    BackgroundColorBehaviorCircular,
    BoxLayout,
    DeclarativeBehavior,
    ElevationBehavior,
):
    pass
