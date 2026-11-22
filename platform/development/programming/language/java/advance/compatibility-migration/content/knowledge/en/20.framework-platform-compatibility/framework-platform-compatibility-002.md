# Separating JDK Upgrades from Major Framework Upgrades When Possible

In a long-lived Java project, upgrading the JDK and upgrading the major framework version are often bundled into one task because both relate to "moving to newer Java". However, these are **two distinct axes of change**. Upgrading the JDK affects the JVM, Java SE APIs, bytecode, compiler, module encapsulation, TLS, GC, foundational libraries, and how the application runs. Upgrading a major framework version, by contrast, can alter dependency structures, annotations, configuration, lifecycles, routing, security defaults, persistence behavior, integration contracts, and how the framework initializes the application.

If both change at the same time, an `InaccessibleObjectException`, an ORM query returning different results, or an endpoint returning 404 can stem from multiple sources. The team struggles to pinpoint which change caused the error, struggles to roll back, and struggles to prove whether the application is compatible with the new JDK or with the new framework. Therefore, whenever technical constraints permit, **separate JDK upgrades from major framework upgrades into independent steps with their own baselines, verification, and recovery paths**.

Still, "when possible" is an important qualifier. The current framework may not support the target JDK; the next framework generation may require a higher minimum JDK than the current JDK; or a migration from `javax.*` to `jakarta.*` may mandate upgrading the framework/container alongside the API set. In such cases, establish a **bridge release** and a feasible upgrade chain rather than forcing a runtime combination unsupported by vendors.

This lesson covers how to read support matrices, split the roadmap, control dependencies and build tools, design experiments to attribute failures, structure rollouts/rollbacks, and handle scenarios where coordinated upgrades are necessary.

## 1. Two Change Axes That Must Be Tracked Independently

### 1.1. The JDK Axis

Changing the JDK can alter:

- **JVM runtime:** class loading, bytecode verification, JIT, garbage collectors, memory layout, threading, and diagnostic flags.
- **Java SE APIs:** new APIs, deprecated or removed APIs, and behavioral shifts in standard library classes.
- **Strong encapsulation:** access to internal JDK packages and reflection-related errors.
- **Compiler/toolchain:** `javac`, `--release`, class-file version, annotation processing, and test runners.
- **Security defaults:** TLS protocols, certificate validation, disabled algorithms, and keystore/provider behaviors.
- **Runtime packaging:** classpath/module path, Java agents, container images, `jlink`, or launchers.
- **Operational characteristics:** heap sizing, cgroup detection, GC logs, startup/warm-up, and performance.

An application can be impacted without changing a single line of business code when switching JVMs or JDK vendors/updates. Therefore, **runtime behavior**, not compilation alone, must be verified.

### 1.2. The Major Framework Axis

Changing a major framework version can alter:

- **Public APIs and annotations:** package names, method signatures, and annotation attributes.
- **Auto-configuration:** component scanning, beans, dependency injection, and default configuration.
- **Web stack:** servlet containers, HTTP routing, request/response binding, validation, and exception mapping.
- **Persistence:** ORM mapping, transaction semantics, generated SQL, lazy-loading behavior, and dialects.
- **Security:** filter chains, authentication/authorization defaults, CSRF, CORS, session management, and TLS integration.
- **Serialization:** Jackson/Gson adapters, date/time handling, enums, polymorphic typing, and message converters.
- **Observability:** logging, metrics, tracing, health checks, and management endpoints.
- **Dependency BOM:** transitive versions of bundled libraries and containers.
- **Build plugins:** executable JAR creation, testing, AOT/native compilation, and layered images.
- **Compatibility contracts:** stored data, queue messages, sessions, and partner API consumers.

Even when the new major framework runs on the old JDK, this change alone can still introduce business bugs or break external contracts.

### 1.3. Why Separate Them?

Suppose the system currently runs:

~~~text
Old JDK + Framework major A
~~~

Combined upgrade:

~~~text
(Old JDK, Framework A)
           |
           v
(New JDK, Framework B)
~~~

If a regression occurs, two large sets of changes must be investigated simultaneously. When the support matrix allows, split into:

~~~text
(Old JDK, Framework A)
           |
           | Upgrade JDK only
           v
(New JDK, Framework A)
           |
           | Upgrade framework major only
           v
(New JDK, Framework B)
~~~

Alternatively, upgrade the framework within the active major line to a patch/minor release supporting the new JDK first, and then upgrade the JDK. The key point is not enforcing one fixed sequence, but **introducing at each transition only the changes needed to reach a supported combination**.

## 2. The Compatibility Matrix Comes First

Before planning, build the JDK × framework matrix. Do not extrapolate from a framework release merely compiling a trivial demo.

| | Current JDK | Target JDK |
|---|---|---|
| Current framework | A — running baseline | B — desired intermediate step |
| New major framework | C — alternative intermediate step | D — target state |

The combinations:

- **A:** the live environment currently running, which must be saved as the baseline.
- **B:** ideal for verifying JDK impact in isolation, **feasible only if the current framework supports the new JDK**.
- **C:** usable for verifying framework upgrade first in isolation, **feasible only if the new major supports the current JDK**.
- **D:** the desired final state, requiring full verification.

All four cells do not have to be valid. For example, a new major framework requiring at least JDK 17 will not run on JDK 11; in that case cell C is invalid. An older framework release may not support JDK 21; in that case cell B is invalid. The team must locate an **intermediate release or different order**, rather than forcing an unsupported runtime with JVM flags.

### 2.1. Evaluation Levels for Each Cell

Distinguish:

1. **Officially vendor-supported:** the combination lies within the support matrix and remains within maintenance policy.
2. **Unverified:** lacks information or test runs; never default to assuming compatible.
3. **Starts in smoke tests:** useful evidence, yet does not replace vendor support commitments or integration tests.
4. **Unsupported:** excluded from target design or used only in short-lived experiments with accepted risk.
5. **Verified by the project:** tested against actual business/deployment flows with specific artifacts and environments recorded.

A combination may "start up" without being vendor-supported, or sit inside a support table while the application still fails due to custom code. Both kinds of evidence complement each other.

### 2.2. Checking Multiple Layers of the Support Matrix

Do not ask only "Which Java version does the framework support?" Check:

- **Framework core** and patch/minor releases in the current major line.
- **Framework build plugins** and supported Maven/Gradle versions.
- **Embedded servlet/reactive servers** or application servers.
- **ORM/JPA providers** and database drivers.
- **Serialization libraries**, HTTP clients, and tracing/metrics agents.
- **Bytecode tools:** ASM, Byte Buddy, cglib, Javassist, instrumentation.
- **Java agents:** APM, profiler, monitoring, and security agents.
- **Annotation processors and generated code** in the project.
- **Third-party starters/extensions** outside framework core.
- **OS/CPU and container base images** if native dependencies exist.
- **JDK vendor and updates** when support or bugs depend on a specific build.

A framework may support JDK 21 while the project's build plugin is still on an unsupported version. Never infer readiness from a single line on the framework's overview page.

## 3. "Upgrading the JDK" Has Multiple Steps: Do Not Merge Compile and Runtime

A JDK change can be broken down further:

### 3.1. Changing the Build Tool JDK

Maven or Gradle runs on its respective JVM. Older plugins can fail as soon as build logic loads if APIs are missing or class-file versions mismatch.

### 3.2. Changing the Compiler/Toolchain

A project can compile with a new JDK while publishing artifacts targeting a lower baseline via `--release`:

~~~text
Build JDK: 21
javac --release 17
Required runtime: Java 17 or newer if dependencies are also compatible
~~~

`--release` controls the Java language level, Java SE APIs, and class-file target emitted by the compiler. It does **not** guarantee every third-party dependency in the artifact supports the older runtime, nor does it control the JVM executing Maven/Gradle.

### 3.3. Changing the Production Runtime

This is where the application actually executes on the new JVM in a container, VM, or server. It tests TLS, GC, class loading, logging, native dependencies, performance, and runtime behavior.

### 3.4. Adopting New Java Features

Starting to use records, pattern matching, virtual threads, or newer Java APIs is a separate decision changing source/runtime requirements. If the goal is isolating the JDK's impact, **avoid simultaneously introducing unnecessary new language features** during the runtime switch.

One possible sequence: upgrade Maven/Gradle and toolchain while keeping the old `--release`; run the current framework on the new JDK if supported; upgrade framework major; and only finally advance the Java source/target baseline intentionally.

## 4. Conditions for Upgrading the JDK First

You can prioritize **JDK-first** when:

- The current framework line has a vendor-confirmed release running on the target JDK.
- Essential plugins, agents, and libraries have patches compatible with the target JDK without needing a new framework major.
- Internal JDK APIs are no longer used by the project/framework, or a valid supported alternative exists.
- The system has sufficient tests to confirm behavior on the target JDK.
- Canary instances can run on the new JDK while holding the app/framework version constant.
- Runtime JDK rollback can use the exact same artifact without changing external data contracts.

Example roadmap:

~~~text
A: Current Framework 2.x patch + JDK 17
     |
     | Upgrade patches within same major if needed
     v
A': Supported Framework 2.x patch + JDK 17
     |
     | Switch runtime and build toolchain to JDK 21
     v
B: Supported Framework 2.x patch + JDK 21
     |
     | Once running stably, upgrade framework major
     v
D: Supported Framework 3.x + JDK 21
~~~

**Important:** major names in the diagram are hypothetical. A specific Framework 2.x may **not** support JDK 21; in that case step B is eliminated. Check the support matrix for the exact framework and version rather than copying the diagram verbatim into a project.

### 4.1. Benefits of JDK-First

If B passes, the team has proven that the new JDK runtime does not break critical behavior while the framework stays fixed. Regressions appearing at step B typically point to the JDK, bytecode/tooling, providers, agents, or operational environment rather than framework-major breaking changes.

That simplifies release notes and rollbacks: within design bounds, you can roll back to the old JDK runtime without simultaneously rolling back the framework or changed API contracts.

### 4.2. Never Force an Old Framework to Run with JVM Flags

Some projects hit `InaccessibleObjectException` and add many flags:

~~~text
--add-opens java.base/java.lang=ALL-UNNAMED
--add-opens java.base/java.util=ALL-UNNAMED
~~~

These flags can serve as temporary workarounds for reflective access where permitted by the JDK, but they **do not turn an unsupported framework version into a guaranteed combination**. If the framework relies on removed internal classes or a bytecode library fails on the new JDK, opening packages will not fix it.

Every workaround requires an owner, rationale, tests, a review date, and a library/framework upgrade plan to remove it.

## 5. Conditions for Upgrading the Framework First

You can prioritize **framework-first** when:

- The new major framework still supports the current JDK.
- Most breaking changes live in APIs/configs/framework and can be verified before switching runtimes.
- Dependencies of the new framework can run on the current JDK.
- Annotations, routing, security, or persistence should be addressed first to reduce risk during the runtime upgrade.
- Code and packaging can keep the current Java target during the initial phase.
- No incompatible data change prevents immediate rollback.

Roadmap:

~~~text
A: Framework A + Old JDK
          |
          | Upgrade framework, keep JDK
          v
C: Framework B + Old JDK
          |
          | Once stable, upgrade JDK
          v
D: Framework B + New JDK
~~~

Again, C is feasible only when framework B supports the old JDK. For example, framework majors requiring a higher minimum Java level invalidate this path.

### 5.1. Benefits of Framework-First

If C passes, changes to routing, dependency injection, transactions, JSON binding, ORM, and security defaults have already been verified independently of the new JDK. Step D then focuses on runtime and toolchain.

### 5.2. A Framework Major May Enforce a New Minimum JDK

If major B requires JDK 17 while the project runs on JDK 11, C cannot go into production even if some classes happen to compile on the current JDK. Do not set `--release 11` and expect framework B to run on Java 11 when core framework dependencies carry Java 17 class-file versions or call new APIs.

In this situation, look for a patch/minor of framework A supporting an intermediate JDK or conduct a coordinated upgrade with broader test coverage.

## 6. When Neither Intermediate Step Is Supported

This is the hard case: the old framework does not support the target JDK, while the new framework does not support the current JDK.

~~~text
A: Old framework + Old JDK        D: New framework + New JDK
           \                       /
            \   No valid B or C   /
             ---------------------
~~~

Strategies:

1. **Check for a framework bridge release:** a minor/patch release within the old major that added intermediate JDK support, or an intermediate major supporting both JDKs.
2. **Check for an intermediate JDK:** transition through a JDK release supported by both the current framework and the next framework.
3. **Separate at the build and test levels even when impossible in production:** prepare independent PRs for build tool/JDK compatibility, framework API changes, dependencies, and deployment; integrate only after matrix testing.
4. **Use a dedicated migration branch:** keep production stable while maintaining an integration branch with checkpoints and tests to control changes.
5. **Use compatibility adapters or the strangler pattern:** isolate the hard-to-upgrade framework portion in a separate service/process communicating via stable contracts.
6. **Execute a controlled coordinated upgrade:** if no supported intermediate combination exists, roll out the new JDK + framework together while raising safeguards via fixtures, canary rollouts, and practical rollbacks.

Do not fork the old framework solely to "patch in new JDK support" unless the team has capacity to maintain and thoroughly test it. That is a major engineering commitment, not a default option.

### 6.1. Distinguishing No Intermediate Path from Insufficient Data

A support matrix missing data is **unverified**, not "guaranteed un-splittable". Inspect release notes, compatibility tables, and the dependency graph for each candidate framework version. Without evidence, state the uncertainty explicitly rather than locking a roadmap on guesses.

## 7. Patches and Minor Versions Can Serve as Bridges

A low-risk step is upgrading to the **latest supported patch/minor of the same major line** before touching the JDK or framework major.

Model example:

~~~text
Framework A.1 + JDK X
       |
       | Upgrade patch/minor A.9 (no major change)
       v
Framework A.9 + JDK X
       |
       | If A.9 supports JDK Y
       v
Framework A.9 + JDK Y
       |
       | Upgrade major B (on JDK Y)
       v
Framework B + JDK Y
~~~

Do not assume SemVer guarantees every minor release only adds non-breaking features. Framework ecosystems can introduce breaking changes in transitive dependencies or altered configuration defaults. Testing and reading release notes remain essential.

Patch/minor bridges are often helpful because vendors may have already updated ASM, bytecode tooling, Java agents, JSON libraries, or declared newer Java support inside a maintenance release of the current major.

## 8. Illustrative Example with the Spring Ecosystem

Spring is a common example of why JDK upgrades and framework major upgrades must be distinguished. Spring Boot/Spring Framework projects can undergo major shifts across major versions: Java baseline, Spring Security configuration, web/server stack, validation/servlet APIs, and the Jakarta namespace.

### 8.1. Changing `javax.*` to `jakarta.*` Is a Framework/Platform Change

In modern Jakarta EE generations, many enterprise APIs moved from `javax.*` packages to `jakarta.*`, for example:

~~~java
// Old API style:
import javax.servlet.http.HttpServletRequest;
import javax.persistence.Entity;
import javax.validation.Valid;

// New API style in the corresponding ecosystem:
import jakarta.servlet.http.HttpServletRequest;
import jakarta.persistence.Entity;
import jakarta.validation.Valid;
~~~

This is **not** an automatic side effect of upgrading the JDK. JDK 17 does not "rename javax packages to jakarta" for the application. That change originates from Jakarta EE, framework, servlet container, JPA/validation provider versions, and accompanying dependencies.

If you upgrade the JDK, change the Spring Boot major, and switch `javax`→`jakarta` simultaneously, failures such as `ClassNotFoundException`, `NoSuchMethodError`, or silent validation bypasses can stem from multiple sources. When a bridge framework version exists, separating code and dependency edits into distinct steps simplifies investigation.

### 8.2. Example Project Plan

A project might design:

1. Lock the baseline of the current Spring Boot and Java versions.
2. Upgrade to an appropriate patch release within the same Spring Boot line to update dependencies/JDK support if available.
3. Upgrade the JDK runtime first **if that patch release is declared to support the target JDK**.
4. Once the JDK runtime passes, migrate the Spring Boot major in a separate change covering Jakarta packages, security configuration, ORM, and integration tests.
5. If no older Boot release supports the target JDK, choose an intermediate JDK or perform a coordinated migration.

Never apply one generic version map across every Spring project. Spring Boot and Spring Framework lines have differing min/max Java requirements and compatibility across releases. Check the matrix for the project's **specific version**.

### 8.3. Beyond Core Framework

A Spring Boot application may use:

- Spring Data and Hibernate/JPA providers.
- Spring Security and OAuth/JWT integrations.
- Embedded Tomcat/Jetty/Undertow or a reactive Netty stack.
- Jackson and JSON modules.
- Micrometer, OpenTelemetry, and tracing exporters.
- Spring Cloud ecosystem and third-party starters.
- Database migration tools.
- Testcontainers, Mockito, Byte Buddy, and JUnit.
- APM/Java agents.

Each group carries its own compatibility matrix. Never overlook Spring Cloud or a custom starter simply because Spring Boot core supports the target JDK.

## 9. With Quarkus, Micronaut, Jakarta EE, and Application Servers

The same principles apply across Java platforms.

### 9.1. Quarkus

Quarkus performs build-time augmentation, bytecode generation, CDI, and persistence integration, and can build native executables. Major Quarkus upgrades often impact build plugins, extensions, and build-time processing mechanisms, not just the runtime JDK. If upgrading the JDK at the same time, errors can happen during augmentation before the app even runs.

Verify the Java baseline and extensions for the exact Quarkus version, then separate build/runtime updates from supported major upgrades.

### 9.2. Micronaut

Micronaut relies on annotation processing and compile-time dependency injection. A new JDK or major framework version may require matching annotation processors and Gradle/Maven plugins. A green build whose generated classes fail at runtime can stem from mixing processor and runtime versions.

Manage processor paths and runtime libraries against the compatibility matrix together, rather than merely changing `JAVA_HOME`.

### 9.3. Jakarta EE / Java EE and Application Servers

WAR/EAR applications depend on both the API specification and the **application server** (for example, an appropriate Tomcat/WildFly/Payara/WebLogic release line). Upgrading the JDK requires verifying the supported server version; migrating Jakarta EE namespaces requires verifying servlet, persistence, validation, CDI, and WAR libraries.

Often the runtime/container provided by operations does not reside inside the application artifact. Hence, a Maven dependency list alone does not reflect the full framework/platform environment.

## 10. Freezing Factors Outside the Step Under Test

The purpose of separating upgrades is controlling variables.

When testing JDK-first:

- Hold application/framework versions and BOMs fixed as far as permitted.
- Hold database schemas, API contracts, message schemas, and business configuration fixed.
- Avoid proactively changing routing/security behavior simultaneously.
- If a build plugin or driver must upgrade to support the JDK, document it as a **mandatory supporting dependency change**, rather than calling the stage strictly "JDK-only".
- Keep test data, traffic mix, and SLO metrics identical for comparison.

When testing framework-first:

- Hold the JDK runtime fixed if supported by the new major.
- Keep unrelated JVM options fixed.
- Separate deferrable data migrations.
- Explicitly record transitive dependencies altered by the BOM/framework.
- Avoid adopting new Java language features simultaneously unless required by the framework.

**It is not always possible to change just one file or one version.** Separation here means separating **causal axes and verification goals**, while transparently listing mandatory supporting changes.

## 11. Managing Maven and Gradle to Separate Changes

### 11.1. Maven: Separating Java Release from Framework Dependencies

Example key section of `pom.xml`:

~~~xml
<properties>
    <java.version>17</java.version>
    <maven.compiler.release>17</maven.compiler.release>
</properties>
~~~

Real projects may use properties defined by a framework parent/BOM. Keep clear intent:

- `maven.compiler.release` controls the Java target if the Maven Compiler Plugin uses this property.
- Parent/BOM versions and framework plugins determine APIs, dependencies, and framework build behavior.
- The JDK running Maven is determined by the environment or toolchain, not locked merely by Java properties.

Example setting compiler release on the plugin:

~~~xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-compiler-plugin</artifactId>
  <version>3.13.0</version>
  <configuration>
    <release>17</release>
  </configuration>
</plugin>
~~~

The plugin version is illustrative; pick a version compatible with your project's Maven/JDK.

A pipeline can have JDK-first swap `JAVA_HOME` / Maven toolchain and container base image first while holding the framework BOM steady. Under framework-first, change the framework parent/BOM and corresponding code while holding the JDK runtime steady if supported.

### 11.2. Gradle: Distinguishing Java Toolchain from Plugin Versions

Groovy DSL example:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'VERSION_DA_DUOC_XAC_MINH'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`VERSION_DA_DUOC_XAC_MINH` is a placeholder, not a plugin version to use directly. Replace it with an actual vendor-supported version. Verify that the Gradle version supports both the build JVM and the target Java toolchain.

- Build/toolchain JDK can change in the JDK migration step.
- Framework plugin versions change in the framework migration step.
- `options.release` can remain fixed to avoid changing the source/bytecode baseline at the same time.
- If the new major framework requires a higher Java baseline, update `--release` when reaching that step and test thoroughly.

### 11.3. Locking the Dependency Graph and Saving Evidence

A framework BOM can upgrade dozens of transitive dependencies even when source changes only one version line. Inspect:

~~~bash
# Maven
./mvnw dependency:tree
./mvnw help:effective-pom

# Gradle
./gradlew dependencies
./gradlew dependencyInsight --dependency jackson-core
~~~

Illustrative commands; `dependencyInsight` requires an appropriate configuration in many projects. Compare outputs across **both transition points** to see which dependencies changed in the JDK step versus the framework step.

Do not assume dependency locking or a BOM resolves every runtime conflict. Production also involves container-provided JARs, Java agents, and runtime layers outside the build.

## 12. Separating Build-Time Compatibility from Application Runtime Compatibility

A project may build on a new JDK while running the old application on an older runtime, or vice versa. Build-time components such as annotation processors, code generators, test runners, and Maven/Gradle plugins carry their own compatibility constraints.

Example:

~~~text
Build system:
  Maven/Gradle Wrapper
          |
          v
  JDK running build tool
          |
          +--> Annotation processor / code generation
          |
          +--> Compiler toolchain / --release
          |
          v
      Application artifact
                |
                v
Production:
  Runtime JDK + framework libraries
                |
                v
    DB / cache / queue / external services
~~~

An `UnsupportedClassVersionError` in an annotation processor can trigger before the program runs. An `InaccessibleObjectException` in an ORM may trigger only when an entity is mapped at runtime. Never slap on a generic label like "Java 21 incompatible with framework" if the actual issue sits in a build plugin or test instrumentation.

Record explicitly whether the failure occurred at **build bootstrap**, **compilation**, **test JVM**, **application startup**, or **production request**.

## 13. Establishing a Baseline Before Upgrading Either Axis

A baseline must be a runnable version, not just a commit hash.

At minimum record:

| Group | Required Information |
|---|---|
| Source | Commit/tag and uncommitted changes |
| JDK | Vendor, feature/update/build, OS/architecture |
| Framework | Core version, plugin versions, starters/extensions |
| Build | Maven/Gradle Wrapper, plugins, toolchains, `--release` |
| Dependencies | BOM/lockfile, resolved dependency tree, agents |
| Runtime | Container image digest, JVM options, memory/GC settings |
| Infrastructure | Database driver/version, broker/cache/client versions |
| Data contracts | Database schemas, caches, sessions, events/messages |
| Tests | Unit, integration, contract, load, compatibility suites |
| Operations | SLOs, p95/p99 latency, error rates, startup, memory/CPU |
| Deployment | Launch command, health checks, rollout/rollback plan |

If the baseline already has known failures, document them explicitly. When upgrading, avoid blaming pre-existing failures on the new JDK or framework.

### 13.1. Minimal-Change Rule

A migration step should have clear **goals and acceptance criteria**:

~~~text
Change JDK runtime from JDK X to JDK Y.
Framework major/version stays constant except explicitly documented patches.
No changes to public API or persistence schema.
Acceptance: previous behavior and SLO tests pass on JDK Y.
Rollback: restore JDK X runtime image with unchanged app artifact.
~~~

This is an example policy, not a valid commitment for every project. If a library must upgrade alongside the JDK, list it in the change log and test that library's impact separately.

## 14. Testing to Pinpoint Exact Regression Causes

To distinguish JDK and framework impacts, run the same **test suite and datasets** across supported combinations.

### 14.1. Test Categories

1. **Build/compiler tests:** toolchains, generated sources, annotation processors, and test plugins.
2. **Unit tests:** business logic with minimal infrastructure dependence.
3. **Framework integration tests:** dependency injection, routing, validation, security, persistence, and transactions.
4. **Contract tests:** public HTTP/gRPC APIs, event schemas, and partner integrations.
5. **Data compatibility tests:** reading database/cache/session/message data created by previous versions.
6. **Runtime/observability tests:** startup, JVM flags, TLS, agents, logging, GC, and metrics.
7. **Performance/load tests:** latency, throughput, memory, CPU, warmup, and tail latency.
8. **Rollback tests:** whether the older version can revert cleanly after new-version data/requests.

Never use a single startup smoke test as overall proof that an upgrade succeeded.

### 14.2. Golden Fixtures and Legacy-Version Data

Maintain reusable fixtures across stages:

~~~text
fixtures/
  http/
    request-v1.json
    response-v1.json
  persistence/
    sample-data-v1.sql
  cache/
    cache-entry-v1.bin
  session/
    session-v1.json
  messages/
    order-created-v1.json
~~~

Fixtures must use synthetic/anonymized data and never commit secrets, real JWTs, or sensitive customer information into Git.

When testing JDK-first, use the same fixtures with the old framework. When testing framework-major, continue using those fixtures to spot serialization, ORM, and validation changes. If data is written under the new version, test backward reading if rolling deployments or rollbacks require it.

## 15. Observing JDK Changes That Framework Tests Might Miss

### 15.1. Strong Encapsulation and Reflection

Newer JDKs may restrict reflection into internal JDK packages. Older frameworks, bytecode libraries, and instrumentation tools can encounter:

~~~text
java.lang.reflect.InaccessibleObjectException
java.lang.IllegalAccessError
~~~

The preferred fix is upgrading the library or switching to public APIs. `--add-opens` should serve only as a controlled, documented bridge.

### 15.2. TLS and Security Providers

Newer JDKs may enforce different disabled algorithms, TLS protocols, or truststores. Connection errors to APIs, databases, or brokers are not necessarily caused by a framework major upgrade.

When testing JDK-first, keeping the framework fixed separates JDK security changes from client/framework changes.

### 15.3. GC and Memory

Newer JDKs differ in default GCs, memory ergonomics, and container awareness across releases. An application showing higher throughput yet worse p99 latency must be evaluated with real workloads. Never conclude from an isolated microbenchmark or unit tests alone.

### 15.4. Bytecode, Class Loading, and Agents

APM/security agents, proxies, mocking, and bytecode instrumentation can rely on class-file versions or internal APIs. Verify agent versions supporting the new JDK. A framework working fine with agents disabled while failing in production may point to the agent rather than framework core.

### 15.5. Removed/Deprecated Java APIs

Some APIs/tools present in older JDKs were relocated or removed in newer generations. When frameworks/libraries depend on them, add replacement dependencies or adjust integrations. `--add-opens` cannot bring back a removed class.

## 16. Observing Framework Changes That JDK Tests Might Miss

### 16.1. Web and Validation

A new framework major version may alter:

- Handler mapping or route-matching precedence.
- JSON serialization defaults.
- Validation annotations and exception mapping.
- HTTP status codes for invalid inputs.
- Filter chains, CORS/CSRF, and redirect/login behavior.
- Content negotiation and multipart/file uploads.

These changes can occur even when the runtime JDK does not change. Use consumer contract tests and end-to-end tests rather than only testing controller methods directly.

### 16.2. ORM and Transactions

Upgrading ORM providers/dialects can change generated SQL, fetch strategies, query translation, schema validation, or transaction boundaries. A query passing unit tests on an in-memory/mock database can fail on production databases.

Test against a database engine/version close to production with anonymized realistic data and proper migration scripts. When database schemas change, design expand–contract and separate rollback plans.

### 16.3. Dependency Injection and AOP

Bean lifecycles, proxy semantics, annotation processing, and conditionals can shift. A bean might instantiate in a different order; an aspect might no longer match; or an exception handler might no longer trigger as before.

Bugs of this sort belong to framework-major behavior rather than the JDK runtime if they appear only on combination D after B has passed.

### 16.4. Configuration Defaults and Actuator Endpoints

A new framework major version can rename properties, remove deprecated properties, or alter defaults. Config properties losing effect sometimes raise no exceptions; the application still starts while behaving differently.

Enable detection of unknown/deprecated configuration properties where supported by the framework and verify critical settings after upgrading.

## 17. Data and Protocols Living Across Multiple Versions

Even when separating JDK and framework upgrades into two deployments, data in databases, Redis, sessions, and brokers can **persist across both deployments**.

Example:

~~~text
App v1 / Framework A / JDK X
      |
      +--> Cache value v1
      +--> Session v1
      +--> Kafka event v1
      |
 Upgrade JDK
      v
App v1 / Framework A / JDK Y
      |
      +--> Still reads v1 data
      |
Upgrade Framework
      v
App v2 / Framework B / JDK Y
      |
      +--> Must read remaining legacy data
~~~

A framework major upgrade may change default serializers, session principal types, Jackson settings, entity names, or event mappings. Testing only on data created by the new version misses compatibility risks.

Principles:

- Version payloads/schemas instead of coupling long-term persistence to Java class serialization whenever possible.
- When changing schemas, upgrade **readers before writers** in rolling-deployment systems.
- Use expand–migrate–contract for databases and persisted state.
- Keep adapters/compatibility readers throughout TTLs, retention windows, DLQ/replay periods, and backup policies.
- Do not wipe sessions, idempotency keys, or messages solely to dodge migration errors.
- Test rollback for both **code** and **data**: can the old app read new data?

Separating the JDK from the framework merely reduces changing variables; it does not replace a data compatibility plan.

## 18. Canary, Rolling Deployment, and Dark Launch

To reduce risk, run a subset of instances on the new combination before rolling out system-wide.

### 18.1. JDK-First Canary

If the current framework supports both old and new JDKs:

~~~text
90% traffic -> Framework A + JDK X
10% traffic -> Framework A + JDK Y
~~~

Use the same artifact and equivalent request/workload mix where applicable. Compare CPU, heap, p95/p99 latency, error rates, TLS, and logs. If errors occur only in the JDK Y cohort, isolate to JDK/environment.

### 18.2. Framework-Major Canary

Once JDK Y stabilizes:

~~~text
90% traffic -> Framework A + JDK Y
10% traffic -> Framework B + JDK Y
~~~

Compare HTTP contracts, persistence behavior, security flows, serialization, and framework metrics. If errors appear only in the framework B cohort, the root cause is narrowed.

### 18.3. Shared State Can Break Canary Isolation

A canary cohort can write a new cache/session/event schema into shared storage and break the older cohort. Check:

- Cache key namespaces and serializers.
- Session compatibility across nodes.
- Database schemas and transactional migrations.
- Message producer/consumer schema compatibility.
- Token signing keys, claims, and cookie settings.
- Whether canary-only feature flags emit data unreadable by older readers.

Application canaries do not automatically isolate **data contracts**. Without two-way compatibility, version namespaces or constrain writers to avoid sending new formats unintentionally to older consumers.

## 19. Using Feature Flags Within the Right Scope

Feature flags can decouple framework behavioral shifts from runtime deployment. For example, after upgrading the framework major, you can keep the old processing path as default and enable the new path for a slice of traffic.

However, not every change can hide behind a flag:

- Classfile/JDK compatibility affects startup and class loading.
- `javax`→`jakarta` namespaces can affect compilation/linking and cannot simply switch at runtime via a boolean.
- An ORM migration that already changed schema or wrote different data formats cannot roll back via a flag.
- Security defaults changed at the framework layer can impact requests before feature code executes.

Feature flags work well for code paths that can safely coexist in parallel and be tested. Never use flags as an excuse to bypass support matrices or data compatibility.

## 20. Release Train and Commit Strategy

To keep reviews manageable, split changes into purposeful groups:

| Change Group | Objective | Do Not Arbitrarily Bundle |
|---|---|---|
| Build baseline | Wrapper, compatible plugins, test infrastructure | Business features |
| JDK adaptation | Toolchains, JVM config, replacement JDK APIs | Framework major |
| Dependency maintenance | Patches/minors supporting the target runtime | Unrelated bulk dependency swaps |
| Framework API migration | Annotations, configs, package namespaces | Another JDK upgrade |
| Data contract migration | Schemas, cache/session/message adapters | Uncontrolled data deletion |
| Deployment | Container image, runtime, flags, health checks | Out-of-scope public API changes |
| Cleanup | Remove workarounds, deprecated code, bridges | Risky untested changes |

Every item does not need its own PR in every organization, yet each must carry **evidence and clear accountability**. Putting all changes in one commit makes error diagnosis and rollback far harder.

### 20.1. Never Use "Green Build" as the Sole Gate

A framework-major PR may compile cleanly while security filter ordering shifts; a JDK-upgrade PR may pass unit tests while TLS to partner systems fails. Gate by real risk:

- Compilation and test coverage.
- API/contract compatibility.
- Integration with DBs, caches, brokers, and third parties.
- Security regressions.
- Runtime/startup/performance.
- Packaging/production-like deployment.
- Rollback and state compatibility.

## 21. A Complete Example: REST + Database + Kafka System

Suppose a Java service consists of:

~~~text
REST API + security + ORM
          |
          +--> PostgreSQL
          +--> Redis sessions/cache
          +--> Kafka producer/consumer
          +--> External payment API
~~~

The team wants to move from JDK X to JDK Y and upgrade framework A to B.

### 21.1. Inventory and Support Matrix

Record:

- Does the current patch of framework A support JDK Y?
- What minimum JDK does framework B require?
- Are the JDBC driver, Kafka client, Redis client, ORM, and security libraries compatible?
- Do any libraries/agents use internal JDK APIs?
- Are there Java-serialized cache/session objects from framework A?
- How long will app v1 and v2 run concurrently?
- Are there irreversible database migrations?

### 21.2. If Step B (JDK-First) Is Supported

1. Upgrade minimal build tools/plugins to run on JDK Y.
2. Keep framework A and API contracts, adjusting incompatible JDK APIs if any.
3. Build with the old `--release` if needed; test on JDK Y.
4. Build a JDK Y image and canary with the same app artifact.
5. Verify TLS to the payment API, database, Kafka, Redis, and metrics/GC.
6. Roll out JDK Y.
7. After observation, start the framework B branch.
8. Upgrade the framework BOM, namespaces/configs, security, persistence, and serialization.
9. Test data/sessions/events produced by the prior version.
10. Roll out framework B with adapters/schema compatibility, then clean up bridges.

### 21.3. If Step B Is Not Supported

1. Check patch/minor releases of framework A or an intermediate JDK.
2. If a bridge exists, select a supported version chain.
3. If no bridge exists, design a coordinated upgrade with dedicated checkpoints for build, framework APIs, JDK/runtime, and data schemas.
4. Increase integration, rolling-compatibility, and rollback tests because no valid intermediate production environment exists.
5. Document clearly why full separation is infeasible, avoiding claims like "we tried and saw the framework doesn't support it" without vendor/test evidence.

### 21.4. Sample Tracking Table

| Stage | JDK | Framework | Key Changes | Gate |
|---|---|---|---|---|
| A baseline | X | A | Unchanged | Existing tests + metrics |
| A' maintenance | X | A patched | Essential patches only | Regression and dependency diff |
| B runtime | Y | A patched | JDK/container/toolchain | TLS, agents, GC, integration, SLO |
| D framework | Y | B | API/BOM/config/framework | Contract, ORM, security, data, rollback |
| Cleanup | Y | B | Remove bridges and flags | Historical data/retention evidence |

If B is invalid, replace the table with a supported roadmap; never run B in production solely to fill a cell in a plan.

## 22. Measuring Performance Along Each Axis of Change

Upgrading the JDK and framework can both affect performance, via different mechanisms.

**The JDK can impact** JIT compilation, GC pauses, heap sizing, crypto throughput, startup, and thread scheduling.

**The framework can impact** the request pipeline, serialization, ORM query counts, proxy creation, dependency injection, caching, and tracing overhead.

To measure accurately:

- Use identical test data and workload patterns.
- Include proper warm-up, separating cold-start from steady-state.
- Compare p50/p95/p99, throughput, error rates, CPU, heap/GC, and connection pools.
- Keep resource limits and container environments identical where feasible.
- Track SQL query counts, external calls, and serialized payload sizes.
- Repeat runs to reduce noise rather than taking a single run.
- Never conclude "the new JDK is faster/slower" if frameworks or dependencies also changed in the same benchmark.

Publish measurements across A/B/D to identify where changes predominantly arise.

## 23. Security and Support Policies Can Force Faster Upgrades

When an old framework has reached end-of-support, delaying the major upgrade too long just to isolate the JDK can increase security risk. Conversely, staying on an unsupported JDK for long periods while waiting on a framework may also be unacceptable.

Decisions should weigh:

- Support lifecycles of the JDK vendor and framework.
- Needed CVE patches.
- Feasibility of bridge releases.
- Risks of unsupported runtimes.
- Testability and rollback capability.
- Business impact of a coordinated upgrade versus deferral.
- Number of integrations and third-party libraries needing updates.

**Separating upgrade steps is a risk-reduction tool, not an absolute goal.** If separating forces the system to stay too long on an unmaintained runtime/framework, a tightly controlled coordinated upgrade path may take priority.

## 24. Rollback: Distinguishing Code, Runtime, and Data

One benefit of splitting steps is easier rollback, yet only when state has not changed one-way.

### 24.1. Rolling Back the JDK Step

When keeping the same artifact/framework and unchanged data, rollback can consist primarily of reverting the container/JDK runtime image. Still check:

- Do artifacts carry bytecode/API targets compatible with the old JDK?
- Did the new JDK cause data to be persisted in a format unreadable by the old JDK?
- Are keystores, TLS, timezones, native libraries, and configs compatible?
- Did jobs/messages emitted while running the new JDK differ in format?

### 24.2. Rolling Back the Major Framework Step

Harder if the new framework already:

- Altered database schemas or data.
- Wrote caches/sessions with a new serializer.
- Emitted events in a new JSON/Avro/Protobuf schema.
- Changed cookie/session token formats or security claims.
- Renamed entities/classes so the old Java deserializer fails to read them.
- Modified migration metadata or outbox/inbox structures.

Appropriate expand–contract, dual-read, or compatibility adapter strategies are required. Simply reverting to the old framework JAR does not guarantee safety.

### 24.3. Accounting for the Point of No Return

A deployment may cross a **point of no return**: once an old schema is dropped, old signing keys are revoked, or producers emit an event type the old consumer cannot handle, reverting to the old version is no longer straightforward.

Identify this point before rollout with dedicated approval conditions. Upgrading the JDK first reduces some risks, yet does not remove the responsibility to manage the point of no return for framework/data migrations.

## 25. Symptoms and How to Find the Failing Axis

| Symptom | Primary Suspect Axis | What to Verify |
|---|---|---|
| `UnsupportedClassVersionError` | JDK/bytecode/toolchain | Classfile target and JVM actually executing |
| `InaccessibleObjectException` | JDK encapsulation or framework reflection | Library calling reflection, JDK version, opens |
| `NoClassDefFoundError` after major update | Framework/dependency or runtime | BOM, class name, removed APIs, and classpath |
| `javax.*` / `jakarta.*` errors | Framework/platform API migration | Namespaces, container/JPA/validation versions |
| Bean not found | Framework | Component scanning, annotations, conditions |
| HTTP routing/security behavior differs | Framework | Routing/filter/authorization configuration |
| TLS handshake fails only on new JDK | JDK security/provider or client library | Disabled algorithms, trust, protocols |
| ORM SQL/queries differ after framework major | Framework/dependencies | Hibernate/dialect, generated SQL, transactions |
| JSON payload changes after major | Serializer/framework | Jackson/message converters, contract fixtures |
| Startup/GC/p99 shifts after JDK-only | JDK/runtime | JVM options, heap, GC, agents, workload |
| Build scripts fail to run on new JDK | Build tools/plugins | Wrapper, build JVM, Gradle/Maven compatibility |
| Old caches/sessions cannot be read | Framework serializer or class evolution | Golden fixtures, schema versions, class names |
| Rollback still fails after reverting code | Shared data contracts | DB/cache/messages/tokens written by new version |

Do not treat this table as an automatic conclusion. A `NoSuchMethodError` can also result from dependency binary mismatches when swapping only the JDK if an agent/library was bumped. Always inspect exact artifacts and stack traces.

## 26. Regression Investigation Workflow Using A–B–D Comparison

If a valid passing B exists:

1. Reproduce the failure on D.
2. Check whether the failure also occurs on B under the same JDK.
3. If not, compare dependency/config/framework diffs between B and D.
4. If it does, compare JDK/runtime/toolchain diffs between A and B.
5. Run a minimal test with the same inputs, DB, broker, and environment.
6. Inspect root cause; record exact loaded class/provider/driver versions.
7. Confirm the fix with regression tests across still-supported combinations.
8. Log in the changelog whether the bug belonged to the JDK axis, framework axis, or a forced supporting dependency.

If B does not exist, use integration branch milestones, component-level unit/integration tests, dependency diffs, and rollback checkpoints to narrow causes. Never spin up unsupported combinations in production to investigate without risk controls.

## 27. Acceptance Criteria for Each Stage

### 27.1. JDK Step

- [ ] Target JDK falls within vendor support of active frameworks/dependencies.
- [ ] Build tools and plugins run on the target JDK/toolchain.
- [ ] Compiler release target is explicit.
- [ ] Unit/integration tests pass without unresolved regressions.
- [ ] TLS, databases, messaging, and security providers function.
- [ ] No incompatible Java agents/native libraries exist.
- [ ] Startup, heap/GC, latency, and error rates stay within acceptable thresholds.
- [ ] Operations documentation and JVM flags are updated.
- [ ] Runtime rollback has been tested within current data boundaries.

### 27.2. Framework Major Step

- [ ] Target framework and ecosystem are supported on the selected JDK.
- [ ] API/annotation/config migrations have been applied.
- [ ] BOM/third-party starters, security, and ORM dependencies are controlled.
- [ ] HTTP/gRPC/event contracts and external integrations have been tested.
- [ ] Legacy sessions/caches/serialized data remain readable over the support window.
- [ ] Database migrations apply expand–contract where required.
- [ ] Canary/mixed deployments maintain necessary two-way compatibility.
- [ ] Observability, management endpoints, and tracing/metrics work.
- [ ] Rollback has been tested, accounting for any point of no return.
- [ ] Legacy workarounds are removed only with supporting verification evidence.

## 28. Misleading Assumptions

**"Both JDK upgrades and framework upgrades are Java upgrades, so putting them in one PR is faster."** It may mean fewer PRs, yet increases variables and regression triage time. Weigh total risk and operational cost, not only coding time.

**"The old framework compiles on the new JDK, so the vendor supports it."** Incorrect. Compilation, smoke tests, and support policy are distinct levels of evidence.

**"The new framework will fix all new-JDK issues."** Not guaranteed. Build plugins, Java agents, JDBC drivers, TLS providers, or custom code still carry independent compatibility requirements.

**"Always upgrade the JDK first."** Wrong if the old framework does not support the target JDK. Look for a bridge, intermediate JDK, or coordinated upgrade instead.

**"Always upgrade the framework first."** Wrong if the framework major requires a higher minimum JDK than the current runtime.

**"Running on a new JDK while keeping the old --release means we're only using the old JDK."** Incorrect. `--release` restricts compiler APIs/bytecode, while runtime behavior of the new JVM still differs.

**"Just changing javax to jakarta finishes the major migration."** Insufficient. Servlet containers, persistence, security, validation, dependencies, configs, and external contracts all need testing.

**"A 10% canary isolates the change completely."** False if those 10% of instances write new schemas into shared Redis, databases, or brokers.

**"Framework rollback just means redeploying the old image."** False once databases/sessions/messages have been altered one-way by the new writer.

**"Adding enough --add-opens means the project is compatible with the new JDK."** Insufficient. It may only bypass reflective access failures temporarily while weakening encapsulation.

**"One passing build and unit test run means the upgrade is finished."** Insufficient for systems with DBs, queues, security, production agents, and performance requirements.

## 29. Planning Checklist for Separating Upgrades

- [ ] Specified exact old/new JDK versions (vendor, update) and exact old/new framework versions.
- [ ] Built the A/B/C/D matrix distinguishing supported, unsupported, and unknown cells.
- [ ] Checked compatibility matrices for framework core, build plugins, and ecosystem.
- [ ] Looked for patch/minor releases or intermediate JDKs that can serve as bridges.
- [ ] Chose JDK-first, framework-first, or coordinated migration with documented rationale.
- [ ] Distinguished build JDK, compiler toolchain, `--release`, and production runtime.
- [ ] Froze unrelated changes in each stage where feasible.
- [ ] Saved baseline source, dependency trees, container/JVM configs, and test metrics.
- [ ] Checked libraries using internal JDK APIs or bytecode instrumentation.
- [ ] Checked ORM, security, web, JSON, validation, and application server layers.
- [ ] Added tests covering persisted data/sessions/caches/messages from prior versions.
- [ ] Designed canary/mixed-version rollouts safe for shared state.
- [ ] Identified which data and APIs cannot be rolled back.
- [ ] Prepared artifact/runtime/data rollback strategies for each stage.
- [ ] Monitored performance, GC, TLS, tracing, error rates, and business KPIs.
- [ ] Documented temporary workarounds, owners, and removal criteria.
- [ ] Ensured final target state sits within vendor support per policy.
- [ ] Recorded test results and technical decisions for infeasible combinations.

## 30. Conclusion

**Separating JDK upgrades from major framework upgrades** is a strategy that reduces changing variables, improves root-cause isolation for regressions, and simplifies testing and rollback in Java Advance Compatibility Migration. When the current framework supports the new JDK, you can upgrade the JDK first and the framework second. When the new framework supports the current JDK, you can go in reverse. In both cases, patch/minor releases and intermediate JDKs can act as bridges avoiding an oversized transition.

Intermediate cells in the JDK × framework matrix are not always valid. If the old framework lacks target JDK support and the new major framework requires a higher JDK than currently running, design a bridge path or a **controlled coordinated upgrade**, rather than running unsupported combinations in production merely for the appearance of "two phases".

Success is not defined by an application compiling or starting up once. Each stage must be backed by artifacts, dependency graphs, integration/contract tests, historical data checks, operational metrics, and rollback readiness. The practical principle is: **vary one axis at a time whenever possible, record mandatory supporting changes explicitly, and advance to the next stage only after the preceding stage produces solid compatibility evidence**.
