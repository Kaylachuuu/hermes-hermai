#!/usr/bin/env bash
# Fetches what "Hey Athena" listening needs and isn't kept in git: the sherpa-onnx Android library
# and its small keyword-spotting model (Apache 2.0, k2-fsa). Each download is checked against a known
# hash. Run once before building; the GitHub build runs it for you.
set -euo pipefail
cd "$(dirname "$0")"

SHERPA=1.13.8
AAR_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/v$SHERPA/sherpa-onnx-$SHERPA.aar"
AAR_SHA=633c24321e06b1fe79feafa03ea16cbc0f8a286641e2da3559bac91bdb13bd96
MODEL=sherpa-onnx-kws-zipformer-gigaspeech-3.3M-2024-01-01
MODEL_URL="https://github.com/k2-fsa/sherpa-onnx/releases/download/kws-models/$MODEL.tar.bz2"
MODEL_SHA=f170013b4716e41b62b9bfd809687c207cef798ef9bc6534d524e17af9b6561a

fetch() {  # url sha256 destination
  if [ -f "$3" ] && echo "$2  $3" | sha256sum -c --status; then return; fi
  curl -sSLf --retry 3 -o "$3.part" "$1"
  echo "$2  $3.part" | sha256sum -c --status || { echo "unexpected download: $1" >&2; rm -f "$3.part"; exit 1; }
  mv "$3.part" "$3"
}

mkdir -p app/libs app/src/main/assets/kws
fetch "$AAR_URL" "$AAR_SHA" "app/libs/sherpa-onnx-$SHERPA.aar"

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
fetch "$MODEL_URL" "$MODEL_SHA" "$tmp/model.tar.bz2"
tar xjf "$tmp/model.tar.bz2" -C "$tmp"
for part in encoder decoder joiner; do
  cp "$tmp/$MODEL/$part-epoch-12-avg-2-chunk-16-left-64.int8.onnx" "app/src/main/assets/kws/$part.onnx"
done
cp "$tmp/$MODEL/tokens.txt" app/src/main/assets/kws/tokens.txt
echo "Wake word files are in place."
