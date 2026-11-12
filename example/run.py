# Fill in the building information here, then run top to bottom from this folder.
import matplotlib.pyplot as plt

from bldgload_analysis import Building

building = Building.from_csv(
    "building.csv",
    name="Hospital",                 # reported as Building_user_Hospital. None gives Building_user_1, _2, ...
    floor_area=9000,
    area_unit="m2",                  # "m2" or "ft2"
    units="SI",                      # "SI" (W, C, L/s) or "IP" (Btu/h, F, gpm) for the file, outputs follow
    building_type="Hospital",
    city="San Francisco",
    climate="3C",
    construction_year=2015,
    source="simulated",              # "measured" or "simulated"
    # With a city, missing outdoor temperature is taken from Open-Meteo and the emission factors
    # of the city's Cambium grid region from the NLR Scenario Viewer.
    # emission_factors="emission_factors.csv",   # your own month-hour factors instead
    # cop=0,                                     # heat recovery without the compressor work, the default COP is 3
)

print(building)
print(building.metrics())                               # the 43 metrics as a DataFrame
print(building.metric("heat_recovery_heating_fraction"))   # one value

folder = building.save()                                # Building_user_Hospital/hourly.csv, metrics.csv, meta.json
building.report(folder / "report.pdf")                  # one page, compared with the example buildings

print(building.figures)                                 # names accepted by plot()
ax = building.plot("load_vs_temperature")
ax.figure.savefig(folder / "load_vs_temperature.png", dpi=200)
plt.close(ax.figure)
