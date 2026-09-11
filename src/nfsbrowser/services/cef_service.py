import os

import pybindcef
from libs.cef_webview import init_cef
from root import ROOT


class CefService:
    _instance = None
    _initialized = False

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(CefService, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def initialize(self, base_dir: str = None):
        if self._initialized:
            return

        if base_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        worker_exe = os.path.join(ROOT, "NfsBrowser_worker.exe")
        res_dir = pybindcef.RESOURCES_DIR

        try:
            init_cef(worker_exe, res_dir, base_dir=base_dir)
            self._initialized = True
            print("[CefService] CEF Initialized successfully.")
        except Exception as e:
            print(f"[CefService] Failed to initialize CEF: {e}")

    def shutdown(self):
        if self._initialized:
            try:
                pybindcef.shutdown()
                self._initialized = False
                print("[CefService] CEF Shutdown successfully.")
            except Exception as e:
                print(f"[CefService] Failed to shutdown CEF: {e}")


cef_service = CefService()
