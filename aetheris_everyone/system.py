"""Opening things the way a double-click would, and the native file dialogs.

The launcher replaces `pick_folder` / `pick_files` with the window's own
dialogs when there is a native window. Without one, a tiny Tk dialog is shown
from a separate process (Tk wants the main thread, which the server is not on).
"""

import json
import os
import shutil
import subprocess
import sys
import webbrowser

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

# Never launched from the chat with a click: these run code.
_RUNNABLE = {".exe", ".bat", ".cmd", ".com", ".msi", ".ps1", ".vbs", ".vbe", ".js", ".jse",
             ".wsf", ".wsh", ".scr", ".lnk", ".sh", ".command", ".app", ".jar", ".py", ".pyw",
             ".reg", ".hta", ".cpl", ".desktop", ".run", ".bin", ".appimage", ".pkg", ".dmg",
             # shortcuts and launchers that start a program named inside them (a text file
             # with URL=file:///...calc.exe is enough), and other code Windows runs on open
             ".url", ".website", ".scf", ".pif", ".msp", ".mst", ".msc", ".inf", ".chm",
             ".appref-ms", ".application", ".settingcontent-ms", ".library-ms", ".search-ms",
             ".gadget", ".psm1", ".psd1", ".ws", ".wsc", ".vb", ".xll", ".iqy", ".slk",
             ".mof", ".diagcab", ".xbap", ".jnlp",
             # macOS and Linux launchers
             ".terminal", ".workflow", ".tool", ".fileloc", ".inetloc", ".webloc", ".action"}


def open_url(url: str) -> bool:
    if not url.startswith(("http://", "https://", "mailto:")):
        return False
    return webbrowser.open(url)


def open_path(path: str) -> bool:
    """Open a file in its usual app; a program is shown in its folder instead."""
    if not os.path.exists(path):
        return False
    if os.path.splitext(path)[1].lower() in _RUNNABLE:
        return reveal(path)
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def reveal(path: str) -> bool:
    """Show the file selected in the file manager (or open the folder)."""
    if not os.path.exists(path):
        path = os.path.dirname(path)
        if not os.path.exists(path):
            return False
    if sys.platform == "win32":
        if os.path.isdir(path):
            subprocess.Popen(["explorer", os.path.normpath(path)])
        else:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", path] if os.path.isfile(path) else ["open", path])
    else:
        folder = path if os.path.isdir(path) else os.path.dirname(path)
        subprocess.Popen(["xdg-open", folder], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def notify(title: str, body: str) -> bool:
    """A desktop notification, as the system shows them. False when there is no way to."""
    title, body = str(title)[:80], " ".join(str(body).split())[:240]
    try:
        if sys.platform == "win32":
            # A tray balloon: no app registration needed, unlike toast notifications.
            script = ("Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing;"
                      "$n = New-Object System.Windows.Forms.NotifyIcon;"
                      "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true;"
                      "$n.ShowBalloonTip(6000, $env:AE_TITLE, $env:AE_BODY, 'Info');"
                      "Start-Sleep -Seconds 7; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             env=dict(os.environ, AE_TITLE=title, AE_BODY=body),
                             creationflags=_NO_WINDOW, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if sys.platform == "darwin":
            subprocess.Popen(["osascript", "-e", "on run argv", "-e",
                              "display notification (item 2 of argv) with title (item 1 of argv)",
                              "-e", "end run", title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        if shutil.which("notify-send"):
            subprocess.Popen(["notify-send", "--app-name=Aetheris Everyone", title, body],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
    except OSError:
        pass
    return False


def can_make_shortcut() -> bool:
    """A packaged Windows or Linux app (a .dmg already offers 'drag to Applications')."""
    return bool(getattr(sys, "frozen", False)) and sys.platform in ("win32", "linux")


def make_shortcut() -> bool:
    """Put the app on the desktop and in the start menu / app launcher."""
    target = sys.executable
    if sys.platform == "win32":
        def quoted(text: str) -> str:          # a PowerShell '...' string: ' is doubled
            return "'" + text.replace("'", "''") + "'"

        script = (
            "$s = New-Object -ComObject WScript.Shell;"
            "foreach ($dir in @([Environment]::GetFolderPath('Desktop'), "
            "[Environment]::GetFolderPath('Programs'))) {"
            "$l = $s.CreateShortcut((Join-Path $dir 'Aetheris Everyone.lnk'));"
            f"$l.TargetPath = {quoted(target)};"
            f"$l.WorkingDirectory = {quoted(os.path.dirname(target))};"
            f"$l.IconLocation = {quoted(target + ',0')};"
            "$l.Save() }")
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, creationflags=_NO_WINDOW)
        return result.returncode == 0
    if sys.platform == "linux":
        from aetheris_everyone import paths
        icon = os.path.join(paths.data_dir(), "icon.png")
        bundled = paths.resource("icon.png")
        if os.path.isfile(bundled):
            with open(bundled, "rb") as src, open(icon, "wb") as dst:
                dst.write(src.read())
        entry = ("[Desktop Entry]\nType=Application\nName=Aetheris Everyone\n"
                 "Comment=AI assistant that works on your files\n"
                 f'Exec="{target}"\nIcon={icon}\nTerminal=false\nCategories=Office;Utility;\n')
        written = False
        for folder in (os.path.expanduser("~/.local/share/applications"),
                       os.path.expanduser("~/Desktop"), os.path.expanduser("~/바탕화면")):
            if folder.endswith("applications"):
                os.makedirs(folder, exist_ok=True)
            if not os.path.isdir(folder):
                continue
            path = os.path.join(folder, "aetheris-everyone.desktop")
            with open(path, "w", encoding="utf-8") as f:
                f.write(entry)
            os.chmod(path, 0o755)
            written = True
        return written
    return False


def _tk_dialog(kind: str, initial: str) -> list:
    if getattr(sys, "frozen", False):
        command = [sys.executable, "--dialog", kind, initial]
    else:
        command = [sys.executable, "-m", "aetheris_everyone", "--dialog", kind, initial]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600,
                                creationflags=_NO_WINDOW)
        return json.loads(result.stdout.strip().splitlines()[-1]) if result.stdout.strip() else []
    except Exception:
        return []


def _default_pick_folder(initial: str = "") -> str:
    chosen = _tk_dialog("folder", initial)
    return chosen[0] if chosen else ""


def _default_pick_files(initial: str = "") -> list:
    return _tk_dialog("files", initial)


pick_folder = _default_pick_folder
pick_files = _default_pick_files


def run_dialog(kind: str, initial: str) -> None:
    """The `--dialog` entry point: show one Tk dialog, print the answer as JSON."""
    chosen = []
    try:
        import tkinter
        from tkinter import filedialog
        root = tkinter.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if kind == "folder":
            path = filedialog.askdirectory(initialdir=initial or os.path.expanduser("~"),
                                           mustexist=False)
            chosen = [path] if path else []
        else:
            chosen = list(filedialog.askopenfilenames(initialdir=initial or os.path.expanduser("~")))
        root.destroy()
    except Exception:
        chosen = []
    print(json.dumps(chosen))
