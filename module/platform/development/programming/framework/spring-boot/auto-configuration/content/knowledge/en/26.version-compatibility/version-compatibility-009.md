# Distinguishing Stable Public APIs from Internal Classes Without Compatibility Guarantees

## 1. Why distinguish them?

When developing with Spring Boot, an IDE can display many framework classes and methods. Some are APIs designed for long-term use by applications or other libraries. Others exist solely to support how Spring Boot implements a feature in the current version.

Both groups may appear in Javadoc, reside in the JAR, and even have the `public` modifier. That does not give them the same compatibility commitment.

If an application depends on internal details, a Spring Boot upgrade can cause compilation failures, `NoSuchMethodError`, startup failures, or behavior changes. If an application depends on published API contracts and tests properly, upgrades become much more predictable.

This lesson explains how to identify public APIs, internal classes, and supported extension points; how to design an auto-configuration library with a small API surface; and how to test without locking the application to implementation details. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 2. Four concepts that should not be conflated

### 2.1. Java visibility: can code access it?

Java uses modifiers:

| Modifier | Access scope |
|---|---|
| `public` | Accessible from code in other packages if module/classpath permits |
| `protected` | Accessible within the package and from subclasses per Java rules |
| package-private (no modifier) | Accessible only within the same package |
| `private` | Accessible only within the declaring class |

This is a rule of the Java language. It answers the question: **does the compiler allow referencing this element?**

It does not automatically answer: **do framework authors commit to keeping this element compatible for users?**

A class may need to be `public` so the framework can invoke it across packages, reflection can instantiate it, or another class in the library can use it. Authors may still regard that class as an implementation detail and not support external applications depending on it directly.

### 2.2. Public API: the contract published for users

The public API is the surface a library intentionally lets users rely on. It typically includes:

- Types, constructors, methods, and annotations documented for usage.
- Interfaces or callbacks published as extension points.
- Documented property keys, data types, default values, and meanings.
- Bean types or customization hooks the library commits to providing.
- Resource names or factory keys if documentation requires users to declare them.
- Behavior, errors, and compatibility rules described in documentation.

Even a published API can change in the future. Compatibility commitments depend on versioning policy, deprecation, and the version scope the library supports. “Public API” does not mean “immutable forever”.

### 2.3. Internal API / implementation detail

Internal components serve how the library implements a feature. Examples:

- `internal`, `impl`, parser, registrar, or helper classes used only inside the framework.
- Nested configuration classes inside an auto-configuration.
- `@Bean` methods that only instantiate a default implementation.
- Bean names derived from method names without a documented commitment.
- Protected or package-private fields, constructors, or methods not published as extension points.
- Metadata structures, internal call orders, or class loaders used internally.

These elements may be renamed, split, merged, or replaced as the implementation evolves. Without an explicit support contract, users should not assume they will stay compatible.

### 2.4. Extension point: a supported customization point

An extension point is a deliberate way a library lets applications customize behavior. Examples:

- Providing a `CatalogClient` interface so applications can write their own implementation.
- Allowing applications to declare an alternative bean via `@ConditionalOnMissingBean`.
- Providing a `CatalogClientCustomizer` interface and documenting how to register it.
- Providing `@ConfigurationProperties` for user configuration via properties.
- Providing annotations or SPIs documented for usage.

Not every subclassable class is an extension point. Look for explicit documentation on purpose, invocation order, lifecycle, and implementation responsibilities.

## 3. A very specific rule from the Spring Boot documentation

Spring Boot Reference 3.3 provides an important example regarding auto-configuration classes:

> Even though auto-configuration classes may be public, only the class name used to exclude the auto-configuration is considered public API. The contents inside the class, such as nested configuration classes and bean methods, are for internal use only.

This means applications may need to know an auto-configuration's name in order to exclude it, yet should not depend on details such as:

- `SomeAutoConfiguration.SomeNestedConfiguration`.
- The `dataSource(...)` or `redisConnectionFactory(...)` method inside auto-configuration.
- Default bean names inferred from method names.
- Method declaration order or nested class structure.

This is the rule documented for Spring Boot's own auto-configurations. When writing your own starter, apply the same design: expose only the points the library truly intends to support; keep nested configurations and bean factory methods internal if they are not extension points.

If the library commits to letting users exclude an auto-configuration, treat the class name listed in `AutoConfiguration.imports` as part of the contract to manage. When changing packages or class names, consider the impact on users using `exclude` or `excludeName`.

### 3.1. A public class can still be for internal framework use only

Spring Framework's Javadoc describes `SpringFactoriesLoader` as a general factory loading mechanism **for internal use within the framework**, even though the class itself carries the `public` modifier.

This is a clear example demonstrating that:

- A public class can be visible and importable from application code.
- Javadoc can restrict that class's intended purpose.
- Users should not infer a compatibility guarantee from accessibility alone.

When reading Javadoc, watch for phrases such as `for internal use`, `not intended for direct use`, `do not use directly`, or explicit notes stating a class is only an implementation. These notes matter more than whether the IDE autocompletes that class.

## 4. How to identify whether an API is supported

No single signal is enough to conclude. Combine multiple sources.

### 4.1. Read official documentation and API purpose

An element has grounds to be treated as a supported API when documentation:

- Clearly explains how applications should call or implement it.
- States parameters, lifecycle, return values, and constraints.
- Includes consumer usage examples.
- Describes how to customize or replace implementations.
- Mentions compatibility, deprecation, or migration when the API changes.

Thorough Javadoc descriptions are a good signal, yet you still must read intended-use notes. A Javadoc page may exist purely to explain the implementation to source readers.

### 4.2. Check packages and class names

Package names such as `internal`, `impl`, `support`, or `configuration` can be signals for caution. However, package names are not an absolute guarantee standard:

- Some `autoconfigure` packages contain public annotations/APIs.
- Some neutrally named packages contain internal helpers.
- A class in a public package can still be marked internal in Javadoc.

Therefore, use package names as an initial signal, then verify with Javadoc, reference documentation, and official examples.

### 4.3. Check annotations and deprecation status

Annotations/metadata can provide signals:

| Signal | How to interpret |
|---|---|
| `@Deprecated` | Element marked as no longer recommended; read the reason and replacement |
| `@Deprecated(since = "...")` | Indicates the version in which deprecation began |
| `@Deprecated(forRemoval = true)` | Intended for future removal; check Javadoc/release notes for timeline and replacement |
| `@since` in Javadoc | Version when the API was introduced; does not prove a compatibility guarantee |
| “internal use only” note | Should not be treated as an application extension point |
| Consumer examples in official docs | Strong signal of supported usage |

Not every project uses the same annotations or rules. Do not assume that lacking `@Deprecated` means an API is permanently stable.

### 4.4. Look for replacement contracts

If a class is deprecated or described as internal, look for:

- Recommended replacement interfaces or builders.
- New annotations replacing old classes.
- Published customizers/callbacks.
- Configuration properties instead of calling implementations directly.
- Release notes or migration guides for the corresponding version.

If no replacement is found, inspect module issues/changelogs or documentation before deciding to upgrade.

## 5. Example: an auto-configuration with a small public API and internal implementation

Suppose the Catalog library provides a product lookup feature. Users need a contract to call the service and a set of properties to configure the timeout.

Public API design:

- `CatalogClient`: the interface application business logic depends on.
- `CatalogProperties`: configuration property contract with prefix `acme.catalog`.
- `CatalogAutoConfiguration`: class published in imports; the library commits to the class name so applications can exclude it if needed.
- Default client creation, nested configuration, and concrete implementation are kept internal.
- Applications can supply their own `CatalogClient` bean; the default auto-configuration backs off.

Dependency model:

```text
APPLICATION CODE
      |
      v
CatalogClient  <------ User implementation (optional)
      ^
      |
Default implementation
      ^
      |
Internal @Bean factory method
      ^
      |
Internal nested configuration
      ^
      |
CatalogAutoConfiguration
      ^
      |
AutoConfiguration.imports
```

Business code depends only on `CatalogClient`. It does not need to know which HTTP client or SDK the library uses, or how nested configurations are structured.

## 6. Complete Maven example with Spring Boot 3.3.13

### 6.1. Directory layout

```text
catalog-api-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/catalog/
    │   │   ├── CatalogClient.java
    │   │   └── CatalogProperties.java
    │   ├── java/com/acme/catalog/autoconfigure/
    │   │   └── CatalogAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/acme/catalog/autoconfigure/
        └── CatalogAutoConfigurationTests.java
```

### 6.2. pom.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>catalog-api-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.3. CatalogClient.java — public API

```java
package com.acme.catalog;

/**
 * Public contract for looking up catalog items.
 * Consumers may inject this interface or provide their own bean.
 */
@FunctionalInterface
public interface CatalogClient {

    String findById(String id);
}
```

This is the contract business code uses. The library must preserve the method meaning, parameter types, and return type within its published compatibility policy.

### 6.4. CatalogProperties.java — public configuration contract

```java
package com.acme.catalog;

import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Documented configuration for the Catalog integration.
 */
@ConfigurationProperties(prefix = "acme.catalog")
public class CatalogProperties {

    private Duration timeout = Duration.ofSeconds(2);

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }
}
```

The `acme.catalog` prefix and `acme.catalog.timeout` property are part of the configuration contract. Renaming keys, changing units, or changing default meanings can be breaking changes for applications using the library.

YAML example:

```yaml
acme:
  catalog:
    timeout: 5s
```

### 6.5. CatalogAutoConfiguration.java — public candidate, internal implementation

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class DefaultClientConfiguration {

        @Bean
        @ConditionalOnMissingBean(CatalogClient.class)
        CatalogClient catalogClient(CatalogProperties properties) {
            return new DefaultCatalogClient(properties.getTimeout());
        }
    }

    /**
     * Internal default implementation. Not a supported consumer API.
     */
    static final class DefaultCatalogClient implements CatalogClient {

        private final Duration timeout;

        DefaultCatalogClient(Duration timeout) {
            this.timeout = timeout;
        }

        @Override
        public String findById(String id) {
            if (timeout.isNegative() || timeout.isZero()) {
                throw new IllegalStateException(
                        "Catalog timeout must be positive.");
            }
            return "catalog-item:" + id;
        }
    }
}
```

Key points:

1. `CatalogAutoConfiguration` is top-level `public` so Spring Boot discovers it from imports. If the library documents excluding the auto-configuration, this class name must be managed as a contract.
2. `DefaultClientConfiguration` is an internal nested configuration, not meant to be imported directly by applications.
3. `catalogClient(...)` is an internal bean factory method. Consumers should inject by type `CatalogClient`, without depending on the method name or bean name derived from the method.
4. `DefaultCatalogClient` is the default implementation. Applications do not need to instantiate or cast to this class.
5. `@ConditionalOnMissingBean(CatalogClient.class)` is the customization hook intentionally supported by the library: when the application supplies its own client, the default bean backs off.

### 6.6. AutoConfiguration.imports

Create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
```

This is the class name published for Spring Boot to discover the auto-configuration. Do not list nested configurations or implementation classes.

### 6.7. Consumer code using only the public API

A service in the application:

```java
package com.acme.orders;

import com.acme.catalog.CatalogClient;
import org.springframework.stereotype.Service;

@Service
public class ProductLookupService {

    private final CatalogClient catalogClient;

    public ProductLookupService(CatalogClient catalogClient) {
        this.catalogClient = catalogClient;
    }

    public String lookup(String id) {
        return catalogClient.findById(id);
    }
}
```

The service does not depend on `CatalogAutoConfiguration`, nested configurations, or `DefaultCatalogClient`. If the library swaps out the default implementation in a later release, the service still uses the same interface.

### 6.8. Application replacing the implementation via the published extension point

If the application wants to use a custom catalog source:

```java
package com.acme.orders;

import com.acme.catalog.CatalogClient;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class CustomCatalogConfiguration {

    @Bean
    CatalogClient customCatalogClient() {
        return id -> "custom-item:" + id;
    }
}
```

Because the library has `@ConditionalOnMissingBean(CatalogClient.class)`, the auto-configuration does not create the default implementation when an application-provided bean is present.

This is an intentional extension point expressed via the `CatalogClient` type. If a library does not document this back-off behavior, users should not assume every default bean is replaceable.

### 6.9. Testing the contract with ApplicationContextRunner

```java
package com.acme.catalog.autoconfigure;

import java.time.Duration;

import com.acme.catalog.CatalogClient;
import com.acme.catalog.CatalogProperties;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void exposesTheDocumentedClientAndPropertyContract() {
        runner.withPropertyValues("acme.catalog.timeout=5s")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    CatalogClient client =
                            context.getBean(CatalogClient.class);

                    assertThat(client.findById("42"))
                            .isEqualTo("catalog-item:42");

                    assertThat(context.getBean(CatalogProperties.class)
                            .getTimeout())
                            .isEqualTo(Duration.ofSeconds(5));
                });
    }

    @Test
    void backsOffWhenTheApplicationProvidesItsOwnClient() {
        runner.withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CatalogClient.class);

                    assertThat(context.getBean(CatalogClient.class)
                            .findById("42"))
                            .isEqualTo("custom-item:42");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogClient customCatalogClient() {
            return id -> "custom-item:" + id;
        }
    }
}
```

The tests verify only the contract visible to consumers:

- A bean of type `CatalogClient` exists.
- The `findById` method returns the result per contract.
- The `acme.catalog.timeout` property is bound as a `Duration`.
- A user bean replaces the default implementation.

The tests do not assert the concrete implementation class, nested configuration names, or bean factory method names. This lets tests catch genuine breaking changes for consumers without locking tests to internal details.

Run:

```bash
mvn test
```

With the two tests in the example, the expected output is:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

This is the expected result; Maven must be run in the project to verify in practice.

## 7. Ways internal dependencies easily cause breakage

### 7.1. Casting to the default implementation

Code that creates coupling:

```java
DefaultCatalogClient client =
        (DefaultCatalogClient) context.getBean(CatalogClient.class);
```

The application is forced to know the default implementation. If the library switches to another implementation, the code can throw `ClassCastException` or fail to compile if the class is hidden/renamed.

Use:

```java
CatalogClient client = context.getBean(CatalogClient.class);
```

### 7.2. Looking up a bean by an uncommitted name

Do not depend on:

```java
CatalogClient client =
        context.getBean("catalogClient", CatalogClient.class);
```

The name `catalogClient` may be derived from the `@Bean` method name. If the library renames the method, the bean name can change too.

Use lookup by type or constructor injection. Use a bean name only when library documentation explicitly commits to it as a stable name.

### 7.3. Importing nested configurations

Do not do:

```java
import com.acme.catalog.autoconfigure.CatalogAutoConfiguration
        .DefaultClientConfiguration;
```

Nested configurations are internal organizational details. The framework can split classes, change conditions, or merge nested classes without changing the `CatalogClient` contract.

### 7.4. Subclassing a helper just because it has protected/public modifiers

A `protected` method may serve only internal subclasses. Before overriding, check Javadoc stating explicitly that the method is a supported hook, along with its call rules and lifecycle.

Without a contract, overriding an internal method can break the subclass when the framework changes its algorithm.

### 7.5. Reflecting on internal fields or methods

Reflection does not turn an implementation detail into a stable API:

```java
Field field = DefaultCatalogClient.class
        .getDeclaredField("timeout");
field.setAccessible(true);
```

Field names, data types, and access permissions can change. The Java module system can also restrict reflective access. Use published constructors, setters, properties, or callbacks instead of reflecting on implementations.

## 8. Types of compatibility to verify

A change can remain compatible in one dimension while breaking another.

| Compatibility type | Question |
|---|---|
| Source compatibility | Does old source compile against the new dependency? |
| Binary compatibility | Does already compiled bytecode link against the new classes/methods? |
| Behavioral compatibility | Do results, callback order, defaults, and side effects still hold? |
| Configuration compatibility | Are property keys, data types, default values, and configuration meanings still compatible? |
| SPI compatibility | Are interfaces, callbacks, constructors, and lifecycles of user-provided implementations still valid? |
| Resource compatibility | Are filenames, factory keys, imports, and metadata needed by applications still supported? |

Common breakage examples:

- Removing a public method called by consumers: source and binary compatibility can break.
- Keeping the method while changing the default timeout meaning: behavioral/configuration compatibility can break.
- Renaming property `acme.catalog.timeout`: configuration compatibility breaks without an alias or migration.
- Changing a callback interface implemented by plugins: SPI compatibility breaks.
- Changing an internal nested configuration while keeping `CatalogClient`: may leave consumers using the proper contract unaffected.

## 9. Deprecation and version upgrades

Public APIs can evolve along an announced path. When encountering a deprecated element:

1. Read the reason in Javadoc.
2. Find the suggested replacement.
3. Check `since` to see when deprecation started.
4. Check `forRemoval` or removal target notes if present.
5. Read release notes and migration guides for the version you plan to upgrade to.
6. Migrate code to the replacement API and re-run contract tests.

Illustrative example:

```java
@Deprecated(since = "3.3", forRemoval = true)
public void oldConfigure(String value) {
    // Legacy method
}
```

`@Deprecated` is a signal for users to transition gradually. `forRemoval = true` indicates intent to remove in the future; do not ignore warnings just because code still compiles in the current version.

Some notes:

- `@since` only states which version introduced the API.
- Lacking `@Deprecated` does not prove an API is guaranteed forever.
- An internal class does not require a deprecation period before changing.
- Do not infer removal policies from version numbers alone; read specific Javadoc, release notes, and migration guides.

## 10. Safe Spring Boot upgrade workflow

When upgrading an application or starter from one Boot version to another:

1. Identify the exact Boot and Spring Framework versions in use.
2. Read the release notes for every skipped feature release, not just the target release.
3. Check the deprecated API list and replacements.
4. Search for imports from `internal`, `impl` packages, or nested auto-configuration classes.
5. Search for casts to default implementations and bean lookups by undocumented names.
6. Replace internal dependencies with published interfaces, properties, or extension points.
7. Compile and run tests on the lowest and highest versions the project commits to supporting.
8. Run consumer integration tests against the packaged artifact, not just internal module tests.
9. Verify property binding, bean back-off, classpath conditions, and resource registration.
10. Read the Condition Evaluation Report if auto-configuration no longer applies as before.

### 10.1. Supporting tools

- `mvn dependency:tree`: determine the actual resolved Spring Boot/Spring Framework versions.
- Javadoc/deprecated-list: identify APIs, replacements, and deprecation status.
- Revapi or japicmp: compare binary API surfaces between two artifacts.
- Contract/integration tests: verify behavior as seen by consuming applications.
- `--debug`: view the Condition Evaluation Report when diagnosing auto-configuration.

API comparison tools do not replace reading documentation. A tool may detect a removed public method without knowing that the method had always been documented as internal use only.

## 11. API design checklist for your own starter

Before publishing an auto-configuration library:

1. Choose one or a few public interfaces as contracts for business code.
2. Publish only properties users genuinely need to configure.
3. Clearly document types, defaults, units, validation, and meaning for each property.
4. Define extension points with documented and tested interfaces/callbacks.
5. Use `@ConditionalOnMissingBean` when allowing users to replace the default implementation.
6. Keep default implementations, helpers, and nested configurations internal.
7. Do not require consumers to import nested configurations or call bean factory methods.
8. Commit to bean names only with good reason and explicit documentation; prefer type-based contracts.
9. Publish auto-configuration class names if users may need to exclude them.
10. Document compatibility policies and deprecation handling.
11. Write tests from the consumer's perspective, avoiding implementation class assertions.
12. Test artifacts/JARs and dependency graphs across supported versions.

## 12. Common misconceptions

| Misconception | Reality |
|---|---|
| A `public` class is definitely public API | The modifier controls only access; intended use and compatibility contracts must be checked in documentation |
| Having Javadoc means it is supported | Javadoc can describe internal classes; read intended-use notes |
| Classes in `autoconfigure` packages are definitely internal | The package can contain both public annotations/APIs and implementations |
| A class with `@since` is stable | `@since` only states the version of introduction |
| Not deprecated means it will never change | APIs remain subject to versioning policy and may change in the future |
| Nested configurations of auto-config are extension points | Spring Boot documents nested configurations and bean methods of auto-config as internal |
| Bean names derived from methods are always stable | Those names can change when methods change unless explicitly committed |
| Tests passing while the current implementation exists is enough | Consumers need tests for externally visible contracts, properties, and behavior |
| Reflection can replace official APIs | Reflection still depends on implementation structure and can be blocked by module access |
| Public APIs are never removed | APIs can be deprecated and removed along a versioned roadmap |

## 13. Self-check questions

**Question 1.** Does the Java `public` modifier mean an element is a stable API?

**Answer:** No. It only allows external code to access it. Documentation, intended use, and compatibility contracts must be checked.

**Question 2.** According to Spring Boot Reference, which part of an auto-configuration class is considered public API?

**Answer:** The class name used to exclude the auto-configuration. Nested configuration classes and bean methods are internal implementation details.

**Question 3.** Why should `CatalogClient` not be cast to `DefaultCatalogClient`?

**Answer:** Because the application becomes coupled to a concrete implementation; the library can swap implementations while keeping the `CatalogClient` interface unchanged.

**Question 4.** Does `@since` guarantee an API will not change?

**Answer:** No. It only indicates the version in which the API was introduced.

**Question 5.** What does `@Deprecated(forRemoval = true)` mean?

**Answer:** The API is deprecated and intended for future removal; look up the replacement and concrete timeline in the documentation.

**Question 6.** If a library wants applications to be able to replace the default client, what should it publish?

**Answer:** An interface like `CatalogClient`, documented contracts, and `@ConditionalOnMissingBean(CatalogClient.class)` on the default bean.

**Question 7.** Why should tests not assert nested configuration names or implementation classes?

**Answer:** Because those are internal details. Tests should check the types, properties, and behavior consumers are promised.

**Question 8.** How should Javadoc on a public class stating “for internal use within the framework” be interpreted?

**Answer:** That class should not be treated as an extension point or supported API for external applications solely because its modifier is public.

## 14. Takeaways

- Java visibility and public API contracts are two distinct concepts.
- Public API is the surface actively documented and supported by a library under a specific compatibility policy.
- Spring Boot states explicitly: for auto-configurations, the class name used for exclusion is public API; nested configurations and bean methods are internal.
- Javadoc on a public class can still restrict it to internal use.
- Prefer published interfaces, properties, and extension points; avoid implementation casts, importing nested configs, depending on bean names, or reflecting on internal fields.
- Test from the consumer's perspective without locking tests to implementation details.
- When upgrading, read the deprecated API list, release notes, and migration guide; use recommended replacements.
- Designing a small, clear, contract-driven API lets a library evolve its implementation with minimal impact on consuming applications.

### Official documentation

- [Spring Boot 3.3 — Developing with Spring Boot / Auto-configuration](https://docs.spring.io/spring-boot/docs/3.3.0-M2/reference/html/using.html)
- [Spring Boot 3.3.13 API — AutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html)
- [Spring Boot 3.3.13 API — Deprecated API List](https://docs.spring.io/spring-boot/3.3/api/java/deprecated-list.html)
- [Spring Framework 6.1 — SpringFactoriesLoader API](https://docs.spring.io/spring-framework/docs/6.1.0-M5/javadoc-api/org/springframework/core/io/support/SpringFactoriesLoader.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
