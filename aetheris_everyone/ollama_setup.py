"""Getting a local AI running without anyone opening a terminal.

Ollama is the engine that runs models on this computer. This module finds it,
starts it if it is installed but not running, installs it through the
platform's own graphical installer if it is missing, and downloads a model
with a progress bar. Every step reports through `emit(event)` so the window can
show it.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request

from aetheris_everyone import providers, settings

DOWNLOAD_PAGE = "https://ollama.com/download"
_RELEASES = "https://github.com/ollama/ollama/releases/latest/download/"

# What the setup screen offers. Sizes are read from the registry at runtime.
MODELS = [
    {"id": "gemma4:e2b", "tier": "light", "min_ram": 0},
    {"id": "gemma4:e4b", "tier": "recommended", "min_ram": 12},
    {"id": "gemma4:12b", "tier": "strong", "min_ram": 24},
]

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def host() -> str:
    return providers.OllamaProvider().host


def running() -> bool:
    try:
        providers.request_json(f"{host()}/api/version", timeout=3, provider="ollama")
        return True
    except providers.ProviderError:
        return False


def _candidates() -> list:
    found = []
    which = shutil.which("ollama")
    if which:
        found.append(which)
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        found += [os.path.join(local, "Programs", "Ollama", "ollama.exe")]
    elif sys.platform == "darwin":
        found += ["/Applications/Ollama.app/Contents/Resources/ollama",
                  os.path.expanduser("~/Applications/Ollama.app/Contents/Resources/ollama"),
                  "/usr/local/bin/ollama", "/opt/homebrew/bin/ollama"]
    else:
        found += ["/usr/local/bin/ollama", "/usr/bin/ollama",
                  os.path.expanduser("~/.local/bin/ollama")]
    return found


def executable() -> str:
    for path in _candidates():
        if path and os.path.isfile(path):
            return path
    return ""


def _mac_app() -> str:
    for path in ("/Applications/Ollama.app", os.path.expanduser("~/Applications/Ollama.app")):
        if os.path.isdir(path):
            return path
    return ""


def installed() -> bool:
    return bool(executable() or (sys.platform == "darwin" and _mac_app()))


def ram_gb() -> float:
    try:
        if sys.platform == "win32":
            import ctypes

            class _Status(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("sullAvailExtendedVirtual", ctypes.c_ulonglong)]
            status = _Status()
            status.dwLength = ctypes.sizeof(_Status)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
            return status.ullTotalPhys / 1024 ** 3
        if sys.platform == "darwin":
            out = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
            return int(out.stdout.strip()) / 1024 ** 3
        return os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except Exception:
        return 0.0


def recommended(ram: float) -> str:
    choice = MODELS[0]["id"]
    for model in MODELS:
        if ram >= model["min_ram"]:
            choice = model["id"]
    return choice


_sizes: dict = {}


def download_size(model: str) -> int:
    """Bytes to download for `model`, from the Ollama registry (0 if unknown)."""
    if model in _sizes:
        return _sizes[model]
    name, _, tag = model.partition(":")
    if "/" not in name:
        name = f"library/{name}"
    url = f"https://registry.ollama.ai/v2/{name}/manifests/{tag or 'latest'}"
    size = 0
    try:
        request = urllib.request.Request(url, headers={
            "Accept": "application/vnd.docker.distribution.manifest.v2+json"})
        with urllib.request.urlopen(request, timeout=8, context=providers.ssl_context()) as r:
            manifest = json.loads(r.read().decode("utf-8"))
        size = sum(int(layer.get("size", 0)) for layer in manifest.get("layers", []))
    except Exception:
        size = 0
    _sizes[model] = size
    return size


def status() -> dict:
    is_running = running()
    models = []
    if is_running:
        try:
            models = providers.OllamaProvider().list_models()
        except providers.ProviderError:
            models = []
    ram = ram_gb()
    return {"installed": is_running or installed(), "running": is_running, "models": models,
            "ram_gb": round(ram, 1), "recommended": recommended(ram),
            "choices": MODELS, "platform": sys.platform,
            "can_install": sys.platform in ("win32", "darwin") or bool(shutil.which("pkexec"))}


def start() -> bool:
    """Start the engine if it is installed; wait up to 30 seconds for it."""
    if running():
        return True
    try:
        if sys.platform == "darwin" and _mac_app():
            subprocess.Popen(["open", "-g", _mac_app()])
        else:
            path = executable()
            if not path:
                return False
            if sys.platform == "win32":
                app = os.path.join(os.path.dirname(path), "ollama app.exe")
                if os.path.isfile(app):
                    subprocess.Popen([app], creationflags=_NO_WINDOW)
                else:
                    subprocess.Popen([path, "serve"], creationflags=_NO_WINDOW,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            else:
                subprocess.Popen([path, "serve"], stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
    except OSError:
        return False
    for _ in range(60):
        if running():
            return True
        time.sleep(0.5)
    return False


def _download(url: str, target: str, emit, stop: threading.Event) -> bool:
    request = urllib.request.Request(url, headers={"User-Agent": "AetherisEveryone"})
    with urllib.request.urlopen(request, timeout=60, context=providers.ssl_context()) as response, \
            open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0)
        done, last = 0, 0.0
        while True:
            if stop.is_set():
                return False
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            done += len(chunk)
            if time.time() - last > 0.3:
                last = time.time()
                emit({"type": "install", "stage": "download", "completed": done, "total": total})
    return True


def install(emit, stop: threading.Event) -> None:
    """Fetch and launch Ollama's own installer, then wait for the engine."""
    try:
        if sys.platform == "win32":
            target = os.path.join(tempfile.gettempdir(), "OllamaSetup.exe")
            if not _download(_RELEASES + "OllamaSetup.exe", target, emit, stop):
                return
            emit({"type": "install", "stage": "installer"})
            os.startfile(target)                     # the installer's own window
        elif sys.platform == "darwin":
            target = os.path.join(tempfile.gettempdir(), "Ollama-darwin.zip")
            if not _download(_RELEASES + "Ollama-darwin.zip", target, emit, stop):
                return
            emit({"type": "install", "stage": "unpack"})
            destination = "/Applications"
            if not os.access(destination, os.W_OK):
                destination = os.path.expanduser("~/Applications")
                os.makedirs(destination, exist_ok=True)
            subprocess.run(["ditto", "-x", "-k", target, destination], check=True)
            subprocess.Popen(["open", os.path.join(destination, "Ollama.app")])
        else:
            if not shutil.which("pkexec"):
                emit({"type": "install", "stage": "manual", "url": DOWNLOAD_PAGE})
                return
            target = os.path.join(tempfile.gettempdir(), "ollama-install.sh")
            if not _download("https://ollama.com/install.sh", target, emit, stop):
                return
            emit({"type": "install", "stage": "installer"})
            # pkexec asks for the password in a graphical dialog.
            result = subprocess.run(["pkexec", "sh", target], capture_output=True, text=True)
            if result.returncode != 0:
                emit({"type": "install", "stage": "failed",
                      "detail": (result.stderr or result.stdout)[-600:]})
                return
        emit({"type": "install", "stage": "waiting"})
        deadline = time.time() + 15 * 60
        while time.time() < deadline and not stop.is_set():
            if running() or (installed() and start()):
                emit({"type": "install", "stage": "done"})
                return
            time.sleep(2)
        emit({"type": "install", "stage": "failed", "detail": "timeout"})
    except Exception as error:
        emit({"type": "install", "stage": "failed", "detail": str(error)[:600]})


def pull(model: str, emit, stop: threading.Event) -> bool:
    """Download `model`, reporting overall progress across its layers."""
    totals, done = {}, {}
    last = 0.0
    try:
        response = providers._open(f"{host()}/api/pull", {"model": model, "stream": True},
                                   timeout=120)
    except urllib.error.HTTPError as error:
        emit({"type": "pull", "model": model, "stage": "failed",
              "detail": providers._error_from_http(error, "ollama").detail})
        return False
    except (urllib.error.URLError, OSError) as error:
        emit({"type": "pull", "model": model, "stage": "failed", "detail": str(error)})
        return False
    with response:
        for raw in response:
            if stop.is_set():
                emit({"type": "pull", "model": model, "stage": "cancelled"})
                return False
            try:
                line = json.loads(raw.decode("utf-8"))
            except ValueError:
                continue
            if line.get("error"):
                emit({"type": "pull", "model": model, "stage": "failed", "detail": line["error"]})
                return False
            digest = line.get("digest")
            if digest and line.get("total"):
                totals[digest] = line["total"]
                done[digest] = line.get("completed", 0)
            if time.time() - last > 0.25 or line.get("status") == "success":
                last = time.time()
                emit({"type": "pull", "model": model, "stage": "download",
                      "status": line.get("status", ""),
                      "completed": sum(done.values()), "total": sum(totals.values())})
            if line.get("status") == "success":
                emit({"type": "pull", "model": model, "stage": "done"})
                return True
    emit({"type": "pull", "model": model, "stage": "failed", "detail": "incomplete"})
    return False


def describe_machine() -> str:
    return f"{platform.system()} {platform.machine()}, {ram_gb():.0f}GB RAM"


def use_model(model: str) -> None:
    settings.update({"provider": "ollama", "models": {"ollama": model}})
