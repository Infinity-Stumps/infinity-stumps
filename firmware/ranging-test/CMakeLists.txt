# Copyright (c) 2026 Infinity Stumps
# SPDX-License-Identifier: Apache-2.0
#
# Phase 1.0 firmware-bringup app: initialise the DW3110 and read its
# device ID over SPI. This is the smoke test for the whole hardware
# stack (board overlay, SPI bus, br101's DW3000 Zephyr driver). Once
# this prints the expected ID, full DS-TWR ranging is just app logic.

cmake_minimum_required(VERSION 3.20.0)
find_package(Zephyr REQUIRED HINTS $ENV{ZEPHYR_BASE})
project(ranging_test LANGUAGES C)

target_sources(app PRIVATE src/main.c)
