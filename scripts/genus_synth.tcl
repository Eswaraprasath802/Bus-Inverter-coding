# Run from the project root using: genus -files scripts/genus_synth.tcl
# Common UI. Use a fresh Genus process for each architecture.
proc setting {name fallback} {
    if {[info exists ::env($name)]} { return $::env($name) }
    return $fallback
}
set DESIGN [setting DESIGN bus_invert]
set DATA_WIDTH [setting DATA_WIDTH 16]
set SEG_WIDTH [setting SEG_WIDTH 4]
set LIBRARY [setting LIBRARY ""]
set OUTPUT_LOAD [setting OUTPUT_LOAD ""]
if {![file isfile $LIBRARY]} {
    error "Set LIBRARY to an existing characterized Liberty .lib file."
}
if {![string is double -strict $OUTPUT_LOAD] || $OUTPUT_LOAD < 0} {
    error "Set OUTPUT_LOAD to a nonnegative per-wire load in library units."
}
if {$DATA_WIDTH <= 0 || $SEG_WIDTH <= 0 || $DATA_WIDTH % $SEG_WIDTH != 0} {
    error "Widths must be positive and DATA_WIDTH divisible by SEG_WIDTH."
}
set tag ${DESIGN}_d${DATA_WIDTH}_s${SEG_WIDTH}
file mkdir reports/$tag netlist/$tag
set_db library [list $LIBRARY]
read_hdl -v2001 {rtl/popcount.v rtl/transition_counter.v rtl/normal_bus.v rtl/bus_invert.v rtl/segmented_bus_invert_encoder.v rtl/segmented_bus_invert_decoder.v rtl/top.v}
if {$DESIGN eq "top" || $DESIGN eq "segmented_bus_invert_encoder" ||
    $DESIGN eq "segmented_bus_invert_decoder"} {
    elaborate $DESIGN -parameters [list $DATA_WIDTH $SEG_WIDTH]
} else {
    elaborate $DESIGN -parameters [list $DATA_WIDTH]
}
check_design -unresolved
read_sdc scripts/constraints.sdc
syn_generic
syn_map
syn_opt
report_area > reports/$tag/area.rpt
report_timing > reports/$tag/timing.rpt
report_gates > reports/$tag/cell_usage.rpt
write_hdl > netlist/$tag/mapped.v
write_sdc > netlist/$tag/mapped.sdc
