# Choosing a Configuration Testing Level: Plain Object, Binder, ApplicationContextRunner, and Full Application

## 1. Lesson Objectives

When using Spring Boot Externalized Configuration, an application can receive properties from **application.yml**, **application.properties**, profile-specific files, environment variables, JVM system properties, CLI arguments, Config Data imports, and other PropertySources. These properties are looked up, type-converted, bound to **@ConfigurationProperties**, validated, and ultimately affect how beans are created.

A configuration test can target many different questions:

- Does a configuration record reject negative values, blank names, or invalid structures?
- Does the Spring Boot Binder correctly convert **5s** to **Duration** and map **read-timeout** to **readTimeout**?
- When configuration is invalid, does a **@Validated @ConfigurationProperties** bean cause the ApplicationContext to fail?
- Does **@ConditionalOnProperty** create or omit a bean according to the feature flag?
- When enabling the prod profile, importing an external file, or passing CLI arguments, does the full application receive the expected values?
- Is an **EnvironmentPostProcessor** registered via spring.factories actually invoked during bootstrap?
- Does a datasource or HTTP client actually receive the configuration after auto-configuration and start properly?

These questions **should not all be tested with a single technique**. If you only check an invariant on a record, starting the entire application is far too heavy. If you want to prove that an EnvironmentPostProcessor is discovered by SpringApplication on the classpath, a unit test calling that class directly is not enough.

This lesson builds a testing strategy across four levels:

1. **Plain Java object tests**: the fastest level, checking constructors, defaults/invariants, and Bean Validation invoked explicitly.
2. **Spring Boot Binder tests**: checking conversion of property names, structure, and data types into objects, without starting an ApplicationContext.
3. **ApplicationContextRunner**: checking the lifecycle of configuration-properties bean registration, integrated validation, conditional auto-configuration, and the effect of properties on a minimal context.
4. **Full application tests**: starting via SpringApplication/@SpringBootTest to verify configuration, profiles, Config Data, bootstrap extensions, and runtime integration in a near-production setup.

The goal is not to pick the "strongest" level for every case. The goal is to **use the lowest level that still proves the required behavior**, and then add a few high-value integration tests at the boundaries where they are genuinely needed.

The examples focus on Spring Boot 3.x, Java 17+, JUnit Jupiter, and AssertJ. For Spring Boot 4.x, check the corresponding test module packages/APIs and extension points in your project version before copying snippets verbatim.

---

## 2. Comparing the Four Testing Levels

| Level | What is initialized? | Tests Binder? | Tests Spring bean lifecycle? | Tests real app bootstrap? | When to use |
| --- | --- | --- | --- | --- | --- |
| Object | Java object and validator if needed | No | No | No | Invariants, defaults, defensive copies, standalone validation logic |
| Binder | Binder + test ConfigurationPropertySource | Yes | No | No | Relaxed binding, nested objects, Duration, List/Map, type conversion errors |
| ApplicationContextRunner | Small ApplicationContext from test config | Yes, when beans are registered properly | Yes | Not fully | @ConfigurationProperties, @Validated, @ConditionalOnProperty, scoped auto-configuration |
| Full application | Application's SpringApplication/ApplicationContext | Yes | Yes | Yes | Profiles, Config Data imports, EPP discovery, full-system wiring, infrastructure integration |

**Level-selection rule:** A test only proves a given behavior when the relevant mechanism is **actually exercised** in that test.

For example, calling **new GatewayProperties(...)** directly does not prove YAML is loaded or that beans are validated automatically. Calling **binder.bind(...)** does not prove Spring knows to register the configuration bean. Creating an ApplicationContextRunner with manual properties does not prove the application's application-prod.yml file is loaded in the right order. Conversely, @SpringBootTest is unnecessary for checking **Duration.isPositive()** or whether a constructor throws IllegalArgumentException.

### 2.1. Proof Scope vs. Execution Time

A heavier test covers more components, but when it fails it is often harder to pinpoint the root cause:

~~~text
Object test
  -> Is the Java object itself correct?

Binder test
  -> Are source properties converted into the object correctly?

ApplicationContextRunner
  -> Are beans/auto-configurations registered, bound, and validated correctly?

Full Spring Boot application
  -> Do full bootstrap, Config Data, and wiring work properly?
~~~

Do not treat the four levels as duplicate tests you must write for every field. Pick **one level as the primary place for detailed checks**, and let higher levels verify only the critical integration seams.

---

## 3. A Configuration Model Used Throughout

Suppose an application has a gateway with a timeout, connection pool, and list of endpoints:

~~~yaml
app:
  gateway:
    timeout: 5s
    pool:
      max-connections: 24
      enabled: true
    endpoints:
      - host: primary.example.test
        port: 8080
      - host: backup.example.test
        port: 8081
~~~

Java model:

~~~java
package example.config;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.gateway")
public record GatewayProperties(
        @NotNull Duration timeout,
        @Valid @NotNull Pool pool,
        @NotEmpty List<@NotNull @Valid Endpoint> endpoints
) {
    public record Pool(
            @Min(1) int maxConnections,
            boolean enabled
    ) {}

    public record Endpoint(
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

Key properties:

| Canonical property | Java component | Type |
| --- | --- | --- |
| app.gateway.timeout | GatewayProperties.timeout | Duration |
| app.gateway.pool.max-connections | Pool.maxConnections | int |
| app.gateway.pool.enabled | Pool.enabled | boolean |
| app.gateway.endpoints[0].host | Endpoint.host | String |
| app.gateway.endpoints[0].port | Endpoint.port | int |

**@Validated** enables Spring Boot validation integration when configuration is bound as a bean. **@Valid** on pool and Endpoint elements enables cascading validation into child objects. **@NotNull** ensures pool is present; @Valid alone does not forbid a null reference.

### 3.1. Registering GatewayProperties at Application Runtime

Example:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

GatewayProperties must reside in a scanned package, or be registered via **@EnableConfigurationProperties(GatewayProperties.class)**.

### 3.2. Common Dependencies

With Maven:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

The test starter typically provides JUnit Jupiter, AssertJ, and Spring Boot testing support. The validation starter provides Jakarta Bean Validation integration and an appropriate provider.

**Without a validation provider**, merely placing constraint annotations in source code does not guarantee validation checks will automatically run at runtime.

---

## 4. Level 1: Plain Java Object Testing

At this level, tests instantiate classes/records with **new**. Spring is not started and application.yml is not read.

Best suited for testing:

- Constructor invariants, such as maxConnections being positive.
- Default-calculation or value-normalization functions.
- Defensive copies of Lists/Maps.
- Cross-field correlation logic.
- Convenience methods built on top of configuration.
- Bean Validation **invoked directly** using a Jakarta Validator.

### 4.1. Constructor Invariant Example

A small record:

~~~java
import java.time.Duration;

public record RetrySettings(
        int maxAttempts,
        Duration backoff
) {
    public RetrySettings {
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be >= 1"
            );
        }
        if (backoff == null ||
                backoff.isZero() ||
                backoff.isNegative()) {
            throw new IllegalArgumentException(
                    "backoff must be positive"
            );
        }
    }
}
~~~

Unit test:

~~~java
import java.time.Duration;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class RetrySettingsTest {

    @Test
    void acceptsValidValues() {
        RetrySettings settings =
                new RetrySettings(3, Duration.ofMillis(250));

        assertThat(settings.maxAttempts()).isEqualTo(3);
        assertThat(settings.backoff())
                .isEqualTo(Duration.ofMillis(250));
    }

    @Test
    void rejectsInvalidAttemptCount() {
        assertThatThrownBy(() ->
                new RetrySettings(0, Duration.ofSeconds(1)))
                .isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void rejectsNegativeBackoff() {
        assertThatThrownBy(() ->
                new RetrySettings(2, Duration.ofSeconds(-1)))
                .isInstanceOf(IllegalArgumentException.class);
    }
}
~~~

These tests are fast, produce clear failures, and do not depend on bean registration, profiles, files, or the network.

**Limitation:** They do not prove Spring Boot can convert **250ms** to Duration, or that the path **app.retry.backoff** is resolved properly.

### 4.2. Testing Immutable Snapshots

If a configuration object holds a List:

~~~java
import java.util.List;

public record ClientSettings(List<String> hosts) {

    public ClientSettings {
        hosts = hosts == null
                ? List.of()
                : List.copyOf(hosts);
    }
}
~~~

Test:

~~~java
import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class ClientSettingsTest {

    @Test
    void protectsAgainstExternalMutation() {
        List<String> original = new ArrayList<>();
        original.add("alpha.example.test");

        ClientSettings settings = new ClientSettings(original);

        original.add("beta.example.test");

        assertThat(settings.hosts())
                .containsExactly("alpha.example.test");

        assertThatThrownBy(() ->
                settings.hosts().add("gamma.example.test"))
                .isInstanceOf(UnsupportedOperationException.class);
    }
}
~~~

This is an exact test for **defensive copying**, though it does not test the Binder converting a YAML list into a Java List.

### 4.3. Explicit Bean Validation Testing

If you want to verify GatewayProperties constraints **without starting Spring**, you can use Jakarta Validator:

~~~java
import java.time.Duration;
import java.util.List;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayConstraintsTest {

    @Test
    void findsInvalidNestedEndpoint() {
        try (var factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            var gateway = new GatewayProperties(
                    Duration.ofSeconds(5),
                    new GatewayProperties.Pool(10, true),
                    List.of(
                        new GatewayProperties.Endpoint("", 0)
                    )
            );

            var violations = validator.validate(gateway);

            assertThat(violations).isNotEmpty();
            assertThat(violations.stream()
                    .map(v -> v.getPropertyPath().toString()))
                    .anyMatch(path -> path.contains("host"))
                    .anyMatch(path -> path.contains("port"));
        }
    }
}
~~~

Here **validator.validate(...)** is called directly without the @ConfigurationProperties binder. It proves the constraints and @Valid describe the object graph accurately, but does not yet prove Spring Boot triggers validation automatically at startup.

### 4.4. @Valid Does Not Mean @NotNull

A reference:

~~~java
@Valid Pool pool
~~~

is cascaded if pool holds an object, but does not forbid pool=null. If pool is required, use:

~~~java
@Valid @NotNull Pool pool
~~~

In unit tests with Validator, include a case constructing GatewayProperties with **pool=null**, then verify @NotNull reports a violation. Testing only Pool.maxConnections=0 without testing null can miss an absent-configuration branch.

### 4.5. When Not to Use Level 1

Do not use object tests alone to conclude:

- The name **max-connections** binds properly to **maxConnections**.
- application-prod.yml is loaded for the right profile.
- The environment variable **APP_GATEWAY_TIMEOUT** overrides application.yml.
- The configuration bean is scanned successfully.
- @ConditionalOnProperty creates beans properly.
- An EnvironmentPostProcessor is discovered via spring.factories.

All of those behaviors lie outside the scope of a plain Java object.

---

## 5. Level 2: Direct Binder Testing

**Binder** is the Spring Boot component that converts structured properties into target objects. Direct Binder testing is ideal when the primary question is **"Are source names and values bound into Java types properly?"**

This level does not need an ApplicationContext. You can build a test property source using **MapConfigurationPropertySource**.

### 5.1. Testing Binding of a Record with Nested Objects and Duration

~~~java
import java.time.Duration;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.bind.Binder;
import org.springframework.boot.context.properties.source.MapConfigurationPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayBinderTest {

    @Test
    void bindsNestedRecordAndDuration() {
        Map<String, Object> values = Map.of(
            "app.gateway.timeout", "5s",
            "app.gateway.pool.max-connections", "24",
            "app.gateway.pool.enabled", "true",
            "app.gateway.endpoints[0].host", "primary.example.test",
            "app.gateway.endpoints[0].port", "8080"
        );

        Binder binder = new Binder(
            new MapConfigurationPropertySource(values)
        );

        GatewayProperties gateway = binder
            .bind("app.gateway", GatewayProperties.class)
            .orElseThrow(() ->
                new IllegalStateException("Gateway not bound"));

        assertThat(gateway.timeout())
            .isEqualTo(Duration.ofSeconds(5));
        assertThat(gateway.pool().maxConnections())
            .isEqualTo(24);
        assertThat(gateway.pool().enabled()).isTrue();
        assertThat(gateway.endpoints())
            .hasSize(1);
        assertThat(gateway.endpoints().get(0).host())
            .isEqualTo("primary.example.test");
    }
}
~~~

The Binder level tests:

- Prefix **app.gateway**.
- Nested property **pool.max-connections**.
- List indexing **endpoints[0]**.
- Type conversion **"5s" -> Duration**.
- Type conversion from strings to int/boolean.
- Record constructor binding in a supported binder context.

It does not test whether the class is scanned, whether the bean is injected, or whether validation integration runs automatically.

### 5.2. Reading BindResult Properly

~~~java
var result = binder.bind(
        "app.gateway",
        GatewayProperties.class
);

if (!result.isBound()) {
    throw new IllegalStateException(
        "No configuration under app.gateway"
    );
}

GatewayProperties gateway = result.get();
~~~

**isBound()** answers whether a binding result exists. It is not a Bean Validation check.

### 5.3. Testing When the Prefix Is Absent

~~~java
Binder binder = new Binder(
        new MapConfigurationPropertySource(
            Map.of("unrelated.value", "example")
        )
);

var result = binder.bind(
        "app.gateway",
        GatewayProperties.class
);

assertThat(result.isBound()).isFalse();
~~~

This is distinct from "a field inside the prefix is missing." An object can still be bound even when some fields are null or take defaults; in that case **isBound()** can still be true.

### 5.4. Testing Type Conversion Errors

~~~java
Map<String, Object> values = Map.of(
        "app.gateway.timeout", "not-a-duration",
        "app.gateway.pool.max-connections", "20"
);

Binder binder = new Binder(
        new MapConfigurationPropertySource(values)
);

assertThatThrownBy(() ->
        binder.bind("app.gateway", GatewayProperties.class))
        .isInstanceOf(
            org.springframework.boot.context.properties.bind.BindException.class
        );
~~~

This case tests conversion/binding failure. It does not prove @Min(1) or @NotBlank are automatically validated.

### 5.5. Testing Relaxed Binding

For example, the Java field **maxConnections** typically corresponds to the canonical property:

~~~text
app.gateway.pool.max-connections
~~~

You can write separate test cases using names from various supported formats, such as:

~~~text
app.gateway.pool.max-connections
app.gateway.pool.maxConnections
app.gateway.pool.max_connections
~~~

The Binder level lets you observe resolution of these variants against a **test ConfigurationPropertySource**.

**Important:** A MapConfigurationPropertySource is not identical to OS environment variables. To prove canonical conversion from actual env var naming, simulate the env PropertySource accurately or run a process-level test with real env vars.

### 5.6. Lists with Bindable

When you do not want to create a wrapper record:

~~~java
import java.util.List;
import org.springframework.boot.context.properties.bind.Bindable;

List<GatewayProperties.Endpoint> endpoints = binder
        .bind(
            "app.gateway.endpoints",
            Bindable.listOf(GatewayProperties.Endpoint.class)
        )
        .orElse(List.of());
~~~

**Bindable.listOf(Endpoint.class)** preserves element type information. Using **List.class** directly can lose the type information the binder needs to instantiate each Endpoint.

### 5.7. Maps with Bindable

~~~java
import java.util.Map;
import org.springframework.boot.context.properties.bind.Bindable;

Map<String, String> labels = binder
    .bind(
        "app.gateway.labels",
        Bindable.mapOf(String.class, String.class)
    )
    .orElse(Map.of());
~~~

With MapConfigurationPropertySource, you can supply:

~~~text
app.gateway.labels.owner=platform
app.gateway.labels.region=asia
~~~

to verify Map keys and values bind properly. For Map keys containing dots or special characters, add dedicated cases for bracket notation.

### 5.8. Does It Automatically Validate @Validated?

When calling **new Binder(new MapConfigurationPropertySource(...))**, do not assume the full @ConfigurationProperties validation integration is installed.

Having **@Validated** on a record does not mean a manual Binder will automatically call Jakarta Validator in the same way as configuration bean creation.

If the test only needs to verify conversion and structure, Binder is enough. If you want to check constraints, you can:

1. Bind the object with Binder.
2. Call **validator.validate(object)** explicitly.
3. Or move to ApplicationContextRunner to test Spring Boot's validation integration with a real bean.

Do not label a Binder test as "application startup validation works" if the validation path has not been enabled.

### 5.9. Source Scope of MapConfigurationPropertySource

MapConfigurationPropertySource contains the keys passed by the test. It **does not automatically load** application.yml, application-prod.yml, spring.config.import, OS env, or CLI arguments.

Therefore:

~~~java
new Binder(new MapConfigurationPropertySource(values))
~~~

is well-suited for a unit binding test, but does not prove the full precedence order of the Spring Environment.

---

## 6. Level 3: ApplicationContextRunner

**ApplicationContextRunner** is part of Spring Boot's testing utilities. It creates a relatively small ApplicationContext, allowing you to supply configuration properties, register configuration/auto-configuration classes, run the context, and assert beans, conditions, or startup failures.

This is especially useful when the main questions are:

- Does Spring Boot register the @ConfigurationProperties bean?
- Does the bean bind properly when using @EnableConfigurationProperties?
- Does @Validated cause the context to fail when a nested property is invalid?
- Does @ConditionalOnProperty create a bean based on a flag?
- Does a library's auto-configuration behave properly under multiple property combinations?

### 6.1. Configuring a Minimal Runner

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
class GatewayTestConfiguration {
}
~~~

Runner:

~~~java
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GatewayTestConfiguration.class);
}
~~~

**withUserConfiguration** specifies the configuration to register in the test context. **withPropertyValues** supplies test properties to the runner's Environment.

### 6.2. Testing Successful Binding

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesContextTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(GatewayTestConfiguration.class);

    @Test
    void createsBoundGatewayBean() {
        runner.withPropertyValues(
            "app.gateway.timeout=5s",
            "app.gateway.pool.max-connections=24",
            "app.gateway.pool.enabled=true",
            "app.gateway.endpoints[0].host=primary.example.test",
            "app.gateway.endpoints[0].port=8080"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                .hasSingleBean(GatewayProperties.class);

            GatewayProperties gateway =
                context.getBean(GatewayProperties.class);

            assertThat(gateway.timeout())
                .isEqualTo(Duration.ofSeconds(5));
            assertThat(gateway.pool().maxConnections())
                .isEqualTo(24);
        });
    }
}
~~~

This test proves more than a Binder test:

- Spring creates a context.
- @EnableConfigurationProperties registers the bean properly.
- The bean receives data through Spring Boot's integration mechanism.
- The bean is resolvable in the ApplicationContext.

However, this context is not the full application with all auto-configurations, profile files, server, and real dependencies.

### 6.3. Testing Validation Failures

With GatewayProperties annotated with @Validated, @Valid, @Min, and @NotEmpty:

~~~java
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

@Test
void rejectsInvalidNestedEndpoint() {
    runner.withPropertyValues(
        "app.gateway.timeout=5s",
        "app.gateway.pool.max-connections=24",
        "app.gateway.pool.enabled=true",
        "app.gateway.endpoints[0].host=",
        "app.gateway.endpoints[0].port=0"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

If the test application does not supply a Validator on its own, include **ValidationAutoConfiguration** and an appropriate validator dependency to exercise the real validation path. An explicit setup:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;

private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withConfiguration(
            AutoConfigurations.of(ValidationAutoConfiguration.class)
        )
        .withUserConfiguration(GatewayTestConfiguration.class);
~~~

Having the validation starter on the classpath makes the validator provider available. Keep the test configuration aligned with your project's Spring Boot version.

**Do not merely assert that the context failed and conclude a specific constraint works.** A context can fail due to a missing bean, import error, or a class failing to instantiate. When targeting validation, inspect the failure cause for the relevant path/constraint, while avoiding brittle verbatim assertions on full error messages that change across versions.

### 6.4. Testing Absent Branches

An important case:

~~~java
@Test
void rejectsMissingRequiredPool() {
    runner.withPropertyValues(
        "app.gateway.timeout=5s",
        "app.gateway.endpoints[0].host=primary.example.test",
        "app.gateway.endpoints[0].port=8080"
    ).run(context -> {
        assertThat(context).hasFailed();
    });
}
~~~

Because **pool** has @NotNull, if the binder does not supply a default object, the validator must detect the missing required branch.

This case differs from having a pool object with maxConnections=0. Both should be tested when the configuration contract requires them.

### 6.5. Testing @ConditionalOnProperty

An example auto-configuration:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class AuditConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "app.audit",
        name = "enabled",
        havingValue = "true"
    )
    AuditWriter auditWriter() {
        return new AuditWriter();
    }

    static class AuditWriter {}
}
~~~

Test:

~~~java
private final ApplicationContextRunner runner =
    new ApplicationContextRunner()
        .withUserConfiguration(AuditConfiguration.class);

@Test
void enablesAuditWhenFlagIsTrue() {
    runner.withPropertyValues("app.audit.enabled=true")
        .run(context ->
            assertThat(context)
                .hasSingleBean(AuditConfiguration.AuditWriter.class));
}

@Test
void omitsAuditWhenFlagIsFalse() {
    runner.withPropertyValues("app.audit.enabled=false")
        .run(context ->
            assertThat(context)
                .doesNotHaveBean(AuditConfiguration.AuditWriter.class));
}
~~~

This case does not need the full DemoApplication. It focuses directly on **bean creation conditions**.

### 6.6. Testing Auto-Configuration Instead of User Configuration

When testing a library-provided auto-configuration, you can use:

~~~java
import org.springframework.boot.autoconfigure.AutoConfigurations;

new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MyAutoConfiguration.class)
    )
    .withPropertyValues("my.feature.enabled=true")
    .run(context -> {
        // Assert specific beans and conditions.
    });
~~~

Unlike @SpringBootTest, the runner loads only the specified configurations and relevant dependencies, making failure causes easy to isolate.

### 6.7. Context Closes After Callback

ApplicationContextRunner manages the test context lifecycle. Do not keep beans or the context in static fields for use after the callback, because the context may already be closed.

If a test needs to assert an object obtained from a bean, check it inside the callback.

### 6.8. Is @DirtiesContext Needed?

With ApplicationContextRunner, each **run** creates a separate test context and closes it after the callback. @DirtiesContext is generally not needed. That annotation is for the Spring TestContext cache in other test styles and carries its own overhead.

### 6.9. Limitations of ApplicationContextRunner

The runner does not automatically perform the full bootstrap of a SpringApplication in the same way a real application does. Do not infer the following solely from withPropertyValues:

- application-prod.yml is loaded through the full Config Data lifecycle.
- spring.config.import from classpath is processed.
- EnvironmentPostProcessor in spring.factories is discovered at the right phase.
- Startup events, logging, and all listeners ran.
- Full-application auto-configuration is loaded according to the production classpath.
- A production web server or datasource actually starts.

If those are the behaviors you need to prove, choose level 4 or construct an appropriate integration test with SpringApplication.

---

## 7. Level 4: Starting the Full Application

With **@SpringBootTest**, Spring Boot tests can start the application's ApplicationContext, load Config Data through the standard flow, perform auto-configuration, and run real wiring. If webEnvironment RANDOM_PORT is chosen, a web server can also start.

Use this level when verifying:

- Combinations of application.yml and application-prod.yml.
- Config Data imports or external config locations.
- Bootstrap behavior and EnvironmentPostProcessor discovery.
- Interactions among multiple auto-configurations.
- Business beans consuming @ConfigurationProperties properly.
- Infrastructure connection configuration (when that is the test's goal).
- An end-to-end functional flow that depends on configuration.

### 7.1. A Small @SpringBootTest

~~~java
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "app.gateway.timeout=7s",
        "app.gateway.pool.max-connections=30",
        "app.gateway.pool.enabled=true",
        "app.gateway.endpoints[0].host=test.example.test",
        "app.gateway.endpoints[0].port=9090"
    }
)
class GatewayApplicationTest {

    @Autowired
    private GatewayProperties gateway;

    @Test
    void wiresConfigurationIntoApplication() {
        assertThat(gateway.timeout())
            .isEqualTo(Duration.ofSeconds(7));
        assertThat(gateway.pool().maxConnections())
            .isEqualTo(30);
    }
}
~~~

This test requires an appropriate @SpringBootConfiguration/@SpringBootApplication and registration of GatewayProperties. It may load more beans than needed in a large application, so avoid using it by default for simple individual config fields.

### 7.2. Profile-Specific Configuration

Example:

~~~yaml
# application.yml
app:
  gateway:
    timeout: 5s
~~~

~~~yaml
# application-prod.yml
app:
  gateway:
    timeout: 12s
~~~

A test:

~~~java
import org.springframework.test.context.ActiveProfiles;

@ActiveProfiles("prod")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ProductionConfigTest {
    // Assert the effective property or real bean receives a 12s timeout.
}
~~~

In a real test, you must supply the other required fields of GatewayProperties via test files or valid sources. Do not pull a real production profile with live secrets/network dependencies into tests without an isolated design.

### 7.3. @ActiveProfiles vs. withPropertyValues

**@ActiveProfiles("prod")** in @SpringBootTest participates in the test bootstrap mechanism with active profiles.

Conversely, an ApplicationContextRunner called only with:

~~~java
runner.withPropertyValues("spring.profiles.active=prod")
~~~

should not be treated as proof that the full Config Data pipeline loaded application-prod.yml just like a real SpringApplication. The runner does not automatically include the entire bootstrap pipeline.

### 7.4. Config Data Imports

If you want to verify:

~~~yaml
spring:
  config:
    import: "optional:file:./config/gateway.yml"
~~~

then the test must control the file/location in the startup environment and inspect the final value received by the bean. This is an integration test involving Config Data, not a plain MapConfigurationPropertySource test.

Relative paths can depend on the test runner's working directory. For stable tests, use a temporary directory or explicitly configured test resource rather than relying on files that happen to exist on a developer machine.

### 7.5. EnvironmentPostProcessor Discovery

If the application has a processor registered in **META-INF/spring.factories**, a unit test calling:

~~~java
processor.postProcessEnvironment(environment, application);
~~~

only proves callback logic.

To prove the spring.factories file is right, a test must start SpringApplication and check that the PropertySource appeared. A @SpringBootTest in a suitable environment can verify that discovery, though when you want to avoid unrelated beans you can use a minimal test application started via SpringApplication.

### 7.6. Not Every Level 4 Test Needs an HTTP Server

Choose webEnvironment according to purpose:

| WebEnvironment | When appropriate |
| --- | --- |
| NONE | Testing bootstrap/config beans without needing the web layer |
| MOCK | Testing a mocked web context without opening a real port |
| RANDOM_PORT | Testing a real web server and HTTP interactions |
| DEFINED_PORT | Only with a clear reason for a fixed port; prone to environment conflicts |

If you only need to check PropertySources or @ConfigurationProperties in the full application, **NONE** is usually enough. Running RANDOM_PORT without HTTP assertions adds unnecessary overhead.

### 7.7. When a Database or External Service Is Needed

@SpringBootTest does not imply connecting to a production database. If the goal is to test infrastructure integration, use a controlled test environment (container, embedded service, or appropriate stub) and avoid real credentials.

If the test only aims to verify a timeout binds properly, mock/stub heavy dependencies or push the test to a lower level instead of booting the entire system.

---

## 8. Choosing the Testing Level via Decision Questions

You can decide in order:

~~~text
Is Spring or property binding needed?
    |
    +-- No --> Plain Java object test
    |
    +-- Yes
         |
         +-- Only testing property names, structure, and conversion?
         |      |
         |      +-- Yes --> Binder test
         |
         +-- Need bean creation, @Validated, or conditionals?
         |      |
         |      +-- Yes --> ApplicationContextRunner
         |
         +-- Need Config Data/profiles/imports/EPP discovery
                or full-application wiring?
                |
                +-- Yes --> @SpringBootTest / SpringApplication
~~~

When a case can be tested at two levels, prefer the **lower** level for detailed checks. Higher levels should only verify a few representative flows, focusing on mechanisms the lower levels do not cover.

### 8.1. A Selection Example

Suppose a production bug occurs where **app.gateway.timeout=5s** binds to the wrong Duration. The right level to reproduce the conversion issue is **Binder**. A @SpringBootTest might show the application failing, but includes many unrelated elements.

If the bug is that **application-prod.yml is not being loaded**, a Binder Map test does not model that cause. You need a SpringApplication/Config Data test.

If the bug is that a **feature flag fails to create a bean**, ApplicationContextRunner with true/false/absent values is usually the most effective.

---

## 9. Distinguishing Four Meanings of "Valid Configuration"

Saying "the configuration is valid" can mean several things:

**Valid object logic** — e.g., maxConnections is at least 1, timeout is positive, List is non-empty.

**Valid binding** — property names match, values convert to Java types, nested paths match the hierarchy.

**Valid Spring context** — classes are registered, beans are created, validation is triggered, bean conditions evaluate properly.

**Valid deployment** — profiles, external files, env vars, CLI arguments, infrastructure, and startup behavior actually match the target environment.

This is why the four testing levels complement each other. A record constructor cannot prove Spring loaded a profile. A passing @SpringBootTest also does not guarantee every rare configuration branch was tested if edge cases are missing from the tests.

---

## 10. A Practical Test Matrix for GatewayProperties

Instead of writing every test at level 4, distribute them as follows:

| Scenario | Primary level | Why |
| --- | --- | --- |
| Timeout must be positive by Java invariant | Object | Does not need Spring |
| Defensive copy of endpoint List | Object | Part of Java contract |
| **5s** converts to Duration | Binder | Conversion |
| **max-connections** maps to maxConnections | Binder | Relaxed binding |
| endpoints[0].port converts to int | Binder | Collection index + conversion |
| Value "abc" for port fails | Binder | Conversion failure |
| @NotBlank on Endpoint.host fails context | ApplicationContextRunner | Integrated validation |
| @NotNull on Pool when entire branch absent | ApplicationContextRunner | Validation + bean binding |
| app.audit.enabled=false omits AuditWriter | ApplicationContextRunner | Conditional bean |
| application-prod.yml overrides application.yml | Full application | Config Data + profile |
| EPP is actually discovered from spring.factories | Full application | Bootstrap discovery |
| Client connects to real mock server | Full application/integration | Runtime integration |
| Secret config is not printed to logs | Dedicated security test | Not solely Binder responsibility |

This matrix clarifies each test's goal and avoids a suite of hundreds of @SpringBootTest classes just to verify a few Strings.

---

## 11. Testing Defaults: Picking the Right Layer

Default values can come from many places:

1. Field initializers in a JavaBean.
2. Compact constructors or invariants in a record.
3. **@DefaultValue** in constructor binding.
4. Base application.yml.
5. Default properties supplied by SpringApplication.
6. Low-priority PropertySources from a library.
7. Fallbacks after an unbound Binder call.

Each source has a different testing scope.

### 11.1. Defaults in Java Objects

~~~java
public record RetrySettings(int attempts) {
    public RetrySettings {
        if (attempts < 1) {
            attempts = 3;
        }
    }
}
~~~

A plain Java test is enough to verify this logic. However, keep in mind that silently turning an invalid value into a default can mask misconfigurations; for required settings, throwing an error or validating is usually better.

### 11.2. Defaults from application.yml

If you want to verify a lower-precedence value from application.yml is used when prod omits it, you need a test with proper Config Data startup. A Binder Map test does not know about the application's base files.

### 11.3. Defaults from a PropertySource Added by an EPP

There are two separate questions:

- Does the EPP add the expected source and default values? -> Unit test the processor with StandardEnvironment.
- Does SpringApplication discover the EPP, and is the source order right? -> Integration test.

### 11.4. Defaults Do Not Mean Missing Properties

If a record has @DefaultValue or a constructor replaces null with a valid value, Bean Validation may see the post-default data. A @NotNull on a defaulted field will not prove an operator actually declared the property.

When a value is required from deployment, do not supply a fake valid default just to make startup tests pass.

---

## 12. Testing Null, Empty, Malformed Types, and Constraint Violations

Four states require separate cases:

| Input | Example | Failure to check |
| --- | --- | --- |
| Undeclared | No app.gateway.pool | Binding/default/@NotNull |
| Declared empty | app.gateway.endpoints=[] | @NotEmpty or collection policy |
| Wrong type | app.gateway.timeout=abc | Conversion |
| Right type, invalid constraint | app.gateway.pool.max-connections=0 | @Min(1) |

If all tests only use one "valid" YAML, many bugs will slip through.

### 12.1. Missing an Entire Nested Branch

A bean with:

~~~java
@Valid @NotNull Pool pool
~~~

needs a test omitting **app.gateway.pool.*** to make sure the program rejects missing required pool config.

### 12.2. Branch Present with Missing Child Field

With Pool using primitive int for maxConnections, when the property is absent the primitive may default to 0 on some binding paths. @Min(1) catches 0 if validation reaches Pool.

If you need to distinguish "absent" from "explicitly 0", use Integer with @NotNull and @Min instead of a primitive.

### 12.3. List with an Invalid Element

Suppose a List contains:

~~~properties
app.gateway.endpoints[0].host=primary.example.test
app.gateway.endpoints[0].port=8080
app.gateway.endpoints[1].host=
app.gateway.endpoints[1].port=0
~~~

The Binder level verifies there are two Endpoints and conversion handles 8080/0. The ApplicationContextRunner level checks @Valid cascading into the second Endpoint so @NotBlank/@Min report violations.

### 12.4. @Valid Does Not Make a Collection Non-Null

If a List is null, @Valid on the element does not create a List. Use @NotEmpty or @NotNull on the container per your contract. If null elements are also disallowed, place @NotNull on the container element type.

---

## 13. Testing Relaxed Binding by Source

Spring Boot provides relaxed binding for @ConfigurationProperties. However, distinguish putting a key into MapConfigurationPropertySource from supplying a **real OS environment variable**.

Example:

~~~text
Canonical: app.gateway.pool.max-connections
Java:      maxConnections
Env:       APP_GATEWAY_POOL_MAXCONNECTIONS
~~~

Typical canonical-to-env conversion rules:

1. Dots become underscores.
2. Remove hyphens.
3. Convert letters to uppercase.

Do not blindly convert it to **APP_GATEWAY_POOL_MAX_CONNECTIONS** just because camelCase has an uppercase C.

### 13.1. What Does a Binder Map Test Prove?

If a Map contains:

~~~text
app.gateway.pool.maxConnections=24
~~~

a Binder test helps verify the binder recognizes name variants in a test source.

### 13.2. What Does Testing Real Env Vars Require?

To prove the application reads an environment variable, the test setup needs real environment-variable semantics—such as a child-process test with env vars supplied before JVM launch, or a PropertySource accurately modeling how Spring processes environment names.

**withPropertyValues("APP_GATEWAY_POOL_MAXCONNECTIONS=24") is not equivalent to OS env**, because it adds a test property rather than placing it in a system-environment-style PropertySource.

### 13.3. Do Not Mutate Process Environment via Reflection

Hacks that mutate System.getenv() via reflection can break on modern JVMs and interfere with other tests. For real env var integration, prefer process-level tests or framework-supported mechanisms.

---

## 14. Testing PropertySource Precedence

Suppose the same property has different values:

~~~text
application.yml             -> 5s
application-prod.yml        -> 8s
OS env                      -> 10s
JVM system property         -> 12s
Command-line argument       -> 15s
~~~

In standard flows, CLI typically outranks Config Data, env, and system properties; however, test and extension sources can be positioned with even higher priority.

### 14.1. When Only Checking Selection Between Two Sources

A Binder test can be built with two ordered ConfigurationPropertySources if you want to verify the algorithm of code that constructs a Binder directly. Remember that the source order you pass is the test contract, not full Spring Boot precedence.

### 14.2. When Verifying Boot Precedence

Use an integration test with SpringApplication and real sources or test harnesses that accurately reproduce them. Check the effective value on the configuration bean, and inspect which source provided it for diagnostics.

### 14.3. Test Property Overrides Have Their Own Precedence

In @SpringBootTest, values passed via test annotations or dynamic test properties typically have high priority, which is great for test isolation. That same precedence can mask values from application.yml.

Thus a test with @SpringBootTest(properties = "app.gateway.timeout=7s") is **not proof** that application-prod.yml contains 7s. It only proves the test override was applied.

---

## 15. Testing Config Data and Profiles

Config Data behaviors should be tested at an appropriate startup level:

- Default profile vs. active profiles.
- application.yml and application-prod.yml.
- spring.config.import and imported files.
- Optional file locations and required files.
- External paths outside the JAR.
- Profile groups and on-profile activation.
- Override order across location groups.
- Multiple sources defining the same property with different precedence.

### 15.1. Do Not Use Plain Binder Tests to Conclude Profile Behavior

A Binder built from a Map does not read profiles automatically. If a test binds a Duration from a Map, that does not prove the prod profile's config file is loaded by SpringApplication.

### 15.2. File Location Tests Should Not Depend on Developer Machines

Do not write tests pointing to:

~~~text
C:\Users\dev\local-config\application-prod.yml
~~~

or real files outside the repository and assume CI has them. Use test resources, temporary directories, or test-controlled configuration with explicit paths.

### 15.3. Test Absent Files Too

If a config import uses optional: and the file is missing, startup can continue per policy. If it is not optional and a required file is missing, startup should fail. This is **Config Data/bootstrap** behavior and should be tested with a SpringApplication-level test rather than new Binder(Map).

---

## 16. Testing EnvironmentPostProcessor and Bootstrap Order

An EnvironmentPostProcessor is typically registered in **META-INF/spring.factories** and runs while preparing the Environment before context refresh.

Two test types should be separated.

### 16.1. Unit Testing the Processor

~~~java
import java.util.Map;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.StandardEnvironment;

StandardEnvironment env = new StandardEnvironment();

env.getPropertySources().addFirst(
    new MapPropertySource(
        "testOverride",
        Map.of("company.http.timeout", "12s")
    )
);

processor.postProcessEnvironment(
    env,
    new SpringApplication(Object.class)
);

assertThat(env.getProperty("company.http.timeout"))
    .isEqualTo("12s");
~~~

This case verifies the processor does not clobber overrides from other sources when the processor follows a low-priority default policy.

### 16.2. Integration Testing Discovery

A real SpringApplication must start and confirm the custom source was added. It verifies:

- The spring.factories path.
- The registration key matching the Boot version.
- Presence of the implementation class on the runtime classpath.
- Successful processor instantiation.
- Ordering relative to Config Data in the real flow.

### 16.3. Differences Between Boot 3 and Boot 4

During migrations, the EnvironmentPostProcessor interface changes packages between Boot 3 and Boot 4. Discovery tests are especially valuable because code can compile against imports while spring.factories still has the wrong key.

### 16.4. Do Not Substitute Local Runner for Discovery Tests

ApplicationContextRunner is designed for testing small contexts and auto-configurations. It does not by default reproduce every bootstrap listener and discovery step of SpringApplication. Therefore, testing an EPP merely by calling .withPropertyValues(...) does not prove discovery.

---

## 17. Testing @ConditionalOnProperty and Edge Cases

If configuration controls a bean with:

~~~java
@ConditionalOnProperty(
    prefix = "app.audit",
    name = "enabled",
    havingValue = "true"
)
~~~

test at least:

| app.audit.enabled value | Expected in this example |
| --- | --- |
| true | Bean is present |
| false | Bean is absent |
| Absent | Bean is absent when matchIfMissing defaults to false |
| String other than "true" | Does not match havingValue="true" |

ApplicationContextRunner fits well because it can spin up small contexts for each combination.

### 17.1. What to Assert

Do not only check that Environment has the property. Assert whether the bean is present or absent, because **bean creation rules** are what is under test.

### 17.2. When a Feature Flag Interacts with Other Beans

If AuditWriter requires a dependency that only exists in production, a Runner-level test can supply a stub bean in minimal configuration instead of starting the entire application.

When bugs arise in full-system wiring or interactions among multiple subsystems' auto-configurations, supplement with a full integration test.

---

## 18. Testing Validation at Two Layers

Two things are distinct:

1. **Correct constraint metadata**: Jakarta Validator catches @NotBlank, @Min, and @Valid on a directly constructed object.
2. **Spring Boot executes validation during bean binding**: the context fails to start or the bean is not created when a property violates constraints.

### 18.1. Checking Constraint Metadata

Use unit tests with Validator to confirm constraints, especially nested Lists/Maps and null cases.

### 18.2. Checking Validation Integration

Use ApplicationContextRunner to bind from property values, register @ConfigurationProperties, and verify the context fails when data is invalid.

A passing unit test with Validator **does not prove** the bean has @Validated, was scanned, and has a validator provider present in a real context.

### 18.3. Do Not Mistake Conversion Failures for Validation

If **max-connections=many** and the Java target is int, Binder can fail before Jakarta Validation runs. Type-mismatch tests belong under conversion tests, not grouped with @Min(1).

### 18.4. Avoid Assuming Every Nested Object Is Validated

Across multiple levels, @Valid is needed at each boundary. A null child object is not automatically rejected by @Valid; add @NotNull if required. Testing a missing branch and testing a child object with invalid fields are two separate cases.

---

## 19. Testing Configuration That Depends on External Infrastructure

A datasource or HTTP client configuration has two verification levels.

**Configuration level:** URL, port, timeout, and pool size bind properly into a Java object or bean factory.

**Connectivity level:** the client can actually connect to an endpoint, uses valid TLS/authentication, and enforces the timeout at runtime.

A Binder test can verify timeout=3s, but cannot prove an HTTP client will abort a slow request after three seconds. A runtime connectivity test requires a fake server, controlled latency, or corresponding test infrastructure.

### 19.1. Do Not Use Production Infrastructure

Tests must not depend on production databases, live tokens, or uncontrolled external services. When a database is needed, use an appropriate container or embedded database and pass connection details through the test environment.

### 19.2. Dynamic Properties for Resources Started in Tests

With @SpringBootTest, Spring supports **@DynamicPropertySource** to register properties whose values are only known once test setup runs, such as ports assigned by containers or mock servers.

Conceptual example:

~~~java
@DynamicPropertySource
static void registerProperties(DynamicPropertyRegistry registry) {
    registry.add(
        "app.external.base-url",
        () -> testServerBaseUrl()
    );
}
~~~

In real code, **testServerBaseUrl()** must come from a server/container created and managed by the test. This snippet illustrates the API hook, not a built-in Spring helper.

### 19.3. Test Sources Can Mask Real Sources

A @DynamicPropertySource override can make beans run properly in tests without proving production deployment env var names are spelled right. When verifying env var naming or Config Data precedence, make sure dynamic properties do not accidentally hide what you intend to test.

---

## 20. Cost and Speed: Practical Trade-Offs

Test cost depends on bean count, classpath, I/O, and infrastructure, with no fixed numbers. However, the relative ordering is usually:

~~~text
Fast and isolated
    |
    v
Plain Java / Bean Validation unit test
    |
    v
Binder + MapConfigurationPropertySource
    |
    v
ApplicationContextRunner
    |
    v
Full @SpringBootTest / server / containers
    |
    v
Heavier, tests more components
~~~

An ApplicationContextRunner is not necessarily faster than every tiny @SpringBootTest, but it deliberately narrows the scope. In large projects, booting the full context repeatedly for every single property can slow CI considerably.

### 20.1. TestContext Caching

Spring TestContext can cache contexts across tests with matching configurations. Changes such as profiles, property overrides, test configurations, and dynamic properties can produce distinct cache keys.

Writing dozens of @SpringBootTest classes with different property combinations can spin up many contexts and increase runtime.

### 20.2. @DirtiesContext Is Not the Default Solution

Use @DirtiesContext when a test genuinely leaves the context unsafe to reuse. Overusing it defeats caching benefits and can mask mutable shared-state problems in tests.

### 20.3. Avoid Unnecessary Sleeps or Network Calls

A configuration test that only compares Duration values should not make slow HTTP requests or call Thread.sleep. If runtime timeout enforcement needs testing, that belongs in a separate behavioral test with controlled timing and deterministic outcomes.

---

## 21. Naming Tests by Behavior

Test names should describe the behavior that level can prove.

Good examples:

~~~text
shouldRejectNegativeBackoff
shouldBindKebabCaseIntoCamelCaseRecordComponent
shouldConvertDurationFromPropertyValue
shouldRejectInvalidNestedEndpointAtContextStartup
shouldCreateAuditWriterOnlyWhenEnabled
shouldLoadProdConfigDataBeforeCreatingClient
shouldDiscoverPlatformEnvironmentPostProcessor
~~~

Overly broad or imprecise examples:

~~~text
shouldVerifyAllConfiguration
shouldGuaranteeProductionIsCorrect
shouldTestEverythingAboutProfiles
~~~

A test running in a local JVM cannot guarantee all production behavior. Clear names help reviewers understand the true scope.

---

## 22. Recommended Test Strategy for a Medium-Sized Project

For a GatewayProperties group with a handful of fields, you might allocate:

- **Object tests:** a few cases for invariants and defensive copies, only if the class actually has logic.
- **Binder tests:** one nested happy path with Duration/List, one key-name/type-error case.
- **ApplicationContextRunner:** one valid bean case, one nested validation failure case, and feature-flag cases if applicable.
- **Full application:** one or a few representative cases for profiles/imports/bootstrap and real client wiring.

You do not need to test every combination at all four levels.

### 22.1. When to Skip Level 1?

If GatewayProperties is purely a data record with no constructor logic and all constraints are covered at the ApplicationContextRunner level, you may skip a separate unit test that merely asserts record accessors return the passed arguments.

Do not write pointless tests just to check off "all four types."

### 22.2. When to Skip Level 2?

If there are only a few plain Strings with no collections, conversions, or special naming, an ApplicationContextRunner happy path may suffice. Dedicated Binder tests are not mandatory for every field.

### 22.3. When to Invest More in Level 4?

If the project relies on multiple Spring profiles, complex Config Data imports, custom EnvironmentPostProcessors, or critical auto-configurations, full integration testing deserves greater investment.

Allocate tests by risk, not by a fixed ratio.

---

## 23. Risk Matrix for Prioritizing Tests

| Risk | Production symptom | Highest-value test |
| --- | --- | --- |
| Wrong Duration/DataSize format | Startup failure or wrong timeout | Binder |
| Wrong nested prefix | Field is null despite file having a value | Binder |
| Missing @Valid | Bean is created with invalid config | ApplicationContextRunner |
| Missing @ConfigurationPropertiesScan | Bean cannot be injected | Runner or full app |
| Wrong conditional bean | Feature disabled yet bean still runs | ApplicationContextRunner |
| Wrong profile precedence | Prod uses dev defaults | Full app |
| Wrong EPP spring.factories | Defaults are not loaded | Full app |
| List replaced on profile switch | Missing endpoints | Full app with Config Data |
| Wrong env var name | Deployment fails to override | Process/env integration |
| Secrets leaked in logs | Security exposure | Dedicated security/logging test |
| HTTP timeout not enforced | Requests hang | Runtime integration |
| Overly heavy context startup | Slow, flaky CI | Push isolatable checks to lower level |

Prioritize tests by **root cause**, not by where the error surfaces. An error logged at startup does not always require @SpringBootTest to reproduce if the root cause is a conversion issue testable with Binder.

---

## 24. Success and Failure Tests Are Equally Valuable

Do not write only a pretty happy-path YAML test. For important configuration, cover:

~~~text
VALID:     valid values -> bean created, object holds expected data
MISSING:   missing required field -> meaningful failure
INVALID:   right type, violates constraint -> validation fails
MALFORMED: cannot convert type -> conversion fails
OVERRIDE:  higher-priority source -> expected final value wins
DISABLED:  feature flag false -> bean is not created
~~~

Each item maps naturally to a layer:

- VALID/MISSING/INVALID for beans -> ApplicationContextRunner.
- MALFORMED for conversion -> Binder.
- OVERRIDE via Config Data profiles -> Full application.
- DISABLED via @ConditionalOnProperty -> ApplicationContextRunner.

---

## 25. Testing Maps and Lists Needs Extra Cases

### 25.1. List Indexing

~~~properties
app.gateway.endpoints[0].host=alpha.example.test
app.gateway.endpoints[0].port=8080
app.gateway.endpoints[1].host=beta.example.test
app.gateway.endpoints[1].port=8081
~~~

A Binder test can verify the exact ordering of the two Endpoints.

### 25.2. List Replacement Across Sources

If application.yml defines two endpoints but application-prod.yml defines one endpoint, Spring Boot typically selects the List from the higher-priority source instead of concatenating them.

To verify that behavior from real files, use a Config Data integration test. Do not infer it from a Binder Map containing manually pre-merged data.

### 25.3. Dynamic Map Keys

For Map<String, Region> with keys containing dots, bracket notation may be required:

~~~yaml
app:
  regions:
    "[tenant.eu]":
      endpoint: "https://eu.example.test"
~~~

A Binder test can verify the resulting Map preserves the key **tenant.eu**, while an integration test checks that the YAML loader and Config Data parse the document properly.

### 25.4. Immutable Collections

If a record uses List.copyOf/Map.copyOf, an object unit test is the best place to verify callers cannot mutate the collection after construction. You do not need to start Spring just to call List.add and expect UnsupportedOperationException.

---

## 26. When Custom Converters Exist

A project might use a domain type:

~~~java
public record RegionId(String value) {}
~~~

and want to convert String properties to RegionId through a custom converter.

There are two separate questions:

1. Is the converter logic right? -> Plain Java unit test for the converter.
2. Is the converter registered with Spring Boot and actually used by the Binder in the application? -> ApplicationContextRunner or integration test with the appropriate conversion service/registration.

A test calling **converter.convert("asia")** directly does not prove the binder knows about that converter. Conversely, a manually constructed binder with a different conversion service does not prove runtime uses the same converter.

### 26.1. @ConfigurationPropertiesBinding

Spring Boot provides a mechanism to register converters for @ConfigurationProperties in supported versions. When custom conversion is required, verify the **registration mechanism** inside a context rather than only testing the convert method result.

### 26.2. Converters Should Have No Side Effects

Property conversion should be fast and predictable. Do not use a converter to query a database or make HTTP calls during configuration initialization. Tests for converters with external dependencies quickly become flaky due to mixed responsibilities.

---

## 27. Testing YAML and .properties Configuration

### 27.1. Source Testing Differences

A Binder Map test receives flattened keys:

~~~text
app.gateway.pool.max-connections=24
~~~

It does not test whether the YAML parser reads this correctly:

~~~yaml
app:
  gateway:
    pool:
      max-connections: 24
~~~

If bugs involve indentation, document separators, or profile activation, use a test with a real loader/Config Data.

### 27.2. Wrong YAML Nesting Level

Broken YAML:

~~~yaml
app:
  gateway:
    max-connections: 24
~~~

has path **app.gateway.max-connections**, not **app.gateway.pool.max-connections**.

A Binder test can expose the effect if given that exact wrong key, but does not prove the source file has that structure unless the parser runs.

### 27.3. Multi-Document YAML

Documents separated by **---** can have their own activation rules. If the goal is to verify when a document is selected, use a Config Data test with the relevant profile rather than manually combining Maps from multiple documents.

---

## 28. Testing Environment Variables and JVM Options

Different sources use different syntaxes:

~~~bash
APP_GATEWAY_TIMEOUT=8s java -jar demo.jar
~~~

~~~bash
java -Dapp.gateway.timeout=8s -jar demo.jar
~~~

~~~bash
java -jar demo.jar --app.gateway.timeout=8s
~~~

These are an OS environment variable, a JVM system property, and a command-line argument—three distinct sources.

### 28.1. A withPropertyValues Test Does Not Prove All Three

ApplicationContextRunner with:

~~~java
.withPropertyValues("app.gateway.timeout=8s")
~~~

proves the runner supplied a property. It does not prove the shell, JVM -D flag, or CLI parser is being exercised.

### 28.2. When Testing Startup CLI Is Needed

Use SpringApplication.run with arguments in an isolated integration test, or launch a child process with the exact desired CLI options. Do not scatter System.setProperty calls without restoring state.

### 28.3. System Property Tests Must Clean Up

If you must use System.setProperty, save the previous value before the test and restore it in a finally block or appropriate extension. System properties are JVM-global state; if leaked, parallel tests can interfere with each other.

### 28.4. Testing Real OS Env

To test UPPER_UNDERSCORE names at the OS level, a test launching a child JVM process with environment variables set before startup is usually more reliable than hacking System.getenv directly.

---

## 29. Testing Configuration with Security and Secrets

An essential testing rule:

**Never use production secrets in test fixtures.** If you need to test usernames/passwords/tokens, use dummy strings with no real access.

Example:

~~~properties
app.external.api-key=dummy-test-key
~~~

Do not log an entire @ConfigurationProperties record when it holds sensitive data; record.toString() can include component values.

### 29.1. Testing Redaction Is a Separate Test

If an operational requirement is that configuration errors must not leak tokens in logs, write a dedicated log-capture test or Actuator/API test. Standard Binder tests do not verify masking.

### 29.2. Do Not Push Secrets Through PropertySources Unnecessarily

An EPP test can use a dummy key to verify a source was added. You do not need to load Secret Manager or real tokens just to prove map precedence.

---

## 30. Avoiding False Confidence from @SpringBootTest

A green @SpringBootTest does not mean:

- All profiles have been tested.
- All environment variable forms bind properly.
- Every custom converter works on every input.
- Secrets are always redacted.
- All constructor invariants have been checked.
- A List from another source will merge as expected.

A test only proves the inputs and behaviors it actually exercises.

### 30.1. Check Final Values, Not Just Startup

If @SpringBootTest only asserts the context starts without error, a misspelled property could silently fall back to a valid default. For critical settings, assert **what values the configuration bean actually receives**.

### 30.2. Do Not Use @SpringBootTest for Every Small Calculation

That increases CI time and complicates debugging. Pure calculations belong in unit tests, and binder behavior belongs in Binder tests.

---

## 31. Avoiding False Confidence from Binder Tests

A green Binder test does not prove:

- Beans are scanned/enabled.
- @Validated actually runs at startup.
- Application PropertySource precedence matches the test Map.
- Config Data external file imports work.
- EPPs registered via spring.factories run.
- The app is free of bean conflicts or other auto-configuration issues.
- Runtime HTTP clients actually apply the timeout.

If the risk lies in lifecycle or integration, add level 3/4 tests.

---

## 32. Avoiding False Confidence from Object Tests

A constructor tested in plain Java might be correct while Spring Boot still fails to instantiate the object due to:

- Mismatched property names.
- Wrong nested paths.
- Field types lacking a converter.
- Constructor binding incompatible with bean registration.
- Missing @ConfigurationPropertiesScan.
- Missing validator provider.
- Unloaded profile/Config Data.

Object tests only check the Java object itself and whatever dependencies the test invokes directly.

---

## 33. When to Use ApplicationContextRunner Instead of the Full App?

Use the Runner when code needs to prove Spring context behavior **without depending on the whole application**.

For example, an auto-configuration module enabling a datasource client based on a property:

~~~java
@ConditionalOnProperty(
    prefix = "feature.client",
    name = "enabled",
    havingValue = "true"
)
~~~

With the runner you can test:

~~~text
feature.client.enabled=true
feature.client.enabled=false
feature.client.enabled absent
~~~

and assert bean counts. You do not need to start a web server, JPA, message broker, or data sources from unrelated modules.

If an auto-configuration depends on an infrastructure bean, supply a stub/mock bean via minimal test configuration or inspect the condition report in the targeted context. Do not drag in the entire application just to satisfy an isolatable dependency.

### 33.1. When Is the Runner Not Enough?

If failures only happen when the application's auto-configurations interact, or during Config Data/EPP bootstrap, full-app tests are still needed. The Runner and @SpringBootTest complement each other.

---

## 34. Organizing the Test Suite in a Repository

One way to group tests:

~~~text
src/test/java/
  example/config/
    RetrySettingsTest.java
    GatewayConstraintsTest.java
    GatewayBinderTest.java
    GatewayPropertiesContextTest.java
  example/autoconfigure/
    AuditAutoConfigurationTest.java
  example/integration/
    ProductionConfigDataTest.java
    EnvironmentProcessorDiscoveryTest.java
    GatewayApplicationTest.java
~~~

Directory names are illustrative. The goal is letting readers immediately see whether a test covers object logic, binder, context, or integration.

### 34.1. Running Fast Tests on Every Small Change

Object/Binder/Runner tests can run in the fast inner development loop. Full-app or container tests can be grouped into an integration suite according to the project's build/CI setup.

However, do not postpone integration tests too long when changes directly touch Config Data, profiles, or critical bootstrap extensions. When risks live at system integration boundaries, run those tests before release.

### 34.2. Never Make Tests Depend on Execution Order

Each test must create its own data and context. Never rely on test A setting System properties and test B accidentally benefitting from them. That breaks easily when CI runs tests in parallel.

---

## 35. Testing Startup Failures for Clear Root Causes

When a test expects the ApplicationContext to fail:

~~~java
runner.withPropertyValues(
    "app.gateway.timeout=5s",
    "app.gateway.pool.max-connections=0",
    "app.gateway.endpoints[0].host=alpha.example.test",
    "app.gateway.endpoints[0].port=8080"
).run(context -> {
    assertThat(context).hasFailed();
});
~~~

Checking hasFailed is only the first step. To make the test meaningful, confirm the failure comes from the @Min(1) constraint on pool rather than an unrelated missing bean.

You can inspect **context.getStartupFailure()** and its cause chain, keeping in mind that exact exception types and messages can vary across Spring Boot versions.

### 35.1. Do Not Rely on Full Log Strings

Avoid verbatim multi-line assertions on failure reports such as whitespace, field ordering, or internal wording. Focus on reliable signals: binding/validation failure types, property paths, and constraints where stably represented.

### 35.2. One Failure Test Should Have One Primary Cause

If a test checks pool.maxConnections=0, provide valid endpoints and timeout. If endpoints and timeout are also missing, the context may fail for a different reason, making the test unreliable.

---

## 36. Step-by-Step Minimal Test Suite for a New Config Group

Suppose you just added:

~~~java
@ConfigurationProperties(prefix = "app.notification")
public record NotificationProperties(
        Duration timeout,
        int maxRetries
) {}
~~~

You can proceed as follows:

**Step A — define the data contract:** timeout must be positive, maxRetries within a valid range, whether defaults exist, and what the canonical names are.

**Step B — if Java invariants exist:** write plain constructor/validation unit tests with no context.

**Step C — if conversions matter:** write a Binder test from **app.notification.timeout=250ms** and **app.notification.max-retries=3**.

**Step D — if @Validated or conditional beans exist:** write ApplicationContextRunner tests for one valid case and one invalid case.

**Step E — if configuration depends on profiles, imports, or bootstrap:** write a full-app integration test proving the final source and proper bean usage.

**Step F — when fixing production bugs:** pick the exact level that reproduces the cause, while keeping representative integration tests if the bug occurred across component boundaries.

This is far more effective than defaulting to @SpringBootTest for every field.

---

## 37. Exercise 1: Pick the Lowest Sufficient Level

Choose one of the four levels for each question:

1. Does **List.copyOf** protect a record component from mutation?
2. Does the string **"5s"** bind to Duration properly?
3. Does @NotBlank on a child object fail the context when @Valid is declared?
4. Is application-prod.yml loaded when the prod profile is enabled?
5. Does @ConditionalOnProperty register a bean only when the flag is true?
6. Does spring.factories discover an EnvironmentPostProcessor inside the JAR?

Suggested answers:

~~~text
1 -> Object
2 -> Binder
3 -> ApplicationContextRunner
4 -> Full application / SpringApplication Config Data
5 -> ApplicationContextRunner
6 -> Full application / SpringApplication discovery
~~~

Do not answer "@SpringBootTest for all six" just because it covers more ground. That bloats the test suite without improving fault isolation.

## 38. Exercise 2: Binder or Validator?

Given the record:

~~~java
public record RetrySettings(
        @Min(1) int attempts,
        Duration backoff
) {}
~~~

With properties:

~~~properties
retry.attempts=0
retry.backoff=3s
~~~

A Binder test can verify **attempts=0** and **backoff=PT3S** bind properly by type, unless there is a constructor invariant or custom handler. That alone is **not enough** to prove @Min(1) is enforced.

You must test @Min(1) with Jakarta Validator directly or with ApplicationContextRunner using a @Validated @ConfigurationProperties bean and a validation provider.

**Key takeaway:** Binding and validation are two distinct mechanisms.

## 39. Exercise 3: ContextRunner or Full Application?

A module defines:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "feature.export",
    name = "enabled",
    havingValue = "true"
)
ExportService exportService() { ... }
~~~

Goal: when the flag is false, the bean must not exist.

**Choose ApplicationContextRunner.** It lets you pass false into a small context and verify the bean is absent.

If the question becomes: "In prod, does an imported external file setting feature.export.enabled=true cause the real application to create ExportService?" then choose **full SpringApplication** because you need to verify Config Data and runtime wiring.

## 40. Exercise 4: Testing a Real Env Source

A developer writes:

~~~java
runner.withPropertyValues(
    "APP_GATEWAY_POOL_MAXCONNECTIONS=20"
)
~~~

and concludes the OS will convert that env var name properly.

That conclusion is unfounded because withPropertyValues does not necessarily represent an OS environment PropertySource. You need a test with proper system environment semantics or a child JVM launched with the real env var.

Also know that the canonical key is:

~~~text
app.gateway.pool.max-connections
~~~

and the standard env name is:

~~~text
APP_GATEWAY_POOL_MAXCONNECTIONS
~~~

## 41. Exercise 5: Missing, Invalid, and Override

Given configuration:

~~~yaml
app:
  pool:
    max-connections: 20
~~~

Create three cases:

1. No app.pool.*.
2. app.pool.max-connections=0.
3. Base file has 20 while the prod profile has 40.

Suggestions:

- Case 1: Binder if just checking absent binding, or Runner if checking @NotNull/@Min fails on the bean.
- Case 2: Runner if the goal is @Validated catching @Min(1).
- Case 3: Full application if proving Config Data profile precedence.

State the goal before choosing the technique; the same input can be tested at different layers because the proof required differs.

## 42. Exercise 6: Reading Errors from the Context

A runner test sets:

~~~properties
app.gateway.pool.max-connections=0
app.gateway.timeout=abc
~~~

It fails. Can you conclude @Min(1) works?

**No.** The value timeout=abc can already fail conversion before validation runs.

Change timeout to **5s**, keep pool.max-connections=0, and supply valid values for the other required fields. Then the test genuinely targets pool validation.

## 43. Exercise 7: Optimizing a Slow Test Suite

A project has 60 separate @SpringBootTest classes, each checking one Duration, int, or feature flag.

A sensible refactoring plan:

- Move conversion-only cases to Binder tests.
- Move conditional beans and @Validated startup checks to ApplicationContextRunner.
- Keep a few representative @SpringBootTest classes for profiles, imports, discovery, and real wiring.
- Do not delete all integration tests; only remove duplicates already proven at lower levels.
- Measure CI duration after changes; do not assume every project has identical timings.

The goal is **reducing cost while preserving risk boundaries**.

---

## 44. Checklist Before Writing a Configuration Test

- [ ] What question is the test proving, and which mechanism is responsible?
- [ ] Does Spring need to start, or is a plain Java object enough?
- [ ] Does Binder need to convert property names and types?
- [ ] Are @ConfigurationProperties bean registration and @Validated needed?
- [ ] Are @ConditionalOnProperty or auto-configurations needed?
- [ ] Are Config Data, profiles, imports, or EPP discovery needed?
- [ ] Is a real HTTP server, datasource, or external service needed?
- [ ] Do the test's properties come from the actual source type under test?
- [ ] Does the test accidentally override the source it intends to verify?
- [ ] Are valid, missing, malformed, and invalid cases covered appropriately?
- [ ] Are nested objects, Lists, and Maps checked at the proper level?
- [ ] Are real secrets kept out of fixtures and logs?
- [ ] Does the test avoid static mutable state, System properties, or fixed ports that cause flakiness?
- [ ] Does a failure isolate a single primary cause?
- [ ] Are you booting the whole application for something Binder can verify?
- [ ] If using the full app, is there a concrete bootstrap/wiring/infrastructure reason?

A good test does not need many lines. It needs **the right scope, intentional data, and conclusions that do not overreach what was actually executed**.

## 45. Summary

The four configuration testing levels answer four distinct questions:

**Plain Java object:** Are defaults, invariants, defensive copies, and explicitly invoked constraints right? Does not test YAML, Binder, or Spring context.

**Direct Binder:** Does a set of properties convert into records/JavaBeans, nested objects, Lists/Maps, Durations, and numeric types properly? Does not by itself prove bean lifecycle, Config Data imports, or @Validated startup.

**ApplicationContextRunner:** Does a small context register, bind, and validate @ConfigurationProperties properly? Do conditional beans or scoped auto-configurations create beans appropriately when properties change? Does not automatically simulate full SpringApplication bootstrap.

**Full application:** Do profiles, Config Data, EnvironmentPostProcessors, auto-configuration, dependency wiring, and runtime integration actually work in a controlled test environment? Higher cost, but essential for boundaries that lower levels cannot prove.

The selection rule is **"the lowest level that sufficiently proves the behavior under test"**, not "always use the heaviest level to be safe." A Spring Boot project achieves an effective test suite by combining easy-to-diagnose unit tests, accurate Binder tests, ApplicationContextRunner for validation/conditions, and selective integration tests for bootstrap and real dependencies.
