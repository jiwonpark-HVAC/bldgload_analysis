"""One page report: header, number tiles, two rows of four cells."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec, GridSpecFromSubplotSpec

from . import figures as F
from .figures import fs
from .units import W_per_btuh, Ft2_per_m2

Design_w = 16.54   # the layout was designed at A3 landscape, fonts scale with the page width

Si_to_ip = 1 / W_per_btuh / Ft2_per_m2   # kWh/m2 -> kBtu/ft2, W/m2 -> Btu/h ft2


def _fmt(x):
    if x is None or not np.isfinite(x):
        return "NA"
    return f"{x:,.0f}" if abs(x) >= 1000 else f"{x:,.1f}"


def _header(ax, b):
    m = b.meta
    ax.set_axis_off()
    area = m.get("floor_area_m2", np.nan)
    if not np.isfinite(area):
        a_txt = "NA"
    elif b.units.ip:
        a_txt = f"{area * Ft2_per_m2:,.0f} ft2 ({area:,.0f} m2)"
    else:
        a_txt = f"{area:,.0f} m2 ({area * Ft2_per_m2:,.0f} ft2)"
    ax.text(0, 0.72, f"{m.get('name', '')} ({m.get('source', 'measured').capitalize()})", fontsize=fs(16), fontweight="bold", va="center")
    cop_txt = "" if b.cop == F.COP else " | Heat recovery without compressor work" if b.cop == 0 else f" | Heat recovery COP: {b.cop:g}"
    ax.text(0, 0.2, f"Location: {m.get('city', 'NA')} (ASHRAE {m.get('climate', 'NA')}) | Type: {m.get('building_type', 'NA')} | "
                    f"Area: {a_txt} | Completed: {m.get('construction_year', 'NA')} | Data from: {str(m.get('year_start', 'NA'))[:10]}{cop_txt}",
            fontsize=fs(9.5), color="#4d4d4d", va="center")
    if m.get("short_record_days") is not None:
        ax.text(1, 0.72, f"Record covers {m['short_record_days']} days, less than one year. Annual values are scaled up.",
                fontsize=fs(9.5), fontweight="bold", color=F.Col["hhw"], ha="right", va="center")
    ax.axhline(0, color="#a6a6a6", lw=0.7)


def _tiles(ax, b):
    ax.set_axis_off()
    area = F._area(b)
    qh, qc = b.metric("annual_load", "hhw", units="SI") / 1000 / area, b.metric("annual_load", "chw", units="SI") / 1000 / area
    pkh, pkc = b.metric("max_load", "hhw", units="SI") / area, b.metric("max_load", "chw", units="SI") / area
    hr = lambda k: f"{_fmt(b.metric(k, units='SI'))} %" if np.isfinite(b.metric(k, units="SI")) else "n/a"
    tiles = [("annual heating energy", f"{_fmt(qh)} kWh/m2 yr", f"{_fmt(qh * Si_to_ip)} kBtu/sqft yr"),
             ("annual cooling energy", f"{_fmt(qc)} kWh/m2 yr", f"{_fmt(qc * Si_to_ip)} kBtu/sqft yr"),
             ("peak heating load", f"{_fmt(pkh)} W/m2", f"{_fmt(pkh * Si_to_ip)} Btu/h sqft"),
             ("peak cooling load", f"{_fmt(pkc)} W/m2", f"{_fmt(pkc * Si_to_ip)} Btu/h sqft"),
             ("heat recovery heating fraction", hr("heat_recovery_heating_fraction"), ""),
             ("heat recovery heat rejection", hr("heat_recovery_heat_rejection"), ""),
             ("heat recovery peak reduction", hr("heat_recovery_heating_peak_reduction"), "")]
    if b.units.ip:                      # IP building: IP line first, SI below
        tiles = [(lab, ip, si) if ip else (lab, si, ip) for lab, si, ip in tiles]
    n = len(tiles)
    for i, (lab, si, ip) in enumerate(tiles):
        xc = (i + 0.5) / n
        ax.add_patch(plt.Rectangle((i / n + 0.003, 0.08), 1 / n - 0.006, 0.84, fc="#f7f7f7", ec="#cccccc", lw=0.5, transform=ax.transAxes))
        ax.text(xc, 0.70 if ip else 0.60, si, ha="center", va="center", fontsize=fs(13), fontweight="bold", transform=ax.transAxes)
        if ip:
            ax.text(xc, 0.46, ip, ha="center", va="center", fontsize=fs(10), color="#333333", transform=ax.transAxes)
        ax.text(xc, 0.22, lab, ha="center", va="center", fontsize=fs(9), color="#595959", transform=ax.transAxes)


def _stack(fig, spec, b, funcs, heights=None, hspace=0.55, **kw):
    n = len(funcs)
    sub = GridSpecFromSubplotSpec(n, 1, subplot_spec=spec, height_ratios=heights or [1] * n, hspace=hspace)
    for i, f in enumerate(funcs):
        f(b, ax=fig.add_subplot(sub[i]), **kw)


def _water_cell(fig, spec, b):
    sub = GridSpecFromSubplotSpec(3, 2, subplot_spec=spec, hspace=0.9, wspace=0.6)
    F.hhw_flow(b, ax=fig.add_subplot(sub[0, 0]))
    F.chw_flow(b, ax=fig.add_subplot(sub[0, 1]))
    F.hhw_temperature(b, ax=fig.add_subplot(sub[1, 0]))
    F.chw_temperature(b, ax=fig.add_subplot(sub[1, 1]))
    F.hhw_delta_t(b, ax=fig.add_subplot(sub[2, 0]))
    F.chw_delta_t(b, ax=fig.add_subplot(sub[2, 1]))


def _grid_cell(fig, spec, b):
    sub = GridSpecFromSubplotSpec(3, 1, subplot_spec=spec, hspace=0.7)
    lims = None
    if b._emission_columns:
        v = b.hourly[b._emission_columns[:2]].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        lims = (v.min(), v.max()) if len(v) else None
    F.grid_summer(b, ax=fig.add_subplot(sub[0]), lims=lims, legend=True)
    F.grid_winter(b, ax=fig.add_subplot(sub[1]), lims=lims, legend=False)
    F.load_shifting(b, ax=fig.add_subplot(sub[2]))


def build_report(b, path, reference=None, page=(11, 8.5)):
    """page: (width, height) in inches, default US letter landscape. (16.54, 11.69) gives A3."""
    b.metrics()
    F.set_scale(page[0] / Design_w)
    try:
        with plt.rc_context(F.style()):
            fig = plt.figure(figsize=page)
            _header(fig.add_axes([0.04, 0.935, 0.945, 0.055]), b)
            _tiles(fig.add_axes([0.04, 0.845, 0.945, 0.08]), b)
            gs = GridSpec(2, 4, figure=fig, hspace=0.25, wspace=0.42, left=0.05, right=0.975, top=0.815, bottom=0.05)
            _stack(fig, gs[0, 0], b, [F.outdoor_temperature, F.load_vs_temperature])
            _stack(fig, gs[0, 1], b, [F.monthly_heating, F.monthly_cooling])
            _stack(fig, gs[0, 2], b, [F.daily_profile_winter, F.daily_profile_summer])
            _water_cell(fig, gs[0, 3], b)
            _grid_cell(fig, gs[1, 0], b)
            _stack(fig, gs[1, 1], b, [F.heat_recovery, F.heat_recovery_capacity])
            _stack(fig, gs[1, 2], b, [F.part_load, F.capacity_configuration])
            F.dataset_position(b, ax=fig.add_subplot(gs[1, 3]), reference=reference)
            fig.savefig(path)
            plt.close(fig)
    finally:
        F.set_scale(1.0)
    return path
