# learning-platform-data

Content modules live in `module/`; AI authoring instructions live in `module-generate-agent/`; content management scripts live in `script/`. Draft module structures are in `temp-module/`.

This repository is mounted at `java-learning/learning-platform-data` as a Git submodule.
The main Gradle build tooling lives in the parent `java-learning` repository. Run module-generation and database scripts from this repository directory so commands beginning with `python script/...` resolve correctly. Oracle connection settings are in `.env.oracle-overview` at the root of **this** `learning-platform-data` repository (Git-ignored).

Clone using `git clone --recurse-submodules` and update the submodule pointer in the parent when a new data revision is ready.
