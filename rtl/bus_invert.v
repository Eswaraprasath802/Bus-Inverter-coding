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
