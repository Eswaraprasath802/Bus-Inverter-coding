# Replacement presentation

Original deck unavailable; this standalone version reflects the implemented segmented-BI method.

## Slide 1: Segmented bus-invert

16-bit bus; five architectures; nine measured workloads. Encoder-only Nangate45 typical reference estimates.

## Slide 2: The problem we built for

Reduce transmitted data switching using independent segment inversion. Recover every accepted word exactly. Flags are measured but are not part of the implemented decision cost.

## Slide 3: Five architectures, one input trace

| Architecture | Segment bits | Flag wires | Total wires |
|---|---|---|---|
| Normal | — | 0 | 16 |
| Global BI | 16 | 1 | 17 |
| 2×8 segmented | 8 | 2 | 18 |
| 4×4 segmented | 4 | 4 | 20 |
| 8×2 segmented | 2 | 8 | 24 |

## Slide 4: Data savings do not set the total ranking

| Architecture | Data | Flags | Total | Total reduction % |
|---|---|---|---|---|
| Normal | 8110 | 0 | 8110 | 0.00 |
| Global BI | 6604 | 473 | 7077 | 12.74 |
| 2×8 BI | 6006 | 925 | 6931 | 14.54 |
| 4×4 BI | 5196 | 1721 | 6917 | 14.71 |
| 8×2 BI | 4144 | 3037 | 7181 | 11.45 |

8×2 minimizes data; 4×4 minimizes total on this seed. Four-seed results split 2:2 between 4×4 and 2×8.

## Slide 5: One independent decision per segment

XOR input with previous encoded data → population count → invert only above half-width → register data and flag. Ties choose no inversion. Decoder XORs each segment with its flag.

## Slide 6: The workload changes the winner

| Workload | Normal | Global | 2×8 | 4×4 | 8×2 | Fewest total transitions |
|---|---|---|---|---|---|---|
| zero_activity | 0 | 0 | 0 | 0 | 0 | Normal, Global BI, 2×8 BI, 4×4 BI, 8×2 BI |
| localized | 376 | 376 | 376 | 167 | 242 | 4×4 BI |
| single_bit_walk | 16 | 16 | 16 | 16 | 24 | Normal, Global BI, 2×8 BI, 4×4 BI |
| random_seed_12345678 | 8110 | 7077 | 6931 | 6917 | 7181 | 4×4 BI |
| random_seed_deadbeef | 8215 | 7083 | 6995 | 6910 | 7218 | 4×4 BI |
| random_seed_cafebabe | 8176 | 7090 | 6911 | 6935 | 7139 | 2×8 BI |
| random_seed_31415926 | 8242 | 7097 | 6912 | 6920 | 7203 | 2×8 BI |
| correlated | 700 | 618 | 625 | 626 | 667 | Global BI |
| bursty | 1344 | 1307 | 1292 | 1136 | 1204 | 4×4 BI |

All RTL assertions and 45 mapped replays pass.

## Slide 7: Measured mapped implementation

| Architecture | Cell area (µm²) | Cells | Max cell path (ns) | Setup slack (ns) |
|---|---|---|---|---|
| Normal | 0.000 | 0 | 0.000000 | 7.900000 |
| Global BI | 210.406 | 124 | 0.968453 | 8.028260 |
| 2×8 BI | 232.218 | 149 | 0.652774 | 8.339456 |
| 4×4 BI | 188.594 | 99 | 0.428559 | 8.548114 |
| 8×2 BI | 212.800 | 107 | 0.327092 | 8.676367 |

Unplaced encoder-only reference; 10 ns clock and 20 fF per output.

## Slide 8: Activity-based power, separated by source

| Architecture | Cell net switching (µW) | Internal (µW) | Leakage (µW) | Cell total (µW) | Output load (µW) |
|---|---|---|---|---|---|
| Normal | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 9.5831 |
| Global BI | 14.9327 | 33.6177 | 4.4818 | 53.0322 | 8.3625 |
| 2×8 BI | 18.3814 | 34.4811 | 4.9688 | 57.8313 | 8.1900 |
| 4×4 BI | 7.0824 | 26.7334 | 3.8553 | 37.6711 | 8.1734 |
| 8×2 BI | 4.0217 | 26.9454 | 4.1792 | 35.1463 | 8.4854 |

Switching excludes the separately shown output load; internal power retains loaded output conditions. No full-link power claim.

## Slide 9: A precise comparison boundary

encoder cells including coded output/state registers; decoder, upstream driver, clock tree and routing excluded; output-load term reported separately. Normal is a direct connection, so it is not a registered full-link baseline.

## Slide 10: What is complete; what comes next

Completed: RTL, expanded traffic, five mappings, timing and power components. Next: real traffic, equivalent full-link endpoints, target technology, physical implementation.

## Slide 11: Choose from the measured conditions

Segment width depends on workload and implementation conditions. Count data and flags, account for cell overhead, and preserve the comparison boundary.
