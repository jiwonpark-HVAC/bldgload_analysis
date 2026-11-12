"""The example buildings: the buildings of the Berkeley Decarb Tool dataset, which ships with the package.

Three files kept inside the package under bldgload_analysis/data:
  all_buildings_data_public.parquet   building, timestamp, heating_W, cooling_W, t_out_C, rh_pct, AER and LRMER factors
  metadata.csv                 one row per building
  load_summary.csv             the 43 metrics per building, the reference for dataset_position
An optional emission_factors_month_hour.csv (gea, month, hour, factors) fills buildings whose parquet rows have none.
Operating hours of an example building are the hours with a positive load.
use_examples(folder) points at another copy of the files.
"""
import json
from pathlib import Path

import numpy as np
import pandas as pd

Cache_dir = Path.home() / ".bldgload_analysis"
Pointer = Cache_dir / "examples.json"
Bundled = Path(__file__).parent / "data"
Data_files = ("all_buildings_data_public.parquet", "all_buildings_data_public.csv")
Table_files = ("metadata.csv", "load_summary.csv")
# column names in the dataset files and the names the package uses
Column_names = {"t_out_C": "oat_C", "rh_pct": "rh_out_pct", "oper_hw": "oper_hhw", "hw_sup_C": "hhw_sup_C", "hw_ret_C": "hhw_ret_C",
             "hw_flow_Lps": "hhw_flow_Lps", "hw_temp_inversion": "hhw_temp_inversion", "hw_temp_valid": "hhw_temp_valid"}
Meta_columns = {"Building Type": "building_type", "City": "city", "Climate": "climate", "Construction Year": "construction_year",
                "Floor Area (m2)": "floor_area_m2", "Model Source": "model_source", "State": "state", "GEA": "grid_region", "Grid Region": "grid_region"}
_cache = {}


def _registered():
    """The folder set with use_examples, or None. A folder that is no longer there is ignored."""
    if not Pointer.exists():
        return None
    try:
        folder = Path(json.loads(Pointer.read_text())["folder"])
    except (ValueError, KeyError):
        return None
    return folder if folder.is_dir() else None


def use_examples(folder=None):
    """Register a folder that holds another copy of the dataset files. It is remembered for later sessions.

    use_examples(None) forgets it and goes back to the copy that ships with the package.
    """
    _cache.clear()
    if folder is None:
        Pointer.unlink(missing_ok=True)
        return Bundled
    folder = Path(folder).expanduser().resolve()
    if not any((folder / f).exists() for f in Data_files):
        raise FileNotFoundError(f"{folder} has no all_buildings_data_public.parquet (or .csv)")
    Cache_dir.mkdir(parents=True, exist_ok=True)
    Pointer.write_text(json.dumps({"folder": str(folder)}))
    return folder


def examples_folder():
    """Where the dataset files are: a folder registered with use_examples, else the copy inside the package."""
    for folder in (_registered(), Bundled):
        if folder is not None and any((folder / f).exists() for f in Data_files):
            return folder
    raise FileNotFoundError(f"no all_buildings_data_public.parquet in {Bundled}. Install the package with its data folder, "
                            "or point at a copy of the dataset with use_examples(folder)")


def _read_table(name):
    """metadata.csv and load_summary.csv, looked for in the same order as the hourly data."""
    for folder in (_registered(), Bundled):
        if folder is not None and (folder / name).exists():
            return pd.read_csv(folder / name, low_memory=False)
    raise FileNotFoundError(f"{name} not found in {Bundled}")


def _key(x):
    """Text without spaces and in lower case, so 'San Francisco' and 'SanFrancisco' compare equal."""
    return "".join(str(x).split()).lower()


def example_buildings(building_type=None, climate=None, city=None, source=None) -> pd.DataFrame:
    """The example buildings, the dataset that ships with the package, one row each. Without arguments, all of them.

    building_type   keep the types that contain this text, so "office" finds OfficeLarge and Lab/Office
    climate         ASHRAE climate zone, e.g. "3C"
    city            city name, with or without spaces
    source          "measured" or "simulated", to keep only those

    Columns: building (the id for Building.from_example), source, model_source, climate, construction_year,
    building_type, city, floor_area_m2, grid_region.
    """
    if "meta" not in _cache:
        m = _read_table("metadata.csv").rename(columns=Meta_columns)
        m["building"] = m["building"].astype(str)
        _cache["meta"] = m
    if source is not None and _key(source) not in ("measured", "simulated"):
        raise ValueError("source must be 'measured' or 'simulated'")
    m = _cache["meta"]
    keep = pd.Series(True, index=m.index)
    if building_type is not None:
        want = _key(building_type)
        keep &= m["building_type"].map(lambda t: want in _key(t) or _key(t) in want)
    for column, value in (("climate", climate), ("city", city), ("source", source)):
        if value is not None:
            keep &= m[column].map(_key) == _key(value)
    return m[keep].reset_index(drop=True)


def emission_factors(gea) -> pd.DataFrame:
    """Month-hour emission factors of one grid region from the optional table, columns month, hour, <metric>_kgCO2_kWh."""
    if "ef" not in _cache:
        try:
            _cache["ef"] = _read_table("emission_factors_month_hour.csv")
        except FileNotFoundError:
            _cache["ef"] = None
    t = _cache["ef"]
    if t is None or gea is None:
        return None
    t = t[t["gea"].astype(str) == str(gea)]
    cols = [c for c in t.columns if c.endswith("_kgCO2_kWh")]
    return t[["month", "hour"] + cols] if len(t) and cols else None


def reference() -> pd.DataFrame:
    """load_summary.csv of the example buildings, the reference distribution for dataset_position."""
    if "ref" not in _cache:
        _cache["ref"] = _read_table("load_summary.csv")
    return _cache["ref"]


def hourly(building_id) -> pd.DataFrame:
    """Hourly table of one example building, in the package column names."""
    bid = str(building_id)
    folder = examples_folder()
    f = next((folder / n for n in Data_files if (folder / n).exists()), None)
    if f is None:
        raise FileNotFoundError(f"no all_buildings_data_public.parquet in {folder}")
    if f.suffix == ".parquet":
        import pyarrow.parquet as pq
        key = pq.read_schema(f).field("building").type
        value = int(bid) if str(key).startswith(("int", "uint")) else bid
        sub = pd.read_parquet(f, filters=[("building", "==", value)])
    else:
        if "data" not in _cache:
            _cache["data"] = pd.read_csv(f, low_memory=False)
        d = _cache["data"]
        sub = d[d["building"].astype(str) == bid]
    if sub.empty:
        raise KeyError(f"building {bid} is not one of the example buildings")
    sub = sub.rename(columns=Column_names)
    sub["timestamp"] = pd.to_datetime(sub["timestamp"])
    if sub["timestamp"].dt.tz is not None:        # keep the local standard clock time the file holds
        sub["timestamp"] = sub["timestamp"].dt.tz_localize(None)
    return sub.sort_values("timestamp").reset_index(drop=True)


def heat_recovery_reference(cop) -> pd.DataFrame:
    """The three heat recovery metrics of every example building for another COP, from the hourly loads.

    Same definitions as metrics.metrics. Returns building, loop, variable, value, the layout of load_summary.csv.
    load_summary.csv itself is for a COP of 3.
    """
    from .metrics import clean_cop, condenser_factor
    key = ("heat_recovery", clean_cop(cop))
    if key not in _cache:
        folder = examples_folder()
        f = next((folder / n for n in Data_files if (folder / n).exists()), None)
        cols = ["building", "heating_W", "cooling_W"]
        if f.suffix == ".parquet":
            d = pd.read_parquet(f, columns=cols)
        else:
            if "data" not in _cache:
                _cache["data"] = pd.read_csv(f, low_memory=False)
            d = _cache["data"][cols]
        d = d[np.isfinite(d["heating_W"]) & np.isfinite(d["cooling_W"])]
        cond = d["cooling_W"] * condenser_factor(cop)
        t = pd.DataFrame({"building": d["building"].astype(str), "qh": d["heating_W"], "cond": cond,
                          "rec": np.minimum(d["heating_W"], cond), "left": (d["heating_W"] - cond).clip(lower=0)})
        g = t.groupby("building")
        total, peak = g[["qh", "cond", "rec"]].sum(), g[["qh", "left"]].max()
        out = pd.DataFrame({
            "heat_recovery_heating_fraction": (total["rec"] / total["qh"] * 100).where(total["qh"] > 0),
            "heat_recovery_heat_rejection": ((1 - total["rec"] / total["cond"]) * 100).where(total["cond"] > 0),
            "heat_recovery_heating_peak_reduction": ((peak["qh"] - peak["left"]) / peak["qh"] * 100).where(peak["qh"] > 0)})
        out = out.round(4).rename_axis("building").reset_index().melt("building", var_name="variable", value_name="value")
        out.insert(1, "loop", "both")
        _cache[key] = out
    return _cache[key]


def building(building_id):
    """One of the example buildings as a Building, ready for metrics(), report() and plot()."""
    from .building import Building, Hourly_cols
    bid = str(building_id)
    m = example_buildings()
    row = m[m["building"] == bid]
    if row.empty:
        raise KeyError(f"building {bid} is not one of the example buildings")
    row = row.iloc[0]
    h = hourly(bid)
    for c in Hourly_cols:
        if c not in h:
            h[c] = np.nan
    h = h[Hourly_cols + [c for c in h.columns if c.endswith("_kgCO2_kWh")]]
    gea = row.get("grid_region")            # the Grid Region column of metadata.csv, a Cambium GEA region
    if not isinstance(gea, str) or not gea:
        gea = None
    if not any(c.endswith("_kgCO2_kWh") for c in h.columns):   # factors not in the parquet: join the month-hour table
        ef = emission_factors(gea)
        if ef is not None:
            h["month"], h["hour"] = h["timestamp"].dt.month, h["timestamp"].dt.hour
            h = h.merge(ef, on=["month", "hour"], how="left").drop(columns=["month", "hour"])
    area = float(pd.to_numeric(row.get("floor_area_m2"), errors="coerce"))
    meta = {"name": f"Building_{bid}", "example_id": bid, "units": "SI", "floor_area_m2": area, "floor_area": area, "area_unit": "m2",
            "source": str(row.get("source", "measured")), "building_type": row.get("building_type"), "city": row.get("city"),
            "climate": row.get("climate"), "construction_year": row.get("construction_year"),
            "model_source": row.get("model_source"), "grid_region": gea, "year_start": str(h["timestamp"].min())}
    meta = {k: v for k, v in meta.items() if v is not None and not (isinstance(v, float) and np.isnan(v))}
    return Building(h, meta)
