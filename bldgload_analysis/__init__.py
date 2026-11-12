"""bldgload_analysis: heating and cooling load metrics, a one page report and figures for a building with hydronic HVAC.

Building reads and cleans one building. example_buildings() and Building.from_example() give the example buildings that ship with the package.
"""
from importlib.metadata import PackageNotFoundError, version

from .building import Building
from .examples import example_buildings, use_examples
from .lookup import get_emission_factors, get_location, get_weather

__all__ = [
    "Building",
    "example_buildings",
    "use_examples",
    "get_emission_factors",
    "get_location",
    "get_weather",
]

try:
    __version__ = version("bldgload_analysis")      # the version in pyproject.toml
except PackageNotFoundError:                        # run from a folder that was not installed
    __version__ = "0+unknown"
