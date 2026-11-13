"""Cleaning protocol for one hydronic loop, same rules as the Berkeley Decarb Tool dataset."""
import numpy as np
import pandas as pd

Flow_neg_tol_lps = 0.1         # L/s, a negative flow this small is a zero offset and is set to 0
Load_zero_w = 100              # W, the plant counts as idle below this load
Load_zero_frac = 0.01          # or below this share of the 99th percentile load, whichever is larger
Load_neg_tol_frac = 0.01       # a negative load within this share of the peak is set to 0, a larger one is removed
Load_max_w = 10e6              # W, a load above this is removed
Flow_max_lps = 1000            # L/s, a flow at or above this is removed
Inversion_k = 5                # K, a return warmer than the supply (heating) by more than this is removed
Stuck_run = 9                  # readings, a run of this many identical non zero readings is a stuck sensor
Temp_resolution_k = 0.01       # K, only a temperature sensor that records finer steps than this is checked for stuck readings
T_max = {"heating": 130, "cooling": 45}      # C, a water temperature outside 0 to this is removed
Oper = {"t_sup_min_heating": 32, "t_sup_max_cooling": 18.5, "flow_min": 0.06, "load_min": 100}   # C, C, L/s, W: the plant is running
Max_zero_run_h = 24 * 90       # h, a year with a longer stretch of no load in both loops is avoided

Loop_cols = ["sup", "ret", "flow", "load_meas"]
Flag_cols = ["flag_flow_zero_offset", "flag_flow_large_negative", "flag_sup_out_of_range", "flag_ret_out_of_range",
             "flag_flow_out_of_range", "flag_load_meas_out_of_range", "flag_sup_consec", "flag_ret_consec",
             "flag_flow_consec", "flag_load_consec", "flag_temp_inversion", "flag_load_calc_out_of_range",
             "flag_load_large_negative"]


def stuck_run(x: pd.Series, min_run=Stuck_run) -> pd.Series:
    """True on every member of a run of >= min_run identical non zero readings. NA and 0 break a run."""
    v = x.to_numpy(dtype=float)
    valid = np.isfinite(v) & (v != 0)
    key = np.where(valid, v, np.nan)
    new = np.ones(len(v), dtype=bool)
    new[1:] = ~(valid[1:] & valid[:-1] & (key[1:] == key[:-1]))
    run_id = np.cumsum(new)
    length = pd.Series(run_id).map(pd.Series(run_id).value_counts()).to_numpy()
    return pd.Series(valid & (length >= min_run), index=x.index)


def flow_negatives(df):
    """Small negative flow, or negative flow while the plant is idle, becomes 0. Other negative flow is removed."""
    flow = df["flow"]
    lm = df["load_meas"]
    if lm.notna().any():
        peak = np.nanquantile(np.abs(lm.to_numpy(dtype=float)), 0.99)
        thr = max(Load_zero_w, Load_zero_frac * peak) if np.isfinite(peak) else Load_zero_w
        idle = lm.notna() & (lm.abs() < thr)
    else:
        idle = pd.Series(False, index=df.index)
    neg = flow.notna() & (flow < 0)
    zeroable = neg & ((flow >= -Flow_neg_tol_lps) | idle)
    df["flag_flow_zero_offset"] = zeroable
    df["flag_flow_large_negative"] = neg & ~zeroable
    df["flow"] = flow.where(~neg, np.where(zeroable, 0.0, np.nan))
    return df


def range_fence(df, mode):
    """Flag and remove temperatures, flow and measured load outside their plausible range."""
    tmax = T_max[mode]
    for c in ("sup", "ret"):
        df[f"flag_{c}_out_of_range"] = df[c].notna() & ((df[c] < 0) | (df[c] > tmax))
        df[c] = df[c].where(~df[f"flag_{c}_out_of_range"])
    df["flag_flow_out_of_range"] = df["flow"].notna() & (df["flow"] >= Flow_max_lps)
    df["flow"] = df["flow"].where(~df["flag_flow_out_of_range"])
    lm = df["load_meas"]
    bad = lm.notna() & ((lm > Load_max_w) | (lm < -0.01 * Load_max_w))
    df["flag_load_meas_out_of_range"] = bad
    df["load_meas"] = lm.where(~bad).clip(lower=0)
    return df


def fine_resolution(x: pd.Series, limit=Temp_resolution_k) -> bool:
    """True when the sensor records steps finer than the limit.

    The step is the typical (median) gap between neighbouring distinct readings. A water temperature held at
    its setpoint repeats on a coarse sensor, say 0.1 C steps, and that is normal. The same value down to
    several decimals, many times in a row, is not.
    """
    v = np.unique(x.to_numpy(dtype=float))
    gaps = np.diff(v[np.isfinite(v)])
    gaps = gaps[gaps > 1e-9]
    return bool(len(gaps)) and float(np.median(gaps)) < limit


def stuck_sensors(df):
    """Remove the readings of a stuck sensor, for each of supply, return, flow and measured load.

    Flow and load are always checked. A temperature is checked only when its sensor has a fine resolution.
    """
    for c, f in zip(Loop_cols, ["flag_sup_consec", "flag_ret_consec", "flag_flow_consec", "flag_load_consec"]):
        if c in ("sup", "ret") and not fine_resolution(df[c]):
            df[f] = False
            continue
        m = stuck_run(df[c])
        df[f] = m
        df[c] = df[c].where(~m)
    return df


def load_calc(df, mode):
    """Load from flow and temperature difference (4186 J/kg K, 1 kg/L). A large temperature inversion removes the hour."""
    dt = df["sup"] - df["ret"] if mode == "heating" else df["ret"] - df["sup"]
    inv = dt.notna() & (dt < -Inversion_k)
    df["flag_temp_inversion"] = inv
    df["load_meas"] = df["load_meas"].where(~inv)
    dt = dt.where(~inv).where(~((dt >= -Inversion_k) & (dt < 0)), 0.0)
    lc = 4186 * df["flow"] * dt
    bad = lc.notna() & (lc.abs() > Load_max_w)
    df["flag_load_calc_out_of_range"] = bad
    df["load_calc"] = lc.where(~bad)
    return df


def to_hourly(df):
    """Hourly mean of the values, and a flag is set when any reading in the hour had it."""
    g = df.groupby(df["datetime"].dt.floor("h"))
    num = g[["sup", "ret", "flow", "load_calc", "load_meas"]].mean()
    flags = g[[c for c in Flag_cols if c in df.columns]].any()
    out = pd.concat([num, flags], axis=1).reset_index().rename(columns={"datetime": "timestamp"})
    return out


def clamp_negative(x: pd.Series, tol=Load_neg_tol_frac):
    """Small negative load becomes 0, large negative load is removed. Returns the load and the flag."""
    peak = x.max(skipna=True)
    peak = peak if np.isfinite(peak) and peak > 0 else 0
    thr = -tol * peak
    flagged = x.notna() & (x < thr)
    return x.where(~flagged).clip(lower=0), flagged


def resolve_load(h, mismatch_frac=0.2, min_e_W=2000):
    """The measured load is used. Where it differs from the calculated load by more than 20% and 2 kW, the calculated one is used."""
    L, E = h["load_meas"], h["load_calc"]
    frac = (1 - L / E).abs()
    mis = np.isfinite(frac) & (frac > mismatch_frac) & E.notna() & ((L - E).abs() > min_e_W)
    load = L.where(L.notna() & ~mis, E)
    h["load"], h["flag_load_large_negative"] = clamp_negative(load)
    return h


def operating_state(h, mode):
    """oper is 1 when the plant runs, 0 when it is off, empty when it cannot be told. The load of an off hour is 0.

    With no supply temperature and no flow, a load of at least 100 W means running. Otherwise the supply
    temperature, the flow and the load all have to agree.
    """
    s, f = h["sup"], h["flow"]
    c_temp = (s >= Oper["t_sup_min_heating"]) if mode == "heating" else (s < Oper["t_sup_max_cooling"])
    c_temp = c_temp.where(s.notna())
    c_flow = (f > Oper["flow_min"]).where(f.notna())
    c_load = (h["load"] >= Oper["load_min"]).where(h["load"].notna())
    c_load = c_load.where(c_load.notna(), (h["load_calc"] >= Oper["load_min"]).where(h["load_calc"].notna()))
    t, fl, ld = [c.astype("boolean") for c in (c_temp, c_flow, c_load)]
    no_sf = s.isna() & f.isna()
    conds = [
        no_sf & ld.notna() & ld.fillna(False),
        no_sf & ld.notna() & ~ld.fillna(True),
        ld.isna() & (s.isna() | f.isna()),
        ld.isna() & t.fillna(False) & fl.fillna(False),
        ld.isna(),
        (t.notna() & ~t.fillna(True)) | (fl.notna() & ~fl.fillna(True)) | ~ld.fillna(True),
        ld.notna() & ld.fillna(False),
    ]
    vals = [1, 0, np.nan, 1, 0, 0, 1]
    oper = np.select([c.to_numpy(dtype=bool) for c in conds], vals, default=np.nan)
    h["oper"] = oper
    h["load"] = h["load"].where(h["oper"] != 0, 0.0)
    return h


def temp_valid(h, mode):
    """Hours whose water temperatures can be trusted: running, in range, not stuck, not inverted, with a positive load."""
    tmax = T_max[mode]
    g = lambda c: h[c].fillna(False).astype(bool) if c in h else pd.Series(False, index=h.index)
    h["temp_valid"] = ((h["oper"] == 1) & h["sup"].notna() & h["ret"].notna()
                       & h["sup"].between(0, tmax) & h["ret"].between(0, tmax)
                       & ~g("flag_sup_consec") & ~g("flag_ret_consec") & ~g("flag_temp_inversion")
                       & h["load"].notna() & (h["load"] > 0))
    return h


def regular_steps(df):
    """Add an empty row for every missing time step, so a gap in the record breaks a run of identical readings.

    The step is the most common spacing. A record whose timestamps do not sit on that grid is left as it is.
    """
    t = df["datetime"]
    if len(t) < 3:
        return df
    step = t.diff().dropna().mode().iloc[0]
    if step <= pd.Timedelta(0) or ((t - t.iloc[0]) % step != pd.Timedelta(0)).any():
        return df
    grid = pd.DataFrame({"datetime": pd.date_range(t.iloc[0], t.iloc[-1], freq=step)})
    return grid.merge(df.drop_duplicates("datetime"), on="datetime", how="left")


def clean_loop(raw: pd.DataFrame, mode: str, stuck: bool = True) -> pd.DataFrame:
    """raw: datetime, sup, ret, flow, load_meas at native resolution. Returns the cleaned hourly loop.

    stuck=False skips the stuck sensor check. Simulated data has no sensors, and a constant load or flow is real there.
    """
    df = raw.sort_values("datetime").reset_index(drop=True).copy()
    for c in Loop_cols:
        if c not in df:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = regular_steps(df)
    df = flow_negatives(df)
    df = range_fence(df, mode)
    if stuck:
        df = stuck_sensors(df)
    else:
        for f in ("flag_sup_consec", "flag_ret_consec", "flag_flow_consec", "flag_load_consec"):
            df[f] = False
    df = load_calc(df, mode)
    h = to_hourly(df)
    h = resolve_load(h)
    h = operating_state(h, mode)
    h = temp_valid(h, mode)
    return h


def best_year(h: pd.DataFrame):
    """Pick the best 8760 or 8784 hour window. Returns (start, end) or None when no window starting at midnight fits."""
    ts = h["timestamp"]
    if (ts.max() - ts.min()).days < 365:
        first = ts.min()                     # a record of exactly one year that starts at midnight is its own window
        n = year_hours(first)
        if first == first.floor("D") and first + pd.Timedelta(hours=n - 1) <= ts.max():
            return first, first + pd.Timedelta(hours=n - 1)
        return None
    full = pd.DataFrame({"timestamp": pd.date_range(ts.min().floor("D"), ts.max() + pd.Timedelta(days=2), freq="h")})
    full = full.merge(h[["timestamp", "heating_W", "cooling_W"]], on="timestamp", how="left")
    hw, cw = full["heating_W"].to_numpy(dtype=float), full["cooling_W"].to_numpy(dtype=float)
    both0 = (~np.isfinite(hw) | (hw == 0)) & (~np.isfinite(cw) | (cw == 0))
    starts = pd.date_range(ts.min().floor("D"), ts.max().floor("D") - pd.Timedelta(days=365), freq="D")
    best = None
    for s in starts:
        n = year_hours(s)
        i0 = int((s - full["timestamp"].iloc[0]) / pd.Timedelta(hours=1))
        a, b, z = hw[i0:i0 + n], cw[i0:i0 + n], both0[i0:i0 + n]
        fail = _max_run(z) > Max_zero_run_h
        total_na = max((~np.isfinite(a)).sum(), (~np.isfinite(b)).sum())
        consec = max(_max_run(~np.isfinite(a)), _max_run(~np.isfinite(b)))
        key = (fail, total_na, consec, -s.value)
        if best is None or key < best[0]:
            best = (key, s, s + pd.Timedelta(hours=n - 1))
    return None if best is None else (best[1], best[2])


def year_hours(start):
    """8784 when the year that starts here holds a February 29, otherwise 8760."""
    leap = any(pd.Timestamp(y, 2, 29) >= start and pd.Timestamp(y, 2, 29) <= start + pd.Timedelta(hours=8783)
               for y in range(start.year, start.year + 2) if _leap(y))
    return 8784 if leap else 8760


def _leap(y):
    return y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)


def _max_run(mask):
    if not mask.any():
        return 0
    d = np.diff(np.concatenate(([0], mask.astype(int), [0])))
    return int((np.where(d == -1)[0] - np.where(d == 1)[0]).max())
