# bldgload_analysis

Heating and cooling load metrics for one building with hydronic HVAC. The package cleans the raw data
with the same protocol as the Berkeley Decarb Tool dataset, picks the best 8760 hour year, computes the
43 core metrics, and draws a one page report or any of its figures on its own. The buildings of that
dataset ship with the package as example buildings, so a building can be compared with them.

## Install

```
pip install git+https://github.com/jiwonpark-HVAC/bldgload_analysis.git
```

From a local copy of this folder, use `pip install -e .` instead.

It needs Python 3.10 or later. pandas, numpy, matplotlib and pyarrow are installed with it.

## Use

```python
from bldgload_analysis import Building

building = Building.from_csv(
    "building.csv",
    name="Hospital",                 # Building_user_Hospital, None gives Building_user_1, _2, ...
    floor_area=9000,
    area_unit="m2",                  # "m2" or "ft2"
    units="SI",                      # "SI" (W, C, L/s) or "IP" (Btu/h, F, gpm) for the file, outputs follow
    building_type="Hospital",
    city="San Francisco",
    climate="3C",
    construction_year=2015,
    source="simulated",              # "measured" or "simulated"
)
building.metrics()                                 # DataFrame with group, loop, variable, value, unit
building.metric("heat_recovery_heating_fraction")  # one value
building.metric("max_load", "chw")                 # the loop is needed when a metric exists for both loops
building.save()                                    # Building_user_Hospital/hourly.csv, metrics.csv, meta.json
building.report("report.pdf")                      # US letter landscape, page=(16.54, 11.69) for A3
building.figures                                   # figure names
ax = building.plot("heat_recovery_capacity")       # matplotlib Axes
building = Building.load("Building_user_Hospital") # back from the saved folder
```

`example/run.py` is a filled in template.

The metrics table has 43 rows. Six of them are grid metrics, so it has 37 rows when no emission factors
are found.

## Input file

One CSV with hourly or finer time steps.

| column | SI | IP | needed |
|---|---|---|---|
| `timestamp` | local standard time | | yes |
| `hhw_load` | W | Btu/h | heating loop, or give sup, ret and flow |
| `hhw_sup`, `hhw_ret`, `hhw_flow` | C, C, L/s | F, F, gpm | optional |
| `chw_load` | W | Btu/h | cooling loop, or give sup, ret and flow |
| `chw_sup`, `chw_ret`, `chw_flow` | C, C, L/s | F, F, gpm | optional |
| `oat` | C | F | outdoor air temperature. Optional, filled from the location when missing |
| `rh_pct` | % | % | optional, carried through. `rh` and `rh_out` are read as well |

`units="SI"` or `"IP"` says which system the file is in. A column can also carry its own unit as a
suffix, and then the suffix wins. The suffixes are `_W`, `_kW`, `_Btuh`, `_kBtuh`, `_C`, `_F`, `_Lps`
and `_gpm`, as in `hhw_load_kW` or `oat_F`. Names are read in any case. `heating` and `cooling` are
accepted for the two load columns. A missing column is treated as not measured. With loads only,
operating hours are the hours with a positive load.

A record shorter than one year still runs. The annual values are then scaled up from the hours
available, a warning is shown, and the report says so in its header.

## Cleaning

Each loop goes through these steps before the metrics are computed.

1. A small negative flow, or a negative flow while the plant is idle, is set to zero. Other negative flow is removed.
2. Temperatures, flow and measured load outside their plausible range are removed.
3. A run of nine or more identical readings is removed as a stuck sensor. Flow and load are always
   checked. A temperature is checked only when its sensor records steps finer than 0.01 K, because a
   supply temperature held at its setpoint repeats on a coarser sensor.
4. The load is calculated from flow and temperature difference. A large temperature inversion removes the hour.
5. The data is averaged to hours. The measured load is used. Where it differs from the calculated load
   by more than 20% and 2 kW, the calculated load is used.
6. Each hour is marked as running or off from the supply temperature, the flow and the load.
7. The year with the fewest missing hours is selected. `select_year=False` keeps the whole record.

The thresholds are at the top of `bldgload_analysis/clean.py`.

## Metrics

| group | metrics |
|---|---|
| Load Magnitude & Distribution | annual and peak load, load per floor area, load statistics, operating hours, data coverage, capacity sizing, daily peak to mean ratio. One set for each loop |
| Heating-Cooling Relationship | ratio of annual energy, ratio of peaks, share of hours with both loads |
| Condenser Heat Recovery Potential | heating fraction covered, heat still rejected, peak heating reduction, heat recovery chiller size |
| Outdoor Temperature & Grid Context | design percentiles of the outdoor temperature, mean emission factors, alignment of the load with the grid |

The definition of every metric is at the top of `bldgload_analysis/metrics.py`. `help(bldgload_analysis.metrics)` shows it.

## Units

Everything inside is SI. `floor_area` takes `area_unit="m2"` or `"ft2"`. With `units="IP"` the
metrics table, `hourly.csv`, the report and the figures come back in IP. The metrics table then uses
Btu, Btu/h and Btu/h ft2, and the report shows energy in kBtu/ft2. `building.metrics(units="SI")` or
`building.metric(name, units="SI")` asks for the other system at any time. The metrics table always
carries a `unit` column.

## Heat recovery COP

The four heat recovery metrics take the condenser heat as the cooling load times (1 + 1/COP). The COP is 3,
as in the dataset. `cop=4` in `from_csv` or `from_example` sets another value, and `building.cop = 4` changes
it later. `cop=0` leaves the compressor work out, so the condenser heat equals the cooling load.

The dataset values are for a COP of 3. With another COP the "position in the dataset" panel recomputes the
heat recovery values of the example buildings with the same COP from their hourly loads. With a
`reference=` file of your own those rows are left out.

## Filled in from the location

With a `city` (or `latitude`, `longitude` and `timezone`) the package fills what the file lacks.

When the file has no outdoor temperature, hourly temperature and relative humidity for the dates of the
record come from the Open-Meteo archive and are converted to local standard time.

When no `emission_factors` are given, the Cambium grid region (GEA) is found from the city (`lookup.Gea_cities`,
then the state table `lookup.State_to_gea`). The month-hour AER and LRMER of that region are then
downloaded from the NLR Scenario Viewer (https://scenarioviewer.nlr.gov) and kept under
`~/.bldgload_analysis`. The first download is about 27 MB. Both tables follow NLR's ZIP code to GEA
table. The state table is approximate where a state is split between regions, so check the region in
`building.meta["grid_region"]`. `grid_region="PJM_West"` sets it by hand, and `cambium_year=2030` picks another
model year. Cambium covers the contiguous United States.

You can also give your own factors with `emission_factors=<csv>`. The file has the columns `month`,
`hour`, `AER` and `LRMER` in kg CO2e per kWh. The grid metrics are named with the year, for example
`AER_2025_annual_avg`.

Everything still runs without internet. The related metrics and panels are then left empty.

The lookups can also be called on their own.

```python
from bldgload_analysis import get_location, get_weather, get_emission_factors

get_location("Denver")                                    # latitude, longitude, timezone and state the name was matched to
get_weather("Denver", "2023-01-01", "2023-12-31")         # hourly outdoor temperature and humidity
get_emission_factors("WestConnect_North", year=2025)      # month-hour AER and LRMER of a Cambium region
```

## The example buildings

The buildings of the dataset behind the Berkeley Decarb Tool ship inside the package
(`bldgload_analysis/data`) as example buildings. The files hold the hourly loads with outdoor temperature,
humidity and grid emission factors, the building metadata, and the 43 metrics of every building.

```python
from bldgload_analysis import Building, example_buildings

example_buildings()                                         # every example building, one row each
example_buildings(building_type="Hospital", climate="3C")   # only the ones that fit
example_buildings(source="measured")                        # only measured ones, or "simulated"
building = Building.from_example(177)                       # then metrics(), report(), plot() as for any building
```

A building of your own can ask for the example buildings that are like it.

```python
building.example_buildings()                                  # same building type and same climate zone
building.example_buildings(same=["climate"])                  # same climate zone only
building.example_buildings(source="measured")                 # same type and climate, measured ones only
```

Example buildings carry loads and outdoor air only, so the water temperature and flow panels stay
empty and operating hours are the hours with a positive load. The "position in the dataset" panel compares
with the example buildings unless `reference=` names another `load_summary.csv`. `use_examples(folder)`
points at another copy of the files, and `use_examples(None)` goes back to the copy in the package.

## Figures

`outdoor_temperature`, `load_vs_temperature`, `monthly_heating`, `monthly_cooling`,
`daily_profile_winter`, `daily_profile_summer`, `hhw_temperature`, `chw_temperature`, `hhw_flow`,
`chw_flow`, `loop_delta_t`, `hhw_delta_t`, `chw_delta_t`, `grid_summer`, `grid_winter`,
`load_shifting`, `heat_recovery`, `heat_recovery_capacity`, `part_load`, `capacity_configuration`,
`dataset_position`

Each name is drawn with `ax = building.plot(name)`. A figure made this way is 4.2 x 3.2 inches and keeps its
title, labels and legend inside. Pass `ax=` to draw on an Axes of your own. The look of the figures is applied
only while they are drawn, so your own matplotlib settings stay as they are. Close figures you no longer need
with `plt.close(ax.figure)`.

## Data sources

- Outdoor weather comes from the Open-Meteo archive (https://open-meteo.com).
- Grid emission factors come from Cambium, provided by the National Laboratory of the Rockies (NLR,
  formerly NREL). Nothing from Cambium ships with this package. Its use is subject to the NLR disclaimer
  shown on the Scenario Viewer. Please cite the Cambium documentation for the release you use.
- The example buildings are the dataset behind the Berkeley Decarb Tool.

## License

Distributed under the MIT License. See the `LICENSE` file.

## Layout

```
bldgload_analysis/
  building.py     Building class, input reading, save and load
  clean.py        cleaning protocol for one loop, best year selection
  metrics.py      the 43 core metrics and their definitions
  units.py        SI and IP conversion
  figures.py      one function per figure
  report.py       one page report
  lookup.py       location, weather, Cambium grid region
  cambium.py      download of the Cambium emission factors
  examples.py     the example buildings
  data/           the files of the example buildings
example/
  run.py          a filled in template, with its building.csv
```
