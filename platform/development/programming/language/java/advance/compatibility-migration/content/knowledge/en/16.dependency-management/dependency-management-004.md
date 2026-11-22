# Aligned Version Management Using BOM or Platform

In a Java project with many modules and many libraries, "upgrading a dependency to a new version" is often not as simple as changing a single number. A framework may depend on dozens of modules in the same family; HTTP clients, JSON serializers, logging, observability, and database drivers also have many transitive dependencies. If modules are upgraded independently, the classpath may contain versions that have never been tested together. The typical consequence is that the source still compiles, but at runtime `NoSuchMethodError`, `NoClassDefFoundError`, `ClassCastException`, `ServiceConfigurationError`, or unexpected behavior occurs.

**BOM (Bill of Materials)** in Maven and **platform** in Gradle are mechanisms for declaring a centrally managed set of versions. They help modules select an intentional combination of versions that is easy to upgrade and easy to reproduce. However, a BOM is not a JAR containing all libraries, does not automatically download every dependency, and does not guarantee that every managed version is compatible with the application's JDK, operating system, or production environment.

This lesson presents the principles of version alignment, how to apply a BOM in Maven and a platform in Gradle, version precedence rules, important differences between the two build systems, and the process for verifying the dependency graph when performing **Java Advance Compatibility Migration**.

## 1. The problem to solve: version drift in the dependency graph

### 1.1. Direct dependencies and transitive dependencies

Suppose an application uses three modules:

```text
order-service
├── acme-web-client
│   ├── json-core       2.4
│   └── http-core       5.1
├── acme-data-client
│   ├── json-core       2.2
│   └── metrics-api     1.8
└── acme-security
    ├── http-core       5.0
    └── metrics-api     1.9
```

The numbers above are only hypothetical examples. A project may declare three direct dependencies, yet the runtime graph contains multiple different version requirements for the same module. The build tool must resolve conflicts and select one version on each classpath.

When a library is compiled against `json-core 2.4` but runtime selects `json-core 2.2`, it may call a method that does not yet exist in version 2.2. When a new framework requires `http-core 5.1` but another constraint keeps version 5.0, the error may only appear when a specific request runs.

Two different versions do not always cause an error. However, an untested combination is a **risk that needs verification** and should not be assumed compatible just because the build completes.

### 1.2. Alignment does not necessarily mean "every module has the same version number"

A library family often releases multiple artifacts on the same cadence and aims to use the same release line. However, many BOMs manage artifacts from multiple vendors with different versions:

| Hypothetical artifact | BOM-managed version | Reason |
|---|---|---|
| `acme-core` | `2.7.0` | Belongs to the internal library group |
| `acme-http` | `2.7.0` | Same release line as core |
| `json-databind` | `2.4.3` | Follows the tested JSON suite |
| `metrics-api` | `1.9.2` | Follows the observability stack |
| `jdbc-driver` | `4.6.1` | Follows database/server support |

The versions are illustrative only. The goal of alignment is **a consistent and approved combination of versions**, not forcing every artifact to have the same version string.

### 1.3. Special risks during JDK migration

When upgrading from Java 17 to Java 21, a framework may require a major version upgrade, pulling in many new libraries. If only some artifacts are upgraded, the application may encounter:

- New APIs missing from the selected runtime dependency.
- Bytecode/agent libraries that do not yet understand the class-file major version of the target JDK.
- Annotation processors and runtime libraries out of sync.
- HTTP/JDBC/ORM drivers incompatible with the framework or server.
- Two versions from the same family present together due to shadow/shading or class loaders.
- Libraries using the `javax.*` namespace while the framework has switched to `jakarta.*`.
- APIs passing compilation while runtime provider/service metadata does not match.

A BOM/platform helps manage the **version graph**, but must be combined with a JDK compatibility matrix and runtime tests.

## 2. What is a BOM in Maven actually?

### 2.1. A BOM is a POM with dependencyManagement

A Maven BOM is typically an artifact with `packaging = pom` that defines managed versions in the `<dependencyManagement>` section.

Illustrative BOM example:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.platform</groupId>
    <artifactId>example-dependencies</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-core</artifactId>
                <version>2.7.0</version>
            </dependency>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-http</artifactId>
                <version>2.7.0</version>
            </dependency>
            <dependency>
                <groupId>com.example</groupId>
                <artifactId>example-observation</artifactId>
                <version>1.9.2</version>
            </dependency>
        </dependencies>
    </dependencyManagement>
</project>
```

The coordinates and versions in the example are hypothetical to explain the mechanism. Do not treat them as real packages or as a vendor-verified version set.

A BOM defines **versions and possibly dependency management metadata**; it does not automatically put the three libraries on the application classpath. The consumer still must declare the dependencies it needs to use, or the dependencies appear through transitive relationships.

### 2.2. Importing a BOM into a Maven project

Consumer POM:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example.app</groupId>
    <artifactId>order-service</artifactId>
    <version>1.0.0</version>

    <properties>
        <example.platform.version>1.0.0</example.platform.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>com.example.platform</groupId>
                <artifactId>example-dependencies</artifactId>
                <version>${example.platform.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-core</artifactId>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>example-http</artifactId>
        </dependency>
    </dependencies>
</project>
```

Here Maven knows the versions of `example-core` and `example-http` from the BOM. Direct dependencies do not need to repeat the version declaration.

**Syntax note:** A BOM is imported inside `dependencyManagement` with `type=pom` and `scope=import`. You should not put a BOM as a regular JAR dependency and expect Maven to automatically apply dependency management.

### 2.3. A BOM is not equivalent to a parent POM

A Maven parent POM can manage:

- Plugin versions via `pluginManagement`.
- Build profiles, compiler settings, repositories, and properties.
- Dependency versions via `dependencyManagement`.
- Other shared build configurations.

A BOM usually focuses on **dependency management** and is imported without needing a parent relationship. A Maven project can only have one direct parent, but it can import multiple BOMs. Conflicts between them must be managed.

| Maven mechanism | Primary content | When to use |
|---|---|---|
| `<parent>` | Inherits build configuration and management | Project belongs to a shared build structure |
| BOM import | Imports a dependency version set | Using libraries/frameworks from the same stack |
| `<dependencyManagement>` | Specifies dependency management | Parent/BOM/module manages versions |
| `<dependencies>` | Adds dependencies to the project graph | When code/build requires a library |
| `<pluginManagement>` | Manages plugin versions/config | Controlling compiler/test/package plugins |
| `<build><plugins>` | Enables or configures plugins | When the lifecycle needs a plugin |

Importing a BOM does not automatically import the compiler plugin, test plugin, or JVM flags of a framework parent. When upgrading the JDK, these layers must be reviewed separately.

## 3. Maven: precedence order and dependency mediation

### 3.1. Dependency management and directly declared versions

Suppose the BOM manages:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
    <version>2.7.0</version>
</dependency>
```

The consumer declares it without a version:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
</dependency>
```

Maven uses the managed version. If the consumer declares an explicit version:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>example-core</artifactId>
    <version>2.5.0</version>
</dependency>
```

then this is an intentional change in the consumer's dependency declaration, and you should not assume the BOM will automatically change it back to 2.7.0.

Detailed rules also depend on which level the dependency is at, scope, type/classifier, and the inheritance model. When investigating, **inspect the effective POM and the resolved dependency tree**, rather than inferring from a single XML snippet.

### 3.2. Maven does not resolve versions the same way as Gradle

Maven has a traditional dependency mediation mechanism: when multiple dependency paths require different versions, the rule is commonly described as **nearest definition**; at equal depth, declaration order may be considered. Dependency management in the current POM can determine the version used for transitive dependencies according to Maven's management rules.

Do not treat "BOM-managed version" as a rigid forced-version mechanism in all cases. Direct declarations with explicit versions, management at various levels, and the structure of the dependency graph can make the result differ from expectations.

An illustrative diagram:

```text
order-service
├── client-a
│   └── library-x:1.0
└── client-b
    └── library-x:2.0
```

Without suitable dependency management, Maven applies mediation based on the dependency graph. If the consumer's BOM/management manages `library-x:2.0` and applies to that case, the resolved result can be standardized to version 2.0.

### 3.3. Multiple BOMs managing the same artifact

Suppose a project imports two BOMs and both manage the version of `library-x`. In Maven, import order can determine which version is used for overlapping entries; when imported BOMs manage the same dependency, **the BOM imported earlier usually wins** when no direct management entry overrides it.

Example:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-a</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>platform-b</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

If there is a conflict, the clearest approach is to declare an explicit management entry in the project where adjustment is needed and document the reason. However, this override can break the version matrix tested by the framework, so tests must be run and the decision recorded.

Do not rely on the intuition that "a later BOM import always overrides an earlier BOM" because that is not a generally valid rule for Maven.

### 3.4. Parent inheritance and local management

A child POM can inherit dependency management from a parent. Management entries declared in the child POM can usually override corresponding inherited entries. When a parent, imported BOMs, and local management coexist, inspect the **effective POM** to confirm the outcome.

Inspection commands:

```bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dverbose
```

In some plugin versions, the `dependency:tree -Dverbose` output displays omitted/conflict entries differently. Do not use text output as the sole source of truth: check the plugin version and the actual resolved artifacts when needed.

### 3.5. A BOM does not manage Maven plugins

An often-overlooked point: `dependencyManagement` manages project dependencies, whereas compiler/surefire/failsafe/shade/codegen plugins belong to **plugin resolution and pluginManagement**.

Example:

```xml
<build>
    <pluginManagement>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>${compiler.plugin.version}</version>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>${surefire.plugin.version}</version>
            </plugin>
        </plugins>
    </pluginManagement>
</build>
```

Version properties need to be declared in the parent/project according to build policy. When upgrading Java 17 → 21, a good dependency BOM still cannot rescue an old Maven plugin that does not run on the build JDK.

## 4. What is a Gradle platform?

Gradle has **platform dependencies** to participate in version alignment on the graph. A Gradle platform can come from:

- A Maven BOM imported via `platform("group:artifact:version")`.
- A project using the `java-platform` plugin.
- A platform component with Gradle-specific metadata.

Conceptually, a platform contains **dependency constraints**, rather than automatically downloading all implementation JARs onto the application runtime.

### 4.1. Importing a Maven BOM in Gradle

Groovy DSL example:

```groovy
dependencies {
    implementation platform("com.example.platform:example-dependencies:1.0.0")

    implementation "com.example:example-core"
    implementation "com.example:example-http"

    testImplementation platform(
        "com.example.platform:example-dependencies:1.0.0"
    )
}
```

The versions of the two dependencies are managed by the platform in the corresponding configurations. These are hypothetical artifact illustrations.

Gradle has different resolution strategies and graph semantics from Maven, so importing **the same BOM** does not always guarantee an identical resolved graph to Maven in all cases. You must verify with `dependencies` and `dependencyInsight`.

### 4.2. Kotlin DSL equivalent

```kotlin
dependencies {
    implementation(platform("com.example.platform:example-dependencies:1.0.0"))

    implementation("com.example:example-core")
    implementation("com.example:example-http")

    testImplementation(
        platform("com.example.platform:example-dependencies:1.0.0")
    )
}
```

Whether writing Groovy or Kotlin DSL, the key point is that the platform must participate in the exact configuration where the dependencies are resolved.

### 4.3. Importing a platform does not mean absolute enforcement

In Gradle, a regular platform introduces version constraints into the resolution process. When another dependency requires a higher version, **Gradle conflict resolution may select a different version from the one suggested/managed by the platform** depending on metadata and constraints.

Therefore:

```groovy
implementation platform("com.example.platform:example-dependencies:1.0.0")
```

does not mean every artifact in the BOM is immutably locked at all costs. To know the final version, inspect the graph.

This also helps distinguish "aligning to a version set" from "locking the entire graph exactly". The two goals require different complementary tools.

## 5. Gradle: how do platform and enforcedPlatform differ?

### 5.1. platform: prioritizes compatibility, does not force everything

Example:

```groovy
dependencies {
    implementation platform("com.example.platform:example-dependencies:1.0.0")
    implementation "com.example:example-core"
}
```

This is a reasonable default choice when you want to use version alignment from a BOM in an application or library, and then verify the resolution result. Constraints can have different effects depending on metadata, strictness, and the graph's dependency requests.

### 5.2. enforcedPlatform: a stronger constraint

Gradle provides:

```groovy
dependencies {
    implementation enforcedPlatform(
        "com.example.platform:example-dependencies:1.0.0"
    )
    implementation "com.example:example-core"
}
```

`enforcedPlatform` enforces the platform-managed versions more strongly. It can be useful when an application needs to force a specific combination, but it poses a risk if published to other consumers: enforced constraints can **propagate through the dependency graph** and override the consumer's choices.

Therefore, do not add `enforcedPlatform` to a reusable library simply because the version graph looks wrong. For a library, you should generally prefer `platform` and clearly designed constraints, leaving consumers the necessary decision-making authority.

### 5.3. "Force" does not replace compatibility analysis

A version forced lower than another library's minimum requirement can cause `NoSuchMethodError` at runtime. A version forced higher can also bring breaking changes. Therefore, forcing a version is only justified after checking:

- Why the version conflict appeared.
- Which artifact actually needs a different version.
- Whether a better-suited BOM/framework release exists.
- Compatibility between modules after enforcing.
- Testing on the production runtime.

If you need to choose a version different from the BOM to patch a CVE, record it as a **temporary governed override** with supporting evidence, tests, and a removal deadline.

## 6. Creating an internal java-platform project

When an organization has multiple Java modules sharing a stack, an internal platform helps manage versions in one place.

### 6.1. Multi-project structure

```text
commerce/
├── settings.gradle
├── dependency-platform/
│   └── build.gradle
├── order-service/
│   └── build.gradle
└── payment-service/
    └── build.gradle
```

In `settings.gradle`:

```groovy
rootProject.name = "commerce"

include "dependency-platform"
include "order-service"
include "payment-service"
```

### 6.2. Defining a java-platform project

In `dependency-platform/build.gradle`:

```groovy
plugins {
    id "java-platform"
}

dependencies {
    constraints {
        api "com.example:example-core:2.7.0"
        api "com.example:example-http:2.7.0"
        api "com.example:example-observation:1.9.2"
    }
}
```

With `java-platform`, declarations under `constraints` create version recommendations/constraints for dependency consumers. The coordinates in the example are hypothetical.

In `order-service/build.gradle`:

```groovy
plugins {
    id "java"
}

dependencies {
    implementation platform(project(":dependency-platform"))

    implementation "com.example:example-core"
    implementation "com.example:example-http"
}
```

`payment-service` can also import the same platform project to receive a consistent set of constraints.

### 6.3. A platform can import another platform

An organization may want an internal platform based on a framework BOM and then add versions for internal libraries. With Gradle `java-platform`, you must allow platform dependencies before importing:

```groovy
plugins {
    id "java-platform"
}

javaPlatform {
    allowDependencies()
}

dependencies {
    api platform(
        "com.example.framework:framework-bom:4.0.0"
    )

    constraints {
        api "com.example:internal-client:2.7.0"
    }
}
```

This is a pattern for using a platform dependency inside a platform project. The BOM and versions are illustrative; select the actual framework BOM and check Gradle/plugin compatibility.

You should not simply add a framework JAR into `java-platform` dependencies: the goal is to carry dependency constraints, not turn the platform into a runtime library.

### 6.4. api and runtime constraints

In a platform, constraints can exist across different variants/scopes. If the platform is published to consumers, determine which constraints should apply to API consumers and which constraints relate only to runtime.

Do not assume every dependency constraint is mandatory in every configuration. When testing, resolve the compile and runtime graphs of a real consumer to confirm that the constraints are visible.

### 6.5. Publishing a platform

A Gradle `java-platform` can participate in publication via `maven-publish` when configured appropriately. When doing so, Gradle Module Metadata and the Maven POM representation can carry different information, especially for rich version constraints and variants.

Check both Gradle and Maven consumers if the platform is used across ecosystems. Do not assume all Gradle-specific rich constraints are translated identically into a Maven BOM.

## 7. BOM, version catalog, constraints, and locking: not the same thing

These four mechanisms are used together but solve different problems.

| Mechanism | Primary function | Participates in dependency graph resolution? |
|---|---|---|
| Maven BOM | Provides dependency management | Yes, according to Maven rules |
| Gradle platform | Provides version constraints/alignment | Yes, according to Gradle rules |
| Gradle version catalog | Defines aliases and versions for declarations | Does not force selected versions by itself |
| Gradle dependency constraints | Requests/prefers/constrains specific versions | Yes |
| Gradle dependency locking | Records resolved versions for reproducible builds | Yes, for locked configurations |
| Dependency verification | Verifies artifact checksums/signatures | Not a version-selection mechanism |

### 7.1. A version catalog is a declaration dictionary

Example `gradle/libs.versions.toml`:

```toml
[versions]
example-platform = "1.0.0"

[libraries]
example-bom = { module = "com.example.platform:example-dependencies", version.ref = "example-platform" }
example-core = { module = "com.example:example-core" }
example-http = { module = "com.example:example-http" }
```

In Gradle Groovy DSL:

```groovy
dependencies {
    implementation platform(libs.example.bom)
    implementation libs.example.core
    implementation libs.example.http
}
```

A version catalog helps avoid repeating group/artifact/version across build scripts; it **does not automatically align transitive dependencies**. If you only use versioned aliases without importing a suitable platform/constraints, conflict resolution can still select a different version.

In particular, a version catalog can also declare plugin aliases, but managing **plugin versions** is a separate issue from the runtime BOM.

### 7.2. Dependency locking for reproducing the resolved graph

A BOM can be updated, and Gradle may resolve different versions due to different constraints or changed metadata. Dependency locking records the resolved versions for configurations that have locking enabled.

Groovy DSL example:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

And a task to generate/update lock state:

```bash
./gradlew dependencies --write-locks
```

Use the appropriate Gradle version and task scope to ensure critical configurations are actually resolved and written to the lockfile. Do not treat a single completed command as proof that every runtime/test configuration has lock state. Use the appropriate build/test tasks to resolve the graphs that need locking.

When upgrading a BOM, update the lockfile intentionally, review the diff, and commit it alongside the migration code/config. If only the BOM changes without updating the lock, the build may remain pinned to the old version or report conflicts depending on configuration.

### 7.3. Dependency verification protects artifacts, not alignment

Gradle dependency verification can store checksums and signatures to confirm that artifacts come from expected sources. Maven can also use checksum/repository policies and appropriate supply chain management tools.

An artifact with a valid checksum can still be an **incompatible version** with the framework. Conversely, a matching version whose artifact was tampered with remains a risk. Alignment, locking, and verification are complementary control layers, not substitutes for one another.

## 8. Framework BOMs and managed versions

Many ecosystems provide official BOMs or platforms:

- Spring Boot dependency management BOM.
- BOMs for the Jackson family or Micrometer/Reactor when used within the appropriate stack.
- Several cloud SDKs use BOMs to align multiple modules.
- Netty and library families with multiple synchronously released artifacts.
- JUnit or testing frameworks with multiple modules.
- Internal BOMs for an organization's own SDKs/service clients.

Do not treat example framework names as assertions about the latest versions or current support matrices. When applying in practice, verify the official documentation for the exact version/framework in use.

### 8.1. A framework BOM is the anchor of the stack

A practical rule: if an application is built on a major framework, the framework-recommended BOM is usually the **starting point** for the libraries tested by that framework.

Example of a Spring Boot application using Maven:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>${spring.boot.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Dependencies belonging to the BOM can then be declared without a version if the exact group/artifact/type/classifier is managed by the BOM. If the project uses the framework's parent POM, check whether dependency management is already inherited before importing it again.

Upgrading a framework BOM from one release line to another can change dozens of versions. Therefore, changing a BOM is **a major unit of change**, not just a single number.

### 8.2. When must a BOM version be overridden?

There can be valid reasons:

- A critical CVE already has a patched version, but the current framework BOM has not been updated yet.
- A confirmed regression exists in the BOM-selected version.
- A driver requires a newer version to support the current server/JDK/OS.
- A needed feature only exists in a specific version.

To override in a controlled manner:

1. Record the artifact, the BOM-managed version, and the target version.
2. Explain the source of the risk or requirement, along with documentation.
3. Evaluate dependency compatibility across the entire library family.
4. Run unit/integration/contract tests on the target JDK/runtime.
5. Inspect the final classpath and SBOM.
6. Assign an owner and a review date to remove the override when the official BOM catches up.

Do not upgrade a single module in a tightly coupled multi-artifact family if the vendor requires version alignment.

## 9. Boundary between dependency BOMs and build plugins

### 9.1. Maven

A Maven BOM import in `dependencyManagement` does not set versions for:

- `maven-compiler-plugin`.
- `maven-surefire-plugin` and `maven-failsafe-plugin`.
- `maven-shade-plugin` / `maven-assembly-plugin`.
- Annotation processor plugins or generator plugins.
- Plugin implementation dependencies.

Manage plugins through `pluginManagement`, build plugin configuration, parent POM, and the Maven wrapper according to project policy.

### 9.2. Gradle

A platform added to `implementation`/`runtimeOnly`/`testImplementation` does not automatically update plugin versions in:

```groovy
plugins {
    id "org.example.some-plugin" version "1.2.3"
}
```

Plugin resolution depends on `pluginManagement`, plugin repositories, included builds, and plugin markers. The buildscript classpath and annotation processor classpath also need to be inventoried separately.

If upgrading the JDK prevents a Gradle plugin from running, adding a BOM for runtime dependencies will not fix that error.

### 9.3. Annotation processors and generators

Lombok, MapStruct, QueryDSL, Protobuf, JAXB/XJC, OpenAPI Generator, and other processors/generators may have:

- An API/runtime library.
- A processor or tool artifact.
- A build plugin.
- Separate version compatibility with the compiler/JDK.

A BOM may manage some of those artifacts, but not all of them. Check generated sources, the processor classpath, and plugin versions according to their respective roles.

## 10. A BOM does not replace a JDK compatibility matrix

### 10.1. Class-file version and API level

If an artifact is compiled for Java 21, its class files typically have major version 65. Java 17 only supports up to major version 61 and cannot load version 65 classes.

A BOM can point to a Java 21 artifact without containing any information that forces the build tool to reject it for a Java 17 runtime. A build using JDK 21 may even compile successfully against that artifact; the error only occurs when deploying on JDK 17.

If a library must support Java 17, you need to:

- Verify the minimum supported JDK for each dependency.
- Configure the compiler with `--release 17` for the sources you compile.
- Check the binary dependency class-file level when needed.
- Run the final artifact on Java 17.
- Check new APIs, reflection, bytecode instrumentation, and runtime behavior.

`--release` does not control precompiled bytecode in dependencies. Nor does a BOM automatically control which underlying Java APIs those binaries reference.

### 10.2. Namespaces and framework major versions

A BOM may manage `jakarta.*` libraries while another module still uses a `javax.*` provider. Aligning group/artifact versions does not automatically convert imports, annotations, or generated sources from `javax` to `jakarta`.

When upgrading a framework major version, evaluate **source compatibility, binary compatibility, and runtime integration**, especially for servlet, JPA, validation, JAXB/JAX-WS, or security APIs.

### 10.3. Native libraries and operating systems

JNI drivers, native images, and tooling may depend on the OS, CPU architecture, or libc/base image. A BOM manages versions, but does not prove that native binaries can load in every container. Artifacts must be tested in a representative production environment.

## 11. Reading the dependency graph before and after applying a BOM/platform

### 11.1. Maven commands

```bash
./mvnw -version
./mvnw help:effective-pom
./mvnw dependency:tree
./mvnw dependency:tree -Dverbose
```

In a multi-module build, you can run at the root or target a specific module depending on the Maven/plugin version capabilities. Save the baseline output and the post-change output.

Pay attention to:

- Which dependencies are managed by the BOM.
- Which dependencies have explicit versions in modules.
- Which versions are omitted due to conflicts.
- Different scopes/types/classifiers.
- The test runtime classpath and plugin classpath.
- Where transitive dependencies come from.

### 11.2. Gradle commands

```bash
./gradlew --version
./gradlew projects
./gradlew :app:dependencies --configuration compileClasspath
./gradlew :app:dependencies --configuration runtimeClasspath
./gradlew :app:dependencies --configuration testRuntimeClasspath
./gradlew :app:dependencyInsight --dependency example-core --configuration runtimeClasspath
./gradlew :app:buildEnvironment
```

`dependencyInsight` is especially useful to see why a version was selected, including the selection reason, constraints, and all paths requesting versions. Replace `:app` and `example-core` with the actual module/dependency.

Do not run only on the root project if the dependencies live in subprojects. An application can have a different resolved graph from a shared library within the same multi-project build.

### 11.3. Saving results as evidence

An inventory table could look like:

| Artifact | Requested version | Selected version | Constraint/management source | Configuration | Notes |
|---|---|---|---|---|---|
| `example-core` | No version specified | 2.7.0 | Platform v1 | Runtime | Same release line |
| `example-http` | 2.5.0 from transitive dependency | 2.7.0 | Platform v1 + conflict resolution | Runtime | Needs transport test |
| `example-observation` | 1.8.0 from client | 1.9.2 | Platform v1 | Runtime | Needs metrics test |
| `example-test` | 3.1.0 | 3.1.0 | Test BOM | Test runtime | Separate test scope |

The data in the table is illustrative only; in actual handoffs, include graph output, BOM URLs/release notes, commits, and reviewer sign-off.

## 12. Conflicts between multiple BOMs/platforms

### 12.1. Common scenario

An application needs framework BOM A and SDK BOM B. Both manage the version of an HTTP client or JSON library:

```text
framework-bom-A
  -> json-library: 2.4

sdk-bom-B
  -> json-library: 2.6
```

This is not proof that either BOM is "wrong". Each BOM may have been tested in its own context, and the A+B combination needs to be evaluated.

### 12.2. How to resolve in Maven

1. Check the effective POM to see which management entry wins.
2. Check the dependency tree to see the final version.
3. Read the compatibility matrices of the framework and SDK.
4. If an official release line supports both together, prefer upgrading the BOMs to that combination.
5. Only add a local override when there is a specific reason and thorough testing.
6. Document the BOM import order and any override entries.

### 12.3. How to resolve in Gradle

1. Inspect the resolved graph and `dependencyInsight`.
2. Distinguish between `platform`, `enforcedPlatform`, and rich constraints.
3. Check whether any dependency declares a strict version or a `force` via resolution strategy.
4. Choose a compatible combination and verify with integration tests.
5. If a conflict cannot be resolved, you may need to split modules/class loaders, replace the SDK, or replace the framework.

Do not start by forcing versions everywhere. This hides the root cause of the conflict and easily creates an unsupported graph.

### 12.4. Do not use exclusions as the primary alignment tool

Some projects exclude transitive dependencies via `exclusions` and then add a direct version. Exclusions can be necessary to avoid old dependencies or duplicate providers, but replacing a dependency with another version does not automatically mean it is compatible.

Before excluding, verify:

- Whether the excluded dependency is still used by a runtime library.
- Whether another module pulls that dependency back in.
- How the exclusion affects the compile/test/runtime graphs.
- Whether service provider/resource metadata is lost.
- Whether a more suitable BOM/framework option exists.

## 13. Dependency resolution differs from duplicate JARs on the classpath

Even when a BOM/platform selects a single version in the build graph, the final artifact can still contain duplicate or conflicting classes because:

- The application server supplies its own libraries.
- An uber-JAR/shading packages classes from multiple artifacts.
- A plugin loader uses a separate class loader.
- A Docker image contains JARs outside the build system.
- A vendor JAR embeds unrelocated dependencies.
- An internal library copies classes from another package.

For example, the application's resolved graph selects `json-library 2.6`, but the server has `json-library 2.2` loaded first. A runtime `NoSuchMethodError` can still appear.

When debugging class loading errors, you must know where a class is loaded from and by which class loader. For complex situations, inspect class loading/JVM logs within an appropriate scope and inspect the actual artifact/container.

**A BOM does not replace inspecting the actual production classpath.**

## 14. Version policy for multi-module repositories

### 14.1. One clear source of version management

In multi-module projects, avoid having each module define framework dependency versions on its own. Choose one primary mechanism:

- Centrally managed Maven parent + imported BOM.
- Gradle root convention plugin + shared platform.
- Internally published platform/BOM shared across multiple repositories.
- Overrides permitted according to a review process.

A module may intentionally need a different version, but that requires an explanation and tests. The goal is not to forbid every override, but to eliminate **accidental drift**.

### 14.2. Do not implicitly align plugin versions and runtime versions

You can define version properties or a catalog to reduce duplication, while keeping scopes clear:

- Runtime dependency BOM/platform.
- Build plugin versions.
- Test tool versions.
- Compiler/JDK toolchain.
- Code generator/annotation processor versions.

A "platform version" does not prove that all scopes share the same compatibility requirements.

### 14.3. Projects publishing libraries differ from applications

**Applications** usually control the final runtime graph, so they can choose a relatively tight version set and lock it.

**Reusable libraries** must avoid forcing consumers to adopt all of their internal versions. In Gradle, avoid exposing an enforced `enforcedPlatform` unless there is a very clear reason. In Maven, publish reasonable dependency metadata and test against diverse consumers.

When releasing a library, define minimum supported dependency versions, runtime JDK support, and API surface rather than simply saying "the internal build passes with our BOM".

## 15. Treating a BOM upgrade as a controlled major change

### 15.1. Why read the diff?

Suppose BOM v1 manages 120 artifacts and BOM v2 changes 65 versions. If a team only looks at the BOM version without inspecting underlying changes, it may miss:

- A major bump of a framework library.
- JSON serialization behavior changes.
- ORM mapping or JDBC driver updates.
- TLS/HTTP client behavior changes.
- Bytecode libraries upgraded to support a new JDK.
- Logger/provider API changes.
- Native dependencies appearing or disappearing.
- Vulnerability fixes that carry breaking changes.

Upgrading a BOM must be treated as upgrading a **coordinated set of dependencies**, not a single dependency.

### 15.2. Breaking the process into steps

1. Capture baseline graph, artifacts, JDK, and test results.
2. Determine the target BOM/platform release line and minimum JDK.
3. Diff the before/after resolved graphs and group the changes.
4. Read release notes/migration guides for high-risk components.
5. Update build/plugins/processors if needed.
6. Compile sources and generated sources on the target JDK.
7. Run unit, integration, contract, and smoke tests.
8. Test the final artifact on the target runtime JDK/OS/container.
9. Check performance, memory, startup, and observability.
10. Review SBOM, CVEs, lockfiles, verification metadata, and overrides.
11. Roll out according to policy with stop/rollback thresholds.
12. Finalize the version matrix and evidence.

### 15.3. Avoid upgrading too many variables at once without a baseline

Upgrading the BOM, JDK, Gradle Wrapper, Spring Boot major version, database schema, and deployment image in a single commit makes regression investigation much harder. Changing them together may be necessary due to compatibility constraints, but they should be broken into steps with separate justifications and evidence whenever feasible.

A sensible path is to lock down the build tool/JDK, verify the BOM and dependency stack, and then verify the artifact on the target runtime. The detailed sequence depends on the system; there is no mandatory order for all projects.

## 16. Reproducibility: snapshots, ranges, and dynamic versions

### 16.1. Version ranges and dynamic versions can cause drift

Example:

```groovy
dependencies {
    implementation "com.example:example-core:2.+"
}
```

or a Maven version range in a dependency configuration can allow the selected version to change over time/repository metadata. This makes it hard to reproduce released binaries.

A BOM/platform usually uses fixed release versions, but if direct dependencies or transitive metadata contain dynamic/changing versions, the resolved graph can still change.

A clear policy is needed:

- Restrict dynamic/range dependencies in production.
- Do not use `SNAPSHOT`/changing modules outside intentional environments.
- Use lockfiles/resolved dependency records when appropriate.
- Pin toolchains, build wrappers, and artifact sources.
- Generate an SBOM for the final artifact and store checksums.

### 16.2. Repository provenance and supply chain

A version coordinate is not enough to prove an artifact comes from a trusted source. Manage repository URLs, mirrors, checksums/signatures, publishing permissions, and artifact immutability policies.

If Maven/Gradle resolves the same coordinates from multiple repositories, repository precedence/provenance must be established. If an artifact is modified after publication, builds may not be reproducible even when the version string does not change.

### 16.3. Lockfiles do not exempt vulnerability response

When a CVE needs to be patched, lockfiles help show the exact versions in use, yet you still must update the BOM/platform or apply a controlled override and regenerate the lock state. Do not use "reproducible builds" as an excuse to leave vulnerable dependencies unpatched indefinitely.

## 17. Decision map: choosing BOM or platform?

### 17.1. Maven application

Prefer importing the framework's official BOM in `dependencyManagement`; declare needed dependencies in `dependencies`; manage plugins in parent/`pluginManagement`. If there are multiple BOMs, check collisions and the effective POM.

### 17.2. Maven multi-module/internal ecosystem

You can publish an internal BOM containing a tested version set, and use a separate parent POM for build plugins/conventions. Define BOM versioning, consumer verification, and dependency management override rules.

### 17.3. Gradle application

Use `platform(...)` to consume the official BOM; use `dependencyInsight` to verify resolution. If reproducible versions are needed, combine with dependency locking. Only use `enforcedPlatform(...)` when you understand the enforcement consequences and scope.

### 17.4. Gradle multi-project/internal ecosystem

Use a `java-platform` project or a published platform with constraints. You can import vendor platforms and then add internal constraints. Use a version catalog for clean aliases and managing declared versions, but do not treat the catalog as an alignment engine.

### 17.5. Mixed Maven/Gradle organization

If an organization publishes a Maven BOM for both build systems to consume, run **separate consumer verification for Maven and Gradle**, because resolution semantics differ. If publishing a Gradle `java-platform`, inspect the Maven POM representation and metadata when Maven consumers do not understand Gradle-specific rich constraints.

## 18. End-to-end example: upgrading from Java 17 to Java 21

Suppose a system consists of `order-service` and `payment-service`, using a web framework, JSON library, HTTP client, database driver, and observability stack. The baseline runs on JDK 17; the target is JDK 21.

### 18.1. Before migration

Modules pin versions individually:

```text
order-service:
  web-framework      A
  json-library       B
  http-client        C
  metrics-library    D

payment-service:
  web-framework      A
  json-library       B-1
  http-client        C-1
  metrics-library    D+1
```

Drift develops that may not immediately cause errors, yet makes verification difficult when changing the JDK.

### 18.2. Designing the target BOM/platform

The team selects an official framework release line supporting Java 21, then manages the versions of related libraries in a platform. Each service declares only the dependencies it needs without pinning versions individually unless approved.

With Gradle, `order-service` can import:

```groovy
dependencies {
    implementation platform(project(":dependency-platform"))

    implementation "com.example:web-client"
    implementation "com.example:json-adapter"
    implementation "com.example:metrics-adapter"
}
```

With Maven, the module imports the internal BOM and declares equivalent versionless dependencies.

### 18.3. Verifying actual alignment

The post-migration graph must show:

- The same version selected for every common module per configuration.
- Framework and drivers compatible with each other per the support matrix.
- Compiler plugins, processors, and test agents supporting JDK 21.
- No duplicate/conflicting providers in the packaged artifact.
- Records of any overrides differing from the BOM and why.

### 18.4. Verifying on JDK 21

Run compilation and tests on the new JDK. If the artifact does not need to run on Java 17, it can target Java 21; if it still must support a Java 17 runtime, `--release 17` and testing on both runtimes are required. A BOM does not decide this bytecode/API target policy.

### 18.5. A common real-world error

After upgrading the BOM, the application compiles successfully, but a runtime test reports:

```text
java.lang.NoSuchMethodError:
  'void com.example.json.JsonProcessor.configure(boolean)'
```

Investigation steps:

1. Inspect the stack trace to identify the caller.
2. Check which JSON library version the caller was compiled against.
3. Use the dependency tree/insight to determine the runtime version.
4. Check whether the BOM was imported into the right project/configuration.
5. Check whether there is a direct version pin, strict constraint, enforced platform, or transitive conflict.
6. Verify whether the actual packaged artifact adds duplicate JARs.
7. Choose a supported combination rather than merely forcing a version to silence the error.
8. Run regression tests and update the platform/lock state.

## 19. Common mistakes

| Mistake | Consequence | How to prevent |
|---|---|---|
| Thinking a BOM downloads every dependency automatically | Libraries are missing from compile/runtime classpath | Declare needed dependencies in the project |
| Putting a BOM in `dependencies` as a JAR | Dependency management is not applied as expected | Import using the proper Maven BOM syntax |
| Thinking a BOM manages compiler/test plugins | Build tools/plugins may be incompatible with the JDK | Manage plugin classpath and versions separately |
| Thinking Gradle `platform` always forces versions | Final version may differ from the BOM | Use `dependencyInsight` and inspect constraints |
| Unknowingly using `enforcedPlatform` in a reusable library | Version forcing leaks to consumers | Prefer regular `platform` and inspect publication |
| Thinking a version catalog is a BOM | Transitive dependency drift still occurs | Use catalogs for aliases and platforms for alignment |
| Thinking Maven and Gradle resolve identically | Consumers using the same BOM get different graphs | Inspect the resolved graph for each build system |
| Importing multiple BOMs without checking collisions | Selected versions differ from expectations | Check effective POM/insight and record overrides |
| Pinning many direct versions outside the BOM | Breaks intentional version alignment | Reduce pins and apply governance to exceptions |
| Only testing compilation | Linkage/runtime errors are missed | Run packaged artifact and integration tests |
| Thinking a BOM guarantees JDK support | Dependencies may require a newer JDK than runtime | Check min JDK/bytecode and run runtime tests |
| Using exclusion/force to mask conflicts | Can cause missing classes/providers | Find the root cause and pick a compatible stack |
| Not updating lockfiles after upgrading a BOM | Build does not pick up the right versions or is non-reproducible | Review and regenerate lock state |
| Inspecting only the development classpath | Production/test classpaths have different dependencies | Inspect every critical configuration |

## 20. Records to save when upgrading a BOM/platform

An aligned version management effort should deliver at minimum:

1. **Baseline inventory:** JDK, framework, build tool, dependency graphs, and versions prior to migration.
2. **Platform source:** BOM/platform coordinates, versions, and official documentation links.
3. **Managed version matrix:** critical managed artifacts and the rationale for version choices.
4. **Resolved graphs:** compile/runtime/test/processor configurations of each module.
5. **Conflict report:** BOM collisions, overrides, forces, strict constraints, exclusions, and reasons.
6. **Plugin/tool inventory:** Maven/Gradle Wrapper, compiler/test plugins, and generators.
7. **JDK compatibility evidence:** min runtime JDK, class-file/API target, and provider support.
8. **Verification report:** compile, unit, integration, contract, smoke, and packaged artifact tests.
9. **Supply-chain record:** lockfiles, verification metadata, SBOM/checksums, and CVE review.
10. **Release plan:** rollout, metrics, stop thresholds, rollback, and owners.

### Checklist Before Finalizing

- [ ] Identified one primary BOM/platform as the anchor for the dependency stack.
- [ ] Distinguished BOM, parent POM, version catalog, platform, and lockfile.
- [ ] Imported the BOM/platform with proper syntax and into the right configurations.
- [ ] Confirmed that `dependencyManagement` does not download dependencies automatically.
- [ ] Managed build plugins and generator versions separately.
- [ ] Inspected the effective POM or resolved dependency graph after changes.
- [ ] Resolved all conflicts between overlapping BOMs or platforms.
- [ ] Minimized unintentional direct version pins.
- [ ] Evaluated the impact of `enforcedPlatform` on library consumers.
- [ ] Diffed the before/after graphs and recorded significant version changes.
- [ ] Verified compatibility of frameworks, drivers, providers, and target JDK.
- [ ] Ran tests on the packaged artifact and a production-equivalent runtime.
- [ ] Verified that the classpath/packaged artifact contains no unintended duplicates.
- [ ] Reviewed lockfiles, checksums/signatures/SBOM, and security risks.
- [ ] Recorded overrides, owners, and criteria for removing exceptions.
- [ ] Prepared rollback and updated the version matrix documentation.

**BOMs and platforms do not make a dependency graph inherently compatible; they provide the mechanism for organizations to manage versions according to a verifiable policy.** Maven uses POM dependency management and mediation; Gradle uses platforms/constraints and its own conflict resolution. Combining a single shared source of versions, inspecting actual graphs, testing on the target JDK, and governing exceptions helps reduce version drift, limit linkage errors, and establish a reliable foundation for subsequent Java compatibility migrations.
