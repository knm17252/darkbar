import re

SCRIPT = "darkbar_1g4a.py"      # the only line you change per build
VERSION, BUILD = re.search(r'VERSION, BUILD = "([^"]+)", "([^"]+)"',
                           open(SCRIPT).read()).groups()

a = Analysis([SCRIPT], datas=[("icon.png", "."), ("DarkBar.icns", ".")])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="DarkBar", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="DarkBar")
app = BUNDLE(
    coll,
    name="DarkBar.app",
    icon="DarkBar.icns",
    bundle_identifier="ua.mk.darkbar",
    version=VERSION,                       # CFBundleShortVersionString -> "1.0"
    info_plist={
        "CFBundleVersion": BUILD,          # the build -> "1G4A"
        "LSUIElement": True,               # no Dock icon, replaces the PlistBuddy step
    },
)
