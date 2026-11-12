"""Download NLR Cambium data on request.

Nothing from Cambium ships with this package. The data is fetched from the
NLR Scenario Viewer when it is needed, and only the CSV that is needed is
read from the remote zip.

month_hour gives the month-hour emission factors of one GEA region, as NLR
publishes them. download_cambium gives one hourly file.

The Scenario Viewer API is not officially documented. If it changes, give
your own factors with emission_factors=<csv> in Building.from_csv.
"""

import io
import json
import pathlib
import re
import urllib.parse
import urllib.request
import zipfile

import pandas as pd

Base = "https://scenarioviewer.nlr.gov/api"
Timeout = 120
Cache_dir = pathlib.Path.home() / ".bldgload_analysis" / "cambium"
Notice = (
    "Cambium data is provided by the National Laboratory of the Rockies (NLR, "
    "formerly NREL) and is downloaded from https://scenarioviewer.nlr.gov. "
    "Its use is subject to the NLR disclaimer shown on that site. "
    "Please cite the Cambium documentation for the release you use."
)
# word that marks each kind of region in the location_type field of the file list
Location_words = {"ba": "balancing", "gea": "gea"}


def _get_json(path, fields=None):
    body = urllib.parse.urlencode(fields).encode() if fields else None
    with urllib.request.urlopen(f"{Base}/{path}/", data=body, timeout=Timeout) as r:
        return json.load(r)


def _project_uuid(release):
    name = f"Cambium {release}"
    for p in _get_json("projects"):
        if p["name"] == name:
            return p["uuid"]
    raise ValueError(f"No project named '{name}' on the Scenario Viewer.")


def _download_url(uuid, file_id):
    """The API answers with a redirect to a short-lived download address."""
    body = urllib.parse.urlencode({"project_uuid": uuid, "file_ids": file_id}).encode()
    with urllib.request.urlopen(f"{Base}/download/", data=body, timeout=Timeout) as r:
        return r.geturl()


def list_cambium_files(release=2024):
    """Return the files of one Cambium release as a DataFrame."""
    files = _get_json("file-list", {"project_uuid": _project_uuid(release)})["files"]
    return pd.DataFrame(files)


class _RemoteFile(io.RawIOBase):
    """Read-only file object that fetches byte ranges over HTTP."""

    def __init__(self, url):
        self.url = url
        self.pos = 0
        with self._open(0, 0) as r:
            self.size = int(r.headers["Content-Range"].split("/")[1])

    def _open(self, start, end):
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={start}-{end}"})
        return urllib.request.urlopen(req, timeout=Timeout)

    def seekable(self):
        return True

    def readable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        if whence == 0:
            self.pos = offset
        elif whence == 1:
            self.pos += offset
        else:
            self.pos = self.size + offset
        return self.pos

    def readinto(self, b):
        if self.pos >= self.size:
            return 0
        end = min(self.pos + len(b), self.size) - 1
        with self._open(self.pos, end) as r:
            data = r.read()
        b[: len(data)] = data
        self.pos += len(data)
        return len(data)


def _open_zip(release, scenario, location, resolution):
    """Open the remote zip of one scenario. resolution is a word in time_resolution, 'hourly' or 'month'."""
    uuid = _project_uuid(release)
    files = _get_json("file-list", {"project_uuid": uuid})["files"]
    kind = [f for f in files if Location_words[location] in f["location_type"].lower()]
    here = [f for f in kind if f["time_resolution"].lower().startswith(resolution)]
    if not here:
        found = sorted({(f["location_type"], f["time_resolution"]) for f in files})
        raise LookupError(f"No '{resolution}' files for location='{location}'. On the Scenario Viewer: {found}")
    match = [f for f in here if f["scenario"].lower() == scenario.lower()]
    match = match or [f for f in here if f["scenario"] == "ALL"]      # one zip that holds every scenario
    if not match:
        names = sorted({f["scenario"] for f in here})
        raise ValueError(f"Unknown scenario '{scenario}'. Available: {names}")
    url = _download_url(uuid, match[0]["id"])
    return zipfile.ZipFile(io.BufferedReader(_RemoteFile(url), buffer_size=1024 * 1024))


def download_cambium(region, year, scenario="Mid-case", release=2024, location="ba", cache_dir=None, quiet=False):
    """Download one hourly CSV and return its local path.

    region    ReEDS balancing area, for example "p100", or a GEA region, for example "CAISO"
    year      model year in the file name, for example 2025
    scenario  scenario name as shown on the Scenario Viewer, for example "Mid-case"
    release   Cambium release year
    location  "ba" when region is a balancing area, "gea" when it is a GEA region

    The file is kept in cache_dir, so a second call does not download again.
    """
    if location not in Location_words:
        raise ValueError("location must be 'ba' or 'gea'")
    cache = pathlib.Path(cache_dir) if cache_dir else Cache_dir
    folder = cache / str(release) / scenario.replace(" ", "_")
    suffix = f"_hourly_{region}_{year}.csv"
    found = sorted(folder.glob(f"*{suffix}"))
    if found:
        return found[0]

    with _open_zip(release, scenario, location, "hourly") as zf:
        members = [n for n in zf.namelist() if n.endswith(suffix)]
        if not members:
            raise ValueError(
                f"No file for region='{region}', year={year} in scenario '{scenario}'. "
                "Check the region name and the model year."
            )
        data = zf.read(members[0])

    folder.mkdir(parents=True, exist_ok=True)
    target = folder / pathlib.PurePosixPath(members[0]).name
    target.write_bytes(data)
    if not quiet:
        print(Notice)
    return target


def read_cambium_csv(path):
    """Read a Cambium hourly CSV, downloaded here or by hand.

    The first five lines hold metadata, categories and units. Line six holds
    the column names.
    """
    df = pd.read_csv(path, skiprows=5)
    for col in ("timestamp", "timestamp_local"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def load_cambium(region, year, scenario="Mid-case", release=2024, location="ba", cache_dir=None, quiet=False):
    """Download if needed, then return the hourly table as a DataFrame."""
    path = download_cambium(region, year, scenario, release, location, cache_dir, quiet)
    return read_cambium_csv(path)


# ------------------------------------------------------------------ month-hour emission factors
def _pick(cols, patterns):
    for p in patterns:
        hit = [c for c in cols if re.search(p, c)]
        if hit:
            return hit[0]
    return None


def _tidy_month_hour(zf, member, gea=None, year=None, scenario=None):
    """One Cambium month-hour CSV as gea, scenario, year, month, hour, aer, lrmer in kg CO2e per kWh.

    The column names sit below a few lines of metadata. A file made for one region, year or scenario
    may leave that column out, then the value asked for is used. Only the columns needed are read.
    """
    with zf.open(member) as f:
        head, cols = None, []
        for i in range(200):
            line = f.readline().decode("utf-8", errors="ignore")
            if re.search(r'(^|,)\s*"?(hour|local_hour)"?\s*(,|$)', line.lower()):
                head, cols = i, [c.strip().strip('"') for c in line.rstrip("\r\n").split(",")]
                break
    if head is None:
        raise ValueError(f"no column names found in {member}")
    low = [c.lower() for c in cols]
    want = {"gea": ([r"^gea$", r"^gea_region$", "gea"], gea), "scenario": ([r"^scenario$", "scenario"], scenario),
            "year": ([r"^year$", r"^t$", r"^projection_year$"], year), "month": ([r"^month$", r"^local_month$"], None),
            "hour": ([r"^hour$", r"^local_hour$"], None),
            "aer": ([r"^aer_load_co2e$", r"^aer_load_co2e_kg", r"^aer_co2e$", r"^aer_load_co2e"], None),
            "lrmer": ([r"^lrmer_co2e$", r"^lrmer_co2e_kg", r"^lrmer_co2e"], None)}
    picked = {name: _pick(low, patterns) for name, (patterns, _) in want.items()}
    for name, (_, fill) in want.items():
        if picked[name] is None and fill is None:
            raise ValueError(f"{member} has no {name} column, columns: {', '.join(cols[:40])}")
    use = [cols[low.index(c)] for c in picked.values() if c is not None]
    with zf.open(member) as f:
        raw = pd.read_csv(f, skiprows=head, usecols=use)
    raw.columns = [c.strip().lower() for c in raw.columns]
    t = pd.DataFrame(index=raw.index)
    for name, (_, fill) in want.items():
        t[name] = raw[picked[name]] if picked[name] is not None else fill
    for name in ("year", "month", "hour", "aer", "lrmer"):
        t[name] = pd.to_numeric(t[name], errors="coerce")
    t["gea"], t["scenario"] = t["gea"].astype(str), t["scenario"].astype(str)
    if t["hour"].min() == 1 and t["hour"].max() == 24:
        t["hour"] -= 1
    if t["aer"].median() > 5:          # kg per MWh in the file
        t[["aer", "lrmer"]] /= 1000
    return t


def _key(name):
    return re.sub(r"[^a-z0-9]", "", str(name).lower())


def month_hour(gea, year, scenario="Mid-case", release=2024, cache_dir=None, quiet=False):
    """Month-hour AER and LRMER of one GEA region in kg CO2e per kWh, from the month-hour file NLR publishes.

    Returns month (1 to 12), hour (0 to 23), aer, lrmer. The Scenario Viewer has one month-hour zip for
    all GEA regions, years and scenarios (about 27 MB). It is downloaded once and its table is kept in
    cache_dir, so later calls do not download again.
    """
    cache = pathlib.Path(cache_dir) if cache_dir else Cache_dir
    saved = cache / str(release) / "month_hour_gea.csv"
    if saved.exists():
        t = pd.read_csv(saved)
    else:
        with _open_zip(release, scenario, "gea", "month") as zf:
            members = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not members:
                raise ValueError("No CSV in the month-hour download.")
            t = pd.concat([_tidy_month_hour(zf, n, gea, year, scenario) for n in members], ignore_index=True)
        saved.parent.mkdir(parents=True, exist_ok=True)
        t.to_csv(saved, index=False)
        if not quiet:
            print(Notice)
    rows = t[(t["gea"].astype(str) == str(gea)) & (t["year"] == year)]
    rows = rows[rows["scenario"].map(_key) == _key(scenario)]
    if rows.empty:
        raise ValueError(f"No Cambium rows for gea='{gea}', year={year}, scenario='{scenario}'. "
                         f"Regions: {sorted(t['gea'].astype(str).unique())}. "
                         f"Years: {sorted(int(y) for y in t['year'].dropna().unique())}. "
                         f"Scenarios: {sorted(t['scenario'].astype(str).unique())}")
    return rows.groupby(["month", "hour"], as_index=False)[["aer", "lrmer"]].mean()
