<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

**TT-RISC8** (`tt_um_orlando_palma_risc8`) is a single-cycle 8-bit RISC microprocessor designed specifically to fit within a single `1x1` tile on the **GlobalFoundries 180nm MCU (`gf180mcuD` / `TTGF26c`)** shuttle. It combines a 16-instruction RISC datapath, a 32x8-bit internal program ROM containing four demonstration algorithms, an external instruction injection bus, a single-step hardware clock controller, and a real-time hexadecimal 7-segment hardware debug unit.

### 1. Microarchitecture and Register File

To achieve optimal placement density (~32 flip-flops total) in `gf180mcu_fd_sc_mcu7t5v0` without routing congestion, the CPU employs an accumulator-register RISC architecture with the following synchronous state registers:

* **`PC[2:0]` (3 bits):** Program Counter addressing 8 instructions (`0..7`) within the active ROM program bank selected by `PROG_SEL[1:0]` (`rom_addr = {PROG_SEL, PC}`). Automatically resets to `0` when `rst_n` is asserted low or whenever `PROG_SEL[1:0]` is changed.
* **`ACC[7:0]` (8 bits):** Primary 8-bit arithmetic/logic accumulator.
* **`R1[7:0]` (8 bits):** Auxiliary 8-bit working register and second ALU operand.
* **`OUT[7:0]` (8 bits):** Dedicated output latch updated by the `OUT` instruction (`0xB0`), continuously driven onto `uio_out[7:0]` in internal ROM mode and inspectable in hexadecimal on the 7-segment display.
* **`FLAG_Z` and `FLAG_C` (2 bits):** Zero (`Z`) and Carry/Borrow (`C`) status flags updated by arithmetic and shift operations. `FLAG_C` is also routed directly to the 7-segment decimal point (`uo_out[7]`).
* **`STEP_PREV` and `PREV_PROG[1:0]` (3 bits):** Edge detector for single-step execution (`STEP_TRIG`) and program-switch auto-reset detector.

### 2. Instruction Set Architecture (8-bit Encoding)

Each instruction is 8 bits wide: **`[7:4]` Opcode** and **`[3:0]` Immediate / Operand (`imm4`)**:

| Opcode | Mnemonic | Encoding | RTL Operation | Flags Updated |
| :---: | :--- | :---: | :--- | :---: |
| `0x0` | `NOP` | `0000_0000` | No operation (`PC <= PC + 1`) | — |
| `0x1` | `LDI imm4` | `0001_iiii` | `ACC <= {4'h0, imm4}` | `Z` |
| `0x2` | `LUI imm4` | `0010_iiii` | `ACC <= {imm4, ACC[3:0]}` | `Z` |
| `0x3` | `ADDI imm4` | `0011_iiii` | `{C, ACC} <= ACC + imm4` | `Z, C` |
| `0x4` | `ADD` | `0100_0000` | `{C, ACC} <= ACC + R1` | `Z, C` |
| `0x5` | `SUB` | `0101_0000` | `{C, ACC} <= ACC - R1` | `Z, C` |
| `0x6` | `AND` | `0110_0000` | `ACC <= ACC & R1` | `Z` |
| `0x7` | `XOR` | `0111_0000` | `ACC <= ACC ^ R1` | `Z` |
| `0x8` | `SHL` | `1000_0000` | `{C, ACC} <= {ACC, 1'b0}` | `Z, C` |
| `0x8` | `SHR` | `1000_0001` | `{ACC, C} <= {1'b0, ACC}` | `Z, C` |
| `0x8` | `MOV R1, ACC`| `1000_0010` | `R1 <= ACC` | — |
| `0x8` | `MOV ACC, R1`| `1000_0011` | `ACC <= R1` | `Z` |
| `0x9` | `SWAP` | `1001_0000` | `ACC <= R1; R1 <= ACC` | — |
| `0xA` | `IN imm4` | `1010_iiii` | `ACC <= imm4 + ui_in[6]` | `Z` |
| `0xB` | `OUT` | `1011_0000` | `OUT <= ACC` | — |
| `0xC` | `JMP addr3` | `1100_0aaa` | `PC <= addr3` | — |
| `0xD` | `JZ addr3` | `1101_0aaa` | `if (Z == 1) PC <= addr3` | — |
| `0xE` | `JC addr3` | `1110_0aaa` | `if (C == 1) PC <= addr3` | — |
| `0xF` | `JNZ addr3` | `1111_0aaa` | `if (Z == 0) PC <= addr3` | — |

### 3. Built-in ROM Programs (`ui_in[1:0]`)

1. **Program `00` — 8-bit Fibonacci Sequence Generator:**
   Computes all 13 unsigned 8-bit Fibonacci numbers (`1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233 / 0xE9`) using `ADD`, `OUT`, and `SWAP`. Upon 8-bit carry overflow (`FLAG_C = 1`), `JC 0` automatically restarts the sequence from `1`.
2. **Program `01` — Generalized Collatz / Hailstone Parity Sequence:**
   Starting from seed `13` (`0x0D`), uses `SHR` to simultaneously divide by 2 and shift the parity bit (`ACC[0]`) into `FLAG_C`. If even (`C=0`), outputs $n/2$; if odd (`C=1`), branches via `JC` to compute $(n-1)/2 + 13$, traversing a 20-state closed Hailstone orbit (`13 -> 19 -> 22 -> 11 -> 18 -> 9 -> 17 -> 21 -> 23 -> 24 -> 12 -> 6 -> 3 -> 14 -> 7 -> 16 -> 8 -> 4 -> 2 -> 1 -> 13`).
3. **Program `10` — 8-bit XOR-Shift + Weyl PRNG:**
   Loads 8-bit seed `0xA5` via `LDI 5` + `LUI 10`, and iterates `((ACC << 1) ^ ACC) + 7` to generate a pseudo-random byte stream (`0xF6, 0x21, 0x6A, 0xC5, 0x56, ...`).
4. **Program `11` — Interactive User-Input Step Accumulator:**
   Executes `IN 1` (`ACC = 1 + ui_in[6]`) inside an accumulation loop, counting by `+1` when `ui_in[6] = 0` or by `+2` when `ui_in[6] = 1`.

---

## How to test

You can test **TT-RISC8** using only the Tiny Tapeout demo board switches, the integrated 7-segment display, and **Tiny Tapeout Commander** (no external PMODs required):

1. **Continuous Execution Mode (`ui_in[2] = 0`, `ui_in[7] = 0`):**
   * Set the board clock in Tiny Tapeout Commander to a slow human-visible frequency (e.g., `5 Hz` to `20 Hz`).
   * Select a ROM program with `ui_in[1:0]`:
     * `00`: Watch the Fibonacci sequence (`1, 1, 2, 3, 5, 8, D, 5, 2, 7, 9, 0, 9`) on the 7-segment display and full 8-bit values on `uio_out[7:0]`.
     * `01`: Watch the Collatz/Hailstone parity trajectory.
     * `10`: Watch the pseudo-random byte sequence.
     * `11`: Toggle `ui_in[6]` (`USER_IN`) between `0` and `1` to change the counter increment between `+1` and `+2`.
2. **Hardware 7-Segment Debug Multiplexer (`ui_in[5:4]`):**
   * `00`: Displays low hex digit of the output register (`OUT[3:0]`).
   * `01`: Displays high hex digit of the output register (`OUT[7:4]`).
   * `10`: Displays low hex digit of the accumulator (`ACC[3:0]`).
   * `11`: Displays current Program Counter (`PC[2:0]`, `0`–`7`).
   * The decimal point (`uo_out[7]`) lights up whenever the ALU Carry flag (`FLAG_C`) is `1`.
3. **Single-Step Execution (`ui_in[2] = 1`):**
   * Set `ui_in[2] = 1` (`STEP_EN`) to pause the processor even while a high-speed clock (e.g., 50 MHz) is running.
   * Toggle `ui_in[3]` (`STEP_TRIG`) from `0 -> 1` to advance execution by **one instruction per pulse**, inspecting `PC`, `ACC`, and `OUT` via `ui_in[5:4]`.
4. **External Instruction Bus Mode (`ui_in[7] = 1`):**
   * Set `ui_in[7] = 1` (`EXT_MODE`). The bidirectional port switches to input mode (`uio_oe = 0x00`), allowing the on-board RP2040 microcontroller to feed arbitrary 8-bit instructions directly on `uio_in[7:0]`.

---

## External hardware

None required. The design uses the on-board 7-segment display (`uo_out[7:0]`), DIP switches (`ui_in[7:0]`), and RP2040 GPIO bridge (`uio[7:0]`) included on the Tiny Tapeout carrier board.
