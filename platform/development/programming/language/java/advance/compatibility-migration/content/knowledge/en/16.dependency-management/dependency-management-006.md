# Inspecting unmaintained dependencies and choosing alternatives

In **Java Advance Compatibility Migration**, changing the JDK affects more than just source code written by developers. Every application also depends on frameworks, runtime libraries, build plugins, annotation processors, agents, native libraries, and transitive JARs that the development team may not directly declare. A component that is **no longer maintained** can block upgrading to a newer Java release, introduce unpatched security vulnerabilities, or leave the system permanently dependent on internal JDK APIs.

However, “unmaintained” cannot be determined solely from a repository having few commits or going a long time without bumping its version. A small, stable library that rarely changes can still meet requirements; conversely, a project with many commits that fails to fix security bugs can still pose high risk. Therefore, you must combine **maintenance status evidence**, **actual dependency paths**, **exposure levels**, **technical contracts**, and **operability on the target JDK** when choosing a solution.

This lesson presents how to inventory direct/transitive dependencies, identify signs of being unmaintained, evaluate options to upgrade, replace, remove, fork, or isolate them, and then verify functionality, data, binary compatibility, security, and performance before concluding a migration as successful.

## 1. Dependency scope in a Java application

Dependencies are not limited to `implementation` entries in Gradle or `<dependency>` entries in Maven. You must examine the entire chain that builds and runs the application.

| Group | Examples | Risk when upgrading the JDK |
|---|---|---|
| Compile libraries | API modules, annotations, utility classes | Syntax/APIs incompatible with target JDK |
| Runtime libraries | JSON, ORM, HTTP, database drivers | Class loading, serialization, network errors |
| Transitive dependencies | JARs pulled in by frameworks/clients | Old versions hidden inside the dependency graph |
| Build plugins | Compiler, packaging, shading, code generation | Plugin fails to run with new Gradle/Maven/JDK |
| Annotation processors | Mappers, metamodels, generators | Reliance on AST or javac internals |
| Test dependencies | Test runners, mocking, coverage | Tests not discovered or instrumentation fails |
| Java agents | APM, profilers, tracing | Bytecode transformation does not support new class-file version |
| Native dependencies | JNI/JNA, native crypto, compression | ABI/architecture or platform mismatch |
| Framework/container | Web runtime, DI, ORM | Java baseline, namespace, or configuration changes |
| Internal libraries | Shared SDKs, clients, common-core | No owner, CI, release, or support policy |
| Additional runtime libraries | Application server JARs, injected libraries | Running artifact differs from build graph |
| Images and tooling | JDK container images, Gradle/Maven wrapper | Broken toolchain or EOL runtime |

A dependency can appear across multiple groups. For example, an ORM framework uses a bytecode library for runtime proxies; the same library might also be used by a test runner for mocking. Upgrading one component while overlooking the other can create conflicts.

**Principle:** inventory along the path **source → build → resolved graph → packaged artifact → runtime/deployment**, rather than relying on a single declaration file.

## 2. Distinguishing deprecated, EOL, abandoned, and vulnerable

### 2.1. Deprecated

An API or package marked deprecated means the publisher no longer recommends using it or is directing users toward another API. Deprecation can span multiple releases. By itself, it does not prove a component is unmaintained.

### 2.2. End-of-life (EOL)

EOL typically applies to **a specific branch or version** under the publisher's policy. A project may still actively maintain newer branches while ceasing to provide security fixes for an older branch.

Hypothetical example: framework 1.x has reached end of support, while 2.x remains maintained. In that case, recording “framework X is unmaintained” is inaccurate; the risk lies in the **1.x branch** that the application uses.

### 2.3. Abandoned/unmaintained

A project may lose its maintainers, have its repository archived, halt its release process, or stop responding to vulnerabilities and new incompatibilities. This status must be verified from authoritative sources rather than inferred solely from the timestamp of the last commit.

### 2.4. Vulnerable

A component can have security advisories or CVEs even while actively maintained. Conversely, an unmaintained library does not necessarily have disclosed vulnerabilities. You need to evaluate the **exact artifact and version in use**, exploitability, actual code paths, and available patches.

| Status | Key question |
|---|---|
| Deprecated | Is there an official migration path or removal date? |
| EOL | Is the current version/branch still supported by the vendor? |
| Unmaintained | If a JDK/security bug arises, who can fix and release it? |
| Vulnerable | Is there an advisory affecting the application's version, code path, and configuration? |
| Unsupported JDK | Does the library support the target JDK, or is there testing evidence? |

A library can be in multiple states simultaneously. Handling must be prioritized based on overall risk.

## 3. Why Java migration exposes dependency risks

Common issues encountered when upgrading the JDK:

1. **Strong encapsulation:** old libraries accessing `sun.*`, `jdk.internal.*`, or using deep reflection may be blocked.
2. **Removed JDK APIs:** code may depend on components previously bundled with the JDK that no longer exist in the new runtime.
3. **Class-file version:** old bytecode parsers or instrumentation libraries do not understand the new major version.
4. **Source/AST compatibility:** annotation processors using internal `com.sun.tools.javac.*` structures may fail.
5. **Framework baseline:** the old framework version does not support the new runtime, while the new version requires a higher minimum JDK.
6. **Namespace migration:** some ecosystems transition from `javax.*` to `jakarta.*` across framework versions.
7. **TLS policy:** older HTTP or crypto libraries assume protocols and algorithms no longer enabled by default.
8. **Serialization behavior:** changing frameworks/codecs can alter serialized data or mapping results.
9. **Build/test tools:** old test runners and plugins may fail to start or silently fail to discover/run tests.
10. **Runtime packaging:** dependencies included in the fat JAR or container differ from the CI graph.

Therefore, “the source code compiled” is only a small piece of evidence. You must know whether the libraries in use can execute and receive bug fixes during the new JDK lifecycle.

## 4. Defining the inventory scope

Before assessing maintenance status, determine **what must be inspected**.

For each application or module, record:

- Service/module name and owner.
- Current JDK, target JDK, CI JDK, and runtime container JDK.
- Gradle/Maven wrapper version, compiler plugin, and key plugins.
- Direct dependencies and transitive dependencies.
- Compile/runtime/test/annotation-processor classpaths.
- Libraries provided by the application server or runtime platform.
- Java agents, native dependencies, and dynamically loaded JARs.
- Final artifact structure: plain JAR, fat JAR, WAR/EAR, image.
- Features, data, and protocols depending on the library under review.

A system may execute with dependencies different from its build: a driver installed in the application server, an agent attached via `JAVA_TOOL_OPTIONS`, or a plugin loaded from an external directory. Without inventorying these, they can cause post-deployment failures even when local builds pass.

### 4.1. Declared versions are not always actual versions

A dependency declaration may use a BOM, constraint, version range, or dynamic version. Illustrative example:

~~~groovy
dependencies {
    implementation 'org.example:protocol-client:2.+'
}
~~~

This is **not a recommended configuration** for a reproducible migration. The resolved version can vary over time, across caches, and across repositories. When building an inventory, record the actual resolved artifact coordinates, not just `2.+`.

A common identifier:

~~~text
groupId:artifactId:version
~~~

Depending on the build tool, there are also classifier, type, variant, and capabilities. Missing this information can lead to identifying the wrong artifact or failing to reproduce the dependency graph.

## 5. Inventorying with Gradle

With the Gradle Java plugin, reference commands:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

In a multi-module project:

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath
~~~

When tracing why a version was selected:

~~~bash
./gradlew :orders-service:dependencyInsight \
  --dependency jackson-databind \
  --configuration runtimeClasspath
~~~

`jackson-databind` is only an example name used to illustrate the investigation command; it does not imply any specific version is unmaintained.

### 5.1. Configurations to distinguish

| Configuration or classpath | Purpose |
|---|---|
| `compileClasspath` | APIs visible to the compiler |
| `runtimeClasspath` | JARs required by the application at runtime |
| `testRuntimeClasspath` | Libraries required when running tests |
| `annotationProcessor` | Processors executed at compile time |
| Buildscript/plugin classpath | Plugins executed by the build tool |
| Custom integration-test configurations | Libraries for integration/functional tests |

Do not overlook test dependencies. An old mock framework or coverage agent may not understand the new JDK's class-file version, breaking the build/test pipeline even when production libraries are compatible.

### 5.2. Build plugins

Reference command:

~~~bash
./gradlew buildEnvironment
~~~

This command helps inspect buildscript dependencies in applicable projects. Plugin resolution via `plugins {}` and `pluginManagement` may have its own mechanics; record plugin IDs/versions and verify compatibility with the JDK/Gradle wrapper rather than assuming a single report shows everything.

### 5.3. Controlling a reproducible graph

Gradle offers dependency locking, version catalogs, dependency constraints, and dependency verification. These mechanisms stabilize resolved versions and verify artifact integrity. They **do not by themselves prove a library is maintained**, but they enable accurate before/after comparison when upgrading the JDK.

## 6. Inventorying with Maven

Basic commands:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:legacy-codec
mvn help:effective-pom
~~~

`dependency:tree` shows the graph according to Maven resolution. `help:effective-pom` is helpful for seeing configuration inherited via parents, BOMs, and `dependencyManagement`.

Some versions of the Maven Dependency Plugin support:

~~~bash
mvn dependency:tree -Dverbose
~~~

Information on omitted/conflict nodes can vary depending on the plugin version. When evaluating, rely on actual output and resolved coordinates.

### 6.1. BOM and dependencyManagement

If `pom.xml` declares only group/artifact without a version, check whether the version comes from a parent or an imported BOM. Do not look at a single dependency line and assume it is using a newer version.

### 6.2. Plugin dependencies

Besides application dependencies, there are compiler, surefire, failsafe, shade, assembly, code generator, and other Maven plugins. A plugin that does not support the target Java version can fail the build before application code even compiles.

### 6.3. Dependency mediation

Maven resolves version conflicts based on dependency relationships and configured constraints; the winning version may not be the newest version. If overriding is necessary, understand the graph and upper-level dependency compatibility instead of manually altering JARs in the local Maven cache.

## 7. Inspecting the actually packaged artifact

After extracting the build graph, inspect the artifact that the runtime will use.

For example:

~~~bash
jar tf application.jar
~~~

In a fat JAR, libraries may be nested or shaded. With a WAR, the classpath can also include JARs provided by the servlet container. With a container image, the entrypoint may add Java agents or external libraries.

Questions to answer:

- Is an old JAR still present inside the artifact?
- Are multiple versions of the same library present across different directories?
- Is there shaded bytecode whose original artifact name no longer appears?
- Are native libraries loaded at runtime outside the dependency graph?
- Does a plugin or application server substitute a different version of a driver?

**Removing a dependency from a build file is not enough to prove it has disappeared from deployment.** You must verify the entire runtime composition.

## 8. SBOM and structured inventory

A **Software Bill of Materials (SBOM)** records components and dependency relationships in a machine-readable format, typically CycloneDX or SPDX.

An illustrative record:

~~~yaml
component:
  name: legacy-codec
  group: org.example
  version: 1.4.2
  purl: pkg:maven/org.example/legacy-codec@1.4.2
  direct: false
  scope: runtime
  introducedBy: org.example:protocol-client:3.0
  usedBy:
    - orders-service
  owner: integration-team
  reviewStatus: pending
~~~

The coordinates above are **hypothetical**, not a claim about the maintenance status of any real package.

An SBOM should be cross-checked against artifacts and deployments because some components may be injected by the runtime, embedded in an image, or dynamically loaded. For each component, record version, source repository, dependency relationships, owner, and review date.

An SBOM assists auditing, but does not by itself tell whether a component is well maintained. That status must still be grounded in official sources and evidence.

## 9. Signals suggesting a library may be unmaintained

| Signal | Meaning to investigate | Caution in interpretation |
|---|---|---|
| Official repository archived | May have stopped accepting changes | May have moved to a successor repository |
| Maintainer announced development halt | Strong evidence of project status | Check affected branch/version scope |
| No release for a long time | May not support newer JDKs yet | Stable libraries may not need frequent releases |
| Critical issues/PRs receive no response | Defect-handling capacity may be impaired | Check actual impact and official channels |
| Security advisory has no patch | High security risk | Verify exact exposure/version applicability |
| CI builds use a very old JDK | Lacks evidence of new runtime compatibility | Library might still work if APIs are very stable |
| Docs do not mention target JDK | Unclear support matrix | Do not automatically assume unmaintained |
| No active publisher/release maintainer | No path to ship fixes | Check for successor/fork projects |
| Dependency on removed APIs | Migration may be blocked | Check API replacement options and workarounds |
| Unclear license/provenance | Legal and supply-chain risk | Not direct proof regarding maintenance |

### 9.1. Sources of evidence to prioritize

Prioritize: maintainer/vendor announcements, support/EOL policies, official release notes, security advisories, changelogs, JDK compatibility documentation, artifact publication records, and the official repository.

Do not rely on a community statistics site without verifying against primary sources. Forks without a clear relationship to upstream can create misleading information.

### 9.2. Recording confidence levels

One approach:

- **Confirmed EOL:** the publisher has announced end of support for the version/branch.
- **Confirmed archived:** the official repository is archived with no plans for development there.
- **Likely unmaintained:** multiple strong signals without direct confirmation.
- **Maintained with caveats:** supported, but with JDK, feature, or security policy limitations.
- **Unknown:** insufficient evidence; requires an owner to investigate.

Do not turn `Unknown` into `Maintained` simply because a scanner found no CVEs.

## 10. Do not equate few commits with high risk

Three hypothetical scenarios:

**Library A** performs a simple data transformation, releases infrequently, has tests, and maintainers still respond to incidents. Replacing it immediately may yield negligible benefit.

**Library B** has many recent commits, yet a critical advisory affecting production remains unaddressed. It may require high priority despite an active community.

**Library C** relies on compiler internals, lacks a version compatible with the target JDK, and causes builds to fail. It is a Java migration blocker even with zero CVEs.

Evaluation should rest on **impact to the application on the target JDK** and ability to respond to new issues, rather than relying on a single metric.

## 11. Checking JDK compatibility independently of maintenance

A well-maintained library may still require a newer Java release than the runtime your application supports.

Determine:

1. The Java baseline published by upstream.
2. The JDK used to build the library.
3. The class-file major version.
4. The set of Java SE APIs required by the library.
5. Dependencies on internal APIs, reflection, and module access.
6. Compatible framework and container versions.
7. Supported native/OS architectures.
8. JDK versions tested in upstream's CI.

Example class-file versions:

| Java | Major version |
|---|---:|
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |

A JAR with class-file major 65 will not run on a Java 17 JVM under normal class-file version rules. Yet major 52 alone does not prove it uses only Java 8 APIs; the compiler may have generated Java 8 bytecode with `-source`/`-target` without constraining the target APIs.

### 11.1. Using javap

~~~bash
javap -verbose -classpath lib/example.jar \
  org.example.Sample
~~~

Look for:

~~~text
major version: 61
~~~

For multi-release JARs, pay attention to the class variants matching the runtime. Do not inspect one class and assume the entire artifact shares the same class-file version.

### 11.2. Using jdeps

~~~bash
jdeps --jdk-internals lib/example.jar
~~~

This tool helps locate certain references to JDK internal APIs; it does not fully detect string-based reflection, native code, or resources/config. Supplementary runtime testing is required.

## 12. Transitive dependencies: a hard-to-see source of risk

Example:

~~~text
orders-service
   |
   +-- protocol-client:3.0
          |
          +-- legacy-codec:1.4
          |
          +-- transport-api:2.1
~~~

If `legacy-codec` is no longer maintained, options include:

- Upgrading `protocol-client` to a version that no longer pulls in the old codec.
- Replacing `protocol-client` altogether with another library.
- If APIs permit, overriding the codec version with a supported compatible version.
- Isolating the feature using the codec and replacing it incrementally.
- Removing the feature if it is no longer used.

**Do not simply exclude `legacy-codec`** if `protocol-client` still calls classes inside it. The build might pass, only for a rare runtime path to hit `NoClassDefFoundError`.

In frameworks with a BOM or compatibility matrix, prefer verified dependency combinations rather than arbitrarily overriding a single transitive version.

## 13. Assessing real-world security vulnerabilities

For each dependency with an advisory:

- Which artifact/version does the advisory apply to?
- Is there a fixed version or vendor backport?
- Which features/configurations are involved in the exploitation conditions?
- Does untrusted input reach that code path?
- Does the application hold sensitive permissions?
- Are there compensating controls or temporary isolation options?
- Is the remaining time available for replacement acceptable?
- If the library is unmaintained, who will fix the next vulnerability?

A scanner matching only coordinates/versions can produce false positives or false negatives. You must inspect the source advisory and reachability in your actual architecture.

Conversely, **having no CVEs does not prove a library has no vulnerabilities**. If it is unmaintained and processes untrusted input, future risk remains worth weighing.

## 14. License, provenance, and supply-chain security

A replacement library must fit beyond just its API.

Check:

- Licenses of both upstream and candidate; notice/attribution/disclosure obligations if applicable.
- Rights to fork, modify, package, and distribute for organizational purposes.
- Official source repository and artifact publisher identity.
- Artifact coordinates, checksums/signatures, and distribution repositories.
- Release policy, security response process, and publish permission controls.
- Risks of dependency confusion, artifact hijacking, and lookalike forks.
- Whether shaded/repackaged components retain license/provenance metadata.

Do not pick a similarly named repository and treat it as the official successor without evidence. Active maintenance does not compensate for an incompatible license or untrustworthy artifact provenance.

## 15. Prioritizing by risk and business impact

A decision-support matrix:

| Evaluation dimension | Low | Medium | High |
|---|---|---|---|
| Security exposure | No untrusted input | Internal data | Public input, secrets, or high privilege |
| JDK compatibility | Passing evidence exists | No reliable tests yet | Fails to compile/run on target JDK |
| Criticality | Auxiliary tooling | Selected workflows | Core paths or multiple services |
| Maintenance status | Has responsible owner | Limited maintenance | EOL/abandoned/no patch path |
| Blast radius | Single module | Several services | Shared across many systems |
| Replaceability | Small API, little data | Requires adapter | Protocol/schema changes/complex |

Teams can classify items as:

- **Blocker:** component prevents the application from running on the target JDK, or required APIs do not exist.
- **High priority:** exposed vulnerability, no patch available, or unrecoverable on incident.
- **Medium priority:** poor maintenance status, yet currently functional with an available replacement option.
- **Monitor:** infrequent changes, yet has an owner, strong test coverage, and currently accepted risk.

Every tier must have rationale, evidence, an owner, and a due date. Never use JAR age as the sole criterion.

## 16. Remediation options

| Option | When appropriate | Cost/risk |
|---|---|---|
| Upgrade version within same project | Upstream offers supported version and fixes | Breaking changes, higher JDK baseline |
| Switch to successor project | Verified successor project exists | API, package, license, behavioral changes |
| Replace with another library | Equivalent functionality; old library has no maintenance path | Contract/data/performance migration |
| Use documented Java SE/JDK API | Standard API now covers the capability | Semantics must be reconciled |
| Remove dependency | Feature is no longer used | Check dead code/transitive references |
| Adapter + gradual replacement | Many call sites requiring phased rollout | Transition overhead |
| Fork or vendor internally | No alternative, internal capacity to maintain exists | Assume security/release obligations |
| Isolate legacy service | Must keep during a transition phase | Security exposure, operations, and latency |
| Accept risk temporarily | Technical constraints cannot be solved immediately | Needs owner, mitigation, deadline |

“Replacing the library” is not always better than “upgrading to an official release”. If a successor provides a clear migration guide and compatibility matrix, it may carry lower risk than an unrelated library that merely shares similar feature names.

## 17. How to evaluate replacement candidates

Two libraries both labeled a “JSON serializer”, “HTTP client”, or “connection pool” are not necessarily compatible.

Comparison checklist should include:

1. Public APIs, method signatures, checked exceptions.
2. Thread safety, ordering, and concurrency semantics.
3. Null handling, defaults, immutable/mutable behavior.
4. Data format, field naming, enums, numeric precision, Unicode.
5. Protocol compatibility, timeouts, retries, redirects.
6. TLS verification and security defaults.
7. Runtime JDK baseline, framework, and OS/platform support.
8. Memory usage, latency, throughput, and resource ownership.
9. Logging, tracing, and metrics.
10. Licensing and artifact provenance.
11. Release cadence, maintainer responsiveness, and security policy.
12. Ease of rollout/rollback.

Evaluate using use cases the application **actually exercises**, not just marketing feature lists or star counts.

### 17.1. Replacing small libraries with Java SE APIs

If an old library only performs Base64 encoding, Java 8+ provides `java.util.Base64`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public final class PayloadEncoding {
    private PayloadEncoding() {
    }

    public static String encode(String raw) {
        return Base64.getEncoder()
                .encodeToString(raw.getBytes(StandardCharsets.UTF_8));
    }

    public static String decode(String encoded) {
        byte[] bytes = Base64.getDecoder().decode(encoded);
        return new String(bytes, StandardCharsets.UTF_8);
    }
}
~~~

However, if the legacy output used MIME line breaks, a URL-safe alphabet, or specific padding, choose the corresponding API and test stored data. “Having a similarly named class” does not mean identical output.

## 18. Adapter pattern for phased dependency replacement

When multiple modules directly call the old library, consider introducing an internal interface reflecting business needs.

~~~java
package com.example.orders.spi;

public interface OrderCodec {
    byte[] encode(OrderPayload value);

    OrderPayload decode(byte[] data);
}
~~~

A legacy adapter might look like:

~~~java
public final class LegacyOrderCodec implements OrderCodec {

    private final LegacySerializer serializer;

    public LegacyOrderCodec(LegacySerializer serializer) {
        this.serializer = serializer;
    }

    @Override
    public byte[] encode(OrderPayload value) {
        return serializer.write(value);
    }

    @Override
    public OrderPayload decode(byte[] data) {
        return serializer.read(data, OrderPayload.class);
    }
}
~~~

`OrderPayload` and `LegacySerializer` are illustrative types assumed to be provided by the application/library. Do not treat this snippet as a standalone runnable example without defining them.

Afterward, you can build `ModernOrderCodec`, compare outputs via golden tests, switch implementations through dependency injection or controlled feature flags, and remove the legacy adapter once no consumers remain.

**An adapter only isolates the API; it does not automatically guarantee semantics.** A new serializer may change field naming, binary format, or default values despite an identical Java interface. Data differences must be tested.

## 19. Replacing dependencies in Gradle

Old declaration example:

~~~groovy
dependencies {
    implementation 'org.example:legacy-http-client:1.0'
}
~~~

After selecting a candidate and updating source code:

~~~groovy
dependencies {
    implementation 'org.example:modern-http-client:2.0'
}
~~~

All coordinates here are **hypothetical examples**, not recommended real packages to install.

### 19.1. Excluding transitive dependencies

~~~groovy
dependencies {
    implementation('org.example:protocol-client:3.0') {
        exclude group: 'org.example', module: 'legacy-codec'
    }
}
~~~

Only exclude once you have verified that `protocol-client` no longer needs `legacy-codec` or has a suitable alternative implementation. If upstream code still calls an excluded class, runtime execution may fail with `ClassNotFoundException`, `NoClassDefFoundError`, or `NoSuchMethodError`.

### 19.2. Using constraints/BOMs when appropriate

Dependency constraints or a platform/BOM can align versions across an ecosystem. However, forcing a newer version does not prove ABI compatibility. Follow the framework's compatibility matrix when available.

### 19.3. Inspecting the graph after changes

~~~bash
./gradlew :orders-service:dependencies \
  --configuration runtimeClasspath

./gradlew :orders-service:dependencyInsight \
  --dependency legacy-codec \
  --configuration runtimeClasspath
~~~

Once the graph looks clean, continue verifying the JAR/fat JAR and runtime image. A shaded component may no longer appear under recognizable coordinates.

## 20. Replacing dependencies in Maven

Old declaration:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>legacy-codec</artifactId>
    <version>1.4.2</version>
</dependency>
~~~

New declaration:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>modern-codec</artifactId>
    <version>2.0.0</version>
</dependency>
~~~

Coordinates are purely illustrative. If the old library is pulled in transitively by another library, an exclusion can be used:

~~~xml
<dependency>
    <groupId>org.example</groupId>
    <artifactId>protocol-client</artifactId>
    <version>3.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>org.example</groupId>
            <artifactId>legacy-codec</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

Verify:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dincludes=org.example:legacy-codec
~~~

Maven `dependencyManagement` can enforce the selected version, but does not fix call sites or guarantee compatibility. Run tests and inspect the runtime graph after making changes.

## 21. Breaking changes when upgrading major versions

Changes that can occur even when a library remains actively maintained:

- Package/class renames.
- Method signature, return type, or exception changes.
- Constructors replaced with builders/factories.
- Different default timeout/retry/redirect policies.
- Different JSON/XML field names or date/time formats.
- Changed immutable/mutable or thread-safety semantics.
- Changed resource closing, connection pooling, and lifecycle behavior.
- Changed default TLS algorithms and hostname verification.
- Changed logging APIs or tracing integrations.
- Changed native library and platform requirements.
- Raised Java baseline.
- Changed transitive dependencies, licenses, or artifact coordinates.

For libraries handling persistent data, a migration guide must cover **data compatibility**, not merely “fixing compiler warnings”.

### 21.1. Binary compatibility

One module may recompile against the new library while another module retains older bytecode calling a method signature that no longer exists. During mixed-version deployment, `NoSuchMethodError`, `NoSuchFieldError`, or `AbstractMethodError` may occur. Inspect consumer modules and the runtime classpath, not just the modified module.

### 21.2. Data compatibility

Data in databases/message queues may have been produced by the old library. When replacing a codec, parser, or cryptography provider, test reading legacy data, writing new data, and rolling back along all compatibility directions required by the system. Never assume the new version reads every historical output.

## 22. When should you fork or vendor a library?

Forking is an acceptable solution in some cases, provided the team becomes a **genuine maintainer**.

Conditions to examine:

- The license permits modification and distribution under your organizational model.
- Source code, a test suite, and CI running on the target JDK exist.
- An owner understands the domain and handles security advisories.
- A release/publish pipeline exists with clear provenance and artifact coordinates.
- Ability to update transitive dependencies.
- Exit criteria for retiring the fork in favor of upstream/a successor.
- Resources to sustain maintenance on subsequent JDK releases.
- Technical risk is lower than architectural changes at that time.

Forking is not just copying a repository and changing a version number. Without an owner, release process, and security response, an internal project can fall back into an unmaintained state.

For libraries handling cryptography, authentication, or complex untrusted parsing, teams lacking domain expertise should think carefully before committing to a long-term self-maintained fork.

## 23. Isolating legacy dependencies as a transitional solution

If a component cannot be replaced immediately while a larger system's JDK migration has a deadline, you can temporarily:

- Place the capability behind an adapter/service boundary.
- Restrict traffic or untrusted input sources.
- Apply appropriate security controls and monitoring.
- Keep the old runtime within a controlled zone, if still supported and approved.
- Use clear error handling and rollback procedures.
- Set a retirement deadline, owner, and completion criteria.

This is not a certification that the system is secure. Keeping an EOL JDK or library can increase risk, especially if security fixes are no longer available. Splitting an old dependency into a separate microservice does not eliminate vulnerabilities in that code either; it only changes the operational boundary.

## 24. Multi-layer testing for replacements

### 24.1. Unit and contract tests

Include:

- Null, empty, and malformed input.
- Unicode, encoding, escaping, large payloads.
- Timezones, locales, large numbers, and rounding.
- Exceptions, timeouts, retries, cancellation.
- Thread safety, ordering, and concurrency.
- Close/cleanup semantics and resource leaks.
- Edge cases that historically caused production bugs.

### 24.2. Golden-file and serialization tests

If the library writes data, store legacy format samples and test reading them with the new version. During multi-version operation phases, also test old clients/servers reading new data when that is an official requirement.

### 24.3. Integration tests

Test integration with databases, HTTP/TLS, messaging, caches, DI/ORM frameworks, application servers, and deployment topology. A library passing unit tests can still be misused by a framework or differ under dependency injection configuration.

### 24.4. API/binary tests

Verify modules and plugins using the library's public API; ensure old-version JARs are not loaded alongside the new version to cause conflicts.

### 24.5. Performance and operations

For libraries on hot paths, measure throughput, p50/p95/p99 latency, CPU, allocation, heap, GC, connection count, startup time, and behavior under high load. Never assume a replacement is automatically faster.

### 24.6. Security tests

Verify TLS verification, deserialization filters, input size limits, sensitive data logging, dependency advisories, and new default configurations. A safer library that is misconfigured can still create vulnerabilities.

## 25. Multi-JDK support matrix

Example of a product committed to supporting Java 17 and Java 21:

| Verification step | Java 17 | Java 21 | Evidence |
|---|---|---|---|
| Build with appropriate compiler/toolchain | PASS/FAIL | PASS/FAIL | Build log |
| Dependency graph | Reviewed | Reviewed | Lockfile/SBOM |
| Class-file/API baseline | Verified | Verified | javap/compile flags |
| Application startup | PASS/FAIL | PASS/FAIL | Startup log |
| Unit tests | PASS/FAIL | PASS/FAIL | Test reports |
| Integration tests | PASS/FAIL | PASS/FAIL | Test artifacts |
| Reflection/bytecode tool compatibility | PASS/FAIL | PASS/FAIL | Runtime logs |
| Serialization/data compatibility | PASS/FAIL | PASS/FAIL | Golden samples |
| Security triage | Reviewed | Reviewed | Advisory/evidence |
| Performance regression | Compared | Compared | Metrics |
| Deployment artifact | Verified | Verified | Checksums/image digests |

The cells are placeholders, not executed results. Mark PASS only with actual evidence. If releasing a Java 17 artifact and running it on Java 21, test that exact artifact on both runtimes when both are within your support scope.

## 26. Step-by-step dependency transition process

### Step 1: Lock down the baseline

Record the commit, JDK, build tool, dependency graph, BOM, lockfile, artifact checksums, runtime image, test results, and metrics.

### Step 2: Build the inventory

Collect direct/transitive/tooling/runtime-injected components. Record owners and consuming systems.

### Step 3: Verify maintenance status

Check official announcements, release notes, support policies, advisories, and JDK compatibility docs. Record the inspection date, sources, and confidence level.

### Step 4: Classify risks

Separate JDK blockers, security exposure, operational risk, and maintenance uncertainty. Assess business criticality and actionability.

### Step 5: Choose an approach

Compare upgrade, successor, replacement, removal, adapter, fork, or temporary isolation. Document trade-offs and the accountable owner.

### Step 6: Prototype on the target JDK

Create a proof of concept with the candidate dependency and run compile/runtime/serialization/security tests. Where possible, avoid upgrading the JDK, framework, and dozens of libraries in one step where root causes cannot be isolated.

### Step 7: Update build and code

Update declarations, imports, adapters, configuration, and transitive exclusions within the intended scope. Inspect the resolved graph.

### Step 8: Verify artifact and behavior

Run unit, integration, contract, and performance tests. Inspect the JAR/fat JAR/container to confirm the old library has genuinely been removed from deployment when removal is the goal.

### Step 9: Roll out safely with rollback readiness

Use an appropriate deployment strategy. Monitor logs, metrics, errors, and data compatibility. If formats/schemas changed, design rollback ahead of time.

### Step 10: Complete the lifecycle

Clean up obsolete workarounds and adapters, and update SBOMs/lockfiles, runbooks, alerts, and ownership. Unresolved risks must have a formal exception with an expiration date.

## 27. Decision scenario example

Suppose a service uses `org.example:legacy-protocol:1.2` (hypothetical name). Inventory findings:

- The dependency runs on the flow receiving partner messages.
- The current version branch has been announced as end-of-support by its maintainers.
- The library uses an old parser that does not support the target JDK.
- A successor library exists, but with a different API and serialization format.
- Some older clients still use the previous protocol version.

Options table:

| Option | Benefit | Risk |
|---|---|---|
| Keep legacy with JVM flags | Minimal code edits | Does not resolve all JDK/security risks |
| Override transitive parser | Easy to prototype | ABI or behavioral mismatch |
| Migrate to successor | Has support path | Needs adapter and data tests |
| Internal fork | Control over fixes | Becomes maintainer |
| Change protocol | Potential architectural improvement | High client migration cost |

One viable path is creating a `ProtocolCodec` interface, retaining golden payloads, implementing a successor adapter, comparing data outputs, running on the target JDK, shifting traffic in phases, and removing the old dependency once no consumers remain.

This is a **hypothetical scenario**, not a conclusion regarding the status of any real artifact.

## 28. Failure symptoms after replacing dependencies

| Symptom | Common cause | Investigation path |
|---|---|---|
| `UnsupportedClassVersionError` | Replacement JAR compiled for a newer JVM | Major version/JDK target |
| `NoSuchMethodError` | ABI conflict or runtime version differs from compile | Dependency graph and packaging |
| `NoClassDefFoundError` | Excluded JAR still called by code | Runtime classpath and stack trace |
| `InaccessibleObjectException` | Legacy library reflects into JDK internals | Library upgrade, JDK module access |
| Test runner discovers no tests | Build/test plugin does not support JDK | Plugin compatibility, test discovery |
| Serialization data mismatch | Defaults or schema changed | Golden datasets and contract tests |
| Performance degradation | New library changed resource/concurrency behavior | Baseline, profiler, metrics |
| Passes locally, fails in production | Different artifact or injected dependency | Container, application server, startup |
| Scanner still detects old library | Transitive/shaded/nested JAR still present | Artifact inspection and SBOM |
| License review failure | Candidate violates policy | Legal/provenance assessment |

Do not use `--add-opens` as the default answer for every error when changing libraries. Package/module access errors, removed APIs, and ABI mismatches are distinct issues.

## 29. Common mistakes

### 29.1. Concluding unmaintained solely from “no commits for a long time”

A small, stable library may need few changes. Evidence from maintainers, support policies, and incident responsiveness is needed.

### 29.2. Inspecting only direct dependencies

Risk can come from transitive libraries, plugins, processors, agents, and injected runtime JARs.

### 29.3. Choosing an alternative solely by star count

Popularity does not guarantee Java compatibility, security practices, data format compatibility, support, licensing, or performance.

### 29.4. Excluding a library and considering it done

If a parent dependency still calls removed classes, errors may surface only on rare runtime paths.

### 29.5. Bulk-overriding transitive versions to latest

BOMs/compatibility matrices exist for a reason. Forcing arbitrary versions can introduce binary conflicts.

### 29.6. Fixing only compile errors

A replacement dependency can compile cleanly yet alter retries, timeouts, serialization, TLS, and semantics.

### 29.7. Unowned forks

A fork lacking CI, security response, and a release plan can itself become unmaintained.

### 29.8. Mistaking “no CVEs found” for “safe”

Vulnerability databases have finite coverage and mapping. Trust boundaries and maintainer responsiveness must be evaluated.

### 29.9. Neglecting data rollback verification

Replacing a serializer/protocol can leave the rollback binary unable to read new data. Compatibility windows and migration plans are required.

### 29.10. Failing to document evidence

A claim that “this dependency is currently maintained” without version, source, and inspection date quickly loses value as the ecosystem evolves.

## 30. Template for a dependency evaluation report

~~~yaml
dependencyReview:
  coordinate: "org.example:legacy-codec:1.4.2"
  scope: "runtime-transitive"
  introducedBy: "org.example:protocol-client:3.0"
  usedBy:
    - "orders-service"
  owner: "integration-team"
  currentJdk: "11"
  targetJdk: "17"
  maintenance:
    status: "under-review"
    evidence: "official support policy or maintainer announcement"
    checkedAt: "YYYY-MM-DD"
    confidence: "unknown"
  security:
    advisoriesReviewed: false
    runtimeExposure: "unknown"
  compatibility:
    source: "unknown"
    binary: "unknown"
    behavior: "not-tested"
  recommendation:
    action: "evaluate-replacement"
    candidate: "to-be-selected"
    deadline: "to-be-agreed"
  validation:
    graphReviewed: false
    buildPassed: false
    integrationPassed: false
    performanceCompared: false
  residualRisk:
    accepted: false
    mitigation: "pending"
~~~

The template above contains hypothetical coordinates and statuses. Never fill in `PASSED` or `maintained` merely to complete the form. Every decision needs an owner, source, timestamp, version scope, and test evidence.

## 31. Pre-closure checklist for dependency migration

- [ ] Identified the component in resolved direct/transitive graphs.
- [ ] Checked build plugins, annotation processors, agents, and runtime-injected JARs.
- [ ] Recorded exact artifact, version, source repository, and owner.
- [ ] Verified maintenance/EOL/deprecation status from sufficiently reliable sources.
- [ ] Reviewed advisories, license, provenance, and exposure level.
- [ ] Checked Java baseline, class-file target, and internal API usage.
- [ ] Documented APIs, data formats, and business logic actually used.
- [ ] Selected upgrade/replacement/removal/fork/isolation with documented rationale.
- [ ] Controlled the graph via pinning/locking/version policy where appropriate.
- [ ] Updated code, build, and configuration within the intended scope.
- [ ] Proven the old library is absent from runtime if removal was the goal.
- [ ] Executed required unit, contract, integration, and security tests.
- [ ] Verified serialization/protocol compatibility and performance where relevant.
- [ ] Tested deployment/rollback in an appropriate environment.
- [ ] Updated SBOMs, lockfiles, runbooks, and ownership.
- [ ] Remaining exceptions have deadlines, mitigations, and retirement plans.

A checklist is an implementation guidance tool, **not evidence that QA has been completed** for a specific application.

## 32. Closing principles

- **Unmaintained, deprecated, EOL, and vulnerable are not synonymous.** Assess the exact status and version with concrete evidence.
- **Inventory must span direct, transitive, build, test, and runtime dependencies.** Missing an old agent or processor can cause migration failure.
- **The resolved dependency graph matters more than isolated declarations.** Retain BOMs, lockfiles, and actual packaged artifacts.
- **A maintained library does not necessarily support the Java release your application needs.** Inspect JDK baseline, class-file version, APIs, reflection, and native dependencies.
- **Do not select a new library based solely on version or popularity.** Compare data contracts, APIs, security, and behavior.
- **Do not exclude/override transitive dependencies mechanically.** Frameworks may still invoke them.
- **Prefer official upgrades or successors when appropriate**, while still testing breaking changes.
- **Replacing small libraries with Java SE APIs reduces dependencies**, provided semantics match.
- **Forking is a long-term maintenance responsibility**, not a zero-cost workaround.
- **Adapters, contract tests, and phased rollouts** enable controlled library replacement.
- **SBOMs, provenance, and security scans are supporting evidence**, not substitutes for engineering evaluation and runtime tests.
- **Exceptions must have owners, expiration dates, and cleanup plans** so temporary risks do not harden into permanent technical debt.

In Java Advance Compatibility Migration, the goal of dependency management is not “upgrading every JAR to the latest version”, but ensuring **every component still in use has a support path, a suitable technical contract, and controlled risk on the target JDK**. By building accurate inventories, verifying maintenance status, selecting alternatives grounded in actual needs, inspecting artifacts/runtime behavior, and designing for rollback, teams can upgrade Java without continuing to rely on links nobody can repair when incidents occur.
