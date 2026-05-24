# Energy Scheduler Backend - API Documentation

## Overview

This backend provides intelligent scheduling algorithms for Matter-enabled home appliances in Ireland, optimizing for cost and renewable energy usage based on household configuration and electricity prices.

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements.txt
```

2. Start the API server:
```bash
cd MatterEnergyScheduler
uvicorn main:app --reload
```

The API will be available at `http://localhost:8000`
Interactive API docs: `http://localhost:8000/docs`

## API Endpoints

### 1. Grid-Only Scheduling
**POST** `/schedule/grid-only`

Finds the cheapest time window to run an appliance based on day-ahead electricity prices.

**Request Body:**
```json
{
  "appliance": {
    "name": "Washing Machine",
    "power_usage_kw": 2.5,
    "duration_seconds": 3600,
    "deadline": "2026-04-20T22:00:00",
    "matter_device_id": "device-12345"
  },
  "household": {
    "id": "household-1",
    "household_type": "grid_only",
    "location_latitude": 53.3498,
    "location_longitude": -6.2603,
    "pv_capacity_kw": 0,
    "bess_capacity_kwh": 0,
    "bess_min_soc_percent": 20
  },
  "target_date": "2026-04-20"
}
```

**Response:**
```json
{
  "start_time": "2026-04-20T02:30:00"
}
```

---

### 2. Grid + PV Scheduling
**POST** `/schedule/grid-pv`

Schedules appliance to maximize solar self-sufficiency. Prioritizes running during peak solar production hours to minimize grid import.

**Request Body:**
```json
{
  "appliance": {
    "name": "Dishwasher",
    "power_usage_kw": 1.8,
    "duration_seconds": 7200,
    "deadline": "2026-04-20T18:00:00",
    "matter_device_id": "device-12346"
  },
  "household": {
    "id": "household-2",
    "household_type": "grid_and_pv",
    "location_latitude": 53.3498,
    "location_longitude": -6.2603,
    "pv_capacity_kw": 5.0,
    "bess_capacity_kwh": 0,
    "bess_min_soc_percent": 20
  },
  "target_date": "2026-04-20"
}
```

**Response:**
```json
{
  "start_time": "2026-04-20T11:00:00"
}
```

---

### 3. Grid + PV + BESS Scheduling
**POST** `/schedule/grid-pv-bess`

Optimizes appliance scheduling to:
- Maximize solar self-consumption
- Minimize grid usage during expensive peak hours
- Use battery stored energy strategically
- Maintain 20% BESS buffer (prevents over-drainage)

**Request Body:**
```json
{
  "appliance": {
    "name": "Electric Oven",
    "power_usage_kw": 3.0,
    "duration_seconds": 5400,
    "deadline": "2026-04-20T19:00:00",
    "matter_device_id": "device-12347"
  },
  "household": {
    "id": "household-3",
    "household_type": "grid_pv_and_bess",
    "location_latitude": 53.3498,
    "location_longitude": -6.2603,
    "pv_capacity_kw": 5.0,
    "bess_capacity_kwh": 13.5,
    "bess_min_soc_percent": 20
  },
  "target_date": "2026-04-20",
  "current_bess_soc_kwh": 10.0
}
```

**Response:**
```json
{
  "start_time": "2026-04-20T10:30:00"
}
```

---

## Data Models

### Appliance
```python
id: str                    # Unique identifier (UUID)
name: str                  # Appliance name
power_usage_kw: float      # Power consumption in kW
duration_seconds: int      # How long appliance must run
deadline: datetime         # Must complete by this time
matter_device_id: str      # Matter device identifier
```

### Household
```python
id: str                          # Unique household identifier
household_type: str              # "grid_only" | "grid_and_pv" | "grid_pv_and_bess"
location_latitude: float         # Geographic location
location_longitude: float        # Geographic location
pv_capacity_kw: float            # Solar panel capacity
bess_capacity_kwh: float         # Battery capacity
bess_min_soc_percent: float       # Minimum battery charge (default: 20%)
```

### EnergyPrice
```python
start_time: datetime     # Time slot start
price_per_kwh: float     # Price in EUR/kWh
```

### SolarProduction
```python
time: datetime           # Timestamp
kw_produced: float       # Expected production in kW
```

---

## Scheduling Algorithms

### Grid-Only (Simple Sliding Window)
- Scans all possible 30-minute windows until deadline
- Selects window with minimum total cost
- Time complexity: O(n) where n = number of price periods

### Grid + PV (Solar Priority)
- Considers both prices and solar production forecast
- Scores windows by: (solar_kwh × 100) - grid_cost
- Maximizes self-sufficiency while minimizing cost

### Grid + PV + BESS (Optimal with Storage)
- Simulates energy flow: Solar → Appliance → BESS → Grid
- Respects 20% BESS buffer to prevent over-drainage
- Prioritizes cheap window + available stored energy
- Recharges battery from excess solar

---

## API Integration Notes

### Real Price Data (ENTSO-E) ✓ IMPLEMENTED
Live day-ahead prices are integrated through the ENTSO-E Transparency API:
- API Token: provide `ENTSOE_API_KEY` in the local backend `.env`
- Data Source: ENTSO-E Transparency API
- Coverage: supported ENTSO-E bidding zones
- Update Frequency: Daily at 13:00 UTC (day-ahead prices)
- Price Format: EUR/kWh (converted from EUR/MWh)

**Intelligent Fallback Strategy:**
- If current day's prices cannot be fetched, the system automatically uses **previous day's prices shifted to today**
- This is based on the assumption that consecutive days follow similar price patterns
- Cached prices are stored locally in `data/price_cache/`
- Provides service continuity when ENTSO-E API is temporarily unavailable

### Real Solar Forecasts (Open-Meteo) ✓ IMPLEMENTED
Real solar irradiance forecasts are now integrated using the free Open-Meteo API:
- Data Source: Open-Meteo Forecast API
- Irradiance Metric: Direct Normal Irradiance (DNI) hourly
- Coverage: Global (all locations)
- Forecast Range: Up to 16 days ahead
- No API Key Required: Free and publicly accessible
- Update Frequency: Updated multiple times per day

The system automatically fetches location-based solar irradiance forecasts for all scheduling requests with PV.

---

## Error Handling

### 400 Bad Request
- No feasible schedule found within deadline
- Missing required fields (e.g., `current_bess_soc_kwh` for BESS scheduling)
- Empty price or solar data

### Example Error:
```json
{
  "detail": "No feasible schedule found within deadline"
}
```

---

## Testing

Example using `curl`:

```bash
curl -X POST "http://localhost:8000/schedule/grid-only" \
  -H "Content-Type: application/json" \
  -d '{
    "appliance": {
      "name": "Washing Machine",
      "power_usage_kw": 2.5,
      "duration_seconds": 3600,
      "deadline": "2026-04-20T22:00:00",
      "matter_device_id": "device-123"
    },
    "household": {
      "id": "h1",
      "household_type": "grid_only",
      "location_latitude": 53.35,
      "location_longitude": -6.26,
      "pv_capacity_kw": 0,
      "bess_capacity_kwh": 0,
      "bess_min_soc_percent": 20
    }
  }'
```

---

## Next Steps

1. **Database Integration** - Store schedules, appliances, household configs
2. **Matter Protocol** - Implement device control and status monitoring
3. **Frontend UI** - Web page for setting deadlines and viewing schedules
4. **Real API Integration** - ENTSO-E prices and Open-Meteo solar forecasts with proper error handling
5. **Advanced Features** - Machine learning forecasts, multi-appliance coordination
