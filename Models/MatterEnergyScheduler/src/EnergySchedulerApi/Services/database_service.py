from ..Infrastructure.database import SessionLocal, engine, Base
from ..Infrastructure.db_models import DmHousehold, DmAppliance, DmMatterDevice, DmSchedule
from ..Models.appliance import Appliance
from ..Models.household import Household
from ..Models.matter_device import MatterDevice
from ..Models.scheduled_appliance import ScheduledAppliance
from ..Models.energy_price import EnergyPrice
from typing import List, Optional
from datetime import datetime, date, timedelta
import logging

logger = logging.getLogger(__name__)

class DatabaseService:
    def __init__(self):
        # Create tables if they don't exist
        Base.metadata.create_all(bind=engine)

    def get_db(self):
        return SessionLocal()

    # Appliance CRUD

    def save_appliance(self, appliance: Appliance):
        with self.get_db() as db:
            db_app = DmAppliance(
                id=appliance.id,
                name=appliance.name,
                power_usage_kw=appliance.power_usage_kw,
                duration_seconds=appliance.duration_seconds,
                deadline=appliance.deadline,
                matter_device_id=appliance.matter_device_id,
                matter_device_ip=appliance.matter_device_ip,
                matter_device_port=appliance.matter_device_port,
                matter_node_id=appliance.matter_node_id,
                device_type=appliance.device_type,
                stored_fingerprint=appliance.power_profile
            )
            db.merge(db_app)
            db.commit()

    def get_appliance(self, appliance_id: str) -> Optional[Appliance]:
        with self.get_db() as db:
            db_appliance = db.query(DmAppliance).filter(DmAppliance.id == appliance_id).first()
            if db_appliance:
                return Appliance(
                    id=db_appliance.id,
                    name=db_appliance.name,
                    power_usage_kw=db_appliance.power_usage_kw,
                    duration_seconds=db_appliance.duration_seconds,
                    deadline=db_appliance.deadline,
                    matter_device_id=db_appliance.matter_device_id,
                    matter_device_ip=db_appliance.matter_device_ip,
                    matter_device_port=db_appliance.matter_device_port,
                    matter_node_id=db_appliance.matter_node_id,
                    device_type=db_appliance.device_type
                )
            return None

    def list_appliances(self) -> List[Appliance]:
        with self.get_db() as db:
            db_appliances = db.query(DmAppliance).all()
            return [
                Appliance(
                    id=a.id,
                    name=a.name,
                    power_usage_kw=a.power_usage_kw,
                    duration_seconds=a.duration_seconds,
                    deadline=a.deadline,
                    matter_device_id=a.matter_device_id,
                    matter_device_ip=a.matter_device_ip,
                    matter_device_port=a.matter_device_port,
                    matter_node_id=a.matter_node_id,
                    device_type=a.device_type,
                    power_profile=a.stored_fingerprint or []
                ) for a in db_appliances
            ]

    def delete_appliance(self, appliance_id: str):
        with self.get_db() as db:
            db.query(DmAppliance).filter(DmAppliance.id == appliance_id).delete()
            db.commit()

    # Matter Device CRUD
    def save_matter_device(self, device: MatterDevice):
        with self.get_db() as db:
            db_device = DmMatterDevice(
                id=device.id,
                name=device.name,
                matter_device_id=device.matter_device_id,
                ip_address=device.ip_address,
                port=device.port,
                device_type=device.device_type,
                command_path=device.command_path,
                status_path=device.status_path,
                node_id=device.node_id,
                fabric_id=device.fabric_id,
                vendor_id=device.vendor_id,
                product_id=device.product_id,
                commissioning_date=device.commissioning_date,
                operational_credentials=device.operational_credentials,
                setup_code=device.setup_code,
                discriminator=device.discriminator,
                commissioning_passcode=device.commissioning_passcode
            )
            db.merge(db_device)
            db.commit()

    def get_matter_device(self, device_id: str) -> Optional[MatterDevice]:
        with self.get_db() as db:
            db_device = db.query(DmMatterDevice).filter(DmMatterDevice.id == device_id).first()
            if db_device:
                return MatterDevice(
                    id=db_device.id,
                    name=db_device.name,
                    matter_device_id=db_device.matter_device_id,
                    ip_address=db_device.ip_address,
                    port=db_device.port,
                    device_type=db_device.device_type,
                    command_path=db_device.command_path,
                    status_path=db_device.status_path,
                    node_id=db_device.node_id,
                    fabric_id=db_device.fabric_id,
                    vendor_id=db_device.vendor_id,
                    product_id=db_device.product_id,
                    commissioning_date=db_device.commissioning_date,
                    operational_credentials=db_device.operational_credentials,
                    setup_code=db_device.setup_code,
                    discriminator=db_device.discriminator,
                    commissioning_passcode=db_device.commissioning_passcode
                )
            return None

    def list_matter_devices(self) -> List[MatterDevice]:
        with self.get_db() as db:
            db_devices = db.query(DmMatterDevice).all()
            return [MatterDevice(
                id=d.id,
                name=d.name,
                matter_device_id=d.matter_device_id,
                ip_address=d.ip_address,
                port=d.port,
                device_type=d.device_type,
                command_path=d.command_path,
                status_path=d.status_path,
                node_id=d.node_id,
                fabric_id=d.fabric_id,
                vendor_id=d.vendor_id,
                product_id=d.product_id,
                commissioning_date=d.commissioning_date,
                operational_credentials=d.operational_credentials,
                setup_code=d.setup_code,
                discriminator=d.discriminator,
                commissioning_passcode=d.commissioning_passcode
            ) for d in db_devices]

    def delete_matter_device(self, device_id: str):
        with self.get_db() as db:
            db.query(DmMatterDevice).filter(DmMatterDevice.id == device_id).delete()
            db.commit()

    # Schedule Persistence
    def save_schedule(self, schedule: ScheduledAppliance, job_id: str, is_daily: bool = False):
        with self.get_db() as db:
            db_schedule = DmSchedule(
                appliance_id=schedule.appliance_id,
                start_time=schedule.start_time,
                duration_seconds=schedule.duration_seconds,
                power_usage_kw=schedule.power_usage_kw,
                job_id=job_id,
                status="pending",
                is_daily=is_daily
            )
            db.add(db_schedule)
            db.commit()

    def get_pending_schedules(self) -> List[dict]:
        with self.get_db() as db:
            db_schedules = db.query(DmSchedule).filter(DmSchedule.status == "pending").all()
            return [
                {
                    "appliance_id": s.appliance_id,
                    "start_time": s.start_time,
                    "duration_seconds": s.duration_seconds,
                    "power_usage_kw": s.power_usage_kw,
                    "job_id": s.job_id,
                    "is_daily": s.is_daily
                } for s in db_schedules
            ]

    def update_schedule_status(self, job_id: str, status: str):
        with self.get_db() as db:
            db.query(DmSchedule).filter(DmSchedule.job_id == job_id).update({"status": status})
            db.commit()

    # Household CRUD
    def save_household(self, household: Household):
        with self.get_db() as db:
            db_household = DmHousehold(
                id=household.id,
                household_type=household.household_type.value if hasattr(household.household_type, 'value') else str(household.household_type),
                location_latitude=household.location_latitude,
                location_longitude=household.location_longitude,
                pv_capacity_kw=household.pv_capacity_kw,
                bess_capacity_kwh=household.bess_capacity_kwh,
                bess_min_soc_percent=household.bess_min_soc_percent,
                bess_device_id=household.bess_device_id,
                bess_device_ip=household.bess_device_ip,
                bess_device_port=household.bess_device_port,
                bidding_zone=household.bidding_zone
            )
            db.merge(db_household)
            db.commit()

    def update_household(self, household_id: str, data: dict):
        with self.get_db() as db:
            db.query(DmHousehold).filter(DmHousehold.id == household_id).update(data)
            db.commit()

    def get_household(self, household_id: str) -> Optional[Household]:
        with self.get_db() as db:
            db_h = db.query(DmHousehold).filter(DmHousehold.id == household_id).first()
            if db_h:
                return Household(
                    id=db_h.id,
                    household_type=db_h.household_type,
                    location_latitude=db_h.location_latitude,
                    location_longitude=db_h.location_longitude,
                    pv_capacity_kw=db_h.pv_capacity_kw,
                    bess_capacity_kwh=db_h.bess_capacity_kwh,
                    bess_min_soc_percent=db_h.bess_min_soc_percent,
                    bess_device_id=db_h.bess_device_id,
                    bess_device_ip=db_h.bess_device_ip,
                    bess_device_port=db_h.bess_device_port,
                    bidding_zone=db_h.bidding_zone
                )
            return None

    def list_households(self) -> List[Household]:
        with self.get_db() as db:
            db_households = db.query(DmHousehold).all()
            return [
                Household(
                    id=h.id,
                    household_type=h.household_type,
                    location_latitude=h.location_latitude,
                    location_longitude=h.location_longitude,
                    pv_capacity_kw=h.pv_capacity_kw,
                    bess_capacity_kwh=h.bess_capacity_kwh,
                    bess_min_soc_percent=h.bess_min_soc_percent,
                    bess_device_id=h.bess_device_id,
                    bess_device_ip=h.bess_device_ip,
                    bess_device_port=h.bess_device_port,
                    bidding_zone=h.bidding_zone
                ) for h in db_households
            ]

    def cleanup_old_schedules(self, days: int = 7):
        """Remove schedules older than X days that are not pending"""
        cutoff = datetime.now() - timedelta(days=days)
        with self.get_db() as db:
            db.query(DmSchedule).filter(
                DmSchedule.start_time < cutoff,
                DmSchedule.status != "pending"
            ).delete()
            db.commit()
            logger.info(f"Cleaned up database records older than {days} days.")

    # Price Persistence
    def save_energy_prices(self, bidding_zone: str, prices: List[EnergyPrice]):
        with self.get_db() as db:
            from ..Infrastructure.db_models import DmEnergyPrice
            for p in prices:
                db_price = DmEnergyPrice(
                    bidding_zone=bidding_zone,
                    start_time=p.start_time,
                    price_per_kwh=p.price_per_kwh,
                    is_real=p.is_real,
                    updated_at=datetime.now()
                )
                # Simple deduplication: delete existing price for same time/zone
                db.query(DmEnergyPrice).filter(
                    DmEnergyPrice.bidding_zone == bidding_zone,
                    DmEnergyPrice.start_time == p.start_time
                ).delete()
                db.add(db_price)
            db.commit()
            logger.info(f"Saved {len(prices)} prices for zone {bidding_zone}")

    def get_latest_prices(self, bidding_zone: str, target_date: date) -> List[EnergyPrice]:
        with self.get_db() as db:
            from ..Infrastructure.db_models import DmEnergyPrice
            start_of_day = datetime.combine(target_date, datetime.min.time())
            end_of_day = datetime.combine(target_date, datetime.max.time())
            
            db_prices = db.query(DmEnergyPrice).filter(
                DmEnergyPrice.bidding_zone == bidding_zone,
                DmEnergyPrice.start_time >= start_of_day,
                DmEnergyPrice.start_time <= end_of_day
            ).order_by(DmEnergyPrice.start_time).all()
            
            return [
                EnergyPrice(
                    start_time=p.start_time,
                    price_per_kwh=p.price_per_kwh,
                    is_real=p.is_real
                ) for p in db_prices
            ]
