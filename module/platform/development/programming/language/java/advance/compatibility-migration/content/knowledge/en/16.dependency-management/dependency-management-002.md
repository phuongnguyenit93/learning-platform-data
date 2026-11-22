# Identifying Dependencies to Upgrade Before Changing the JDK

## 1. Why Inventory Dependencies Before Upgrading the JDK?

Upgrading the JDK is not merely changing `JAVA_HOME`, switching the Docker base image, or editing `sourceCompatibility`. A Java application usually depends on multiple layers of components: build tools, plugins, compilers, annotation processors, frameworks, runtime libraries, drivers, agents, native code, and *transitive dependencies*. Even a single link that does not support the target JDK can make the entire migration fail.

For example, when moving from JDK 17 to JDK 21:

- Gradle/Maven or build plugins may not yet run on the new build JVM.
- Annotation processors or compiler extensions may use internal `javac` APIs and fail during compilation.
- A framework may pull in a bytecode library that cannot read the new class-file format.
- A library using deep reflection into JDK packages that are now more strongly encapsulated may throw `InaccessibleObjectException`.
- Drivers, TLS providers, native libraries, or APM agents may require different versions to run on the new runtime.
- A dependency may still rely on a module that used to ship with the old JDK but was removed in the target JDK.
- The actual version of a transitive dependency may differ from what was expected due to a BOM, constraints, or conflict resolution.

If you switch the JDK first and handle each stack trace one by one, the team ends up fixing failures reactively: upgrading the build plugin, then discovering an annotation processor, followed by the framework, drivers, and agents. A more controlled approach is to **map all dependencies and identify components that must be upgraded before switching environments**.

In this lesson, the term *dependency* does not refer only to JARs declared in `implementation` or `<dependencies>`. It includes any component the application needs in order to **compile, test, package, start up, and run stably on the target JDK**.

## 2. Expected Outputs of an Inventory Pass

After the survey, the team should be able to answer:

1. **Which components and versions does the application use?** Including direct, transitive, build plugins, test dependencies, agents, native components, and libraries bundled inside the packaged artifact.
2. **Which components are genuinely incompatible with the target JDK?** Based on vendor support matrices, release notes, and test-run evidence, not mere guesswork.
3. **Which components must be upgraded first?** For example, a build tool that fails to start, a processor that cannot compile, or a framework that cannot start.
4. **Which components can remain unchanged?** Libraries that are still supported, compatible with the target JDK, and do not cause blockers may not need upgrading yet.
5. **In what order should they be upgraded?** Accounting for constraints across frameworks/BOMs, plugins, compilers, runtime, and native components.
6. **How is completion proven?** Resolution results, compatibility tests, integration tests, actual artifacts/runtimes, and a rollout plan.

The most important output is a **dependency decision table**: current state, target version, reason for change, blocker status, owner, evidence, and execution order. A list of "latest" versions does not satisfy this goal.

## 3. Categorizing Dependencies by Role

| Group | Example | Primary Impact |
| --- | --- | --- |
| Build tool | Gradle Wrapper, Maven Wrapper | Starting and orchestrating builds |
| Build plugin | Spring Boot plugin, shading, code quality, container plugin | Configuration and build tasks |
| Compiler/toolchain | `javac`, Kotlin/Scala compiler, toolchain | Parsing and bytecode generation |
| Annotation processor | Lombok, MapStruct processor, custom APT | Code generation and annotation processing |
| Compile dependency | APIs on compile classpath | Signature checks, generics, source compatibility |
| Runtime library | ORM, JSON, logging, HTTP, messaging | Class loading and runtime functionality |
| Test dependency | JUnit, Mockito, coverage, test runner | Test discovery and execution |
| Bytecode/instrumentation | ASM, Byte Buddy, Javassist, Java agents | Reading, generating, or transforming bytecode |
| Native component | JNI/JNA, native drivers, platform libraries | ABI, CPU, OS, and native linking |
| Platform/BOM | Framework BOM, Maven dependencyManagement, Gradle platform | Selecting compatible version combinations |
| Internal library | Company SDK, shared starter, DTO | API/ABI/behavior across modules |
| Deployment runtime | JRE/container image, `jlink`, infrastructure-provided agents | Ability to run in production |

Categories can overlap. For instance, a starter may be a direct dependency on `runtimeClasspath` while pulling in many transitive libraries and being managed by a BOM. An APM agent might not appear in build files at all because infrastructure attaches it through startup flags.

Therefore, do not take a single `runtimeClasspath` report and conclude that you have inventoried all migration-relevant dependencies.

## 4. Distinguishing Build JDK, Compiler JDK, and Runtime JDK

Saying "the project uses Java 21" does not specify:

- **Build JVM:** the JVM running Gradle or Maven along with their plugins.
- **Compiler JDK:** the JDK providing `javac` or the selected compiler toolchain.
- **Target release:** the Java API level and bytecode target of the artifact, for example `--release 17`.
- **Test JVM:** the JVM running tests, which may be configured separately.
- **Application runtime:** the actual JVM in the container, VM, or production runtime image.

For example, CI might run Gradle on JDK 21, use a JDK 21 compiler toolchain with `--release 17` to publish a library that still supports Java 17. A build plugin must support **Gradle's JVM**, whereas a runtime library must fit the **lowest JVM the artifact promises to support**. An annotation processor, in turn, must be compatible with the **chosen compiler**.

Reference inspection commands:

~~~bash
java -version
javac -version
./gradlew --version
mvn -version
~~~

Running `java -version` in a terminal does not prove the IDE, Gradle daemon, Maven compiler plugin, or production container uses the same JDK. Record each role in separate fields:

~~~text
Build JVM:         JDK ...
Build tool:        Gradle/Maven ...
Compiler toolchain: JDK ...
Release target:    Java ...
Unit/IT JVM:       JDK ...
Production runtime: JDK/JRE ...
~~~

## 5. Locking Down the Target JDK and Support Policy Before Choosing Versions

Before evaluating a dependency, determine:

- Source and target JDKs, for example 17 → 21.
- JDK vendor/distribution if there are constraints.
- Minimum Java level the product must still support.
- Whether running across multiple JDKs is required during transition.
- Whether the production runtime is a full JDK, JRE image, or `jlink` image.
- Whether changing the current framework major version is permitted.
- Whether there are rolling deployments, rollbacks, and consumers sharing libraries.
- Which business flows must operate prior to cutover.

The newest version of a library may require a higher minimum Java version than the product supports, or pull in a framework major version with API/namespace changes outside the migration scope. Thus, a **target version is a version that is supported and fits the whole system**, not by default the highest version number.

### 5.1. Support Evidence to Look For

For critical components, check:

1. The vendor's compatibility matrix against the target JDK and framework.
2. Release notes, upgrade guides, and breaking changes.
3. Maintenance/EOL policy for the version branch.
4. Issue trackers regarding the target JDK, bytecode, reflection, JNI, or memory model.
5. BOM/platform and the set of versions tested by the vendor.
6. Actual application tests.

Do not infer "Java 21 supported" merely because a JAR contains class-file version 52 (Java 8). A newer JVM can load old bytecode, yet the library may still use internal APIs that changed or rely on behaviors no longer guaranteed.

## 6. Step 1: Inventory Direct and Transitive Dependencies

### 6.1. With Gradle

Configurations that usually need inspection include `compileClasspath`, `runtimeClasspath`, `testCompileClasspath`, `testRuntimeClasspath`, `annotationProcessor`, and configurations created by plugins.

Reference commands:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew :service-a:dependencies --configuration runtimeClasspath
~~~

In a multi-module project, inspect the graph of every important module, because module A's dependencies are not necessarily the same as module B's.

To find why a particular version was selected:

~~~bash
./gradlew dependencyInsight \
    --dependency byte-buddy \
    --configuration testRuntimeClasspath
~~~

`dependencyInsight` shows the dependency path, resolution process, version conflicts, and constraints. This report matters because the version actually resolved by Gradle may differ from the version number written directly in the build file.

Do not forget the **plugin/buildscript classpath**. A failing dependency inside the Gradle daemon might not appear on the application's `runtimeClasspath`.

### 6.2. With Maven

Maven dependencies can come from direct POMs, parent POMs, `dependencyManagement`, BOM imports, and profiles. Scopes such as `compile`, `runtime`, `provided`, and `test` affect how a dependency participates at each stage.

Reference commands:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
~~~

`dependency:tree` displays the dependency tree resolved by Maven for that configuration. `effective-pom` shows the configuration after applying parent POMs, profiles, and management rules.

Maven plugins have their own dependencies and versions. Upgrading a library in `<dependencies>` does not automatically upgrade `maven-compiler-plugin`, `maven-surefire-plugin`, `maven-failsafe-plugin`, `maven-shade-plugin`, or code generation plugins.

### 6.3. Transitive Dependencies Are Frequent Blockers

Example:

~~~text
orders-service
 └── framework-starter
      ├── framework-core
      ├── json-runtime
      └── bytecode-engine:old
~~~

The application does not declare `bytecode-engine` directly, yet the framework uses it. If the old version does not understand new class files, errors may occur when the framework generates proxies, scans annotations, or runs tests.

Do not immediately force `bytecode-engine` to a new major version when the parent framework does not yet support that combination. Check first whether the framework/BOM has a release line declared compatible with the target JDK.

## 7. Step 2: Identify Build Tools and Plugins That Must Be Upgraded First

The build tool is the gateway to the pipeline. If Gradle/Maven cannot run on the new JVM, the team cannot yet verify the remaining changes.

### 7.1. Gradle Wrapper

The project version is managed via the Gradle Wrapper, typically in `gradle/wrapper/gradle-wrapper.properties`. Consult Gradle's **Java compatibility matrix** to distinguish:

- Whether Gradle can **run on** the target JDK yet.
- Whether Gradle can use the target JDK as a **compilation/test toolchain** yet.

These two capabilities may appear in different Gradle versions. Therefore, do not use "toolchains support Java 21" to claim that the Gradle daemon of that version can run on Java 21.

Plugins to survey:

- Framework plugins and dependency-management plugins.
- Kotlin/Groovy/Scala build integration.
- Checkstyle/PMD/SpotBugs/Error Prone.
- JaCoCo and coverage tools.
- Packaging, shading, native image, and Docker/container builds.
- OpenAPI/protobuf/gRPC generators.
- Convention plugins, `buildSrc`, and internal plugins.

Upgrading the Gradle Wrapper may also change DSL behavior or require different plugin APIs. Pick a supported **JDK ↔ Gradle ↔ plugin** combination rather than bumping the wrapper and fixing plugins ad hoc.

### 7.2. Maven Wrapper and Plugins

With Maven, check Maven Core, Maven Wrapper, Compiler Plugin, Surefire/Failsafe, Shade/JAR, Resources, and code generation plugins. Pin plugin versions via `pluginManagement` or an equivalent mechanism so CI and developers do not resolve to different defaults.

A plugin might run on the current Maven version yet be incompatible with the new JDK. Another plugin might support the new JDK yet require a newer Maven Core. Verify both conditions.

### 7.3. Compiler Toolchain Does Not Automatically Fix the Build JVM

Gradle Groovy DSL example:

~~~groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

This configuration illustrates a JDK 21 compiler producing Java 17 artifacts; it **does not determine the JVM launching Gradle**. If Gradle/plugins do not support the JVM running the build, the compile task might not even execute.

## 8. Step 3: Check Annotation Processors and Compiler Extensions

This category frequently breaks when upgrading the compiler JDK because some processors or plugins use internal compiler APIs:

- Lombok.
- MapStruct annotation processor.
- Dagger, AutoValue, custom APTs.
- Error Prone or compiler plugins.
- Kotlin kapt/KSP in Java/Kotlin projects.
- Internal code generation tools accessing `com.sun.tools.javac.*`.

Example symptom:

~~~text
java.lang.IllegalAccessError:
module jdk.compiler does not export com.sun.tools.javac.*
~~~

Or:

~~~text
java.lang.NoSuchFieldError: ... javac tree ...
~~~

This can be a processor incompatibility rather than an error in application source code.

### 8.1. How to Document Processors

| Processor/plugin | Module | Target Compiler JDK | Required Evidence |
| --- | --- | --- | --- |
| Lombok | Entity/DTO | Target JDK | Vendor support and compile tests |
| MapStruct processor | Mapper | Target JDK | Generated code and mapper tests |
| Custom APT | Shared modules | Target JDK | No reliance on compiler internals |
| Error Prone | CI build | Corresponding JDK/compiler | Plugin/compiler integration |

With Gradle, check `annotationProcessor` and `testAnnotationProcessor`. With Maven, check annotation processor paths in Maven Compiler Plugin and related plugin configurations.

Do not settle for compilation passing alone. If a processor generates a different API than before, consumers may experience source, binary, or behavioral impacts.

## 9. Step 4: Identify the Framework/BOM as the Anchor

The foundational framework typically governs a cohesive set of interconnected dependencies:

~~~text
Framework/BOM
 ├─ Framework core
 ├─ JSON & validation
 ├─ ORM & JDBC integration
 ├─ Embedded web server
 ├─ Logging & tracing
 └─ Test libraries
~~~

Examples of ecosystems to verify include Spring Boot/Spring Framework, Jakarta EE, Hibernate, Netty, Jackson, and reactive or messaging stacks.

Upgrading the platform/BOM to a branch confirmed by the vendor to support the target JDK is usually more reliable than manually overriding multiple transitive dependencies.

However, a BOM does not guarantee everything:

- Some dependencies sit outside the BOM.
- Build plugins have separate version management.
- Explicit constraints/forced versions can override it.
- Multi-module projects may apply different platforms.
- Shaded/native components may be hidden in the dependency tree.

After changing a BOM, you must **re-inspect the resolved dependency graph** to confirm the actual combination.

### 9.1. Separating Framework Major Migration from JDK Migration

A framework major upgrade may entail:

- Namespace changes in APIs moving from Java EE to Jakarta EE (for example, `javax.persistence` to `jakarta.persistence` when adopting the corresponding Jakarta generation).
- Changes to configuration keys, validation, and security defaults.
- Removed methods/classes.
- Changes in serializers, transactions, and exception mapping.
- An increased minimum Java level.

These are not issues caused solely by upgrading the JDK. When planning, explicitly mark which items are **JDK compatibility blockers** and which are **framework breaking changes** so appropriate tests, owners, and rollbacks exist.

### 9.2. Do Not Turn Every `javax.*` Into `jakarta.*`

Not every package starting with `javax` belongs to the same ecosystem. Some `javax.*` APIs are Java SE APIs; Java EE/Jakarta EE APIs have their own history and modules. For instance, JAXB used to be included in some older JDK releases but is no longer bundled in JDK 11+, so an application may need a separate dependency. Switching persistence/servlet namespaces belongs to the corresponding API/framework generation, not a blanket search-and-replace triggered because the JDK version increased.

## 10. Step 5: Detect Usage of JDK Internals and Reflection

Older libraries may use `sun.misc.Unsafe`, `jdk.internal.*`, deep reflection, or unsupported APIs. When the JDK tightens module encapsulation or removes APIs, failures can occur at runtime.

### 10.1. Static Analysis with `jdeps`

Reference commands:

~~~bash
jdeps --jdk-internals library.jar
jdeps --jdk-internals --recursive application.jar
jdeps --multi-release 21 --jdk-internals dependency.jar
~~~

For multi-release JARs, specify the release being surveyed. `jdeps` analyzes bytecode linkage/class files but is not guaranteed to detect all dynamic reflection, JNI, runtime-generated bytecode, or externally loaded agents.

### 10.2. Reading Symptoms at the Right Layer

| Symptom | Likely Cause | How to Investigate |
| --- | --- | --- |
| `InaccessibleObjectException` | Deep reflection into a non-open package | Class/module and dependency in the stack trace |
| `IllegalAccessError` | Access control or module access error during linkage | Caller, target, and module permissions |
| `NoClassDefFoundError` | Class missing on runtime path, or initializer failed | Artifact/class loader/module dependencies |
| `NoSuchMethodError` | API/ABI mismatch due to version conflict | Method descriptor and resolved graph |
| `UnsupportedClassVersionError` | Bytecode newer than JVM runtime | Class-file major version |
| Class file/ASM parser error | Library does not recognize new class-file format | Bytecode library pulled in by framework/plugin |

Do not assume every failure in the table is caused by the new JDK; a skewed classpath or dependency graph can produce the exact same symptoms.

### 10.3. `--add-opens` Is Not an Upgrade

JVM flags such as `--add-opens` or `--add-exports` can serve as scoped workarounds, but they do not guarantee that internal APIs remain stable or present. If used, document the reason, owner, scope limitation, and removal milestone. Do not replace `sun.misc.Unsafe` with `jdk.internal.misc.Unsafe` and treat it as a long-term solution.

## 11. Step 6: Inspect Bytecode and Instrumentation Libraries

Notable groups:

- ASM, Byte Buddy, Javassist.
- Runtime proxies, AOP, ORM bytecode enhancement.
- Mockito, test mocking/agents.
- JaCoCo or coverage agents.
- Classpath scanners and DI frameworks.
- Compiler/codegen pipelines.

A library may run normally with older class-file versions yet fail to parse class files produced by a newer compiler.

| Java release | Class-file major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

You can inspect an artifact:

~~~bash
javap -classpath application.jar -verbose com.example.Main
~~~

Look for `major version`. However, a compatible class-file target **does not by itself prove** the application uses Java SE APIs properly or is free from runtime reflection/native errors.

If Mockito or a coverage agent fails in unit tests, that does not automatically mean production runtime libraries are broken. Distinguish **test-time blockers** from **runtime blockers**.

## 12. Step 7: JDBC, Native Libraries, and JVM Agents

### 12.1. JDBC and Databases

Verify driver versions against vendor support, database server versions, authentication, TLS/certificates, timezones, encodings, connection pools, and ORM integration. Compiling successfully does not prove connection/transaction paths work on the new JDK.

### 12.2. JNI/JNA and Native Binaries

Native components are constrained by CPU architecture, OS, JDK/JNI, shared library ABI, and base image. A JAR may bundle binaries for multiple platforms or require OS-level libraries installed externally.

Do not look only at the JAR version number; test on the actual **container/host runtime**.

### 12.3. APM, Profiler, Security, and Coverage Agents

Agents may be attached at JVM startup outside `pom.xml`/`build.gradle`:

~~~text
JAVA_TOOL_OPTIONS
JDK_JAVA_OPTIONS
-javaagent:/opt/agents/agent.jar
container entrypoint / platform injection
~~~

They can instrument class files, use internal APIs, or change startup/performance characteristics. When upgrading the JDK, confirm vendor support for the agent and test startup, tracing/metrics, and operational overhead.

Disabling an agent to isolate a bug is not evidence that the production configuration is ready.

## 13. Step 8: JDK Modules and Removed APIs

When upgrading from older JDKs, applications may encounter APIs no longer bundled by the JDK, such as Java EE/CORBA modules removed in Java 11. Applications using JAXB/JAX-WS or legacy technologies must identify appropriate standalone dependencies.

Check:

- Packages/modules previously provided by the older JDK.
- JavaFX if previously relying on a bundled distribution.
- The application's module graph.
- Whether a `jlink` runtime image includes all required modules/providers.
- APIs deprecated for removal or already removed in the target JDK.

Reference commands:

~~~bash
jdeps --print-module-deps application.jar
jdeps --missing-deps application.jar
~~~

`jdeps` cannot automatically infer all service loading, reflection, or dynamic native dependencies. For `jlink` images, run integration tests on the final image rather than only using a full JDK in CI.

## 14. Version Conflict Risks and Resolution Rules

Example:

~~~text
orders-service
 ├── library-a
 │    └── common-core:2.x
 └── library-b
      └── common-core:1.x
~~~

The build tool picks one version of `common-core` via its resolution/management rules. If a consumer requires an API missing from the chosen version, `NoSuchMethodError` or behavioral changes can occur.

Pay special attention to:

- Logging facades/bindings.
- JSON modules (core, databind, annotations).
- Bytecode libraries.
- HTTP/Netty stacks.
- Guava/utility libraries.
- Jakarta APIs and ORM integration.
- Telemetry/tracing modules.

For dependency constraints, `force`, `strictly`, Gradle locking, Maven `dependencyManagement`, or BOM overrides, record:

1. Who requests which version.
2. Which version actually resolves.
3. Which rule selects or forces the version.
4. Who depends on a specific version's API.
5. Whether it aligns with the target framework/BOM.

An override added in the past to mitigate a CVE may no longer be needed after upgrading the framework. Audit exceptions instead of carrying them forward mechanically.

## 15. Security, Support Lifecycles, and SBOM

JDK compatibility is only one dimension of the decision. Also check:

- Whether the version branch is actively maintained and receiving patches.
- Whether there are relevant CVEs or advisories.
- Licenses and organizational policies.
- Artifact provenance and trusted repositories.
- Bundled transitive dependencies.
- Inventory traceability via SBOM (Software Bill of Materials).

Having an unpatched CVE **does not mean** a dependency is a JDK compatibility blocker; conversely, a dependency with no known CVE may still fail to run on the target JDK.

Record separately:

~~~text
Reason for upgrade:
  JDK compatibility / security advisory /
  vendor support lifecycle / framework alignment
~~~

If an urgent security patch is needed, it may have to be prioritized immediately before the JDK migration. Where possible, separate security patches from framework major upgrades to isolate regressions easily.

SBOMs are helpful when accurately reporting packaged artifacts; for shaded JARs and native components, supplementary inventory beyond the resolved dependency tree may be required.

## 16. Classifying Blocker Severity

| Level | Meaning | Example | Action |
| --- | --- | --- | --- |
| P0 — Blocking | Cannot build/start or critical functionality fails on target JDK | Build plugin fails to start, processor errors | Replace/upgrade before cutover |
| P1 — High risk | Insufficient support/evidence for critical production flows | Unconfirmed JDBC/agent | Remediate or verify before deployment |
| P2 — Planned | Not an immediate blocker, but poses support or operational risk | Version branch nearing EOL | Schedule controlled upgrade |
| P3 — Defer | Already compatible, supported by adequate evidence, no upgrade needed yet | Stable utility library | Keep version, document reason |

This classification is illustrative, not a mandatory standard. What matters is avoiding the "upgrade everything just because a newer version exists" trap.

### 16.1. Evidence Levels

- **Vendor-supported:** vendor announces support for the target JDK.
- **Observed working:** application passed a specific test suite.
- **Untested:** insufficient data.
- **Known incompatible:** documented support limits or reproducible failure.

"Currently runs" is not synonymous with "vendor-supported". If accepting a dependency without official support, record the owner, test scope, risk, and remediation plan.

## 17. Determining Upgrade Order by Dependency Constraints

A typical decision flow:

~~~mermaid
flowchart TD
    A[Lock target JDK and minimum Java version] --> B[Inventory resolved dependencies]
    B --> C[Can build tool and plugins run?]
    C --> D[Are compiler/annotation processors compatible?]
    D --> E[Select framework and BOM]
    E --> F[Resolve transitive conflicts]
    F --> G[Runtime drivers, bytecode, native, agents]
    G --> H[Build and test on target JDK]
    H --> I[Canary and rollout]
~~~

Steps may require iteration; for instance, a new framework/BOM may require newer plugins, while processors must be upgraded before builds run. View the order above as a **dependency chain**, rather than a strict single-pass checklist.

Practical strategy:

1. **Survey everything** and lock down constraints before changing versions.
2. **Stabilize the build system** so a verification pipeline exists on the target JDK.
3. **Select the target framework/BOM** per vendor support.
4. **Resolve transitive runtime blockers** using the resolved graph.
5. **Test across layers** before changing the production runtime.
6. **Split commits/PRs by clear scope** so each change can be bisected and rolled back independently.

## 18. Example Pre-Upgrade Decision Matrix for Java 17 → 21

| Component | JDK 21 Relationship to Verify | Planned Action | Evidence |
| --- | --- | --- | --- |
| Gradle Wrapper | Can it run on build JVM 21? | Upgrade if required by matrix | Wrapper version, clean build |
| Build plugins | Do they support the new Gradle/JDK? | Upgrade specific plugins | Plugin releases, build tasks |
| Lombok | Is it compatible with JDK 21 compiler? | Upgrade to confirmed version | Compiling generated models |
| ASM/Byte Buddy | Can it read/generate class-file 65? | Upgrade via appropriate platform/plugin | Instrumentation/proxy tests |
| Framework/BOM | Is there a JDK 21-supported branch? | Choose appropriate platform | Vendor docs, integration |
| JDBC driver | TLS/auth/transactions on JDK 21? | Choose supported driver | Real DB integration tests |
| APM agent | Agent instrumentation on JVM 21? | Upgrade agent if needed | Startup, traces, and metrics |
| Internal SDK | Any JDK internals or legacy ABI? | Inventory and test consumers | `jdeps`, compatibility tests |
| Utility library | Supported, tests pass, no conflicts? | Can keep as-is | Resolved graph and tests |

No fixed target version numbers appear in the table because the appropriate versions depend on the project, framework, minimum Java level, and support information available at migration time.

### 18.1. Case Requiring No Upgrade

A pure-Java utility library using stable public APIs that remains maintained and passes tests on the target JDK. Without blockers, security requirements, or conflicts, **keeping the existing version** can carry lower risk than an untargeted upgrade.

### 18.2. Case Requiring Immediate Upgrade

An old processor throws `IllegalAccessError` under the JDK 21 compiler and every module depends on generated code. This is a compile-stage blocker, so a compatible processor version must be selected or internal API reliance removed before switching compilers.

### 18.3. Case Favoring Platform Upgrade

An old framework pulls in a web server, JSON stack, and bytecode engine that are unsupported on the target JDK. If a compatible framework/BOM is provided by the vendor, upgrading along that bundle is usually sounder than forcing individual transitive versions. Framework breaking changes must be documented separately.

## 19. Do Not Use "Latest" as a Selection Criterion

Update-finder tools may suggest:

~~~text
library-a: 2.8 -> 3.0
library-b: 4.1 -> 4.9
framework: 5.x -> 6.x
~~~

This list **does not prove** that the new releases run on the target JDK, match the BOM, preserve APIs, satisfy the minimum Java level, or avoid other breaking changes.

Before selecting a version, ask:

~~~text
Is this version supported on target JDK?
Is it supported with the selected framework/BOM?
Does it preserve minimum Java runtime?
What are the documented breaking changes?
Which tests prove critical behavior?
~~~

Not every Java library adheres strictly to Semantic Versioning. Even a patch release should be tested against behaviors the product relies upon.

## 20. Making the Dependency Graph Reproducible

An inventory becomes stale quickly if CI and developers resolve different dependency graphs.

With Gradle, consider:

- Version catalogs for centralized declarations.
- Platforms/BOMs and dependency constraints.
- Dependency locking.
- Dependency verification.
- Fixed Wrapper version.

With Maven:

- Parent POM and `dependencyManagement`.
- BOM imports.
- `pluginManagement`.
- Maven Wrapper.
- Enforcer rules and appropriate repository policies.

These mechanisms serve different purposes: a version catalog does not force every transitive dependency; locking fixes the resolved graph but does not verify compatibility. For verifiable migrations, also record JDK/toolchain, plugin, native library, and container image versions.

Restrict dynamic versions and overly broad version ranges during validation, because if builds of the same commit produce shifting graphs, isolating bugs becomes very difficult.

## 21. Isolating JDK Impact from Dependency Upgrade Impact

A matrix can help pinpoint failure sources:

| Case | JDK | Dependency graph | Purpose |
| --- | --- | --- | --- |
| A | Old JDK | Old graph | Baseline |
| B | New JDK | Old graph | Detect incompatibilities of old graph with new JDK |
| C | Old JDK | New graph | Measure impact of dependency upgrade if supported |
| D | New JDK | New graph | Target state |

Not every cell is valid. If the new graph already requires the new JDK, cell C is an **unsupported combination** and should be explicitly noted rather than forced to run.

For example, if B fails and D passes: there is evidence that the dependency upgrade resolved a blocker on the new JDK. If B passes while D shows a behavioral regression, investigate the new dependency graph changes before blaming the JDK.

The matrix does not replace stack traces or compatibility tests, but helps keep each experiment varying only one group of factors where feasible.

## 22. Layered Testing Before Cutover

### 22.1. Build and Compile

- Build tool starts using the intended build JVM.
- Compiler toolchain/release are configured properly.
- Annotation processors and generated sources work.
- Code quality and packaging plugins are not skipped due to configuration errors.

### 22.2. Unit and Test Tooling

- Test engine discovers and runs all tests.
- Mocking, coverage, and instrumentation are compatible.
- Test JVM matches the intended version.
- Tests are not accidentally disabled just to get a green build.

### 22.3. Runtime Smoke

- Application starts with the packaged dependency graph.
- DI, configuration, logging, and service loaders work.
- Agents and native libraries load successfully.
- Core request/event paths function.

### 22.4. Integration

- Database, JDBC transactions, and connection pools.
- HTTP/TLS, messaging, caching, and external services.
- Serialization/deserialization and historical data.
- Reflection, module access, and runtime proxies.
- Real production runtime image/container.

### 22.5. Non-Functional

- Startup time, memory/GC, throughput, and p95/p99 latency.
- Connection/thread pools and native memory.
- Logs, metrics, and traces.
- Security defaults, certificates, and audit.

Not every utility library upgrade warrants dedicated microbenchmarks. However, for frameworks, drivers, JNI, Netty, agents, or low-level concurrency libraries, non-functional measurements can decide production readiness.

## 23. Common Mistakes When Choosing Upgrade Order

**Looking only at direct dependencies.** Blockers may hide deep in the transitive graph. Use dependency tree/insight to trace pull-in paths.

**Changing the JDK before checking Gradle/Maven.** If the build tool fails to run, the entire pipeline stalls; check the compatibility matrix first.

**Ignoring annotation processors.** A processor using `javac` internals can fail even when all runtime libraries are compatible.

**Upgrading every library to latest.** Increases the number of changing variables, can violate BOM constraints, and introduces extra breaking changes.

**Forcing newer ASM/Netty/JSON versions inside an older framework.** Not every combination is tested by the vendor.

**Equating test dependencies with production dependencies.** Mockito or coverage agent failures point to a specific category of issue that should be classified before fixing.

**Checking only `java -version`.** Build JVM, compiler JDK, test JVM, and container runtime may differ.

**Assuming an old class-file target guarantees execution on all newer JDKs.** Reflection, internal APIs, and native integrations can still fail.

**Forgetting agents and native libraries.** They are often injected outside source dependency declarations.

**Changing every `javax.*` to `jakarta.*`.** Identify the relevant APIs and framework generation first.

**Running only unit tests.** Drivers, TLS, containers, agents, and data usually require integration tests.

**Failing to record the resolved graph.** Rebuilds choosing different versions undermine JDK comparison accuracy.

**Using `--add-opens` as a permanent solution.** Flags can grant temporary access, but do not substitute for upgrading to a supported library release.

## 24. Checklist Before Approving a JDK Change

- [ ] Locked source/target JDK, minimum runtime, and target environment.
- [ ] Clearly distinguished build JVM, compiler/toolchain, Java release target, test JVM, and runtime.
- [ ] Captured resolved dependency graphs for compile, runtime, and test scopes of key modules.
- [ ] Inventoried build plugins, processors, and compiler extensions separately.
- [ ] Checked Gradle/Maven wrappers and plugins against the Java compatibility matrix.
- [ ] Confirmed target framework/BOM and version overrides.
- [ ] Fully traced risky or conflicting transitive dependencies.
- [ ] Reviewed bytecode instrumentation, mocking, and coverage agents.
- [ ] Checked JDK internals, reflection, and module changes.
- [ ] Reviewed JDBC, JNI/native dependencies, APM/agents, and container images.
- [ ] Assigned priority, owner, and clear upgrade/keep rationale for each dependency.
- [ ] Documented specific vendor support evidence or test results.
- [ ] Separated security patches from JDK blockers where feasible.
- [ ] Baseline graph and toolchain versions are reproducible.
- [ ] Tests ran under the intended JDK without being skipped.
- [ ] Integration tests covered database, network, serialization, and agents.
- [ ] Production runtime image actually loads the right artifacts.
- [ ] Prepared rollback/roll-forward plans suitable for the framework and data.
- [ ] Release notes document breaking changes affecting consumers.

A checklist verifies readiness status; it does not turn a single passing test run into an absolute guarantee that every dependency is compatible across all workloads.

## 25. Dependency Decision Record Template

An actual record can follow a template:

~~~text
ID: DEP-JDK-012
Component: annotation-processor-x
Coordinates: group:artifact:current-version
Kind: annotationProcessor
Resolved from: build.gradle / platform constraint
Owner: build-platform
Current JDK: 17
Target JDK: 21
Observed issue: fails to access javac internals
Vendor support: target-version supports JDK 21 (needs verification)
Target version: approved compatible release
Priority: P0 blocker
Prerequisites: compiler plugin compatibility
Validation: compile all modules; check generated output
Rollback: restore prior processor and compiler toolchain
Status: pending / in-progress / verified
~~~

Items marked "needs verification" must have evidence before becoming "verified"; the example above is not a compatibility claim for any specifically named artifact.

In addition to an artifact table, draw the dependency chain:

~~~text
Target JDK
  ├─ Build tool compatible version
  │   ├─ Build plugins
  │   └─ Annotation processors
  ├─ Framework/BOM compatible branch
  │   ├─ Bytecode engine
  │   ├─ ORM and JDBC
  │   ├─ HTTP/JSON stack
  │   └─ Test ecosystem
  └─ Runtime image
      ├─ Java agents
      ├─ Native libraries
      └─ JDK modules/providers
~~~

This diagram shows that you cannot select each dependency independently of constraints imposed by upper-layer components.

## 26. Comprehensive Scenario: Backend Cannot Switch Straight to JDK 21

Suppose a service has:

~~~text
orders-service
  build: Gradle Wrapper + code quality plugins
  compiler: javac + Lombok + mapper processor
  runtime: framework server + JSON + ORM + JDBC
  tests: JUnit + Mockito + coverage agent
  deploy: container JRE + APM agent
~~~

The team wants to move from Java 17 to 21. Merely editing `JAVA_HOME` may fail builds due to processors, fail tests due to bytecode instrumentation, or prevent production startup due to agents.

A grounded plan:

**Phase A — Baseline:** save dependency trees, JDK/toolchain versions, artifact metadata, build/test results, container images, and JVM flags.

**Phase B — Build:** check the Gradle Java compatibility matrix, select supported wrapper/plugin versions, and verify processors with the new compiler.

**Phase C — Platform:** select a compatible framework/BOM, diff the dependency graph before and after, and record non-JDK breaking changes.

**Phase D — Runtime:** check JDBC, HTTP/TLS, JSON, native/JNI, and APM agents against the expected runtime image.

**Phase E — Triage:** processor fails to compile → P0; bytecode parser cannot read new class files → P0/P1 depending on usage path; agent without confirmed support → P1; compatible utility library → keep as-is.

**Phase F — Verification and rollout:** clean build, unit, smoke, integration, select operational measurements, then canary. On failure, use the dependency graph and A/B/C/D matrix to determine whether the cause is the JDK, framework, or version override.

The goal is not having the latest version of every library. The goal is a **reproducible dependency combination that aligns with support policies and is proven to work on the target JDK**.

## 27. Conclusion

Identifying dependencies to upgrade **before changing the JDK** is a crucial risk-reduction step in Java Advance Compatibility Migration. The dependency landscape covers build tools, compiler processors, frameworks/BOMs, direct/transitive libraries, agents, native components, and runtime images. Reading only `implementation` declarations or looking up "latest version" misses many blockers.

A sound process locks down the target JDK and minimum Java support level, captures the **resolved dependency graph**, consults compatibility matrices and release notes, identifies JDK internals/bytecode/module issues, classifies blockers, and upgrades in a controlled order. Finally, run tests on the real toolchain and runtime image to prove the new combination operates properly.

A successful migration does not necessarily replace every dependency; it replaces **the exact components that must change**, retains already compatible parts, avoids untargeted upgrades, and produces sufficient evidence for safe deployment.
