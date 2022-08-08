import os, sys, time, json, glob
import falcon
from logzero import logger as log
from wsgiref import simple_server
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from threading import Event, Thread
import vsc


class VSCUpdater(object):

    def on_get(self, req, resp, platform, buildquality, commitid):
        updatedir = os.path.join(vsc.ARTIFACTS_INSTALLERS, platform, buildquality)
        if not os.path.exists(updatedir):
            log.warning(f'Update build directory does not exist at {updatedir}. Check sync or sync configuration.')
            resp.status = falcon.HTTP_500
            return
        latestpath = os.path.join(updatedir, 'latest.json')
        latest = vsc.Utility.load_json(latestpath)
        if not latest:
            resp.content = 'Unable to load latest.json'
            log.warning(f'Unable to load latest.json for platform {platform} and buildquality {buildquality}')
            resp.status = falcon.HTTP_500
            return
        if latest['version'] == commitid:
            # No update available
            log.debug(f'Client {platform}, Quality {buildquality}. No Update available.')
            resp.status = falcon.HTTP_204
            return
        name = latest['name']
        updateglob = os.path.join(updatedir, f'vscode-{name}.*')
        updatepath = vsc.Utility.first_file(updateglob)
        if not updatepath:
            resp.content = 'Unable to find update payload'
            log.warning(f'Unable to find update payload from {updateglob}')
            resp.status = falcon.HTTP_404
            return
        if not vsc.Utility.hash_file_and_check(updatepath, latest['sha256hash']):
            resp.content = 'Update payload hash mismatch'
            log.warning(f'Update payload hash mismatch {updatepath}')
            resp.status = falcon.HTTP_403
            return
        # Url to get update
        latest['url'] = vsc.URLROOT + updatepath
        log.debug(f'Client {platform}, Quality {buildquality}. Providing update {updatepath}')
        resp.status = falcon.HTTP_200
        resp.media = latest

class VSCBinaryFromCommitId(object):

    def on_get(self, req, resp, commitid, platform, buildquality):
        updatedir = os.path.join(vsc.ARTIFACTS_INSTALLERS, platform, buildquality)
        if not os.path.exists(updatedir):
            log.warning(f'Update build directory does not exist at {updatedir}. Check sync or sync configuration.')
            resp.status = falcon.HTTP_500
            return
        jsonpath = os.path.join(updatedir, f'{commitid}.json')
        updatejson = vsc.Utility.load_json(jsonpath)
        if not updatejson:
            resp.content = f'Unable to load {jsonpath}'
            log.warning(resp.content)
            resp.status = falcon.HTTP_500
            return
        name = updatejson['name']
        updateglob = os.path.join(updatedir, f'vscode-{name}.*')
        updatepath = vsc.Utility.first_file(updateglob)
        if not updatepath:
            resp.content = f'Unable to find update payload from {updateglob}'
            log.warning(resp.content)
            resp.status = falcon.HTTP_404
            return
        if not vsc.Utility.hash_file_and_check(updatepath, updatejson['sha256hash']):
            resp.content = f'Update payload hash mismatch {updatepath}'
            log.warning(resp.content)
            resp.status = falcon.HTTP_403
            return
        # Url for the client to fetch the update
        resp.set_header('Location', vsc.URLROOT + updatepath)
        resp.status = falcon.HTTP_302

class VSCRecommendations(object):

    def on_get(self, req, resp):
        if not os.path.exists(vsc.ARTIFACT_RECOMMENDATION):
            resp.status = falcon.HTTP_404
            return
        resp.status = falcon.HTTP_200
        resp.content_type = 'application/octet-stream'
        with open(vsc.ARTIFACT_RECOMMENDATION, 'r') as f:
            resp.body = f.read()

class VSCMalicious(object):

    def on_get(self, req, resp):
        if not os.path.exists(vsc.ARTIFACT_MALICIOUS):
            resp.status = falcon.HTTP_404
            return
        resp.status = falcon.HTTP_200
        resp.content_type = 'application/octet-stream'
        with open(vsc.ARTIFACT_MALICIOUS, 'r') as f:
            resp.body = f.read()

class VSCGallery(object):

    def __init__(self, interval=3600):
        self.extensions = {}
        self.interval = interval
        self.loaded = Event()
        self.update_worker = Thread(target=self.update_state_loop, args=())
        self.update_worker.daemon = True
        self.update_worker.start()

    def update_state(self):
        # Load each extension
        for extensiondir in glob.glob(vsc.ARTIFACTS_EXTENSIONS + '/*/'):

            # Load the latest version of each extension
            latestpath = os.path.join(extensiondir, 'latest.json')
            latest = vsc.Utility.load_json(latestpath)

            if not latest:
                log.debug(f'Tried to load invalid manifest json {latestpath}')
                continue

            latest = self.process_loaded_extension(latest, extensiondir)

            if not latest:
                log.debug(f'Unable to determine latest version {latestpath}')
                continue

            # Determine the latest version
            latestversion = latest['versions'][0]

            # Find other versions
            for versionpath in glob.glob(extensiondir + '/*/extension.json'):
                #log.info(f'Version path: {versionpath}')
                vers = vsc.Utility.load_json(versionpath)
                if not vers:
                    log.debug(f'Tried to load invalid version manifest json {versionpath}')
                    continue
                vers = self.process_loaded_extension(vers, extensiondir)

                # If this extension.json is actually the latest version, then ignore it
                if not vers or latestversion == vers['versions'][0]:
                    continue

                # Append this other possible version
                latest['versions'].append(vers['versions'][0])

            # Sort versions
            latest['versions'] = sorted(latest['versions'], key=lambda k: k['version'], reverse=True)

            # Save the extension in the cache
            name = latest['identity']
            self.extensions[name] = latest

        log.info(f'Loaded {len(self.extensions)} extensions')

    def process_loaded_extension(self, extension, extensiondir):
            name = extension['identity']

            # Repoint asset urls
            for version in extension["versions"]:
                if "targetPlatform" in version:
                    targetPlatform = version['targetPlatform']
                    asseturi = vsc.URLROOT + os.path.join(extensiondir, version['version'], targetPlatform)
                else:                    
                    asseturi = vsc.URLROOT + os.path.join(extensiondir, version['version'])

                version['assetUri'] = asseturi
                version['fallbackAssetUri'] = asseturi
                for asset in version['files']:
                    asset['source'] = asseturi + '/' + asset['assetType']

            # Map statistics for later lookup
            stats = {
                'averagerating': 0,
                'install': 0,
                'weightedRating': 0
            }
            if 'statistics' not in extension or not extension['statistics']:
                log.info(f'Statistics are missing from extension {name} in {extensiondir}, generating.')
            else:
                extension_statistics = {}
                for statistic in extension['statistics']:
                    extension_statistics[statistic['statisticName']] = statistic['value']
                stats.update(extension_statistics)
            extension['stats'] = stats
            return extension

    def update_state_loop(self):
        while True:
            self.update_state()
            self.loaded.set()
            log.info(f'Checking for updates in {vsc.Utility.seconds_to_human_time(self.interval)}')
            time.sleep(self.interval)

    def on_post(self, req, resp):
        if 'filters' not in req.media or 'criteria' not in req.media['filters'][0] or 'flags' not in req.media:
            log.warning(f'Post missing critical components. Raw post {req.media}')
            resp.status = falcon.HTTP_404
            return

        sortby = vsc.SortBy.NoneOrRelevance
        sortorder = vsc.SortOrder.Default
        #flags = vsc.QueryFlags.NoneDefined
        criteria = req.media['filters'][0]['criteria']

        if req.media['filters'][0]['sortOrder']:
            sortorder = vsc.SortOrder(req.media['filters'][0]['sortOrder'])

        if req.media['filters'][0]['sortBy']:
            sortby = vsc.SortBy(req.media['filters'][0]['sortBy'])

        # Flags can be used for version management, but it appears the client doesn't care what's sent back
        #if req.media['flags']:
        #    flags = vsc.QueryFlags(req.media['flags'])

        # Unused
        #pagenumber = req.media['filters'][0]['pageNumber']
        #pagesize = req.media['filters'][0]['pageSize']
        #log.info(f'CRITERIA {criteria}, flags {flags}, sortby {sortby}, sortorder {sortorder}')

        # If no order specified, default to InstallCount (e.g. popular first)
        if sortby == vsc.SortBy.NoneOrRelevance:
            sortby = vsc.SortBy.InstallCount
            sortorder = vsc.SortOrder.Descending

        result = self._apply_criteria(criteria)
        self._sort(result, sortby, sortorder)
        resp.media = self._build_response(result)
        resp.status = falcon.HTTP_200

    def _sort(self, result, sortby, sortorder):
        if sortorder == vsc.SortOrder.Ascending:
            rev = False
        else:
            rev = True

        if sortby == vsc.SortBy.PublisherName:
            rev = not rev
            result.sort(key=lambda k: k['publisher']['publisherName'], reverse=rev)

        elif sortby == vsc.SortBy.InstallCount:
            result.sort(key=lambda k: k['stats']['install'], reverse=rev)

        elif sortby == vsc.SortBy.AverageRating:
            result.sort(key=lambda k: k['stats']['averagerating'], reverse=rev)

        elif sortby == vsc.SortBy.WeightedRating:
            result.sort(key=lambda k: k['stats']['weightedRating'], reverse=rev)

        elif sortby == vsc.SortBy.LastUpdatedDate:
            result.sort(key=lambda k: vsc.Utility.from_json_datetime(k['lastUpdated']), reverse=rev)

        elif sortby == vsc.SortBy.PublishedDate:
            result.sort(key=lambda k: vsc.Utility.from_json_datetime(k['publishedDate']), reverse=rev)

        else:
            rev = not rev
            result.sort(key=lambda k: k['displayName'], reverse=rev)

    def _apply_criteria(self, criteria):
        # `self.extensions` may be modified by the update thread while this
        # function is executing so we need to operate on a copy
        extensions = self.extensions.copy()
        result = []

        for crit in criteria:
            if 'filterType' not in crit or 'value' not in crit:
                continue
            ft = vsc.FilterType(crit['filterType'])
            val = crit['value'].lower()

            if ft == vsc.FilterType.Tag:
                # ?? Tags
                log.info(f"Not implemented filter type {ft} for {val}")
                continue

            elif ft == vsc.FilterType.ExtensionId:
                for name in extensions:
                    if val == extensions[name]['extensionId']:
                        result.append(extensions[name])

            elif ft == vsc.FilterType.Category:
                log.info(f"Not implemented filter type {ft} for {val}")
                continue

            elif ft == vsc.FilterType.ExtensionName:
                for name in extensions:
                    if name.lower() == val:
                        result.append(extensions[name])

            elif ft == vsc.FilterType.Target:
                # Ignore the product, typically Visual Studio Code. If it's custom, then let it connect here
                continue

            elif ft == vsc.FilterType.Featured:
                log.info(f"Not implemented filter type {ft} for {val}")
                continue

            elif ft == vsc.FilterType.SearchText:
                for name in extensions:
                    # Search in extension name, display name and short description
                    if val in name.lower():
                        result.append(extensions[name])
                    elif 'displayName' in extensions[name] and val in extensions[name]['displayName'].lower():
                        result.append(extensions[name])
                    elif 'shortDescription' in extensions[name] and val in extensions[name]['shortDescription'].lower():
                        result.append(extensions[name])

            elif ft == vsc.FilterType.ExcludeWithFlags:
                # Typically this ignores Unpublished Flag (4096) extensions
                continue

            else:
                log.warning(f"Undefined filter type {crit}")

        # Handle popular / recommended
        if len(result) <= 0 and len(criteria) <= 2:
            log.info(f'Search criteria {criteria}')
            result = [ext for ext in extensions.values() if 'recommended' in ext and ext['recommended']]

        return result

    def _build_response(self, resultingExtensions):
        result = {
            'results': [
                {
                    'extensions': resultingExtensions,
                    'pagingToken': None,
                    'resultMetadata': [
                        {
                            'metadataType': 'ResultCount',
                            'metadataItems': [
                                {
                                    'name': 'TotalCount',
                                    'count': len(resultingExtensions)
                                }
                            ]
                        }
                    ]
                }
            ]
        }
        return result

class VSCIndex(object):

    def __init__(self):
        pass

    def on_get(self, req, resp):
        resp.content_type = 'text/html'
        with open('/opt/vscoffline/vscgallery/content/index.html', 'r') as f:
            resp.body = f.read()
        resp.status = falcon.HTTP_200

class VSCDirectoryBrowse(object):

    def __init__(self, root):
        self.root = root

    def on_get(self, req, resp):
        requested_path = os.path.join(self.root, req.get_param('path', required=True))
        # Check the path requested
        if os.path.commonprefix((os.path.realpath(requested_path), self.root)) != self.root:
            resp.status = falcon.HTTP_403
            return
        resp.content_type = 'text/html'
        # Load template and replace variables
        with open('/opt/vscoffline/vscgallery/content/browse.html', 'r') as f:
            resp.body = f.read()
        resp.body = resp.body.replace('{PATH}', requested_path)
        resp.body = resp.body.replace('{CONTENT}', self.simple_dir_browse_response(requested_path))
        resp.status = falcon.HTTP_200

    def simple_dir_browse_response(self, path):
        response = ''
        for item in vsc.Utility.folders_in_folder(path):
            response += f'd <a href="/browse?path={os.path.join(path, item)}">{item}</a><br />'
        for item in vsc.Utility.files_in_folder(path):
            if item != path:
                response += f'f <a href="{os.path.join(self.root, path, item)}">{item}</a><br />'
        return response

class ArtifactChangedHandler(FileSystemEventHandler):

    def __init__(self, gallery):
        self.gallery = gallery

    def on_modified(self, event):
        if 'updated.json' in event.src_path:
            log.info('Detected updated.json change, updating extension gallery')
            self.gallery.update_state()


if not os.path.exists(vsc.ARTIFACTS):
    log.warning(f'Artifact directory missing {vsc.ARTIFACTS}. Cannot proceed.')
    sys.exit(-1)

if not os.path.exists(vsc.ARTIFACTS_INSTALLERS):
    log.warning(f'Installer artifact directory missing {vsc.ARTIFACTS_INSTALLERS}. Cannot proceed.')
    sys.exit(-1)

if not os.path.exists(vsc.ARTIFACTS_EXTENSIONS):
    log.warning(f'Extensions artifact directory missing {vsc.ARTIFACTS_EXTENSIONS}. Cannot proceed.')
    sys.exit(-1)

vscgallery = VSCGallery()

log.debug('Waiting for gallery cache to load')
#vscgallery.loaded.wait()

observer = PollingObserver()
observer.schedule(ArtifactChangedHandler(vscgallery), '/artifacts/', recursive=False)
observer.start()

application = falcon.App(cors_enable=True)
application.add_route('/api/update/{platform}/{buildquality}/{commitid}', VSCUpdater())
application.add_route('/commit:{commitid}/{platform}/{buildquality}', VSCBinaryFromCommitId())
application.add_route('/extensions/workspaceRecommendations.json.gz', VSCRecommendations()) # Why no compress??
application.add_route('/extensions/marketplace.json', VSCMalicious())
application.add_route('/_apis/public/gallery/extensionquery', vscgallery)
application.add_route('/browse', VSCDirectoryBrowse(vsc.ARTIFACTS))
application.add_route('/', VSCIndex())
application.add_static_route('/artifacts/', '/artifacts/')

if __name__ == '__main__':
    httpd = simple_server.make_server('0.0.0.0', 5000, application)
    httpd.serve_forever()
