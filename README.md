# Visual Studio Code - Offline Gallery and Updater

This enables Visual Studio Code's web presence to be mirrored for seamless use in an offline environment (e.g. air-gapped), or to run a private gallery.

In effect, content is served through expected interfaces, without changing any of the publicly available binaries. Typically, you would sync the content needing to be availabe on the non-Internet connected system and point the DNS to the mirror service. __No binaries nor extensions are modified.__


## Features

On the Internet connected system , **vscsync** will:
* Mirror the VS Code installer/update binaries across platforms (Windows|Linux|Darwin) and builds (stable|insider);
* Mirror recommended/typical extensions from the marketplace;
* Mirror the malicious extension list; 
* Mirror a list of manually specified extensions (artifacts/specified.json); and
* Optionally, mirror all extensions (--syncall, rather than the default of --sync).

On the non-Internet connected system, **vscgallery**:
* Implements the updater interface to enable offline updating;
* Implements the extension API to enable offline extension use;
* Implements the malicious extension list; 
* Implements initial support for multiple versions;
* Supports extension search (name, author and short description) and sorting;
* Supports custom/private extensions (follow the structure of a mirrored extension); and
* Supports Remote Development.

Possible TODO List:
* vscgallery - Support paging, if it's really needed (who searches 1000s of extensions anyway).
* Investigate some form of dependency handling (if possible).
* Add test cases.

## Requirements
* Docker (ideally with docker-compose for simplicity)

## Getting Started - Full Offline Use - Using Docker Containers

There are two components, **vscsync** which mirrors the content on an Internet connected system, and **vscgallery** which provides the necessary APIs and endpoints necessary to support VS Code's use. While it is designed for offline environments, it is possible, with some DNS trickery, that this could be operated as a "corporate" VS Code gallery.

On the Internet connected system:

1. Acquire/mirror the Docker containers (vscsync/vscgallery). 

    `docker-compose pull`

2. Setup and run the vscsync service on the Internet connected system.
    * Ensuring the artifact directory is accessible to whatever transfer mechanism you will use and vscsync.
    * Run vscsync service and ensure the artifacts are generated.
    * Wait for the sync to complete. You should see 'Complete' and that it is sleeping when the artifacts have finished downloading.

    `docker-compose up vscsync`

4. Copy the artifacts to the non-Internet connected system.

On the non-Internet connected system:

1. On the non-Internet connected system, ensure the following DNS addresses are pointed toward the vscgallery service.
    * update.code.visualstudio.com
    * main.vscode-cdn.net
    * marketplace.visualstudio.com

    This may be achieved using a corporate DNS server, or by modifying a client's host file.

2. Sort out SSL/TLS within your environment to support offline use. 
    * Either create a certificate which is signed for the above domains, and is trusted by the clients; or
    * Deploy the bundled root and intermediate certificate authority (vscoffline/vscgallery/ssl/ca.crt and ia.crt), with the obvious security tradeoff.

    **Windows 10**: Import the certificates into the machine's trusted root certificate authority (Start > "Manage Computer Certificates").

    **Darwin**: Import the certificates into the machine's trusted root certificate authority.

    **Ubuntu**: Easiest method seems to be Open Chrome, navigate to 
    chrome://settings/certificates, select authorities and add the certificates. Firefox on Ubuntu maintains its own certificate store. Either add the root CA, or switch Firefox to use OS provided certificates (see: https://github.com/LOLINTERNETZ/vscodeoffline/issues/43#issuecomment-1545801875). 

3. Run the vscgallery service, ensuring the artifacts are accessible to the service. It needs to listen on port 443.

    `docker-compose up vscgallery`

4. Using Chrome/Firefox navigate to https://update.code.visualstudio.com. You should not see any certificate warnings, if you do it's unlikely to work in VS Code.

5. Open VS Code, hopefully you can magically install extensions and update the install. The Help > Developer Tools > Network should tell you what is going on.

Note: Chrome, rather than other browsers, will likely give you a better indication as to what is going on as VS Code and Chrome share the same certificate trust.


## Getting Started - Standalone Install (Testing or Private Gallery) - Using Docker Containers
This guide will setup the vscsync and vscgallery service on the same Docker host. 

1. Grab the docker-compose.yml file.
    * Ensure the docker-compose DNS configuration will override what is configured in step 2 (e.g. vscsync can access the Internet, whereas local hosts are directed toward the vscgallery service).
    * Ensure both containers will mount the same artifact folder.

2. Point the DNS addresses to the vscgallery service.
    * update.code.visualstudio.com
    * main.vscode-cdn.net
    * marketplace.visualstudio.com

    This may be achieved using a corporate DNS server, or by modifying a client's host file.

3. Deploy SSL/TLS certificates as necessary, as described above.

4. Run the services

    `docker-compose up`

5. Using Chrome navigate to https://update.code.visualstudio.com. You should not see any certificate warnings, if you do it's unlikely to work in VS Code.

6. Open VS Code, hopefully you can magically install extensions and update the install. The Help > Developer Tools > Network should tell you what is going on.


## Sync Arguments (vscsync)
These arguments can be passed as command line arguments to sync.py  (e.g. --varA or --varB), or passed via the Docker environment variable `SYNCARGS`.

### Typical Sync Args:
 * `--sync` To fetch stable binaries and popular extensions.
 * `--syncall` To fetch everything (stable binaries, insider binaries and all extensions).
 * `--sync --check-insider` To fetch stable binaries, insider binaries and popular extensions.

 ### Possible Args:
```
usage: sync.py [-h] [--sync] [--syncall] [--artifacts ARTIFACTDIR] [--frequency FREQUENCY] [--check-binaries] [--check-insider] [--check-recommended-extensions] [--check-specified-extensions] [--extension-name EXTENSIONNAME] [--extension-search EXTENSIONSEARCH] [--prerelease-extensions]
               [--update-binaries] [--update-extensions] [--update-malicious-extensions] [--skip-binaries] [--vscode-version VERSION] [--total-recommended TOTALRECOMMENDED] [--debug] [--logfile LOGFILE] [--include-existing] [--skip-existing] [--garbage-collection]

Synchronises VSCode in an Offline Environment

options:
  -h, --help            show this help message and exit
  --sync, -s            The basic-user sync. It includes stable binaries and typical extensions
  --syncall, -a         The power-user sync. It includes all binaries and extensions
  --artifacts ARTIFACTDIR, -d ARTIFACTDIR
                        Path to downloaded artifacts
  --frequency FREQUENCY, -f FREQUENCY
                        The frequency to try and update (e.g. sleep for '12h' and try again)
  --check-binaries      Check for updated binaries
  --check-insider, -i   Check for updated insider binaries
  --check-recommended-extensions
                        Check for recommended extensions
  --check-specified-extensions, -w
                        Check for extensions in <artifacts>/specified.json
  --extension-name EXTENSIONNAME, -n EXTENSIONNAME
                        Find a specific extension by name
  --extension-search EXTENSIONSEARCH
                        Search for a set of extensions
  --prerelease-extensions, -p
                        Download prerelease extensions. Defaults to false.
  --update-binaries, -b
                        Download binaries
  --update-extensions, -u
                        Download extensions
  --update-malicious-extensions, -m
                        Update the malicious extension list
  --skip-binaries, -B   Skip downloading binaries
  --vscode-version VERSION, -v VERSION
                        VSCode version to search extensions as.
  --total-recommended TOTALRECOMMENDED
                        Total number of recommended extensions to sync from Search API. Defaults to 500
  --debug               Show debug output
  --logfile LOGFILE, -l LOGFILE
                        Sets a logfile to store loggging output
  --include-existing, -e
                        Include existing extensions in the update process
  --skip-existing, -E   Skip inclusion of existing extensions in the update process
  --garbage-collection, -g
                        Remove old versions of artifacts (binaries / extensions)
  ```
