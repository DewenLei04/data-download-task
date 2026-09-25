import json
import os
import pwd
import subprocess
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

params = json.loads(Path(os.environ["ALE_PARAMS_JSON"]).read_text())
url = params["site_url"].rstrip("/")
if ".invalid" in url:
    raise RuntimeError("Configure the task site_url before running ALE.")
# A website outage is an environment error, not an agent failure.
with urllib.request.urlopen(url, timeout=25) as response:
    if response.status != 200:
        raise RuntimeError("Website is unavailable")

bus_address = Path("/tmp/dbus-session-bus-address").read_text().strip()
subprocess.run(
    [
        "runuser", "-u", "user", "--", "env", "HOME=/home/user", "DISPLAY=:1",
        f"DBUS_SESSION_BUS_ADDRESS={bus_address}", "gnome-extensions", "disable",
        "ding@rastersoft.com",
    ],
    check=True,
    timeout=10,
)
wm_log = open("/tmp/task-openbox.log", "ab")
wm = subprocess.Popen(
    ["runuser", "-u", "user", "--", "env", "HOME=/home/user", "DISPLAY=:1",
     "openbox", "--replace"],
    stdout=wm_log,
    stderr=wm_log,
    start_new_session=True,
)
for _ in range(50):
    if wm.poll() is not None:
        raise RuntimeError("Openbox exited; inspect /tmp/task-openbox.log")
    if subprocess.run(["pgrep", "-x", "openbox"], stdout=subprocess.DEVNULL,
                      check=False).returncode == 0:
        break
    time.sleep(0.2)
else:
    raise RuntimeError("Openbox was not ready")
time.sleep(1)

user = pwd.getpwnam("user")
output = Path("/home/user/output")
output.mkdir(exist_ok=True)
os.chown(output, user.pw_uid, user.pw_gid)
profile = Path("/home/user/.config/task-chromium")
(profile / "Default").mkdir(parents=True, exist_ok=True)
(profile / "Default/Preferences").write_text(
    json.dumps(
        {
            "download": {
                "default_directory": str(output),
                "prompt_for_download": False,
                "directory_upgrade": True,
            },
            "browser": {"check_default_browser": False},
        }
    )
)
for root, dirs, files in os.walk(profile):
    os.chown(root, user.pw_uid, user.pw_gid)
    for name in files:
        os.chown(Path(root) / name, user.pw_uid, user.pw_gid)
with sync_playwright() as p:
    executable = p.chromium.executable_path
proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
browser_args = [f"--proxy-server={proxy}"] if proxy else []
driver_log = open("/tmp/task-cua-driver.log", "ab")
driver = subprocess.Popen(
    [
        "runuser", "-u", "user", "--", "env", "HOME=/home/user", "DISPLAY=:1",
        "cua-driver", "serve", "--socket",
        "/home/user/.cache/cua-driver/cua-driver.sock",
    ],
    stdout=driver_log,
    stderr=driver_log,
    start_new_session=True,
)
for _ in range(50):
    if driver.poll() is not None:
        raise RuntimeError("Desktop driver exited; inspect /tmp/task-cua-driver.log")
    check = subprocess.run(
        ["runuser", "-u", "user", "--", "env", "HOME=/home/user", "DISPLAY=:1",
         "cua-driver", "call", "get_screen_size", "{}"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        timeout=5,
        check=False,
    )
    if check.returncode == 0:
        break
    time.sleep(0.2)
else:
    raise RuntimeError("Desktop driver was not ready")

log = open("/tmp/task-browser.log", "ab")
process = subprocess.Popen(
    [
        "runuser",
        "-u",
        "user",
        "--",
        "env",
        "HOME=/home/user",
        "DISPLAY=:1",
        executable,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-background-networking",
        *browser_args,
        "--window-size=1280,900",
        "--start-maximized",
        f"--user-data-dir={profile}",
        url,
    ],
    stdout=log,
    stderr=log,
    start_new_session=True,
)
time.sleep(3)
if process.poll() is not None:
    raise RuntimeError("Browser exited; inspect /tmp/task-browser.log")
