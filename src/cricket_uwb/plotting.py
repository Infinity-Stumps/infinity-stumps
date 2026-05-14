"""Shared plot helpers."""

from __future__ import annotations
import numpy as np
from numpy.typing import NDArray
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from .geometry import ANCHORS_8, PITCH_HL, STUMP_W, STUMP_HEIGHT


def draw_pitch_topdown(ax, anchors=ANCHORS_8, show_anchor_labels=True):
    ax.set_aspect("equal")
    ax.add_patch(patches.Rectangle((-PITCH_HL, -1.525), 2*PITCH_HL, 3.05,
                                    facecolor="#d4a574", alpha=0.3))
    for x_end in [-PITCH_HL, PITCH_HL]:
        ax.add_patch(patches.Rectangle((x_end-0.03, -STUMP_W/2),
                                        0.06, STUMP_W, color="saddlebrown"))
    ax.scatter(anchors[:, 0], anchors[:, 1],
               c=anchors[:, 2], cmap="viridis", s=120,
               edgecolors="k", zorder=5)
    if show_anchor_labels:
        for i, a in enumerate(anchors):
            ax.annotate(f"A{i+1}", (a[0], a[1]),
                        textcoords="offset points", xytext=(8, 6), fontsize=8)
    ax.set_xlim(-12, 12); ax.set_ylim(-3, 3)
    ax.set_xlabel("X along pitch (m)"); ax.set_ylabel("Y across pitch (m)")
    ax.grid(alpha=0.3)


def draw_pitch_sideview(ax, anchors=ANCHORS_8):
    ax.scatter(anchors[:, 0], anchors[:, 2], s=120, c="steelblue",
               edgecolors="k", zorder=5)
    for x_end in [-PITCH_HL, PITCH_HL]:
        ax.plot([x_end, x_end], [0, STUMP_HEIGHT], color="saddlebrown", lw=3)
    ax.axhline(0, color="#8b6f47", lw=2)
    ax.set_xlim(-12, 12); ax.set_ylim(-0.2, 3)
    ax.set_xlabel("X along pitch (m)"); ax.set_ylabel("Z height (m)")
    ax.grid(alpha=0.3)
