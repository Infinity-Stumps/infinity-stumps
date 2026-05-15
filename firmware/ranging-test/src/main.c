/*
 * Copyright (c) 2026 Infinity Stumps
 * SPDX-License-Identifier: Apache-2.0
 *
 * Phase 1.0 firmware-bringup smoke test.
 *
 * Initialise the DW3110 over SPI via br101's Zephyr DW3000 driver,
 * read its 32-bit device ID, and print it on the console. A correct
 * read proves the whole hardware path works end to end: board
 * overlay, SPI3, CS/IRQ/RESET pins, the driver's platform layer.
 *
 * Expected device ID for the DW3110 on the DWM3001C: 0xDECA0302.
 */

#include <zephyr/kernel.h>
#include <zephyr/sys/printk.h>

#include <dw3000_hw.h>
#include <deca_device_api.h>

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
	k_sleep(K_MSEC(2));

	uint32_t devid = dwt_readdevid();
	printk("DW3110 device ID: 0x%08x  (expected 0xDECA0302)\n", devid);

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
