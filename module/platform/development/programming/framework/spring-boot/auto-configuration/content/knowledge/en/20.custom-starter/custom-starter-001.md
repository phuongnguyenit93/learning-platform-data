# Distinguishing the API Module, Autoconfigure Module, and Starter Module

## Learning Objectives

When developing a Spring Boot integration library, three components are commonly mentioned: **API**, **autoconfigure**, and **starter**. They are related to one another but hold different responsibilities. If responsibilities are misplaced, the API may unnecessarily depend on Spring Boot, applications may pull in optional dependencies, auto-configuration may fail to be discovered, or users may have to manually import configuration despite adding the starter.

This lesson explains the boundary of each module, the dependency direction between them, how they are packaged into artifacts, how Spring Boot discovers auto-configuration, and how to test the experience of an application consuming the library.

After this lesson, you will be able to:

- Identify what belongs in the public API, what belongs in auto-configuration, and what belongs in the starter.
- Design a unidirectional dependency graph without cyclic dependencies.
- Organize a Gradle multi-project or Maven multi-module build for a library.
- Place `AutoConfiguration.imports` in the right artifact and understand why a starter is usually nearly empty.
- Separate optional integrations so the core starter does not pull in unnecessary dependencies.
- Test the API, auto-configuration conditions, and starter consumption experience.

## 1. Viewing from the Consuming Application's Perspective

Suppose a company publishes an Acme library providing a client to call the Acme service. An application wants to add the library with a single dependency, configure the endpoint in `application.yml`, and then inject `AcmeClient` into its service.

Users expect:

1. A stable Java contract to call the service.
2. Spring Boot automatically registers a default implementation when required dependencies are present and the feature is enabled.
3. Endpoint/timeout can be configured without manually writing a `@Bean`.
4. The default implementation can be replaced when desired.
5. Only dependencies for integrations that are actually needed have to be added.

To satisfy this, the library can be split into three modules:

~~~text
acme-api/
    AcmeClient.java
    AcmeRequest.java
    AcmeException.java

acme-spring-boot-autoconfigure/
    AcmeAutoConfiguration.java
    AcmeProperties.java
    DefaultAcmeClient.java
    META-INF/spring/
        org.springframework.boot.autoconfigure.AutoConfiguration.imports

acme-spring-boot-starter/
    build.gradle / pom.xml
    (mainly declares dependencies)
~~~

Dependency flow:

~~~text
Spring Boot Application
       |
       v
acme-spring-boot-starter
       |
       +---- spring-boot-starter
       |
       v
acme-spring-boot-autoconfigure
       |
       +---- spring-boot-autoconfigure
       |
       v
acme-api
~~~

In this example, the starter brings auto-configure and required dependencies into the application; auto-configure uses the API to create the default bean; the API does not need to know Spring Boot exists.

**Note:** this is a three-module architecture to clarify boundaries. Not every library needs to be split into three artifacts. If the API is only used together with Spring Boot, the API can be placed inside the autoconfigure module. Spring Boot also describes a minimal model consisting of one module containing auto-configuration (which may contain the API) and one starter module.

## 2. The API Module: The Contract Users Program Against Directly

The API module contains the types that applications or other integrations need to reference at compile time. This is the **public face of the library**.

Typical contents include:

- Interfaces/service contracts, for example AcmeClient.
- Request/response models or DTOs.
- Public exceptions.
- Enums and value types.
- SPI/extension interfaces if allowing third parties to provide implementations.

Example:

~~~java
package com.acme.api;

import java.net.URI;

public interface AcmeClient {
    URI endpoint();
}
~~~

A realistic API can expand with business methods and dedicated models:

~~~java
package com.acme.api;

public record AcmeRequest(String message) {
}

public record AcmeResponse(String requestId, boolean accepted) {
}
~~~

These are illustrative Java files; each public top-level type should reside in its own file with a matching name.

### 2.1. The API Module Should Know as Little as Possible

If possible, the API module should be independent of Spring Boot and the implementation framework. It should not contain:

- @AutoConfiguration, @Bean, @ConditionalOnClass.
- DataSource, HTTP client pool, or connection factory configurations.
- Code that reads Environment and binds properties.
- Default implementation classes.
- The AutoConfiguration.imports file.

Benefits:

- Plain Java applications or other frameworks can still use the contract.
- Integrations across multiple platforms can share the same API.
- Avoids pulling Spring Boot into every consumer just because they need interfaces/models.
- The API changes less frequently than implementations, making binary compatibility easier to maintain.

Do not expose vendor SDK details in the public API if you want to allow swapping vendors. For example, if `AcmeClient` takes a `VendorSdkRequest`, every API consumer becomes coupled to that SDK. Use library-owned request/response types and convert to vendor types in an adapter.

### 2.2. The API Module Does Not Automatically Activate Beans

Merely adding the `acme-api` dependency does not cause Spring Boot to create an `AcmeClient`. The API only provides Java types. To get automatic beans, the application needs the artifact containing auto-configuration and Spring Boot's discovery mechanism.

### 2.3. When Is a Separate API Module Unnecessary?

If a library is small, has only one implementation, and the API is not used standalone, splitting out an extra artifact can increase build, versioning, and release overhead. In that case, interfaces/models can be placed in the autoconfigure module or the main library module.

Split out a separate API when:

- Multiple integrations implement the same contract.
- Other applications need to compile solely against interfaces/models.
- You want to keep the API neutral with respect to Spring Boot.
- You want to manage API compatibility and releases independently.

## 3. The Autoconfigure Module: Connecting the API with Spring Boot

The autoconfigure module contains the **registration and configuration code for implementations** so Spring Boot applications can use the library conveniently.

Typical contents include:

- `@AutoConfiguration` classes.
- Default implementations of the API.
- `@ConfigurationProperties` and defaults.
- Conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`.
- Callbacks/customizers for user extensibility.
- Sub-configurations for optional integrations.
- The `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` resource.
- Auto-configuration condition metadata and configuration properties metadata generated by annotation processors.

### 3.1. Default Configuration Example

Suppose the API module already has `AcmeClient`. The autoconfigure module defines properties:

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "acme")
public record AcmeProperties(
        @DefaultValue("https://api.acme.example") URI endpoint
) {
}
~~~

Default implementation:

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;

final class DefaultAcmeClient implements AcmeClient {

    private final URI endpoint;

    DefaultAcmeClient(URI endpoint) {
        this.endpoint = endpoint;
    }

    @Override
    public URI endpoint() {
        return endpoint;
    }
}
~~~

Auto-configuration:

~~~java
package com.acme.autoconfigure;

import com.acme.api.AcmeClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true)
@EnableConfigurationProperties(AcmeProperties.class)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(AcmeClient.class)
    AcmeClient acmeClient(AcmeProperties properties) {
        return new DefaultAcmeClient(properties.endpoint());
    }
}
~~~

This is a minimal wiring example: `DefaultAcmeClient` represents the default implementation of the contract. In a real library, this class would use a transport/client implementation to perform its business logic; the transport layer should have its own tests.

The `@ConditionalOnMissingBean` condition allows the application to provide its own implementation. The class-level `@ConditionalOnProperty` condition specifies that `acme.enabled=false` disables the core branch; when the key is omitted, it is default-on per `matchIfMissing=true`.

### 3.2. Auto-Configuration Must Be Registered

Spring Boot 3.x discovers auto-configuration from the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Each line is the fully qualified name of an auto-configuration class. When an application uses `@SpringBootApplication` or `@EnableAutoConfiguration`, Boot scans for this file in JARs on the classpath, then processes candidates according to conditions and ordering.

**The imports file must reside in the autoconfigure JAR**, not only in the starter aggregator. The starter typically contains no configuration code and does not need to re-list classes itself. When building, verify the actual resources inside the published artifact.

Auto-configurations should be top-level classes, not targets of component scanning. Do not use a broad `@ComponentScan` inside auto-configuration to find library classes; use explicit `@Import` for supporting configurations when needed.

### 3.3. Dependencies of Autoconfigure

The autoconfigure module typically needs:

- The API module.
- `spring-boot-autoconfigure`.
- Required runtime libraries to construct the default implementation.
- `spring-boot-configuration-processor` to generate metadata for configuration keys.
- `spring-boot-autoconfigure-processor` to generate condition metadata if the project needs optimized auto-configuration filtering.

If public method/constructor signatures in the autoconfigure module expose API types to consumers, declare the API dependency appropriately (for example, Gradle `api(project(":acme-api"))`). If a dependency is solely an internal detail, use `implementation` when the dependency graph permits.

For libraries with optional dependencies, clearly decide which artifact's runtime graph owns them. An optional SDK should not be pulled into every application that only uses core.

## 4. The Starter Module: Packaging Dependencies for One-Time Addition

The starter has a different purpose from autoconfigure: **bundling the dependencies required for an intentional usage experience**.

A standard starter is usually an almost empty JAR:
- Contains no service implementations.
- Contains no `@AutoConfiguration`.
- Needs no component scanning.
- Contains no `AutoConfiguration.imports` file if it provides no auto-configuration itself.
- Mainly declares dependencies on autoconfigure and required libraries.

Example of a user adding it:

~~~kotlin
dependencies {
    implementation("com.acme:acme-spring-boot-starter:1.2.0")
}
~~~

The starter can pull in:
- `acme-spring-boot-autoconfigure`.
- `acme-api` via the transitive dependency of autoconfigure.
- `spring-boot-starter` if the starter needs to ensure the core Spring Boot starter is present.
- An HTTP client or foundational dependency that the core library actually needs.

After adding the starter, users can configure:

~~~yaml
acme:
  enabled: true
  endpoint: https://tenant.example
~~~

And then inject the API:

~~~java
@Service
class NotificationService {

    private final AcmeClient acmeClient;

    NotificationService(AcmeClient acmeClient) {
        this.acmeClient = acmeClient;
    }
}
~~~

Users **do not need** to manually `@Import(AcmeAutoConfiguration.class)` or `@ComponentScan("com.acme.autoconfigure")`. Boot automatically finds the imports file in the autoconfigure JAR.

### 4.1. Must a Starter Always Be an Empty JAR?

By Spring Boot convention, a starter is a dependency aggregator, usually an almost empty JAR. The artifact name and POM/build file describe the selected dependencies.

You can merge autoconfigure and starter if a library is small and has few optional features. In that case, a single artifact both contains auto-configuration code and supplies the needed dependencies. However, if you want to allow applications to use autoconfigure alone to pick dependencies themselves or to create multiple starters with different combinations, keeping the two modules separate provides greater flexibility.

## 5. Comparing Responsibilities and Artifacts

| Criterion | API module | Autoconfigure module | Starter module |
| --- | --- | --- | --- |
| Purpose | Public contract | Automatically create/configure beans | Bundle dependencies for consumers |
| Contains interfaces/models | Yes | Can reference them | Should not |
| Contains default implementation | No | Yes | No |
| Contains @AutoConfiguration | No | Yes | Usually no |
| Contains @ConfigurationProperties | Usually no | May contain them | No |
| Contains AutoConfiguration.imports | No | Yes | Usually no |
| Depends on Spring Boot | Preferably no | Yes | Usually indirectly |
| Can be used standalone | Usable by plain Java/other frameworks | Usable when manually selecting dependencies | Intended for Spring Boot integration experience |
| Role for users | Compile contract | Provides automatic behavior | Single dependency to add |

The three modules are not three layers that must always exist. Split according to actual usage needs and the real dependency graph.

## 6. Designing a Unidirectional Dependency Graph

With three modules:

~~~text
acme-api
    ^
    |
acme-spring-boot-autoconfigure
    ^
    |
acme-spring-boot-starter
    ^
    |
Consumer application
~~~

Arrows represent dependencies from bottom to top in the diagram: autoconfigure depends on API; starter depends on autoconfigure; the application depends on starter.

Do not create cycles such as:

~~~text
acme-api -> autoconfigure -> starter -> acme-api
~~~

The API must not know about the starter, and autoconfigure should not depend on the starter. The starter is the outermost layer, aggregating existing components.

### 6.1. When to Separate Optional Integrations?

Suppose Acme also has a Vendor codec, but only some applications need it. You can create:

~~~text
acme-api
acme-spring-boot-autoconfigure
acme-spring-boot-starter

acme-vendor-codec-autoconfigure
acme-spring-boot-starter-vendor-codec
~~~

Dependency graph:

~~~text
Core application
    |
    v
acme-spring-boot-starter
    |
    v
acme-spring-boot-autoconfigure
    |
    v
acme-api

Application needing codec
    |
    +---- acme-spring-boot-starter
    |
    +---- acme-spring-boot-starter-vendor-codec
                |
                +---- acme-vendor-codec-autoconfigure
                |
                +---- Vendor SDK
~~~

The core starter does not pull in the Vendor SDK. The codec starter represents an optional add-on that can depend on the core starter, codec autoconfigure, and the SDK.

In optional auto-configuration, use `@ConditionalOnClass` at the **configuration class level** if method signatures contain vendor types that may be missing. If a client bean created by the SDK is required, add `@ConditionalOnBean`. When allowing the application to replace the adapter, use `@ConditionalOnMissingBean`.

## 7. Gradle Multi-Project Example

### 7.1. Directory Structure

~~~text
acme/
  settings.gradle.kts
  build.gradle.kts

  acme-api/
    build.gradle.kts
    src/main/java/com/acme/api/AcmeClient.java

  acme-spring-boot-autoconfigure/
    build.gradle.kts
    src/main/java/com/acme/autoconfigure/AcmeAutoConfiguration.java
    src/main/java/com/acme/autoconfigure/AcmeProperties.java
    src/main/resources/META-INF/spring/
      org.springframework.boot.autoconfigure.AutoConfiguration.imports

  acme-spring-boot-starter/
    build.gradle.kts
~~~

### 7.2. settings.gradle.kts

~~~kotlin
rootProject.name = "acme"

include(
    "acme-api",
    "acme-spring-boot-autoconfigure",
    "acme-spring-boot-starter"
)
~~~

### 7.3. API build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}
~~~

The API module needs no Spring Boot dependency if the contract only uses Java/JDK types.

### 7.4. Autoconfigure build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":acme-api"))

    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor(
        "org.springframework.boot:spring-boot-configuration-processor"
    )
    annotationProcessor(
        "org.springframework.boot:spring-boot-autoconfigure-processor"
    )

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Here:
- `api(project(":acme-api"))` because the API is the contract consumed by callers.
- `implementation(spring-boot-autoconfigure)` provides annotations and runtime support for auto-configuration.
- The two annotation processors generate metadata at compile time.
- Autoconfigure tests use `spring-boot-starter-test`.

### 7.5. Starter build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(project(":acme-spring-boot-autoconfigure"))
    api("org.springframework.boot:spring-boot-starter")
}
~~~

The starter needs no Java source. The `api` dependency ensures dependencies are propagated transitively to applications consuming the starter; `api`/`implementation` can be adjusted based on the actual contract and publishing setup.

**Version:** the examples omit versions in individual dependencies because they assume the root project already manages the Spring Boot version via a plugin or BOM. In a published library, ensure dependency versions resolve consistently and do not force host applications onto an unintended Spring Boot version.

## 8. Maven Multi-Module Uses the Same Boundaries

In Maven, the root project typically uses `pom` packaging and lists the three modules:

~~~xml
<packaging>pom</packaging>

<modules>
    <module>acme-api</module>
    <module>acme-spring-boot-autoconfigure</module>
    <module>acme-spring-boot-starter</module>
</modules>
~~~

The autoconfigure POM depends on the API and Spring Boot autoconfigure:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-api</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-configuration-processor</artifactId>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

The starter POM bundles autoconfigure and the core starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>${project.version}</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The snippets above show the main dependencies/modules section, not a complete publishable POM. A real project needs `groupId`, `artifactId`, `version`, repositories, compiler release, test plugins, and dependency management. Use the Spring Boot BOM to manage compatible Spring Boot library versions; avoid declaring scattered versions in individual modules.

### 8.1. Does the Library Need Its Own BOM?

If there are only a few artifacts and all release at the same version, dependency management in the parent or Spring Boot BOM may suffice. If the library has many modules or multiple optional starters for users to select independently, you can additionally publish `acme-bom` to manage versions in sync:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-api</artifactId>
            <version>${acme.version}</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>${acme.version}</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>${acme.version}</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

A BOM manages versions; it does not automatically add dependencies to the classpath. Consumers still must declare the starter or API artifacts they need.

## 9. Consumer Experience: Add Starter, Configure, Inject API

An application using Gradle:

~~~kotlin
dependencies {
    implementation("com.acme:acme-spring-boot-starter:1.2.0")
}
~~~

Configuration:

~~~yaml
acme:
  enabled: true
  endpoint: https://tenant.example
~~~

Using the API:

~~~java
@Service
class OrderNotificationService {

    private final AcmeClient acmeClient;

    OrderNotificationService(AcmeClient acmeClient) {
        this.acmeClient = acmeClient;
    }

    void inspectEndpoint() {
        URI endpoint = acmeClient.endpoint();
    }
}
~~~

Users only need to know the public API and properties. They do not need to know the `DefaultAcmeClient` class, manually create the default bean, or manually import the auto-configuration.

If they want to replace the implementation:

~~~java
@Configuration(proxyBeanMethods = false)
class MyAcmeConfiguration {

    @Bean
    AcmeClient myAcmeClient() {
        return new MyAcmeClient();
    }
}
~~~

`@ConditionalOnMissingBean(AcmeClient.class)` in the auto-configuration causes the default bean to back off when a user bean is processed first. This is a customization contract that should be documented.

## 10. Testing at the Right Module Boundaries

Do not rely solely on a single test that boots the entire application to conclude all modules are correct. Each module needs appropriate tests:

| Module | Recommended tests |
| --- | --- |
| API | Compile contract, model behavior, compatibility of public types |
| Autoconfigure | ApplicationContextRunner: defaults, property overrides, disabling, custom bean back-off, classpath conditions |
| Starter | Dependency graph, imports resource present in JAR, consumer smoke test adding only the starter |
| Optional integration | SDK present/missing, client bean present/missing, custom adapter override |

### 10.1. Testing Auto-Configuration with ApplicationContextRunner

The example below is **a complete test file** verifying defaults, property overrides, disabling the feature, and user-provided beans. In production, the API/properties/auto-configuration reside in their separate modules as described.

**File:** src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTest.java

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AcmeAutoConfiguration.class));

    @Test
    void createsDefaultClientWhenEnabledPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context.getBean(AcmeClient.class).endpoint())
                    .isEqualTo(URI.create("https://api.acme.example"));
        });
    }

    @Test
    void bindsEndpointFromEnvironment() {
        runner.withPropertyValues("acme.endpoint=https://tenant.example")
                .run(context -> {
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://tenant.example"));
                });
    }

    @Test
    void explicitFalseDisablesTheAutoConfiguration() {
        runner.withPropertyValues("acme.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class));
    }

    @Test
    void userClientMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(AcmeClient.class);
                    assertThat(context.getBean(AcmeClient.class).endpoint())
                            .isEqualTo(URI.create("https://custom.example"));
                    assertThat(context.containsBean("acmeClient")).isFalse();
                });
    }

    record TestAcmeClient(URI endpoint) implements AcmeClient {
    }

    @ConfigurationProperties(prefix = "acme")
    record AcmeProperties(
            @DefaultValue("https://api.acme.example") URI endpoint
    ) {
    }

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "acme",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    @EnableConfigurationProperties(AcmeProperties.class)
    static class AcmeAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(AcmeClient.class)
        TestAcmeClient acmeClient(AcmeProperties properties) {
            return new TestAcmeClient(properties.endpoint());
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        AcmeClient customAcmeClient() {
            return new TestAcmeClient(
                    URI.create("https://custom.example"));
        }
    }
}
~~~

### 10.2. Dependencies and Test Run Commands

In the autoconfigure module, Gradle test dependencies can be:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Run from the multi-project root:

~~~bash
# Linux/macOS
./gradlew :acme-spring-boot-autoconfigure:test

# Windows
gradlew.bat :acme-spring-boot-autoconfigure:test
~~~

**Expected result:** all four tests PASS:
- `acme.enabled` not declared: default client appears.
- `acme.endpoint` present: endpoint is bound.
- `acme.enabled=false`: no default client.
- User bean present: auto-configuration does not create a second default.

Assertions verify the context without printing fixed application stdout. Console output depends on Gradle/JUnit logging.

### 10.3. Verifying the Actual Starter JAR

The `ApplicationContextRunner` above loads auto-configuration directly via `AutoConfigurations.of(...)`; therefore it tests bean logic but **does not prove** the imports resource was packaged properly in the JAR.

After building:

~~~bash
# Inspect contents of autoconfigure JAR
jar tf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar

# Verify the imports file is packaged
jar xf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Open the extracted resource and confirm it contains the line:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Then create a sample consumer that only adds `acme-spring-boot-starter` and run a startup smoke test. This step verifies discovery and transitive dependencies in an environment closest to the end user.

## 11. Artifact Naming and Versioning

A suitable naming convention for a library is:

~~~text
com.acme:acme-api
com.acme:acme-spring-boot-autoconfigure
com.acme:acme-spring-boot-starter
com.acme:acme-codec-autoconfigure
com.acme:acme-spring-boot-starter-codec
~~~

Spring Boot recommends that a library's own module names **do not start with `spring-boot`**, avoiding confusion with official Spring Boot modules. Use the library's brand name or namespace.

### Versioning

If modules are released together, they should share the same version, for example 1.2.0. When bumping versions:
- API changes can be breaking changes for compile-time consumers.
- Changing property names or defaults can be a breaking behavior change.
- Renaming auto-configuration classes/packages can affect before/after ordering, exclusions, and imports metadata.
- Adding new dependencies in a starter can alter the application's runtime classpath.
- Adding a large or differently licensed SDK in an optional starter should be clearly announced.

Do not let `acme-api:1.1.0` and `acme-spring-boot-autoconfigure:1.2.0` be pulled into the same application if the two versions are incompatible. Use a synchronized parent version or an Acme BOM to manage them.

### Spring Boot Compatibility

The library should publish its supported Spring Boot range. A starter should not arbitrarily force a newer Spring Boot version than the one the application is using. Let users manage versions via the Spring Boot BOM/plugin; build the library against supported versions and run CI against the committed compatible versions.

## 12. Common Mistakes When Splitting Modules

1. **Putting `@AutoConfiguration` into the API module.** The API becomes coupled to Spring Boot even when consumers only need the contract; move auto-configuration to a separate module.
2. **Putting implementations into the starter.** The starter becomes a home for logic and hard to reuse; keep implementations in the library/autoconfigure module.
3. **Assuming the starter creates beans by itself.** The starter only brings dependencies onto the classpath; auto-configuration registers beans.
4. **Putting the imports file in the starter instead of autoconfigure.** Boot will not find the file in the artifact that actually holds the configuration, or the file gets omitted during packaging.
5. **Forgetting the imports file.** The auto-configuration class is in the JAR but never becomes a candidate; add its fully qualified name to the standard resource.
6. **Using component scan to discover auto-configurations.** Breaks discovery/ordering and risks scanning unintended classes; use the imports file.
7. **Creating cyclic dependencies.** API depends on autoconfigure or starter; keep the direction API -> autoconfigure -> starter in terms of top-down dependency.
8. **Core starter pulling in optional SDKs.** Applications only needing core still get unwanted dependencies; split optional integrations and starters separately.
9. **Splitting too many modules without clear boundaries.** Increases versioning/publishing overhead; merge when the API is not used standalone and there are no optional flavors.
10. **Failing to publish a clear API contract.** Consumers have to import implementation classes; expose only necessary interfaces/models.
11. **API containing vendor types.** Every consumer gets locked into the SDK; write adapters in the integration module.
12. **Not checking transitive dependencies.** The starter may miss the core starter or pull wrong versions; inspect the dependency insight/tree.
13. **Not inspecting the published artifact.** Source has the right resource, but the JAR is missing imports/metadata; inspect the actual JAR.
14. **Using module names starting with `spring-boot`.** Easily confused with official modules; use a distinct name such as `acme-spring-boot-starter`.
15. **Testing only auto-config directly without testing starter consumption.** Logic works, but the starter may miss dependencies or resources; add a smoke test with the published/local-published starter.

## 13. Pre-Release Checklist

### API
- [ ] Public interfaces/models/exceptions are stable and documented.
- [ ] No dependency on Spring Boot unless required.
- [ ] Does not expose implementations or optional SDK types.
- [ ] API compatibility has been verified.

### Autoconfigure
- [ ] Has `@AutoConfiguration` and appropriate conditions.
- [ ] Default beans have `@ConditionalOnMissingBean` when overrides are allowed.
- [ ] Properties have a dedicated namespace, clear types, and defaults.
- [ ] The imports file is in the correct JAR and lists all classes.
- [ ] Optional classes are guarded at class level.
- [ ] Annotation processors are configured if metadata is needed.

### Starter
- [ ] Pulls only dependencies actually needed for the default use case.
- [ ] Contains no duplicate bean/auto-configuration logic.
- [ ] Includes core `spring-boot-starter` directly or transitively when needed.
- [ ] Optional features are separated into dedicated starters when appropriate.
- [ ] Dependency versions are managed consistently.

### Release Testing
- [ ] API module compiles/tests independently.
- [ ] Autoconfigure tests defaults, overrides, disabling, and conditions.
- [ ] Imports/metadata verified inside the JAR.
- [ ] Consumer smoke test adding only the starter.
- [ ] Dependency tree does not pull unwanted optional SDKs.

## 14. Self-Check Questions

**Question 1.** A user only needs the `AcmeClient` interface and does not use Spring Boot. Which module should they depend on?

**Answer:** The API module. No need to pull in auto-configuration or the starter.

**Question 2.** Which module contains `AcmeAutoConfiguration` and `AutoConfiguration.imports`?

**Answer:** The autoconfigure module. This is the artifact holding configuration code and the resource for Spring Boot discovery.

**Question 3.** Does the starter create the `AcmeClient` bean itself?

**Answer:** No. The starter brings autoconfigure and required dependencies onto the classpath; the auto-configuration in the JAR registers the bean.

**Question 4.** When there is an optional codec SDK, should it be included in the core starter?

**Answer:** No if core users do not need the codec. Create a separate optional integration/autoconfigure and starter for users to choose.

**Question 5.** Why must you inspect the JAR after building even if `ApplicationContextRunner` tests already pass?

**Answer:** The test runner loads classes directly and does not prove that the imports resource is present in the JAR or that the starter's transitive dependencies are correct. You must inspect the artifact and test a sample consumer.

## 15. Takeaways for Library Design

- **API** defines the contract that consumers program against directly.
- **Autoconfigure** connects the contract to Spring Boot: properties, default implementations, conditions, and imports metadata.
- **Starter** provides a convenient dependency set so applications enable the library with a single declaration.

Dependency direction should be unidirectional: API at the bottom, autoconfigure depending on API, and starter depending on autoconfigure and required runtime dependencies. When there are optional features, create separate integrations/starters so core does not pull unnecessary SDKs.

Splitting into three artifacts is not mandatory for every library. If the API is not used independently or the library is very simple, you can merge the API into autoconfigure and/or merge autoconfigure with the starter. Split when boundaries help consumers pick the right dependencies, keep the API stable, and make the activation/customization contract clear.

### Official Spring Boot Documentation

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — @AutoConfiguration Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
