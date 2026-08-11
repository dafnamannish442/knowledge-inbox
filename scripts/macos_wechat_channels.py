from __future__ import annotations

import ctypes
import subprocess
import sys
import time
from pathlib import Path


APPLICATION_SERVICES = Path(
    "/System/Library/Frameworks/ApplicationServices.framework/ApplicationServices"
)
CORE_FOUNDATION = Path(
    "/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation"
)


class CGPoint(ctypes.Structure):
    _fields_ = [("x", ctypes.c_double), ("y", ctypes.c_double)]


class CGSize(ctypes.Structure):
    _fields_ = [("width", ctypes.c_double), ("height", ctypes.c_double)]


def open_channels() -> None:
    app = ctypes.CDLL(str(APPLICATION_SERVICES))
    cf = ctypes.CDLL(str(CORE_FOUNDATION))
    _configure(app, cf)
    if not app.AXIsProcessTrusted():
        raise RuntimeError(
            "Hermes Python 缺少辅助功能权限："
            f"{Path(sys.executable).resolve()}"
        )

    subprocess.run(
        ["/usr/bin/open", "-b", "com.tencent.xinWeChat"],
        check=True,
        capture_output=True,
        text=True,
    )
    pid = int(
        subprocess.run(
            ["/usr/bin/pgrep", "-x", "WeChat"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()[0]
    )
    window = _landscape_window(app, cf, pid)
    try:
        position = CGPoint(100, 100)
        position_value = app.AXValueCreate(1, ctypes.byref(position))
        attribute = _cf_string(cf, "AXPosition")
        action = _cf_string(cf, "AXRaise")
        try:
            _ax_check(
                app.AXUIElementSetAttributeValue(window, attribute, position_value),
                "无法移动微信主窗口",
            )
            _ax_check(
                app.AXUIElementPerformAction(window, action),
                "无法唤醒微信主窗口",
            )
        finally:
            cf.CFRelease(action)
            cf.CFRelease(attribute)
            cf.CFRelease(position_value)

        time.sleep(1)
        point = CGPoint(130, 415)
        for event_type in (1, 2):
            event = app.CGEventCreateMouseEvent(None, event_type, point, 0)
            if not event:
                raise RuntimeError("无法创建视频号点击事件")
            app.CGEventPost(0, event)
            cf.CFRelease(event)
    finally:
        cf.CFRelease(window)


def _configure(app: ctypes.CDLL, cf: ctypes.CDLL) -> None:
    app.AXIsProcessTrusted.restype = ctypes.c_bool
    app.AXUIElementCreateApplication.argtypes = [ctypes.c_int]
    app.AXUIElementCreateApplication.restype = ctypes.c_void_p
    app.AXUIElementCopyAttributeValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    app.AXUIElementCopyAttributeValue.restype = ctypes.c_int32
    app.AXUIElementSetAttributeValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    app.AXUIElementSetAttributeValue.restype = ctypes.c_int32
    app.AXUIElementPerformAction.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    app.AXUIElementPerformAction.restype = ctypes.c_int32
    app.AXValueGetValue.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    app.AXValueGetValue.restype = ctypes.c_bool
    app.AXValueCreate.argtypes = [ctypes.c_uint32, ctypes.c_void_p]
    app.AXValueCreate.restype = ctypes.c_void_p
    app.CGEventCreateMouseEvent.argtypes = [
        ctypes.c_void_p,
        ctypes.c_uint32,
        CGPoint,
        ctypes.c_uint32,
    ]
    app.CGEventCreateMouseEvent.restype = ctypes.c_void_p
    app.CGEventPost.argtypes = [ctypes.c_uint32, ctypes.c_void_p]

    cf.CFStringCreateWithCString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_uint32,
    ]
    cf.CFStringCreateWithCString.restype = ctypes.c_void_p
    cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
    cf.CFArrayGetCount.restype = ctypes.c_long
    cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
    cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
    cf.CFRetain.argtypes = [ctypes.c_void_p]
    cf.CFRetain.restype = ctypes.c_void_p
    cf.CFRelease.argtypes = [ctypes.c_void_p]


def _cf_string(cf: ctypes.CDLL, value: str) -> int:
    return cf.CFStringCreateWithCString(None, value.encode(), 0x08000100)


def _copy_attribute(app: ctypes.CDLL, cf: ctypes.CDLL, element: int, name: str) -> int:
    value = ctypes.c_void_p()
    attribute = _cf_string(cf, name)
    try:
        _ax_check(
            app.AXUIElementCopyAttributeValue(element, attribute, ctypes.byref(value)),
            f"无法读取微信窗口属性 {name}",
        )
    finally:
        cf.CFRelease(attribute)
    return value.value


def _landscape_window(
    app: ctypes.CDLL, cf: ctypes.CDLL, pid: int
) -> int:
    application = app.AXUIElementCreateApplication(pid)
    windows = _copy_attribute(app, cf, application, "AXWindows")
    try:
        for index in range(cf.CFArrayGetCount(windows)):
            window = cf.CFArrayGetValueAtIndex(windows, index)
            size_value = _copy_attribute(app, cf, window, "AXSize")
            try:
                size = CGSize()
                if app.AXValueGetValue(size_value, 2, ctypes.byref(size)):
                    if size.width > size.height:
                        return cf.CFRetain(window)
            finally:
                cf.CFRelease(size_value)
    finally:
        cf.CFRelease(windows)
        cf.CFRelease(application)
    raise RuntimeError("未找到微信主窗口")


def _ax_check(code: int, message: str) -> None:
    if code:
        raise RuntimeError(f"{message}（AX error {code}）")


if __name__ == "__main__":
    open_channels()
