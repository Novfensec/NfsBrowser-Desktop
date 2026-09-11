import os

from kivy.factory import Factory
from kivy.logger import Logger

component_register = Factory.register


def register_components():
    """
    Searches for all directories named "components" within the "View" directory
    and registers their sub-directories as components in the Kivy Factory.
    """

    project_root = os.path.dirname(os.path.abspath(__file__))
    view_path = os.path.join(project_root, "View")

    if not os.path.exists(view_path):
        Logger.warning(f"ComponentRegister: 'View' directory not found at {view_path}")
        return

    for root, dirs, files in os.walk(view_path):
        if os.path.basename(root) == "components":
            for component_name in dirs:
                # Skip python cache
                if component_name == "__pycache__":
                    continue

                target_dir = os.path.join(root, component_name)

                try:
                    rel_path = os.path.relpath(target_dir, start=project_root)
                except ValueError:
                    Logger.error(
                        f"ComponentRegister: Could not calculate path for {component_name}"
                    )
                    continue

                module_import_path = rel_path.replace(os.sep, ".")

                try:
                    component_register(component_name, module=module_import_path)
                    Logger.debug(
                        f"ComponentRegister: Registered {component_name} from {module_import_path}"
                    )
                except Exception as e:
                    Logger.error(
                        f"ComponentRegister: Failed to register {component_name}. Error: {e}"
                    )


register_components()

component_register("NfsWebviewWidget", module="nfswebview")
