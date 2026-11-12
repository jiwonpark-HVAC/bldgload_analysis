"""Unit handling. Everything inside the package is SI; input and output can be IP."""
import re
import numpy as np

W_per_btuh = 0.29307107
Ft2_per_m2 = 10.76391
Gpm_per_lps = 15.850323

# column suffixes the reader understands, and the unit each one means
Suffix_units = {"W": ("load", "SI"), "Btuh": ("load", "IP"), "C": ("temp", "SI"), "F": ("temp", "IP"),
                "Lps": ("flow", "SI"), "gpm": ("flow", "IP")}
Kilo_suffix = {"kW": "W", "kBtuh": "Btuh"}      # read as 1000 times the unit
Suffix_spelling = {k.lower(): k for k in [*Suffix_units, *Kilo_suffix]}


def _suffix(name):
    """'hhw_load_kw' -> ('hhw_load', 'kW'), the suffix in its usual spelling, or (name, None)."""
    m = re.fullmatch(r"(.+?)_([A-Za-z]+)", name)
    suffix = Suffix_spelling.get(m.group(2).lower()) if m else None
    return (m.group(1), suffix) if suffix else (name, None)


def split_column(name):
    """'hhw_sup_F' -> ('hhw_sup', 'temp', 'IP'); 'hhw_sup' -> ('hhw_sup', None, None). The suffix is read in any case."""
    base, suffix = _suffix(name)
    if suffix in Suffix_units:
        return base, *Suffix_units[suffix]
    return name, None, None


def kilo_column(name):
    """'hhw_load_kW' -> ('hhw_load_W', 1000). Any other name comes back as it is, with factor 1."""
    base, suffix = _suffix(name)
    if suffix in Kilo_suffix:
        return f"{base}_{Kilo_suffix[suffix]}", 1000
    return name, 1


def to_si(x, quantity, unit):
    if unit == "SI":
        return x
    if quantity == "load":
        return x * W_per_btuh
    if quantity == "temp":
        return (x - 32) * 5 / 9
    if quantity == "flow":
        return x / Gpm_per_lps
    raise ValueError(quantity)


def area_to_m2(area, unit):
    if unit in ("m2", "m^2", "sqm"):
        return float(area)
    if unit in ("ft2", "ft^2", "sqft"):
        return float(area) / Ft2_per_m2
    raise ValueError("area_unit must be m2 or ft2")


class Units:
    """Converts SI values for display when the building is reported in IP."""

    def __init__(self, system="SI"):
        if system not in ("SI", "IP"):
            raise ValueError("units must be SI or IP")
        self.system = system
        self.ip = system == "IP"

    def temp(self, c):            return c * 9 / 5 + 32 if self.ip else c
    def dtemp(self, k):           return k * 9 / 5 if self.ip else k
    def area(self, m2):           return m2 * Ft2_per_m2 if self.ip else m2
    def load(self, w):            return w / W_per_btuh if self.ip else w
    def kload(self, w):           return w / W_per_btuh / 1000 if self.ip else w / 1000
    def load_density(self, wm2):  return wm2 / W_per_btuh / Ft2_per_m2 if self.ip else wm2
    def energy_density(self, kwhm2): return kwhm2 / W_per_btuh / Ft2_per_m2 if self.ip else kwhm2
    def flow(self, lps):          return lps * Gpm_per_lps if self.ip else lps

    @property
    def temp_unit(self):           return "F" if self.ip else "C"
    @property
    def dtemp_unit(self):          return "F" if self.ip else "K"
    @property
    def area_unit(self):           return "ft2" if self.ip else "m2"
    @property
    def kload_unit(self):          return "kBtu/h" if self.ip else "kW"
    @property
    def load_density_unit(self):   return "Btu/h ft2" if self.ip else "W/m2"
    @property
    def energy_density_unit(self): return "kBtu/ft2" if self.ip else "kWh/m2"
    @property
    def flow_unit(self):           return "gpm" if self.ip else "L/s"


# unit of each metric in SI and IP, blank when dimensionless or percent
Metric_units = {
    "annual_load": ("Wh", "Btu"), "max_load": ("W", "Btu/h"), "max_load_per_area": ("W/m2", "Btu/h ft2"),
    "min_load_gt0": ("W", "Btu/h"), "mean_load_gt0": ("W", "Btu/h"), "median_load_gt0": ("W", "Btu/h"),
    "q25_load": ("W", "Btu/h"), "q75_load": ("W", "Btu/h"),
    "heating_hour_ratio": ("%", "%"), "cooling_hour_ratio": ("%", "%"), "valid_hours": ("h", "h"), "data_coverage": ("%", "%"),
    "heating_capacity_marginal_gain_5pct": ("% of peak", "% of peak"), "cooling_capacity_marginal_gain_5pct": ("% of peak", "% of peak"),
    "winter_heating_average_profile_pmr": ("", ""), "summer_cooling_average_profile_pmr": ("", ""),
    "annual_heating_and_cooling_ratio": ("", ""), "ratio_of_peak_heating_and_cooling": ("", ""),
    "simultaneous_heating_and_cooling_hour_ratio": ("%", "%"),
    "heat_recovery_heating_fraction": ("%", "%"), "heat_recovery_heat_rejection": ("%", "%"),
    "heat_recovery_heating_peak_reduction": ("%", "%"), "hrc_capacity_marginal_gain_5pct": ("% of peak cooling", "% of peak cooling"),
    "p00_4_temp": ("C", "F"), "p01_temp": ("C", "F"), "p99_temp": ("C", "F"), "p99_6_temp": ("C", "F"),
}


def _metric_unit(variable, ip):
    """Unit of each metric. The grid metrics carry the year in their name, so they are found by pattern."""
    unit = variable.map(lambda k: Metric_units.get(k, ("", ""))[1 if ip else 0])
    return np.where(variable.str.startswith("alignment_factor"), "", np.where(variable.str.endswith("_annual_avg"), "kg CO2e/kWh", unit))


def metrics_to_ip(df):
    """Convert a metrics table from SI to IP and add a unit column."""
    out = df.copy()
    v = out["variable"]
    unit = _metric_unit(v, ip=True)
    x = out["value"].astype(float)
    x = np.where(v.isin(["annual_load", "max_load", "min_load_gt0", "mean_load_gt0", "median_load_gt0", "q25_load", "q75_load"]), x / W_per_btuh, x)
    x = np.where(v == "max_load_per_area", out["value"] / W_per_btuh / Ft2_per_m2, x)
    x = np.where(v.str.endswith("_temp"), out["value"] * 9 / 5 + 32, x)
    out["value"] = np.round(x, 4)
    out["unit"] = unit
    return out


def metrics_units_si(df):
    """Add the unit column to a metrics table in SI."""
    out = df.copy()
    out["unit"] = _metric_unit(out["variable"], ip=False)
    return out
