# Implementation Summary: Energy Scheduler Backend (Phase 1 & 2)

## What Has Been Implemented

### ✅ Phase 1: Project Structure & Grid-Only Scheduling
- Clean Python/FastAPI project structure
- Appliance and EnergyPrice models
- Grid-only scheduler using sliding window algorithm
- Mock price provider for testing

### ✅ Phase 2: Multi-Household Scheduling & Advanced Algorithms

#### 1. **Household Types Support**
Three scheduling strategies for different energy configurations:
- **Grid-Only**: Minimize electricity cost
- **Grid + PV**: Maximize solar self-sufficiency
- **Grid + PV + BESS**: Minimize cost + protect battery (20% buffer)

#### 2. **New Models**
- `Household`: Stores configuration (type, location, PV capacity, BESS capacity)
- Updated `Appliance`: Better structure for deadline scheduling

#### 3. **Three Specialized Schedulers**

**GridOnlyScheduler**
- Simple sliding window algorithm
- Finds cheapest consecutive time slots
- Respects appliance deadline
- Used for: Grid-only households

**GridAndPvScheduler**
- Integrates solar forecast data
- Scoring: `(solar_kwh * 100) - grid_cost`
- Prioritizes running during peak solar hours
- Used for: Grid + PV households

**GridPvAndBessScheduler**
- Simulates energy flow with BESS management
- Priority: Solar → BESS → Grid
- Respects 20% minimum SOC buffer (prevents over-drainage)
- Automatically recharges battery from excess solar
- Used for: Grid + PV + BESS households

#### 4. **API Integrations**
- **ENTSO-E Provider**: Live day-ahead electricity prices (XML parsing)
- **Open-Meteo Provider**: Real solar irradiance forecasts
- **Mock Providers**: For testing without API keys

#### 5. **Three API Endpoints**
```
POST /schedule/grid-only        → Cheapest window
POST /schedule/grid-pv          → Solar-prioritized window
POST /schedule/grid-pv-bess     → Optimal with battery management
GET  /health                    → API health check
```

#### 6. **BESS Features**
- Configurable battery capacity (e.g., Tesla Powerwall 13.5 kWh)
- 20% minimum SOC buffer by default (configurable)
- Prevents over-drainage of battery
- Intelligently recharges from solar
- Minimizes grid usage during expensive windows

---

## File Structure

```
MatterEnergyScheduler/
├── requirements.txt                          # Python dependencies
├── main.py                                   # FastAPI app & endpoints
├── test_imports.py                           # Quick import verification
├── examples.py                               # Example requests (3 scenarios)
├── docs/
│   └── API_DOCUMENTATION.md                  # Complete API docs
├── src/
│   └── EnergyScheduler.Api/
│       ├── __init__.py
│       ├── Models/
│       │   ├── appliance.py
│       │   ├── energy_price.py
│       │   ├── location.py
│       │   ├── solar_production.py
│       │   ├── household_type.py
│       │   ├── household.py
│       │   └── __init__.py
│       ├── Services/
│       │   ├── scheduling_service.py         # Original (deprecated)
│       │   ├── scheduling_strategies.py      # NEW: 3 schedulers
│       │   └── __init__.py
│       ├── Infrastructure/
│       │   ├── mock_price_provider.py
│       │   ├── mock_geo_service.py
│       │   ├── mock_solar_forecast_service.py
│       │   ├── entso_price_provider.py       # NEW: Real prices
│       │   ├── open_meteo_solar_forecast.py  # NEW: Real forecasts
│       │   └── __init__.py
│       └── Controllers/
│           └── __init__.py
```

---

## How to Test

### 1. **Install dependencies**
```bash
cd MatterEnergyScheduler
pip install -r requirements.txt
```

### 2. **Verify imports**
```bash
python test_imports.py
```

Expected output:
```
✓ All models imported successfully
✓ All scheduling services imported successfully
✓ All mock providers imported successfully
✓ Grid-only scheduler works: optimal start time = ...
All tests passed! ✓
```

### 3. **Start API**
```bash
uvicorn main:app --reload
```

API available at: `http://localhost:8000`
Docs available at: `http://localhost:8000/docs`

### 4. **Test endpoints**

**Option A: Interactive Swagger UI**
- Visit `http://localhost:8000/docs`
- Click "Try it out" on each endpoint

**Option B: Command line with examples.py**
```bash
# (Make sure API is running first)
python examples.py
```

**Option C: Manual curl**
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

## Key Features: BESS Scheduler Deep Dive

### How the 20% Buffer Works
```
Battery: 13.5 kWh (e.g., Tesla Powerwall)
Minimum SOC: 20% = 2.7 kWh
Usable energy: 13.5 - 2.7 = 10.8 kWh

Current SOC: 10 kWh
Can use for appliance: 10 - 2.7 = 7.3 kWh
```

### Energy Priority During Appliance Run
1. **Solar Production** (free, highest priority)
2. **BESS** (stored, low cost)
3. **Grid** (expensive, last resort)
4. **BESS Recharges** from excess solar after appliance completes

### Example Scenario
**Grid + PV + BESS household at 2 PM:**
- Washing machine (2.5 kW, 1 hour deadline)
- Solar forecast: 2 kW available
- BESS: 10 kWh current (can use 7.3 kWh)
- Grid prices: €0.20/kWh (expensive window)

**Scheduler decision:**
- Use 2 kW from solar (free)
- Use 0.5 kW from BESS (stored energy)
- Result: 0 kWh from grid, minimal cost

---

## Real API Integration Instructions

### ENTSO-E (Day-Ahead Electricity Prices)
1. Register: https://www.entsoe.eu/
2. Create API token in ENTSO-E platform
3. Update `main.py`:
   ```python
   from src.EnergyScheduler.Api.Infrastructure.entso_price_provider import EntsoePriceProvider
   
   price_provider = EntsoePriceProvider(api_key="YOUR_KEY")
   ```

### Open-Meteo (Solar Forecasts)
1. No registration or API key required.
2. Update `main.py` (already implemented):
   ```python
   from src.EnergySchedulerApi.Infrastructure.open_meteo_solar_forecast import OpenMeteoSolarForecast
   
   solar_provider = OpenMeteoSolarForecast()
   ```

---

## What's Next (Phase 3+)

1. **Database Layer**
   - Store household configs, appliances, scheduled jobs
   - Track historical costs and solar production
   - Use: PostgreSQL + SQLAlchemy

2. **Matter Protocol Integration**
   - Device discovery and pairing
   - Send start/stop commands to appliances
   - Read appliance status and power usage
   - Use: matter-server or python-matter-server

3. **Frontend Web UI**
   - React/Vue SPA
   - Set appliance deadlines
   - View scheduled times
   - Monitor real-time costs and savings
   - Dashboard with charts

4. **Advanced Features**
   - Multi-appliance coordination (avoid peak simultaneous loads)
   - Machine learning forecasts
   - Cost optimization over multiple days
   - User preferences (carbon vs cost)
   - Export metrics to dashboard

---

## Testing Scenarios Included

Three complete example scenarios in `examples.py`:
1. **Grid-Only Dublin House**
   - 2.5 kW washer, 1-hour deadline
   - Finds cheapest hour

2. **Grid + PV Dublin House**
   - 1.8 kW dishwasher, 2-hour deadline
   - Prioritizes noon (peak solar)

3. **Grid + PV + BESS Smart Home**
   - 3.0 kW oven, 1.5-hour deadline
   - Uses battery strategically
   - Maintains 20% buffer (2.7 kWh)

---

## Error Handling

All endpoints return proper HTTP responses:
- **200 OK**: Successful scheduling with `start_time`
- **400 Bad Request**: No feasible schedule or missing required fields
- **500 Internal Server Error**: API provider failures

Example error:
```json
{
  "detail": "No feasible schedule found within deadline"
}
```

---

## Performance

- **Grid-Only**: O(n) where n = price periods (typically 48)
- **Grid + PV**: O(n²) with solar lookup
- **Grid + PV + BESS**: O(n²) with energy simulation

Typical response time: <100ms for mock providers, 1-2s with real APIs
