# Change Log for Visual Studio Code - Offline Gallery and Updater

## ToDo
- [X] Cleanup old extension versions
- [X] Cleanup old binary versions
- [X] Include existing extensions in update process
- [ ] Determine VSCode version automatically
- [ ] Shorthands for command line arguments

## `1.0.24` - 2023-06-05
### Fixed
- Improvements to requests session handling to prevent ConnectionErrors due to repeated connections. Thanks @tomer953 for reporting.

### Added
- Note about Firefox in Readme.md. Thanks @jmorcate for highlighting this gap.

### Changed
- Sort gallery listings with simple python sort.
- Removed deprecated logzero dependency, switched to logging. Thanks @bdsoha for the implementation and note.

## `1.0.23` - 2022-11-09
### Fixed
- @forky2 resolved an issue related to incorrect version ordering (from reverse-alphanumberical to reverse-chronological), which prevented extensions updating correctly by vscode clients.

## `1.0.22` - 2022-10-31
### Added
- @maxtruxa added support for specifying docker container environment variable `SSLARGS` to control SSL arguments, or disable SSL by setting `BIND=0.0.0.0:80` and `SSLARGS=` (empty).

### Changed
- @Precioussheep improved consistency of the codebase, reducing bonus code and added typing.

## `1.0.21` - 2022-08-08
### Added
- @tomer953 added support for fetching a specified number of recommended extensions `--total-recommended`.
- @Ebsan added support for fetching pre-release extensions `--prerelease-extensions` and fix fetching other extensions [#31](https://github.com/LOLINTERNETZ/vscodeoffline/issues/31).
- @Ebsan added support for specifying which Visual Studio Code version to masquerade as when fetching extensions `--vscode-version`.

### Changed
- Merge dependabot suggestions for CI pipeline updates.
- Utilise individual requests, rather than a Requests session, for fetching extensions to improve stability of fetch process. Should resolve [#33](https://github.com/LOLINTERNETZ/vscodeoffline/issues/33). Thanks @Ebsan for the fix and @annieherram for reporting.
- Updated build-in certificate and key to update its expiry [#37](https://github.com/LOLINTERNETZ/vscodeoffline/issues/37). Included CA chain aswell. Thanks for reporting @Ebsan.
- Removed platform suport for ia32 builds, as they're no longer provided since ~1.35.
- Split out this changelog.

### Fixed
- @tomer953 removed a duplicate flag to QueryFlags.
- @Ebsan fixed an issue with downloading cross-platform extensions [#24](https://github.com/LOLINTERNETZ/vscodeoffline/issues/24).

## `1.0.20`
### Fixed
- Fixed an issue when downloading multiple versions of extensions. Thanks @forky2!

## `1.0.19`
### Fixed
- Lots of really solid bug fixes. Thank you to @fullylegit! Resilience improvements when fetching from marketplace. Thanks @forky2 and @ebsan.

## `1.0.18`
### Changed
- Meta release to trigger CI.

## `1.0.17`
### Changed
- CORS support for gallery. Thanks @kenyon!

## `1.0.16`
### Changed
- Support for saving sync logs to file. Thanks @ap0yuv!

## `1.0.16`
### Changed
- Improve extension stats handling.

## `1.0.14`
### Fixed
- Fixed insider builds being re-fetched.

## `1.0.13`
### Added
- Added initial support for extension version handling. Hopefully this resolves issue #4.

## `1.0.12`
### Fixed
- @ttutko fixed a bug preventing multiple build qualities (stable/insider) from being downloaded. Thanks @darkonejr for investigating and reporting.

## `1.0.11`
### Fixed
- Fixed bugs in Gallery sorting, and added timeouts for Sync.

## `1.0.10`
### Changed
- Refactored to improve consistency.

## `1.0.9`
### Added
- Added support for Remote Development, currently (2019-05-12) available to insiders. Refactored various badness.

## `1.0.8`
### Added
- Insiders support and extension packs (remotes).
