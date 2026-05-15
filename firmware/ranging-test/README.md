# ranging-test — Phase 1.0 bring-up app

A freestanding Zephyr application that initialises the DW3110 inside
each DWM3001CDK and (eventually) runs DS-TWR ranging between two
boards. It is the first hardware-validation app — once it prints the
expected DW3110 device ID (`0xDECA0302`), the entire hardware path
(board overlay → SPI3 → CS/IRQ/RESET pins → driver → chip) is proven,
and the remaining work is application logic.

## Dependencies

This app depends on **`br101/zephyr-dw3000-decadriver`** — Bruno
Randolf's ISC-licensed Zephyr port of Qorvo's official DW3000 driver.
Clone it into the NCS workspace once:

```bash
git clone https://github.com/br101/zephyr-dw3000-decadriver.git \
  ~/ncs/v3.3.0/modules/lib/zephyr-dw3000-decadriver
```

The underlying Qorvo driver source (in
`dwt_uwb_driver/`) ships under Qorvo's proprietary licence
(`LicenseRef-QORVO-2`) — preserved on those files. Bruno's wrapper
and our application code remain Apache-2.0.

## Build

```bash
nrfutil toolchain-manager launch --ncs-version v3.3.0 \
  --chdir ~/ncs/v3.3.0 -- west build -p \
  -b decawave_dwm3001cdk/nrf52833 \
  $PWD/firmware/ranging-test -d /tmp/is_ranging_test \
  -- -DZEPHYR_EXTRA_MODULES=$HOME/ncs/v3.3.0/modules/lib/zephyr-dw3000-decadriver
```

## Flash

```bash
nrfutil toolchain-manager launch --ncs-version v3.3.0 \
  --chdir ~/ncs/v3.3.0 -- west flash --build-dir /tmp/is_ranging_test
```

Connect to the J-Link VCOM serial port at 115200 baud to see the boot
output.

## Layout

| File | Purpose |
|---|---|
| `CMakeLists.txt` | Zephyr app skeleton |
| `prj.conf` | Enables SPI, GPIO, the DW3000 driver, logging |
| `boards/decawave_dwm3001cdk_nrf52833.overlay` | Adds the DW3110 as a child of `&spi3`; pins IRQ to P1.2, RESET to P0.25, WAKEUP to P1.19 (per the DWM3001C internal wiring) |
| `src/main.c` | Bring-up smoke test — driver init, reset, device ID read |

## Status

- **Build:** passes, links cleanly against the driver and our overlay.
- **Runtime:** `dw3000_hw_init()` succeeds; `dw3000_hw_reset()`
  currently triggers an MPU instruction-access fault — under
  investigation. The driver is parsing the overlay correctly (pins
  log out with the right numbers); the fault is somewhere in the
  reset path.

This app will grow into the actual DS-TWR ranging test (initiator
on one board, responder on the other, ranges printed over UART) once
the bring-up smoke test passes.
