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
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import hashlib
import urllib.error
import urllib.parse
import urllib.request

from aetheris_everyone import providers, settings

DOWNLOAD_PAGE = "https://ollama.com/download"
_LATEST_API = "https://api.github.com/repos/ollama/ollama/releases/latest"
_RELEASE_FILES = "https://github.com/ollama/ollama/releases/download/{tag}/{name}"

# What the setup screen offers. Sizes are read from the registry at runtime.
MODELS = [
    {"id": "gemma4:e2b", "tier": "light", "min_ram": 0},
    {"id": "gemma4:e4b", "tier": "recommended", "min_ram": 12},
    {"id": "gemma4:12b", "tier": "strong", "min_ram": 24},
]

_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def host() -> str:
    return providers.OllamaProvider().host


def is_local() -> bool:
    """Whether the engine address is this computer (and so something this app can start)."""
    name = (urllib.parse.urlparse(host()).hostname or "").lower()
    return name in ("127.0.0.1", "localhost", "::1", "0.0.0.0") or name.startswith("127.")


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
    local = is_local()
    return {"installed": is_running or (local and installed()), "running": is_running,
            "models": models, "ram_gb": round(ram, 1), "recommended": recommended(ram),
            "choices": MODELS, "platform": sys.platform, "local": local, "host": host(),
            "can_install": local and (sys.platform in ("win32", "darwin")
                                      or bool(shutil.which("pkexec")))}


def start() -> bool:
    """Start the engine if it is installed; wait up to 30 seconds for it."""
    if running():
        return True
    if not is_local():
        return False                 # an engine on another computer is not ours to start
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


class Unverified(Exception):
    pass


def _get(url: str, timeout: float = 20) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "AetherisEveryone",
                                                   "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=timeout, context=providers.ssl_context()) as r:
        return r.read(2_000_000)


def _parse_sums(text: str) -> dict:
    """`sha256sum` output ("<hash>  ./name") as name -> hash."""
    sums = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", parts[0]):
            sums[parts[1].lstrip("*").removeprefix("./")] = parts[0].lower()
    return sums


def release_asset(name: str) -> dict:
    """{"url", "sha256", "size"} of `name` in Ollama's latest GitHub release.

    The hash comes from GitHub's own record of the release (or the release's
    sha256sum.txt), and the address is pinned to that release's tag, so what is
    checked is what is downloaded. Raises `Unverified` when no hash can be had.
    """
    try:
        release = json.loads(_get(_LATEST_API).decode("utf-8"))
        tag = release["tag_name"]
    except Exception as error:
        raise Unverified(f"the release list could not be read ({error})") from None
    asset = next((a for a in release.get("assets") or [] if a.get("name") == name), None)
    if asset is None:
        raise Unverified(f"{name} is not in release {tag}")
    digest = str(asset.get("digest") or "")
    sha = digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else ""
    if not sha:
        try:
            sums = _get(_RELEASE_FILES.format(tag=tag, name="sha256sum.txt")).decode("utf-8", "replace")
            sha = _parse_sums(sums).get(name, "")
        except Exception:
            sha = ""
    if not sha:
        raise Unverified(f"release {tag} publishes no checksum for {name}")
    return {"url": _RELEASE_FILES.format(tag=tag, name=name), "sha256": sha,
            "size": int(asset.get("size") or 0)}


def _download(url: str, target: str, emit, stop: threading.Event, expected: dict) -> bool:
    """Download to `target` and check it against `expected` (size, sha256); False if stopped."""
    request = urllib.request.Request(url, headers={"User-Agent": "AetherisEveryone"})
    digest = hashlib.sha256()
    with urllib.request.urlopen(request, timeout=60, context=providers.ssl_context()) as response, \
            open(target, "wb") as out:
        total = int(response.headers.get("Content-Length") or 0) or expected.get("size", 0)
        done, last = 0, 0.0
        while True:
            if stop.is_set():
                return False
            chunk = response.read(1 << 20)
            if not chunk:
                break
            out.write(chunk)
            digest.update(chunk)
            done += len(chunk)
            if time.time() - last > 0.3:
                last = time.time()
                emit({"type": "install", "stage": "download", "completed": done, "total": total})
    emit({"type": "install", "stage": "verify"})
    if (expected.get("size") and done != expected["size"]) or digest.hexdigest() != expected["sha256"]:
        try:
            os.remove(target)
        except OSError:
            pass
        raise Unverified("the downloaded installer does not match the published checksum")
    return True


def _fetch_verified(name: str, emit, stop: threading.Event) -> str:
    """Path of the verified download of release file `name`, or "" if cancelled."""
    asset = release_asset(name)
    target = os.path.join(tempfile.mkdtemp(prefix="aetheris-ollama-"), name)
    return target if _download(asset["url"], target, emit, stop, asset) else ""


def install(emit, stop: threading.Event) -> None:
    """Fetch, verify and launch Ollama's own installer, then wait for the engine."""
    try:
        if not is_local():
            emit({"type": "install", "stage": "failed", "detail": "remote"})
            return
        if sys.platform == "win32":
            target = _fetch_verified("OllamaSetup.exe", emit, stop)
            if not target:
                return
            emit({"type": "install", "stage": "installer"})
            os.startfile(target)                     # the installer's own window
        elif sys.platform == "darwin":
            target = _fetch_verified("Ollama-darwin.zip", emit, stop)
            if not target:
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
            target = _fetch_verified("install.sh", emit, stop)
            if not target:
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
    except Unverified as error:
        # Never run an installer that could not be checked; offer the download page instead.
        emit({"type": "install", "stage": "manual", "url": DOWNLOAD_PAGE,
              "detail": f"not verified: {error}"})
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
