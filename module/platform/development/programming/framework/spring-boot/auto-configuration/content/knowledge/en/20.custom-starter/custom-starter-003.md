# Third-Party Starter Naming Conventions and Avoiding Spring Boot Namespace Collisions

## 1. Why Design Starter Names and Namespaces From the Beginning?

A starter helps an application add a single dependency to receive the libraries, auto-configuration, and default configuration required for a technology. When building a starter for your own library, developers need to name it so users recognize **the provider and the capability**, while ensuring users do not confuse a third-party starter with an official Spring Boot starter.

Spring Boot reserves the `spring-boot` module prefix for official artifacts. The Spring Boot 3.3 documentation specifies: **third-party starters must not start their module name with `spring-boot`, even when using a different Maven `groupId`**. The standard convention is to put the project or brand name first, followed by `-spring-boot-starter`.

For example, a hypothetical library named `acme` should use:

- `com.acme:acme-spring-boot` — the module containing integration APIs and auto-configuration classes.
- `com.acme:acme-spring-boot-starter` — the starter module bundling the required dependencies.
- `com.acme:acme-spring-boot-starter-test` — the test-support starter if the project provides its own test suite.

Do not name a third-party artifact `spring-boot-starter-acme` or `spring-boot-acme-starter`. Changing `groupId` to `com.acme` does not make a name starting with `spring-boot` compliant.

Beyond the artifact name, the library also needs its own **Java package** and its own **configuration namespace**. These three scopes are related but serve different purposes:

| Scope | Recommended example | Avoid using |
|---|---|---|
| Maven/Gradle artifact | `acme-spring-boot-starter` | `spring-boot-starter-acme` |
| Java package | `com.acme.report.autoconfigure` | `org.springframework.boot.autoconfigure.acme` |
| Configuration property prefix | `acme.report` | `spring.acme.report`, `server.acme`, `management.acme` |

The goal is for users to know precisely which library owns the module, package, and configuration keys.

## 2. Third-Party Artifact Naming Rules

### 2.1. The Prefix Belongs to the Project or Provider

Official starters follow the form `spring-boot-starter-*`. Spring Boot reserves that convention for its own artifacts. Third-party starters typically start with the project name:

```text
thirdpartyproject-spring-boot-starter
acme-spring-boot-starter
mycompany-observability-spring-boot-starter
```

Names should:

- Start with the brand, project name, or organization that owns the library.
- Describe Spring Boot integration using the `-spring-boot` or `-spring-boot-starter` suffix.
- Stay consistent across the auto-configuration, starter, and test starter modules.
- Be short, stable, and independent of an internal implementation likely to change.

| Module name | Assessment | Reason |
|---|---|---|
| `acme-spring-boot-starter` | **Recommended** | Project name comes first; follows third-party convention |
| `acme-spring-boot` | **Recommended** | Auto-configuration module per Spring Boot examples |
| `acme-spring-boot-starter-test` | **Recommended** | Test starter preserves the same naming namespace |
| `spring-boot-starter-acme` | **Avoid** | Starts with the prefix reserved for official starters |
| `spring-boot-acme-starter` | **Avoid** | Still starts with `spring-boot` |
| `acme-starter` | Usable but less clear | Does not clearly indicate Spring Boot integration |
| `starter-acme-spring` | Unclear | Does not follow a recognizable convention |

### 2.2. `groupId` and `artifactId` Are Not the Same Thing

A Maven coordinate has the form:

```text
groupId:artifactId:version
```

Example:

```text
com.acme:acme-spring-boot-starter:1.0.0
```

- `groupId` identifies the publishing namespace of the artifact, usually based on a domain/organization controlled by the developer.
- `artifactId` identifies the specific module name within that group.
- `version` identifies the released version.

Spring Boot emphasizes the rule that a module name **must not start with `spring-boot` even when the Maven `groupId` differs**. Therefore, do not use `org.example:spring-boot-starter-acme` on the grounds that `groupId` already distinguishes the provider.

With Gradle, the same idea is expressed via coordinates:

```groovy
dependencies {
    implementation 'com.acme:acme-spring-boot-starter:1.0.0'
}
```

When publishing, keep `groupId` and the project name stable. Renaming an artifact after users already depend on it can break resolution of old coordinates and force users to update dependencies.

## 3. Choosing the Right Module Structure

The Spring Boot documentation describes two typical modules:

1. An auto-configuration module, e.g., `acme-spring-boot`, containing integration APIs and auto-configuration classes.
2. A starter module, e.g., `acme-spring-boot-starter`, bundling the auto-configuration module along with the library and commonly needed dependencies so users only need to add one dependency.

Reference structure:

```text
acme-parent/
├── acme-core/
│   └── Spring-independent API and business logic
├── acme-spring-boot/
│   ├── Spring Boot integration API
│   ├── ReportAutoConfiguration.java
│   ├── ReportProperties.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── acme-spring-boot-starter/
│   └── pom.xml / build.gradle
└── acme-spring-boot-starter-test/
    └── test fixtures and testing dependencies (if needed)
```

Module names and count depend on the library's complexity:

| Case | Suitable structure |
|---|---|
| Multiple optional features or multiple integration paths | Separate the auto-configuration module and starter |
| Small integration with no optional dependencies | Can combine auto-configuration into `acme-spring-boot-starter` |
| Shared test fixtures or integration test helpers | Add `acme-spring-boot-starter-test` |
| API/business logic usable outside Spring | Separate `acme-core` to avoid forcing Spring Boot onto the core module |

Separating modules gives users choices. One application can depend solely on the auto-configuration module to pick dependencies itself; another uses the starter to get the vendor-recommended default dependency set.

### 3.1. The Auto-Configuration Module

The `acme-spring-boot` module typically contains:

- `@AutoConfiguration` classes.
- `@ConfigurationProperties` and configuration types.
- Callbacks/interfaces allowing component initialization customization.
- Classpath, property, bean, or resource conditions.
- Metadata supporting IDEs and auto-configuration filtering.
- The `AutoConfiguration.imports` file so Spring Boot finds the configuration.

It is **not** a module that bundles all runtime dependencies for users. Optional integration libraries should be declared in a way that does not force every application to install them.

### 3.2. The Starter Module

A starter is usually a JAR nearly empty of source code. Its main job is declaring dependencies:

- The library's auto-configuration module.
- Foundational libraries needed by the integration.
- Spring Boot starters or related starters required.
- Default dependencies genuinely useful for common use cases.

Do not include every optional integration in the starter just because it might be useful to some users. Extra dependencies bloat the classpath, increase conflict risks, and may cause unintended auto-configuration activation.

Spring Boot requires a starter to reference the core `spring-boot-starter` directly or indirectly. If the starter already depends on another starter that pulls in the core starter, there is no need to add it redundantly.

### 3.3. Test Starter

If the library provides testing support, follow the same naming rule:

```text
acme-spring-boot-starter-test
```

This module can contain test fixtures, mocks, alternative auto-configurations, or test-only dependencies. Do not put test helpers in the runtime starter if production applications do not need them.

## 4. Maven Multi-Module Example

A parent POM can declare modules and manage the Spring Boot version using a BOM:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <modules>
        <module>acme-core</module>
        <module>acme-spring-boot</module>
        <module>acme-spring-boot-starter</module>
    </modules>

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
</project>
```

This is an illustrative parent POM; real projects can use `spring-boot-starter-parent` or a dedicated BOM per build policy. Do not manually specify individual Spring Framework versions when the Spring Boot BOM already manages compatible versions.

### 4.1. POM for the Auto-Configuration Module

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>acme-spring-boot</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-core</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>1.0.0</version>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
        </dependency>
    </dependencies>
</project>
```

`acme-client` is an example of an optional client library. Declaring `optional` in Maven means this dependency is not automatically propagated to every application depending solely on the auto-configuration module. The starter module can explicitly add `acme-client` as a default runtime dependency.

For auto-configurations with classpath conditions, isolate methods referencing the optional client so that when the client is absent, the JVM does not eagerly load the library's types before the classpath condition takes effect.

### 4.2. POM for the Starter

```xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.acme</groupId>
        <artifactId>acme-parent</artifactId>
        <version>1.0.0</version>
    </parent>

    <artifactId>acme-spring-boot-starter</artifactId>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-spring-boot</artifactId>
            <version>1.0.0</version>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-client</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
```

The starter does not need Java classes if its sole job is bundling dependencies. It can include a POM and a usage README. When adding other dependencies, include only what typical users need for the integration to run.

### 4.3. Application Consuming the Starter

The application only needs to declare the starter coordinate:

```xml
<dependency>
    <groupId>com.acme</groupId>
    <artifactId>acme-spring-boot-starter</artifactId>
    <version>1.0.0</version>
</dependency>
```

The application receives the auto-configuration module and default dependencies through the starter's dependency relationships. Users do not need to manually declare individual JARs if they choose this starter.

## 5. Gradle Example for the Same Structure

If the project uses Gradle, you can keep the same module naming conventions:

```groovy
// settings.gradle
rootProject.name = 'acme-parent'

include 'acme-core'
include 'acme-spring-boot'
include 'acme-spring-boot-starter'
```

Auto-configuration module:

```groovy
// acme-spring-boot/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    api 'org.springframework.boot:spring-boot-autoconfigure'
    implementation project(':acme-core')

    compileOnly 'com.acme:acme-client:1.0.0'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
```

Starter module:

```groovy
// acme-spring-boot-starter/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    implementation project(':acme-spring-boot')
    implementation 'com.acme:acme-client:1.0.0'
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

This is a Gradle sample for a project that already configured Spring Boot dependency management/BOM. `compileOnly` for the client in the auto-configuration module allows the module to compile without forcing the client dependency as a shared runtime dependency; the starter adds the client at runtime for the default use case. Adjust `api`/`implementation` depending on whether types from a dependency appear in the public API.

You do not need to declare individual versions for every Spring Boot dependency when a BOM/plugin already manages versions. Choose a Spring Boot baseline that the library supports and test against all published compatible versions.

## 6. Java Packages Must Belong to the Provider's Namespace

The artifact name does not dictate the Java package. A module named `acme-spring-boot` should place classes in a package owned by the organization, for example:

```text
com.acme.report
com.acme.report.core
com.acme.report.autoconfigure
com.acme.report.autoconfigure.properties
```

An auto-configuration can look like:

```java
package com.acme.report.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(ReportClient.class)
@EnableConfigurationProperties(ReportProperties.class)
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    ReportService reportService(ReportClient client, ReportProperties properties) {
        return new DefaultReportService(client, properties);
    }
}
```

This is an illustrative configuration snippet; `ReportClient`, `ReportProperties`, `ReportService`, and `DefaultReportService` belong to the `com.acme` library and must be defined accordingly.

Do not place third-party library classes into Spring-owned packages such as `org.springframework.boot` or `org.springframework.boot.autoconfigure`. Dedicated packages avoid class name collisions, avoid depending on internal packages, and clarify API ownership.

### Auto-Configuration Is Not a Regularly Scanned Component

Spring Boot locates auto-configuration through the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

In the `acme-spring-boot` module, example file contents:

```text
com.acme.report.autoconfigure.ReportAutoConfiguration
```

Each line is an FQCN of an auto-configuration. Multiple classes can be listed, one per line. For non-top-level nested classes, use the `$` symbol between the enclosing class name and the nested class name.

Spring Boot requires auto-configurations to be loaded via the imports file; **do not use component scanning as the mechanism to discover auto-configurations**. Auto-configurations should also not enable component scanning themselves to find other components. Use explicit `@Import` when additional configurations need to be registered.

Distinguish between them:

- Application component scanning finds `@Component` classes within scanned packages.
- `AutoConfiguration.imports` registers auto-configuration classes published by the library.
- `@Import` registers a specific configuration or component that an auto-configuration needs.

## 7. Configuration Properties Must Use a Library-Owned Prefix

If a starter provides configuration keys, define a dedicated prefix named after the project or organization:

```yaml
acme:
  report:
    enabled: true
    endpoint: https://reports.example.test
    timeout: 3s
```

Example properties class:

```java
package com.acme.report.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.report")
public class ReportProperties {

    /**
     * Whether the Acme report integration is enabled.
     */
    private boolean enabled = true;

    /**
     * Endpoint used to submit reports.
     */
    private URI endpoint;

    /**
     * Timeout for sending a report.
     */
    private Duration timeout = Duration.ofSeconds(3);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

The `acme.report` prefix belongs to the library. Do not use Spring Boot-owned namespaces such as:

- `spring.*`
- `server.*`
- `management.*`

Examples to avoid:

```yaml
spring:
  report:
    enabled: true

management:
  acme:
    endpoint: https://reports.example.test

server:
  acme:
    timeout: 3s
```

Even though these keys might technically bind, they intrude into Spring Boot's namespace or another feature group. Spring Boot may add keys in those namespaces in future releases; at that point the library could collide, be overridden, or change behavior unexpectedly.

**Practical rule:** every library key should start with a unique prefix controlled by the provider, such as `acme`, `mycompany.observability`, or `vendor.messaging`.

### 7.1. Key Names Should Be Stable and Meaningful

Group configuration by feature:

```yaml
acme:
  report:
    enabled: true
    endpoint: https://reports.example.test
    connect-timeout: 2s
    read-timeout: 5s
```

Use relaxed binding to map `connect-timeout` to the `connectTimeout` field. Avoid overly generic names like `enabled` at the application-wide root; the prefix identifies which feature owns the key.

### 7.2. Write Javadoc for Every Property

Spring Boot recommends documenting configuration keys with field Javadoc so metadata and IDEs can provide assistance. For boolean types, descriptions usually start with “Whether” or “Enable”; for collections, clarify the data format; for `Duration`, document the default unit if it differs from milliseconds.

Add the appropriate annotation processor to generate configuration metadata. When publishing, verify that `META-INF/spring-configuration-metadata.json` contains the right prefixes and descriptions. Metadata does not replace validation, but it improves configuration discoverability for users.

## 8. Optional Dependencies and Classpath Conditions

An auto-configuration module may integrate with an optional client library. If that dependency is pulled into every application, users may receive unnecessary JARs or trigger unintended auto-configurations.

Spring Boot advises marking dependencies on integration libraries as optional in the auto-configuration module so the module can be reused easily. The starter decides which dependencies should be present in the default bundle.

Example:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(ReportClient.class)
    @EnableConfigurationProperties(ReportProperties.class)
    static class ReportClientConfiguration {

        @Bean
        @ConditionalOnMissingBean
        ReportService reportService(
                ReportClient client,
                ReportProperties properties) {
            return new DefaultReportService(client, properties);
        }
    }
}
```

The nested configuration isolates methods referencing the optional client. Classpath conditions on the nested configuration prevent eager loading of method signatures using types absent from the runtime classpath. Ensure all classes and methods referencing the optional client reside inside the appropriately isolated scope.

Do not add optional dependencies to the default starter if most users do not need them. You can publish separate starters for those flavors, such as `acme-spring-boot-starter-reporting` or `acme-spring-boot-starter-cloud`, provided the project name still comes first.

## 9. Metadata and Required Files When Packaging

An auto-configuration module typically needs to pay attention to the following metadata files:

| File | Role |
|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Declares auto-configuration candidates for Spring Boot |
| `META-INF/spring-configuration-metadata.json` | Describes configuration properties for IDEs and tools |
| `META-INF/spring-autoconfigure-metadata.properties` | Condition metadata so Boot can filter out some auto-configurations early |

Not every project needs to hand-author all three files. Annotation processors and build tools can generate the corresponding metadata. When packaging the JAR, check that the required files are actually inside the published artifact.

For Gradle, the annotation processor for auto-configuration condition metadata can be declared as:

```groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
}
```

For configuration properties, use `spring-boot-configuration-processor` per the Spring Boot guide. The two processors serve different metadata; do not confuse the condition metadata file with the property description file.

## 10. Testing the Starter From the User's Perspective

Do not test only the auto-configuration module in isolation. An important integration test is creating a sample application depending solely on the **public starter**, then verifying:

1. The dependency graph includes the required libraries.
2. Auto-configuration is loaded from the imports file inside the JAR.
3. The dedicated property prefix binds.
4. Default beans are created when conditions match.
5. User beans can override the defaults.
6. Optional features do not activate when corresponding dependencies are absent.
7. No component scanning of internal library packages is required.

A basic test for properties/beans can use `ApplicationContextRunner`:

```java
package com.acme.report.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReportAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(ReportAutoConfiguration.class)
                    );

    @Test
    void bindsPropertiesUnderOwnedNamespace() {
        runner.withPropertyValues(
                        "acme.report.enabled=true",
                        "acme.report.endpoint=https://reports.example.test",
                        "acme.report.timeout=1500ms"
                )
                .run(context -> {
                    assertTrue(context.containsBean("reportProperties"));

                    ReportProperties properties =
                            context.getBean(ReportProperties.class);

                    assertEquals(
                            "https://reports.example.test",
                            properties.getEndpoint().toString()
                    );
                    assertEquals(
                            java.time.Duration.ofMillis(1500),
                            properties.getTimeout()
                    );
                });
    }
}
```

This test assumes `ReportAutoConfiguration` registers `ReportProperties` via `@EnableConfigurationProperties(ReportProperties.class)`. The test uses `ApplicationContextRunner` to verify binding; it does not prove the imports file was packaged properly, because the class is passed directly into `AutoConfigurations.of`.

To verify the real artifact, you need a consumer smoke test depending on the `com.acme:acme-spring-boot-starter` coordinate published or installed to a local repository. That consumer declares only the starter, does not directly declare the auto-configuration module, and does not component-scan the library package.

## 11. Pre-Release Artifact Verification Workflow

### 11.1. Verify Coordinate Names

Confirm the published artifacts follow the right form:

```text
com.acme:acme-spring-boot:1.0.0
com.acme:acme-spring-boot-starter:1.0.0
com.acme:acme-spring-boot-starter-test:1.0.0
```

No third-party module starts with `spring-boot`.

### 11.2. Verify the Dependency Graph

With Maven:

```bash
mvn dependency:tree
```

With Gradle:

```bash
./gradlew dependencies
```

Confirm the starter brings in the right auto-configuration module and required dependencies; optional dependencies are not pulled in unintentionally.

### 11.3. Inspect JAR Contents

After building:

```bash
jar tf acme-spring-boot-1.0.0.jar
jar tf acme-spring-boot-starter-1.0.0.jar
```

Inside the auto-configuration JAR, confirm the presence of:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-configuration-metadata.json
```

The imports file must contain the exact FQCN of the auto-configuration. The starter JAR may contain only Maven metadata and no Java classes; that is normal for a dependency-only starter.

### 11.4. Verify Packages and Configuration Namespace

- Library classes reside in an organization-owned package, e.g., `com.acme...`.
- No third-party classes appear in the `org.springframework.boot...` package.
- All properties start with `acme.` or a provider-controlled prefix.
- No custom properties sit under `spring.`, `server.`, or `management.`.
- Property fields have descriptions and corresponding metadata.

### 11.5. Verify With a Sample Application

Create a small consumer app adding only the starter dependency. Start the context, inspect the Condition Evaluation Report if needed, and verify beans/properties. This confirms the real user experience, including transitive dependencies and auto-configuration discovery.

## 12. Common Mistakes

1. **Naming it `spring-boot-starter-acme` after seeing official starters use that pattern.** That prefix is reserved for official artifacts. Change it to `acme-spring-boot-starter`.
2. **Assuming a distinct `groupId` permits starting the artifact with `spring-boot`.** The Spring Boot documentation explicitly states the module naming rule still applies even with a different `groupId`.
3. **Placing properties under `spring.acme`.** The `spring` prefix belongs to Spring Boot's namespace. Use `acme`.
4. **Placing properties under `management.acme` or `server.acme`.** Those two namespaces serve dedicated Spring Boot features; use the library's own prefix.
5. **Placing classes in `org.springframework.boot.autoconfigure`.** That package does not belong to third-party libraries. Create your own package like `com.acme.report.autoconfigure`.
6. **Using component scan to load auto-configuration.** Register the FQCN via `AutoConfiguration.imports`.
7. **Making the starter contain every possible dependency.** The starter should only include commonly needed dependencies; extract optional flavors when needed.
8. **Not marking optional client dependencies as optional in the auto-configuration module.** The integration module becomes hard to reuse and pulls unnecessary dependencies into applications.
9. **Forgetting the core starter.** A custom starter must reference `spring-boot-starter` directly or indirectly.
10. **Forgetting property metadata.** Users struggle to discover configuration keys in IDEs; add Javadoc and annotation processors.
11. **Testing only auto-configuration classes without testing the starter JAR.** Test runners can register classes directly and overlook a missing imports file; add a consumer smoke test.
12. **Not inspecting the JAR after publishing.** The imports file or metadata may be omitted from packaging even though the source tree looks right.

## 13. Third-Party Starter Design Checklist

| Item | Expected outcome |
|---|---|
| Module name | Starts with project/organization name, does not start with `spring-boot` |
| Maven groupId | Provider's namespace, e.g., `com.acme` |
| Auto-configuration module | `acme-spring-boot` |
| Starter module | `acme-spring-boot-starter` |
| Test starter (if any) | `acme-spring-boot-starter-test` |
| Java package | Dedicated namespace like `com.acme.report.autoconfigure` |
| Auto-configuration registration | `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` |
| Property prefix | Dedicated prefix like `acme.report` |
| Optional dependencies | Isolated/marked optional in the auto-configuration module |
| Core starter | Includes `spring-boot-starter` directly or indirectly |
| Property metadata | Has Javadoc and generated metadata |
| Verification | Dependency tree, JAR contents, and consumer smoke test all pass |

## 14. Takeaways

- Third-party starters **must not start their module name with `spring-boot`**, regardless of `groupId`.
- Put the project name first, e.g., `acme-spring-boot-starter`.
- Separate `acme-spring-boot` and `acme-spring-boot-starter` when distinguishing auto-configuration code from the dependency bundle.
- Use a provider-owned Java package, e.g., `com.acme...`.
- Register auto-configurations via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; do not use component scanning to discover auto-configurations.
- All configuration properties must sit under a dedicated namespace, e.g., `acme.report`; avoid `spring`, `server`, and `management`.
- A starter is a dependency descriptor; it should not contain unnecessary optional dependencies.
- Mark optional integration library dependencies in the auto-configuration module and let the starter decide default dependencies.
- Verify the published JAR and a real consumer application, not just the source code.

### Official Spring Boot 3.3 Documentation

- Build Systems — Starters and third-party naming rules: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Creating Your Own Auto-configuration — starter modules, naming, configuration keys, imports, and optional dependencies: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Configuration Metadata: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
