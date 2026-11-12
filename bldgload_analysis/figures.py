"""Figures, one function per panel. Each takes a Building and an optional matplotlib Axes."""
import numpy as np
import pandas as pd
import functools
import re
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap

from .metrics import COP, Winter, Summer, condenser_factor, running
from .units import Units

Col = {"hhw": "#B3452C", "chw": "#2C6FB3", "n1": "#002676", "n2": "#b0750c", "gold": "#fdb515", "grey": "#737373"}
Months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
Loop = {"hhw": ("heating_W", "oper_hhw", "heating"), "chw": ("cooling_W", "oper_chw", "cooling")}
Season = {"winter": (Winter, "hhw"), "summer": (Summer, "chw")}
Rate_cmap = LinearSegmentedColormap.from_list("rate", ["#FFFFFF", "#FEF0C9", "#FDD87A", "#FDB515", "#B0750C"])

Base_font = {"font.size": 8.4, "axes.titlesize": 10.5, "axes.labelsize": 8.8, "xtick.labelsize": 8.4,
             "ytick.labelsize": 8.4, "legend.fontsize": 7.5}
_scale = [1.0]


def set_scale(k=1.0):
    """Scale every font by k, used by the report when the page is smaller than the design size."""
    _scale[0] = k


def fs(x):
    return x * _scale[0]


# look of the package figures. Applied only while a figure is drawn, the user's own matplotlib settings stay as they are
Fonts = ["Arial", "Helvetica", "DejaVu Sans"]      # the first one installed is used
Style = {"axes.titleweight": "bold", "axes.titlelocation": "left",
         "axes.titlepad": 5, "axes.labelpad": 2, "axes.labelcolor": "#404040",
         "axes.spines.top": False, "axes.spines.right": False, "axes.spines.left": False, "axes.spines.bottom": False,
         "axes.grid": True, "axes.axisbelow": True, "grid.color": "#e0e0e0", "grid.linewidth": 0.35,
         "xtick.color": "#595959", "ytick.color": "#595959", "xtick.major.size": 0, "ytick.major.size": 0,
         "xtick.major.pad": 2, "ytick.major.pad": 2, "legend.frameon": False, "legend.handlelength": 1.6,
         "legend.handletextpad": 0.5, "legend.columnspacing": 1.0, "lines.linewidth": 1.5, "lines.markersize": 2.4}


def style():
    """The matplotlib settings of the package figures at the current font scale."""
    return {**Style, "font.family": _font_family(), **{key: v * _scale[0] for key, v in Base_font.items()}}


@functools.lru_cache(maxsize=1)
def _font_family():
    """Fonts of the package that are installed on this computer, in order of preference."""
    have = set(font_manager.get_font_names())
    return [f for f in Fonts if f in have] or ["sans-serif"]


def _keep_ticks(ax):
    """Fix the tick label size and create the ticks now. matplotlib reads both at draw time, which can be after the style is gone."""
    for a in [ax, *ax.child_axes]:
        for axis, name in ((a.xaxis, "x"), (a.yaxis, "y")):
            if "labelsize" not in axis.get_tick_params():
                axis.set_tick_params(labelsize=plt.rcParams[f"{name}tick.labelsize"])
            axis.get_major_ticks()


def _styled(f):
    """Draw one figure with the package style, without changing the settings of the session."""
    @functools.wraps(f)
    def wrapper(b, ax=None, **kw):
        with plt.rc_context(style()):
            out = f(b, ax=ax, **kw)
            _keep_ticks(out)
        return out
    return wrapper


def _ax(ax, size=(4.2, 3.2)):
    if ax is None:                       # the layout keeps titles, labels and legends inside the figure
        _, ax = plt.subplots(figsize=size, layout="constrained")
    else:
        _restyle(ax)
    return ax


def _restyle(ax):
    """Give an Axes made by the user the package look: spines, grid, ticks and fonts."""
    rc = plt.rcParams
    family = rc["font.family"]
    for side, sp in ax.spines.items():
        sp.set_visible(rc[f"axes.spines.{side}"])
    ax.set_axisbelow(rc["axes.axisbelow"])
    ax.grid(rc["axes.grid"], color=rc["grid.color"], linewidth=rc["grid.linewidth"])
    ax.set_title("", loc=rc["axes.titlelocation"], family=family)
    for axis, name in ((ax.xaxis, "x"), (ax.yaxis, "y")):
        axis.set_tick_params(length=rc[f"{name}tick.major.size"], pad=rc[f"{name}tick.major.pad"],
                             colors=rc[f"{name}tick.color"], labelsize=rc[f"{name}tick.labelsize"])
        for tick in axis.get_major_ticks():
            tick.label1.set_family(family)
            tick.label2.set_family(family)
        axis.label.set(color=rc["axes.labelcolor"], size=rc["axes.labelsize"], family=family)
        axis.labelpad = rc["axes.labelpad"]


def _msg(ax, title, msg):
    ax.set_title(title)
    ax.text(0.5, 0.5, msg, ha="center", va="center", color="grey", fontsize=fs(8), transform=ax.transAxes)
    ax.set_axis_off()
    return ax


def _loop(b, lp):
    load_c, oper_c, _ = Loop[lp]
    h = b.hourly
    load = h[load_c]
    oper = h[oper_c] if oper_c in h else None
    return load, running(oper, load) & load.notna()


def _peak(x):
    x = x[np.isfinite(x) & (x > 0)]
    return float(x.max()) if len(x) else np.nan


def _area(b):
    a = b.meta.get("floor_area_m2", np.nan)
    return a if a and np.isfinite(a) and a > 0 else np.nan


def _band(ax, x, q, color, label=None):
    ax.fill_between(x, q[0], q[4], color=color, alpha=0.16, lw=0)
    ax.fill_between(x, q[1], q[3], color=color, alpha=0.40, lw=0)
    ax.plot(x, q[2], color=color, marker="o", label=label)


def _rate_name(column):
    """'AER_2025_kgCO2_kWh' -> 'AER', the label of an emission factor in a figure."""
    return re.sub(r"_\d{4}$", "", column.replace("_kgCO2_kWh", ""))


def _legend_bottom(ax, ncol=2):
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=ncol, borderaxespad=0)


def _f_axis(ax, which="y", u=None):
    """Twin temperature axis in the other unit system."""
    ip = u is not None and u.ip
    f = (lambda x: (x - 32) * 5 / 9, lambda c: c * 9 / 5 + 32) if ip else (lambda c: c * 9 / 5 + 32, lambda x: (x - 32) * 5 / 9)
    sec = ax.secondary_yaxis("right", functions=f) if which == "y" else ax.secondary_xaxis("top", functions=f)
    (sec.set_ylabel if which == "y" else sec.set_xlabel)("[C]" if ip else "[F]")
    sec.tick_params(length=0, colors="#595959")
    for sp in sec.spines.values():
        sp.set_visible(False)
    return sec


def _unit_y(ax, unit):
    ax.set_ylabel(unit)


def _top_label(sec, text):
    """Unit of a secondary y axis written horizontally above the axis."""
    sec.set_ylabel(text, rotation=0, ha="center", va="bottom")
    sec.yaxis.set_label_coords(1.0, 1.01)


def _month_quantiles(series, month, keep, probs=(0, .25, .5, .75, 1), min_n=8):
    out = np.full((5, 12), np.nan)
    for m in range(1, 13):
        z = series[keep & (month == m)].dropna()
        if len(z) >= min_n:
            out[:, m - 1] = z.quantile(probs).to_numpy()
    return out


# ------------------------------------------------------------------ 1 outdoor air by month
@_styled
def outdoor_temperature(b, ax=None):
    """Outdoor air temperature by month: median, quartiles and range, with the four design temperatures."""
    ax = _ax(ax)
    h = b.hourly
    if "oat_C" not in h or h["oat_C"].notna().sum() < 24:
        return _msg(ax, "Outdoor air temperature", "no outdoor air temperature")
    u = b.units
    q = u.temp(_month_quantiles(h["oat_C"], h["timestamp"].dt.month, pd.Series(True, index=h.index), min_n=24))
    x = np.arange(1, 13)
    _band(ax, x, q, Col["n1"])
    des = [b.meta.get(k) for k in ("design_h996", "design_h99", "design_c1", "design_c04")]
    if not all(d is not None and np.isfinite(d) for d in des):
        des = h["oat_C"].quantile([0.004, 0.01, 0.99, 0.996]).to_numpy()
    for i, (y, lab) in enumerate(zip(u.temp(np.asarray(des, dtype=float)), ["99.6%", "99%", "1%", "0.4%"])):
        ax.axhline(y, color=Col["gold"], lw=0.8)
        ax.text(1.1 + (i % 2) * 3.2, y, f"{lab}  {y:.1f} {u.temp_unit}", color=Col["n2"], fontsize=fs(6.5), va="bottom")
    ax.set(title="Outdoor air temperature", xticks=x, xticklabels=Months, xlim=(1, 12))
    _unit_y(ax, f"[{u.temp_unit}]")
    _f_axis(ax, "y", u)
    return ax


# ------------------------------------------------------------------ 2 load vs outdoor air
@_styled
def load_vs_temperature(b, ax=None):
    """Mean and peak load of each loop against outdoor air temperature, in % of the loop's peak."""
    ax = _ax(ax)
    h = b.hourly
    if "oat_C" not in h or h["oat_C"].notna().sum() < 3:
        return _msg(ax, "Heating and cooling load", "no outdoor air temperature")
    u = b.units
    edges = np.arange(-40, 50, 5)
    ctr = u.temp(edges[:-1] + 2.5)
    bins = pd.cut(h["oat_C"], edges, labels=False, right=False)
    drawn = False
    for lp in ("hhw", "chw"):
        load, keep = _loop(b, lp)
        ok = keep & bins.notna()
        ref = _peak(load[ok].to_numpy(dtype=float))
        if ok.sum() < 3 or not np.isfinite(ref):
            continue
        g = load[ok].groupby(bins[ok])
        n, av, pk = g.size(), g.mean(), g.max()
        idx = n.index[n >= 3].astype(int)
        if not len(idx):
            continue
        lab = lp.upper()
        ax.plot(ctr[idx], av[idx] / ref * 100, color=Col[lp], marker="o", label=f"{lab} mean (peak {u.kload(ref):,.0f} {u.kload_unit})")
        ax.plot(ctr[idx], pk[idx] / ref * 100, color=Col[lp], ls=(0, (2, 2)), marker="o", label=f"{lab} peak")
        drawn = True
    if not drawn:
        return _msg(ax, "Heating and cooling load", "no operating hours with temperature")
    ax.set(title="Heating and cooling load", xlabel=f"outdoor air temperature [{u.temp_unit}]", ylabel="percentage of peak load [%]",
           xlim=tuple(u.temp(np.array([-25.0, 45.0]))), ylim=(0, 100), yticks=range(0, 101, 25))
    _f_axis(ax, "x", u)
    _legend_bottom(ax, 2)
    return ax


# ------------------------------------------------------------------ 3 monthly load
def _mload(b, lp, ax):
    ax = _ax(ax)
    load, keep = _loop(b, lp)
    ref = _peak(load[keep].to_numpy(dtype=float))
    title = f"{Loop[lp][2].capitalize()} load"
    if keep.sum() < 24 or not np.isfinite(ref):
        return _msg(ax, title, "no operating hours")
    q = _month_quantiles(load, b.hourly["timestamp"].dt.month, keep) / ref * 100
    _band(ax, np.arange(1, 13), q, Col[lp])
    ax.set(title=title, xticks=range(1, 13), xticklabels=Months, ylabel="percentage of peak load [%]", ylim=(0, 100), xlim=(1, 12))
    _secondary_wm2(ax, ref, _area(b), u=b.units)
    return ax


@_styled
def monthly_heating(b, ax=None):
    """Heating load by month over operating hours: median, quartiles and range, in % of the peak."""
    return _mload(b, "hhw", ax)


@_styled
def monthly_cooling(b, ax=None):
    """Cooling load by month over operating hours: median, quartiles and range, in % of the peak."""
    return _mload(b, "chw", ax)


def _secondary_wm2(ax, ref_W, area, top=True, u=None):
    u = u or Units()
    if np.isfinite(area):
        d = u.load_density(ref_W / area)
        s = ax.secondary_yaxis("right", functions=(lambda p: p / 100 * d, lambda w: w / d * 100))
        _top_label(s, u.load_density_unit) if top else s.set_ylabel(u.load_density_unit)
        s.tick_params(length=0, colors="#595959")
        for sp in s.spines.values():
            sp.set_visible(False)


# ------------------------------------------------------------------ 4 daily profile by season
def _dayprof(b, season, ax):
    ax = _ax(ax)
    months, lp = Season[season]
    h = b.hourly
    load = h[Loop[lp][0]]
    ok = h["timestamp"].dt.month.isin(months) & load.notna()
    title = "Winter heating load" if season == "winter" else "Summer cooling load"
    if ok.sum() < 24 * 14 or load[ok].max() <= 0:
        return _msg(ax, title, f"no {season} hours")
    ref = load[ok].max()
    hr = h["timestamp"].dt.hour
    q = np.full((5, 24), np.nan)
    for hh in range(24):
        z = load[ok & (hr == hh)]
        if len(z) >= 8:
            q[:, hh] = z.quantile([0, .25, .5, .75, 1]).to_numpy() / ref * 100
    _band(ax, np.arange(24), q, Col[lp])
    ax.set(title=title, xlabel="hour of the day", ylabel="percentage of peak load [%]", xticks=[0, 6, 12, 18, 23], ylim=(0, 100), xlim=(0, 23))
    _secondary_wm2(ax, ref, _area(b), u=b.units)
    return ax


@_styled
def daily_profile_winter(b, ax=None):
    """Heating load by hour of the day in winter: median, quartiles and range, in % of the peak."""
    return _dayprof(b, "winter", ax)


@_styled
def daily_profile_summer(b, ax=None):
    """Cooling load by hour of the day in summer: median, quartiles and range, in % of the peak."""
    return _dayprof(b, "summer", ax)


# ------------------------------------------------------------------ 5 water temperatures vs part load
def _water(b, lp):
    h = b.hourly
    sup, ret, fl = h.get(f"{lp}_sup_C"), h.get(f"{lp}_ret_C"), h.get(f"{lp}_flow_Lps")
    load, run = _loop(b, lp)
    if sup is None or sup.notna().sum() == 0 or ret is None:
        return None
    tv = h.get(f"{lp}_temp_valid")
    keep = (tv.fillna(False).astype(bool) if tv is not None and tv.notna().any() else run)
    dT = sup - ret if lp == "hhw" else ret - sup
    ok = keep & sup.notna() & ret.notna() & load.notna() & (load > 0) & dT.notna() & (dT > 0.5)
    if ok.sum() < 50:
        return None
    return dict(Q=load[ok], sup=sup[ok], ret=ret[ok], dT=dT[ok], flow=fl[ok] if fl is not None else None, pk=_peak(load[ok].to_numpy(dtype=float)))


def _water_temp(b, lp, ax):
    ax = _ax(ax)
    title = lp.upper() + " temperature"
    w = _water(b, lp)
    if w is None:
        return _msg(ax, title, "no water temperature\nand flow data")
    edges = np.arange(0, 101, 5)
    bins = pd.cut(np.minimum(w["Q"] / w["pk"] * 100, 99.999), edges, labels=False, right=False)
    ctr = edges[:-1] + 2.5
    u = b.units
    for key, color, lab in (("sup", Col[lp], "supply"), ("ret", Col["grey"], "return")):
        g = u.temp(w[key]).groupby(bins)
        lo, md, hi = g.min(), g.median(), g.max()
        x = ctr[lo.index.astype(int)]
        ax.fill_between(x, lo, hi, color=color, alpha=0.16, lw=0)
        ax.plot(x, md, color=color, label=lab)
    if w["flow"] is not None and w["flow"].notna().any():
        fmax = w["flow"].max()
        r = (w["flow"] / fmax).where(lambda v: (v > 0) & (v <= 1))
        sfl = w["ret"] + r * w["dT"] if lp == "hhw" else w["ret"] - r * w["dT"]
        md = u.temp(sfl).groupby(bins).median().dropna()
        ax.plot(ctr[md.index.astype(int)], md, color=Col["n2"], lw=1.2, ls=(0, (2, 2)), label="at full flow")
    ax.set(title=title, xlabel="% of peak load", xlim=(0, 100))
    _unit_y(ax, f"[{u.temp_unit}]")
    ax.legend(loc="best", fontsize=fs(6.5), handlelength=1.2)
    return ax


@_styled
def hhw_temperature(b, ax=None):
    """Heating supply and return temperature against part load. Dashed: the supply that full flow would allow."""
    return _water_temp(b, "hhw", ax)


@_styled
def chw_temperature(b, ax=None):
    """Cooling supply and return temperature against part load. Dashed: the supply that full flow would allow."""
    return _water_temp(b, "chw", ax)


# ------------------------------------------------------------------ 6 flow vs part load
def _flow(b, lp, ax):
    ax = _ax(ax)
    title = lp.upper() + " flow"
    h = b.hourly
    fl = h.get(f"{lp}_flow_Lps")
    load, run = _loop(b, lp)
    if fl is None or fl.notna().sum() == 0:
        return _msg(ax, title, "no flow data")
    ok = run & fl.notna() & (fl > 0) & load.notna() & (load > 0)
    if ok.sum() < 50:
        return _msg(ax, title, "too few operating hours")
    pk, fmax = _peak(load[ok].to_numpy(dtype=float)), fl[ok].max()
    edges = np.arange(0, 101, 5)
    bins = pd.cut(np.minimum(load[ok] / pk * 100, 99.999), edges, labels=False, right=False)
    g = (fl[ok] / fmax * 100).groupby(bins)
    lo, md, hi = g.min(), g.median(), g.max()
    x = edges[:-1][lo.index.astype(int)] + 2.5
    ax.plot([0, 100], [0, 100], color="#999999", lw=0.6, ls=(0, (2, 2)))
    ax.fill_between(x, lo, hi, color=Col[lp], alpha=0.18, lw=0)
    ax.plot(x, md, color=Col[lp])
    ax.set(title=title, xlabel="% of peak load", ylabel="% of max flow", xlim=(0, 100), ylim=(0, 102))
    if np.isfinite(fmax) and fmax > 0:
        u = b.units
        fm = u.flow(fmax)
        s = ax.secondary_yaxis("right", functions=(lambda p: p / 100 * fm, lambda f: f / fm * 100))
        _top_label(s, u.flow_unit)
        s.tick_params(length=0, colors="#595959")
        for sp in s.spines.values():
            sp.set_visible(False)
    return ax


@_styled
def hhw_flow(b, ax=None):
    """Heating loop flow against part load, in % of the largest flow."""
    return _flow(b, "hhw", ax)


@_styled
def chw_flow(b, ax=None):
    """Cooling loop flow against part load, in % of the largest flow."""
    return _flow(b, "chw", ax)


# ------------------------------------------------------------------ 7 loop dT vs supply temperature
@_styled
def loop_delta_t(b, ax=None, loops=("hhw", "chw")):
    """Loop temperature difference against supply temperature. The dot size shows the number of hours."""
    ax = _ax(ax)
    title = "Loop temperature difference" if len(loops) > 1 else f"{Loop[loops[0]][2].capitalize()} loop dT"
    drawn = False
    for lp, brk in (("hhw", np.arange(25, 91, 2.5)), ("chw", np.arange(0, 21, 1.0))):
        if lp not in loops:
            continue
        w = _water(b, lp)
        if w is None:
            continue
        bins = pd.cut(w["sup"], brk, labels=False, right=False)
        g = w["dT"].groupby(bins)
        n = g.size()
        idx = n.index[n >= 8].astype(int)
        if not len(idx):
            continue
        u = b.units
        x = u.temp(brk[idx] + np.diff(brk)[0] / 2)
        q = u.dtemp(np.array([g.quantile(p)[idx] for p in (.1, .25, .5, .75, .9)]))
        ax.fill_between(x, q[0], q[4], color=Col[lp], alpha=0.15, lw=0)
        ax.fill_between(x, q[1], q[3], color=Col[lp], alpha=0.33, lw=0)
        ax.plot(x, q[2], color=Col[lp], label=Loop[lp][2])
        ax.scatter(x, q[2], s=n[idx] / n[idx].max() * 20 + 2, color=Col[lp], zorder=3)
        drawn = True
    if not drawn:
        return _msg(ax, title, "no water\ntemperature data")
    ax.set(title=title,
           xlabel=f"supply temperature [{b.units.temp_unit}]", ylabel=f"loop dT [{b.units.dtemp_unit}]")
    if len(loops) > 1:
        _legend_bottom(ax, 2)
    return ax


@_styled
def hhw_delta_t(b, ax=None):
    """Heating loop temperature difference against supply temperature."""
    return loop_delta_t(b, ax, loops=("hhw",))


@_styled
def chw_delta_t(b, ax=None):
    """Cooling loop temperature difference against supply temperature."""
    return loop_delta_t(b, ax, loops=("chw",))


# ------------------------------------------------------------------ 8 grid rates and seasonal load
def _grid_season(b, season, ax, lims=None, legend=True):
    ax = _ax(ax)
    months, lp = Season[season]
    h = b.hourly
    title = f"{season.capitalize()} grid rates and {Loop[lp][2]} load"
    if not b._emission_columns:
        return _msg(ax, title, "no grid emission factors")
    hr = h["timestamp"].dt.hour
    ok_s = h["timestamp"].dt.month.isin(months)
    load = h[Loop[lp][0]]
    strips = []
    for cc in b._emission_columns[:2]:
        e = h.loc[ok_s & h[cc].notna(), cc]
        if len(e):
            strips.append((_rate_name(cc), e.groupby(hr[ok_s & h[cc].notna()]).mean()))
    if not strips:
        return _msg(ax, title, f"no {season} hours")
    allv = np.concatenate([s.to_numpy() for _, s in strips])
    lims = lims or (allv.min(), allv.max())
    for i, (name, s) in enumerate(strips):
        y = 113 + 12 * i
        ax.imshow(s.to_numpy()[None, :], aspect="auto", cmap=Rate_cmap, vmin=lims[0], vmax=lims[1], extent=(-0.5, 23.5, y - 4.5, y + 4.5))
        ax.text(-1.0, y, name, fontsize=fs(6.5), va="center", ha="right", color="#595959", clip_on=False)
    ok = ok_s & load.notna()
    if ok.sum() >= 24:
        L = load[ok].groupby(hr[ok]).mean()
        if len(L) == 24 and L.max() > 0:
            ax.fill_between(L.index, L / L.max() * 100, color=Col[lp], alpha=0.2, lw=0)
            ax.plot(L.index, L / L.max() * 100, color=Col[lp], marker="o")
            _secondary_wm2(ax, L.max(), _area(b), top=False, u=b.units)
    ax.set(title=title, xticks=[0, 6, 12, 18, 23], yticks=[0, 50, 100], ylabel="% of peak load", xlim=(-0.5, 23.5), ylim=(0, 132))
    ax.yaxis.set_label_coords(-0.13, 0.38)
    ax.grid(False)
    if legend:
        sm = plt.cm.ScalarMappable(cmap=Rate_cmap, norm=plt.Normalize(*lims))
        cax = ax.inset_axes([0.5, -0.4, 0.42, 0.07])
        cb = plt.colorbar(sm, cax=cax, orientation="horizontal")
        cb.outline.set_visible(False)
        cax.xaxis.tick_top()
        cax.tick_params(labelsize=fs(6.5), length=2, pad=1)
        cax.set_ylabel("kg CO2e / kWh", fontsize=fs(6.5), rotation=0, ha="right", va="center", labelpad=4)
    return ax


@_styled
def grid_summer(b, ax=None, **kw):
    """Emission factors by hour in summer, above the average summer cooling day."""
    return _grid_season(b, "summer", ax, **kw)


@_styled
def grid_winter(b, ax=None, **kw):
    """Emission factors by hour in winter, above the average winter heating day."""
    return _grid_season(b, "winter", ax, **kw)


# ------------------------------------------------------------------ 9 current grid status and potential
@_styled
def load_shifting(b, ax=None):
    """Emission factor the load sees now, between the cleanest and the dirtiest hour of the average day."""
    ax = _ax(ax)
    if not b._emission_columns:
        return _msg(ax, "Current grid status and potential", "no grid emission factors")
    h = b.hourly
    hr, mo = h["timestamp"].dt.hour, h["timestamp"].dt.month
    rows = []
    for season, (months, lp) in Season.items():
        for cc in b._emission_columns:
            ok = mo.isin(months) & h[cc].notna() & h[Loop[lp][0]].notna()
            if ok.sum() < 24:
                continue
            L, E = h.loc[ok, Loop[lp][0]].groupby(hr[ok]).mean(), h.loc[ok, cc].groupby(hr[ok]).mean()
            if len(L) != 24 or L.sum() <= 0:
                continue
            rows.append((f"{season} {_rate_name(cc)}", (L * E).sum() / L.sum(), E.min(), E.max()))
    if not rows:
        return _msg(ax, "Current grid status and potential", "no seasonal hours")
    rows.sort(key=lambda r: r[0], reverse=True)
    y = np.arange(len(rows))
    best, cur, worst = (np.array([r[i] for r in rows]) for i in (2, 1, 3))
    ax.barh(y, best, color=Col["n1"], height=0.5, label="minimum emission")
    ax.barh(y, cur - best, left=best, color=Col["gold"], height=0.5, label="current emission")
    ax.barh(y, worst - cur, left=cur, color="#e5e5e5", height=0.5, label="maximum emission")
    for yi, r in zip(y, rows):
        ax.text(r[3] * 1.02, yi, f"{(r[1] - r[2]) / r[1] * 100:.0f}%" if r[1] > 0 else "", va="center", fontsize=fs(7))
    ax.set(title="Current grid status and potential", yticks=y, yticklabels=[r[0] for r in rows], xlabel="kg CO2e / kWh", xlim=(0, worst.max() * 1.18))
    ax.tick_params(axis="y", labelsize=fs(7))
    ax.grid(axis="y", visible=False)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.34), ncol=3, borderaxespad=0, handlelength=1.2)
    return ax


# ------------------------------------------------------------------ 10 condenser heat recovery potential
@_styled
def heat_recovery(b, ax=None):
    """The three condenser heat recovery metrics as bars, with the energy or load each one refers to."""
    ax = _ax(ax)
    hrhf, rej, hcr = (b.metric(k, units="SI") for k in ("heat_recovery_heating_fraction", "heat_recovery_heat_rejection",
                                           "heat_recovery_heating_peak_reduction"))
    if not np.isfinite(hrhf):
        return _msg(ax, "Condenser heat recovery potential", "needs hours with both heating\nand cooling load valid")
    area = _area(b)
    qh, qc = b.metric("annual_load", "hhw", units="SI") / 1000 / area, b.metric("annual_load", "chw", units="SI") / 1000 / area
    pkh = b.metric("max_load", "hhw", units="SI") / 1000
    labs = ["heating fraction", "heat rejection", "peak reduction"]
    got = np.clip([hrhf, rej, hcr], 0, 100)
    u = b.units
    tot = [f"{u.energy_density(qh):,.0f} {u.energy_density_unit}" if np.isfinite(qh) else "",
           f"{u.energy_density(qc * condenser_factor(b.cop)):,.0f} {u.energy_density_unit}" if np.isfinite(qc) else "",
           f"{u.kload(pkh * 1000):,.0f} {u.kload_unit}"]
    y = np.arange(3)[::-1]
    ax.barh(y, got, color=Col["n1"], height=0.5)
    ax.barh(y, 100 - got, left=got, color="none", edgecolor=Col["gold"], height=0.5, lw=0.8)
    for yi, g in zip(y, got):
        ax.text(g + 1.5, yi, f"{g:.1f}%", va="center", fontsize=fs(7))
    ax.set(title="Condenser heat recovery potential", yticks=y, xlabel="Fraction [%]", xlim=(0, 100), xticks=[0, 25, 50, 75, 100])
    ax.set_yticklabels([f"{l}\n{t}" if t else l for l, t in zip(labs, tot)])
    for lab in ax.get_yticklabels():
        lab.set_ha("right")
    ax.grid(axis="y", visible=False)
    return ax


# ------------------------------------------------------------------ 11 HRC sizing curve
@_styled
def heat_recovery_capacity(b, ax=None):
    """Heating covered by heat recovery against the size of the heat recovery chiller."""
    ax = _ax(ax)
    h = b.hourly
    ok = h["heating_W"].notna() & h["cooling_W"].notna()
    Qh, Qc = h.loc[ok, "heating_W"].to_numpy(dtype=float), h.loc[ok, "cooling_W"].to_numpy(dtype=float)
    if not len(Qh) or Qh.sum() <= 0 or Qc.max() <= 0:
        return _msg(ax, "HR heating fraction vs HRC capacity", "needs hours with both heating\nand cooling load valid")
    cond = condenser_factor(b.cop)
    R = np.minimum(Qh, Qc * cond)
    pcts = np.array([0, 3, 4, 5, 6, 8, 10, 15, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    curve = np.array([np.minimum(R, p / 100 * Qc.max() * cond).sum() / Qh.sum() * 100 for p in pcts])
    knee = b.metric("hrc_capacity_marginal_gain_5pct", units="SI")
    ax.axhline(R.sum() / Qh.sum() * 100, color="grey", lw=0.6, ls="--")
    ax.plot(pcts, curve, color=Col["n2"], lw=1.3, marker="o", ms=2.5)
    if np.isfinite(knee):
        ax.axvline(knee, color=Col["n1"], lw=0.8, ls=":")
        ax.text(knee + 1, 3, f"5% gain limit at {knee:.0f}%", fontsize=fs(7), color=Col["n1"])
    area = _area(b)
    xlab = "HRC capacity fraction of peak cooling [%]"
    if np.isfinite(area):
        u = b.units
        xlab += f"\n100% = {u.load_density(Qc.max() / area):,.0f} {u.load_density_unit}, {u.kload(Qc.max()):,.0f} {u.kload_unit}"
    ax.set(title="HR heating fraction vs HRC capacity", xlabel=xlab, ylabel="annual covered heating energy [%]",
           xlim=(0, 100), ylim=(0, 100), xticks=range(0, 101, 20), yticks=range(0, 101, 25))
    return ax


# ------------------------------------------------------------------ 12 part load distribution
@_styled
def part_load(b, ax=None):
    """Share of operating hours at or below each part load, for both loops."""
    ax = _ax(ax)
    drawn = False
    for lp in ("hhw", "chw"):
        load, keep = _loop(b, lp)
        z = load[keep & (load > 0)].to_numpy(dtype=float)
        if not len(z):
            continue
        ps = np.arange(0, 101, 10)
        y = [np.mean(z < z.max() * p / 100) * 100 for p in ps]
        y[-1] = 100
        ax.plot(ps, y, color=Col[lp], marker="o", label=Loop[lp][2])
        drawn = True
    if not drawn:
        return _msg(ax, "Partial load distribution", "no operating hours")
    ax.set(title="Partial load distribution", xlabel="percentage of peak load [%]", ylabel="satisfied operating hours [%]",
           xlim=(0, 100), ylim=(0, 100), xticks=[0, 25, 50, 75, 100], yticks=[0, 25, 50, 75, 100])
    _legend_bottom(ax, 2)
    return ax


# ------------------------------------------------------------------ 13 primary and backup sizing
@_styled
def capacity_configuration(b, ax=None):
    """How much smaller the primary equipment gets when the top hours are left to backup equipment."""
    ax = _ax(ax)
    pcts = [0.1, 0.5, 1, 5, 10]
    x = np.arange(len(pcts))
    drawn = False
    for k, lp in enumerate(("hhw", "chw")):
        load, keep = _loop(b, lp)
        z = load[keep & (load > 0)].to_numpy(dtype=float)
        if len(z) < 100:
            continue
        cut = [(1 - np.quantile(z, 1 - p / 100) / z.max()) * 100 for p in pcts]
        bars = ax.bar(x + (k - 0.5) * 0.4, cut, width=0.38, color=Col[lp], label=Loop[lp][2])
        ax.bar_label(bars, fmt="%.0f%%", fontsize=fs(7.5), padding=1, color="#4d4d4d")
        drawn = True
    if not drawn:
        return _msg(ax, "Primary and peaking equipment size", "too few operating hours")
    ax.set(title="Primary and peaking equipment size", xticks=x, xticklabels=[f"{p:g}%" for p in pcts],
           xlabel="share of operating hours given to backup", ylabel="primary capacity reduction [%]")
    ax.grid(axis="x", visible=False)
    _legend_bottom(ax, 2)
    return ax


# ------------------------------------------------------------------ 14 position in a reference dataset
Context = [("hhw", "max_load_per_area", "peak heating load", "density"), ("chw", "max_load_per_area", "peak cooling load", "density"),
           ("hhw", "heating_hour_ratio", "heating hours", "%"), ("chw", "cooling_hour_ratio", "cooling hours", "%"),
           ("both", "annual_heating_and_cooling_ratio", "heating to cooling", ""),
           ("both", "heat_recovery_heating_fraction", "HR heating fraction", "%"),
           ("both", "heat_recovery_heat_rejection", "HR heat rejection", "%"),
           ("both", "heat_recovery_heating_peak_reduction", "HR peak reduction", "%")]


@_styled
def dataset_position(b, ax=None, reference=None):
    """reference: load_summary.csv of the dataset, long format with loop, variable, value. None uses the example buildings.

    The dataset values are for a COP of 3. With another COP the heat recovery rows of the example buildings are
    recomputed with that COP from their hourly loads. With a reference file of your own those rows are left out.
    """
    ax = _ax(ax)
    from . import examples
    heat_recovery = None                     # the heat recovery values to compare with, when the COP is not 3
    if reference is None:
        try:
            reference = examples.reference()
        except Exception:
            return _msg(ax, "Position in the dataset", "no reference dataset\n(use_examples or reference=)")
        if b.cop != COP:
            try:
                heat_recovery = examples.heat_recovery_reference(b.cop)
            except Exception:
                heat_recovery = None
    ref = reference if isinstance(reference, pd.DataFrame) else pd.read_csv(reference)
    rows = []
    u = b.units
    for lp, var, lab, unit in Context:
        src = ref
        if "heat_recovery" in var and b.cop != COP:
            if heat_recovery is None:
                continue
            src = heat_recovery
        peers = src.loc[(src["loop"] == lp) & (src["variable"] == var), "value"].dropna()
        v = b.metric(var, lp, units="SI")
        if len(peers) and np.isfinite(v):
            shown = f"{u.load_density(v):,.1f} {u.load_density_unit}" if unit == "density" else f"{v:,.1f} {unit}".strip()
            rows.append((lab, (peers < v).mean() * 100, shown, len(peers)))
    if not rows:
        return _msg(ax, "Position in the dataset", "no comparable metrics")
    y = np.arange(len(rows))[::-1]
    for yi, (lab, pct, v, n) in zip(y, rows):
        ax.plot([0, 100], [yi, yi], color="#e5e5e5", lw=4, solid_capstyle="round")
        ax.plot(pct, yi, "o", color=Col["hhw"], ms=5)
        ax.text(104, yi, v, va="center", fontsize=fs(7.5), color="#404040")
    ax.axvline(50, color="#b3b3b3", lw=0.6, ls=(0, (2, 2)))
    ax.set(title=f"Position in the dataset (n = {max(r[3] for r in rows)})", yticks=y, yticklabels=[r[0] for r in rows],
           xlabel="percentile", xlim=(0, 140), xticks=[0, 25, 50, 75, 100])
    ax.tick_params(axis="y", labelsize=fs(7.5))
    ax.grid(False)
    return ax


_figures = {
    "outdoor_temperature": outdoor_temperature, "load_vs_temperature": load_vs_temperature,
    "monthly_heating": monthly_heating, "monthly_cooling": monthly_cooling,
    "daily_profile_winter": daily_profile_winter, "daily_profile_summer": daily_profile_summer,
    "hhw_temperature": hhw_temperature, "chw_temperature": chw_temperature,
    "hhw_flow": hhw_flow, "chw_flow": chw_flow, "loop_delta_t": loop_delta_t, "hhw_delta_t": hhw_delta_t, "chw_delta_t": chw_delta_t,
    "grid_summer": grid_summer, "grid_winter": grid_winter, "load_shifting": load_shifting,
    "heat_recovery": heat_recovery, "heat_recovery_capacity": heat_recovery_capacity,
    "part_load": part_load, "capacity_configuration": capacity_configuration, "dataset_position": dataset_position,
}
