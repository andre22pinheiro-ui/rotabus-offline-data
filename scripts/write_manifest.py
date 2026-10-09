#!/usr/bin/env python3
"""Write version, source metadata and checksums for an offline package."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

FILES = ("portugal-valhalla.tar", "portugal-places.sqlite", "portugal-map.mbtiles")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--osm-timestamp", required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--source-md5", required=True)
    parser.add_argument("--bbox", required=True)
    parser.add_argument("--valhalla-image", required=True)
    parser.add_argument("--tilemaker", required=True)
    parser.add_argument("--osmium", required=True)
    args = parser.parse_args()
    files = {}
    for filename in FILES:
        path = args.directory / filename
        if not path.is_file() or path.stat().st_size == 0:
            raise SystemExit(f"Required file missing or empty: {filename}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[filename] = {"size": path.stat().st_size, "sha256": digest}
    now = datetime.now(timezone.utc)
    manifest = {
        "version": now.strftime("%Y.%m.%d"),
        "generatedAt": now.isoformat(),
        "region": "Portugal Continental",
        "bbox": args.bbox,
        "source": {"name": "Geofabrik Portugal OpenStreetMap extract", "url": args.source_url,
                   "timestamp": args.osm_timestamp, "md5": args.source_md5},
        "tools": {"valhalla": args.valhalla_image, "tilemaker": args.tilemaker, "osmium": args.osmium},
        "files": files,
        "attribution": "© OpenStreetMap contributors",
        "license": "ODbL-1.0",
        "copyrightUrl": "https://www.openstreetmap.org/copyright",
    }
    (args.directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
