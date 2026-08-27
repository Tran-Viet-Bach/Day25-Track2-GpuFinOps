import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finops import pricing, sustainability, metrics


def test_cache_is_worth_it():
    # Break-even for write=1.25, read=0.10 is: (1.25 - 1.0) / (1.0 - 0.10) = 0.25 / 0.90 = 0.278
    assert pricing.cache_is_worth_it(avg_reads=0.1, write_cost_multiplier=1.25, read_discount=0.10) is False
    assert pricing.cache_is_worth_it(avg_reads=0.5, write_cost_multiplier=1.25, read_discount=0.10) is True
    assert pricing.cache_is_worth_it(avg_reads=3.5, write_cost_multiplier=1.25, read_discount=0.10) is True
    # Zero or negative reads should not be worth it
    assert pricing.cache_is_worth_it(avg_reads=0.0) is False


def test_recommend_tier_with_sla_and_duration():
    # High interruption rate should reject spot and fall back to on_demand / reserved
    assert pricing.recommend_tier(hours_per_day=4, interruptible=True, interruption_rate=0.25, max_tolerable_interrupt_rate=0.15) == "on_demand"
    # Normal interruption rate allows spot
    assert pricing.recommend_tier(hours_per_day=4, interruptible=True, interruption_rate=0.05, max_tolerable_interrupt_rate=0.15) == "spot"
    # 1-year reserved has lower discount, requires higher duty cycle
    # Break even at 30% discount is 70% duty (~16.8 hours/day)
    assert pricing.recommend_tier(hours_per_day=15, interruptible=False, duration_years=1) == "on_demand"
    assert pricing.recommend_tier(hours_per_day=20, interruptible=False, duration_years=1) == "reserved"


def test_sustainability_carbon_and_energy():
    wh_normal = sustainability.wh_per_query(1000, is_reasoning=False)
    wh_reasoning = sustainability.wh_per_query(1000, is_reasoning=True)
    assert abs(wh_reasoning / wh_normal - 80.0) < 1e-6

    # Verify cleanest region
    cleanest = min(sustainability.REGION_CARBON, key=sustainability.REGION_CARBON.get)
    assert cleanest == "europe-north1"
    assert sustainability.carbon_g(1000, "europe-north1") < sustainability.carbon_g(1000, "us-east-1")
