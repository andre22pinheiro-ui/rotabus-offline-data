# rotabus-offline-data

OpenStreetMap-derived offline routing data for RotaBus navigation.

The [Build Portugal offline package](.github/workflows/build-portugal.yml) workflow
builds `rotabus-portugal-offline.zip` for mainland Portugal (Portugal Continental,
bbox `-9.60,36.80,-6.10,42.20`; Azores and Madeira are excluded). It publishes the ZIP to
the [`portugal-latest`](../../releases/tag/portugal-latest) release, which the RotaBus
Android app downloads and verifies via the GitHub-provided SHA-256 asset digest.

## Package contents

The ZIP contains exactly these files at its root:

| File | Contents | Built with |
| --- | --- | --- |
| `manifest.json` | Version, source extract, tool versions, sizes and SHA-256 of the other files, attribution | `scripts/write_manifest.py` |
| `portugal-valhalla.tar` | Valhalla routing tile extract (`index.bin` + graph tiles) | `ghcr.io/valhalla/valhalla:3.6.3` (matches `valhalla-mobile` 0.6.1) |
| `portugal-places.sqlite` | FTS5 table `places(name, label, lat, lon)` for offline search | pyosmium (`scripts/build_places.py`) |
| `portugal-map.mbtiles` | OpenMapTiles-schema vector tiles, z0–14 | tilemaker v3.2.0 (`config-openmaptiles.json`) |

Source data: [Geofabrik Portugal extract](https://download.geofabrik.de/europe/portugal.html),
clipped to the mainland with `osmium extract --strategy smart`. The coastline and Natural Earth
shapefiles used by the tilemaker OpenMapTiles profile are downloaded during the build.

## Building

The workflow runs on pushes that change the build, weekly, and on manual dispatch. It
builds, validates (ZIP layout, manifest hashes, FTS5 queries used by the app, MBTiles layers,
Valhalla tar contents and a Lisboa → Porto truck route), publishes, and then re-downloads the
release asset to verify its digest and size.

To build locally on Linux with Docker, `osmium-tool`, `zip`, `unzip`, `jq` and Python 3:

```sh
python3 -m pip install -r requirements.txt
bash scripts/build.sh
python3 scripts/validate.py dist/rotabus-portugal-offline.zip --valhalla-image ghcr.io/valhalla/valhalla:3.6.3
```

## Attribution and licence

Map, routing and place data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright),
available under the [Open Database License (ODbL) 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The published package is a derivative database distributed under the ODbL; any public use must
credit "© OpenStreetMap contributors". Natural Earth data is in the public domain; coastline water
polygons are from [osmdata.openstreetmap.de](https://osmdata.openstreetmap.de/) (ODbL).
