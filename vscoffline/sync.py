import os, sys, argparse, requests, pathlib, hashlib, uuid, logzero, logging, json, time, datetime
from logzero import logger as log
from pytimeparse.timeparse import timeparse
import vsc


class VSCUpdateDefinition(object):

    session = requests.session()

    def __init__(self, platform=None, architecture=None, buildtype=None, quality=None,
            updateurl=None, name=None, version=None, productVersion=None, 
            hashs=None, timestamp=None, sha256hash=None, supportsFastUpdate=None):

        if not vsc.Utility.validate_platform(platform):
            raise ValueError(f"Platform {platform} invalid or not implemented")
            
        if not vsc.Utility.validate_architecture(architecture):
            raise ValueError(f"Architecture {architecture} invalid or not implemented")

        if not vsc.Utility.validate_buildtype(buildtype):
            raise ValueError(f"Buildtype {buildtype} invalid or not implemented")

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
            old_commit_id = '7c4205b5c6e52a53b81c69d2b2dc8a627abaa0ba' # To trigger the API to delta

        url = vsc.URL_BINUPDATES + f"{self.identity}/{self.quality}/{old_commit_id}"
        
        log.debug(f'Update url {url}')
        result = self.session.get(url, allow_redirects=True, timeout=vsc.TIMEOUT)
        self.checkedForUpdate = True

        if result.status_code == 204:
            # No update available
            return False
        elif result.status_code != 200:
            # Unhandled response from API
            log.warning(f"Update url failed {url}. Unhandled status code {result.status_code}")
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
            log.warning('Cannot download update if the update definition has not been downloaded')
            return
        if not self.updateurl:
            log.warning('Cannot download update if there is no url to download from')
            return

        destination = os.path.join(destination, self.identity, self.quality)
        if not os.path.isdir(destination):
            os.makedirs(destination)            
        suffix = pathlib.Path(self.updateurl).suffix
        if '.gz' in suffix:
            suffix = ''.join(pathlib.Path(self.updateurl).suffixes)
        destfile = os.path.join(destination, f'vscode-{self.name}{suffix}')

        if os.path.exists(destfile):
            log.debug(f'Previously downloaded {self.identity}, checking hash')
        else:
            log.info(f'Downloading {self.identity} {self.quality} to {destfile}')
            result = self.session.get(self.updateurl, allow_redirects=True, timeout=vsc.TIMEOUT)
            open(destfile, 'wb').write(result.content)

        if not vsc.Utility.hash_file_and_check(destfile, self.sha256hash):
            log.warning(f'HASH MISMATCH for {self.identity} at {destfile} expected {self.sha256hash}. Removing local file.')
            os.remove(destfile)
            return False
        log.debug(f'Hash ok for {self.identity} with {self.sha256hash}')
        return True

    def save_state(self, destination):
        destination = os.path.join(destination, self.identity)
        if not os.path.isdir(destination):
            os.makedirs(destination)
        # Write version details blob as latest
        vsc.Utility.write_json(os.path.join(destination, self.quality, 'latest.json'), self)
        # Write version details blob as the commit id
        if self.version:
            vsc.Utility.write_json(os.path.join(destination, self.quality, f'{self.version}.json'), self)

    def __repr__(self):
        strs = f"<{self.__class__.__name__}> Target: {self.identity} Quality:{self.quality} "        
        if self.updateurl:
            strs += f"Update available: {self.name} Build: {self.version}"
        elif self.checkedForUpdate:
            strs += f"No update found"
        return strs

class VSCExtensionDefinition(object):
    
    session = requests.session()

    def __init__(self, identity, raw=None):
        self.identity = identity
        self.extensionId = None
        self.recommended = False
        self.versions = []
        if raw:
            self.__dict__.update(raw)            
            if 'extensionId' in raw:
                self.extensionId = raw['extensionId']

    def download_assets(self, destination):
        availableassets = self._get_asset_types()
        for availableasset in availableassets:
            self._download_asset(destination, availableasset)        

    def process_embedded_extensions(self, destination, mp):
        """
        Check an extension's Manifest for an extension pack (e.g. more extensions to download)
        """
        bonusextensions = []
        manifestpath = os.path.join(destination, self.identity, self.version(), 'Microsoft.VisualStudio.Code.Manifest')
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
        with open(os.path.join(destination, self.version(), 'extension.json'), 'w') as outfile:
            json.dump(self, outfile, cls=vsc.MagicJsonEncoder, indent=4)

    def version(self):
        if self.versions and len(self.versions) > 1:
            log.warning(f"version(). More than one version returned for {self.identity}. Unhandled.")
            return None
        return self.versions[0]['version']
    
    def set_recommended(self):
        self.recommended = True

    def _download_asset(self, destination, asset):
        if not self.extensionId:
            log.warning('download_asset() cannot download update if the update definition has not been downloaded')
            return
        destination = os.path.join(destination, self.identity, self.version())
        if not os.path.isdir(destination):
            os.makedirs(destination)
        url = self._get_asset_source(asset)
        if not url:
            log.warning('download_asset() cannot download update as asset url is missing')
            return
        destfile = os.path.join(destination, f'{asset}')
        if not os.path.exists(destfile):
            log.debug(f'Downloading {self.identity} {asset} to {destfile}')
            result = self.session.get(url, allow_redirects=True, timeout=vsc.TIMEOUT)
            with open(destfile, 'wb') as dest:
                dest.write(result.content)
    
    def _get_asset_types(self):
        if self.versions and len(self.versions) > 1:
            log.warning(f"_get_asset_types(). More than one version returned for {self.identity}. Unhandled.")
            return None
        assets = []
        for asset in self.versions[0]['files']:
           if 'assetType' in asset:
               assets.append(asset['assetType'])
        return assets

    def _get_asset_source(self, name):
        if self.versions and len(self.versions) > 1:
            log.warning(f"_get_asset_source(). More than one version returned for {self.identity}. Unhandled.")
            return None
        for asset in self.versions[0]['files']:
           if asset['assetType'] == name:
               return asset['source']
        return False

    def __repr__(self):
        strs = f"<{self.__class__.__name__}> Target: {self.identity} Id: {self.extensionId} Version: {self.version()}"
        return strs

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
                            if platform == 'win32' and architecture == 'ia32':
                                continue
                            if platform == 'darwin' and (architecture != '' or buildtype != ''):
                                continue
                            if 'linux' in platform and (architecture == '' or buildtype != ''):
                                continue                        
                            ver = VSCUpdateDefinition(platform, architecture, buildtype, quality)
                            ver.check_for_update()
                            log.info(ver)
                            versions[f'{ver.identity}-{ver.quality}'] = ver
        return versions

    @staticmethod
    def signal_updated(artifactdir):
        signalpath = os.path.join(artifactdir, 'updated.json')
        result = {
            'updated': datetime.datetime.utcnow()
        }
        with open(signalpath, 'w') as outfile:
            json.dump(result, outfile, cls=vsc.MagicJsonEncoder, indent=4)

class VSCMarketplace(object):
   
    session = requests.session()

    def __init__(self, insider):
        self.insider = insider

    def get_recommendations(self, destination):
        recommendations = self.search_top_n(n=200)
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
                log.debug(f'get_recommendations failed finding a recommended extension by name for {packagename}. This extension has likely been removed.')
        
        for recommendation in recommendations:
            recommendation.set_recommended()

        return recommendations

    def get_recommendations_old(self, destination):
        result = self.session.get(vsc.URL_RECOMMENDATIONS, allow_redirects=True, timeout=vsc.TIMEOUT)
        if result.status_code != 200:            
            log.warning(f"get_recommendations failed accessing url {vsc.URL_RECOMMENDATIONS}, unhandled status code {result.status_code}")
            return False

        jresult = result.json()        
        with open(os.path.join(destination, 'recommendations.json'), 'w') as outfile:
            json.dump(jresult, outfile, cls=vsc.MagicJsonEncoder, indent=4)

        # To dict to remove duplicates
        packages = {}
        for recommendation in jresult['workspaceRecommendations']:
            for package in recommendation['recommendations']:
                packages[package] = None
        
        return packages

    def get_malicious(self, destination, extensions=None):
        result = self.session.get(vsc.URL_MALICIOUS, allow_redirects=True, timeout=vsc.TIMEOUT)
        if result.status_code != 200:            
            log.warning(f"get_malicious failed accessing url {vsc.URL_MALICIOUS}, unhandled status code {result.status_code}")
            return False
        # Remove random utf-8 nbsp from server response
        stripped = result.content.decode('utf-8','ignore').replace(u'\xa0', u'')
        jresult = json.loads(stripped)
        with open(os.path.join(destination, 'malicious.json'), 'w') as outfile:
            json.dump(jresult, outfile, cls=vsc.MagicJsonEncoder, indent=4)
        
        if not extensions:
            return
        
        for malicious in jresult['malicious']:
            log.debug(f'Malicious extension {malicious}')
            if malicious in extensions.keys():
                log.warning(f'Preventing malicious extension {malicious} from being downloaded')
                del extensions[malicious]

    def get_specified(self, specifiedpath):
        if not os.path.exists(specifiedpath):
            result = {
                'extensions': []
            }
            with open(specifiedpath, 'w') as outfile:
                json.dump(result, outfile, cls=vsc.MagicJsonEncoder, indent=4)
            log.info(f'Created empty list of custom extensions to mirror at {specifiedpath}')
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
                        log.debug(f'get_custom failed finding a recommended extension by name for {packagename}. This extension has likely been removed.')
                return specified

    def search_by_text(self, searchtext):
        if searchtext == '*':
            searchtext = ''

        return self._query_marketplace(vsc.FilterType.SearchText, searchtext)
    
    def search_top_n(self, n=200):
        return self._query_marketplace(vsc.FilterType.SearchText, '', limit=n, sortOrder=vsc.SortOrder.Descending, sortBy=vsc.SortBy.InstallCount)

    def search_by_extension_id(self, extensionid):
        result = self._query_marketplace(vsc.FilterType.ExtensionId, extensionid)
        if result and len(result) == 1:
            return result[0]
        else:
            log.warning(f"search_by_extension_id failed {extensionid}")
            return False

    def search_by_extension_name(self, extensionname):
        result = self._query_marketplace(vsc.FilterType.ExtensionName, extensionname)
        if result and len(result) == 1:
            return result[0]
        else:
            #log.debug(f"search_by_extension_name failed {extensionname} got {result}")
            return False

    def _query_marketplace(self, filtertype, filtervalue, pageNumber=0, pageSize=500, limit=0, sortOrder=vsc.SortOrder.Default, sortBy=vsc.SortBy.NoneOrRelevance):
        extensions = {}
        total = 0
        count = 0
        while count <= total:
            #log.debug(f'Query marketplace count {count} / total {total} - pagenumber {pageNumber}, pagesize {pageSize}')
            pageNumber = pageNumber + 1
            query = self._query(filtertype, filtervalue, pageNumber, pageSize)
            result = self.session.post(vsc.URL_MARKETPLACEQUERY, headers=self._headers(), json=query, allow_redirects=True, timeout=vsc.TIMEOUT)
            jresult = result.json()
            count = count + pageSize
            if 'results' in jresult:
                for jres in jresult['results']:
                    for extension in jres['extensions']:
                        identity = extension['publisher']['publisherName'] + '.' + extension['extensionName']
                        mpd = VSCExtensionDefinition(identity=identity, raw=extension)
                        extensions[identity] = mpd

                    if 'resultMetadata' in jres:
                        for resmd in jres['resultMetadata']:                        
                            if 'ResultCount' in resmd['metadataType']:
                                total = resmd['metadataItems'][0]['count']
            if limit > 0 and count > limit:
                break

        return list(extensions.values())

    def _query(self, filtertype, filtervalue, pageNumber, pageSize):
        return {
            'assetTypes': [],
            'filters': [self._query_filter(filtertype, filtervalue, pageNumber, pageSize)],
            'flags': int(self._query_flags())
        }

    def _query_filter(self, filtertype, filtervalue, pageNumber, pageSize):
        result = {
            'pageNumber': pageNumber,
            'pageSize': pageSize,
            'sortBy': vsc.SortBy.NoneOrRelevance,
            'sortOrder': vsc.SortOrder.Default,
            'criteria': [
                self._query_filter_criteria(vsc.FilterType.Target, 'Microsoft.VisualStudio.Code'),
                self._query_filter_criteria(vsc.FilterType.ExcludeWithFlags, str(int(vsc.QueryFlags.Unpublished)))                
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
        #return QueryFlags(914)
        return vsc.QueryFlags.IncludeFiles | vsc.QueryFlags.IncludeVersionProperties | vsc.QueryFlags.IncludeAssetUri | \
            vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeStatistics | vsc.QueryFlags.IncludeLatestVersionOnly

    def _headers(self, version='1.34.0'):
        if self.insider:
            insider = '-insider'
        else:
            insider = ''
        return {
            'content-type': 'application/json',
            'accept': 'application/json;api-version=3.0-preview.1',
            'accept-encoding': 'gzip, deflate, br',
            'User-Agent': f'VSCode {version}{insider}',
            'x-market-client-Id': f'VSCode {version}{insider}',            
            'x-market-user-Id': str(uuid.uuid4())
        }

    def __repr__(self):
        strs = f"<{self.__class__.__name__}>"
        return strs


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Synchronises VSCode in an Offline Environment')
    parser.add_argument('--sync', dest='sync', action='store_true', help='The basic-user sync. It includes stable binaries and typical extensions')
    parser.add_argument('--syncall', dest='syncall', action='store_true', help='The power-user sync. It includes all binaries and extensions ')
    parser.add_argument('--artifacts', dest='artifactdir', default='../artifacts/', help='Path to downloaded artifacts')
    parser.add_argument('--frequency', dest='frequency', default=None, help='The frequency to try and update (e.g. sleep for \'12h\' and try again')    

    # Arguments to tweak behaviour
    parser.add_argument('--check-binaries', dest='checkbinaries', action='store_true', help='Check for updated binaries')
    parser.add_argument('--check-insider', dest='checkinsider', action='store_true', help='Check for updated insider binaries')
    parser.add_argument('--check-recommended-extensions', dest='checkextensions', action='store_true', help='Check for recommended extensions')
    parser.add_argument('--check-specified-extensions', dest='checkspecified', action='store_true', help='Check for extensions in <artifacts>/specified.json')    
    parser.add_argument('--extension-name', dest='extensionname', help='Find a specific extension by name')
    parser.add_argument('--extension-search', dest='extensionsearch', help='Search for a set of extensions')    
    parser.add_argument('--update-binaries', dest='updatebinaries', action='store_true', help='Download binaries')
    parser.add_argument('--update-extensions', dest='updateextensions', action='store_true', help='Download extensions')
    parser.add_argument('--update-malicious-extensions', dest='updatemalicious', action='store_true', help='Update the malicious extension list')
    parser.add_argument('--skip-binaries', dest='skipbinaries', action='store_true', help='Skip downloading binaries')
    parser.add_argument('--debug', dest='debug', action='store_true', help='Show debug output')
    config = parser.parse_args()
    
    if config.debug:
        logzero.loglevel(logging.DEBUG)
    else:
        logzero.loglevel(logging.INFO)

    config.artifactdir_installers = os.path.join(os.path.abspath(config.artifactdir), 'installers')
    config.artifactdir_extensions = os.path.join(os.path.abspath(config.artifactdir), 'extensions')

    if config.sync or config.syncall:
        config.checkbinaries = True
        config.checkextensions = True
        config.updatebinaries = True
        config.updateextensions = True
        config.updatemalicious = True
        config.checkspecified = True
        if not config.frequency:
            config.frequency = '12h'
    
    if config.syncall:
        config.extensionsearch = '*'
        config.checkinsider = True

    if config.artifactdir and config.updatebinaries:
        if not os.path.isdir(config.artifactdir):            
            raise FileNotFoundError(f'Artifact directory does not exist at {config.artifactdir}')
    
    if config.updatebinaries and not config.checkbinaries:
        config.checkbinaries = True

    if config.frequency:
        config.frequency = timeparse(config.frequency)
    
    while True:        
        versions = []
        extensions = {}
        mp = VSCMarketplace(config.checkinsider)

        if config.checkbinaries and not config.skipbinaries:
            log.info('Syncing VS Code Versions')
            versions = VSCUpdates.latest_versions(config.checkinsider)

        if config.updatebinaries and not config.skipbinaries:
            log.info('Syncing VS Code Binaries')
            for idkey in versions:
                if versions[idkey].updateurl:
                    result = versions[idkey].download_update(config.artifactdir_installers)

                    # Only save the reference json if the download was successful
                    if result:
                        versions[idkey].save_state(config.artifactdir_installers)
        
        if config.checkspecified:
            log.info('Syncing VS Code Specified Extensions')
            specifiedpath = os.path.join(os.path.abspath(config.artifactdir), 'specified.json')
            specified = mp.get_specified(specifiedpath)
            if specified:
                for item in specified:
                    log.info(item)
                    extensions[item.identity] = item

        if config.extensionsearch:
            log.info(f'Searching for VS Code Extension: {config.extensionsearch}')
            results = mp.search_by_text(config.extensionsearch)
            log.info(f'Found {len(results)} extensions')
            for item in results:
                log.info(item)
                extensions[item.identity] = item

        if config.extensionname:
            log.info(f'Checking Specific VS Code Extension: {config.extensionname}')
            result = mp.search_by_extension_name(config.extensionname)
            if result:
                log.info(result)
                extensions[result.identity] = result
        
        if config.checkextensions:
            log.info('Syncing VS Code Recommended Extensions')            
            recommended = mp.get_recommendations(os.path.abspath(config.artifactdir))
            for item in recommended:
                log.info(item)
                extensions[item.identity] = item
        
        if config.updatemalicious:
            log.info('Syncing VS Code Malicious Extension List')
            malicious = mp.get_malicious(os.path.abspath(config.artifactdir), extensions)

        if config.updateextensions:
            log.info(f'Checking and Downloading Updates for {len(extensions)} Extensions')
            count = 0
            bonus = []
            for identity in extensions:
                if count % 100 == 0:
                    log.info(f'Progress {count}/{len(extensions)} ({count/len(extensions)*100:.1f}%)')
                extensions[identity].download_assets(config.artifactdir_extensions)
                bonus = extensions[identity].process_embedded_extensions(config.artifactdir_extensions, mp) + bonus
                extensions[identity].save_state(config.artifactdir_extensions)
                count = count + 1

            for bonusextension in bonus:
                log.info(f'Processing Embedded Extension: {bonusextension}')
                bonusextension.download_assets(config.artifactdir_extensions)                
                bonusextension.save_state(config.artifactdir_extensions)
                
        log.info('Complete')
        VSCUpdates.signal_updated(os.path.abspath(config.artifactdir))

        if not config.frequency:
            break
        else:
            log.info(f'Going to sleep for {vsc.Utility.seconds_to_human_time(config.frequency)}')
            time.sleep(config.frequency)
                