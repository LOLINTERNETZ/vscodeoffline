# Visual Studio Code - Offline Gallery and Updater

This enables Visual Studio Code's web presence to be mirrored for seamless use in an offline environment (e.g. air-gapped), or to run a private gallery.

In effect, content is served through expected interfaces, without changing any of the publically available binaries. Typically, you would sync the content needing to be availabe on the non-Internet connected system and point the DNS to the mirror service. 

There are two components, **vscsync** which mirrors the content on an Internet connected system, and **vscgallery** which provides the necessary APIs and endpoints necessary to support VS Code's use. While it is designed for offline environments, it is possible, with some DNS trickery, that this could be operated as a "corporate" VS Code gallery.

On the Internet connected system , **vscsync** will:
* Mirror the VS Code installer/update binaries across platforms (Windows|Linux|Darwin);
* Mirror recommended/typical extensions from the marketplace;
* Mirror the malicious extension list; 
* Mirror a list of manually specified extensions (artifacts/specified.json); and
* Optionally, mirror all extensions (--goall, rather than the default of --go).

On the non-Internet connected system, **vscgallery**:
* Implements the updater interface to enable offline updating;
* Implements the extension API to enable offline extension use;
* Implements the malicious extension list; 
* Supports extension search (name, author and short description) and sorting; and
* Supports custom/private extensions (follow the structure of a mirrored extension).

Possible todo list:
* vscgallery - Support paging, if it's really needed (who searches 1000s of extensions anyway).
* Investigate some form of dependency handling (if possible).
* Investigate support for multiple versions of extensions.


## Setting up for full offline use - Using the Docker containers

On the Internet connected system:

1. Acquire/mirror the Docker containers (vscsync/vscgallery). `docker-compose pull`

2. Setup and run the vscsync service on the Internet connected system. `docker-compose up vscsync`
    * Ensuring the artifact directory is accessible to whatever transfer mechanism you will use and vscsync.
    * Run vscsync service and ensure the artifacts are generated.
    * Wait for the sync to complete. You should see 'Complete' and that it is sleeping when the artifacts have finished downloading.

4. Copy the artifacts to the non-Internet connected system.

On the non-Internet connected system:
1. On the non-Internet connected system, ensure the following DNS addresses are pointed toward the vscgallery service.
    * update.code.visualstudio.com
    * az764295.vo.msecnd.net
    * marketplace.visualstudio.com

2. Sort out SSL/TLS within your environment to support offline use. 
    * Either create a certificate which is signed for the above domains, and is trusted by the clients; or
    * Deploy the bundled certificate authorities (vscoffline/vscgallery/ssl/ca.crt and ia.crt), with the obvious security tradeoff.    

3. Run the vscgallery service, ensuring the artifacts are accessible to the service. It needs to listen on port 443. `docker-compose up vscgallery`

4. Navigate to https://update.code.visualstudio.com and hopefully it all works in the browser.

5. ??? (The debug tools in VS Code are useful to see what's going on.)

6. Hopefully it works like magic.


## Setting up for private gallery - Using the Docker containers

1. Setup the vscsync and vscgallery service on the same Docker host.
    * The easiest way is to grab the docker-compose.yml file and edit. 
    * Ensure the docker-compose DNS configuration will override what is configured in step 2 (e.g. vscsync can access the Internet, whereas local hosts are directed toward the vscgallery service).
    * Ensure the artifact folder exists and is shared with both containers.

2. Point the DNS addresses, as described above, to the vscgallery service.

3. Deploy SSL/TLS certificates as necessary, as described above.

4. Run the services - `docker-compose up`

5. Navigate to https://update.code.visualstudio.com and hopefully it all works in the browser.

6. ??? (The debug tools in VS Code are useful to see what's going on.)

7. Hopefully it works like magic.
