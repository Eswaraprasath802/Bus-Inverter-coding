#!/usr/bin/env bash
# Encoder-only matrix. No combined comparison-harness area is used.
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.."
: "${LIBRARY:?Set LIBRARY to a characterized Liberty file}"
: "${OUTPUT_LOAD:?Set OUTPUT_LOAD in library capacitance units}"
command -v genus >/dev/null
export LIBRARY OUTPUT_LOAD
for design in normal_bus bus_invert; do
    DESIGN="$design" SEG_WIDTH=16 genus -batch -files scripts/genus_synth.tcl
done
for width in 8 4 2; do
    DESIGN=segmented_bus_invert_encoder SEG_WIDTH="$width" genus -batch -files scripts/genus_synth.tcl
done
