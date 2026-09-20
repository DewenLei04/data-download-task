"""Exercise reference-style UI downloads and task oracle navigation in Chromium.

This is host-side browser testing, not a headed ALE sandbox or model run.
"""

import argparse
import calendar
import hashlib
import importlib.util
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "website/catalog.json").read_text())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8765")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    out = ROOT / "reports/screenshots"
    out.mkdir(parents=True, exist_ok=True)
    results, oracle_results, errors, external_requests = [], [], [], []
    download_count = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            accept_downloads=True, viewport={"width": 1440, "height": 1080}
        )
        page = context.new_page()
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on(
            "request",
            lambda request: (
                external_requests.append(request.url)
                if not request.url.startswith(base + "/")
                else None
            ),
        )
        page.goto(base)
        page.screenshot(path=str(out / "collections-desktop.png"), full_page=True)
        page.get_by_role("link", name="Transport", exact=True).click()
        assert not page.locator(".year-archive").get_attribute("open")
        page.locator(".year-archive > summary").click()
        for item in [d for d in CATALOG if d["site"] == "transport"]:
            month = calendar.month_name[int(item["period"][-2:])]
            row = page.locator("article.dataset").filter(
                has=page.get_by_role("heading", name=month, exact=True)
            )
            with page.expect_download() as event:
                row.get_by_role("link", name="Download Parquet").click()
            download = event.value
            assert download.suggested_filename == item["filename"]
            assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest() == item["sha256"]
            download_count += 1
            results.append({"id": item["id"], "surface": "year accordion", "passed": True})
        page.screenshot(path=str(out / "transport-desktop.png"), full_page=True)
        page.get_by_role("button", name="Collapse All").click()
        assert not page.locator("article.dataset").first.is_visible()
        page.get_by_role("button", name="Expand All").click()
        assert page.locator("article.dataset").first.is_visible()
        page.get_by_role("link", name="Climate", exact=True).click()
        page.evaluate("document.fonts.ready")
        assert page.evaluate('document.fonts.check("16px Noto Sans")')
        assert page.evaluate('document.fonts.check("38px Lato")')
        page.screenshot(path=str(out / "climate-desktop.png"), full_page=True)
        for item in [d for d in CATALOG if d["site"] == "climate"]:
            panel = page.get_by_role("tabpanel", name="Search by Station Name")
            panel.get_by_label("Name:", exact=True).fill(item["station"])
            panel.get_by_role("button", name="Search", exact=True).click()
            assert page.locator("tr.station").count() == 1
            page.get_by_role("link", name="View station data").click()
            with page.expect_download() as event:
                page.get_by_role("link", name="Download CSV", exact=True).click()
            download = event.value
            assert download.suggested_filename == item["filename"]
            assert hashlib.sha256(Path(download.path()).read_bytes()).hexdigest() == item["sha256"]
            download_count += 1
            results.append(
                {"id": item["id"], "surface": "station-name search and detail", "passed": True}
            )
            page.get_by_role("link", name="Back to station search").click()
        for item in CATALOG:
            page.goto(base + f"/v1/{item['site']}/datasets/{item['id']}")
            with page.expect_download() as event:
                page.get_by_role("link", name="Download " + item["format"], exact=True).click()
            assert (
                hashlib.sha256(Path(event.value.path()).read_bytes()).hexdigest() == item["sha256"]
            )
            download_count += 1
        page.goto(base + "/v1/climate?q=missing-station")
        assert page.get_by_role("heading", name="No matching stations").is_visible()
        page.get_by_role("link", name="Show all stations", exact=True).click()
        assert page.locator("tr.station").count() == 2
        for index, item in enumerate([d for d in CATALOG if d["site"] == "climate"]):
            with page.expect_download() as event:
                page.locator("tr.station").nth(index).get_by_role(
                    "link", name="Download CSV"
                ).click()
            assert (
                hashlib.sha256(Path(event.value.path()).read_bytes()).hexdigest() == item["sha256"]
            )
            download_count += 1
        # Both query methods, header search, menu and keyboard tab selection.
        page.goto(base + "/v1/climate")
        page.get_by_role("tab", name="Search by Station Name").focus()
        page.keyboard.press("ArrowRight")
        province_panel = page.get_by_role("tabpanel", name="Search by Province or Territory")
        assert province_panel.is_visible()
        province_panel.get_by_label("Province or Territory:").select_option("British Columbia")
        province_panel.get_by_role("button", name="Search", exact=True).click()
        assert page.locator("tr.station").count() == 1
        assert "Vancouver" in page.locator("tr.station").inner_text()
        page.get_by_label("Search station data", exact=True).fill("Toronto")
        page.locator(".gc-site-search").get_by_role("button", name="Search", exact=True).click()
        assert "Toronto" in page.locator("tr.station").inner_text()
        page.locator(".gc-menu > summary").click()
        assert page.get_by_role("navigation", name="Collections menu").is_visible()
        page.goto(base)
        page.get_by_role("link", name="CORGIS JSON Datasets", exact=True).click()
        page.screenshot(path=str(out / "corgis-desktop.png"), full_page=True)
        search = page.get_by_role("searchbox", name="Search:", exact=True)
        search.fill("unavailable-dataset")
        assert page.locator("#corgis-empty").is_visible()
        assert not page.get_by_role("link", name="View Airlines", exact=True).is_visible()
        search.fill("AIRLINES")
        page.get_by_role("link", name="View Airlines", exact=True).click()
        assert page.locator(".corgis-table tbody tr").count() == 24
        assert page.locator("h1").first.evaluate("el => getComputedStyle(el).fontSize") == "40px"
        assert page.locator("h1").first.evaluate("el => el.getBoundingClientRect().x") == 15
        page.screenshot(path=str(out / "corgis-airlines-desktop.png"), full_page=True)
        item = next(d for d in CATALOG if d["site"] == "corgis")
        with page.expect_download() as event:
            page.get_by_role("link", name="Download JSON", exact=True).click()
        download = event.value
        content = Path(download.path()).read_bytes()
        assert download.suggested_filename == item["filename"]
        assert hashlib.sha256(content).hexdigest() == item["sha256"]
        rows = json.loads(content)
        assert len(rows) == 348 and list(rows[0]) == ["Airport", "Time", "Statistics"]
        download_count += 1
        results.append(
            {"id": item["id"], "surface": "JSON catalog search and download link", "passed": True}
        )
        # Server-rendered queries remain usable without JavaScript, and clearing a
        # nonmatching query restores the card through the live filter.
        page.goto(base + "/v1/corgis?q=missing")
        page.get_by_role("searchbox", name="Search:", exact=True).fill("")
        assert page.get_by_role("link", name="View Airlines", exact=True).is_visible()
        # Exercise the actual code shipped in each oracle against the live host site.
        # This does not test sandbox setup, headed execution or ALE's phase orchestration.
        with tempfile.TemporaryDirectory() as temporary:
            for task in sorted((ROOT / "tasks").iterdir()):
                spec = importlib.util.spec_from_file_location(
                    "oracle_" + task.name, task / "oracle/oracle.py"
                )
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                output = Path(temporary) / task.name
                for item in json.loads((task / "oracle/solution.json").read_text()):
                    module.download_dataset(page, base, item, output)
                    download_count += 1
                for expected in json.loads((task / "verify/expected.json").read_text()):
                    assert (
                        hashlib.sha256((output / expected["filename"]).read_bytes()).hexdigest()
                        == expected["sha256"]
                    )
                oracle_results.append({"task": task.name, "host_browser_navigation_passed": True})
        page.set_viewport_size({"width": 390, "height": 844})
        for path in [
            "",
            "/v1/transport",
            "/v1/climate",
            "/v1/climate?browse=1",
            "/v1/climate/datasets/toronto-2023",
            "/v1/corgis",
            "/v1/corgis/datasets/airlines-2015",
        ]:
            page.goto(base + path)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), path
        page.goto(base + "/v1/transport")
        page.screenshot(path=str(out / "transport-mobile.png"), full_page=True)
        page.goto(base + "/v1/climate")
        page.screenshot(path=str(out / "climate-mobile.png"), full_page=True)
        page.goto(base + "/v1/corgis")
        page.screenshot(path=str(out / "corgis-mobile.png"), full_page=True)
        page.goto(base + "/v1/corgis/datasets/airlines-2015")
        page.screenshot(path=str(out / "corgis-airlines-mobile.png"), full_page=True)
        assert not errors, errors
        assert not external_requests, external_requests
        browser.close()
    report = {
        "base_url": base,
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "test_kind": "host Chromium GUI; not an ALE sandbox/model run",
        "passed": True,
        "datasets": results,
        "oracle_navigation": oracle_results,
        "download_events": download_count,
        "mobile_width": 390,
        "page_errors": errors,
        "external_requests": external_requests,
    }
    (ROOT / "reports/gui-validation.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
