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
    source="measured",               # "measured" or "simulated"
    # Outdoor air temperature: taken from the "oat_C" column. Without it, downloaded from Open-Meteo for the city.
    # Emission factors: leave this out and they are downloaded for the city's Cambium grid region (NLR Scenario Viewer).
    # emission_factors="emission_factors.csv",   # or give your own month-hour factors
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
