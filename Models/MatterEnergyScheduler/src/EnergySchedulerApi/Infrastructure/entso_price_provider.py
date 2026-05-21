from typing import List, Optional, Any
from datetime import datetime, date, timedelta
import json
import logging
import os
from pathlib import Path
from ..Models.energy_price import EnergyPrice
from .provider_errors import ProviderError

logger = logging.getLogger(__name__)


class EntsoePriceProvider:
    """Fetch ENTSO-E day-ahead prices, falling back only when live data is unavailable."""
    BASE_URL = "https://data.transparency.entsoe.eu/api"
    CACHE_DIR = Path("data/price_cache")
    FALLBACK_BASELINES_EUR_KWH = {
        # Approximate recent day-ahead wholesale averages converted from EUR/MWh to EUR/kWh.
        # These are fallback baselines only; live ENTSO-E data is always attempted first.
        "10YAL-KESH-----5": 0.095,  # Albania
        "10YAT-APG------L": 0.085,  # Austria
        "10YBE----------2": 0.082,  # Belgium
        "10YCA-BULGARIA-R": 0.100,  # Bulgaria
        "10YCH-SWISSGRIDZ": 0.095,  # Switzerland
        "10YCY-1001A0003J": 0.130,  # Cyprus
        "10YCZ-CEPS-----N": 0.095,  # Czech Republic
        "10YDOM-1001A082P": 0.090,  # Germany/Luxembourg
        "10YDE-RWENET---I": 0.090,  # Germany alias used by location lookup
        "10Y1001A1001A83F": 0.090,  # Germany/Luxembourg legacy alias
        "10YDK-1-------W": 0.075,  # Denmark DK1
        "10YDK-2-------M": 0.085,  # Denmark DK2
        "10Y1001A1001A391": 0.095,  # Estonia
        "10YES-REE------0": 0.066,  # Spain
        "10YFI-1--------U": 0.065,  # Finland
        "10YFR-RTE------C": 0.062,  # France
        "10Y1001A1001B012": 0.090,  # Georgia
        "10YGR-HTSO-----Y": 0.103,  # Greece
        "10YHR-HEP------M": 0.105,  # Croatia
        "10YHU-MAVIR----U": 0.110,  # Hungary
        "10IEA-TRAN------M": 0.117,  # Ireland SEM
        "10YIEA-TRAN------M": 0.117,  # Ireland SEM legacy alias
        "10Y1001A1001A016": 0.117,  # Northern Ireland SEM
        "10YITA-NORTH---N": 0.105,  # Italy North
        "10YIT-NORTH---N": 0.105,  # Italy North alias used by location lookup
        "10YITA-CNORTH--1": 0.108,  # Italy Center North
        "10YITA-CSOUTH--W": 0.112,  # Italy Center South
        "10YITA-SOUTH---8": 0.115,  # Italy South
        "10YITA-SICILY--Q": 0.120,  # Italy Sicily
        "10YITA-SARDINIA-R": 0.118,  # Italy Sardinia
        "10YIT-GRTN-----B": 0.108,  # Italy aggregate legacy alias
        "10YLT-1001A0008Q": 0.100,  # Lithuania
        "10YLV-1001A00074": 0.100,  # Latvia
        "10YME-EPCG-----P": 0.095,  # Montenegro
        "10YMK-MEPSO----8": 0.100,  # North Macedonia
        "10YNL----------L": 0.083,  # Netherlands
        "10YNO-1-------2": 0.055,  # Norway NO1
        "10YNO-2-------T": 0.065,  # Norway NO2
        "10YNO-3-------P": 0.045,  # Norway NO3
        "10YNO-4-------9": 0.035,  # Norway NO4
        "10YNO-5-------E": 0.050,  # Norway NO5
        "10YPL-AREA-----S": 0.106,  # Poland
        "10YPL-TSO------P": 0.106,  # Poland legacy alias
        "10YPT-REN------W": 0.066,  # Portugal
        "10YRO-TEL------P": 0.105,  # Romania
        "10YCS-SERBIATSOV": 0.105,  # Serbia
        "10YSE-1-------K": 0.035,  # Sweden SE1
        "10YSE-2-------L": 0.040,  # Sweden SE2
        "10YSE-3-------M": 0.060,  # Sweden SE3
        "10YSE-4-------9": 0.075,  # Sweden SE4
        "10YSI-ELES-----W": 0.095,  # Slovenia
        "10YSK-SEPS-----K": 0.095,  # Slovakia
        "10YTR-TEIAS----W": 0.085,  # Turkey
        "10YUA-WEPS-----0": 0.090,  # Ukraine
        "10YGB----------A": 0.095,  # Great Britain, GBP average approximated in EUR
    }
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    
    def _get_cache_file(self, target_date: date, bidding_zone: str) -> Path:
        """Get cache file path for a specific date and bidding zone"""
        return self.CACHE_DIR / f"prices_{bidding_zone}_{target_date.isoformat()}.json"

    def _to_naive(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value
        return value.astimezone().replace(tzinfo=None)
    
    def _save_prices_to_cache(self, target_date: date, bidding_zone: str, prices: List[EnergyPrice]) -> None:
        """Save prices to local cache"""
        try:
            cache_file = self._get_cache_file(target_date, bidding_zone)
            data = [
                {
                    "start_time": p.start_time.isoformat(),
                    "price_per_kwh": p.price_per_kwh
                }
                for p in prices
            ]
            with open(cache_file, 'w') as f:
                json.dump(data, f)
        except Exception:
            logger.warning("Failed to write ENTSO-E price cache for %s", target_date, exc_info=True)
    
    def _load_prices_from_cache(self, target_date: date, bidding_zone: str) -> List[EnergyPrice]:
        """Load prices from local cache"""
        cache_file = self._get_cache_file(target_date, bidding_zone)
        if not cache_file.exists():
            return []
        
        try:
            with open(cache_file, 'r') as f:
                data = json.load(f)
                prices = [
                    EnergyPrice(
                        start_time=self._to_naive(datetime.fromisoformat(p["start_time"])),
                        price_per_kwh=p["price_per_kwh"]
                    )
                    for p in data
                ]
                return prices
        except Exception:
            logger.warning("Failed to read ENTSO-E price cache for %s", target_date, exc_info=True)
            return []
    
    def _shift_prices_to_date(self, prices: List[EnergyPrice], target_date: date) -> List[EnergyPrice]:
        """Shift cached prices from previous day to target date"""
        if not prices:
            return []
        
        # Get the date from the first price
        source_date = prices[0].start_time.date()
        days_diff = (target_date - source_date).days
        
        # Shift all prices by the date difference
        shifted_prices = [
            EnergyPrice(
                start_time=p.start_time + timedelta(days=days_diff),
                price_per_kwh=p.price_per_kwh,
                is_real=False,
            )
            for p in prices
        ]
        return shifted_prices

    def _generate_fallback_prices(self, target_date: date, bidding_zone: str) -> List[EnergyPrice]:
        """
        Generate deterministic fallback prices for offline/demo scheduling.

        These are only used after live ENTSO-E fetches and cache fallbacks fail.
        They are intentionally marked as non-real and are not written to the
        live price cache.
        """
        import math

        if bidding_zone in self.FALLBACK_BASELINES_EUR_KWH:
            base_price = self.FALLBACK_BASELINES_EUR_KWH[bidding_zone]
        else:
            zone_hash = sum(ord(c) for c in bidding_zone) % 6
            base_price = 0.085 + (zone_hash * 0.006)
        base_time = datetime.combine(target_date, datetime.min.time())
        prices: List[EnergyPrice] = []

        for hour in range(24):
            # Cheap overnight, a modest midday dip, and a clear evening peak.
            overnight_discount = -0.045 if 0 <= hour <= 5 else 0
            midday_discount = -0.025 if 11 <= hour <= 15 else 0
            evening_peak = 0.075 if 17 <= hour <= 21 else 0
            smooth_variation = 0.018 * math.sin((hour - 7) * math.pi / 12)
            price = max(0.015, base_price + overnight_discount + midday_discount + evening_peak + smooth_variation)

            prices.append(
                EnergyPrice(
                    start_time=base_time + timedelta(hours=hour),
                    price_per_kwh=round(price, 4),
                    is_real=False,
                )
            )

        return prices

    def _get_fallback_prices(self, target_date: date, bidding_zone: str) -> List[EnergyPrice]:
        """Prefer real cached data shifted to the target date, then synthetic fallback prices."""
        cached_today = self._load_prices_from_cache(target_date, bidding_zone)
        if cached_today:
            logger.warning("Using cached ENTSO-E prices for %s/%s as fallback", bidding_zone, target_date)
            return [
                EnergyPrice(
                    start_time=p.start_time,
                    price_per_kwh=p.price_per_kwh,
                    is_real=False,
                )
                for p in cached_today
            ]

        for days_back in range(1, 8):
            previous_date = target_date - timedelta(days=days_back)
            cached_prices = self._load_prices_from_cache(previous_date, bidding_zone)
            if cached_prices:
                logger.warning(
                    "Using cached ENTSO-E prices from %s shifted to %s as fallback for %s",
                    previous_date,
                    target_date,
                    bidding_zone,
                )
                return self._shift_prices_to_date(cached_prices, target_date)

        logger.warning("Using generated fallback prices for %s/%s", bidding_zone, target_date)
        return self._generate_fallback_prices(target_date, bidding_zone)
    
    async def get_day_ahead_prices(self, target_date: date, household: Optional[Any] = None, lat: Optional[float] = None, lng: Optional[float] = None) -> List[EnergyPrice]:
        """
        Fetch day-ahead prices for a specific bidding zone.
        """
        # 1. Determine bidding zone
        bidding_zone = None
        
        # Priority: Direct coordinates (if possible to map) > Household object
        if lat is not None and lng is not None:
            from ..Services.location_service import LocationService
            bidding_zone = LocationService.get_bidding_zone_from_coords(lat, lng)
        
        if not bidding_zone and household and hasattr(household, 'bidding_zone'):
            bidding_zone = household.bidding_zone
            
        if not bidding_zone:
            # If no zone is found and no household is provided, we can't fetch official prices.
            # We return empty list instead of guessing.
            logger.debug("No bidding zone provided for ENTSO-E. Returning empty list.")
            return []

        if os.getenv("WEAVER_LIVE_PRICES", "0").lower() not in {"1", "true", "yes"}:
            logger.info("Using offline/demo fallback prices for %s/%s", bidding_zone, target_date)
            return self._get_fallback_prices(target_date, bidding_zone)
        
        # ENTSO-E format: YYYYMMDDHHMM
        period_start = target_date.strftime("%Y%m%d") + "0000"
        period_end = (target_date + timedelta(days=1)).strftime("%Y%m%d") + "0000"
        
        params = {
            "securityToken": self.api_key,
            "documentType": "A44",  # Day-ahead prices
            "in_Domain": bidding_zone,
            "out_Domain": bidding_zone,
            "periodStart": period_start,
            "periodEnd": period_end
        }
        
        try:
            if not self.api_key or self.api_key == "YOUR_TOKEN_HERE":
                raise ProviderError("No ENTSO-E API Key provided.")

            import requests
            import urllib.parse
            
            query_string = urllib.parse.urlencode(params)
            target_url = f"{self.BASE_URL}/query?{query_string}"
            
            response = None
            # Step 1: Direct Attempt
            try:
                logger.debug("ENTSO-E direct fetch attempt")
                response = requests.get(target_url, timeout=10, verify=False)
                resp_text = response.text.strip().lower()
                if response.status_code != 200 or resp_text.startswith("<!doctype") or "<html" in resp_text[:100]:
                    logger.debug("ENTSO-E direct fetch failed or returned HTML")
                    response = None
                else:
                    logger.debug("ENTSO-E direct fetch succeeded")
            except Exception as e:
                logger.debug("ENTSO-E direct fetch failed: %s", e)

            # Step 2: Proxy 1 (AllOrigins - with JSON unwrapping)
            if response is None:
                try:
                    encoded_target = urllib.parse.quote(target_url, safe='')
                    proxy_url = f"https://api.allorigins.win/get?url={encoded_target}"
                    logger.debug("Trying ENTSO-E proxy 1")
                    proxy_resp = requests.get(proxy_url, timeout=15, verify=False)
                    if proxy_resp.status_code == 200:
                        json_data = proxy_resp.json()
                        content = json_data.get("contents", "").strip()
                        if content and not content.lower().startswith("<!doctype") and "<html" not in content.lower()[:100]:
                            # Create a dummy response object to fit the rest of the logic
                            class DummyResponse:
                                def __init__(self, text): 
                                    self.text = text
                                    self.status_code = 200
                            response = DummyResponse(content)
                            logger.debug("ENTSO-E proxy 1 succeeded")
                except Exception as e:
                    logger.debug("ENTSO-E proxy 1 failed: %s", e)

            # Step 3: Proxy 2 (CorsProxy)
            if response is None:
                try:
                    proxy_url = f"https://corsproxy.io/?{urllib.parse.quote(target_url)}"
                    logger.debug("Trying ENTSO-E proxy 2")
                    proxy_resp = requests.get(proxy_url, timeout=15, verify=False)
                    resp_text = proxy_resp.text.strip().lower()
                    if proxy_resp.status_code == 200 and not resp_text.startswith("<!doctype") and "<html" not in resp_text[:100]:
                        response = proxy_resp
                        logger.debug("ENTSO-E proxy 2 succeeded")
                except Exception as e:
                    logger.debug("ENTSO-E proxy 2 failed: %s", e)

            if response is None or response.status_code != 200:
                raise ProviderError("All ENTSO-E fetch routes failed.")

            prices = self._parse_entso_response(response.text, target_date)
            if not prices:
                raise ProviderError("ENTSO-E returned no price points.")

            prices = [
                EnergyPrice(start_time=self._to_naive(p.start_time), price_per_kwh=p.price_per_kwh, is_real=p.is_real)
                for p in prices
            ]
            self._save_prices_to_cache(target_date, bidding_zone, prices)
            return prices
        except Exception as e:
            logger.warning("ENTSO-E fetch failed for %s: %s", bidding_zone, e)
            return self._get_fallback_prices(target_date, bidding_zone)
    
    def _parse_entso_response(self, xml_response: str, target_date: date) -> List[EnergyPrice]:
        """Parse ENTSO-E XML response into EnergyPrice objects"""
        import xml.etree.ElementTree as ET
        
        prices = []
        try:
            # Clean up response text in case of proxy issues
            xml_text = xml_response.strip()
            if not xml_text.startswith('<?xml') and '<Publication_MarketDocument' not in xml_text:
                # If it doesn't look like XML, it might be a proxy error message
                raise ValueError(f"Invalid XML response: {xml_text[:200]}...")

            root = ET.fromstring(xml_text)
            
            # Use namespace-agnostic findall
            # This handles different ENTSO-E document versions (PublicationDocument, etc.)
            for time_series in root.findall('.//{*}TimeSeries'):
                period = time_series.find('{*}Period')
                if period is None:
                    continue
                
                start_str = period.findtext('{*}timeInterval/{*}start', '')
                if not start_str:
                    continue
                
                try:
                    start_time = datetime.fromisoformat(start_str.replace('Z', '+00:00'))
                except ValueError:
                    continue
                
                for point in period.findall('{*}Point'):
                    position = int(point.findtext('{*}position', '1'))
                    price_str = point.findtext('{*}price.amount', '0')
                    
                    try:
                        price_eur_mwh = float(price_str)
                        price_eur_kwh = price_eur_mwh / 1000
                        
                        # Calculate time (assume 60-min intervals for Day Ahead Publication Document)
                        # ENTSO-E usually specifies resolution (PT60M, PT15M, etc.)
                        res_str = period.findtext('{*}resolution', 'PT60M')
                        interval_mins = 60
                        if 'PT15M' in res_str:
                            interval_mins = 15
                        elif 'PT30M' in res_str:
                            interval_mins = 30
                        
                        point_time = start_time + timedelta(minutes=interval_mins * (position - 1))
                        
                        prices.append(EnergyPrice(
                            start_time=point_time,
                            price_per_kwh=price_eur_kwh
                        ))
                    except (ValueError, IndexError):
                        continue
            
            if not prices:
                logger.debug("No prices found in ENTSO-E XML. Root tag: %s", root.tag)
                
            return sorted(prices, key=lambda p: p.start_time)
        except Exception as e:
            logger.error(f"Failed to parse ENTSO-E XML: {e}")
            raise ValueError(f"Failed to parse ENTSO-E XML response: {str(e)}")
