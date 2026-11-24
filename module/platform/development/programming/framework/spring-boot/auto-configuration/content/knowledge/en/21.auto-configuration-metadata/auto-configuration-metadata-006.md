# Third-Party Starter Naming Conventions and Avoiding Spring Boot Namespace Collisions

## 1. Namespaces Are Part of the Library Contract

A starter is the entry point for an application to add dependencies, receive foundational libraries, auto-configurations, and default configuration. If the artifact name, Java package, or property prefix collides with Spring Boot's namespaces, the library can cause confusion during setup and conflicts when Spring Boot adds new features.

There are three scopes to design distinctly:

1. **Publishing namespace:** Maven `groupId`, `artifactId`, and Gradle module name; determines dependency coordinates.
2. **Source code namespace:** Java packages containing APIs, implementations, and auto-configurations; determines class ownership.
3. **Configuration namespace:** prefixes in `application.yml` or `application.properties`; determines which library owns and can change properties.

Examples throughout this article use a hypothetical library Northstar Audit:

| Scope | Namespace owned by the library |
|---|---|
| Maven group | `io.northstar` |
| Auto-configuration artifact | `northstar-spring-boot` |
| Starter artifact | `northstar-spring-boot-starter` |
| Java package | `io.northstar.audit.autoconfigure` |
| Property prefix | `northstar.audit` |

Example names do not represent published artifacts. When applying them, substitute the domain, project name, and brand your organization actually owns.

## 2. Third-Party Module Naming Rules

Spring Boot reserves the `spring-boot` module prefix for official artifacts. **Third-party modules must not start with `spring-boot`, even if the Maven `groupId` is different.** If multiple vendors use this prefix, users have trouble identifying artifact origins and may mistake them for official Spring Boot support.

Names should start with the project or organization name, followed by the integration role:

~~~text
northstar-spring-boot
northstar-spring-boot-starter
northstar-spring-boot-starter-test
northstar-spring-boot-starter-messaging
~~~

Names to avoid:

~~~text
spring-boot-starter-northstar
spring-boot-northstar-starter
spring-boot-audit
~~~

Changing `groupId` to `io.northstar` does not make an artifact starting with `spring-boot` an appropriate name.

### 2.1. Distinguishing `groupId`, `artifactId`, and Module Name

Maven coordinates have the form:

~~~text
groupId:artifactId:version
~~~

Example:

~~~text
io.northstar:northstar-spring-boot-starter:1.2.0
~~~

- `groupId` identifies the publishing group, usually following a reversed domain controlled by the organization.
- `artifactId` identifies the specific module. For third-party starters, the name should start with the brand/project.
- `version` identifies the release and must be managed consistently across modules in the same release train.

Gradle also declares dependencies using similar coordinates:

~~~groovy
dependencies {
    implementation 'io.northstar:northstar-spring-boot-starter:1.2.0'
}
~~~

Do not confuse repository directory names with published coordinates. A project might use a `boot-integration` directory while the public artifact is `northstar-spring-boot`; users and repositories resolve the coordinates declared in the build.

### 2.2. Choosing Names by Module Count

| Design | Suggested Name | When Appropriate |
|---|---|---|
| Single module combining code and dependencies | `northstar-spring-boot-starter` | Small integration without many optional dependencies |
| Auto-configuration module | `northstar-spring-boot` | Want applications or other starters to reuse the integration |
| Module aggregating default dependencies | `northstar-spring-boot-starter` | Want users to declare only one dependency |
| Separate test support | `northstar-spring-boot-starter-test` | Have fixtures or alternative configurations used only in tests |
| Multiple independent flavors | `northstar-spring-boot-starter-messaging` | Can enable individual integrations via separate dependencies |

If a library has multiple flavors, names still start with `northstar`. Do not flip the order to `spring-boot-starter-northstar-messaging`.

## 3. Splitting Modules by Responsibility

Common structure:

~~~text
northstar-parent/
├── northstar-core/
│   └── Spring-independent API and business logic
├── northstar-spring-boot/
│   ├── NorthstarAuditAutoConfiguration.java
│   ├── AuditProperties.java
│   └── META-INF/spring/
│       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
├── northstar-spring-boot-starter/
│   └── pom.xml or build.gradle
└── northstar-spring-boot-starter-test/
    └── test fixtures and test auto-configuration
~~~

`northstar-core` does not need to depend on Spring Boot if the audit logic can be used in other Java applications. The `northstar-spring-boot` module contains the adapter for Spring Boot, while the starter aggregates commonly used dependencies.

### 3.1. Auto-Configuration Module

This module can contain:

- `@AutoConfiguration` classes and conditional nested configurations.
- `@ConfigurationProperties` classes along with metadata describing properties.
- Callbacks or extension points for applications to customize initialization.
- Classpath, bean, property, resource, and application-type conditions.
- `AutoConfiguration.imports` resource so Boot discovers configurations.
- Tests verifying conditions and default beans.

Keep integration library dependencies optional whenever possible. That way, applications using only part of the library do not have to bring along clients or SDKs for other features.

### 3.2. Starter Module

A starter is typically a JAR almost empty of source code. Its role is to declare dependencies so an application has all required components for common use cases:

- Northstar's auto-configuration module.
- The Northstar client library needed at runtime.
- Core Spring Boot starter, directly or through another starter.
- Foundational starters that the integration actually needs.

A starter should represent an intentional dependency selection. If the library has multiple optional integrations, create small flavor starters instead of pulling every SDK into a single starter.

### 3.3. Test Starter

A test starter can provide fixtures, fake clients, in-memory configurations, or helpers to test the integration. Test dependencies should not be pulled into production applications just because the application uses the runtime starter.

Test starter names still keep the brand first: `northstar-spring-boot-starter-test`.

## 4. Vendor-Owned Java Packages

Use packages following a reversed domain controlled by your organization. For this example:

~~~text
io.northstar.audit
io.northstar.audit.api
io.northstar.audit.core
io.northstar.audit.autoconfigure
io.northstar.audit.autoconfigure.properties
~~~

Do not put third-party classes into Spring-owned packages such as `org.springframework.boot` or `org.springframework.boot.autoconfigure`. Those packages belong to Spring; adding classes there can create classpath conflicts and couple code to internal details.

Organize packages by role:

- `api`: interfaces applications can call or implement.
- `core`: Spring-independent logic.
- `autoconfigure`: auto-configuration classes.
- `autoconfigure.properties`: property groups and configuration types if numerous enough.
- `internal`: non-public-API implementations, if clear separation is needed.

Avoid overly generic packages like `util` or `config` at the root of a large library. Specific packages help users understand which integration a class belongs to and reduce collision risk with other dependencies.

## 5. Registering Auto-Configuration via the Imports File

Spring Boot finds auto-configurations in published JARs through the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

In the `northstar-spring-boot` module, the file may contain:

~~~text
io.northstar.audit.autoconfigure.NorthstarAuditAutoConfiguration
io.northstar.audit.autoconfigure.NorthstarAuditMetricsAutoConfiguration
~~~

Each line is the fully qualified class name of an auto-configuration. Comments starting with `#` can be added. If an auto-configuration is a nested class, the class name uses `$` to separate the enclosing class and the nested class.

**Auto-configuration is only loaded when listed in the imports file.** Do not rely on component scanning to find it and do not enable component scanning from an auto-configuration to hunt for other components. If you need to register a specific configuration or component, use `@Import` with the target class.

Example:

~~~java
package io.northstar.audit.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Import;

@AutoConfiguration
@Import(AuditInfrastructureConfiguration.class)
public class NorthstarAuditAutoConfiguration {
}
~~~

`AuditInfrastructureConfiguration` is a specific configuration belonging to the same library. This clearly bounds the imported classes, helps control startup scope, and avoids accidentally scanning components in subpackages.

### 5.1. When Renaming or Moving Auto-Configurations

Auto-configuration names may be referenced in `before`, `after`, or exclusions of other applications. When you must change a published package or class name, Spring Boot supports the resource:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
~~~

Example mapping old name to new name:

~~~text
io.northstar.audit.autoconfigure.NorthstarAuditAutoConfiguration=io.northstar.audit.autoconfigure.core.NorthstarAuditAutoConfiguration
~~~

When using the replacements mechanism, update `AutoConfiguration.imports` to list only the replacement class. This resource helps Spring Boot handle references to the old class in ordering/exclusion metadata; it does not automatically replace Java imports or public APIs in application code. Changing public packages still requires its own compatibility and migration plan.

## 6. Property Prefixes Must Be Dedicated Namespaces

If a starter provides configuration, all keys should reside under a single prefix owned by the library. For example:

~~~yaml
northstar:
  audit:
    enabled: true
    endpoint: https://audit.example.test
    connect-timeout: 2s
    batch-size: 250
~~~

Namespaces such as `spring`, `server`, and `management` belong to Spring Boot. Do not place third-party library properties into these groups. Avoid examples like:

~~~yaml
spring:
  audit:
    enabled: true

server:
  northstar:
    endpoint: https://audit.example.test

management:
  northstar:
    batch-size: 250
~~~

Just because a property can technically bind does not mean the library should occupy that namespace. Spring Boot may expand its own configuration groups in a later release; library keys misplaced there could collide in name or change meaning.

### 6.1. Designing Stable Property Names

Use a meaningful hierarchy:

~~~text
northstar.audit.enabled
northstar.audit.endpoint
northstar.audit.connect-timeout
northstar.audit.batch-size
northstar.audit.include-principal
~~~

Some helpful rules:

- Use lowercase letters and hyphens in property names.
- Group keys by function; do not create a new prefix for every field.
- Use `Duration` for durations instead of unitless `long`.
- Use specific data types such as `URI`, `Duration`, `DataSize`, enums, and collections when appropriate.
- Set intentional defaults and document units explicitly when values do not use standard units.
- Do not use generic names like `enabled` at the application-wide root.

The property prefix is part of the starter's API. Once users have saved `northstar.audit.connect-timeout` in deployment configs, renaming the key can cause integrations to lose configuration after upgrading.

## 7. Example `@ConfigurationProperties` and Auto-Configuration

The properties class lives in its own package and has a library-owned prefix:

~~~java
package io.northstar.audit.autoconfigure;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "northstar.audit")
public class AuditProperties {

    /**
     * Whether the Northstar audit integration is enabled.
     */
    private boolean enabled = false;

    /**
     * Endpoint used to submit audit events.
     */
    private URI endpoint;

    /**
     * Timeout for establishing a connection to the audit service.
     */
    private Duration connectTimeout = Duration.ofSeconds(2);

    /**
     * Maximum number of events sent in one batch.
     */
    private int batchSize = 250;

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

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public int getBatchSize() {
        return batchSize;
    }

    public void setBatchSize(int batchSize) {
        this.batchSize = batchSize;
    }
}
~~~

This is a JavaBean properties class. Spring Boot Binder maps `connect-timeout` to `connectTimeout`. Field Javadocs are plain-text descriptions for the annotation processor to put into metadata; do not write Markdown or HTML in these descriptions.

An API interface can be defined in the core module:

~~~java
package io.northstar.audit.api;

public interface AuditService {
    void publish(String event);
}
~~~

Default implementation:

~~~java
package io.northstar.audit.autoconfigure;

import io.northstar.audit.api.AuditService;

final class DefaultAuditService implements AuditService {

    private final AuditProperties properties;

    DefaultAuditService(AuditProperties properties) {
        this.properties = properties;
    }

    @Override
    public void publish(String event) {
        // Send event using the client provided by the integration library.
        // Transport implementation depends on the actual client API.
    }
}
~~~

Auto-configuration registers properties and the default bean:

~~~java
package io.northstar.audit.autoconfigure;

import io.northstar.audit.api.AuditService;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@EnableConfigurationProperties(AuditProperties.class)
public class NorthstarAuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "northstar.audit",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnMissingBean(AuditService.class)
    AuditService auditService(AuditProperties properties) {
        return new DefaultAuditService(properties);
    }
}
~~~

This is a structural example; event sending needs to be wired to a real client. Two conditions are clear: the application must enable `northstar.audit.enabled=true`, and the library only creates the default bean when no `AuditService` is provided by the application.

## 8. Recording Metadata So IDEs Support Users

Spring Boot has two metadata types commonly used in an auto-configuration module:

| Resource | Purpose |
|---|---|
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Declares auto-configurations loaded by Boot |
| `META-INF/spring-configuration-metadata.json` | Describes properties, data types, groups, defaults, and hints for IDEs |
| `META-INF/spring-autoconfigure-metadata.properties` | Condition information helping Boot filter out inapplicable auto-configurations early |

The two metadata files do not replace the imports file. The imports file determines which classes are auto-configuration candidates; configuration metadata describes configuration keys; auto-configure metadata records conditions to assist early filtering.

### 8.1. Configuration Metadata Processor

Add `spring-boot-configuration-processor` as an annotation processor to generate `spring-configuration-metadata.json` from `@ConfigurationProperties` classes. Javadoc on fields is used as descriptions. For records, component descriptions should be placed in class-level Javadoc using `@param` tags.

Spring Boot recommends consistent descriptions:

- Booleans: start with “Whether” or “Enable”.
- Collections: state data format, e.g., “Comma-separated list”.
- Durations: use `Duration`; note the default unit if there is no suffix.
- Do not start with “The” or “A”.
- Do not repeat the default value in the description unless the default is decided at runtime.

### 8.2. Auto-Configuration Metadata Processor

`spring-boot-autoconfigure-processor` collects auto-configuration conditions and generates `spring-autoconfigure-metadata.properties`. When metadata is present, Spring Boot can filter out non-matching configurations early, reducing startup work.

This is optimization metadata and does not replace writing proper conditions. After building, verify the JAR contains the generated file and contents corresponding to actual classes.

## 9. Optional Dependencies and Keeping Starters Lean

Suppose Northstar has a core API and an optional HTTP client:

- The auto-configuration module needs to compile against the client type to declare beans.
- Applications using only the core part do not necessarily need the HTTP client.
- The standard starter can choose to include the HTTP client at runtime because that is the starter's default choice.

In Maven, the auto-configuration module can mark the client dependency as optional:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-audit-client</artifactId>
    <version>2.4.0</version>
    <optional>true</optional>
</dependency>
~~~

The starter can declare the client dependency as a regular runtime dependency:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-audit-client</artifactId>
    <version>2.4.0</version>
</dependency>
~~~

In Gradle, `compileOnly` can be used to compile the auto-configuration module against client types without making the client a default runtime dependency of that module; the starter adds the client via `implementation`.

When a client is optional, place methods whose signatures reference the client inside a nested configuration guarded by `@ConditionalOnClass`. Spring Boot reads condition metadata at the class level; a condition only on a `@Bean` method may arrive too late because the JVM already has to process method signatures. Splitting a nested configuration isolates optional types.

Do not pack every client, database driver, cloud SDK, or unnecessary integration into the default starter. If many users only need a subset, create flavor starters so they can pick appropriate dependencies.

## 10. Maven Structure Example

The parent POM can aggregate modules and import the Spring Boot BOM:

~~~xml
<project>
    <modelVersion>4.0.0</modelVersion>

    <groupId>io.northstar</groupId>
    <artifactId>northstar-parent</artifactId>
    <version>1.2.0</version>
    <packaging>pom</packaging>

    <properties>
        <java.version>17</java.version>
        <spring-boot.version>3.3.13</spring-boot.version>
    </properties>

    <modules>
        <module>northstar-core</module>
        <module>northstar-spring-boot</module>
        <module>northstar-spring-boot-starter</module>
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
~~~

This is an illustrative parent POM. Projects can also use `spring-boot-starter-parent`; the key is that all modules use the same chosen Spring Boot baseline.

The auto-configuration module has coordinates:

~~~xml
<artifactId>northstar-spring-boot</artifactId>
~~~

Main dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-core</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-audit-client</artifactId>
        <version>2.4.0</version>
        <optional>true</optional>
    </dependency>
</dependencies>
~~~

To generate metadata, configure Maven Compiler Plugin version 3.12.0 or higher with both annotation processors:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.12.1</version>
    <configuration>
        <release>17</release>
        <annotationProcessorPaths>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-autoconfigure-processor</artifactId>
                <version>3.3.13</version>
            </path>
            <path>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-configuration-processor</artifactId>
                <version>3.3.13</version>
            </path>
        </annotationProcessorPaths>
    </configuration>
</plugin>
~~~

The starter module has artifact ID `northstar-spring-boot-starter` and mainly contains dependencies:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-spring-boot</artifactId>
        <version>1.2.0</version>
    </dependency>

    <dependency>
        <groupId>io.northstar</groupId>
        <artifactId>northstar-audit-client</artifactId>
        <version>2.4.0</version>
    </dependency>
</dependencies>
~~~

A starter can be a JAR containing no Java classes. This is normal design: it exists to provide a curated set of dependencies. If the starter depends on another starter that already pulls in `spring-boot-starter`, there is no need to declare the core starter redundantly.

## 11. Gradle Structure Example

In `settings.gradle`:

~~~groovy
rootProject.name = 'northstar-parent'

include 'northstar-core'
include 'northstar-spring-boot'
include 'northstar-spring-boot-starter'
~~~

Auto-configuration module:

~~~groovy
// northstar-spring-boot/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    api platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    api 'org.springframework.boot:spring-boot-autoconfigure'

    implementation project(':northstar-core')
    compileOnly 'io.northstar:northstar-audit-client:2.4.0'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter module:

~~~groovy
// northstar-spring-boot-starter/build.gradle
plugins {
    id 'java-library'
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.13')
    implementation project(':northstar-spring-boot')
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'io.northstar:northstar-audit-client:2.4.0'
}
~~~

In Gradle, `compileOnly` does not mean the client is packaged into the starter. The starter needs to declare a runtime dependency if you want users adding only the starter to get the client. If a dependency type appears in a module's public API, consider `api` or `compileOnlyApi` according to the contract the module exposes.

## 12. Testing from Module to Published Starter

There are two different levels of testing.

### 12.1. Testing Auto-Configuration Directly

Use `ApplicationContextRunner` to verify:

- Does the property prefix bind properly?
- When `northstar.audit.enabled=false`, does the default bean stay absent?
- When the property is enabled, does the default bean appear?
- When the application provides its own `AuditService`, does auto-configuration back off?
- When the optional client library is absent, does configuration depending on the client avoid failing the context?

Basic configuration test example:

~~~java
package io.northstar.audit.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class NorthstarAuditAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    NorthstarAuditAutoConfiguration.class
                            )
                    );

    @Test
    void doesNotCreateServiceWhenDisabled() {
        runner.withPropertyValues("northstar.audit.enabled=false")
                .run(context ->
                        assertFalse(context.containsBean("auditService"))
                );
    }

    @Test
    void createsServiceWhenEnabled() {
        runner.withPropertyValues("northstar.audit.enabled=true")
                .run(context ->
                        assertTrue(context.containsBean("auditService"))
                );
    }
}
~~~

This example assumes the default implementation needs no external client and is declared right as the auto-configuration in section 7. For real configurations, add tests for bean override, invalid properties, and optional classpath using `FilteredClassLoader`.

### 12.2. Consumer Smoke Test for the Starter

Tests using `AutoConfigurations.of(NorthstarAuditAutoConfiguration.class)` register the class directly. Therefore, they **do not prove** the imports file was packaged or that the starter has the right transitive dependencies.

Create a small consumer application declaring only:

~~~xml
<dependency>
    <groupId>io.northstar</groupId>
    <artifactId>northstar-spring-boot-starter</artifactId>
    <version>1.2.0</version>
</dependency>
~~~

The consumer test should start Spring Boot normally, without directly adding `northstar-spring-boot` and without component-scanning the `io.northstar` package. If auto-configuration is still discovered and beans/properties work, that is stronger evidence the artifacts were packaged properly.

## 13. Checking Artifacts Before Release

### 13.1. Artifact Coordinates

The release list should look like:

~~~text
io.northstar:northstar-core:1.2.0
io.northstar:northstar-spring-boot:1.2.0
io.northstar:northstar-spring-boot-starter:1.2.0
io.northstar:northstar-spring-boot-starter-test:1.2.0
~~~

No third-party module starts with `spring-boot`.

### 13.2. Dependency Graph

With Maven:

~~~bash
mvn dependency:tree
~~~

With Gradle:

~~~bash
./gradlew :northstar-spring-boot-starter:dependencies
~~~

Verify the starter pulls in the right auto-configuration module and required runtime clients. Verify optional dependencies do not appear in consumers that only need core or auto-configuration.

### 13.3. JAR Contents

List resources in the JAR:

~~~bash
jar tf northstar-spring-boot-1.2.0.jar
jar tf northstar-spring-boot-starter-1.2.0.jar
~~~

In the auto-configuration JAR, look for:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
META-INF/spring-configuration-metadata.json
META-INF/spring-autoconfigure-metadata.properties
~~~

Not every project generates both metadata files. If there are `@ConfigurationProperties`, check configuration metadata; if auto-configure processor is enabled, check condition metadata. The imports file must exist in the JAR and contain exact FQCNs.

A starter JAR that only aggregates dependencies may contain no Java classes; that is not an error. Inspect the starter's POM/module metadata to confirm dependencies are published properly.

### 13.4. Testing Property Metadata in the IDE

Use a Spring Boot-capable IDE to test `northstar.audit.*` keys. Check that property suggestions, types, descriptions, and default values are accurate. Wrong metadata can cause users to enter wrong configuration even though the application compiles.

## 14. Compatibility and Namespace Changes Across Versions

Artifact names, public packages, and property prefixes can all become contracts that applications depend on.

Before releasing a new version:

1. Keep `groupId:artifactId` coordinates stable unless there is a major reason to change them.
2. Do not rename property prefixes or keys merely for internal alignment; if a change is unavoidable, plan deprecation and migration.
3. Do not move public packages without evaluating the impact on user imports.
4. When renaming an auto-configuration, update the imports file and consider `AutoConfiguration.replacements` for ordering/exclusion references.
5. Keep Spring Boot dependencies compatible via the BOM of the declared baseline.
6. Test against the Spring Boot versions the library claims to support; do not assume all major versions are compatible.

Spring Boot 3.3 requires Java 17 or higher. If the starter targets Boot 3.3, set the Java release and test against that baseline. Do not arbitrarily pick a Spring Framework version different from the one Spring Boot manages unless there is a specific reason and compatibility testing.

## 15. Common Design Mistakes

1. **Naming the artifact `spring-boot-starter-northstar`.** Change to a brand-first name such as `northstar-spring-boot-starter`.
2. **Assuming a separate `groupId` permits artifacts starting with `spring-boot`.** The module naming rule still applies even with a different groupId.
3. **Placing classes in `org.springframework.boot.*`.** Create packages under your organization's domain.
4. **Putting properties in `spring.*`, `server.*`, or `management.*`.** Use a dedicated prefix such as `northstar.audit`.
5. **Using component scanning to load auto-configuration.** Register classes via `AutoConfiguration.imports`; use `@Import` for specific supporting configurations.
6. **Putting every optional SDK into the default starter.** Split flavor starters and let the auto-configuration module mark optional dependencies.
7. **Missing the core starter in the dependency graph.** A starter must depend on `spring-boot-starter` directly or indirectly.
8. **Not generating property metadata.** IDEs cannot properly suggest library-owned keys.
9. **Confusing the two metadata types.** The imports file registers auto-configurations; configuration metadata describes properties; auto-configure metadata supports condition filtering.
10. **Testing only configuration classes.** Test runners registering classes directly can miss imports file errors; add a consumer smoke test.
11. **Renaming an auto-configuration while forgetting references.** Check `before`, `after`, exclusions, and the replacements file.
12. **Not checking transitive dependencies after publishing.** Consumers might lack runtime clients or pull in unnecessary libraries.

## 16. Release Checklist

| Item | Passing Criteria |
|---|---|
| Artifact naming | Third-party modules start with the project name, not `spring-boot` |
| Maven coordinates | `groupId` belongs to the organization; `artifactId` is stable |
| Module layout | Separate core, auto-configuration, starter, and test support when needed |
| Java package | Packages reside in the vendor's namespace |
| Auto-configuration discovery | Imports file is in the JAR with exact FQCNs |
| Component scanning | Auto-configuration is not a scan target and does not enable broad scanning |
| Property namespace | Dedicated prefix, not occupying `spring`, `server`, `management` |
| Property documentation | Clear field Javadoc, metadata generated and verified |
| Optional dependencies | Auto-configuration module does not force optional dependencies on every consumer |
| Core starter | Has `spring-boot-starter` directly or indirectly |
| Compatibility | Java/Spring Boot baseline and support matrix published |
| Tests | Unit/runner tests and consumer smoke test all pass |
| Packaging | JAR, dependency tree, and metadata verified after building |

## 17. Key Takeaways

- Third-party starter module names do not start with `spring-boot`, even when Maven `groupId` differs.
- Put the project name first, such as `northstar-spring-boot-starter`.
- Java packages must belong to the owning domain/organization; do not put classes in Spring packages.
- Property prefixes must be dedicated namespaces, such as `northstar.audit`; avoid `spring`, `server`, `management`.
- Auto-configurations are registered via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- The auto-configuration module can mark clients optional; the starter decides the default dependency set.
- Core Spring Boot starter must appear directly or indirectly in the dependency graph.
- Use processors to generate property metadata and auto-configuration metadata; inspect exact files in the JAR.
- Consumer smoke tests verify the starter usage experience better than testing auto-configuration classes alone.
- Artifact names, public packages, and property prefixes are contracts that must be protected across releases.

### Official Spring Boot 3.3 Documentation

- Build Systems — Starters and third-party naming rules: https://docs.spring.io/spring-boot/3.3/reference/using/build-systems.html
- Creating Your Own Auto-configuration — naming, module structure, imports, property namespaces, and optional dependencies: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Configuration Metadata — configuration metadata format: https://docs.spring.io/spring-boot/3.3/specification/configuration-metadata/index.html
