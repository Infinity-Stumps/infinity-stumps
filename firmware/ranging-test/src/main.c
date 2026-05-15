/*
 * Copyright (c) 2026 Infinity Stumps
 * SPDX-License-Identifier: Apache-2.0
 *
 * Phase 1.0 firmware-bringup smoke test.
 *
 * Initialise the DW3110 over SPI via br101's Zephyr DW3000 driver,
 * walk it through the canonical Qorvo init sequence
 * (hw reset -> dwt_probe -> wait for IDLE_RC -> dwt_initialise),
 * then read the chip's 32-bit device ID. A correct read proves the
 * whole hardware path works end to end: board overlay, SPI3,
 * CS/IRQ/RESET pins, the driver's platform layer, the Qorvo API.
 *
 * Expected device ID for the DW3110 on the DWM3001C: 0xDECA0302.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <dw3000_hw.h>
#include <deca_device_api.h>
#include <deca_probe_interface.h>

int main(void)
{
	printk("\n=== Infinity Stumps ranging-test ===\n");
	printk("Board: %s\n", CONFIG_BOARD);

	printk("dw3000_hw_init... ");
	int ret = dw3000_hw_init();
	if (ret < 0) {
		printk("FAILED (%d)\n", ret);
		return ret;
	}
	printk("OK\n");

	printk("dw3000_hw_reset...\n");
	dw3000_hw_reset();
	k_msleep(2);

	printk("dwt_probe...\n");
	int32_t rc = dwt_probe((struct dwt_probe_s *)&dw3000_probe_interf);
	printk("  -> %d\n", rc);

	printk("waiting for IDLE_RC...\n");
	int timeout_ms = 200;
	while (!dwt_checkidlerc() && timeout_ms-- > 0) {
		k_msleep(1);
	}
	if (timeout_ms <= 0) {
		printk("  TIMEOUT — chip didn't reach IDLE_RC state\n");
	} else {
		printk("  IDLE_RC reached\n");

		printk("dwt_initialise... ");
		if (dwt_initialise(DWT_DW_INIT) == DWT_ERROR) {
			printk("FAILED\n");
		} else {
			printk("OK\n");
		}
	}

	uint32_t devid = dwt_readdevid();
	printk("\nDW3110 device ID: 0x%08x  (expected 0xDECA0302)\n", devid);

	if (devid == 0xDECA0302) {
		printk("PASS — chip is talking to us.\n");
	} else {
		printk("FAIL — unexpected ID, check wiring / overlay.\n");
	}

	while (1) {
		k_sleep(K_SECONDS(10));
	}

	return 0;
}
