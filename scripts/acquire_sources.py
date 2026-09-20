"""Bounded acquisition, separate from the data-generation skill.

Download only the five declared official input files; retain existing snapshots.
"""

import hashlib
import json
import subprocess
from pathlib import Path
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
SOURCES = {
    **{
        f"green-2023-{m:02}.parquet": f"https://d37ci6vzurychx.cloudfront.net/trip-data/green_tripdata_2023-{m:02}.parquet"
        for m in range(1, 4)
    },
    **{
        f"{name}-2023.csv": f"https://climate.weather.gc.ca/climate_data/bulk_data_e.html?format=csv&stationID={station}&Year=2023&Month=1&Day=1&timeframe=2&submit=Download+Data"
        for name, station in [("toronto", 51459), ("vancouver", 51442)]
    },
}


def acquire():
    RAW.mkdir(parents=True, exist_ok=True)
    expected_path = ROOT / "docs/source-snapshots.json"
    expected = (
        {i["file"]: i["sha256"] for i in json.loads(expected_path.read_text())["sources"]}
        if expected_path.exists()
        else {}
    )
    for filename, url in SOURCES.items():
        path = RAW / filename
        if not path.exists():
            temp = path.with_suffix(path.suffix + ".part")
            subprocess.run(
                ["wget", "--timeout=30", "--tries=3", "-q", "-O", str(temp), url], check=True
            )
            temp.replace(path)
        if not path.stat().st_size:
            raise ValueError(f"Empty source {filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if filename in expected and digest != expected[filename]:
            raise ValueError(
                f"Upstream snapshot changed: {filename}. Review and create a new release."
            )
        if path.suffix == ".parquet":
            table = pq.read_table(path)
            month = filename[6:13]
            valid = [
                r
                for r in table.to_pylist()
                if r["lpep_pickup_datetime"].strftime("%Y-%m") == month
                and r["lpep_dropoff_datetime"] >= r["lpep_pickup_datetime"]
                and 0 < r["trip_distance"] < 100
                and 0 < r["fare_amount"] < 500
                and r["PULocationID"]
                and r["DOLocationID"]
            ]
            selected = [valid[i * len(valid) // 240] for i in range(240)]
            sample = path.with_name(path.stem + "-sample.parquet")
            new = pa.Table.from_pylist(selected, schema=table.schema)
            if sample.exists():
                if not pq.read_table(sample).equals(new):
                    raise ValueError(f"Sampling drift: {sample.name}")
            else:
                pq.write_table(new, sample)
            print(
                filename,
                table.num_rows,
                "source rows;",
                len(valid),
                "eligible;",
                len(selected),
                "sample rows",
            )
        else:
            print(filename, "snapshot verified")


if __name__ == "__main__":
    acquire()
