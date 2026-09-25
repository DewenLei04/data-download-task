"""Trusted oracle navigates visible pages and downloads through browser links."""

import calendar
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


def download_dataset(page, base_url, item, output):
    page.goto(base_url.rstrip("/") + "/v1/" + item["site"])
    if item["site"] == "transport":
        page.locator(".year-archive > summary").click()
        month = calendar.month_name[int(item["period"][-2:])]
        row = page.locator("article.dataset").filter(
            has=page.get_by_role("heading", name=month, exact=True)
        )
        row.get_by_role("link", name="Dataset details", exact=True).click()
    elif item["site"] == "climate":
        page.get_by_role("tab", name="Search by Province or Territory").click()
        panel = page.get_by_role("tabpanel", name="Search by Province or Territory")
        panel.get_by_label("Province or Territory:", exact=True).select_option(item["province"])
        panel.get_by_label("Year", exact=True).select_option(item["period"])
        panel.get_by_role("button", name="Search", exact=True).click()
        page.get_by_role(
            "link", name="View station data — " + item["station"].title() + " International A"
        ).click()
    elif item["site"] == "corgis":
        page.get_by_role("searchbox", name="Search:", exact=True).fill("airlines")
        page.get_by_role("link", name="View Airlines", exact=True).click()
    else:
        raise ValueError("Unsupported dataset site: " + item["site"])
    with page.expect_download() as event:
        page.get_by_role("link", name="Download " + item["format"], exact=True).click()
    download = event.value
    if download.suggested_filename != item["filename"]:
        raise RuntimeError("Release filename changed")
    output.mkdir(parents=True, exist_ok=True)
    download.save_as(output / download.suggested_filename)


def main():
    root = Path(__file__).resolve().parent
    params = json.loads(Path(os.environ["ALE_PARAMS_JSON"]).read_text())
    solution = json.loads((root / "solution.json").read_text())
    output = Path("/home/user/output")
    with sync_playwright() as p:
        proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        browser = p.chromium.launch(
            headless=False,
            args=["--disable-dev-shm-usage"],
            proxy={"server": proxy} if proxy else None,
        )
        page = browser.new_page(accept_downloads=True)
        for item in solution:
            download_dataset(page, params["site_url"], item, output)
        browser.close()


if __name__ == "__main__":
    main()
