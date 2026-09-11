from Model.base_model import BaseScreenModel
from Model.entrypoint_screen import EntrypointScreenModel
from View.DevSupportScreen.devsupport_screen import DevSupportScreenView
from View.EntrypointScreen.entrypoint_screen import EntrypointScreenView

screens = {
    "entrypoint screen": {
        "object": EntrypointScreenView,
        "module": "View.EntrypointScreen",
        "view_model": EntrypointScreenModel,
    },
    "devsupport screen": {
        "object": DevSupportScreenView,
        "module": "View.DevSupportScreen",
        "view_model": BaseScreenModel,
    },
}
