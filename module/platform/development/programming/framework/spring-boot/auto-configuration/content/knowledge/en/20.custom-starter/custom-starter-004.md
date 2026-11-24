# Choosing Required Dependencies for the Default Usage Experience

## 1. A Good Starter Begins With the User Experience

A custom Spring Boot starter is a promise about the experience when an application adds **a single dependency**. Users expect features to be sensibly configured, required libraries to be present, auto-configuration to activate when appropriate, and not having to hunt down individual JARs to piece together.

Therefore, when designing a starter, the crucial question is not just “which libraries does this module need to compile?” but also:

- When a user adds the starter, **which default capabilities** must work?
- Which libraries are mandatory foundations of that experience?
- Which integrations are merely optional, needed only by a subset of users?
- Is the starter inadvertently choosing a server, database driver, logging implementation, or client SDK on behalf of the application?
- When the application already defines its own bean, does auto-configuration back off properly?
- Is the dependency graph consistent with the Spring Boot and Java versions the library supports?

A good starter supplies enough dependencies for the common path to work out of the box, while leaving application-specific decisions to the user. For instance, a JDBC starter can provide a pool and Spring JDBC, yet should not unilaterally choose a PostgreSQL or MySQL driver unless the library is tied to one specific vendor.

This article designs a custom starter targeting Spring Boot 3.3.x and Java 17+, covering module separation, dependency/scope selection, using a BOM, organizing starter variants, inspecting the dependency tree, and verifying the experience in a consumer application.

## 2. Splitting Two Modules: Autoconfigure and Starter

A common layout consists of two artifacts:

```text
acme-notify/
├── acme-notify-spring-boot-autoconfigure/
│   ├── src/main/java/...
│   └── src/main/resources/
│       └── META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-notify-spring-boot-starter/
    └── pom.xml
```

**The `autoconfigure` module** contains the Java code:

- `@AutoConfiguration` and conditions.
- `@ConfigurationProperties` and configuration metadata.
- Default beans, customizers, health indicators, or integration adapters.
- The `AutoConfiguration.imports` resource so Spring Boot discovers auto-configuration.
- Tests verifying conditions, bean back-off, and behavior.

**The `starter` module** is primarily a dependency aggregator:

- Depends on the autoconfigure module.
- Pulls in foundational libraries that the default experience genuinely requires.
- Pulls in the intentionally chosen default SDK/implementation.
- Usually contains no Java sources, does not register a second auto-configuration, and does not implement business logic itself.

This separation benefits both sides:

1. Applications that only need auto-configuration or want to manage dependencies themselves can depend directly on the autoconfigure artifact.
2. Typical users simply add the starter and receive a set of dependencies tested together.

Artifact names for a third-party starter typically take the form `acme-notify-spring-boot-starter`; the configuration code module can be `acme-notify-spring-boot-autoconfigure`. Names starting with `spring-boot-starter-` are reserved for official Spring Boot starters; third parties should put their organization/product name first.

### 2.1. Why Not Combine Everything Into One JAR?

A single JAR can still work for a small library. However, when integrating multiple SDKs or multiple web/database stacks, it easily turns into a heavyweight dependency that every user is forced to pull in.

For example, a notification library might support:

- Default HTTP client.
- Kafka publisher.
- AWS SQS.
- Email via SMTP.
- WebFlux adapter.

If all SDKs are bundled into one starter, an application that only wants HTTP still has to pull in Kafka, AWS, mail, and a reactive server. The dependency graph becomes hard to reason about, the classpath grows larger, and version conflict risks increase.

Separating autoconfigure from the main starter, and then extracting integration starters when real demand arises, lets each artifact express a clear usage contract.

## 3. Categorizing Dependencies Before Adding Them to the POM

Before adding a dependency, categorize it by role rather than relying on whether a class import happens to appear in source code.

| Group | Examples | Should it belong in the default starter? |
| --- | --- | --- |
| Spring Boot baseline | `spring-boot-starter`, `spring-boot-autoconfigure` | Yes if the default experience relies on this foundation |
| Mandatory core library | Core HTTP SDK of the library | Yes if default capabilities cannot run without it |
| Optional integration | Kafka, AWS SQS, Redis, SMTP SDK | Only if it is part of the default or split into a dedicated starter |
| Web runtime | Servlet/Tomcat or reactive/Reactor Netty | Only choose if the feature actually needs that server runtime |
| Database pool/JDBC | HikariCP, Spring JDBC | Yes when the default starter provides JDBC access |
| Database vendor driver | PostgreSQL, MySQL, Oracle | Usually left for the application to choose |
| Validation | Jakarta Validation provider | Yes if the default contract requires validation and code actually uses it |
| Metrics/Actuator | Spring Boot Actuator | Optional or separate metrics starter if not a core requirement |
| Configuration processor | `spring-boot-configuration-processor` | Only at compile/annotation-processing time, not a runtime feature |
| Test libraries | `spring-boot-starter-test`, Testcontainers | Only in test scope |
| Logging implementation | Logback or Log4j implementation | Do not replace the application's logging stack without a clear reason |

A dependency should only be **mandatory** when omitting it breaks the experience the starter advertises. “Can integrate with” is not enough to make it a default dependency.

### 3.1. Dependency Decision Check

For each dependency, answer:

1. If this dependency is removed, can a user who adds the starter still run the default use case?
2. Is the dependency referenced in public API signatures, bean methods, or classes eagerly loaded at startup?
3. Is it a runtime implementation, compile-time API, or strictly for annotation processing/testing?
4. Should consuming applications be allowed to choose a different implementation?
5. Does the dependency pull in a server, driver, native library, or large transitive dependencies?
6. Is its version managed by the Boot BOM or does it require a separate version policy?
7. Can it be extracted into an integration starter to avoid pulling it into every application?

If the answer to question 1 is “no”, the dependency usually should not be in the default starter. If question 4 is “yes”, consider providing a replaceable default rather than forcing an implementation.

## 4. Maven Dependency Semantics: compile, runtime, optional, and test

Maven scopes affect the current module's classpath and how dependencies propagate to consumers.

| Scope / attribute | On module compile classpath? | On module runtime? | Propagated to consumers? |
| --- | :---: | :---: | --- |
| `compile` (default) | Yes | Yes | Yes, transitively |
| `runtime` | No | Yes | Yes at consumer runtime |
| `provided` | Yes | Present in Maven test/runtime per scope semantics | Not as a normal compile dependency |
| `test` | In test | In test | No |
| `<optional>true</optional>` on dependency | Per original scope | Per original scope | Not automatically propagated as a required dependency to consumers |

For an autoconfigure module, a dependency may be needed to compile yet **should not be pulled into every consumer automatically**. In that case Maven `optional` is very useful: the autoconfigure module declares the SDK dependency as optional; the library's official starter adds that SDK as a regular dependency.

### 4.1. Autoconfigure POM Example

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-autoconfigure</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-client</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

This is an illustrative POM; versions are managed by the project's parent or dependency management. The notification SDK is optional so a consumer depending only on autoconfigure is not forced to pull the SDK in. The configuration processor only assists with generating IDE/build metadata; it does not need to be present at application runtime.

If autoconfigure has classes that directly reference an optional SDK, place that part in a nested configuration with a class-level condition. Do not assume an optional dependency automatically prevents the JVM from loading every method signature. Example:

```java
@AutoConfiguration
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.notify.NotifyClient")
    static class NotifyClientConfiguration {
        // Bean methods can reference NotifyClient here.
    }
}
```

This is an illustrative structural fragment. Isolating optional classes in a nested configuration allows the condition to be evaluated before the configuration section depending on that class is processed.

### 4.2. Starter POM Example

The starter adds back the dependencies default users need:

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-starter</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-spring-boot-autoconfigure</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-notify-client</artifactId>
        </dependency>
    </dependencies>
</project>
```

This starter has three parts: Boot baseline, autoconfigure code, and default SDK. The SDK dependency is added **non-optionally** in the starter, so applications using the starter receive it at runtime.

Do not include `spring-boot-starter-test` in the starter POM in the default scope. Do not include unrelated database drivers or servers merely because they might be useful in some projects.

### 4.3. When to Use runtime Instead of compile?

If an implementation is only needed when the application runs and does not appear in the public API, `runtime` may be appropriate. For example, a plugin implementation loaded via SPI/reflection that consumers do not need to compile against directly.

If users need to declare beans, invoke APIs, or configure that class in source code, the dependency usually requires compile visibility. Examine the signatures of all beans exposed by autoconfigure, not just internal imports.

`provided` is not a general-purpose way to mark “optional”; it describes dependencies supplied by the deployment environment. For starters running in normal Boot applications, do not use `provided` merely to suppress propagation if consumers actually need that library.

## 5. Gradle: api, implementation, compileOnly, and runtimeOnly

With Gradle, distinguish public API from internal implementation:

- `api`: dependency appears on the consumer's compile classpath, suitable when the module's public API exposes types from that dependency.
- `implementation`: dependency needed by the module but omitted from the consumer's compile classpath; still present at runtime via the dependency graph.
- `compileOnly`: needed to compile the module but not added to the consumer's runtime classpath.
- `runtimeOnly`: needed only at runtime, not at compile time.
- `testImplementation`/`testRuntimeOnly`: for tests only.

Example with the `java-library` plugin:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.acme:acme-notify-client'

    annotationProcessor \
        'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation \
        'org.springframework.boot:spring-boot-starter-test'
}
```

This example shows how to prevent the SDK from propagating to consumers from the autoconfigure module; the starter will add the SDK as its own dependency. If the SDK appears in autoconfigure's public API and consumers must compile against that type, consider `compileOnlyApi` or redesigning the API so consumers are not forced to know the SDK. Either way, the starter must still provide the SDK at runtime.

The Gradle starter can be:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    api project(':acme-notify-spring-boot-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'com.acme:acme-notify-client'
}
```

In a multi-module project, `project(...)` is the dependency on the autoconfigure module. For published artifacts, replace it with the corresponding Maven coordinates.

**Note:** Gradle's configuration model and Maven `optional` are not exact equivalents. Do not mechanically translate each Maven scope into a Gradle name; inspect the consumer's compile/runtime graph after publishing or resolving the project.

## 6. Using a BOM to Keep Versions Consistent

A starter often depends on multiple Spring Boot and Spring Framework libraries. If each dependency declares its own version independently, it is very easy to produce combinations untested by Boot.

The Spring Boot BOM manages a compatible set of versions. With Maven, you can use `spring-boot-starter-parent` or import `spring-boot-dependencies` in `dependencyManagement`.

Example BOM import:

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

Then Boot-managed dependencies do not need versions listed:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-autoconfigure</artifactId>
</dependency>
```

With Gradle, you can use a dependency management plugin or import a platform BOM:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.13'
    )
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
}
```

Do not pin a Spring Framework version different from the one managed by the Boot BOM unless there is a tested compatibility reason. If a custom starter publishes multiple modules, keep internal versions aligned; an organization-specific BOM can manage `com.acme` artifacts if the ecosystem is large.

### 6.1. Version Policy for External Libraries

Not every dependency is managed by the Boot BOM. For vendor SDKs:

- Choose a version tested with target Java and Spring Boot versions.
- Manage versions centrally via properties or a dedicated BOM.
- Avoid declaring the same dependency with different versions across modules.
- Monitor CVEs and update periodically.
- Check dependency convergence and version conflicts in consumers.

Do not automatically adopt the latest version without verifying compatibility; an SDK may change its Java baseline, HTTP stack, or logging API.

## 7. Choosing the Right Default Runtime: MVC, WebFlux, or No Web Server?

One of the highest-impact dependency decisions is whether to pull in a web starter.

| Dependency | Default experience | When to choose |
| --- | --- | --- |
| `spring-boot-starter` | Boot foundation, does not pick an MVC/reactive server | Core libraries, batch/CLI, integrations needing no HTTP server |
| `spring-boot-starter-web` | Spring MVC + Servlet stack; typically includes embedded Tomcat by default | Libraries providing REST MVC endpoints or Servlet integration |
| `spring-boot-starter-webflux` | Spring WebFlux + reactive stack; typically includes Reactor Netty server | Libraries needing a reactive server and non-blocking HTTP handling |
| `spring-boot-starter-web` + `spring-boot-starter-webflux` | Boot prioritizes MVC when both are present | Only when the app truly needs both API stacks; often WebFlux is added to use `WebClient` |
| No web starter added | Does not enforce a web application type | Libraries needing only an HTTP client, domain service, or background auto-configuration |

Do not add both MVC and WebFlux merely to get `WebClient`. `WebClient` can be used with appropriate WebFlux dependencies inside a Servlet application; however, choose starters and dependency closures matching the experience you genuinely intend to support. If a starter promises a reactive server, it must pull the needed server runtime. If it only provides a client, do not accidentally turn the application into a web server.

### 7.1. Do Not Choose a Database Vendor on Behalf of Users

A starter providing JDBC access may need:

- `spring-boot-starter-jdbc` for Spring JDBC and the default connection pool.
- An abstraction or driver-independent API in the library.
- Auto-configuration for `DataSource`/templates if the product is responsible for that part.

It typically **should not** pull a PostgreSQL or MySQL driver by default. Applications choose drivers based on their actual database. If the product integrates exclusively with a service that has a dedicated driver, explain that decision and optionally offer a separate integration starter.

Similarly, do not add `spring-boot-starter-data-jpa` if the feature only needs JDBC; JPA pulls in an ORM and many additional runtime choices. Choose the smallest dependency sufficient to satisfy the contract.

### 7.2. Logging, Metrics, and Security

- Use Spring/JCL or SLF4J logging abstractions; avoid forcing a logging backend unless necessary.
- If Actuator integration is optional, place health indicators in a nested configuration guarded by `@ConditionalOnClass(HealthContributor.class)` and keep Actuator dependencies out of the core starter.
- If security is a core feature, clearly declare dependencies and the default security policy. If you only provide a Spring Security integration adapter, split it into a separate module/starter.
- Do not automatically enable management endpoints or expose sensitive information merely because the starter pulls in Actuator.

## 8. Designing a Family of Starters Instead of One Giant Starter

If the library has multiple independent integrations, organize by capability:

```text
acme-notify-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── acme-notify-client

acme-notify-kafka-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── kafka integration SDK

acme-notify-sqs-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── AWS SQS integration SDK

acme-notify-webflux-spring-boot-starter
    ├── acme-notify-spring-boot-autoconfigure
    └── WebFlux-specific adapter dependencies
```

Actual names and modules depend on the product. What matters is that users pull in only the integrations they need.

### 8.1. Do Not Mix Server Variants in the Core Starter

If the library supports both Servlet and Reactive:

- The core starter contains only shared dependencies and shared autoconfigure.
- The MVC starter adds adapter/Servlet dependencies.
- The WebFlux starter adds adapter/Reactive dependencies.
- Each adapter has `@ConditionalOnWebApplication(type = ...)`.
- Do not let two starters accidentally register the same bean name/type without back-off.

An application including both starters must still have documented behavior. When both runtimes are on the classpath, Spring Boot has rules for choosing the web application type; having WebFlux on the classpath does not automatically switch an MVC application to Reactive.

### 8.2. Do Not Put Every Integration in the Core Starter and Rely on Conditions

Conditions can prevent beans from being registered, but they do not make dependencies disappear from the dependency graph. If a starter pulls in Kafka, AWS SDK, Redis, mail, and WebFlux, users still download all those JARs even when the auto-configurations do not match.

Therefore, using `@ConditionalOnClass` is necessary for optional auto-configuration, yet **does not replace designing a lean dependency graph**. Splitting starters by capability reduces downloads, classpath conflicts, attack surface, and startup time.

## 9. Auto-Configuration Must Match the Dependency Contract

The dependency graph and conditions need to align.

Example of a custom starter providing a notification client:

```java
@AutoConfiguration
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.notify.NotifyClient")
    @ConditionalOnProperty(
            prefix = "acme.notify",
            name = "enabled",
            havingValue = "true")
    @EnableConfigurationProperties(NotifyProperties.class)
    static class NotifyClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NotifyClient notifyClient(NotifyProperties properties) {
            return new NotifyClient(
                    properties.endpoint(),
                    properties.apiKey());
        }
    }
}
```

This is an illustrative structure; `NotifyClient` is a type from the SDK and `NotifyProperties` is the library's configuration class. Imports and constructors depending on the real SDK must be adapted to the vendor API.

Meaning:

- If the SDK is absent from the classpath, the nested config does not participate.
- If the feature is not enabled, no client is created.
- If the user already provides a custom client, the default bean backs off.
- Properties are registered only in the enabled feature branch, if the contract requires mandatory configuration only when ON.

Do not include an SDK in the starter solely so a condition can find the class if that feature is not part of the default experience. If users need to pick the SDK themselves, provide the autoconfigure artifact and document the optional dependency.

### 9.1. Registering AutoConfiguration.imports

In the autoconfigure module, create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.acme.notify.autoconfigure.NotifyAutoConfiguration
```

If the resource is missing or has the wrong class name, the starter might pull the right dependencies while auto-configuration goes undiscovered. This is why a consumer smoke test against the packaged artifact is essential, not just direct tests with `AutoConfigurations.of(...)`.

### 9.2. Back-Off and Customization

The default bean should yield to an application-provided bean when appropriate:

```java
@Bean
@ConditionalOnMissingBean(NotifyClient.class)
NotifyClient notifyClient(NotifyProperties properties) {
    return new NotifyClient(properties.endpoint(), properties.apiKey());
}
```

This pattern allows the application to replace the client. Clearly document whether a user override exempts required properties. If configuration properties are bound at the nested class level, validation might still execute even when a user bean has replaced the client; that contract should be tested.

Do not create two beans of the same type/name and expect `@Primary` to solve every case. Backing off at the right layer makes dependency injection and behavior far more predictable.

## 10. Inspecting the Dependency Graph Consumers Actually Receive

A starter POM looking right is not enough. What must be verified is **the dependency closure after an application adds the starter**.

### 10.1. Maven

Inspect the dependency tree:

```bash
mvn dependency:tree
```

Filter specific artifacts:

```bash
mvn dependency:tree -Dincludes=com.acme,org.springframework.boot
```

Trace which branch and scope a dependency comes from and whether a different version is being pulled in. If the starter should not pull an optional integration, verify it is genuinely absent from the consumer's graph.

Check dependency convergence with Maven Enforcer when the project has multiple modules/vendor SDKs. A starter should not leave consumers to resolve unpredictable version conflicts themselves.

### 10.2. Gradle

Inspect the runtime graph:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Trace a specific artifact:

```bash
./gradlew dependencyInsight --dependency acme-notify-client --configuration runtimeClasspath
```

Pay attention to the difference between `compileClasspath`, `runtimeClasspath`, `testRuntimeClasspath`, and dependency constraints. A dependency present only in the test graph does not prove the starter publishes it to consumers.

### 10.3. Inspecting the Published POM

For Maven artifacts published or installed locally, read the actual POM:

- Which dependencies are declared compile/runtime?
- Which dependencies are marked optional?
- Are there unnecessary hard-coded versions?
- Does the starter depend on autoconfigure at the same version?
- Did test dependencies leak into runtime dependencies?
- Are there vendor/server dependencies that applications do not want?

Do not inspect only the source POM of a module; consumers receive the published/resolved POM, which may be altered by parents/BOMs/profiles.

## 11. Testing the Default Experience in a Consumer Application

There should be at least two test layers:

1. **Autoconfigure tests:** verify conditions, properties, bean creation/back-off, and classpath missing optional dependencies.
2. **Starter consumer smoke test:** create an app adding only the starter, verifying auto-configuration is discovered from the packaged resource and the dependency closure is sufficient for the default use case.

Testing the autoconfigure module directly with `AutoConfigurations.of(...)` does not prove `AutoConfiguration.imports` was packaged properly. A consumer smoke test catches that error.

### 11.1. Basic Auto-Configuration Tests

Example using `ApplicationContextRunner`:

```java
class NotifyAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NotifyAutoConfiguration.class));

    @Test
    void disabledByDefaultDoesNotCreateClient() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context).doesNotHaveBean(NotifyClient.class);
        });
    }

    @Test
    void enabledWithSettingsCreatesDefaultClient() {
        runner.withPropertyValues(
                "acme.notify.enabled=true",
                "acme.notify.endpoint=https://notify.example.test",
                "acme.notify.api-key=test-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(NotifyClient.class);
                });
    }

    @Test
    void userClientReplacesDefault() {
        runner.withUserConfiguration(UserNotifyClientConfiguration.class)
                .withPropertyValues(
                        "acme.notify.enabled=true",
                        "acme.notify.endpoint=https://notify.example.test",
                        "acme.notify.api-key=test-token")
                .run(context -> {
                    assertThat(context).hasSingleBean(NotifyClient.class);
                    assertThat(context).hasBean("customNotifyClient");
                    assertThat(context).doesNotHaveBean("notifyClient");
                });
    }
}
```

This is an illustrative skeleton; add imports for JUnit 5, AssertJ, `NotifyAutoConfiguration`, `NotifyClient`, and `UserNotifyClientConfiguration`. The methods above verify the default-OFF, ON, and user-override contracts.

If the SDK dependency is optional, add a `FilteredClassLoader` test to verify the nested config is not loaded when the SDK class is absent. Also verify the context still starts normally in that optional branch.

### 11.2. Consumer Smoke Test

Create an integration test module or project declaring only the starter as its primary dependency:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-notify-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

The consumer app needs a Boot application class. The test can start the context and verify:

- Auto-configuration is discovered from `AutoConfiguration.imports`.
- The default SDK is actually on the runtime classpath.
- Expected beans appear when properties are enabled.
- The application does not have to redeclare each dependency the starter promises to provide.
- No unintended servers/database drivers or integrations are present.
- User overrides are recognized.
- Dependency versions match the BOM.

A test calling `AutoConfigurations.of(...)` directly does not replace this test because it bypasses discovery via the imports resource and does not test the packaged starter POM.

### 11.3. Recommended Test Matrix

| Scenario | Check | Expected outcome |
| --- | --- | --- |
| Only add starter, feature disabled | Dependencies and startup | Context starts; no external connections created |
| Add starter + enable feature + full settings | Default behavior | Default bean/client is created |
| Enabled but missing required settings | Validation | Clear startup failure if contract requires fail-fast |
| User provides bean | Back-off | Default bean is not created |
| Use autoconfigure without optional SDK | Classpath condition | Context still starts, integration branch skipped |
| Use MVC app | Web type condition | Only Servlet adapter activates |
| Use Reactive app | Web type condition | Only Reactive adapter activates |
| Add two integration starters | Dependency collision | No duplicate beans/unintended servers |
| Consumer declares only starter | Packaging/discovery | Auto-configuration imported from resource |
| Upgrade Boot BOM | Compatibility | No Spring Framework/Boot conflicts |

## 12. Dependency Selection Examples for Three Different Products

### 12.1. Starter for a Domain/Client Library

The primary capability is a client calling an external API:

- `spring-boot-starter` as the baseline.
- Core HTTP SDK used by the library.
- Autoconfigure module.
- Do not add MVC server or WebFlux server just because the client uses HTTP.
- Obtain credentials/endpoints from properties or a secret source, never hard-coded.

### 12.2. Starter for a REST MVC API

The primary capability is providing controller/Servlet integration:

- `spring-boot-starter-web`.
- Autoconfigure module and MVC adapter.
- Validation may be needed if request DTOs are validated.
- Do not add a reactive server runtime.
- Do not pick a database driver if applications decide the database themselves.

### 12.3. Starter for a Reactive Gateway

The primary capability is reactive HTTP endpoints:

- `spring-boot-starter-webflux`.
- WebFlux adapter and autoconfigure module.
- Appropriate default reactive server implementation (usually already pulled in by the WebFlux starter).
- Do not add the MVC starter.
- Include reactive context tests and real HTTP integration tests.

These examples are architectural choices; if a product supports multiple modes, publish starter variants and clearly document how to combine them. Do not let a core starter automatically pull all three experiences.

## 13. Common Mistakes When Selecting Dependencies

| Symptom | Design flaw | Fix |
| --- | --- | --- |
| App only needs a client yet starts a server | Starter pulls an unnecessary web server | Use Boot baseline/client dependencies, drop web starter |
| MVC app gets a reactive server pulled in | Core starter pulls WebFlux when only WebClient is needed | Separate client dependency and WebFlux server adapter |
| Every consumer must download Kafka/AWS/Redis | Autoconfigure optional dependency wrong or starter too bloated | Separate integration starters and inspect the graph |
| Class not found at startup | Auto-config references optional type outside nested guarded config | Use class-level conditions and isolate optional types |
| Auto-configuration not discovered | Missing/incorrect `AutoConfiguration.imports` | Inspect the resource in the packaged JAR |
| Consumers use mismatched Spring versions | No BOM or scattered hard-coded versions | Centralize via Boot BOM and internal BOM |
| Database connection fails due to missing driver | Starter assumes a database vendor | Let consumers choose the driver or provide a driver-specific starter |
| Consumer gets two beans of the same type | Missing `@ConditionalOnMissingBean` or wrong type condition | Design back-off and test user overrides |
| Starter passes in tests yet fails in real app | Tests import class directly, skipping resource/dependency closure | Add a consumer smoke test |
| Dependency only present in test scope | Wrong POM/Gradle scope declared | Inspect `runtimeClasspath`/published POM |
| Artifact pulls in a test framework | Test dependency declared in wrong scope | Move to `test` / `testImplementation` |
| Logging changed unexpectedly | Starter forces a logging backend | Use logging abstractions and let the app choose the backend |

## 14. Checklist Before Releasing a Custom Starter

**Default experience**

- [ ] Clearly document the use case a single starter dependency activates.
- [ ] Intentional default ON/OFF; do not establish external connections merely upon adding the dependency.
- [ ] Endpoints, credentials, and driver-specific choices are delegated to the application when they belong to the application environment.
- [ ] User beans can override according to the contract.

**Dependency graph**

- [ ] Separate autoconfigure module holding code and starter module acting as dependency aggregator.
- [ ] Optional SDKs in autoconfigure do not propagate to every consumer unintentionally.
- [ ] Starter adds back dependencies needed for the default experience.
- [ ] Does not pull database vendor drivers unless mandatory.
- [ ] Does not pull both MVC and WebFlux unless the product genuinely needs both.
- [ ] Does not leak test libraries into the runtime graph.
- [ ] Dependency scopes match compile/runtime/API visibility.
- [ ] Dependency versions are managed by a BOM and backed by a compatibility policy.

**Auto-configuration and packaging**

- [ ] Contains the `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource.
- [ ] Optional classes are guarded at the appropriate configuration level.
- [ ] Conditions check classpath, web type, properties, and bean presence.
- [ ] Default beans back off when user beans are present.
- [ ] Includes property metadata and appropriate validation.
- [ ] Inspected the actual published artifact.

**Verification**

- [ ] Autoconfigure tests cover ON/OFF, missing classes, and user overrides.
- [ ] Consumer smoke test adds only the starter and verifies the default experience.
- [ ] Dependency tree contains no unintended integrations.
- [ ] Verified MVC/Reactive if providing web adapters.
- [ ] Verified version alignment and dependency convergence.

**Takeaway:** A starter is a contract for the dependency graph and the default experience. Separate auto-configuration code from the dependency aggregator; keep optional SDKs in the autoconfigure module and pull them into the starter only when they are a chosen default; manage versions via a BOM; do not choose a database driver or web server on the user's behalf if the product does not need it; and test inside a consumer project declaring only the starter. That is how “adding one dependency” genuinely delivers a clear, lightweight, and predictable experience.

## Official Documentation

- Spring Boot 3.3 — Creating Your Own Starter: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, optional dependencies, and starter modules: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Dependency Versions / BOM: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Spring Boot 3.3 — Starters: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Maven — Introduction to Dependency Mechanism and Optional Dependencies: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Java Library Plugin and API/Implementation Separation: https://docs.gradle.org/current/userguide/java_library_plugin.html
