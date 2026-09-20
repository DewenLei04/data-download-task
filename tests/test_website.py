import hashlib
import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("website_app", ROOT / "website/app.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


@pytest.fixture
def client():
    return module.app.test_client()


def test_catalog_and_downloads(client):
    for item in module.CATALOG:
        response = client.get(item["url"])
        assert response.status_code == 200
        assert "attachment" in response.headers["Content-Disposition"]
        assert hashlib.sha256(response.data).hexdigest() == item["sha256"]
        page = client.get(f"/v1/{item['site']}/datasets/{item['id']}")
        assert page.status_code == 200 and item["filename"].encode() in page.data


def test_filters_and_empty_state(client):
    page = client.get("/v1/transport?month=2023-02").text
    assert (
        "February 2023 · Green taxi trips" in page and "January 2023 · Green taxi trips" not in page
    )
    page = client.get("/v1/climate?province=Ontario&station=toronto&year=2023").text
    assert (
        "Toronto International A · 2023" in page and "Vancouver International A · 2023" not in page
    )
    assert (
        "No matching stations" in client.get("/v1/climate?province=Ontario&station=vancouver").text
    )
    assert "No datasets match" in client.get("/v1/transport?month=1999-01").text


@pytest.mark.parametrize(
    "path",
    [
        "/data/raw/toronto-2023.csv",
        "/data/generated/toronto-2023/dirty-manifest.json",
        "/tasks/transport-january/verify/expected.json",
        "/catalog.json",
        "/app.py",
        "/downloads/v1/../../catalog.json",
        "/v1/climate/datasets/green-2023-01",
        "/downloads/v1/missing.csv",
    ],
)
def test_private_and_invalid_paths(client, path):
    assert client.get(path).status_code == 404
