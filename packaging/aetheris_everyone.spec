# PyInstaller recipe. Build with:  pyinstaller packaging/aetheris_everyone.spec
# Windows -> one AetherisEveryone.exe; macOS -> Aetheris Everyone.app; Linux -> one executable.
import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
NAME = "AetherisEveryone"

datas = [(os.path.join(ROOT, "aetheris_everyone", "web"), os.path.join("aetheris_everyone", "web")),
         (os.path.join(SPECPATH, "icon.png"), "aetheris_everyone")]
hidden = collect_submodules("aetheris_everyone") + collect_submodules("ddgs") + \
    collect_submodules("keyring")
for package in ("webview", "certifi", "ddgs"):
    try:
        datas += collect_data_files(package)
    except Exception:
        pass
# keyring finds its backends through package metadata (entry points).
try:
    datas += copy_metadata("keyring")
except Exception:
    pass

a = Analysis(
    [os.path.join(SPECPATH, "launch.py")],
    pathex=[ROOT],
    datas=datas,
    hiddenimports=hidden,
    excludes=["matplotlib", "numpy", "pandas", "scipy", "PyQt5", "PyQt6", "PySide2", "PySide6",
              "IPython", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

icon = os.path.join(SPECPATH, "icon.ico" if sys.platform == "win32" else "icon.png")

if sys.platform == "darwin":
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name=NAME, console=False,
              icon=icon, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name=NAME)
    app = BUNDLE(
        coll,
        name="Aetheris Everyone.app",
        icon=icon,
        bundle_identifier="io.github.minjun1177.aetheris-everyone",
        info_plist={
            "CFBundleDisplayName": "Aetheris Everyone",
            "CFBundleShortVersionString": "1.2.0",
            "NSHighResolutionCapable": True,
            "LSApplicationCategoryType": "public.app-category.productivity",
        },
    )
else:
    exe = EXE(pyz, a.scripts, a.binaries, a.datas, [], name=NAME, console=False, icon=icon,
              upx=False)
