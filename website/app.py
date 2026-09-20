"""Two independent data portals, deployed together as one Flask application."""

import json
from pathlib import Path
from flask import Flask, abort, render_template, request, send_from_directory

ROOT = Path(__file__).resolve().parent
CATALOG = json.loads((ROOT / "catalog.json").read_text())
app = Flask(__name__, root_path=str(ROOT), static_folder="public", static_url_path="")


@app.get("/")
def home():
    return render_template("home.html", theme="hub", title="Fieldwork · Data collections")


@app.get("/v1/transport")
def transport():
    period = request.args.get("month", "")
    items = [
        d for d in CATALOG if d["site"] == "transport" and (not period or d["period"] == period)
    ]
    return render_template(
        "transport.html",
        theme="transport",
        title="Metro Data · Trip archive",
        items=items,
        month=period,
    )


@app.get("/v1/climate")
def climate():
    province, station, year = (request.args.get(k, "") for k in ("province", "station", "year"))
    items = [
        d
        for d in CATALOG
        if d["site"] == "climate"
        and (not province or d["province"] == province)
        and (not station or d["station"] == station)
        and (not year or d["period"] == year)
    ]
    return render_template(
        "climate.html",
        theme="climate",
        title="Northstar · Historical climate",
        items=items,
        province=province,
        station=station,
        year=year,
    )


@app.get("/v1/<site>/datasets/<dataset_id>")
def detail(site, dataset_id):
    item = next((d for d in CATALOG if d["id"] == dataset_id and d["site"] == site), None)
    if item is None:
        abort(404)
    return render_template("detail.html", theme=site, title=item["title"], item=item)


@app.get("/downloads/v1/<filename>")
def download(filename):
    if filename not in {d["filename"] for d in CATALOG}:
        abort(404)
    return send_from_directory(
        ROOT / "public/downloads/v1", filename, as_attachment=True, max_age=31536000
    )


@app.errorhandler(404)
def not_found(error):
    return render_template("404.html", theme="hub", title="Page not found"), 404


@app.after_request
def headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    return response
