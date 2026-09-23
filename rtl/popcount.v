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
