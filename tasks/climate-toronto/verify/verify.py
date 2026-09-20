"""Score only the requested files; GUI evidence is reviewed separately in ATIF."""

import hashlib
import json
import os
import stat
from pathlib import Path
from ale_verify import CheckResult, Verification


def check_download(output, item):
    if output.is_symlink() or not output.is_dir():
        return CheckResult(0, "Output directory is missing or is a symbolic link.")
    filename = item["filename"]
    if Path(filename).name != filename:
        raise ValueError("Invalid trusted reference filename")
    try:
        fd = os.open(output / filename, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != item["bytes"]:
                return CheckResult(0, "Missing regular file or incorrect file size.")
            actual = hashlib.sha256(stream.read(item["bytes"] + 1)).hexdigest()
    except OSError:
        return CheckResult(0, "Requested download is missing or unreadable.")
    ok = actual == item["sha256"]
    return CheckResult(
        float(ok),
        "Exact release file received."
        if ok
        else "File content differs from the requested release.",
    )


def main():
    expected = json.loads((Path(__file__).parent / "expected.json").read_text())
    verification = Verification()
    for item in expected:
        verification.check(
            item["id"].replace("-", "_"), check_download(Path("/home/user/output"), item)
        )
    verification.aggregate("overall")
    verification.write()


if __name__ == "__main__":
    main()
