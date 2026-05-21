from typing import Optional
from ..Infrastructure.bidding_zones import BIDDING_ZONES

class LocationService:
    """Service to map GPS coordinates or Country Codes to ENTSO-E Bidding Zones"""

    # Approximate bounding boxes for European countries
    # format: [min_lat, max_lat, min_lng, max_lng]
    COUNTRY_BOUNDS = {
        "IE": [51.4, 55.4, -10.5, -6.0],
        "ES": [36.0, 43.8, -9.3, 3.3],
        "FR": [42.3, 51.1, -4.8, 8.2],
        "DE": [47.3, 55.1, 5.9, 15.0],
        "IT": [36.6, 47.1, 6.6, 18.5],
        "BE": [49.5, 51.5, 2.5, 6.4],
        "NL": [50.7, 53.6, 3.3, 7.2],
        "AT": [46.4, 49.0, 9.5, 17.1],
        "CH": [45.8, 47.8, 5.9, 10.5],
        "PT": [36.9, 42.2, -9.5, -6.2],
        "DK": [54.5, 57.8, 8.0, 15.2],
        "SE": [55.3, 69.1, 11.1, 24.1],
        "NO": [57.9, 71.2, 4.6, 31.1],
        "FI": [59.8, 70.1, 20.6, 31.6],
        "PL": [49.0, 54.9, 14.1, 24.1],
        "GB": [49.9, 58.7, -8.1, 1.8], # UK
    }

    @classmethod
    def get_bidding_zone_from_coords(cls, lat: float, lng: float, country_hint: Optional[str] = None) -> Optional[str]:
        """
        Attempts to find the bidding zone for a given lat/lng or country code.
        Returns None if not in a supported European region.
        """
        # 1. Try by country hint (most reliable if from geocoder)
        if country_hint:
            # Map country codes to ENTSO-E zones
            hint_map = {
                "GB": "10YGB----------A",
                "IE": "10IEA-TRAN------M",
                "FR": "10YFR-RTE------C",
                "DE": "10YDE-RWENET---I",
                "ES": "10YES-REE------0",
                "IT": "10YIT-NORTH---N",
                "BE": "10YBE----------2",
                "NL": "10YNL----------L",
                "PT": "10YPT-REN------W",
                "DK": "10YDK-1-------W",
                "NO": "10YNO-1-------2",
                "SE": "10YSE-3-------M",
                "FI": "10YFI-1--------U",
                "AT": "10YAT-APG------L",
                "CH": "10YCH-SWISSGRIDZ",
                "PL": "10YPL-AREA-----S",
                "CZ": "10YCZ-CEPS-----N",
                "HU": "10YHU-MAVIR----U",
                "RO": "10YRO-TEL------P",
                "GR": "10YGR-HTSO-----Y",
            }
            if country_hint in hint_map:
                return hint_map[country_hint]

        # 2. Try by bounding box
        for country, bounds in cls.COUNTRY_BOUNDS.items():
            if bounds[0] <= lat <= bounds[1] and bounds[2] <= lng <= bounds[3]:
                if country == "DK":
                    return BIDDING_ZONES.get("DK_1") if lng < 10 else BIDDING_ZONES.get("DK_2")
                if country == "NO":
                    if lat > 65:
                        return BIDDING_ZONES.get("NO_4")
                    if lng < 7:
                        return BIDDING_ZONES.get("NO_2")
                    return BIDDING_ZONES.get("NO_1")
                if country == "SE":
                    if lat > 64:
                        return BIDDING_ZONES.get("SE_1")
                    if lat > 60:
                        return BIDDING_ZONES.get("SE_2")
                    return BIDDING_ZONES.get("SE_3")
                
                # Check mapping for country code
                zone = BIDDING_ZONES.get(country)
                if zone:
                    return zone
        
        return None
