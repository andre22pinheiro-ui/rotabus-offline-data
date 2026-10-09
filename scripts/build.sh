#!/usr/bin/env bash
# Builds rotabus-portugal-offline.zip for mainland Portugal from the Geofabrik
# OpenStreetMap extract. Requires: docker, osmium-tool, python3 (with the
# packages in requirements.txt), zip, jq, curl, git, md5sum, sha256sum.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WORK="${WORK_DIR:-$ROOT/work}"
OUT="${OUT_DIR:-$ROOT/dist}"
GEOFABRIK_URL="${GEOFABRIK_URL:-https://download.geofabrik.de/europe/portugal-latest.osm.pbf}"
# Mainland Portugal only (excludes the Azores and Madeira).
MAINLAND_BBOX="${MAINLAND_BBOX:--9.60,36.80,-6.10,42.20}"
VALHALLA_IMAGE="${VALHALLA_IMAGE:-ghcr.io/valhalla/valhalla:3.6.3}"
TILEMAKER_REPO="${TILEMAKER_REPO:-https://github.com/systemed/tilemaker.git}"
TILEMAKER_REF="${TILEMAKER_REF:-v3.2.0}"
TILEMAKER_IMAGE="rotabus/tilemaker:${TILEMAKER_REF}"
PACKAGE_NAME="rotabus-portugal-offline.zip"
UIDGID="$(id -u):$(id -g)"

log() { printf '\n==> %s\n' "$*" >&2; }

rm -rf "$WORK/package" "$WORK/valhalla" "$OUT"
mkdir -p "$WORK/package" "$WORK/valhalla" "$WORK/tilemaker" "$OUT"
cd "$WORK"

log "Downloading Geofabrik Portugal extract"
curl -fsSL --retry 5 -o portugal-latest.osm.pbf.md5 "${GEOFABRIK_URL}.md5"
curl -fSL --retry 5 --retry-all-errors -o portugal-latest.osm.pbf "$GEOFABRIK_URL"
md5sum -c portugal-latest.osm.pbf.md5
OSM_TIMESTAMP="$(osmium fileinfo -g header.option.osmosis_replication_timestamp portugal-latest.osm.pbf || true)"
[ -n "$OSM_TIMESTAMP" ] || OSM_TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "OSM data timestamp: $OSM_TIMESTAMP"

log "Clipping to mainland Portugal ($MAINLAND_BBOX)"
osmium extract --bbox="$MAINLAND_BBOX" --strategy smart --set-bounds \
  --overwrite -o mainland.osm.pbf portugal-latest.osm.pbf
osmium fileinfo mainland.osm.pbf

log "Building Valhalla routing tiles with $VALHALLA_IMAGE"
docker pull "$VALHALLA_IMAGE"
docker run --rm --user "$UIDGID" -e HOME=/tmp -v "$WORK:/data" --entrypoint /bin/bash "$VALHALLA_IMAGE" -euo pipefail -c '
  cd /data/valhalla
  valhalla_build_config \
    --mjolnir-tile-dir /data/valhalla/tiles \
    --mjolnir-tile-extract /data/valhalla/portugal-valhalla.tar \
    --mjolnir-admin /data/valhalla/admins.sqlite \
    --mjolnir-timezone /data/valhalla/timezones.sqlite \
    --mjolnir-concurrency "$(nproc)" > valhalla.json
  valhalla_build_timezones > timezones.sqlite || { echo "WARNING: timezone database unavailable" >&2; rm -f timezones.sqlite; }
  valhalla_build_admins -c valhalla.json /data/mainland.osm.pbf
  valhalla_build_tiles -c valhalla.json /data/mainland.osm.pbf
  valhalla_build_extract -c valhalla.json -v
'
mv "$WORK/valhalla/portugal-valhalla.tar" "$WORK/package/portugal-valhalla.tar"
VALHALLA_DIGEST="$(docker image inspect --format '{{index .RepoDigests 0}}' "$VALHALLA_IMAGE")"

log "Building tilemaker $TILEMAKER_REF"
docker build -t "$TILEMAKER_IMAGE" "${TILEMAKER_REPO}#${TILEMAKER_REF}"
TILEMAKER_COMMIT="$(git ls-remote "$TILEMAKER_REPO" "refs/tags/${TILEMAKER_REF}^{}" "refs/tags/${TILEMAKER_REF}" | head -n1 | cut -f1)"

log "Downloading coastline and Natural Earth shapefiles used by the OpenMapTiles profile"
cd "$WORK/tilemaker"
mkdir -p coastline landcover
[ -f coastline/water-polygons-split-4326.zip ] || \
  curl -fSL --retry 5 -o coastline/water-polygons-split-4326.zip https://osmdata.openstreetmap.de/download/water-polygons-split-4326.zip
unzip -o -q -j coastline/water-polygons-split-4326.zip -d coastline
for layer in physical/ne_10m_antarctic_ice_shelves_polys cultural/ne_10m_urban_areas physical/ne_10m_glaciated_areas; do
  name="$(basename "$layer")"
  [ -f "landcover/$name.zip" ] || \
    curl -fSL --retry 5 -o "landcover/$name.zip" "https://naciscdn.org/naturalearth/10m/$layer.zip"
  mkdir -p "landcover/$name"
  unzip -o -q "landcover/$name.zip" -d "landcover/$name"
done

docker run --rm --entrypoint cat "$TILEMAKER_IMAGE" /usr/src/app/resources/config-openmaptiles.json > config-openmaptiles.upstream.json
docker run --rm --entrypoint cat "$TILEMAKER_IMAGE" /usr/src/app/resources/process-openmaptiles.lua > process-openmaptiles.lua
jq --arg attr '<a href="https://www.openstreetmap.org/copyright">© OpenStreetMap contributors</a> (ODbL)' '
  .settings.name = "RotaBus Portugal Continental"
  | .settings.description = "OpenMapTiles-schema vector tiles for mainland Portugal built with tilemaker"
  | .settings.filemetadata.attribution = $attr
  | .settings.filemetadata.license = "ODbL-1.0"
' config-openmaptiles.upstream.json > config-openmaptiles.json
ln -f "$WORK/mainland.osm.pbf" mainland.osm.pbf

log "Building OpenMapTiles-schema vector MBTiles"
rm -f portugal-map.mbtiles
docker run --rm --user "$UIDGID" -v "$WORK/tilemaker:/data" -w /data --entrypoint /usr/src/app/tilemaker "$TILEMAKER_IMAGE" \
  --input /data/mainland.osm.pbf \
  --output /data/portugal-map.mbtiles \
  --config /data/config-openmaptiles.json \
  --process /data/process-openmaptiles.lua \
  --bbox="$MAINLAND_BBOX"
mv portugal-map.mbtiles "$WORK/package/portugal-map.mbtiles"
cd "$WORK"

log "Building FTS5 places database"
python3 "$ROOT/scripts/build_places.py" mainland.osm.pbf "$WORK/package/portugal-places.sqlite"

log "Writing manifest.json"
python3 "$ROOT/scripts/write_manifest.py" "$WORK/package" \
  --osm-timestamp "$OSM_TIMESTAMP" \
  --source-url "$GEOFABRIK_URL" \
  --source-md5 "$(cut -d' ' -f1 portugal-latest.osm.pbf.md5)" \
  --bbox="$MAINLAND_BBOX" \
  --valhalla-image "$VALHALLA_DIGEST" \
  --tilemaker "${TILEMAKER_REPO}@${TILEMAKER_REF} (${TILEMAKER_COMMIT})" \
  --osmium "$(osmium --version | head -n1)"

log "Creating $PACKAGE_NAME"
(cd "$WORK/package" && zip -X -9 "$OUT/$PACKAGE_NAME" manifest.json portugal-valhalla.tar portugal-places.sqlite portugal-map.mbtiles)
(cd "$OUT" && sha256sum "$PACKAGE_NAME" > "$PACKAGE_NAME.sha256")
cp "$WORK/package/manifest.json" "$OUT/manifest.json"
ls -l "$OUT"
cat "$OUT/$PACKAGE_NAME.sha256"
