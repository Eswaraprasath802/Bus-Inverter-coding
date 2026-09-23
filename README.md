# Segmented Bus-Invert Coding for Dynamic Power Reduction

Implemented in 391 lines across eight Verilog-2001 files. The synthesizable RTL and simulation-only testbench are separate. Local verification used Icarus Verilog 12.0 with `-g2001 -Wall` and passed without compiler warnings. Xcelium and Genus are not installed here, so the Cadence scripts still require execution in your licensed environment and your own technology library.

## Part 1 — Problem statement

Switching a bus charges and discharges its wire and receiver capacitances. The project reduces data-wire transitions by selecting either each input word or its bitwise complement, while preserving the information needed to reconstruct the original word.

Compare an uncoded bus, whole-bus Bus-Invert, and independently encoded segments. Count flag switching explicitly: fewer data transitions do not necessarily imply fewer total transitions or lower implementation power.

## Part 2 — Proposed solution

The primary configuration uses DATA_WIDTH=16 and SEG_WIDTH=4: four 4-bit segments and four flags, for 20 transmitted wires. Segment 0 is [3:0], segment 1 [7:4], segment 2 [11:8], and segment 3 [15:12].

For each segment, let d be the population count of current_data XOR previous_encoded_data. The normal cost is d and the inverted cost is SEG_WIDTH-d. Invert only when SEG_WIDTH-d < d; ties choose flag=0.

The implementation uses the equivalent comparison d > SEG_WIDTH/2. Integer division also makes this valid for odd positive widths. This decision minimizes data-wire switching for the current stored state; flag switching is measured but is deliberately not included in the decision.

Timing contract: active-high synchronous reset clears encoded outputs and flags on a rising edge. Each following rising edge accepts data_in and registers its encoded data and flags together. The output data registers themselves store the last transmitted encoded word. The combinational decoder recovers that accepted word after the edge. Hold the input stable around the sampling edge.

The normal bus remains the requested combinational assignment with no coding state. The testbench compares all architectures on the same accepted sequence after each rising edge. Its comparison is by transaction, not by identical output-change timestamps.

## Part 3 — Architecture

```text
                         data_in[15:0]
                              |
           +------------------+--------------------+
           |                  |                    |
     Normal assignment   Global encoder      Segment splitter
           |            one 16-bit decision    4 x 4 bits
           |                  |                    |
           |                  |       +------------+------------+
           |                  |       | repeated for segment s  |
           |                  |       |                         |
           |                  |       | current segment         |
           |                  |       |       XOR <-------------+---+
           |                  |       |        |                |   |
           |                  |       |     popcount            |   |
           |                  |       |        |                |   |
           |                  |       | compare d with 4-d      |   |
           |                  |       |        |                |   |
           |                  |       | select normal/inverted  |   |
           |                  |       +------------+------------+   |
           |                  |                    |                |
           |             data/flag regs      data/flag regs --------+
           |                  |              feedback: encoded data
           |                  |                    |
       16 wires           17 wires             20 wires
           |                  |                    |
           |             global decode       segment decoder
           |                  |                    |
           +---------- exact accepted original word+
```

## Part 4 — Directory structure

```text
vlsi/
├── README.md
├── Makefile
├── .gitignore
├── results_template.csv
├── rtl/
│   ├── normal_bus.v
│   ├── bus_invert.v
│   ├── popcount.v
│   ├── transition_counter.v
│   ├── segmented_bus_invert_encoder.v
│   ├── segmented_bus_invert_decoder.v
│   └── top.v
├── tb/
│   └── tb_top.v
├── scripts/
│   ├── xrun_waves.tcl
│   ├── genus_synth.tcl
│   └── constraints.sdc
└── build/                       # Generated local verification artifacts
    ├── tb_top.vvp
    ├── parameters.vvp
    ├── simulation.log
    ├── verification.log
    ├── results.csv
    └── segmented_bus_invert.vcd
```

## Part 5 — Complete Verilog code

### rtl/normal_bus.v

```verilog
`timescale 1ns/1ps
// Zero-overhead, uncoded bus baseline.
module normal_bus #(
    parameter DATA_WIDTH = 16
) (
    input  [DATA_WIDTH-1:0] data_in,
    output [DATA_WIDTH-1:0] encoded_data
);
    assign encoded_data = data_in;
endmodule
```

### rtl/bus_invert.v

```verilog
`timescale 1ns/1ps
// Registered transmission; encoded_data itself holds the previous transmission.
module bus_invert #(
    parameter DATA_WIDTH = 16
) (
    input clk,
    input reset,
    input [DATA_WIDTH-1:0] data_in,
    output reg [DATA_WIDTH-1:0] encoded_data,
    output reg invert_flag
);
    wire [DATA_WIDTH-1:0] transitions;
    wire invert;
    transition_counter #(.WIDTH(DATA_WIDTH)) u_transition (
        .current_data(data_in), .previous_data(encoded_data),
        .transition_count(transitions)
    );
    assign invert = (transitions > DATA_WIDTH / 2);
    always @(posedge clk) begin
        if (reset) begin
            encoded_data <= {DATA_WIDTH{1'b0}};
            invert_flag <= 1'b0;
        end else begin
            encoded_data <= invert ? ~data_in : data_in;
            invert_flag <= invert;
        end
    end
endmodule
```

### rtl/popcount.v

```verilog
`timescale 1ns/1ps
// COUNT_WIDTH must represent WIDTH; the conservative default is always safe.
module popcount #(
    parameter WIDTH = 4,
    parameter COUNT_WIDTH = WIDTH
) (
    input [WIDTH-1:0] data_in,
    output reg [COUNT_WIDTH-1:0] count
);
    integer i;
    always @(*) begin
        count = {COUNT_WIDTH{1'b0}};
        for (i = 0; i < WIDTH; i = i + 1)
            count = count + data_in[i];
    end
endmodule
```

### rtl/transition_counter.v

```verilog
`timescale 1ns/1ps
module transition_counter #(
    parameter WIDTH = 16,
    parameter COUNT_WIDTH = WIDTH
) (
    input [WIDTH-1:0] current_data,
    input [WIDTH-1:0] previous_data,
    output [COUNT_WIDTH-1:0] transition_count
);
    wire [WIDTH-1:0] transition_bits;
    assign transition_bits = current_data ^ previous_data;
    popcount #(.WIDTH(WIDTH), .COUNT_WIDTH(COUNT_WIDTH)) u_count (
        .data_in(transition_bits), .count(transition_count)
    );
endmodule
```

### rtl/segmented_bus_invert_encoder.v

```verilog
`timescale 1ns/1ps
// Require DATA_WIDTH > 0, SEG_WIDTH > 0, DATA_WIDTH % SEG_WIDTH == 0.
module segmented_bus_invert_encoder #(
    parameter DATA_WIDTH = 16,
    parameter SEG_WIDTH = 4
) (
    input clk,
    input reset,
    input [DATA_WIDTH-1:0] data_in,
    output reg [DATA_WIDTH-1:0] encoded_data,
    output reg [(DATA_WIDTH/SEG_WIDTH)-1:0] invert_flags
);
    localparam SEGMENTS = DATA_WIDTH / SEG_WIDTH;
    wire [DATA_WIDTH-1:0] next_data;
    wire [SEGMENTS-1:0] next_flags;
    genvar s;
    generate
        for (s = 0; s < SEGMENTS; s = s + 1) begin : segments
            wire [SEG_WIDTH-1:0] transitions;
            transition_counter #(.WIDTH(SEG_WIDTH)) u_transition (
                .current_data(data_in[s*SEG_WIDTH +: SEG_WIDTH]),
                .previous_data(encoded_data[s*SEG_WIDTH +: SEG_WIDTH]),
                .transition_count(transitions)
            );
            assign next_flags[s] = (transitions > SEG_WIDTH / 2);
            assign next_data[s*SEG_WIDTH +: SEG_WIDTH] = next_flags[s] ?
                ~data_in[s*SEG_WIDTH +: SEG_WIDTH] :
                 data_in[s*SEG_WIDTH +: SEG_WIDTH];
        end
    endgenerate
    always @(posedge clk) begin
        if (reset) begin
            encoded_data <= {DATA_WIDTH{1'b0}};
            invert_flags <= {SEGMENTS{1'b0}};
        end else begin
            encoded_data <= next_data;
            invert_flags <= next_flags;
        end
    end
endmodule
```

### rtl/segmented_bus_invert_decoder.v

```verilog
`timescale 1ns/1ps
// Same positive, divisible width requirements as the encoder.
module segmented_bus_invert_decoder #(
    parameter DATA_WIDTH = 16,
    parameter SEG_WIDTH = 4
) (
    input [DATA_WIDTH-1:0] encoded_data,
    input [(DATA_WIDTH/SEG_WIDTH)-1:0] invert_flags,
    output [DATA_WIDTH-1:0] decoded_data
);
    genvar s;
    generate
        for (s = 0; s < DATA_WIDTH/SEG_WIDTH; s = s + 1) begin : segments
            assign decoded_data[s*SEG_WIDTH +: SEG_WIDTH] =
                encoded_data[s*SEG_WIDTH +: SEG_WIDTH] ^
                {SEG_WIDTH{invert_flags[s]}};
        end
    endgenerate
endmodule
```

### rtl/top.v

```verilog
`timescale 1ns/1ps
// Comparison harness: normal is combinational; both coded buses are registered.
module top #(
    parameter DATA_WIDTH = 16,
    parameter SEG_WIDTH = 4
) (
    input clk,
    input reset,
    input [DATA_WIDTH-1:0] data_in,
    output [DATA_WIDTH-1:0] normal_data,
    output [DATA_WIDTH-1:0] global_encoded_data,
    output global_invert_flag,
    output [DATA_WIDTH-1:0] segmented_encoded_data,
    output [(DATA_WIDTH/SEG_WIDTH)-1:0] segmented_invert_flags,
    output [DATA_WIDTH-1:0] segmented_decoded_data
);
    normal_bus #(.DATA_WIDTH(DATA_WIDTH)) u_normal (
        .data_in(data_in), .encoded_data(normal_data)
    );
    bus_invert #(.DATA_WIDTH(DATA_WIDTH)) u_global (
        .clk(clk), .reset(reset), .data_in(data_in),
        .encoded_data(global_encoded_data), .invert_flag(global_invert_flag)
    );
    segmented_bus_invert_encoder #(
        .DATA_WIDTH(DATA_WIDTH), .SEG_WIDTH(SEG_WIDTH)
    ) u_encoder (
        .clk(clk), .reset(reset), .data_in(data_in),
        .encoded_data(segmented_encoded_data), .invert_flags(segmented_invert_flags)
    );
    segmented_bus_invert_decoder #(
        .DATA_WIDTH(DATA_WIDTH), .SEG_WIDTH(SEG_WIDTH)
    ) u_decoder (
        .encoded_data(segmented_encoded_data), .invert_flags(segmented_invert_flags),
        .decoded_data(segmented_decoded_data)
    );
endmodule
```

### tb/tb_top.v

```verilog
`timescale 1ns/1ps
module tb_top;
    reg clk, reset;
    reg [15:0] data_in, previous_normal;
    wire [15:0] normal_data;
    // Slots: 0=global, 1=seg16, 2=seg8, 3=seg4, 4=seg2. Flags padded to 8.
    wire [79:0] encoded, decoded;
    wire [39:0] flags;
    reg [15:0] previous [0:4];
    reg [7:0] previous_flags [0:4];
    integer data_total [0:4], flag_total [0:4], inversions [0:4];
    integer per_segment [0:39], ties [0:4];
    integer errors, samples, normal_total, i, j, csv;
    reg [31:0] rng;
    reg [15:0] walking;
    top dut (
        .clk(clk), .reset(reset), .data_in(data_in), .normal_data(normal_data),
        .global_encoded_data(encoded[15:0]), .global_invert_flag(flags[0]),
        .segmented_encoded_data(encoded[63:48]),
        .segmented_invert_flags(flags[27:24]), .segmented_decoded_data(decoded[63:48])
    );
    assign flags[7:1] = 7'b0;
    assign flags[31:28] = 4'b0;
    assign decoded[15:0] = encoded[15:0] ^ {16{flags[0]}};
    genvar g;
    generate
        for (g = 1; g < 5; g = g + 1) begin : experiments
            if (g != 3) begin : extra
                localparam SW = 16 >> (g-1);
                localparam NF = 16 / SW;
                segmented_bus_invert_encoder #(.SEG_WIDTH(SW)) enc (
                    .clk(clk), .reset(reset), .data_in(data_in),
                    .encoded_data(encoded[g*16 +: 16]), .invert_flags(flags[g*8 +: NF])
                );
                segmented_bus_invert_decoder #(.SEG_WIDTH(SW)) dec (
                    .encoded_data(encoded[g*16 +: 16]), .invert_flags(flags[g*8 +: NF]),
                    .decoded_data(decoded[g*16 +: 16])
                );
                if (NF < 8) begin : padding
                    assign flags[g*8+NF +: 8-NF] = 0;
                end
            end
        end
    endgenerate
    always #5 clk = ~clk;
    function integer ones;
        input [15:0] word;
        integer b;
        begin
            ones = 0;
            for (b = 0; b < 16; b = b + 1) ones = ones + word[b];
        end
    endfunction
    task fail;
        input [8*64-1:0] reason;
        begin
            errors = errors + 1;
            $display("ERROR time=%0t input=%h: %0s", $time, data_in, reason);
        end
    endtask
    task clear_counts;
        integer a;
        begin
            samples = 0; normal_total = 0;
            for (a = 0; a < 5; a = a + 1) begin
                data_total[a] = 0; flag_total[a] = 0; inversions[a] = 0;
            end
            for (a = 0; a < 40; a = a + 1) per_segment[a] = 0;
        end
    endtask
    task reset_dut;
        integer a;
        reg [79:0] held;
        reg [39:0] held_flags;
        begin
            @(negedge clk);
            held = encoded; held_flags = flags;
            reset = 1; data_in = 16'hffff;
            #1;
            if (encoded !== held || flags !== held_flags) fail("reset must be synchronous");
            @(posedge clk); #1;
            if (encoded !== 80'b0 || flags !== 40'b0 || decoded !== 80'b0)
                fail("reset must clear all encoded outputs, flags and decoders");
            for (a = 0; a < 5; a = a + 1) begin
                previous[a] = 0; previous_flags[a] = 0;
            end
            previous_normal = 0;
            @(negedge clk); reset = 0; data_in = 0;
        end
    endtask
    task send;
        input [15:0] value;
        integer a, s, b, sw, distance, flips;
        reg [15:0] expected, actual;
        reg [7:0] expected_flags, actual_flags;
        reg [79:0] held;
        reg [39:0] held_flags;
        begin
            @(negedge clk);
            held = encoded; held_flags = flags; data_in = value;
            #1;
            if (encoded !== held || flags !== held_flags) fail("outputs changed between clock edges");
            @(posedge clk); #1;
            if (normal_data !== value) fail("normal bus mismatch");
            normal_total = normal_total + ones(value ^ previous_normal);
            previous_normal = value; samples = samples + 1;
            for (a = 0; a < 5; a = a + 1) begin
                sw = (a == 0) ? 16 : (16 >> (a-1));
                expected = value; expected_flags = 0;
                actual = encoded[a*16 +: 16]; actual_flags = flags[a*8 +: 8];
                for (s = 0; s < 16/sw; s = s + 1) begin
                    distance = 0;
                    for (b = 0; b < sw; b = b + 1)
                        distance = distance + (value[s*sw+b] ^ previous[a][s*sw+b]);
                    if (sw-distance < distance) begin
                        expected_flags[s] = 1;
                        for (b = 0; b < sw; b = b + 1)
                            expected[s*sw+b] = ~value[s*sw+b];
                    end
                    if (sw-distance == distance) ties[a] = ties[a] + 1;
                    flips = 0;
                    for (b = 0; b < sw; b = b + 1)
                        flips = flips + (actual[s*sw+b] ^ previous[a][s*sw+b]);
                    if (flips > sw/2) fail("segment exceeded half-width transition bound");
                    per_segment[a*8+s] = per_segment[a*8+s] + flips;
                end
                if (actual !== expected || actual_flags !== expected_flags) begin
                    $display("slot=%0d expected=%h/%h actual=%h/%h",
                             a, expected, expected_flags, actual, actual_flags);
                    fail("encoding decision/history/tie mismatch");
                end
                if (decoded[a*16 +: 16] !== value) fail("decoder mismatch");
                data_total[a] = data_total[a] + ones(actual ^ previous[a]);
                flag_total[a] = flag_total[a] + ones({8'b0, actual_flags ^ previous_flags[a]});
                inversions[a] = inversions[a] + ones({8'b0, actual_flags});
                previous[a] = expected; previous_flags[a] = expected_flags;
            end
            if (encoded[15:0] !== encoded[31:16] || flags[0] !== flags[8])
                fail("global BI differs from SEG_WIDTH=16");
        end
    endtask
    task report;
        input [8*24-1:0] workload;
        integer a, s, sw, total, sum;
        real data_reduction, total_reduction;
        begin
            $display("\nWORKLOAD %0s samples=%0d normal=%0d", workload, samples, normal_total);
            $fwrite(csv, "%0s,normal,16,0,%0d,0,%0d,0,", workload, normal_total, normal_total);
            if (normal_total == 0) $fwrite(csv, "N/A,N/A\n");
            else $fwrite(csv, "0.00,0.00\n");
            for (a = 0; a < 5; a = a + 1) begin
                sw = (a == 0) ? 16 : (16 >> (a-1));
                total = data_total[a] + flag_total[a]; sum = 0;
                $display("slot=%0d width=%0d flags=%0d data=%0d flag=%0d total=%0d inversions=%0d",
                         a, sw, 16/sw, data_total[a], flag_total[a], total, inversions[a]);
                $fwrite(csv, "%0s,slot%0d,%0d,%0d,%0d,%0d,%0d,%0d,",
                        workload, a, sw, 16/sw, data_total[a], flag_total[a], total, inversions[a]);
                if (normal_total == 0) begin
                    $display("data reduction=N/A total reduction=N/A (zero baseline)");
                    $fwrite(csv, "N/A,N/A\n");
                end else begin
                    data_reduction = 100.0 * (normal_total-data_total[a]) / normal_total;
                    total_reduction = 100.0 * (normal_total-total) / normal_total;
                    $display("data reduction=%0.2f%% total reduction=%0.2f%%", data_reduction, total_reduction);
                    $fwrite(csv, "%0.2f,%0.2f\n", data_reduction, total_reduction);
                end
                for (s = 0; s < 16/sw; s = s + 1) begin
                    $display("  segment %0d data transitions=%0d", s, per_segment[a*8+s]);
                    sum = sum + per_segment[a*8+s];
                end
                if (sum != data_total[a]) fail("per-segment total mismatch");
            end
        end
    endtask
    initial begin
        clk = 0; reset = 0; data_in = 0; errors = 0; rng = 32'h12345678;
        for (i = 0; i < 5; i = i + 1) ties[i] = 0;
        csv = $fopen("results.csv", "w");
        if (csv == 0) begin $display("TEST FAILED: cannot open results.csv"); $finish; end
        $fwrite(csv, "Workload,Architecture,SegmentSize,FlagBits,DataTransitions,FlagTransitions,TotalTransitions,Inversions,DataReductionPct,TotalReductionPct\n");
`ifdef DUMP_VCD
        $dumpfile("segmented_bus_invert.vcd");
        $dumpvars(0, tb_top);
`endif
        reset_dut; clear_counts;
        for (i = 0; i < 8; i = i + 1) send(16'h0000);
        report("zero_activity");
        reset_dut; clear_counts;
        send(16'h0000); send(16'hffff); send(16'haaaa); send(16'h5555);
        reset_dut; send(16'h5555); // Half the bits in every even-width segment.
        send(16'hffff); send(16'hffff); send(16'h0000);
        for (i = 0; i < 16; i = i + 1) send(16'b1 << i);
        reset_dut; send(16'hffff); send(16'h0000); // Reset after active history.
        report("directed_and_ties");
        reset_dut; clear_counts;
        for (i = 0; i < 64; i = i + 1)
            send({{4{i[0]}}, 8'h00, 3'b000, i[4]});
        for (i = 0; i < 4; i = i + 1)
            for (j = 0; j < 16; j = j + 1) send(j << (i*4));
        report("localized");
        reset_dut; send(16'hffff); clear_counts; // Warm up before measuring.
        walking = 16'hffff;
        for (i = 0; i < 16; i = i + 1) begin
            walking = walking ^ (16'b1 << i); send(walking);
        end
        report("single_bit_walk");
        reset_dut; clear_counts;
        for (i = 0; i < 1024; i = i + 1) begin
            rng = rng ^ (rng << 13);
            rng = rng ^ (rng >> 17);
            rng = rng ^ (rng << 5);
            send(rng[15:0]);
        end
        report("random_seed_12345678");
        for (i = 0; i < 5; i = i + 1)
            if (ties[i] == 0) fail("missing tie coverage");
        $fclose(csv);
        if (errors == 0) $display("TEST PASSED");
        else $display("TEST FAILED: %0d errors", errors);
        $finish;
    end
    initial begin
        #200000;
        $display("TEST FAILED: watchdog timeout");
        $finish;
    end
endmodule
```

## Part 6 — Detailed code explanation

- Segmentation uses indexed part-selects, such as `data_in[s*SEG_WIDTH +: SEG_WIDTH]`. Generate loops, local parameters, indexed part-selects, and the testbench's reg/integer memories are all standard Verilog-2001.
- History is the registered `encoded_data`, fed into each transition counter. Nonblocking assignments update it only after the decision using the old value has been sampled. No previous-original-data register participates in encoding.
- XOR produces one bit per wire that would change; popcount adds those bits. For width 4, inputs 0000, 0001, 0011, 0111 and 1111 yield 0, 1, 2, 3 and 4.
- The strict greater-than-half comparison implements the requested cost comparison, including flag=0 for ties. Complementing every bit changes a distance d into SEG_WIDTH-d.
- Each flag is registered with its segment. Decoder XOR with a replicated flag either preserves every bit or complements every bit.
- Require DATA_WIDTH > 0, SEG_WIDTH > 0, and DATA_WIDTH divisible by SEG_WIDTH. Width parameters are compile/elaboration-time constants. The synthesis script checks these requirements; RTL contains no simulation-only parameter checks.
- Popcount's COUNT_WIDTH default equals WIDTH, which safely represents every possible count for positive WIDTH. Synthesis can trim unused upper count bits. An override may reduce it to ceil(log2(WIDTH+1)), but must never make it smaller.

The independent testbench reference model uses bit-by-bit calculations and explicit normal/inverted costs. It checks the exact encoded word and flag, decoding, the half-width transition bound, registered-output stability, synchronous reset, per-segment sums, tie coverage, and global-versus-SEG_WIDTH=16 equivalence. A decoder-only check would not detect an encoder that always chose normal coding.

Five workloads are reported separately. Counters are cleared only when starting a new workload, never automatically by reset. Reset clears the history used by the reference model, preserving any accumulated workload measurements. Reset transitions are excluded, and the first measured transmission is compared with zero after reset. The single-bit-walk workload has a measured interval after one all-ones warm-up word; that warm-up is excluded while preserving its state.

Inversions count how many accepted segments have flag=1, including consecutive inverted segments. Flag transitions count changes between consecutive flags; the two measurements are different. Every workload reports data-only and data-plus-flag reductions. When normal transitions are zero, both percentages are N/A.

The pseudo-random sequence uses a reproducible 32-bit xorshift generator seeded with 0x12345678. There are 1,024 consecutive random words. The directed and localized workloads cover zeros, ones, both alternating patterns, all segment ties, heavy activity in segment 3, slow activity in segment 0, one segment at a time, walking bits, repeated words, and reset after active history. `TEST PASSED` appears only if the accumulated error count is zero. The Makefile also checks the log, because portable Verilog $finish does not provide a standardized failing process exit status.

## Part 7 — Numerical example

Use an 8-bit bus with two 4-bit segments. Suppose the previous encoded data is 0011_1100, the previous flags are 00, and the current input is 1101_1101.

| Calculation | Segment 1 [7:4] | Segment 0 [3:0] |
|---|---|---|
| Current input | 1101 | 1101 |
| Previous encoded | 0011 | 1100 |
| XOR | 1110 | 0001 |
| Popcount d | 3 | 1 |
| Normal cost | 3 | 1 |
| Inverted cost 4-d | 1 | 3 |
| Flag | 1 | 0 |
| Transmitted segment | 0010 | 1101 |
| Actual transmitted XOR | 0001 | 0001 |
| Data transitions | 1 | 1 |

Transmit data 0010_1101 and flags 10. Decode segment 1 as ~0010=1101 and segment 0 unchanged, giving 1101_1101.

Data transitions are 2, flag transitions are popcount(10 XOR 00)=1, and total transitions are 3. Since the previous flags were 00, the previous original word was also 0011_1100; the normal bus would have 4 transitions. Global 8-bit BI sees d=4, a tie, so it also has 4 data transitions and no flag transition.

For a following input 0111_1101, compare against the newly stored 0010_1101. Segment 1 has XOR 0101, d=2, and equal normal/inverted costs; send 0111 with flag=0. Segment 0 has d=0 and flag=0. Data transitions are 2 and flags change 10 to 00, adding 1. This illustrates why the previous encoded word and flag overhead matter.

## Part 8 — Simulation

Load your institution's Cadence environment and license setup. From the project root, compile and run:

```bash
xrun -access +rwc -top tb_top +define+DUMP_VCD rtl/*.v tb/tb_top.v
```

All HDL sources use .v extensions. Do not enable another HDL language mode. The command produces results.csv and segmented_bus_invert.vcd in the current directory. Select tb_top as the simulation top; select top or a selected encoder as the synthesis top.

For an organized output directory, run `make xrun`. For a local Icarus installation, `make test` compiles with `-g2001 -Wall`, runs verification, and checks its result. The local run passed all 1,202 measured words plus the warm-up and reset checks. Additional independent checks passed for DATA_WIDTH/SEG_WIDTH pairs 8/4, 9/3, 33/11, and 1/1. Temporary deliberately faulty variants using invert-on-tie and incorrect history were both rejected by the testbench.

## Part 9 — Waveform analysis

Create a native waveform database using scripts/xrun_waves.tcl:

```tcl
database -open waves -into waves.shm -default
probe -create -shm tb_top -all -depth all
run
exit
```

```bash
xrun -access +rwc -top tb_top rtl/*.v tb/tb_top.v -input scripts/xrun_waves.tcl
simvision waves.shm
```

Cadence documents the `-input` Tcl flow and database/probe commands in its [Xcelium waveform guidance](https://community.cadence.com/cadence_technology_forums/f/functional-verification/57941/xrun-dump-all-internal-signals). Its [SimVision guidance](https://community.cadence.com/cadence_technology_forums/f/functional-verification/57967/xcelium---usage-of-xrun-command/1392714) also describes reopening recorded waveforms after a batch run.

In SimVision, open the design browser, expand tb_top.dut, select signals, and add them to the waveform window. Inspect clk, reset, data_in, normal_data, global_encoded_data, global_invert_flag, segmented_encoded_data, segmented_invert_flags, and segmented_decoded_data.

For the primary encoder, inspect `tb_top.dut.u_encoder.encoded_data`, `next_data`, `next_flags`, and `segments[0].transitions` through `segments[3].transitions`. Before a rising edge, encoded_data holds the previous transmitted word and next_data holds the upcoming candidate. After the edge, encoded_data holds the new transmission; combinational next_data and transition counts may recompute for the still-held input. Read the pre-edge combinational values when explaining the decision.

The testbench changes input on falling edges and checks outputs 1 ns after rising edges, allowing nonblocking assignments and decoder propagation to settle. A synchronous reset affects coded outputs only at a rising edge. During reset the decoded output is zero regardless of data_in. For the other segment widths, expand tb_top.experiments[1].extra, [2].extra, and [4].extra.

## Part 10 — Cadence synthesis

Use a fresh Genus Common UI session and run from the project root:

```bash
genus -files scripts/genus_synth.tcl
```

scripts/genus_synth.tcl:

```tcl
# Run from the project root using: genus -files scripts/genus_synth.tcl
# Common UI. Use a fresh Genus process for each architecture.
set DESIGN top
set DATA_WIDTH 16
set SEG_WIDTH 4
set LIBRARY "<YOUR_STANDARD_CELL_LIBRARY>"
set OUTPUT_LOAD "<OUTPUT_LOAD_IN_LIBRARY_CAPACITANCE_UNITS>"
if {![file isfile $LIBRARY]} {
    error "Replace LIBRARY with an existing characterized Liberty .lib file."
}
if {![string is double -strict $OUTPUT_LOAD] || $OUTPUT_LOAD < 0} {
    error "Replace OUTPUT_LOAD with a nonnegative per-wire load in library units."
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
```

scripts/constraints.sdc:

```tcl
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
```

Replace LIBRARY with the path to your characterized standard-cell Liberty file, at the intended process/voltage/temperature corner. Replace OUTPUT_LOAD with a numerical per-wire capacitance in that library's capacitance units. Adjust the example clock period, input/output delays, slew, and uncertainty to your actual interface and library time units. The clock example corresponds to 100 MHz only if the library time unit is ns.

The flow reads only synthesizable RTL, elaborates parameters in declaration order, checks unresolved references, applies constraints, runs generic synthesis, technology mapping and optimization, and writes mapped RTL/SDC plus area, timing, and cell-usage reports. These stages follow the [Cadence synthesis flow discussion](https://community.cadence.com/cadence_technology_forums/f/digital-implementation/58890/failed-to-synthesis-riscy-core-on-genus-legacy/1397114); parameter ordering is described in the [Cadence Genus User Guide](https://iccircle.com/static/upload/img20250710134249.pdf).

DESIGN=top builds the integrated demonstration. For separate encoder comparisons, set DESIGN to normal_bus, bus_invert, or segmented_bus_invert_encoder, and select SEG_WIDTH=8, 4, or 2 for the latter. Width 16 provides an additional equivalence baseline. Output directories are tagged by design and widths. For decoder area/timing, select segmented_bus_invert_decoder with the corresponding width, including 16 for global BI.

Do not use the total area of the integrated demonstration as any individual architecture's area. Decide whether your comparison measures encoder-only hardware or the complete link; label that boundary. The normal assignment has no coding logic and can map to a connection, so a zero-cell result is possible. A fair complete-link comparison must give all alternatives equivalent launch/capture registers, load models, throughput, and timing requirements, and include decoder cost. Keep encoded data and flag wires as observable link boundaries so synthesis cannot optimize away the link by merging encoder and decoder logic.

Synchronous reset remains timed. The combinational normal bus and decoder use a virtual reference clock for I/O timing. Inspect mapping warnings, unconstrained paths, clock requirements, cell count and total area; report actual path delay and clock period separately from slack.

## Part 11 — Power analysis

The experiment measures sampled wire transitions, not watts. Use this implementation flow:

```text
RTL + identical workloads
        |
        v
Xcelium simulation --> VCD activity / SHM for waveform inspection
        |
        v
Genus + characterized cell library + timing and load constraints
        |
        v
Mapped gate netlist --> gate simulation + cell models + VCD
        |                         |
        +----------+--------------+
                   v
         Activity-based power analysis
                   |
                   v
     Placement/routing + extracted parasitics
                   |
                   v
       Refined implementation power estimate
```

Cadence's [Joules RTL Power Solution documentation](https://login.cadence.com/content/dam/cadence-www/global/en_US/documents/tools/digital-design-signoff/joules-rtl-power-solution-ds.pdf) describes activity-driven power estimation. Use your installed Genus/Joules flow for early estimates and your implementation/signoff flow, such as Innovus/Voltus, for physical estimates.

Generate VCD using DUMP_VCD. SHM is intended here for waveform inspection; use the activity format supported by the selected power engine. In your installed release, check `help read_vcd` and `help report_power` in Genus, or the documented `read_stimulus`/power-computation flow in Joules. Select the correct VCD hierarchy, for example tb_top.dut.u_encoder for the primary standalone encoder, and the measured workload's time window. Check the annotation coverage report: successfully reading a file does not prove that its activity matched the netlist. Cadence discusses hierarchy selection in its [VCD annotation guidance](https://community.cadence.com/cadence_technology_forums/f/logic-design/26545/using-modelsim-questasim-vcd-file-in-rtl-compiler/1362592).

For better internal activity estimates, simulate the mapped netlist with your library's Verilog cell models and optionally annotated delays; use that gate-level VCD. RTL activity does not capture physical glitches, interconnect effects, or all clock-tree power. A post-route netlist and extracted parasitics improve capacitance and timing accuracy. For gate simulation, use a testbench with the same workload and an observation delay appropriate to the mapped design's timing.

If alpha counts charging events per cycle, the usual relation is P_switch ≈ alpha*C*V²*f. If a transition rate counts both rising and falling edges, then for a balanced, long observation interval P_switch ≈ 0.5*transition_rate*C*V². This project's counters count both directions, so state the convention explicitly.

Actual power depends on technology node, standard-cell library, voltage, clock frequency, capacitance, activity, synthesis mapping, encoder/decoder internal activity, flags, registers and clock distribution. Include load on flag wires as well as data wires. For differing wire capacitances, an unweighted count is only a proxy; use per-wire activity and capacitance.

Exclude reset and warm-up windows consistently when comparing with the printed measurements. The full VCD includes them. An unchanged data bus can still have internal clock power. Report switching, internal, leakage, and total power separately where supported. No power, area, or delay values are fabricated in this project.

## Part 12 — Experiments

| Architecture | SEG_WIDTH | Segments | Flag wires | Total transmitted wires |
|---|---:|---:|---:|---:|
| Normal | — | — | 0 | 16 |
| Global BI | 16 | 1 | 1 | 17 |
| 2×8 segmented BI | 8 | 2 | 2 | 18 |
| 4×4 segmented BI | 4 | 4 | 4 | 20 |
| 8×2 segmented BI | 2 | 8 | 8 | 24 |

The testbench also instantiates segmented width 16 and checks it against the separate global encoder on every word. CSV slot0=global, slot1=seg16, slot2=seg8, slot3=seg4, slot4=seg2.

Run all workloads on the same inputs and initial conditions. The report contains normal/data/flag/total transitions, inversion decisions and per-segment data counts. Calculate:

- DataReductionPct = 100*(normal_data_transitions - encoded_data_transitions)/normal_data_transitions.
- TotalReductionPct = 100*(normal_data_transitions - encoded_data_transitions - flag_transitions)/normal_data_transitions.

Negative total reduction means the encoded link switched more often. Zero baseline means N/A. More inversion decisions are not necessarily better.

The following are actual local simulation counts for the 1,024-word random workload, not Cadence power estimates:

| Architecture | Data transitions | Flag transitions | Total | Data reduction % | Total reduction % |
|---|---:|---:|---:|---:|---:|
| Normal | 8110 | 0 | 8110 | 0.00 | 0.00 |
| Global BI | 6604 | 473 | 7077 | 18.57 | 12.74 |
| 2×8 BI | 6006 | 925 | 6931 | 25.94 | 14.54 |
| 4×4 BI | 5196 | 1721 | 6917 | 35.93 | 14.71 |
| 8×2 BI | 4144 | 3037 | 7181 | 48.90 | 11.45 |

On this workload, 8×2 minimizes data transitions among the tested options, but 4×4 has the fewest total wire transitions. On the localized workload, 4×4 has 167 total transitions versus 376 normal. On the single-bit walk after inverted warm-up, 8×2 has 24 total transitions versus 16 normal, yielding -50% total reduction. These are workload-specific observations, not proof that any segment width always wins.

Use multiple representative traffic traces and seeds for the final study. Smaller segments add flags and decision regions; actual cell area is synthesis-dependent, since their popcounts and decision paths are also smaller. Do not assume a monotonic area, delay, or power ordering.

## Part 13 — Results table

Fill one table per workload and implementation corner. In this table, Transition Reduction % means total data-plus-flag reduction. Keep the separately reported data-only percentage alongside it in your detailed report. Measurement cells are deliberately empty; configuration entries are design facts.

| Architecture | Segment Size | Flag Bits | Data Transitions | Flag Transitions | Total Transitions | Transition Reduction % | Area | Cell Count | Delay | Power |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Normal | — | 0 | | | | | | | | |
| Global Bus-Invert | 16 | 1 | | | | | | | | |
| 2×8 Segmented BI | 8 | 2 | | | | | | | | |
| 4×4 Segmented BI | 4 | 4 | | | | | | | | |
| 8×2 Segmented BI | 2 | 8 | | | | | | | | |

The same blank measurement template is supplied as results_template.csv. State area units, delay units, power units, library corner, voltage, frequency, loads, observation duration, reset treatment and the encoder-only or complete-link measurement boundary.

## Part 14 — VLSI project presentation

1. Problem: show how bit transitions charge and discharge bus capacitance.
2. Objective: preserve every accepted 16-bit word while measuring the effect of segmentation on switching and implementation cost.
3. Existing approach: explain normal transmission and global BI with one inversion flag.
4. Proposed approach: explain four independent 4-bit decisions and the resulting 20-wire link.
5. Architecture: show the XOR, popcount, comparison, registers, flag wires and decoder; highlight encoded-data feedback.
6. RTL implementation: explain parameterization, synchronous reset, strict tie handling and registered transmission.
7. Simulation: show TEST PASSED, reset and tie waveforms, repeated inputs, localized changes and exact decoding.
8. Cadence synthesis: show mapped architecture, area, cell usage, timing and the chosen constraints/library.
9. Power/area/timing comparison: compare identical workloads and loads, explicitly including data and flag activity.
10. Trade-offs: show the random workload's data-versus-total ranking and the single-bit-walk counterexample; discuss hardware overhead and physical capacitance.
11. Conclusion: choose a segment size only for the measured traffic and implementation conditions. Phrase an RTL-only result as reduced switching, and claim lower dynamic power only after activity-annotated implementation analysis.
