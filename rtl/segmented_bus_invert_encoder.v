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
