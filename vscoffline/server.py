import os, time, json, glob, threading
import falcon
from logzero import logger as log
from wsgiref import simple_server
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
import vsc


URLROOT = 'https://update.code.visualstudio.com'


class VSCUpdater(object):

    def __init__(self):
        self.home = '/artifacts/installers'
        if not os.path.exists(self.home):
            log.warn(f'Installers artifact directory missing {self.home}')

    def on_get(self, req, resp, platform, buildquality, commitid):
        updatedir = os.path.join(self.home, platform, buildquality)
        if not os.path.exists(updatedir):
            log.warn(f'Update directory does not exist at {updatedir}')
            resp.status = falcon.HTTP_500
            return
        with open(os.path.join(updatedir, 'latest.json')) as fp:
            latest = json.load(fp)
        if not latest:
            resp.content = 'Unable to load latest.json'
            log.warn(f'Unable to load latest.json for platform {platform} and buildquality {buildquality}')
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
            log.warn(f'Unable to find update payload from {updateglob}')
            resp.status = falcon.HTTP_404
            return
        if not vsc.Utility.hash_file_and_check(updatepath, latest['sha256hash']):
            resp.content = 'Update payload hash mismatch'
            log.warn(f'Update payload hash mismatch {updatepath}')
            resp.status = falcon.HTTP_403
            return
        # Url to get update
        latest['url'] = URLROOT + updatepath
        log.debug(f'Client {platform}, Quality {buildquality}. Providing update {updatepath}')
        resp.status = falcon.HTTP_200
        resp.media = latest

class VSCRecommendations(object):

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.content_type = 'application/octet-stream'
        with open('/artifacts/recommendations.json', 'r') as f:
            resp.body = f.read()

class VSCMalicious(object):

    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.content_type = 'application/octet-stream'
        with open('/artifacts/malicious.json', 'r') as f:
            resp.body = f.read()

class VSCGallery(object):

    def __init__(self, interval=600):
        self.home = '/artifacts/extensions'
        if not os.path.exists(self.home):
            log.warn(f'Extensions artifact directory does not exist at {self.home}')
        self.extensions = {}
        self.interval = interval
        self.update_worker = threading.Thread(target=self.update_state_loop, args=())
        self.update_worker.daemon = True
        self.update_worker.start()

    def update_state(self):
        if not os.path.exists(self.home):
            log.warn(f'Extensions artifact directory does not exist at {self.home}')
            return
        for extensiondir in glob.glob(self.home + '/*/'):
            latestpath = os.path.join(extensiondir, 'latest.json')
            if not os.path.exists(latestpath):
                log.warn(f'Extension directory is missing latest.json at {latestpath}')
                continue
            with open(latestpath, 'r') as fp:
                latest = json.load(fp)

            # Repoint asset urls
            asseturi = URLROOT + os.path.join(extensiondir, latest['versions'][0]['version'])
            latest['versions'][0]['assetUri'] = asseturi           
            for asset in latest['versions'][0]['files']:
                asset['source'] = asseturi + '/' + asset['assetType']
            #log.info(asset)
            name = latest['identity']

            # Map statistics for later lookup
            statistics = {}
            for statistic in latest['statistics']:
                statistics[statistic['statisticName']] = statistic['value']
            latest['stats'] = statistics

            self.extensions[name] = latest
        log.info(f'Loaded {len(self.extensions)} extensions.')

    def update_state_loop(self):
        while True:
            self.update_state()
            log.info(f'Checking for updates in {vsc.Utility.seconds_to_human_time(self.interval)}.')
            time.sleep(self.interval)

    def on_post(self, req, resp):
        if 'filters' not in req.media or 'criteria' not in req.media['filters'][0] or 'flags' not in req.media:
            log.warn(f'Post missing critical components. Raw post {req.media}')
            resp.status = falcon.HTTP_404
            return

        #flags = req.media['flags']
        criteria = req.media['filters'][0]['criteria']
        #pagenumber = req.media['filters'][0]['pageNumber']
        #pagesize = req.media['filters'][0]['pageSize']
        sortorder = vsc.SortOrder(req.media['filters'][0]['sortOrder'])
        sortby = vsc.SortBy(req.media['filters'][0]['sortBy'])
        #log.info(f'Search criteria {criteria}, flags {flags}, page {pagenumber}, limit {pagesize}, sortby {sortby}, sortorder {sortorder}')

        result = self._apply_criteria(criteria)
        self._sort(result, sortby, sortorder)
        resp.media = self._build_response(result)
        resp.status = falcon.HTTP_200

    def _sort(self, result, sortby, sortorder):
        if sortorder == vsc.SortBy.Ascending:
            rev = False
        else:
            rev = True

        if sortby == vsc.SortOrder.PublisherName:
            rev = not rev
            result.sort(key=lambda k: k['publisher']['publisherName'], reverse=rev)

        elif sortby == vsc.SortOrder.InstallCount:
            result.sort(key=lambda k: k['stats']['install'], reverse=rev)

        elif sortby == vsc.SortOrder.AverageRating:
            result.sort(key=lambda k: k['stats']['averagerating'], reverse=rev)

        elif sortby == vsc.SortOrder.WeightedRating:
            result.sort(key=lambda k: k['stats']['weightedRating'], reverse=rev)

        elif sortby == vsc.SortOrder.LastUpdatedDate:
            result.sort(key=lambda k: vsc.Utility.from_json_datetime(k['lastUpdated']), reverse=rev)

        elif sortby == vsc.SortOrder.PublishedDate:
            result.sort(key=lambda k: vsc.Utility.from_json_datetime(k['publishedDate']), reverse=rev)

        else:
            rev = not rev
            result.sort(key=lambda k: k['displayName'], reverse=rev)     

    def _apply_criteria(self, criteria):
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
                for name in self.extensions:
                    if val == self.extensions[name]['extensionId']:
                        result.append(self.extensions[name])

            elif ft == vsc.FilterType.Category:
                log.info(f"Not implemented filter type {ft} for {val}")  
                continue

            elif ft == vsc.FilterType.ExtensionName:                
                for name in self.extensions:
                    if name.lower() == val:
                        result.append(self.extensions[name])    

            elif ft == vsc.FilterType.Target:
                # Ignore the product, typically Visual Studio Code. If it's custom, then let it connect here
                continue

            elif ft == vsc.FilterType.Featured:
                log.info(f"Not implemented filter type {ft} for {val}")
                continue

            elif ft == vsc.FilterType.SearchText:
                for name in self.extensions:
                    # Search in extension name, display name and short description
                    if val in name.lower():                    
                        result.append(self.extensions[name])
                    elif val in self.extensions[name]['displayName'].lower():
                        result.append(self.extensions[name])
                    elif val in self.extensions[name]['shortDescription'].lower():
                        result.append(self.extensions[name])

            elif ft == vsc.FilterType.ExcludeWithFlags:
                # Typically this ignores Unpublished Flag (4096) extensions
                continue

            else:
                log.warn(f"Undefined filter type {crit}")
        
        # Handle popular / recommended
        if len(result) <= 0 and len(criteria) <= 2:
            log.info(f'Search criteria {criteria}')
            result = [ext for ext in self.extensions.values() if 'recommended' in ext and ext['recommended']]

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

    def on_get(self, req, resp):        
        resp.content_type = 'text/html'
        with open('/opt/vscoffline/vscgallery/content/index.html', 'r') as f:
            resp.body = f.read()
        # Hacky af
        resp.body = resp.body.replace('{binaries}', self.simple_binary_list('/artifacts/installers/*/*/*'))
        resp.body = resp.body.replace('{extensions}', self.simple_binary_list('/artifacts/extensions/*/*/*VSIXPackage'))
        resp.status = falcon.HTTP_200

    def simple_binary_list(self, path):
        output = ""
        files = vsc.Utility.files_in_folder(path, False)
        for f in files:
            first_file = vsc.Utility.first_file(f, reverse=True)
            if 'latest.json' in first_file:
                continue
            output += f'<a href="{first_file}">{first_file}</a> <br />'
        return output

class ArtifactChangedHandler(FileSystemEventHandler):

    def __init__(self, gallery):
        self.gallery = gallery

    def on_modified(self, event):
        if 'updated.json' in event.src_path:
            log.info('Detected updated.json change, updating extension gallery')
            self.gallery.update_state()


gallery = VSCGallery()

observer = PollingObserver()
observer.schedule(ArtifactChangedHandler(gallery), '/artifacts/', recursive=False)
observer.start()

application = falcon.API()
application.add_route('/api/update/{platform}/{buildquality}/{commitid}', VSCUpdater())
application.add_route('/extensions/workspaceRecommendations.json.gz', VSCRecommendations()) # Why no compress??
application.add_route('/extensions/marketplace.json', VSCMalicious())
application.add_route('/_apis/public/gallery/extensionquery', gallery)
application.add_static_route('/artifacts/', '/artifacts/')
application.add_route('/', VSCIndex())

if __name__ == '__main__':
    httpd = simple_server.make_server('0.0.0.0', 5000, application)
    httpd.serve_forever()

