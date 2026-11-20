/*
 * TT-RISC8: 8-bit RISC Micro-CPU with Internal Program ROM and 7-Segment Debug Unit
 * Author: Orlando Arturo Palma Leon (GitHub: Orlando-Palma)
 * Shuttle: Tiny Tapeout GF180MCU TTGF26c
 * SPDX-License-Identifier: Apache-2.0
 */

`default_nettype none

module tt_um_orlando_palma_risc8 (
    input  wire [7:0] ui_in,    // Dedicated inputs
    output wire [7:0] uo_out,   // Dedicated outputs
    input  wire [7:0] uio_in,   // IOs: Input path
    output wire [7:0] uio_out,  // IOs: Output path
    output wire [7:0] uio_oe,   // IOs: Enable path (active high: 0=input, 1=output)
    input  wire       ena,      // always 1 when the design is powered, so you can ignore it
    input  wire       clk,      // clock
    input  wire       rst_n     // reset_n - low to reset
);

    // -------------------------------------------------------------------------
    // Pin Decoding (ui_in[7:0])
    // -------------------------------------------------------------------------
    wire [1:0] prog_sel  = ui_in[1:0]; // Select 1 of 4 internal ROM programs
    wire       step_en   = ui_in[2];   // 0: continuous clock, 1: single-step mode
    wire       step_trig = ui_in[3];   // Rising edge 0->1 advances 1 cycle when step_en=1
    wire [1:0] dbg_sel   = ui_in[5:4]; // 7-seg mux: 00=OUT[3:0], 01=OUT[7:4], 10=ACC[3:0], 11=PC
    wire       user_in   = ui_in[6];   // 1-bit user data input read by IN instruction
    wire       ext_mode  = ui_in[7];   // 0: internal ROM (uio=OUT), 1: external instr on uio_in

    // -------------------------------------------------------------------------
    // Processor Registers (32 Flip-Flops total for 1x1 tile fit in GF180MCU)
    // -------------------------------------------------------------------------
    reg [2:0] pc;
    reg [7:0] acc;
    reg [7:0] r1;
    reg [7:0] out_reg;
    reg       flag_z;
    reg       flag_c;
    reg       step_prev;
    reg [1:0] prev_prog;

    // -------------------------------------------------------------------------
    // Internal 32x8 Program ROM (4 Banks x 8 Instructions)
    // -------------------------------------------------------------------------
    wire [4:0] rom_addr = {prog_sel, pc};
    reg  [7:0] rom_data;

    always @(*) begin
        case (rom_addr)
            // Bank 0 (prog_sel = 2'b00): 8-bit Fibonacci Sequence with Auto-Restart
            // Sequence: 1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233 (0xE9)
            5'h00: rom_data = 8'h10; // LDI 0        (ACC = 0)
            5'h01: rom_data = 8'h82; // MOV R1, ACC  (R1 = 0)
            5'h02: rom_data = 8'h11; // LDI 1        (ACC = 1)
            5'h03: rom_data = 8'h40; // ADD          ({C, ACC} = ACC + R1)
            5'h04: rom_data = 8'hE0; // JC  0        (Restart at 0 on 8-bit carry overflow)
            5'h05: rom_data = 8'hB0; // OUT          (Publish Fibonacci term to OUT)
            5'h06: rom_data = 8'h90; // SWAP         (ACC <-> R1)
            5'h07: rom_data = 8'hC3; // JMP 3        (Next Fibonacci iteration)

            // Bank 1 (prog_sel = 2'b01): Generalized Collatz / Hailstone Parity Sequence
            // Seed = 13: n/2 if even, (n-1)/2 + 13 if odd (20-state closed orbit via 16->8->4->2->1)
            5'h08: rom_data = 8'h1D; // LDI 13       (ACC = 13)
            5'h09: rom_data = 8'h82; // MOV R1, ACC  (R1 = 13)
            5'h0A: rom_data = 8'hB0; // OUT          (Publish current Hailstone value)
            5'h0B: rom_data = 8'h81; // SHR          (ACC = ACC >> 1, C = parity bit ACC[0])
            5'h0C: rom_data = 8'hE6; // JC  6        (If odd, jump to 6)
            5'h0D: rom_data = 8'hC2; // JMP 2        (If even, loop back to OUT at 2)
            5'h0E: rom_data = 8'h40; // ADD          (Odd branch: ACC = (n-1)/2 + 13)
            5'h0F: rom_data = 8'hC2; // JMP 2        (Loop back to OUT at 2)

            // Bank 2 (prog_sel = 2'b10): 8-bit XOR-Shift + Weyl PRNG Pattern Generator
            // Seed = 0xA5: outputs 0xF6, 0x21, 0x6A, 0xC5, 0x56, ...
            5'h10: rom_data = 8'h15; // LDI 5        (ACC = 0x05)
            5'h11: rom_data = 8'h2A; // LUI 10       (ACC = 0xA5)
            5'h12: rom_data = 8'h82; // MOV R1, ACC  (R1 = ACC)
            5'h13: rom_data = 8'h80; // SHL          (ACC = ACC << 1)
            5'h14: rom_data = 8'h70; // XOR          (ACC = (ACC << 1) ^ R1)
            5'h15: rom_data = 8'h37; // ADDI 7       (ACC = ACC + 7)
            5'h16: rom_data = 8'hB0; // OUT          (Publish pseudo-random byte)
            5'h17: rom_data = 8'hC2; // JMP 2        (Next PRNG state)

            // Bank 3 (prog_sel = 2'b11): Interactive User-Input Step Accumulator
            // Increments by +1 when ui_in[6]=0, or +2 when ui_in[6]=1
            5'h18: rom_data = 8'h10; // LDI 0        (ACC = 0)
            5'h19: rom_data = 8'h82; // MOV R1, ACC  (R1 = 0)
            5'h1A: rom_data = 8'hA1; // IN  1        (ACC = 1 + user_in)
            5'h1B: rom_data = 8'h40; // ADD          (ACC = ACC + R1)
            5'h1C: rom_data = 8'h82; // MOV R1, ACC  (R1 = new total)
            5'h1D: rom_data = 8'hB0; // OUT          (Publish total to OUT)
            5'h1E: rom_data = 8'hC2; // JMP 2        (Loop to read input again)
            5'h1F: rom_data = 8'h00; // NOP
            default: rom_data = 8'h00;
        endcase
    end

    // -------------------------------------------------------------------------
    // Instruction Fetch and Single-Step Control
    // -------------------------------------------------------------------------
    wire [7:0] instr      = ext_mode ? uio_in : rom_data;
    wire [3:0] opcode     = instr[7:4];
    wire [3:0] imm        = instr[3:0];
    wire       step_pulse = step_trig & ~step_prev;
    wire       cpu_step   = ~step_en | step_pulse;
    wire       prog_chg   = ~ext_mode & (prog_sel != prev_prog);

    // -------------------------------------------------------------------------
    // Combinational ALU Helpers
    // -------------------------------------------------------------------------
    wire [8:0] sum_imm = {1'b0, acc} + {5'd0, imm};
    wire [8:0] sum_r1  = {1'b0, acc} + {1'b0, r1};
    wire [8:0] sub_r1  = {1'b0, acc} - {1'b0, r1};
    wire [7:0] and_r1  = acc & r1;
    wire [7:0] xor_r1  = acc ^ r1;
    wire [7:0] shl_acc = {acc[6:0], 1'b0};
    wire [7:0] shr_acc = {1'b0, acc[7:1]};
    wire [7:0] in_val  = {4'h0, imm} + {7'd0, user_in};

    // -------------------------------------------------------------------------
    // Sequential Execution Pipeline
    // -------------------------------------------------------------------------
    always @(posedge clk) begin
        if (!rst_n) begin
            pc        <= 3'd0;
            acc       <= 8'd0;
            r1        <= 8'd0;
            out_reg   <= 8'd0;
            flag_z    <= 1'b0;
            flag_c    <= 1'b0;
            step_prev <= 1'b0;
            prev_prog <= prog_sel;
        end else begin
            step_prev <= step_trig;
            prev_prog <= prog_sel;

            if (prog_chg) begin
                pc      <= 3'd0;
                acc     <= 8'd0;
                r1      <= 8'd0;
                out_reg <= 8'd0;
                flag_z  <= 1'b0;
                flag_c  <= 1'b0;
            end else if (cpu_step) begin
                pc <= pc + 3'd1;

                case (opcode)
                    4'h0: begin // NOP
                    end
                    4'h1: begin // LDI imm4
                        acc    <= {4'h0, imm};
                        flag_z <= (imm == 4'h0);
                    end
                    4'h2: begin // LUI imm4
                        acc    <= {imm, acc[3:0]};
                        flag_z <= ({imm, acc[3:0]} == 8'h00);
                    end
                    4'h3: begin // ADDI imm4
                        acc    <= sum_imm[7:0];
                        flag_c <= sum_imm[8];
                        flag_z <= (sum_imm[7:0] == 8'h00);
                    end
                    4'h4: begin // ADD (ACC + R1)
                        acc    <= sum_r1[7:0];
                        flag_c <= sum_r1[8];
                        flag_z <= (sum_r1[7:0] == 8'h00);
                    end
                    4'h5: begin // SUB (ACC - R1)
                        acc    <= sub_r1[7:0];
                        flag_c <= sub_r1[8];
                        flag_z <= (sub_r1[7:0] == 8'h00);
                    end
                    4'h6: begin // AND (ACC & R1)
                        acc    <= and_r1;
                        flag_z <= (and_r1 == 8'h00);
                    end
                    4'h7: begin // XOR (ACC ^ R1)
                        acc    <= xor_r1;
                        flag_z <= (xor_r1 == 8'h00);
                    end
                    4'h8: begin // SHIFT / MOV
                        case (imm[1:0])
                            2'b00: begin // SHL
                                acc    <= shl_acc;
                                flag_c <= acc[7];
                                flag_z <= (shl_acc == 8'h00);
                            end
                            2'b01: begin // SHR
                                acc    <= shr_acc;
                                flag_c <= acc[0];
                                flag_z <= (shr_acc == 8'h00);
                            end
                            2'b10: begin // MOV R1, ACC
                                r1 <= acc;
                            end
                            2'b11: begin // MOV ACC, R1
                                acc    <= r1;
                                flag_z <= (r1 == 8'h00);
                            end
                        endcase
                    end
                    4'h9: begin // SWAP (ACC <-> R1)
                        acc <= r1;
                        r1  <= acc;
                    end
                    4'hA: begin // IN imm4 (ACC = imm4 + user_in)
                        acc    <= in_val;
                        flag_z <= (in_val == 8'h00);
                    end
                    4'hB: begin // OUT (OUT = ACC)
                        out_reg <= acc;
                    end
                    4'hC: begin // JMP addr3
                        pc <= imm[2:0];
                    end
                    4'hD: begin // JZ addr3
                        if (flag_z) pc <= imm[2:0];
                    end
                    4'hE: begin // JC addr3
                        if (flag_c) pc <= imm[2:0];
                    end
                    4'hF: begin // JNZ addr3
                        if (!flag_z) pc <= imm[2:0];
                    end
                    default: begin
                    end
                endcase
            end
        end
    end

    // -------------------------------------------------------------------------
    // Hardware Debug Unit & Hexadecimal 7-Segment Decoder
    // -------------------------------------------------------------------------
    reg [3:0] dbg_nibble;
    always @(*) begin
        case (dbg_sel)
            2'b00:   dbg_nibble = out_reg[3:0];
            2'b01:   dbg_nibble = out_reg[7:4];
            2'b10:   dbg_nibble = acc[3:0];
            2'b11:   dbg_nibble = {1'b0, pc};
            default: dbg_nibble = out_reg[3:0];
        endcase
    end

    reg [6:0] seg7; // {g, f, e, d, c, b, a} active-high
    always @(*) begin
        case (dbg_nibble)
            4'h0: seg7 = 7'b0111111; // 0x3F
            4'h1: seg7 = 7'b0000110; // 0x06
            4'h2: seg7 = 7'b1011011; // 0x5B
            4'h3: seg7 = 7'b1001111; // 0x4F
            4'h4: seg7 = 7'b1100110; // 0x66
            4'h5: seg7 = 7'b1101101; // 0x6D
            4'h6: seg7 = 7'b1111101; // 0x7D
            4'h7: seg7 = 7'b0000111; // 0x07
            4'h8: seg7 = 7'b1111111; // 0x7F
            4'h9: seg7 = 7'b1101111; // 0x6F
            4'hA: seg7 = 7'b1110111; // 0x77
            4'hB: seg7 = 7'b1111100; // 0x7C
            4'hC: seg7 = 7'b0111001; // 0x39
            4'hD: seg7 = 7'b1011110; // 0x5E
            4'hE: seg7 = 7'b1111001; // 0x79
            4'hF: seg7 = 7'b1110001; // 0x71
            default: seg7 = 7'b0000000;
        endcase
    end

    // -------------------------------------------------------------------------
    // Output Assignments
    // -------------------------------------------------------------------------
    assign uo_out  = {flag_c, seg7};
    assign uio_out = out_reg;
    assign uio_oe  = ext_mode ? 8'h00 : 8'hFF;

    // List all unused inputs to prevent linter warnings
    wire _unused = &{ena, 1'b0};

endmodule
