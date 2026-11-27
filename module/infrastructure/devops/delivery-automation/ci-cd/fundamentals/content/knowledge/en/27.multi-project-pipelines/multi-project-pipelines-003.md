# Selecting Build Scope in a Monorepo Without Missing Dependencies

A monorepo typically stores multiple applications, libraries, and tools in the same repository. The simplest way to guarantee every change is verified is to build and test all projects after every push. This approach is safe, but it can be very slow when the repository is large, many teams work concurrently, and most changes only affect a few projects.

The opposite optimization—building only the directory with changed files—also carries risk. A change in a shared library can affect dozens of applications; a change to a schema, root config file, or build plugin can impact projects outside the modified directory. If a pipeline misses a consumer, it can report green while a dependent project is already broken.

Therefore, selecting build scope in a monorepo requires combining **the changed file list, project map, and dependency graph**. The pipeline must identify modified projects, find all directly or transitively dependent projects, and then generate a build/test plan in the proper order. When there is insufficient data to prove impact scope, the pipeline must widen the scope or run a full build.

This lesson explains how to identify changed projects, analyze dependency graphs, handle shared files, build selective build/test workflows, control false-green risks, and measure optimization effectiveness. The goal is to reduce unnecessary work while preserving the reliability of quality gates.

## 1. Monorepos and the Change-Scope Identification Problem

A monorepo stores multiple projects in the same repository. Projects can include:

- Independently deployable applications or services.
- Libraries shared across multiple applications.
- Packages or modules containing APIs, schemas, and contracts.
- Build tools, code generation, or migration tools.
- Test suites, fixtures, and test utilities.
- Infrastructure, deployment manifests, and environment configurations.

Example structure:

~~~text
repository/
  apps/
    web-store/
    admin-portal/
    order-api/
  libs/
    ui-components/
    order-domain/
    auth-client/
  schemas/
    events/
    openapi/
  tools/
    codegen/
    build-logic/
  config/
    lint/
    typescript/
  package.json
  lockfile
  build-config/
~~~

If only `apps/web-store` is edited, you may only need to check `web-store` along with the libraries it depends on. However, if `libs/auth-client` is edited, applications using that library also need to be checked. If the root lockfile or shared build logic is edited, the scope may be the entire repository.

The problem poses two questions:

1. **Which projects contain the changed files?** This is the step of mapping paths to the project that owns the files.
2. **Which projects are affected by those projects?** This is the step of querying the dependency graph, specifically reverse dependents.

Solving only the first question misses cascading impacts.

## 2. Project Model and Dependency Graph

Before computing build scope, a repository needs clear project boundaries and metadata describing relationships between them.

A project should have a stable identifier, root directory, project type, and a set of runnable targets:

| Attribute | Example | Meaning |
|---|---|---|
| Project ID | order-api | Stable identifier name |
| Root path | apps/order-api | Directory owning source code and configuration |
| Type | application | Application, library, or tool |
| Targets | lint, test, build, package | CI tasks that can be executed |
| Dependencies | order-domain, auth-client | Projects used by this project |
| Owner | team-orders | Accountable team |

A dependency graph represents dependency relationships. If A uses B, an edge A → B can represent "A depends on B". When B changes, A is potentially affected.

Example:

~~~mermaid
flowchart BT
    D["auth-client"] --> B["order-domain"]
    B --> A["order-api"]
    C["ui-components"] --> E["web-store"]
    D --> E
    F["event-schema"] --> B
    F --> A
~~~

In this diagram:

- `order-api` depends on `order-domain`.
- `order-domain` depends on `auth-client` and `event-schema`.
- `web-store` depends on `ui-components` and `auth-client`.

If `auth-client` changes, not only `auth-client` needs building/testing. Projects depending on it such as `order-domain`, `order-api`, and `web-store` may also need verification. This is reverse dependency traversal.

### 2.1. Distinguishing Direct and Transitive Dependencies

A direct dependency is a relationship declared immediately between two projects. A transitive dependency is a relationship passing through one or more intermediate projects.

Example:

- `order-api` depends on `order-domain`.
- `order-domain` depends on `auth-client`.
- `order-api` does not declare `auth-client` directly, yet can still be affected when `auth-client` changes.

If you only collect direct dependents of `auth-client`, the pipeline will check `order-domain` while skipping `order-api`. You must compute all transitive reverse dependents.

### 2.2. The Graph Must Describe Dependency Types Accurately

Not all relationships are identical. Distinguish them when necessary:

- Build dependency: needs another project to compile or package.
- Runtime dependency: the application calls another service at runtime.
- Test dependency: tests require fixtures, services, or contracts from another project.
- Code generation dependency: source code is generated from a schema or API definition.
- Deployment dependency: one project can only be deployed when another component is ready.

For selective builds, build/test dependencies, generated-code dependencies, and contract dependencies are usually most critical. Runtime dependencies may also require integration/contract tests when APIs or compatibility behavior change.

If the graph only contains dependencies declared in a package manager while ignoring codegen, test fixtures, or shared configurations, the affected projects result can be incomplete.

## 3. Identifying Changed Files with Git

The first step is obtaining the list of files changed between the base revision and the revision under test.

For a pull request, the base revision is typically the merge base between the target branch and source branch. For a push to a branch, you can use the before SHA and after SHA provided by the CI provider. Choose the right commit pair for the trigger type.

Example of finding the merge base and changed file list:

~~~bash
git fetch origin main
BASE="$(git merge-base origin/main HEAD)"
HEAD_SHA="$(git rev-parse HEAD)"

git diff --name-status --find-renames "$BASE" "$HEAD_SHA"
~~~

Using merge base evaluates all changes on the current branch relative to its common ancestor with the target branch. For multi-commit pull requests, using only `HEAD~1` will miss files modified in earlier commits.

In CI, prefer explicit base/head SHAs from the provider. If a shallow clone lacks sufficient history to compute the merge base, fetch additional history. If a reliable base still cannot be determined, run a full build instead of picking a recent commit and guessing.

### 3.1. Handling Renames and Deletions

The change list must preserve file statuses:

| Git Status | Meaning | How to Handle |
|---|---|---|
| A | New file | Map the new path to a project |
| M | Modified file | Map the project owning the file |
| D | Deleted file | Use the old path to identify the affected project |
| R | Renamed file | Inspect both the old path and the new path |
| C | Copied file | Inspect the destination path and ownership rules |

If you only process files still existing in the working tree, the pipeline can miss deleted files. A file renamed from project A to project B can affect both projects. Read `name-status` output or use a structured diff API instead of parsing path strings in ways that lose information.

### 3.2. Distinguishing Working Tree Changes from Commit Changes

CI typically checks a clean commit, but local workflows or some custom pipelines may have uncommitted files. Scope measurement should be based on the revision being built, without unintentionally mixing local uncommitted files into results.

Record the base SHA, head SHA, and list of changed files in logs so the affected-projects decision can be reproduced later.

## 4. Mapping Changed Files to Owning Projects

Once you have changed paths, the pipeline must find the project owning each file.

A simple approach is declaring a root path for each project:

~~~yaml
projects:
  order-api:
    root: apps/order-api
    type: application

  order-domain:
    root: libs/order-domain
    type: library

  auth-client:
    root: libs/auth-client
    type: library

  web-store:
    root: apps/web-store
    type: application
~~~

The file `apps/order-api/src/OrderController.java` belongs to `order-api`. The file `libs/auth-client/src/AuthClient.ts` belongs to `auth-client`.

In practice, you can use project manifests, workspace configuration, or the build system to extract this information rather than maintaining a separate mapping. What matters is that the mapping is validated and has an owner.

### 4.1. Files Outside Any Specific Project

Some files have broad scope:

- Root package manifest or lockfile.
- Shared build scripts and plugins.
- Root compiler configuration.
- Lint rules, formatters, and test runner configurations.
- CI workflows or scripts that compute affected projects.
- Code generation tools.
- Schemas or API contracts used by multiple projects.
- Container base images or toolchain definitions.
- Shared deployment scripts.

Do not assume files outside `apps/` and `libs/` affect no projects. Classify them into:

- Global inputs: changes that can affect all projects or a large set of projects.
- Shared inputs: changes affecting a known group of projects.
- Repository metadata: changes requiring only specific dedicated checks.
- Unknown paths: paths without ownership rules yet, requiring scope expansion or a full build.

### 4.2. Lockfiles and Dependency Manifests

If a repository uses a single root lockfile for the entire workspace, a lockfile change can update dependencies of many projects. When you cannot determine which packages changed and which projects use them, treat the lockfile as a global input.

If each package has its own lockfile, you can map that lockfile to the corresponding project, but you must account for workspace packages or shared dependency resolution.

### 4.3. Inherited Configuration Files

A project may inherit `tsconfig`, lint configs, compiler options, or build logic from root files. When a root file changes, every project referencing it may be affected.

Do not map solely by the directory containing the file. Model configuration relationships or use explicit rules for global/shared files.

## 5. Computing Affected Projects via Reverse Dependency Traversal

After identifying directly modified projects (seed projects), compute the projects that depend on them.

Suppose edge A → B means A depends on B. If B changes, we must collect B and every project that has a path to B in this graph.

General algorithm:

1. Build the set of changed projects from the modified files.
2. If there is a global input, add all projects within the global scope.
3. Enqueue the changed projects.
4. Find all reverse dependents of each project.
5. Add unprocessed projects to the affected set and the queue.
6. Continue until no new projects remain.
7. Return the affected set along with the reason each project was selected.

Pseudo-code:

~~~text
affected = set(changed_projects)
queue = list(changed_projects)

while queue is not empty:
    changed = queue.pop()

    for dependent in reverse_dependencies[changed]:
        if dependent not in affected:
            affected.add(dependent)
            queue.push(dependent)

return affected
~~~

Use a set to avoid duplicate processing when a project has multiple dependency paths to a changed project.

### 5.1. Impact Propagation Example

Suppose the graph is:

- `order-domain` depends on `auth-client`.
- `order-api` depends on `order-domain`.
- `web-store` depends on `auth-client`.
- `admin-portal` does not depend on `auth-client`.

If only `auth-client` is edited, the affected set is:

- `auth-client`.
- `order-domain`.
- `order-api`.
- `web-store`.

`admin-portal` does not need to be built solely for this change, provided the dependency graph is complete and there are no other shared/global inputs.

If `order-api` is edited, only `order-api` and consumers depending on `order-api` (if any) need consideration. There is no need to build every library `order-api` uses merely because they are its dependencies, unless the build target needs to produce them or test policy requires it.

### 5.2. Build Order and Test Order

When A depends on B, B typically must be built before A. Topological sort can produce a valid build order.

Independent projects can run in parallel. Projects with dependencies must respect execution order or use a build system capable of scheduling a task graph.

Do not hardcode ordering by directory name. Derive ordering from the dependency graph and the build system's task graph.

## 6. Changes to the Dependency Graph Require Special Handling

Files declaring dependencies or workspace configuration can also change. For example, `order-api` starts depending on `auth-client`, or a project drops an old dependency.

If you only use the old graph to compute affected projects, the pipeline can miss new relationships. If you only use the new graph, it can miss consumers that previously depended on a library before the dependency was removed.

A safe approach is to compute impact from both the before graph and after graph:

- Use the graph at the base revision to find projects that previously depended on modified/removed components.
- Use the graph at the head revision to find projects that currently depend on modified/added components.
- Take the union of both affected sets.
- If graphs cannot be reliably generated or compared, run a full build.

Changes to project manifests, workspace configuration, build plugins, or the affected-calculation script should be treated as broad-impact changes until checks prove a narrower scope.

### 6.1. Adding or Removing Projects

When a new project is added, test that project and any new consumers. When a project is removed, check projects that previously depended on it to ensure the dependency was cleanly removed or replaced.

If a project is renamed, handle both old and new identifiers so history is not lost and dependencies are not missed.

## 7. Selecting Build, Test, and Lint Targets for Affected Projects

Affected projects is the list of projects to consider. It does not by itself dictate every target that must run.

You can apply policies based on project type and change type:

| Project/Change Type | Targets Typically Required |
|---|---|
| Application source | lint, unit test, build |
| Library source | lint, unit test, build, and test consumers |
| API/schema/contract | validate schema, generate code, contract tests, and consumer tests |
| Test fixtures/shared test utilities | tests of projects using the fixture |
| Build logic/plugins | build/test projects using that logic, often expanded workspace-wide |
| Root lockfile | dependency validation and build/test according to lockfile scope |
| Documentation | link checks, markdown lint, or docs build |
| Deployment manifests | validate manifests and check deployment policies |

A documentation-only change may not require compiling the entire application. However, if documentation is generated from schemas or contains tested code samples, those corresponding checks must still run.

### 7.1. Separating Project Selection from Target Selection

Maintain two independent steps:

- **Project selection:** determine which projects are potentially affected.
- **Target selection:** determine which lint/test/build/contract/deploy validations must run for each project.

Separating these two steps makes policies easier to understand and test. A project might need tests without needing deployment; a schema change might require codegen and contract tests across multiple consumers.

### 7.2. Verifying Library Consumers

When a library's public API changes, testing the library alone is not enough. Consumers may depend on old methods, types, or behaviors.

Run consumer compile/test suites or appropriate contract compatibility tests. If a library has many consumers and the graph does not describe them completely, widen the scope or run a full build.

## 8. Handling Global, Shared, and Unknown Files

Selective builds are only trustworthy when every changed file is mapped or covered by a fallback rule.

Reference policy:

| File Group | Suggested Scope |
|---|---|
| Source inside a project root | Owning project and reverse dependents |
| Shared library | The library and all reverse dependents |
| Root lockfile | Entire workspace, or projects using changed dependencies if precisely analyzed |
| Root build config/plugins | Projects inheriting/using them; full build if unprovable |
| CI workflows or affected scripts | Validate pipeline logic and run full build on sensitive changes |
| Shared schemas | Codegen, contracts, and all consumers |
| Standalone docs files | Docs checks and related project docs |
| Unclassified paths | Full build or require adding an ownership rule |

Do not use rules like "ignore files outside `apps/`". That can skip root build logic or shared configs.

### 8.1. Changes Across Multiple File Groups

A single pull request can modify one project's source, a root config, and a shared schema at once. Merge all impacts into a single affected set, then select corresponding targets. Do not run the same project multiple times just because multiple rules selected it.

### 8.2. Non-Source Changes

Changes such as workflows, build scripts, dependency manifests, base Dockerfiles, or codegen tools can affect the entire repository even though they are outside project roots. Include them in global/shared input policies.

## 9. Generating a Pipeline Plan from the Affected Set

Once you have affected projects and targets, the pipeline should generate an observable and traceable execution plan.

General flow:

~~~mermaid
flowchart TD
    A["Receive base/head revisions"] --> B["Fetch Git diff"]
    B --> C["Classify paths"]
    C --> D["Map paths to seed projects"]
    D --> E{"Any global or unknown inputs?"}
    E -- "Yes" --> F["Expand scope / full build"]
    E -- "No" --> G["Compute reverse dependents"]
    G --> H["Select targets by project and change type"]
    F --> I["Generate execution plan"]
    H --> I
    I --> J["Topological order and parallel scheduling"]
    J --> K["Build / test / lint"]
    K --> L["Aggregate required checks"]
    L --> M["Save affected report and results"]
~~~

The execution plan should record:

- Base SHA and head SHA.
- List of changed paths and their A/M/D/R statuses.
- Owning project for each path.
- Seed projects and selection reasons.
- Affected projects and the dependency paths leading to them.
- Targets selected for each project.
- Full-build reason, if triggered.
- Results of each job and required check.

This lets the team inspect path mapping rules or the dependency graph whenever a project is missed, rather than merely seeing a green pipeline.

## 10. Selective Build Command and Configuration Examples

Monorepo tools often include built-in commands to compute affected projects. Exact syntax depends on the tool and version; always supply explicit base/head revisions.

Example with Nx:

~~~bash
npx nx affected -t lint test build \
  --base=origin/main \
  --head=HEAD
~~~

This command illustrates instructing Nx to compute affected projects from Git changes and run selected targets. Ensure Git history is sufficient to resolve the base and the dependency graph is properly updated.

With multi-project Gradle, you can invoke tasks by project path once scope is determined:

~~~bash
./gradlew :order-domain:test :order-api:test
~~~

This is a concrete task example. Determining affected projects must still rely on the project graph, convention plugins, or repository-specific logic. Do not infer dependencies solely from module names.

### 10.1. Example Plan in YAML

~~~yaml
change_scope:
  base: "origin/main"
  head: "HEAD"
  changed_paths:
    - "libs/auth-client/src/AuthClient.ts"

  seed_projects:
    - auth-client

  affected_projects:
    - auth-client
    - order-domain
    - order-api
    - web-store

  targets:
    auth-client:
      - lint
      - test
      - build
    order-domain:
      - lint
      - test
      - build
    order-api:
      - lint
      - test
      - build
    web-store:
      - lint
      - test
      - build

  fallback:
    full_build: false
    reason: "All changed paths mapped and dependency graph validated"
~~~

The plan is data explaining the decision, not an independent source of truth. It must be generated from a verified revision and graph, and stored alongside the pipeline run.

## 11. Path Filters and Their Common Limitations

Path filters can skip workflows or jobs when changes are unrelated. However, path filters only look at file paths; they do not inherently understand dependency relationships between projects.

For example, editing only `libs/auth-client` while a workflow filters solely on `apps/order-api` will fail to run if the path filter does not recognize the library is used transitively.

Some limitations:

- Do not automatically compute transitive dependents.
- Can miss deleted or renamed files if path handling is incomplete.
- Root configs/lockfiles can impact multiple projects.
- Multi-commit pull requests require accurate base/head comparison.
- CI providers handle skipped workflows/checks differently; a required check may remain pending or fail policy checks.
- Path filters may skip an aggregator workflow needed to report status.

### 11.1. Keeping Required Checks Unambiguous

A safe pattern is having an orchestrator/aggregator job that always runs. This job:

1. Computes changed projects and affected projects.
2. Spawns the necessary verification jobs.
3. Explicitly marks which projects/targets are skipped by policy.
4. Waits for all required jobs to finish.
5. Returns pass only when every mandatory gate passes or is legitimately skipped according to defined rules.

Never let "did not run" be misinterpreted as "verified successfully". Reports should distinguish **PASSED**, **FAILED**, **SKIPPED_BY_POLICY**, and **NOT_EVALUATED**.

## 12. Ensuring Dependency Graph Correctness

Selective builds rely on graph accuracy. If the graph is missing an edge, the pipeline can miss a consumer. If the graph has an extra edge, the pipeline runs more projects than necessary, which is usually still safe.

Thus, when trading off false positives vs. false negatives:

- False positive: building/testing extra unaffected projects, costing extra time.
- False negative: missing an affected project, causing a false green and release risk.

False negatives are far more dangerous. When in doubt, widen the scope.

### 12.1. The Graph Must Be Validated

Checks should include:

- Every project has a unique ID and valid root path.
- Every dependency target exists.
- No cycles exist unless explicitly supported by the build system.
- Every shared config has consumer mappings or a global rule.
- Generated-code inputs and outputs are described.
- New, deleted, and renamed projects are detected.
- The graph is generated from the exact revision under test.
- Graph output is reproducible from the same source and toolchain.

### 12.2. Do Not Blindly Trust Graphs Modified by a Pull Request

A pull request can modify project manifests, affected-calculation scripts, or workflows. If the pipeline uses new logic from the pull request itself to decide which mandatory checks to skip, a change can accidentally or intentionally reduce verification scope.

For critical gates:

- Keep required-check policies in protected configuration.
- Validate changes to the project graph and affected scripts.
- Inspect graphs at both base and head when dependencies change.
- Do not let untrusted changes disable mandatory gates.
- Run a full build or require review when the graph generator/policy changes in an unverified way.

Selective building is an execution optimization; it must never become a way for modified code to choose how strictly it is tested.

## 13. Caching and Artifacts in Selective Builds

Selective builds and caching complement each other, yet solve two different problems:

- Affected analysis decides which projects/targets need to run.
- Caching reuses results or dependencies when corresponding inputs have not changed.

Cache keys must include inputs that can affect results, such as source code, lockfiles, compiler/toolchain, build config, and target. Cache keys that are too broad reduce hit rates; keys that are too narrow can return stale, invalid results.

For remote caches:

- Trust results only from appropriate sources/identities.
- Do not let untrusted pull requests write to caches used by high-privilege releases.
- Separate namespaces or read/write permissions along trust boundaries.
- Attach provenance or metadata to artifacts/cache results when tools support it.
- Verify proper invalidation when graph or cache key logic changes.

If multiple projects use the same artifact or generated output, clearly define the owner and dependencies. Do not rebuild a library in ways that produce different artifacts for each consumer when you can build one deterministic artifact and reuse it.

## 14. When Should You Run a Full Build?

A full build is a necessary fallback mechanism, not a failure of selective builds.

Run a full build when:

- A reliable base/head revision cannot be determined.
- Git history is incomplete and cannot be fetched sufficiently.
- Unclassified paths exist.
- Root build logic, the project graph generator, or the affected algorithm changed.
- Shared configuration has an unclear impact scope.
- Lockfiles or dependency resolution changed and consumers cannot be determined.
- Graph validation fails or unresolvable dependencies exist.
- Cross-cutting changes occur, such as compiler, runtime, toolchain, or codegen updates.
- It is a scheduled nightly run, release candidate, or policy-mandated full repository verification.

You can use selective builds for routine pull requests and run full builds periodically or before releases. Scheduled full builds help uncover hidden dependencies not yet modeled in the current graph.

### 14.1. Fallbacks Must Record a Reason

When a full build is triggered, the report should record a specific reason: **UNKNOWN_PATH**, **GRAPH_INVALID**, **BASE_NOT_FOUND**, **ROOT_BUILD_CONFIG_CHANGED**, or **LOCKFILE_SCOPE_UNKNOWN**. This helps teams add rules to reduce unnecessary fallbacks.

Never silently turn an affected-calculation error into an empty list. If the algorithm fails and returns zero projects, the pipeline might report green without running any checks. Scope analysis failures must fail the job or fall back to a full build.

## 15. Measuring Effectiveness and Tracking False Greens

A faster selective pipeline is not necessarily better if it misses checks.

Track:

| Metric | Meaning |
|---|---|
| Affected project count | Number of projects selected per change |
| Full-build fallback rate | Percentage of changes falling back to full build |
| Pipeline duration | End-to-end execution time |
| Required-check completion | Percentage of mandatory gates completing properly |
| Cache hit rate | Percentage of results/dependencies reused |
| Graph validation failures | Count of invalid graph detections |
| Unknown path rate | Percentage of files lacking ownership rules |
| Missed impact incidents | Incidents where missed projects were found post-merge/release |

No single metric proves selective building is correct. Validate periodically by running full builds on a sample of changes and comparing outcomes with selective builds. If a full build catches an error that a selective build missed, that is a signal to fix the graph or policy.

### 15.1. Shadow Validation

You can run affected analysis in shadow mode:

- The pipeline still uses a full build for the authoritative outcome.
- Collect the list of projects the selective algorithm would have selected.
- Compare against the project scope checked by the full build.
- Analyze discrepancies and fix mappings/graphs.
- Enable selective builds only after sufficient evidence and review.

Shadow mode is especially valuable when onboarding a monorepo onto selective CI or changing the affected algorithm.

## 16. Sample Scenario: Modifying a Shared Library

Suppose a developer edits a single function in `libs/auth-client`. The repository has:

- `order-domain` depending on `auth-client`.
- `order-api` depending on `order-domain`.
- `web-store` depending on `auth-client`.
- `admin-portal` not depending on `auth-client`.

Workflow:

1. The pipeline receives the pull request's base SHA and head SHA.
2. Git diff identifies that a file in `libs/auth-client` changed.
3. Path mapping selects `auth-client` as a seed project.
4. The dependency graph is validated and confirmed valid.
5. Reverse traversal finds `order-domain`, `order-api`, and `web-store`.
6. The pipeline forms the affected set: `auth-client`, `order-domain`, `order-api`, and `web-store`.
7. Build order follows dependencies: `auth-client` before `order-domain`, then `order-api`; `web-store` can run in parallel after `auth-client`.
8. Run lint/test/build for the corresponding targets.
9. `admin-portal` is skipped per the verified dependency graph.
10. The aggregator job waits for all required checks and publishes the result.
11. The pipeline records changed paths, graph revision, affected list, and the reason for skipping `admin-portal`.

If the same pull request also modifies root compiler config, the global policy can widen scope to all projects. If the graph cannot be verified, the pipeline falls back to a full build.

## 17. Practice Roadmap

You can practice on a sample monorepo following these steps:

1. **List projects:** record project ID, root path, type, owner, and targets.
2. **Draw the dependency graph:** declare build, test, codegen, and contract dependencies.
3. **Generate a Git diff:** use appropriate base/head SHAs and test add/modify/delete/rename.
4. **Map changed paths:** identify owning projects and global/shared/unknown groups.
5. **Compute reverse dependents:** test changing a shared library and verify all consumers are selected.
6. **Test transitive dependencies:** create chain A depends on B, B depends on C; edit C and verify A is selected.
7. **Handle graph changes:** add/remove a dependency and compare impacts from base/head graphs.
8. **Select targets:** determine lint/test/build/contract tests by project type and change type.
9. **Generate an execution plan:** save base/head, changed paths, seeds, affected, targets, and fallback reasons.
10. **Test global inputs:** edit root lockfile or build config and verify scope widens properly.
11. **Test unknown paths:** create a file without an ownership rule and verify a full build is triggered.
12. **Verify the aggregator job:** ensure policy skips are distinguished from passes and all required checks report results.
13. **Compare with full builds:** run shadow validation and look for discrepancies.
14. **Measure effectiveness:** compare pipeline duration, affected count, and missed impact incidents.

### Completion Criteria

Learners can consider the practice complete when they can demonstrate:

- Accurately identifying base/head revisions for pull requests and pushes.
- Handling added, modified, deleted, and renamed files.
- Mapping files to project owners.
- Distinguishing direct dependencies from transitive reverse dependencies.
- Computing the complete set of affected projects from the dependency graph.
- Handling root configs, lockfiles, schemas, build logic, and unknown paths.
- Ordering builds by dependencies and running safe tasks in parallel.
- Separating project selection from target selection.
- Preventing path filters or graph errors from producing false greens.
- Providing a full-build fallback with explicit reasons.
- Persisting execution plans and affected-analysis evidence.
- Comparing selective builds with full builds to verify coverage.

## Conclusion

Selecting build scope in a monorepo requires more than finding directories with modified files. Pipelines must determine accurate base/head revisions, map changed paths to project owners, detect global/shared inputs, and compute all reverse dependents in the dependency graph. Only then should they select targets and schedule builds/tests in dependency order.

Selective builds reduce unnecessary work when the graph is complete and the algorithm is verified. When graphs, path mappings, or revisions are untrustworthy, a full build is the right fallback. Execution plans, aggregated required checks, shadow validation, and tracking missed-impact incidents ensure time optimization never comes at the expense of CI/CD reliability.
