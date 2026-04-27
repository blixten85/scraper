# Changelog

## [1.8.0](https://github.com/blixten85/scraper/compare/v1.7.2...v1.8.0) (2026-04-27)


### Features

* consolidate app services into single image ([cc91614](https://github.com/blixten85/scraper/commit/cc9161400d8d796f6e732096c40d6998b315f6e7))

## [1.7.2](https://github.com/blixten85/scraper/compare/v1.7.1...v1.7.2) (2026-04-27)


### Bug Fixes

* auto-detect name/URL normalization in scraper config UI ([7af5f4e](https://github.com/blixten85/scraper/commit/7af5f4ef7fe1cf268bb7062af36d89b793d10361))

## [1.7.1](https://github.com/blixten85/scraper/compare/v1.7.0...v1.7.1) (2026-04-27)


### Bug Fixes

* add path validation to api_request to prevent SSRF ([0539f42](https://github.com/blixten85/scraper/commit/0539f428103523dcb7b308074547c0ae7664ea43))

## [1.7.0](https://github.com/blixten85/scraper/compare/v1.6.0...v1.7.0) (2026-04-26)


### Features

* add postgres permission init container and daily pg_dump backup ([bf7ce31](https://github.com/blixten85/scraper/commit/bf7ce31ffa7ef7a99873a519fe77d76d5e345ef8))

## [1.6.0](https://github.com/blixten85/scraper/compare/v1.5.0...v1.6.0) (2026-04-26)


### Features

* **webui:** replace spider icon with custom SVG; fix page load performance ([937bdb7](https://github.com/blixten85/scraper/commit/937bdb725351af07334322b27843c67a20df6dbc))

## [1.5.0](https://github.com/blixten85/scraper/compare/v1.4.0...v1.5.0) (2026-04-26)


### Features

* add price history, deals, pagination, and auto-detect selectors ([41adac8](https://github.com/blixten85/scraper/commit/41adac8dbe7ad78f07900cc1c48985c9486f2a1a))

## [1.4.0](https://github.com/blixten85/scraper/compare/v1.3.1...v1.4.0) (2026-04-26)


### Features

* **webui:** redesign UI with dark/light theme toggle ([db27030](https://github.com/blixten85/scraper/commit/db27030480b1091e407ec39378e5599e30f5f01c))

## [1.3.1](https://github.com/blixten85/scraper/compare/v1.3.0...v1.3.1) (2026-04-26)


### Bug Fixes

* resolve code scanning alerts ([ac1c657](https://github.com/blixten85/scraper/commit/ac1c657c21f20d3386b73150ababa11b69b226b6))

## [1.2.2](https://github.com/blixten85/scraper/compare/v1.2.1...v1.2.2) (2026-04-26)


### Bug Fixes

* resolve code scanning alerts ([ac1c657](https://github.com/blixten85/scraper/commit/ac1c657c21f20d3386b73150ababa11b69b226b6))

## [1.2.1](https://github.com/blixten85/scraper/compare/v1.2.0...v1.2.1) (2026-04-25)


### Bug Fixes

* **scraper:** set scraping_active flag in manual trigger path ([a823ec2](https://github.com/blixten85/scraper/commit/a823ec2d3cbc537d412c32d6b13a11425d5f4ba5))

## [1.2.0](https://github.com/blixten85/scraper/compare/v1.1.0...v1.2.0) (2026-04-25)


### Features

* **scraper:** add subcategory pagination mode and fix inet.se config ([a0e7bb2](https://github.com/blixten85/scraper/commit/a0e7bb203561cb0fbbc05a68ae3a2be4dddc1f14))


### Bug Fixes

* **docker:** replace curl healthcheck with python urllib ([bbe1a18](https://github.com/blixten85/scraper/commit/bbe1a18b1e635199f08186c4c3767f7bf5692273))
* **docker:** use correct scraper-engine image name ([7a093de](https://github.com/blixten85/scraper/commit/7a093de8ec0b109442455aa2841c2277df03a358))
* **export:** wire up CSV export through webui ([43acda7](https://github.com/blixten85/scraper/commit/43acda7e97e83f72a9a21183a0ccb37f916b97ad))
* **scraper:** add 60s hard timeout around element extraction loop ([02fdc70](https://github.com/blixten85/scraper/commit/02fdc7099836684d2589709c7d93cc6da1b040fa))
* **scraper:** add asyncio timeout to page.evaluate() calls in infinite scroll ([f8616d4](https://github.com/blixten85/scraper/commit/f8616d4a9ee640c82dfd5edfe28d3d4c177f68e9))
* **scraper:** set 30s default timeout on all page operations ([2c02e75](https://github.com/blixten85/scraper/commit/2c02e75756ad7379ce76e70ca211ec3ddc8cda9b))
* **webui:** add SSRF path validation to engine_request ([f3c68f8](https://github.com/blixten85/scraper/commit/f3c68f88129ce5e01306df088ad4eba66488185f))

## [1.1.0](https://github.com/blixten85/scraper/compare/v1.0.1...v1.1.0) (2026-04-25)


### Features

* add dual push to GHCR and Docker Hub for all services ([88628e4](https://github.com/blixten85/scraper/commit/88628e4c0bf7a92f4f73e8293dc380fb4979bc2e))
* **scraper:** replace partial scroll with infinite-scroll-aware loop ([39e5c16](https://github.com/blixten85/scraper/commit/39e5c1664cd1510fdcf2f169c4e47f003e6647ce))
* update scraper/scraper.py [skip ci] ([0d8f8f4](https://github.com/blixten85/scraper/commit/0d8f8f424705270b7e1a998195641d90a8647168))


### Bug Fixes

* add missing jobs section to build workflows ([4cb8687](https://github.com/blixten85/scraper/commit/4cb86878e2d816d6077ad3159498ffe92eae54a4))
* **alerts:** narrow exception types to satisfy CodeQL ([724508f](https://github.com/blixten85/scraper/commit/724508fd64a227a61cbab67db9fbd61e2c096a64))
* badge README.md ([92f51ca](https://github.com/blixten85/scraper/commit/92f51ca07ba14bea7b95521e27b52aef505ac9ec))
* **ci:** add issues write permission to release workflow and remove duplicate ([d480109](https://github.com/blixten85/scraper/commit/d4801099071b7adcdc19d31234504a4f26b319fa))
* **ci:** exclude Dependabot PRs from auto-rebase to prevent foreign commits ([032f4df](https://github.com/blixten85/scraper/commit/032f4df26d0509786a11a33ff714c582fe10eb9b))
* correct active_configs, port configuration, API security and error handling ([531cc59](https://github.com/blixten85/scraper/commit/531cc59936e55bffe2803b0bb26c646a8c9c97ce))
* correct release-please action inputs and permissions ([a15eb8c](https://github.com/blixten85/scraper/commit/a15eb8c86ce194577d229a79c0d5d5d4986f5de1))
* Corrected version number .github/.release-please-manifest.json ([1eeb633](https://github.com/blixten85/scraper/commit/1eeb6336fcb8ea6553fa851818320956ac200fcb))
* eliminate zombie processes from Playwright Chrome instances ([03830fd](https://github.com/blixten85/scraper/commit/03830fdda6399c2a019b7f48b28634f56ac20af4))
* remove duplicate CodeQL workflow, use default setup ([5c97bb0](https://github.com/blixten85/scraper/commit/5c97bb0275d8459bec06832789a55d35def85068))
* remove duplicate dependabot entries ([b792cf1](https://github.com/blixten85/scraper/commit/b792cf171b874c2e8b899292585f726a53f9730d))
* resolve all CodeQL security alerts ([83b5772](https://github.com/blixten85/scraper/commit/83b57720d432f79d40ffa879b28e86dd9ae285ad))
* **scraper:** guard empty selectors and fix re.escape on regex patterns ([4d61f3e](https://github.com/blixten85/scraper/commit/4d61f3e571f8a8a0b755329d653b0c8b0af17a48))
* Updated README.md ([b654be6](https://github.com/blixten85/scraper/commit/b654be6cb68546ecdfe243ac6ee9a0a5acd3c8ec))
* upgrade Flask-Cors to &gt;=6.0.0 for CVE-2024-6221 ([ad7dfe2](https://github.com/blixten85/scraper/commit/ad7dfe21f5f61e36fd8a60441a55f96e6bdcd770))
* upgrade Flask-Cors to &gt;=6.0.0 in scraper and webui ([c052efd](https://github.com/blixten85/scraper/commit/c052efd044f07e7d7b72f5e8828c225da09227b6))
* upgrade requests to &gt;=2.33.0 in alerts and webui ([72f48ee](https://github.com/blixten85/scraper/commit/72f48ee331cca55aa094de997ea37efa6a9c5cff))
* use GHCR_TOKEN for release-please and add Node.js 24 compat ([2fe8287](https://github.com/blixten85/scraper/commit/2fe82877a7421838d1c69837235fe03894686dbe))
