# Upgrading Tools and Dependencies in Dependency Order

In a large Java project, changing the JDK version often triggers a cascade of decisions: whether to upgrade Maven or Gradle first, which compiler plugin supports the new bytecode, whether JUnit and coverage tools can run on the target JVM, what minimum Java version the framework requires, and whether BOM-managed dependencies are upgraded in sync. If all versions are changed simultaneously, a `NoSuchMethodError` or `UnsupportedClassVersionError` appearing at the end of the pipeline is very hard to trace back to the original change.

Therefore, **upgrade order must be based on dependency relationships and compatibility requirements, not merely on tool names or version recency**. The goal is to build a sequence of changes where at every stage, the build tool can run, the code compiles, tests are discovered properly, artifacts can be packaged, and the application can start within a supported version combination.

This lesson belongs to the **Migration Strategy** chapter of the **Java Advance Compatibility Migration** module. The focus is on methods for mapping dependencies, ordering JDK, build tool, plugin, library, and framework upgrades by prerequisites; and then proving each step with build, test, and runtime results rather than relying solely on a single green build.

## 1. Learning objectives

After this lesson, learners will be able to:

- Distinguish dependencies between **application components** from dependencies between **migration steps**.
- Build a directed dependency graph, identify which steps must execute first, and find a feasible upgrade path.
- Inventory JDKs, Maven/Gradle, plugins, annotation processors, test engines, agents, framework BOMs, and runtime dependencies.
- Understand why the JVM running the build, the JDK compiling code, the JDK running tests, and the production JDK may differ.
- Choose upgrade stages based on a compatibility matrix and minimum Java versions.
- Use dependency trees, effective POMs, dependency insight, and locking to detect version drift, duplicate dependencies, and transitive dependencies.
- Separate toolchain upgrades, library upgrades, API changes, and behavioral changes to isolate regressions easily.
- Design quality gates, rollback plans, and reporting for each migration stage.
- Handle difficult situations such as dependency cycles, plugins unsupported on the new JDK, code generation, the Jakarta namespace, and end-of-life libraries.

## 2. Two types of dependency relationships to distinguish

### 2.1. Software dependency graph

This is the relationship among modules, libraries, and tools when building and running a program.

Example:

```text
order-service
├── spring-like-framework
│   ├── dependency-injection-core
│   ├── web-runtime
│   └── logging-api
├── persistence-module
│   ├── orm-provider
│   └── jdbc-driver
├── json-library
└── test-tooling
    ├── junit-platform
    ├── mocking-library
    └── coverage-agent
```

The graph shows which libraries are placed on the compile/runtime/test classpath and whose version may be governed by dependency management. A dependency of another dependency is commonly called a **transitive dependency**.

### 2.2. Migration plan dependency graph

The second graph describes **which upgrade step requires the result of another step**.

Example:

```text
        Inventory current state
                   |
                   v
Choose target JDK and compatibility constraints
       |                          |
       +--------------------------+
       |                          |
       v                          v
Build tool supporting JDK  Test tools supporting JDK
       |                          |
       +------------+-------------+
                    |
                    v
        Framework/dependency baseline
                    |
                    v
          Update source/config/API
                    |
                    v
           Integration verification
                    |
                    v
           Packaging and deployment
```

The diagram above is illustrative, not a fixed order for every project. In some cases a new framework requires the new JDK first; in other cases an older Gradle version cannot run on the new JDK, so the Gradle wrapper must be upgraded **while still using the old JDK** first. Prerequisites must be derived from compatibility documentation and actual project constraints.

### 2.3. What is the "A must precede B" edge?

The relationship should be defined explicitly:

```text
A -> B
means completing/meeting condition A before executing or verifying B.
```

Examples:

- A Maven Compiler Plugin supporting `--release` and the required class-file target must be in place before building the new code.
- A Mockito/Byte Buddy version supporting the target JDK's class files must be in place before concluding that mocking tests run on that JDK.
- A Servlet container supporting the corresponding Jakarta Servlet API must be in place before deploying an application migrated from `javax.servlet` to `jakarta.servlet`.
- A contract-compatible schema/database migration must be prepared before deploying new code into production.

These are **execution dependencies**. They differ from a dependency declared in `pom.xml` or `build.gradle`.

## 3. There is no single "upgrade JDK first" order for every project

### 3.1. Compatibility is a multi-dimensional problem

At least the following dimensions must be checked:

| Component | Constraint to verify |
| --- | --- |
| JDK running Maven/Gradle | Do the build tool and plugins run on this JVM? |
| JDK used to compile | Does the compiler support the required source/API/class-file level? |
| Artifact Java release | Are bytecode and APIs compatible with the Java level the product commits to? |
| JDK running unit/integration tests | Are the JUnit engine, mocking agent, and coverage agent supported? |
| Framework/application runtime | Does the framework version support the JDK, servlet container, module system, and actual dependencies? |
| Code generation | Can annotation processors, parsers/bytecode generators read and emit the new class files? |
| Packaging | Do shading plugins, native packaging, Docker images, and buildpacks support the output? |
| Production runtime | Are OS/container/JDK vendor, TLS, CPU architecture, and native libraries compatible? |

A combination may compile successfully yet fail when running tests; another combination may pass tests yet fail in production because the server no longer meets the minimum version.

### 3.2. Example of two different valid orders

**Case A: build tool is too old to run on the new JDK**

```text
Current state: old JDK + old Gradle wrapper
                  |
                  v
Upgrade Gradle wrapper to a version supporting both old JDK and target JDK
                  |
                  v
Upgrade compatible plugins and test dependencies
                  |
                  v
Switch JDK running build/runtime
                  |
                  v
Update source, test, package, and deploy
```

If you switch the JDK running Gradle first, Gradle may fail immediately during build configuration before reaching compilation.

**Case B: new framework requires a higher JDK**

```text
Old framework + old JDK
        |
        v
Upgrade build/test tools capable of running with both states
        |
        v
Prepare new JDK and toolchain
        |
        v
Upgrade framework to a line requiring the new JDK
        |
        v
Update API/config and integration tests
```

Here, you cannot run the new framework on the old JDK runtime once its Java baseline has increased. Some steps can be performed on a migration branch/staging within the same release; the order is still dictated by compatibility, not a mechanical rule of thumb.

### 3.3. Choosing "supported intermediate states"

Each migration stage should produce a verifiable state:

```text
S0: Old combination running stably
S1: New tooling, old application/JDK still builds
S2: Target JDK, framework in a supported combination
S3: Target framework and dependencies, source/config migrated
S4: New combination passed testing and is ready for rollout
```

Not every project has all of S1–S4, and not all intermediate states need to be released. However, **never accept an unsupported intermediate state as proof of production readiness**; if it must be used temporarily during migration, document its limits and do not deploy it.

## 4. Step 1: inventory the "four JVMs" and actual tools

### 4.1. JVM running the build tool

Maven or Gradle runs inside a JVM. This can differ from the JDK the project uses to compile thanks to Maven Toolchains or Gradle Java Toolchains.

Example inspection commands:

```bash
java -version
javac -version
mvn -version
```

For Gradle:

```bash
./gradlew --version
```

On Windows, use the project's corresponding wrapper command, such as `gradlew.bat --version`.

These commands capture a baseline, but do not yet prove that compiler plugins or test processes use that exact JVM.

### 4.2. JDK compiling the code

Maven example:

```xml
<properties>
  <maven.compiler.release>17</maven.compiler.release>
</properties>
```

`--release 17` controls the source level, target class file, and allowed Java SE APIs during compilation per the compiler contract. It does **not** automatically prove that third-party dependencies or the test runtime have the right minimum Java version.

A newer JDK can compile an artifact targeting Java 17. However, if the code inadvertently depends on a dependency compiled for Java 21, the product cannot run on Java 17 just because `release` is set to 17.

### 4.3. JDK running tests

Maven Surefire/Failsafe can fork a JVM; Gradle can use a Java toolchain for the `Test` task. Agents like JaCoCo or bytecode libraries like Byte Buddy run inside the test JVM itself.

Therefore, in addition to `mvn -version`, you must verify the JVM version launched by the **test launcher** and the actual JVM arguments.

### 4.4. JDK running production

A CI agent might use JDK 21 while the Docker image runs Java 17. If the compiler generates Java 21 bytecode or a dependency requires Java 21, deployment can fail with `UnsupportedClassVersionError`.

Record production runtime details from the image/deployment manifest and measurements when the process actually runs. Do not rely solely on a Docker image tag name or the `JAVA_HOME` variable on a developer's machine.

### 4.5. JVM of codegen and auxiliary tools

Annotation processors, compiler plugins, Kotlin/Groovy/Scala compilers, schema generators, API clients, bytecode enhancement tools, or test agents may each have their own minimum JDK.

A build can fail inside a processor before application code is even compiled, even when Java source is completely valid.

## 5. Step 2: collect the dependency graph and actually resolved versions

### 5.1. Maven: declared POM is not always the final result

Versions can originate from:

- Module `dependencies`.
- `dependencyManagement` and imported BOMs.
- Parent POM.
- Transitive dependencies.
- Profiles or properties.
- Plugin dependencies and plugin management.

Useful commands:

```bash
mvn dependency:tree
mvn dependency:tree -Dscope=test
mvn help:effective-pom
```

Read the **effective POM** to see inherited configuration and read the dependency tree to identify the versions actually resolved.

Maven commonly applies mediation rules such as nearest definition when multiple paths lead to different versions, along with related dependency management rules. Consequently, seeing a version in a transitive POM does not mean that exact version will be present.

### 5.2. Gradle: configuration and variant matter

Examples:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight \
  --dependency example-library \
  --configuration runtimeClasspath
```

A module can resolve different dependencies across compile, runtime, and test. `dependencyInsight` helps explain why Gradle selected a particular version within a specific configuration.

Projects using version catalogs, constraints, platforms, enforced platforms, or dependency locking must inspect those sources as well. A version appearing in `libs.versions.toml` is insufficient proof that every configuration resolved to the expected version.

### 5.3. Inventory plugins separately from application dependencies

Maintain two separate lists:

**Application dependencies:** framework, database driver, JSON library, logging, HTTP client, messaging, security, etc.

**Build/test plugins and tools:** compiler plugin, Surefire/Failsafe, JaCoCo, Maven Shade, Gradle plugins, annotation processors, code generators, static analysis, native-image toolchain, etc.

A common mistake is upgrading runtime libraries first, only to discover later that a Maven plugin cannot parse the target JDK's class-file version. Separating the lists enables handling toolchain prerequisites early.

### 5.4. Capture comparable before/after snapshots

The baseline should record:

- Direct and transitive versions of key dependencies.
- Version origins (parent/BOM/platform/override).
- Test-only and runtime-only dependencies.
- Plugin versions and custom JVM arguments.
- Checksums/lockfiles if the project uses them.
- Framework/application server versions.
- Duplicate dependencies or multiple `.jar` copies in deployment.

When comparing, focus on **unintended version shifts**. Upgrading a BOM can shift dozens of dependencies, including components the project source does not import directly.

## 6. Step 3: create an evidence-based compatibility matrix

### 6.1. One row per component to upgrade

| Component | Current | Target | Minimum JDK / support | Blocked by | Verification evidence |
| --- | --- | --- | --- | --- | --- |
| JDK runtime | Source JDK | Target JDK | Level required by product | Container, native library | Startup and integration tests |
| Gradle/Maven | Source version | Chosen version | Can it run on target JDK? | JVM running build | Version log + build |
| Compiler plugin | Source version | Target-supporting version | Supports `--release`/class file? | Build tool/JDK compiler | Compile + inspect bytecode |
| JUnit/engine | Source version | Compatible line | Test JVM minimum | Surefire/Gradle Test | Test discovery + report |
| Mockito/Byte Buddy | Source version | Target-JDK-supporting line | Class-file parser/agent support | Test JVM | Mock/instrumentation tests |
| JaCoCo | Source version | Bytecode-supporting line | Class-file version | Test plugin/JVM | Coverage report |
| Framework BOM | Source version | Target line | Java baseline + extension compatibility | Build tool, JDK | Dependency graph + startup |
| Persistence/HTTP libs | Source version | Target line | Framework/API/driver requirements | BOM, runtime | Integration/contract tests |
| Packaging/deploy | Source version | Target version | Jar/module/image support | Toolchain/JDK | Artifact smoke test |

Fill in concrete versions from vendor documentation matching that exact version and from project measurements. Do not use a "latest" label as a target state because what "latest" resolves to can change between builds.

### 6.2. Distinguish minimum, supported, and tested

Three distinct concepts:

- **Minimum JDK:** the lowest version a library declares or its class files can run on.
- **Supported JDK:** the set of versions the vendor commits to or documents as supported.
- **Tested JDK:** the set of versions on which the project team has executed tests against its own artifacts.

A dependency having a minimum of Java 11 does not imply vendor support on all future JDKs. Similarly, code passing a smoke test on JDK 21 is not enough to claim full support.

### 6.3. Classify hard vs. soft constraints

**Hard constraints** must be satisfied before dependent stages:

- Tool cannot run on the chosen JVM.
- Framework requires a higher minimum JDK than the current runtime.
- Plugin does not support the class-file version to compile/inspect.
- `javax.*`/`jakarta.*` APIs or module system incompatibility.
- Runtime lacks a required dependency.

**Soft constraints** need governance but may allow temporary execution with clear risk:

- Deprecated API warnings.
- Older plugin not yet failing within tested scope; must check support policy.
- Slight performance regression within acceptable thresholds.
- Extension lacking formal vendor certification yet passing a representative test suite.

Do not turn all warnings into blocking errors without an established policy; equally, do not ignore hard constraints just because the build happens to be green temporarily.

## 7. Step 4: build an upgrade order via a directed graph

### 7.1. Identify nodes and edges

Example plan:

```text
Node A: Upgrade Gradle wrapper to run on target JDK
Node B: Upgrade compiler/test/coverage plugins
Node C: Configure target JDK toolchain
Node D: Upgrade framework platform/BOM
Node E: Upgrade extension libraries according to BOM
Node F: Update source + configuration
Node G: Run integration/contract tests
Node H: Switch deployment runtime
```

Possible edges:

```text
A -> B
A -> C
B -> G
C -> D
D -> E
D -> F
E -> G
F -> G
G -> H
```

If in practice the new framework only builds after upgrading the JDK, add edge `C -> D`. If the migration guide requires an API transformation step before changing the BOM, model that dependency explicitly instead of applying a diagram mechanically.

### 7.2. Topological ordering

With an **acyclic** dependency graph, topological sorting provides a valid order: at each step, prioritize nodes whose prerequisites are all complete.

```text
Ready: A
Do A
Ready: B, C
Do B and C (can be two independent branches)
Ready: D
Do D
Ready: E, F
Do E and F
Ready: G
Do G
Ready: H
Do H
```

This does **not** mean committing everything in one massive change. You can split PRs/CI gates by "wave", recording baseline and results for each wave.

### 7.3. When the graph has a cycle

Example:

```text
New framework needs new JDK
        ^
        |
New build plugin needs new framework
        ^
        |
New build tool needs new JDK
```

When a genuine dependency cycle exists, no topological order exists. You must find a way to **break the cycle**:

- Find an intermediate version supporting both the old and new frameworks.
- Extract the code/migration tool into an independent task outside the main build.
- Upgrade the build tool on the old JDK first, then upgrade the JDK.
- Extract a shared module or library acting as an adapter with a stable contract.
- Run a controlled code transformation step before switching the runtime.
- Ask the vendor to confirm an upgrade path or choose a different target version.

Do not force through using an unsupported version combination and call it verified.

### 7.4. Maintain a "verification trail" for every wave

Each wave should specify:

1. Concrete input versions.
2. List of changed dependencies.
3. Rationale for the change and satisfied prerequisites.
4. Appropriate build/test checks.
5. Pass/fail criteria.
6. How to roll back to the pre-wave state.
7. Owner.

If a wave changes too many independent versions, narrow its scope so failures remain traceable.

## 8. Practical ordering among build tools, plugins, and the JDK

### 8.1. Upgrade the build tool before switching the build JVM when needed

For example, an old Gradle wrapper cannot run on the new JDK. A sound order is:

```text
Current JDK + old wrapper
          |
          v
Upgrade wrapper to a version supporting both current and target states
          |
          v
Builds successfully with current JDK
          |
          v
Switch JDK running Gradle / toolchain and re-test
```

Use the project's Gradle Wrapper so CI and developers use a unified version. Do not rely on different pre-installed Gradle versions across machines.

With Maven, check the Java baseline of the Maven distribution alongside Maven plugins. Upgrading the Maven launcher alone does not guarantee all plugins support the new JDK.

### 8.2. Upgrade plugins that understand the class-file format

Plugins that read or transform bytecode include:

- Maven Compiler Plugin / Gradle Java plugin and compiler toolchain.
- JaCoCo, code coverage, instrumentation.
- Byte Buddy, ASM, mocking libraries.
- Maven Shade/Gradle Shadow, bytecode relocation.
- Obfuscators, scanners, bytecode analyzers.
- Kotlin/Groovy/Scala compilers and corresponding plugins.

If a tool only supports class files up to Java 17 while the new JDK emits Java 21 class files, the plugin can fail during class scanning even though `javac` succeeded.

Therefore, select plugin versions based on the **class-file version they must process**, not only the plugin's minimum JDK.

### 8.3. Upgrade test infrastructure before trusting test results

A meaningful order:

```text
Test runner/plugin supporting target JDK
          |
          v
JUnit Platform and correct test engine
          |
          v
Mocking/coverage agents able to run on target JDK
          |
          v
Unit/integration tests are actually discovered
          |
          v
Compare test counts and behavior before/after migration
```

A dangerous pitfall is `BUILD SUCCESS` with `Tests run: 0` after changing the JUnit provider or include patterns. Only when the right engine is configured and reports confirm the expected test count can tests serve as a quality gate for subsequent waves.

### 8.4. Do not upgrade the toolchain unconditionally

Some legacy build plugins or frameworks only run on the source JDK. If you cannot upgrade everything simultaneously, options include:

- Running the build tool on a different JDK than the compile JDK via toolchains.
- Using an intermediate build branch.
- Using a transitional plugin version supporting both.
- Transforming source/config before upgrading the runtime.

However, respect the actual capabilities of Maven/Gradle/plugins. Never assume a toolchain fixes a plugin that executes inside the build tool's own JVM and accesses JDK internals.

## 9. BOMs, platforms, and grouped dependency upgrades

### 9.1. A BOM is the "unit of compatibility" when frameworks manage versions

Many frameworks publish a BOM or platform carrying a verified set of versions tested together. In Maven, a BOM can be imported under `dependencyManagement`; in Gradle, `platform(...)` or the corresponding plugin/framework mechanism can be used.

Maven example with hypothetical coordinates:

```xml
<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>com.example.platform</groupId>
      <artifactId>example-bom</artifactId>
      <version>3.0.0</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>com.example.platform</groupId>
    <artifactId>example-web-starter</artifactId>
  </dependency>
</dependencies>
```

This example illustrates only the BOM mechanism, not an actual published artifact.

A BOM helps control versions of dependencies within its managed scope. However, it does **not guarantee** that all Maven plugins, third-party libraries, or runtime containers are also governed by the BOM.

### 9.2. Gradle platforms and dependency locking

Example:

```groovy
dependencies {
    implementation platform('com.example.platform:example-bom:3.0.0')
    implementation 'com.example.platform:example-web-starter'
}
```

In a real project, check version catalogs, constraints, dependency locking, and overrides. A dependency may be constrained from multiple places; the resolved result is what matters.

When upgrading a BOM, lockfiles may need controlled updates. Never delete the entire lockfile just to force a build to "pass" without reviewing which versions changed.

### 9.3. Why not upgrade individual framework JARs arbitrarily?

A framework's module suite may share internal APIs or extension points that are compatible only within a coordinated version range. If core is on a new major version while a starter or security module stays on an old major version, code may compile yet fail at runtime:

```text
java.lang.NoSuchMethodError
java.lang.NoClassDefFoundError
java.lang.IncompatibleClassChangeError
```

Thus, for frameworks with an official platform/BOM, **upgrade the dependency group in the combination prescribed by the framework**, unless you have valid reasons and evidence for an override.

### 9.4. Managed vs. unmanaged dependencies

During each BOM upgrade, categorize components into:

1. Components managed by the BOM and expected to upgrade together.
2. Components with explicit overrides for security or compatibility reasons.
3. Components outside the BOM whose compatibility must be checked manually.
4. Build plugins outside BOM dependency management.
5. Runtime/libraries supplied by the application server, excluded from the artifact.
6. Native libraries, agents, and tools deployed outside the Java dependency graph.

A new BOM neither upgrades the server hosting the application nor modifies custom class loaders or JDK container images.

## 10. Where should code generation and annotation processing be upgraded?

### 10.1. Processors must understand current APIs and language features

Some projects use:

- Lombok or boilerplate-generating annotation processors.
- MapStruct or code mappers.
- JPA metamodel generators.
- Query code generation.
- OpenAPI/gRPC/Protobuf generators.
- Kotlin KAPT/KSP or equivalent tools.
- Framework AOT and build-time augmentation.

These tools may depend on compiler internals, ASTs, reflection, or framework-specific annotation APIs. When changing JDK/framework, they may need to be upgraded before application code can compile.

### 10.2. Separate generated source from handwritten source

A typical pipeline:

```text
JDK + build tool + annotation processor
                 |
                 v
          Generated source
                 |
                 v
         Compile application
                 |
                 v
          Package/run/test
```

If generated code still imports legacy `javax.*` packages while the target framework expects `jakarta.*`, editing imports in handwritten sources is insufficient. You must upgrade the generator/template or change generator configuration first.

Do not manually patch generated files on every build; fixes must come from **code generation inputs and the generator version**.

### 10.3. Verify generated artifacts remain suitable

After upgrading tools, verify:

- Generated source matches the target framework API.
- Annotations and nullability semantics are correct.
- Compiler target/class-file level is appropriate.
- No duplicate generated classes appear.
- Generated source resides in the right compile source set.
- Output does not silently alter schema/API contracts.
- Runtime does not rely on a processor that was previously packaged accidentally as a production dependency.

When a generator emits schemas or database migrations, enforce dedicated review because changes can affect persisted data.

## 11. Jakarta, JPMS, and framework upgrade stages

### 11.1. The framework's Java baseline dictates the path

For instance, many modern framework lines increase the minimum JDK. If the target framework requires Java 17, you cannot deploy it on Java 11 even if the compiler on a developer laptop runs JDK 21.

Cross-check:

- Framework core.
- Servlet/application server.
- ORM/JPA provider.
- Security integrations.
- Bean Validation and serialization.
- Message broker clients.
- Monitoring/test libraries.

Checking a single "supports Java 17" note in core documentation is not enough to assume every extension is compatible.

### 11.2. Namespace `javax` → `jakarta`

Several generations of Jakarta EE and related frameworks moved many APIs from `javax.*` to `jakarta.*`.

Example:

```java
// Legacy Java EE APIs in some ecosystems
import javax.persistence.Entity;
import javax.servlet.http.HttpServletRequest;

// Corresponding Jakarta APIs in newer lines
import jakarta.persistence.Entity;
import jakarta.servlet.http.HttpServletRequest;
```

This is a source/API ecosystem migration, not merely a JDK upgrade. Upgrade ordering must ensure the framework, servlet container, ORM, validation provider, and third-party dependencies form a combination supporting the right namespace.

**Do not replace every `javax.*` with `jakarta.*`.** Java SE APIs such as `javax.sql.DataSource` or `javax.crypto` remain `javax.*`.

### 11.3. JPMS and reflection

When moving to Java 9+ or placing JARs on the module path, named modules can restrict `exports`/`opens`. Legacy reflection-heavy libraries may throw `InaccessibleObjectException` or `IllegalAccessError`.

Do not scatter `--add-opens` indiscriminately before trying to upgrade frameworks. If a temporary workaround is necessary, record:

- Source JDK/module and package.
- Target named module or `ALL-UNNAMED`.
- Offending component.
- JVMs needing the flag (build/test/app).
- Target supported version to remove the workaround.

Upgrading a dependency to eliminate internal API access may be a prerequisite for upgrading the production JDK.

## 12. Separating dependency scopes when moving to a new JDK

### 12.1. Compile-time differs from runtime

A library needed only for compilation, such as an annotation API or processor, does not necessarily belong at runtime. Conversely, a JDBC driver or JUnit engine may be required at runtime even though source code never imports it directly.

Wrong scopes can lead to:

- Compile succeeds, but runtime misses classes.
- Runtime contains two implementations of the same service.
- Processor is packaged by mistake into the production artifact.
- Test classpath resolves a different dependency version than runtime classpath.
- A server-"provided" library is bundled anyway and causes class-loader conflicts.

### 12.2. Maven scopes

Maven commonly has `compile`, `provided`, `runtime`, `test`, and other scopes with distinct meanings. During migration, reconcile scopes against actual packaging.

For example, a Servlet API supplied by an application server can use an appropriate server-provided scope, whereas an embedded-container deployment requires different packaging/dependencies. Never apply one blanket `provided` rule to every web stack.

### 12.3. Gradle configurations

Gradle distinguishes `implementation`, `api` (with `java-library`), `compileOnly`, `runtimeOnly`, `testImplementation`, and `testRuntimeOnly`.

If the JUnit Jupiter API is present in `testImplementation` while its engine is absent from `testRuntimeOnly` or equivalent dependencies, tests may compile yet the launcher cannot execute them.

### 12.4. Dependencies "outside the build"

Some runtime dependencies do not appear in the application POM:

- JARs provided by the application server.
- Java agents or monitoring libraries.
- Plugin JARs mounted from a separate volume.
- JDBC drivers installed directly on the server.
- Native libraries.
- JDK modules or command-line flags.
- Sidecars/container images supplying assets.

These must be included in the upgrade matrix even though they do not show up in the application's dependency tree.

## 13. Library upgrade workflow without unintended breakage

### 13.1. Upgrade dependencies in small groups

One way to partition waves:

1. Build/test tooling prerequisites.
2. Security dependencies or replacements for unmaintained libraries within the current compatible range.
3. Target framework BOM/platform with core dependencies.
4. Extensions: security, ORM, web, messaging, serialization.
5. Application source/config/API changes.
6. Packaging, deployment image, and production runtime.
7. Clean up temporary dependencies/flags once stable.

Order can vary by dependency graph, yet **tightly coupled components** should stay within the same verification wave to avoid unsupported combinations.

### 13.2. SemVer is not an absolute guarantee

Semantic Versioning helps estimate change scope, yet a SemVer-compliant dependency does not eliminate all risk. A patch can fix a bug in a way that alters prior behavior; a library not strictly adhering to SemVer can change APIs in a minor release.

Therefore, for every version bump, read:

- Release notes.
- Migration guides if available.
- Minimum JDK.
- Deprecated/removed APIs.
- Security advisories.
- Transitive dependency compatibility.
- Known issues and behavioral changes.

Never use a "minor is always safe" rule to skip testing.

### 13.3. Source, binary, and behavioral compatibility

| Type | Question | Verification method |
| --- | --- | --- |
| Source | Does existing code compile against the new API? | Recompile each module/client. |
| Binary | Do existing compiled client JARs link against the new library? | Binary compatibility checks and running precompiled clients. |
| Behavior | Do results, exceptions, protocols, and transactions preserve contract? | Regression/integration/contract tests. |
| Operational | Are startup, resource use, health, and monitoring still healthy? | Staging/canary/observability. |
| Data | Are schemas, serialization, and historical data compatible? | Migration tests/backup/restore validation. |

A dependency upgrade can be source-compatible yet behavior-incompatible. Running `mvn compile` alone is insufficient for full evaluation.

### 13.4. Classpath conflicts and version convergence

Pay close attention when multiple modules pull in different versions of the same library. With Maven/Gradle, verify the resolved version and why it was chosen.

You can consider enforcement/convergence rules or appropriate dependency constraints. However, forcing every dependent to **an arbitrary version** does not guarantee compatibility if one library actually depends on an old removed API.

When convergence fails, consider upgrading the upstream dependency, replacing a library, classloader isolation, or controlled shading. Shading carries high maintenance cost because reflection, service metadata, and binary compatibility can break.

## 14. Test infrastructure as a prerequisite for every wave

### 14.1. You cannot trust wave quality if the test runner is broken

When upgrading the JDK, test suites may fail or silently not execute because:

- Outdated Surefire/Failsafe does not recognize the test engine.
- Jupiter API is present without the Jupiter engine.
- Vintage is unconfigured, causing JUnit 4 tests to vanish.
- Mockito/Byte Buddy does not yet support the class-file format.
- JaCoCo agent cannot instrument the new classes.
- Testcontainers/framework integration is incompatible with the environment.
- JVM args for forked tests differ from the intended runtime.

Thus, upgrade the **test toolchain sufficiently to preserve baseline test coverage** before relying on test output to judge other framework/dependency changes.

### 14.2. Separating Surefire and Failsafe in Maven

Maven Surefire typically runs unit tests in the `test` phase. Maven Failsafe is used for integration tests via `integration-test` and `verify` goals when configured accordingly.

Example:

```bash
mvn test
mvn verify
```

`mvn test` does not mean every `*IT` ran. `mvn verify` only truly validates integration tests when Failsafe is bound and matching source/test naming conventions are configured properly.

During migration, compare both unit and integration test reports. A passing build reporting `Tests run: 0` is a red flag requiring investigation, not success.

### 14.3. Controlling test coverage

If JaCoCo or an instrumentation agent fails on the target JDK, coverage reports may be missing/zero or the job may fail before tests start.

Do not rush to lower coverage thresholds or disable the agent. Check the agent's Java compatibility and how `argLine`/JVM arguments are combined in the test launcher.

### 14.4. Before/after verification matrix

| Stage | Must prove |
| --- | --- |
| Compile | Correct JDK/toolchain; compatible source and dependencies. |
| Unit tests | Test engine discovers tests properly; counts do not drop unexpectedly. |
| Integration tests | DB, messaging, web, serialization, and framework extensions work. |
| Contract tests | API/wire formats do not break consumers. |
| Package | JAR/WAR/native image contains expected classes/resources/services. |
| Runtime smoke | Artifact starts on the target JDK/container. |
| Load/security tests | Latency, throughput, and authentication/authorization meet policy. |

## 15. Staged example: upgrading a Java 11 system to Java 17

### 15.1. Hypothetical context

Suppose a service has these components:

```text
Application: inventory-service
Source JDK: 11
Target: JDK 17
Build: old Gradle wrapper
Framework: line A
Security extension: line S
ORM: line O
Tests: JUnit 4 + Jupiter, Mockito, JaCoCo
Deploy: Docker container
```

Names A/S/O are illustrative placeholders, not real versions.

### 15.2. Issues found during discovery

- The current Gradle wrapper cannot run on JDK 17.
- A code generation plugin calls legacy JDK/compiler APIs.
- Coverage agent does not support the target bytecode/JVM yet.
- Only framework line B supports JDK 17 and changes security configuration.
- The ORM extension must upgrade alongside framework B.
- The production container image is still Java 11.
- Several JUnit 4 unit tests only run via Vintage/legacy runners.

### 15.3. Migration dependency graph

```text
A. Upgrade wrapper, keep JDK 11
       |
       +--> B. Upgrade codegen/bytecode tooling
       |
       +--> C. Upgrade test runner/engine/JaCoCo
                    |
                    v
D. Prepare JDK 17 toolchain and test baseline
                    |
                    v
E. Upgrade framework BOM A -> B
       |
       +--> F. Upgrade corresponding security/ORM extensions
                    |
                    v
G. Update source and configuration per migration guide
                    |
                    v
H. Unit + integration + contract tests on JDK 17
                    |
                    v
I. Build artifact + JDK 17 container image
                    |
                    v
J. Staging/canary + metrics + rollout decision
```

This is a reasonable path if intermediate versions are vendor-supported. Do not treat it as a substitute for a real compatibility matrix. If framework A cannot run on JDK 17, step D must be replaced with preparing a separate toolchain/compile target or executed alongside step E on a tested migration branch.

### 15.4. Per-wave plan

| Wave | Changes | Gate before continuing |
| --- | --- | --- |
| 0 | Capture JDK, dependency graph, and test report baselines | Baseline results are reproducible. |
| 1 | Upgrade wrapper and plugins on JDK 11 | Existing build and tests continue to run. |
| 2 | Prepare JDK 17 and test tools | Test runner accurately discovers the full test suite. |
| 3 | Upgrade framework BOM + mandatory extensions | Compile, startup, and security/ORM integration tests pass. |
| 4 | Update source/API/config | Contract/regression tests pass; no ignored legacy configs remain. |
| 5 | Switch container runtime and package | Image contains right JDK; artifact starts cleanly. |
| 6 | Staging and canary | Error/latency thresholds not exceeded; rollback verified. |

### 15.5. Conclusion of the example

Upgrading to the Java 17 image before updating the wrapper can stop the pipeline from running. Upgrading the framework before the JDK meets the version baseline can trigger class-file errors. Changing everything simultaneously allows a JUnit engine issue to produce "false green" tests that mask framework regressions.

Prerequisite-based sequencing isolates failure classes and yields evidence at every wave.

## 16. Maven: example of pinning plugins and Java release

An illustrative Maven configuration pinning source/target Java release and declaring plugin versions:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>inventory-service</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.2</version>
        <executions>
          <execution>
            <goals>
              <goal>integration-test</goal>
              <goal>verify</goal>
            </goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

Versions here are purely illustrative of **pinning plugins**; check the support matrix against your current JDK/Maven and framework before applying in a real project.

The snippet above does not itself declare a JUnit engine, test framework dependencies, ORM, or runtime dependencies. For `mvn verify` to be meaningful, you need complete test dependencies, test sources, and a real integration test environment.

### 16.1. Maven Compiler Plugin does not change the Maven runtime

`maven.compiler.release` only adjusts how the compiler compiles for the target Java release. It does not change the Java version running Maven. If a Maven plugin requires Java 17 while Maven runs on Java 11, the plugin may fail to load.

### 16.2. Parent and pluginManagement

In a multi-module Maven project, plugin versions can be declared in parent `pluginManagement` so modules inherit configured versions appropriately. However, an entry in `pluginManagement` does not automatically activate every plugin goal for every module.

When auditing, inspect each key module's effective POM to verify the executing plugins and inherited settings.

### 16.3. Multi-module dependency ordering

Maven modules can depend on each other:

```text
shared-api -> data-access -> order-service
```

The reactor orders build execution according to internal dependencies. However, **build order** does not automatically determine the upgrade order for major framework versions or the JDK; a dedicated migration plan is needed for module versions and contracts.

In a monorepo, establish stable publishing/consumption for shared APIs before downstream modules switch to new APIs.

## 17. Gradle: wrapper, toolchain, and dependency constraints

### 17.1. Wrapper and Java toolchain are two separate axes

Gradle Groovy DSL example:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

A Java toolchain lets certain Java tasks use the chosen JDK, yet it does not mean every Gradle plugin runs on that toolchain JDK. The Gradle daemon/build logic still has its own JVM running Gradle and must be supported by the wrapper/plugins.

### 17.2. Dependency constraints

Illustrative example:

```groovy
dependencies {
    implementation 'com.example:client-api:2.0.0'

    constraints {
        implementation('com.example:shared-codec:3.0.0') {
            because 'Version duoc kiem tra voi client-api 2.0.0'
        }
    }
}
```

A constraint expresses a version requirement during dependency resolution, not proof of binary compatibility. After adding a constraint, inspect `dependencyInsight` and run tests for affected consumers.

### 17.3. Dependency locking

If a project uses dependency locking, upgrading a BOM or plugin may require updating lock state. You should:

1. Capture the current lockfile.
2. Execute an upgrade wave.
3. Generate/update lock state following project procedures.
4. Review the diff of changed versions.
5. Run tests.
6. Commit lockfiles together with the explanatory changeset.

Do not delete lockfiles just to resolve a resolution failure without knowing which dependencies will shift.

### 17.4. Toolchains in CI

CI must provide the right JDK or a controlled provisioning mechanism. If a task requires a Java 17 toolchain and CI lacks a matching JDK, the build can fail before compilation starts.

Using the wrapper alongside explicit version/toolchain settings avoids "works on developer machine, fails on CI" caused by differing tools.

## 18. Dependency graphs across modules and services

### 18.1. Shared libraries first, consumers later

If `shared-api` is used by multiple services, altering its public API can trigger synchronized changes across teams.

A safe strategy:

1. Add new APIs in a backward-compatible way if possible.
2. Release the shared library with adapters or parallel APIs.
3. Upgrade consumers individually per plan.
4. Monitor consumers still using the legacy API.
5. Remove legacy APIs only when compatibility policy permits.

This is **organization-level dependency-graph ordering**, not merely one application's Maven libraries.

### 18.2. Database schemas and message contracts

Changing an ORM or serializer can alter schemas or wire formats. In distributed systems, you cannot always upgrade every service simultaneously.

Prefer the *expand–migrate–contract* pattern when appropriate:

```text
Expand compatible schema/protocol
        |
        v
Deploy producer/consumer reading both old and new formats if needed
        |
        v
Migrate data and traffic
        |
        v
Verify no legacy consumers remain
        |
        v
Remove old schema/API in an appropriate release
```

This protects partial rollouts and enables safer rollback than immediate breaking changes.

### 18.3. Version skew between services

Even when one service finishes migration, another may still run an older version. Test **new–old** version combinations across realistic rollout windows, especially for authentication, JSON payloads, Kafka/queue schemas, or shared database state.

## 19. Handling blockers by root-cause category

| Symptom | Root-cause class | Diagnostic direction |
| --- | --- | --- |
| Gradle/Maven fails to start on new JDK | Build tool JVM compatibility | Check wrapper/distribution support and plugin versions. |
| `invalid target release` | Compiler JDK does not support `--release`/target | Check `javac -version` and compiler toolchain. |
| `UnsupportedClassVersionError` | Running JVM is older than loaded bytecode | Check class-file version and test/runtime JDK. |
| `NoSuchMethodError` | Binary API mismatch or dependency mediation | Identify actual JAR loaded and inspect dependency tree. |
| `NoClassDefFoundError` | Missing class or wrong dependency/runtime path | Check scopes, packaging, class loaders, and module path. |
| `InaccessibleObjectException` | Reflection blocked by JPMS | Upgrade library/framework; configure `opens` if needed. |
| `ServiceConfigurationError` | Invalid SPI/provider metadata | Check `META-INF/services`, shading, and provider classes. |
| Green build but `Tests run: 0` | Test engine/provider/include filters | Check Surefire/Failsafe/JUnit Platform and test reports. |
| JaCoCo/Mockito fails on new JDK | Unsupported bytecode/agent | Upgrade JaCoCo/Byte Buddy/ASM/Mockito accordingly. |
| Generated source still has `javax.*` | Old generator/template | Upgrade processor/codegen and target source APIs. |
| Runtime fails only in production | Dependency/container/JDK mismatch with CI | Compare images, classpaths, native libs, and configs. |
| API output differs despite passing compile | Framework/dependency behavioral change | Run regression/contract/security/integration tests. |
| Unexpected version in artifact | BOM override/lockfile/transitive resolution | Effective POM, dependencyInsight, inspect packaging. |

Do not fix errors by jumping everything to "latest" at once. Classify which category the error falls into and resolve the missing prerequisite.

## 20. Analysis process for hard-to-untangle dependency cycles

### 20.1. Example of a blocker

A project has:

- Legacy codegen plugin cannot run on the new JDK.
- New codegen plugin only supports a newer framework line.
- Newer framework requires sources migrated to the new namespace.
- Legacy sources can only be generated by the legacy codegen plugin.

A viable staged approach:

1. Keep the old JDK to generate current sources and save baseline artifacts.
2. Upgrade the plugin/generator to a transitional version or replace the generator if no compatible path exists.
3. Migrate templates/source annotations per guide.
4. Upgrade the framework and compiler toolchain on a branch holding the updated generated code.
5. Compile and test on the target JDK.

If no intermediate version exists, extract generation into an independent module/tool or apply controlled manual updates **at the template source**, avoiding edits to generated outputs that would be wiped out on the next build.

### 20.2. When a dependency is unmaintained

If a library does not support the target JDK and has no upgrade release:

- Evaluate replacing it with an alternative library.
- Write an adapter to narrow the API surface and migrate incrementally.
- Isolate into a separate service/worker running on the legacy runtime for a bounded period, if security policy allows.
- Use class-loader isolation or shading only when genuinely suitable.
- Retire unused features.

Never assume shading or `--add-opens` ensures long-term viability; they do not fix bytecode, native, API removal, or security issues across the board.

### 20.3. Decisions must have an owner and deadline

For unresolved blockers, document:

```text
Blocked component:
Current version:
Required target:
Blocking constraint:
Supported intermediate version:
Owner:
Mitigation / alternative:
Risk accepted by:
Review date:
Verification evidence:
```

Do not let temporary workarounds persist indefinitely without clear ownership.

## 21. Designing quality gates for each wave

### 21.1. Technical gates

A wave may require:

- Dependency resolution succeeds with no unintended version conflicts.
- Build tool operates on the chosen JVM.
- Java source compiles at the desired release level.
- Test suite is fully discovered; any count drops are justified.
- No bytecode agent, annotation processor, or packaging errors.
- Final artifact contains required resources and service providers.
- Runtime smoke tests pass on the target JDK/container.

### 21.2. Business gates

If the wave touches frameworks or persistence:

- API contracts remain accurate.
- Authentication/authorization does not widen permissions beyond policy.
- Database queries, transactions, and schemas operate cleanly.
- Message serialization remains compatible between producers and consumers.
- Retries, timeouts, and idempotency work as expected.
- Latency p95/p99 and resource usage stay within thresholds.
- Logs/metrics/traces continue to meet operational requirements.

### 21.3. Security and dependency inventory gates

When updating dependencies:

- Identify versions with unresolved CVEs.
- Review licenses/NOTICE files.
- Update SBOMs and dependency lock states.
- Ensure vulnerable dependencies are not hidden inside shaded JARs unseen by scanners.
- Verify the JDK/runtime image remains within support policy.

### 21.4. Release and rollback gates

Before production rollout:

- Wave-level changelog is prepared.
- Matching deployment artifacts and configurations are ready.
- Canary limits/feature flags are set where appropriate.
- Metric-driven rollback criteria are defined.
- Plans exist for non-directly-reversible data/schemas.
- An explicit approver owns the stage sign-off.

## 22. Dependency-ordered migration worksheet template

You can use a table such as:

| ID | Step | Prerequisites | Component/version | Action | Evidence | Status |
| --- | --- | --- | --- | --- | --- | --- |
| M-01 | Baseline | None | JDK, framework, build | Capture versions and reports | Logs, dependency graph | Pending |
| M-02 | Upgrade build wrapper | M-01 | Gradle/Maven | Pick version supporting source and target states | Legacy build still passes | Pending |
| M-03 | Upgrade compiler/codegen | M-02 | Plugins/processors | Ensure target compilation is supported | Compile and generated-source checks | Pending |
| M-04 | Upgrade test tooling | M-02 | JUnit/agents | Configure engine and bytecode tools | Test counts and coverage | Pending |
| M-05 | Prepare target JDK | M-02,M-03,M-04 | Toolchain/runtime | Verify JDK and baseline tests | Toolchain log and smoke tests | Pending |
| M-06 | Upgrade platform/BOM | M-05 or actual prereq | Framework | Apply guide, record version diff | Dependency graph | Pending |
| M-07 | Upgrade extensions | M-06 | ORM/security/web | Pick compatible combination | Integration tests | Pending |
| M-08 | Update API/config | M-06,M-07 | Source/config | Rename/replace/migrate semantics | Compile, contract/security tests | Pending |
| M-09 | Switch artifact/image | M-08 | Package/deploy | Build and test target runtime | Startup/health/performance | Pending |
| M-10 | Rollout | M-09 | Production | Canary and monitor | Metrics, rollback proof | Pending |

This is a **starting template**, not a rigid schedule. In actual projects, adjust prerequisites to express true dependencies; for example, you may need namespace changes before part of a framework upgrade, or a JDK upgrade at a different milestone.

### 22.1. Using meaningful statuses

Useful status labels:

- `PENDING`: not yet started.
- `READY`: all prerequisites met.
- `BLOCKED`: unmet constraint remains.
- `IN_PROGRESS`: changes underway.
- `VALIDATED`: wave gates passed.
- `ROLLED_BACK`: reverted.
- `WAIVED`: incomplete yet formally approved with documented risk evidence.

Never mark `BLOCKED` as `VALIDATED` simply because a failing test branch was skipped.

## 23. Common mistakes

### 23.1. Upgrading all versions at once

When hundreds of dependencies and plugins change in a single commit, tracing a runtime regression to its cause becomes extremely difficult. Upgrade in waves tied to prerequisites with before/after reports.

### 23.2. Upgrading only the JDK while keeping outdated tooling

Compiler plugins, JaCoCo, or mocking frameworks may fail on new bytecode. Choosing a target JDK must go hand in hand with toolchain verification.

### 23.3. Treating Maven/Gradle runtime and Java toolchain as identical

The JDK running the build tool is not necessarily the JDK compiling code or running tests. Measure each JVM in CI and production.

### 23.4. Upgrading a BOM while overriding many old libraries

A new BOM can be partially negated by version overrides, transitive dependencies, and independent plugins. Read the effective POM/dependency insight to see the final resolved versions.

### 23.5. Adding `--add-opens` to cure every failure

JPMS access is only one category of errors. `UnsupportedClassVersionError`, `NoSuchMethodError`, broken codegen plugins, or missing `ServiceLoader` providers cannot be fixed by opening packages blindly.

### 23.6. Overlooking the test engine

Upgrading only the JUnit API without a matching engine/provider can cause builds to run zero tests. Inspect test reports, not merely the exit code.

### 23.7. Editing generated source instead of the generator

The next build regenerates the old output and erases manual patches. Upgrade the processor/template/extension at the source.

### 23.8. Assuming SemVer or release notes guarantee behavior

Even a minor version bump can alter defaults or fix bugs in ways that change outputs. Run meaningful regression and contract tests.

### 23.9. Equating POM dependencies with actual runtime

Application servers, containers, plugin directories, and Java agents may inject their own dependencies. Inventory the deployed runtime classpath, not just build descriptors.

### 23.10. Forgetting data rollback and cross-service contracts

Fast code rollback does not automatically mean database schemas, message formats, or serialized payloads can revert instantly. Upgrade plans must account for consumers still running old versions.

## 24. Checklist before finalizing the upgrade strategy

- [ ] Source/target JDKs and Java support scope are clearly defined.
- [ ] JVMs running Maven/Gradle, compilation, tests, and production are verified.
- [ ] Build plugins, code generators, test engines, agents, and dependencies are listed.
- [ ] Dependency tree/effective POM or Gradle dependency insight/lockfiles are captured.
- [ ] Tool dependencies are separated from runtime/test dependencies.
- [ ] Minimum/supported/tested Java versions are checked for every critical component.
- [ ] Framework BOM/platform and out-of-BOM overrides are identified.
- [ ] Migration dependency graph is created with clear edge meanings.
- [ ] Supported intermediate stages are identified and dependency cycles are broken if any exist.
- [ ] Upgrade waves for wrapper/plugins/JDK/framework/extensions/source/deploy are planned appropriately.
- [ ] Annotation processors, generated sources, and bytecode tools are verified.
- [ ] Jakarta, JPMS, reflection, native libraries, and service metadata are evaluated where relevant.
- [ ] Test runners use the proper engines; test counts do not drop unexpectedly.
- [ ] Source/binary/behavioral compatibility is verified for upgraded dependencies.
- [ ] Integration, contract, security, and performance tests are executed on the target runtime.
- [ ] Packaged artifacts and actual container/application servers are verified.
- [ ] Version locks, SBOM, licenses, and security reports are updated appropriately.
- [ ] Blockers, workarounds, owners, deadlines, and evidence are documented.
- [ ] Rollout/canary/rollback and plans for backward-incompatible data are defined.
- [ ] CI, upgrade documentation, and per-wave verification status are up to date.

## 25. Conclusion

**Upgrading tools and dependencies in dependency order** turns a complex migration into an explainable, verifiable sequence of changes. Rather than asking "should we upgrade the JDK or the framework first?", ask: **which combination is supported, which component is a prerequisite for the next state, and which checks prove that stage succeeded?**

In Java Advance Compatibility Migration, begin with a dependency graph and compatibility matrix, upgrade the tools needed for trustworthy builds and tests, update coordinated framework/dependency lines, and then migrate source, runtime, and deployment across clearly gated waves. With concrete evidence, tracked blockers, and rollback paths at every step, teams control both technical compatibility and operational risk instead of hoping a single massive upgrade succeeds.
