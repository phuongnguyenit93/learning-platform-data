# Reconciling Actual Dependencies Using Maven or Gradle Tools

In a Java project, the list of dependencies declared in the build file does not fully reflect the libraries actually present on the classpath when compiling, testing, or running the application. A dependency may be pulled in transitively through a framework; multiple libraries may request the same module yet only one version is selected; and profiles, variants, constraints, and build configurations can cause results to differ across environments.

During a Java migration, you need to know **which dependencies actually resolve, which version is selected, why that version was chosen, and which configuration uses it**. Both Maven and Gradle provide reports answering those questions. This lesson teaches how to use those tools to inventory actual dependencies, trace transitive dependencies, analyze version conflicts, and verify compatibility with the target Java version.

This content belongs to the **Java Advance Compatibility Migration** topic, chapter **Analysis Tools**. The focus is analyzing the resolved graph via Maven or Gradle; editing source code or swapping dependencies should occur only after understanding the findings.

## 1. Why Reconcile Resolved Dependencies?

Suppose the build file directly declares:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web:3.x")
}
~~~

This declaration states only that the application asks for a starter. The starter itself depends on Spring MVC, Spring Core, Jackson, logging, and many other libraries. Those dependencies in turn bring their own dependencies.

The actual graph can be visualized like this:

~~~text
Application
  |
  +-- spring-boot-starter-web
        |
        +-- spring-webmvc
        |     |
        |     +-- spring-web
        |     +-- spring-core
        |
        +-- spring-boot-starter-json
        |     |
        |     +-- jackson-databind
        |     |     +-- jackson-core
        |     |     +-- jackson-annotations
        |     +-- jackson-datatype-*
        |
        +-- spring-boot-starter-tomcat
              |
              +-- tomcat-embed-core
              +-- tomcat-embed-websocket
~~~

This diagram illustrates dependency relationships, not a fixed graph across every Spring Boot version. Actual versions depend on the BOM, plugins, configurations, and other project dependencies.

A library can enter the graph from multiple branches. For example:

~~~text
Application
  |
  +-- library A
  |     +-- commons-io:2.11
  |
  +-- library B
        +-- commons-io:2.15
~~~

The project does not necessarily package both versions. The build tool applies conflict resolution rules to select one version for that module within a given configuration.

This creates distinctions among key concepts:

| Concept | Meaning |
|---|---|
| Declared dependency | Dependency declared directly in the build file or inherited from a parent config |
| Transitive dependency | Dependency requested by another dependency |
| Resolved dependency | Dependency selected by the build system after applying rules and constraints |
| Selected version | Final version chosen for a module in the graph |
| Configuration / scope | Dependency set serving a specific purpose such as compile, runtime, or test |
| Artifact | JAR, POM, or component downloaded and used |
| Dependency constraint | Rule restricting, preferring, or requiring versions |
| Exclusion | Rule removing a transitive dependency from a branch or graph per configuration |

When auditing a migration, the key question is not merely "which libraries does the POM/build.gradle declare?" but "which artifacts does the application's runtime actually receive?".

## 2. Separating Dependency Graphs by Classpath

A Java project typically has multiple classpaths. Never treat a single dependency report as the entire project's dependencies.

### 2.1. Classpaths Usually Requiring Inspection

| Classpath | Purpose | Migration risk |
|---|---|---|
| Compile classpath | Dependencies required to compile main source | APIs or annotations incompatible with compiler/release |
| Runtime classpath | Dependencies required when running the application | Class-loading failures, API or bytecode incompatibilities |
| Test compile classpath | Dependencies to compile tests | Test frameworks or mock libraries lacking new-JDK support |
| Test runtime classpath | Dependencies when running tests | Engines, agents, or test runtimes failing |
| Annotation processor | Tools processing annotations and generating code | Old processors failing under the new compiler |
| Buildscript/plugin classpath | Libraries and plugins powering the build | Build tool or plugins incompatible with the build JDK |
| Custom configuration | Dependencies of specialized tasks or capabilities | Easily missed if inspecting only default compile/runtime |

For example, a dependency might appear solely on the test classpath and never be packaged into the application. Conversely, a library might exist only at runtime because it was declared under a runtime scope/configuration.

In Spring applications, looking only at the compile classpath can miss drivers, logging providers, or libraries loaded at runtime. In a shared library, the test runtime may contain dependencies outside the published artifact's public runtime.

### 2.2. Direct vs Transitive Dependencies

A direct dependency is one the module explicitly declares. A transitive dependency is pulled in by another dependency.

Example:

~~~text
app
  +-- library-a:1.0
  |     +-- common-utils:2.0
  |
  +-- library-b:3.0
        +-- common-utils:2.5
~~~

The application might declare only `library-a` and `library-b`, yet `common-utils` still enters the graph. Upgrading `library-b` can change the selected version of `common-utils` even though the build file never touches a `common-utils` declaration.

This matters especially during Java migrations: a transitive dependency can demand a newer runtime, break APIs, or pull in another library incompatible with the current platform.

### 2.3. The Same Module Can Have Different Graphs

Graphs can vary by:

- Built module.
- Active Maven profiles.
- Resolved Gradle configuration.
- Applied platform or BOM.
- Operating system and CPU architecture.
- Variant attributes.
- JDK version or toolchain.
- Properties, environment variables, or init scripts.
- Dependency locks and resolution rules.

Therefore, when sharing a report, state the module, configuration/scope, profiles, and exact command executed. Local reports do not necessarily match CI or production if resolution inputs differ.

## 3. Reconciling Dependencies With Maven

Maven provides the Dependency plugin to view the dependency tree, analyze used dependencies, and inspect resolved artifacts. The Help plugin displays the effective POM after inheritance and profile application.

### 3.1. Viewing the Dependency Tree With `dependency:tree`

Run from the module directory containing `pom.xml`:

~~~bash
./mvnw dependency:tree
~~~

If the project lacks a Maven Wrapper, invoke `mvn` using your installed Maven version.

On Windows, the equivalent command is typically:

~~~powershell
.\mvnw.cmd dependency:tree
~~~

Illustrative output:

~~~text
com.example:orders-service:jar:1.0.0
+- org.springframework.boot:spring-boot-starter-web:jar:3.x:compile
|  +- org.springframework:spring-webmvc:jar:6.x:compile
|  |  +- org.springframework:spring-web:jar:6.x:compile
|  |  \- org.springframework:spring-context:jar:6.x:compile
|  \- com.fasterxml.jackson.core:jackson-databind:jar:2.x:compile
|     +- com.fasterxml.jackson.core:jackson-annotations:jar:2.x:compile
|     \- com.fasterxml.jackson.core:jackson-core:jar:2.x:compile
\- org.postgresql:postgresql:jar:42.x:runtime
~~~

The `x` numbers are placeholders for illustration. Read exact versions from your analyzed project's report.

A line typically displays:

~~~text
groupId:artifactId:type:version:scope
~~~

Example:

~~~text
org.postgresql:postgresql:jar:42.x:runtime
~~~

This means the artifact belongs to group `org.postgresql`, artifact `postgresql`, packaged as a JAR, with a resolved version and `runtime` scope in the Maven graph.

Tree symbols:

- `+-` marks a branch followed by sibling dependencies.
- `\-` marks the last branch at the current level.
- `|` shows a continuing parent branch.
- Deeper indented lines are transitive dependencies of the line above.

### 3.2. Showing Conflict-Omitted Branches

By default, the tree may focus on selected dependencies. Add `-Dverbose` to display extra details about omitted or conflicting nodes:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Illustrative output:

~~~text
com.example:orders-service:jar:1.0.0
+- com.example:client-a:jar:1.0:compile
|  \- com.example:common-utils:jar:2.0:compile
\- com.example:client-b:jar:1.0:compile
   \- (com.example:common-utils:jar:2.5:compile
       - omitted for conflict with 2.0)
~~~

In this hypothetical example, Maven selects `common-utils:2.0` due to Maven mediation rules. Dependency `2.5` is marked omitted due to conflict.

Do not misread `omitted for conflict` as proof the omitted version does not exist in the repository. It simply indicates that node was not selected in the current graph.

### 3.3. Filtering Dependencies Under Investigation

For large graphs, filter by `groupId` or `artifactId`:

~~~bash
./mvnw dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
~~~

You can also filter by scope:

~~~bash
./mvnw dependency:tree -Dscope=runtime
~~~

Or combine them to focus on a library group in the runtime graph:

~~~bash
./mvnw dependency:tree -Dverbose -Dscope=runtime -Dincludes=com.fasterxml.jackson.core:*
~~~

Filters cut noise when investigating a specific dependency. To understand the full path from root dependencies to the selected library, re-run the full tree or inspect related branches; filtered output can omit context from other branches.

### 3.4. Inspecting Effective POM and `dependencyManagement`

The `pom.xml` in the repository is rarely the final POM Maven uses. A POM can inherit from a parent, import BOMs, interpolate properties, and activate profiles.

Generate the effective POM:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Add verbose output to include origin details if your Maven Help Plugin version supports it:

~~~bash
./mvnw help:effective-pom -Dverbose
~~~

The effective POM answers:

- Which dependencies are inherited from the parent?
- What version properties are being substituted?
- Which BOMs are imported?
- Which versions does `dependencyManagement` govern?
- Which profiles add or alter dependencies?
- Which plugins are configured at the parent level?

Distinguish `dependencyManagement` from `dependencies`:

- `dependencies` adds dependencies into the project's graph.
- `dependencyManagement` manages default versions, scopes, or configurations when a dependency is declared; on its own, it does not necessarily place anything on the classpath.
- A BOM imported inside `dependencyManagement` supplies a coordinated set of managed versions for related dependencies.

If `dependency:tree` shows a version different from what appears in one POM file, inspect the effective POM and resolved graph to find why.

### 3.5. Checking Active Profiles

Maven profiles can activate based on properties, JDK version, OS, file presence, or `settings.xml`.

View active profiles:

~~~bash
./mvnw help:active-profiles
~~~

If the project requires a specific profile, run reports under those same profile conditions:

~~~bash
./mvnw -Pproduction dependency:tree
~~~

A dependency report from the default profile does not prove the production graph is identical. When comparing against CI, pass the exact `-P`, `-D`, and appropriate settings.

### 3.6. Analyzing Declared Yet Apparently Unused Dependencies

The Maven Dependency Plugin provides the `dependency:analyze` goal:

~~~bash
./mvnw dependency:analyze
~~~

This goal inspects compiled bytecode to surface cases such as:

- Declared dependencies with no detected direct usage.
- Classes directly used whose dependency is undeclared.
- Dependencies used indirectly through other classes.

Output may report:

~~~text
Used undeclared dependencies found
Unused declared dependencies found
~~~

These are signals to investigate, not an automatic command to delete dependencies. Static analysis can miss:

- Reflection and dynamically constructed class names.
- `ServiceLoader` and SPIs.
- Annotations processed at runtime or compile time.
- Frameworks performing classpath scanning.
- Resources loaded by name.
- Dependencies used only in a specific profile or special code path.
- Dependencies required in a library's public API for consumers to compile.

Before removing a dependency, verify how the application uses it at runtime, in tests, and in deployment environments.

### 3.7. Reviewing Maven Scopes

Maven scopes determine which classpaths include a dependency and whether it propagates to consumers.

| Scope | Compile | Test | Application runtime | Transitively exposed to consumers |
|---|---:|---:|---:|---:|
| compile | Yes | Yes | Yes | Yes |
| provided | Yes | Yes | Not on standard runtime classpath | No |
| runtime | Not used for main compile | Yes | Yes | Yes |
| test | No | Yes | No | No |
| system | Yes | Yes | Should not rely on as normal dependency | No |
| import | Used in dependencyManagement for BOM | — | — | Manages versions, not a runtime artifact |

`provided` scope is commonly used when the deployment environment supplies the API or implementation. If switching runtimes or application servers, confirm the new platform actually provides that dependency.

`runtime` scope may be absent from the compile classpath yet essential when running. Inspecting only the compile graph can miss runtime failures.

### 3.8. Version Selection Rules in Maven

Maven applies dependency mediation to pick one version when the same dependency coordinates appear multiple times. The standard rule is **nearest definition**: the version found closest to the project in tree depth usually wins; at equal depth, declaration order can decide the outcome.

Example:

~~~text
app
  +-- library-a
  |     +-- shared-api:1.4
  |
  +-- library-b
        +-- shared-api:2.0
~~~

When two versions sit at equal depth, branch ordering in the POM can decide the selected version. Declaring a version directly in the project typically overrides deeper transitive versions.

Do not assume Maven always chooses the highest version. To control versions, use `dependencyManagement` or direct declarations, while verifying binary/API compatibility of the forced version.

## 4. Reconciling Dependencies With Gradle

Gradle provides the `dependencies` task to inspect the dependency tree and `dependencyInsight` to trace why a specific version was chosen. Both operate per configuration, so specify the exact module and classpath to inspect.

### 4.1. Viewing the Dependency Tree

From the project root:

~~~bash
./gradlew dependencies
~~~

For multi-module builds, target a module:

~~~bash
./gradlew :orders-service:dependencies
~~~

To view the runtime classpath:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

To view the compile classpath:

~~~bash
./gradlew :orders-service:dependencies --configuration compileClasspath
~~~

On Windows, use the wrapper batch script:

~~~powershell
.\gradlew.bat :orders-service:dependencies --configuration runtimeClasspath
~~~

Illustrative output:

~~~text
runtimeClasspath - Runtime classpath of source set 'main'.
+--- org.springframework.boot:spring-boot-starter-web:3.x
|    +--- org.springframework:spring-webmvc:6.x
|    |    +--- org.springframework:spring-web:6.x
|    |    \--- org.springframework:spring-context:6.x
|    \--- org.springframework.boot:spring-boot-starter-json:3.x
|         \--- com.fasterxml.jackson.core:jackson-databind:2.x
|              +--- com.fasterxml.jackson.core:jackson-annotations:2.x
|              \--- com.fasterxml.jackson.core:jackson-core:2.x
\--- org.postgresql:postgresql:42.x
~~~

Configuration names can differ across Java applications, Android, Kotlin, framework plugins, or custom configurations. If `runtimeClasspath` does not exist, list available configurations in the project and pick the resolvable one.

### 4.2. Checking Key Configurations

Common configurations in the Java plugin:

~~~bash
./gradlew :orders-service:dependencies --configuration compileClasspath
./gradlew :orders-service:dependencies --configuration runtimeClasspath
./gradlew :orders-service:dependencies --configuration testCompileClasspath
./gradlew :orders-service:dependencies --configuration testRuntimeClasspath
./gradlew :orders-service:dependencies --configuration annotationProcessor
~~~

Purposes:

- `compileClasspath`: libraries needed to compile main code.
- `runtimeClasspath`: libraries needed when running the application.
- `testCompileClasspath`: libraries needed to compile tests.
- `testRuntimeClasspath`: libraries needed when running tests.
- `annotationProcessor`: processors used during compilation.

Not every project has all of these configurations. Other plugins can add custom configurations such as integration tests, code generation, migration, or native image.

### 4.3. Tracing a Dependency With `dependencyInsight`

When a dependency resolves to an unexpected version, run:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

You can match exact coordinates:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency com.fasterxml.jackson.core:jackson-databind --configuration runtimeClasspath
~~~

This report answers:

- Which branches request the dependency?
- Which versions are requested directly or transitively?
- Which version was ultimately selected?
- Why did Gradle choose that version?
- Did any constraints, platforms, or resolution rules apply?

Illustrative output may contain:

~~~text
com.fasterxml.jackson.core:jackson-databind:2.x
  Selection reasons:
    - By conflict resolution: between versions 2.a and 2.b
    - By constraint
~~~

`Selection reasons` lines are critical. They distinguish versions chosen via conflict resolution, constraints, rules, or another dependency in the graph.

### 4.4. Reading Symbols in Gradle Reports

In the dependency tree, Gradle may show:

| Symbol or label | Common meaning |
|---|---|
| `+---` | A dependency branch |
| `\---` | Final branch at the current level |
| `(*)` | Branch already shown elsewhere, not expanded redundantly |
| `->` | Requested version was replaced by the selected version |
| `FAILED` | Dependency or configuration failed to resolve |
| `Selection reasons` | Reasons Gradle chose a component/version |

Example:

~~~text
+--- com.example:client-a:1.0
|    \--- com.example:shared-api:1.4
\--- com.example:client-b:1.0
     \--- com.example:shared-api:2.0 -> 2.3
~~~

This shows one branch requested `shared-api:2.0`, yet the selected version in the graph is `2.3`. Run `dependencyInsight` to find the branches, constraints, or rules behind that change.

### 4.5. Checking Buildscript Dependencies

Gradle builds have dependencies serving the build itself, such as plugins or libraries declared in `buildscript`.

Inspect the buildscript classpath with:

~~~bash
./gradlew :orders-service:buildEnvironment
~~~

This report helps when plugins or buildscript libraries conflict. However, do not treat it as the complete list of all plugins resolved via the Plugins DSL. The Plugins DSL also involves `pluginManagement` in settings, plugin markers, and other resolution config. When investigating plugins, also read `settings.gradle`/`settings.gradle.kts`, `plugins` blocks, version catalogs, and init scripts if any.

This is a critical migration boundary: the application might run on the new JDK while Gradle or a plugin fails even to launch on that JDK.

## 5. Understanding Gradle Resolution Rules

Gradle resolves dependencies using components, versions, constraints, variants, and attributes. The outcome is not always simply picking the highest version.

### 5.1. Conflict Resolution

For modules sharing coordinates, Gradle defaults to picking the higher version in ordinary version conflicts. However, constraints, platforms, strict versions, resolution rules, and other mechanisms can alter the choice.

Example:

~~~text
app
  +-- library-a
  |     +-- shared-api:1.4
  |
  +-- library-b
        +-- shared-api:2.0

Resolved:
  shared-api:2.0
~~~

Verify actual outcomes with `dependencyInsight` instead of guessing from a diagram.

### 5.2. Constraints and Version Catalogs

Version catalogs provide aliases and versions for centralized declaration management. Example:

~~~toml
[versions]
jackson = "2.x"

[libraries]
jackson-databind = {
    module = "com.fasterxml.jackson.core:jackson-databind",
    version.ref = "jackson"
}
~~~

Catalogs reduce repetitive declarations yet are not always what decides the final version. Dependencies can still be influenced by platforms, constraints, or rules elsewhere.

Gradle supports version constraints and directives such as:

- `strictly`: tightly bounds allowed version ranges.
- `prefer`: prefers a version absent stronger constraints.
- `require`: requires a version or range.
- `reject`: forbids specific versions.
- `because`: documents the rationale for a constraint.

When `dependencyInsight` prints `By constraint`, search for constraints in build scripts, platforms, version catalogs, or dependency-management plugins.

### 5.3. Platforms and BOMs

A platform can coordinate versions across related libraries. Example:

~~~groovy
dependencies {
    implementation(platform("com.example:example-bom:1.0"))
    implementation("com.example:library-a")
    implementation("com.example:library-b")
}
~~~

BOMs/Platforms help modules within an ecosystem use a version set tested together. When upgrading a framework, usually upgrade the platform or BOM per vendor guidance rather than forcing individual child dependencies to latest versions independently.

Gradle distinguishes `platform()` from `enforcedPlatform()`:

- `platform()` imports dependency constraints from the platform.
- `enforcedPlatform()` enforces platform versions far more strictly over matching dependencies.

Using an enforced platform can affect library consumers if constraints propagate outward. Use it only intentionally with full understanding of graph impact.

### 5.4. Variant Selection and Attributes

Gradle selects not only versions, but also component variants using attributes. Examples:

- Usage: compile vs runtime.
- Category: library, platform, or documentation.
- Target JVM version.
- Operating system or architecture in native-supporting plugins.
- Plugin-defined custom attributes.

A single module can publish multiple variants. Gradle selects the variant matching the consumer's requirements.

During Java migration, the `org.gradle.jvm.version` attribute can drive JVM-level variant selection. If a producer publishes only variants requiring a newer JVM than the consumer targets, resolution may fail reporting no compatible variant found.

When hitting variant errors, do not inspect only version strings. Read the full attribute mismatch diagnostics and consumer/producer requirements.

### 5.5. Exclusions and `force`

Gradle supports excluding transitive dependencies or forcing versions. Example:

~~~groovy
dependencies {
    implementation("com.example:library-a:1.0") {
        exclude group: "com.example", module: "legacy-api"
    }
}
~~~

Or:

~~~groovy
configurations.configureEach {
    resolutionStrategy.force("com.example:shared-api:2.3")
}
~~~

These techniques can resolve an immediate conflict, yet can also produce graphs incompatible with dependencies expecting another version. When forcing a version, verify binary/API compatibility and test every flow exercising that dependency.

Exclusions can silently drop a library needed by dynamic framework loading or service loaders. Exclude a dependency only after understanding why it entered the graph and how the application uses it.

## 6. Comparing Maven and Gradle Results

Do not expect both tools to always print identical-looking graphs. Maven and Gradle use different resolution models, scopes/configurations, and variants.

| Item to compare | Maven | Gradle |
|---|---|---|
| View graph | `dependency:tree` | `dependencies` |
| Trace one dependency | Filter `dependency:tree`, verbose mode | `dependencyInsight` |
| View effective config | `help:effective-pom` | Inspect build scripts, convention plugins, catalogs, platforms, and attributes |
| View active profiles/configs | `help:active-profiles` | Inspect tasks/configurations, properties, and plugin logic |
| Build dependencies | Plugins/dependencies in POM and build extensions | `buildEnvironment`, plugins DSL, and settings |
| Declared vs used analysis | `dependency:analyze` | Separate analysis plugins or bytecode/tooling inspection |
| Version locking | `dependencyManagement`, explicit versions, and artifact control process | Dependency locking |
| Artifact verification | Repositories, checksums/signatures, and supporting plugins | Dependency verification |

When a module builds with both Maven and Gradle, the two graphs can diverge due to:

- One side missing a declared dependency.
- Maven scopes mapping differently than Gradle configurations.
- Out-of-sync BOMs/platforms or version catalogs.
- Exclusions or force rules present on only one side.
- Differing Maven profiles vs Gradle properties.
- Variant metadata used by Gradle without an identical mechanism in Maven.
- Different repositories or resolution timestamps.
- One side using dependency locks while the other resolves dynamically.

Always compare matching purposes: compile vs compile, runtime vs runtime, test vs test. Comparing a Maven runtime graph against Gradle `compileClasspath` leads to wrong conclusions.

## 7. From Dependency Graph to Java Compatibility

Dependency reports identify resolved modules and versions, yet rarely answer on their own what minimum Java version a dependency supports. Assessing a migration requires combining multiple evidence sources.

### 7.1. Identify Which Dependencies Affect Runtime

Start from the runtime classpath of the deployable application or module. Classify:

- Direct dependencies.
- Transitive dependencies.
- Test-only dependencies.
- Build-only dependencies.
- Container/application-server-provided dependencies.
- Dynamically loaded or config-driven dependencies.

Not every dependency in a build is packaged into the artifact. Understand your application's packaging and classloader layout.

For example, a WAR app may mark libraries `provided` because the application server supplies them. A fat JAR app bundles most runtime dependencies. Both deployment styles require different verification.

### 7.2. Inspect Artifact Metadata and Documentation

For critical dependencies, check:

- Documented minimum JDK requirements.
- Release notes and compatibility matrices.
- Maven POM metadata or Gradle Module Metadata.
- Supported framework versions.
- OS, native library, or agent requirements.
- Known issues on the target JDK.

In Gradle, metadata can expose variants and target JVM attributes. In Maven, POMs provide dependency metadata and project info, though not every library explicitly declares its Java baseline.

When documentation is unclear, inspect the actual artifact and test it in the target environment.

### 7.3. Inspect JAR Bytecode

Use `javap` to examine a class file:

~~~bash
javap -verbose -classpath library.jar com.example.SomeClass
~~~

Look for the `major version` to determine that class's class-file version. Key milestones:

| Java | Class file major version |
|---|---:|
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |
| Java 25 | 69 |

If a class has a major version higher than the target runtime supports, the older runtime cannot load it normally.

However, checking one class does not prove the entire JAR is compatible. A JAR can contain classes compiled across different releases, especially Multi-Release JARs. Inspect multiple representative classes or scan the entire artifact.

### 7.4. Use `jdeps` to Analyze Dependencies and Internal APIs

The JDK includes `jdeps` to inspect class/package-level dependencies and detect certain internal API usages:

~~~bash
jdeps --jdk-internals library.jar
~~~

Specify the target release when analyzing Multi-Release JARs:

~~~bash
jdeps --multi-release 21 --jdk-internals library.jar
~~~

`jdeps` helps detect references to JDK internal APIs or package dependencies. It does not replace vendor compatibility matrices nor prove accurate runtime behavior. Dynamic calls via reflection or configuration may escape static analysis.

### 7.5. Distinguish Bytecode Version From Java API Baseline

A JAR containing Java 17 class files can still call an API introduced only in Java 21 if the build failed to constrain APIs properly. Conversely, a library can be compiled with a newer JDK while targeting an older release.

Therefore, combine:

1. Vendor metadata and documentation.
2. Target release/variant metadata.
3. Actual bytecode.
4. Java APIs referenced by the library.
5. Testing on the target runtime.

Never rely solely on the class-file major version to conclude an entire dependency runs on a JDK.

## 8. Investigating a Problematic Dependency: Practical Example

Suppose after upgrading a framework, the application hits errors around a JSON library. Build reports show multiple branches requesting different Jackson versions.

### 8.1. With Maven

Inspect the full tree and conflict nodes:

~~~bash
./mvnw dependency:tree -Dverbose
~~~

Filter the Jackson group:

~~~bash
./mvnw dependency:tree -Dverbose -Dincludes=com.fasterxml.jackson.core:*
~~~

Inspect the effective POM:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
~~~

Check active profiles:

~~~bash
./mvnw help:active-profiles
~~~

Then trace:

- Which framework/BOM manages Jackson?
- Which direct dependency specifies its own version?
- Does a transitive library pull a different version?
- Does a production profile change versions or scopes?
- Are all Jackson modules aligned to the same release?

Do not fix `jackson-databind` alone while ignoring `jackson-core` and `jackson-annotations` if the ecosystem requires them aligned.

### 8.2. With Gradle

Inspect the runtime graph:

~~~bash
./gradlew :orders-service:dependencies --configuration runtimeClasspath
~~~

Trace the problematic module:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Repeat for related modules if needed:

~~~bash
./gradlew :orders-service:dependencyInsight --dependency jackson-core --configuration runtimeClasspath
~~~

Inspect:

- Versions requested per branch.
- Final selected version.
- Selection reasons.
- Influencing platforms or constraints.
- Any `force` or resolution rules.
- Whether the selected variant matches the JVM target.

### 8.3. Applying an Evidence-Based Fix

Common fixes include:

- Upgrading the framework BOM/platform to obtain a co-tested dependency set.
- Removing duplicate explicit versions where versions are centrally managed.
- Replacing a direct dependency if it pulls an unmaintained legacy branch.
- Replacing unmaintained libraries.
- Adding a well-documented constraint when holding a compatible version.
- Excluding a dependency only after confirming that branch is unnecessary and an alternative implementation exists.
- Upgrading the framework or application server if the dependency is platform-bound.

After fixing, re-run the exact dependency report commands to verify the new graph. Then build and test on the target JDK. A cleaner graph report alone does not prove the application works properly.

## 9. Managing Reproducibility of Dependency Resolution

Dependency graphs can shift over time if a project uses dynamic versions, SNAPSHOTs, mutable repositories, or lacks dependency locking.

### 9.1. Dynamic Versions

Declarations such as:

~~~groovy
implementation("com.example:library:+")
~~~

or:

~~~xml
<version>[2.0,)</version>
~~~

can resolve to different versions on future builds depending on repository metadata and resolution timing. This makes migration results hard to reproduce.

In production builds, prefer explicit versions, controlled BOMs/platforms, or appropriate locking mechanisms.

### 9.2. Gradle Dependency Locking

Gradle supports dependency locking to record resolved versions. Enable locking in the project, e.g.:

~~~groovy
dependencyLocking {
    lockAllConfigurations()
}
~~~

Then write lock state when running the appropriate resolution task:

~~~bash
./gradlew dependencies --write-locks
~~~

Lock files keep subsequent builds using the locked versions across managed configurations. When intentionally upgrading dependencies, update lock files and review the diff as part of the migration.

Locking does not guarantee repository artifacts weren't swapped. Pair it with dependency verification to check checksums or signatures of downloaded artifacts.

### 9.3. Version Management With Maven

Maven typically relies on:

- Explicit versions for dependencies.
- Parent POMs and BOMs in `dependencyManagement`.
- Maven Enforcer Plugin to enforce dependency rules.
- Governed repositories.
- Pinned build plugin versions.
- CI archiving of effective POMs and dependency trees when auditing is needed.

For instance, Maven Enforcer can enforce `dependencyConvergence` to flag branches requesting mismatched versions. This rule detects divergence, though it does not automatically prove which version suits the application.

### 9.4. Repositories and Checksums

Identical dependency coordinates can yield different metadata or artifacts if the build permits untrusted repositories or mutable artifacts.

For critical builds:

- Use managed repositories.
- Restrict SNAPSHOTs and dynamic versions in release builds.
- Verify checksums or signatures where feasible.
- Record repository and dependency metadata.
- Keep caches/build environments consistent when reproducibility is required.
- Never treat local cache as the sole source of truth.

## 10. Integrating Dependency Analysis Into CI

Do not run dependency reports only when a migration fails. Put checks in the pipeline to catch graph changes early.

A pipeline can perform:

~~~text
Checkout source
     |
     v
Resolve dependencies
     |
     v
Generate dependency reports
     |
     +--> Compile classpath
     |
     +--> Runtime classpath
     |
     +--> Test classpath
     |
     v
Check dependency policy
     |
     +--> Version conflict
     +--> Unsupported/blocked dependency
     +--> Dynamic version policy
     +--> Vulnerability scan
     |
     v
Build and tests on target JDK
     |
     v
Publish reports and artifact metadata
~~~

Archive reports by commit or build number so before- and after-migration states can be compared.

Track:

- Added or removed direct dependencies.
- Newly appearing transitive dependencies.
- Changes in selected versions.
- Dependencies moving between compile and runtime.
- BOM/platform changes.
- Dependencies requiring a higher minimum Java version.
- Artifacts with bytecode release exceeding the baseline.
- Vulnerable or EOL dependencies.

### 10.1. Before-and-After Migration Comparison

Generate two sets of reports:

~~~text
baseline/
  compile-dependencies.txt
  runtime-dependencies.txt
  test-dependencies.txt
  effective-pom.xml        # Maven
  dependency-locks/        # Gradle, if using locking

target/
  compile-dependencies.txt
  runtime-dependencies.txt
  test-dependencies.txt
  effective-pom.xml
  dependency-locks/
~~~

Diff to uncover meaningful shifts, then trace every critical dependency with the right tool.

Not every graph shift is an error. A new dependency may be a valid requirement of a new framework. What matters is identifying intentional changes, evaluating impact, and preserving evidence.

### 10.2. Policy Enforcement Instead of Passive Archiving

If an organization enforces Java baselines, add policy checks:

- Disallow runtime dependencies with bytecode exceeding the supported release.
- Disallow dynamic versions in release builds.
- Disallow specific blocked dependencies.
- Disallow dependencies with vulnerabilities above policy thresholds.
- Require framework versions within the supported matrix.
- Require shared modules to align on the agreed runtime baseline.

Policies must match real needs. Rigid rules produce false positives if they fail to distinguish test-only, build-only, `provided`, and runtime dependencies.

## 11. Limits to Keep in Mind When Reading Dependency Reports

### Reports Do Not Show Every Dynamically Loaded Dependency

Applications can load plugins, drivers, or modules by class name at runtime. Such components do not necessarily appear in the static dependency graph.

### Dependency Graphs Do Not Prove API Compatibility

A library can resolve cleanly yet still call APIs removed or absent on the target runtime. Bytecode inspection, API checks, and tests remain necessary.

### Resolved Does Not Always Mean Packaged

`provided` dependencies, container libraries, compile-only dependencies, and custom packaging may omit resolved items from the final artifact. Inspect the actual packaging output.

### Transitive Dependencies Can Shift Via Platforms

BOMs, constraints, version catalogs, and profiles can alter selected versions without editing direct module declarations.

### One Configuration Report Does Not Represent All

The runtime graph differs from the test graph; the compile graph differs from the annotation processor graph. Inspect the configurations relevant to your goal.

### Static Dependency Analysis Can Misreport Usage

Reflection, service loaders, framework scanning, and resource-based loading can prevent tools from seeing a dependency is actively used.

### Local Output Can Differ From CI

JDKs, properties, profiles, repositories, init scripts, lock states, and caches can differ. When investigating migrations, capture the exact command, environment, and commit behind each report.

## 12. Dependency Reconciliation Checklist for a Java Migration

Before signing off on a migration, confirm:

- [ ] Identified the exact modules requiring analysis.
- [ ] Recorded commit, JDK, build tool, and build flags.
- [ ] Inspected both compile classpath and runtime classpath.
- [ ] Inspected test classpath and annotation processors where relevant.
- [ ] Checked direct and transitive dependencies.
- [ ] Traced dependencies whose versions shifted or conflicted.
- [ ] Inspected Maven effective POM/profiles or Gradle constraints/platforms/variants.
- [ ] Checked build dependencies and plugins.
- [ ] Verified Java baselines of critical libraries.
- [ ] Inspected bytecode/APIs of high-risk artifacts.
- [ ] Accounted for native libraries, agents, and dynamically loaded dependencies.
- [ ] Checked dynamic versions, SNAPSHOTs, locks, and repository policies.
- [ ] Re-ran reports after making changes.
- [ ] Built and tested on the target runtime.
- [ ] Archived before/after reports for review.

## 13. Dependency Report Template for Migration

Save a concise record using a template:

~~~text
PROJECT
  Module:
  Commit:
  Build tool and version:
  Build JVM:
  Target JDK:
  Compiler release:

RESOLUTION CONTEXT
  Maven profiles / Gradle properties:
  Module:
  Configuration or scope:
  Repository:
  Lock state:

DEPENDENCY FINDINGS
  Direct dependencies:
  Important transitive dependencies:
  Version conflicts:
  Selected versions and reasons:
  BOM / platform / constraints:
  Exclusions / force rules:
  Build plugins and processors:

JAVA COMPATIBILITY
  Required Java baseline:
  Bytecode major versions:
  Internal JDK API usage:
  Native libraries and agents:
  Vendor support evidence:

MIGRATION IMPACT
  Dependencies to upgrade:
  Dependencies to replace/remove:
  Compatibility blockers:
  Unverified components:
  Required tests:

VALIDATION
  Dependency report before:
  Dependency report after:
  Build result:
  Runtime test result:
  Security scan:
  Rollback plan:
~~~

A strong report lets reviewers trace from a problematic dependency back to the branch introducing it, version selection rules, Java compatibility evidence, and remediation decisions.

## 14. Key Takeaways

When reconciling dependencies with Maven or Gradle, answer four questions:

1. **What is in the graph?** Check the right module and configuration/scope, including transitive dependencies.
2. **Why is it there?** Trace dependency branches, BOMs/platforms, constraints, profiles, variants, and rules.
3. **Which version is used?** Verify the selected version and selection reason rather than trusting only what is written in declaration files.
4. **Will it run on the target?** Combine support documentation, metadata, bytecode, API analysis, and target-runtime testing.

Maven and Gradle supply evidence about the resolved graph. Migration engineers must interpret that evidence in application context: which dependencies belong to runtime, which serve only build/test, which versions were overridden, and which libraries might block the target Java release.

Once actual dependencies and version selection reasons are clear, the team can execute migrations on solid evidence, avoid arbitrary bumps or forced versions, and leave reproducible before/after reports ready for review.
