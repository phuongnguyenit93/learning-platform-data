# When to Separate the Starter from Auto-Configuration Code and When They Can Be Combined?

## 1. The Architectural Problem

When developing a Spring Boot integration library, two parts often go together yet serve different responsibilities:

- **Auto-configuration** is the Java code describing how Spring Boot automatically creates and configures beans: applicability conditions, properties to bind, required dependencies, and how applications can override defaults.
- **Starter** is the Maven/Gradle artifact that lets users add a single dependency to obtain the library along with the dependencies commonly needed for that use case.

You can publish these two parts as **two separate modules**, or **combine the auto-configuration code and dependency descriptor into the same module**. Spring Boot allows both approaches. The decision depends on the number of integrations, optional dependencies, product variants, and reuse requirements.

The question to answer is not “how many modules must a standard project have?”, but rather:

1. Does anyone need to use the auto-configuration without wanting the starter's default dependency bundle?
2. Are there multiple variants or optional integrations that need to be selected independently?
3. Does the auto-configuration code have reuse value across multiple different starters?
4. Is the overhead of releasing, versioning, and testing extra modules outweighed by practical flexibility?

**Decision rule:** separate when the auto-configuration code is an independently reusable component or multiple dependency packaging flavors are needed; combine when the auto-configuration is small, has only one common usage pattern, and has no optional dependencies that need separation.

This article uses Spring Boot **3.5.x**, Java 17+, and Maven for illustration. Module names and structure can be adapted to Gradle or other build systems.

## 2. Distinguishing Three Responsibilities: Core Library, Auto-Configuration, and Starter

An integration library may have three layers of responsibility:

| Component | What does it contain? | When do users need it? |
| --- | --- | --- |
| **Core library** | Business APIs, clients, models, protocols, main processing; ideally with minimal Spring dependencies if possible | When needing to use the library independently of Spring Boot or integrate in another way |
| **Auto-configuration module** | `@AutoConfiguration` classes, `@ConfigurationProperties`, conditions, default beans, and callback APIs | When wanting Spring Boot integration logic while choosing dependencies and packaging themselves |
| **Starter module** | Primarily a dependency descriptor, pulling in auto-configuration, the core library, and dependencies needed for common scenarios | When wanting to add a single dependency and get started quickly |

Not every library needs all three modules. If the core part is already a standalone library, it can stay separate. If the project only has a few Spring beans and no logic reusable outside Boot, a separate core library may not be needed.

**A starter is usually a JAR nearly empty of source code.** Its primary job is declaring appropriate dependencies. Auto-configuration Java code should live in a clearly scoped module, or in the same module as the starter if the project chooses the combined approach.

### Diagram When Separated

~~~text
Spring Boot Application
        |
        v
acme-spring-boot-starter
        |
        +--------------------+
        |                    |
        v                    v
acme-spring-boot       acme-client
(auto-configuration)  (core library)
        |
        v
spring-boot-autoconfigure
~~~

The starter pulls in the needed artifacts. The auto-configuration module holds the Spring Boot integration code and can mark the core dependency as optional so this module can be used in other dependency compositions.

### Diagram When Combined

~~~text
Spring Boot Application
        |
        v
acme-spring-boot-starter
        |
        +-- Auto-configuration classes
        +-- Configuration properties
        +-- META-INF/...AutoConfiguration.imports
        +-- Required library dependencies
~~~

The same JAR both contains the auto-configuration code and declares the required dependencies. Spring Boot still loads auto-configuration via the imports file; combining artifacts does not lose condition evaluation or bean back-off mechanisms.

## 3. When Should You Separate the Auto-Configuration Module and Starter Module?

### 3.1. There Are Multiple Integrations or Optional Dependencies

This is the strongest reason to separate. For example, an Acme library might connect to services via:
- HTTP client;
- Kafka;
- JMS;
- Redis cache;
- an internal transport provided by a customer.

Not every application needs all transports. If a single starter pulls in every dependency, an application using only HTTP still receives Kafka, JMS, and Redis on the classpath. That increases the dependency graph, configuration surface area, and risk of version conflicts.

You can organize as:

~~~text
acme-client
acme-spring-boot
acme-spring-boot-starter
acme-spring-boot-starter-kafka
acme-spring-boot-starter-jms
acme-spring-boot-starter-redis
~~~

Where:
- `acme-spring-boot` contains the shared API and auto-configuration;
- the basic starter provides minimal dependencies for HTTP;
- the Kafka starter adds Kafka integration;
- the JMS starter adds JMS integration;
- the Redis starter adds cache integration.

Each starter pulls only the appropriate dependencies. Applications can also depend directly on `acme-spring-boot` and select the transports they need themselves.

### 3.2. There Are Multiple Ways to Package Dependencies for the Same Auto-Configuration

A platform team may want to provide a minimal starter; another product team wants a starter pre-integrated with metrics, tracing, or a specific client. Both can share a single auto-configuration module.

Example:

~~~text
acme-spring-boot
    ^
    |
    +-- acme-spring-boot-starter-minimal
    |
    +-- acme-spring-boot-starter-observed
    |
    +-- company-platform-acme-starter
~~~

If auto-configuration and the starter are tightly merged into one artifact, teams wanting a different dependency bundle might be forced to pull unnecessary dependencies or duplicate configuration code.

Separating helps **reuse auto-configuration logic** while each starter represents a distinct dependency choice.

### 3.3. Some Users Want to Compose Dependencies Themselves

A library may be used in:
- a Spring Boot application;
- a Spring Framework application not using Boot;
- a starter maintained by another company;
- an application that only wants property binding/callback APIs while creating the client bean itself;
- a system needing to swap the transport or default implementation.

If the auto-configuration module can be consumed standalone, downstream consumers can add it alongside dependencies of their choice. The default starter is merely a convenient packaging, not the sole way to consume it.

### 3.4. Components Need to Be Released and Tested at Different Cadences

Separating can be useful when:
- the core library has its own release cycle;
- auto-configuration supports multiple versions of the library;
- dependency bundles change faster than the configuration API;
- multiple teams own different starters;
- you want to test auto-configuration independently against each dependency bundle.

However, splitting modules also adds responsibilities: version synchronization, dependency management, publish ordering, compatibility matrices, and CI pipelines. Only do this when the benefit is real.

## 4. When Can They Be Combined?

The Spring Boot Reference explicitly states: if the auto-configuration is relatively simple and **has no optional features**, combining auto-configuration with the starter is a valid option.

Indicators suited for combining:

- Only one foundational library and one default integration exist.
- Required dependencies are mandatory for almost all users.
- There are no multiple flavors or opinionated starter variants.
- No downstream consumers need to depend on auto-configuration separately.
- Auto-configuration code is small, has few callbacks, and needs no independent versioning.
- Small or internal project where the benefit of extra modules does not offset maintenance costs.

Example:

~~~text
acme-spring-boot-starter
    ├── src/main/java/.../AcmeAutoConfiguration.java
    ├── src/main/java/.../AcmeProperties.java
    ├── src/main/resources/META-INF/spring/
    │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── pom.xml
~~~

In a single artifact:
- the POM declares required dependencies;
- source contains the auto-configuration;
- the imports file registers classes with Spring Boot;
- property metadata is generated during build.

**Combining artifacts does not mean dumping every responsibility into one class.** You should still separate packages/classes by configuration, properties, integrations, and conditions to keep code readable and testable.

### Do Not Create Modules Just Because “We Might Need Them Later”

A small project can start with a single starter. When real needs emerge—such as a Kafka flavor, optional transport, or another downstream starter—you can split modules in a planned release. Pre-creating many modules without existing users or use cases increases artifact count, versions, and build steps without delivering value.

## 5. Quick Decision Table

| Question | If the answer is “yes” | Direction to consider |
| --- | --- | --- |
| Are there multiple transports or optional integrations? | Each application needs to pick a different group of dependencies | Separate auto-configuration and flavor-specific starters |
| Do downstream consumers want to build their own starters? | They need the auto-config logic with their own dependency bundle | Publish an independent auto-configuration module |
| Do some users need to use the library without the starter? | They want to choose dependencies or configure beans themselves | Separate core/auto-configuration by responsibility |
| Do multiple starters share the same auto-config logic? | Avoid copy/pasting configuration | Extract a shared module |
| Only one mandatory integration and dependency set? | All users need the same set of dependencies | Can be combined |
| Auto-configuration is very small with no optional features? | No clear benefit from a separate artifact | Can be combined |
| Does splitting significantly increase release/compatibility overhead? | Benefits are not large enough yet | Keep structure simple; re-evaluate when a use case arises |

A useful criterion is the **dependency graph**: if a starter pulls in a dependency many applications do not need, or if multiple starters must duplicate the same dependency/auto-config code, that is a signal to split.

## 6. Maven Architecture Example When Separated

Suppose there is a core library `acme-client` with an API to construct a client. The project publishes two Spring Boot modules:

- `acme-spring-boot-autoconfigure`: contains properties, auto-configuration, and their tests;
- `acme-spring-boot-starter`: dependency descriptor for users who want the default configuration.

The `-autoconfigure` suffix is a common explicit naming convention. The Spring Boot 3.5 documentation also illustrates an auto-configuration module named `acme-spring-boot` and a starter named `acme-spring-boot-starter`. The artifact name is not a runtime requirement; what matters is the role and dependency graph.

### 6.1. Repository Structure

~~~text
acme-parent/
├── pom.xml
├── acme-client/
│   ├── pom.xml
│   └── src/main/java/com/example/acme/AcmeClient.java
├── acme-spring-boot-autoconfigure/
│   ├── pom.xml
│   ├── src/main/java/com/example/acme/autoconfigure/
│   │   ├── AcmeAutoConfiguration.java
│   │   └── AcmeProperties.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/acme/autoconfigure/
│       └── AcmeAutoConfigurationTests.java
└── acme-spring-boot-starter/
    └── pom.xml
~~~

### 6.2. POM of the Auto-Configuration Module

Abbreviated example, assuming parent/BOM already manages Spring Boot versions and plugins:

~~~xml
<artifactId>acme-spring-boot-autoconfigure</artifactId>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
        <optional>true</optional>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

Key points:
- `spring-boot-autoconfigure` provides the auto-configuration APIs.
- `acme-client` is declared optional so users can consume the auto-configuration module while choosing how to supply the library dependency.
- `spring-boot-autoconfigure-processor` generates condition optimization metadata during build; configure the annotation processor per Boot's guidelines.
- If auto-configuration needs additional Spring Boot, Spring Framework, or other APIs at compile time, declare dependencies with the proper scope and version management.

**What does Maven `optional` mean?** An optional dependency is still present when building/testing this module itself, but is not automatically propagated down the user's dependency graph like a regular dependency. Therefore, the starter must explicitly declare the library dependencies it wants to provide to applications.

### 6.3. POM of the Starter Module

~~~xml
<artifactId>acme-spring-boot-starter</artifactId>

<dependencies>
    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The starter:
- depends on the auto-configuration module;
- pulls in the core library needed for the basic scenario;
- pulls in the core Spring Boot starter directly or transitively;
- does not add every optional dependency just “in case it is needed”.

If HTTP integration requires a specific HTTP client, put that dependency in the corresponding HTTP starter or the base starter when it is genuinely mandatory. If Kafka is optional, create a separate Kafka starter.

In real projects, manage versions via a parent POM or BOM to avoid repeating versions across multiple modules. Internal artifacts of the same release must be published with compatible versions.

## 7. Auto-Configuration Code Example in a Separate Module

### 7.1. Configuration Properties

File `AcmeProperties.java`:

~~~java
package com.example.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties("acme.client")
public record AcmeProperties(URI endpoint, Duration timeout) {
}
~~~

Two properties are bound:
- `acme.client.endpoint`: the Acme service address;
- `acme.client.timeout`: connection or request timeout according to the core client's contract.

In a real library, write clear Javadoc describing each property, duration units if a default differs from milliseconds, and validation rules. Use a project-owned namespace such as `acme.client`, avoiding putting custom keys under `spring`, `server`, or `management`.

### 7.2. Auto-Configuration

Suppose the core library has an `AcmeClient` class and constructor accepting endpoint/timeout:

~~~java
package com.example.acme.autoconfigure;

import com.example.acme.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(AcmeClient.class)
    static class AcmeClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        AcmeClient acmeClient(AcmeProperties properties) {
            return new AcmeClient(
                    properties.endpoint(),
                    properties.timeout());
        }
    }
}
~~~

The example above illustrates these principles:
- `@AutoConfiguration` marks the configuration class loaded by Boot.
- `@EnableConfigurationProperties` registers and binds properties.
- A nested configuration has `@ConditionalOnClass` to isolate parts referencing an optional library.
- `@ConditionalOnMissingBean` lets applications provide their own `AcmeClient`; the default bean backs off when a matching bean already exists.
- The method returns the exact `AcmeClient` type so the condition has sufficient type information.

**Why place the class condition on a nested configuration?** When a dependency is optional, a method in an always-processed class should not have a return type or direct reference to a potentially absent class. Separating the conditional branch prevents the optional class from being loaded/processed when the library is absent from the runtime classpath.

This is an illustrative configuration; the constructor and package of `AcmeClient` must match the actual core library API.

### 7.3. Registering Auto-Configuration

In the auto-configuration module, create the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

~~~text
com.example.acme.autoconfigure.AcmeAutoConfiguration
~~~

Spring Boot 3.x reads this file from the published JAR; each line is a fully qualified class name. Auto-configuration must be registered via the imports file. Do not use component scanning to discover auto-configuration classes; use `@Import` for specific configurations that need to be combined.

If there are multiple separate configurations, such as `AcmeAutoConfiguration` and `AcmeKafkaAutoConfiguration`, you can declare multiple lines and manage ordering with `before`/`after` or appropriate ordering annotations.

## 8. When Combining Auto-Configuration and Starter into One Module

For a small project, you can place both POM dependencies and auto-configuration code in the same artifact:

~~~text
acme-spring-boot-starter/
├── pom.xml
└── src/main/
    ├── java/com/example/acme/autoconfigure/
    │   ├── AcmeAutoConfiguration.java
    │   └── AcmeProperties.java
    └── resources/META-INF/spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The POM declares:
- Spring Boot dependencies needed to write auto-configuration;
- the mandatory core library;
- `spring-boot-starter` directly or transitively;
- appropriate annotation processors and build plugins.

When users add the single dependency `acme-spring-boot-starter`, they receive both configuration code and required dependencies. There is no need to publish a separate autoconfigure artifact.

### Abbreviated POM Example for a Combined Module

~~~xml
<artifactId>acme-spring-boot-starter</artifactId>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>com.example</groupId>
        <artifactId>acme-client</artifactId>
        <version>1.4.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

With the combined approach, the `acme-client` dependency can be a required dependency of the starter. If later it becomes optional or multiple different transports emerge, consider splitting modules rather than pulling every library into a shared starter.

**Even when combined, auto-configuration must still be tested independently.** Having one artifact does not mean skipping condition tests, properties tests, or verifying the imports file.

## 9. Testing Auto-Configuration Independently of the Starter

The auto-configuration module should have its own tests. `ApplicationContextRunner` allows testing combinations of:
- library present on the classpath;
- library excluded from the classpath;
- property present/absent;
- user bean supplied;
- whether the default auto-configuration backs off properly.

Test example with JUnit 5 and AssertJ:

~~~java
package com.example.acme.autoconfigure;

import java.net.URI;
import java.time.Duration;

import com.example.acme.AcmeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenLibraryIsPresent() {
        runner.withPropertyValues(
                "acme.client.endpoint=https://api.example.test",
                "acme.client.timeout=2s"
        ).run(context ->
                assertThat(context).hasSingleBean(AcmeClient.class));
    }

    @Test
    void userClientMakesDefaultBeanBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "acme.client.endpoint=https://api.example.test",
                        "acme.client.timeout=2s"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context).hasBean("customAcmeClient");
                    assertThat(context).doesNotHaveBean("acmeClient");
                });
    }

    @Test
    void missingOptionalLibraryDisablesClientConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(AcmeClient.class))
                .run(context ->
                        assertThat(context).doesNotHaveBean("acmeClient"));
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new AcmeClient(
                    URI.create("https://custom.example.test"),
                    Duration.ofSeconds(1));
        }
    }
}
~~~

The test above assumes the core `AcmeClient` constructor accepts `URI` and `Duration` as shown in the example. If the real API differs, adjust the object creation part while keeping the assertions on conditions and bean back-off.

### 9.1. Why Test with FilteredClassLoader?

When a dependency is declared optional, tests must prove that auto-configuration **does not fail when the class is absent**. `FilteredClassLoader` simulates a runtime classpath missing a class or package.

Do not only assert that no bean exists; the test must start the context successfully to catch linkage errors caused by a method signature or class-level reference touching an optional dependency too early.

### 9.2. Why Test User Overrides?

A good auto-configuration provides defaults while allowing applications to define their own beans. `@ConditionalOnMissingBean` is one of the common mechanisms for doing so.

User override tests prove:
- the application-defined bean is kept;
- the default bean is not additionally registered;
- no two beans of the same type exist to cause injection ambiguity.

### 9.3. Testing the Starter as a Real Consumer

Tests inside the auto-configuration module do not prove that the starter JAR pulled in the right dependencies or that the imports file was packaged properly. There should be at least one consumer smoke test:
1. Create a module/sample app declaring only the starter dependency.
2. Do not manually import the auto-configuration class.
3. Boot using `SpringApplication` or `@SpringBootTest`.
4. Verify the default bean is registered.
5. Inspect the dependency tree to ensure the starter does not pull unwanted integrations.

This is packaging/integration testing; `ApplicationContextRunner` in the auto-config module is condition logic testing. The two layers complement each other.

## 10. Optional Dependencies and Multiple Starter Flavors

When separating modules, distinguish between dependencies **optional in the auto-configuration module** and dependencies **selected by the starter to pull in**.

Example:

| Artifact | Acme core | Kafka | Redis | Auto-configuration |
| --- | --- | --- | --- | --- |
| `acme-spring-boot-autoconfigure` | Optional | Optional | Optional | Yes |
| `acme-spring-boot-starter` | Required | No | No | Pulls autoconfigure |
| `acme-spring-boot-starter-kafka` | Required | Required | No | Pulls autoconfigure |
| `acme-spring-boot-starter-redis` | Required | No | Required | Pulls autoconfigure |

If each starter pulls only the appropriate dependencies, an application that does not need Redis will not receive the Redis client merely from using the Acme HTTP starter.

In auto-configuration, isolate branches using class conditions:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(KafkaTemplate.class)
static class KafkaConfiguration {

    // Kafka-specific beans go here.
}
~~~

This is an illustrative snippet; in real code, all type references to Kafka should reside inside the condition-isolated branch so applications without the Kafka dependency can still boot.

**Do not mechanically make every dependency optional.** If auto-configuration cannot function without a dependency, either:
- mark the dependency optional and use a condition to skip the feature;
- or treat that dependency as mandatory in the corresponding module/starter;
- or extract a separate starter flavor.

The goal is a dependency graph that accurately reflects the usage contract.

## 11. Metadata and User Experience Quality

A good starter does not merely help an application compile. Users need to know which properties are supported, their data types, meanings, defaults, and valid values.

With `@ConfigurationProperties`:
- Use a dedicated prefix, such as `acme.client`.
- Write Javadoc for every field/property.
- Use `Duration` for time intervals instead of integers with ambiguous units.
- Generate metadata using `spring-boot-configuration-processor` when appropriate.
- Check the `META-INF/spring-configuration-metadata.json` file in the built artifact.

In the auto-configuration module, Spring Boot also offers the `spring-boot-autoconfigure-processor` annotation processor to collect condition metadata into:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Condition metadata helps Boot filter out inapplicable auto-configurations early, aiding startup time. With Maven, the Boot 3.5 documentation guides configuring annotation processors via `maven-compiler-plugin` version 3.12.0 or later; with Gradle, declare them in the `annotationProcessor` configuration.

Do not confuse the two files:
- `spring-configuration-metadata.json` describes properties for IDEs and users.
- `spring-autoconfigure-metadata.properties` contains condition metadata to optimize auto-configuration filtering.

## 12. Versioning, Dependency Management, and Compatibility

Separating modules enables reuse but also requires clear version management.

### When Separated

- Keep artifacts from the same release compatible, e.g., core 1.4.x, autoconfigure 1.4.x, and starter 1.4.x.
- Manage the Spring Boot version via an appropriate parent/BOM rather than letting each module pull a different Boot version.
- Test the core library and Boot version pairs you commit to supporting.
- If a starter flavor has its own lifecycle, clearly publish which autoconfigure versions it is compatible with.
- Avoid making the starter module reverse-depend on the autoconfigure module in a cyclic dependency.
- Never let the core library reverse-depend on the starter; core must sit lower in the dependency graph.

### When Combined

- One artifact versions both the auto-configuration code and the dependency bundle together.
- Fewer artifacts and a simpler release pipeline.
- If transitive dependencies change, evaluate the impact on all applications using the starter.
- When adding optional integrations, consider extracting a separate starter flavor or module to avoid bloating the dependency graph.

A dedicated BOM can be helpful when there are many artifacts needing synchronized version management. With a single starter, a dedicated BOM is usually unnecessary.

## 13. Artifact and Package Naming

For third-party libraries, do not name modules starting with `spring-boot`. That prefix is reserved for official Spring Boot artifacts.

Example names:
- `acme-spring-boot-autoconfigure`: auto-configuration module;
- `acme-spring-boot-starter`: regular starter;
- `acme-spring-boot-starter-kafka`: starter for Kafka;
- `acme-spring-boot-starter-test`: test starter if test-specific auto-configuration actually exists.

The Spring Boot 3.5 Reference illustrates an auto-configuration module named `acme-spring-boot` and starter `acme-spring-boot-starter`. The `-autoconfigure` suffix is a clear naming choice, not a requirement for Boot to recognize the module.

The auto-configuration package should be separate from the consuming application's component-scan package. Auto-configuration is loaded via `AutoConfiguration.imports`; there is no need to component-scan the entire library package.

## 14. Should a Test Starter Be Separated?

Some libraries need to provide testing support for consuming applications, such as:
- fake/in-memory transports;
- test fixtures;
- embedded servers;
- mock beans or test configuration utilities;
- test-specific auto-configuration replacing external dependencies with in-memory implementations.

If these tools are valuable to share and do not belong in the runtime starter, you can publish:

~~~text
acme-spring-boot-starter-test
~~~

Users add it in test scope:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>acme-spring-boot-starter-test</artifactId>
    <version>1.4.0</version>
    <scope>test</scope>
</dependency>
~~~

There is no need to create a test starter just to hold a small helper used in only one module. Split when test integration is an officially supported API for multiple applications or teams.

## 15. Common Architectural Mistakes

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| One starter pulls all optional integrations | Large dependency graph, easy conflicts, and expanded configuration surface | Separate starters by flavor or integration |
| Auto-configuration module mandatorily pulls the entire library | Downstream cannot choose dependencies themselves | Mark dependencies optional and use class conditions where appropriate |
| Starter omits core library thinking optional autoconfigure passes it down | Applications adding only the starter lack runtime libraries | Starter explicitly declares core dependencies |
| Combining everything into one module despite having multiple distinct starters | Starters duplicate dependencies or pull excess ones | Extract a shared auto-configuration module |
| Splitting modules prematurely | More artifacts, versions, pipelines, and docs than needed | Start simple; split when a real need arises |
| Putting optional dependencies into the base starter | Users not using the feature still receive the dependencies | Move into an appropriate flavor starter |
| Auto-configuration using component scan | May accidentally scan app packages or load unintended configs | Register via imports file and use `@Import` |
| Missing `AutoConfiguration.imports` | Auto-configuration JAR is not loaded by Boot automatically | Verify the resource file inside the built JAR |
| Optional class appears in a method signature outside a conditional branch | May hit class loading errors when the dependency is absent | Isolate inside a nested configuration with `@ConditionalOnClass` |
| Not testing classpath with missing library | Starter is unsafe when optional integration is absent | Use `FilteredClassLoader` |
| Testing only auto-configuration without testing the starter | May miss dependencies or imports resource in the artifact | Add a consumer smoke test |
| Not managing versions across modules | Prone to `NoSuchMethodError` or dependency convergence issues | Use a parent/BOM and compatibility matrix |

## 16. Decision and Implementation Workflow

You can use the following checklist before creating modules:

1. List truly required runtime libraries and optional dependencies.
2. Determine whether anyone needs auto-configuration without the default starter.
3. Determine whether there are multiple starter flavors or independent integrations.
4. If there is only one mandatory integration, consider combining.
5. If there are multiple dependency compositions, create an independent auto-configuration module and dependency-only starters.
6. Keep the core library independent of Spring Boot if it has value outside the Boot ecosystem.
7. Write clear conditions for classpath, properties, and user bean overrides.
8. Register auto-configuration in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
9. Generate configuration metadata and condition metadata.
10. Test defaults, disabled properties, missing optional classes, user overrides, and starter flavors.
11. Add consumer smoke tests to confirm published artifacts work when declaring only the starter.
12. Inspect the dependency tree and confirm the starter does not pull unselected integrations.

### How Should the Decision Outcome Be Documented?

A concise architectural decision record should explain:
- **Why separate/combine:** real use cases and number of dependency compositions.
- **Which module owns which responsibility:** core, auto-config, starter, test starter.
- **Which dependencies are required/optional:** and which starter pulls them.
- **Compatibility:** supported Spring Boot versions and library versions.
- **Testing:** which tests prove back-off, missing classes, and packaging.

If there is no practical reason for a separate artifact, keeping a single simple module is usually easier to maintain. When there are multiple packaging options or multiple consumers of auto-configuration, splitting modules creates helpful boundaries and enables reuse.

## 17. Self-Check Questions

**Question 1.** Must a starter necessarily contain auto-configuration Java code?

**Answer:** No. A starter is usually just a dependency descriptor. Auto-configuration code can reside in a separate module that the starter pulls in.

**Question 2.** When should auto-configuration and the starter be separated?

**Answer:** When there are multiple flavors/optional dependencies, downstream consumers want to compose dependencies themselves, or multiple starters share the same auto-configuration logic.

**Question 3.** When can they be combined?

**Answer:** When auto-configuration is simple, has no optional features, a single dependency bundle satisfies almost all users, and no standalone auto-config artifact is needed.

**Question 4.** Why are library dependencies in an auto-configuration module often marked optional?

**Answer:** So the auto-configuration module can be consumed without forcing the library dependency onto every consumer. When the library is absent, classpath conditions allow Boot to skip the corresponding configuration branch.

**Question 5.** What must the starter declare if the core dependency in the auto-configuration module is optional?

**Answer:** The starter must declare the core library as a regular dependency if it is required for the default usage scenario.

**Question 6.** How do you prove auto-configuration works when an optional library is absent?

**Answer:** Use `ApplicationContextRunner` with `FilteredClassLoader` to simulate a missing class and verify the context starts without registering beans that depend on that class.

**Question 7.** Why are consumer smoke tests necessary?

**Answer:** Tests in the auto-configuration module do not prove that the starter properly packaged the imports file and transitive dependencies. Consumer tests verify the real usage experience: adding the starter causes Boot to load configuration automatically.

## 18. Official References

- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration, section Creating Your Own Starter, autoconfigure module, starter module, and test starter: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Reference — Build Systems, section Starters and naming conventions: https://docs.spring.io/spring-boot/3.5/reference/using/build-systems.html
- Spring Boot 3.5 Reference — Configuration Metadata: https://docs.spring.io/spring-boot/3.5/specification/configuration-metadata/index.html
- Spring Boot 3.5 API — `AutoConfiguration`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.5 API — `ConditionalOnClass`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.5 API — `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
