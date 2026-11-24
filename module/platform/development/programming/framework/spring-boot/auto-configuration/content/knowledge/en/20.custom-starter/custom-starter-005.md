# optional in Maven and compileOnly, api, implementation in Gradle When Building a Custom Starter

## 1. Why Dependency Scope Matters for a Custom Starter

A Spring Boot starter usually bundles auto-configuration and the libraries needed so users only have to add a single dependency. However, not every dependency that the starter module uses must appear in every application that consumes it.

For example, the Acme library has a client and a Spring Boot integration module. The auto-configuration part can compile against Acme's API, yet only needs to activate when the application actually puts the Acme Client onto the classpath. If a starter always pulls every integration into the application, users receive extra libraries even when they do not use that feature, bloating the classpath and risking version conflicts.

Maven and Gradle solve this with different mechanisms:

- **Maven `optional`**: the dependency is still used in the current module according to its declared scope, but is not automatically propagated to projects depending on that module.
- **Gradle `compileOnly`**: the dependency is only on the declaring module's compile classpath; it is absent from the module's runtime classpath and is not propagated to consumers.
- **Gradle `api`**: the dependency belongs to the library's public API and is propagated to consumers at both compile time and runtime.
- **Gradle `implementation`**: the dependency is used to compile and run the current module, and is propagated to consumers at runtime without appearing on the consumer's compile classpath.

These are not different names for the same concept. `optional` is a flag controlling dependency transitivity in Maven; `compileOnly`, `api`, and `implementation` are configurations in the Gradle Java Library Plugin with distinct classpath semantics.

This lesson focuses on designing a starter with auto-configuration and one or more optional integration features, while ensuring consumers receive the right libraries at compile time and runtime.

## 2. Two Module Layers Commonly Found in a Custom Starter

Spring Boot describes a common two-module structure:

```text
acme-spring-boot-autoconfigure
    - @AutoConfiguration
    - @ConfigurationProperties
    - @ConditionalOnClass / @ConditionalOnMissingBean
    - callbacks/customizers for the Acme library
    - integration dependency may be optional

acme-spring-boot-starter
    - usually a nearly empty JAR
    - depends on acme-spring-boot-autoconfigure
    - declares libraries needed for the default experience
    - provides a single dependency for the application
```

**The autoconfigure module** contains code that knows how to wire Spring Boot to an external library. It can be consumed directly by an application that wants to choose dependencies itself or package its own starter. Thus, the Acme library dependency in this module is often marked optional/compile-only if the feature should only operate when Acme is present.

**The starter module** is a convenient, opinionated selection of commonly needed dependencies. When an application adds the starter, this module directly declares the libraries that the default experience requires. Non-optional dependencies in the starter module will be propagated to the application via the respective dependency management mechanism.

Splitting into two modules is not mandatory. For a small integration with no optional features and always-needed dependencies, auto-configuration and starter can be combined. When there are multiple flavors or optional integrations, separating modules makes boundaries clearer.

### 2.1. Example of an Optional Integration

Suppose a library has these artifacts:

| Artifact | Responsibility |
| --- | --- |
| `acme-client` | Client API and implementation |
| `acme-spring-boot-autoconfigure` | Auto-configuration, properties, and Spring adapters |
| `acme-spring-boot-starter` | Dependency bundle for common configuration |
| `acme-client-json` | Optional JSON adapter, only needed if the application opts into this feature |

An application may use only `acme-spring-boot-autoconfigure` without installing `acme-client-json`; in that case, JSON auto-configuration must remain inactive. A dedicated starter can declare `acme-client-json` to enable that feature out of the box.

## 3. Maven: Understanding optional Correctly

### 3.1. Optional Is Not a Dependency Scope

In Maven, a dependency has a scope such as `compile`, `provided`, `runtime`, `test`, or `system`. The `<optional>true</optional>` element is an additional flag placed inside a dependency declaration.

Example in the autoconfigure module's POM:

```xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-client</artifactId>
        <version>${acme-client.version}</version>
        <optional>true</optional>
    </dependency>
</dependencies>
```

The dependency above defaults to `compile` scope. This means:

- The `acme-spring-boot-autoconfigure` module still has `acme-client` on its compile classpath to compile sources.
- The dependency is also on the runtime classpath of that module itself.
- When another application depends solely on `acme-spring-boot-autoconfigure`, Maven **does not automatically propagate** `acme-client` to that application.
- If the application wants to use Acme features, it must declare `acme-client` directly or use a starter that declares that dependency.

Therefore, optional does not mean "not needed when running this module". It means "do not force this dependency onto every consumer of the module by default".

### 3.2. Table Distinguishing Maven Scope and optional

| Declaration | Current module | Consuming module | Purpose |
| --- | --- | --- | --- |
| `compile` (default) | Compile + runtime + test | Typically receives transitive dependency at compile/runtime | Standard required dependency |
| `runtime` | Runtime + test, not main source compile | Received at runtime, not compile | Drivers or implementations needed only when running |
| `provided` | Compile + test, not runtime | Not propagated as a regular runtime dependency | Provided by container/JDK/infrastructure |
| `test` | Test compile + test execution | Not propagated | JUnit, Mockito, test utilities |
| `compile` + `optional=true` | Compile + runtime + test | Not automatically propagated to consumers | Optional library feature |
| `runtime` + `optional=true` | Runtime + test | Not automatically propagated to consumers | Optional runtime implementation |

`optional` does not replace `provided`. An optional compile dependency is still included on the current module's runtime classpath. A provided dependency is not packaged into the module's runtime classpath in the same way, because Maven assumes the deployment environment provides it.

If a dependency is mandatory for applications to use the library, do not mark it optional just to shrink the dependency tree. If it only serves a dedicated integration, consider splitting modules or combining optional dependency with conditions.

### 3.3. Optional Is Evaluated Per Dependency Edge

Suppose:

- Project A is `acme-spring-boot-autoconfigure`.
- Project A declares `acme-client` as optional.
- Project B is an application depending on A.

Maven includes A in B's dependency graph, but does not automatically bring `acme-client` across the A -> `acme-client` edge. B can declare `acme-client` itself, or depend on starter C where starter C declares `acme-client` as a regular dependency.

If another dependency in the graph also brings in `acme-client` non-optionally, it will still appear in the application. `optional=true` is not a global exclusion command across all dependency paths.

If a consumer needs to remove a transitive dependency pulled by another artifact, use `<exclusions>` on the appropriate dependency; that is a different mechanism from optional.

## 4. Maven: POM Templates for Autoconfigure Module and Starter Module

### 4.1. Autoconfigure Module

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>${acme-client.version}</version>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

Here `spring-boot-autoconfigure` is the dependency auto-configuration code needs to compile and function. `acme-client` is an integration that may not be used by every consumer, so it is marked optional.

In real projects, versions can be managed by a parent POM or imported BOM; the example above is abbreviated to clarify optional semantics.

### 4.2. Starter Module

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>${project.version}</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>${acme-client.version}</version>
        </dependency>
    </dependencies>
</project>
```

The starter declares `acme-client` directly and does not mark it optional. When an application adds `acme-spring-boot-starter`, Maven receives both the autoconfigure module and Acme Client.

If you want a starter for JSON, create a separate starter artifact or add the JSON dependency to the corresponding starter. Do not put every database, JSON, messaging, and cloud integration into a single starter if most applications do not use them.

### 4.3. Consumer Chooses Usage Mode

Using only the auto-configure module and picking libraries manually:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>
</dependency>
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-client</artifactId>
    <version>4.2.0</version>
</dependency>
```

Or using the starter with pre-packaged default dependencies:

```xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

Both approaches can activate auto-configuration if the required classes and conditions are present. The difference is who takes responsibility for choosing the Acme library dependency.

## 5. Gradle: api and implementation

To use `api` and `implementation` for a Java library, apply the `java-library` plugin:

```kotlin
plugins {
    java-library
}
```

This plugin distinguishes dependencies belonging to the module's public API from dependencies that are strictly implementation details.

### 5.1. api: Dependencies Exported to Consumers

Use `api` when types from a dependency appear in the API that consumers need to compile against, for example:

- A public class inherits from a class in the dependency.
- A public interface extends an interface from the dependency.
- A public method accepts or returns a type from the dependency.
- A public field or annotation contract uses a type from the dependency.

Example:

```kotlin
dependencies {
    api("com.acme:acme-client:4.2.0")
}
```

Consumers receive this dependency on both their compile classpath and runtime classpath. Thus, consumer code can import `AcmeClient` when calling the library's API.

`api` does not mean the dependency is loaded with "higher priority"; it expresses that the dependency is part of the exported compile-time API.

### 5.2. implementation: Internal Dependencies Needed at Runtime

Use `implementation` when a module needs a dependency to compile and run, yet consumers do not need to see its types on their compile classpath.

```kotlin
dependencies {
    implementation("com.acme:acme-client:4.2.0")
}
```

Result:

- The dependency is on the current module's compile classpath.
- The dependency is on the current module's runtime classpath.
- Consumers do not receive the dependency on their compile classpath merely by depending on this module.
- Consumers still receive the dependency on their runtime classpath, because the library's implementation needs it when running.

This is the preferred default choice when a dependency is not part of the public API. It shrinks consumers' compile classpaths and prevents consumer code from accidentally depending on an internal library.

If consumers need to import Acme types in their own source code, `implementation` may not be enough; in that case, review the API boundary and consider `api`.

## 6. Gradle: compileOnly, compileOnlyApi, and runtimeOnly

### 6.1. compileOnly

`compileOnly` puts a dependency on the **current module's** compile classpath, but does not put it on the runtime classpath and does not export it to consumers.

```kotlin
dependencies {
    compileOnly("com.acme:acme-client:4.2.0")
}
```

It fits when:

- The module needs to compile code referencing types from the dependency.
- The module/application runtime receives that dependency from elsewhere, or the feature stays inactive when the dependency is absent.
- You do not want this dependency to automatically appear in consumers' runtimes merely because they use the current module.

In a custom starter, `compileOnly` often makes sense in the autoconfigure module for an optional integration guarded by `@ConditionalOnClass`. The corresponding starter can declare the real dependency via `implementation` to bring it into the application's runtime.

**Be careful:** if the dependency is genuinely needed to execute activated code and nothing else supplies it, `compileOnly` leads to `ClassNotFoundException`/`NoClassDefFoundError` or linkage errors. `compileOnly` does not automatically fetch dependencies when conditions match.

### 6.2. compileOnlyApi

`compileOnlyApi` comes from the Java Library Plugin. It makes a dependency present on both the module's compile classpath and the consumer's compile classpath, without supplying the dependency at runtime.

```kotlin
dependencies {
    compileOnlyApi("com.acme:acme-contract:4.2.0")
}
```

Use it when a type is only needed for consumers to compile against the public API, while runtime is provided by the environment or another dependency. For example, a library exposing annotation/type contracts provided by a container.

If applications need that exact dependency at runtime, ensure the runtime dependency is added separately. `compileOnlyApi` does not replace `api` when the library is needed at runtime.

### 6.3. runtimeOnly

`runtimeOnly` is for dependencies needed only at runtime, not to compile the module's source:

```kotlin
dependencies {
    runtimeOnly("com.h2database:h2")
}
```

A common example is a JDBC driver: source code may only use the JDBC API from the JDK, while runtime requires the driver to open connections. If an integration module needs to compile directly against the driver's classes, `runtimeOnly` is insufficient for that module; a compile configuration is needed then.

### 6.4. Gradle Comparison Table

| Configuration | Module compile | Module runtime | Consumer compile | Consumer runtime |
| --- | --- | --- | --- | --- |
| `api` | Yes | Yes | Yes | Yes |
| `implementation` | Yes | Yes | No | Yes |
| `compileOnly` | Yes | No | No | No |
| `compileOnlyApi` | Yes | No | Yes | No |
| `runtimeOnly` | No | Yes | No | Yes |

The table assumes `java-library` is applied and dependencies are published/consumed with corresponding metadata. When publishing for Maven/Ivy or consuming metadata from another build system, inspect the actual metadata because dependency representation may differ.

## 7. Gradle: Two-Module Custom Starter Structure

### 7.1. Autoconfigure Module

Example `acme-spring-boot-autoconfigure/build.gradle.kts`:

```kotlin
plugins {
    java-library
}

dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.acme:acme-client:4.2.0")

    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.acme:acme-client:4.2.0")
}
```

- Autoconfigure code compiles against Acme Client thanks to `compileOnly`.
- Applications depending solely on the autoconfigure module do not automatically get Acme Client at runtime.
- Module tests need the real library to test auto-configuration branches, so the dependency is added in `testImplementation`.
- `spring-boot-configuration-processor` is placed in `annotationProcessor`, not mistakenly placed in `implementation`.

If public methods/constructors of the module directly export the `AcmeClient` type to consumers, consider `compileOnlyApi` instead of `compileOnly` if consumers need that type at compile time. Or design the API so third-party types stay inside nested auto-configuration/internal methods and the starter's public contract does not expose them.

### 7.2. Starter Module

Example `acme-spring-boot-starter/build.gradle.kts`:

```kotlin
plugins {
    java-library
}

dependencies {
    api(project(":acme-spring-boot-autoconfigure"))
    implementation("com.acme:acme-client:4.2.0")
}
```

- `api(project(...))` exports the autoconfigure module to the application's compile classpath.
- `implementation("com.acme:acme-client:...")` puts Acme Client on the consumer's runtime classpath without exposing its types on the consumer's compile classpath.
- If applications are expected to call the `AcmeClient` API directly, change the starter's dependency to `api(...)` or intentionally provide a public API from the starter.

If the starter is purely a dependency-bundle artifact and exposes no types for consumers to compile against, pick a packaging approach that better matches the desired API. Base the decision on the contract the starter publishes, not on the assumption that `api` is always better than `implementation`.

### 7.3. Splitting Starters by Feature

If Acme has a core client, JSON codec, and messaging adapter:

```text
acme-spring-boot-autoconfigure
acme-spring-boot-starter
acme-spring-boot-starter-json
acme-spring-boot-starter-messaging
```

Each feature starter adds its corresponding dependency. Applications only add the JSON starter when they genuinely need JSON integration. This structure reduces unnecessary dependencies and allows versions/capabilities to be managed intentionally.

## 8. Making Auto-Configuration Safe When Dependencies Are Absent

Marking a dependency optional or compile-only is not enough. Auto-configuration needs **classpath conditions** so it does not create beans when the library is absent.

Example:

```java
@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        AcmeClient acmeClient(AcmeProperties properties) {
            return new AcmeClient(properties.getEndpoint());
        }
    }
}
```

The nested configuration isolates references to the optional class. When `AcmeClient` is not on the classpath, Spring Boot can skip the nested configuration based on metadata without instantiating beans of that type.

In the autoconfigure module, register the root class in:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Example contents:

```text
com.example.acme.autoconfigure.AcmeAutoConfiguration
```

`@ConditionalOnClass` determines whether the feature is considered; `@ConditionalOnMissingBean` allows applications to supply their own bean overriding the default. The two conditions solve two different problems:

- Acme library absent: do not activate integration.
- Acme library present, yet application already has an `AcmeClient`: auto-configuration yields to the application's bean.

Do not rely on a compile-only dependency "hiding itself" in place of a class condition. If code or annotation metadata still references an optional class in a spot loaded too early by the JVM, applications may encounter linkage errors. For optional types in method signatures, isolate them in a nested configuration as shown and test both with and without the dependency on the classpath.

## 9. Choosing Configurations Based on the Actual Published API

An important Gradle rule is to **prefer `implementation` first, and only use `api` when required by the public API**.

Example:

```java
public final class CatalogFacade {
    private final AcmeClient client;

    public CatalogFacade(AcmeClient client) {
        this.client = client;
    }

    public AcmeResponse fetch(String id) {
        return client.fetch(id);
    }
}
```

In this example, the public constructor accepts `AcmeClient` and the public method returns `AcmeResponse`. These types belong to the module's public API; if consumers compile code calling that constructor/method, the corresponding dependencies must be present on the consumer's compile classpath. `api` is the right choice if runtime also requires the library.

Conversely:

```java
public final class CatalogFacade {
    public CatalogResult fetch(String id) {
        return internalClient.fetch(id);
    }

    private final AcmeClient internalClient;
}
```

If `AcmeClient` only appears in a private field and implementation, consumers do not need to compile against Acme types merely to use `CatalogFacade`. `implementation` is more appropriate if the dependency is needed at runtime.

Examine the entire binary API, not just import statements. Superclasses/interfaces, generic parameters, annotations, and public/protected method signatures can all make a dependency type part of the contract. Additionally, the compiler sometimes needs a type's class file even when it is not overtly visible in source APIs—such as type annotations or overload resolution; when hitting consumer compile errors, inspect the classpath and consider `compileOnlyApi` or `api` depending on runtime needs.

## 10. Do Not Confuse Optional Dependencies With Feature Flags

The following mechanisms serve different purposes:

| Mechanism | Question answered |
| --- | --- |
| Maven `<optional>true</optional>` | Does the dependency automatically propagate to consumers? |
| Gradle `compileOnly` | Does the module need the dependency at compile time without putting it in runtime/consumers? |
| Gradle `api` | Do consumers need the dependency's types to compile against the public API? |
| Gradle `implementation` | Does the module need the dependency internally at compile time and runtime? |
| `@ConditionalOnClass` | Is the class present to activate the integration? |
| `@ConditionalOnProperty` | Did the user enable the feature via the Environment? |
| `@ConditionalOnMissingBean` | Has the application already provided a replacement bean? |

For example, an integration might require all three conditions:

```java
@AutoConfiguration
@ConditionalOnClass(AcmeClient.class)
@ConditionalOnProperty(
    prefix = "acme.client",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
public class AcmeClientAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
```

This is an illustrative snippet; for optional types in method signatures, consider a nested configuration to protect class loading. Classpath conditions do not replace dependency declarations: the module still needs the right dependency at compile time and the application needs the right dependency at runtime.

## 11. Inspecting the Real Dependency Graph

Do not just look at build files and guess how dependencies were published. Inspect both the producer and consumer module graphs.

### 11.1. Maven

Inspect the dependency tree:

```bash
mvn dependency:tree
```

Filter specifically for Acme Client:

```bash
mvn dependency:tree -Dincludes=com.acme:acme-client
```

Expectations:

- In the autoconfigure module, `acme-client` is present in that module's own tree.
- In an application depending only on the autoconfigure module, the optional dependency does not automatically appear across that edge.
- In an application depending on the starter, `acme-client` appears because the starter directly declares a non-optional dependency.
- If it still appears when a consumer depends only on autoconfigure, look for another dependency path bringing Acme Client in.

To inspect the published POM, check the POM in the repository or run `mvn help:effective-pom` on the current project. The published POM is the metadata consumers actually read.

### 11.2. Gradle

Inspect the consumer's compile classpath:

```bash
./gradlew :app:dependencies --configuration compileClasspath
```

Inspect the runtime classpath:

```bash
./gradlew :app:dependencies --configuration runtimeClasspath
```

Or trace why a dependency appears:

```bash
./gradlew :app:dependencyInsight --dependency acme-client --configuration runtimeClasspath
```

With `java-library`, check:

- `api`: on both the consumer's compile and runtime classpaths.
- `implementation`: absent from the consumer's compile classpath yet present on the runtime classpath.
- `compileOnly`: not propagated to consumer compile or runtime classpaths.
- `compileOnlyApi`: on the consumer's compile classpath but not runtime.
- `runtimeOnly`: only on the consumer's runtime classpath.

If publishing a Maven POM, inspect the generated metadata as well. Gradle Module Metadata preserves richer variant information; consumers using Maven POMs may receive semantics represented as Maven scopes. Do not assume every consumer build tool reads the exact same metadata format.

## 12. Common Mistakes

1. **Assuming optional is a scope.** It is a flag on a dependency, combined with the existing scope; it does not replace compile, runtime, provided, or test.
2. **Marking every dependency optional.** Core dependencies the starter needs to function will not reach consumers automatically; applications may hit missing classes at runtime.
3. **Marking optional in autoconfigure and forgetting to redeclare in the starter.** Consumers add the starter yet lack the library needed for the feature to run.
4. **Using compileOnly for a library needed at runtime with nothing else providing it.** Compilation succeeds, yet context startup or code execution fails when loading classes.
5. **Using api for all dependencies.** Consumer compile classpaths bloat, accidentally exposing implementation details and creating coupling.
6. **Using implementation for types in the public API.** Consumers may fail to compile when calling APIs containing those types.
7. **Using compileOnlyApi and forgetting the runtime dependency.** Consumers compile yet still lack the class at runtime.
8. **Using runtimeOnly for a dependency that main source needs to import.** Main source fails to compile because classes are missing from the compile classpath.
9. **Using compileOnly and forgetting class conditions.** Auto-configuration may reference absent classes and trigger load/linkage errors.
10. **Placing optional classes directly in multiple method signatures of the root config.** Consider a nested configuration with `@ConditionalOnClass` for isolation.
11. **Using the java plugin while expecting api.** `api` and `compileOnlyApi` belong to the Java Library Plugin; apply `java-library`.
12. **Relying on accidental transitive dependencies.** If code directly uses a type, declare the dependency directly with the right scope.
13. **Testing only inside the autoconfigure module.** The producer module has compile dependencies so tests always see the classes; add a separate test or consumer sample lacking the optional dependency.
14. **Not inspecting published artifacts.** Local builds may pass while published POM/Gradle metadata fails to reflect the configuration consumers need.
15. **Using different versions between the starter and autoconfigure.** Use a parent/BOM or version catalog to manage versions consistently.

## 13. Test Matrix for a Custom Starter

A minimal test suite should cover:

| Scenario | Autoconfigure module | Starter/consumer | Result to verify |
| --- | --- | --- | --- |
| Using autoconfigure alone, Acme Client missing | Has integration code, dependency optional/compile-only | Does not declare Acme Client | Context starts; Acme integration is not created |
| Using autoconfigure and declaring Acme Client directly | Condition sees the class | Consumer adds dependency | Default bean can be created |
| Using standard starter | Starter adds required dependencies | Adds only starter | Class is present and integration is configured |
| User supplies bean | Class is present | Consumer has custom bean | `@ConditionalOnMissingBean` causes default to back off |
| Feature property disabled | Class is present | Property `enabled=false` | Auto-configuration does not create feature bean |
| Using a different library version | Version graph changes | Dependency mediation/constraints | No binary incompatibility or class linkage errors |

With Spring Boot, `ApplicationContextRunner` can verify the context across classpath/property/user-bean scenarios. However, tests in the autoconfigure module still have test dependencies and therefore cannot alone prove a consumer lacking the optional library will run. Create a separate sample consumer or integration test to confirm the real graph.

## 14. Dependency Declaration Checklist

Before publishing a custom starter, answer:

- [ ] Is this dependency mandatory for every consumer of the module?
- [ ] Does it serve only an optional integration that can be split separately?
- [ ] In Maven, should the dependency be `optional=true` in the autoconfigure module?
- [ ] Has the starter module directly declared the dependencies needed for the default experience?
- [ ] In Gradle, has `java-library` been applied if `api`/`implementation` are needed?
- [ ] Does the dependency appear in the public API? If yes, was `api` or `compileOnlyApi` chosen to match runtime requirements?
- [ ] Is the dependency strictly an implementation detail? Was `implementation` preferred?
- [ ] Is the dependency needed only at compile time and supplied externally? Is `compileOnly` accurate?
- [ ] If a runtime feature requires the dependency, do the starter/consumer actually bring it onto the runtime classpath?
- [ ] Is the optional feature guarded with `@ConditionalOnClass` and an appropriate property condition?
- [ ] Have both consumers with and without the optional dependency been tested?
- [ ] Have you inspected the Maven dependency tree or Gradle compile/runtime classpaths and published metadata?

## 15. Self-Check Questions

**Question 1.** If a Maven dependency has `<optional>true</optional>`, can the current module use it to compile?  
**Answer:** Yes, if the scope permits; optional does not remove the dependency from the module's own compile/runtime classpath.

**Question 2.** Does a consumer depending on the autoconfigure module automatically receive optional dependencies?  
**Answer:** No. The consumer must declare that dependency directly or use a starter that declares it as a regular dependency.

**Question 3.** Is `optional` equivalent to Gradle `compileOnly`?  
**Answer:** No. Optional controls transitivity; compileOnly restricts the dependency to the module's compile classpath and omits it from runtime/consumer classpaths.

**Question 4.** Is Gradle `implementation` included in the consumer's runtime?  
**Answer:** Yes. It does not appear on the consumer's compile classpath, yet is still needed at runtime for the library's implementation to function.

**Question 5.** When do you use `api` instead of `implementation`?  
**Answer:** When types from the dependency are exported in the public API and consumers need those types to compile.

**Question 6.** How does `compileOnlyApi` differ from `compileOnly`?  
**Answer:** Neither provides a runtime dependency; compileOnlyApi additionally places types onto the consumer's compile classpath.

**Question 7.** A starter marked the Acme library optional in the autoconfigure module. How do you make the standard starter always enable the Acme feature?  
**Answer:** The starter module declares the Acme dependency directly and non-optionally; the consumer's runtime classpath will receive it.

**Question 8.** Why is `@ConditionalOnClass` needed if a dependency is already compileOnly?  
**Answer:** CompileOnly only controls the build classpath; it does not guarantee the class exists when the application runs. Conditions help auto-configuration skip the integration when the class is absent.

## Official Documentation

- Maven — Introduction to Optional and Excludes Dependencies: https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html
- Maven — Introduction to the Dependency Mechanism (dependency scopes and transitivity): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — The Java Library Plugin (api, implementation, compileOnly, compileOnlyApi, runtime variants): https://docs.gradle.org/current/userguide/java_library_plugin.html
- Gradle — Building Java Projects (compile/runtime dependency configurations): https://docs.gradle.org/current/userguide/building_java_projects.html
- Spring Boot — Creating Your Own Auto-configuration and custom starters: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html

**Takeaway:** Maven optional prevents a dependency from automatically propagating to consumers; Gradle compileOnly provides classes only at compile time for the module; api exports types for consumer compile/runtime; implementation keeps a dependency internal at module compile time while still providing it at consumer runtime. For a custom starter, typically mark integration libraries optional in the autoconfigure module, then declare required dependencies directly in the starter module.
