# ruff: noqa: E402

import logging
import os
import sys
from datetime import date, datetime, timedelta
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel

# Optional convenience for local development (.env file)
try:
    from dotenv import load_dotenv  # type: ignore
except Exception:  # pragma: no cover
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv()

sys.path.insert(0, "src")

from EnergySchedulerApi.Models.appliance import Appliance
from EnergySchedulerApi.Models.appliance_requests import (
    ApplianceRegistrationRequest,
    ApplianceUpdateRequest,
    SetDeadlineRequest,
)
from EnergySchedulerApi.Models.scheduled_appliance import ScheduledAppliance
from EnergySchedulerApi.Models.energy_price import EnergyPrice
from EnergySchedulerApi.Models.household import Household
from EnergySchedulerApi.Models.matter_device import MatterDevice
from EnergySchedulerApi.Models.water_heater import WaterHeater
from EnergySchedulerApi.Infrastructure.entso_price_provider import EntsoePriceProvider
from EnergySchedulerApi.Infrastructure.open_meteo_solar_forecast import OpenMeteoSolarForecast
from EnergySchedulerApi.Infrastructure.provider_errors import ProviderError
from EnergySchedulerApi.Services.appliance_registry import ApplianceRegistry
from EnergySchedulerApi.Services.matter_commissioning_service import (
    MatterCommissioningError,
    MatterCommissioningService,
)
from EnergySchedulerApi.Services.database_service import DatabaseService
from EnergySchedulerApi.Services.cleanup_service import CleanupService
from EnergySchedulerApi.Services.scheduling_strategies import (
    GridAndPvScheduler,
    GridOnlyScheduler,
    GridPvAndBessScheduler,
    MultiApplianceScheduler,
    WaterHeaterScheduler,
)
from EnergySchedulerApi.Services.matter_controller import MatterController, MatterControllerError
from EnergySchedulerApi.Services.background_runner import BackgroundRunnerService

# Initialize providers
entsoe_token = os.getenv("ENTSOE_TOKEN") or os.getenv("ENTSOE_API_KEY") or "YOUR_TOKEN_HERE"
price_provider = EntsoePriceProvider(entsoe_token)
solar_provider = OpenMeteoSolarForecast()

# Schedulers
grid_only_scheduler = GridOnlyScheduler()
grid_pv_scheduler = GridAndPvScheduler()
grid_pv_bess_scheduler = GridPvAndBessScheduler()
water_heater_scheduler = WaterHeaterScheduler()
multi_appliance_scheduler = MultiApplianceScheduler()
matter_controller = MatterController()

# Database service
db_service = DatabaseService()

# Cleanup service
cleanup_service = CleanupService(db_service, retention_days=7)

# Matter commissioning service
matter_commissioning = MatterCommissioningService(fabric_id=1, db_service=db_service)

# Appliance registry
appliance_registry = ApplianceRegistry(db_service)

# Background runner
background_runner = BackgroundRunnerService(matter_controller, appliance_registry, db_service, cleanup_service)

@asynccontextmanager
async def lifespan(app: FastAPI):
    background_runner.start()
    yield
    background_runner.stop()

app = FastAPI(title="Energy Scheduler API", version="0.1.0", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.getenv("FRONTEND_ORIGINS", "*").split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.getLogger(__name__).info("Energy Scheduler API starting")
logger = logging.getLogger(__name__)


def to_naive_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone().replace(tzinfo=None)


def get_existing_schedules_for_request(request) -> List[ScheduledAppliance]:
    existing = list(request.existing_schedules or [])
    now = datetime.now()
    for schedule in db_service.get_pending_schedules():
        if schedule["appliance_id"] == request.appliance_id:
            continue
        start_time = to_naive_datetime(schedule["start_time"])
        if start_time + timedelta(seconds=schedule["duration_seconds"]) <= now:
            continue
        existing.append(
            ScheduledAppliance(
                appliance_id=schedule["appliance_id"],
                start_time=start_time,
                duration_seconds=schedule["duration_seconds"],
                power_usage_kw=schedule["power_usage_kw"],
            )
        )
    return existing


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    # Avoid noisy 404s from browsers requesting a favicon.
    return Response(status_code=204)


class ScheduleRequest(BaseModel):
    appliance_id: str
    household: Household
    target_date: Optional[date] = None
    current_bess_soc_kwh: Optional[float] = None
    existing_schedules: Optional[List[ScheduledAppliance]] = None
    house_limit_kw: float = 11.0
    deadline_override: Optional[datetime] = None  # Override the appliance's deadline
    is_daily: bool = False


class WaterHeaterScheduleRequest(BaseModel):
    water_heater: WaterHeater
    household: Household
    target_date: Optional[date] = None
    current_bess_soc_kwh: Optional[float] = None
    existing_schedules: Optional[List[ScheduledAppliance]] = None
    house_limit_kw: float = 11.0
    is_daily: bool = False


class MultiApplianceScheduleRequest(BaseModel):
    appliance_ids: List[str]  # List of appliance IDs to schedule together
    household: Household
    target_date: Optional[date] = None
    current_bess_soc_kwh: Optional[float] = None
    existing_schedules: Optional[List[ScheduledAppliance]] = None
    house_limit_kw: float = 11.0
    deadline_override: Optional[datetime] = None  # Override deadlines for all appliances
    is_daily: bool = False


class HouseholdUpdate(BaseModel):
    household_type: Optional[str] = None
    location_latitude: Optional[float] = None
    location_longitude: Optional[float] = None
    country_code: Optional[str] = None
    pv_capacity_kw: Optional[float] = None
    bess_capacity_kwh: Optional[float] = None
    bess_min_soc_percent: Optional[float] = None
    bidding_zone: Optional[str] = None

class MatterDeviceRegistrationRequest(BaseModel):
    name: str
    matter_device_id: str
    ip_address: str
    matter_device_port: int = 5540
    matter_node_id: Optional[int] = None
    device_type: str = "generic" # 'dishwasher', 'washer', 'ev_charger', etc.
    command_path: Optional[str] = "/matter/command"
    status_path: Optional[str] = "/matter/status"


class MatterCommandRequest(BaseModel):
    command: str
    payload: Optional[dict] = None


class MatterScheduleRequest(BaseModel):
    start_time: datetime
    duration_seconds: int


class MatterCommissionRequest(BaseModel):
    qr_code: str
    device_name: str
    ip_address: str
    port: int = 5540
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None
    thread_dataset: Optional[str] = None
    network_only: bool = False


class MatterDiscoveryResponse(BaseModel):
    device_id: str
    device_type: str
    vendor_id: int
    product_id: int
    ip_address: str
    port: int


from EnergySchedulerApi.Services.location_service import LocationService

# Household Management Endpoints
@app.put("/households/{household_id}")
async def update_household(household_id: str, request: HouseholdUpdate):
    """Update a household's properties and automatically sync bidding zone if location changes"""
    try:
        update_data = request.dict(exclude_unset=True)
        
        # If location or country is being updated, automatically sync the bidding zone
        if "location_latitude" in update_data and "location_longitude" in update_data:
            # Prioritize country_code if provided by geocoding
            provided_country = update_data.get("country_code")
            new_zone = LocationService.get_bidding_zone_from_coords(
                update_data["location_latitude"], 
                update_data["location_longitude"],
                country_hint=provided_country
            )
            
            if new_zone:
                update_data["bidding_zone"] = new_zone
                logging.info(f"Automatically updated bidding zone to {new_zone}")
            else:
                # If no zone found, it's outside supported regions
                raise HTTPException(status_code=400, detail="outside_supported_region")
        
        # Remove country_code from update_data before DB call as it's not a DB column
        update_data.pop("country_code", None)

        db_service.update_household(household_id, update_data)
        return {"message": "Household updated", "bidding_zone": update_data.get("bidding_zone")}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/households/{household_id}")
async def get_household(household_id: str):
    """Get a household's properties (Auto-creates if missing)"""
    h = db_service.get_household(household_id)
    if not h:
        # Create a default household
        from EnergySchedulerApi.Models.household_type import HouseholdType
        default_h = Household(
            id=household_id,
            household_type=HouseholdType.GRID_ONLY,
        )
        db_service.save_household(default_h)
        return default_h
    return h

class CommissionRequest(BaseModel):
    code: str
    name: Optional[str] = "Matter Appliance"
    network_only: bool = True

@app.post("/commission")
async def commission_device(request: CommissionRequest):
    """Commission a Matter device using its setup code (QR or digits)"""
    try:
        # The Matter server resolves the commissioned node through operational
        # DNS-SD on the IPv6 fabric. This metadata field is intentionally not
        # treated as a command transport address.
        device = await matter_commissioning.commission_device_via_qr(
            qr_code=request.code,
            device_name=request.name or "Matter Appliance",
            ip_address="operational-discovery",
            port=int(os.getenv("MATTER_DEFAULT_PORT", "5540")),
            network_only=request.network_only,
        )
        return {"status": "success", "node_id": device.node_id, "name": device.name}
    except Exception as e:
        logger.error(f"Commissioning failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Appliance Management Endpoints
@app.post("/appliances")
async def register_appliance(request: ApplianceRegistrationRequest):
    """Register a new appliance"""
    try:
        appliance = Appliance(
            name=request.name,
            power_usage_kw=request.power_usage_kw,
            duration_seconds=request.duration_seconds,
            deadline=request.deadline or datetime.now() + timedelta(days=1),  # Default deadline
            matter_device_id=request.matter_device_id,
            matter_device_ip=request.matter_device_ip,
            matter_device_port=request.matter_device_port,
            matter_node_id=request.matter_node_id,
            device_type=request.device_type
        )
        return appliance_registry.register_appliance(appliance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/appliances")
async def list_appliances():
    """List all registered appliances"""
    return appliance_registry.list_appliances()


@app.get("/appliances/{appliance_id}")
async def get_appliance(appliance_id: str):
    """Get a specific appliance by ID"""
    try:
        return appliance_registry.get_appliance(appliance_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/appliances/{appliance_id}")
async def delete_appliance(appliance_id: str):
    """Delete an appliance by ID"""
    try:
        appliance_registry.remove_appliance(appliance_id)
        return {"message": "Appliance deleted"}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/appliances/{appliance_id}")
async def update_appliance(appliance_id: str, request: ApplianceUpdateRequest):
    """Update an appliance's properties"""
    try:
        return appliance_registry.update_appliance(appliance_id, request.dict(exclude_unset=True))
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.put("/appliances/{appliance_id}/deadline")
async def set_appliance_deadline(appliance_id: str, request: SetDeadlineRequest):
    """Set a deadline for an appliance"""
    try:
        return appliance_registry.set_deadline(appliance_id, request.deadline)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/appliances/{appliance_id}/run-now")
async def run_appliance_now(appliance_id: str):
    """Immediately trigger an appliance to run via Matter device"""
    try:
        appliance = appliance_registry.get_appliance(appliance_id)

        # Send immediate run command
        # If node_id is missing, we try to use the device_id as a fallback
        target_id = appliance.matter_node_id if appliance.matter_node_id is not None else appliance.matter_device_id
        
        return await matter_controller.send_command(
            target_id,
            "run_now",
            {
                "duration_seconds": appliance.duration_seconds,
                "power_kw": appliance.power_usage_kw
            },
            endpoint_id=appliance.matter_device_port if appliance.matter_device_port else None,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MatterControllerError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/appliances/{appliance_id}/status")
async def get_appliance_status(appliance_id: str):
    """Return appliance state reported by the Matter device when available."""
    try:
        appliance = appliance_registry.get_appliance(appliance_id)
        target_id = appliance.matter_node_id if appliance.matter_node_id is not None else appliance.matter_device_id
        if target_id is None:
            return {"appliance_id": appliance_id, "state": "unknown", "is_on": None, "source": "not_linked"}

        status = await matter_controller.get_onoff_status(
            target_id,
            endpoint_id=appliance.matter_device_port if appliance.matter_device_port else None,
        )
        return {"appliance_id": appliance_id, **status}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MatterControllerError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/schedule/grid-only")
async def schedule_grid_only(request: ScheduleRequest):
    """Schedule appliance for grid-only household (minimize cost)"""
    try:
        appliance = appliance_registry.get_appliance(request.appliance_id)

        # Use deadline override if provided, otherwise use appliance's deadline
        deadline = to_naive_datetime(request.deadline_override or appliance.deadline)

        target_date = request.target_date or datetime.now().date()
        prices = await price_provider.get_day_ahead_prices(target_date, request.household)

        # Create a temporary appliance with the deadline override
        temp_appliance = Appliance(
            id=appliance.id,
            name=appliance.name,
            power_usage_kw=appliance.power_usage_kw,
            duration_seconds=appliance.duration_seconds,
            deadline=deadline,
            matter_device_id=appliance.matter_device_id,
            matter_device_ip=appliance.matter_device_ip,
            matter_device_port=appliance.matter_device_port,
            matter_node_id=appliance.matter_node_id,
            device_type=appliance.device_type,
            power_profile=appliance.power_profile
        )

        existing_schedules = get_existing_schedules_for_request(request)

        start_time = grid_only_scheduler.calculate_optimal_start_time(
            temp_appliance,
            prices,
            existing_schedules,
            request.house_limit_kw
        )

        job_id = background_runner.schedule_appliance(
            request.appliance_id, 
            start_time, 
            temp_appliance.duration_seconds, 
            temp_appliance.power_usage_kw,
            is_daily=request.is_daily
        )
        return {"start_time": start_time, "job_id": job_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Appliance not found: {str(e)}")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/schedule/grid-pv")
async def schedule_grid_pv(request: ScheduleRequest):
    """Schedule appliance for Grid + PV household (prioritize solar self-sufficiency)"""
    try:
        appliance = appliance_registry.get_appliance(request.appliance_id)

        # Use deadline override if provided, otherwise use appliance's deadline
        deadline = request.deadline_override or appliance.deadline

        target_date = request.target_date or datetime.now().date()
        prices = await price_provider.get_day_ahead_prices(target_date, request.household)
        solar = await solar_provider.get_forecast(
            target_date,
            request.household
        )

        # Create a temporary appliance with the deadline override
        temp_appliance = Appliance(
            id=appliance.id,
            name=appliance.name,
            power_usage_kw=appliance.power_usage_kw,
            duration_seconds=appliance.duration_seconds,
            deadline=deadline,
            matter_device_id=appliance.matter_device_id,
            matter_device_ip=appliance.matter_device_ip,
            matter_device_port=appliance.matter_device_port,
            matter_node_id=appliance.matter_node_id,
            device_type=appliance.device_type,
            power_profile=appliance.power_profile
        )

        existing_schedules = get_existing_schedules_for_request(request)

        start_time = grid_pv_scheduler.calculate_optimal_start_time(
            temp_appliance,
            prices,
            solar,
            existing_schedules,
            request.house_limit_kw
        )
        job_id = background_runner.schedule_appliance(
            request.appliance_id, 
            start_time, 
            temp_appliance.duration_seconds, 
            temp_appliance.power_usage_kw,
            is_daily=request.is_daily
        )
        return {"start_time": start_time, "job_id": job_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Appliance not found: {str(e)}")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/schedule/grid-pv-bess", include_in_schema=False)
async def schedule_grid_pv_bess(request: ScheduleRequest):
    """Schedule appliance for Grid + PV + BESS household (minimize cost, use stored energy)"""
    try:
        if request.current_bess_soc_kwh is None:
            raise ValueError("current_bess_soc_kwh required for BESS scheduling")

        appliance = appliance_registry.get_appliance(request.appliance_id)

        # Use deadline override if provided, otherwise use appliance's deadline
        deadline = request.deadline_override or appliance.deadline

        target_date = request.target_date or datetime.now().date()
        prices = await price_provider.get_day_ahead_prices(target_date, request.household)
        solar = await solar_provider.get_forecast(
            target_date,
            request.household
        )

        bess_min_soc = (
            request.household.bess_capacity_kwh *
            request.household.bess_min_soc_percent / 100
        )

        # Create a temporary appliance with the deadline override
        temp_appliance = Appliance(
            id=appliance.id,
            name=appliance.name,
            power_usage_kw=appliance.power_usage_kw,
            duration_seconds=appliance.duration_seconds,
            deadline=deadline,
            matter_device_id=appliance.matter_device_id,
            matter_device_ip=appliance.matter_device_ip,
            matter_device_port=appliance.matter_device_port,
            matter_node_id=appliance.matter_node_id,
            device_type=appliance.device_type,
            power_profile=appliance.power_profile
        )

        existing_schedules = get_existing_schedules_for_request(request)

        start_time = grid_pv_bess_scheduler.calculate_optimal_start_time(
            temp_appliance,
            prices,
            solar,
            request.current_bess_soc_kwh,
            request.household.bess_capacity_kwh,
            bess_min_soc,
            existing_schedules,
            request.house_limit_kw
        )
        job_id = background_runner.schedule_appliance(
            request.appliance_id, 
            start_time, 
            temp_appliance.duration_seconds, 
            temp_appliance.power_usage_kw,
            is_daily=request.is_daily
        )
        return {"start_time": start_time, "job_id": job_id}
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Appliance not found: {str(e)}")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/schedule/water-heater")
async def schedule_water_heater(request: WaterHeaterScheduleRequest):
    """Schedule a flexible water heater to use cheap electricity and solar."""
    try:
        target_date = request.target_date or datetime.now().date()
        prices = await price_provider.get_day_ahead_prices(target_date, request.household)
        solar = await solar_provider.get_forecast(
            target_date,
            request.household
        )

        bess_min_soc = (
            request.household.bess_capacity_kwh *
            request.household.bess_min_soc_percent / 100
        )

        if request.household.bess_capacity_kwh > 0 and request.current_bess_soc_kwh is None:
            raise ValueError("current_bess_soc_kwh required for BESS water heater scheduling")

        start_time = water_heater_scheduler.calculate_optimal_start_time(
            request.water_heater,
            prices,
            solar,
            request.existing_schedules,
            request.house_limit_kw,
            request.current_bess_soc_kwh or 0.0,
            request.household.bess_capacity_kwh,
            bess_min_soc
        )
        job_id = background_runner.schedule_appliance(
            request.water_heater.id, 
            start_time, 
            request.water_heater.duration_seconds, 
            request.water_heater.power_usage_kw,
            is_daily=request.is_daily
        )
        return {"start_time": start_time, "job_id": job_id}
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))



@app.post("/schedule/multi-appliance")
async def schedule_multi_appliance(
    request: MultiApplianceScheduleRequest,
) -> List[ScheduledAppliance]:
    """Schedule multiple appliances together, considering all load constraints."""
    try:
        # Get appliances from registry
        appliances = []
        for appliance_id in request.appliance_ids:
            appliance = appliance_registry.get_appliance(appliance_id)

            # Use deadline override if provided, otherwise use appliance's deadline
            deadline = request.deadline_override or appliance.deadline

            # Create a temporary appliance with the deadline override
            temp_appliance = Appliance(
                id=appliance.id,
                name=appliance.name,
                power_usage_kw=appliance.power_usage_kw,
                duration_seconds=appliance.duration_seconds,
                deadline=deadline,
                matter_device_id=appliance.matter_device_id,
                matter_device_ip=appliance.matter_device_ip,
                matter_device_port=appliance.matter_device_port,
                matter_node_id=appliance.matter_node_id,
                device_type=appliance.device_type,
                power_profile=appliance.power_profile
            )
            appliances.append(temp_appliance)

        target_date = request.target_date or datetime.now().date()
        prices = await price_provider.get_day_ahead_prices(target_date, request.household)
        solar = await solar_provider.get_forecast(
            target_date,
            request.household
        )

        household_type = request.household.household_type.value.lower().replace('_', '-')

        bess_min_soc = (
            request.household.bess_capacity_kwh *
            request.household.bess_min_soc_percent / 100
        ) if request.household.bess_capacity_kwh > 0 else 0.0

        if household_type == 'grid-pv-bess' and request.current_bess_soc_kwh is None:
            raise ValueError("current_bess_soc_kwh required for BESS multi-appliance scheduling")

        schedules = multi_appliance_scheduler.schedule_all_appliances(
            appliances,
            [],  # No water heaters for now
            prices,
            solar,
            household_type,
            request.current_bess_soc_kwh or 0.0,
            request.household.bess_capacity_kwh,
            bess_min_soc,
            request.house_limit_kw
        )
        for schedule in schedules:
            background_runner.schedule_appliance(
                schedule.appliance_id, 
                schedule.start_time, 
                schedule.duration_seconds, 
                schedule.power_usage_kw
            )
        return schedules
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Appliance not found: {str(e)}")
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/prices/current/{bidding_zone}")
async def get_current_price(bidding_zone: str, lat: Optional[float] = None, lng: Optional[float] = None):
    """Get the current energy price for a location (Checking DB first, then real API)"""
    try:
        now = datetime.now()
        # Check DB first (in case browser synced it earlier)
        db_prices = db_service.get_latest_prices(bidding_zone, now.date())
        current_p = next((p for p in db_prices if p.start_time <= now < (p.start_time + timedelta(hours=1))), None)
        
        if current_p:
            return current_p
            
        # If not in DB, try real API
        # Create a temporary household-like object to carry the bidding_zone
        from collections import namedtuple
        HH = namedtuple('HH', ['bidding_zone'])
        temp_hh = HH(bidding_zone=bidding_zone)
        
        prices = await price_provider.get_day_ahead_prices(now.date(), household=temp_hh, lat=lat, lng=lng)
        current_p = next((p for p in prices if p.start_time <= now < (p.start_time + timedelta(hours=1))), None)
        return current_p or (prices[0] if prices else None)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))

@app.post("/prices/sync/{bidding_zone}")
async def sync_prices(bidding_zone: str, prices: List[EnergyPrice]):
    """Receive prices from frontend to ensure backend has real data even if its DNS is failing"""
    try:
        db_service.save_energy_prices(bidding_zone, prices)
        return {"status": "synced", "count": len(prices)}
    except Exception as e:
        logger.error(f"Failed to sync prices: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/matter/devices")
async def register_matter_device(request: MatterDeviceRegistrationRequest):
    try:
        device = MatterDevice(**request.dict())
        return matter_controller.register_device(device)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/matter/devices")
async def list_matter_devices():
    return matter_controller.list_devices()


@app.get("/matter/devices/{device_id}")
async def get_matter_device(device_id: str):
    try:
        return matter_controller.get_device(device_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/matter/devices/{device_id}")
async def delete_matter_device(device_id: str):
    try:
        return matter_controller.remove_device(device_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/matter/devices/{device_id}/command")
async def send_matter_command(device_id: str, request: MatterCommandRequest):
    try:
        return await matter_controller.send_command(
            device_id,
            request.command,
            request.payload or {},
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MatterControllerError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/matter/devices/{device_id}/schedule")
async def schedule_matter_device(device_id: str, request: MatterScheduleRequest):
    try:
        return await matter_controller.send_schedule_command(
            device_id,
            request.start_time,
            request.duration_seconds,
        )
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MatterControllerError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.get("/matter/devices/{device_id}/status")
async def matter_device_status(device_id: str):
    try:
        return await matter_controller.get_device_status(device_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except MatterControllerError as e:
        raise HTTPException(status_code=502, detail=str(e))


# Matter Commissioning Endpoints
@app.post("/matter/commission")
async def commission_matter_device(request: MatterCommissionRequest):
    """Commission a Matter device using QR code"""
    try:
        commissioned_device = await matter_commissioning.commission_device_via_qr(
            qr_code=request.qr_code,
            device_name=request.device_name,
            ip_address=request.ip_address,
            port=request.port,
            wifi_ssid=request.wifi_ssid,
            wifi_password=request.wifi_password,
            thread_dataset=request.thread_dataset,
            network_only=request.network_only,
        )

        # Also register with the matter controller for operation
        matter_controller.register_device(commissioned_device)

        return {
            "device": commissioned_device,
            "message": "Device commissioned successfully"
        }
    except MatterCommissioningError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/matter/discover")
async def discover_matter_devices():
    """Discover Matter devices on the network"""
    try:
        devices = await matter_commissioning.discover_devices()
        return {"devices": devices}
    except MatterCommissioningError as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/matter/commissioned-devices")
async def list_commissioned_devices():
    """List all commissioned Matter devices"""
    return matter_commissioning.list_commissioned_devices()


@app.get("/matter/commissioned-devices/{device_id}")
async def get_commissioned_device(device_id: str):
    """Get a specific commissioned device"""
    try:
        return matter_commissioning.get_commissioned_device(device_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.delete("/matter/commissioned-devices/{device_id}")
async def remove_commissioned_device(device_id: str):
    """Remove a commissioned device"""
    try:
        device = matter_commissioning.remove_commissioned_device(device_id)
        # Also remove from matter controller
        matter_controller.remove_device(device_id)
        return device
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/schedules")
async def get_schedules():
    """List all currently scheduled background jobs"""
    return {"jobs": background_runner.get_scheduled_jobs()}

@app.delete("/schedules/{job_id}")
async def cancel_schedule(job_id: str):
    """Cancel a scheduled background job"""
    if background_runner.cancel_job(job_id):
        return {"message": "Job cancelled"}
    raise HTTPException(status_code=404, detail="Job not found")


@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=os.getenv("API_HOST", "0.0.0.0"), port=int(os.getenv("API_PORT", "8000")), reload=True)
