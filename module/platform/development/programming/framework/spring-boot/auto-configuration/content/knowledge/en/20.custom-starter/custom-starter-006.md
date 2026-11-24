# Distinguishing Dependencies Published to Users from Compile-Only Dependencies

**Topic:** Spring Boot Auto Configuration  
**Context:** Custom Starter  
**Goal:** When developing a Java library, auto-configuration module, or starter, determine which dependencies must travel with the artifact to consuming applications, which are needed only during compilation/testing of the current module, and how to publish that choice accurately in Maven or Gradle.

## 1. Two Different Questions When Declaring Dependencies

A dependency may be needed by the source code of the module being built, yet does not necessarily belong on the classpath of every application using that module.

For example, the `acme-json-autoconfigure` library has an adapter using Jackson:

```java
public interface JsonCodec {
    String encode(Map<String, ?> value);
}
```

Internal implementation:

```java
final class JacksonJsonCodec implements JsonCodec {

    private final ObjectMapper objectMapper = new ObjectMapper();

    @Override
    public String encode(Map<String, ?> value) {
        try {
            return this.objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException ex) {
            throw new IllegalArgumentException("Cannot encode JSON", ex);
        }
    }
}
```

The application only uses the `JsonCodec` contract. It does not need to compile its own source code against `ObjectMapper` unless it uses Jackson directly. Yet when the Jackson branch actually activates, Jackson still must be present at runtime.

Therefore we must distinguish:

1. **Dependencies needed for the module itself:** the current module's compiler, tests, or runtime need that library to build/run code.
2. **Dependencies to publish to consumers:** does an application depending on the module's artifact need that library on its own compile classpath or runtime classpath?

The answer depends on whether the dependency appears in the public API or is used solely inside the implementation, and whether the dependency is needed at runtime.

## 2. What Does a “Published” Dependency Mean?

When publishing a Java library to a Maven repository or a Maven-compatible repository, the artifact usually consists of:

- A JAR containing the module's own classes/resources.
- A POM describing artifact coordinates, dependencies, scopes, optionality, and build info.
- With Gradle Module Metadata, an additional `.module` file describing variants and dependencies per classpath.

A normal JAR **does not bundle all dependencies inside itself**. The application's build tool reads published metadata to resolve the dependency graph, download required artifacts, and construct compile/runtime classpaths.

Example:

```text
Consumer application
    |
    +---- acme-json-starter
                |
                +---- acme-json-autoconfigure
                |          |
                |          +---- acme-core
                |          +---- Jackson (optional in this module)
                |
                +---- Jackson (runtime dependency of the starter)
```

Here the auto-configuration module can compile against Jackson without forcing all direct consumers of that module to receive Jackson. The starter for the JSON feature proactively adds Jackson into the application's runtime graph.

**A published dependency does not mean the dependency is embedded inside the JAR.** These are two different mechanisms:

- Dependency metadata controls how build tools download libraries onto the classpath.
- Shaded/uber JARs or Spring Boot executable JARs package dependencies in specialized ways for distribution/execution.

## 3. Choosing Scopes in Maven

Maven has common scopes: `compile`, `provided`, `runtime`, `test`, `system`, and `import`. The scope determines which classpaths a dependency appears on and how it propagates through the dependency graph.

| Scope | Module compile classpath | Module runtime classpath | Test classpath | Propagated to consumers |
| --- | --- | --- | --- | --- |
| `compile` (default) | Yes | Yes | Yes | Yes |
| `provided` | Yes | No | Yes | No |
| `runtime` | No | Yes | Yes | Yes, at runtime |
| `test` | No | No | Yes | No |
| `system` | Yes | Yes | Yes | Not via normal repository mechanism; requires local path |
| `import` | Not a normal classpath dependency | No | No | Used only to import dependency management from a BOM in `dependencyManagement` |

`system` is rarely appropriate in modern projects because it depends on JAR paths on a specific machine. Use repositories and regular dependencies instead.

### 3.1. `compile`: Public Dependency by Default

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-core</artifactId>
    <version>1.0.0</version>
</dependency>
```

Omitting scope means `compile`. The current module uses the dependency at compile and runtime; consumers also receive it along the dependency graph.

Use when:

- The library's public API includes types from the dependency.
- Consumers need to compile against those types.
- The dependency is a mandatory part of using the artifact.
- The library genuinely needs the dependency at runtime and wants it propagated.

Do not let an internally-used-only dependency become a public compile dependency unnecessarily; it enlarges the classpath and coupling of every consumer.

### 3.2. `runtime`: Needed at Runtime, Not to Compile Module Sources

```xml
<dependency>
    <groupId>org.postgresql</groupId>
    <artifactId>postgresql</artifactId>
    <scope>runtime</scope>
</dependency>
```

A JDBC driver is usually a fitting example: application code may only use `DataSource`/JDBC APIs without importing specific driver classes, yet the driver must be present when connecting to the database.

Consumers receive this dependency on their runtime classpath, not on their compile classpath merely because a runtime dependency was propagated.

If module source code directly imports `org.postgresql.Driver`, `runtime` scope will be insufficient to compile those sources; in that case, revisit the design or scope. Do not choose a scope merely by the label “driver”—choose based on the actual classpath needed.

### 3.3. `provided`: Module Needs Compile/Test, Runtime Supplied by Environment

```xml
<dependency>
    <groupId>jakarta.servlet</groupId>
    <artifactId>jakarta.servlet-api</artifactId>
    <scope>provided</scope>
</dependency>
```

`provided` states that the dependency is needed during compile/test yet is expected to be supplied by the container or platform at runtime. Maven does not propagate this dependency as a regular dependency to consumers.

A common example is the Servlet API when an application is deployed inside a servlet container that already provides that API.

**Do not use `provided` merely to “reduce dependencies”** if the actual runtime lacks the library. If consumers run standalone without a container supplying the API, they may hit `ClassNotFoundException`/`NoClassDefFoundError`.

### 3.4. `test`: Only for Module Tests

```xml
<dependency>
    <groupId>org.junit.jupiter</groupId>
    <artifactId>junit-jupiter</artifactId>
    <scope>test</scope>
</dependency>
```

JUnit, Mockito, Testcontainers, or fixtures used only in `src/test` belong in `test`. They must not become runtime dependencies of applications just because the library has unit tests.

### 3.5. `optional=true`: Do Not Propagate Dependency, Still Used in Current Module

For example, an auto-configuration module needs Jackson to compile and when the Jackson branch runs:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Without an explicit scope, the scope remains `compile`. Inside the `acme-json-autoconfigure` module itself, Jackson is present on compile, runtime, and test classpaths per that scope.

The difference lies in consumers: a project depending solely on `acme-json-autoconfigure` **does not automatically receive** Jackson as a transitive dependency. If a consumer wants to enable the Jackson adapter, it must add Jackson itself or depend on a starter that intentionally supplies it.

`optional=true` does not mean:

- The library is not needed in the current module's runtime.
- Maven skips downloading the dependency when building the current module.
- The dependency is stripped from the current module's JAR/metadata.
- The dependency is loaded automatically if missing from the classpath.
- The dependency can be referenced safely in every class signature regardless of conditions.

This is the single most important distinction: **optional controls transitivity; scope controls the module's classpath.**

### 3.6. `dependencyManagement` Does Not Add Dependencies to the Classpath

A BOM is typically imported as follows:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

A BOM manages versions/scopes/exclusions for dependencies declared elsewhere. Merely listing an artifact in `dependencyManagement` **does not** cause that artifact to be downloaded or added to the classpath. You still must declare it under `<dependencies>` if the module actually needs it.

## 4. Choosing Configurations in Gradle `java-library`

Gradle distinguishes dependencies meant for the public API from dependencies meant solely for implementation. For a Java library, use the `java-library` plugin rather than treating all dependencies as a single flat list.

| Configuration | Current module | Consumer compile classpath | Consumer runtime classpath | Meaning |
| --- | --- | --- | --- | --- |
| `api` | Compile + runtime | Yes | Yes | Dependency required by the API and published |
| `implementation` | Compile + runtime | No | Yes | Internal dependency, still needed when consumer runs |
| `compileOnly` | Compile, no runtime | No | No | Needed only to compile the current module |
| `compileOnlyApi` | Compile, no runtime | Yes | No | Consumer needs types at compile time; runtime supplied elsewhere |
| `runtimeOnly` | Runtime, no compile | No | Yes | Dependency needed only at runtime |
| `testImplementation` | Test compile/runtime | No | No | Dependency for tests only |
| `testRuntimeOnly` | Test runtime | No | No | Dependency for running tests only |
| `annotationProcessor` | Compile/code generation | No | No | Processor used during build, not a consumer runtime dependency |

Test configurations are separated; the table focuses on publication semantics. An `implementation` dependency is omitted from the consumer's compile classpath, yet still propagated at runtime so the library functions. This is why `implementation` fits most internal dependencies.

### 4.1. `api`: Dependency Types Appear in the Public API

```kotlin
plugins {
    `java-library`
}

dependencies {
    api("com.acme:acme-core:1.0.0")
}
```

Use `api` when consumers need the dependency on their compile classpath to compile against the library's public surface.

For example, a public method returns `com.acme.core.Result`, a public constructor takes `com.acme.core.Request`, or a public class extends a superclass from the dependency. Consumers need to see those types during compilation.

`api` also includes a runtime dependency. If the dependency is not needed at runtime (for instance, already provided or shaded under a clear contract), consider `compileOnlyApi`.

### 4.2. `implementation`: Module Compile and Runtime, Consumer Runtime Only

```kotlin
dependencies {
    implementation("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

Use when module sources need Jackson yet the public API does not expose `ObjectMapper` or Jackson types to consumers. The dependency is still supplied in the application's runtime so the implementation works, without coupling the consumer's compile classpath directly to Jackson.

This is the right choice for mandatory internal dependencies of a library, not “compile-only” dependencies.

### 4.3. `compileOnly`: Present Only on the Module's Compile Classpath

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

`compileOnly` fits when a dependency is needed only by the compiler and must not enter runtime or regular publications. Lombok is also typically declared in `annotationProcessor` to run its annotation processor.

For libraries whose runtime code actually invokes a class from the dependency, do **not** place the dependency exclusively in `compileOnly` unless runtime provision of that class is guaranteed (e.g., by the platform/container or separate packaging/shading). Otherwise, consumers may compile successfully yet fail at runtime.

### 4.4. `compileOnlyApi`: Types Needed for Consumer Compilation, Runtime Provided Elsewhere

```kotlin
dependencies {
    compileOnlyApi("jakarta.servlet:jakarta.servlet-api:6.1.0")
}
```

Use when a dependency's type appears in the public API so consumers need it to compile, yet the dependency is not provided by the library at runtime because another platform is responsible for it.

This is a narrow case. If consumers also need the library at runtime, use `api` instead of `compileOnlyApi`.

### 4.5. `runtimeOnly`: Consumers Need It at Runtime, Not Compile Time

```kotlin
dependencies {
    runtimeOnly("org.postgresql:postgresql:42.7.5")
}
```

Suited for JDBC drivers when code only uses standard JDBC APIs and does not directly import driver classes. Gradle places the dependency onto the module's runtime classpath and publishes it to consumers in the runtime variant.

### 4.6. `annotationProcessor` and Dependencies for Code Generation

```kotlin
dependencies {
    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor:3.3.13")
}
```

Annotation processors participate in the build to generate metadata/code. They are not dependencies applications need to run the library's beans or services. Placing processors in a dedicated configuration avoids accidentally pulling build tools into the runtime graph.

## 5. Maven `optional` Is Not Equivalent to Gradle `compileOnly`

These two mechanisms are frequently confused because both can prevent consumers from receiving a dependency normally. However, they answer two different questions:

| Declaration | Current module compile? | Current module runtime? | Consumer automatically receives dependency? |
| --- | --- | --- | --- |
| Maven `compile` | Yes | Yes | Yes, compile/runtime |
| Maven `compile` + `optional=true` | Yes | Yes | Not automatically received |
| Maven `provided` | Yes | No | No |
| Gradle `implementation` | Yes | Yes | Runtime, not compile |
| Gradle `compileOnly` | Yes | No | No |
| Gradle `api` | Yes | Yes | Compile and runtime |
| Gradle `runtimeOnly` | No | Yes | Runtime |

Consider the same Jackson library:

- Maven `optional=true` with the default scope still puts Jackson on the **autoconfigure module's** runtime classpath. Only consumers do not receive it automatically.
- Gradle `compileOnly` puts Jackson on the **autoconfigure module's** compile classpath, yet omits it from the module's runtime classpath unless added separately (e.g., `testRuntimeOnly`) or provided by a starter module.
- Gradle `implementation` includes Jackson at both compile and runtime for the module, while consumers receive Jackson only at runtime.
- Gradle `api` exposes Jackson at both compile and runtime for consumers.

Therefore, when migrating a build from Maven to Gradle, do not mechanically translate `<optional>true</optional>` into `compileOnly`. Determine separately: does the module need the dependency at runtime, do consumers need to compile against those types, and who is responsible for providing the runtime dependency.

## 6. Designing Modules for a Custom Starter With an Optional Adapter

An understandable structure:

```text
acme/
├── acme-core/
│   └── Public API (independent of Jackson)
├── acme-json-autoconfigure/
│   └── Auto-configuration and optional Jackson adapter
├── acme-json-starter/
│   └── Starter proactively providing default JSON adapter
└── consumer-app/
    └── Application using the starter
```

### 6.1. Module `acme-core`

Public API does not reference Jackson:

```java
package com.acme.core;

import java.util.Map;

public interface JsonCodec {
    String encode(Map<String, ?> value);
}
```

Because consumers can compile against `JsonCodec` without needing Jackson, core does not need to publish a Jackson dependency.

### 6.2. Module `acme-json-autoconfigure` in Maven

Abbreviated POM:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-core</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

In this module, Jackson is used to compile the implementation and can run tests/adapter branches. Yet applications depending solely on `acme-json-autoconfigure` will not automatically receive Jackson. To use the Jackson adapter, the application must declare the dependency or use a starter responsible for supplying it.

If `JsonCodec` is part of the autoconfigure module's public API and depends on `acme-core`, the `acme-core` dependency must be published appropriately so consumers compile against `JsonCodec`.

### 6.3. Module `acme-json-starter` in Maven

A starter dedicated to the JSON feature can proactively publish Jackson:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-json-autoconfigure</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
```

Because the starter declares Jackson in `runtime` scope non-optionally, consumers receive Jackson on their runtime classpath. Consumers do not receive Jackson on their compile classpath just because the starter has a runtime dependency; if the application wants to write code importing `ObjectMapper`, declare Jackson directly in compile scope in the application.

In a real product, the starter may choose `compile` scope if it wants an API using Jackson to be published for consumer compilation. Choose according to the starter's contract, not merely “adding dependencies just to be safe”.

### 6.4. Module `acme-json-autoconfigure` in Gradle

```kotlin
plugins {
    `java-library`
    `maven-publish`
}

dependencies {
    api("com.acme:acme-core:1.0.0")
    implementation("org.springframework.boot:spring-boot-autoconfigure:3.3.13")

    compileOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")
    testRuntimeOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")

    testImplementation("org.springframework.boot:spring-boot-starter-test:3.3.13")
}
```

Here Jackson is a compile-only dependency of the module. `testRuntimeOnly` adds Jackson to test the optional branch when present. A consumer using only the autoconfigure module must provide Jackson at runtime itself if it wants to activate the adapter.

If the module's implementation needs Jackson at runtime in all cases when consumers use autoconfigure, and the dependency should propagate to consumer runtime without compile visibility, consider `implementation` instead of `compileOnly`. Choose the configuration based on the adapter's actual distribution model.

### 6.5. Starter Module in Gradle

```kotlin
plugins {
    `java-library`
}

dependencies {
    api(project(":acme-json-autoconfigure"))
    runtimeOnly("com.fasterxml.jackson.core:jackson-databind:2.17.2")
}
```

This starter brings auto-configuration into the consumer's API/runtime graph and adds Jackson to the runtime variant. If the starter wants consumers to compile directly against Jackson, switch to `api` (or declare the dependency directly in the consumer as needed).

The same library can have multiple starters with different dependency choices: a basic starter pulling no adapters, `json-starter` pulling Jackson, `xml-starter` pulling an XML provider. This split gives users explicit feature selection and avoids classpath bloat.

## 7. The Public API Determines Which Dependencies Need Publishing

You cannot pick `api` or `implementation` just by looking at imports at the top of a file. You must inspect whether a dependency's types appear in **public/protected signatures and contracts that consumers need to compile against**.

Example:

```java
public interface ReportClient {
    com.vendor.api.Report fetch(String id);
}
```

Consumers compiling code that calls `fetch` need to see `com.vendor.api.Report`. The dependency containing this type must be on the consumer's compile classpath.

With Gradle:

- Use `api` if consumers need the dependency at both compile time and runtime.
- Use `compileOnlyApi` only when consumers need to compile against that type while runtime is supplied by a separate source.

With Maven, non-optional `compile` dependencies are normally propagated. Maven has no general equivalent to `compileOnly`. If a public signature needs a type at runtime, do not mark the dependency optional and expect every consumer to find the library on its own.

Conversely:

```java
public interface ReportClient {
    String fetchJson(String id);
}
```

If the internal implementation uses `com.vendor.api.Client` without exposing that type in the API, consumers do not need to compile against the vendor client. You can use Gradle `implementation`; in Maven, use a dependency matching the runtime/transitivity and optionality policy of the adapter.

### 7.1. Inheritance, Annotations, and Generics Are Also API

A dependency does not only “leak” when appearing in a return type. It can become required when a public class:

- `extends` a superclass from the dependency.
- `implements` an interface from the dependency.
- Has a public constructor/field/method parameter or return type using the dependency.
- Has generic bounds or public annotations that the consumer's compiler needs to process.
- Requires the dependency's processor/plugin to generate sources that the consumer must compile.

Verify the public surface with the compiler and real consumer tests. Do not just grep for import strings.

## 8. Dependencies Dedicated to Build and Test

Some dependencies only serve artifact creation:

| Purpose | Maven | Gradle |
| --- | --- | --- |
| JUnit/Mockito | `scope=test` | `testImplementation` |
| Test runtime DB/driver | `scope=test` or `runtime` suitable for tests | `testRuntimeOnly` |
| Annotation processor | `maven-compiler-plugin` / `annotationProcessorPaths` | `annotationProcessor` |
| Compile-only API | No general equivalent scope; use `provided` if environment supplies runtime and non-transitivity is understood | `compileOnlyApi` |
| Compile-only implementation | No direct equivalent scope; consider `provided` per runtime contract | `compileOnly` |
| Runtime-only dependency | `runtime` | `runtimeOnly` |

Maven `provided` and Gradle `compileOnly` share similarities in keeping dependencies off the module's runtime classpath, yet should not be treated as exact equivalents across all publication and transitive resolution scenarios. Inspect actual producer and consumer classpaths before switching build tools.

### 8.1. Annotation Processors Are Not Runtime Dependencies

Gradle example:

```kotlin
dependencies {
    compileOnly("org.projectlombok:lombok:1.18.36")
    annotationProcessor("org.projectlombok:lombok:1.18.36")
}
```

Maven Compiler Plugin can declare processors in `annotationProcessorPaths`. Processors run during the build and do not need to enter the application's runtime graph merely because they generated code during compilation.

Similarly, the Spring Boot configuration processor generates configuration metadata for IDEs. Applications consuming the starter do not need the configuration processor at runtime to read `@ConfigurationProperties`.

## 9. Exclusion, Optional, and Dependency Management Are Not the Same

Three mechanisms often conflated:

**Optional** published by an upstream library: “consumers are not required to receive this dependency; if needed, declare it explicitly”.

**Exclusion** requested by a consumer or dependency declaration: “remove this specific transitive dependency from this branch of the dependency graph”.

Maven example:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-json-starter</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
        </exclusion>
    </exclusions>
</dependency>
```

An exclusion only removes the dependency from that dependency branch. Another artifact in the graph can still bring Jackson back. If the starter needs Jackson for its default branch to function, an exclusion can cause conditions not to match or trigger runtime errors; use it only when you know which adapter will replace it.

**Dependency management/BOM** manages shared versions and metadata; it does not automatically add dependencies to the classpath. A project can import a BOM yet still must declare the artifacts it needs in `<dependencies>`.

## 10. Distinguishing Dependency Metadata from Fat JARs and Spring Boot Executable JARs

Suppose a POM declares a `runtime` dependency. Maven resolution adds it to the application's runtime classpath; the dependency does not necessarily get copied into a normal library JAR.

A regular library JAR:

```text
acme-json-autoconfigure.jar
    com/acme/json/JsonCodec.class
    com/acme/json/autoconfigure/JsonAutoConfiguration.class
```

Dependencies are downloaded separately from repositories according to POM/metadata.

A Spring Boot executable JAR can contain nested library dependencies inside:

```text
application.jar
├── BOOT-INF/classes/
│   └── com/example/Application.class
└── BOOT-INF/lib/
    ├── acme-json-autoconfigure-1.0.0.jar
    ├── jackson-databind-2.17.2.jar
    └── spring-core-....jar
```

This is a packaging mechanism for running applications. It does not change the meaning of `api`, `implementation`, `optional`, or `compileOnly` during dependency resolution. If using shading/relocation, you must additionally manage class packaging and licenses/resources; do not treat shading as an invisible substitute for the dependency contract.

## 11. Inspecting Actual Dependencies of Producer and Consumer

Do not just read `POM`/`build.gradle` and guess. Check both sides.

### 11.1. Maven

Inspect the module's dependency tree:

```bash
mvn dependency:tree
```

Filter a specific dependency:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
```

Inspect the effective POM:

```bash
mvn help:effective-pom
```

In the consumer project, run `dependency:tree` to confirm whether the dependency appears and whether the effective scope is right. Compare:

- A consumer depending directly on `acme-json-autoconfigure`.
- A consumer depending on `acme-json-starter`.

Expected result: Jackson does not automatically propagate from the autoconfigure module if that dependency is marked optional; the JSON starter can add Jackson at runtime/compile per the starter's contract.

### 11.2. Gradle

Inspect compile classpath:

```bash
./gradlew :acme-json-autoconfigure:dependencies --configuration compileClasspath
```

Inspect runtime classpath:

```bash
./gradlew :acme-json-autoconfigure:dependencies --configuration runtimeClasspath
```

Inspect consumer runtime:

```bash
./gradlew :consumer-app:dependencies --configuration runtimeClasspath
```

Find the source bringing a dependency into the graph:

```bash
./gradlew :consumer-app:dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

These commands help distinguish dependencies arriving from `api`, `implementation`, `runtimeOnly`, platform/BOM, or another transitive branch.

### 11.3. Inspecting Published Artifacts

With Maven, open the POM in the repository or the POM installed to the local repository; verify `scope` and `optional`.

With Gradle, inspect both the POM and Gradle Module Metadata (`.module`) if publishing generated both. Gradle Module Metadata can express compile/runtime variants of a Java Library in greater detail than a POM. Consumers using Maven rely primarily on the POM; consumers using Gradle can use Gradle metadata when available.

A test inside the source module is not enough to verify dependency publication. Maintain an independent consumer sample depending on artifacts published to a local/staging repository, then run compilation and tests with the exact classpath a real user sees.

## 12. Quick Selection Matrix

| Situation | Typical Maven choice | Typical Gradle `java-library` choice |
| --- | --- | --- |
| Dependency appears in public API, needed at compile + runtime | `compile` (default), non-optional | `api` |
| Internal-only dependency, yet needed at compile + runtime | `compile` | `implementation` |
| Dependency needed only at runtime, e.g., JDBC driver | `runtime` | `runtimeOnly` |
| Dependency needed for compile/test, runtime provided by container | `provided` | `compileOnly`, or `compileOnlyApi` if consumer compilation needs the type |
| Optional dependency of an adapter, not auto-propagated to consumers | `optional=true` with matching scope | `compileOnly` if adapter needs compile only; or design separate runtime/starter if runtime is needed |
| Test-only dependency | `test` | `testImplementation` / `testRuntimeOnly` |
| Annotation processor | Compiler plugin processor path | `annotationProcessor` |
| Centralized version management | BOM in `dependencyManagement` | `platform(...)` / version catalog / constraints |

This table is a starting point, not a one-to-one mapping between the two build tools. Maven scope and optionality are two properties; Gradle configurations describe variants/classpaths. Choose based on the public API and runtime contract.

## 13. Common Mistakes

**Mistake 1 — Marking a Maven dependency optional because you do not want consumers to compile against it.**  
`optional=true` prevents transitivity, yet the dependency may still be needed in the module's own runtime. If only compile time is needed, check the runtime contract and packaging/provision mechanism; Maven has no general equivalent to `compileOnly`.

**Mistake 2 — Using Gradle `compileOnly` for a library that the implementation calls at runtime.**  
Consumers compile successfully yet can fail with `NoClassDefFoundError` when running. Add the runtime dependency via a starter/consumer or switch to the appropriate configuration.

**Mistake 3 — Exposing implementation details in public signatures while declaring `implementation`.**  
Consumers may fail to compile because the required type is absent from the compile classpath. Use `api` or redesign the API to hide implementation types.

**Mistake 4 — Using `api` for all dependencies.**  
Consumer compile classpaths bloat, compilation depends on unnecessary libraries, increasing coupling and version conflict risk. Prefer `implementation` for internal dependencies in Gradle.

**Mistake 5 — Using `provided` without a container supplying it at runtime.**  
Application startup fails due to missing classes. `provided` is a promise about the environment, not a free way to drop a dependency.

**Mistake 6 — Assuming a BOM already adds the dependency.**  
`dependencyManagement`/platform manages versions; you still must declare the actual dependency in the project.

**Mistake 7 — Checking only the library module's dependency tree.**  
You must inspect the consumer after publishing, because optionality, scopes, and variants determine how dependencies propagate.

**Mistake 8 — Thinking dependency metadata means the JAR already contains the library.**  
POM/Gradle metadata only describes the dependency graph. Fat JARs, shaded JARs, and Spring Boot executable JARs are separate packaging strategies.

**Mistake 9 — Putting tests/annotation processors into runtime.**  
Separate test configurations and processor paths so consuming artifacts do not receive build-only tools.

**Mistake 10 — Forgetting that public APIs can inherit external types.**  
Even without fields or methods returning that type, superclasses/interfaces/generic bounds can still force consumers to need the dependency at compile time.

## 14. Checklist Before Publishing a Starter/Library

1. List dependencies directly used by production sources; do not rely on accidental transitive dependencies.
2. Mark which types appear in public/protected APIs, annotations, superclasses, generics, and extension points.
3. Determine whether each dependency is needed at compile time, runtime, test, or annotation processing.
4. For Maven, verify scope and `optional` separately; do not use optional in place of runtime scope.
5. For Gradle, distinguish `api`, `implementation`, `compileOnly`, `compileOnlyApi`, and `runtimeOnly`.
6. For optional adapters, ensure dependency publication matches class conditions and auto-configuration structure.
7. Create a dedicated starter if an adapter needs to be offered as a default choice.
8. Inspect POM/Gradle Module Metadata after publishing.
9. Run an independent consumer sample, inspect compile/runtime classpaths, and start both with and without optional dependencies.
10. Ensure test libraries and annotation processors are not published as runtime dependencies.

## 15. Self-Check Questions

**Question 1.** A Maven module uses Jackson for both internal compile and runtime, yet consumers only use an interface independent of Jackson. How do you prevent consumers from automatically receiving Jackson?  
**Answer:** Declare the dependency with the appropriate module scope and `optional=true`. Within the module itself, Jackson remains on the classpath per scope; consumers do not receive it transitively.

**Question 2.** Does Maven `optional=true` mean the dependency is only on the compile classpath?  
**Answer:** No. Optional controls propagation; scope controls the current module's classpath.

**Question 3.** A Gradle library has a public method returning `com.vendor.Result` and consumers need that type at compile/runtime. What should be declared?  
**Answer:** `api("com.vendor:library:...")`.

**Question 4.** A Gradle implementation uses a logging library yet the public API never mentions its types. What should be used?  
**Answer:** Typically `implementation`, because consumers need the dependency at runtime yet do not need it on their compile classpath just to compile against the library's API.

**Question 5.** A JDBC driver is not imported in source code yet must be present when connecting. Which scope is usually appropriate?  
**Answer:** Maven `runtime`, Gradle `runtimeOnly`.

**Question 6.** The Servlet API is provided by the container at runtime; a module needs to compile against the API without packaging/propagating it as a runtime dependency. What can be used?  
**Answer:** Maven `provided`; Gradle `compileOnly` or `compileOnlyApi` depending on whether the type appears in the consumer-facing API.

**Question 7.** Why is `compileOnly` not a mechanical replacement for Maven `optional=true`?  
**Answer:** `compileOnly` removes the dependency from the producer's runtime classpath; Maven optional does not do that—it only stops the dependency from propagating to consumers.

**Question 8.** An artifact appears in `dependencyManagement` yet does not appear in the dependency tree. Is Maven broken?  
**Answer:** No. `dependencyManagement` only manages versions/configuration; the project still must declare the artifact in `dependencies`.

**Question 9.** Why should an independent consumer be tested after publishing?  
**Answer:** Because published dependency metadata, optionality, and variants govern the consumer's classpath; internal tests may accidentally have enough dependencies and mask publication errors.

## 16. Principles to Remember

- Dependencies needed by the producer and dependencies published to consumers are two independent questions.
- Maven scope controls classpaths; `optional=true` controls whether a dependency propagates.
- Maven optional is not equivalent to Gradle `compileOnly`.
- Gradle `api` is for public APIs; `implementation` is for internals; `compileOnly` does not provide runtime; `runtimeOnly` is for runtime only.
- Public signatures, inheritance, annotations, and generic types determine whether consumers need a dependency on their compile classpath.
- A starter can publish an optional adapter by proactively adding runtime/compile dependencies per its contract.
- POM and Gradle Module Metadata describe the dependency graph; they do not embed libraries into the JAR.
- Always inspect the dependency tree and an independent consumer sample before releasing.

### Official References

- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven — POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven — Maven Dependencies](https://maven.apache.org/repositories/dependencies.html)
- [Gradle — The Java Library Plugin](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle — Building Java Projects](https://docs.gradle.org/current/userguide/building_java_projects.html)
