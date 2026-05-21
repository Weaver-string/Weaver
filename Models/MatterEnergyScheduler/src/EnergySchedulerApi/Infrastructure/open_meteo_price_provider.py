from datetime import datetime, date, timedelta
from typing import List, Optional
from ..Models.energy_price import EnergyPrice

class OpenMeteoPriceProvider:
    """Provides real energy prices using Open-Meteo (No API Key required)"""
    
    # Use the specific energy subdomain for price data
    BASE_URLS = [
        "https://api.open-meteo.com/v1/forecast",
        "https://energy-api.open-meteo.com/v1/forecast"
    ]

    def _resolve_dns_doh(self, hostname: str) -> Optional[str]:
        """Use Google DNS-over-HTTPS to resolve a hostname if system DNS is blocked"""
        try:
            import requests
            print(f"DEBUG: Using Google DoH to resolve {hostname}...")
            # Using Google's JSON DNS API
            url = f"https://dns.google/resolve?name={hostname}&type=A"
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if "Answer" in data and len(data["Answer"]) > 0:
                    ip = data["Answer"][0]["data"]
                    print(f"DEBUG: Resolved {hostname} to {ip} via DoH")
                    return ip
        except Exception as e:
            print(f"DEBUG: DoH Resolution failed: {e}")
        return None

    async def get_day_ahead_prices(self, date: date, household: Optional[any] = None, lat: Optional[float] = None, lng: Optional[float] = None) -> List[EnergyPrice]:
        """
        Fetch electricity prices from Open-Meteo.
        """
        # Priority: Direct Lat/Lng > Household Coords > Default Central Europe
        final_lat = lat if lat is not None else (household.location_latitude if household and hasattr(household, 'location_latitude') else 50.0)
        final_lng = lng if lng is not None else (household.location_longitude if household and hasattr(household, 'location_longitude') else 10.0)
        
        # Bidding zone is mostly used for logging/debugging in this provider
        bidding_zone = household.bidding_zone if household and hasattr(household, 'bidding_zone') else "GENERIC"

        params = {
            "latitude": final_lat,
            "longitude": final_lng,
            "hourly": "electricity_price",
            "timezone": "auto",
            "start_date": date.isoformat(),
            "end_date": date.isoformat()
        }

        try:
            import requests
            import urllib.parse
            
            response = None
            
            for base_url in self.BASE_URLS:
                print(f"DEBUG: Attempting fetch for {base_url} (Lat: {final_lat}, Lng: {final_lng})")
                
                # Step 1: Direct Attempt
                try:
                    response = requests.get(base_url, params=params, timeout=8, verify=False)
                    if response.status_code == 200:
                        print(f"DEBUG: SUCCESS via Direct fetch for {base_url}")
                        break
                    response = None
                except Exception as e:
                    print(f"DEBUG: Direct fetch failed for {base_url}: {e}")

                # Step 2: Proxy 1 (AllOrigins)
                try:
                    query_string = urllib.parse.urlencode(params)
                    target_url = f"{base_url}?{query_string}"
                    encoded_target = urllib.parse.quote(target_url, safe='')
                    proxy_url = f"https://api.allorigins.win/raw?url={encoded_target}"
                    print(f"DEBUG: Trying Proxy 1 for {base_url}")
                    response = requests.get(proxy_url, timeout=12, verify=False)
                    if response.status_code == 200:
                        print(f"DEBUG: SUCCESS via Proxy 1 for {base_url}")
                        break
                    response = None
                except Exception as e:
                    print(f"DEBUG: Proxy 1 failed for {base_url}: {e}")

                # Step 3: Proxy 2 (CorsProxy)
                try:
                    query_string = urllib.parse.urlencode(params)
                    target_url = f"{base_url}?{query_string}"
                    proxy_url = f"https://corsproxy.io/?{urllib.parse.quote(target_url)}"
                    print(f"DEBUG: Trying Proxy 2 for {base_url}")
                    response = requests.get(proxy_url, timeout=12, verify=False)
                    if response.status_code == 200:
                        print(f"DEBUG: SUCCESS via Proxy 2 for {base_url}")
                        break
                    response = None
                except Exception as e:
                    print(f"DEBUG: Proxy 2 failed for {base_url}: {e}")
            
            if response is None or response.status_code != 200:
                print("DEBUG: All fetch attempts failed for all domains.")
                return self._generate_fallback_prices(date, bidding_zone)
            
            data = response.json()
            print(f"DEBUG: Open-Meteo Data Received: {str(data)[:500]}...") # Print first 500 chars
            
            if "hourly" not in data or "electricity_price" not in data["hourly"]:
                print(f"DEBUG: No price data in response for {final_lat}, {final_lng}. Available fields: {list(data.get('hourly', {}).keys())}")
                return self._generate_fallback_prices(date, bidding_zone)

            times = data["hourly"]["time"]
            prices = data["hourly"]["electricity_price"]
            
            result = []
            for t_str, p in zip(times, prices):
                if p is None:
                    continue
                # Open-Meteo returns EUR/MWh, we want EUR/kWh
                price_kwh = p / 1000.0
                result.append(EnergyPrice(
                    start_time=datetime.fromisoformat(t_str),
                    price_per_kwh=round(price_kwh, 4)
                ))
            
            if not result:
                return self._generate_fallback_prices(date, bidding_zone)
                         
            return result

        except Exception as e:
            # On network failure or API issues, return semi-realistic fallback data
            # so the app remains functional for the user.
            print(f"Open-Meteo fetch failed ({e}), using realistic fallback.")
            return self._generate_fallback_prices(date, bidding_zone)

    def _generate_fallback_prices(self, date: date, bidding_zone: str) -> List[EnergyPrice]:
        """Stable fallback if Open-Meteo doesn't have data for a specific coordinate"""
        zone_hash = sum(ord(c) for c in bidding_zone) % 10
        base_price = 0.15 + (zone_hash * 0.02)
        prices = []
        base_time = datetime.combine(date, datetime.min.time())
        for i in range(24):
            start_time = base_time + timedelta(hours=i)
            import math
            variation = 0.05 * math.sin((i - 6) * math.pi / 12)
            price = max(0.05, base_price + variation)
            prices.append(EnergyPrice(start_time=start_time, price_per_kwh=round(price, 3), is_real=False))
        return prices
