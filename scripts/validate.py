#!/usr/bin/env python3
"""Validate the package layout and the SQLite, MBTiles and Valhalla contracts."""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import tarfile
import tempfile
import zipfile
from pathlib import Path

EXPECTED = {"manifest.json", "portugal-valhalla.tar", "portugal-places.sqlite", "portugal-map.mbtiles"}
LAYERS = {"transportation", "water", "building", "landuse", "landcover", "boundary"}


def validate(package: Path) -> None:
    with zipfile.ZipFile(package) as archive:
        names = set(archive.namelist())
        if names != EXPECTED:
            raise SystemExit(f"Unexpected ZIP contents. Missing: {EXPECTED - names}; extra: {names - EXPECTED}")
        manifest = json.loads(archive.read("manifest.json"))
        if not manifest.get("version") or manifest.get("license") != "ODbL-1.0" or "OpenStreetMap contributors" not in manifest.get("attribution", ""):
            raise SystemExit("Manifest version, ODbL license or OSM attribution is missing.")
        with tempfile.TemporaryDirectory(prefix="rotabus-offline-") as temporary:
            root = Path(temporary)
            for name in EXPECTED - {"manifest.json"}:
                data = archive.read(name)
                entry = manifest.get("files", {}).get(name, {})
                if not data or entry.get("size") != len(data) or entry.get("sha256") != hashlib.sha256(data).hexdigest():
                    raise SystemExit(f"Manifest size/hash mismatch or empty file: {name}")
                (root / name).write_bytes(data)
            places = sqlite3.connect(f"file:{root / 'portugal-places.sqlite'}?mode=ro", uri=True)
            try:
                schema = places.execute("SELECT sql FROM sqlite_master WHERE name='places'").fetchone()
                columns = [row[1] for row in places.execute("PRAGMA table_info(places)")]
                count = places.execute("SELECT count(*) FROM places").fetchone()[0]
                if not schema or "VIRTUAL TABLE" not in schema[0].upper() or "FTS5" not in schema[0].upper() or columns != ["name", "label", "lat", "lon"] or count == 0:
                    raise SystemExit("Places DB must be a populated FTS5 table with name,label,lat,lon columns.")
                for query in ('"lisboa"*', '"porto"*'):
                    if places.execute("SELECT 1 FROM places WHERE places MATCH ? LIMIT 1", (query,)).fetchone() is None:
                        raise SystemExit(f"Places FTS5 query returned no result: {query}")
                print(f"Places FTS5: {count:,} records; Lisboa and Porto queries passed.")
            finally:
                places.close()
            maps = sqlite3.connect(f"file:{root / 'portugal-map.mbtiles'}?mode=ro", uri=True)
            try:
                tables = {row[0] for row in maps.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"metadata", "tiles"}.issubset(tables) or maps.execute("SELECT count(*) FROM tiles").fetchone()[0] == 0:
                    raise SystemExit("Map MBTiles lacks metadata or vector tiles.")
                metadata = dict(maps.execute("SELECT name,value FROM metadata"))
                layers = {layer.get("id") for layer in json.loads(metadata.get("json", "{}")).get("vector_layers", [])}
                if missing := LAYERS - layers:
                    raise SystemExit(f"Map is missing app style layers: {sorted(missing)}")
                print(f"Vector MBTiles: app style layers present ({', '.join(sorted(LAYERS))}).")
            finally:
                maps.close()
            with tarfile.open(root / "portugal-valhalla.tar", "r:*") as graph:
                entries = [item.name for item in graph if item.isfile()]
                if not any(Path(name).name == "index.bin" for name in entries) or not any(name.endswith(".gph") for name in entries):
                    raise SystemExit("Valhalla tar must contain index.bin and graph tile files.")
                print(f"Valhalla tiles: {len(entries):,} files; index and graph tiles present.")
    print(f"Validated {package} ({package.stat().st_size:,} bytes).")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("package", type=Path)
    parser.add_argument("--valhalla-image", help="Reserved for optional routing smoke tests.")
    args = parser.parse_args()
    if not args.package.is_file():
        raise SystemExit(f"Package not found: {args.package}")
    validate(args.package)


if __name__ == "__main__":
    main()
