# TT-RISC8 — Micro-CPU RISC de 8 bits con ROM y Unidad de Debug (Tiny Tapeout TTGF26c)

Diseño digital en Verilog para una celda **`1x1`** en la lanzadera **GlobalFoundries 180nm MCU (`TTGF26c` / `gf180mcuD`, biblioteca `gf180mcu_fd_sc_mcu7t5v0`)**.

- **Autor:** Orlando Arturo Palma León ([@Orlando-Palma](https://github.com/Orlando-Palma))
- **Módulo superior (`top_module`):** `tt_um_orlando_palma_risc8`
- **Área:** `1x1` tile ($\approx 340\,\mu\text{m} \times 160\,\mu\text{m}$, 32 Flip-Flops en total)
- **Frecuencia objetivo:** 50 MHz (`CLOCK_PERIOD = 20 ns`)

---

## Características principales

1. **Arquitectura RISC de 8 bits de ciclo único:**
   - Registros internos: Contador de Programa `PC[2:0]`, Acumulador `ACC[7:0]`, Registro Auxiliar `R1[7:0]`, Registro de Salida `OUT[7:0]` y banderas de estado `Z` (Cero) y `C` (Acarreo/Préstamo).
   - **16 instrucciones de 8 bits (`[7:4]` opcode, `[3:0]` inmediato/operando):** `NOP`, `LDI`, `LUI`, `ADDI`, `ADD`, `SUB`, `AND`, `XOR`, `SHL`, `SHR`, `MOV`, `SWAP`, `IN`, `OUT`, `JMP`, `JZ`, `JC`, `JNZ`.
2. **ROM interna de 32×8 bits con 4 programas seleccionables por `ui_in[1:0]`:**
   - `00`: **Sucesión de Fibonacci de 8 bits** (`1, 1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233`) con reinicio automático al detectar desbordamiento (`JC 0`).
   - `01`: **Secuencia de Collatz / Hailstone por paridad** ($n/2$ si es par, $(n-1)/2 + 13$ si es impar; órbita cerrada de 20 estados pasando por `16 -> 8 -> 4 -> 2 -> 1`).
   - `10`: **Generador Pseudoaleatorio (PRNG) XOR-Shift + Weyl de 8 bits** (`0xF6, 0x21, 0x6A, 0xC5, 0x56...`).
   - `11`: **Acumulador interactivo controlado por usuario (`IN`)** que suma `+1` o `+2` según el interruptor `ui_in[6]`.
3. **Unidad de Debug en hardware para Display de 7 Segmentos (`uo_out[7:0]`):**
   - Decodificador Hexadecimal completo (`0`–`9`, `A`–`F`) con selector en tiempo real (`ui_in[5:4]`) para inspeccionar `OUT[3:0]`, `OUT[7:4]`, `ACC[3:0]` o `PC[2:0]`, más indicador de bandera de acarreo `C` en el punto decimal (`uo_out[7]`).
   - **Modo Paso a Paso (`ui_in[2]=1`):** Congela el procesador y ejecuta exactamente 1 instrucción por cada flanco de subida `0 -> 1` en `ui_in[3]`.
4. **Modo de Bus Externo de Instrucciones (`ui_in[7]=1`):**
   - Conmuta el puerto bidireccional `uio[7:0]` a modo entrada (`uio_oe = 8'h00`) para inyectar programas arbitrarios desde el RP2040 de la tarjeta de pruebas.

---

## Estructura del repositorio (`ttgf-verilog-template`)

- [`src/project.v`](src/project.v): Implementación RTL en Verilog-2005 del módulo `tt_um_orlando_palma_risc8`.
- [`src/config.json`](src/config.json): Configuración de síntesis y ruteo en LibreLane para `gf180mcuD`.
- [`info.yaml`](info.yaml): Metadatos del proyecto y asignación de los 26 pines para TTGF26c.
- [`docs/info.md`](docs/info.md): Hoja de datos completa (arquitectura, tabla ISA y guía de pruebas).
- [`test/tb.v`](test/tb.v) y [`test/test.py`](test/test.py): Banco de pruebas automatizado en `cocotb` que verifica los 4 programas de la ROM, el decodificador de 7 segmentos, el modo paso a paso y la ejecución de instrucciones externas.
