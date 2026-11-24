# Distinguishing API Module, Autoconfigure Module, and Starter Module

## Learning objectives

When developing a Spring Boot integration library, three components are commonly mentioned: **API**, **autoconfigure**, and **starter**. They are related but carry different responsibilities. If responsibilities are misplaced, the API may unnecessarily depend on Spring Boot, applications may be forced to pull optional dependencies, auto-configuration may go undiscovered, or users may have to import configurations manually despite adding the starter.

This lesson explains the boundaries of each module, the dependency direction among them, how they are packaged into artifacts, how Spring Boot discovers auto-configuration, and how to test the experience of an application consuming the library.

After this lesson, you can:

- Determine what belongs in the public API, what belongs in auto-configuration, and what belongs in the starter.
- Design a unidirectional dependency graph without circular dependencies.
- Organize a Gradle multi-project or Maven multi-module build for a library.
- Place AutoConfiguration.imports in the right artifact and understand why a starter is usually nearly empty.
- Separate optional integrations so the core starter does not pull unnecessary dependencies.
- Test the API, auto-configuration conditions, and starter consumption experience.

## 1. From the perspective of an application using the library

Suppose a company releases an Acme library providing a client to call the Acme service. An application wants to add the library with a single dependency, configure the endpoint in application.yml, and inject AcmeClient into its services.

Users expect:

1. A stable Java contract for calling the service.
2. Spring Boot to automatically register a default implementation when required dependencies are present and the feature is enabled.
3. Configuration of endpoint/timeout without writing @Bean methods manually.
4. The ability to replace the default implementation when desired.
5. Only having to add dependencies for integrations they actually need.

To meet this, the library can be split into three modules:

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
    (mostly dependency declarations)
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

**Note:** this is a three-module architecture to clarify boundaries. Not every library needs to be split into three artifacts. If the API is only used with Spring Boot, the API can be placed inside the autoconfigure module. Spring Boot also describes a minimal model consisting of one module containing auto-configuration (which may contain the API) and one starter module.

## 2. API module: the contract users program against directly

The API module contains types that applications or other integrations need to reference at compile time. This is the **public surface of the library**.

Typical contents include:

- Interface/service contracts, e.g., AcmeClient.
- Request/response models or DTOs.
- Public exceptions.
- Enums and value types.
- SPI/extension interfaces if third parties are allowed to provide implementations.

Example:

~~~java
package com.acme.api;

import java.net.URI;

public interface AcmeClient {
    AcmeResponse send(AcmeRequest request);
    URI endpoint();
}
~~~

Public models:

~~~java
package com.acme.api;

public record AcmeRequest(String message) {
}

public record AcmeResponse(String requestId, boolean accepted) {
}
~~~

Public exception:

~~~java
package com.acme.api;

public class AcmeException extends RuntimeException {
    public AcmeException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

These are illustrative Java types; each public top-level type should reside in its own correspondingly named file.

### 2.1. The API module should know as little as possible

If possible, the API module should be independent of Spring Boot and implementation frameworks. It should not contain:

- @AutoConfiguration, @Bean, @ConditionalOnClass.
- DataSource, HTTP client pool, or connection factory configurations.
- Code reading Environment and binding properties.
- Default implementation classes.
- The AutoConfiguration.imports file.

Benefits:

- Plain Java applications or other frameworks can still use the contract.
- Integrations for multiple platforms can share the API.
- Spring Boot is not pulled into every consumer that only needs interfaces/models.
- The API changes less frequently than implementations, making binary compatibility easier to maintain.

Avoid exposing vendor SDK details in the public API if you want to allow swapping vendors. For example, if AcmeClient accepts VendorSdkRequest, every consumer of the API becomes coupled to the SDK. Use request/response types owned by your library and convert to vendor types in an adapter.

### 2.2. The API module does not activate beans by itself

Simply adding the acme-api dependency does not make Spring Boot create an AcmeClient. The API only provides Java types. To get beans automatically, the application needs the artifact containing auto-configuration and Spring Boot's discovery mechanism.

### 2.3. When is a separate API module unnecessary?

If a library is small, has only a single implementation, and the API is not used standalone, splitting out an extra artifact can increase build, versioning, and release overhead. In that case, interfaces/models can live in the autoconfigure module or the main library module.

Split out a separate API when:

- Multiple integrations implement the same contract.
- Other applications need to compile against only the interfaces/models.
- You want to keep the API framework-neutral with respect to Spring Boot.
- You want to manage API compatibility and releases independently.

## 3. Autoconfigure module: bridging the API to Spring Boot

The autoconfigure module contains **code for registering and configuring implementations** so Spring Boot applications can use the library conveniently.

Typical contents include:

- @AutoConfiguration classes.
- Default implementations of the API.
- @ConfigurationProperties and defaults.
- Conditions such as @ConditionalOnClass, @ConditionalOnProperty, @ConditionalOnBean, @ConditionalOnMissingBean.
- Callbacks/customizers for user extension.
- Sub-configurations for optional integrations.
- Resource META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports.
- Auto-configuration condition metadata and configuration properties metadata generated by annotation processors.

### 3.1. Example properties and default implementation

Assuming the API module already has AcmeClient, the autoconfigure module defines properties:

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

A simple default implementation can use Java HttpClient:

~~~java
package com.acme.autoconfigure;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeException;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;

final class DefaultAcmeClient implements AcmeClient {

    private final URI endpoint;
    private final HttpClient httpClient;

    DefaultAcmeClient(URI endpoint) {
        this.endpoint = endpoint;
        this.httpClient = HttpClient.newHttpClient();
    }

    @Override
    public AcmeResponse send(AcmeRequest request) {
        try {
            HttpRequest httpRequest = HttpRequest.newBuilder(endpoint)
                    .header("Content-Type", "text/plain; charset=UTF-8")
                    .POST(HttpRequest.BodyPublishers.ofString(request.message()))
                    .build();

            HttpResponse<String> response = httpClient.send(
                    httpRequest,
                    HttpResponse.BodyHandlers.ofString());

            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw new AcmeException(
                        "Acme service returned HTTP " + response.statusCode(),
                        null);
            }

            return new AcmeResponse(response.body(), true);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new AcmeException("Acme request was interrupted", ex);
        } catch (java.io.IOException ex) {
            throw new AcmeException("Could not call Acme service", ex);
        }
    }

    @Override
    public URI endpoint() {
        return endpoint;
    }
}
~~~

This illustrative implementation compiles on Java 17+ using standard Java APIs and the API module above. The actual HTTP protocol of the Acme service is hypothetical; in a real implementation, you must determine path, authentication, request/response format, status mapping, and timeouts per the service's API.

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

The @ConditionalOnMissingBean condition allows the application to provide its own implementation. The class-level @ConditionalOnProperty condition specifies that acme.enabled=false disables the core branch; when the key is not declared, it is default-on via matchIfMissing=true.

### 3.2. Auto-configuration must be registered

Spring Boot 3.x discovers auto-configurations from the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Each line is the fully qualified name of an auto-configuration class. When an application uses @SpringBootApplication or @EnableAutoConfiguration, Boot looks for this file in JARs on the classpath, then processes candidates by conditions and order.

**The imports file must be inside the autoconfigure JAR**, not only in the starter aggregator. The starter usually contains no configuration code and does not need to re-list classes itself. When building, verify the actual resources inside the published artifact.

Auto-configurations should be top-level classes, not targets of component scanning. Do not use broad @ComponentScan inside auto-configuration to locate library classes; use explicit @Import for supporting configurations when needed.

### 3.3. Dependencies of autoconfigure

The autoconfigure module typically needs:

- The API module.
- spring-boot-autoconfigure.
- Required runtime libraries to create default implementations.
- spring-boot-configuration-processor to generate metadata for configuration keys.
- spring-boot-autoconfigure-processor to generate condition metadata if the project needs optimized auto-configuration filtering.

If public method/constructor signatures in the autoconfigure module expose API types to consumers, declare the API dependency appropriately (e.g., Gradle api(project(":acme-api"))). If a dependency is strictly an internal detail, use implementation when the dependency graph allows.

For libraries with optional dependencies, clearly decide which artifact's runtime graph owns them. An optional SDK should not be pulled into every application that only uses core.

## 4. Starter module: bundling dependencies for a one-line user addition

The starter has a different purpose from autoconfigure: **gathering the necessary dependencies for an intentional user experience**.

A standard starter is typically a nearly empty JAR:
- Contains no service implementations.
- Contains no @AutoConfiguration.
- Needs no component scanning.
- Contains no AutoConfiguration.imports file if it provides no auto-configuration.
- Primarily declares dependencies on autoconfigure and required libraries.

Example of what the user adds:

~~~kotlin
dependencies {
    implementation("com.acme:acme-spring-boot-starter:1.2.0")
}
~~~

The starter may pull in:
- acme-spring-boot-autoconfigure.
- acme-api via transitive dependency from autoconfigure.
- spring-boot-starter if the starter needs to ensure the core Spring Boot starter is present.
- HTTP clients or foundational dependencies that the core library actually needs.

Once the starter is added, the user can configure:

~~~yaml
acme:
  enabled: true
  endpoint: https://tenant.example
~~~

Then inject the API:

~~~java
@Service
class NotificationService {

    private final AcmeClient acmeClient;

    NotificationService(AcmeClient acmeClient) {
        this.acmeClient = acmeClient;
    }

    AcmeResponse notify(String message) {
        return acmeClient.send(new AcmeRequest(message));
    }
}
~~~

Users **do not need** to manually @Import(AcmeAutoConfiguration.class) or @ComponentScan("com.acme.autoconfigure"). Boot automatically finds the imports file in the autoconfigure JAR.

### 4.1. Must a starter always be an empty JAR?

By Spring Boot convention, a starter is a dependency aggregator, usually a nearly empty JAR. The artifact name and POM/build file describe the selected dependencies.

You can merge autoconfigure and starter if a library is small and lacks many optional features. In that case, one artifact both contains auto-configuration code and supplies the needed dependencies. However, if you want applications to be able to use autoconfigure alone to pick dependencies themselves, or to create multiple starters with different combinations, keeping the two modules separate is more flexible.

## 5. Comparing responsibilities and artifacts

| Criterion | API module | Autoconfigure module | Starter module |
| --- | --- | --- | --- |
| Purpose | Public contract | Automatically create/configure beans | Bundle dependencies for consumers |
| Contains interfaces/models | Yes | May reference them | Should not |
| Contains default implementations | No | Yes | No |
| Contains @AutoConfiguration | No | Yes | Usually no |
| Contains @ConfigurationProperties | Usually no | May contain | No |
| Contains AutoConfiguration.imports | No | Yes | Usually no |
| Depends on Spring Boot | Preferably no | Yes | Usually indirectly |
| Usable standalone | Usable by plain Java/other frameworks | Usable when selecting dependencies manually | Intended for Spring Boot integration experience |
| Role for users | Compile-time contract | Provides automatic behavior | Single dependency to add |

Three modules are not three layers that must always exist. Split according to actual usage needs and the dependency graph.

## 6. Designing a unidirectional dependency graph

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
Consuming Application
~~~

Arrows depict dependencies from bottom to top in the diagram: autoconfigure depends on API; starter depends on autoconfigure; the application depends on starter.

Avoid creating cycles such as:

~~~text
acme-api -> autoconfigure -> starter -> acme-api
~~~

The API must not know about the starter, and autoconfigure should not depend on the starter. The starter is the outermost layer aggregating existing components.

### 6.1. When to separate optional integrations?

Suppose Acme also has a Vendor codec, needed only by certain applications. You can create:

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

The core starter does not pull in the Vendor SDK. The codec starter represents an opt-in choice, which can depend on the core starter, codec autoconfigure, and SDK.

In optional auto-configurations, use @ConditionalOnClass at the **configuration class level** if method signatures reference vendor types that might be missing. If a client bean created by the SDK is required, add @ConditionalOnBean. When allowing applications to replace the adapter, use @ConditionalOnMissingBean.

## 7. Gradle multi-project example

### 7.1. Directory structure

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

    implementation(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    implementation("org.springframework.boot:spring-boot-autoconfigure")

    annotationProcessor("org.springframework.boot:spring-boot-configuration-processor")
    annotationProcessor("org.springframework.boot:spring-boot-autoconfigure-processor")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Here:
- api(project(":acme-api")) because the API is the contract used by consumers.
- implementation(spring-boot-autoconfigure) provides annotations and runtime support for auto-configuration.
- The two annotation processors generate metadata at compile time.
- Autoconfigure tests use spring-boot-starter-test.

### 7.5. Starter build.gradle.kts

~~~kotlin
plugins {
    id("java-library")
}

dependencies {
    api(platform("org.springframework.boot:spring-boot-dependencies:3.3.13"))
    api(project(":acme-spring-boot-autoconfigure"))
    api("org.springframework.boot:spring-boot-starter")
}
~~~

The starter needs no Java sources. Using api dependencies ensures transitive propagation to applications consuming the starter; api/implementation can be adjusted to match your contract and publishing setup.

**Version:** the example uses Spring Boot 3.3.13 as an illustrative BOM. In a published library, ensure dependency versions resolve consistently and do not force a host application onto an unintended Spring Boot version. You can move the BOM version into a version catalog or root dependency management.

## 8. Maven multi-module uses the same boundaries

In Maven, the root project typically uses pom packaging and lists three modules:

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
        <version>1.2.0</version>
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

The starter POM gathers autoconfigure and the core starter:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-spring-boot-autoconfigure</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

The snippets above cover core dependencies/modules, not a complete publishable POM. A real project must declare groupId, artifactId, version, repositories, compiler release, test plugins, and dependency management. Use the Spring Boot BOM to manage compatible Spring Boot library versions; avoid scattering independent version declarations across modules.

### 8.1. Do you need a separate BOM for your library?

If there are only a few artifacts and all are released with the same version, dependency management in the parent/Spring Boot BOM may suffice. If the library has many modules or multiple optional starters that users choose independently, you can publish an acme-bom to manage versions consistently:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-api</artifactId>
            <version>1.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-autoconfigure</artifactId>
            <version>1.2.0</version>
        </dependency>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot-starter</artifactId>
            <version>1.2.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

A BOM manages versions; it does not automatically add dependencies to the classpath. Consumers still have to declare the starter or API artifacts they need.

## 9. Consumer experience: add starter, configure, inject API

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

    AcmeResponse notify(String message) {
        return acmeClient.send(new AcmeRequest(message));
    }
}
~~~

Users only need to know the public API and properties. They do not need to know the DefaultAcmeClient class, create the default bean manually, or manually import the auto-configuration.

To replace the implementation:

~~~java
@Configuration(proxyBeanMethods = false)
class MyAcmeConfiguration {

    @Bean
    AcmeClient myAcmeClient() {
        return new MyAcmeClient();
    }
}
~~~

@ConditionalOnMissingBean(AcmeClient.class) in the auto-configuration causes the default bean to back off when the user bean is processed first. This customization contract should be documented.

## 10. Testing at the right module boundaries

You should not rely solely on a single test booting the whole application to conclude every module is correct. Each module needs appropriate tests:

| Module | Recommended tests |
| --- | --- |
| API | Compile contract, model behavior, compatibility of public types |
| Autoconfigure | ApplicationContextRunner: defaults, property overrides, disable, custom bean back-off, classpath conditions |
| Starter | Dependency graph, imports resource present in JAR, consumer smoke test adding only the starter |
| Optional integration | SDK present/missing, client bean present/missing, custom adapter override |

### 10.1. Testing auto-configuration with ApplicationContextRunner

The example below is **a complete test file** verifying defaults, property overrides, feature disabling, and user-provided beans. In production, the API/properties/auto-configuration reside in their respective modules as described.

**File:** src/test/java/com/acme/autoconfigure/AcmeAutoConfigurationTest.java

~~~java
package com.acme.autoconfigure;

import java.net.URI;

import com.acme.api.AcmeClient;
import com.acme.api.AcmeRequest;
import com.acme.api.AcmeResponse;
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
        @Override
        public AcmeResponse send(AcmeRequest request) {
            return new AcmeResponse("test-id", true);
        }
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

The test file uses AcmeClient, AcmeRequest, and AcmeResponse from the API module. The test implementation returns a mock response; it only checks binding and bean conditions, without sending HTTP requests.

### 10.2. Dependencies and test execution commands

In the autoconfigure module, the Gradle test dependency can be:

~~~kotlin
dependencies {
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

Run at the multi-project root:

~~~bash
# Linux/macOS
./gradlew :acme-spring-boot-autoconfigure:test

# Windows
gradlew.bat :acme-spring-boot-autoconfigure:test
~~~

**Expected result:** four tests PASS:
- Without acme.enabled declared: the default client appears.
- With acme.endpoint set: the endpoint is bound.
- With acme.enabled=false: no default client exists.
- With a user bean present: the auto-configuration does not create a second default.

Assertions inspect the context and do not print fixed application stdout. Console output depends on Gradle/JUnit logging.

### 10.3. Verifying the actual starter JAR

The ApplicationContextRunner above loads the auto-configuration directly using AutoConfigurations.of(...); therefore, it verifies bean logic but **does not prove** that the imports resource is packaged properly in the JAR.

After building:

~~~bash
# Inspect autoconfigure JAR contents
jar tf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar

# Check that the imports file was packaged
jar xf acme-spring-boot-autoconfigure/build/libs/acme-spring-boot-autoconfigure-1.2.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Open the extracted resource and confirm it contains the line:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

Then create a sample consumer that only adds acme-spring-boot-starter and run a startup smoke test. This verifies discovery and transitive dependencies in an environment closest to the end user.

## 11. Artifact naming and version management

A suitable convention for a library is:

~~~text
com.acme:acme-api
com.acme:acme-spring-boot-autoconfigure
com.acme:acme-spring-boot-starter
com.acme:acme-codec-autoconfigure
com.acme:acme-spring-boot-starter-codec
~~~

Spring Boot recommends that a library's own module names **do not start with spring-boot**, to avoid confusion with official Spring Boot modules. Use your library's brand name or namespace.

### Versioning

If modules are released together, they should share the same version, e.g., 1.2.0. When bumping versions:
- API changes may be breaking changes for compile-time consumers.
- Renaming properties or changing defaults may be breaking behavior changes.
- Renaming auto-configuration classes/packages can affect before/after ordering, exclusions, and imports metadata.
- A starter adding new dependencies can alter the application's runtime classpath.
- An optional starter adding a large SDK or one with a different license must be clearly documented.

Avoid letting acme-api:1.1.0 and acme-spring-boot-autoconfigure:1.2.0 be pulled into the same application if the two versions are incompatible. Use a synchronized parent version or an Acme BOM to manage versions.

### Spring Boot compatibility

Libraries should publish their supported Spring Boot version range. A starter should not arbitrarily force a newer Spring Boot version than the one the application uses. Let users manage versions via the Spring Boot BOM/plugin; build the library against supported versions and run CI against the committed compatible versions.

## 12. Common mistakes when splitting modules

1. **Putting @AutoConfiguration in the API module.** The API becomes coupled to Spring Boot even when consumers only need contracts; move auto-configuration to a separate module.
2. **Putting implementations in the starter.** The starter becomes a home for logic and is hard to reuse; keep implementations in the library/autoconfigure module.
3. **Thinking the starter creates beans itself.** The starter only brings dependencies onto the classpath; auto-configuration registers the beans.
4. **Placing the imports file in the starter instead of autoconfigure.** Boot cannot find the file in the artifact that actually holds the configuration, or the file gets omitted during packaging.
5. **Forgetting the imports file.** The auto-configuration class is in the JAR but never becomes a candidate; add its fully qualified name to the standard resource.
6. **Using component scanning to discover auto-configurations.** This breaks discovery/ordering and risks scanning unintended classes; use the imports file.
7. **Creating circular dependencies.** API depends on autoconfigure or starter; keep the direction API → autoconfigure → starter in terms of upward dependency.
8. **Core starter pulling optional SDKs.** Applications needing only core get unwanted dependencies; extract optional integrations and separate starters.
9. **Over-splitting modules with no clear boundary.** Increases versioning/publishing overhead; merge when the API is not used standalone and has no optional flavors.
10. **Not publishing a clear API contract.** Consumers end up importing implementation classes; expose only the necessary interfaces/models.
11. **API containing vendor types.** Every consumer is locked into the SDK; write adapters in an integration module.
12. **Not checking transitive dependencies.** A starter may miss the core starter or pull wrong versions; inspect the dependency insight/tree.
13. **Not checking published artifacts.** Sources have the right resources, but the JAR lacks imports/metadata; inspect the actual JAR.
14. **Using module names starting with spring-boot.** Causes confusion with official modules; use a dedicated name such as acme-spring-boot-starter.
15. **Testing only auto-config directly without testing the consumer starter.** Logic is sound, but the starter may miss dependencies or resources; add a smoke test with the published/locally-published starter.

## 13. Pre-release checklist

### API
- [ ] Public interfaces/models/exceptions are stable and documented.
- [ ] Does not depend on Spring Boot if unnecessary.
- [ ] Does not expose implementations or optional SDK types.
- [ ] API compatibility has been verified.

### Autoconfigure
- [ ] Has @AutoConfiguration and appropriate conditions.
- [ ] Default beans have @ConditionalOnMissingBean when overrides are allowed.
- [ ] Properties have a dedicated namespace, clear types, and clear defaults.
- [ ] Imports file is in the right JAR and lists all classes.
- [ ] Optional classes are guarded at the class level.
- [ ] Annotation processors are configured if metadata is needed.

### Starter
- [ ] Pulls only dependencies genuinely needed for the default use case.
- [ ] Contains no duplicate bean/auto-configuration logic.
- [ ] Includes core spring-boot-starter directly or transitively when needed.
- [ ] Optional features are split into separate starters where appropriate.
- [ ] Dependency versions are managed consistently.

### Release testing
- [ ] API module compiles/tests independently.
- [ ] Autoconfigure tests defaults, overrides, disable, and conditions.
- [ ] Imports/metadata verified inside the JAR.
- [ ] Consumer smoke test adding only the starter.
- [ ] Dependency tree does not pull unwanted optional SDKs.

## 14. Self-check questions

**Question 1.** A user only needs the AcmeClient interface, without Spring Boot. Which module should they depend on?

**Answer:** The API module. No need to pull in auto-configuration or the starter.

**Question 2.** Which module contains AcmeAutoConfiguration and AutoConfiguration.imports?

**Answer:** The Autoconfigure module. This is the artifact holding configuration code and the resource for Spring Boot discovery.

**Question 3.** Does the starter create the AcmeClient bean itself?

**Answer:** No. The starter puts autoconfigure and required dependencies onto the classpath; the auto-configuration inside the JAR registers the bean.

**Question 4.** When there is an optional codec SDK, should it be included in the core starter?

**Answer:** No, if core users do not need the codec. Create a separate optional integration/autoconfigure and starter for users to opt into.

**Question 5.** Why inspect the JAR after building even if ApplicationContextRunner tests already pass?

**Answer:** Runner tests load classes directly and do not prove that the imports resource is inside the JAR or that the starter's transitive dependencies are correct. You must verify the artifact and a sample consumer.

## 15. Takeaways when designing a library

- **API** defines the contract consumers program against directly.
- **Autoconfigure** connects the contract to Spring Boot: properties, default implementations, conditions, and imports metadata.
- **Starter** provides a convenient dependency set so applications can enable the library with a single declaration.

Dependencies should flow unidirectionally: API at the bottom, autoconfigure depending on API, and starter depending on autoconfigure plus required runtime dependencies. When optional features exist, create separate integrations/starters so core does not pull unnecessary SDKs.

Splitting into three artifacts is not mandatory for every library. If the API is not used standalone or the library is very simple, you can merge the API into autoconfigure and/or merge autoconfigure with the starter. Split when boundaries help consumers pick the right dependencies, keep the API stable, and make activation/customization contracts clear.

### Official Spring Boot documentation

- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — @AutoConfiguration Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
