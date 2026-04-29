#!/usr/bin/env python3
"""
spearman.py — pure-stdlib Spearman rank correlation.

Used by calibrate.sh to measure the LLM-as-judge against hand-graded
calibration fixtures. Spearman is the Pearson correlation of the ranks;
ties resolve to average rank (the standard convention).

Usage:
    spearman.py <pairs.tsv>

The TSV has two whitespace-separated columns: judge_score human_score.
Each row is one fixture / dimension pair. spearman.py prints a single
floating-point number to stdout.
"""
from __future__ import annotations

import math
import statistics
import sys


def rank_with_ties(values: list[float]) -> list[float]:
    """Return ranks (1-indexed); ties get the average of the rank positions
    they would have occupied."""
    indexed = sorted(enumerate(values), key=lambda x: x[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        # Group consecutive equal values
        j = i
        while j + 1 < len(indexed) and indexed[j + 1][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # average of 1-indexed positions
        for k in range(i, j + 1):
            ranks[indexed[k][0]] = avg_rank
        i = j + 1
    return ranks


def pearson(xs: list[float], ys: list[float]) -> float:
    """Pearson correlation. Returns NaN when either input has zero variance."""
    n = len(xs)
    if n == 0 or n != len(ys):
        return float("nan")
    mx = statistics.fmean(xs)
    my = statistics.fmean(ys)
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx2 = sum((x - mx) ** 2 for x in xs)
    dy2 = sum((y - my) ** 2 for y in ys)
    denom = math.sqrt(dx2 * dy2)
    if denom == 0:
        return float("nan")
    return num / denom


def spearman(xs: list[float], ys: list[float]) -> float:
    return pearson(rank_with_ties(xs), rank_with_ties(ys))


def main(argv: list[str] | None = None) -> int:
    args = (argv if argv is not None else sys.argv[1:])
    if len(args) != 1:
        print("Usage: spearman.py <pairs.tsv>", file=sys.stderr)
        return 64
    xs, ys = [], []
    with open(args[0], encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            xs.append(float(parts[0]))
            ys.append(float(parts[1]))
    if len(xs) < 2:
        print("nan")
        return 0
    rho = spearman(xs, ys)
    if math.isnan(rho):
        print("nan")
    else:
        print(f"{rho:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
