"""M3 — Purchasing Strategy: break-even, tier choice, spot-checkpoint sim (deck §4).

Run: python missions/m3_purchasing.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from missions._common import load_csv, num, catalog_by_type
from finops import pricing

DAYS = 30


def run(verbose: bool = True) -> dict:
    jobs = load_csv("workloads.csv")
    cat = catalog_by_type()
    on_demand_monthly = optimized_monthly = 0.0
    recs = []
    for j in jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        interruptible = bool(int(num(j["interruptible"])))
        c = cat[gtype]
        gpu_hours = hpd * DAYS * ngpu
        od = num(c["on_demand_hr"])
        on_demand_cost = gpu_hours * od

        tier = pricing.recommend_tier(hpd, interruptible)
        if tier == "spot":
            sim = pricing.spot_checkpoint_cost(gpu_hours, num(c["spot_hr"]), od)
            opt_cost = sim["spot_cost"]
        elif tier == "reserved":
            opt_cost = gpu_hours * num(c["reserved_3yr_hr"])
        else:
            opt_cost = on_demand_cost

        on_demand_monthly += on_demand_cost
        optimized_monthly += opt_cost
        recs.append({"job_id": j["job_id"], "gpu_type": gtype, "tier": tier,
                     "on_demand": round(on_demand_cost), "optimized": round(opt_cost)})

    savings = on_demand_monthly - optimized_monthly
    savings_pct = savings / on_demand_monthly * 100 if on_demand_monthly else 0.0

    # --- Extension 5: Carbon-Aware Scheduling for Interruptible Workloads ---
    from finops import sustainability
    carbon_comparison = {}
    interruptible_jobs = [j for j in jobs if bool(int(num(j["interruptible"])))]
    total_inter_kwh = 0.0
    for j in interruptible_jobs:
        gtype = j["gpu_type"]
        ngpu = int(num(j["num_gpus"]))
        hpd = num(j["hours_per_day"])
        watts = num(cat[gtype]["watts"])
        monthly_gpu_hours = hpd * DAYS * ngpu
        total_inter_kwh += (monthly_gpu_hours * watts) / 1000.0

    for reg in sustainability.REGION_CARBON:
        co2_kg = (total_inter_kwh * sustainability.REGION_CARBON[reg]) / 1000.0
        elec_cost = total_inter_kwh * sustainability.REGION_PRICE_KWH[reg]
        carbon_comparison[reg] = {
            "gco2_kwh": sustainability.REGION_CARBON[reg],
            "price_kwh": sustainability.REGION_PRICE_KWH[reg],
            "co2_kg": round(co2_kg, 1),
            "elec_cost_usd": round(elec_cost, 2),
        }

    base_co2 = carbon_comparison["us-east-1"]["co2_kg"]
    cleanest_reg = "europe-north1"
    cleanest_co2 = carbon_comparison[cleanest_reg]["co2_kg"]
    saved_co2_kg = base_co2 - cleanest_co2
    co2_reduction_pct = (saved_co2_kg / base_co2 * 100) if base_co2 else 0.0

    if verbose:
        print("== M3 Purchasing Strategy ==")
        print(f"break-even utilization @ 45% reserved discount = {pricing.break_even_utilization(0.45):.0%}")
        print(f"{'job':18}{'gpu':7}{'tier':11}{'on-demand':>12}{'optimized':>12}")
        for r in recs:
            print(f"{r['job_id']:18}{r['gpu_type']:7}{r['tier']:11}${r['on_demand']:>11,}${r['optimized']:>11,}")
        print(f"\nmonthly: on-demand ${on_demand_monthly:,.0f} -> optimized ${optimized_monthly:,.0f}  ({savings_pct:.1f}% saved)")
        print("\n--- [Extension 5] Carbon-Aware Region Scheduling for Batch/Training ---")
        print(f"Interruptible Workloads Monthly Power: {total_inter_kwh:,.1f} kWh")
        print(f"{'Region':18}{'gCO2/kWh':>10}{'$/kWh':>8}{'Monthly CO2 (kg)':>18}{'Power Cost':>12}")
        for reg, data in carbon_comparison.items():
            print(f"{reg:18}{data['gco2_kwh']:>10}{data['price_kwh']:>8.3f}${data['co2_kg']:>17,}${data['elec_cost_usd']:>11,.2f}")
        print(f"Relocating interruptible jobs from us-east-1 to {cleanest_reg} saves {saved_co2_kg:,.1f} kg CO2/month ({co2_reduction_pct:.1f}% reduction).")

    return {
        "recommendations": recs,
        "on_demand_monthly": round(on_demand_monthly),
        "optimized_monthly": round(optimized_monthly),
        "savings_pct": round(savings_pct, 1),
        "carbon_comparison": carbon_comparison,
        "co2_saved_kg": round(saved_co2_kg, 1),
    }


if __name__ == "__main__":
    run()

