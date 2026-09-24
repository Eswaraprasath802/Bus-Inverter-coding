#!/usr/bin/env python3
"""Snapshot a successful reference run and refresh the report and local deck."""
import csv
from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "build/measurements"
SNAPSHOT = ROOT / "measurements/nangate45_typical"
NAMES = {"normal": "Normal", "global": "Global BI", "seg8": "2×8 BI", "seg4": "4×4 BI", "seg2": "8×2 BI"}
SLOTS = {"normal": "normal", "global": "slot0", "seg8": "slot2", "seg4": "slot3", "seg2": "slot4"}
MAIN = "random_seed_12345678"
REFERENCE_LIBRARY_SHA256 = "8d540a4d4cf6d09d27c87ad067857a9c0c2eeb023ab7a56e058cd3113db4e9b1"


def rows(path):
    with path.open() as handle:
        return list(csv.DictReader(handle))


def md_table(headers, data):
    return "\n".join(["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"] +
                     ["| " + " | ".join(map(str, row)) + " |" for row in data])


def html_table(headers, data):
    return "<table><thead><tr>" + "".join(f"<th>{escape(str(x))}</th>" for x in headers) + "</tr></thead><tbody>" + \
        "".join("<tr>" + "".join(f"<td>{escape(str(x))}</td>" for x in row) + "</tr>" for row in data) + "</tbody></table>"


def validate_run(synthesis, power, transitions, manifest, traces):
    if manifest.get("status") != "complete":
        raise SystemExit("Incomplete run: run make measure before publishing")
    if manifest.get("library_sha256") != REFERENCE_LIBRARY_SHA256:
        raise SystemExit("This publisher requires the pinned Nangate45 typical library")
    versions = manifest.get("tool_versions", {})
    if versions.get("yosys") != "Yosys 0.33 (git sha1 2584903a060)" or versions.get("sta") != "3.1.0":
        raise SystemExit("This publisher requires the documented reference tool versions")
    for field in ("source_sha256", "artifact_sha256"):
        if not manifest.get(field):
            raise SystemExit(f"Missing {field}: rerun make measure")
        for name, expected in manifest[field].items():
            path = ROOT / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
                raise SystemExit(f"Changed or missing run input/output: {name}; rerun make measure")
    keys = {(r["Workload"], r["Architecture"]) for r in power}
    expected_keys = {(workload, arch) for workload in traces for arch in NAMES}
    if (len(synthesis) != len(NAMES) or {r["Architecture"] for r in synthesis} != set(NAMES) or
            len(traces) != 9 or MAIN not in traces or keys != expected_keys or len(power) != len(keys)):
        raise SystemExit("Incomplete architecture/workload matrix: refusing to publish")
    trans = {(r["Workload"], r["Architecture"]): r for r in transitions}
    if len(trans) != len(transitions):
        raise SystemExit("Duplicate transition rows: refusing to publish")
    for row in power:
        workload, arch = row["Workload"], row["Architecture"]
        transition = trans.get((workload, SLOTS[arch]))
        if (transition is None or int(row["Samples"]) != traces[workload]["samples"] or
                int(row["UnannotatedPins"]) != 0):
            raise SystemExit(f"Invalid measurement coverage: {workload}/{arch}")


def main():
    synthesis = rows(SOURCE / "synthesis.csv")
    power = rows(SOURCE / "power.csv")
    transitions = rows(ROOT / "build/results.csv")
    manifest = json.loads((SOURCE / "manifest.json").read_text())
    traces = json.loads((ROOT / "build/traces/manifest.json").read_text())
    validate_run(synthesis, power, transitions, manifest, traces)
    syn = {r["Architecture"]: r for r in synthesis}
    pwr = {(r["Workload"], r["Architecture"]): r for r in power}
    trans = {(r["Workload"], r["Architecture"]): r for r in transitions}
    SNAPSHOT.mkdir(parents=True, exist_ok=True)
    for filename in ("synthesis.csv", "power.csv"):
        shutil.copyfile(SOURCE / filename, SNAPSHOT / filename)
    shutil.copyfile(ROOT / "build/results.csv", SNAPSHOT / "transitions.csv")
    shutil.copyfile(ROOT / "build/traces/manifest.json", SNAPSHOT / "traces.json")
    manifest["recorded_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["source_revisions"] = dict(opensta="6be0b1d7da7c98391f5a7fe2a26b3323d28565cc", nangate_platform="db8b985f89d456db29d39588443a025e7305a0a6")
    (SNAPSHOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with zipfile.ZipFile(SNAPSHOT / "raw_reports.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(SOURCE.rglob("*")):
            if file.is_file() and file.suffix in (".log", ".json", ".tcl", ".ys", ".constr"):
                archive.write(file, file.relative_to(SOURCE))
            elif file.name == "mapped.v":
                archive.write(file, file.relative_to(SOURCE))
        for file in sorted((ROOT / "build/traces").glob("*.hex")):
            archive.write(file, Path("traces") / file.name)
        archive.write(ROOT / "build/simulation.log", "rtl_simulation.log")
        for name in manifest["source_sha256"]:
            archive.write(ROOT / name, Path("sources") / name)

    synth_data, power_data, first_data = [], [], []
    for arch in NAMES:
        s, p, t = syn[arch], pwr[(MAIN, arch)], trans[(MAIN, SLOTS[arch])]
        synth_data.append([NAMES[arch], f"{float(s['AreaUm2']):.3f}", s["CellCount"],
                           f"{float(s['MaxCellPathNs']):.6f}", f"{float(s['SetupSlackNs']):.6f}"])
        power_data.append([NAMES[arch]] + [f"{float(p[k])*1e6:.4f}" for k in
                          ("CellSwitchingW", "InternalW", "LeakageW", "EncoderCellTotalW", "OutputLoadSwitchingW")])
        first_data.append([NAMES[arch], t["DataTransitions"], t["FlagTransitions"], t["TotalTransitions"], t["TotalReductionPct"]])
    traffic_data = []
    for workload in traces:
        totals = {arch:int(trans[(workload, SLOTS[arch])]["TotalTransitions"]) for arch in NAMES}
        winners = ", ".join(NAMES[a] for a, count in totals.items() if count == min(totals.values()))
        traffic_data.append([workload, *totals.values(), winners])
    synth_headers = ["Architecture", "Cell area (µm²)", "Cells", "Max cell path (ns)", "Setup slack (ns)"]
    power_headers = ["Architecture", "Cell net switching (µW)", "Internal (µW)", "Leakage (µW)", "Cell total (µW)", "Output load (µW)"]
    traffic_headers = ["Workload", "Normal", "Global", "2×8", "4×4", "8×2", "Fewest total transitions"]
    section = """## Part 13 — Measured reference results

**These are encoder-only numbers, including the coded encoders' output/state registers; decoder, upstream launch/capture hardware, clock tree and routing are excluded.** The uncoded baseline is the original direct wire: zero mapped cells, zero intrinsic cell delay and zero encoder-cell power. It is not an equivalent registered full link. Output-load switching is shown separately for every architecture.

Yosys 0.33/ABC + OpenSTA 3.1.0; Nangate45 typical, 1.10 V, 25 C; 100 MHz; 20 fF per data/flag output; 0.1 ns input/clock slew and clock uncertainty; 1 ns maximum I/O delays. These are unplaced, zero-wire-parasitic estimates, with no clock tree or SDF. Maximum cell path excludes external input delay and includes clock-to-Q on register paths; clock period is 10 ns. See [the full measurement contract](docs/reference_flow.md).

""" + md_table(synth_headers, synth_data) + """

The following activity-annotated power estimates use the original 1,024-word `random_seed_12345678` workload over 10.24 µs, excluding reset and warm-up. Switching, internal and leakage are reported separately. The 20 fF output-load term is an analytical, both-edge activity estimate; it is subtracted from the coded OpenSTA switching totals before reporting encoder-cell power, and is also shown for the uncoded wire. It is not counted twice. Internal power retains the specified loading. All mapped VCDs have zero unannotated pins.

""" + md_table(power_headers, power_data) + """

Loaded encoder cost and link switching savings are different quantities. This table does not establish a full-link power saving; it omits decoder and equivalent launch/capture/clock hardware. Zero-delay gate activity does not capture physical glitches. The estimates are model results, not measured silicon watts.

""" + md_table(["Architecture", "Data transitions", "Flag transitions", "Total transitions", "Total reduction %"], first_data) + """

Expanded workload results (total data + flag transitions):

""" + md_table(traffic_headers, traffic_data) + """

Across the four random seeds, 4×4 and 2×8 each win twice. Global BI has the fewest total transitions on the correlated workload; 4×4 wins on the bursty and localized workloads. These synthetic traces demonstrate workload dependence, not a universal best segment width. The 8×2 single-bit-walk counterexample still increases total transitions by 50%.

The complete [synthesis CSV](measurements/nangate45_typical/synthesis.csv), [power CSV for all nine workloads](measurements/nangate45_typical/power.csv), [transition CSV](measurements/nangate45_typical/transitions.csv), [conditions and checksums](measurements/nangate45_typical/manifest.json), [trace definitions](measurements/nangate45_typical/traces.json), and [raw reports, mapped netlists, sources and exact traces](measurements/nangate45_typical/raw_reports.zip) are saved in the repository. Live VCDs and per-run logs are under `build/measurements/`. Reproduce with `make measure`; refresh this snapshot/deck with `python3 scripts/publish_reference.py`, or run both steps with `make publish`. The publisher rejects incomplete runs and changed source/report files.

`results_template.csv` remains an optional blank collection form. The populated CSVs above are the evidence for this report. Cadence and post-route results have not been claimed.

"""
    readme = (ROOT / "README.md").read_text()
    readme = re.sub(r"## Part 13 .*?(?=## Part 14)", lambda _: section, readme, flags=re.S)
    readme = readme[:readme.index("## Part 14")] + """## Part 14 — VLSI project presentation

Open [the standalone replacement deck](presentation/index.html) in a browser. Slides 2–4 cover the implemented problem, five-architecture comparison, and data-versus-total tradeoff. Later slides use the measured synthesis, power and expanded-workload results above. Use the arrow keys to navigate; print to PDF in landscape for sharing.

The original deck was not present in the repository and no location was supplied, so this is a replacement deck, not an edit to the unavailable original. It contains no unsupported mentor names or projected results. The [slide text](presentation/slides.md) is available for copying into the original presentation.
"""
    # Keep existing inline source listings aligned with the files they document.
    for file in sorted((ROOT / "rtl").glob("*.v")) + [ROOT / "tb/tb_top.v"]:
        heading = "### " + str(file.relative_to(ROOT))
        pattern = re.escape(heading) + r"\n\n```verilog\n.*?\n```"
        readme = re.sub(pattern, lambda _, f=file, h=heading: h + "\n\n```verilog\n" + f.read_text().rstrip() + "\n```", readme, flags=re.S)
    for file in [ROOT / "scripts/genus_synth.tcl", ROOT / "scripts/constraints.sdc"]:
        marker = str(file.relative_to(ROOT)) + ":"
        readme = re.sub(re.escape(marker) + r"\n\n```tcl\n.*?\n```", lambda _, f=file, m=marker: m + "\n\n```tcl\n" + f.read_text().rstrip() + "\n```", readme, flags=re.S)
    (ROOT / "README.md").write_text(readme)

    slides = []
    def slide(title, subtitle, body, markdown):
        slides.append((title, subtitle, body, markdown))
    slide("Segmented bus-invert", "Implemented · verified · mapped · activity analyzed",
          '<p class="hero">Fewer data transitions.<br><em>Count the flags, too.</em></p><p>16-bit bus · five architectures · nine measured workloads</p><p class="small">Nangate45 typical reference run · encoder-only · September 2026</p>',
          "16-bit bus; five architectures; nine measured workloads. Encoder-only Nangate45 typical reference estimates.")
    slide("The problem we built for", "02 / Problem statement",
          '<div class="grid"><article><h2>Reduce switching</h2><p>Choose each segment’s original data or complement using the previous encoded word.</p></article><article><h2>Preserve the word</h2><p>Transmit one flag per segment. Decode every accepted 16-bit word exactly.</p></article></div><p class="callout">The implemented decision minimizes data-wire transitions. Flag activity is counted in the evaluation.</p>',
          "Reduce transmitted data switching using independent segment inversion. Recover every accepted word exactly. Flags are measured but are not part of the implemented decision cost.")
    architecture = [["Normal", "—", "0", "16"], ["Global BI", "16", "1", "17"], ["2×8 segmented", "8", "2", "18"], ["4×4 segmented", "4", "4", "20"], ["8×2 segmented", "2", "8", "24"]]
    slide("Five architectures, one input trace", "03 / Actual comparison",
          html_table(["Architecture", "Segment bits", "Flag wires", "Total wires"], architecture) + '<p class="small">Same accepted words and initial history. Coded outputs are registered; normal is a direct assignment.</p>',
          md_table(["Architecture", "Segment bits", "Flag wires", "Total wires"], architecture))
    slide("Data savings do not set the total ranking", "04 / Key finding · original random seed",
          html_table(["Architecture", "Data", "Flags", "Total", "Total reduction %"], first_data) + '<p class="callout">8×2 minimizes data transitions; 4×4 minimizes total transitions on this seed.</p><p class="small">Across four random seeds, 4×4 and 2×8 each win twice. No universal winner.</p>',
          md_table(["Architecture", "Data", "Flags", "Total", "Total reduction %"], first_data) + "\n\n8×2 minimizes data; 4×4 minimizes total on this seed. Four-seed results split 2:2 between 4×4 and 2×8.")
    slide("One independent decision per segment", "05 / Implemented method",
          '<div class="flow"><span>Input ⊕ previous encoded data</span><b>→</b><span>Population count d</span><b>→</b><span>Invert if d &gt; width / 2</span><b>→</b><span>Register data + flag</span></div><p class="callout">Decode = encoded segment ⊕ replicated flag</p><p>Ties choose no inversion. The registered encoded output is the next comparison history.</p>',
          "XOR input with previous encoded data → population count → invert only above half-width → register data and flag. Ties choose no inversion. Decoder XORs each segment with its flag.")
    compact_traffic = [r for r in traffic_data if r[0] not in ("zero_activity", "single_bit_walk", "localized")]
    slide("The workload changes the winner", "06 / Expanded verification",
          html_table(["Trace", "Normal", "Global", "2×8", "4×4", "8×2"], [r[:-1] for r in compact_traffic]) + '<p class="small">Four random seeds, correlated holds/updates, and idle/burst traffic: 1,024 words each. Also localized, zero activity and the warm-up edge case.</p><p>RTL assertions pass. All 45 mapped replays match RTL transition totals.</p>',
          md_table(traffic_headers, traffic_data) + "\n\nAll RTL assertions and 45 mapped replays pass.")
    slide("Measured mapped implementation", "07 / Yosys + OpenSTA · typical / 1.10 V / 25 C",
          html_table(synth_headers, synth_data) + '<p class="small">100 MHz budget; 20 fF on each output. Cell paths exclude external I/O delay. No placement, routing or clock tree. Normal has no cells.</p>',
          md_table(synth_headers, synth_data) + "\n\nUnplaced encoder-only reference; 10 ns clock and 20 fF per output.")
    slide("Activity-based power, separated by source", "08 / Original random seed · 10.24 µs",
          html_table(["Architecture", "Switch µW", "Internal µW", "Leak µW", "Cell total µW", "Load µW"], power_data) + '<p class="small">Cell terms: Liberty + zero-delay mapped VCD, with full pin annotation. Load: separate 20 fF capacitive estimate. Reset and warm-up excluded.</p><p class="callout">Reduced wire switching alone does not establish lower full-link power.</p>',
          md_table(power_headers, power_data) + "\n\nSwitching excludes the separately shown output load; internal power retains loaded output conditions. No full-link power claim.")
    slide("A precise comparison boundary", "09 / Encoder-only",
          '<div class="grid"><article><h2>Counted as encoder cells</h2><p>Decision logic, feedback, encoded-data and flag registers, internal net switching, cell internal power and leakage.</p></article><article><h2>Outside that boundary</h2><p>Decoder, upstream launch/capture, clock tree, routed interconnect. Equal output loads are reported separately.</p></article></div><p class="small">The normal bus is a zero-cell direct connection. A full-link experiment needs equivalent endpoint registers and decoder cost.</p>',
          manifest["boundary"] + ". Normal is a direct connection, so it is not a registered full-link baseline.")
    slide("What is complete; what comes next", "10 / Evidence and remaining scope",
          '<div class="grid"><article><h2>Completed</h2><p>Parameterized RTL and decoding checks.<br>Expanded traffic and exact replay.<br>Five mapped designs and timing.<br>Separate power components and source artifacts.</p></article><article><h2>Next experiment</h2><p>Representative application traces.<br>Equivalent full-link endpoints.<br>Licensed target library if required.<br>Placement, routing and extracted activity.</p></article></div>',
          "Completed: RTL, expanded traffic, five mappings, timing and power components. Next: real traffic, equivalent full-link endpoints, target technology, physical implementation.")
    slide("Choose from the measured conditions", "11 / Conclusion",
          '<p class="hero">Segment width is a<br><em>workload-dependent choice.</em></p><p>Count data and flags. Account for encoder cost. Preserve the boundary when comparing watts.</p><p class="small">Evidence: README Part 13; measurements/nangate45_typical; reproducible flow: make measure.</p>',
          "Segment width depends on workload and implementation conditions. Count data and flags, account for cell overhead, and preserve the comparison boundary.")
    deck = ROOT / "presentation"
    deck.mkdir(exist_ok=True)
    (deck / "slides.md").write_text("# Replacement presentation\n\nOriginal deck unavailable; this standalone version reflects the implemented segmented-BI method.\n\n" + "\n\n".join(f"## Slide {i}: {title}\n\n{markdown}" for i, (title, _, _, markdown) in enumerate(slides, 1)) + "\n")
    sections = "\n".join(f'<section class="slide" id="slide-{i}"><header>{escape(subtitle)}</header><h1>{escape(title)}</h1><main>{body}</main><footer>Segmented bus-invert · reference study <span>{i:02d} / {len(slides):02d}</span></footer></section>' for i, (title, subtitle, body, _) in enumerate(slides, 1))
    html = '''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Segmented bus-invert — measured reference study</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#101727;color:#f5f7fa;font:22px/1.45 system-ui,sans-serif}.slide{background:#141f32;width:1280px;min-height:720px;margin:32px auto;padding:42px 56px;position:relative;border-top:5px solid #66ddbf;display:flex;flex-direction:column;page-break-after:always}header{font-size:15px;text-transform:uppercase;letter-spacing:2px;color:#66ddbf}h1{font-size:42px;line-height:1.15;max-width:1120px;margin:22px 0 32px;letter-spacing:-1px}h2{font-size:25px;color:#66ddbf}main{flex:1}p{margin:18px 0}.hero{font-size:62px;font-weight:700;line-height:1.18;margin:38px 0}em{color:#66ddbf;font-style:normal}.small{font-size:17px;color:#bbcadc}.grid{display:grid;grid-template-columns:1fr 1fr;gap:34px}.grid article{padding:10px 25px;background:#1b2b43;border-radius:8px}.callout{border-left:5px solid #f8b365;padding:13px 20px;background:#1d2c43;font-size:24px}table{border-collapse:collapse;width:100%;font-size:20px;font-variant-numeric:tabular-nums}th{text-align:left;color:#66ddbf;background:#1b2b43}th,td{padding:12px 13px;border-bottom:1px solid #34455c}td:not(:first-child){text-align:right}tbody tr:nth-child(even){background:#19273b}footer{font-size:13px;color:#b1bfd2;padding-top:25px;display:flex;justify-content:space-between}.flow{display:flex;align-items:center;gap:15px;margin:35px 0 55px}.flow span{background:#213752;padding:22px 18px;border-radius:8px;flex:1;text-align:center}.flow b{color:#66ddbf}.controls{position:fixed;bottom:8px;right:12px;z-index:2}button{background:#1b2b43;color:white;border:1px solid #66ddbf;padding:10px 16px;margin-left:8px;cursor:pointer}@media(max-width:1300px){.slide{width:96vw;min-height:54vw;padding:3vw}h1{font-size:3.2vw}body{font-size:1.7vw}.hero{font-size:4.8vw}table{font-size:1.55vw}.small{font-size:1.35vw}}@media print{@page{size:13.333in 7.5in;margin:0}body{background:#141f32;-webkit-print-color-adjust:exact;print-color-adjust:exact}.slide{width:13.333in;height:7.5in;min-height:0;margin:0;padding:42px 56px;break-inside:avoid}h1{font-size:42px}body{font-size:22px}.hero{font-size:62px}table{font-size:20px}.small{font-size:17px}.controls{display:none}}
</style>''' + sections + '''<nav class="controls" aria-label="Slide navigation"><button id="previous" aria-label="Previous slide">←</button><button id="next" aria-label="Next slide">→</button></nav><script>
const slides=[...document.querySelectorAll('.slide')];let index=0;function go(delta){index=Math.max(0,Math.min(slides.length-1,index+delta));slides[index].scrollIntoView({behavior:'smooth',block:'start'});history.replaceState(null,'','#slide-'+(index+1))}document.getElementById('previous').onclick=()=>go(-1);document.getElementById('next').onclick=()=>go(1);document.addEventListener('keydown',e=>{if(['ArrowRight','PageDown','ArrowLeft','PageUp','Home','End'].includes(e.key)){e.preventDefault();if(e.key==='Home')index=0;else if(e.key==='End')index=slides.length-1;else index+=['ArrowRight','PageDown'].includes(e.key)?1:-1;go(0)}});const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting)index=slides.indexOf(e.target)}),{threshold:.6});slides.forEach(s=>observer.observe(s));
</script></html>'''
    (deck / "index.html").write_text(html)
    print(f"Published {SNAPSHOT} and {deck}")


if __name__ == "__main__":
    main()
