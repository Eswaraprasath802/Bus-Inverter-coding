`timescale 1ns/1ps
// Compile with TOP, SEG_WIDTH, FLAG_BITS and optionally NORMAL or GLOBAL_BI.
// Replay exactly the same trace as tb_top; record only after reset/warm-up.
module tb_mapped;
    reg clk = 0;
    reg reset = 1;
    reg [15:0] data_in = 0;
    wire [15:0] encoded_data;
    wire [`FLAG_BITS-1:0] flags;
    reg [15:0] words [0:1023];
    reg [15:0] previous_data, expected;
    reg [`FLAG_BITS-1:0] previous_flags, expected_flags;
    integer n, count, warmup, s, b, distance, errors, data_count, flag_count;
    reg [8*512-1:0] trace_path, vcd_path;
`ifdef NORMAL
    `TOP dut (.data_in(data_in), .encoded_data(encoded_data));
    assign flags = 0;
`elsif GLOBAL_BI
    `TOP dut (.clk(clk), .reset(reset), .data_in(data_in),
              .encoded_data(encoded_data), .invert_flag(flags));
`else
    `TOP dut (.clk(clk), .reset(reset), .data_in(data_in),
              .encoded_data(encoded_data), .invert_flags(flags));
`endif
    always #5 clk = ~clk;
    task check_word;
        begin
            expected = data_in;
            expected_flags = 0;
`ifndef NORMAL
            for (s = 0; s < `FLAG_BITS; s = s + 1) begin
                distance = 0;
                for (b = 0; b < `SEG_WIDTH; b = b + 1)
                    distance = distance + (data_in[s*`SEG_WIDTH+b] ^ previous_data[s*`SEG_WIDTH+b]);
                if (distance > `SEG_WIDTH/2) begin
                    expected_flags[s] = 1;
                    for (b = 0; b < `SEG_WIDTH; b = b + 1)
                        expected[s*`SEG_WIDTH+b] = ~data_in[s*`SEG_WIDTH+b];
                end
            end
`endif
            if (encoded_data !== expected || flags !== expected_flags) begin
                errors = errors + 1;
                $display("ERROR sample=%0d input=%h expected=%h/%h actual=%h/%h",
                         n, data_in, expected, expected_flags, encoded_data, flags);
            end
            for (b = 0; b < 16; b = b + 1)
                data_count = data_count + (encoded_data[b] ^ previous_data[b]);
            for (b = 0; b < `FLAG_BITS; b = b + 1)
                flag_count = flag_count + (flags[b] ^ previous_flags[b]);
            previous_data = expected;
            previous_flags = expected_flags;
        end
    endtask
    initial begin
        errors = 0; data_count = 0; flag_count = 0;
        previous_data = 0; previous_flags = 0;
        if (!$value$plusargs("TRACE=%s", trace_path) ||
            !$value$plusargs("VCD=%s", vcd_path) ||
            !$value$plusargs("COUNT=%d", count) ||
            !$value$plusargs("WARMUP=%d", warmup)) begin
            $display("TEST FAILED: missing replay arguments"); $finish;
        end
        $readmemh(trace_path, words, 0, count-1);
        repeat (2) @(posedge clk);
        #1;
        if (encoded_data !== 0 || flags !== 0) begin
            $display("TEST FAILED: mapped reset"); $finish;
        end
        @(negedge clk); reset = 0;
        if (warmup >= 0) begin
            data_in = warmup[15:0];
            @(posedge clk); #1; check_word;
            @(negedge clk);
        end
        data_count = 0; flag_count = 0;
        // One ns before the first input transition, through N complete cycles.
        #9;
        $dumpfile(vcd_path);
        $dumpvars(0, tb_mapped.dut);
        for (n = 0; n < count; n = n + 1) begin
            #1; data_in = words[n];
            @(posedge clk); #1; check_word;
            #3;
        end
        $display("COUNTS %0d %0d", data_count, flag_count);
        if (errors == 0) $display("TEST PASSED");
        else $display("TEST FAILED: %0d errors", errors);
        $finish;
    end
endmodule
