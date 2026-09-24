#!/usr/bin/env python3
"""Deterministic synthetic traffic shared by RTL and mapped-netlist simulation."""
import hashlib
import json
from pathlib import Path


def xorshift(state):
    state ^= (state << 13) & 0xFFFFFFFF
    state ^= state >> 17
    state ^= (state << 5) & 0xFFFFFFFF
    return state & 0xFFFFFFFF


def generate(destination=Path("build/traces")):
    destination.mkdir(parents=True, exist_ok=True)
    traces = {}

    def add(name, words, description, seed=None, warmup=None):
        content = "".join(f"{w:04x}\n" for w in words)
        (destination / f"{name}.hex").write_text(content)
        traces[name] = dict(samples=len(words), seed=seed, warmup=warmup,
                            description=description,
                            sha256=hashlib.sha256(content.encode()).hexdigest())

    add("zero_activity", [0] * 8, "Constant zero following reset")
    localized = [((0xF000 if i & 1 else 0) | ((i >> 4) & 1)) for i in range(64)]
    localized += [j << (i * 4) for i in range(4) for j in range(16)]
    add("localized", localized, "Original localized nibble traffic")
    walking, words = 0xFFFF, []
    for i in range(16):
        walking ^= 1 << i
        words.append(walking)
    add("single_bit_walk", words, "One bit changes per cycle after inverted warm-up", warmup=0xFFFF)
    for seed in (0x12345678, 0xDEADBEEF, 0xCAFEBABE, 0x31415926):
        state, words = seed, []
        for _ in range(1024):
            state = xorshift(state)
            words.append(state & 0xFFFF)
        add(f"random_seed_{seed:08x}", words, "Independent-looking xorshift32 low words", seed)
    state, value, words = 0xA5A55A5A, 0, []
    for _ in range(1024):
        state = xorshift(state)
        # 68.75% holds, 25% single-bit updates, 6.25% whole-word replacements.
        if state & 15 == 15:
            value = (state >> 8) & 0xFFFF
        elif state & 3 == 0:
            value ^= 1 << ((state >> 8) & 15)
        words.append(value)
    add("correlated", words, "68.75% holds; 25% bit updates; 6.25% replacements (nominal branch probabilities)", 0xA5A55A5A)
    state, value, words = 0xB16B00B5, 0, []
    for i in range(1024):
        state = xorshift(state)
        # Alternate 32-cycle idle intervals and 32-cycle active bursts.
        if i % 64 >= 32:
            if i % 8 == 0:
                value = state & 0xFFFF
            else:
                nibble = (i // 64) % 4
                value = (value & ~(15 << (4 * nibble))) | ((state & 15) << (4 * nibble))
        words.append(value)
    add("bursty", words, "32-cycle holds / 32-cycle bursts; nibble updates and periodic replacements", 0xB16B00B5)
    (destination / "manifest.json").write_text(json.dumps(traces, indent=2) + "\n")
    return traces


if __name__ == "__main__":
    generate()
