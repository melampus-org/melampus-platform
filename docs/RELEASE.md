# Releases

`VERSION` is the authoritative platform package version. Match its section in CHANGELOG.md.
A version-change PR runs the same guard as melampus-python. After merge, release.yml
runs `make ci`, creates an annotated vX.Y.Z tag and publishes validated wheel and
source assets as an alpha GitHub release. Re-running an already completed release is idempotent.
Never create release tags manually. SDK and platform versions are independent.
The SDK dependency is pinned to a published GitHub release wheel; PyPI is not required.

Install a release:

```sh
pip install "https://github.com/melampus-org/melampus-platform/releases/download/v0.1.0/melampus_platform-0.1.0-py3-none-any.whl"
melampus-platform --demo
```
