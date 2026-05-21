from typing import List
from datetime import datetime
from ..Models.appliance import Appliance
from .database_service import DatabaseService


class ApplianceRegistry:
    """Manages registered appliances for scheduling with SQLite storage"""

    def __init__(self, db_service: DatabaseService):
        self.db_service = db_service

    def register_appliance(self, appliance: Appliance) -> Appliance:
        """Register a new appliance"""
        self.db_service.save_appliance(appliance)
        return appliance

    def list_appliances(self) -> List[Appliance]:
        """List all registered appliances"""
        return self.db_service.list_appliances()

    def get_appliance(self, appliance_id: str) -> Appliance:
        """Get a specific appliance by ID"""
        appliance = self.db_service.get_appliance(appliance_id)
        if not appliance:
            raise KeyError(f"Appliance '{appliance_id}' not found")
        return appliance

    def update_appliance(self, appliance_id: str, updates: dict) -> Appliance:
        """Update an appliance's properties"""
        appliance = self.get_appliance(appliance_id)

        # Update allowed fields
        for key, value in updates.items():
            if hasattr(appliance, key) and key != 'id':
                setattr(appliance, key, value)

        self.db_service.save_appliance(appliance)
        return appliance

    def set_deadline(self, appliance_id: str, deadline: datetime) -> Appliance:
        """Set a deadline for an appliance"""
        appliance = self.get_appliance(appliance_id)
        appliance.deadline = deadline
        self.db_service.save_appliance(appliance)
        return appliance

    def remove_appliance(self, appliance_id: str) -> Appliance:
        """Remove an appliance from registry"""
        appliance = self.get_appliance(appliance_id)
        self.db_service.delete_appliance(appliance_id)
        return appliance

    def get_appliances_by_matter_device(self, matter_device_id: str) -> List[Appliance]:
        """Get all appliances associated with a Matter device"""
        return [
            appliance for appliance in self.list_appliances()
            if appliance.matter_device_id == matter_device_id
        ]
