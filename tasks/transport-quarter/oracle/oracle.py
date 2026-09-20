"""Trusted oracle navigates visible pages and downloads through browser links."""

import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
params = json.loads(Path(os.environ["ALE_PARAMS_JSON"]).read_text())
solution = json.loads((root / "solution.json").read_text())
output = Path("/home/user/output")
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, args=["--disable-dev-shm-usage"])
    page = browser.new_page(accept_downloads=True)
    for item in solution:
        page.goto(params["site_url"].rstrip("/") + "/v1/" + item["site"])
        if item["site"] == "transport":
            page.get_by_label("Pickup month").select_option(item["period"])
            page.get_by_role("button", name="Apply filter").click()
            page.get_by_role("link", name="Dataset details").click()
        else:
            page.get_by_label("Province", exact=True).select_option(item["province"])
            page.get_by_label("Station", exact=True).select_option(item["station"])
            page.get_by_label("Year", exact=True).select_option(item["period"])
            page.get_by_role("button", name="Search stations").click()
            page.get_by_role("link", name="View station data").click()
        with page.expect_download() as event:
            page.get_by_role("link", name="Download " + item["format"]).click()
        download = event.value
        if download.suggested_filename != item["filename"]:
            raise RuntimeError("Release filename changed")
        download.save_as(output / download.suggested_filename)
    browser.close()
