from typing import List, Optional
from datetime import datetime, timedelta
from math import ceil
from ..Models.appliance import Appliance
from ..Models.energy_price import EnergyPrice
from ..Models.solar_production import SolarProduction
from ..Models.scheduled_appliance import ScheduledAppliance
from ..Models.water_heater import WaterHeater


class SchedulerBase:
    INTERVAL_HOURS = 0.5
    HOUSE_LIMIT_KW = 11.0

    def _align_to_interval(self, dt: datetime) -> datetime:
        minute = 30 if dt.minute >= 30 else 0
        return dt.replace(minute=minute, second=0, microsecond=0)

    def _window_fits_load(
        self,
        start_time: datetime,
        num_intervals: int,
        candidate_kw: float,
        existing_schedules: Optional[List[ScheduledAppliance]],
        house_limit_kw: float
    ) -> bool:
        if existing_schedules is None:
            return candidate_kw <= house_limit_kw

        interval_length = timedelta(hours=self.INTERVAL_HOURS)
        for j in range(num_intervals):
            interval_start = start_time + timedelta(hours=j * self.INTERVAL_HOURS)
            interval_end = interval_start + interval_length
            total_kw = candidate_kw
            for scheduled in existing_schedules:
                scheduled_start = scheduled.start_time
                scheduled_end = scheduled.start_time + timedelta(seconds=scheduled.duration_seconds)
                if scheduled_start < interval_end and interval_start < scheduled_end:
                    total_kw += scheduled.power_usage_kw
                    if total_kw > house_limit_kw:
                        return False
        return candidate_kw <= house_limit_kw

    def _find_first_feasible_start(
        self,
        duration_hours: float,
        deadline: datetime,
        existing_schedules: Optional[List[ScheduledAppliance]],
        house_limit_kw: float,
        candidate_kw: float,
        search_start: Optional[datetime] = None
    ) -> Optional[datetime]:
        start_time = self._align_to_interval(search_start or datetime.now())
        num_intervals = max(1, ceil(duration_hours / self.INTERVAL_HOURS))
        interval_length = timedelta(hours=self.INTERVAL_HOURS)

        while start_time + timedelta(hours=duration_hours) <= deadline:
            if self._window_fits_load(start_time, num_intervals, candidate_kw, existing_schedules, house_limit_kw):
                return start_time
            start_time += interval_length
        return None

    def _fallback_start_time(
        self,
        appliance_duration_hours: float,
        deadline: datetime,
        existing_schedules: Optional[List[ScheduledAppliance]],
        house_limit_kw: float,
        candidate_kw: float
    ) -> datetime:
        now = datetime.now()
        earliest = self._find_first_feasible_start(
            appliance_duration_hours,
            deadline,
            existing_schedules,
            house_limit_kw,
            candidate_kw,
            search_start=now
        )
        if earliest:
            return earliest
        if now + timedelta(hours=appliance_duration_hours) <= deadline:
            return now
        return max(deadline - timedelta(hours=appliance_duration_hours), now)


class GridOnlyScheduler(SchedulerBase):
    """Scheduling for Grid-only households: minimize cost using day-ahead prices"""

    def calculate_optimal_start_time(
        self,
        appliance: Appliance,
        prices: List[EnergyPrice],
        existing_schedules: Optional[List[ScheduledAppliance]] = None,
        house_limit_kw: float = 11.0
    ) -> datetime:
        prices = sorted(prices, key=lambda p: p.start_time) if prices else []
        num_intervals = max(1, ceil(appliance.duration.total_seconds() / (self.INTERVAL_HOURS * 3600)))
        
        min_cost = float('inf')
        optimal_start = None

        if prices:
            for i in range(len(prices) - num_intervals + 1):
                start_time = prices[i].start_time
                end_time = start_time + timedelta(hours=num_intervals * self.INTERVAL_HOURS)
                if end_time > appliance.deadline:
                    continue
                if not self._window_fits_load(start_time, num_intervals, appliance.power_usage_kw, existing_schedules, house_limit_kw):
                    continue
                # Use power profile if available, otherwise assume constant load
                profile = appliance.power_profile if appliance.power_profile else [appliance.power_usage_kw] * num_intervals
                
                cost = sum(
                    prices[i + j].price_per_kwh * profile[j] * self.INTERVAL_HOURS
                    for j in range(num_intervals)
                )
                if cost < min_cost:
                    min_cost = cost
                    optimal_start = start_time

        if optimal_start is not None:
            return optimal_start

        return self._fallback_start_time(appliance.duration_seconds / 3600, appliance.deadline, existing_schedules, house_limit_kw, appliance.power_usage_kw)

    def _schedule_ev_fragmented(
        self,
        appliance: Appliance,
        prices: List[EnergyPrice],
        existing_schedules: Optional[List[ScheduledAppliance]] = None,
        house_limit_kw: float = 11.0
    ) -> List[ScheduledAppliance]:
        """Special logic for EVs: find the N cheapest 30m intervals before deadline"""
        prices = sorted(prices, key=lambda p: p.start_time)
        intervals_needed = max(1, ceil(appliance.duration_seconds / (self.INTERVAL_HOURS * 3600)))
        
        valid_intervals = []
        for p in prices:
            if p.start_time + timedelta(hours=self.INTERVAL_HOURS) > appliance.deadline:
                continue
            if p.start_time < datetime.now():
                continue
            
            # Check load limit for this specific 30m block
            if self._window_fits_load(p.start_time, 1, appliance.power_usage_kw, existing_schedules, house_limit_kw):
                valid_intervals.append(p)
        
        # Sort by price and pick cheapest N
        valid_intervals.sort(key=lambda x: x.price_per_kwh)
        best_intervals = valid_intervals[:intervals_needed]
        best_intervals.sort(key=lambda x: x.start_time) # Re-sort by time for order
        
        runs = []
        for interval in best_intervals:
            runs.append(ScheduledAppliance(
                appliance_id=appliance.id,
                start_time=interval.start_time,
                duration_seconds=int(self.INTERVAL_HOURS * 3600),
                power_usage_kw=appliance.power_usage_kw
            ))
        return runs


class GridAndPvScheduler(SchedulerBase):
    """Scheduling for Grid + PV households: prioritize solar self-sufficiency"""

    def calculate_optimal_start_time(
        self,
        appliance: Appliance,
        prices: List[EnergyPrice],
        solar_production: List[SolarProduction],
        existing_schedules: Optional[List[ScheduledAppliance]] = None,
        house_limit_kw: float = 11.0
    ) -> datetime:
        prices = sorted(prices, key=lambda p: p.start_time) if prices else []
        solar_production = sorted(solar_production, key=lambda s: s.time) if solar_production else []
        num_intervals = max(1, ceil(appliance.duration.total_seconds() / (self.INTERVAL_HOURS * 3600)))
        
        best_score = float('-inf')
        optimal_start = None

        if prices:
            for i in range(len(prices) - num_intervals + 1):
                start_time = prices[i].start_time
                end_time = start_time + timedelta(hours=num_intervals * self.INTERVAL_HOURS)
                if end_time > appliance.deadline:
                    continue
                if not self._window_fits_load(start_time, num_intervals, appliance.power_usage_kw, existing_schedules, house_limit_kw):
                    continue

                # Use power profile if available
                profile = appliance.power_profile if appliance.power_profile else [appliance.power_usage_kw] * num_intervals
                
                solar_kwh = 0
                grid_cost = 0
                for j in range(num_intervals):
                    price = prices[i + j]
                    p_load = profile[j]
                    solar = next((s for s in solar_production if s.time == price.start_time), None)
                    solar_available = solar.kw_produced * self.INTERVAL_HOURS if solar else 0
                    solar_kwh += min(solar_available, p_load * self.INTERVAL_HOURS)
                    grid_kwh = max(0, p_load * self.INTERVAL_HOURS - solar_available)
                    grid_cost += grid_kwh * price.price_per_kwh

                score = (solar_kwh * 100) - grid_cost
                if score > best_score:
                    best_score = score
                    optimal_start = start_time

        if optimal_start is not None:
            return optimal_start

        return self._fallback_start_time(appliance.duration.total_seconds() / 3600, appliance.deadline, existing_schedules, house_limit_kw, appliance.power_usage_kw)


class GridPvAndBessScheduler(SchedulerBase):
    """Scheduling for Grid + PV + BESS: minimize grid usage in expensive windows, use stored energy"""

    def calculate_optimal_start_time(
        self,
        appliance: Appliance,
        prices: List[EnergyPrice],
        solar_production: List[SolarProduction],
        current_bess_soc_kwh: float,
        bess_capacity_kwh: float,
        bess_min_soc_kwh: float,
        existing_schedules: Optional[List[ScheduledAppliance]] = None,
        house_limit_kw: float = 11.0
    ) -> datetime:
        prices = sorted(prices, key=lambda p: p.start_time) if prices else []
        solar_production = sorted(solar_production, key=lambda s: s.time) if solar_production else []
        num_intervals = max(1, ceil(appliance.duration.total_seconds() / (self.INTERVAL_HOURS * 3600)))

        best_score = float('-inf')
        optimal_start = None

        if prices:
            for i in range(len(prices) - num_intervals + 1):
                start_time = prices[i].start_time
                end_time = start_time + timedelta(hours=num_intervals * self.INTERVAL_HOURS)
                if end_time > appliance.deadline:
                    continue
                if not self._window_fits_load(start_time, num_intervals, appliance.power_usage_kw, existing_schedules, house_limit_kw):
                    continue

                # Use power profile if available
                profile = appliance.power_profile if appliance.power_profile else [appliance.power_usage_kw] * num_intervals
                
                bess_soc = current_bess_soc_kwh
                total_grid_cost = 0
                bess_used = 0
                solar_used = 0

                for j in range(num_intervals):
                    price = prices[i + j]
                    p_load = profile[j]
                    solar = next((s for s in solar_production if s.time == price.start_time), None)
                    solar_available = solar.kw_produced * self.INTERVAL_HOURS if solar else 0
                    appliance_demand = p_load * self.INTERVAL_HOURS

                    solar_for_appliance = min(solar_available, appliance_demand)
                    appliance_demand -= solar_for_appliance
                    solar_used += solar_for_appliance

                    bess_can_use = max(0, bess_soc - bess_min_soc_kwh)
                    bess_for_appliance = min(bess_can_use, appliance_demand)
                    appliance_demand -= bess_for_appliance
                    bess_soc -= bess_for_appliance
                    bess_used += bess_for_appliance

                    grid_kwh = appliance_demand
                    total_grid_cost += grid_kwh * price.price_per_kwh

                    solar_excess = max(0, solar_available - solar_for_appliance)
                    bess_can_charge = bess_capacity_kwh - bess_soc
                    bess_charged = min(solar_excess, bess_can_charge)
                    bess_soc += bess_charged

                score = -total_grid_cost + (bess_used * 10)
                if score > best_score:
                    best_score = score
                    optimal_start = start_time

        if optimal_start is not None:
            return optimal_start

        return self._fallback_start_time(appliance.duration.total_seconds() / 3600, appliance.deadline, existing_schedules, house_limit_kw, appliance.power_usage_kw)


class WaterHeaterScheduler(SchedulerBase):
    """Flexible water heater scheduler prioritizing cheap electricity and solar"""

    def calculate_optimal_start_time(
        self,
        heater: WaterHeater,
        prices: List[EnergyPrice],
        solar_production: List[SolarProduction],
        existing_schedules: Optional[List[ScheduledAppliance]] = None,
        house_limit_kw: float = 11.0,
        current_bess_soc_kwh: float = 0.0,
        bess_capacity_kwh: float = 0.0,
        bess_min_soc_kwh: float = 0.0
    ) -> datetime:
        prices = sorted(prices, key=lambda p: p.start_time) if prices else []
        solar_production = sorted(solar_production, key=lambda s: s.time) if solar_production else []
        num_intervals = max(1, ceil(heater.duration_seconds / (self.INTERVAL_HOURS * 3600)))

        if heater.current_temperature_c < heater.min_temperature_c:
            immediate = self._find_first_feasible_start(
                heater.duration_seconds / 3600,
                heater.deadline,
                existing_schedules,
                house_limit_kw,
                heater.power_usage_kw,
                search_start=datetime.now()
            )
            if immediate:
                return immediate
            return self._fallback_start_time(heater.duration_seconds / 3600, heater.deadline, existing_schedules, house_limit_kw, heater.power_usage_kw)

        best_score = float('-inf')
        optimal_start = None

        if prices:
            for i in range(len(prices) - num_intervals + 1):
                start_time = prices[i].start_time
                end_time = start_time + timedelta(hours=num_intervals * self.INTERVAL_HOURS)
                if end_time > heater.deadline:
                    continue
                if not self._window_fits_load(start_time, num_intervals, heater.power_usage_kw, existing_schedules, house_limit_kw):
                    continue

                total_grid_cost = 0
                solar_used = 0
                bess_used = 0
                bess_soc = current_bess_soc_kwh

                for j in range(num_intervals):
                    price = prices[i + j]
                    solar = next((s for s in solar_production if s.time == price.start_time), None)
                    solar_available = solar.kw_produced * self.INTERVAL_HOURS if solar else 0
                    demand = heater.power_usage_kw * self.INTERVAL_HOURS

                    solar_for_heater = min(solar_available, demand)
                    demand -= solar_for_heater
                    solar_used += solar_for_heater

                    bess_can_use = max(0, bess_soc - bess_min_soc_kwh)
                    bess_for_heater = min(bess_can_use, demand)
                    demand -= bess_for_heater
                    bess_soc -= bess_for_heater
                    bess_used += bess_for_heater

                    total_grid_cost += demand * price.price_per_kwh
                    excess_solar = max(0, solar_available - solar_for_heater)
                    charge_available = bess_capacity_kwh - bess_soc
                    bess_soc += min(excess_solar, charge_available)

                score = (solar_used * 100) - total_grid_cost + (bess_used * 5)
                if score > best_score:
                    best_score = score
                    optimal_start = start_time

        if optimal_start is not None:
            return optimal_start

        return self._fallback_start_time(heater.duration_seconds / 3600, heater.deadline, existing_schedules, house_limit_kw, heater.power_usage_kw)


class MultiApplianceScheduler(SchedulerBase):
    """Coordinated scheduler for multiple appliances"""

    def schedule_all_appliances(
        self,
        appliances: List[Appliance],
        water_heaters: List[WaterHeater],
        prices: List[EnergyPrice],
        solar_production: List[SolarProduction],
        household_type: str,  # 'grid-only', 'grid-pv', 'grid-pv-bess'
        current_bess_soc_kwh: float = 0.0,
        bess_capacity_kwh: float = 0.0,
        bess_min_soc_kwh: float = 0.0,
        house_limit_kw: float = 11.0
    ) -> List[ScheduledAppliance]:
        # Combine and sort all loads by deadline (earliest first)
        all_loads = appliances + water_heaters
        all_loads.sort(key=lambda x: x.deadline)
        
        scheduled = []
        for load in all_loads:
            if isinstance(load, WaterHeater):
                scheduler = WaterHeaterScheduler()
                start_time = scheduler.calculate_optimal_start_time(
                    load, prices, solar_production, scheduled, house_limit_kw,
                    current_bess_soc_kwh, bess_capacity_kwh, bess_min_soc_kwh
                )
            else:
                if load.device_type == 'ev_charger':
                    # EV EXCEPTION: Allow fragmented runs
                    runs = GridOnlyScheduler()._schedule_ev_fragmented(load, prices, scheduled, house_limit_kw)
                    scheduled.extend(runs)
                    continue
                else:
                    # STANDARD APPLIANCES: Continuous runs only
                    if household_type == 'grid-only':
                        scheduler = GridOnlyScheduler()
                        res = scheduler.calculate_optimal_start_time(load, prices, scheduled, house_limit_kw)
                        scheduled.extend(res)
                    elif household_type == 'grid-pv':
                        scheduler = GridAndPvScheduler()
                        start_time = scheduler.calculate_optimal_start_time(load, prices, solar_production, scheduled, house_limit_kw)
                        scheduled.append(ScheduledAppliance(
                            appliance_id=load.id,
                            start_time=start_time,
                            duration_seconds=load.duration_seconds,
                            power_usage_kw=load.power_usage_kw
                        ))
                    else:  # grid-pv-bess
                        scheduler = GridPvAndBessScheduler()
                        start_time = scheduler.calculate_optimal_start_time(
                            load, prices, solar_production, current_bess_soc_kwh,
                            bess_capacity_kwh, bess_min_soc_kwh, scheduled, house_limit_kw
                        )
                        scheduled.append(ScheduledAppliance(
                            appliance_id=load.id,
                            start_time=start_time,
                            duration_seconds=load.duration_seconds,
                            power_usage_kw=load.power_usage_kw
                        ))
        
        return scheduled
