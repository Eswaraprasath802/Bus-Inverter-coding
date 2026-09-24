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
    integer errors, samples, normal_total, i, csv;
    reg [15:0] trace_words [0:1023];
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
    task run_trace;
        input [8*24-1:0] name;
        input integer count;
        input integer warmup;
        integer n;
        reg [8*128-1:0] filename;
        begin
            reset_dut;
            if (warmup >= 0) send(warmup[15:0]);
            clear_counts;
            $sformat(filename, "traces/%0s.hex", name);
            $readmemh(filename, trace_words, 0, count-1);
            for (n = 0; n < count; n = n + 1) begin
                if (^trace_words[n] === 1'bx) fail("missing or unknown trace sample");
                send(trace_words[n]);
            end
            report(name);
        end
    endtask
    initial begin
        clk = 0; reset = 0; data_in = 0; errors = 0;
        for (i = 0; i < 5; i = i + 1) ties[i] = 0;
        csv = $fopen("results.csv", "w");
        if (csv == 0) begin $display("TEST FAILED: cannot open results.csv"); $finish; end
        $fwrite(csv, "Workload,Architecture,SegmentSize,FlagBits,DataTransitions,FlagTransitions,TotalTransitions,Inversions,DataReductionPct,TotalReductionPct\n");
`ifdef DUMP_VCD
        $dumpfile("segmented_bus_invert.vcd");
        $dumpvars(0, tb_top);
`endif
        run_trace("zero_activity", 8, -1);
        reset_dut; clear_counts;
        send(16'h0000); send(16'hffff); send(16'haaaa); send(16'h5555);
        reset_dut; send(16'h5555); // Half the bits in every even-width segment.
        send(16'hffff); send(16'hffff); send(16'h0000);
        for (i = 0; i < 16; i = i + 1) send(16'b1 << i);
        reset_dut; send(16'hffff); send(16'h0000); // Reset after active history.
        report("directed_and_ties");
        run_trace("localized", 128, -1);
        run_trace("single_bit_walk", 16, 65535);
        run_trace("random_seed_12345678", 1024, -1);
        run_trace("random_seed_deadbeef", 1024, -1);
        run_trace("random_seed_cafebabe", 1024, -1);
        run_trace("random_seed_31415926", 1024, -1);
        run_trace("correlated", 1024, -1);
        run_trace("bursty", 1024, -1);
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
