# Building from Clean Source Instead of Relying on Existing Local Files

A reliable CI/CD pipeline must be able to build deliverables from source code and inputs explicitly declared in the repository. If a build succeeds only because the machine happens to hold an old JAR file, an outdated generated-source directory, a dependency cached from a prior run, or an uncommitted local configuration file, the result does not accurately reflect the current commit.

**Building from clean source** means starting from a known Git revision in a clean workspace, regenerating derived files via a declared process, and building and testing with controlled toolchains and dependencies. A pipeline must never rely on accidental outputs left behind by a previous run or files that exist only on a single developer's workstation.

This is the foundation of reproducible builds in CI/CD. It helps teams catch missing dependency declarations early, expose host-state assumptions in build scripts, detect stale generated code, and eliminate discrepancies between developer machines and CI environments. A clean build is an essential prerequisite, though it does not by itself guarantee byte-for-byte identical outputs across runs; reproducibility also depends on toolchains, dependencies, configuration, and other sources of nondeterminism.

## 1. What Does "Clean Source" Mean?

A workspace is clean when everything required for the build comes from the selected revision and explicitly declared inputs. Typically, that includes:

- Checking out the exact commit SHA rather than building an arbitrary branch or uncommitted edits.
- Having no stale build outputs, outdated generated files, or personal configuration files altering the outcome.
- Fetching all submodules, Git LFS objects, and auxiliary sources at their recorded revisions.
- Regenerating auto-generated files from schemas, templates, or source inputs using explicitly versioned tools.
- Resolving dependencies and toolchains according to repository configuration and lockfiles.
- Supplying required environment variables and system configuration explicitly.

Clean source does not mean wiping every cache on the machine for every single run. Distinguish workspace files that can influence outputs from dependency caches or build caches keyed by declared inputs. A valid cache can speed up builds when reuse is controlled and preserves correctness.

## 2. Why Existing Local Files Corrupt Results

A build can pass on a developer workstation yet fail in CI or on a fresh machine because the old machine holds state the repository does not provide. Common scenarios include:

| Leftover File or State | Risk | Remediation |
|---|---|---|
| Old JARs, class files, or `build/`, `target/` folders | Builds or tests accidentally consume outputs from an earlier source revision | Provision a fresh workspace or clean build outputs properly before building |
| Stale generated sources | Generated code no longer matches the current schema or template | Run the generation step from declared inputs |
| Uncommitted local config files | Build only works on machines containing that file | Commit non-sensitive config or inject configuration through an explicit mechanism |
| Manually installed dependencies outside lockfiles | Results diverge between local machines and CI | Use dependency declarations, lockfiles, and standard resolution workflows |
| Pre-set local environment variables | Build depends on values not declared by the pipeline | Declare required variables and validate mandatory inputs |
| Untracked or ignored files | Files hidden from normal diffs are still read by build scripts | Use a clean workspace; inspect ignored files when investigating |
| Uninitialized submodules/LFS | Required sources or assets are missing | Initialize submodules and fetch LFS objects per repository configuration |

For example, a Java project updates `src/main/java`, yet a developer's machine still holds `build/classes` from a prior run. If a misconfigured build script packages stale classes, the JAR may contain code that does not match the current commit. A fresh CI machine lacks that directory, so the build fails or yields a different artifact.

Similarly, an OpenAPI schema is updated without regenerating the client. A machine with stale generated sources still compiles, whereas a clean environment uncovers missing classes or incompatible APIs. Clean builds expose these hidden dependencies.

## 3. Creating a Clean Workspace from Git

### Prefer fresh checkouts or ephemeral workspaces

The cleanest approach is provisioning a fresh workspace per CI run, checking out the target commit, and destroying the workspace once the job completes. Ephemeral hosted runners typically provide a fresh workspace per job; for self-hosted runners, explicitly govern directory reuse across runs.

If long-lived runners must be used, isolate each job in its own directory keyed by run ID or commit and clean up per policy. Never let two jobs share a checkout directory, because files emitted by one job can contaminate the next.

### Verifying the revision and Git state

Before building, record the checked-out commit:

```bash
git rev-parse HEAD
git status --short
git diff --exit-code
git diff --cached --exit-code
```

`git rev-parse HEAD` shows the actual commit. The two `diff` commands verify no changes exist in tracked files across the working tree and staging area. `git status --short` surfaces ordinary untracked files. When investigating files masked by `.gitignore`, use `git status --short --ignored` to inspect ignored files as well.

Note: `git status` alone does not prove a workspace lacks ignored files. Build outputs listed in `.gitignore` will not appear in default output yet can still be read by custom scripts. Fresh workspaces are a simpler way to avoid guessing about leftover state.

`git clean` deletes untracked or ignored files and can cause local data loss. Never run destructive variants such as `git clean -xfd` casually on developer machines. To inspect first, use dry-run mode `git clean -ndx` to preview targets; execute deletions only inside ephemeral CI workspaces or after confirming the scope.

### Fetching all auxiliary sources

If a repository uses Git submodules, check out the exact revision recorded in the gitlink. If it uses Git LFS, fetch the actual objects instead of pointer files. If builds depend on Git tags or commit history for versioning, set fetch depth deep enough to retrieve that data.

Example with GitHub Actions:

```yaml
steps:
  - name: Checkout source
    uses: actions/checkout@<FULL_COMMIT_SHA>
    with:
      clean: true
      submodules: recursive
      lfs: true
      fetch-depth: 0
```

`<FULL_COMMIT_SHA>` is a placeholder that must be replaced with a verified full commit SHA. Enable `submodules`, `lfs`, and `fetch-depth` only as needed by the repository; fetching full history can add latency unnecessarily if the build does not rely on Git history or tags. `clean: true` instructs the action to clean tracked/untracked state per its checkout behavior, though it does not replace verifying workspace and runner setup.

## 4. Regenerating Build Outputs and Generated Files

Build outputs are products of the build process, not primary source inputs. Directories such as `build/`, `target/`, `out/`, `dist/`, or `bin/` are typically regenerated on every build and should be excluded via appropriate `.gitignore` rules.

Generated sources fall into two categories:

- **Committed generated sources:** generated files are part of the source revision. Pipelines must verify those files match the underlying schemas/templates per project rules.
- **Build-time generated sources:** files are not committed; pipelines must run the generator from managed inputs prior to compiling or packaging.

Never rely on stale generated files left on a runner. Declare the generator as a task with explicit dependencies, pin the plugin/tool version, and specify outputs. If generation consumes schemas from another repository, pin the corresponding revision or schema version.

Gradle example:

```kotlin
val generateApi by tasks.registering(JavaExec::class) {
    // Configure generator, classpath, and input schema for the project.
    inputs.file("src/main/openapi/orders.yaml")
    outputs.dir(layout.buildDirectory.dir("generated/sources/openapi"))
}

tasks.named("compileJava") {
    dependsOn(generateApi)
}
```

This is an illustrative skeleton; add `mainClass`, `classpath`, arguments, and source set wiring matching your actual generator. Declaring inputs/outputs tells Gradle when the task must re-run and when valid outputs can be reused. Never omit inputs, or Gradle may treat stale outputs as up-to-date even after schemas change.

## 5. Understanding Build Tool Clean Commands

A `clean` command typically deletes build outputs managed by the build tool. It does not necessarily delete every untracked, ignored, or local config file in the repository.

| Tool | Common Command | Primary Scope |
|---|---|---|
| Gradle | `./gradlew clean build` | Deletes project build directories, then executes requested build tasks |
| Maven | `./mvnw clean verify` | Deletes outputs in `target/`, then runs lifecycle phases through `verify` |
| npm | `npm ci` | Installs dependencies cleanly from the lockfile; does not replace a clean workspace |
| Make | `make clean` | Depends on the `clean` target defined in the Makefile |

With Gradle, `clean` deletes project/subproject `build` directories. By default, it does not wipe the entire Gradle user home or dependency cache. With Maven, `clean` deletes `target` per plugin configuration; it does not wipe the local Maven repository. In most cases this is desirable: removing project build outputs while still reusing a managed dependency cache.

Example for a Java project:

```bash
./gradlew --no-daemon clean build
```

Or with Maven Wrapper:

```bash
./mvnw -B clean verify
```

`clean` is useful for verifying that a build does not need stale outputs. However, it does not create a fresh checkout, remove personal configuration files, guarantee identical environments, or make dependencies immutable. Pair it with clean workspaces and controlled inputs.

## 6. When Are Caches Safe to Use?

Caches are performance optimizations, never the project's source of truth. Distinguish between:

- **Dependency caches:** store downloaded packages to avoid re-fetching. With lockfiles, checksums, and trusted repositories, caches can be safely reused.
- **Build caches:** store task outputs keyed by input fingerprints. Safe only when tasks declare complete inputs/outputs and the cache cannot be poisoned.
- **Workspace caches:** preserve the working directory across runs. Most prone to carrying over temp files, generated outputs, or undeclared state, requiring the greatest caution.

A clean build does not have to re-download every dependency from the Internet. If dependency caches are checksum-verified and dependency resolution is locked, caching changes download speed without changing dependency contents. Likewise, a build cache can safely reuse outputs when fingerprints cover every influential input.

When suspecting cache-related drift, run a verification build without the build cache or under a fresh cache namespace to compare. If results diverge, inspect task inputs, cache keys, dependency locks, and cache origins. For release artifacts, record sufficient metadata to tell whether outputs were built directly or restored from cache.

Never share writable caches arbitrarily between untrusted jobs and privileged release jobs. External pull-request jobs may execute third-party code; their caches must not feed production pipelines without isolation and verification.

## 7. Controlling the Docker Build Context

Docker builds can unintentionally bake local host files into images when the build context includes the entire working directory. `COPY . .` copies everything in the context (except paths excluded by `.dockerignore`), allowing stale outputs, `.env` files, caches, or credentials to enter images if left unchecked.

An appropriate `.dockerignore` excludes non-build inputs:

```dockerignore
.git
.gradle
.idea
build
target
out
dist
*.log
.env
```

Adjust this list per project. If an application needs a build-generated file, generate it in an explicit step and copy it deliberately. Never exclude required source files or metadata merely to shrink the build context.

Build images from a clean checkout and record the commit, build arguments, base image digest, and output image digest. The build context itself is an input; two builds of the same commit with different files in the context can produce different images.

## 8. Designing a CI Job That Starts from Clean Source

A reference CI job for a Gradle project might include the following steps:

```yaml
name: clean-source-build

on:
  pull_request:
  push:
    branches: [main]

jobs:
  verify:
    runs-on: ubuntu-24.04
    steps:
      - name: Checkout exact source revision
        uses: actions/checkout@<FULL_COMMIT_SHA>
        with:
          clean: true

      - name: Record source revision
        run: |
          git rev-parse HEAD
          git status --short

      - name: Build and test from clean outputs
        run: ./gradlew --no-daemon clean build

      - name: Verify tracked source was not modified
        run: git diff --exit-code
```

This example uses hosted runners and a placeholder for the action SHA. On self-hosted runners, ensure workspaces are isolated or checkouts are properly cleaned. If builds depend on submodules, Git LFS, or Git tags, add the matching checkout options. If a build updates tracked generated files, the final step may need explicit rules to verify generated sources rather than assuming zero diff.

A complete pipeline typically separates steps as follows:

1. Check out the source revision and fetch all auxiliary sources.
2. Verify the commit, workspace state, and build inputs.
3. Restore a trusted dependency cache or resolve dependencies via lockfiles.
4. Generate derived sources and resources from declared inputs.
5. Run a clean build, unit tests, and required checks.
6. Package artifacts and record commit SHA, toolchain, and digests.
7. Store artifacts alongside test reports and metadata for downstream promotion.

## 9. Testing Whether Builds Are Truly Host-Independent

When a build only ever runs on one machine, hidden file or configuration dependencies are hard to spot. Ways to verify independence:

- Create a fresh clone or worktree at the same commit and build inside that directory.
- Run inside a managed container/runner image with minimal environment variables.
- Temporarily disable the build cache to compare outputs.
- Inspect ignored, untracked, and generated outputs whenever builds behave unexpectedly.
- Clear build-tool outputs using the proper `clean` task before building.
- Compare artifact digests from two independent workspaces if checking byte-level reproducibility.
- Run post-build tests and verify artifacts correspond to the exact commit.

If two clean workspaces at the same commit yield different outputs, compare toolchains, dependency resolution, build arguments, environment variables, timestamps, locale, timezone, and remote data sources. That is how reproducibility investigations work; simply running `clean` repeatedly in one workspace will not catch every hidden dependency.

## 10. Common Failures

| Symptom | Possible Cause | Remedy |
|---|---|---|
| Developer machine builds, CI fails | Local file or pre-installed tool missing in CI | Provision a fresh workspace and declare dependencies/toolchains |
| CI fails first run, passes on retry | First job leaves files consumed accidentally by the next | Fix task dependencies and avoid relying on workspace persistence |
| Clean build misses generated classes | Generator not wired into compile task or outputs wiped | Declare generator task and dependencies accurately |
| Docker build differs from host build | Docker context includes extra files or base image changed | Control `.dockerignore`, build context, and base image digest |
| Build fails only on self-hosted runners | Workspace reused across runs or host-specific config | Isolate workspaces/jobs and capture diagnostics |
| Build stays unstable even after clean | Dependencies/toolchains/OS or nondeterminism changed | Pin inputs, record provenance, and remove variance sources |
| Build cache returns wrong outputs | Task missing input declarations or untrusted cache | Fix input fingerprints, isolate caches, verify without cache |

## 11. Distinguishing Clean Builds from Reproducible Builds

These two concepts are related yet distinct:

- **Clean build:** a build starting from source/workspaces free of undeclared leftover outputs.
- **Reproducible build:** identical controlled inputs produce identical outputs by a chosen criterion, typically matching checksums.

Clean builds eliminate one class of hidden workspace-state dependencies. Reproducible builds additionally require controlling compilers, dependencies, OS, build flags, timestamps, packaging order, network inputs, and other nondeterministic sources. A build can be clean yet still non-reproducible if archives embed the current timestamp or dependencies download from mutable URLs.

Conversely, a build system can reuse a valid build cache and still produce reproducible outputs, provided the cache is keyed by complete inputs and outputs are verified. What must be avoided is relying on random leftover files in a workspace that the pipeline cannot account for.

## 12. Clean-Source Build Checklist

- [ ] Check out the exact commit SHA into a fresh workspace or a strictly cleaned workspace.
- [ ] Verify Git state and inspect untracked/ignored files that could influence the build.
- [ ] Fetch all required submodules, Git LFS objects, and history/tags if needed.
- [ ] Generate derived sources from managed schemas/templates/inputs with pinned tool versions.
- [ ] Clear old build outputs via the appropriate clean task or fresh workspace.
- [ ] Ensure dependency and build caches have proper input keys, checksums, and access boundaries.
- [ ] Control the Docker build context with `.dockerignore` and exclude secrets.
- [ ] Record OS, toolchain, build tool, and environment variables.
- [ ] Link artifacts to their commit, digest, pipeline run, and test reports.
- [ ] Maintain the ability to re-run builds in an independent workspace to diagnose divergence.

When pipelines consistently start from an identified source revision, regenerate outputs through declared workflows, and reuse only verifiable caches, teams no longer depend on accidental machine state. This forms the basis for traceable builds, meaningful tests, and artifacts released faithfully from approved source code.
