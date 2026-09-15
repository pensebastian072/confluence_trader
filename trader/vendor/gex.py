"""Gamma-exposure toolkit — own Black-Scholes gamma (no SciPy). Pure functions.

A strike row is a dict: {strike, iv, t_years, call_oi, put_oi}. GEX per strike uses
the naive dealer convention (dealers short calls / long puts): call gamma adds,
put gamma subtracts. Zero-gamma flip = the spot where net GEX crosses zero. Max
pain = the strike minimising total option-holder intrinsic value at expiry. All
inputs guarded so bad rows contribute 0 rather than raising.
"""
from __future__ import annotations

import math

_SQRT_2PI = math.sqrt(2.0 * math.pi)
CONTRACT_MULT = 100


def norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_gamma(spot: float, strike: float, t_years: float, iv: float,
             r: float = 0.0) -> float:
    """Black-Scholes gamma. Returns 0 on any degenerate input."""
    if spot <= 0 or strike <= 0 or t_years <= 0 or iv <= 0:
        return 0.0
    vol_t = iv * math.sqrt(t_years)
    d1 = (math.log(spot / strike) + (r + 0.5 * iv * iv) * t_years) / vol_t
    return norm_pdf(d1) / (spot * vol_t)


def strike_gex(spot: float, row: dict) -> float:
    """Net gamma-exposure contribution of one strike (calls +, puts -), in
    $ per 1% move (spot^2 * 0.01 * gamma * OI * contract_mult)."""
    g = bs_gamma(spot, float(row.get("strike", 0)), float(row.get("t_years", 0)),
                 float(row.get("iv", 0)))
    scale = g * CONTRACT_MULT * spot * spot * 0.01
    return scale * (float(row.get("call_oi", 0)) - float(row.get("put_oi", 0)))


def total_gex(spot: float, chain: list[dict]) -> float:
    return sum(strike_gex(spot, row) for row in chain)


def zero_gamma(chain: list[dict], lo: float, hi: float, steps: int = 200) -> float | None:
    """Spot where net GEX flips sign, scanning [lo, hi]. None if no crossing."""
    if hi <= lo or not chain:
        return None
    prev_s = lo
    prev_g = total_gex(lo, chain)
    for i in range(1, steps + 1):
        s = lo + (hi - lo) * i / steps
        g = total_gex(s, chain)
        if prev_g == 0.0:
            return prev_s
        if (prev_g < 0) != (g < 0):
            # linear interpolate the crossing
            if g != prev_g:
                return prev_s + (s - prev_s) * (0.0 - prev_g) / (g - prev_g)
            return s
        prev_s, prev_g = s, g
    return None


def max_pain(chain: list[dict]) -> float | None:
    """Strike minimising total holder intrinsic value at expiry. None if empty."""
    strikes = sorted({float(r.get("strike", 0)) for r in chain if r.get("strike")})
    if not strikes:
        return None
    best_k, best_pay = None, None
    for k_star in strikes:
        pay = 0.0
        for r in chain:
            k = float(r.get("strike", 0))
            pay += float(r.get("call_oi", 0)) * max(0.0, k_star - k)
            pay += float(r.get("put_oi", 0)) * max(0.0, k - k_star)
        if best_pay is None or pay < best_pay:
            best_pay, best_k = pay, k_star
    return best_k


def oi_walls(chain: list[dict], n: int = 2) -> dict:
    """Top-n call and put OI strikes (resistance / support walls). OI is summed
    per strike across expiries so a strike never appears twice."""
    call_by: dict[float, float] = {}
    put_by: dict[float, float] = {}
    for r in chain:
        k = float(r.get("strike", 0))
        call_by[k] = call_by.get(k, 0.0) + float(r.get("call_oi", 0) or 0)
        put_by[k] = put_by.get(k, 0.0) + float(r.get("put_oi", 0) or 0)
    calls = sorted((k for k, v in call_by.items() if v > 0),
                   key=lambda k: call_by[k], reverse=True)
    puts = sorted((k for k, v in put_by.items() if v > 0),
                  key=lambda k: put_by[k], reverse=True)
    return {"call_walls": calls[:n], "put_walls": puts[:n]}
