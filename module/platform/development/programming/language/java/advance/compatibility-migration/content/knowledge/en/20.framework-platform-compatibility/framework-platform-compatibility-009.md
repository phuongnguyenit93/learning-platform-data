# Cross-checking migration guides for upcoming framework release lines

Upgrading Java does not stop at swapping the JDK or fixing APIs removed from the JDK. In an enterprise application, frameworks and application platforms also have their own lifecycles: Spring, Hibernate, Quarkus, Micronaut, Jakarta EE, application servers, security libraries, and build tools have different **release lines** and upgrade rules. An application can run steadily on a new JDK yet fail when moving to the next major framework version; or conversely, a new framework release can force raising the minimum Java version.

Therefore, "cross-checking migration guides for upcoming framework release lines" is not reading the newest guide and patching code from memory. It is a process of **comparing official guides step by step across each upgrade stage**, tracing JDK and dependency requirements, recording API/behavioral changes, and turning release notes into verifiable items inside the codebase and deployment environments.

This lesson belongs to the **Frameworks and Platforms** chapter of the **Java Advance Compatibility Migration** module. It guides you in working systematically with migration guides, release notes, compatibility matrices, and test evidence, regardless of whether the project uses Spring, Jakarta EE, Hibernate, or another framework platform.

## 1. Learning objectives

After this lesson, learners can:

- Distinguish migration guides, upgrade guides, release notes, compatibility matrices, and versioned reference documentation.
- Identify **specific upgrade sources and targets**, avoiding inferences from the "latest" label.
- Cross-check guides across each major/minor release and identify necessary intermediate transition stages.
- Verify relationships among the Java baseline, framework core, platform/BOM, extension libraries, application servers, and build tools.
- Record changes in APIs, namespaces, configurations, security, persistence, serialization, class loading, and default behaviors.
- Build a cross-check matrix containing evidence sources, owners, impact severity, and verification tests.
- Plan staged upgrades with clear rollback conditions and acceptance criteria.
- Recognize failures caused by skipping migration guides or mistakenly applying guides from a different framework line.

## 2. Why must multiple migration guides be cross-checked?

### 2.1. A framework is a version chain, not a single JAR file

An application can have the structure:

```text
Business application
├── Base framework: Spring Boot / Quarkus / Micronaut / Jakarta EE runtime
├── Framework core: DI, Web, AOP, Transactions
├── Security: filter chain, authentication, authorization
├── Persistence: JPA provider, ORM, transaction manager, JDBC
├── Serialization: JSON, XML, validation
├── Observability: logging, metrics, tracing
├── Build plugins: compiler, test, packaging, code generation
└── Deployment: application server, container, cloud runtime
```

Upgrading one component can pull multiple other components onto newer versions. For instance, upgrading the base framework can simultaneously bump the web framework, security, ORM, logging, and test libraries via the BOM.

Consequently, "the framework already supports Java 17" is insufficient to conclude the entire system supports Java 17. You must examine **the actual dependency set and production execution paths**.

### 2.2. A migration guide usually applies to a single version interval

Suppose the system sits on framework line A and aims to reach line C:

```text
Framework A  ──────> Framework B ──────> Framework C
     |                   |                   |
  Guide A→B           Guide B→C          Guide C reference
```

If reading only guide B→C, the team may miss mandatory changes explained in A→B. Some frameworks require passing through intermediate releases to run migration tools or clean up deprecations; others permit jumping directly yet still require **applying the combined set of breaking changes**.

Never assume every framework allows jumping directly across multiple major releases. The **officially published upgrade path** is a mandatory input to verify.

### 2.3. "Making code compile" is not the end goal

A framework upgrade can introduce zero compilation errors while still changing:

- How HTTP routes match or endpoints are secured.
- Default configuration values.
- Bean initialization and extension ordering.
- Transaction boundaries, lazy loading, and schema generation.
- JSON serialization, date/time formatting, and null handling.
- Service discovery, logging, and tracing.
- TLS, cookie, header, and proxy policies.
- Class/proxy loading when running on a newer JDK.

These changes can only be caught through behavioral tests, contract tests, runtime observability, and trial deployments—not via `javac` alone.

## 3. Distinguishing the types of documentation to read

| Document | Answers the question | What to do with the document? |
| --- | --- | --- |
| **Migration / upgrade guide** | What must change when going from line X to Y? | Extract mandatory steps, migration tools, changed APIs/configs, and prerequisites before upgrading. |
| **Release notes** | What features, behavioral changes, and bug fixes exist in a specific release? | Inspect changes not summarized in the migration guide, especially in maintenance releases. |
| **Compatibility matrix** | Which JDKs, containers, dependencies, and toolchains does the framework support? | Verify Java baseline, application server, Gradle/Maven, and library ecosystem. |
| **Deprecated API list** | Which APIs should no longer be used? | Locate call sites and replacements before removal. |
| **Reference documentation** | What are the current behaviors and valid configs of the new version? | Cross-check new contracts after applying migration guides. |
| **Security advisory** | Do releases fix CVEs or alter security behavior? | Prioritize remediation and confirm safe versions. |
| **Known issues** | Which problems remain post-upgrade? | Assign risks/mitigations and test active features. |
| **Plugin/extension compatibility notes** | Which integrations require synchronized upgrades? | Verify starters, plugins, ORM dialects, test runners, native image, and third-party tools. |

**Do not use reference docs of a newer version to assume the behavior of an older target version.** When reading online docs, record the version selector, URL, and review date. If pages automatically redirect to "current," switch back to versioned documentation.

## 4. Capturing the project baseline before reading guides

### 4.1. Information to capture

For each application or module, record:

- **Java runtime:** vendor, exact version running in dev/test/production.
- **Java compiler:** Maven/Gradle JDK and `--release` or source/target levels.
- **Framework line:** groupId/artifactId/version of base framework and core.
- **Dependency management:** parent POM, BOM, version catalog, or dependency constraints.
- **Build tool:** Maven/Gradle and wrapper versions, compiler/test/packaging plugins.
- **Runtime:** application server, servlet container, Docker base image, OS/architecture.
- **Additional languages:** Kotlin, Groovy, Scala if used by the project.
- **Integrations:** Security, ORM, JPA, validation, messaging, REST clients, observability.
- **Special mechanisms:** custom class loaders, annotation processors, bytecode agents, reflection, JNI.
- **Tests:** unit/integration/contract/performance tests, executed test counts, and skipped ratio.

Command-line examples where applicable:

```bash
java -version
javac -version
mvn -version
```

With Gradle:

```bash
./gradlew --version
```

These measure the command-execution environment. Systems may also use Maven toolchains, Gradle Java toolchains, or containers running the app on a different JDK; measure the **actual JVM used**.

### 4.2. Reading the current dependency graph

Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

These commands identify which versions dependencies resolve to, even when POMs or build scripts do not declare them directly because a BOM, parent, or plugin manages them.

Do not mass-edit versions before saving a baseline. Changing multiple variables at once makes it hard for the team to tell whether errors stem from the JDK, framework core, transitive dependencies, or build configuration.

### 4.3. Recording current operational behavior

Capture a baseline for critical functionality:

- Startup/shutdown and health checks.
- HTTP contracts: statuses, headers, JSON schemas, authentication.
- Database migrations, transactions, queries, schema validation.
- Message schemas and retry handling.
- Schedulers/batch jobs.
- Caches and sessions.
- Logging, metrics, traces.
- Flows using reflection and dynamic loading.

A solid baseline separates **true regressions** from pre-existing differences.

## 5. Defining the target and upgrade stages

### 5.1. Separating three goals

In many projects, three goals get bundled into one:

1. **Upgrading the JDK runtime:** keeping the app running on a newer JDK.
2. **Upgrading the framework major version:** moving to a supported line with breaking changes.
3. **Modularization/architectural modernization:** adding JPMS, changing packaging, switching framework stacks.

All three do not have to happen in a single commit. You may upgrade runtime first on a supported framework, then upgrade the framework; or a newer framework may require upgrading the JDK first. **Migration guides and compatibility matrices** dictate feasible ordering.

### 5.2. Constructing an upgrade path

Illustrative example:

```text
Current:
  JDK 11 + Framework Line A + ORM Line P

Stage 1:
  Fix warnings / upgrade patch line A + lock dependencies

Stage 2:
  JDK 17 + Framework Line B + ORM Line Q

Stage 3:
  Framework Line C if supported on target JDK
```

This diagram does not claim every framework uses these versions. For a real project, each stage must have entry criteria, exact versions, and matching official guides.

### 5.3. When is an intermediate release necessary?

An intermediate release can be necessary when:

- The new line only supports migrating from the immediately preceding line.
- Automated config/source migration tools must run at an intermediate version.
- Old APIs must migrate to replacement APIs before removal.
- Transitive dependencies or plugins are only compatible stage by stage.
- Data/schema changes cannot be rolled back directly.
- Warnings must be cleaned up to expose genuine errors during the final major upgrade.

**An intermediate release used to perform migration work does not necessarily have to deploy to production.** It can be a staging branch or CI milestone if guides permit. Save test results from every stage.

## 6. Building a migration guide cross-check matrix

### 6.1. One row in the matrix represents one change

Instead of keeping a generic checklist item like "upgraded Spring," record each concrete change:

| ID | Guide source | Scope | Change | Project impact | Verification method |
| --- | --- | --- | --- | --- | --- |
| MIG-001 | Guide A→B, Java baseline section | Build/runtime | Minimum JDK raised | CI and old base images | Build, startup on target JDK |
| MIG-002 | Guide A→B, configuration section | Config | Old property renamed | `application.yml` | Config binding test |
| MIG-003 | Guide A→B, API removal section | Source | Old API removed | 12 call sites | Compile + unit tests |
| MIG-004 | Guide B→C, security section | Behavior | Default filter/authorization changed | Selected endpoints | Security contract tests |
| MIG-005 | Guide B→C, persistence section | Runtime/data | Dialect/SQL behavior changed | ORM and reporting | Database integration tests |

All version names and counts in the table are examples; actual data must be collected by the project team.

### 6.2. Fields to include in the record

An actionable table typically includes:

| Field | Meaning |
| --- | --- |
| Framework/component | Name, artifact, current version, and target version. |
| Guide interval | E.g., line A→B or B→C. |
| Source | URL/document title, version selector, section, review date. |
| Change type | JDK, API, config, dependency, behavior, security, data, deployment. |
| Requirement level | Required, conditional, optional, deprecated, informational. |
| Applicability condition | Does the project actually use that feature/API/config? |
| Affected locations | Module, file, service, endpoint, database, or job. |
| Owner | Responsible individual/team. |
| Action | Bump version, edit code, change config, run migration tool. |
| Test evidence | Tests/reports/logs proving the change is correct. |
| Status | Unassessed, impacted, in progress, validated, waived. |
| Rollback | Reversible, or requires a separate data plan? |

### 6.3. Do not equate "not seen in usage" with "unaffected"

A framework feature can be triggered indirectly via starters, annotations, auto-configuration, SPI, or reflection. Hence, before marking "not applicable," inspect:

- Source imports and annotations.
- Properties/YAML/XML configs.
- Dependency trees.
- Runtime wiring and bean registries where applicable.
- Plugin/service metadata.
- Profiles enabled only in production.

Negative evidence from `rg` or a single test run is insufficient for every dynamic-loading case.

## 7. Reading migration guides by change category

### 7.1. JDK and class-file compatibility requirements

Check:

- Minimum Java version of framework core.
- JDKs supported to **run the application**.
- JDKs used to **build the framework or plugins**.
- Bytecode target published by libraries.
- JDKs remaining in the support matrix and upcoming end-of-support plans.

If a test framework or plugin is compiled to higher bytecode than the running JVM, `UnsupportedClassVersionError` may appear even if application code compiled with an older `--release`.

For example, a build may use JDK 21 to compile with `--release 17`, yet a test dependency only supports Java 21. To test on JDK 17, select dependencies with a compatible minimum Java level.

### 7.2. API changes and deprecations

Search guides for phrases such as:

```text
removed / renamed / replaced / deprecated
no longer supported / behavior changed / default changed
migration required / upgrade required
```

For each API, record:

- Old and new type/method.
- Signature or return type changes.
- Null/exception/transaction contracts.
- Whether a temporary adapter exists.
- Source compatibility and binary compatibility impact.
- When the old API is scheduled for removal.

Do not just swap imports and call it done if the new API has different semantics.

### 7.3. Configuration changes

Frameworks commonly alter:

- Property names.
- Prefixes or hierarchy.
- Default values.
- Data types: boolean, duration, size, enum.
- Profile mechanisms and precedence.
- TLS, proxy, port, and management endpoint configs.
- Deprecated properties silently ignored without failing startup.

Illustrative example:

```yaml
# Old configuration (hypothetical)
framework:
  http:
    timeout-ms: 5000
```

Suppose post-migration documentation requires changing it to:

```yaml
# New configuration (hypothetical)
framework:
  http:
    timeout: 5s
```

This only simulates renaming a key and unit; it is not a real property of any specific framework. In real projects, use exact key names and semantics from official guides.

A dangerous failure occurs when an old key is **silently ignored** and the framework falls back to a new default. The application still boots, yet timeouts, pool sizes, or security policies shift.

### 7.4. Auto-configuration and dependency injection

When framework major versions change, bean creation conditions may shift:

- A bean previously auto-created now requires explicit declaration.
- Auto-configuration ordering or conditional rules change.
- Bean overriding is no longer allowed by default.
- Component scanning no longer covers old packages.
- Bean lifecycles or proxy strategies change.

Tests should verify the presence, types, and settings of critical beans rather than checking startup success alone.

### 7.5. Security behavior

Security changes require careful review:

- Authorization rules and route matching.
- Filter chains and execution ordering.
- Authentication providers and password encoders.
- CSRF, CORS, cookies/sessions.
- TLS/ciphers, headers, and redirects.
- Management/actuator endpoints and access rules.
- Deprecated or replaced security APIs.

Never restore insecure legacy behavior by disabling entire security features. Understand the rationale behind new defaults and apply approved business policies.

### 7.6. Persistence, ORM, and transactions

Migration guides may cover:

- JPA API namespaces.
- ORM major versions and query behavior.
- Dialects, schema validation, and type mappings.
- HQL/JPQL and native SQL queries.
- Lazy loading and session boundaries.
- Transaction propagation and timeouts.
- ID generation and enum/date/time mappings.
- Minimum database drivers.

An ORM change may compile cleanly while altering generated SQL, bypassing indexes, or mapping values differently. Run integration tests against real DB versions and schemas, ideally with representative datasets.

### 7.7. Serialization and API contracts

Check changes affecting:

- JSON property naming, date/time, null serialization.
- Polymorphic typing and security constraints.
- XML namespaces/bindings.
- Validation messages and exception payloads.
- HTTP error response shapes.
- Enum serialization and unknown-field handling.

If external services depend on wire formats, maintain **consumer-driven contract tests** or golden-file fixtures to detect breaking changes.

### 7.8. Observability and operations

Upgrading a framework may change:

- Metric names and labels.
- Trace propagation.
- Log/appender configuration.
- Health/readiness endpoints.
- Shutdown behavior.
- Exporter and agent compatibility.

These shifts may not break business flows immediately yet render dashboards, alerts, or deployment probes ineffective. Have an observability owner review corresponding guide sections.

## 8. Critical scenario: `javax.*` to `jakarta.*`

### 8.1. Context

Recent framework lines and modern Jakarta EE generations moved many legacy Java EE APIs from `javax.*` to `jakarta.*`. This is one of the highest-impact changes when upgrading foundational frameworks.

Example:

```java
// Old namespace-style code
import javax.persistence.Entity;
import javax.validation.constraints.NotNull;
import javax.servlet.http.HttpServletRequest;
```

In a Jakarta EE 9+ ecosystem, you may need:

```java
// New namespace-style code
import jakarta.persistence.Entity;
import jakarta.validation.constraints.NotNull;
import jakarta.servlet.http.HttpServletRequest;
```

**Never replace every `javax.*` with `jakarta.*`.** Many Java SE packages stay under `javax.*`, such as `javax.sql`, `javax.crypto`, and `javax.net`. Replace only APIs within Jakarta EE's namespace migration scope per the exact migration guide.

### 8.2. More than just source imports

Namespace migration affects:

- Source APIs and annotations.
- Dependency coordinates and versions.
- Servlet containers or application servers.
- ORM/JPA providers.
- Bean Validation providers.
- XML descriptors and namespaces/schemas where present.
- Third-party starters/extensions.
- Classes generated by annotation processors.
- Precompiled libraries still referencing `javax.servlet` or `javax.persistence`.

A third-party JAR lacking Jakarta support may still fail even after your application's source edits imports, throwing `ClassNotFoundException` or `NoClassDefFoundError` at runtime.

### 8.3. Spring ecosystem example: understanding the exact scope

A well-known path is moving from Spring Boot 2.x/Spring Framework 5.x to Spring Boot 3.x/Spring Framework 6.x: the newer line raises minimum Java requirements (Java 17 for Boot 3) and aligns with the Jakarta EE ecosystem.

However, this lesson **does not replace** official upgrade guides for your exact source and target versions. Beyond Java/Jakarta, projects must cross-check Spring Security, data access, observability, servlet containers, configuration properties, extension libraries, and minor/patch release notes.

If the project sits on a very old line, read guides across every necessary intermediate milestone instead of searching for a single "Spring Boot 3 migration" post.

### 8.4. Steps to audit namespaces

1. Locate Java EE/Jakarta EE imports in source code.
2. Identify which dependencies provide those classes.
3. Map each API to the Jakarta version supported by the target framework.
4. Inspect generated sources and annotation processors.
5. Confirm servers/containers and integration libraries belong to the compatible ecosystem.
6. Build, start up, and run integration tests for HTTP, ORM, and validation.
7. Never retain both old and new APIs merely to fix compilation if doing so introduces conflicting runtime generations.

## 9. Cross-checking framework core against the surrounding ecosystem

### 9.1. Do not upgrade only the parent/BOM and ignore extensions

A BOM or platform version manages a curated dependency set, yet does not govern every third-party plugin or extension.

After upgrading the BOM, check:

- Manual version overrides inside modules.
- Dependencies outside the BOM.
- Starters/plugins supporting only older framework lines.
- Annotation processors and codegen tools.
- Server/container versions.
- Test frameworks, mocking libraries, and coverage agents.
- Native-image build tooling if used.

A library resolved to matching compile and runtime versions can still be incompatible if compiled against an older framework API.

### 9.2. Extending the matrix to other platforms

Although names differ, the same approach applies across stacks:

| Platform group | Specific docs to cross-check |
| --- | --- |
| Spring Boot/Spring Framework | Line-specific upgrade guides, BOM dependencies, Security/Data, configuration properties, and observability. |
| Hibernate ORM/JPA | ORM migration guides, query/type mappings, schema/dialect, transactions, and Jakarta namespaces. |
| Quarkus | Platform BOMs, extension compatibility, configuration migration, native image/build-time augmentation. |
| Micronaut | Major-version framework guides, annotation processing, AOT/native tooling, serialization, security modules. |
| Jakarta EE/application servers | Java/Jakarta API levels, server compatibility, servlet/JPA/validation, deployment descriptors, class loading. |
| Web/servlet containers | Servlet API versions, connectors/TLS, sessions, request processing, and namespaces. |
| Messaging/security frameworks | Client/server protocols, serializers, policy defaults, and release compatibility. |

This table points to **where to read**, not which specific versions are supported. Each ecosystem must be verified against documentation for the chosen version.

### 9.3. Reading independent extension documentation

Suppose an application uses Spring Boot alongside a third-party starter. Boot supporting JDK 17 does not guarantee that starter works. The starter may touch internal packages, removed Spring APIs, or auto-configuration metadata from the prior line.

For critical extensions, obtain two pieces of evidence:

1. Core framework declares the target version and JDK compatible.
2. The extension publisher documents or demonstrates by tests that the extension works on that line.

Without the second piece of evidence, put it on the risk list rather than assuming compatibility.

## 10. Cross-checking API removals against the Java runtime

### 10.1. Framework guides and JDK guides complement each other

A framework upgrade guide may omit changes originating from the JDK:

- Java EE/CORBA modules split out or removed from the JDK in earlier releases.
- Tightened encapsulation blocking reflection into internal APIs.
- Default encoding changes in newer JDKs.
- Changed TLS/security providers and default algorithms.
- Evolving Java agents, bytecode instrumentation, and class-file formats.
- Differing class loaders, locales, timezones, and runtime service behavior.

Conversely, JDK migration notes do not know which library APIs a framework relies on.

Maintain a **two-way inventory**: one table for JDK requirements and one for framework breaking changes, linking overlapping entries.

### 10.2. Example of an API removed from the JDK

A legacy project previously relied directly on JDK-bundled JAXB APIs on an older JDK. When moving to a JDK no longer bundling JAXB the same way, adding an external dependency may be necessary.

However, when simultaneously upgrading the framework to a line using Jakarta XML Binding, select artifacts and namespaces matching the **target framework**. Do not blindly add an old dependency just to silence `ClassNotFoundException` without checking whether you are on the `javax` or `jakarta` generation.

### 10.3. Reflection and proxies

An older framework version may reflect deeply into JDK packages. When the target JDK tightens encapsulation, the app throws `InaccessibleObjectException`.

The preferred solution is upgrading to a compatible framework/bytecode library. If temporarily using `--add-opens`, document:

- Which module/package is opened.
- Target module or `ALL-UNNAMED`.
- Triggering component and version.
- Which JVMs need the flag (app, test, build tool).
- Plan for removing the workaround.

Do not read migration guides as implying broad JDK package opening is standard practice for all applications.

## 11. Comparing "removed," "deprecated," "changed default," and "optional"

Guides use varying terminology. Classify items before converting them into tasks:

| Category | Meaning | Typical priority |
| --- | --- | --- |
| Removed API | Class/method/option no longer exists. | Mandatory if the project uses it. |
| Renamed/replaced | Replacement API/config exists, possibly with altered semantics. | Mandatory or conditional. |
| Deprecated | Still exists yet no longer recommended. | Schedule removal before the removal release. |
| Default changed | When unconfigured, new behavior differs. | Prioritize behavioral tests because code may still compile. |
| New optional feature | New capability not mandatory to adopt. | Can usually be deferred to a later phase. |
| Support ended | Old JDK/server/dependency dropped from support matrix. | Directly impacts operations and security updates. |
| Known regression | Bug present in target release. | Assess impact and workarounds/alternative versions. |

Do not turn every release-note bullet into a "must-do." At the same time, never overlook default changes simply because they cause no compile errors.

## 12. Controlling guide source reliability

### 12.1. Prioritize authoritative, version-matched sources

Practical priority order:

1. Official framework migration/upgrade guides.
2. Official release notes and versioned reference docs.
3. Official compatibility matrices and plugin/extension docs.
4. Issues/commits confirmed by maintainers for specific bugs.
5. Community articles as leads to verify independently.

If a community post advises disabling a security feature or stacking JVM flags, never apply it merely because "others did it." Understand the impact and confirm against official versioned guides.

### 12.2. Record review dates and URLs

Online docs get updated or redirected. A migration record should include:

```text
Framework: name and source/target versions
Document: title + official URL
Version selector: selected documentation line
Reviewed at: cross-check date
Relevant section: section / heading
Decision: apply / do not apply / needs verification
Evidence: commit, test report, deployment log
```

If docs are edited later, the team can trace which guide version backed the decision.

### 12.3. When guides do not clarify an integration

Never guess. Mark "needs verification," inspect extension/driver compatibility, and write tests covering key behavior.

For high-risk areas like schema migrations or authentication, require maintainer/vendor confirmation or representative testing before rollout.

## 13. Turning a migration guide into an engineering plan

### Step 1: Lock down concrete baseline and target versions

Record JDKs, framework versions, BOM/parent, plugins, dependency graph, deployment runtime, and baseline tests. Targets must have **explicit version numbers**, not merely "latest."

### Step 2: List guides across every stage

Example:

```text
Current framework line 2.x
        |
        v
Guide: 2.x -> 3.0
        |
        v
Release notes: 3.0 -> 3.1 -> 3.2
        |
        v
Target: 3.2.z (version locked in project)
```

This model is illustrative. Depending on the framework, intermediate release guides or official upgrade tools may be needed.

### Step 3: Extract changes into the matrix

Each item needs a source, applicability condition, impacted scope, owner, and verification method. Never collapse multiple breaking changes into one vague task.

### Step 4: Map task dependencies

Example:

```text
Upgrade JDK to meet minimum runtime
            |
            v
Upgrade Maven/Gradle + compiler/test tools
            |
            v
Upgrade framework BOM and extension compatibility
            |
            v
Update source APIs / namespaces / configuration
            |
            v
Fix tests, security contracts, DB integration
            |
            v
Staging / performance / canary / rollout
```

Exact ordering is dictated by guides, support matrices, and the existing system. If the build tool cannot run on the new JDK, handle that before expecting the framework to compile.

### Step 5: Separate mechanical changes from behavioral changes

**Mechanical changes** include renaming imports, updating property keys, and adding guide-prescribed dependencies. Some can use scripts or framework-supported OpenRewrite recipes.

**Behavioral changes** include security policies, SQL semantics, transactions, serializers, route matching, or runtime lifecycles. These require careful design, testing, and domain review—never blind search-and-replace automation.

### Step 6: Execute in small batches and store evidence

Each batch should have:

- Reviewable commits/PRs or changesets.
- References back to guide items.
- Targeted tests for the main impact.
- Before/after logs and reports.
- Rollback plans if config or data is affected.

### Step 7: Verify on the target JDK and deployment runtime

Do not rely solely on tests run on a developer laptop JVM. Test on real containers/application servers and meaningful profiles: development, staging, production-like.

### Step 8: Finalize results and update documentation

Upon acceptance, update:

- Dependency/BOM locks.
- Build/CI toolchains.
- Runtime images.
- Configuration references.
- Runbooks and observability.
- Deploy/rollback procedures.
- Remaining deprecation backlogs and upcoming upgrade stages.

## 14. Layered testing to confirm the migration

### 14.1. Compilation and static checks

Ensure sources compile against target dependencies. Inspect warnings about deprecated APIs, raw types, plugin compatibility, or removed packages.

However, compile tests only answer **is the source valid**, not whether behavior stays intact.

### 14.2. Unit tests

Focus on business logic and API wrappers. Tests must genuinely run without silently disappearing due to JUnit engine or plugin filter changes.

Compare before/after test counts. A green build showing "Tests run: 0" is not evidence of a successful migration.

### 14.3. Integration tests

Test the framework with real databases, message brokers, HTTP servers/clients, transaction managers, and integrations.

Examples to check when upgrading ORMs:

- Entity mappings and database schemas.
- Parameterized and named queries.
- Lazy loading and transaction boundaries.
- Generated IDs.
- Migration scripts and data backward compatibility.

### 14.4. Contract tests

For REST/messaging, compare request/response pairs relied upon by consumers. Inspect status codes, headers, field names, nullability, validation errors, timezones, and security filter ordering.

### 14.5. Startup, shutdown, and configuration binding

Frameworks can alter defaults or bean creation conditions. Tests should verify:

- Every profile starts cleanly.
- Key properties bind instead of being ignored.
- Mandatory beans/services/providers initialize.
- Health/readiness endpoints work accurately.
- Graceful shutdown and resource cleanup operate properly.

### 14.6. Performance and resource usage

Framework upgrades can alter default thread pools, connection pools, serialization, or observability overhead.

Do not judge from a single benchmark run. Maintain a representative workload and measure latency, throughput, CPU, memory/GC, database query counts, connection usage, and error rates.

### 14.7. Security tests

Endpoints previously requiring authorization must stay protected per policy. Test valid and invalid requests, anonymous/role-based access, CSRF/CORS, and upgrades altering path-matcher semantics.

Never equate "service starts and returns HTTP 200" with complete security testing.

## 15. Choosing migration tooling

### 15.1. Source search tools

Search for APIs and configs cited in guides:

```bash
rg -n 'javax\.persistence|javax\.validation|javax\.servlet' src
rg -n '@Deprecated|deprecated|old-property-name' .
```

Regex examples are starting points, not an exhaustive list of Java EE packages. Never blindly replace all `javax` with `jakarta`.

### 15.2. Dependency analysis

Maven:

```bash
mvn dependency:tree
mvn help:effective-pom
```

Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

Compare before/after graphs to catch unintended dependency upgrades and remove obsolete version overrides.

### 15.3. Class/JDK dependency analysis

`jdeps` helps inspect static dependencies of JARs:

```bash
jdeps --recursive path/to/application.jar
```

To locate JDK internal usage, consult the corresponding mode:

```bash
jdeps --jdk-internals path/to/application.jar
```

Do not treat `jdeps` results as complete for reflection, SPI, or classes loaded dynamically from configuration—frameworks rely heavily on all three.

### 15.4. Code automation tools

Some ecosystems supply recipes, migration plugins, scripts, or IDE inspections for updating APIs/configs. Use them to generate controlled diffs.

Rules:

1. Pick recipes matching exact source and target versions.
2. Run on a separate branch with a clean, recoverable working tree.
3. Review the entire diff.
4. Run relevant behavioral tests.
5. Never treat recipe output as proof that manual guide items were also handled.

Automation excels at structural rewrites; it struggles to determine business intent behind security, transaction, or data behaviors.

## 16. Practical example: cross-checking a two-stage framework upgrade

### 16.1. Hypothetical scenario

A Java service has:

```text
Current JDK: 11
Framework: line 2.x
Security extension: line S1
ORM extension: line O1
Database: PostgreSQL
Build: Maven
Target: JDK 17 + framework line 3.x
```

The team wants to avoid one giant PR changing JDK, web APIs, security, and schemas simultaneously.

`S1` and `O1` are illustrative symbols, not specific vendor releases.

### 16.2. Documentation set to cross-check

Create a table of documents:

| Source | Section to read | Question |
| --- | --- | --- |
| Framework 2.x→3.x guide | Java baseline | Is upgrading the JDK first mandatory? |
| Framework 2.x→3.x guide | Namespace/API changes | Which packages, methods, and annotations must change? |
| Security extension upgrade guide | Filters/authorization | Which endpoints need re-testing? |
| ORM extension upgrade guide | Mapping/query/dialect | Which queries and schemas may shift behavior? |
| Framework 3.x release notes | Defaults/known issues | Are there changes not fully covered in the guide? |
| Maven/build plugin docs | JDK/toolchain support | Which plugins must upgrade first? |
| Deployment runtime docs | Container/server support | Does production runtime meet minimum versions? |

### 16.3. Action matrix

| ID | Cross-check | Action | Acceptance evidence |
| --- | --- | --- | --- |
| EX-01 | New minimum JDK | Upgrade CI toolchains/base images to JDK 17 | `java -version`, build/startup |
| EX-02 | Jakarta namespace if applicable | Update Java EE imports and dependencies | Compile and servlet/JPA/validation tests |
| EX-03 | Security matchers/defaults | Review policies and test protected endpoints | Security contract report |
| EX-04 | ORM behavior | Verify dialects/queries/transactions | DB integration report |
| EX-05 | Framework properties | Update keys/units and check binding | Startup/config tests |
| EX-06 | Test tooling | Align JUnit engine, Surefire/Failsafe | Zero dropped test counts |
| EX-07 | Target release notes | Audit default changes and known issues | Decision log and related tests |

### 16.4. Phased execution

Stage A: lock baseline, upgrade plugins/build tooling, and resolve warnings on the old line per guides.

Stage B: upgrade the target JDK when the current framework provides a supported path; otherwise structure the framework/JDK upgrade per compatibility matrix rather than forcing unsupported combinations.

Stage C: apply breaking changes for the new framework line and extensions per matching guides.

Stage D: run unit/integration/contract/security/performance tests, roll out to staging/canary, and update runbooks.

### 16.5. Self-assessment practice

Answer:

1. Why does "source compiled" not prove HTTP security stayed unchanged?
2. Why read the ORM extension guide in addition to framework core?
3. If `javax.sql.DataSource` appears in source, should it change to `jakarta.sql.DataSource`?
4. If a test dependency requires higher Java than the CI JDK, should you alter business code or adjust the dependency/toolchain?
5. If an old property is silently ignored and the app still boots, which test types catch it?

Guidance: inspect behavioral security; integrations have separate lifecycles; never change Java SE `javax.sql`; verify dependency/JVM baselines; rely on configuration binding and integration tests.

## 17. Common mistakes

### 17.1. Reading only the target version's guide

A B→C guide may omit breaking changes from A→B. Chain all relevant stages.

### 17.2. Relying on unversioned blog posts

A config snippet valid for another version may make a newer framework silently fall back to defaults. Always verify against official versioned documentation.

### 17.3. Upgrading the BOM while leaving old starters/extensions behind

Framework core may run while an extension calls removed APIs. Verify compatibility of every key extension.

### 17.4. Replacing all `javax.*` with `jakarta.*`

Not all `javax` packages migrate namespaces. Separate Java SE APIs from Java EE/Jakarta EE APIs.

### 17.5. Mixing behavioral changes with unrelated refactors

Changing ORM, security, serialization, and business logic together makes isolating regressions nearly impossible. Keep changesets tied to guide items.

### 17.6. Treating a green build as a successful migration

Test engines might not load; test suites may skip; data/security bugs only surface at runtime. Require test counts and behavioral evidence.

### 17.7. Failing to separate framework versions from JDK versions

One framework can span multiple JDKs, while another major release raises minimum floors. Never use "newer framework" interchangeably with "newer JDK."

### 17.8. Testing only the development profile

Production may use different databases, authentication, feature flags, proxies, config servers, and class loaders. Staging must represent critical boundaries.

### 17.9. Using JVM flags to mask every reflection failure

`--add-opens` can serve as a temporary workaround, yet never fixes removed APIs, bad provider metadata, or incompatible bytecode versions.

### 17.10. Neglecting data rollback preparation

Code can roll back rapidly, yet schema migrations or new data formats may be backward-incompatible. Establish forward/backward compatibility rules, backups, and dedicated rollback plans.

## 18. Migration guide cross-check report template

The following template works per application:

```markdown
# Framework migration assessment

## Baseline
- Service/module:
- JDK runtime:
- JDK compile:
- Framework line/version:
- BOM/parent:
- Major extensions:
- Build/test tooling:
- Deployment runtime:

## Target
- JDK:
- Framework line/version:
- Planned intermediate steps:
- Rollout window:

## Source documents
| Document | Version scope | Reviewed date | Relevant sections |
| --- | --- | --- | --- |

## Required changes
| ID | Guide reference | Change type | Impact | Owner | Test evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |

## Compatibility checks
- Source:
- Binary:
- Runtime:
- Security:
- Persistence:
- API contract:
- Observability:

## Risks and waivers
- Unsupported extensions:
- Required temporary flags:
- Unverified behavior:
- Rollback limitations:

## Exit criteria
- All required guide items addressed
- Unit/integration/contract tests run with expected counts
- Staging/canary results accepted
- Owners approve remaining exceptions
```

This template applies across multiple frameworks. Crucially, every "no impact" or "resolved" conclusion must attach evidence rather than just a checkmark.

## 19. Acceptance criteria before moving to the next release line

- [ ] Identified exact source and target versions without vague "latest" labels.
- [ ] Compiled migration guides covering every required upgrade stage.
- [ ] Verified minimum JDK, build tools, plugins, and deployment runtimes.
- [ ] Captured dependency graphs and BOM/parent before and after.
- [ ] Cross-checked documentation for framework core and critical extensions.
- [ ] Located API removals/deprecations, namespace changes, and config renames.
- [ ] Separated mechanical changes from behavioral changes.
- [ ] Assessed security, persistence, serialization, and API contracts.
- [ ] Audited JPMS/reflection, annotation processing, and bytecode tooling when JDK versions change.
- [ ] Built a change matrix with sources, owners, statuses, and evidence.
- [ ] Confirmed unit/integration test counts did not drop unexpectedly.
- [ ] Executed tests on the target JDK and production-like runtime.
- [ ] Tested startup/shutdown, health checks, observability, and error handling.
- [ ] Confirmed any data/schema changes have compatibility and rollback strategies.
- [ ] Recorded known issues, waivers, and follow-up items for the next release.
- [ ] Updated build/CI configs, operational runbooks, and dependency security inventories.

## 20. Conclusion

Cross-checking migration guides for upcoming framework release lines turns **release knowledge** into a **verifiable change plan**. Each framework alters Java baselines, APIs, dependencies, configurations, and behaviors on its own schedule. Reading only the destination guide, bumping a BOM, or getting code to compile is never sufficient to prove system compatibility.

In Java Advance Compatibility Migration, lock down your baseline and target versions, read guides across every stage, tie each breaking change to real components, and validate across representative test suites and runtimes. Doing so prepares teams for upcoming framework lines without turning every upgrade into an unverified trial-and-error exercise.
