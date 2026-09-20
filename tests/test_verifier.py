"""Use ALE's real verification API, without needing a container/model."""

import importlib.util
import json
import os
import shutil
import sys
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
ALE_VERIFY = ROOT.parent / "ale/packages/ale-verify/src"
if not ALE_VERIFY.is_dir():
    pytest.skip("ALE checkout required for verifier contract tests", allow_module_level=True)
sys.path.insert(0, str(ALE_VERIFY))
spec = importlib.util.spec_from_file_location(
    "task_verifier", ROOT / "tooling/task-template/verify/verify.py"
)
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


@pytest.mark.parametrize("task", sorted((ROOT / "tasks").iterdir()), ids=lambda p: p.name)
def test_correct_empty_and_wrong(task, tmp_path, monkeypatch):
    expected = json.loads((task / "verify/expected.json").read_text())
    output = tmp_path / "output"
    output.mkdir()
    for item in expected:
        assert verify.check_download(output, item).score == 0
        target = output / item["filename"]
        target.write_bytes(b"placeholder")
        assert verify.check_download(output, item).score == 0
        correct = ROOT / "website/public/downloads/v1" / item["filename"]
        shutil.copyfile(correct, target)
        assert verify.check_download(output, item).score == 1
        blob = bytearray(target.read_bytes())
        blob[len(blob) // 2] ^= 1
        target.write_bytes(blob)
        assert verify.check_download(output, item).score == 0
        target.unlink()
        target.symlink_to(correct)
        assert verify.check_download(output, item).score == 0
        target.unlink()
        target.mkdir()
        assert verify.check_download(output, item).score == 0
        target.rmdir()
        os.mkfifo(target)
        assert verify.check_download(output, item).score == 0
        target.unlink()
    # Exercise ALE's actual record and aggregate contract with zero/all-one inputs.
    from ale_verify import Verification

    for present in (False, True):
        record = tmp_path / f"verification-{present}.json"
        verdict = tmp_path / f"rewards-{present}.json"
        monkeypatch.setenv("ALE_VERIFICATION_PATH", str(record))
        monkeypatch.setenv("ALE_VERDICT_PATH", str(verdict))
        v = Verification()
        for item in expected:
            if present:
                shutil.copyfile(
                    ROOT / "website/public/downloads/v1" / item["filename"],
                    output / item["filename"],
                )
            v.check(item["id"].replace("-", "_"), verify.check_download(output, item))
        assert v.aggregate("overall") == float(present)
        v.write()
        assert record.exists() and verdict.exists()


def test_partial_credit_and_output_symlink(tmp_path, monkeypatch):
    monkeypatch.setenv("ALE_VERIFICATION_PATH", str(tmp_path / "record.json"))
    monkeypatch.setenv("ALE_VERDICT_PATH", str(tmp_path / "rewards.json"))
    from ale_verify import Verification

    task = ROOT / "tasks/transport-quarter"
    expected = json.loads((task / "verify/expected.json").read_text())
    output = tmp_path / "output"
    output.mkdir()
    shutil.copyfile(
        ROOT / "website/public/downloads/v1" / expected[0]["filename"],
        output / expected[0]["filename"],
    )
    v = Verification()
    for item in expected:
        v.check(item["id"].replace("-", "_"), verify.check_download(output, item))
    assert v.aggregate("overall") == pytest.approx(1 / 3)
    link = tmp_path / "link"
    link.symlink_to(output, target_is_directory=True)
    assert verify.check_download(link, expected[0]).score == 0
