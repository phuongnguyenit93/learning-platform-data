# Loading Test Sources with @TestPropertySource and Understanding Config Data Limits

## 1. Lesson Objectives

In Spring Boot, the same application can run in multiple environments thanks to externalized configuration. When writing integration tests, we often want to override values such as `app.client.timeout`, `app.feature.enabled`, mock server URLs, or test-specific database connection details.

The Spring TestContext Framework provides `@TestPropertySource` to add **test-specific property sources** into the application context's `Environment`. It is a convenient mechanism when a test needs a few inline values or a small `.properties` file.

Example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=150ms",
    "app.client.enabled=false"
})
class ClientConfigurationTest {

    @Test
    void contextLoads() {
    }
}
~~~

However, `@TestPropertySource` is **not** a loader for full Spring Boot Config Data. Boot Config Data handles `application.yml`, `application-{profile}.yml`, multi-document activation, location groups, and `spring.config.import` via its own startup pipeline. A test-specific property source can override Config Data values after being added to the context, yet that does not give it all Config Data features.

This lesson aims at six outcomes:

1. Using `properties` and `locations` in `@TestPropertySource`.
2. Understanding file paths, annotation inheritance, and precedence order.
3. Distinguishing `.properties` file loading from YAML loading via Boot Config Data.
4. Picking `@ActiveProfiles`, `@SpringBootTest(properties)`, and `@DynamicPropertySource` for the right scenarios.
5. Recognizing risks around properties read very early by Boot.
6. Writing stable tests independent of developer environments and free of exposed secrets.

## 2. PropertySource, Environment, and Binder

In Spring Framework, `Environment` maintains a collection of `PropertySource` instances. Each source can contribute values for keys. When multiple sources declare `app.client.timeout`, the source with higher precedence generally determines the effective value.

~~~text
application.yml / application-test.yml
               |
        Boot Config Data
               |
               v
           Environment
               ^
               |
     @TestPropertySource
      |           |
 inline values  .properties file
               |
               v
      @ConfigurationProperties
               |
               v
           Bean under test
~~~

`@TestPropertySource` adds property sources into the test context's `Environment`. Afterward, `@Value` or `@ConfigurationProperties` can consume them.

For example, by default:

~~~properties
app.client.timeout=3s
~~~

Test declares:

~~~java
@TestPropertySource(properties = "app.client.timeout=200ms")
~~~

When the test source is applied as expected, a `@ConfigurationProperties` bean receives timeout `200ms` instead of `3s`.

**Two questions to keep separate:** is the value present in `Environment`, and did the bean bind/convert types properly? A key's presence does not guarantee every bean is registered or all validation rules pass.

## 3. Complete Example with @ConfigurationProperties

Class:

~~~java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.client")
public record ClientProperties(
        Duration timeout,
        boolean enabled,
        String endpoint
) {}
~~~

Application:

~~~java
package com.example.demo;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {}
~~~

Default resource:

~~~yaml
# src/main/resources/application.yml
app:
  client:
    timeout: 3s
    enabled: true
    endpoint: "https://default.example.test"
~~~

Test:

~~~java
package com.example.demo;

import com.example.demo.config.ClientProperties;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=250ms",
    "app.client.enabled=false",
    "app.client.endpoint=https://mock.example.test"
})
class ClientPropertiesTest {

    @Autowired ClientProperties properties;

    @Test
    void bindsTestValues() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofMillis(250));
        assertThat(properties.enabled()).isFalse();
        assertThat(properties.endpoint())
            .isEqualTo("https://mock.example.test");
    }
}
~~~

Spring Boot converts `250ms` to `Duration` and `false` to `boolean` during binding. The annotation does not modify `application.yml`; it only contributes values into the test's context.

### 3.1. Why Should Tests Use Fake Endpoints?

If a test uses a production URL, it could accidentally call a live system. Prefer stub/mock servers or non-routable endpoints in tests that do not send requests. When a real test server is needed, start it within the test lifecycle and supply its dynamic URL appropriately.

### 3.2. When Is a Spring Context Unnecessary?

A plain Java unit test with directly constructed objects does not get properties injected by TestContext. For example:

~~~java
ClientProperties props =
        new ClientProperties(Duration.ofSeconds(1), true, "local");
~~~

No Binder, no Spring `Environment`, and `@TestPropertySource` has no effect. Use Spring test annotations only when verifying Spring context or binding behavior.

## 4. Inline Properties Syntax

`@TestPropertySource` has a `properties` attribute for declaring one or more key/value strings:

~~~java
@TestPropertySource(properties = {
    "demo.name=integration",
    "demo.port=18080",
    "demo.mode:test"
})
~~~

Spring Test supports Java properties syntax such as `key=value`, `key:value`, or valid separators. Standardize on **`key=value`** for readability and to avoid unnecessary literal variations.

### 4.1. Values with Special Formatting

Example:

~~~java
@TestPropertySource(properties = {
    "client.connect-timeout=500ms",
    "client.endpoint=https://api.example.test/v1?mode=fast",
    "client.enabled=true"
})
~~~

The `=` in the URL query string is part of the value, not a new property. However, complex payloads, multiline values, PEM blocks, or credentials should not be stuffed into annotations. Use an appropriate fixture or secure runtime source instead.

### 4.2. Never Put Real Credentials in Test Source Code

A string hardcoded in an annotation gets committed to Git and ends up in test artifacts. Use fake tokens or minimal-privilege sandbox accounts; never put production tokens inside `@TestPropertySource`.

### 4.3. Test Context Cache and Literal Strings

Spring TestContext uses test property metadata to compute context cache keys. Two classes with identical semantics but different literal formatting can reduce context reuse:

~~~java
@TestPropertySource(properties = "demo.port=8081")
~~~

and:

~~~java
@TestPropertySource(properties = "demo.port = 8081")
~~~

Use consistent formatting across the test suite to avoid unnecessary context restarts.

## 5. Loading Files via locations

Layout:

~~~text
src/test/resources/
└── config/
    └── client-test.properties
~~~

Contents:

~~~properties
app.client.timeout=400ms
app.client.enabled=false
app.client.endpoint=https://stub.example.test
~~~

Test:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/client-test.properties"
)
class ClientFileTest {
}
~~~

`locations` (or its alias `value`) accepts one or more Spring resource locations. By default, Spring Test supports traditional Java `.properties` files and corresponding XML properties files.

### 5.1. Relative Paths

Suppose a test class belongs to package `com.example.demo`. Writing:

~~~java
@TestPropertySource("client-test.properties")
~~~

resolves the plain path relative to the **test class's package**, equivalent to a classpath resource such as:

~~~text
classpath:com/example/demo/client-test.properties
~~~

It does not resolve relative to the working directory where Maven/Gradle runs.

### 5.2. Paths from Classpath Root

~~~java
@TestPropertySource("/config/client-test.properties")
~~~

or:

~~~java
@TestPropertySource("classpath:/config/client-test.properties")
~~~

explicitly locates the resource from the classpath root.

### 5.3. Multiple Files

~~~java
@TestPropertySource(locations = {
    "classpath:/config/common-test.properties",
    "classpath:/config/payment-test.properties"
})
~~~

can be used to split fixtures. If the same key is set in multiple files, control ordering/precedence rather than treating it as a complex merge mechanism. Avoid scattering critical settings across too many files.

### 5.4. Missing Resources

If a required location does not exist or cannot be read, the test context fails during initialization. Check filename, package, spelling, path, and whether the build copies the resource onto the test classpath.

## 6. Omitting Both locations and properties

An empty annotation:

~~~java
@TestPropertySource
class MyIntegrationTest {
}
~~~

does not mean "enable test properties without loading anything." Spring TestContext follows a convention that looks for a default file matching the class name.

For `com.example.demo.MyIntegrationTest`, the expected location is:

~~~text
classpath:com/example/demo/MyIntegrationTest.properties
~~~

If the file is missing, context creation throws `IllegalStateException`.

Therefore, unless intentionally using the default-file convention, declare `properties` or `locations` explicitly; never leave `@TestPropertySource` empty as decoration.

## 7. Combining Files and Inline Properties

You can declare:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/client-test.properties",
    properties = {
        "app.client.timeout=100ms",
        "app.client.enabled=true"
    }
)
class FastClientTest {
}
~~~

Suppose the file contains:

~~~properties
app.client.timeout=400ms
app.client.enabled=false
app.client.endpoint=https://stub.example.test
~~~

Per Spring TestContext, **inline test properties take higher precedence than test properties loaded via locations**. Expected values:

| Key | File | Inline | Effective value |
| --- | --- | --- | --- |
| `app.client.timeout` | `400ms` | `100ms` | `100ms` |
| `app.client.enabled` | `false` | `true` | `true` |
| `app.client.endpoint` | Stub URL | Not set | Stub URL |

This works nicely when multiple tests share a fixture while one test needs a small override. When too many keys change, consider creating another fixture or a dedicated profile.

## 8. Precedence Relative to Other Sources

Spring TestContext specifies that test property sources take higher precedence than many regular sources, including OS environment variables, Java system properties, and standard application property sources.

Key rules:

- `@TestPropertySource(properties = ...)` outranks `@TestPropertySource(locations = ...)`.
- `@DynamicPropertySource` is documented by Spring TestContext as having higher precedence than `@TestPropertySource`.
- Spring Boot also adds sources from `@SpringBootTest(properties = ...)` and test slice annotations, with precedence rules matching how Boot prepares the context.

**Practical recommendation:** never define the same key in multiple annotations just to rely on precedence. If a scenario genuinely requires combining them, assert the final value from `Environment` and consult docs for your exact framework version.

### 8.1. Why Precedence Affects Tests

Suppose a default file sets:

~~~properties
app.client.timeout=3s
~~~

while a test superclass has:

~~~java
@TestPropertySource(properties = "app.client.timeout=1s")
~~~

and a subclass has:

~~~java
@TestPropertySource(properties = "app.client.timeout=200ms")
~~~

When inheritance is enabled, the subclass value overrides according to merge rules. If a dynamic source also defines the same key, effective behavior depends on the dynamic source and registration order. Tests should intentionally designate one authoritative source for critical values.

## 9. Major Limitation: YAML Is Not Supported by Default

Spring Boot loads files like:

~~~text
application.yml
application.yaml
application-test.yml
~~~

through Config Data. However, `@TestPropertySource` does not automatically invoke Boot's YAML loader when you write:

~~~java
@TestPropertySource("classpath:/client-test.yml")
~~~

Per Spring Boot documentation, YAML is not loaded directly by `@PropertySource` or `@TestPropertySource` by default. Spring Test reads Java Properties/XML properties by default; YAML is a different format.

### 9.1. Do Not Assume YAML Parsed Properly Just Because No Exception Was Thrown

If a YAML file has nested structure:

~~~yaml
app:
  client:
    timeout: 200ms
    enabled: false
~~~

a Java properties reader can misinterpret each line unexpectedly. A test not crashing does not prove `app.client.timeout` and `app.client.enabled` were actually created.

To verify, assert both the value from `Environment` and the bound value in the bean.

### 9.2. Loading YAML Properly via Boot Config Data

Place:

~~~text
src/test/resources/application-it.yml
~~~

Contents:

~~~yaml
app:
  client:
    timeout: 200ms
    enabled: false
~~~

Test:

~~~java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("it")
class ClientProfileTest {
}
~~~

When Spring Boot bootstraps the test context with profile `it` active, Config Data loads `application-it.yml` per Boot's rules. No `@TestPropertySource(locations = "...yml")` is needed.

## 10. Custom PropertySourceFactory Since Spring Framework 6.1

Starting in Spring Framework 6.1, `@TestPropertySource` provides a `factory` attribute to specify a custom `PropertySourceFactory` for reading formats such as YAML or JSON.

Example factory for a single-document YAML file:

~~~java
import java.io.IOException;
import org.springframework.boot.env.YamlPropertySourceLoader;
import org.springframework.core.env.PropertySource;
import org.springframework.core.io.support.EncodedResource;
import org.springframework.core.io.support.PropertySourceFactory;

public class SingleYamlTestFactory implements PropertySourceFactory {

    @Override
    public PropertySource<?> createPropertySource(
            String name,
            EncodedResource resource
    ) throws IOException {
        var list = new YamlPropertySourceLoader().load(
            name != null ? name : "test-yaml",
            resource.getResource()
        );

        if (list.size() != 1) {
            throw new IllegalArgumentException(
                "Expected one YAML document for this test factory"
            );
        }
        return list.get(0);
    }
}
~~~

In Spring Framework with `factory`:

~~~java
@TestPropertySource(
    locations = "classpath:/client-test.yml",
    factory = SingleYamlTestFactory.class
)
class ClientTest {
}
~~~

This example handles a single-document YAML file, not a full Config Data loader implementation. If multiple YAML documents exist, the factory must process them under an explicit policy.

**Important:** a custom factory parses YAML into a `PropertySource`, yet does not automatically support `spring.config.import`, `spring.config.activate.on-profile`, location groups, profile-specific resolution, or other Spring Boot Config Data semantics. If your goal is testing those features, use Boot Config Data directly.

## 11. Where Does Config Data Differ from TestPropertySource?

Spring Boot Config Data handles:

- `application.properties`, `application.yml`, and supported filename variants.
- `application-{profile}.properties` and `application-{profile}.yml`.
- Multi-document YAML and multi-document properties.
- `spring.config.activate.on-profile` and other activation conditions.
- `spring.config.import` to import additional Config Data.
- `optional:` for locations allowed to be absent.
- `spring.config.location` and `spring.config.additional-location`.
- Location groups, property-source ordering, and specialized precedence rules.

By contrast, `@TestPropertySource` mainly takes a set of key/value pairs and inserts them into the test context's Environment. It is **not a general-purpose entrypoint** for all Config Data rules.

### 11.1. Reading a File Does Not Mean Config Data Processing Ran

A custom factory can flatten YAML into a map:

~~~text
app.client.timeout -> 200ms
app.client.enabled -> false
~~~

Yet if the file also contains:

~~~yaml
spring:
  config:
    import: "classpath:/config/extra.yml"
~~~

the factory may simply store `spring.config.import` as a plain string in the map. That does not make Boot re-run the Config Data resolver to import `extra.yml`.

### 11.2. Implications for Testing

If you are testing **Binder behavior** on a few defined properties, `@TestPropertySource` is enough.

If you are testing **Config Data loading rules** involving profiles, imports, or location precedence, use a real Config Data file loaded by Boot. Different goals require different setups.

## 12. Properties Read Very Early

Certain properties control where Spring Boot looks for Config Data:

~~~properties
spring.config.name=custom
spring.config.location=classpath:/cfg/
spring.config.additional-location=file:./external/
~~~

Boot needs these values **before searching for files**. Boot documentation instructs supplying them as early environment properties—for example via OS environment variables, JVM system properties, or command-line arguments.

Do not expect:

~~~java
@TestPropertySource(properties =
    "spring.config.location=classpath:/cfg/")
~~~

to make Boot restart the entire Config Data discovery step when TestContext processes the annotation.

### 12.1. Why Can the Final Environment Mislead You?

An assertion:

~~~java
assertThat(environment.getProperty("spring.config.location"))
    .isEqualTo("classpath:/cfg/");
~~~

only shows the key exists in `Environment` after the context is prepared. It **does not prove** files at `classpath:/cfg/` were loaded during Config Data bootstrap.

To test a location, assert a marker key that exists only in the target file, such as `loaded.from.custom.location=true`.

### 12.2. Better Alternatives

- Use `@ActiveProfiles` with `application-it.yml` when testing profiles.
- Place `spring.config.import` inside a **real Config Data document** when testing imports.
- For custom Config Data locations, use a test harness that sets early properties in the right phase.
- Do not use a regular test-source annotation as a substitute for full early Boot configuration.

## 13. @ActiveProfiles and application-test.yml

`@ActiveProfiles` is a Spring TestContext annotation specifying active profiles for a test's application context.

~~~java
@SpringBootTest
@ActiveProfiles("test")
class PaymentIntegrationTest {
}
~~~

Example:

~~~text
src/main/resources/application.yml
src/test/resources/application-test.yml
~~~

Spring Boot normally loads `application-test.yml` through Config Data when profile `test` is active, applying standard precedence rules.

`application-test.yml`:

~~~yaml
payment:
  gateway:
    endpoint: "https://sandbox.example.test"
    connect-timeout: 100ms
    enabled: false
~~~

Tests can inject a `@ConfigurationProperties` bean to assert timeout and endpoint, or test corresponding service behavior.

### 13.1. Combining with Inline Overrides

~~~java
@SpringBootTest
@ActiveProfiles("test")
@TestPropertySource(properties =
    "payment.gateway.connect-timeout=50ms")
class FastGatewayTest {
}
~~~

Boot loads profile configuration first via Config Data; TestContext adds an override on top. This is a concise way to keep most settings in YAML while changing one field for a single test class.

### 13.2. When Testing Profile Behavior Itself

If the goal is verifying that profile `test` selects the right document, **do not** add an inline override for the exact key you want to observe. That would mask bugs in the profile file.

## 14. Multi-Document YAML and Activation

Boot Config Data can process:

~~~yaml
app:
  cache:
    ttl: 30s

---
spring:
  config:
    activate:
      on-profile: it

app:
  cache:
    ttl: 1s
~~~

With `@ActiveProfiles("it")`, the second document activates and overrides `app.cache.ttl` per Config Data rules.

A generic `PropertySourceFactory` does not inherently understand that the second document applies only when profile `it` is active. When testing activation logic, use Boot Config Data.

### 14.1. Profile-Specific Files Differ from Document Activation

Two mechanisms:

~~~text
application-it.yml
~~~

and:

~~~yaml
spring:
  config:
    activate:
      on-profile: it
~~~

both serve profile-based configuration, yet Boot processes them according to distinct rules and locations. Do not assume `@TestPropertySource` participates in those steps automatically.

## 15. Testing spring.config.import Properly

Suppose test resources contain:

~~~text
src/test/resources/
  application-it.yml
  config/remote-it.yml
~~~

`application-it.yml`:

~~~yaml
spring:
  config:
    import: "classpath:/config/remote-it.yml"

app:
  client:
    timeout: 1s
~~~

`config/remote-it.yml`:

~~~yaml
app:
  client:
    timeout: 80ms
    enabled: false
~~~

Test:

~~~java
@SpringBootTest
@ActiveProfiles("it")
class ConfigDataImportTest {

    @Autowired ClientProperties properties;

    @Test
    void importIsApplied() {
        assertThat(properties.timeout())
            .isEqualTo(Duration.ofMillis(80));
        assertThat(properties.enabled()).isFalse();
    }
}
~~~

In this straightforward case, Spring Boot processes `spring.config.import` during Config Data loading; values from the imported file take precedence per Boot rules over the document importing it.

### 15.1. Contrast with Imports Placed Inside a @TestPropertySource File

If `client-test.properties` loaded via `@TestPropertySource` contains:

~~~properties
spring.config.import=classpath:/config/remote-it.yml
~~~

do not conclude Boot imported `remote-it.yml` under Config Data semantics. Checking only that `spring.config.import` exists in `Environment` is insufficient; assert a key defined exclusively in the imported file.

### 15.2. Optional Imports

~~~yaml
spring:
  config:
    import: "optional:classpath:/config/remote-it.yml"
~~~

`optional:` allows the location to be absent per Boot rules. If you want to test failure when a required file is missing, omit `optional:` and write a test asserting the expected failure.

## 16. Where Does @SpringBootTest(properties) Fit?

Spring Boot provides a `properties` attribute on `@SpringBootTest`:

~~~java
@SpringBootTest(properties = {
    "app.client.timeout=75ms",
    "app.client.enabled=true"
})
class ClientBootTest {
}
~~~

It is similar to `@TestPropertySource(properties=...)` in its goal of **supplying static overrides to the test context**, as a native Boot annotation attribute.

Comparison table:

| Need | Usually appropriate tool |
| --- | --- |
| A few values for a Boot integration test | `@SpringBootTest(properties=...)` |
| Spring TestContext test source | `@TestPropertySource(properties=...)` |
| `.properties` fixture file | `@TestPropertySource(locations=...)` |
| YAML and profile-specific Config Data | `@ActiveProfiles` + `application-{profile}.yml` |
| Dynamic ports, container URLs | `@DynamicPropertySource` |
| Lean auto-config and binding tests | `ApplicationContextRunner` |
| Config needed during earliest bootstrap | Early environment in test harness |

Do not use both `@SpringBootTest(properties)` and `@TestPropertySource(properties)` simultaneously to declare the same key unless explicitly testing precedence.

## 17. @DynamicPropertySource for Runtime-Generated Values

Some values are known only after test resources start, such as the port of a Testcontainers PostgreSQL instance or WireMock server.

`@DynamicPropertySource` registers a supplier for values:

~~~java
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;

@DynamicPropertySource
static void registerDynamicValues(DynamicPropertyRegistry registry) {
    registry.add("app.remote.port", () -> mockServer.getPort());
}
~~~

This is far better than hardcoding a random port into `@TestPropertySource`.

### 17.1. Testcontainers Example

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class RepositoryIntegrationTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Test
    void repositoryWorks() {
        // Integration test against the container.
    }
}
~~~

This requires Testcontainers dependencies, a compatible container runtime, and real service configuration. The `@DynamicPropertySource` method does not manage the container's lifecycle by itself.

### 17.2. Avoid Declaring the Same Key in Two Places

For example:

~~~java
@TestPropertySource(properties =
    "spring.datasource.url=jdbc:h2:mem:test")
~~~

while also registering `spring.datasource.url` via a dynamic supplier creates competing sources. If the test truly requires PostgreSQLContainer, remove the static H2 key or separate the two test configurations.

Per Spring TestContext, dynamic properties take higher precedence on the same key, yet having one authoritative source is clearer and more reliable.

## 18. Inheriting Property Sources from Test Superclasses

`@TestPropertySource` inherits `locations` and `properties` from superclasses by default.

~~~java
@TestPropertySource(properties = {
    "app.cache.enabled=false",
    "app.client.timeout=1s"
})
abstract class BaseIntegrationTest {
}
~~~

Subclass:

~~~java
@SpringBootTest
@TestPropertySource(properties = {
    "app.client.timeout=100ms"
})
class FastIntegrationTest extends BaseIntegrationTest {
}
~~~

Spring TestContext merges inherited configurations with local declarations per annotation rules, allowing subclasses to override specific keys.

### 18.1. inheritLocations and inheritProperties

~~~java
@TestPropertySource(
    inheritLocations = false,
    inheritProperties = false,
    properties = "app.client.timeout=100ms"
)
~~~

These two flags control inheritance of file locations and inline properties from parent classes, respectively. Both default to `true`. When setting `false`, understand that it **replaces** part of the inherited test configuration rather than merely overriding one key.

### 18.2. Meta-Annotations and Repeatable Annotations

`@TestPropertySource` can appear on composed annotations and in complex test hierarchies. Spring TestContext defines merge and precedence rules across direct, meta-present, and inherited sources.

Across multiple inheritance levels, keep setups explicit; avoid building an override graph where nobody can tell which key wins.

## 19. TestContext Caching and Test Configuration

Spring TestContext caches `ApplicationContext` instances to avoid re-initializing equivalent contexts. Components such as locations, profiles, test properties, and context customizers contribute to the cache key.

Consequences:

- A new inline property can produce a separate context.
- Two classes with compatible configurations can reuse the same context.
- A mutable bean modified directly by one test can affect another test sharing that context.
- A dynamic supplier tied to a resource that changes across subclasses may require lifecycle/cache adjustments.

### 19.1. Do Not Mutate Global Environment Arbitrarily

An anti-pattern:

~~~java
@BeforeEach
void setUp() {
    System.setProperty("app.client.timeout", "100ms");
}
~~~

without restoring it can corrupt other tests in the same JVM or running in parallel.

Prefer declaring test properties in annotations or runners before context creation. If mutating a system property is unavoidable, restore it and serialize concurrent access.

### 19.2. @DirtiesContext Is Not a Cure-All

`@DirtiesContext` prevents the current context from being reused within the configured scope. It helps when state changes are difficult to reset, but restarting contexts is expensive. Never use it to paper over poorly isolated tests.

## 20. Test Slices and Bean Registration

`@SpringBootTest` loads a broad application context, whereas slices such as `@WebMvcTest` or `@DataJpaTest` narrow loaded beans and auto-configurations.

A `@ConfigurationProperties` bean may not appear automatically in a slice test if it falls outside the loaded slice scope.

Minimal configuration example:

~~~java
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

@SpringBootConfiguration
@EnableConfigurationProperties(ClientProperties.class)
class ClientBindingTestConfig {
}
~~~

Test:

~~~java
@SpringBootTest(classes = ClientBindingTestConfig.class)
@TestPropertySource(properties = {
    "app.client.timeout=125ms",
    "app.client.enabled=true",
    "app.client.endpoint=https://stub.example.test"
})
class ClientBindingTest {
}
~~~

If a test cannot find `ClientProperties`, verify bean registration before assuming `@TestPropertySource` failed. The annotation only adds a property source; it does not create target beans.

## 21. Testing Binding and Validation

Suppose:

~~~java
import java.time.Duration;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.retry")
public record RetryProperties(
    @NotNull Duration delay
) {}
~~~

A test with:

~~~java
@TestPropertySource(properties = "app.retry.delay=500ms")
~~~

lets Binder convert the value to `Duration.ofMillis(500)`. If the string is malformed:

~~~java
@TestPropertySource(properties = "app.retry.delay=tomorrow")
~~~

an error occurs during **type conversion** when creating the bean.

An empty or missing required property can violate Bean Validation if a provider is registered. `@TestPropertySource` does not enable validation on its own; that depends on the class, registration, and validation infrastructure.

### 21.1. Never Print Rejected Values Containing Secrets

If a property holds a password or API key, binding errors can surface input values in framework/library exceptions or logs. Use fake canary values in tests and check outputs to ensure secrets never leak.

### 21.2. Testing Failures Separately with ApplicationContextRunner

Spring Boot's `ApplicationContextRunner` is helpful for testing configuration classes or auto-configurations in a lean context:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class RetryFailureTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(RetryTestConfig.class);

    @Test
    void invalidDurationFails() {
        runner.withPropertyValues("app.retry.delay=not-a-duration")
            .run(context ->
                assertThat(context.getStartupFailure()).isNotNull());
    }
}
~~~

`RetryTestConfig` must register `RetryProperties`. Here the runner supplies values via `withPropertyValues`, so `@TestPropertySource` is not needed. Pick tools by test scope rather than booting a full Spring Boot context for every case.

## 22. Checking Which Source Supplied a Property

When a test fails with an unexpected value, start by checking a specific key:

~~~java
import org.springframework.core.env.Environment;

@Autowired Environment environment;

@Test
void propertyValueIsVisible() {
    assertThat(environment.getProperty("app.client.timeout"))
        .isEqualTo("250ms");
}
~~~

Then check the bound bean:

~~~java
@Autowired ClientProperties properties;

@Test
void binderConvertedValue() {
    assertThat(properties.timeout())
        .isEqualTo(Duration.ofMillis(250));
}
~~~

These two steps distinguish:

1. **Source/configuration problem:** key is missing or overridden by another source.
2. **Binding problem:** key exists, yet the bean fails to bind due to prefix mismatch, conversion error, or missing bean registration.

### 22.1. Never Dump Environment in CI Logs

`Environment` can hold credentials from CI, developer machines, or test containers. Avoid printing all `PropertySources`, `System.getenv()`, or raw rejected values. When diagnosing issues, log key names and safe source descriptions rather than sensitive values.

### 22.2. Diagnosing Early Locations

If a test sets `spring.config.location` yet the new file does not appear to load, do not inspect only that location property. Place a unique marker property inside the target file:

~~~properties
test.location.marker=loaded
~~~

and assert `test.location.marker` in `Environment`. This proves the file actually contributed data rather than the location string merely being added too late.

## 23. Practical Scenarios

### 23.1. A Single Feature Flag

~~~java
@SpringBootTest
@TestPropertySource(properties = "feature.catalog.enabled=false")
class CatalogDisabledTest {
}
~~~

Ideal inline usage: one static key requiring no new profile or file.

### 23.2. A Multi-Property Fixture

File:

~~~properties
# src/test/resources/config/payment-test.properties
payment.gateway.endpoint=https://sandbox.example.test
payment.gateway.timeout=1s
payment.gateway.enabled=false
~~~

Test:

~~~java
@SpringBootTest
@TestPropertySource(
    locations = "classpath:/config/payment-test.properties"
)
class PaymentIntegrationTest {
}
~~~

Good choice for reusing several simple properties without needing YAML activation.

### 23.3. Testing Profile-Specific YAML

File `src/test/resources/application-it.yml`, test:

~~~java
@SpringBootTest
@ActiveProfiles("it")
class ConfigDataProfileTest {
}
~~~

Ideal for testing profile-specific Config Data.

### 23.4. Testing YAML Imports

File `application-it.yml` has `spring.config.import=classpath:/config/extra-it.yml`. Use `@ActiveProfiles("it")` and assert a marker from the imported file. Do not place the import inside a `@TestPropertySource` file when verifying the Config Data bootstrap path.

### 23.5. Testing Random Ports

A mock server or Testcontainers assigns a port at startup: use `@DynamicPropertySource` to register a supplier. Never hardcode the port into `@TestPropertySource`.

### 23.6. Testing Custom Early Config Data Locations

To test `spring.config.location` or `spring.config.name`, use a harness supplying values before Config Data processing runs, rather than adding test properties afterward.

## 24. Common Misconceptions

### 24.1. "@TestPropertySource loads YAML out of the box"

False by default. It loads `.properties` and XML properties; YAML needs Config Data or a custom factory (Framework 6.1+) with explicit limitations.

### 24.2. "@TestPropertySource is Config Data"

False. It adds property sources to the test context. It does not automatically process `spring.config.import`, profile activation, or Boot location resolution.

### 24.3. "Presence of spring.config.import in Environment proves import ran"

False. `Environment` may contain a `spring.config.import` string that Boot never processed as a directive in the right phase. Assert data originating from the imported location.

### 24.4. "@ActiveProfiles and @TestPropertySource are interchangeable"

False. `@ActiveProfiles` selects active profiles; `@TestPropertySource` supplies test-specific keys/values. They complement each other with distinct purposes.

### 24.5. "Repeating the same key across every source increases stability"

The opposite is true. Multiple sources declaring the same key obscure tests and create fragile precedence dependencies. Choose one owning source.

### 24.6. "An empty annotation does nothing"

False. It triggers convention lookup for `ClassName.properties` and fails if that file does not exist.

### 24.7. "@TestPropertySource automatically registers @ConfigurationProperties beans"

False. Beans still require scanning, enabling, or explicit registration.

### 24.8. "@TestPropertySource works in plain Java unit tests"

False without a Spring TestContext application context. Plain JUnit does not inject properties into objects.

### 24.9. "A custom YAML factory enables full multi-document activation"

False. A factory that parses YAML does not replace Boot's Config Data resolver/loader.

### 24.10. "@DirtiesContext guarantees complete test isolation"

False. External databases, filesystems, static state, and CI environments can still be shared; design full isolation explicitly.

## 25. Quick Selection Table

| Goal | Recommended tool | Why |
| --- | --- | --- |
| Override 1–5 static keys | `@TestPropertySource(properties=...)` | Concise and explicit |
| Boot integration test with inline overrides | `@SpringBootTest(properties=...)` | Integrated in Boot annotation |
| Many keys from `.properties` | `@TestPropertySource(locations=...)` | Easy to reuse |
| YAML profile testing | `@ActiveProfiles` + `application-it.yml` | Proper Boot Config Data mechanism |
| Multi-document YAML activation | Boot Config Data | Understands activation conditions |
| `spring.config.import` | Real Config Data file | Runs in proper import phase |
| Custom YAML fixture | `@TestPropertySource(factory=...)` if supported | Parses into PropertySource only |
| Dynamic database URL | `@DynamicPropertySource` | Runtime supplier |
| Isolated binding failure test | `ApplicationContextRunner` | Small, fast context |
| Properties read very early by Boot | Early environment / test harness | Avoids late loading |

## 26. Test Implementation Checklist

- [ ] Test actually uses Spring TestContext or Boot test context.
- [ ] Inline `properties` used when only a few fixed keys are needed.
- [ ] `locations` used for simple `.properties` files.
- [ ] Resource paths are explicitly package-relative or classpath-root.
- [ ] Empty annotation avoided unless default-file detection is intentional.
- [ ] Aware that inline values override file locations.
- [ ] Not assuming YAML loads via `@TestPropertySource` by default.
- [ ] Using `@ActiveProfiles` and Boot Config Data when YAML or Config Data semantics are needed.
- [ ] If using a custom `PropertySourceFactory`, testing its limits separately.
- [ ] Not putting early `spring.config.location` in the annotation expecting Boot to reload.
- [ ] Avoiding accidental key overlaps between `@DynamicPropertySource` and `@TestPropertySource`.
- [ ] Using dynamic suppliers for runtime-generated values.
- [ ] Understanding `inheritLocations` and `inheritProperties` when extending test base classes.
- [ ] Using consistent inline formatting to improve context caching.
- [ ] Avoiding uncleaned mutations to system properties or global state.
- [ ] Verifying `@ConfigurationProperties` bean registration.
- [ ] Asserting both keys in `Environment` and bound bean values.
- [ ] Testing conversion/validation instead of only asserting context loads.
- [ ] Keeping production secrets out of test resources.
- [ ] Never dumping Environment or raw exceptions containing credentials to logs.
- [ ] Avoiding `@DirtiesContext` as a default on every test.
- [ ] Asserting marker properties from imported files when testing Config Data imports.

## 27. Reasoning Exercises

### Exercise A: Inline Override

`application.yml` sets `app.timeout=3s`. The test uses:

~~~java
@TestPropertySource(properties = "app.timeout=250ms")
~~~

Which timeout value does Binder see in a standard test context?

**Hint:** a test-specific source overrides application Config Data values.

### Exercise B: File and Inline

`test-client.properties` contains:

~~~properties
app.timeout=1s
app.enabled=false
~~~

Annotation:

~~~java
@TestPropertySource(
    locations = "classpath:/test-client.properties",
    properties = "app.timeout=100ms"
)
~~~

Where do `app.timeout` and `app.enabled` come from?

**Hint:** inline overrides file for matching keys; non-overridden keys come from the file.

### Exercise C: YAML and Import

A test writes:

~~~java
@TestPropertySource("classpath:/application-it.yml")
~~~

expecting `spring.config.import` inside the YAML to load another file automatically.

**Hint:** wrong mechanism. Use Boot Config Data with profile `it`; a custom YAML-parsing factory does not replace Config Data.

### Exercise D: Dynamic Port

A Testcontainer runs PostgreSQL on a random port.

**Hint:** register URL/username/password via `@DynamicPropertySource` or appropriate Testcontainers integration; never hardcode ports.

### Exercise E: Context Cache

Two tests use identical key/value pairs formatted with different literals. Why might this reduce context reuse?

**Hint:** test properties—including their configured literals—form part of the context cache key.

## 28. Conclusion

`@TestPropertySource` is an effective tool for adding **test-specific property sources** to the Spring `Environment`, especially when overriding a few keys or loading `.properties` fixtures for integration tests.

Remember the boundary: **loading a property source is not running Spring Boot Config Data**. Features such as profile-specific YAML, multi-document activation, `spring.config.import`, and early location resolution must be tested through Boot Config Data rather than TestContext annotations alone.

Selection guide:

1. Few static values -> `@TestPropertySource(properties=...)` or `@SpringBootTest(properties=...)`.
2. Many values in `.properties` files -> `@TestPropertySource(locations=...)`.
3. YAML/profiles/imports/Config Data -> `@ActiveProfiles` with Config Data files loaded by Boot.
4. Values generated during test lifecycles -> `@DynamicPropertySource`.
5. Binding/failure tests in a minimal context -> `ApplicationContextRunner`.

Finally, assert results in both `Environment` and bound beans, avoid overlapping multiple sources on the same key, maintain test isolation, watch context caching, and never commit production credentials into fixtures.

### References

- [Spring Framework Reference — Context Configuration with Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html)
- [Spring Framework Reference — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html)
- [Spring Framework API — TestPropertySource](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestPropertySource.html)
- [Spring Framework API — ActiveProfiles](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/ActiveProfiles.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
