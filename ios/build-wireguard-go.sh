#!/bin/sh
# Builds WireGuardKit's Go half (libwg-go.a) from the Swift package checkout, as wireguard-apple's
# README describes for an External Build target. Xcode runs this with its build settings in the
# environment (BUILD_DIR, PLATFORM_NAME, ARCHS, ...), which the package's Makefile reads.
set -eu
packages="${BUILD_DIR%Build/*}SourcePackages"
go_dir="$packages/checkouts/wireguard-apple/Sources/WireGuardKitGo"
if [ ! -d "$go_dir" ]; then
    echo "error: WireGuardKit's Go sources aren't at $go_dir; resolve the Swift packages first" >&2
    ls "$packages/checkouts" >&2 || true
    exit 1
fi
command -v go >/dev/null || { echo "error: Go isn't installed (WireGuardKit needs it to build)" >&2; exit 1; }
cd "$go_dir"
exec /usr/bin/make "${1:-build}"
