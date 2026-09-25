"""Install pinned Linux x86_64/Python 3.12 wheels with verified retryable downloads."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile


with tempfile.TemporaryDirectory() as directory:
    wheels = Path(directory)
    for asset in json.loads(Path(__file__).with_name("wheels.json").read_text()):
        destination = wheels / asset["filename"]
        for attempt in range(5):
            result = subprocess.run([
                "wget", "--quiet", "--timeout=30", "--tries=3", "--limit-rate=2m",
                "-O", str(destination), asset["url"],
            ])
            if result.returncode == 0 and hashlib.sha256(destination.read_bytes()).hexdigest() == asset["sha256"]:
                break
        else:
            raise RuntimeError(f"Could not obtain verified wheel: {asset['filename']}")
    subprocess.run([
        sys.executable, "-m", "pip", "install", "--no-cache-dir", "--no-index",
        "--find-links", directory, "playwright==1.63.0",
    ], check=True)
