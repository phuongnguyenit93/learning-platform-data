# Configuration Matches, Yet Bean Creation Fails Due to Input Data or External Resources

## 1. Understanding the Difference Between a Condition Match and Successful Bean Creation

In Spring Boot, an auto-configuration can be selected properly by its conditions yet the application still fails to start. For example, the property `acme.catalog.enabled=true` makes `@ConditionalOnProperty` match, Spring registers a bean definition for `CatalogService`, yet the `@Bean` method attempts to read a missing external config file. As a result, context refresh fails with `BeanCreationException`.

These are two separate questions:

- **Does the condition allow registering the configuration/bean definition?**
- **Can Spring bind data, instantiate the object, resolve dependencies, and finish initializing the bean?**

A matching condition confirms only the first question. It does not prove the constructor will succeed, input data is valid, resources can be opened, databases can connect, or third-party dependencies are ready.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1, Java 17+, and Maven**. We walk from conditions to binding, validation, bean factory methods, and resource loading; then we build an auto-configuration that reads an external catalog file and test both the happy path and startup failures.

After this lesson, you can:

1. Distinguish condition evaluation from bean instantiation and initialization.
2. Pinpoint whether a failure happened during binding, validation, constructor execution, dependency injection, or resource loading.
3. Use `@ConfigurationProperties` and Jakarta Validation to catch bad configuration early.
4. Read resources through Spring's `ResourceLoader` and report errors with context.
5. Decide when to fail fast, use a fallback, or defer operations until runtime.
6. Write tests for disabled properties, valid data, missing files, malformed files, and user bean overrides.
7. Read the condition report without confusing it with bean creation outcomes.

## 2. Lifecycle: From Condition to Instance

A simplified startup flow looks like this:

~~~text
Read Environment and annotation metadata
                |
                v
Evaluate @Conditional...
          /           \
      no match       match
         |              |
         v              v
  Do not register   Register bean definition
  bean definition          |
                           v
                Bind @ConfigurationProperties
                           |
                           v
                  Validate input data
                           |
                           v
              Resolve constructor / method dependencies
                           |
                           v
                 Invoke constructor or @Bean method
                           |
                           v
                Initialize bean and run callbacks
                           |
                           v
                  Context refresh succeeds
~~~

Conditions are typically evaluated while Spring parses configurations and registers bean definitions. Singleton bean instantiation normally occurs later during context refresh. Thus, a condition can match while a failure surfaces only during property binding or factory-method execution.

### 2.1. Conditions Answer Applicability

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true"
)
public class CatalogAutoConfiguration {
    // Beans are considered only when the feature is enabled.
}
~~~

When `acme.catalog.enabled=true`, the condition lets Spring process the configuration. It does not check whether `acme.catalog.location` is declared, whether the file at that path can be opened, whether its contents are valid, or whether the service can initialize.

`@ConditionalOnProperty` reads values from the Spring `Environment`. By default, the property must exist and differ from `false`; `havingValue` and `matchIfMissing` customize the rule. If explicit boolean activation is desired, write `havingValue="true"`.

### 2.2. A Registered Bean Definition Does Not Mean an Instance Exists

A `@Bean` method can be registered as a bean definition before the method is ever invoked:

~~~java
@Bean
CatalogService catalogService(CatalogProperties properties) {
    return new CatalogService(properties.getLocation());
}
~~~

Spring can learn the bean name, return type, and dependencies to inject from method metadata. When creating the bean, the framework invokes the method. If the method throws an exception, bean creation fails and the exception is normally wrapped in `BeanCreationException`.

Similarly, constructor injection can fail when a dependency cannot be constructed. Bean A's condition matching does not guarantee bean B, which A depends on, initializes cleanly.

### 2.3. Bean Creation Involves Multiple Steps Beyond the Factory Method

A bean can fail at several stages:

- The constructor throws an exception.
- A constructor or `@Bean` method parameter lacks a matching dependency.
- `@ConfigurationProperties` fails to bind.
- Validation detects invalid data.
- The `@Bean` method fails reading a file or parsing contents.
- `InitializingBean`, `@PostConstruct`, or a custom init method fails.
- A bean eagerly connects to an external system and times out.
- The bean is lazy, so errors appear only when code first requests it.

When debugging, determine **whether the condition matched** and **at which step bean creation stopped**. Both can be true simultaneously: the condition matched, yet bean creation failed.

## 3. What Different Conditions Check vs. Do Not Check

| Condition | Checks | Does not prove |
| --- | --- | --- |
| `@ConditionalOnProperty` | Property exists and matches criteria | Other properties are valid; referenced file exists; bean can be constructed |
| `@ConditionalOnClass` | Class exists on classpath | Binary version compatibility; error-free class initialization; complete dependencies |
| `@ConditionalOnBean` | Matching bean exists in BeanFactory per criteria | That bean instance initializes cleanly or underlying services are ready |
| `@ConditionalOnMissingBean` | No matching bean exists yet for auto-configuration to provide default | Default bean can be constructed |
| `@ConditionalOnSingleCandidate` | A single candidate can be chosen for injection | That candidate can be constructed |
| `@ConditionalOnResource` | Specified resource exists per resource condition rules | Valid content, proper read permissions, resource opens cleanly and remains present at use |

### 3.1. `@ConditionalOnResource` Is Not a Content Validator

Example:

~~~java
@AutoConfiguration
@ConditionalOnResource(
    resources = "classpath:catalog/default.properties"
)
public class CatalogDefaultsAutoConfiguration {
}
~~~

This condition is useful when a library applies configuration only if a prepackaged resource is present. It does not validate whether the file has required keys, proper encoding, or parseable content.

For external files whose paths are user-configured, checking presence at one moment also does not substitute for actually opening and reading the file. Files can be deleted, permissions can change, or contents can be corrupted after the condition evaluates. This is a classic time-of-check/time-of-use situation.

If a resource is mandatory when the feature is enabled, let the bean/service open the resource and throw a contextual error when unusable. If the resource is genuinely optional, define a clear fallback and test both branches.

### 3.2. `@ConditionalOnExpression` Should Not Invoke Beans to Check Resources

Avoid writing expressions referencing beans to check files or remote services:

~~~java
@ConditionalOnExpression("@catalogHealthChecker.available()")
~~~

Referencing a bean in an expression can force eager initialization during context refresh. At that point the bean may not yet have gone through full post-processing, including configuration properties binding. Furthermore, the condition becomes tied to I/O or external service state and hard to test.

Conditions should decide applicability from metadata/properties/classpath. Opening files, parsing data, and connecting to services belong inside beans/services at the appropriate phase.

## 4. Categorizing Input Data and Common Failures

Before reading a stack trace, identify where inputs come from and when they are checked.

| Input category | Examples | Common failures | Resolution |
| --- | --- | --- | --- |
| Scalar properties | `acme.catalog.enabled`, `max-items` | Missing key, wrong type, out-of-range value | Type-safe binding and validation |
| Structured properties | Endpoint lists, credentials, nested options | Missing nested field, invalid element | `@Valid`, constraints on nested objects |
| Resource paths | `file:./config/catalog.properties` | File missing, unreadable permissions, wrong working directory | `ResourceLoader`, error message showing exact location |
| Resource content | Properties, YAML, JSON, XML | Missing keys, wrong encoding, corrupted data | Controlled parsing and schema/domain validation |
| External dependencies | Database, HTTP API, message broker | DNS, TLS, authentication, timeouts, service unavailable | Timeouts, bounded retries, readiness/health, appropriate fallback |
| Java dependencies | Optional classes or libraries | Missing class, incompatible version, `LinkageError` | Dependency management and class conditions |

### 4.1. Binding Errors Differ from Condition No-Match

For example, `acme.catalog.max-items=many` does not make `@ConditionalOnProperty(acme.catalog.enabled=true)` evaluate to false. The condition still matches. Then the binder attempts to convert the string `many` to a numeric type and fails.

This is a data-conversion (binding) error, not a condition error. Rewriting the condition to inspect `max-items` via SpEL is rarely good practice; bind to `int` or `Integer` and validate the value instead.

### 4.2. Validation Differs from Resource Parsing

`acme.catalog.location=` can bind as an empty string. With `@NotBlank` on the field, validation rejects the configuration before the `@Bean` method is called.

Conversely, a syntactically valid string such as `file:./config/catalog.properties` can still point to a non-existent file. Property validation confirms only that the string is non-blank; it does not guarantee the filesystem holds the resource.

### 4.3. A Readable File Can Still Contain Invalid Data

A file may exist and be readable, yet:

- Lack required keys.
- Have unparseable numeric values.
- Have values outside valid business bounds.
- Use a different encoding than assumed.
- Be truncated or partially written.
- Contain content incompatible with the library's schema version.

Therefore, after opening a resource, validate its structure and domain values. Never treat `Resource.exists()` or `Resource.isReadable()` as proof that the content is valid.

## 5. Binding and Validating Configuration with `@ConfigurationProperties`

For related properties, group them into a typed class instead of reading individual strings with `@Value`.

### 5.1. Declaring the Properties Class

Example:

~~~java
package com.acme.catalog.autoconfigure;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    public String getLocation() {
        return this.location;
    }

    public void setLocation(String location) {
        this.location = location;
    }
}
~~~

`@ConfigurationProperties` lets Spring Boot bind properties from properties/YAML files, environment variables, system properties, or command-line arguments. `@Validated` enables validation on the class; `@NotBlank` requires `location` to contain non-whitespace characters.

To use Jakarta Validation, add an implementation to the classpath. In the Maven example in Section 9, `spring-boot-starter-validation` provides the validation infrastructure.

### 5.2. Registering the Properties Bean in Auto-Configuration

Use `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(CatalogProperties.class)
public class CatalogAutoConfiguration {
}
~~~

When the configuration is processed, Spring Boot registers the properties bean and performs binding/validation. If `location` is missing or blank, the context fails while creating the properties bean, before the factory method creating `CatalogService` is invoked.

### 5.3. Validating Simple Cases Right at the Configuration Boundary

Common constraints:

| Annotation | Rule |
| --- | --- |
| `@NotNull` | Value must not be null |
| `@NotBlank` | String must not be null and must contain non-whitespace characters |
| `@NotEmpty` | String/collection/map must not be empty |
| `@Min(1)` | Numeric value must be at least 1 |
| `@Max(1000)` | Numeric value must be at most 1000 |
| `@Positive` | Number must be positive |
| `@Email` | String must match email validator format |
| `@Pattern` | String must match regular expression |

Example:

~~~java
@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    @Min(1)
    @Max(1000)
    private int maxItems = 100;

    // getters and setters
}
~~~

For nested objects, place `@Valid` on fields requiring cascaded validation. Without `@Valid`, constraints inside child objects may not be evaluated as expected.

### 5.4. Do Not Put I/O Checks Inside Configuration Validators

Validation is meant to verify bound values: non-blank, proper format, within bounds, consistent with other properties.

Do not turn validators into places that make HTTP calls, query databases, or read large files. Those operations can be slow, environment-dependent, and have side effects. Inspect actual resources inside the service/factory method after properties have bound.

## 6. Reading External Resources Using Spring's Resource Abstraction

Spring provides `Resource` and `ResourceLoader` to access diverse resource types through a unified API.

Common location formats:

| Prefix | Meaning |
| --- | --- |
| `classpath:` | Resource on the classpath |
| `file:` | Resource on the filesystem |
| URL such as `https:` | Resource accessed through the matching URL handler |
| Unprefixed path | Handling depends on the `ResourceLoader` in use |

Example:

~~~java
Resource resource = resourceLoader.getResource(
    "file:./config/catalog.properties"
);
~~~

### 6.1. Using `getInputStream()` and Closing Streams Properly

`Resource` is a descriptor for a resource. To actually open its content, call `getInputStream()`. Streams must be closed, so use try-with-resources:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Read data.
}
~~~

Do not check only `resource != null`: creating a descriptor does not mean the resource exists or can be opened. `exists()` checks physical presence and `isReadable()` indicates readability per the descriptor, yet calling `getInputStream()` can still fail.

### 6.2. Relative Paths Depend on the Working Directory

The location `file:./config/catalog.properties` resolves relative to the process working directory. When running from an IDE, Maven, a service manager, a container, or systemd, the working directory can differ.

For production deployments, prefer one of these approaches:

- Supply an absolute path via environment variable or deployment config.
- Mount the file to a fixed path inside the container.
- Use `spring.config.import`/config tree if the file is effectively an application configuration source.
- Use a supported secret/configuration provider with clear policy.

Never log secrets or credentials when reporting errors. Log only the location, property name, and technical cause needed for operators to fix it.

### 6.3. When Should `spring.config.import` Be Used?

If an external file is **application configuration** that Spring Boot should load into `Environment`, consider the Config Data API:

~~~properties
spring.config.import=file:./config/extra.properties
~~~

Properties in that file are added to `Environment` and can bind via `@ConfigurationProperties`.

If the file is **domain data specific to a bean**, such as a catalog, template, or mapping file, `ResourceLoader` is usually better suited. Do not manually parse `application.properties` using `Properties.load()` as a replacement for Spring Boot's Config Data mechanism.

## 7. Designing Auto-Configuration with Clear, Actionable Errors

The example below creates a default `CatalogService` when the feature is enabled and the user has not supplied a custom implementation. Properties are registered only inside the default nested configuration; if a user bean already exists, the library does not need to bind `location` or read the default file.

### 7.1. Service Model

File `src/main/java/com/acme/catalog/autoconfigure/CatalogService.java`:

~~~java
package com.acme.catalog.autoconfigure;

public record CatalogService(String name, int maxItems) {
}
~~~

### 7.2. Auto-Configuration

File `src/main/java/com/acme/catalog/autoconfigure/CatalogAutoConfiguration.java`:

~~~java
package com.acme.catalog.autoconfigure;

import java.io.IOException;
import java.io.InputStreamReader;
import java.io.Reader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.Resource;
import org.springframework.core.io.ResourceLoader;

@AutoConfiguration
@ConditionalOnProperty(
    prefix = "acme.catalog",
    name = "enabled",
    havingValue = "true"
)
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnMissingBean(CatalogService.class)
    @EnableConfigurationProperties(CatalogProperties.class)
    static class DefaultCatalogConfiguration {

        @Bean
        CatalogService catalogService(
                CatalogProperties properties,
                ResourceLoader resourceLoader) {

            String location = properties.getLocation();
            Resource resource = resourceLoader.getResource(location);
            Properties values = new Properties();

            try (Reader reader = new InputStreamReader(
                    resource.getInputStream(),
                    StandardCharsets.UTF_8)) {
                values.load(reader);
            }
            catch (IOException ex) {
                throw new IllegalStateException(
                    "Cannot read catalog resource '" + location + "'",
                    ex
                );
            }
            catch (IllegalArgumentException ex) {
                throw new IllegalStateException(
                    "Catalog resource '" + location
                        + "' contains malformed properties data",
                    ex
                );
            }

            String name = values.getProperty("catalog.name");
            if (name == null || name.isBlank()) {
                throw new IllegalStateException(
                    "Required key 'catalog.name' is missing or blank in '"
                        + location + "'"
                );
            }

            String rawMaxItems =
                values.getProperty("catalog.max-items", "100");

            int maxItems;
            try {
                maxItems = Integer.parseInt(rawMaxItems.trim());
            }
            catch (NumberFormatException ex) {
                throw new IllegalStateException(
                    "Property 'catalog.max-items' in '" + location
                        + "' must be an integer, but was '"
                        + rawMaxItems + "'",
                    ex
                );
            }

            if (maxItems < 1) {
                throw new IllegalStateException(
                    "Property 'catalog.max-items' in '" + location
                        + "' must be greater than zero"
                );
            }

            return new CatalogService(name.trim(), maxItems);
        }
    }
}
~~~

Several key design decisions appear here:

- The outer condition checks whether the feature is enabled.
- `@ConditionalOnMissingBean` allows the application to replace the default service.
- `@EnableConfigurationProperties` lives only inside the nested default configuration. If the application already supplies `CatalogService`, default properties do not need binding and the external file does not need reading.
- `ResourceLoader` resolves the location via Spring's abstraction.
- `getInputStream()` actually opens the file; `IOException` is wrapped with a location-specific exception.
- Contents are parsed and keys/values validated before returning the service.
- Every error names the property or resource that needs fixing.

Never catch generic `Exception` and ignore the error or return an empty object. Doing so lets the application continue in an invalid state and obscures the true root cause.

### 7.3. Why Not Check the File Inside a Condition?

One might consider a custom condition that reads the file before registering the bean. That design fits poorly here:

- Conditions run during the configuration-processing phase.
- Reading files involves I/O and depends on permissions or the filesystem.
- After a condition returns a match, the file can still change before the bean opens it.
- If the condition reads and parses the file, the bean/service still needs the parsed data or must read it again.
- Errors inside conditions are harder to express with domain-specific messages than errors inside factory methods.

Let conditions check simple configuration applicability. Let beans/services instantiate objects and validate the resources those objects require.

## 8. Distinguishing Mandatory, Optional, and Remote Resources

Not every missing resource should crash application startup. The right policy depends on the resource's role.

| Dependency type | Usually appropriate policy | Examples |
| --- | --- | --- |
| Mandatory to serve every request | Fail fast when unreadable/unvalidated | Core catalog, required schema, required truststore |
| Optional, with safe default | Use fallback and log clearly | Default template, optional override file |
| Used by only one feature | Disable just that feature or initialize lazily by design | Export module unused in all deployments |
| Remote service that may be disrupted | Client bean can be created upfront; calls use timeouts/retries and health/readiness | HTTP API, message broker |
| Service mandatory before serving traffic | Fail fast or keep instance unready until dependency is ready | Mandatory authentication system |

### 8.1. Failing Fast When Mandatory Data Is Missing

If every request fails without the catalog, stop startup with a clear message:

~~~text
APPLICATION FAILED TO START

Description:
Cannot read catalog resource 'file:./config/catalog.properties'

Action:
Verify that the file exists, is readable by the application process,
and contains the required catalog properties.
~~~

This is an illustrative message that an application or custom `FailureAnalyzer` can produce. Exact output depends on the exception and logging.

### 8.2. Falling Back When a Resource Is Truly Optional

If an override file customizes UI only, you can use defaults when the file is absent:

~~~java
if (!resource.exists()) {
    return CatalogService.withDefaults();
}
~~~

However, fallback must be documented behavior. Never silently fall back for a mandatory resource, or the application may run while serving incorrect data.

### 8.3. Do Not Make Arbitrary Network Connections in Constructors

A `@Bean` method can construct a client object without opening a connection immediately. This is usually better than calling remote APIs in the constructor. When real requests arrive, the client applies timeouts, bounded retries, and circuit breakers appropriately.

If startup strictly must verify a remote dependency, document why and bound the wait time. Never let DNS/network outages hang startup indefinitely. Under Kubernetes or orchestrators, readiness/health checks can reflect dependency availability according to application policy.

## 9. Complete Java 17+ and Maven Example

The example below contains an auto-configuration, a demo application, and a test suite using `ApplicationContextRunner`. The application package `demo.app` is separate from the library package `com.acme.catalog.autoconfigure`; auto-configuration loads via the imports file.

### 9.1. Project Structure

~~~text
catalog-demo/
├── pom.xml
├── config/
│   └── catalog.properties
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── com/acme/catalog/autoconfigure/
    │   │   │   ├── CatalogProperties.java
    │   │   │   ├── CatalogService.java
    │   │   │   └── CatalogAutoConfiguration.java
    │   │   └── demo/app/
    │   │       └── CatalogApplication.java
    │   └── resources/
    │       ├── application.properties
    │       └── META-INF/spring/
    │           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/app/
            └── CatalogAutoConfigurationTests.java
~~~

### 9.2. File `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>catalog-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-boot-starter-validation` provides the Jakarta Validation implementation so `@Validated` and `@NotBlank` work. `spring-boot-starter-test` provides JUnit, AssertJ, and Spring Boot test utilities.

### 9.3. File `CatalogProperties.java`

~~~java
package com.acme.catalog.autoconfigure;

import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "acme.catalog")
@Validated
public class CatalogProperties {

    @NotBlank
    private String location;

    public String getLocation() {
        return this.location;
    }

    public void setLocation(String location) {
        this.location = location;
    }
}
~~~

### 9.4. File `CatalogService.java`

~~~java
package com.acme.catalog.autoconfigure;

public record CatalogService(String name, int maxItems) {
}
~~~

### 9.5. File `CatalogAutoConfiguration.java`

Uses the exact implementation from Section 7.2. In the demo project, the file sits at `src/main/java/com/acme/catalog/autoconfigure/CatalogAutoConfiguration.java`.

### 9.6. Registering Auto-Configuration

File `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`:

~~~text
com.acme.catalog.autoconfigure.CatalogAutoConfiguration
~~~

The imports file lets Spring Boot discover the auto-configuration inside the JAR. The auto-configuration package does not need to sit under the application's component-scan package.

### 9.7. Application Configuration

File `src/main/resources/application.properties`:

~~~properties
acme.catalog.enabled=true
acme.catalog.location=file:./config/catalog.properties
~~~

External file `config/catalog.properties` at the project root:

~~~properties
catalog.name=Demo Catalog
catalog.max-items=25
~~~

`file:./config/catalog.properties` is relative to the working directory. When running the Maven command below, run from the `catalog-demo` directory so the path points to the right file.

### 9.8. Main Application

File `src/main/java/demo/app/CatalogApplication.java`:

~~~java
package demo.app;

import com.acme.catalog.autoconfigure.CatalogService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CatalogApplication {

    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }

    @Bean
    CommandLineRunner printCatalog(CatalogService catalog) {
        return args -> System.out.printf(
            "catalog=%s, maxItems=%d%n",
            catalog.name(),
            catalog.maxItems()
        );
    }
}
~~~

### 9.9. Running the Application

Requirements: JDK 17+ and Maven. From the project directory:

~~~bash
mvn clean spring-boot:run
~~~

Output line printed by `CommandLineRunner`:

~~~text
catalog=Demo Catalog, maxItems=25
~~~

Spring Boot also emits startup logs. The line above is the example's business output when the file exists and has valid contents.

## 10. Testing Both Success and Failure with `ApplicationContextRunner`

`ApplicationContextRunner` builds a minimal context, allowing properties and user configurations to vary per test. It is well suited for checking whether an auto-configuration handles all input combinations properly.

### 10.1. Test File

File `src/test/java/demo/app/CatalogAutoConfigurationTests.java`:

~~~java
package demo.app;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import com.acme.catalog.autoconfigure.CatalogAutoConfiguration;
import com.acme.catalog.autoconfigure.CatalogService;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class)
            );

    private ApplicationContextRunner enabledWith(Path file) {
        return this.contextRunner.withPropertyValues(
            "acme.catalog.enabled=true",
            "acme.catalog.location=" + file.toUri()
        );
    }

    @Test
    void doesNotCreateCatalogWhenFeatureIsDisabled() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=false")
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).doesNotHaveBean(CatalogService.class);
            });
    }

    @Test
    void createsCatalogFromValidExternalFile(@TempDir Path tempDir)
            throws IOException {

        Path file = tempDir.resolve("catalog.properties");
        Files.writeString(
            file,
            "catalog.name=Test Catalog\ncatalog.max-items=12\n",
            StandardCharsets.UTF_8
        );

        this.enabledWith(file).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CatalogService.class);

            CatalogService catalog =
                context.getBean(CatalogService.class);

            assertThat(catalog.name()).isEqualTo("Test Catalog");
            assertThat(catalog.maxItems()).isEqualTo(12);
        });
    }

    @Test
    void failsWithLocationWhenExternalFileIsMissing(@TempDir Path tempDir) {
        Path missing = tempDir.resolve("missing.properties");

        this.enabledWith(missing).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .hasStackTraceContaining("Cannot read catalog resource");
        });
    }

    @Test
    void failsWhenLocationIsBlank() {
        this.contextRunner
            .withPropertyValues(
                "acme.catalog.enabled=true",
                "acme.catalog.location="
            )
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasStackTraceContaining("must not be blank");
            });
    }

    @Test
    void failsWhenCatalogNumberIsMalformed(@TempDir Path tempDir)
            throws IOException {

        Path file = tempDir.resolve("catalog.properties");
        Files.writeString(
            file,
            "catalog.name=Test Catalog\ncatalog.max-items=many\n",
            StandardCharsets.UTF_8
        );

        this.enabledWith(file).run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure())
                .hasStackTraceContaining("must be an integer");
        });
    }

    @Test
    void userServiceOverridesDefaultWithoutReadingDefaultFile() {
        this.contextRunner
            .withPropertyValues("acme.catalog.enabled=true")
            .withUserConfiguration(UserCatalogConfiguration.class)
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(CatalogService.class);

                CatalogService catalog =
                    context.getBean(CatalogService.class);

                assertThat(catalog.name()).isEqualTo("Custom Catalog");
                assertThat(catalog.maxItems()).isEqualTo(7);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService customCatalogService() {
            return new CatalogService("Custom Catalog", 7);
        }
    }
}
~~~

### 10.2. Result Matrix

| Test | Input | Expected outcome |
| --- | --- | --- |
| Feature disabled | `enabled=false` | Context succeeds, no `CatalogService` |
| Valid file | `enabled=true`, location points to valid file | Context succeeds, service holds exact data |
| Missing file | `enabled=true`, location points to non-existent file | Context fails, error includes location |
| Blank location | `enabled=true`, empty location | Binding/validation fails before reading file |
| Malformed content | `catalog.max-items=many` | Bean creation fails with parse error naming the key |
| User bean override | Application supplies `CatalogService` | Default configuration backs off, default location unneeded |

The last test is especially helpful: the nested configuration with `@ConditionalOnMissingBean` wraps `@EnableConfigurationProperties`. When the application supplies `CatalogService`, default properties do not bind and the default file is never read.

### 10.3. Running the Tests

In the project directory:

~~~bash
mvn clean test
~~~

There are six independent tests. Expected result is all six passing and Maven reporting `BUILD SUCCESS`. These are expectations from the example assertions; run the command in your project environment to confirm specific dependencies/plugins and runtime behavior.

### 10.4. Why Should Tests Verify the Context Rather Than Only Calling Helpers?

Testing only the file-reading function leaves untested:

- Whether `@ConditionalOnProperty` matches properly.
- Whether `@EnableConfigurationProperties` binds and validates properly.
- Whether `@ConditionalOnMissingBean` backs off properly.
- Whether Spring wraps exceptions in `BeanCreationException`.
- Whether context refresh succeeds or fails in the right scenarios.

`ApplicationContextRunner` tests the full auto-configuration flow in a small scope, far faster than booting the whole application for every test.

## 11. Diagnosing Errors Once the Condition Already Matched

When logs show the auto-configuration was applied yet the application still fails, investigate in sequence.

### 11.1. Read the First Exception of the Failing Bean

Find the bean name in `BeanCreationException`, for example:

~~~text
Error creating bean with name 'catalogService'
~~~

Then trace the `Caused by` chain to the deepest root cause. A chain might look like:

~~~text
BeanCreationException
  -> IllegalStateException:
       Cannot read catalog resource 'file:./config/catalog.properties'
       -> FileNotFoundException
~~~

The outermost message tells which bean failed to create; the deepest cause typically tells which operation failed.

### 11.2. Categorize by Failure Point

| Symptom | Where to inspect |
| --- | --- |
| `ConfigurationPropertiesBindException` / `BindException` | Property names, data types, conversion, and config sources |
| Validation exception | Constraints, missing/blank properties, nested `@Valid` |
| `UnsatisfiedDependencyException` | Which bean dependency could not be injected |
| `NoSuchBeanDefinitionException` | Missing bean definition or condition did not register it |
| `NoUniqueBeanDefinitionException` | Multiple bean candidates for a single-valued injection |
| `BeanCreationException` | Constructor, `@Bean` method, init callbacks, or dependencies |
| `FileNotFoundException` | Location, working directory, mounts, and filename |
| `AccessDeniedException` / `IOException` | Permissions, filesystem, encoding, streams, or I/O |
| `NumberFormatException` / parse exception | Resource contents and value formatting |
| `ConnectException`, timeout, SSL/auth exception | DNS, endpoints, TLS, credentials, and timeouts |

Do not alter the condition merely because you see `BeanCreationException`. If the condition matched properly, fix the failing data, resource, or bean factory logic.

### 11.3. Enable the Condition Evaluation Report

Run the application with `--debug`:

~~~bash
java -jar target/catalog-demo-1.0.0.jar --debug
~~~

The condition report shows which auto-configurations/conditions matched or did not match. If `CatalogAutoConfiguration` matched, the report confirms the property gate opened.

However, the condition report does not inspect file contents and does not prove `CatalogService` was created successfully. Once you confirm the condition matched, continue reading the failing bean's stack trace.

If the application started and includes Actuator, the `conditions` endpoint can supply the report. When the context fails to start, rely on startup logs, failure analysis, and the exception chain.

### 11.4. Using `FailureAnalyzer` and Actionable Messages

Spring Boot invokes registered `FailureAnalyzer`s when startup fails. An analyzer turns a technical exception into a message with Description and Action.

For custom libraries, you can provide an analyzer for domain-specific exceptions when default messages are unclear. Ensure the message states:

- Which bean/feature failed.
- Which resource or property is involved.
- What root error occurred.
- What the operator should check next.

Never put secrets, passwords, tokens, or sensitive content into error messages.

## 12. Lazy Initialization, Retries, and Health Checks: Choosing the Right Check Time

### 12.1. Lazy Initialization Does Not Fix Bad Configuration

When enabled:

~~~properties
spring.main.lazy-initialization=true
~~~

Beans are created on demand instead of during startup. This can speed up startup, yet configuration/resource errors surface only when the bean is first used.

Lazy initialization helps when beans are genuinely optional or rarely used. It is not an error-handling strategy for mandatory resources. If a feature needs a file for every request, delaying detection of a missing file pushes failures into production after traffic arrives.

You can use `@Lazy(false)` for beans that must initialize eagerly even when global lazy initialization is enabled.

### 12.2. Retries Fit Only Recoverable Errors

Retries can help with network timeouts or temporarily unavailable services. They cannot fix:

- Permanently wrong file paths.
- Missing properties.
- Unparseable values.
- Incompatible file schemas.
- Misconfigured permissions.

Never retry indefinitely during bean initialization. When retries are needed, set timeouts, attempt limits, backoff, and clear final-state logging.

### 12.3. Readiness and Health Differ from Startup Conditions

A client bean can be created cleanly even if a remote service is temporarily unavailable. Health/readiness can then reflect capacity to serve traffic.

Conversely, if a bean factory method connects remotely during bean creation and throws an exception, the context may fail to start before health endpoints come up. Pick one clear policy:

- **Dependency mandatory before serving traffic:** check readiness and keep the instance unready or fail startup as required.
- **Interruptible dependency:** construct the client safely, apply timeouts/retries/circuit breakers, and handle failures at runtime.

## 13. Common Mistakes and Fixes

| Mistake / misconception | Why it is wrong | Resolution |
| --- | --- | --- |
| Condition match means the bean is guaranteed to be created | Conditions control only registration | Check binding, factory method, dependencies, and init |
| `@ConditionalOnProperty` verifies the file a property points to | It reads only `Environment` values | Open the resource inside the bean/service |
| `@ConditionalOnResource` validates file content | It checks only resource presence | Parse and validate contents after opening |
| Calling `exists()` and assuming `getInputStream()` always succeeds | Resources can change or fail on open | Catch `IOException` at the actual read operation |
| Using `@Value` for multiple related properties | Hard to group types and cross-validate fields | Use `@ConfigurationProperties` |
| Checking only that the location string is non-empty | A syntactically valid path may not exist | Test opening the resource and report the location |
| Catching exceptions and returning an empty object | Application runs with corrupt state | Fail fast or use intentional fallback |
| Reading files inside conditions | I/O occurs during config registration, hard to diagnose | Read inside factory methods/services |
| Connecting remotely inside constructors | Startup unnecessarily depends on network availability | Create client first, connect under runtime policy |
| Enabling lazy initialization to hide errors | Errors appear only when the bean is first used | Keep eager init for mandatory dependencies |
| Inspecting only the condition report | Report does not verify bean initialization | Read the exception chain and test the context |
| Using relative paths without documenting working directory | IDE/Maven/containers have different working directories | Use absolute paths or stable mount paths |
| Logging full configuration on error | Can leak credentials/secrets | Log only keys/locations and non-sensitive details |

## 14. Review Checklist for Auto-Configuration with External Resources

Before releasing a library, verify:

- [ ] Conditions check only feature flags, classpath, beans, or appropriate metadata.
- [ ] No I/O, network calls, database access, or `getBean()` calls happen inside conditions.
- [ ] Properties bind to strongly typed `@ConfigurationProperties`.
- [ ] Proper constraints are enabled with `@Validated` and a validation implementation is on the classpath.
- [ ] Nested properties have `@Valid` when cascaded validation is needed.
- [ ] Resource locations follow clear rules for `classpath:`, `file:`, or URLs.
- [ ] Relative paths document the working directory; production uses stable paths.
- [ ] Streams are closed with try-with-resources.
- [ ] Charsets are specified explicitly instead of relying on platform defaults.
- [ ] File contents are parsed and validated after opening.
- [ ] Exceptions state the bean, property/resource, and corrective action.
- [ ] Mandatory dependencies fail fast; optional dependencies have documented fallbacks.
- [ ] Remote connections have appropriate timeout/retry/health policies.
- [ ] User-defined bean overrides are tested and not forced to supply default resources unnecessarily.
- [ ] Tests cover disabled, valid, missing, malformed, and invalid input cases.
- [ ] Condition report and exception chains are used appropriately.
- [ ] Lazy initialization does not defer failures of mandatory dependencies.

## 15. Self-Check Questions

**Question 1.** Does `@ConditionalOnProperty` matching prove the `@Bean` method runs cleanly?  
**Answer:** No. It only permits registering the configuration/bean definition; binding, dependency injection, and the factory method can still fail.

**Question 2.** Can `acme.catalog.enabled=true` and `acme.catalog.location=file:./missing.properties` let the condition match while bean creation fails?  
**Answer:** Yes. The property gate matches, yet when the factory method opens the resource, the operation throws `IOException` and fails bean creation.

**Question 3.** Does `@ConditionalOnResource` guarantee the file has required keys?  
**Answer:** No. It checks resource presence; contents must be read, parsed, and validated separately.

**Question 4.** When should `@ConfigurationProperties` be used over multiple `@Value` fields?  
**Answer:** When dealing with a structured group of properties needing type-safe binding, relaxed binding, and centralized validation.

**Question 5.** Why might `@Validated` be present yet constraints never run?  
**Answer:** A Jakarta Validation implementation may be missing from the classpath, or the properties bean was not registered via an appropriate mechanism.

**Question 6.** A file exists yet `getInputStream()` fails. What should be checked?  
**Answer:** Permissions, filesystem/mounts, working directory, URL handler, resource descriptor, and I/O errors at open time.

**Question 7.** Should `Condition.matches()` call an HTTP endpoint to decide on a bean?  
**Answer:** No. Conditions run during configuration processing; remote calls create side effects, nondeterminism, and brittle startups.

**Question 8.** When `--debug` shows the auto-configuration matched yet the context still fails, what is the next step?  
**Answer:** Locate the bean name in `BeanCreationException`, trace `Caused by`, classify as binding/validation/dependency/resource, and fix the root cause.

**Question 9.** When is lazy initialization appropriate?  
**Answer:** For optional or rarely used beans where deferring errors is acceptable. It should not hide missing mandatory resources.

**Question 10.** A user provides a custom `CatalogService`. Should they be forced to supply a default catalog file when the default bean is unused?  
**Answer:** No. Place `@ConditionalOnMissingBean` on a nested default configuration alongside `@EnableConfigurationProperties` so location binding and file reading happen only when the default service is actually needed.

## 16. Key Takeaways and References

- A condition match only allows Spring to register a configuration/bean definition; beans can still fail during binding, validation, dependency injection, factory methods, or initialization.
- `@ConditionalOnProperty` checks `Environment`; `@ConditionalOnResource` checks resource presence. Neither annotation validates file contents.
- Combining `@ConfigurationProperties`, `@Validated`, and Jakarta constraints catches bad inputs before dependent beans are created.
- Use `ResourceLoader`/`Resource` to read classpath, file, or URL resources; close streams and handle `IOException` with context.
- Validate resources inside beans/services; never read files or call networks inside conditions.
- Mandatory dependencies should fail fast with concrete messages; optional dependencies need explicit fallbacks; remote dependencies need timeout, retry, and readiness policies.
- `--debug` displays the condition evaluation report; the exception chain and `FailureAnalyzer` help diagnose bean creation failures.
- `ApplicationContextRunner` tests both match/no-match and failures occurring after conditions match.

Official Spring Boot 3.3.13 and Spring Framework 6.1 Documentation:

1. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — condition annotations, resource conditions, bean registration, and `ApplicationContextRunner`.
2. [Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html) — property sources, `@ConfigurationProperties`, validation, and external config files.
3. [SpringApplication — Startup Failure and Lazy Initialization](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) — `FailureAnalyzer`, `--debug`, and limits of lazy initialization.
4. [ConditionalOnProperty Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html) — property matching rules and `havingValue`/`matchIfMissing`.
5. [ConditionalOnResource Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html) — resource condition.
6. [ConfigurationProperties Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html) — binding external properties.
7. [Resource Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/Resource.html) — `exists()`, `isReadable()`, `getInputStream()`, and resource descriptions.
8. [ResourceLoader Javadoc — Spring Framework 6.1](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/io/ResourceLoader.html) — creating resources by location.
9. [ApplicationContextRunner Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html) — testing auto-configurations in isolated contexts.
