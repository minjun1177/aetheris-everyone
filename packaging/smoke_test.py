"""Start a built app without a window and check it really serves the UI.

    python packaging/smoke_test.py path/to/executable

Catches the packaging mistakes unit tests cannot: a missing web folder, a
module PyInstaller did not pick up, a crash at start.
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request


def main(executable: str) -> int:
    home = tempfile.mkdtemp(prefix="aetheris-smoke-")
    env = dict(os.environ, AETHERIS_EVERYONE_HOME=home)
    process = subprocess.Popen([executable, "--no-window"], env=env)
    instance = os.path.join(home, "instance.json")
    try:
        deadline = time.time() + 120
        while not os.path.exists(instance):
            if process.poll() is not None:
                print("the app exited early with", process.returncode)
                return 1
            if time.time() > deadline:
                print("the app did not start within 120 seconds")
                return 1
            time.sleep(1)
        time.sleep(1)
        with open(instance, encoding="utf-8") as f:
            info = json.load(f)
        base = f"http://127.0.0.1:{info['port']}"
        with urllib.request.urlopen(f"{base}/", timeout=10) as response:
            page = response.read().decode("utf-8")
            assert "Aetheris Everyone" in page, "index.html missing"
        for asset in ("app.js", "style.css", "i18n.js", "markdown.js", "icon.svg"):
            with urllib.request.urlopen(f"{base}/{asset}", timeout=10) as response:
                assert response.status == 200 and response.read(), asset
        request = urllib.request.Request(f"{base}/api/state", headers={"X-Token": info["token"]})
        with urllib.request.urlopen(request, timeout=10) as response:
            state = json.loads(response.read())
            assert state["version"], "no version in state"
        print("smoke test passed:", state["version"])
        return 0
    finally:
        process.kill()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
