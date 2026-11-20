# SPDX-FileCopyrightText: © 2026 Orlando Arturo Palma Leon
# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

# Hexadecimal (0x0 - 0xF) to 7-segment pattern {g, f, e, d, c, b, a}
SEG7_HEX = {
    0x0: 0x3F,
    0x1: 0x06,
    0x2: 0x5B,
    0x3: 0x4F,
    0x4: 0x66,
    0x5: 0x6D,
    0x6: 0x7D,
    0x7: 0x07,
    0x8: 0x7F,
    0x9: 0x6F,
    0xA: 0x77,
    0xB: 0x7C,
    0xC: 0x39,
    0xD: 0x5E,
    0xE: 0x79,
    0xF: 0x71,
}


async def reset_cpu(dut, ui_val=0):
    dut.ena.value = 1
    dut.ui_in.value = ui_val
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 1)


@cocotb.test()
async def test_prog0_fibonacci_and_7seg_debug(dut):
    """Verify Program 0 (8-bit Fibonacci sequence in ROM) and 7-segment Debug Unit."""
    dut._log.info("Start Program 0: Fibonacci & 7-Segment Debug test")
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # prog_sel = 00, step_en = 0, dbg_sel = 00 (OUT[3:0]), ext_mode = 0
    await reset_cpu(dut, ui_val=0x00)
    assert int(dut.uio_oe.value) == 0xFF, "uio_oe must be 0xFF in internal ROM mode"

    expected_fib = [1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233]
    observed_fib = []

    # After reset (Wait 1 cycle after rst_n=1 means PC=0 executed at that edge, or let's sample every cycle)
    # In Program 0:
    # PC=0: LDI 0
    # PC=1: MOV R1, ACC
    # PC=2: LDI 1
    # PC=3: ADD
    # PC=4: JC 0
    # PC=5: OUT  <-- updates uio_out every 5 cycles in the loop (3->4->5->6->7)
    # PC=6: SWAP
    # PC=7: JMP 3
    # Let's step cycle-by-cycle and record OUT whenever PC=5 finishes
    await reset_cpu(dut, ui_val=0x00)
    # Wait 5 cycles so PC=0, 1, 2, 3, 4 have executed and PC is at 5 (OUT)
    await ClockCycles(dut.clk, 5)

    for expected in expected_fib:
        # Next cycle executes PC=5 (OUT) and updates uio_out
        await ClockCycles(dut.clk, 1)
        out_val = int(dut.uio_out.value)
        observed_fib.append(out_val)
        assert out_val == expected, f"Fibonacci mismatch: got {out_val}, expected {expected}"

        # Check 7-segment display low nibble (dbg_sel = 00)
        seg_lo = int(dut.uo_out.value) & 0x7F
        assert seg_lo == SEG7_HEX[expected & 0x0F], (
            f"7-seg low nibble mismatch for 0x{expected:02X}: got 0x{seg_lo:02X}"
        )

        # Advance 4 cycles (PC=6 SWAP, PC=7 JMP 3, PC=3 ADD, PC=4 JC 0)
        await ClockCycles(dut.clk, 4)

    dut._log.info(f"Verified all 13 Fibonacci numbers: {observed_fib}")

    # On the 14th iteration (144 + 233 = 377 > 255), ADD at PC=3 sets Carry flag (uo_out[7] == 1)
    # and JC 0 at PC=4 jumps back to PC=0 to restart the sequence!
    # Wait for PC=0, 1, 2, 3, 4, 5 (6 cycles) and verify OUT restarts at 1
    await ClockCycles(dut.clk, 6)
    assert int(dut.uio_out.value) == 1, "Fibonacci did not auto-restart at 1 after 8-bit overflow"


@cocotb.test()
async def test_prog1_collatz_hailstone(dut):
    """Verify Program 1 (Generalized Collatz / Hailstone parity sequence in ROM)."""
    dut._log.info("Start Program 1: Collatz / Hailstone sequence test")
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # prog_sel = 01 (Program 1)
    await reset_cpu(dut, ui_val=0x01)

    # Expected Hailstone orbit from seed 13: n/2 if even, (n-1)/2 + 13 if odd
    expected_collatz = [13, 19, 22, 11, 18, 9, 17, 21, 23, 24, 12, 6, 3, 14, 7, 16, 8, 4, 2, 1, 13]
    seen = []

    # Run enough cycles to collect the 21 values as uio_out changes
    prev_val = int(dut.uio_out.value)
    for _ in range(120):
        await ClockCycles(dut.clk, 1)
        cur_val = int(dut.uio_out.value)
        if cur_val != prev_val and cur_val != 0:
            seen.append(cur_val)
            prev_val = cur_val
            if len(seen) == len(expected_collatz):
                break

    assert seen == expected_collatz, f"Collatz sequence mismatch:\nGot:      {seen}\nExpected: {expected_collatz}"
    dut._log.info(f"Verified 20-state closed Hailstone orbit: {seen}")


@cocotb.test()
async def test_prog2_prng_xorshift(dut):
    """Verify Program 2 (8-bit XOR-Shift + Weyl PRNG in ROM) and high/low 7-seg nibbles."""
    dut._log.info("Start Program 2: PRNG test")
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # prog_sel = 10 (Program 2)
    await reset_cpu(dut, ui_val=0x02)

    expected_prng = [0xF6, 0x21, 0x6A, 0xC5, 0x56]
    seen = []
    prev_val = 0

    for _ in range(40):
        await ClockCycles(dut.clk, 1)
        cur_val = int(dut.uio_out.value)
        if cur_val != prev_val and cur_val != 0:
            seen.append(cur_val)
            prev_val = cur_val
            if len(seen) == len(expected_prng):
                break

    assert seen == expected_prng, f"PRNG sequence mismatch: got {[hex(x) for x in seen]}"

    # Test 7-segment high nibble selector (dbg_sel = 01 -> ui_in[5:4] = 01 -> 0x10) on 0x56
    dut.ui_in.value = 0x02 | 0x04 | 0x10  # prog_sel=10, step_en=1 (pause), dbg_sel=01 (OUT[7:4])
    await ClockCycles(dut.clk, 2)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0x5], "7-seg high nibble failed for 0x56"

    # Test 7-segment low nibble selector (dbg_sel = 00 -> OUT[3:0]) on 0x56
    dut.ui_in.value = 0x02 | 0x04 | 0x00  # prog_sel=10, step_en=1 (pause), dbg_sel=00 (OUT[3:0])
    await ClockCycles(dut.clk, 2)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0x6], "7-seg low nibble failed for 0x56"


@cocotb.test()
async def test_prog3_user_input_and_single_step(dut):
    """Verify Program 3 (User Input IN instruction) and Single-Step Hardware Debugger."""
    dut._log.info("Start Program 3: User Input & Single-Step test")
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # Start in Single-Step mode (step_en = 1 -> bit 2 = 0x04), prog_sel = 11 (0x03), dbg_sel = 11 (PC -> 0x30)
    base_ui = 0x03 | 0x04 | 0x30
    dut.ena.value = 1
    dut.ui_in.value = base_ui
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)

    # Because step_en = 1 and step_trig = 0, PC must remain frozen at 0 even after 5 clock cycles!
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0], "CPU did not stay paused at PC=0 in single-step mode"

    async def pulse_step(extra_flags=0):
        dut.ui_in.value = base_ui | extra_flags
        await ClockCycles(dut.clk, 1)
        dut.ui_in.value = base_ui | extra_flags | 0x08  # step_trig = 1 (rising edge)
        await ClockCycles(dut.clk, 1)
        dut.ui_in.value = base_ui | extra_flags         # step_trig = 0
        await ClockCycles(dut.clk, 1)

    # Step 1 instruction (executes PC=0: LDI 0 -> advances to PC=1)
    await pulse_step()
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[1], "Single-step did not advance PC to 1"

    # Step 1 instruction (executes PC=1: MOV R1, ACC -> advances to PC=2)
    await pulse_step()
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[2], "Single-step did not advance PC to 2"

    # Execute 1 full loop of Program 3 with USER_IN = 0 (ui_in[6] = 0 -> increments by +1):
    # PC=2 (IN 1), PC=3 (ADD), PC=4 (MOV R1, ACC), PC=5 (OUT), PC=6 (JMP 2)
    for _ in range(5):
        await pulse_step(extra_flags=0x00)
    assert int(dut.uio_out.value) == 1, f"Expected OUT=1 with USER_IN=0, got {int(dut.uio_out.value)}"

    # Execute next loop with USER_IN = 1 (ui_in[6] = 0x40 -> increments by +2, so 1 + 2 = 3):
    for _ in range(5):
        await pulse_step(extra_flags=0x40)
    assert int(dut.uio_out.value) == 3, f"Expected OUT=3 with USER_IN=1, got {int(dut.uio_out.value)}"


@cocotb.test()
async def test_external_instruction_bus_mode(dut):
    """Verify External Instruction Bus Mode (EXT_MODE=1) and remaining ISA instructions (SUB, AND, MOV, JZ, JNZ)."""
    dut._log.info("Start External Instruction Bus Mode test")
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    # EXT_MODE = 1 (bit 7 = 0x80), dbg_sel = 10 (ACC[3:0] -> 0x20)
    ext_ui = 0x80 | 0x20
    dut.ena.value = 1
    dut.ui_in.value = ext_ui
    dut.uio_in.value = 0x00  # NOP
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1

    # Verify bidirectional bus is in input mode (uio_oe == 0x00)
    await ClockCycles(dut.clk, 1)
    assert int(dut.uio_oe.value) == 0x00, "uio_oe must be 0x00 when EXT_MODE=1"

    async def exec_ext(opcode_byte):
        dut.uio_in.value = opcode_byte
        await ClockCycles(dut.clk, 1)

    # 1. LDI 0x0C (ACC = 12)
    await exec_ext(0x1C)
    await ClockCycles(dut.clk, 1)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0xC], "EXT LDI 0xC failed"

    # 2. MOV R1, ACC (0x82 -> R1 = 12)
    await exec_ext(0x82)
    # 3. LDI 0x05 (ACC = 5)
    await exec_ext(0x15)
    # 4. SWAP (0x90 -> ACC = 12, R1 = 5)
    await exec_ext(0x90)
    # 5. SUB (0x50 -> ACC = 12 - 5 = 7, Carry/Borrow = 0)
    await exec_ext(0x50)
    dut.uio_in.value = 0x00  # NOP while checking
    await ClockCycles(dut.clk, 1)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0x7], "EXT SUB (12 - 5 = 7) failed"
    assert (int(dut.uo_out.value) >> 7) == 0, "Carry/Borrow flag should be 0 for 12 - 5"

    # 6. AND (0x60 -> ACC = 7 & 5 = 5)
    await exec_ext(0x60)
    dut.uio_in.value = 0x00  # NOP
    await ClockCycles(dut.clk, 1)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0x5], "EXT AND (7 & 5 = 5) failed"

    # 7. MOV ACC, R1 (0x83 -> ACC = 5), then SUB (0x50 -> ACC = 5 - 5 = 0, Z = 1)
    await exec_ext(0x83)
    await exec_ext(0x50)
    # 8. JZ 5 (0xD5 -> since Z=1, PC jumps to 5)
    await exec_ext(0xD5)
    # Switch dbg_sel to 11 (PC) while paused in single-step mode to verify PC jumped to 5
    dut.ui_in.value = 0x80 | 0x30 | 0x04  # EXT_MODE=1, dbg_sel=11 (PC), step_en=1
    await ClockCycles(dut.clk, 2)
    assert (int(dut.uo_out.value) & 0x7F) == SEG7_HEX[0x5], "EXT JZ 5 did not set PC=5"
