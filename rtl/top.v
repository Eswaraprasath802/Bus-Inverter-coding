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
