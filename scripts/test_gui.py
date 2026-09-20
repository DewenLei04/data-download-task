"""Click visible UI links in Chromium and verify downloaded bytes (no model)."""

import hashlib
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "website/catalog.json").read_text())


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    out = ROOT / "reports/screenshots"
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1440, "height": 1080}
        )
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(args.base_url)
        page.screenshot(path=str(out / "collections-desktop.png"), full_page=True)
        page.get_by_role("link", name="Transport", exact=True).click()
        for item in [d for d in CATALOG if d["site"] == "transport"]:
            page.get_by_label("Pickup month").select_option(item["period"])
            page.get_by_role("button", name="Apply filter").click()
            assert page.locator("article.dataset").count() == 1
            with page.expect_download() as event:
                page.get_by_role("link", name="Download Parquet").click()
            download = event.value
            assert download.suggested_filename == item["filename"]
            assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest() == item["sha256"]
            results.append({"id": item["id"], "surface": "archive", "passed": True})
        page.goto(args.base_url + "/v1/transport")
        page.screenshot(path=str(out / "transport-desktop.png"), full_page=True)
        page.get_by_role("link", name="Climate", exact=True).click()
        for item in [d for d in CATALOG if d["site"] == "climate"]:
            page.get_by_label("Province", exact=True).select_option(item["province"])
            page.get_by_label("Station", exact=True).select_option(item["station"])
            page.get_by_label("Year", exact=True).select_option("2023")
            page.get_by_role("button", name="Search stations").click()
            assert page.locator("article.station").count() == 1
            page.get_by_role("link", name="View station data").click()
            with page.expect_download() as event:
                page.get_by_role("link", name="Download CSV").click()
            download = event.value
            assert download.suggested_filename == item["filename"]
            assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest() == item["sha256"]
            results.append({"id": item["id"], "surface": "detail", "passed": True})
            page.get_by_role("link", name="Back to station search").click()
        page.screenshot(path=str(out / "climate-desktop.png"), full_page=True)
        # Exercise every details-page download and station-card download as well.
        for item in CATALOG:
            page.goto(args.base_url + f"/v1/{item['site']}/datasets/{item['id']}")
            with page.expect_download() as event:
                page.get_by_role("link", name="Download " + item["format"], exact=False).click()
            assert (
                hashlib.sha256(Path(event.value.path()).read_bytes()).hexdigest() == item["sha256"]
            )
        page.goto(args.base_url + "/v1/climate?province=Ontario&station=vancouver")
        assert page.get_by_role("heading", name="No matching stations").is_visible()
        page.get_by_role("link", name="Show all stations").click()
        assert page.locator("article.station").count() == 2
        for index, item in enumerate([d for d in CATALOG if d["site"] == "climate"]):
            with page.expect_download() as event:
                page.locator("article.station").nth(index).get_by_role(
                    "link", name="Download CSV"
                ).click()
            assert (
                hashlib.sha256(Path(event.value.path()).read_bytes()).hexdigest() == item["sha256"]
            )
        page.set_viewport_size({"width": 390, "height": 844})
        for site in ["", "/v1/transport", "/v1/climate", "/v1/climate/datasets/toronto-2023"]:
            page.goto(args.base_url + site)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), site
        page.goto(args.base_url + "/v1/transport")
        page.screenshot(path=str(out / "transport-mobile.png"), full_page=True)
        assert not errors, errors
        browser.close()
    report = {
        "test_kind": "scripted Chromium GUI, not an ALE model run",
        "passed": True,
        "datasets": results,
        "download_events": 12,
        "mobile_width": 390,
        "page_errors": errors,
    }
    (ROOT / "reports/gui-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
