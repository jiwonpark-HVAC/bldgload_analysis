"""One building: read, clean, summarise, report, plot."""
import json
import re
import warnings
from pathlib import Path

import numpy as np
import pandas as pd

from . import clean, lookup
from . import units as units_mod
from .metrics import COP, clean_cop, metrics

Input_aliases = {
    "heating": "hhw_load", "cooling": "chw_load", "heating_load": "hhw_load", "cooling_load": "chw_load",
    "hw_load": "hhw_load", "hw_sup": "hhw_sup", "hw_ret": "hhw_ret", "hw_flow": "hhw_flow",
    "datetime": "timestamp", "time": "timestamp", "t_out": "oat", "oat_temp": "oat", "rh": "rh_out", "rh_out_pct": "rh_out",
}
Base_quantity = {"hhw_load": "load", "chw_load": "load", "hhw_sup": "temp", "hhw_ret": "temp", "chw_sup": "temp", "chw_ret": "temp",
                 "hhw_flow": "flow", "chw_flow": "flow", "oat": "temp"}
Si_suffix = {"load": "W", "temp": "C", "flow": "Lps"}
Loop_input = {"hhw": ["hhw_load_W", "hhw_sup_C", "hhw_ret_C", "hhw_flow_Lps"],
              "chw": ["chw_load_W", "chw_sup_C", "chw_ret_C", "chw_flow_Lps"]}
Hourly_cols = ["timestamp", "heating_W", "cooling_W", "oat_C", "rh_out_pct", "oper_hhw", "oper_chw",
               "hhw_sup_C", "hhw_ret_C", "hhw_flow_Lps", "hhw_temp_valid",
               "chw_sup_C", "chw_ret_C", "chw_flow_Lps", "chw_temp_valid"]
Meta_keys = ["name", "floor_area_m2", "building_type", "city", "climate", "construction_year", "source",
             "design_h996", "design_h99", "design_c1", "design_c04"]


def read_input(path, unit_system="SI") -> pd.DataFrame:
    """Read the CSV and return it in SI with the package column names.

    A unit suffix on a column (hhw_load_Btuh, hhw_load_kW, hhw_sup_F, hhw_flow_gpm, oat_F) says what that column is in.
    Without a suffix the unit_system argument decides. Column names are read in any case.
    """
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    for c in list(df.columns):                   # kW and kBtuh columns become W and Btuh
        name, factor = units_mod.kilo_column(c)
        if factor != 1:
            df[name] = pd.to_numeric(df[c], errors="coerce") * factor
            df = df.drop(columns=c)
    rename = {}
    for c in df.columns:
        base, q, u = units_mod.split_column(c)
        base = Input_aliases.get(base.lower(), base.lower())
        if base in Base_quantity:
            q = Base_quantity[base]
            df[c] = units_mod.to_si(pd.to_numeric(df[c], errors="coerce"), q, u or unit_system)
            rename[c] = f"{base}_{Si_suffix[q]}"
        elif base == "rh_out":
            rename[c] = "rh_out_pct"
        else:
            rename[c] = base
    df = df.rename(columns=rename)
    if "timestamp" not in df:
        raise ValueError("input needs a timestamp column")
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    if getattr(df["timestamp"].dt, "tz", None) is not None:       # a UTC offset in the file: keep the clock time as written
        df["timestamp"] = df["timestamp"].dt.tz_localize(None)
    df = df[df["timestamp"].notna()].sort_values("timestamp")
    df = df.groupby("timestamp", as_index=False).mean(numeric_only=True)
    return df


def emission_name(column, year):
    """'AER' -> 'AER_2025_kgCO2_kWh'. A year already in the name is kept."""
    base = column.replace("_kgCO2_kWh", "")
    if not re.search(r"_\d{4}$", base):
        base = f"{base}_{year}"
    return f"{base}_kgCO2_kWh"


def read_emission_factors(source, year=2025) -> pd.DataFrame:
    """month, hour, and one column per metric, e.g. AER, LRMER in kg CO2e per kWh (kg per MWh is rescaled).

    source: csv path or DataFrame. Columns come back as <metric>_<year>_kgCO2_kWh.
    """
    ef = source.copy() if isinstance(source, pd.DataFrame) else pd.read_csv(source)
    ef.columns = [c.strip() for c in ef.columns]
    mcols = [c for c in ef.columns if c.lower() not in ("month", "hour")]
    ef = ef.rename(columns={c: emission_name(c, year) for c in mcols})
    mcols = [c for c in ef.columns if c.endswith("_kgCO2_kWh")]
    if ef[mcols].median().median() > 5:
        ef[mcols] = ef[mcols] / 1000
    if ef["hour"].min() == 1 and ef["hour"].max() == 24:
        ef["hour"] = ef["hour"] - 1
    return ef.groupby(["month", "hour"], as_index=False)[mcols].mean()


def building_name(name=None, parent="."):
    """Building_user_<name> when a name is given, otherwise Building_user_1, _2, ... counting the folders in parent."""
    if name:
        return f"Building_user_{name}"
    nums = [int(m.group(1)) for p in Path(parent).glob("Building_user_*")
            if (m := re.fullmatch(r"Building_user_(\d+)", p.name))]
    return f"Building_user_{max(nums, default=0) + 1}"


Design_keys = ("design_h996", "design_h99", "design_c1", "design_c04")


class Building:
    """One building: its cleaned hourly table, its metadata, and the metrics, report and figures made from them.

    Make one with Building.from_csv (your own data), Building.from_example (one of the example buildings) or
    Building.load (a folder written by save).

    hourly   DataFrame, one row per hour, always in SI: timestamp, heating_W, cooling_W, oat_C, rh_out_pct,
             oper_hhw, oper_chw, the loop temperatures and flows, and the emission factor columns
    meta     dict with the name, floor area, units, location and the other building information
    """

    def __init__(self, hourly: pd.DataFrame, meta: dict, metrics: pd.DataFrame | None = None):
        self.hourly = hourly
        self.meta = meta
        self._metrics = metrics

    def __repr__(self):
        area = self.meta.get("floor_area_m2")
        area = f"{area:,.0f} m2" if area is not None and np.isfinite(area) else "no floor area"
        return f"Building({self.meta.get('name', '')}, {self.meta.get('source', '')}, {len(self.hourly)} hours, {area})"

    # ---------------------------------------------------------------- build
    @classmethod
    def from_csv(cls, path, name=None, floor_area=np.nan, area_unit="m2", units="SI", building_type=None, city=None,
                 country="US", climate=None, construction_year=None, source="measured", emission_factors=None,
                 cambium_year=2025, latitude=None, longitude=None, timezone=None, grid_region=None,
                 weather=True, select_year=True, cop=COP, folder=".", **design):
        """Build one building from a CSV.

        name               reported as Building_user_<name>; None gives Building_user_1, _2, ...
        floor_area         gross floor area, in area_unit ("m2" or "ft2")
        units              "SI" (W, C, L/s) or "IP" (Btu/h, F, gpm) for the CSV columns without a unit suffix.
                           Metrics, report and figures come back in the same system
        building_type      e.g. Office, Hospital, Lab
        city, country      location, used to fetch weather and to pick the grid region
        climate            ASHRAE climate zone, e.g. 3C
        construction_year  year completed
        source             "measured" or "simulated"
        emission_factors   month-hour emission factor csv or DataFrame. None: downloaded from the NLR Scenario Viewer
                           (Cambium) for the location's grid region
        cambium_year       Cambium model year, also the year in the metric names, e.g. AER_2025_annual_avg
        latitude, longitude, timezone   instead of a city; timezone is an IANA name like America/Los_Angeles
        grid_region        Cambium GEA region, e.g. CAISO or PJM_West. None: found from the city, else from its state
        weather            when the input has no oat_C, download hourly temperature and humidity (Open-Meteo)
        select_year        choose the best 8760 hour window, False keeps the whole record. annual_load is then the
                           energy of the whole record, not of one year
        cop                COP of the heat recovery chiller in the heat recovery metrics, 3 as in the dataset.
                           0 leaves the compressor work out, so the condenser heat equals the cooling load
        design_h996, design_h99, design_c1, design_c04   ASHRAE design temperatures, optional
        """
        if source not in ("measured", "simulated"):
            raise ValueError("source must be 'measured' or 'simulated'")
        units = str(units).upper()
        if units not in ("SI", "IP"):
            raise ValueError("units must be 'SI' or 'IP'")
        unknown = sorted(set(design) - set(Design_keys))
        if unknown:
            raise TypeError(f"from_csv got unknown argument(s): {', '.join(unknown)}")
        raw = read_input(path, units)
        area_m2 = units_mod.area_to_m2(floor_area, area_unit) if np.isfinite(float(floor_area)) else np.nan
        meta = {"name": building_name(name, folder), "floor_area_m2": area_m2, "floor_area": float(floor_area), "area_unit": area_unit,
                "units": units, "building_type": building_type,
                "city": city, "climate": climate, "construction_year": construction_year, "source": source, **design}
        meta = {k: v for k, v in meta.items() if v is not None}
        meta["cop"] = clean_cop(cop)
        loc = cls._locate(city, country, latitude, longitude, timezone, meta)
        if weather and loc and ("oat_C" not in raw or raw["oat_C"].notna().sum() == 0):
            try:
                w = lookup.get_weather(loc["latitude"], raw["timestamp"].min(), raw["timestamp"].max(),
                                   longitude=loc["longitude"], timezone=loc.get("timezone") or "UTC")
                raw = raw.drop(columns=[c for c in ("oat_C", "rh_out_pct") if c in raw]).merge(w, on="timestamp", how="left")
                meta["weather_source"] = "Open-Meteo archive"
            except Exception as e:
                warnings.warn(f"weather download failed, oat_C left empty: {e}")
        if emission_factors is None and (loc or grid_region or city):
            gea = grid_region or lookup.grid_region(city, (loc or {}).get("admin1"))
            if gea is None:
                warnings.warn("no Cambium grid region found for this location, grid metrics left empty. Set grid_region=<GEA region>")
            else:
                meta["grid_region"] = gea
                try:
                    emission_factors = lookup.get_emission_factors(gea, cambium_year)
                except Exception as e:
                    warnings.warn(f"no emission factors: {e}")
        loops = {}
        for lp, cols in Loop_input.items():
            have = [c for c in cols if c in raw]
            if not have:
                continue
            sub = raw[["timestamp"] + have].rename(columns={cols[0]: "load_meas", cols[1]: "sup", cols[2]: "ret", cols[3]: "flow",
                                                             "timestamp": "datetime"})
            sub = sub[~sub.drop(columns="datetime").isna().all(axis=1)]
            loops[lp] = clean.clean_loop(sub, "heating" if lp == "hhw" else "cooling")
        if not loops:
            raise ValueError("input needs hhw_load or chw_load, or sup, ret and flow for a loop. "
                             f"Columns read: {', '.join(raw.columns)}")
        h = None
        for lp, d in loops.items():
            d = d.rename(columns={"load": f"{'heating' if lp == 'hhw' else 'cooling'}_W", "oper": f"oper_{lp}",
                                  "sup": f"{lp}_sup_C", "ret": f"{lp}_ret_C", "flow": f"{lp}_flow_Lps",
                                  "temp_valid": f"{lp}_temp_valid"})
            d = d[[c for c in Hourly_cols if c in d]]
            h = d if h is None else h.merge(d, on="timestamp", how="outer")
        for c in ("oat_C", "rh_out_pct"):
            if c in raw:
                w = raw[["timestamp", c]].copy()
                w["timestamp"] = w["timestamp"].dt.floor("h")
                h = h.merge(w.groupby("timestamp", as_index=False)[c].mean(), on="timestamp", how="left")
        for c in Hourly_cols:
            if c not in h:
                h[c] = np.nan
        h = h[Hourly_cols].sort_values("timestamp").reset_index(drop=True)
        days = (h["timestamp"].max() - h["timestamp"].min()).days
        if days < 365:
            meta["short_record_days"] = int(days)
            warnings.warn(f"the record covers {days} days, less than one year. Annual values are scaled up from the "
                          "hours available and can be far from the real annual values")
        if select_year:
            win = clean.best_year(h)
            start = win[0] if win else h["timestamp"].min().ceil("D")
            n = 8784 if win and (win[1] - win[0]) > pd.Timedelta(hours=8760) else 8760
            frame = pd.DataFrame({"timestamp": pd.date_range(start, periods=n, freq="h")})
            h = frame.merge(h, on="timestamp", how="left")
            meta["year_start"] = str(start)
        if emission_factors is not None:
            ef = read_emission_factors(emission_factors, cambium_year)
            h["month"], h["hour"] = h["timestamp"].dt.month, h["timestamp"].dt.hour
            h = h.merge(ef, on=["month", "hour"], how="left").drop(columns=["month", "hour"])
        return cls(h, meta)

    @staticmethod
    def _locate(city, country, latitude, longitude, timezone, meta):
        if latitude is not None and longitude is not None:
            loc = {"latitude": float(latitude), "longitude": float(longitude), "timezone": timezone, "admin1": None}
            if timezone is None:
                warnings.warn("no timezone given, weather timestamps are taken as UTC")
        elif city:
            try:
                loc = lookup.get_location(city, country)
            except Exception as e:
                warnings.warn(f"geocoding failed: {e}")
                return None
        else:
            return None
        meta.update({k: loc[k] for k in ("latitude", "longitude", "timezone") if loc.get(k) is not None})
        if loc.get("admin1"):
            meta["state"] = loc["admin1"]
        return loc

    @classmethod
    def from_example(cls, building_id, cop=COP):
        """One of the example buildings, see example_buildings() for the ids. cop as in from_csv."""
        from . import examples
        b = examples.building(building_id)
        b.cop = cop
        return b

    @classmethod
    def load(cls, out_dir):
        """A building back from a folder written by save(). The metrics are computed again from hourly.csv."""
        out = Path(out_dir)
        meta = json.loads((out / "meta.json").read_text())
        h = pd.read_csv(out / "hourly.csv", parse_dates=["timestamp"])
        ren = {}
        for c in h.columns:                       # an IP hourly.csv comes back to SI
            base, q, u = units_mod.split_column(c)
            if q and u == "IP":
                h[c] = units_mod.to_si(h[c], q, u)
                ren[c] = f"{base}_{Si_suffix[q]}"
        h = h.rename(columns=ren)
        return cls(h, meta)          # metrics are recomputed from hourly, metrics.csv on disk may be in IP

    # ---------------------------------------------------------------- results
    @property
    def _emission_columns(self):
        return [c for c in self.hourly.columns if c.endswith("_kgCO2_kWh")]

    @property
    def units(self):
        """Units(SI or IP) the building reports in, set from the input."""
        return units_mod.Units(self.meta.get("units", "SI"))

    @property
    def cop(self):
        """COP of the heat recovery chiller in the heat recovery metrics. 0 means the compressor work is left out.

        It can be changed at any time, building.cop = 4, and the metrics, figures and report follow.
        """
        return self.meta.get("cop", COP)

    @cop.setter
    def cop(self, value):
        self.meta["cop"] = clean_cop(value)
        self._metrics = None

    def metrics(self, units=None) -> pd.DataFrame:
        """The 43 metrics. units: "SI" or "IP", default the input's system. Values inside stay SI."""
        if self._metrics is None:
            self._metrics = metrics(self.hourly, self.meta.get("floor_area_m2", np.nan), self._emission_columns, self.cop)
        system = units or self.meta.get("units", "SI")
        return units_mod.metrics_to_ip(self._metrics) if system == "IP" else units_mod.metrics_units_si(self._metrics)

    def metric(self, name, loop=None, units=None):
        """One metric value. loop ("hhw" or "chw") is needed for the metrics that exist for both loops."""
        s = self.metrics(units)
        m = s["variable"] == name
        if not m.any():
            raise KeyError(f"no metric named {name!r}, see building.metrics()['variable']")
        if loop:
            m &= s["loop"] == loop
        v = s.loc[m, "value"]
        if len(v) > 1:
            raise ValueError(f"{name!r} exists for {', '.join(s.loc[m, 'loop'])}, give loop=")
        return float(v.iloc[0]) if len(v) else np.nan

    def example_buildings(self, same=("building_type", "climate"), source=None) -> pd.DataFrame:
        """The example buildings that have the same building type and climate zone as this one.

        same     what has to be the same as in this building: any of "building_type", "climate" and "city".
                 same=["climate"] keeps every example building in the same climate zone
        source   "measured" or "simulated" to keep only those, None keeps both

        The rows are those of example_buildings(). Load one with Building.from_example(id).
        """
        from . import examples
        names = {"building_type", "climate", "city"}
        same = [same] if isinstance(same, str) else list(same)
        if set(same) - names:
            raise ValueError(f"same takes any of {', '.join(sorted(names))}")
        missing = [k for k in same if self.meta.get(k) is None]
        if missing:
            raise ValueError(f"this building has no {', '.join(missing)}. Give it in from_csv, or leave it out of same=")
        found = examples.example_buildings(source=source, **{k: self.meta[k] for k in same})
        if found.empty:
            asked = [f"{k} ({self.meta[k]})" for k in same] + ([f"source ({source})"] if source else [])
            warnings.warn("no example building has the same " + " and ".join(asked) + ". Try fewer conditions, for example same=['climate']")
        return found

    def save(self, out_dir=None):
        """Write hourly.csv, metrics.csv and meta.json to a folder, by default one named after the building. Returns the folder."""
        out = Path(out_dir or self.meta["name"])
        out.mkdir(parents=True, exist_ok=True)
        self.hourly_in_units().to_csv(out / "hourly.csv", index=False)
        self.metrics().to_csv(out / "metrics.csv", index=False)
        meta = {k: v for k, v in self.meta.items() if not (isinstance(v, float) and np.isnan(v))}     # NaN is not valid JSON
        (out / "meta.json").write_text(json.dumps(meta, indent=2, default=str))
        return out

    def hourly_in_units(self):
        """Hourly table in the building's unit system, column suffixes say the unit."""
        u = self.units
        if not u.ip:
            return self.hourly
        h = self.hourly.copy()
        ren = {}
        for c in h.columns:
            base, q, _ = units_mod.split_column(c)
            if q == "load":
                h[c] = u.load(h[c]); ren[c] = f"{base}_Btuh"
            elif q == "temp":
                h[c] = u.temp(h[c]); ren[c] = f"{base}_F"
            elif q == "flow":
                h[c] = u.flow(h[c]); ren[c] = f"{base}_gpm"
        return h.rename(columns=ren)

    def report(self, path, reference=None, page=(11, 8.5)):
        """Draw the one page report to a file, pdf or png by the file name.

        reference   load_summary.csv to compare with in the "position in the dataset" panel, None uses the example buildings
        page        (width, height) in inches. US letter landscape by default, (16.54, 11.69) is A3
        """
        from .report import build_report
        return build_report(self, path, reference, page)

    def plot(self, name, ax=None, **kw):
        """Draw one figure and return its matplotlib Axes. building.figures lists the names.

        ax   an Axes of your own to draw on. Without it a new 4.2 x 3.2 inch figure is made
        Save with ax.figure.savefig("name.png", dpi=200), and close figures you no longer need with plt.close.
        """
        from .figures import _figures
        if name not in _figures:
            raise KeyError(f"unknown figure {name!r}, choose from {', '.join(_figures)}")
        return _figures[name](self, ax=ax, **kw)

    @property
    def figures(self):
        """Names accepted by plot()."""
        from .figures import _figures
        return list(_figures)
