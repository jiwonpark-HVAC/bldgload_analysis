# bldgload_analysis

A Python package for analyzing building heating and cooling loads. Starting with your building’s load data, the package:

- Cleans and standardizes the raw load data for analysis.
- Selects the most complete year (8,760 hours) when the data spans more than one year.
- Retrieves outdoor weather data and grid emission factors when a building location is provided, enabling analysis of load patterns in relation to weather and associated carbon emissions.
- Calculates 43 core metrics.
- Generates a one-page summary report, with options to create each figure separately.

The package also includes a mix of measured and simulated load data from 373 commercial buildings, allowing you to compare your building with similar buildings.

## Install

```
pip install git+https://github.com/jiwonpark-HVAC/bldgload_analysis.git
```

Requires Python 3.10 or later. Dependencies (pandas, numpy, matplotlib, and pyarrow) are installed automatically.

## Use

```python
from bldgload_analysis import Building

building = Building.from_csv(
    "building.csv",
    name="Hospital",                 # Sets the ID to Building_user_Hospital; None assigns a numbered ID (e.g. Building_user_1)
    floor_area=9000,
    area_unit="m2",                  # "m2" or "ft2"
    units="SI",                      # Input and output units: "SI" (W, C, L/s) or "IP" (Btu/h, F, gpm)
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
building = Building.load("Building_user_Hospital") # Load from the saved folder
```

See `example/run.py` for a complete usage example.
The metrics table contains 43 rows, including six grid-related metrics. When emission factors are unavailable, the table contains 37 rows.

## Input file

Provide a CSV file with hourly or subhourly data.

| Column | SI | IP | Required / notes |
|---|---|---|---|
| `timestamp` | local standard time | local standard time | Required |
| `hhw_load` | W | Btu/h | Heating load. Required unless supply temperature, return temperature, and flow rate are provided |
| `hhw_sup`, `hhw_ret`, `hhw_flow` | °C, °C, L/s | °F, °F, gpm | Optional when `hhw_load` is provided; otherwise, all three are required to calculate the heating load |
| `chw_load` | W | Btu/h | Cooling load. Required unless supply temperature, return temperature, and flow rate are provided |
| `chw_sup`, `chw_ret`, `chw_flow` | °C, °C, L/s | °F, °F, gpm | Optional when `chw_load` is provided; otherwise, all three are required to calculate the cooling load |
| `oat` | °C | °F | Outdoor air temperature. Optional; retrieved using the building location if not provided |
| `rh_pct` | % | % | Optional; retained in the output. Also accepts `rh` and `rh_out` as column names |

Set `units="SI"` or `"IP"` to specify the input file’s unit system. Individual columns can use a unit suffix to override this setting. Supported suffixes are `_W`, `_kW`, `_Btuh`, `_kBtuh`, `_C`, `_F`, `_Lps`, and `_gpm`, for example, `hhw_load_kW` or `oat_F`.

Column names are case-insensitive. The load columns also accept `heating` and `cooling` as alternatives to `hhw_load` and `chw_load`, respectively. Missing columns are treated as unmeasured variables. When only load data is provided, operating hours are defined as hours with a positive load.

Records shorter than one year can also be analyzed. Annual values are estimated by scaling the available data to a full year. A warning is displayed, and the report header indicates that the record covers less than one year.

## Cleaning

Before calculating the metrics, the package cleans each loop’s data. Invalid readings are treated as missing (N/A), while readings considered to represent zero are set to zero.

1. Small negative flow readings and negative flow readings while the plant is idle are set to zero. All other negative flow readings are treated as missing (N/A).
2. Temperature, flow, and measured load readings outside their plausible ranges are treated as missing (N/A).
3. Sequences of nine or more identical readings are treated as missing (N/A). This check is always applied to flow and load. For temperature, it is applied only when the sensor records increments smaller than 0.01 K. Coarser temperature readings may repeat during normal operation when the supply temperature is maintained at its setpoint.
4. Loads are calculated from flow rates and supply–return temperature differences.
5. Data are averaged to hourly values. Measured loads are used by default. If the difference between the measured and calculated loads exceeds both 20% and 2 kW, the calculated load is used instead.
6. Each hour is classified as operating or off based on supply temperature, flow rate, and load.
7. The year with the fewest missing hours is selected. Set `select_year=False` to retain the full record.

The thresholds used in these steps are defined at the top of `bldgload_analysis/clean.py`.

## Metrics

| Group | Metrics |
|---|---|
| Load Magnitude & Distribution | Annual and peak loads, load statistics, operating hours, data coverage, capacity sizing, and daily peak-to-mean load ratios. Calculated separately for each loop |
| Heating-Cooling Relationship | Annual heating to cooling energy ratio, peak heating to cooling load ratio, and fraction of hours with simultaneous heating and cooling loads |
| Condenser Heat Recovery Potential | Fraction of heating demand covered by recovered heat, unrecovered condenser heat, peak heating load reduction, and heat recovery chiller capacity |
| Outdoor Temperature & Grid Context | Design outdoor temperatures, average grid emission factors, and alignment of load patterns with grid carbon intensity |

Definitions of all metrics are provided at the top of `bldgload_analysis/metrics.py` and can also be viewed using `help(bldgload_analysis.metrics)`.

## Units

All internal calculations use SI units. Specify the floor area unit with `area_unit="m2"` or `"ft2"`.

When `units="IP"` is selected, the metrics table, `hourly.csv`, report, and figures use IP units. The metrics table uses Btu, Btu/h, and Btu/(h·ft²) for energy, load, and load per floor area, respectively. The report displays energy per floor area in kBtu/ft².

To retrieve metrics in SI units, use `building.metrics(units="SI")` or `building.metric(name, units="SI")`. The metrics table always includes a `unit` column.

## Condenser heat recovery potential

The coefficient of performance (COP) of a chiller is the cooling load divided by the compressor power. By energy balance, the condenser heat is the sum of the cooling load and the compressor power. So the condenser heat equals the cooling load multiplied by (1 + 1/COP).

The four heat recovery metrics use this condenser heat as the heat that can be recovered for heating. The default COP is 3, matching the example dataset.

Set `cop=4` in `from_csv` or `from_example` to use a different COP, or change it later with `building.cop = 4`. As a special option, `cop=0` excludes compressor power from the calculation, making condenser heat equal to the cooling load.

The comparison panel uses all example buildings by default. To compare only with selected buildings, pass the result of `building.example_buildings(...)` or a list of example building IDs through `reference=`. When the COP is changed, the heat recovery comparisons use the same COP for your building and the selected example buildings.

## Weather data and grid emission factors

Provide `city`, or `latitude`, `longitude`, and `timezone`, to retrieve weather data and grid emission factors when they are not supplied.

If the input file does not include outdoor air temperature, the package retrieves hourly outdoor air temperature and relative humidity for the record’s date range from the Open-Meteo archive. Timestamps are converted to local standard time.

You can provide your own emission factors with `emission_factors="factors.csv"`. The CSV must contain `month`, `hour`, `AER`, and `LRMER` columns, with emission factors expressed in kg CO₂e/kWh. Grid metric names include the year, for example, `AER_2025_annual_avg`.

If `emission_factors` are not provided, the package identifies the Cambium grid region (GEA) using a city lookup, with a state-level lookup as a fallback. Both lookups are based on NLR’s ZIP code-to-GEA mapping.

Monthly hourly profiles of average emission rates (AER) and long-run marginal emission rates (LRMER) are downloaded from the NLR Scenario Viewer (https://scenarioviewer.nlr.gov) and cached in `~/.bldgload_analysis`. The initial download is approximately 27 MB.

The state-level lookup is approximate for states that span multiple grid regions. Check the selected region using `building.meta["grid_region"]`, or specify it directly with `grid_region="PJM_West"`. Use `cambium_year=2030` to select a different model year. Cambium data cover the contiguous United States.

The package can also run without an internet connection. If weather data or emission factors are unavailable, the corresponding metrics and report panels are left empty.

You can also retrieve location, weather, and grid emission data without creating a `Building` object.

```python
from bldgload_analysis import get_location, get_weather, get_emission_factors

get_location("Denver")                               # Latitude, longitude, timezone, and state
get_weather("Denver", "2023-01-01", "2023-12-31")      # Hourly outdoor air temperature and relative humidity
get_emission_factors("WestConnect_North", year=2025)   # Monthly hourly AER and LRMER profiles
```

## Example buildings

The package includes measured and simulated load data from 373 commercial buildings in `bldgload_analysis/data`. This dataset is also used by the Berkeley Decarb Tool.

The files contain hourly loads, outdoor air conditions, building metadata, and calculated metrics for each building.

```python
from bldgload_analysis import Building, example_buildings, use_examples

example_buildings()                                        # List all example buildings
example_buildings(building_type="Hospital", climate="3C")   # Filter by building type and climate zone
example_buildings(source="measured")                       # List measured buildings only
building = Building.from_example(177)                      # Load an example building
```

Use `metrics()`, `report()`, and `plot()` on the loaded building in the same way as for your own building.

Find example buildings with characteristics matching your building:

```python
building.example_buildings()                   # Same building type and climate zone
building.example_buildings(same=["climate"])    # Same climate zone only
building.example_buildings(source="measured")  # Same type and climate zone, measured data only
```

Pass the selected buildings through `reference=` to use them in the report’s comparison panel. If no selection is provided, the panel compares your building with all example buildings.

```python
reference = building.example_buildings()
building.report("report.pdf", reference=reference)
```

Example buildings do not include water temperature or flow data, so the corresponding report panels are left empty. Operating hours are defined as hours with a positive load.

Use `use_examples(folder)` to load the example dataset from another folder, or `use_examples(None)` to return to the dataset included in the package.

## Figures

`outdoor_temperature`, `load_vs_temperature`, `monthly_heating`, `monthly_cooling`,
`daily_profile_winter`, `daily_profile_summer`, `hhw_temperature`, `chw_temperature`, `hhw_flow`,
`chw_flow`, `loop_delta_t`, `hhw_delta_t`, `chw_delta_t`, `grid_summer`, `grid_winter`,
`load_shifting`, `heat_recovery`, `heat_recovery_capacity`, `part_load`, `capacity_configuration`,
`dataset_position`

Create a figure with `ax = building.plot(name)`, where `name` is one of the figure names listed above. Each figure is 4.2 × 3.2 inches, with the title, axis labels, and legend contained within the figure.

Pass `ax=` to plot on an existing matplotlib Axes. The package applies its plotting style only while drawing, preserving your existing matplotlib settings.

Close figures you no longer need with `plt.close(ax.figure)`.

## Data sources

- Weather data are retrieved from the [Open-Meteo archive](https://open-meteo.com).
- Grid emission factors retrieved automatically by the package come from Cambium through the [NLR Scenario Viewer](https://scenarioviewer.nlr.gov). Refer to the disclaimer on the Scenario Viewer and cite the Cambium documentation for the release you use.
- The example building dataset contains measured and simulated load data and is also used by the Berkeley Decarb Tool.

## License

Distributed under the MIT License. See the `LICENSE` file.

## Project structure

```text
bldgload_analysis/
    building.py     Building class, input handling, saving, and loading
    clean.py        Data cleaning and most complete year selection
    metrics.py      Calculation and definitions of the 43 core metrics
    units.py        SI and IP unit conversion
    figures.py      Individual plotting functions
    report.py       One-page summary report generation
    lookup.py       Location, weather, and grid region lookups
    cambium.py      Cambium emission factor downloads
    examples.py     Example building access and filtering
    data/           Example building datasets

example/
    run.py          Complete usage example
    building.csv    Example input data
    emission_factors.csv    Example emission factor input
```
