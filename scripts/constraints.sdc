# Example timing budget: replace these numbers using your interface requirements.
# Time and capacitance units are those of the loaded library.
if {$DESIGN eq "normal_bus" || $DESIGN eq "segmented_bus_invert_decoder"} {
    create_clock -name bus_clk -period 10.0
    set timed_inputs [all_inputs]
} else {
    create_clock -name bus_clk -period 10.0 [get_ports clk]
    set timed_inputs [remove_from_collection [all_inputs] [get_ports clk]]
}
# Synchronous reset is timed as an input; it is not a false path.
set_input_delay -max 1.0 -clock bus_clk $timed_inputs
set_input_delay -min 0.0 -clock bus_clk $timed_inputs
set_input_transition 0.1 $timed_inputs
set_output_delay -max 1.0 -clock bus_clk [all_outputs]
set_output_delay -min 0.0 -clock bus_clk [all_outputs]
set_clock_uncertainty 0.1 [get_clocks bus_clk]
set_load $OUTPUT_LOAD [all_outputs]
