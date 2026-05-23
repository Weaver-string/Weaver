import asyncio
from datetime import date, datetime
from types import SimpleNamespace
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from EnergySchedulerApi.Infrastructure.bidding_zones import BIDDING_ZONES
from EnergySchedulerApi.Infrastructure.entso_price_provider import EntsoePriceProvider
from EnergySchedulerApi.Models.energy_price import EnergyPrice


def test_all_configured_bidding_zones_have_explicit_fallback_baselines():
    missing = sorted(
        zone
        for zone in set(BIDDING_ZONES.values())
        if zone not in EntsoePriceProvider.FALLBACK_BASELINES_EUR_KWH
    )

    assert missing == []


def test_generated_fallback_prices_are_hourly_and_marked_non_real():
    provider = EntsoePriceProvider("unused")

    prices = provider._generate_fallback_prices(date(2026, 5, 3), "10YFR-RTE------C")

    assert len(prices) == 24
    assert all(price.is_real is False for price in prices)
    assert all(price.start_time.date() == date(2026, 5, 3) for price in prices)
    assert min(price.price_per_kwh for price in prices) < max(price.price_per_kwh for price in prices)


def test_missing_price_windows_use_fallback_without_replacing_real_prices():
    provider = EntsoePriceProvider("unused")
    target_date = date(2026, 5, 3)
    real_price = EnergyPrice(
        start_time=datetime(2026, 5, 3, 18, 0),
        price_per_kwh=0.1234,
        is_real=True,
    )

    prices = provider._merge_missing_price_windows(
        [real_price],
        target_date,
        "10YFR-RTE------C",
    )

    assert len(prices) == 24
    assert prices[18].start_time == real_price.start_time
    assert prices[18].price_per_kwh == real_price.price_per_kwh
    assert prices[18].is_real is True
    assert all(price.is_real is False for index, price in enumerate(prices) if index != 18)


def test_price_window_uses_fallback_only_for_missing_future_windows():
    provider = EntsoePriceProvider("unused")
    household = SimpleNamespace(bidding_zone="10YFR-RTE------C")
    start_time = datetime(2026, 5, 3, 22, 15)
    deadline = datetime(2026, 5, 4, 2, 30)
    real_prices = [
        EnergyPrice(start_time=datetime(2026, 5, 3, 22), price_per_kwh=0.11, is_real=True),
        EnergyPrice(start_time=datetime(2026, 5, 3, 23), price_per_kwh=0.12, is_real=True),
    ]

    async def fake_day_prices(target_date, _household, _lat=None, _lng=None):
        if target_date == date(2026, 5, 3):
            return real_prices
        return []

    provider.get_day_ahead_prices = fake_day_prices

    prices = asyncio.run(provider.get_prices_for_window(start_time, deadline, household))

    assert [price.start_time for price in prices] == [
        datetime(2026, 5, 3, 22),
        datetime(2026, 5, 3, 23),
        datetime(2026, 5, 4, 0),
        datetime(2026, 5, 4, 1),
        datetime(2026, 5, 4, 2),
    ]
    assert [price.is_real for price in prices] == [True, True, False, False, False]
