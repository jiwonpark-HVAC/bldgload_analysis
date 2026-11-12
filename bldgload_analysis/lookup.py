"""Lookups by location: coordinates, hourly weather (Open-Meteo), Cambium grid region and emission factors (NLR Cambium)."""
import json
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

Geocode_url = "https://geocoding-api.open-meteo.com/v1/search"
Archive_url = "https://archive-api.open-meteo.com/v1/archive"
Cache_dir = Path.home() / ".bldgload_analysis"


def _get_json(url, params):
    with urllib.request.urlopen(url + "?" + urllib.parse.urlencode(params), timeout=60) as r:
        return json.loads(r.read().decode())


# ------------------------------------------------------------------ location
def get_location(city, country=None):
    """Look a city up and return dict(latitude, longitude, timezone, admin1, country). admin1 is the state.

    Building.from_csv calls this with its city. Call it yourself to see which place the name was matched to.
    """
    q = city if country is None else f"{city}, {country}"
    res = _get_json(Geocode_url, {"name": q, "count": 5, "language": "en", "format": "json"}).get("results") or []
    if country:
        res = [r for r in res if r.get("country_code", "").lower() == country.lower() or r.get("country", "").lower() == country.lower()] or res
    if not res:
        raise ValueError(f"could not geocode {city!r}")
    r = res[0]
    return {"latitude": r["latitude"], "longitude": r["longitude"], "timezone": r.get("timezone"),
            "admin1": r.get("admin1"), "country": r.get("country_code")}


def standard_offset_hours(timezone):
    """Standard time offset from UTC in hours, taken in January so daylight saving is not included."""
    jan = datetime(2020, 1, 15, tzinfo=ZoneInfo(timezone))
    return jan.utcoffset().total_seconds() / 3600


# ------------------------------------------------------------------ weather
def get_weather(place, start, end, longitude=None, timezone="UTC"):
    """Hourly outdoor temperature and relative humidity for start..end in local standard time.

    place: a city name, or a latitude with longitude and timezone given separately.
    """
    if isinstance(place, str):
        loc = get_location(place)
        latitude, longitude, timezone = loc["latitude"], loc["longitude"], loc["timezone"] or "UTC"
    else:
        latitude = place
    start, end = pd.Timestamp(start), pd.Timestamp(end)
    offset = standard_offset_hours(timezone)
    params = {"latitude": latitude, "longitude": longitude,
              "start_date": (start - pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
              "end_date": (end + pd.Timedelta(days=1)).strftime("%Y-%m-%d"),
              "hourly": "temperature_2m,relative_humidity_2m", "timezone": "GMT"}
    h = _get_json(Archive_url, params)["hourly"]
    w = pd.DataFrame({"timestamp": pd.to_datetime(h["time"]) + pd.Timedelta(hours=offset),
                      "oat_C": h["temperature_2m"], "rh_pct": h["relative_humidity_2m"]})
    return w[(w["timestamp"] >= start) & (w["timestamp"] <= end)].reset_index(drop=True)


# ------------------------------------------------------------------ grid region
# The Cambium GEA region is found from the city and its state. A city in Gea_cities gets that region.
# Any other city gets the region most of its state is in, which is only approximate where a state is
# split between regions. grid_region=<name> in Building.from_csv sets the region by hand.
# Both tables were checked against NLR's ZIP code to GEA table (GEA Mappings and Shapefiles on the
# Scenario Viewer, Cambium 2023 GEA regions).
State_to_gea = {
    "California": "CAISO", "Washington": "NorthernGrid_West", "Oregon": "NorthernGrid_West",
    "Idaho": "NorthernGrid_East", "Montana": "NorthernGrid_East", "Utah": "NorthernGrid_South", "Nevada": "NorthernGrid_South",
    "Wyoming": "NorthernGrid_East", "Colorado": "WestConnect_North",
    "Arizona": "WestConnect_South", "New Mexico": "WestConnect_South", "Texas": "ERCOT",
    "North Dakota": "MISO_North", "South Dakota": "SPP_North", "Nebraska": "SPP_North", "Kansas": "SPP_South",
    "Oklahoma": "SPP_South", "Minnesota": "MISO_North", "Wisconsin": "MISO_North", "Iowa": "MISO_North",
    "Illinois": "MISO_Central", "Indiana": "MISO_Central", "Michigan": "MISO_Central", "Missouri": "MISO_Central",
    "Arkansas": "MISO_South", "Louisiana": "MISO_South", "Mississippi": "MISO_South",
    "Ohio": "PJM_East", "Kentucky": "PJM_East", "West Virginia": "PJM_East",
    "Pennsylvania": "PJM_East", "New Jersey": "PJM_East", "Maryland": "PJM_East", "Delaware": "PJM_East",
    "District of Columbia": "PJM_East", "Virginia": "PJM_East", "New York": "NYISO",
    "Connecticut": "ISONE", "Massachusetts": "ISONE", "Maine": "ISONE", "New Hampshire": "ISONE",
    "Rhode Island": "ISONE", "Vermont": "ISONE",
    "Tennessee": "SERTP", "Alabama": "SERTP", "Georgia": "SERTP", "North Carolina": "SERTP", "South Carolina": "SERTP",
    "Florida": "FRCC",
}


# Major cities by Cambium GEA region and state, names written without spaces
Gea_cities = {
    "CAISO": {"California": ["LosAngeles", "SanDiego", "SanJose", "SanFrancisco", "Sacramento", "Fresno", "Oakland", "LongBeach"]},
    "NorthernGrid_West": {"Washington": ["Seattle", "Spokane", "Tacoma"], "Oregon": ["Portland"]},
    "NorthernGrid_East": {"Idaho": ["Boise"], "Montana": ["Billings", "GreatFalls"]},
    "NorthernGrid_South": {"Utah": ["SaltLakeCity"], "Nevada": ["LasVegas", "Reno"]},
    "WestConnect_North": {"Colorado": ["Denver", "ColoradoSprings"], "Wyoming": ["Cheyenne", "Casper"], "South Dakota": ["RapidCity"]},
    "WestConnect_South": {"Arizona": ["Phoenix", "Tucson"], "New Mexico": ["Albuquerque"], "Texas": ["ElPaso"]},
    "ERCOT": {"Texas": ["Houston", "Dallas", "SanAntonio", "Austin", "FortWorth"]},
    "SPP_North": {"Nebraska": ["Omaha", "Lincoln"], "South Dakota": ["SiouxFalls"], "North Dakota": ["Bismarck"]},
    "SPP_South": {"Oklahoma": ["OklahomaCity", "Tulsa"], "Kansas": ["Wichita", "Topeka"], "Missouri": ["KansasCity", "Springfield"],
                  "Texas": ["Amarillo", "Lubbock"]},
    "MISO_North": {"Minnesota": ["Minneapolis", "SaintPaul", "InternationalFalls"], "Wisconsin": ["Milwaukee", "Madison"],
                   "Iowa": ["DesMoines"], "North Dakota": ["Fargo"]},
    "MISO_Central": {"Michigan": ["Detroit", "GrandRapids"], "Indiana": ["Indianapolis"], "Missouri": ["SaintLouis"],
                     "Illinois": ["Springfield", "Peoria"]},
    "MISO_South": {"Louisiana": ["NewOrleans", "BatonRouge"], "Arkansas": ["LittleRock"], "Mississippi": ["Jackson"], "Texas": ["Beaumont"]},
    "PJM_West": {"Illinois": ["Chicago", "Rockford", "Aurora", "Naperville", "Joliet"]},
    "PJM_East": {"Pennsylvania": ["Philadelphia", "Pittsburgh"], "Maryland": ["Baltimore"], "District of Columbia": ["Washington"],
                 "New Jersey": ["Newark"], "Virginia": ["Richmond", "VirginiaBeach"], "Ohio": ["Columbus", "Cleveland", "Cincinnati"],
                 "Kentucky": ["Louisville", "Lexington"], "West Virginia": ["Charleston"]},
    "NYISO": {"New York": ["NewYork", "Buffalo", "Rochester", "Albany", "Syracuse"]},
    "ISONE": {"Massachusetts": ["Boston"], "Rhode Island": ["Providence"], "Connecticut": ["Hartford"], "Vermont": ["Burlington"],
              "New Hampshire": ["Manchester"]},
    "SERTP": {"Georgia": ["Atlanta"], "North Carolina": ["Charlotte", "Raleigh"], "Tennessee": ["Nashville", "Memphis"],
              "Alabama": ["Birmingham"], "Florida": ["Pensacola"], "Kentucky": ["Paducah"]},
    "FRCC": {"Florida": ["Miami", "Tampa", "Orlando", "Jacksonville", "Tallahassee"]},
}


def grid_region(city=None, state=None):
    """Cambium GEA region of a city: the city table first, then the state table. None when neither knows it.

    state is the full name, e.g. Illinois. Without a state the city table is used only when the name is in it once.
    """
    if isinstance(city, str):
        key = "".join(city.split())
        hits = {st: gea for gea, states in Gea_cities.items() for st, cities in states.items() if key in cities}
        if state in hits:
            return hits[state]
        if state is None and len(hits) == 1:
            return next(iter(hits.values()))
    return State_to_gea.get(state)


# ------------------------------------------------------------------ Cambium emission factors
def get_emission_factors(gea, year=2025, scenario="Mid-case", release=2024):
    """Month-hour AER and LRMER for one GEA region, kg CO2e per kWh, downloaded from the NLR Scenario Viewer.

    Columns: month, hour, AER_<year>_kgCO2_kWh, LRMER_<year>_kgCO2_kWh. Kept under ~/.bldgload_analysis after the first call.
    """
    from . import cambium
    ef = cambium.month_hour(gea, year, scenario, release)
    return ef.rename(columns={"aer": f"AER_{year}_kgCO2_kWh", "lrmer": f"LRMER_{year}_kgCO2_kWh"})
