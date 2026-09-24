#!/usr/bin/env python3
"""Five standalone encoders: Yosys mapping, OpenSTA timing, gate-VCD power.

Defaults are the documented Nangate45 reference experiment, not signoff.
All subprocess arguments are passed without a shell; failures stop the run.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

from generate_traces import generate

ROOT = Path(__file__).resolve().parents[1]
ARCHS = [
    ("normal", "normal_bus", 16, 0, "normal"),
    ("global", "bus_invert", 16, 1, "slot0"),
    ("seg8", "segmented_bus_invert_encoder", 8, 2, "slot2"),
    ("seg4", "segmented_bus_invert_encoder", 4, 4, "slot3"),
    ("seg2", "segmented_bus_invert_encoder", 2, 8, "slot4"),
]


def tool(name, fallback):
    configured = os.environ.get(name.upper())
    if configured:
        return shlex.split(configured)
    found = shutil.which(name)
    if found:
        return [found]
    path = ROOT / fallback
    if not path.exists():
        raise SystemExit(f"Missing {name}: install it or set {name.upper()}.")
    args = [str(path)]
    if name == "iverilog":
        args += ["-B", str(ROOT / "build/tools/root/usr/lib/x86_64-linux-gnu/ivl")]
    return args


def run(args, logfile, cwd=ROOT):
    result = subprocess.run(args, cwd=cwd, text=True, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    logfile.write_text(result.stdout)
    if result.returncode or re.search(r"(?m)^(ERROR:|Error:|TEST FAILED|ERROR )", result.stdout):
        raise RuntimeError(f"Command failed; see {logfile}:\n{result.stdout[-2000:]}")
    return result.stdout


def quote(path):
    # The generated scripts deliberately reject paths needing Tcl/Yosys escaping.
    value = str(path)
    if any(c in value for c in '{}"\n\r$;\\[]'):
        raise ValueError(f"Unsupported script path: {value}")
    return f'"{value}"'


def write_csv(path, rows):
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--library", type=Path, default=ROOT / "build/tools/NangateOpenCellLibrary_typical.lib")
    parser.add_argument("--synthesis-only", action="store_true")
    args = parser.parse_args()
    os.chdir(ROOT)
    lib = args.library.resolve()
    if not lib.is_file():
        parser.error(f"Liberty file not found: {lib}")
    # These constants and the power conversion below apply only to this reference corner.
    library_text = lib.read_text()
    for pattern in (r'time_unit\s*:\s*"1ns"', r'capacitive_load_unit\s*\(1,\s*ff\)',
                    r'nom_voltage\s*:\s*1\.10\s*;'):
        if not re.search(pattern, library_text):
            parser.error("Reference flow requires 1 ns / 1 fF units and 1.10 V; adapt constraints for another corner.")
    yosys = tool("yosys", "build/tools/root/usr/bin/yosys")
    sta = tool("sta", "build/tools/sta-build/sta")
    out = ROOT / "build/measurements"
    out.mkdir(parents=True, exist_ok=True)
    # Invalidate a previous successful run before any artifacts are overwritten.
    manifest_path = out / "manifest.json"
    manifest_path.write_text(json.dumps({"status": "running"}) + "\n")
    sources = sorted((ROOT / "rtl").glob("*.v")) + [
        ROOT / "tb/tb_top.v", ROOT / "tb/tb_mapped.v",
        ROOT / "scripts/generate_traces.py", ROOT / "scripts/measure.py",
    ]
    source_hashes = {str(p.relative_to(ROOT)): sha256(p) for p in sources}
    traces = generate()
    synthesis, power = [], []
    if not args.synthesis_only:
        iverilog = tool("iverilog", "build/tools/root/usr/bin/iverilog")
        vvp = tool("vvp", "build/tools/root/usr/bin/vvp")
        print("Verifying RTL against shared traffic...", flush=True)
        rtl_sim = ROOT / "build/tb_top.vvp"
        run(iverilog + ["-g2001", "-Wall", "-DDUMP_VCD", "-s", "tb_top", "-o", str(rtl_sim)] +
            [str(p) for p in sorted((ROOT / "rtl").glob("*.v"))] + [str(ROOT / "tb/tb_top.v")],
            out / "rtl_compile.log")
        rtl_log = run(vvp + [str(rtl_sim)], ROOT / "build/simulation.log", cwd=ROOT / "build")
        if not re.search(r"(?m)^TEST PASSED$", rtl_log):
            raise RuntimeError("RTL verification did not pass; see build/simulation.log")
        models = out / "cells_sim.v"
        run(yosys + ["-Q", "-T", "-p", f"read_liberty -ignore_miss_func -ignore_miss_dir {quote(lib)}; write_verilog {quote(models)}"], out / "models.log")
        reference = {(r["Workload"], r["Architecture"]): r for r in csv.DictReader((ROOT / "build/results.csv").open())}
    for name, top, sw, nf, slot in ARCHS:
        directory = out / name
        directory.mkdir(exist_ok=True)
        print(f"Mapping and timing {name}...", flush=True)
        (directory / "abc.constr").write_text("set_driving_cell BUF_X1\nset_load 20\n")
        parameters = f"chparam -set DATA_WIDTH 16" + (f" -set SEG_WIDTH {sw}" if name.startswith("seg") else "") + f" {top}"
        script = f'''read_verilog rtl/normal_bus.v rtl/bus_invert.v rtl/popcount.v rtl/transition_counter.v rtl/segmented_bus_invert_encoder.v
{parameters}
synth -top {top} -flatten -noabc
dfflibmap -liberty {quote(lib)}
abc -liberty {quote(lib)} -constr {quote(directory / 'abc.constr')} -D 10000
clean
read_liberty -lib {quote(lib)}
check -assert
tee -o build/measurements/{name}/stat.json stat -json -liberty {quote(lib)}
write_verilog -noattr -noexpr {quote(directory / 'mapped.v')}
write_json {quote(directory / 'mapped.json')}
'''
        (directory / "synth.ys").write_text(script)
        run(yosys + ["-Q", "-T", "-s", str(directory / "synth.ys")], directory / "synthesis.log")
        stats = json.loads((directory / "stat.json").read_text())["modules"]["\\" + top]
        clocks = "create_clock -name bus_clk -period 10\nset inputs [all_inputs]" if nf == 0 else "create_clock -name bus_clk -period 10 [get_ports clk]\nset inputs [get_ports {data_in* reset}]"
        base = f'''read_liberty {quote(lib)}
read_verilog {quote(directory / 'mapped.v')}
link_design {top}
{clocks}
set_input_delay -max 1 -clock bus_clk $inputs
set_input_delay -min 0 -clock bus_clk $inputs
set_input_transition 0.1 $inputs
set_output_delay -max 1 -clock bus_clk [all_outputs]
set_output_delay -min 0 -clock bus_clk [all_outputs]
set_clock_uncertainty 0.1 [get_clocks bus_clk]
set_clock_transition 0.1 [get_clocks bus_clk]
set_load 20 [all_outputs]
'''
        timing = base + f'''
check_setup -verbose
report_checks -path_delay max -group_path_count 5 -digits 6
report_check_types -max_slew -max_capacitance -violators
set max_delay 0.0
foreach path [find_timing_paths -from $inputs -path_delay max -group_path_count 1000] {{
    set endpoint [lindex [get_property $path points] end]
    set delay [expr {{[get_property $endpoint arrival] - 1.0}}]
    set max_delay [expr {{max($max_delay, $delay)}}]
}}
'''
        if nf:
            timing += '''foreach path [find_timing_paths -from [all_registers -clock_pins] -path_delay max -group_path_count 1000] {
    set endpoint [lindex [get_property $path points] end]
    set max_delay [expr {max($max_delay, [get_property $endpoint arrival])}]
}
'''
        timing += '''puts "MAX_CELL_PATH_NS $max_delay"
report_worst_slack -max -digits 6
exit
'''
        (directory / "timing.tcl").write_text(timing)
        timing_log = run(sta + ["-exit", str(directory / "timing.tcl")], directory / "timing.log")
        delay = float(re.search(r"MAX_CELL_PATH_NS (\S+)", timing_log)[1])
        slack = float(re.search(r"worst slack (?:max )?(-?[\d.]+)", timing_log)[1])
        synthesis.append(dict(Architecture=name, Top=top, SegmentWidth=sw, FlagBits=nf,
                              AreaUm2=stats.get("area", 0.0), CellCount=stats["num_cells"],
                              MaxCellPathNs=delay, SetupSlackNs=slack))
        if args.synthesis_only:
            continue
        compile_args = iverilog + ["-g2001", "-s", "tb_mapped", f"-DTOP={top}", f"-DSEG_WIDTH={sw}", f"-DFLAG_BITS={max(1,nf)}"]
        if name == "normal":
            compile_args += ["-DNORMAL"]
        elif name == "global":
            compile_args += ["-DGLOBAL_BI"]
        run(compile_args + ["-o", str(directory / "sim.vvp"), str(models), str(directory / "mapped.v"), "tb/tb_mapped.v"], directory / "compile.log")
        for workload, trace in traces.items():
            vcd = directory / f"{workload}.vcd"
            gate_log = run(vvp + [str(directory / "sim.vvp"), f"+TRACE={ROOT}/build/traces/{workload}.hex", f"+VCD={vcd}", f"+COUNT={trace['samples']}", f"+WARMUP={trace['warmup'] if trace['warmup'] is not None else -1}"], directory / f"{workload}.simulation.log")
            if "TEST PASSED" not in gate_log:
                raise RuntimeError("Gate simulation did not pass")
            counts = re.search(r"COUNTS (\d+) (\d+)", gate_log)
            expected = reference[(workload, slot)]
            if tuple(map(int, counts.groups())) != (int(expected["DataTransitions"]), int(expected["FlagTransitions"])):
                raise RuntimeError(f"Gate/RTL transition mismatch: {name}/{workload}")
            power_script = base + f'''read_vcd -scope tb_mapped/dut {quote(vcd)}
report_activity_annotation -report_unannotated
report_power -digits 9
exit
'''
            (directory / f"{workload}.power.tcl").write_text(power_script)
            log = run(sta + ["-exit", str(directory / f"{workload}.power.tcl")], directory / f"{workload}.power.log")
            annotation = re.search(r"(?m)^unannotated\s+(\d+)", log)
            if not annotation or int(annotation[1]) != 0:
                raise RuntimeError(f"Incomplete VCD annotation: {name}/{workload}")
            values = re.search(r"(?m)^Total\s+([\deE.+-]+)\s+([\deE.+-]+)\s+([\deE.+-]+)\s+([\deE.+-]+)", log)
            if not values:
                raise RuntimeError(f"Missing power totals: {name}/{workload}")
            internal, switching, leakage, total = map(float, values.groups())
            duration = trace["samples"] * 10e-9
            link = 0.5 * int(expected["TotalTransitions"]) / duration * 20e-15 * 1.1**2
            # OpenSTA sums cells. Coded output drivers include set_load; normal has no cell.
            # Separate the equal, explicit output capacitance from encoder cell switching.
            cell_switching = switching - (link if nf else 0)
            if cell_switching < -1e-10:
                raise RuntimeError("Output-load subtraction inconsistent with activity duration")
            power.append(dict(Workload=workload, Architecture=name, Samples=trace["samples"],
                              InternalW=internal, CellSwitchingW=max(0, cell_switching), LeakageW=leakage,
                              EncoderCellTotalW=internal+max(0, cell_switching)+leakage,
                              OutputLoadSwitchingW=link, RawOpenSTATotalW=total,
                              UnannotatedPins=int(annotation[1])))
            print(f"  {workload}: mapped replay PASS", flush=True)
    write_csv(out / "synthesis.csv", synthesis)
    if power:
        write_csv(out / "power.csv", power)
    if any(sha256(ROOT / p) != digest for p, digest in source_hashes.items()):
        raise RuntimeError("Sources changed during measurement; rerun before publishing")
    manifest = dict(status="synthesis_only" if args.synthesis_only else "complete",
                    completed_utc=datetime.now(timezone.utc).isoformat(),
                    boundary="encoder cells including coded output/state registers; decoder, upstream driver, clock tree and routing excluded; output-load term reported separately",
                    library=str(lib), library_sha256=sha256(lib),
                    voltage_v=1.1, temperature_c=25, corner="typical", clock_ns=10,
                    output_load_ff=20, input_slew_ns=0.1, clock_slew_ns=0.1,
                    io_delay_ns=1, clock_uncertainty_ns=0.1,
                    timing="unplaced mapped cells; no wire parasitics; maximum cell path excludes input delay; register paths include clock-to-Q",
                    activity="zero-delay mapped gate VCD; reset and warm-up excluded; same hex samples as RTL",
                    tools=dict(yosys=yosys, sta=sta),
                    tool_versions=dict(yosys=run(yosys + ["-V"], out / "yosys_version.log").strip(),
                                       sta=run(sta + ["-version"], out / "sta_version.log").strip()),
                    source_sha256=source_hashes)
    if not args.synthesis_only:
        artifacts = [p for p in out.rglob("*") if p.is_file() and p != manifest_path and
                     p.suffix in (".csv", ".log", ".json", ".tcl", ".ys", ".constr", ".v")]
        artifacts += list((ROOT / "build/traces").glob("*"))
        artifacts += [ROOT / "build/results.csv", ROOT / "build/simulation.log"]
        manifest["artifact_sha256"] = {str(p.relative_to(ROOT)): sha256(p) for p in sorted(artifacts)}
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Results: {out}")


if __name__ == "__main__":
    main()
