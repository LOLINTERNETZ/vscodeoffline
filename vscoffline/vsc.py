import datetime
import hashlib
import json
import os
import pathlib
from enum import IntFlag
from typing import Any, Dict, List, Union
import logging as log

PLATFORMS = ["win32", "linux", "linux-deb", "linux-rpm", "darwin", "linux-snap", "server-linux", "server-linux-legacy", "cli-alpine"]
ARCHITECTURES = ["", "x64"]
BUILDTYPES = ["", "archive", "user"]
QUALITIES = ["stable", "insider"]

URL_BINUPDATES = r"https://update.code.visualstudio.com/api/update/"
URL_RECOMMENDATIONS = r"https://az764295.vo.msecnd.net/extensions/workspaceRecommendations.json.gz"
URL_MARKETPLACEQUERY = r"https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery"
URL_MALICIOUS = r"https://az764295.vo.msecnd.net/extensions/marketplace.json"

URLROOT = "https://update.code.visualstudio.com"
ARTIFACTS = "/artifacts/"
ARTIFACTS_INSTALLERS = "/artifacts/installers"
ARTIFACTS_EXTENSIONS = "/artifacts/extensions"
ARTIFACT_RECOMMENDATION = "/artifacts/recommendations.json"
ARTIFACT_MALICIOUS = "/artifacts/malicious.json"

TIMEOUT = 12


class QueryFlags(IntFlag):
    __no_flags_name__ = "NoneDefined"
    NoneDefined = 0x0
    IncludeVersions = 0x1
    IncludeFiles = 0x2
    IncludeCategoryAndTags = 0x4
    IncludeSharedAccounts = 0x8
    IncludeVersionProperties = 0x10
    ExcludeNonValidated = 0x20
    IncludeInstallationTargets = 0x40
    IncludeAssetUri = 0x80
    IncludeStatistics = 0x100
    IncludeLatestVersionOnly = 0x200
    Unpublished = 0x1000


class FilterType(IntFlag):
    __no_flags_name__ = "Target"
    Tag = 1
    ExtensionId = 4
    Category = 5
    ExtensionName = 7
    Target = 8
    Featured = 9
    SearchText = 10
    ExcludeWithFlags = 12
    UndefinedType = 14


class SortBy(IntFlag):
    __no_flags_name__ = "NoneOrRelevance"
    NoneOrRelevance = 0
    LastUpdatedDate = 1
    Title = 2
    PublisherName = 3
    InstallCount = 4
    PublishedDate = 5
    AverageRating = 6
    WeightedRating = 12


class SortOrder(IntFlag):
    __no_flags_name__ = "Default"
    Default = 0
    Ascending = 1
    Descending = 2


class MagicJsonEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Union[str, Dict[str, Any]]:
        try:
            return super().default(o)
        except TypeError as err:
            # could be datetime
            if isinstance(o, datetime.datetime):
                return o.isoformat()
            # could also be cls with slots
            try:
                return {key: getattr(o, key, None) for key in o.__slots__}
            except AttributeError:
                pass
            # finally, should have a dict if it is a dataclass or another cls
            try:
                return o.__dict__
            except AttributeError:
                raise TypeError(
                    "Can't encode object. Tried isoformat of datetime, class slots and class dict"
                ) from err


class Utility:
    """
    Utility tool
    """

    @staticmethod
    def hash_file_and_check(filepath: Union[str, pathlib.Path], expectedchecksum: str) -> bool:
        """
        Hashes a file and checks for the expected checksum.
        Checksum is sha256 default implementation.
        """
        h = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                h.update(chunk)
        return expectedchecksum == h.hexdigest()

    @staticmethod
    def load_json(filepath: Union[str, pathlib.Path]) -> Union[List[Any], Dict[str, Any]]:
        if isinstance(filepath, str):
            filepath: pathlib.Path = pathlib.Path(filepath)

        result = []
        if not filepath.exists():
            log.debug(f"Unable to load json from {filepath.absolute()}. Does not exist.")
            return result
        elif filepath.is_dir():
            log.debug(f"Cannot load json at path {filepath.absolute()}. It is a directory")
            return result

        with open(filepath, "r", encoding="utf-8-sig") as fp:
            try:
                result = json.load(fp)
                if not result:
                    return []
            except json.decoder.JSONDecodeError as err:
                log.debug(f"JSONDecodeError while processing {filepath.absolute()} \n error: {str(err)}")
                return []
        return result

    @staticmethod
    def write_json(filepath: Union[str, pathlib.Path], content: Dict[str, Any]) -> None:
        with open(filepath, "w") as outfile:
            json.dump(content, outfile, cls=MagicJsonEncoder, indent=4)

    @staticmethod
    def first_file(filepath: Union[str, pathlib.Path], pattern: str, reverse: bool = False) -> Union[str, bool]:
        if isinstance(filepath, str):
            filepath = pathlib.Path(filepath)
        results = [*filepath.glob(pattern)]
        if not results:
            return False
        elif len(results) >= 1 and reverse:
            results.sort(reverse=True)
        return str(results[0].absolute())

    @staticmethod
    def folders_in_folder(filepath: str) -> List[str]:
        listing = [f for f in os.listdir(filepath) if os.path.isdir(os.path.join(filepath, f))]
        listing.sort()
        return listing

    @staticmethod
    def files_in_folder(filepath: str) -> List[str]:
        listing = [f for f in os.listdir(filepath) if os.path.isfile(os.path.join(filepath, f))]
        listing.sort()
        return listing


    @staticmethod
    def seconds_to_human_time(seconds: int) -> str:
        return str(datetime.timedelta(seconds=seconds))

    @staticmethod
    def from_json_datetime(jsondate: str) -> datetime.datetime:
        return datetime.datetime.strptime(jsondate, "%Y-%m-%dT%H:%M:%S.%fZ")

    @staticmethod
    def validate_platform(platform: str) -> bool:
        return platform in PLATFORMS

    @staticmethod
    def validate_architecture(arch: str) -> bool:
        return arch in ARCHITECTURES

    @staticmethod
    def validate_buildtype(buildtype: str) -> bool:
        return buildtype in BUILDTYPES

    @staticmethod
    def validate_quality(quality: str) -> bool:
        return quality in QUALITIES
