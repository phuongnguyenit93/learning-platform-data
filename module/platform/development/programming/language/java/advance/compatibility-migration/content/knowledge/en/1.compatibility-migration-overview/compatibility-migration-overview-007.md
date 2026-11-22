# From current-state inventory to verification and release

Migrating a Java version is a change with cross-cutting impact, from source code, libraries, and build tools to the runtime environment and operational processes. A project compiling successfully on a developer's machine is not enough to prove that the project is compatible with the target platform. The application must also be able to start up, preserve correct business behavior, connect to dependent systems, meet performance requirements, and have a safe release plan.

Therefore, a Java compatibility migration needs to follow a verifiable sequence: recording the current state, defining the target destination, finding compatibility gaps, planning remediation, making controlled changes, testing on a representative environment, and then releasing with evidence and a rollback plan. Each stage produces clear inputs for the next stage. This approach helps the team know exactly what has been checked, what remains uncertain, and who is responsible for handling what is still missing.

## 1. Defining migration goals and scope

Before inspecting the source code, the goals of the migration need to be clearly written down. "Upgrading Java" may mean only changing the JDK that runs the application, but it can also include raising the compilation language level, changing frameworks, updating libraries, switching build tools, or migrating deployment images. These changes are interrelated, yet they are not the same.

Distinguish the following versions:

| Component | Meaning | Question to answer |
|---|---|---|
| JDK used to run the build | The JDK that launches Gradle, Maven, and build plugins | Can the build tools and plugins run on this JDK? |
| Compilation JDK/toolchain | The JDK used by the compiler to compile source code | Which version's compiler and APIs are used to compile the source code? |
| Target API level | The set of Java APIs that compiled code is allowed to use | Can the artifact run on the committed minimum runtime? |
| Application runtime JRE/JDK | The actual JVM that launches the application on the server or in the container | Does the runtime match the verified version, vendor, and configuration? |
| Framework and library versions | External components that provide functionality for the application | Do these versions support the target JDK and framework? |

A project may use a newer JDK to run Gradle while still compiling bytecode for a lower Java version. Conversely, a project may compile successfully yet be deployed on a runtime that is too old to load the bytecode or provide the APIs the application uses. Therefore, the migration documentation must record each version separately, rather than lumping everything into a single "Java version" field.

The scope also needs to be clearly defined:

- Which modules are being migrated in this effort; which shared modules could affect multiple applications.
- Target JDK, framework, build tool versions, and target deployment environment.
- Whether configuration, container images, operating system, database drivers, or integration protocols are changing.
- Which features, APIs, and external systems must preserve their behavior.
- Completion criteria, release timing, and conditions that require stopping or rolling back.

If the scope is unclear, inventory results will make it difficult to distinguish between errors belonging to the migration and pre-existing issues.

## 2. Inventorying the current state before making changes

Inventorying the current state establishes a baseline for before-and-after migration comparison. Perform it on a specific commit, and save the commands run and important results. Do not upgrade libraries or change configuration while conducting the inventory, because the team will no longer know what the true initial state was.

### 2.1. Inventorying the Java platform and build tools

Record at least:

- JDK version, vendor, and path on developer machines, CI, and the runtime environment.
- Values of `JAVA_HOME`, `PATH`, toolchain configuration, and environment variables that affect JDK selection.
- Gradle Wrapper or Maven Wrapper version; versions of build plugins and custom project-developed plugins.
- Compiler source, target, or `release` level; encoding; annotation processors; compiler arguments.
- Build, testing, packaging, code analysis, and documentation generation tasks currently executed by CI.

With Gradle, commonly used inspection commands include:

```bash
./gradlew --version
./gradlew projects
./gradlew tasks
```

With Maven Wrapper:

```bash
./mvnw -version
./mvnw help:effective-pom
```

On Windows, `gradlew.bat` or `mvnw.cmd` can be used. Note that the output of `java -version` in a terminal does not necessarily reflect the JDK that CI or the Gradle daemon is using. Read the build logs and toolchain configuration to confirm what is actually used.

### 2.2. Inventorying dependencies and dependency relationships

The list of direct dependencies does not fully represent everything the application loads at runtime. A single library can pull in many transitive dependencies; the same library can also appear in multiple versions across different dependency branches.

With Gradle, you can view the dependency tree and trace a specific library:

```bash
./gradlew dependencies
./gradlew dependencyInsight --dependency <library-name>
```

With Maven:

```bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=<groupId>:<artifactId>
```

When recording dependencies, distinguish:

- Direct dependencies declared by the module.
- Transitive dependencies pulled in by other libraries.
- Dependencies used only for compilation, testing, or annotation processing.
- Dependencies provided by the runtime, container, or deployment platform.
- Internal dependencies between modules and bundled artifacts.

For each important library, record the current version, planned version, declaration source, dependency path, usage scope, and target JDK/framework support information. Do not just look at the latest version in the package repository and conclude that it is the right version; check compatibility documentation, API changes, runtime requirements, and relationships with related dependencies.

### 2.3. Inventorying frameworks, APIs, and configuration

List frameworks and foundational components such as web frameworks, persistence, dependency injection, logging, JSON, validation, security, messaging, cache, database drivers, and testing libraries. For each component, identify its version, configuration approach, integration points, and consuming modules.

Pay special attention to areas that may depend on JDK behavior:

- Reflection, proxies, bytecode generation, and access to JDK internals.
- Serialization, date/time formatting, locale, timezone, and default charset.
- TLS, certificates, cryptographic algorithms, and security policies.
- Class loading, service providers, the Java Platform Module System, and resource lookup.
- Threads, executors, synchronization, timeouts, interrupts, and asynchronous error handling.
- File system, permissions, path encoding, and operating system behavior.

Also inventory configuration outside the source code: environment variables, JVM options, system properties, profile-specific configuration files, secret references, container images, startup arguments, health checks, and CI/CD configuration. Many errors only surface because the new environment has different default values than the old environment.

### 2.4. Inventorying existing behavior and evidence

Do not just record "has tests" or "build is green". You need to know which tests actually run, which tests are skipped, which modules lack tests, and which critical business flows are not covered.

Make a list of flows to protect, such as:

- Application startup, bean registration, and configuration loading.
- Authentication, authorization, and request/response processing.
- Database reads/writes, transactions, schema migrations, and connection pooling.
- External service calls, timeout handling, retries, and network errors.
- Message sending/receiving, background job processing, and graceful application shutdown.
- File generation, data reading/writing, date/time handling, and data containing non-ASCII characters.
- Flows with strict latency, throughput, or memory requirements.

Save build and test results, startup logs, performance metrics if available, known bugs, and existing warnings. This baseline helps distinguish regressions caused by the migration from pre-existing issues.

### 2.5. Creating a traceable inventory record

A useful inventory record should include the following columns:

| Field | Content |
|---|---|
| Component | Name of the module, library, plugin, or environment |
| Current state | Currently used version and configuration |
| Target | Planned version/configuration |
| Evidence source | Configuration file, command, log, documentation, or confirmer |
| Impact scope | Related modules, business flows, and environments |
| Certainty level | Confirmed, inferred, or no data yet |
| Owner | Person tracking and resolving the issue |

Record unknowns as well. An "undetermined" cell with an owner and a resolution deadline is safer than a guessed value treated as fact.

## 3. Defining the target compatibility matrix

After establishing the baseline, build a compatibility matrix for the entire combination to be released. Do not evaluate components in isolation if they only operate within a specific combination.

For example, the target JDK might be supported by a new framework version, yet the current build plugin cannot run on that JDK. A database driver might support the new JDK, yet the framework version in use is incompatible with the new driver version. The matrix must capture these relationships.

| Group | Current state | Target | Conditions to verify |
|---|---|---|---|
| JDK/runtime | Current version and vendor | Planned JDK/runtime | Official support, JVM options, deployment image |
| Compiler/toolchain | Current compiler and API level | Target compiler/toolchain | Source compatibility, bytecode, permitted APIs |
| Build tool/plugin | Current Wrapper and plugins | Compatible versions | Ability to run on the JDK used to run the build |
| Framework | Version currently in use | Target version | JDK support matrix, API changes, configuration |
| Dependency | Direct and transitive | Finalized versions | Mutual compatibility, license, security |
| Runtime platform | OS, container, server | Release environment | Image, certificates, timezone, permissions, and resources |
| Integrated systems | Database, broker, external APIs | Actual versions/configuration | Drivers, protocols, TLS, schemas, and contracts |

For each cell or relationship in the matrix, use clear statuses:

- **Support confirmed:** there is official documentation or a support commitment matching the combination under consideration.
- **Verified:** the team has tested on the exact combination and saved evidence.
- **Undetermined:** documentation is missing or a test environment is not yet available.
- **Incompatible:** there is evidence that the combination does not work or falls outside support.
- **Conditional/workaround available:** usable only when applying the documented configuration, version, or workaround.

"Vendor-supported" and "verified by the project" are two distinct conclusions. A good matrix must show both, avoiding using a single broad conclusion to obscure untested parts.

## 4. Analyzing gaps and prioritizing risks

Compare the baseline against the target matrix to compile a list of compatibility gaps. Each gap should describe the symptom, reproduction conditions, impact scope, evidence, severity, remediation approach, and closure criteria.

Common risk categories include:

1. **Removed or changed APIs:** source code calls APIs that no longer exist, APIs with changed signatures, or APIs with changed contracts.
2. **Internal API access:** libraries or the application depend on internal JDK packages; module encapsulation and access controls in newer runtimes may block this behavior.
3. **Binary incompatibility:** compiled code references a class, method, or field that is no longer provided in the actual runtime.
4. **Outdated dependencies:** libraries, plugins, or annotation processors do not support the target JDK; transitive dependencies conflict or pull in an incompatible version.
5. **Runtime default changes:** charset, timezone, TLS, security algorithms, GC, reflection, or warning handling changes.
6. **Framework differences:** lifecycle, auto-configuration, request mapping, transaction, serialization, or proxy mechanisms change.
7. **Environment differences:** containers missing tools or certificates, different memory limits, different file permissions, or environment variables that have not been updated.
8. **Lack of evidence:** critical flows have no tests, integration environments are not ready, or metrics to evaluate regressions are unavailable.

Three priority levels can be used to coordinate the work:

| Level | Indicators | Handling |
|---|---|---|
| Release-blocking | Build does not complete, application fails to start, core flows fail, data is at risk of corruption, or there is no recovery plan | Must be resolved or have an approved exception decision before release |
| High | Affects critical flows, security, stability, or performance; likely to occur in production | Prioritize remediation and verify on a representative environment |
| Medium/low | Narrow scope, detectable and controllable, does not violate release criteria | Schedule remediation, clearly record the owner and acceptance conditions |

Do not prioritize based solely on error count. A rare error that can corrupt data or disable authentication carries higher risk than many warning messages that do not affect behavior. Consider probability of occurrence, severity of impact, detectability, and recoverability together.

For each issue, create a structured tracking item:

```text
ID: COMPAT-001
Component: library X
Symptom: API access no longer permitted on the target runtime
Condition: starting module Y with configuration Z
Impact: module Y cannot start
Evidence: error logs and dependency check results
Priority: release-blocking
Remediation: upgrade the library or replace the integration approach
Owner: person responsible for module Y
Closure criteria: startup test and integration test run successfully on the target runtime
```

An issue should only be closed when there is evidence meeting the agreed criteria, not merely because a commit was made or the implementer considers the fix done.

## 5. Planning and preparing the migration path

The migration plan needs to turn each gap into tasks with ordering, dependencies, an owner, and completion criteria. Foundational changes usually have sequential dependencies: the build tool must be able to run on the JDK used to run the build; the framework must support the target JDK; related dependencies must have compatible versions; and finally the application must be verified on the deployment runtime.

Before modifying code:

- Lock in the baseline commit and create a migration branch following the team's conventions.
- Confirm the build and tests on the baseline; record pre-existing failures.
- Finalize target versions and compatibility documentation sources.
- Verify that CI can install, select, and use the right JDK/toolchain.
- Prepare a test environment close to production in terms of runtime, containers, configuration, and integrated services.
- Ensure tests exist for critical business flows; add characterization tests before making changes if needed.
- Finalize dependency management so that build results are reproducible.
- Identify who has decision authority when encountering an unsupported dependency or needing an exception.

Prioritize breaking changes into groups that can be verified independently. For example, wrapper/plugin updates, toolchain configuration, framework upgrades, handling removed APIs, and changing deployment images can be separated into distinct steps. However, the final order must follow the project's actual compatibility dependencies; do not mechanically apply a single order to every system.

Each step should have entry criteria and exit criteria. For example, begin upgrading the framework only after confirming that the build tool runs with the planned JDK and obtaining the list of dependencies managed by the framework. Move to integration testing only once the application compiles, packages, and starts on the target runtime.

## 6. Executing the migration in a controlled manner

### 6.1. Synchronizing build and runtime environments

First, ensure developer machines, CI, and the deployment environment do not accidentally pick different JDKs. Use the Wrapper and toolchain declared in the project to reduce reliance on personal machine settings. Build logs should show the actual JDK, build tool version, and key compiler arguments.

With `javac`, the `--release` option constrains the language level, bytecode, and set of platform APIs permitted for the target release. Setting `source` and `target` alone may not be enough to prevent source code from referencing APIs that only exist in a newer JDK. With Gradle or Maven, configure the equivalent mechanism according to the compiler plugin version in use.

Illustrative example when compiling directly:

```bash
javac --release 21 -d build/classes src/example/App.java
```

The number `21` is only an example; it must be replaced with the Java level approved for the project. If the goal is to run on the target JDK, verify both the compiler and the actual runtime, rather than inferring the runtime from the compiler configuration.

### 6.2. Upgrading build tools and plugins according to the support matrix

Gradle/Maven and plugins are part of the build platform. Plugins may use JDK APIs, bytecode libraries, or their own reflection mechanisms, so they can break even when application source code has not changed.

When updating:

- Use a Wrapper version that has been tested with the JDK running the build.
- Check plugins for Java, Spring, Kotlin, code generation, coverage, static analysis, and packaging.
- Read the release notes for versions with behavioral or configuration changes.
- Run the actual CI build tasks, not just a simple compile task.
- Check custom build scripts and internal plugins if they use APIs that have changed.

If the build tool cannot run on the target JDK, this constraint must be resolved in the plan before moving to the next steps.

### 6.3. Updating dependencies and frameworks

Prioritize updating according to the compatible version matrix and dependency management relationships. If the framework provides a BOM or centralized version management mechanism, clearly understand which versions are controlled by the framework and which dependencies the project pins itself. Do not randomly upgrade individual libraries to the latest version, as doing so can create an unsupported combination.

After each dependency update:

- Inspect the dependency tree to detect overridden, duplicate, or conflicting versions.
- Confirm that required libraries are present in the final artifact.
- Check for deprecated APIs or changed signatures.
- Run tests related to serialization, persistence, HTTP, security, and integration.
- Record any workarounds or temporary compatibility configurations if they cannot be removed immediately.

Workarounds should not be kept indefinitely without an owner and a review deadline. Each workaround needs to state the reason, impact scope, how to detect when it is no longer needed, and removal conditions.

### 6.4. Modifying source code and configuration

When the compiler or runtime flags an API that is no longer appropriate, fix it using an officially supported approach. Avoid replacing an old API with a new one just to silence a compile error without checking semantics. Confirm that the new behavior meets business requirements, especially in areas dealing with time, cryptography, security, transactions, and concurrency.

For reflection or JDK internal access, first identify which library or code snippet actually needs access. Prioritize upgrading the library or using public APIs. Use module/package opening options only when there is a clear reason, narrow scope, and a removal plan; broadening access globally can mask compatibility issues and weaken security boundaries.

Review JVM and application configuration after upgrading. A JVM option may have been removed, changed meaning, or become unnecessary. Heap, GC, thread pool, timeout, TLS, logging, and health check settings need to be verified on the target environment.

### 6.5. Keeping changes traceable

Each commit should represent a group of changes with a clear rationale. Do not mix a JDK upgrade with major business refactoring unless necessary, because when tests fail it will be hard to pinpoint the cause. Record upgraded dependencies, changed configurations, replaced APIs, and related check results. If multiple layers must be changed simultaneously, clearly document the dependency relationships and evidence for the entire combination.

## 7. Multi-layer compatibility verification

Verification must answer four questions: can the project build, can the application run, is the behavior still correct, and does the system operate stably? No single type of test answers all four questions completely.

### 7.1. Static checks and build checks

Initial verification gates include:

- Compiling all modules in scope, including modules not invoked directly on the main execution path.
- Running annotation processors, code generation, and packaging tasks.
- Running static analysis, checking deprecated APIs, and scanning for JDK internal access.
- Checking the dependency tree, dependency convergence, and artifact contents.
- Confirming the artifact has bytecode and target APIs compatible with the committed minimum runtime.

Tools such as `jdeps` can help find dependencies between classes/packages and references to internal JDK APIs; `jdeprscan` can help detect deprecated APIs in bytecode. For example:

```bash
jdeps --jdk-internals app.jar
jdeprscan --release 21 app.jar
```

These commands are only supporting tools. Their output may require an appropriate classpath, and they do not prove that the application will run correctly. Treat them as one source of evidence alongside the compiler, tests, and runtime testing.

### 7.2. Unit tests and component testing

Run unit tests on the target JDK to detect differences in data processing, collections, time, encoding, exceptions, and business logic. Component testing should include frameworks or adapters that the application actually uses, such as mappers, validators, serializers, repositories, and HTTP clients.

If existing tests depend on execution order, system time, machine timezone, or shared data, those assumptions need to be made explicit. A test that only passes reliably on its author's machine may not be reliable enough to serve as a release gate.

### 7.3. Integration tests and contract tests

Run the application against the systems it actually integrates with: databases, message brokers, caches, HTTP services, identity providers, and internal services. Use driver versions and configurations equivalent to the target environment.

Test both success paths and failure paths:

- Connection, authentication, transactions, and connection closing.
- Timeouts, retries, circuit breakers, and abnormal response handling.
- Request/response contracts, JSON/XML, headers, status codes, and encoding.
- Schemas, data migration, and compatibility between old and new application versions.
- Repeatability of operations when retries or repeated message processing occur.

Contract tests help detect protocol changes between systems that internal unit tests cannot see.

### 7.4. Startup and runtime behavior testing

Package the application exactly as it will be released, then run the artifact on the target runtime. Do not only run from an IDE or the Gradle/Maven classpath, because the development classpath can differ from the deployed artifact.

Verify:

- The application starts, loads configuration, and registers components successfully.
- Health checks and readiness report ready only when mandatory dependencies are satisfied.
- Requests, scheduled jobs, message consumers, and background tasks work properly.
- Graceful shutdown, properly completing or canceling tasks and releasing resources.
- Logs, metrics, traces, and error information remain observable.
- There are no linkage, class loading, or reflection errors, or critical warnings being ignored.

### 7.5. Performance and stability testing

Compare against the baseline using the same data types, load, and configuration as closely as possible. Monitor at least:

- Startup time and time to reach ready state.
- Throughput, average latency, and key percentiles.
- CPU, heap, non-heap, allocation, GC pauses, and thread count.
- Connection pools, queues, timeouts, and error rates.
- File descriptor, socket, and operating system resource usage if relevant.

Run short load tests to detect obvious regressions, then run extended load or soak tests for systems with high stability requirements. A test passing over a few minutes does not prove that the application will not leak memory or exhaust resources after many hours.

Do not draw conclusions from a single aggregate number alone. Compare under the same conditions and set acceptance thresholds before running. If performance changes significantly, identify the cause before releasing or record a risk acceptance decision.

### 7.6. Security and operational configuration checks

A newer JDK can change TLS policies, certificates, cryptographic algorithms, or how legacy protocols are handled. Check authentication, authorization, TLS connections, secret loading, file permissions, and relevant JVM options. Run dependency vulnerability checks according to project policy and review any new warnings that appear after updating.

Test on the container or server that will actually run the application. Confirm the image has the right runtime, timezone, CA certificates, locale, user/permissions, CPU/memory limits, and network configuration. A test run on a JDK installed on a developer's machine does not replace testing the artifact inside the release image.

## 8. Evaluating results and making the release decision

Before creating a release candidate, summarize results by each criterion instead of simply writing "tests pass". A verification table may include:

| Criterion | Evidence to record | Pass condition |
|---|---|---|
| Build environment | Logs for JDK, Wrapper, plugins, and compiler configuration | Matches finalized versions, reproducible build |
| Compilation and packaging | Compile, test, package logs, and artifact details | All modules in scope complete |
| Dependencies | Dependency tree, version list, and security scan | No remaining conflicts or unaccepted issues |
| Startup | Startup logs, health/readiness, and runtime configuration | Application starts stably on the target runtime |
| Business behavior | Unit, integration, contract, and regression test results | Mandatory flows uphold their contracts |
| Performance | Comparison report against baseline | Within agreed thresholds or has an approved exception |
| Operations | Logs, metrics, traces, shutdown, and resource checks | Observable and capable of incident response |
| Recovery | Rollback scenario and drill results if needed | Can return to a safe state within defined limits |

Open issues must be categorized and have clear decisions. Do not treat "not reproduced" as "fixed", or "no test" as "no bug". If accepting a residual risk, record the impact scope, rationale for acceptance, mitigation measures, approver, and review deadline.

The release candidate must be tied to a specific commit and set of artifacts. Save checksums, dependency versions, required configurations, and verification results so the exact version released can be traced. If rebuilding the same commit produces different artifacts, investigate the cause before considering the process reproducible.

## 9. Phased release and rollback preparation

Do not shift all traffic to the new runtime immediately once tests pass in the test environment. Choose a strategy suited to your architecture and traffic control capabilities:

- **Canary:** route a small portion of traffic or a subset of instances to the new version, monitor, and then gradually increase.
- **Rolling deployment:** replace instances in batches, maintaining sufficient serving capacity during the transition.
- **Blue-green:** prepare a new environment in parallel, verify first, and then switch traffic once conditions are met.
- **Per-module/per-service release:** partition the scope along independent boundaries to limit impact.

During each stage, monitor error rates, latency, CPU, memory, GC, restart counts, health checks, and connection errors. Compare against the baseline or unmigrated instance groups. Set stop thresholds in advance: for example, error rate exceeding threshold, failing health checks, abnormal latency spikes, or data errors appearing. When a threshold is reached, halt traffic increases and execute the prepared response procedure.

### 9.1. Designing a practical rollback

Rollback must be designed before release, not written from scratch once production is already experiencing an incident. Identify:

- Where artifacts and configurations of the previous version are stored and how quickly they can be restored.
- Who has authority to decide on a rollback and who executes it.
- Trigger conditions, response time, and how to confirm recovery.
- Which logs, metrics, and data must be preserved for post-rollback investigation.
- Which changes cannot be reversed automatically.

In particular, schema or data changes need to be compatible between old and new application versions. An expand/contract approach can be used: add new structures in a way that the old version still works, migrate the application and data step by step, and remove old structures only after confirming no version depends on them anymore. If data migration is irreversible, rolling back the application alone may not be enough; a separate data recovery plan is required.

### 9.2. Completing the release

Once the rollout meets stability criteria:

- Record the released JDK, framework, dependency versions, and environment.
- Save the commit, artifact checksum, test results, and exception decisions.
- Update the compatibility matrix from planned status to verified status.
- Update runbooks, development guides, CI configuration, and incident response documentation.
- Document remaining workarounds along with their owners and removal deadlines.
- Monitor post-release errors for a period appropriate to the system's load characteristics.

Remove temporary compatibility mechanisms only after confirming no instance or process depends on them anymore. Cleanup should be controlled and traceable work.

## 10. End-to-end example: a dependency incompatible with the target runtime

Suppose a Java application uses library X for proxy generation. When running on the target runtime, application startup fails because library X accesses an internal JDK package that the new runtime no longer permits in the old way.

The remediation process should proceed as follows:

1. **Record the baseline:** save the commit, current JDK, library X version, dependency tree, and startup logs on the old environment.
2. **Reproduce on target:** run the exact artifact with the target runtime and save the stack trace. Do not only test an isolated code snippet if the error depends on the framework or the application's classpath.
3. **Trace origin:** determine whether library X is a direct or transitive dependency, which module invokes it, and which version begins supporting the target runtime.
4. **Cross-check the matrix:** check whether the version of X is compatible with the JDK, framework, and related dependencies.
5. **Choose remediation:** prioritize upgrading X to a supported version or replacing it with a public mechanism. If forced to use a temporary package-opening option, limit the scope, document the risk, and record a removal plan.
6. **Verify:** run compile, unit tests, proxy generation tests, integration tests, and smoke tests on the target runtime. Test the flows that use proxies in production as well, rather than only confirming that the application started.
7. **Release:** deploy the artifact to the test environment, monitor startup errors and runtime behavior, and then roll out following the chosen strategy.
8. **Close the issue:** save evidence, update the dependency matrix, and close the risk item once completion criteria have been met.

This example shows that an error detected at runtime can originate from a transitive dependency. Simply modifying application source code or adding a broad JVM option may hide the immediate symptom without solving the long-term root cause.

## 11. Common mistakes

| Mistake | Consequence | Prevention |
|---|---|---|
| Changing the JDK only on a personal machine | CI or production still uses a different JDK | Declare and verify the JDK in each environment |
| Checking compilation only | Misses linkage, configuration, integration, and runtime behavior errors | Test the artifact on the target runtime and run multi-layer tests |
| Looking only at direct dependencies | Misses transitive libraries or forced-resolved versions | Save the dependency tree and trace important libraries |
| Upgrading all dependencies to the latest version | Creates unsupported combinations and expands the scope of changes | Rely on the compatibility matrix and update in controlled batches |
| Ignoring build plugins | Builds fail even though application code is compatible | Check the Wrapper, plugins, and actual CI tasks |
| Using global workarounds | Hides errors and widens the risk surface | Prefer public APIs, scope down workarounds, and set removal deadlines |
| Having no baseline | Cannot tell whether a regression appeared after migration or already existed | Save commits, logs, tests, and metrics before making changes |
| Testing on an environment unlike production | False-positive results due to different runtime, image, or configuration | Use a representative environment and verify the final artifact |
| Not preparing rollback | Prolonged outages or inability to recover quickly | Finalize conditions, authority, artifacts, and recovery data before release |

## 12. Migration completion record

A migration can be handed over and audited when all of the following deliverables are complete:

1. **Baseline:** original commit, JDK/build tool/framework/dependency inventory, environment configuration, and initial test results.
2. **Compatibility matrix:** target version combinations, support confirmation sources, and verification status of each component.
3. **Gap/risk register:** discovered issues, priority levels, evidence, owners, remediation approaches, and closure criteria.
4. **Migration plan:** task order, dependency relationships, module scope, checkpoints, and stop conditions.
5. **Change record:** related commits or pull requests, changed dependencies/configuration, and rationale.
6. **Verification report:** build logs, test results, runtime checks, performance, security, and deployment environment verification.
7. **Release record:** version, artifacts, checksums, timestamp, rollout strategy, and confirmer.
8. **Recovery plan:** rollback conditions, previous artifacts/configuration, data recovery procedure, and drill results if available.
9. **Follow-up:** accepted risks, remaining workarounds, cleanup tasks, and post-release monitoring period.

### Checklist before closing the migration

- [ ] Build JDK, compilation JDK, target API level, and application runtime are clearly identified.
- [ ] Direct dependencies, transitive dependencies, plugins, frameworks, and related modules have been inventoried.
- [ ] Compatibility matrix and evidence sources are in place for critical components.
- [ ] Release-blocking issues have been resolved or have approved exception decisions.
- [ ] Build and packaging succeed on the finalized configuration.
- [ ] Unit, integration, contract, and regression tests for critical flows meet requirements.
- [ ] Final artifact has run on the target runtime and representative deployment environment.
- [ ] Performance, security, observability, and shutdown have been verified against project criteria.
- [ ] Artifacts, checksums, commits, and reports are available for release traceability.
- [ ] Rollout strategy, stop thresholds, and a feasible rollback plan are in place.
- [ ] Compatibility matrix, runbooks, and operational documentation have been updated.
- [ ] Remaining risks have owners, mitigation measures, and review deadlines.

A Java compatibility migration is only complete when the team proves that the target version combination works properly under expected conditions, can be released, and can be recovered when needed. Inventory reveals the starting point; the matrix and risk register turn differences into concrete tasks; verification provides evidence; and controlled release puts the results into operation within agreed risk limits.