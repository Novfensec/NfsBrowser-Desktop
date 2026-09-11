# Of course, "very flexible Python" allows you to do without an abstract
# superclass at all or use the clever exception `NotImplementedError`. In my
# opinion, this can negatively affect the architecture of the application.
# I would like to point out that using Kivy, one could use the on-signaling
# model. In this case, when the state changes, the model will send a signal
# that can be received by all attached observers. This approach seems less
# universal - you may want to use a different library in the future.


from kivy.event import EventDispatcher
from kivy.properties import ObjectProperty


class Observer(EventDispatcher):
    """Abstract superclass for all observers."""

    view_model = ObjectProperty(None, allownone=True)

    def on_view_model(self, instance: object, value: object) -> None:
        """
        This method is called when the view model is set.
        It adds the view as an observer to the model.
        """
        if value is not None:
            if self.view_model is not None and (self not in self.view_model._observers):
                value.add_observer(self)
                self.model_is_changed()

    def model_is_changed(self, *args):
        """
        The method that will be called on the observer when the model changes.
        """
        pass
