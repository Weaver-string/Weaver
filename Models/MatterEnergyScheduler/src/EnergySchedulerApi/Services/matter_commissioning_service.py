import asyncio
from datetime import datetime
from typing import Dict, Optional, Any

import aiohttp

from ..Models.matter_device import MatterDevice
from .matter_server_ws_client import MatterServerError
from .database_service import DatabaseService
from ..Models.appliance import Appliance


class MatterCommissioningError(Exception):
    pass


class MatterCommissioningService:
    """Service for commissioning Matter devices using QR codes"""

    def __init__(
        self,
        fabric_id: int = 1,
        db_service: Optional[DatabaseService] = None,
        ws_url: Optional[str] = None,
    ):
        self.fabric_id = fabric_id
        self.db_service = db_service or DatabaseService()
        self.ws_url = ws_url

    async def commission_device_via_qr(
        self,
        qr_code: str,
        device_name: str,
        ip_address: str,
        port: int = 5540,
        *,
        wifi_ssid: Optional[str] = None,
        wifi_password: Optional[str] = None,
        thread_dataset: Optional[str] = None,
        network_only: bool = False,
    ) -> MatterDevice:
        """
        Commission a Matter device using QR code data.
        """
        session = None
        client = None
        try:
            session = aiohttp.ClientSession()
            from matter_server.client import MatterClient
            from .matter_server_ws_client import MatterServerWsClient

            ws_url = self.ws_url or MatterServerWsClient().ws_url
            client = MatterClient(ws_url, session)
            await asyncio.wait_for(client.connect(), timeout=15)

            # Configure WiFi/Thread credentials
            if wifi_ssid and wifi_password:
                await client.set_wifi_credentials(wifi_ssid, wifi_password)
            if thread_dataset:
                await client.set_thread_operational_dataset(thread_dataset)

            # Commission via python-matter-server
            result = await asyncio.wait_for(
                client.commission_with_code(qr_code, network_only=network_only),
                timeout=60,
            )

            node_id = result.node_id if hasattr(result, "node_id") else None
            if node_id is None and isinstance(result, dict):
                node_id = result.get("node_id") or result.get("data", {}).get("node_id")
            
            if node_id is None:
                nodes = list(client.nodes.values())
                if nodes:
                    node_ids = [getattr(n, "node_id", None) for n in nodes]
                    node_ids = [n for n in node_ids if isinstance(n, int)]
                    node_id = max(node_ids) if node_ids else None

            if node_id is None:
                raise MatterCommissioningError(f"Commissioning succeeded but node_id was not returned: {result}")

            # --- INTROSPECTION PHASE ---
            # commission_with_code already returns a MatterNodeData object. The
            # client cache may not be populated yet, so prefer the returned data
            # and fall back to the local cache only when needed.
            node = None
            try:
                node = client.get_node(node_id)
            except Exception:
                node = None

            node_data = getattr(node, "node_data", None) or result
            attributes = getattr(node_data, "attributes", {}) or {}
            
            # 3. Identify and Validate Device (New!)
            # We check if it has appliance-like clusters (at least OnOff for now)
            onoff_endpoint_id = None
            if node is not None:
                for endpoint_id, endpoint in node.endpoints.items():
                    if endpoint.has_cluster(6):
                        onoff_endpoint_id = endpoint_id
                        break
            if onoff_endpoint_id is None:
                for path in attributes:
                    parts = path.split("/")
                    if len(parts) >= 2 and parts[1] == "6":
                        onoff_endpoint_id = int(parts[0])
                        break

            has_control = onoff_endpoint_id is not None
            
            if not has_control:
                raise ValueError("Device identified but is not a controllable appliance (missing OnOff cluster).")

            # Map Matter Device Types to Weaver Appliance Names and default power
            # 0x0052 = Dishwasher, 0x010A = Smart Plug, etc.
            device_type_id = None
            for path, value in attributes.items():
                if path.endswith("/29/0") and isinstance(value, list) and value:
                    first_type = value[0]
                    if isinstance(first_type, dict):
                        device_type_id = first_type.get("deviceType")
                    else:
                        device_type_id = getattr(first_type, "deviceType", None)
                    break
            
            # Smart defaults based on device type
            auto_name = getattr(node, "name", None) or f"Matter Device {node_id}"
            vendor_id = attributes.get("0/40/2")
            product_id = attributes.get("0/40/4")
            auto_power = 2.0 # Default fallback
            auto_duration = 3600 # Default 1h
            
            if device_type_id == 0x0052: # Dishwasher
                auto_power = 2.2
                auto_duration = 7200
            elif device_type_id == 0x0073: # Washing Machine
                auto_power = 2.0
                auto_duration = 5400
            elif device_type_id == 0x0074: # Laundry Dryer
                auto_power = 3.0
                auto_duration = 3600
            elif device_type_id == 0x00B5: # EV Charger
                auto_power = 7.4
                auto_duration = 14400
            elif device_type_id == 0x010A: # Smart Plug
                auto_power = 1.5
                auto_duration = 3600

            device = MatterDevice(
                name=auto_name,
                matter_device_id=f"matter_{node_id}",
                ip_address=ip_address,
                port=port,
                device_type="matter",
                node_id=node_id,
                fabric_id=self.fabric_id,
                vendor_id=vendor_id if isinstance(vendor_id, int) else None,
                product_id=product_id if isinstance(product_id, int) else None,
                commissioning_date=datetime.now().isoformat(),
                setup_code=qr_code,
                discriminator=None,
                operational_credentials=None,
            )

            # Store commissioned device in Database
            self.db_service.save_matter_device(device)

            # AUTO-REGISTER AS APPLIANCE
            # This makes the device immediately available in the UI list
            new_appliance = Appliance(
                name=auto_name,
                power_usage_kw=auto_power,
                duration_seconds=auto_duration,
                deadline=datetime.now(), # Default to now, will be updated by user
                matter_device_id=device.matter_device_id,
                matter_device_ip=device.ip_address,
                matter_device_port=onoff_endpoint_id or 1,
                matter_node_id=device.node_id
            )
            self.db_service.save_appliance(new_appliance)

            return device

        except MatterServerError as e:
            raise MatterCommissioningError(str(e))
        except asyncio.TimeoutError as e:
            raise MatterCommissioningError(
                "Timed out while commissioning via python-matter-server. "
                "Confirm matter-server is running and the appliance is still advertising as uncommissioned."
            ) from e
        except Exception as e:
            detail = str(e) or e.__class__.__name__
            raise MatterCommissioningError(f"Commissioning failed: {detail}") from e
        finally:
            if client is not None:
                await client.disconnect()
            if session is not None:
                await session.close()

    async def discover_devices(self, network_timeout: int = 30) -> list[Dict[str, Any]]:
        """
        Discover commissionable Matter devices through python-matter-server.
        """
        try:
            discovered = await self._ws.call("discover", timeout_s=float(network_timeout))
            if isinstance(discovered, list):
                return discovered
            return []
        except MatterServerError as e:
            raise MatterCommissioningError(str(e))

    def get_commissioned_device(self, device_id: str) -> MatterDevice:
        """Get a commissioned device by ID"""
        device = self.db_service.get_matter_device(device_id)
        if not device:
            raise KeyError(f"Commissioned device '{device_id}' not found")
        return device

    def list_commissioned_devices(self) -> list[MatterDevice]:
        """List all commissioned devices"""
        return self.db_service.list_matter_devices()

    def remove_commissioned_device(self, device_id: str) -> MatterDevice:
        """Remove a commissioned device"""
        device = self.get_commissioned_device(device_id)
        self.db_service.delete_matter_device(device_id)
        return device
