# Reproducing the open reference run

This flow uses Yosys/ABC for technology mapping and standalone OpenSTA for
timing and Liberty/VCD power analysis. It does not perform OpenROAD placement
or routing. The result is an unplaced reference estimate, not a foundry or
post-route result.

## Tools and reference library

- Icarus Verilog 12.0, Ubuntu package `12.0-2build2`.
- Yosys 0.33, git `2584903a060`, and its matching `yosys-abc` package,
  Ubuntu package `0.33-5build2`.
- OpenSTA 3.1.0 source revision
  `6be0b1d7da7c98391f5a7fe2a26b3323d28565cc` from
  [OpenSTA](https://github.com/The-OpenROAD-Project/OpenSTA/tree/6be0b1d7da7c98391f5a7fe2a26b3323d28565cc),
  built with GCC 13.3, Tcl 8.6, Eigen 3.4, SWIG 4.2 and CUDD 3.0.0.
- Nangate45 `NangateOpenCellLibrary_typical.lib`, typical / 1.10 V / 25 C,
  from [the pinned OpenROAD platform](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/db8b985f89d456db29d39588443a025e7305a0a6/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib).
  The library has 1 ns time units and 1 fF capacitance units. Its checksum is
  recorded in the measurement manifest. See the platform's
  [license](https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts/blob/db8b985f89d456db29d39588443a025e7305a0a6/flow/platforms/nangate45/LICENSE).

The local tools downloaded for this run are confined to ignored `build/tools/`.
On another machine, install the versions above or supply `YOSYS`, `STA`,
`IVERILOG`, and `VVP` environment variables. Each accepts an executable plus
arguments. `Makefile` and `measure.py` also discover the workspace-local tools.
To build OpenSTA from the pinned source, its build dependencies are a C++20
compiler, CMake, Flex (including headers), Bison, SWIG, Tcl development headers,
Eigen, zlib and CUDD. Configure with `-DBUILD_TESTS=OFF -DUSE_TCL_READLINE=OFF`
and `-DCUDD_DIR=<CUDD installation>`; then run `cmake --build`.

Put the Liberty file in `build/tools/NangateOpenCellLibrary_typical.lib`, then:

```bash
make test       # creates deterministic traffic; verifies all RTL encoders
make synth      # five separate mapped designs and timing reports
make measure    # RTL check, mapping, timing, 45 mapped replays and power reports
make publish    # full measurement, then refresh repository CSVs, README and deck
```

`python3 scripts/measure.py --library /path/to/library.lib` accepts another
library with the same reference units and voltage. Adapt the script's explicit
constraints and conversions before using a different voltage or unit system.
The checked-in table applies only to the pinned reference library.

The measurement script runs its own RTL verification, so direct invocation also
works from a clean build. The manifest records completion status, tool versions,
and hashes of the measured sources and output reports. After a successful run,
`python3 scripts/publish_reference.py` refreshes the snapshot and presentation
without repeating measurement. It checks those hashes and refuses partial,
synthesis-only, altered, or non-reference results.

## Measurement contract

**These are encoder-only numbers, including the coded encoders' output/state
registers; decoder, upstream launch/capture hardware, clock tree and routing
are excluded.** The uncoded module is a wire assignment with zero cell area
and zero encoder-cell power. It is not a registered full-link baseline.

- One accepted 16-bit word per 10 ns (100 MHz); synchronous reset is timed.
- 1 ns maximum input/output delay, 0 ns minimum I/O delay, 0.1 ns clock
  uncertainty, 0.1 ns input/clock slew. Every data and flag output sees 20 fF.
- Yosys maps flip-flops with `dfflibmap`, logic with `abc`, using a `BUF_X1`
  input driver and 20 fF output load. ABC gets a 10,000 ps delay target.
- Maximum cell path is the largest data path across input/register/output
  endpoints, excluding the external 1 ns input delay and including clock-to-Q
  on register paths. It is distinct from the clock period and setup slack.
- No placement, extracted wire capacitance, clock tree, or SDF is included.
  Setup timing is evaluated; no post-route/hold signoff claim is made.
- Yosys derives zero-delay simulation models from Liberty Boolean/FF functions.
  Missing-function cells are skipped during model generation; the used mapped
  cells must all compile. Each mapped trace checks the exact inversion decision,
  tie behavior and encoded word, and its transition totals must match RTL.
- Every gate VCD starts after reset and any warm-up, one ns before the first
  measured input change, and spans exactly `samples × 10 ns`. The clock runs
  during idle traffic. The directed reset/tie suite remains a functional test;
  it is not included in the power dataset.
- `report_activity_annotation` must report zero unannotated pins. Annotation
  coverage, raw power components and mapped replay logs are saved per workload.
- OpenSTA's cell switching result includes the coded output driver load.
  The separate output-load term is
  `0.5 × total_transitions / duration × 20 fF × (1.1 V)^2`, where transitions
  count both directions. Subtract it from coded switching power to obtain
  encoder-internal net switching; retain it separately for **every** architecture,
  including the uncoded wire. This avoids treating the uncoded link as power-free
  and avoids double-counting the coded output load. Cell internal power still
  reflects the specified output load. The raw OpenSTA totals remain available.
- Power is a Liberty/activity model estimate in watts. Zero-delay gate VCDs
  do not resolve physical glitches; probabilistic Liberty internal/leakage
  calculations are not transistor-level measurements. The small warm-up
  counterexample is useful for transitions, not a steady-state power claim.

The synthetic correlated/bursty traces expand coverage; they are not captures
from a real bus. Seeds, definitions, sample counts and SHA-256 hashes are in
`build/traces/manifest.json`. Four random seeds support a limited comparison,
not a universal optimum or a statistical confidence claim.

The flow follows the documented [Yosys library mapping passes](https://yosyshq.readthedocs.io/projects/yosys/en/0.36/CHAPTER_CellLib.html)
and [OpenSTA VCD power example](https://openroad.readthedocs.io/en/latest/main/src/sta/doc/Examples.html#power-analysis).

## Cadence alternative

```bash
LIBRARY=/path/to/corner.lib OUTPUT_LOAD=20 bash scripts/run_genus.sh
```

Set the load in **your** library's units and edit `scripts/constraints.sdc` for
your interface. The script launches a fresh Genus process per architecture.
It has not been executed here because Cadence is unavailable. Its outputs must
not be mixed with the Nangate45/Yosys snapshot. Use your release's activity and
power commands and verify hierarchy coverage before reporting Cadence watts.
