#!/usr/bin/env python3
"""Build the Android app's FTS5 places database from an OSM PBF extract."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import osmium


class PlacesHandler(osmium.SimpleHandler):
    def __init__(self, database: sqlite3.Connection) -> None:
        super().__init__()
        self.cursor = database.cursor()
        self.count = 0

    def _insert(self, tags: object, latitude: float, longitude: float) -> None:
        name = tags.get("name") or tags.get("name:pt") or tags.get("official_name")
        if not name or not name.strip():
            return
        feature = next((f"{key.replace('_', ' ')} {value.replace('_', ' ')}"
                        for key, value in tags
                        if key in {"amenity", "shop", "tourism", "leisure", "public_transport", "railway", "highway", "place"}
                        and value not in {"yes", "no"}), "local")
        street = tags.get("addr:street")
        number = tags.get("addr:housenumber")
        locality = tags.get("addr:city") or tags.get("addr:place")
        address = " ".join(item for item in (street, number, locality) if item)
        label = " · ".join(item for item in (address, feature) if item)
        self.cursor.execute("INSERT INTO places(name,label,lat,lon) VALUES(?,?,?,?)",
                            (name.strip(), label or feature, latitude, longitude))
        self.count += 1

    def node(self, node: osmium.osm.Node) -> None:
        if node.location.valid():
            self._insert(node.tags, node.location.lat, node.location.lon)

    def way(self, way: osmium.osm.Way) -> None:
        locations = [node.location for node in way.nodes if node.location.valid()]
        if locations:
            self._insert(way.tags,
                         sum(point.lat for point in locations) / len(locations),
                         sum(point.lon for point in locations) / len(locations))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)
    database = sqlite3.connect(args.output)
    try:
        database.execute("PRAGMA journal_mode=OFF")
        database.execute("PRAGMA synchronous=OFF")
        database.execute("CREATE VIRTUAL TABLE places USING fts5(name, label, lat UNINDEXED, lon UNINDEXED, tokenize='unicode61 remove_diacritics 2')")
        handler = PlacesHandler(database)
        handler.apply_file(str(args.input), locations=True)
        database.commit()
        if handler.count == 0:
            raise RuntimeError("OSM extract produced no named places.")
        result = database.execute("SELECT name FROM places WHERE places MATCH ? LIMIT 1", ('"lisboa"*',)).fetchone()
        if result is None:
            result = database.execute("SELECT name FROM places WHERE places MATCH ? LIMIT 1", ('"porto"*',)).fetchone()
        if result is None:
            raise RuntimeError("Generated FTS5 index cannot find Lisboa or Porto.")
        print(f"Indexed {handler.count:,} places; search found {result[0]}.")
    finally:
        database.close()


if __name__ == "__main__":
    main()
