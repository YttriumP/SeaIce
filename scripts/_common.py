#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脚本共用工具：路径、打印、读 SIE、写 NetCDF。**不放科学口径**（口径在 glossary.md）。"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import xarray as xr

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "out"
FIG = ROOT / "figs"


def banner(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def read_sie(path: Path | None = None) -> tuple[np.ndarray, np.ndarray]:
    """读 9 月 SIE 年序列，返回 (year, sie_1e6km2)。"""
    with open(path or OUT / "sie_sep.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return (np.array([int(r["year"]) for r in rows]),
            np.array([float(r["sie_1e6km2"]) for r in rows]))


def save_nc(ds: xr.Dataset, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    ds.to_netcdf(path, mode="w")
    print(f"[输出] {path}（{path.stat().st_size / 1e6:.1f} MB）")
    return path
