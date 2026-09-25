"""The build must reject corrupted downloads instead of feeding them to pip."""

from pathlib import Path
import runpy
import subprocess

import pytest


def test_installer_rejects_corrupted_wheel(monkeypatch):
    downloads = []

    def fake_run(argv, **kwargs):
        assert argv[0] == "wget", "pip must not run after a checksum mismatch"
        destination = Path(argv[argv.index("-O") + 1])
        destination.write_bytes(b"corrupted wheel")
        downloads.append(destination)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    installer = Path(__file__).resolve().parents[1] / "tooling/task-template/image/install_python.py"
    with pytest.raises(RuntimeError, match="Could not obtain verified wheel"):
        runpy.run_path(str(installer))
    assert len(downloads) == 5
    assert all(not path.exists() for path in downloads)
