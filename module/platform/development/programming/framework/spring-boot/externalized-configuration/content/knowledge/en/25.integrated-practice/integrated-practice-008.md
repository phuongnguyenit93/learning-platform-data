# Writing Tests for Override Rules, Binding, and Validation in Spring Boot

## 1. Practice Objectives

Spring Boot Externalized Configuration lets an application receive configuration from many sources: `application.yml`, `application.properties`, profile-specific files, OS environment variables, Java system properties, command-line arguments, and programmatically added property sources.

When the same key appears in multiple sources, Spring Boot must resolve **precedence**. Next, the Binder converts data into Java types and validation enforces business constraints. All three steps can go wrong or be misunderstood.

A good configuration test suite should be able to answer:

1. When a file sets `retries=1` and the CLI sets `retries=4`, what is the effective result?
2. How is `timeout=750ms` bound into a `Duration`?
3. When `regions` is specified in a higher-precedence profile, are the two lists concatenated?
4. When a `Map<String,Integer>` configuration spans multiple sources, how are overlapping and non-overlapping keys handled?
5. When `retries=many`, does the system fail at binding or validation?
6. When `retries=99`, the Binder converts the type successfully, yet does the validator catch the out-of-range value?
7. When `enabled=true` but `base-url` is missing, does the application context fail fast?
8. When using `@DynamicPropertySource`, do dynamic values override `@TestPropertySource`?
9. Is an `ApplicationContextRunner` test alone enough to prove that an actual Config Data file was loaded?

The assignment focuses on a **reproducible test suite**, rather than merely explaining concepts.

> Distinguish three steps: **property resolution → type-safe binding → validation**. Testing the right step helps pinpoint the root cause when a test fails.

The examples below target Spring Boot 3.x, Java 17+, JUnit Jupiter, and AssertJ.

## 2. Choosing the Test Level by Goal

| Goal | Tool | What it verifies |
| --- | --- | --- |
| Which config source wins? | `StandardEnvironment`, `MapPropertySource` | Precedence order when property names collide |
| Does Binder convert `String` to `Duration`, `int`, `URI`? | `ApplicationContextRunner` | Binding from test properties into a bean |
| Does the bean validate and fail startup? | `ApplicationContextRunner` | Context initialization and binding/validation errors |
| Does `application-it.yml` override the base file? | `@SpringBootTest` + `@ActiveProfiles` | Profile-based Config Data loading |
| Does CLI beat app defaults? | Non-web `SpringApplication` run | Startup source precedence |
| Does a Testcontainers port take effect? | `@DynamicPropertySource` | Dynamic property sources and bean wiring |
| Is a Docker/Kubernetes mounted file found? | Deployment smoke test | Runtime location, working directory, and permissions |

Do not force every case to use a full `@SpringBootTest`: long startup times and unrelated bean failures can obscure the core configuration question. At the same time, do not use `withPropertyValues(...)` and then conclude that an external YAML file outside the JAR was found by the Config Data loader.

## 3. Configuration Contract Used in This Lesson

Suppose an application connects to a `lab.gateway` service:

~~~yaml
lab:
  gateway:
    enabled: true
    base-url: https://gateway.example.test
    timeout: 750ms
    retries: 3
    regions:
      - apac
      - eu
    limits:
      catalog: 2
      inventory: 1
~~~

Rule table:

| Key | Type | Default | Constraints |
| --- | --- | --- | --- |
| `lab.gateway.enabled` | Boolean | `false` | Enabled only by deployment choice |
| `lab.gateway.base-url` | `URI` | None | When enabled, must be an absolute HTTPS URI with a host |
| `lab.gateway.timeout` | `Duration` | `2s` | Positive and at most 10 seconds |
| `lab.gateway.retries` | `int` | `2` | From 0 to 5 |
| `lab.gateway.regions` | `List<String>` | Optional | Preserves order; entire List replaced when declared by a higher source |
| `lab.gateway.limits` | `Map<String,Integer>` | Optional | Distinct keys can combine; duplicate keys take the higher source |

This contract distinguishes **missing property**, **invalid type**, and **invalid business rule**. Those are three cases requiring distinct assertions.

## 4. Dependencies and Source Layout

A Maven project using Spring Boot dependency management:

~~~xml
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
~~~

`spring-boot-starter-validation` brings the Bean Validation implementation needed to process Jakarta validation annotations. `spring-boot-starter-test` includes JUnit Jupiter, AssertJ, Spring Test, and Boot testing utilities.

Suggested structure:

~~~text
src/
├── main/java/com/example/gateway/
│   └── GatewayProperties.java
└── test/
    ├── java/com/example/gateway/
    │   ├── GatewayPropertiesTest.java
    │   ├── PropertyPriorityTest.java
    │   ├── CommandLinePriorityTest.java
    │   ├── ProfileConfigDataTest.java
    │   └── DynamicValueTest.java
    └── resources/
        ├── application.yml
        └── application-it.yml
~~~

Tests requiring Testcontainers should belong to a separate integration group or run only on runners with a Docker-compatible runtime.

## 5. Creating the Type-Safe Model with Validation

~~~java
package com.example.gateway;

import java.net.URI;
import java.time.Duration;
import java.util.List;
import java.util.Map;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "lab.gateway")
public record GatewayProperties(
        @DefaultValue("false") boolean enabled,
        URI baseUrl,
        @NotNull @DefaultValue("2s") Duration timeout,
        @Min(0) @Max(5) @DefaultValue("2") int retries,
        List<String> regions,
        Map<String, Integer> limits) {

    @AssertTrue(message = "base-url must be an absolute HTTPS URI when enabled")
    public boolean isBaseUrlValidWhenEnabled() {
        if (!enabled) {
            return true;
        }

        return baseUrl != null
                && baseUrl.isAbsolute()
                && "https".equalsIgnoreCase(baseUrl.getScheme())
                && baseUrl.getHost() != null;
    }

    @AssertTrue(message = "timeout must be positive and at most 10s")
    public boolean isTimeoutWithinRange() {
        return timeout != null
                && !timeout.isZero()
                && !timeout.isNegative()
                && timeout.compareTo(Duration.ofSeconds(10)) <= 0;
    }
}
~~~

Explanation:

- `@ConfigurationProperties` binds keys under the `lab.gateway` prefix.
- `@DefaultValue` provides fallback values when a key is missing.
- `@Min/@Max` blocks out-of-range retry counts.
- `@AssertTrue` on JavaBeans-style boolean getters validates business relationships.
- `@Validated` pairs with Jakarta Bean Validation to catch invalid config during the bean binding lifecycle.
- `List<String>` and `Map<String,Integer>` preserve element and map-value types.

`baseUrl` may be absent when `enabled=false`. Placing `@NotNull` unconditionally there would violate the contract. A URI with scheme `http` is still a parseable URI, so the business rule must check HTTPS explicitly.

## 6. Baseline Tests with `ApplicationContextRunner`

Create a test configuration without needing a full application:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsDefaults() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.enabled()).isFalse();
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(2));
            assertThat(p.retries()).isEqualTo(2);
        });
    }
}
~~~

`ApplicationContextRunner` creates a lightweight context to test bean registration, binding, and validation. It enables testing context startup failures without starting an HTTP server or database.

### 6.1. Bean Defaults Are Not Property Sources

A dedicated test:

~~~java
@Test
void defaultInRecordDoesNotCreateEnvironmentProperty() {
    runner.run(context -> {
        GatewayProperties p =
                context.getBean(GatewayProperties.class);

        assertThat(p.timeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));

        assertThat(context.getEnvironment()
                .getProperty("lab.gateway.timeout")).isNull();
    });
}
~~~

`@DefaultValue("2s")` applies during binding into the record; it does not automatically insert `lab.gateway.timeout=2s` into `Environment`. This matters if another component reads `Environment` directly or uses `@ConditionalOnProperty`.

Never rely solely on `Environment.getProperty` as proof that a `@ConfigurationProperties` object bound properly.

## 7. Testing Override Rules with `MapPropertySource`

`StandardEnvironment` lets you construct sources with clear priorities without touching real OS environment variables.

~~~java
package com.example.gateway;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyPriorityTest {

    @Test
    void lastAddFirstHasHighestPriority() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
                new MapPropertySource("packaged",
                    Map.of("lab.gateway.retries", "1")));

        env.getPropertySources().addFirst(
                new MapPropertySource("deployment",
                    Map.of("lab.gateway.retries", "3")));

        env.getPropertySources().addFirst(
                new MapPropertySource("commandLine",
                    Map.of("lab.gateway.retries", "4")));

        assertThat(env.getProperty(
                "lab.gateway.retries", Integer.class)).isEqualTo(4);
    }

    @Test
    void lowerPrioritySourceStillSuppliesMissingKey() {
        StandardEnvironment env = new StandardEnvironment();

        env.getPropertySources().addFirst(
                new MapPropertySource("defaults", Map.of(
                    "lab.gateway.retries", "1",
                    "lab.gateway.timeout", "2s")));

        env.getPropertySources().addFirst(
                new MapPropertySource("override", Map.of(
                    "lab.gateway.retries", "5")));

        assertThat(env.getProperty(
                "lab.gateway.retries", Integer.class)).isEqualTo(5);

        assertThat(env.getProperty(
                "lab.gateway.timeout")).isEqualTo("2s");
    }
}
~~~

`addFirst` places a source at the front of the priority list. For an overlapping key, the source appearing earlier wins; for non-overlapping keys, Spring continues searching lower-priority sources.

### 7.1. Testing `addLast` as a Fallback

~~~java
@Test
void fallbackSourceDoesNotOverrideDeployment() {
    StandardEnvironment env = new StandardEnvironment();

    env.getPropertySources().addFirst(
        new MapPropertySource("deployment",
            Map.of("lab.gateway.retries", "4")));

    env.getPropertySources().addLast(
        new MapPropertySource("fallback",
            Map.of("lab.gateway.retries", "1")));

    assertThat(env.getProperty(
        "lab.gateway.retries", Integer.class)).isEqualTo(4);
}
~~~

This tests **Environment rules using simulated sources**. It does not yet test how `SpringApplication` actually orders OS env, CLI, and Config Data. The next level addresses that.

## 8. Testing Command-Line Arguments with a Real `SpringApplication`

There is no need to call `System.setProperty(...)` to test precedence. You can run a minimal `SpringApplication`:

~~~java
package com.example.gateway;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.boot.context.properties.EnableConfigurationProperties;

import static org.assertj.core.api.Assertions.assertThat;

class CommandLinePriorityTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApplication {
    }

    @Test
    void commandLineOverridesDefaultProperties() {
        SpringApplication app =
                new SpringApplication(TestApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setDefaultProperties(Map.of(
            "lab.gateway.retries", "1",
            "lab.gateway.timeout", "3s"));

        try (ConfigurableApplicationContext ctx =
                app.run("--lab.gateway.retries=4")) {

            GatewayProperties p =
                    ctx.getBean(GatewayProperties.class);

            assertThat(p.retries()).isEqualTo(4);
            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofSeconds(3));
        }
    }
}
~~~

This test is close to real startup: Spring Boot builds the `Environment` and registers the command-line property source. Under default settings, CLI arguments take higher precedence than `SpringApplication.setDefaultProperties(...)`.

If a project disables CLI properties with `setAddCommandLineProperties(false)`, tests must follow that different contract. Do not overlook project-specific `SpringApplication` configuration.

### 8.1. Why Avoid `System.setProperty`?

`System.setProperty` mutates JVM-wide state, causing test leaks when cleanup is missed or when suites run in parallel. It is especially unsafe when two test classes use the same key while expecting different values.

When you only need a source inside a test context, use `withPropertyValues` or a scoped test source. When you need to prove real CLI behavior, pass args to `SpringApplication.run`.

## 9. Testing Single-Value Binding

Continuing `GatewayPropertiesTest` and `runner` from section 6.

### 9.1. Duration

~~~java
@Test
void convertsDurationToTypedProperty() {
    runner.withPropertyValues(
            "lab.gateway.timeout=750ms")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.timeout())
                    .isEqualTo(java.time.Duration.ofMillis(750));
        });
}
~~~

Spring Boot supports duration syntax such as `500ms`, `2s`, and `1m`. A `Duration` with no suffix normally interprets bare numbers as **milliseconds** unless `@DurationUnit` specifies otherwise. Tests should therefore use explicit suffixes to prevent unit mistakes.

### 9.2. URI

~~~java
@Test
void bindsHttpsUri() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=https://gateway.example.test")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                    context.getBean(GatewayProperties.class);

            assertThat(p.baseUrl().getScheme())
                    .isEqualTo("https");
            assertThat(p.baseUrl().getHost())
                    .isEqualTo("gateway.example.test");
        });
}
~~~

Parsing a URI successfully does not prove the service is reachable. Here we test type conversion and the HTTPS rule, not connectivity to an external endpoint.

### 9.3. Integer and Defaults

~~~java
@Test
void overridesDefaultRetryValue() {
    runner.withPropertyValues(
            "lab.gateway.retries=5")
        .run(context -> {
            assertThat(context).hasNotFailed();

            assertThat(context.getBean(GatewayProperties.class)
                    .retries()).isEqualTo(5);
        });
}
~~~

`5` sits on the valid upper boundary. Testing boundaries is more meaningful than picking only an interior value.

## 10. Testing Generically Typed Lists and Maps

~~~java
@Test
void bindsIndexedListAndKeyedMap() {
    runner.withPropertyValues(
            "lab.gateway.regions[0]=apac",
            "lab.gateway.regions[1]=eu",
            "lab.gateway.limits.catalog=2",
            "lab.gateway.limits.inventory=4")
        .run(context -> {
            assertThat(context).hasNotFailed();

            GatewayProperties p =
                context.getBean(GatewayProperties.class);

            assertThat(p.regions())
                    .containsExactly("apac", "eu");

            assertThat(p.limits())
                    .containsEntry("catalog", 2)
                    .containsEntry("inventory", 4);
        });
}
~~~

`List<String>` preserves the order `apac` then `eu`. `Map<String,Integer>` holds `Integer` values rather than mere configuration Strings.

Avoid using raw `List.class` or `Map.class` and casting afterward, since doing so discards the target's generic type information.

### 10.1. When a Map Value Cannot Convert

~~~java
@Test
void rejectsNonNumericMapValue() {
    runner.withPropertyValues(
            "lab.gateway.limits.catalog=many")
        .run(context -> assertThat(context).hasFailed());
}
~~~

This is a **type conversion** error on `Map<String,Integer>`. It is independent of `retries` range validation.

## 11. Testing Wrong Types, Invalid Values, and Missing Keys Separately

Three cases:

~~~properties
# Missing retries
~~~

~~~properties
lab.gateway.retries=many
~~~

~~~properties
lab.gateway.retries=99
~~~

Expected behavior:

- Missing: uses `@DefaultValue("2")`.
- `many`: fails during binding/conversion.
- `99`: converts to `int`, then fails `@Max(5)`.

Put them into tests:

~~~java
@Test
void missingRetriesUsesDefault() {
    runner.run(ctx -> {
        assertThat(ctx.getBean(GatewayProperties.class)
                .retries()).isEqualTo(2);
    });
}

@Test
void nonNumericRetriesFailBinding() {
    runner.withPropertyValues("lab.gateway.retries=many")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void retriesAboveMaximumFailValidation() {
    runner.withPropertyValues("lab.gateway.retries=99")
        .run(ctx -> assertThat(ctx).hasFailed());
}
~~~

If the third test fails to reject `99`, the validation provider may be missing from the test runtime classpath, `@Validated` may have been omitted, or the bean is not going through the binding path you expect.

## 12. Testing Validation with JUnit Parameterized Tests

JUnit Jupiter allows verifying multiple boundary values cleanly:

~~~java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

@ParameterizedTest
@ValueSource(strings = {"-1", "6", "100"})
void rejectsRetriesOutsideAllowedRange(String retries) {
    runner.withPropertyValues(
            "lab.gateway.retries=" + retries)
        .run(ctx -> assertThat(ctx).hasFailed());
}

@ParameterizedTest
@ValueSource(strings = {"0", "1", "5"})
void acceptsRetriesInsideAllowedRange(String retries) {
    runner.withPropertyValues(
            "lab.gateway.retries=" + retries)
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

Similarly for timeout:

~~~java
@ParameterizedTest
@ValueSource(strings = {"0s", "-1s", "11s"})
void rejectsInvalidTimeout(String timeout) {
    runner.withPropertyValues(
            "lab.gateway.timeout=" + timeout)
        .run(ctx -> assertThat(ctx).hasFailed());
}

@ParameterizedTest
@ValueSource(strings = {"1ms", "2s", "10s"})
void acceptsValidTimeout(String timeout) {
    runner.withPropertyValues(
            "lab.gateway.timeout=" + timeout)
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

Boundary values `0`, `5`, and `10s` should be tested explicitly because `<` vs. `<=` off-by-one bugs easily escape middle-range examples.

## 13. Testing Cross-Field Validation

Contract:

~~~text
enabled=false:
  base-url may be missing

enabled=true:
  base-url must be an absolute HTTPS URI with a host
~~~

Tests:

~~~java
@Test
void disabledGatewayDoesNotRequireUrl() {
    runner.withPropertyValues("lab.gateway.enabled=false")
        .run(ctx -> assertThat(ctx).hasNotFailed());
}

@Test
void enabledGatewayRequiresUrl() {
    runner.withPropertyValues("lab.gateway.enabled=true")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void enabledGatewayRejectsHttp() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=http://gateway.example.test")
        .run(ctx -> assertThat(ctx).hasFailed());
}

@Test
void enabledGatewayAcceptsHttps() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.base-url=https://gateway.example.test")
        .run(ctx -> assertThat(ctx).hasNotFailed());
}
~~~

`@NotNull` on `baseUrl` would not express the conditional rule accurately. In the sample model, `@AssertTrue` enforces it. For more complex logic, a class-level Jakarta constraint or Spring `Validator` can be used.

Never make a test "fail" by dropping the validation dependency and letting another bean accidentally break startup. Isolating the configuration model ensures assertions reflect the true cause.

## 14. Testing Config Data Profile Override Rules

`ApplicationContextRunner.withPropertyValues(...)` does not automatically load all `application-{profile}.yml` files like a normal `SpringApplication`. To test real Config Data behavior, create files under `src/test/resources` and use `@SpringBootTest`.

`src/test/resources/application.yml`:

~~~yaml
lab:
  gateway:
    enabled: false
    timeout: 2s
    retries: 1
    regions:
      - apac
      - eu
    limits:
      catalog: 2
      inventory: 1
~~~

`src/test/resources/application-it.yml`:

~~~yaml
lab:
  gateway:
    retries: 3
    regions:
      - us
    limits:
      catalog: 5
      billing: 3
~~~

Test:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ProfileConfigDataTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@ActiveProfiles("it")
class ProfileConfigDataTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApp {
    }

    @Autowired
    GatewayProperties properties;

    @Test
    void profileOverridesScalarsAndCollections() {
        assertThat(properties.retries()).isEqualTo(3);
        assertThat(properties.timeout())
                .isEqualTo(java.time.Duration.ofSeconds(2));

        assertThat(properties.regions())
                .containsExactly("us");

        assertThat(properties.limits())
                .containsEntry("catalog", 5)
                .containsEntry("inventory", 1)
                .containsEntry("billing", 3);
    }
}
~~~

This is an important test because:

- `retries` in the profile file overrides the value from the base file.
- `timeout` does not appear in the profile, so it still comes from the base file.
- `regions` is a **List**, so it is replaced wholesale, resulting in `[us]`.
- `limits` is a **Map**, so keys merge: overlapping `catalog` is overridden to `5`, `inventory` is kept, and `billing` is added.

A single "merge everything" rule **does not apply** equally to both Lists and Maps.

### 14.1. Splitting Tests for Easier Root-Cause Identification

~~~java
@Test
void profileListReplacesAllPreviousElements() {
    assertThat(properties.regions()).containsExactly("us");
}

@Test
void mapRetainsNonOverriddenKeys() {
    assertThat(properties.limits())
            .containsEntry("inventory", 1)
            .containsEntry("catalog", 5)
            .containsEntry("billing", 3);
}
~~~

If a test fails because `regions` has unexpected contents, that does not imply a bug in `@Validated`. Check the right layer: verify the Config Data sources first, then inspect binding.

## 15. Testing `@TestPropertySource` and Dynamic Properties

Static values known at test-authoring time:

~~~java
@TestPropertySource(properties = {
    "lab.gateway.retries=1",
    "lab.gateway.timeout=3s"
})
~~~

However, Testcontainers or an HTTP mock server may pick a random mapped port only when runtime starts. `@DynamicPropertySource` solves this and has higher precedence than `@TestPropertySource`.

Test:

~~~java
package com.example.gateway;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(classes = DynamicValueTest.TestApp.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestPropertySource(properties = "lab.gateway.retries=1")
class DynamicValueTest {

    @SpringBootConfiguration
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestApp {
    }

    @DynamicPropertySource
    static void dynamic(DynamicPropertyRegistry registry) {
        registry.add("lab.gateway.retries", () -> 4);
    }

    @Autowired
    GatewayProperties properties;

    @Test
    void dynamicPropertyWins() {
        assertThat(properties.retries()).isEqualTo(4);
    }
}
~~~

A `@DynamicPropertySource` method must be `static`, accept a `DynamicPropertyRegistry`, and use `registry.add(key, Supplier)`. The `Supplier` can be a lambda or a method reference. Never pass a raw value directly instead of a `Supplier`.

### 15.1. Limitations of Dynamic Suppliers

A dynamic source may be resolved multiple times, not only at registration time. However, a singleton that already injected `@Value` or bound `@ConfigurationProperties` **does not automatically rebind** just because the `Supplier` changes its value after startup.

When test classes use different containers, Spring TestContext caching can keep a bean pointing at an older stopped container. Decide the fixture lifecycle and consider `@DirtiesContext` if the context cannot be safely reused.

## 16. Testcontainers: Verifying Client Wiring as Well

A test that only asserts a JDBC URL string is present **does not prove** the datasource actually works.

Illustrative example:

~~~java
@Testcontainers
@SpringBootTest
class PostgreSqlIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine")
            .withDatabaseName("integration_db")
            .withUsername("integration_user")
            .withPassword("integration_password");

    @DynamicPropertySource
    static void dataSourceProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    @Autowired
    DataSource dataSource;

    @Test
    void connectsToTheContainer() {
        Integer result = new JdbcTemplate(dataSource)
                .queryForObject("select 1", Integer.class);

        assertThat(result).isEqualTo(1);
    }
}
~~~

This example requires the Testcontainers PostgreSQL/JUnit Jupiter dependencies, Spring JDBC/JDBC starter, and PostgreSQL driver; the CI environment must also have an active container runtime. `@Container` manages a container through the extension lifecycle, and `@DynamicPropertySource` retrieves the **actual** URL, username, and password.

With Spring Boot 3.1+ and `spring-boot-testcontainers`, `@ServiceConnection` can replace some manual property registration via `ConnectionDetails`. Pick one integration style suited to your Boot version instead of layering conflicting mechanisms.

## 17. Testing Key Naming Under Relaxed Binding

The Java component `baseUrl` is commonly bound from the canonical key:

~~~properties
lab.gateway.base-url=https://gateway.example.test
~~~

Some naming variants such as camelCase are also accepted by the Binder:

~~~java
@Test
void camelCaseNameCanBindToCanonicalProperty() {
    runner.withPropertyValues(
            "lab.gateway.enabled=true",
            "lab.gateway.baseUrl=https://gateway.example.test")
        .run(ctx -> {
            assertThat(ctx).hasNotFailed();

            GatewayProperties p =
                    ctx.getBean(GatewayProperties.class);

            assertThat(p.baseUrl().getHost())
                    .isEqualTo("gateway.example.test");
        });
}
~~~

Still, in operational documentation, always stick to **one canonical kebab-case name**.

For OS environment variables:

~~~text
lab.gateway.base-url  → LAB_GATEWAY_BASEURL
lab.gateway.timeout   → LAB_GATEWAY_TIMEOUT
lab.gateway.retries   → LAB_GATEWAY_RETRIES
~~~

Do not use an ordinary `MapPropertySource` to mimic all semantics of `SystemEnvironmentPropertySource` and then claim OS env conversion rules are proven. To test real environment variables, launch a process or container with explicit env vars, or use the exact property-source type at the `Environment` layer.

## 18. Testing a Custom `Validator` for Complex Rules

For a multi-field rule, you can use a Spring `Validator`:

~~~java
package com.example.gateway;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class GatewayPropertiesValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return GatewayProperties.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object value, Errors errors) {
        GatewayProperties p = (GatewayProperties) value;

        if (p.enabled() && p.baseUrl() == null) {
            errors.rejectValue("baseUrl",
                "gateway.baseUrl.required",
                "base-url is required when enabled");
        }
    }
}
~~~

Register it under the special bean name if you want Spring Boot to invoke it when binding configuration properties:

~~~java
@Configuration(proxyBeanMethods = false)
public class GatewayValidationConfig {

    @Bean(name = "configurationPropertiesValidator")
    public static Validator configurationPropertiesValidator() {
        return new GatewayPropertiesValidator();
    }
}
~~~

The `@Bean` method should be `static` because the validator may be initialized very early.

Pure validator unit test:

~~~java
@Test
void customValidatorRejectsMissingEndpoint() {
    GatewayProperties p = new GatewayProperties(
        true, null, Duration.ofSeconds(2), 2,
        List.of(), Map.of());

    BeanPropertyBindingResult errors =
        new BeanPropertyBindingResult(p, "gateway");

    new GatewayPropertiesValidator().validate(p, errors);

    assertThat(errors.hasFieldErrors("baseUrl")).isTrue();
}
~~~

This test verifies validator logic, yet does not prove Boot actually registered the special bean. To test wiring, pass `GatewayValidationConfig.class` to `ApplicationContextRunner.withUserConfiguration(...)` and assert that startup fails on the matching configuration.

Avoid maintaining duplicate rules across `@AssertTrue` and a custom `Validator` in a real codebase unless intentional. Pick a consistent approach so errors are not duplicated.

## 19. Inspecting the Failure Source When the Context Fails

A broad assertion:

~~~java
assertThat(context).hasFailed();
~~~

is useful, yet a context can fail for many different reasons. To prevent false confidence, inspect the startup failure:

~~~java
@Test
void invalidRetriesPreventStartup() {
    runner.withPropertyValues("lab.gateway.retries=99")
        .run(context -> {
            assertThat(context).hasFailed();
            assertThat(context.getStartupFailure()).isNotNull();
        });
}
~~~

When confirming a specific failure, check the exception class/cause or an application-controlled error code. Do not assert entire stack traces or exact punctuation of Spring Boot messages, because framework exception details vary across versions.

### 19.1. Conversion Failure vs. Validation Failure

~~~properties
lab.gateway.retries=wrong
~~~

is a conversion failure.

~~~properties
lab.gateway.retries=99
~~~

is a validation failure when `@Max(5)` is active.

Even when both tests fail, recognize that they fail at two different layers. A semantic validation test should never pass falsely because Spring could not find an unrelated bean.

## 20. Contract on Unknown Fields

Spring Boot `@ConfigurationProperties` supports:

~~~java
@ConfigurationProperties(
    prefix = "lab.gateway",
    ignoreUnknownFields = false)
~~~

When a key is misspelled:

~~~properties
lab.gateway.timout=5s
~~~

`timout` is not `timeout`. If the binder ignores this key, the record can still receive the `2s` default, leading an operator to believe the `5s` override took effect.

For a strict contract, consider `ignoreUnknownFields=false` and add a test with a misspelled key. Keep in mind that unknown-key detection also depends on property-source capabilities and structure; do not assume every typo variant across every source is reported identically.

If multiple modules share a prefix, strict binding can also expose namespace-design issues. Preferably, give each configuration group a clearly owned prefix.

## 21. Config Data Locations and Working Directory in Integration Tests

Example:

~~~bash
java -jar app.jar \
  --spring.config.additional-location=file:/etc/gateway/
~~~

`spring.config.additional-location` adds locations alongside defaults; `spring.config.location` replaces the default search locations. This parameter must be available early enough to steer Config Data loading.

A test with `withPropertyValues("spring.config.additional-location=...")` in `ApplicationContextRunner` does not prove that the Config Data processor loaded that file the way `SpringApplication` does at startup.

If the requirement is to verify location loading:

1. Create test files in a temporary directory or dedicated fixture.
2. Start `SpringApplication` with an explicit location argument.
3. Assert that values were loaded and the bean bound properly.
4. Close the context and clean up fixtures per lifecycle rules.
5. Add smoke tests against the actual Docker/systemd/Kubernetes filesystem if needed.

A path like `file:./config/` depends on the **working directory**, which is not automatically the directory containing the JAR. If production launches from a different directory than the IDE, tests should reflect that difference.

## 22. A Suggested Test Matrix

| ID | Category | Input | Expected |
| --- | --- | --- | --- |
| P01 | Priority | source A=1, source B=4 (B higher) | 4 |
| P02 | Priority | fallback=1, deployment=3 | 3 |
| P03 | Priority | `setDefaultProperties=1`, CLI=4 | 4 |
| P04 | Profile | base retries=1, it retries=3 | 3 |
| P05 | Dynamic | TestPropertySource=1, dynamic=4 | 4 |
| B01 | Binding | timeout omitted | 2s from record default |
| B02 | Binding | `timeout=750ms` | `Duration.ofMillis(750)` |
| B03 | Binding | `retries=5` | int 5 |
| B04 | Binding | HTTPS URI | Valid scheme and host |
| B05 | Binding | regions[0], regions[1] | Ordered List |
| B06 | Binding | limits.catalog=2 | Map value Integer 2 |
| B07 | Binding | Profile replaces regions | List contains profile items only |
| B08 | Binding | Profile updates limits.catalog | Overlapping Map key overridden |
| B09 | Conversion | `retries=many` | Context fails |
| B10 | Conversion | `limits.catalog=many` | Context fails |
| V01 | Validation | enabled=false, URL missing | Context starts |
| V02 | Validation | enabled=true, URL missing | Context fails |
| V03 | Validation | enabled=true, HTTP URL | Context fails |
| V04 | Validation | enabled=true, HTTPS URL | Context starts |
| V05 | Validation | retries=-1 or 6 | Context fails |
| V06 | Validation | retries=0 or 5 | Context starts |
| V07 | Validation | timeout=0s, -1s, 11s | Context fails |
| V08 | Validation | timeout=1ms, 10s | Context starts |
| I01 | Integration | Container random port | Query/HTTP call hits right endpoint |
| I02 | Deployment | External config directory | Expected values and startup behavior |

A solid test suite includes both **positive** and **negative** cases. Never test just one valid config file and assume all override and validation rules are enforced.

## 23. Practice Exercise: Precedence

Given these sources:

~~~text
Source A:
  lab.gateway.retries=1
  lab.gateway.timeout=2s

Source B (higher than A):
  lab.gateway.retries=3

Source C (higher than B):
  lab.gateway.base-url=https://gateway.example.test
~~~

What is the result for each key?

**Answer:**

- `retries=3` from B.
- `timeout=2s` from A because no higher source overrides it.
- `base-url` from C.
- Each property resolves per key, rather than picking one entire source and discarding all keys from other sources.

Write a `StandardEnvironment` test calling `addFirst` in the order A, B, C and assert all three keys.

## 24. Exercise: List Replacement vs. Map Merging

Base config:

~~~yaml
lab:
  gateway:
    regions: [apac, eu]
    limits:
      catalog: 2
      inventory: 1
~~~

Profile config:

~~~yaml
lab:
  gateway:
    regions: [us]
    limits:
      catalog: 5
      billing: 3
~~~

**Expected:** `regions=[us]`; `limits.catalog=5`, `limits.inventory=1`, `limits.billing=3`.

Do not expect `regions=[apac,eu,us]`, because Spring Boot list overrides normally replace rather than concatenate. Write a `@SpringBootTest` with the two YAML files to prove the rule inside the real Config Data lifecycle.

## 25. Exercise: Distinguishing Conversion Failures from Validation Failures

Suppose:

~~~properties
lab.gateway.retries=abc
~~~

and:

~~~properties
lab.gateway.retries=8
~~~

**Answer:**

- `abc` cannot convert to `int`, so it fails during type conversion.
- `8` converts successfully, yet violates `@Max(5)` and fails validation.

A test suite should include cases for both. If the key is missing, per contract it uses default `2` and does not fail.

## 26. Exercise: Conditional Required Fields

Given:

~~~text
enabled=false, base-url missing
enabled=true, base-url missing
enabled=true, base-url=http://gateway.example.test
enabled=true, base-url=https://gateway.example.test
~~~

**Outcomes in order:** valid, fail, fail, valid.

The `@AssertTrue` rule on the record expresses this behavior. For more complex logic, a Spring `Validator` or Jakarta class-level constraint is appropriate.

Do not annotate `baseUrl` with `@NotNull` unconditionally if the feature must be allowed to stay disabled without a URL.

## 27. Exercise: Dynamic Values Overriding Test Properties

~~~java
@TestPropertySource(properties = "lab.gateway.retries=1")
class ExampleTest {

    @DynamicPropertySource
    static void values(DynamicPropertyRegistry registry) {
        registry.add("lab.gateway.retries", () -> 4);
    }
}
~~~

When the test class runs inside Spring TestContext, dynamic properties outrank `@TestPropertySource`: the resolved value is **4**.

If a bound bean needs to receive `4`, ensure the bean is created in the context backed by that dynamic source. Annotations alone on a plain JUnit test without starting a Spring context will not trigger binding automatically.

## 28. Test Hygiene and CI

Principles:

1. Never mutate global JVM properties in tests when a context-scoped option exists.
2. Avoid relying on fixed ports for external resources.
3. Use non-sensitive test data; never log passwords or tokens.
4. Keep Testcontainers resources alive across the lifetime of a cached context.
5. Separate Docker-dependent tests from fast unit tests when CI does not always have a container runtime.
6. Use `@DirtiesContext` only when reloading the context is truly necessary, because it is expensive.
7. Never assert verbatim framework stack traces.
8. Pick distinct values across sources so tests do not pass by accidentally matching defaults.
9. In integration tests, verify real beans/clients rather than only String properties.
10. Cover profiles, Config Data imports, and startup arguments intentionally.
11. Isolate shared `src/test/resources/application*.yml` files across test suites.
12. Clean up temporary files, connections, and container resources after tests.
13. Test min, max, and out-of-bounds values.
14. When upgrading Spring Boot versions, review assumptions about source ordering and conversion.
15. Whenever renaming a key or changing its type or default, update tests as an API contract.

Maven command:

~~~bash
mvn test
~~~

Run only the contract test:

~~~bash
mvn -Dtest=GatewayPropertiesTest test
~~~

With Gradle:

~~~bash
./gradlew test
~~~

If a project uses Maven Failsafe for integration tests, `mvn verify` can execute those configuration tests according to plugin setup. Do not assume every project has Failsafe active unless configured.

## 29. When a Test Fails: Diagnostic Sequence

1. **Does the context have the bean under test?** Check `@EnableConfigurationProperties` or scanning.
2. **Which source supplied the value?** Check active profiles, CLI, env, and test properties.
3. **Is the canonical key right?** Distinguish `base-url`, `baseUrl`, and OS env naming.
4. **Is the value convertible?** `abc` is not a retry int; `wrong` is not a `Duration`.
5. **Is business validation running?** Are `@Validated` and a validation provider present?
6. **Are there conditional rules?** Does `enabled=true` require a URL?
7. **Is there a profile-specific file?** Did the test declare `@ActiveProfiles`?
8. **Are List/Map merge semantics understood?** Lists replace; Maps may merge keys.
9. **Did a dynamic source override the test property?** `@DynamicPropertySource` has high precedence.
10. **Did context caching retain an older bean?** Check fixture lifecycle and `@DirtiesContext`.
11. **Is the test mocking properties or loading real Config Data?** Runner and `SpringApplication` differ in scope.
12. **Did startup fail for the right rule?** Never let an unrelated dependency failure produce a false pass.

Do not change annotations or configuration sources wholesale before identifying **which layer** produced the wrong outcome.

## 30. Summary

A well-structured configuration test plan flows from raw sources to bean behavior:

~~~text
application.yml / profile / env / CLI / dynamic test source
                     |
                     v
          [PropertySource precedence]
                     |
                     v
          [Binder + type conversion]
                     |
                     v
          [@ConfigurationProperties]
                     |
                     v
          [Jakarta / custom validation]
                     |
                     v
             [Spring beans]
                     |
                     v
         [Integration with real resources]
~~~

Key points to remember:

- `StandardEnvironment` suits testing priority among explicit mock sources.
- `ApplicationContextRunner` suits binding/defaults/validation without booting a full app.
- `SpringApplication` and `@SpringBootTest` better verify Config Data and startup semantics.
- `Duration` values should carry explicit suffixes such as `750ms` or `2s`.
- Lists normally **replace wholesale** when declared by a higher source; Maps can merge keys.
- Both `@Validated` and an active provider must be present to enforce Jakarta constraints.
- Conversion errors differ from semantic validation errors.
- `@DynamicPropertySource` outranks `@TestPropertySource`, yet does not automatically rebind singletons if the `Supplier` changes after startup.
- Test positive, negative, boundary, missing, precedence, and failure causes independently.
- When external dependencies exist, a real query or HTTP request verifies complete client wiring.

### References

- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
- Spring Boot — Configuration Properties Validation: https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation
- Spring Boot — Testing: https://docs.spring.io/spring-boot/reference/testing/index.html
- Spring Boot — Testing Auto-configuration: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing
- Spring Framework — Dynamic Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Framework — Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Spring Framework — TestContext Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Testcontainers Java — JUnit Jupiter: https://java.testcontainers.org/test_framework_integration/junit_5/
