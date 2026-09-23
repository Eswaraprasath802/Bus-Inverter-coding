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
