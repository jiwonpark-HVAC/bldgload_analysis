"""The 43 core metrics, same definitions as the Berkeley Decarb Tool dataset.

Every metric is one row with group, loop, variable and value. Values are in SI.
The loop is hhw (heating hot water), chw (chilled water), both, temperature or grid.

Load Magnitude & Distribution, one set for hhw and one for chw
  annual_load          energy over the year in Wh. Scaled up to all hours when some hours are missing
  max_load             largest hourly load in W
  max_load_per_area    max_load divided by the floor area, W/m2
  min_load_gt0         smallest hourly load above zero, W
  mean_load_gt0        mean of the hourly loads above zero, W
  median_load_gt0      median of the hourly loads above zero, W
  q25_load, q75_load   25th and 75th percentile of all hourly loads, W
  heating_hour_ratio   share of the hours with a known state in which the plant runs, %. cooling_hour_ratio for chw
  valid_hours          hours with a load value
  data_coverage        valid_hours as a share of all hours, %
  heating_capacity_marginal_gain_5pct   capacity, in % of the peak, at which one more 5% step adds less than 5%
                       to the energy served. cooling_capacity_marginal_gain_5pct for chw
  winter_heating_average_profile_pmr    peak to mean ratio of the average winter day. summer_cooling_... for chw

Heating-Cooling Relationship, over the hours where both loads are known
  annual_heating_and_cooling_ratio              heating energy divided by cooling energy
  ratio_of_peak_heating_and_cooling             peak heating divided by peak cooling
  simultaneous_heating_and_cooling_hour_ratio   share of hours with both loads above zero, %

Condenser Heat Recovery Potential, over the same hours. The condenser heat is cooling x (1 + 1/COP).
COP is 3 unless another value is given. A COP of 0 leaves the compressor work out, so the condenser heat is the cooling load
  heat_recovery_heating_fraction         share of the heating energy that condenser heat can cover hour by hour, %
  heat_recovery_heat_rejection           share of the condenser heat that is still rejected, %
  heat_recovery_heating_peak_reduction   cut in the peak heating left for other equipment, %
  hrc_capacity_marginal_gain_5pct        heat recovery chiller size, in % of peak cooling, at which one more 5%
                                         step adds less than 5% to the heating covered

Outdoor Temperature & Grid Context
  p00_4_temp, p01_temp, p99_temp, p99_6_temp   0.4, 1, 99 and 99.6 percentile of the outdoor temperature, C
  <rate>_annual_avg                 mean emission factor over the year, kg CO2e/kWh. <rate> is AER_2025 or LRMER_2025
  alignment_factor_summer_<rate>    emission factor weighted by the average summer cooling day, divided by its
                                    plain mean. Above 1 means the load falls in the dirtier hours
  alignment_factor_winter_<rate>    the same for the average winter heating day

Winter is December to February and summer is June to August, so the seasons fit the northern hemisphere.
"""
import numpy as np
import pandas as pd

COP = 3                     # heat recovery chiller, cooling delivered per unit of compressor work. The dataset uses 3
Core_step = 5               # capacity steps of the sizing curves, % of peak
Core_gain_limit = 0.05      # the curve ends at the first step that adds less than this share
Winter, Summer = (12, 1, 2), (6, 7, 8)
G_load, G_rel, G_hr, G_ctx = ("Load Magnitude & Distribution", "Heating-Cooling Relationship",
                              "Condenser Heat Recovery Potential", "Outdoor Temperature & Grid Context")


def clean_cop(cop):
    """The COP as a number. 0 stands for no compressor work, and None or infinity are stored as 0."""
    if cop is None or cop == 0 or np.isinf(cop):
        return 0
    if not cop > 0:
        raise ValueError("cop must be positive, or 0 to leave the compressor work out")
    return float(cop)


def condenser_factor(cop=COP):
    """Condenser heat per unit of cooling, 1 + 1/COP. With a COP of 0 the compressor work is left out and the factor is 1."""
    cop = clean_cop(cop)
    return 1.0 if cop == 0 else 1 + 1 / cop


def running(oper, load):
    """Operating hours: the oper column when the building has one, otherwise the hours with a positive load."""
    if oper is not None and oper.notna().any():
        return oper == 1
    return load.notna() & (load > 0)


def first_small_gain(curve, caps):
    """First capacity step where the relative gain in energy served drops below Core_gain_limit."""
    prev, nxt = curve[:-1], curve[1:]
    with np.errstate(invalid="ignore", divide="ignore"):
        gain = np.where(np.isfinite(prev) & (prev > 0), (nxt - prev) / prev, np.nan)
    hit = np.where(np.isfinite(gain) & (gain < Core_gain_limit))[0]
    return float(caps[hit[0] + 1]) if len(hit) else np.nan


def capacity_fraction(load):
    """Capacity, in % of the peak, beyond which a larger unit serves little more energy."""
    x = load.to_numpy(dtype=float)
    x = x[np.isfinite(x) & (x >= 0)]
    if not len(x) or x.sum() <= 0:
        return np.nan
    caps = np.arange(0, 101, Core_step)
    curve = np.array([np.minimum(x, p / 100 * x.max()).sum() / x.sum() for p in caps])
    return first_small_gain(curve, caps)


def profile_pmr(load, month, hour, months):
    """Peak to mean ratio of the average day of a season. Needs all 24 hours."""
    ok = month.isin(months) & load.notna()
    if not ok.any():
        return np.nan
    a = load[ok].groupby(hour[ok]).mean()
    return float(a.max() / a.mean()) if len(a) == 24 and a.mean() > 0 else np.nan


def alignment(load, e, month, hour, months):
    """Load weighted emission factor of the average day of a season, divided by the plain mean of that day."""
    ok = month.isin(months) & load.notna() & e.notna()
    if not ok.any():
        return np.nan
    L, E = load[ok].groupby(hour[ok]).mean(), e[ok].groupby(hour[ok]).mean()
    if len(L) != 24 or L.sum() <= 0 or E.mean() <= 0:
        return np.nan
    return float((L * E).sum() / L.sum() / E.mean())


def loop_rows(load, oper, lp, ratio_name, n_total, area):
    """The eleven load metrics of one loop."""
    ok = load.notna()
    n = int(ok.sum())
    x = load[ok]
    gt0 = x[x > 0]
    has_oper = oper is not None and oper.notna().any()
    run = running(oper, load)
    known = int(oper.notna().sum()) if has_oper else n
    mx = float(x.max()) if n else np.nan
    q = x.quantile([0.25, 0.75]).to_numpy() if n else [np.nan, np.nan]
    vals = [x.sum() * n_total / n if n else np.nan, mx,
            mx / area if np.isfinite(area) and area > 0 else np.nan,
            gt0.min() if len(gt0) else np.nan, gt0.mean() if len(gt0) else np.nan, gt0.median() if len(gt0) else np.nan,
            q[0], q[1], run.sum() / known * 100 if known > 0 else np.nan, n, n / n_total * 100]
    names = ["annual_load", "max_load", "max_load_per_area", "min_load_gt0", "mean_load_gt0", "median_load_gt0",
             "q25_load", "q75_load", ratio_name, "valid_hours", "data_coverage"]
    return pd.DataFrame({"group": G_load, "loop": lp, "variable": names, "value": vals})


def metrics(h: pd.DataFrame, area_m2=np.nan, emission_columns=(), cop=COP) -> pd.DataFrame:
    """All metrics of one building from its hourly table. Six rows are added for each emission factor column.

    cop is the COP of the heat recovery chiller, used by the four heat recovery metrics. 0 leaves the compressor work out.
    """
    cond = condenser_factor(cop)
    n_total = len(h)
    month, hour = h["timestamp"].dt.month, h["timestamp"].dt.hour
    H, C = h["heating_W"], h["cooling_W"]
    rows = [loop_rows(H, h.get("oper_hhw"), "hhw", "heating_hour_ratio", n_total, area_m2),
            loop_rows(C, h.get("oper_chw"), "chw", "cooling_hour_ratio", n_total, area_m2),
            pd.DataFrame({"group": G_load, "loop": ["hhw", "chw", "hhw", "chw"],
                          "variable": ["heating_capacity_marginal_gain_5pct", "cooling_capacity_marginal_gain_5pct",
                                       "winter_heating_average_profile_pmr", "summer_cooling_average_profile_pmr"],
                          "value": [capacity_fraction(H), capacity_fraction(C),
                                    profile_pmr(H, month, hour, Winter), profile_pmr(C, month, hour, Summer)]})]
    paired = H.notna() & C.notna()
    Qh, Qc = H[paired].to_numpy(dtype=float), C[paired].to_numpy(dtype=float)
    Qcond = Qc * cond
    R = np.minimum(Qh, Qcond)
    both = [np.nan] * 7
    if len(Qh):
        both[0] = Qh.sum() / Qc.sum() if Qc.sum() > 0 else np.nan
        both[1] = Qh.max() / Qc.max() if Qc.max() > 0 else np.nan
        both[2] = ((Qh > 0) & (Qc > 0)).mean() * 100
        both[3] = R.sum() / Qh.sum() * 100 if Qh.sum() > 0 else np.nan
        both[4] = (1 - R.sum() / Qcond.sum()) * 100 if Qcond.sum() > 0 else np.nan
        both[5] = (Qh.max() - np.maximum(0, Qh - Qcond).max()) / Qh.max() * 100 if Qh.max() > 0 else np.nan
        if Qh.sum() > 0 and Qc.max() > 0:
            caps = np.arange(0, 101, Core_step)
            curve = np.array([np.minimum(R, p / 100 * Qc.max() * cond).sum() / Qh.sum() for p in caps])
            both[6] = first_small_gain(curve, caps)
    rows.append(pd.DataFrame({
        "group": [G_rel] * 3 + [G_hr] * 4, "loop": "both",
        "variable": ["annual_heating_and_cooling_ratio", "ratio_of_peak_heating_and_cooling",
                     "simultaneous_heating_and_cooling_hour_ratio", "heat_recovery_heating_fraction",
                     "heat_recovery_heat_rejection", "heat_recovery_heating_peak_reduction", "hrc_capacity_marginal_gain_5pct"],
        "value": both}))
    t = h["oat_C"].dropna() if "oat_C" in h else pd.Series(dtype=float)
    p_air = t.quantile([0.004, 0.01, 0.99, 0.996]).to_numpy() if len(t) else [np.nan] * 4
    rows.append(pd.DataFrame({"group": G_ctx, "loop": "temperature",
                              "variable": ["p00_4_temp", "p01_temp", "p99_temp", "p99_6_temp"], "value": p_air}))
    for cc in emission_columns:
        m, e = cc.replace("_kgCO2_kWh", ""), h[cc]
        rows.append(pd.DataFrame({"group": G_ctx, "loop": "grid",
                                  "variable": [f"{m}_annual_avg", f"alignment_factor_summer_{m}", f"alignment_factor_winter_{m}"],
                                  "value": [e.mean() if e.notna().any() else np.nan,
                                            alignment(C, e, month, hour, Summer), alignment(H, e, month, hour, Winter)]}))
    out = pd.concat(rows, ignore_index=True)
    out["value"] = out["value"].astype(float).round(4)
    return out
