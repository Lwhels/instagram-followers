"""Native macOS Desktop Application for Instagram Follower Analyzer.
Uses PyObjC Cocoa and WebKit to render a standalone desktop window without browser URL bars.
"""

import os
import sys
import time
import threading
import socket
import uvicorn
from urllib.request import urlopen

def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]

def start_backend(port: int):
    from instagram_analyzer.api import app
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

def wait_for_server(url: str, timeout: float = 5.0):
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urlopen(f"{url}/api/status", timeout=0.5) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False

def run_desktop_app():
    port = 8000
    # Check if port 8000 is occupied or find free port
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('127.0.0.1', port))
    except OSError:
        port = find_free_port()

    server_url = f"http://127.0.0.1:{port}"

    # Launch backend thread
    server_thread = threading.Thread(target=start_backend, args=(port,), daemon=True)
    server_thread.start()

    print(f"[*] Starting Follower Vault macOS App on {server_url}...")
    if not wait_for_server(server_url, timeout=6.0):
        print("[-] Server failed to respond in time.")
        sys.exit(1)

    try:
        import Cocoa
        import WebKit
        from Foundation import NSURL, NSURLRequest

        app = Cocoa.NSApplication.sharedApplication()
        app.setActivationPolicy_(Cocoa.NSApplicationActivationPolicyRegular)

        # Window rect (1200 x 860)
        screen = Cocoa.NSScreen.mainScreen()
        screen_rect = screen.frame() if screen else Cocoa.NSMakeRect(0, 0, 1440, 900)
        w, h = 1240, 860
        x = (screen_rect.size.width - w) / 2
        y = (screen_rect.size.height - h) / 2
        frame = Cocoa.NSMakeRect(x, y, w, h)

        style_mask = (
            Cocoa.NSWindowStyleMaskTitled
            | Cocoa.NSWindowStyleMaskClosable
            | Cocoa.NSWindowStyleMaskMiniaturizable
            | Cocoa.NSWindowStyleMaskResizable
        )

        window = Cocoa.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame, style_mask, Cocoa.NSBackingStoreBuffered, False
        )
        window.setTitle_("Instagram Follower Analyzer & Swipe Deck")
        window.setMinSize_(Cocoa.NSMakeSize(800, 600))
        window.setReleasedWhenClosed_(False)

        # WebKit View
        web_view = WebKit.WKWebView.alloc().initWithFrame_(frame)
        ns_url = NSURL.URLWithString_(server_url)
        req = NSURLRequest.requestWithURL_(ns_url)
        web_view.loadRequest_(req)

        window.setContentView_(web_view)
        window.makeKeyAndOrderFront_(None)
        app.activateIgnoringOtherApps_(True)

        print("[+] macOS Native App Window running.")
        app.run()

    except Exception as e:
        print(f"[!] PyObjC WebKit error: {e}. Falling back to default browser.")
        import webbrowser
        webbrowser.open(server_url)
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down.")

if __name__ == "__main__":
    run_desktop_app()
