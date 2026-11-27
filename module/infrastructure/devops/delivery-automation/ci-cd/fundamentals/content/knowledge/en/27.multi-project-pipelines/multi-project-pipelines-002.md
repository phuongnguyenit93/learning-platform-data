# Detecting Impact of Shared Code and Libraries

In a multi-project system, a small change in a shared library can require many services to be recompiled, retested, or re-released. If a pipeline only runs tests for the modified library, compatibility bugs can slip into projects that consume that library. Conversely, if every change triggers the entire system, feedback time increases and development teams struggle to see the true scope of a change.

Impact analysis helps a pipeline answer three questions before selecting which jobs to run:

- Which projects directly contain the modified code or configuration?
- Which projects depend on them directly or indirectly?
- What level of verification does each affected project need before being allowed to produce an artifact or release?

The goal is to determine a justified testing scope from dependency relationships, keep feedback fast, and still protect contracts across projects.

## 1. Why Does Shared Code Change CI/CD Scope?

A project often contains many types of components: independently deployable applications, internal libraries, data models, API schemas, build plugins, test configurations, and pipeline conventions. A shared component can be used by many projects.

For example, an order model library is used by both an order-intake API and a billing worker. When the library renames a field, both applications may fail to compile. When the library still compiles but changes how order statuses are interpreted, bugs may only surface during integration tests or at runtime. Therefore, a library passing its own unit tests does not prove that its consuming projects still work properly.

Impact scope does not reside solely in the directory containing the modified file. It is determined by the relationships between the changed component and the components that use it.

## 2. Modeling Dependency Relationships

### 2.1. Distinguishing Projects, Components, and Artifacts

In CI/CD analysis, you must define the boundaries that the pipeline can build and verify:

- **Project:** a unit that can be selected to build, test, package, or deploy, such as a Gradle application or a service.
- **Shared component:** a library, schema, plugin, configuration, or test suite used by multiple projects.
- **Artifact:** an identifiable and distributable output, such as a JAR, container image, or library package.

A library can be a project in a monorepo and produce a JAR. An application can depend on the library project at build time, then package that JAR into the application artifact. During impact analysis, you must preserve the link from source code to consuming projects and the final artifact.

### 2.2. Reading Dependency Edge Directions Correctly

There are two common ways to represent the graph:

- Edges from the consuming project to the used project: application → library.
- Edges from the library to the project using it: library → application.

Both are valid, but the pipeline must follow one consistent convention. In this article, diagrams use the second direction so impact flows along the arrow direction: when a library changes, we follow outgoing edges to find consuming projects.

Example:

~~~mermaid
flowchart TD
    contracts["Order contract library"]
    auth["Auth SDK"]
    logging["Logging library"]
    orders["Order API"]
    invoices["Invoice Worker"]

    contracts --> orders
    contracts --> invoices
    auth --> orders
    logging --> auth
    logging --> invoices
~~~

The arrow means "is used by". Order API directly depends on the order contract library and Auth SDK. Auth SDK in turn uses the logging library. Therefore, when the logging library changes, Order API can still be affected even though it does not declare a direct dependency on that library.

### 2.3. Identifying Direct and Transitive Dependencies

- **Direct dependency:** a project declares that it uses another library or project.
- **Transitive (indirect) dependency:** a project uses a component that itself depends on the recently changed component.
- **Build-time dependency:** required for compiling, packaging, or code generation.
- **Runtime dependency:** required when the application runs, even if it does not appear on the compile classpath.
- **Test dependency:** shared test fixtures, datasets, mock servers, or testing libraries.
- **Release dependency:** base images, manifests, deployment charts, pipeline templates, or environment configurations that affect artifacts or how they are deployed.

Graphs provided by build tools usually describe build relationships well, but can miss runtime relationships. For example, an application looks up implementations via reflection, service discovery, class names in configuration, or dynamically loaded plugins. These relationships must be explicitly declared or guarded by integration tests.

Do not assume every file in the same directory has the same impact scope. Project boundaries and dependency metadata are the proper basis for selecting CI work.

## 3. From Changed Files to Affected Projects

A pipeline typically starts with a diff list of files between the current commit and the base commit of the target branch. From this list, it determines which projects own those files, then expands the scope along the dependency graph.

### 3.1. Choosing the Right Comparison Range

For a pull request or merge request, compare the commit under test with the appropriate merge base or target commit. Comparing against an outdated commit by mistake can include files unrelated to the current change or miss files that actually changed.

Analysis must also handle newly added, deleted, and renamed files. If you only collect files that still exist in the new commit, a deleted project or configuration could disappear from the analysis results.

### 3.2. Mapping Files to Projects

Each path must be assigned to the project or configuration scope that owns it. You can use directory structure, build tool declarations, or a team-maintained metadata file.

Example:

| Changed Path | Owning Project or Scope |
|---|---|
| **services/order-api/src/** | Order API |
| **services/invoice-worker/src/** | Invoice Worker |
| **libraries/order-contract/src/** | Order contract library |
| **build-logic/** | Projects applying the build logic |
| **gradle/libs.versions.toml** | Projects using the changed alias or version |
| **.ci/templates/java.yml** | Pipelines using the Java template |

The mapping table must reflect the actual structure of the repository. Do not assume every change in the root directory affects all projects if the configuration has a narrow scope; likewise, do not ignore a root file that is actually used by every project.

### 3.3. Expanding Through Consuming Projects

Suppose the set of projects containing changes is **C**. With the edge convention from dependency to consumer, the set of projects to consider is:

~~~text
Affected(C) = C ∪ all consumers reachable from C
~~~

For a library project, expansion must traverse both direct and transitive consumers. If library A is used by B, and B is used by application C, a change in A can affect both B and C.

Analysis results should record why a project was selected—for example, "used directly by Order API" or "transitively dependent via Auth SDK". This reasoning helps reviewers understand why the pipeline runs a set of tests and helps investigate when analysis results are wrong.

## 4. Classifying Changes to Select Verification Depth

The graph shows which projects are potentially affected. The change type and risk level determine how deeply they must be verified.

| Change Type | Scope to Consider | Appropriate Verification |
|---|---|---|
| Modifying internal application logic | The modified application and related integration flows | Unit tests, flow-based integration tests |
| Modifying shared library logic | The library and its direct and transitive consumers | Library tests, compiling and testing consumers |
| Changing public APIs, data types, or schemas | All consumers of the contract | Compatibility checks, contract tests, and integration tests |
| Changing dependencies or version catalogs | Projects whose resolved dependencies changed | Build, test, and dependency security scanning |
| Changing shared plugins, conventions, or build logic | Projects applying that logic | Build and test projects within the applied scope |
| Changing shared test fixtures or test utilities | Projects using the fixture or utility | Run tests of related consumers |
| Changing base images or shared deployment configs | Images or services inheriting the config | Image build, config checks, and appropriate smoke tests |

A change should only be called "internal" when there is evidence that it does not alter observable behavior for consumers. Internal algorithm changes can still change outputs, processing times, event ordering, or error handling. Therefore, when contracts and tests are not strong enough to rule out impact, keep consumers in the verification scope.

Testing can be organized into multiple tiers:

1. **Build and unit tests:** confirm the changed project still compiles and verifies its own logic.
2. **Compatibility checks:** confirm consumers can compile or exchange data with the new contract version.
3. **Contract and integration tests:** confirm both sides agree on requests, responses, schemas, events, and behavior.
4. **End-to-end or smoke tests:** confirm critical business flows still work when components are assembled together.

Not every change needs to run every testing tier. However, skipping a tier must be justified by change classification, the dependency graph, and existing test evidence.

## 5. Example with a Java and Gradle Monorepo

Suppose a repository has the following projects:

~~~text
root
├── applications
│   ├── order-api
│   └── invoice-worker
└── libraries
    ├── order-contract
    ├── auth-sdk
    └── common-logging
~~~

Order API and Invoice Worker both use the order contract library. Order API additionally uses Auth SDK. Auth SDK and Invoice Worker both use the logging library.

In Order API's build script, project relationships can be declared as follows:

~~~kotlin
dependencies {
    implementation(project(":libraries:order-contract"))
    implementation(project(":libraries:auth-sdk"))
}
~~~

In Invoice Worker's build script:

~~~kotlin
dependencies {
    implementation(project(":libraries:order-contract"))
    implementation(project(":libraries:common-logging"))
}
~~~

Auth SDK declares a dependency on the logging library:

~~~kotlin
dependencies {
    implementation(project(":libraries:common-logging"))
}
~~~

### 5.1. When the Contract Library Changes

If a change is in **libraries/order-contract**, the projects to consider include:

- **libraries:order-contract:** the project containing the change.
- **applications:order-api:** direct consumer.
- **applications:invoice-worker:** direct consumer.

The pipeline needs to build and test the library, then verify both applications. If the contract schema or behavior changed, contract tests and integration tests for both consumers provide higher value than compile checks alone.

### 5.2. When the Logging Library Changes

If a change is in **libraries/common-logging**, the expanded scope includes:

- **libraries/common-logging:** the project containing the change.
- **libraries:auth-sdk:** direct consumer.
- **applications:invoice-worker:** direct consumer.
- **applications:order-api:** transitive consumer via Auth SDK.

Illustrative Gradle command for running tests in this scope:

~~~bash
./gradlew \
  :libraries:common-logging:test \
  :libraries:auth-sdk:test \
  :applications:invoice-worker:test \
  :applications:order-api:test
~~~

Project and task names must match the repository's actual configuration. Gradle can automatically build required project dependencies to run a consumer's task, but that does not mean the test tasks of every dependent library are automatically invoked. If you need to verify the library's unit tests, explicitly include the library's test task in the list.

When a full-repository verification is needed, you can use an aggregate task appropriate for the build. However, change-driven pipelines should generate task lists from the dependency graph to avoid missing consumers and avoid running unrelated projects.

## 6. When Libraries Are Shared Across Multiple Repositories

In a multi-repository model, library source code and application source code live in different places. A change in the library repository does not necessarily change the application immediately, because the application may be pinned to an already-published artifact version.

Example:

1. Shared SDK publishes artifact version **2.4.0**.
2. Order API declares usage of **2.4.0**.
3. Shared SDK is updated and publishes **2.5.0**.
4. Order API is only affected by the new version after updating its dependency to **2.5.0** and running Order API's own pipeline.

The library pipeline needs to verify the library, run compatibility checks, and produce a clearly versioned artifact. The consumer pipeline needs to verify dependency updates, run tests with the new artifact, and record the verified version.

For breaking changes, a versioning strategy and controlled consumer upgrade process are required. Do not use floating versions like **latest** where pipelines might accidentally fetch different artifacts across runs. Immutable artifacts and pinned versions keep build results reproducible.

In a multi-repository system, you can maintain a dependency catalog or manifest showing which consumers use which artifacts. The catalog must be updated alongside the version upgrade process; otherwise, cross-repository impact analysis will lack data.

## 7. Structuring the Impact Analysis Step in a Pipeline

A CI workflow can separate an analysis step to produce the list of projects requiring verification. Subsequent steps use that result to generate a build/test matrix or select corresponding jobs.

~~~mermaid
flowchart TD
    A["Commit or pull request"] --> B["Find base commit and changed files"]
    B --> C["Map files to projects and configs"]
    C --> D["Classify changes"]
    D --> E["Expand via dependency graph"]
    E --> F{"Graph and mapping complete?"}
    F -->|Yes| G["Generate affected projects list"]
    F -->|No| H["Select safe scope: all related projects"]
    G --> I["Generate build and test matrix"]
    H --> I
    I --> J["Run quality checks"]
    J --> K["Eligible to produce artifact or release"]
~~~

The high-level logic can be expressed as follows:

~~~text
base_commit = find_merge_base(target_branch, current_commit)
changed_files = diff(base_commit, current_commit)

changed_projects = map_files_to_projects(changed_files)
changed_scopes = classify_shared_configuration(changed_files)

if dependency_map_is_incomplete(changed_projects, changed_scopes):
    affected_projects = all_projects_in_safe_scope
else:
    affected_projects = changed_projects
    affected_projects += transitive_consumers(changed_projects)
    affected_projects += projects_using(changed_scopes)

validation_plan = select_tests(affected_projects, change_types)
run(validation_plan)
~~~

The analysis step should emit structured output for downstream jobs to consume. Example:

~~~json
{
  "changedProjects": [
    "libraries:order-contract"
  ],
  "affectedProjects": [
    "libraries:order-contract",
    "applications:order-api",
    "applications:invoice-worker"
  ],
  "reasons": {
    "applications:order-api": [
      "direct consumer of libraries:order-contract"
    ],
    "applications:invoice-worker": [
      "direct consumer of libraries:order-contract"
    ]
  }
}
~~~

Output should be deterministic and stored alongside pipeline logs. When a job is skipped, reviewers can still inspect which projects were selected, which were not, and why. If using a job matrix, each entry should receive the analyzed project and task set rather than re-inferring it from a different set of path filters.

## 8. Broad-Impact Changes Requiring Special Handling

Not every impact starts from source files inside a project. Some repository-level changes can alter how many projects are built or deployed.

- **Shared build logic:** changes to convention plugins, shared scripts, or compiler configurations can affect every project that applies them.
- **Dependency catalogs and lockfiles:** updated versions can alter classpaths, runtime behavior, or security risk levels across many consumers.
- **Schemas and generated code:** schema changes may require running generators before compiling consumers. Both code-generating and code-consuming projects must be identified.
- **Base Dockerfiles or base images:** image changes can affect multiple applications even when source code has not changed.
- **Shared pipeline templates and actions:** changes can affect every pipeline invoking that template or action.
- **Deployment configurations:** changes to charts, manifests, or shared config variables can affect multiple environments or services.

For these scopes, maintain a mapping from shared configuration to the projects or pipelines that use it. If it cannot be determined accurately, expand to the entire potentially affected scope. One redundant test run is usually easier to handle than missing an important consumer.

## 9. Common Mistakes When Selecting Pipeline Scope

| Wrong Practice | Consequence | How to Fix |
|---|---|---|
| Running tests only for the modified library | Compatibility bugs in consuming apps are missed | Expand to direct and transitive consumers |
| Using path filters alone | Cross-project dependencies are invisible | Combine file mapping with a dependency graph |
| Considering only direct dependencies | Multi-hop consumers are skipped | Traverse all reachable consumers |
| Treating a passing build as sufficient | Incorrect behavior may appear only at runtime | Run contract, integration, or smoke tests based on risk |
| Ignoring build logic and root configs | Many projects may use new config without being tested | Track applicability scope of shared configurations |
| Marking projects unaffected when metadata is missing | Pipeline may skip necessary work | Use a safe fallback scope and enrich metadata |
| Rebuilding artifacts in every environment | Environments may run different contents | Attach versions or digests and promote the same verified artifact |

A good scope-selection system balances precision and safety. Selecting too broadly slows CI and wastes resources; selecting too narrowly erodes confidence in test results. You can optimize incrementally once the dependency graph, contracts, and tests are sufficiently reliable.

## 10. Verifying Analysis Results Before Allowing Release

Before a pipeline uses impact analysis results as a quality gate, confirm:

- Every changed file is mapped to the right project or configuration scope.
- The dependency graph includes direct, transitive, and critical runtime dependencies.
- Changes in shared libraries expand to consumers at every tier.
- Changes to APIs, schemas, dependencies, build logic, and release configs are classified accurately.
- Task lists include test tasks for projects requiring verification, not just dependent compilation tasks.
- When data is missing, the pipeline expands scope according to a defined fallback policy.
- Pipeline logs record the base commit, changed files, dependency graph or metadata version, selected project list, and selection reasons.
- Artifacts are produced or released only after quality gates for the entire affected scope pass.

When reviewing a change in a multi-project repository, trace the path from changed files to owning projects, from those projects to consumers, and then to the required artifacts and test flows. When every step has clear data and rationale, the pipeline can select the right verification scope and provide sufficient evidence to decide whether to proceed with release.
