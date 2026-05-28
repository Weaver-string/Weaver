import asyncio
from datetime import datetime, timedelta, timezone

import main
from main import ScheduleRequest, effective_duration_seconds, get_existing_schedules_for_request
from EnergySchedulerApi.Models.appliance import Appliance
from EnergySchedulerApi.Models.energy_price import EnergyPrice
from EnergySchedulerApi.Models.household import Household
from EnergySchedulerApi.Models.household_type import HouseholdType
from EnergySchedulerApi.Models.scheduled_appliance import ScheduledAppliance
from EnergySchedulerApi.Models.solar_production import SolarProduction
from EnergySchedulerApi.Services.scheduling_strategies import GridAndPvScheduler, GridOnlyScheduler


def test_existing_schedules_include_other_pending_jobs(monkeypatch) -> None:
    now = datetime.now()

    def fake_pending_schedules():
        return [
            {
                "appliance_id": "other_appliance",
                "start_time": now + timedelta(hours=2),
                "duration_seconds": 3600,
                "power_usage_kw": 4.0,
                "job_id": "other_job",
                "is_daily": False,
            },
            {
                "appliance_id": "target_appliance",
                "start_time": now + timedelta(hours=3),
                "duration_seconds": 3600,
                "power_usage_kw": 2.0,
                "job_id": "old_target_job",
                "is_daily": False,
            },
            {
                "appliance_id": "past_appliance",
                "start_time": now - timedelta(hours=2),
                "duration_seconds": 1800,
                "power_usage_kw": 3.0,
                "job_id": "past_job",
                "is_daily": False,
            },
        ]

    monkeypatch.setattr("main.db_service.get_pending_schedules", fake_pending_schedules)

    request = ScheduleRequest(
        appliance_id="target_appliance",
        household=Household(id="house_1", household_type=HouseholdType.GRID_ONLY),
        existing_schedules=[
            ScheduledAppliance(
                appliance_id="manual_context",
                start_time=now + timedelta(hours=1),
                duration_seconds=1800,
                power_usage_kw=1.0,
            )
        ],
    )

    existing = get_existing_schedules_for_request(request)

    assert [schedule.appliance_id for schedule in existing] == [
        "manual_context",
        "other_appliance",
    ]


def test_grid_scheduler_skips_windows_that_exceed_house_limit() -> None:
    base = (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    appliance = Appliance(
        id="target_appliance",
        name="Target appliance",
        power_usage_kw=4.0,
        duration_seconds=1800,
        deadline=base + timedelta(hours=3),
        matter_device_id="matter_target",
        matter_device_ip="127.0.0.1",
    )
    prices = [
        EnergyPrice(start_time=base, price_per_kwh=0.05),
        EnergyPrice(start_time=base + timedelta(minutes=30), price_per_kwh=0.10),
        EnergyPrice(start_time=base + timedelta(hours=1), price_per_kwh=0.20),
    ]
    existing = [
        ScheduledAppliance(
            appliance_id="other_appliance",
            start_time=base,
            duration_seconds=1800,
            power_usage_kw=8.0,
        )
    ]

    scheduler = GridOnlyScheduler()
    scheduler._now = lambda: base - timedelta(hours=1)  # type: ignore[method-assign]

    start_time = scheduler.calculate_optimal_start_time(
        appliance,
        prices,
        existing_schedules=existing,
        house_limit_kw=10.0,
    )

    assert start_time == base + timedelta(minutes=30)


def test_unknown_runtime_defaults_to_one_hour() -> None:
    assert effective_duration_seconds(None) == 3600
    assert effective_duration_seconds(0) == 3600
    assert effective_duration_seconds(2700) == 2700


def test_grid_pv_schedule_accepts_timezone_aware_deadline(monkeypatch) -> None:
    base = (datetime.now() + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    appliance = Appliance(
        id="target_appliance",
        name="Target appliance",
        power_usage_kw=1.0,
        duration_seconds=2700,
        deadline=base + timedelta(hours=6),
        matter_device_id="matter_target",
        matter_device_ip="127.0.0.1",
    )
    day_start = base.replace(hour=0, minute=0)
    prices = []
    solar = []
    for i in range(48):
        start_time = day_start + timedelta(minutes=30 * i)
        is_base_window = start_time in {base, base + timedelta(minutes=30)}
        prices.append(EnergyPrice(start_time=start_time, price_per_kwh=0.01 if is_base_window else 10.0))
        solar.append(SolarProduction(time=start_time, kw_produced=0.0))

    async def fake_prices(_target_date, _household, _lat=None, _lng=None):
        return prices

    async def fake_solar(_target_date, _household):
        return solar

    monkeypatch.setattr(main.appliance_registry, "get_appliance", lambda _id: appliance)
    monkeypatch.setattr(main.price_provider, "get_day_ahead_prices", fake_prices)
    monkeypatch.setattr(main.solar_provider, "get_forecast", fake_solar)
    monkeypatch.setattr(main.db_service, "get_pending_schedules", lambda: [])
    monkeypatch.setattr(main.background_runner, "schedule_appliance", lambda *args, **kwargs: "job-1")
    monkeypatch.setattr(main.grid_pv_scheduler, "_now", lambda: base - timedelta(hours=1))

    request = ScheduleRequest(
        appliance_id="target_appliance",
        household=Household(
            id="house_1",
            household_type=HouseholdType.GRID_AND_PV,
            bidding_zone="10YFR-RTE------C",
            location_latitude=48.85341,
            location_longitude=2.3488,
            pv_capacity_kw=5.0,
        ),
        deadline_override=(base + timedelta(hours=4)).replace(tzinfo=timezone.utc),
    )

    result = asyncio.run(main.schedule_grid_pv(request))

    assert result == {"start_time": base, "job_id": "job-1"}


def test_grid_pv_normalizes_price_and_solar_windows() -> None:
    base = datetime(2026, 5, 29, 6, 0, 0)
    appliance = Appliance(
        id="dishwasher",
        name="Dishwasher",
        power_usage_kw=0.8,
        duration_seconds=45 * 60,
        deadline=base.replace(hour=23),
        matter_device_id="virtual_test_load",
        matter_device_ip="127.0.0.1",
        device_type="virtual_load",
    )
    prices = [
        EnergyPrice(start_time=base.replace(hour=7), price_per_kwh=0.13),
        EnergyPrice(start_time=base.replace(hour=8), price_per_kwh=0.14),
        EnergyPrice(start_time=base.replace(hour=14), price_per_kwh=0.001),
        EnergyPrice(start_time=base.replace(hour=14, minute=15), price_per_kwh=0.001),
        EnergyPrice(start_time=base.replace(hour=14, minute=30), price_per_kwh=0.0),
        EnergyPrice(start_time=base.replace(hour=14, minute=45), price_per_kwh=0.0),
    ]
    solar = [
        SolarProduction(time=base.replace(hour=7), kw_produced=0.46),
        SolarProduction(time=base.replace(hour=14), kw_produced=0.68),
    ]

    scheduler = GridAndPvScheduler()
    scheduler._now = lambda: base  # type: ignore[method-assign]

    start_time = scheduler.calculate_optimal_start_time(appliance, prices, solar)

    assert start_time == base.replace(hour=14)


def test_price_normalization_handles_common_entso_resolutions() -> None:
    scheduler = GridOnlyScheduler()
    base = datetime(2026, 5, 29, 0, 0, 0)

    cases = [
        [
            EnergyPrice(start_time=base, price_per_kwh=0.10),
            EnergyPrice(start_time=base + timedelta(hours=1), price_per_kwh=0.20),
        ],
        [
            EnergyPrice(start_time=base, price_per_kwh=0.10),
            EnergyPrice(start_time=base + timedelta(minutes=30), price_per_kwh=0.20),
        ],
        [
            EnergyPrice(start_time=base, price_per_kwh=0.10),
            EnergyPrice(start_time=base + timedelta(minutes=15), price_per_kwh=0.30),
            EnergyPrice(start_time=base + timedelta(minutes=30), price_per_kwh=0.20),
            EnergyPrice(start_time=base + timedelta(minutes=45), price_per_kwh=0.40),
        ],
    ]

    expected_prices = [
        [0.10, 0.10, 0.20],
        [0.10, 0.20],
        [0.20, 0.30],
    ]

    for prices, expected in zip(cases, expected_prices):
        normalized = scheduler._normalize_prices(prices)
        assert [price.start_time for price in normalized[:len(expected)]] == [
            base + timedelta(minutes=30 * index)
            for index in range(len(expected))
        ]
        assert [round(price.price_per_kwh, 3) for price in normalized[:len(expected)]] == expected


def test_solar_lookup_maps_hourly_forecast_to_half_hour_blocks() -> None:
    scheduler = GridAndPvScheduler()
    base = datetime(2026, 5, 29, 14, 0, 0)
    solar = [
        SolarProduction(time=base, kw_produced=0.68),
        SolarProduction(time=base + timedelta(hours=1), kw_produced=0.45),
    ]

    assert scheduler._solar_kw_at(base, solar) == 0.68
    assert scheduler._solar_kw_at(base + timedelta(minutes=30), solar) == 0.68
    assert scheduler._solar_kw_at(base + timedelta(hours=1), solar) == 0.45
