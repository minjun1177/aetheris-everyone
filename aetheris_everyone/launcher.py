"""Starting the app: one double-click, one window.

1. If the app is already running, its window is shown again instead of a second copy.
2. The local server starts on a random port.
3. A native window opens on it (pywebview). Where that is not available, an
   Edge / Chrome / Chromium "app window" is used, and failing that the default
   browser. In those two cases the app ends a minute after its last window closes.
"""

import os
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

from aetheris_everyone import APP_NAME, ollama_setup, paths, server, settings, system


def _instance_file() -> str:
    return os.path.join(paths.data_dir(), "instance.json")


def _running_instance() -> str:
    """The address of an already-running copy, or ""."""
    info = paths.read_json(_instance_file())
    if not isinstance(info, dict) or not info.get("port"):
        return ""
    url = f"http://127.0.0.1:{info['port']}/api/state?t={info.get('token', '')}"
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            if response.status == 200:
                return f"http://127.0.0.1:{info['port']}/?t={info['token']}"
    except Exception:
        pass
    return ""


def _log_to_file() -> None:
    """A windowed app has no console; keep what it would have printed."""
    if sys.stdout is None or sys.stderr is None or getattr(sys, "frozen", False):
        try:
            log = open(os.path.join(paths.data_dir(), "log.txt"), "a", encoding="utf-8",
                       buffering=1)
            sys.stdout = sys.stdout or log
            sys.stderr = log
        except OSError:
            pass


def _browser_app(url: str) -> bool:
    """A Chromium-family browser as a plain app window, with a profile of its own."""
    candidates = []
    if sys.platform == "win32":
        for root in (os.environ.get("PROGRAMFILES(X86)", ""), os.environ.get("PROGRAMFILES", ""),
                     os.environ.get("LOCALAPPDATA", "")):
            if root:
                candidates += [os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"),
                               os.path.join(root, "Google", "Chrome", "Application", "chrome.exe")]
    elif sys.platform == "darwin":
        candidates += ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                       "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                       "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    else:
        for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                     "microsoft-edge", "brave-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(found)
    profile = paths.sub("window-profile")
    for path in candidates:
        if path and os.path.isfile(path):
            try:
                subprocess.Popen([path, f"--app={url}", f"--user-data-dir={profile}",
                                  "--no-first-run", "--no-default-browser-check",
                                  "--window-size=1240,860"],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return True
            except OSError:
                continue
    return False


def _native_window(url: str, app: server.App) -> bool:
    """Show the app in a native window. False when this machine cannot."""
    try:
        import webview
    except Exception:
        return False
    try:
        window = webview.create_window(APP_NAME, url, width=1240, height=860,
                                       min_size=(760, 560), text_select=True)
        dialog = getattr(webview, "FileDialog", None)
        folder_kind = getattr(dialog, "FOLDER", None) if dialog else None
        open_kind = getattr(dialog, "OPEN", None) if dialog else None
        if folder_kind is None:
            folder_kind = getattr(webview, "FOLDER_DIALOG", 20)
            open_kind = getattr(webview, "OPEN_DIALOG", 10)

        def pick_folder(initial: str = "") -> str:
            chosen = window.create_file_dialog(folder_kind, directory=initial or "")
            return (chosen[0] if isinstance(chosen, (list, tuple)) else chosen) or ""

        def pick_files(initial: str = "") -> list:
            chosen = window.create_file_dialog(open_kind, directory=initial or "",
                                               allow_multiple=True)
            return list(chosen or [])

        system.pick_folder = pick_folder
        system.pick_files = pick_files
        webview.start(private_mode=False, storage_path=paths.sub("webview"))
        return True
    except Exception as error:
        print(f"native window unavailable: {error}", file=sys.stderr)
        system.pick_folder = system._default_pick_folder
        system.pick_files = system._default_pick_files
        return False


def _wait_while_watched(app: server.App) -> None:
    """Keep running while a window is connected, and a minute after the last closes."""
    grace = 90
    while True:
        time.sleep(2)
        watched = len(app.bus._subscribers) > 0
        if watched or app.agent.busy:
            app.last_seen = time.time()
        elif time.time() - app.last_seen > grace:
            return


def _warm_up() -> None:
    """Start the local AI engine early so the first message does not wait for it."""
    current = settings.load()
    if current.get("setup_done") and current.get("provider") == "ollama":
        try:
            if not ollama_setup.running() and ollama_setup.installed():
                ollama_setup.start()
        except Exception:
            pass


def main(argv: list | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "--dialog":
        system.run_dialog(argv[1], argv[2] if len(argv) > 2 else "")
        return 0
    _log_to_file()
    browser_only = "--browser" in argv
    headless = "--no-window" in argv

    existing = _running_instance()
    if existing and not headless:
        if browser_only or not _browser_app(existing):
            import webbrowser
            webbrowser.open(existing)
        return 0

    try:
        server.recover_changes()
    except Exception as error:              # never keep the app from opening
        print(f"could not recover change cards: {error}", file=sys.stderr)
    app = server.App()
    httpd = server.serve(app)
    url = f"http://127.0.0.1:{app.port}/?t={app.token}"
    paths.write_json(_instance_file(), {"port": app.port, "token": app.token, "pid": os.getpid()},
                     private=True)
    threading.Thread(target=_warm_up, daemon=True).start()
    threading.Thread(target=server.clean_attachments, daemon=True).start()
    try:
        if headless:
            print(url, flush=True)
            _wait_while_watched(app) if "--exit-when-idle" in argv else threading.Event().wait()
        elif not browser_only and _native_window(url, app):
            pass                                    # returns when the window closes
        else:
            if browser_only or not _browser_app(url):
                import webbrowser
                webbrowser.open(url)
            _wait_while_watched(app)
    except KeyboardInterrupt:
        pass
    finally:
        app.agent.stop()
        app.agent.wait(15)                  # its change card must reach the conversation
        app.job_stop.set()
        httpd.shutdown()
        info = paths.read_json(_instance_file())
        if isinstance(info, dict) and info.get("pid") == os.getpid():
            try:
                os.remove(_instance_file())
            except OSError:
                pass
    return 0
