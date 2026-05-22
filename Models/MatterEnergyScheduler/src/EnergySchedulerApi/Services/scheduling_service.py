from typing import List
from datetime import datetime, timedelta
from math import ceil
from ..Models.appliance import Appliance
from ..Models.energy_price import EnergyPrice

class SchedulingService:
    INTERVAL_HOURS = 0.5

    def calculate_optimal_start_time(self, appliance: Appliance, prices: List[EnergyPrice]) -> datetime:
        if not prices:
            raise ValueError("Prices cannot be empty")
        prices = sorted(prices, key=lambda p: p.start_time)
        num_intervals = max(1, ceil(appliance.duration.total_seconds() / (self.INTERVAL_HOURS * 3600)))
        min_cost = float('inf')
        optimal_start = None
        for i in range(len(prices) - num_intervals + 1):
            start_time = prices[i].start_time
            end_time = start_time + timedelta(hours=num_intervals * self.INTERVAL_HOURS)
            if end_time > appliance.deadline:
                continue
            cost = sum(prices[i + j].price_per_kwh * appliance.power_usage_kw * self.INTERVAL_HOURS for j in range(num_intervals))
            if cost < min_cost:
                min_cost = cost
                optimal_start = start_time
        if optimal_start is None:
            raise ValueError("No feasible schedule found")
        return optimal_start
