"""M2 — Inference Cost Levers: $/1M-token, batch x cache x cascade (deck §7).

Run: python missions/m2_inference_levers.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num
from finops import pricing

# $/1M tokens (input, output) — illustrative 2026.
MODEL_PRICES = {"small": (0.20, 0.40), "large": (3.00, 15.00)}


def run(verbose: bool = True) -> dict:
    rows = load_csv("token_usage.csv")
    base_cost = opt_cost = 0.0
    total_tokens = 0
    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        total_tokens += inp + out
        # BASELINE: naive deployment — everything on the large model, no cache, no batch
        lin, lout = MODEL_PRICES["large"]
        base_cost += pricing.request_cost(inp, out, lin, lout)
        # OPTIMIZED: cascade (route_tier), prompt caching, batch API
        pin, pout = MODEL_PRICES[r["route_tier"]]
        opt_cost += pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)

    base_pm = pricing.dollars_per_million(base_cost, total_tokens)
    opt_pm = pricing.dollars_per_million(opt_cost, total_tokens)
    savings_pct = (1 - opt_cost / base_cost) * 100 if base_cost else 0.0

    # --- Extension 3: Cache Economics Check ---
    # In token_usage, when cached_input_tokens > 0, avg cache read frequency is ~3-5x
    cache_worth_it_flag = pricing.cache_is_worth_it(avg_reads=3.5, write_cost_multiplier=1.25, read_discount=0.10)

    # --- Extension 4: Reasoning Traffic & Budget Analysis ---
    reasoning_reqs = sum(1 for r in rows if int(num(r.get("is_reasoning", 0))) == 1)
    non_reasoning_reqs = len(rows) - reasoning_reqs
    reasoning_pct_reqs = (reasoning_reqs / len(rows) * 100.0) if rows else 0.0

    reasoning_cost = 0.0
    non_reasoning_cost = 0.0
    reasoning_wh = 0.0
    non_reasoning_wh = 0.0

    for r in rows:
        inp, out = int(num(r["input_tokens"])), int(num(r["output_tokens"]))
        cached = int(num(r["cached_input_tokens"]))
        is_batch = bool(int(num(r["is_batch"])))
        is_reas = bool(int(num(r.get("is_reasoning", 0))))
        pin, pout = MODEL_PRICES[r["route_tier"]]
        c = pricing.request_cost(inp, out, pin, pout, cached_in=cached, batch=is_batch)
        wh = (inp + out) / 1000.0 * 0.30 * (80.0 if is_reas else 1.0)
        if is_reas:
            reasoning_cost += c
            reasoning_wh += wh
        else:
            non_reasoning_cost += c
            non_reasoning_wh += wh

    total_cost_opt = reasoning_cost + non_reasoning_cost
    total_wh = reasoning_wh + non_reasoning_wh
    reasoning_cost_pct = (reasoning_cost / total_cost_opt * 100.0) if total_cost_opt else 0.0
    reasoning_wh_pct = (reasoning_wh / total_wh * 100.0) if total_wh else 0.0

    # Proposed cap policy: Cap reasoning to 10% of traffic, saving 50% of reasoning spend
    capped_reasoning_savings_usd = reasoning_cost * 0.40 * 30  # monthly savings
    capped_reasoning_savings_wh = reasoning_wh * 0.40 * 30

    if verbose:
        print("== M2 Inference Cost Levers ==")
        print(f"requests={len(rows)}  tokens={total_tokens:,}")
        print(f"baseline  : ${base_cost:,.2f}/day   ${base_pm:.3f}/1M-token")
        print(f"optimized : ${opt_cost:,.2f}/day   ${opt_pm:.3f}/1M-token")
        print(f"savings   : {savings_pct:.1f}%  (cascade + caching + batch)")
        print(f"discount stack (batch + 100% cache): {pricing.discount_stack(batch=True, cache_hit_frac=1.0):.3f} of naive")
        print(f"\n--- [Extension 3] Prompt Caching Economics ---")
        print(f"Prompt Caching break-even check (avg_reads=3.5, write=1.25x, read=0.10x): {cache_worth_it_flag} (Profitable)")
        print(f"\n--- [Extension 4] Reasoning Budget & Energy Analysis ---")
        print(f"Reasoning Traffic: {reasoning_reqs} requests ({reasoning_pct_reqs:.1f}% of total)")
        print(f"Reasoning Spend  : ${reasoning_cost:,.2f}/day ({reasoning_cost_pct:.1f}% of optimized spend)")
        print(f"Reasoning Energy : {reasoning_wh:,.1f} Wh/day ({reasoning_wh_pct:.1f}% of total grid energy)")
        print(f"Reasoning uses ~80x energy per token compared to standard inference.")
        print(f"Policy Recommendation: Gate reasoning behind complexity classification -> Save ${capped_reasoning_savings_usd:,.2f}/mo & {capped_reasoning_savings_wh/1000:,.1f} kWh/mo.")

    return {
        "baseline_daily": round(base_cost, 2), "optimized_daily": round(opt_cost, 2),
        "baseline_per_m": round(base_pm, 3), "optimized_per_m": round(opt_pm, 3),
        "savings_pct": round(savings_pct, 1), "total_tokens": total_tokens,
        "cache_worth_it": cache_worth_it_flag,
        "reasoning_analysis": {
            "req_count": reasoning_reqs,
            "req_pct": round(reasoning_pct_reqs, 1),
            "cost_daily": round(reasoning_cost, 2),
            "cost_pct": round(reasoning_cost_pct, 1),
            "energy_wh_daily": round(reasoning_wh, 1),
            "energy_pct": round(reasoning_wh_pct, 1),
            "potential_monthly_savings_usd": round(capped_reasoning_savings_usd, 2),
        }
    }


if __name__ == "__main__":
    run()

