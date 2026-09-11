import ctypes
import platform
import sys
from ctypes import wintypes

from kivy.clock import Clock
from kivy.core.window import Window

if platform.system() == "Windows":
    user32 = ctypes.windll.user32
    dwmapi = ctypes.windll.dwmapi

    class POINT(ctypes.Structure):
        _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

    class MINMAXINFO(ctypes.Structure):
        _fields_ = [
            ("ptReserved", POINT),
            ("ptMaxSize", POINT),
            ("ptMaxPosition", POINT),
            ("ptMinTrackSize", POINT),
            ("ptMaxTrackSize", POINT),
        ]

    class NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class MONITORINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("rcMonitor", wintypes.RECT),
            ("rcWork", wintypes.RECT),
            ("dwFlags", wintypes.DWORD),
        ]

    class MARGINS(ctypes.Structure):
        _fields_ = [
            ("cxLeftWidth", ctypes.c_int),
            ("cxRightWidth", ctypes.c_int),
            ("cyTopHeight", ctypes.c_int),
            ("cyBottomHeight", ctypes.c_int),
        ]

    if sys.maxsize > 2**32:
        GetWindowLongPtr = user32.GetWindowLongPtrW
        GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
        GetWindowLongPtr.restype = ctypes.c_void_p

        SetWindowLongPtr = user32.SetWindowLongPtrW
        SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        SetWindowLongPtr.restype = ctypes.c_void_p
    else:
        GetWindowLongPtr = user32.GetWindowLongW
        GetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int]
        GetWindowLongPtr.restype = ctypes.c_void_p

        SetWindowLongPtr = user32.SetWindowLongW
        SetWindowLongPtr.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        SetWindowLongPtr.restype = ctypes.c_void_p

    WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM
    )


class NativeFrame:
    """Encapsulates Win32/DWM hooks to provide a borderless resizable window
    with native taskbar-aware maximization and aero-snap support."""

    def __init__(self, border_width=5):
        self.border_width = border_width
        self.old_wndproc = None
        self.wndproc_hook = None
        if platform.system() == "Windows":
            Clock.schedule_once(self._apply, 0.1)

    def _apply(self, dt):
        hwnd = user32.GetActiveWindow()
        if not hwnd:
            Clock.schedule_once(self._apply, 0.1)
            return

        GWL_STYLE = -16
        WS_CAPTION = 0x00C00000
        WS_THICKFRAME = 0x00040000

        style = GetWindowLongPtr(hwnd, GWL_STYLE) or 0
        new_style = style | WS_CAPTION | WS_THICKFRAME
        SetWindowLongPtr(hwnd, GWL_STYLE, new_style)
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)

        try:
            dark_mode = ctypes.c_int(1)
            dwmapi.DwmSetWindowAttribute(
                hwnd, 19, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)
            )
            dwmapi.DwmSetWindowAttribute(
                hwnd, 20, ctypes.byref(dark_mode), ctypes.sizeof(dark_mode)
            )

            DWMWA_BORDER_COLOR = 34
            border_color = ctypes.c_uint(0xFFFFFFFE)  # DWMWA_COLOR_NONE
            dwmapi.DwmSetWindowAttribute(
                hwnd,
                DWMWA_BORDER_COLOR,
                ctypes.byref(border_color),
                ctypes.sizeof(border_color),
            )

            margins = MARGINS(-1, -1, -1, -1)
            dwmapi.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
        except Exception:
            pass

        GWLP_WNDPROC = -4
        raw_old_ptr = GetWindowLongPtr(hwnd, GWLP_WNDPROC)
        self.old_wndproc = WNDPROC(raw_old_ptr)

        border_w = self.border_width

        def wndproc(hwnd, msg, wparam, lparam):
            try:
                # WM_NCCALCSIZE: Remove standard top border
                if msg == 0x0083 and wparam:
                    if user32.IsZoomed(hwnd):
                        params = ctypes.cast(
                            lparam, ctypes.POINTER(NCCALCSIZE_PARAMS)
                        ).contents
                        # SM_CXSIZEFRAME = 32, SM_CYSIZEFRAME = 33, SM_CXPADDEDBORDER = 92
                        border_x = user32.GetSystemMetrics(
                            32
                        ) + user32.GetSystemMetrics(92)
                        border_y = user32.GetSystemMetrics(
                            33
                        ) + user32.GetSystemMetrics(92)
                        params.rgrc[0].left += border_x
                        params.rgrc[0].top += border_y
                        params.rgrc[0].right -= border_x
                        params.rgrc[0].bottom -= border_y
                    return 0

                # WM_NCHITTEST: Custom small resizable borders
                if msg == 0x0084 and not user32.IsZoomed(hwnd):
                    x = ctypes.c_short(lparam & 0xFFFF).value
                    y = ctypes.c_short((lparam >> 16) & 0xFFFF).value

                    rect = wintypes.RECT()
                    user32.GetWindowRect(hwnd, ctypes.byref(rect))

                    is_left = x < rect.left + border_w
                    is_right = x >= rect.right - border_w
                    is_top = y < rect.top + border_w
                    is_bottom = y >= rect.bottom - border_w

                    if is_top and is_left:
                        return 13  # HTTOPLEFT
                    if is_top and is_right:
                        return 14  # HTTOPRIGHT
                    if is_bottom and is_left:
                        return 16  # HTBOTTOMLEFT
                    if is_bottom and is_right:
                        return 17  # HTBOTTOMRIGHT
                    if is_top:
                        return 12  # HTTOP
                    if is_bottom:
                        return 15  # HTBOTTOM
                    if is_left:
                        return 10  # HTLEFT
                    if is_right:
                        return 11  # HTRIGHT

                # WM_GETMINMAXINFO: Fix taskbar overlap when maximized
                if msg == 0x0024:
                    h_monitor = user32.MonitorFromWindow(hwnd, 2)
                    monitor_info = MONITORINFO()
                    monitor_info.cbSize = ctypes.sizeof(MONITORINFO)
                    user32.GetMonitorInfoW(h_monitor, ctypes.byref(monitor_info))

                    mmi = ctypes.cast(lparam, ctypes.POINTER(MINMAXINFO)).contents
                    mmi.ptMaxSize.x = (
                        monitor_info.rcWork.right - monitor_info.rcWork.left
                    )
                    mmi.ptMaxSize.y = (
                        monitor_info.rcWork.bottom - monitor_info.rcWork.top
                    )
                    mmi.ptMaxPosition.x = (
                        monitor_info.rcWork.left - monitor_info.rcMonitor.left
                    )
                    mmi.ptMaxPosition.y = (
                        monitor_info.rcWork.top - monitor_info.rcMonitor.top
                    )

                    mmi.ptMinTrackSize.x = 800
                    mmi.ptMinTrackSize.y = 600

                    return 0

                if msg == 0x0086 and wparam == 0:
                    return 1
            except Exception:
                pass

            return user32.CallWindowProcW(self.old_wndproc, hwnd, msg, wparam, lparam)

        self.wndproc_hook = WNDPROC(wndproc)
        SetWindowLongPtr(
            hwnd, GWLP_WNDPROC, ctypes.cast(self.wndproc_hook, ctypes.c_void_p)
        )
        user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0027)
