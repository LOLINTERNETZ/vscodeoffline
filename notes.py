if config.sync or config.syncall:
    config.checkbinaries = True
    config.checkextensions = True
    config.updatebinaries = True
    config.updateextensions = True
    config.updatemalicious = True
    config.checkspecified = True
    if not config.frequency:
        config.frequency = '12h'

# Methods to grab extension list
mp.search_by_text(config.extensionsearch)
mp.search_by_extension_name(config.extensionname)
mp.get_recommendations(os.path.abspath(config.artifactdir))
mp.get_specified(specifiedpath)