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
