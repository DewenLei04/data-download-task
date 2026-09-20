import hashlib
import importlib.util
import json
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


def test_station_name_search_modes(client):
    contains = client.get("/v1/climate?q=ONTO&match=contains").text
    assert "Toronto International A · 2023" in contains
    assert "Vancouver International A · 2023" not in contains
    begins = client.get("/v1/climate?q=onto&match=begins").text
    assert "No matching stations" in begins
    prefix = client.get("/v1/climate?q=VAN&match=begins&year=2023").text
    assert "Vancouver International A · 2023" in prefix
    assert "Toronto International A · 2023" not in prefix


def test_initial_search_then_browse(client):
    initial = client.get("/v1/climate").text
    assert "Station Search Results" not in initial
    browse = client.get("/v1/climate?browse=1").text
    assert "Toronto International A · 2023" in browse
    assert "Vancouver International A · 2023" in browse
    assert (
        "No matching stations" in client.get("/v1/climate?q=Toronto&province=British+Columbia").text
    )


def test_json_download_schema_and_release(client):
    item = next(d for d in module.CATALOG if d["site"] == "corgis")
    response = client.get(item["url"])
    assert response.mimetype == "application/json"
    assert item["filename"] in response.headers["Content-Disposition"]
    rows = json.loads(response.data)
    assert len(rows) == item["rows"] == 348
    assert len({(r["Airport"]["Code"], r["Time"]["Label"]) for r in rows}) == 348
    assert {r["Time"]["Year"] for r in rows} == {2015}
    assert all(list(r) == ["Airport", "Time", "Statistics"] for r in rows)
    assert client.get("/v1/corgis/datasets/toronto-2023").status_code == 404
    assert client.get("/corgis-fields.json").status_code == 404


def test_json_catalog_search_without_javascript(client):
    hit = client.get("/v1/corgis?q=AIRLINES").text
    miss = client.get("/v1/corgis?q=missing").text
    assert '<p id="corgis-empty" hidden>' in hit
    assert '<p id="corgis-empty" >' in miss
    assert (
        'data-search="airlines 2015 airplane airports travel flights delays transportation json" hidden'
        in miss
    )


def test_json_detail_without_cdn_files_in_function(client, monkeypatch):
    read_text = Path.read_text

    def function_read(path, *args, **kwargs):
        if path.is_relative_to(ROOT / "website/public"):
            raise FileNotFoundError("CDN assets are not part of the function filesystem")
        return read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", function_read)
    response = client.get("/v1/corgis/datasets/airlines-2015")
    assert response.status_code == 200
    assert 'aria-label="Download JSON"' in response.text
    assert "2015/01" in response.text
