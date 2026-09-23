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
