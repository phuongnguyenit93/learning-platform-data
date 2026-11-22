# Avoiding Bulk Upgrades Without Test Evidence

During **Java Advance Compatibility Migration**, moving to a new JDK often produces a long list of libraries and plugins recommended for upgrading: logging, HTTP clients, JDBC drivers, JSON serializers, ORMs, test frameworks, Gradle plugins, bytecode enhancers, Java agents, and many transitive dependencies. Seeing dozens of old versions, a team may be tempted to "upgrade everything to the latest version" in a single pull request and fix whatever compile errors appear.

This approach carries high risk. Each dependency can change APIs, behavior, minimum Java requirements, dependency graphs, data formats, or security defaults. When dozens of components change at once, a failing test or production error becomes hard to attribute to a root cause; even if the build succeeds, that does not prove contracts and behavior remain compatible.

A safer strategy is **upgrading in change batches with clear boundaries, a stated hypothesis, and test evidence**. This does not mean mechanically upgrading one JAR at a time: components with synchronized version requirements must be upgraded together as a consistent cluster. The core principle is controlling scope, isolating causes, and measuring outcomes at each step.

## 1. What Is an "Unverified Bulk Upgrade"?

An uncontrolled upgrade typically shows these signs:

- Changing many versions in `build.gradle.kts`, `pom.xml`, or a version catalog without identifying reasons.
- Using `latest.release`, overly broad version ranges, or `SNAPSHOT` versions to "catch up" on dependencies.
- Running only `compileJava` or a smoke test and concluding compatibility.
- Upgrading JDK, Gradle, framework, database drivers, serializers, and schema simultaneously.
- Not saving before/after dependency graphs, or lacking lockfiles or proper artifact checksums.
- Ignoring release notes on breaking changes, JDK baselines, module paths, and deprecations.
- Not knowing which APIs of the upgraded library the application actually uses.
- Lacking tests for failure cases, boundary data, serialization, authorization, or concurrency.
- Lacking a rollback plan and an owner for the release decision.

**Test evidence** does not have to be a massive report. At a minimum, it must state old/new versions, the reason for upgrading, the environment, checks executed, results, and what was not tested. More important than test count is how well those tests protect the contracts actually relied upon by consumers.

## 2. Why a "Green Build" Is Not Enough

A Java build usually consists of several stages: dependency resolution, compilation, testing, packaging, running the application, and deployment. These stages verify different properties.

| Signal | What It Proves Within the Executed Scope | What Remains Unproven |
|---|---|---|
| Dependency resolution succeeds | Gradle/Maven found a set of artifacts under current rules | That chosen versions are safe or behaviorally compatible |
| `compileJava` succeeds | Source compiled against current compiler/classpath | Older runtimes, binary dependencies, and production data work |
| Unit tests pass | Executed tests detected no discrepancies | Integration, databases, TLS, load, external consumers |
| Integration tests pass | Certain wired flows worked in the test environment | Every production configuration and failure path |
| API diff reports no breaks | Tool found no breakage of the patterns it checks | Behavior, runtime, reflective access, wire formats |
| Staging smoke test passes | Application starts and a few basic paths work | Rare flows, historical data, peak load |
| Canary is stable | A slice of live traffic runs well during the observation window | Unseen edge cases and longer-term operational risks |

A compatibility bug may surface only when reading timestamps around DST, handling high-scale DECIMAL numbers, generating a proxy for a specific class, or performing a TLS handshake with a rarely used endpoint. Zero failures in a thin test suite is not proof of "zero risk".

## 3. Compatibility Dimensions to Consider

Each dependency exposes a different compatibility surface. When upgrading, distinguish:

1. **Source compatibility:** does consumer code still compile against the new API?
2. **Binary compatibility:** does previously compiled consumer or plugin bytecode still link against the new library?
3. **Behavioral compatibility:** do values, exceptions, ordering, retries, timeouts, side effects, and concurrency still honor the contract?
4. **Runtime/JDK compatibility:** are class-file versions, Java SE APIs, module access, security providers, and OS aligned?
5. **Dependency compatibility:** do direct/transitive dependencies conflict or shift which implementation is selected?
6. **Data/protocol compatibility:** do DB schemas, JDBC mappings, JSON/XML, events, serialization, and HTTP contracts hold?
7. **Operational compatibility:** do startup, memory, latency, logging, metrics, and resource lifecycles meet SLOs?
8. **Security compatibility:** TLS, certificate validation, authorization, and data controls are not relaxed outside policy.

Not every artifact needs the same depth of checking across every dimension. Swapping a test-only library has a different scope from changing an ORM or production HTTP client. Still, **record why each check was chosen or omitted**.

## 4. Inventorying Dependencies Before Choosing New Versions

A Java project has multiple dependency layers:

- **Direct dependency:** declared directly in the module.
- **Transitive dependency:** pulled in through another dependency.
- **Build plugin/tool:** used by Gradle/Maven at build time.
- **Annotation processor/code generator:** runs at compile time and may need a newer JDK.
- **Test dependency:** JUnit, mocking, test containers, assertion libraries.
- **Runtime-only dependency:** JDBC drivers, logging backends, service providers, native bindings.
- **Optional/plugin/agent:** may be loaded dynamically and absent from standard compile paths.
- **Platform/BOM:** defines versions or constraints for a group of artifacts.
- **Application server/container:** may provide libraries under a different class loader from the application.

With Gradle, distinguish `compileClasspath`, `runtimeClasspath`, and `testRuntimeClasspath`. The same library coordinates can resolve to different versions or variants across different configurations.

Example commands **for use in real projects**, not mandatory steps while authoring lessons:

~~~bash
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency jackson-databind
~~~

In multi-module projects, select the right project or task path, such as `:service:dependencies`. Dependency insight output shows **why a version was chosen**, not whether that version is compatible.

Maven can inspect the dependency tree in the appropriate scope:

~~~bash
mvn dependency:tree
~~~

For plugin dependencies, toolchains, or dynamically loaded artifacts, additional reports and dedicated inventory steps may be needed.

## 5. Saving a Reproducible Baseline Before Making Changes

Before an upgrade pass, save enough baseline information for others to reproduce issues:

| Information | Significance |
|---|---|
| Git commit/tag | Pinpoints the exact source code and build scripts |
| Java feature/update/build, vendor | Distinguishes compiler, Gradle daemon, test JVM, and production JVM |
| Gradle/Maven and plugin versions | Ensures build tools are supported on the JDK |
| Resolved dependency graph | Not merely declared versions |
| Lockfile/verification metadata | Pins artifacts and detects source discrepancies |
| Artifact checksum/digest | Verifies built/deployed binaries |
| Database/server/schema revision | Clarifies integration environment |
| Test results and reports | Evidence of the initial state |
| JVM options, container image | Explains runtime differences |
| Pre-existing failures | Avoids misattributing them to new dependencies |

A **green baseline** means the selected checks had acceptable outcomes at the start; it does not mean every behavior is flawless. If the baseline already has flaky tests, document them instead of hiding them. When checks fail after an upgrade, distinguish new regressions from pre-existing issues.

### 5.1. Dependency Locking and Verification Are Not the Same Thing

**Dependency locking** pins resolved versions, reducing the risk of builds unexpectedly selecting newer versions.

**Dependency verification** verifies the identity/checksum/signature of downloaded artifacts against build policy to guard against unintended binaries.

Version locking does not prove an artifact is safe, and artifact verification does not guarantee API compatibility. Both are tools for **reproducibility and provenance** that must be combined with testing.

## 6. Classifying Dependencies by Risk Level

Do not upgrade in random order or alphabetically from a catalog. Build a risk register based on:

| Group | Typical Risks | Priority Tests |
|---|---|---|
| JSON/XML serializer | Field naming changes, null handling, polymorphism, date/time, parsing security | Golden fixtures and consumer contracts |
| JDBC driver | Numeric precision, timezone, null, transactions, TLS | Round-trip, DB integration, negative cases |
| ORM/framework | Entity mapping, proxies, transactions, SQL dialect | Repository tests, schema validation, rollback |
| HTTP client | Timeouts, redirects, TLS, hostnames, proxies, retries | Endpoint integration and security negative cases |
| Logging | Binding conflicts, formatting, MDC, sensitive data | Startup, log format, correlation, leak checks |
| Bytecode/proxy/agent | Class-file support, reflection, JPMS access | Startup, instrumentation, JDK runtime matrix |
| Cryptography/security | Providers, algorithms, certificate validation | Positive/negative security contracts |
| Build plugins | Gradle API, JDK baseline, task configuration | Build reproducibility and plugin tasks |
| Test libraries | Test engine discovery, mocking, assertions | Test suite and coverage/test execution reports |
| Core utility | Generic APIs, null behavior, transitive dependencies | Compile tests and targeted unit tests |

Priority must also reflect **usage exposure**. A dependency outside production code paths may carry lower risk. Yet an old build plugin blocking the entire JDK upgrade pipeline can be a top blocker even though it never enters production runtime.

## 7. "One Change at a Time" Does Not Mean "Change Exactly One JAR"

The key rule is that **each upgrade batch has boundaries clear enough to reason about**. If two artifacts have synchronized version requirements, upgrading them separately can produce an unsupported combination.

Examples:

- Modules of the same framework usually should align via a BOM/platform.
- A core library and its extension modules may need the same generation.
- A driver and ORM dialect may require mutually supported versions.
- A Gradle plugin may require a minimum Gradle/JDK version.
- A Servlet/Jakarta namespace migration may require updating the framework and integrations together.

The proper unit of upgrade is a **coherent upgrade unit**: a group of dependencies changing together for a sound technical reason, paired with a clear verification goal.

For instance:

~~~text
Batch 1: upgrade Gradle wrapper and required plugins to build on the new JDK
Batch 2: switch toolchain/compiler release and verify bytecode baseline
Batch 3: upgrade JSON stack together via BOM
Batch 4: upgrade JDBC driver while keeping DB server/schema fixed
Batch 5: upgrade ORM/dialect and verify transactions
Batch 6: change schema/database server under a separate plan
~~~

This is an illustrative split, not a mandatory sequence for every system. Where dependencies have version constraints, redesign the ordering accordingly.

## 8. Why Should You Avoid Uncontrolled "Latest" Versions?

Configuration prone to non-reproducible builds:

~~~kotlin
dependencies {
    implementation("com.example:client:+")
}
~~~

The `+` indicates dynamic version selection under resolution rules. Today's build and the next build can resolve different binaries if a newer version is published to the repository.

For a dependency being migrated, usually select an explicit, verified version:

~~~kotlin
dependencies {
    implementation("com.example:client:2.7.3")
}
~~~

The artifact name and version above are examples only. In real projects, verify version metadata and choose a release with an appropriate support policy. Pinning a version improves reproducibility but does not replace checking transitive dependencies or compatibility.

Similarly, calling the newest release "best" is not always true. A new major release may require a higher JDK baseline, change namespaces, or be incompatible with the current framework. Decisions should rely on **requirements and evidence**, not release age alone.

## 9. Version Catalogs, BOMs, and Constraints: Management Tools, Not Proof

With Gradle, version catalogs centralize coordinates and versions in one place:

~~~toml
# gradle/libs.versions.toml - illustrative example
[versions]
jackson = "2.17.2"

[libraries]
jackson-databind = { module = "com.fasterxml.jackson.core:jackson-databind", version.ref = "jackson" }
~~~

In `build.gradle.kts`:

~~~kotlin
dependencies {
    implementation(libs.jackson.databind)
}
~~~

A version catalog prevents scattered version declarations, yet by itself it **does not force** every dependency to unify. Transitive dependencies or platform constraints can cause the actual version to differ from what is written in the catalog. Inspect the **resolved graph**.

For ecosystems with a BOM/platform, for example:

~~~kotlin
dependencies {
    implementation(platform("com.example:example-bom:3.1.0"))
    implementation("com.example:module-a")
    implementation("com.example:module-b")
}
~~~

These coordinates are placeholders. A BOM defines version selection rules for the modules it manages; it does not guarantee that all of those modules have been tested against your consumers.

If using `enforcedPlatform` or strict version constraints, understand how they affect dependency resolution and library consumers. Forcing a version merely to "silence conflicts" can cause another module to hit binary errors at runtime.

## 10. Avoiding Changing Too Many Variables in One Pull Request

Suppose one pull request simultaneously:

1. Upgrades JDK 17 to 21.
2. Upgrades the Gradle wrapper.
3. Upgrades the web framework to a new major release.
4. Upgrades Jackson, JDBC driver, Hibernate, and logging.
5. Changes the database schema and JSON DTOs.
6. Changes TLS configuration and the garbage collector.

When the system throws `NoSuchMethodError`, it is unclear which library, classloader, BOM conflict, or changed API caused it. When latency increases, it is equally hard to attribute to GC, driver, ORM, or query plans.

Split into pull requests with distinct objectives and criteria. A well-scoped PR usually has:

- A clear hypothesis: "Upgrade HTTP client X from A to B to support the target JDK."
- A related set of changed artifacts with an explainable relationship.
- Accompanying migration code changes if APIs break.
- Tests targeting the identified risks.
- A resolved graph diff and key release notes.
- A rollback path independent of unrelated changes.

Still, splitting PRs must keep the repository in a buildable state. Sometimes two changes must land in the same batch because no supported intermediate state exists; in such cases, document why clearly and increase test depth.

## 11. "No Source Changes" Does Not Mean "No Behavior Changes"

A driver or library can preserve method signatures while changing semantics:

| Library | Changes Possible Even When Source Builds Pass |
|---|---|
| HTTP client | Retries, redirects, proxies, TLS defaults |
| JSON mapper | Null inclusion, enum naming, unknown fields, date formats |
| JDBC driver | `getObject()` mapping, timezones, decimal scale |
| ORM | Flush ordering, lazy loading, query generation |
| Logging | Timestamp formats, MDC propagation, log levels |
| Metrics | Metric names, tags, and units |
| Caching | TTL interpretation, eviction order, serializers |
| Security library | Token validation, certificate rules, algorithm availability |

Therefore, dependency upgrades need **behavioral contract tests** wherever consumers rely on semantics. One test can outweigh hundreds of trivial tests if it guards the actual complex contract.

## 12. Example: Upgrading a JSON Library Around Data Contracts

A service has an API returning:

~~~json
{
  "customerId": "C-42",
  "active": true,
  "registeredAt": "2026-11-12T08:00:00Z"
}
~~~

When upgrading the JSON library, verify:

- Are null fields included in JSON or omitted?
- Are enums serialized by name, value, or custom serializer?
- What format and timezone do `Instant`, `LocalDateTime`, and `OffsetDateTime` use?
- Do large numbers lose precision?
- Are unknown properties ignored or rejected on deserialization?
- Does polymorphic type deserialization enforce proper security constraints?
- Does key ordering change in ways consumers actually depend on?
- Can historical payloads still be read?

A **golden fixture** can store inputs and expected domain results, or expected JSON per contract. If an intentional, documented change occurs, update fixtures under review; do not blindly accept every diff by "regenerating snapshots" without inspecting the contents.

Example Java record representing a contract (Java 16+):

~~~java
public record CustomerPayload(
        String customerId,
        boolean active,
        java.time.Instant registeredAt
) {}
~~~

This is an illustrative domain type; actual mapping depends on serializer configuration. The record compiling does not prove JSON output is compatible. Test round-trip serialization–deserialization using the exact selected library version.

## 13. Example: Upgrading a JDBC Driver While Keeping Schema Fixed

To isolate the driver's impact, keep the database server/schema and test data identical and compare:

~~~text
Driver A + schema S + JDK R --> Result set A
Driver B + schema S + JDK R --> Result set B

Compare according to contract:
- NULL vs 0/false
- DECIMAL precision/scale
- DATE/TIMESTAMP/timezone/DST
- Unicode/emoji
- generated keys
- transaction rollback
- SQLState/exception classification
~~~

For monetary values, use `BigDecimal` and contract-appropriate comparisons rather than converting to `double`. For timestamps, determine whether the column represents an instant or local date-time; otherwise, asserting "identical to old output" may cement a long-standing bug.

If the new driver supports only the new JDK, it is not always possible to keep the JVM identical. In that case, explicitly state that tests compare the **driver/JDK combination** rather than claiming isolated driver impact.

## 14. Example: Upgrading Build Plugins Separately from Runtime Dependencies

A plugin can fail when Gradle runs on a new JDK even if business application code has no issues. Factors include:

- The plugin uses Gradle APIs that changed.
- The plugin relies on internal JDK APIs or deep reflection.
- The plugin needs a different class-file version or JDK tool.
- An annotation processor rejects new syntax or bytecode.
- A code generator produces different sources after upgrading.
- The plugin alters task ordering or incremental build behavior.

A sound workflow:

1. Pin the JDK running Gradle/Maven.
2. Check the compatibility matrix of the build tool and plugins.
3. Upgrade required wrappers/plugins as a synchronized unit.
4. Keep the application's source/target/release level at the declared baseline.
5. Diff generated sources and packaging.
6. Run clean builds and key tasks.
7. Separate build-tool compatibility outcomes from application behavioral test results.

With Gradle Java toolchains, the JDK running Gradle and the JDK used to compile/test can differ. Configuring a **toolchain** does not automatically prove the artifact runs on the minimum supported JDK.

## 15. Java `--release` and Bytecode Do Not Guarantee All Dependencies Are Compatible

When building on a new JDK while supporting an older runtime, Gradle can be configured:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
}
~~~

The illustrative example above instructs the Java 21 compiler to emit Java 17 source/bytecode and restricts referenced Java SE APIs to release 17. It does not control the bytecode of dependency JARs already built elsewhere.

A library may publish a new version requiring Java 21. Even if the main application compiles with `--release 17`, a Java 17 runtime can still fail to load the dependency class with `UnsupportedClassVersionError`.

Therefore, check:

- Minimum Java version of **every critical runtime dependency**.
- Class-file major version of relevant artifacts.
- Module path, automatic modules, and `exports/opens`.
- Real runtime tests on the minimum supported JDK.
- Plugins or Java agents have versions compatible with the target JDK.

Do not write "Java 17 compatible" merely because your own module sets `options.release = 17`.

## 16. Detecting Dependency Conflicts Before Production

Library A may require a newer version of module C, while library B was built against an older version of C. Gradle resolution can pick a version per constraints/rules, yet the Java runtime may still suffer binary incompatibility.

Example:

~~~text
service
  +-- library-a:2.0 --> common-core:4.0
  +-- library-b:1.0 --> common-core:2.0
  |
  +-- resolved common-core:4.0
~~~

This graph does not prove B is compatible with common-core 4.0. B may call a removed method, causing `NoSuchMethodError` when that code path executes.

Actions to consider:

- Read release notes and requirements of A/B/C.
- Inspect ecosystem version constraints/BOMs.
- Run `dependencyInsight` and diff the graph.
- Use API/binary compatibility analysis when both old and new artifacts exist.
- Run integration tests that genuinely exercise those components.
- If no supported combination exists, upgrade the whole cluster or replace the dependency.

Do not blindly `force` a version just to silence resolution warnings without evaluating consumers. **Resolution success** is a necessary condition for building, not a conclusion of compatibility.

## 17. API Changes and Binary Compatibility

A new library version can:

- Rename or remove methods/classes.
- Change method descriptors or visibility.
- Alter generic signatures and affect source compilation.
- Add overloads creating ambiguity with `null` or lambdas.
- Add an abstract method to an interface, breaking implementors.
- Add a default method creating conflicts.
- Change return/parameter types or checked exceptions in the API contract.
- Change module exports and reflective access permissions.

Old API example:

~~~java
public String normalize(String input);
~~~

New API:

~~~java
public String normalize(CharSequence input);
~~~

Source may compile when compatible types are passed, yet previously compiled consumer bytecode referencing `normalize(String)` can hit `NoSuchMethodError` if the library drops the old method.

Therefore, verify **source compatibility** by recompiling older consumers and **binary compatibility** by running bytecode compiled against the old library against the new library artifact. Those two checks answer different questions.

API diff tools can help catch static changes, but cannot replace runtime behavioral tests.

## 18. Setting Evidence Standards for Every Upgrade PR

A dependency upgrade pull request should have a concise but informative structure:

| Item | Contents |
|---|---|
| Reason for upgrade | Vulnerability fix, new JDK support, specific feature or bug |
| Artifact | Group, name, old → new version |
| Related cluster | BOM/platform and dependencies forced to upgrade together |
| Environment | JDK, OS, Gradle/Maven, database/framework |
| API/behavior diff | Notable changes and affected consumers |
| Graph diff | Direct/transitive changes and conflict resolution |
| Tests | Compile, unit, integration, contract, runtime, security |
| Results | PASS/FAIL, logs/reports, versions, and limitations |
| Rollback | How to revert to the previous build and data limitations |
| Owner | Assignee and reviewer |
| Remaining risk | Untested cases and rationale for acceptance |

Example record:

~~~yaml
dependencyUpgrade:
  component: "example-service"
  changedArtifacts:
    - artifact: "com.example:client"
      fromVersion: "2.4.1"
      toVersion: "2.7.3"
  javaRuntime: "17"
  evidence:
    sourceCompile: PASS
    unitTests: PASS
    integrationTests: PASS
    consumerContract: PASS
    securityNegativeCases: PASS
  unresolved:
    - "not tested on Windows"
  rollback:
    artifact: "previous signed deployment artifact"
  decision: CONDITIONAL_GO
~~~

This is an illustrative template, **not real test results**. When applying in CI, include commit, artifact digest, resolved dependency report, JDK build, log paths, and actual test scope.

## 19. Evidence Depth Must Match the Risk of the Change

Not every library needs the same test matrix. You can define **risk tiers** such as:

### Low Tier: Dependencies with Minimal Runtime Impact

For example, test helpers, minor patch updates not exposing APIs to consumers. Usually check compilation, relevant test suites, dependency graph checks, and artifact packaging.

### Medium Tier: Runtime Utilities or HTTP Clients

Requires targeted unit, integration, contract, exception handling, timeout, TLS, and startup tests. If external-module consumers exist, consider binary compatibility tests.

### High Tier: ORM, JDBC, Serialization, Security, Runtime Agents

Requires contract tests, boundary data, negative tests, JDK runtime matrix, integration with real systems or equivalent environments, load/canary tests, and a rollback plan. For schemas or event formats, verify rolling deployments and reading historical data.

This is only a structural suggestion. A "patch release" may still require High Tier checks if it touches payment flows or security. **Risk level is based on actual impact**, not just MAJOR/MINOR/PATCH numbers.

## 20. Cases Requiring Urgent Security Upgrades

Avoiding unverified bulk upgrades does not mean indefinitely delaying critical vulnerability fixes. If an advisory affects the real application, prioritize remediation per security policy and exposure.

Emergency workflows should still retain minimum verification:

1. Confirm affected artifacts/versions and exposed code paths.
2. Identify the patched version or vendor-supported mitigation.
3. Upgrade the **minimal necessary cluster** rather than dragging in unrelated dependencies.
4. Run focused builds/tests and security negative tests for the relevant risk.
5. Test in staging/canary if possible, with rollback and observability.
6. Record acceptance rationale for less-tested areas and a follow-up plan.

Sometimes temporary mitigations outside a dependency update are necessary, but record the owner, expiration, and replacement criteria. Avoid re-enabling weak TLS algorithms, disabling authorization, or loosening policies just to make a new version run.

Speed and verification are not mutually exclusive; the goal is **small, risk-targeted evidence under time pressure**.

## 21. Separating Dependency Upgrades from Unrelated Business Fixes

Another pitfall is piggybacking large refactors or business-logic edits onto an "upgrade PR". This makes diffs hard to read and test failures hard to explain.

Distinguish:

- **Dependency bump:** the chosen version or artifact.
- **Required migration:** code edits needed to meet new APIs, configuration, or behavior.
- **Incidental cleanup:** optional style, variable-renaming, or structural changes.
- **Behavior redesign:** changes to the application's own contracts.

Changes strictly required for the upgrade to work can stay in the same PR, but should be described separately. Unrelated refactors should be split out whenever possible.

For example, when upgrading a serializer and needing to change a null-handling adapter, document explicitly which behavior changed, why, and which contract tests protect consumers. Do not bundle an overhaul of every DTO format if it is not required by the dependency bump.

## 22. Risks of Upgrading Data/Schema Simultaneously

A dependency upgrade may require a new schema or data format. Once production data is migrated, rolling back binaries may not reverse the schema or data.

Example:

~~~text
Release A:
  app v1 + driver v1 + schema S1

Release B:
  app v2 + driver v2 + schema S2
~~~

If S2 alters column types, JSON encoding, or drops fields, app v1 might fail to read data written by v2. Hence, design **roll-forward/rollback** capabilities for both data and code.

The expand–migrate–contract strategy can be suitable:

1. **Expand schema:** add columns/fields or a compatibility layer that older apps can still use.
2. **Migrate consumers and data:** transition gradually with measurement and consistency checks.
3. **Contract:** drop old fields only after all supported consumers have migrated.

When a change cannot be rolled back safely, the plan must state so clearly and prioritize roll-forward recovery instead of promising an unworkable rollback.

## 23. CI Pipeline: Multi-Layer Verification Instead of One Signal

A dependency-upgrade pipeline can be divided into:

~~~text
Dependency change
      |
Resolve + lock + verify artifact identity
      |
Compile / static analysis / API diff
      |
Focused unit tests
      |
Contract + integration tests
      |
Target JDK runtime matrix
      |
Package + staging / canary
      |
Evidence review + go/no-go
~~~

Steps should match risk and infrastructure. For slow tests or tests relying on external environments, separate CI jobs can be used, but the release decision must know which tests ran and when.

### 23.1. Gradle Dependency Checks

Reference commands:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind \
  --configuration runtimeClasspath
./gradlew test
./gradlew integrationTest
~~~

`integrationTest` is merely an example custom task; not every project has it. Documentation or pipelines must use real tasks configured in the repository.

**Never treat a command existing in a checklist as proof that it actually ran.** Results must have corresponding logs, commits, JDKs, and artifacts.

### 23.2. Verifying the Minimum JDK

If a library claims Java 17 support, test on actual Java 17; compiling with JDK 21 and `--release 17` alone does not prove runtime dependencies have Java 17-compatible bytecode and APIs.

You can set the test launcher via Gradle toolchains:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(javaToolchains.launcherFor {
        languageVersion.set(JavaLanguageVersion.of(17))
    })
}
~~~

JDK 17 must be present or provided by a toolchain resolver. For broader JDK matrices, create separate jobs to avoid assuming one test launcher suffices for every supported runtime.

## 24. Reading Failure Outcomes to Preserve Root-Cause Attribution

When an upgrade step fails, do not rush to bump another batch of dependencies just to "make errors disappear". Classify the failure:

| Signal | Investigation |
|---|---|
| `cannot find symbol` | Source API changed, compile classpath, JDK baseline |
| `NoSuchMethodError` | Binary API incompatibility or transitive version conflict |
| `ClassNotFoundException` | Missing artifact, classloader, shading, module path |
| `UnsupportedClassVersionError` | Dependency bytecode requires a higher JDK |
| `InaccessibleObjectException` | Reflection into non-open package, older framework |
| `SSLHandshakeException` | TLS/certificate/endpoint/provider; do not disable validation |
| `SQLDataException` or wrong mapping | JDBC driver, SQL type, precision/timezone |
| Different serialization snapshot | Mapper config, library behavior, API contract |
| Memory/latency spike | Pooling, buffering, serializer, GC, instrumentation |
| Flaky test | Timing, concurrency, shared fixture, external service |

A good experiment isolates the smallest change sufficient to trigger the failure. You can temporarily revert a bump on a test branch, diff artifacts/graphs, or build a minimal reproduction. These diagnostic steps establish causal proof rather than guessing from when the error appeared.

## 25. Checkpointed Batch Upgrade Roadmap

In a multi-module repository, you can execute:

### Phase A: Inventory and Target JDK Selection

Record dependency graphs and JDK compatibility, and choose compiler/runtime baselines. Classify direct blockers.

### Phase B: Upgrading Build Tools and Core Plugins

Ensure Gradle/Maven, code generators, and test frameworks can run on the target JDK. Keep output artifacts compatible with the minimum runtime.

### Phase C: Upgrading Independent Library Clusters

Separate logging, HTTP, JSON, JDBC, ORM, or framework stacks per actual constraints. Each cluster has its own contract tests.

### Phase D: Integration and Consumer Testing

Test source/binary, behavioral, schema, security, and performance compatibility within the chosen scope. Do not equate "my module is green" with "downstream consumers are safe".

### Phase E: Canary and Observation

Monitor errors, latency, memory, success rates, data anomalies, and business metrics. Define rollout stop criteria.

### Phase F: Finalizing Evidence and Opening the Next Cluster

Save reports, update status, and confirm rollback/roll-forward plans before starting the next batch. If regressions appear, retain the closest reproducible baseline.

A checkpoint does not require a separate public release, but it must map to exact commits, artifacts, and tests.

## 26. Managing Consumers Outside the Module

A shared library may be used by multiple applications. Even when the library author and its own tests pass, consumers can be impacted by:

- Changes to public/protected APIs or SPIs.
- Runtime dependencies upgraded transitively.
- Version conflicts with libraries declared directly by the consumer.
- Interface/default method or exception behavior changes.
- Changes in module exports/opens or reflective integration.
- Serialization or persistence data contract changes.
- A new minimum Java version.

Maintain a **consumer inventory** and representative contract tests. If not all external consumers are known, do not claim "backward compatible with all applications"; state the verified scope and remaining risks.

When libraries publish SemVer, PATCH/MINOR/MAJOR signal release intent rather than replacing test results. A patch release can still change behavior; a major release does not automatically break every consumer.

## 27. When May Multiple Dependencies Be Bundled into One Batch?

There are cases where bundling multiple artifacts is the right technical choice:

- A BOM/framework release requires synchronized upgrades.
- Modules belong to a single distribution with mandatory version alignment.
- New library A requires new B/C with no intermediate supported combination.
- A security fix is released as a unified stack version.
- A namespace migration (such as the Jakarta ecosystem) requires updating related integrations together.

To bundle with control:

1. State the dependency constraint or reason it cannot be split.
2. Keep the bundle as technically small as possible.
3. Define the "shared contract" of the entire cluster.
4. Run integration/consumer tests covering interactions across the cluster.
5. Save before/after graphs and confirm version alignment.
6. Treat it as a single appropriate rollback or roll-forward unit.

**Bundled upgrades with clear rationale and evidence** are not "reckless bulk upgrades". The difference lies in explainability, verification, and accountability.

## 28. Report Template for Prime or Reviewers

An upgrade summary can be written as:

~~~text
Objective:
  Upgrade library-client A -> B for JDK 21 compatibility.

Scope:
  library-client + required transport module per BOM.
  No changes to database schema, JSON DTOs, or runtime JDK.

Evidence:
  Dependency graph diff: reviewed
  Source compile: PASS
  Old consumer binary test: PASS
  Contract integration tests: PASS
  TLS negative tests: PASS
  JDK 17 runtime test: NOT_APPLICABLE (artifact now requires Java 21)

Remaining risk:
  Windows deployment and external plugins have not yet been tested.

Decision:
  Staging/canary before rollout; monitor handshake errors,
  latency, and client retries; roll back to the previous artifact if needed.
~~~

This is a **presentation template**, not actual results from a live run. Replace artifact names, JDKs, results, and scope according to the exact report.

If a test has not been run, record `NOT_RUN` or `NOT_TESTED` rather than treating it as PASS. If a test is not applicable, explain why. If an exception is approved, record the owner, review date, and remaining risk level.

## 29. Misconceptions to Avoid

**"Upgrading as many dependencies at once as possible is faster."** It may mean fewer PRs, yet debugging failures and rolling back becomes harder; total regression-fixing time may actually be higher.

**"One dependency is a mandatory upgrade unit."** False for frameworks, BOMs, or version-aligned modules. Pick consistent dependency clusters.

**"A centralized version catalog eliminates conflicts."** A catalog manages declarations; resolved graphs can still differ due to transitive dependencies or constraints.

**"A green build proves production safety."** A build does not execute all contracts, datasets, and production environments.

**"Patch releases are guaranteed non-breaking."** Versioning reflects publisher intent; real consumers must still be tested.

**"Upgrading to latest is always the most secure and compatible."** Too new a version may require a different JDK or framework baseline, while an older release may carry critical advisories. Choose by support and evidence.

**"With `--release 17`, all dependencies run on Java 17."** `--release` controls code compiled by that compiler, not pre-built bytecode inside JARs.

**"Successful dependency resolution means binary-compatible."** A resolved graph can still harbor runtime method mismatches.

**"Swapping a driver without changing code requires no data tests."** JDBC mappings can still change for nulls, decimals, timestamps, and vendor types.

**"When upgrading a security library, disable validation so nothing breaks."** Disabling security checks is not a safe compatibility fix.

**"Rollback just means reverting the Git commit."** If schemas or data changed incompatibly, rolling back binaries can fail.

**"Test evidence has to be huge to be useful."** A small, risk-targeted test suite with exact logs and versions is far more valuable than a test list detached from decisions.

## 30. Checklist When Approving Dependency Upgrades

- [ ] Described the specific rationale for each upgrade.
- [ ] Recorded current JDK, Gradle/Maven, runtime, container, and baseline.
- [ ] Inventoried direct, transitive, test, plugin, runtime, and agent dependencies.
- [ ] Preserved resolved graphs and lockfiles/verification metadata where applicable.
- [ ] Identified artifact clusters that must be upgraded together.
- [ ] Avoided dynamic versions or out-of-scope pins lacking evidence.
- [ ] Reviewed breaking changes, deprecations, Java baselines, and compatibility policies.
- [ ] Tested source, binary, and behavioral compatibility commensurate with risk.
- [ ] Ran targeted unit/contract/integration tests.
- [ ] Verified boundary data and JSON/JDBC/schema formats where relevant.
- [ ] Tested the minimum JVM the application claims to support.
- [ ] Tested relevant positive/negative security cases.
- [ ] Verified performance and resource lifecycles for sensitive components.
- [ ] Saved test reports, commits, resolved versions, and artifact digests.
- [ ] Explicitly listed untested environments/consumers.
- [ ] Established owner, go/no-go decision, and rollback/roll-forward plan.
- [ ] Established a checkpoint before moving to the next dependency group.

## Conclusion

**Avoiding unverified bulk upgrades** does not mean slowing down upgrades or holding onto old dependencies indefinitely. It is a risk-control principle: split changes into logical clusters, define compatibility boundaries, lock down reproducible environments, pick tests tied to consumer contracts, and record evidence at each checkpoint.

In Java Advance Compatibility Migration, you must verify JDK/compiler/runtime, build plugins, direct/transitive dependencies, API/binary compatibility, behavior, data, and security together. A small pull request with clear scope and strong evidence is usually safer than an "upgrade everything to latest" batch backed only by a green build. Even when upgrading a synchronized stack or shipping an urgent vulnerability fix, apply the same discipline: **state the reason, limit scope, target the actual risks, document limitations, and provide a recovery path**.
