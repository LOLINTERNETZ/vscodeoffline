import os
import io
import json
import hashlib
import glob
import datetime
from enum import IntFlag
from logzero import logger as log

PLATFORMS = ['win32', 'linux', 'linux-deb', 'linux-rpm',
             'darwin', 'linux-snap', 'server-linux']
ARCHITECTURES = ['', 'x64']
BUILDTYPES = ['', 'archive', 'user']
QUALITIES = ['stable', 'insider']

URL_BINUPDATES = r'https://update.code.visualstudio.com/api/update/'
URL_RECOMMENDATIONS = r'https://az764295.vo.msecnd.net/extensions/workspaceRecommendations.json.gz'
URL_MARKETPLACEQUERY = r'https://marketplace.visualstudio.com/_apis/public/gallery/extensionquery'
URL_MALICIOUS = r'https://az764295.vo.msecnd.net/extensions/marketplace.json'

URLROOT = 'https://update.code.visualstudio.com'
ARTIFACTS = '/artifacts/'
ARTIFACTS_INSTALLERS = '/artifacts/installers'
ARTIFACTS_EXTENSIONS = '/artifacts/extensions'
ARTIFACT_RECOMMENDATION = '/artifacts/recommendations.json'
ARTIFACT_MALICIOUS = '/artifacts/malicious.json'

TIMEOUT = 12


class QueryFlags(IntFlag):
    __no_flags_name__ = 'NoneDefined'
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
    __no_flags_name__ = 'Target'
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
    __no_flags_name__ = 'NoneOrRelevance'
    NoneOrRelevance = 0
    LastUpdatedDate = 1
    Title = 2
    PublisherName = 3
    InstallCount = 4
    PublishedDate = 5
    AverageRating = 6
    WeightedRating = 12


class SortOrder(IntFlag):
    __no_flags_name__ = 'Default'
    Default = 0
    Ascending = 1
    Descending = 2


class MagicJsonEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime.datetime):
            return o.isoformat()
        return o.__dict__


class Utility(object):
    """
    Utility tool
    """

    @staticmethod
    def hash_file_and_check(filepath, expectedchecksum):
        """
        Hashes a file and checks for the expected checksum
        """
        h = hashlib.sha256()
        with open(filepath, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b''):
                h.update(chunk)
        if expectedchecksum != h.hexdigest():
            return False

        return True

    @staticmethod
    def load_json(filepath):
        result = []
        if not os.path.exists(filepath):
            log.debug(f'Unable to load json from {filepath}')
            return []
        with io.open(filepath, 'r', encoding='utf-8-sig') as fp:
            try:
                result = json.load(fp)
                if not result:
                    return []
            except json.decoder.JSONDecodeError:
                log.debug(f'JSONDecodeError while processing {filepath}')
                return []
        return result

    @staticmethod
    def write_json(filepath, content):
        with open(filepath, 'w') as outfile:
            json.dump(content, outfile, cls=MagicJsonEncoder, indent=4)

    @staticmethod
    def first_file(filepath, reverse=False):
        results = glob.glob(filepath)
        if reverse:
            results.sort(reverse=True)
        # log.info(filepath)
        if results and len(results) >= 1:
            return results[0]
        return False

    @staticmethod
    def folders_in_folder(filepath):
        return [f for f in os.listdir(filepath) if os.path.isdir(os.path.join(filepath, f))]

    @staticmethod
    def files_in_folder(filepath):
        return [f for f in os.listdir(filepath) if os.path.isfile(os.path.join(filepath, f))]

    @staticmethod
    def seconds_to_human_time(seconds):
        return str(datetime.timedelta(seconds=seconds))

    @staticmethod
    def from_json_datetime(jsondate):
        datetime.datetime.strptime(jsondate, '%Y-%m-%dT%H:%M:%S.%fZ')

    @staticmethod
    def validate_platform(platform):
        if platform in PLATFORMS:
            return True
        else:
            return False

    @staticmethod
    def validate_architecture(arch):
        if arch in ARCHITECTURES:
            return True
        else:
            return False

    @staticmethod
    def validate_buildtype(buildtype):
        if buildtype in BUILDTYPES:
            return True
        else:
            return False

    @staticmethod
    def validate_quality(quality):
        if quality in QUALITIES:
            return True
        else:
            return False
