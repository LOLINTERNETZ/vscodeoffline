from dataclasses import dataclass
import glob
import os
import sys
import re
import argparse
import requests
import pathlib
import uuid
import logging
import json
import time
import datetime
from typing import List
from platform import release
import logging as log
from pytimeparse.timeparse import timeparse
import vsc
from distutils.dir_util import create_tree
from requests.adapters import HTTPAdapter, Retry
from packaging.version import Version


class VSCUpdateDefinition(object):

    def __init__(self, platform=None, architecture=None, buildtype=None, quality=None,
                 updateurl=None, name=None, version=None, productVersion=None,
                 hashs=None, timestamp=None, sha256hash=None, supportsFastUpdate=None):

        if not vsc.Utility.validate_platform(platform):
            raise ValueError(f"Platform {platform} invalid or not implemented")

        if not vsc.Utility.validate_architecture(architecture):
            raise ValueError(
                f"Architecture {architecture} invalid or not implemented")

        if not vsc.Utility.validate_buildtype(buildtype):
            raise ValueError(
                f"Buildtype {buildtype} invalid or not implemented")

        if not vsc.Utility.validate_quality(quality):
            raise ValueError(f"Quality {quality} invalid or not implemented")

        self.identity = platform

        if architecture:
            self.identity += f'-{architecture}'
        if buildtype:
            self.identity += f'-{buildtype}'

        self.platform = platform
        self.architecture = architecture
        self.buildtype = buildtype
        self.quality = quality
        self.updateurl = updateurl
        self.name = name
        self.version = version
        self.productVersion = productVersion
        self.hash = hashs
        self.timestamp = timestamp
        self.sha256hash = sha256hash
        self.supportsFastUpdate = supportsFastUpdate
        self.checkedForUpdate = False

    def check_for_update(self, old_commit_id=None):
        if not old_commit_id:
            # To trigger the API to delta
            old_commit_id = '7c4205b5c6e52a53b81c69d2b2dc8a627abaa0ba'

        url = vsc.URL_BINUPDATES + \
            f"{self.identity}/{self.quality}/{old_commit_id}"

        log.debug(f'Update url {url}')
        result = requests.get(url, allow_redirects=True, timeout=vsc.TIMEOUT)
        self.checkedForUpdate = True

        if result.status_code == 204:
            # No update available
            return False
        elif result.status_code != 200:
            # Unhandled response from API
            log.warning(
                f"Update url failed {url}. Unhandled status code {result.status_code}")
            return False

        jresult = result.json()

        self.updateurl = jresult['url']
        self.name = jresult['name']
        self.version = jresult['version']
        self.productVersion = jresult['productVersion']
        self.hash = jresult['hash']
        self.timestamp = jresult['timestamp']
        self.sha256hash = jresult['sha256hash']

        if 'supportsFastUpdate' in jresult:
            self.supportsFastUpdate = jresult['supportsFastUpdate']
        if self.updateurl:
            return True
        else:
            return False

    def download_update(self, destination):
        if not self.checkedForUpdate:
            log.warning(
                'Cannot download update if the update definition has not been downloaded')
            return
        if not self.updateurl:
            log.warning(
                'Cannot download update if there is no url to download from')
            return

        destination = os.path.join(destination, self.identity, self.quality)
        if not os.path.isdir(destination):
            os.makedirs(destination)
        suffix = pathlib.Path(self.updateurl).suffix
        if '.gz' in suffix:
            suffix = ''.join(pathlib.Path(self.updateurl).suffixes)
        destfile = os.path.join(destination, f'vscode-{self.name}{suffix}')

        if os.path.exists(destfile) and vsc.Utility.hash_file_and_check(destfile, self.sha256hash):
            log.debug(f'Previously downloaded {self}')
        else:
            log.info(f'Downloading {self} to {destfile}')
            result = requests.get(
                self.updateurl, allow_redirects=True, timeout=vsc.TIMEOUT)
            open(destfile, 'wb').write(result.content)

            if not vsc.Utility.hash_file_and_check(destfile, self.sha256hash):
                log.warning(
                    f'HASH MISMATCH for {self} at {destfile} expected {self.sha256hash}. Removing local file.')
                os.remove(destfile)
                return False
            log.debug(f'Hash ok for {self} with {self.sha256hash}')
        return True

    def save_state(self, destination):
        destination = os.path.join(destination, self.identity)
        if not os.path.isdir(destination):
            os.makedirs(destination)
        # Write version details blob as latest
        vsc.Utility.write_json(os.path.join(
            destination, self.quality, 'latest.json'), self)
        # Write version details blob as the commit id
        if self.version:
            vsc.Utility.write_json(os.path.join(
                destination, self.quality, f'{self.version}.json'), self)

    def __repr__(self):
        strs = f"<{self.__class__.__name__}> {self.quality}/{self.identity}"
        if self.updateurl:
            strs += f" - Version: {self.name} ({self.version})"
        elif self.checkedForUpdate:
            strs += f" - Latest version not available"
        return strs


@dataclass
class File:
    assetType: str
    source: str

    @staticmethod
    def from_dict(obj) -> 'File':
        _assetType = str(obj.get("assetType"))
        _source = str(obj.get("source"))
        return File(_assetType, _source)


@dataclass
class Property:
    key: str
    value: str

    @staticmethod
    def from_dict(obj) -> 'Property':
        _key = str(obj.get("key"))
        _value = str(obj.get("value"))
        return Property(_key, _value)


@dataclass
class VSCExtensionVersionDefinition:

    version: str
    flags: str
    lastUpdated: str
    files: List[File]
    properties: List[Property]
    assetUri: str
    fallbackAssetUri: str

    @staticmethod
    def from_dict(obj) -> 'VSCExtensionVersionDefinition':
        _version = str(obj.get("version"))
        _flags = str(obj.get("flags"))
        _lastUpdated = str(obj.get("lastUpdated"))
        _files = [File.from_dict(y) for y in obj.get("files")]
        _properties = [Property.from_dict(y) for y in obj.get("properties")] if obj.get(
            "properties") else []  # older versions do not have properties so we need to set to empty array
        _assetUri = str(obj.get("assetUri"))
        _fallbackAssetUri = str(obj.get("fallbackAssetUri"))
        return VSCExtensionVersionDefinition(_version, _flags, _lastUpdated, _files, _properties, _assetUri, _fallbackAssetUri)

    def isprerelease(self):
        prerelease = False
        for property in self.properties:
            # if property["key"] == "Microsoft.VisualStudio.Code.PreRelease" and property["value"] == "true":
            if property.key == "Microsoft.VisualStudio.Code.PreRelease" and property.value == "true":
                prerelease = True
        return prerelease

    def __repr__(self):
        strs = f"<{self.__class__.__name__}> {self.version} ({self.lastUpdate}) - Version: {self.version}"
        return strs


class VSCExtensionDefinition(object):

    def __init__(self, identity, raw=None):
        self.identity = identity
        self.extensionId = None
        self.recommended = False
        self.versions: List[VSCExtensionVersionDefinition] = []
        if raw:
            self.__dict__.update(raw)
            if 'extensionId' in raw:
                self.extensionId = raw['extensionId']

    def download_assets(self, destination, session):
        for version in self.versions:
            targetplatform = ''
            if "targetPlatform" in version:
                targetplatform = version["targetPlatform"]
            ver_destination = os.path.join(
                destination, self.identity, version["version"], targetplatform)
            for file in version["files"]:
                url = file["source"]
                if not url:
                    log.warning(
                        'download_asset() cannot download update as asset url is missing')
                    return
                asset = file["assetType"]
                destfile = os.path.join(ver_destination, f'{asset}')
                create_tree(os.path.abspath(os.sep), (destfile,))
                if not os.path.exists(destfile):
                    for i in range(5):
                        try:
                            if i == 0:
                                log.debug(f'Downloading {self.identity} {asset} to {destfile}')
                            else:
                                log.info(f'Retrying {i+1}, download {self.identity} {asset} to {destfile}')
                            result = session.get(
                                url, allow_redirects=True, timeout=vsc.TIMEOUT)
                            with open(destfile, 'wb') as dest:
                                dest.write(result.content)
                            break
                        except requests.exceptions.ProxyError:
                            log.info("ProxyError: Retrying.")
                        except requests.exceptions.ReadTimeout:
                            log.info("ReadTimeout: Retrying.")

    def process_embedded_extensions(self, destination, mp):
        """
        Check an extension's Manifest for an extension pack (e.g. more extensions to download)
        """
        bonusextensions = []
        for version in self.versions:
            targetplatform = ''
            if "targetPlatform" in version:
                targetplatform = version["targetPlatform"]
            manifestpath = os.path.join(
                destination, self.identity, version["version"], targetplatform, 'Microsoft.VisualStudio.Code.Manifest')
            manifest = vsc.Utility.load_json(manifestpath)
            if manifest and 'extensionPack' in manifest:
                for extname in manifest['extensionPack']:
                    bonusextension = mp.search_by_extension_name(extname)
                    if bonusextension:
                        bonusextensions.append(bonusextension)
        return bonusextensions

    def save_state(self, destination):
        destination = os.path.join(destination, self.identity)
        if not os.path.isdir(destination):
            os.makedirs(destination)
        # Save as latest
        with open(os.path.join(destination, 'latest.json'), 'w') as outfile:
            json.dump(self, outfile, cls=vsc.MagicJsonEncoder, indent=4)
        # Save in the version folder
        for version in self.versions:
            with open(os.path.join(destination, version["version"], 'extension.json'), 'w') as outfile:
                json.dump(self, outfile, cls=vsc.MagicJsonEncoder, indent=4)

    def isprerelease(self):
        prerelease = False
        if "properties" in self.versions[0].keys():
            for property in self.versions[0]["properties"]:
                if property["key"] == "Microsoft.VisualStudio.Code.PreRelease" and property["value"] == "true":
                    prerelease = True
        return prerelease

    def get_latest_release_versions(self):
        if self.versions and len(self.versions) > 1:
            releaseVersions = list(filter(lambda x: VSCExtensionVersionDefinition.from_dict(
                x).isprerelease() == False, self.versions))
            if(len(releaseVersions) > 0):
                releaseVersions.sort(
                    reverse=True, key=lambda x: x["lastUpdated"])
                latestversion = releaseVersions[0]["version"]

                filteredversions = []
                for version in releaseVersions:
                    if version["version"] == latestversion:
                        filteredversions.append(version)

                return filteredversions
        return self.versions

    def version(self):
        if self.versions and len(self.versions) > 1:
            return ";".join(list(map(lambda x: x['version'], self.versions)))
        return self.versions[0]['version']

    def set_recommended(self):
        self.recommended = True

    def __repr__(self):
        strs = f"<{self.__class__.__name__}> {self.identity} ({self.extensionId}) - Version: {self.version()}"
        return strs


class VSCExtension:

    @staticmethod
    def remove_old(artifactdir_extensions):
        for path, directoryNames, fileNames in os.walk(artifactdir_extensions):
            path = path.replace(artifactdir_extensions, '')
            if path == '':
                continue    # Skip root directory
            if str(path).count(os.path.sep) > 1:
                continue    # Skip any subdirectory
            versions = sorted(directoryNames, key=lambda dir: Version(dir), reverse=True)
            versions.remove(versions[0])
            if len(versions) == 0:
                continue    # Only a single version exists
            for version in versions:
                # Delete all left over versions
                log.debug(f'Remove version {version} of {os.path.basename(path)}')


class VSCUpdates(object):

    @staticmethod
    def latest_versions(insider=False):
        versions = {}
        for platform in vsc.PLATFORMS:
            for architecture in vsc.ARCHITECTURES:
                for buildtype in vsc.BUILDTYPES:
                    for quality in vsc.QUALITIES:
                        if quality == 'insider' and not insider:
                            continue
                        if platform == 'win32-x64' and architecture == 'ia32':
                            continue
                        if platform == 'darwin' and (architecture != '' or buildtype != ''):
                            continue
                        if 'linux' in platform and (architecture == '' or buildtype != ''):
                            continue
                        ver = VSCUpdateDefinition(
                            platform, architecture, buildtype, quality)
                        ver.check_for_update()
                        log.info(ver)
                        versions[f'{ver.identity}-{ver.quality}'] = ver
        return versions

    @staticmethod
    def latest_version(insider=False):
        versions = VSCUpdates.latest_versions(insider)
        latestVersion = Version('0.0.0')
        for version in versions.items():
            productVersion = version[1].productVersion
            if not productVersion:
                break
            productVersion = Version(productVersion)
            if productVersion > latestVersion:
                latestVersion = productVersion
        return str(latestVersion)

    @staticmethod
    def signal_updated(artifactdir):
        signalpath = os.path.join(artifactdir, 'updated.json')
        result = {
            'updated': datetime.datetime.now(datetime.timezone.utc)
        }
        with open(signalpath, 'w') as outfile:
            json.dump(result, outfile, cls=vsc.MagicJsonEncoder, indent=4)

    @staticmethod
    def remove_old(artifactdir_installers):
        for path, directoryNames, fileNames in os.walk(artifactdir_installers):
            path = path.replace(artifactdir_installers, '')
            if path == '':
                continue    # Skip root directory
            if str(path).count(os.path.sep) == 1:
                continue    # Skip version directory
            if str(path).count(os.path.sep) > 2:
                continue    # Skip any subdirectory
            filtered = filter(lambda file: not file.endswith('.json'), fileNames)
            versions = sorted(filtered, key=lambda file: Version(re.findall(r'\d+\.\d+\.\d+', file)[0]), reverse=True)
            if not versions:
                # Versions could not be determined
                log.debug(f'Versions of {path[path.index(os.path.sep)]} could not be determined')
                continue
            versions.remove(versions[0])
            if len(versions) == 0:
                continue    # Only a single version exists
            for version in versions:
                # Delete all left over versions
                log.debug(f'Remove version {version} of {path[path.index(os.path.sep)]}')


class VSCMarketplace(object):

    def __init__(self, insider, prerelease, version, session):
        self.insider = insider
        self.prerelease = prerelease
        self.version = version
        self.session = session
        self.backoff = 1

    def get_recommendations(self, destination, totalrecommended):
        recommendations = self.search_top_n(totalrecommended)
        recommended_old = self.get_recommendations_old(destination)

        for extension in recommendations:
            # If the extension has already been found then prevent it from being collected again when processing the old recommendation list
            if extension.identity in recommended_old.keys():
                del recommended_old[extension.identity]

        for packagename in recommended_old:
            extension = self.search_by_extension_name(packagename)
            if extension:
                recommendations.append(extension)
            else:
                log.debug(
                    f'get_recommendations failed finding a recommended extension by name for {packagename}. This extension has likely been removed.')

        prereleasecount = 0
        for recommendation in recommendations:
            recommendation.set_recommended()
            #  If the found extension is a prerelease version search for the next available release version
            if not self.prerelease and recommendation.isprerelease():
                prereleasecount += 1
                extension = self.search_release_by_extension_id(
                    recommendation.extensionId)
                if extension:
                    recommendation.versions = extension.get_latest_release_versions()
        return recommendations

    def get_recommendations_old(self, destination):
        result = self.session.get(vsc.URL_RECOMMENDATIONS,
                              allow_redirects=True, timeout=vsc.TIMEOUT)
        if result.status_code != 200:
            log.warning(
                f"get_recommendations failed accessing url {vsc.URL_RECOMMENDATIONS}, unhandled status code {result.status_code}")
            return {}  # Return an empty dictionary instead of False

        jresult = result.json()
        with open(os.path.join(destination, 'recommendations.json'), 'w') as outfile:
            json.dump(jresult, outfile, cls=vsc.MagicJsonEncoder, indent=4)

        # To dict to remove duplicates
        packages = {}
        for recommendation in jresult['workspaceRecommendations']:
            for package in recommendation['recommendations']:
                packages[package] = None

        return packages

    def get_malicious(self, extensions=None):
        if not extensions:
            return

        # Query Microsofts list
        result = self.session.get(
            vsc.URL_MALICIOUS, allow_redirects=True, timeout=vsc.TIMEOUT)
        if result.status_code != 200:
            log.warning(
                f"get_malicious failed accessing url {vsc.URL_MALICIOUS}, unhandled status code {result.status_code}")
            return False
        # Remove random utf-8 nbsp from server response
        stripped = result.content.decode(
            'utf-8', 'ignore').replace(u'\xa0', u'')
        jresult = json.loads(stripped)

        for extension in (extensions.copy()):
            if extension in jresult['malicious']:
                log.warning(
                    f'Preventing malicious extension {extension} from being downloaded')
                del extensions[extension]

    def get_specified(self, specifiedpath):
        if not os.path.exists(specifiedpath):
            result = {
                'extensions': []
            }
            with open(specifiedpath, 'w') as outfile:
                json.dump(result, outfile, cls=vsc.MagicJsonEncoder, indent=4)
            log.info(
                f'Created empty list of custom extensions to mirror at {specifiedpath}')
            return
        else:
            with open(specifiedpath, 'r') as fp:
                specifiedextensions = json.load(fp)
            if specifiedextensions and 'extensions' in specifiedextensions:
                specified = []
                for packagename in specifiedextensions['extensions']:
                    extension = self.search_by_extension_name(packagename)
                    if extension:
                        log.info(f'Adding extension to mirror {packagename}')
                        specified.append(extension)
                    else:
                        log.debug(
                            f'get_custom failed finding a recommended extension by name for {packagename}. This extension has likely been removed.')
                return specified

    def search_by_text(self, searchtext):
        if searchtext == '*':
            searchtext = ''

        return self._query_marketplace(vsc.FilterType.SearchText, searchtext)

    def search_top_n(self, n=200):
        log.info(f'Searching for top {n} recommended extensions')
        return self._query_marketplace(vsc.FilterType.SearchText, '', limit=n, sortOrder=vsc.SortOrder.Descending, sortBy=vsc.SortBy.InstallCount)

    def search_by_extension_id(self, extensionid):
        result = self._query_marketplace(
            vsc.FilterType.ExtensionId, extensionid)
        if result and len(result) == 1:
            return result[0]
        else:
            log.warning(f"search_by_extension_id failed {extensionid}")
            return False

    def search_by_extension_name(self, extensionname):
        if self.prerelease:
            result = self._query_marketplace(
                vsc.FilterType.ExtensionName, extensionname)
        else:
            releaseQueryFlags = vsc.QueryFlags.IncludeFiles | vsc.QueryFlags.IncludeVersionProperties | vsc.QueryFlags.IncludeAssetUri | \
                vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeVersions
            result = self._query_marketplace(
                vsc.FilterType.ExtensionName, extensionname, queryFlags=releaseQueryFlags)
            if result and len(result) == 1:
                result[0].versions = result[0].get_latest_release_versions()

        if result and len(result) == 1:
            return result[0]
        else:
            #log.debug(f"search_by_extension_name failed {extensionname} got {result}")
            return False

    def search_release_by_extension_id(self, extensionid):
        log.debug(
            f'Searching for release candidate by extensionId: {extensionid}')
        releaseQueryFlags = vsc.QueryFlags.IncludeFiles | vsc.QueryFlags.IncludeVersionProperties | vsc.QueryFlags.IncludeAssetUri | \
            vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeVersions
        result = self._query_marketplace(
            vsc.FilterType.ExtensionId, extensionid, queryFlags=releaseQueryFlags)
        if result and len(result) == 1:
            return result[0]
        else:
            log.warning(f"search_release_by_extension_id failed {extensionid}")
            return False

    def backoff_reset(self):
        self.backoff = 1
        
    def backoff_sleep(self):
        time.sleep(self.backoff)
        self.backoff *= 2

    def get_existing(self, artifactdir_extensions):
        extensions=[]
        for extension in glob.glob(os.path.join(artifactdir_extensions, '*', 'latest.json')):
            manifest = vsc.Utility.load_json(extension)
            result = self.search_by_extension_id(manifest['extensionId'])
            if result:
                extensions.append(result)
        return extensions

    def _query_marketplace(self, filtertype, filtervalue, pageNumber=0, pageSize=500, limit=0, sortOrder=vsc.SortOrder.Default, sortBy=vsc.SortBy.NoneOrRelevance, queryFlags=0):
        extensions = {}
        total = 0
        count = 0

        if 0 < limit < pageSize:
            pageSize = limit

        while count <= total:
            # log.debug(f'Query marketplace count {count} / total {total} - pagenumber {pageNumber}, pagesize {pageSize}')
            pageNumber = pageNumber + 1
            query = self._query(filtertype, filtervalue,
                                pageNumber, pageSize, queryFlags)
            result = None
            i = 0
            while i < 10:
                try:
                    result = self.session.post(vsc.URL_MARKETPLACEQUERY, headers=self._headers(
                    ), json=query, allow_redirects=True, timeout=vsc.TIMEOUT)
                    if result:
                        self.backoff_reset()
                        break
                    elif result.status_code == 429:
                        # Server is rate limiting us. Backoff.
                        self.backoff_sleep()
                        continue
                except requests.exceptions.ProxyError:
                    log.info("ProxyError: Retrying.")
                except requests.exceptions.ReadTimeout:
                    log.info("ReadTimeout: Retrying.")
                i += 1
                if i < 10:
                    log.info("Retrying pull page %d attempt %d." %
                             (pageNumber, i+1))
            if not result:
                log.info("Failed 10 attempts to query marketplace. Giving up.")
                break
            jresult = result.json()
            count = count + pageSize
            if 'results' in jresult:
                for jres in jresult['results']:
                    for extension in jres['extensions']:
                        identity = extension['publisher']['publisherName'] + \
                            '.' + extension['extensionName']
                        mpd = VSCExtensionDefinition(
                            identity=identity, raw=extension)
                        extensions[identity] = mpd

                    if 'resultMetadata' in jres:
                        for resmd in jres['resultMetadata']:
                            if 'ResultCount' in resmd['metadataType']:
                                total = resmd['metadataItems'][0]['count']
            if limit > 0 and count >= limit:
                break

        return list(extensions.values())

    def _query(self, filtertype, filtervalue, pageNumber, pageSize, queryFlags=0):
        if queryFlags == 0:
            queryFlags = self._query_flags()
        payload = {
            'assetTypes': [],
            'filters': [self._query_filter(filtertype, filtervalue, pageNumber, pageSize)],
            'flags': int(queryFlags)
        }
        return payload

    def _query_filter(self, filtertype, filtervalue, pageNumber, pageSize):
        result = {
            'pageNumber': pageNumber,
            'pageSize': pageSize,
            'sortBy': vsc.SortBy.NoneOrRelevance,
            'sortOrder': vsc.SortOrder.Default,
            'criteria': [
                self._query_filter_criteria(
                    vsc.FilterType.Target, 'Microsoft.VisualStudio.Code'),
                self._query_filter_criteria(
                    vsc.FilterType.ExcludeWithFlags, str(int(vsc.QueryFlags.Unpublished)))
            ]
        }

        if filtervalue != '':
            result['criteria'].append(
                self._query_filter_criteria(filtertype, filtervalue)
            )

        return result

    def _query_filter_criteria(self, filtertype, queryvalue):
        return {
            'filterType': int(filtertype),
            'value': queryvalue
        }

    def _query_flags(self):
        # return QueryFlags(914)
        return vsc.QueryFlags.IncludeFiles | vsc.QueryFlags.IncludeVersionProperties | vsc.QueryFlags.IncludeAssetUri | \
            vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeLatestVersionOnly

    def _headers(self):
        if self.insider:
            insider = '-insider'
        else:
            insider = ''
        return {
            'content-type': 'application/json',
            'accept': 'application/json;api-version=3.0-preview.1',
            'accept-encoding': 'gzip, deflate, br',
            'User-Agent': f'VSCode {self.version}{insider}',
            'x-market-client-Id': f'VSCode {self.version}{insider}',
            'x-market-user-Id': str(uuid.uuid4())
        }

    def __repr__(self):
        strs = f"<{self.__class__.__name__}>"
        return strs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Synchronises VSCode in an Offline Environment')
    parser.add_argument('--sync', '-s',
                        dest='sync',
                        action='store_true',
                        help='The basic-user sync. It includes stable binaries and typical extensions'
    )
    parser.add_argument('--syncall', '-a',
                        dest='syncall',
                        action='store_true',
                        help='The power-user sync. It includes all binaries and extensions'
    )
    parser.add_argument('--artifacts', '-d',
                        dest='artifactdir',
                        default='../artifacts/',
                        help='Path to downloaded artifacts'
    )
    parser.add_argument('--frequency', '-f',
                        dest='frequency',
                        default=None,
                        help='The frequency to try and update (e.g. sleep for \'12h\' and try again)'
    )

    # Arguments to tweak behaviour
    # ToDo Implement action=argparse.BooleanOptionalAction to combine --check-binaries and --skip-binaries into a single argument
    parser.add_argument('--check-binaries',
                        dest='checkbinaries',
                        action='store_true',
                        help='Check for updated binaries'
    )
    parser.add_argument('--check-insider', '-i',
                        dest='checkinsider',
                        action='store_true',
                        help='Check for updated insider binaries'
    )
    parser.add_argument('--check-recommended-extensions',
                        dest='checkextensions',
                        action='store_true',
                        help='Check for recommended extensions'
    )
    parser.add_argument('--check-specified-extensions', '-w',
                        dest='checkspecified',
                        action='store_true',
                        help='Check for extensions in <artifacts>/specified.json'
    )
    # ToDo Allow for list of names (action='extend' nargs='+')
    parser.add_argument('--extension-name', '-n',
                        dest='extensionname',
                        help='Find a specific extension by name'
    )
    # ToDo Allow for list of names (action='extend' nargs='+')
    parser.add_argument('--extension-search',
                        dest='extensionsearch',
                        help='Search for a set of extensions'
    )
    parser.add_argument('--prerelease-extensions', '-p',
                        dest='prerelease',
                        action='store_true',
                        help='Download prerelease extensions. Defaults to false.'
    )
    parser.add_argument('--update-binaries', '-b',
                        dest='updatebinaries',
                        action='store_true',
                        help='Download binaries'
    )
    parser.add_argument('--update-extensions', '-u',
                        dest='updateextensions',
                        action='store_true',
                        help='Download extensions'
    )
    parser.add_argument('--update-malicious-extensions', '-m',
                        dest='updatemalicious',
                        action='store_true',
                        help='Update the malicious extension list'
    )
    parser.add_argument('--skip-binaries', '-B',
                        dest='skipbinaries',
                        action='store_true',
                        help='Skip downloading binaries'
    )
    parser.add_argument('--vscode-version', '-v',
                        dest='version',
                        default=VSCUpdates.latest_version(),
                        help='VSCode version to search extensions as.'
    )
    parser.add_argument('--total-recommended',
                        type=int,
                        dest='totalrecommended',
                        default=500,
                        help='Total number of recommended extensions to sync from Search API. Defaults to 500'
    )
    parser.add_argument('--debug',
                        dest='debug',
                        action='store_true',
                        help='Show debug output'
    )
    parser.add_argument('--logfile', '-l',
                        dest='logfile',
                        default=None,
                        help='Sets a logfile to store loggging output'
    )
    parser.add_argument('--include-existing', '-e',
                        dest='existing',
                        action='store_true',
                        help='Include existing extensions in the update process'
    )
    parser.add_argument('--skip-existing', '-E',
                        dest='skipExisting',
                        action='store_true',
                        help='Skip inclusion of existing extensions in the update process'
    )
    parser.add_argument('--garbage-collection', '-g',
                        dest='garbageCollection',
                        action='store_true',
                        help='Remove old versions of artifacts (binaries / extensions)'
    )
    config = parser.parse_args()

    if config.debug:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    if config.logfile:
        log_dir = os.path.dirname(os.path.abspath(config.logfile))
        if not os.path.exists(log_dir):
            raise FileNotFoundError(
                f'Log directory does not exist at {log_dir}')
        logging.basicConfig(filename=config.logfile, encoding='utf-8', level=loglevel)
    else:
        log.basicConfig(
            format='[%(levelname)1.1s %(asctime)s %(module)s:%(lineno)d] %(message)s',
            datefmt='%y%m%d %H:%M:%S',
            level=loglevel
        )

    config.artifactdir_installers = os.path.join(
        os.path.abspath(config.artifactdir), 'installers')
    config.artifactdir_extensions = os.path.join(
        os.path.abspath(config.artifactdir), 'extensions')

    if config.sync or config.syncall:
        config.checkbinaries = True
        config.checkextensions = True
        config.updatebinaries = True
        config.updateextensions = True
        config.updatemalicious = True
        config.checkspecified = True
        config.existing = True

    if config.syncall:
        config.extensionsearch = '*'
        config.checkinsider = True

    if config.artifactdir:
        if not os.path.isdir(config.artifactdir):
            raise FileNotFoundError(
                f'Artifact directory does not exist at {config.artifactdir}')

    if config.updatebinaries and not config.checkbinaries:
        config.checkbinaries = True

    if config.existing:
        config.updateextensions = True

    if config.frequency:
        config.frequency = timeparse(config.frequency)

    session = requests.Session()
    retries = Retry(total=5,
            backoff_factor=0.1,
            status_forcelist=[ 500, 502, 503, 504 ])
    session.mount('https://', HTTPAdapter(max_retries=retries))

    while True:
        versions = []
        extensions = {}
        mp = VSCMarketplace(config.checkinsider,
                            config.prerelease, config.version, session)

        if config.checkbinaries and not config.skipbinaries:
            log.info('Syncing VS Code Update Binaries')
            versions = VSCUpdates.latest_versions(config.checkinsider)

        if config.updatebinaries and not config.skipbinaries:
            log.info('Syncing VS Code Binaries')
            for idkey in versions:
                if versions[idkey].updateurl:
                    result = versions[idkey].download_update(
                        config.artifactdir_installers)

                    # Only save the reference json if the download was successful
                    if result:
                        versions[idkey].save_state(
                            config.artifactdir_installers)

        if config.garbageCollection:
            log.info('Removing old VS Code Binaries')
            VSCUpdates.remove_old(config.artifactdir_installers)
            log.info('Removing old VS Code Extensions')
            VSCExtension.remove_old(config.artifactdir_extensions)

        if config.existing and not config.skipExisting:
            log.info('Get existing extensions from artifact directory')
            existing = mp.get_existing(config.artifactdir_extensions)
            if existing:
                for item in existing:
                    extensions[item.identity] = item

        if config.checkspecified:
            log.info('Syncing VS Code Specified Extensions')
            specifiedpath = os.path.join(os.path.abspath(
                config.artifactdir), 'specified.json')
            specified = mp.get_specified(specifiedpath)
            if specified:
                for item in specified:
                    log.info(item)
                    extensions[item.identity] = item

        if config.extensionsearch:
            log.info(
                f'Searching for VS Code Extension: {config.extensionsearch}')
            results = mp.search_by_text(config.extensionsearch)
            log.info(f'Found {len(results)} extensions')
            for item in results:
                log.debug(item)
                extensions[item.identity] = item

        if config.extensionname:
            log.info(
                f'Checking Specific VS Code Extension: {config.extensionname}')
            result = mp.search_by_extension_name(config.extensionname)
            if result:
                extensions[result.identity] = result

        if config.checkextensions:
            log.info('Syncing VS Code Recommended Extensions')
            recommended = mp.get_recommendations(os.path.abspath(
                config.artifactdir), config.totalrecommended)
            for item in recommended:
                extensions[item.identity] = item

        if config.updatemalicious:
            log.info('Syncing VS Code Malicious Extension List')
            malicious = mp.get_malicious(
                extensions)

        if config.updateextensions:
            log.info(
                f'Checking and Downloading Updates for {len(extensions)} Extensions')
            count = 0
            bonus = []
            for identity in extensions:
                log.debug(f'Fetching extension: {identity}')
                if count % 100 == 0:
                    log.info(
                        f'Progress {count}/{len(extensions)} ({count/len(extensions)*100:.1f}%)')
                extensions[identity].download_assets(
                    config.artifactdir_extensions, session)
                bonus = extensions[identity].process_embedded_extensions(
                    config.artifactdir_extensions, mp) + bonus
                extensions[identity].save_state(config.artifactdir_extensions)
                count = count + 1

            for bonusextension in bonus:
                log.debug(f'Processing Embedded Extension: {bonusextension}')
                bonusextension.download_assets(config.artifactdir_extensions, session)
                bonusextension.save_state(config.artifactdir_extensions)

        # Check if we did anything
        if config.checkbinaries or config.checkextensions or config.updatebinaries or config.updateextensions or config.updatemalicious or config.checkspecified or config.checkinsider:
            log.info('Complete')
            VSCUpdates.signal_updated(os.path.abspath(config.artifactdir))

            # Check if we need to sleep
            if config.frequency:
                log.info(
                    f'Going to sleep for {vsc.Utility.seconds_to_human_time(config.frequency)}')
                time.sleep(config.frequency)
            else:
                break
        else:
            log.info('Nothing to do')
            break

