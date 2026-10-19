#!/bin/sh
# WireGuardKit 1.0.15-26's C header uses u_int32_t and friends without including <sys/types.h>,
# which Xcode 16's explicit module builds reject ("must be imported from module ... before it is
# required"). Adds the include to the resolved package checkout; running it twice changes nothing.
set -eu
header="${1:-build/DerivedData}/SourcePackages/checkouts/wireguard-apple/Sources/WireGuardKitC/WireGuardKitC.h"
[ -f "$header" ] || { echo "error: $header not found; resolve the Swift packages first" >&2; exit 1; }
grep -q '<sys/types.h>' "$header" || { printf '#include <sys/types.h>\n' | cat - "$header" > "$header.new" && mv "$header.new" "$header"; }
echo "patched $header"
