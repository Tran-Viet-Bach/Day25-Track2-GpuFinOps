"""M1 — Efficiency Audit: MFU/MBU, the GPU-Util lie, and idle waste (deck §5).

Run: python missions/m1_efficiency_audit.py
"""
from __future__ import annotations
import os as _os, sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
from collections import defaultdict
from missions._common import load_csv, num, catalog_by_type
from finops import metrics


def run(verbose: bool = True) -> dict:
    tel = load_csv("gpu_telemetry.csv")
    cat = catalog_by_type()

    # per-row MFU/MBU, then aggregate per GPU
    agg = defaultdict(lambda: {"util": [], "mfu": [], "mbu": [], "type": None, "idle_hours": 0})
    for r in tel:
        gtype = r["gpu_type"]
        peak_fp16 = num(cat[gtype]["peak_tflops_fp16"])
        peak_bw = num(cat[gtype]["peak_bw_tbs"])
        mfu = metrics.compute_mfu(num(r["achieved_tflops"]), peak_fp16)
        mbu = metrics.compute_mbu(num(r["achieved_bw_tbs"]), peak_bw)
        a = agg[r["gpu_id"]]
        a["type"] = gtype
        a["util"].append(num(r["gpu_util_pct"]))
        a["mfu"].append(mfu)
        a["mbu"].append(mbu)
        if num(r["gpu_util_pct"]) < 10:  # effectively idle this interval (1h)
            a["idle_hours"] += 1

    summary = []
    for gid, a in agg.items():
        summary.append({
            "gpu_id": gid, "gpu_type": a["type"],
            "gpu_util_pct": round(sum(a["util"]) / len(a["util"]), 1),
            "mfu": round(sum(a["mfu"]) / len(a["mfu"]), 3),
            "mbu": round(sum(a["mbu"]) / len(a["mbu"]), 3),
            "idle_hours": a["idle_hours"],
        })

    lies = metrics.flag_util_lies(summary)
    idle_waste = 0.0
    for s in summary:
        on_demand = num(catalog_by_type()[s["gpu_type"]]["on_demand_hr"])
        idle_waste += metrics.idle_waste_usd(s["idle_hours"], on_demand)

    # --- Extension 2: Right-sizing analysis based on MBU, VRAM & Roofline ---
    rightsizing_analysis = []
    total_rightsize_monthly_savings = 0.0
    for s in summary:
        cur_type = s["gpu_type"]
        cur_cat = cat[cur_type]
        cur_od = num(cur_cat["on_demand_hr"])
        cur_vram = num(cur_cat["hbm_gb"])
        cur_bw = num(cur_cat["peak_bw_tbs"])

        # Flag memory-bound or underutilized GPUs that can be right-sized
        # E.g., if MFU < 0.25 (memory-bound/overprovisioned) or flagged as util-lie
        recommended_type = cur_type
        if s["gpu_id"] in [l["gpu_id"] for l in lies] or s["mfu"] < 0.25:
            if cur_type == "H100":
                recommended_type = "A100" if s["mbu"] > 0.40 else "A10G"
            elif cur_type == "A10G":
                recommended_type = "L4"
            elif cur_type == "H200":
                recommended_type = "H100"

        rec_cat = cat[recommended_type]
        rec_od = num(rec_cat["on_demand_hr"])
        monthly_saving = max(0.0, (cur_od - rec_od) * 24 * 30)
        total_rightsize_monthly_savings += monthly_saving

        rightsizing_analysis.append({
            "gpu_id": s["gpu_id"],
            "current_gpu": cur_type,
            "recommended_gpu": recommended_type,
            "current_cost_hr": cur_od,
            "rec_cost_hr": rec_od,
            "cost_per_gb_vram": round(cur_od / cur_vram, 4),
            "cost_per_tbps_bw": round(cur_od / cur_bw, 3),
            "monthly_savings": round(monthly_saving, 2),
        })

    if verbose:
        print("== M1 Efficiency Audit ==")
        print(f"{'GPU':14}{'type':7}{'util%':>7}{'MFU':>7}{'MBU':>7}{'idle_h':>8}")
        for s in sorted(summary, key=lambda x: x["mfu"]):
            print(f"{s['gpu_id']:14}{s['gpu_type']:7}{s['gpu_util_pct']:>7}{s['mfu']:>7}{s['mbu']:>7}{s['idle_hours']:>8}")
        print(f"\nGPU-Util LIES (util>=90% but MFU<30%): {[l['gpu_id'] for l in lies]}")
        print(f"Idle waste (1 day): ${idle_waste:,.2f}  ->  ${idle_waste*30:,.0f}/month")
        print("\n--- [Extension 2] MBU & VRAM Right-Sizing Recommendations ---")
        print(f"{'GPU ID':14}{'Current':8}{'$/GB-VRAM':>11}{'$/TBps':>9}{'Proposed':10}{'Mo.Savings':>12}")
        for r in rightsizing_analysis:
            if r["current_gpu"] != r["recommended_gpu"]:
                print(f"{r['gpu_id']:14}{r['current_gpu']:8}${r['cost_per_gb_vram']:>10.4f}${r['cost_per_tbps_bw']:>8.2f}  -> {r['recommended_gpu']:8}${r['monthly_savings']:>10,.0f}")
        print(f"Total potential monthly right-sizing savings: ${total_rightsize_monthly_savings:,.0f}/month")

    return {
        "summary": summary,
        "lies": lies,
        "idle_waste_daily": round(idle_waste, 2),
        "rightsizing_analysis": rightsizing_analysis,
        "rightsize_monthly_savings": round(total_rightsize_monthly_savings, 2),
    }


if __name__ == "__main__":
    run()

