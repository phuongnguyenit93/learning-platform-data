# Testing Invalid Configuration and Verifying Startup Failures

Spring Boot supports externalized configuration via `application.yml`, `application.properties`, profile-specific documents, Config Data imports, environment variables, Java system properties, and command-line arguments. The Binder converts these values into Java types, typically via `@ConfigurationProperties`. A configuration may load without syntax errors yet still be **invalid for operation**: a timeout cannot convert to `Duration`, a required token is blank, retry count is zero, or an endpoint list item lacks a URL.

For many services, such errors should be caught **at application startup** rather than on the first request or after the system begins accepting work. Therefore, configuration testing must cover both directions:

- **Positive tests:** valid configuration lets the ApplicationContext start and binds expected bean values.
- **Negative tests:** invalid configuration prevents the ApplicationContext from starting, and the failure stems from binding, validation, or bootstrap as designed.

A proper negative test still **PASSES in JUnit** when it verifies that startup failed as expected. Never treat running a test suite and leaving it red as "having tested startup failures."

This lesson uses Spring Boot 3.x, Java 17+, JUnit 5, AssertJ, and Jakarta Bean Validation. APIs and error messages may differ across versions; align details with the Spring Boot version in your project.

## 1. Distinguishing Configuration Failure Categories

A negative test needs to know where the failure occurs.

| Category | Invalid input | Detection point |
| --- | --- | --- |
| YAML/parser | Missing closing bracket, broken YAML structure | Config Data loading |
| Config Data location | Required imported file does not exist | Bootstrap |
| Conversion | `timeout=tomorrow` into `Duration` | Binder/conversion |
| Missing value | `api-key` absent | Validation or required-field logic |
| Bean Validation | `retries=0` with `@Min(1)` | Typed properties validation |
| Nested validation | Endpoint in a List missing URL | `@Valid` cascade |
| Strict unknown key | Typo `max-retreis` | Strict Binder config if enabled |
| Cross-field rule | `enabled=true` without endpoint | Custom/class-level validation |
| Bean composition | Properties type not registered | ApplicationContext initialization |
| Profile override | Dev list wipes out item fields | Binding/validation after source selection |

All of these can produce a Spring Boot "Failed to start" message, yet they **do not share the same root cause**. Asserting on just any exception can accidentally verify a classpath problem instead of the intended constraint.

## 2. Criteria for a Good Negative Configuration Test

A test should answer:

1. What is the exact invalid input?
2. Are all other properties kept valid to isolate the failure?
3. Does the context fail?
4. Does the failure belong to the expected error category?
5. When replaced with valid input, does the exact same test configuration start cleanly?
6. Does it avoid logging secret values or calling external production services?

For example, a test with `max-retries=0` aims to prove `@Min(1)` works. If the context actually fails because a datasource or properties bean is missing, `hasFailed()` still passes while **failing to test the intended rule**.

Always maintain a **valid baseline** and cases that change only one invalid parameter at a time.

## 3. Preparing Dependencies

Maven:

~~~xml
<dependencies>
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

Gradle Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

With Spring Boot 3.x, the constraint API uses `jakarta.validation`. Older Boot lines may use a different namespace. In projects using the Spring Boot parent or BOM, dependency versions are managed together; avoid adding arbitrary extra Bean Validation providers.

Understand that `@NotBlank`, `@Min`, `@NotNull`, and `@Valid` are only annotations. For validation to actually run when properties beans bind, appropriate infrastructure/providers and activation hooks must be present.

## 4. A @ConfigurationProperties Target Under Test

Valid configuration:

~~~yaml
payment:
  client:
    endpoint: "https://api.example.invalid"
    timeout: 3s
    max-retries: 3
    api-key: "fake-test-key"
~~~

Java:

~~~java
package example.payment;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "payment.client")
public record PaymentClientProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) @Max(5) int maxRetries,
        @NotBlank String apiKey
) {}
~~~

Configuration contract:

- `endpoint` must hold a URI value; `@NotNull` does not guarantee an HTTP(S) URL with a valid host.
- `timeout` must hold a `Duration`; `@NotNull` does not forbid `Duration.ZERO` or negative durations.
- `maxRetries` must be in 1..5.
- `apiKey` cannot be null, empty, or whitespace-only.

The bean must be registered:

~~~java
package example.payment;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PaymentClientProperties.class)
public class PaymentClientConfiguration {
}
~~~

Never skip registration when testing validation: an unregistered properties type can cause the test to exercise an entirely unrelated error.

## 5. The Right Tool: ApplicationContextRunner

`ApplicationContextRunner` from Spring Boot Test creates a minimal ApplicationContext from test-supplied configuration classes and property values. It is especially valuable because it **lets you observe startup failures without failing JUnit setup before the test method executes**.

A runner:

~~~java
package example.payment;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class PaymentClientPropertiesTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PaymentClientConfiguration.class);
}
~~~

`withConfiguration(AutoConfigurations.of(...))` brings validation auto-configuration into the small context when conditions and dependencies match. `withUserConfiguration(...)` loads the properties bean registration. `withPropertyValues(...)` supplies test values, and `run(context -> ...)` verifies startup success or failure.

A minimal runner **does not automatically run all Spring Boot auto-configurations or full profile-based Config Data loading**. It is suited to testing binding/validation for a module. Complex bootstrap scenarios need dedicated integration tests.

## 6. Baseline: Valid Configuration Must Pass

~~~java
package example.payment;

import java.net.URI;
import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.validation.ValidationAutoConfiguration;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class PaymentClientPropertiesTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(AutoConfigurations.of(
                ValidationAutoConfiguration.class))
            .withUserConfiguration(PaymentClientConfiguration.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
            "payment.client.endpoint=https://api.example.invalid",
            "payment.client.timeout=3s",
            "payment.client.max-retries=3",
            "payment.client.api-key=fake-test-key"
        ).run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                .hasSingleBean(PaymentClientProperties.class);

            PaymentClientProperties props =
                context.getBean(PaymentClientProperties.class);

            assertThat(props.endpoint()).isEqualTo(
                URI.create("https://api.example.invalid"));
            assertThat(props.timeout()).isEqualTo(
                Duration.ofSeconds(3));
            assertThat(props.maxRetries()).isEqualTo(3);
        });
    }
}
~~~

The baseline proves:

1. The configuration class loads.
2. Exactly one `PaymentClientProperties` bean exists.
3. Binder converts URI, Duration, and integers properly.
4. Validation accepts valid inputs.
5. Test infrastructure works.

If the baseline fails, do not interpret negative tests as succeeding. Fix test setup/registration first.

## 7. Testing @Min Violations with Valid-Type Data

~~~java
@Test
void zeroRetriesStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=0",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .isNotNull();
    });
}
~~~

The number `0` converts to `int`. The error is the `@Min(1)` constraint, not conversion. This test catches cases where a service might silently accept an invalid retry policy if validation annotations were disabled or omitted.

A similar test for `@Max(5)`:

~~~java
@Test
void tooManyRetriesStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=99",
        "payment.client.api-key=fake-test-key"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Do not use `max-retries=abc` to test `@Min`, because that value fails conversion before reaching Bean Validation.

## 8. Testing Binding/Conversion Errors

~~~java
@Test
void malformedDurationStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=not-a-duration",
        "payment.client.max-retries=3",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .isNotNull();
    });
}
~~~

Here `not-a-duration` cannot convert to `Duration` under supported formats. The error occurs inside Binder/conversion.

Comparison:

| Property | Java type | Error category |
| --- | --- | --- |
| `timeout=not-a-duration` | `Duration` | Conversion |
| `max-retries=many` | `int` | Conversion |
| `max-retries=0` | `int` + `@Min(1)` | Validation |
| `api-key=` | `String` + `@NotBlank` | Validation |
| Missing `endpoint` | `URI` + `@NotNull` | Validation or contract binding |

`@DefaultValue` is not a mechanism for silently ignoring present-but-malformed values. Defaults apply when keys are absent per contract; conversion errors still surface explicitly.

## 9. Testing Missing Required Properties

Keep endpoint, timeout, and retries valid; only **omit `api-key`**:

~~~java
@Test
void missingApiKeyStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=3"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Assuming no other property source provides `payment.client.api-key`, Binder receives null/absence and `@NotBlank` rejects it. If CI already sets an environment variable or system property under that key, results may differ—which is why isolated test namespaces matter.

Blank differs from missing:

~~~java
@Test
void blankApiKeyStopsStartup() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=3s",
        "payment.client.max-retries=3",
        "payment.client.api-key=   "
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

Use fake tokens in test data; never put real secrets in source code, logs, assertion messages, or snapshots. To confirm the right field failed, check violation metadata or cause types rather than printing raw values.

## 10. Null, Blank, Zero, and Missing Values Are Distinct

| Java declaration | Input | Can result in |
| --- | --- | --- |
| `@NotNull String name` | `""` | Passes @NotNull but may violate business rules |
| `@NotBlank String name` | `"   "` | Violates @NotBlank |
| `@Min(1) int retries` | `0` | Violates @Min |
| `@Min(1) Integer retries` | Key absent | Null can pass @Min |
| `@NotNull @Min(1) Integer retries` | Key absent | Violates @NotNull |
| `@NotNull Duration timeout` | `0s` | Non-null; needs positive rule if zero is disallowed |
| `@NotNull URI endpoint` | Relative URI | Passes @NotNull; needs scheme/host rules |

Many numeric constraints such as `@Min` treat null as valid; if the key is required, pair with `@NotNull`.

With primitives, an omitted key may take Java defaults like 0 or false in some binding structures; do not rely on that to distinguish "undeclared" from "explicitly 0." Wrappers like `Integer` make that distinction explicit.

## 11. Inspecting Error Causes Without Coupling to Log Strings

When ApplicationContext startup fails, the framework often wraps causes across multiple layers, such as:

~~~text
BeanCreationException
    |
    +-- ConfigurationPropertiesBindException
            |
            +-- BindException
                    |
                    +-- conversion/validation cause
~~~

This diagram is illustrative; wrapper types and order can vary across versions and bean creation paths.

A helper to traverse the cause chain:

~~~java
static boolean containsCause(
        Throwable error,
        Class<? extends Throwable> expected) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {
        if (expected.isInstance(current)) {
            return true;
        }
    }
    return false;
}
~~~

Using a Spring Boot exception type:

~~~java
import org.springframework.boot.context.properties.ConfigurationPropertiesBindException;

@Test
void bindingErrorIsReportedAsConfigurationPropertiesFailure() {
    runner.withPropertyValues(
        "payment.client.endpoint=https://api.example.invalid",
        "payment.client.timeout=not-a-duration",
        "payment.client.max-retries=3",
        "payment.client.api-key=fake-test-key"
    ).run(context -> {
        Throwable error = context.getStartupFailure();
        assertThat(error).isNotNull();
        assertThat(containsCause(
            error,
            ConfigurationPropertiesBindException.class
        )).isTrue();
    });
}
~~~

Asserting on exception types separates binding failures from completely unrelated errors. To distinguish conversion from validation more strictly, inspect `BindValidationException` or violation details per your version's API.

Avoid asserting on verbatim failure-analysis text. Stack traces, bean names, and wording can change across Boot/Framework upgrades, and error messages might inadvertently include sensitive values.

## 12. Testing Exactly One Error per Test

Do not write a test like this and merely assert context failure:

~~~properties
payment.client.endpoint=
payment.client.timeout=broken
payment.client.max-retries=0
payment.client.api-key=
~~~

This has at least four problems. Binder may stop at Duration conversion, leaving `@Min` and `@NotBlank` untested. Or another error may surface before validation runs.

A better structure:

~~~text
Case A: valid data -> PASS.
Case B: only timeout malformed -> FAIL binding.
Case C: only maxRetries=0 -> FAIL validation.
Case D: only apiKey blank -> FAIL validation.
Case E: only endpoint missing -> FAIL validation.
~~~

This is easy to diagnose and maintain: after editing a constraint, readers know which case guards which contract.

You can add a multi-error integration test to observe overall failure analysis, but never use it as the sole proof for all constraints.

## 13. @DefaultValue Changes Test Expectations

Example record with defaults:

~~~java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        @DefaultValue("3s") Duration timeout,
        @DefaultValue("2") int retries
) {}
~~~

When the source **omits** timeout or retries, Binder applies the declared defaults; missing-property tests should then PASS and assert `3s`/`2`.

Conversely:

~~~properties
batch.timeout=not-a-duration
~~~

is a present-but-malformed value, not replaced automatically with `3s`. Sensible defaults do not swallow configuration mistakes.

When updating the Java contract, update the test matrix:

- Required property: missing must fail.
- Property with safe default: missing must pass using that default.
- Malformed property: must fail.
- Overridden by higher-priority source: must take the selected effective value.

## 14. Nested Objects Need @Valid for Cascaded Validation

A root with a nested endpoint:

~~~java
@Validated
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        @NotNull @Valid Server server
) {
    public record Server(
            @NotBlank String host,
            @Min(1) int port
    ) {}
}
~~~

With `@NotNull Server server` but no `@Valid`, the validator does not descend into host and port. With `@Valid Server server` but no `@NotNull`, a null object is typically not rejected by cascading validation.

A test set should cover:

1. server absent: fails due to `@NotNull`.
2. server with blank host: fails due to `@NotBlank`.
3. server with port 0: fails due to `@Min(1)`.
4. server complete: passes.

Do not place `@Valid` on a nested object with zero constraints and think "all fields are validated"; cascading only enforces declared constraints.

## 15. Testing List Elements

YAML:

~~~yaml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: ""
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

Java:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import java.net.URI;
import java.time.Duration;
import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotEmpty
        List<@NotNull @Valid Endpoint> endpoints
) {
    public record Endpoint(
            @NotBlank String name,
            @NotNull URI url,
            @NotNull Duration timeout
    ) {}
}
~~~

Meaning:

- `@NotEmpty`: List has at least one item.
- `@NotNull` on type argument: items cannot be null.
- `@Valid`: validates fields of each Endpoint.
- `@NotBlank`/`@NotNull` on Endpoint: protects required properties.

Runner with matching registration:

~~~java
private final ApplicationContextRunner routingRunner =
    new ApplicationContextRunner()
        .withConfiguration(AutoConfigurations.of(
            ValidationAutoConfiguration.class))
        .withUserConfiguration(RoutingConfiguration.class);
~~~

Test failure on the second item:

~~~java
@Test
void blankEndpointNameStopsStartup() {
    routingRunner.withPropertyValues(
        "routing.endpoints[0].name=primary",
        "routing.endpoints[0].url=https://primary.example.invalid",
        "routing.endpoints[0].timeout=3s",
        "routing.endpoints[1].name=",
        "routing.endpoints[1].url=https://backup.example.invalid",
        "routing.endpoints[1].timeout=5s"
    ).run(context ->
        assertThat(context).hasFailed()
    );
}
~~~

`RoutingConfiguration` is a `@Configuration` with `@EnableConfigurationProperties(RoutingProperties.class)`. This test is only meaningful when a baseline with two valid endpoints PASSES on the same runner.

## 16. Testing Invalid Map Values

Named Map example:

~~~yaml
clients:
  definitions:
    inventory:
      endpoint: "https://inventory.example.invalid"
      pool-size: 5
    pricing:
      endpoint: "https://pricing.example.invalid"
      pool-size: 0
~~~

Java:

~~~java
@Validated
@ConfigurationProperties(prefix = "clients")
public record ClientsProperties(
        @NotEmpty
        Map<String, @NotNull @Valid Client> definitions
) {
    public record Client(
            @NotNull URI endpoint,
            @Min(1) int poolSize
    ) {}
}
~~~

When `pricing.pool-size=0`, integer binding succeeds, yet nested validation must reject it.

A negative test can supply:

~~~java
clientRunner.withPropertyValues(
    "clients.definitions.pricing.endpoint=https://pricing.example.invalid",
    "clients.definitions.pricing.pool-size=0"
).run(context -> assertThat(context).hasFailed());
~~~

`clientRunner` here is a runner dedicated to `ClientsProperties` with matching bean registration and validation infrastructure. Do not reuse the `PaymentClientProperties` runner and assume Maps are validated.

If `@Valid` is removed from the Map value type, tests stop catching constraints inside Client. This demonstrates why validation must be placed at the **right level**, not only on the Map root.

## 17. Container-Element Constraints

For a List of Strings, `@NotEmpty List<String>` only checks the List is non-empty, not each element.

~~~java
@Validated
@ConfigurationProperties(prefix = "notifications")
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank String> recipients
) {}
~~~

Input:

~~~properties
notifications.recipients[0]=ops@example.invalid
notifications.recipients[1]=
~~~

The second element is rejected by `@NotBlank`.

With Maps, direct constraints on keys/values behave similarly:

~~~java
Map<
    @NotBlank String,
    @NotNull @Min(1) Integer
> retryLimits
~~~

To test keys with special characters, understand Map binding/bracket notation and how keys are normalized prior to validation. Do not assume the validator broke simply because Binder transformed the input key.

## 18. Profile List Replacement Can Cause Missing-Field Errors

Spring Boot follows a key rule: **Lists are not deep-merged by index across sources with different precedence**. When a higher-priority profile redefines a List, the List from the lower source is replaced completely.

Common file:

~~~yaml
# application.yml
routing:
  endpoints:
    - name: "primary"
      url: "https://primary.example.invalid"
      timeout: 3s
    - name: "backup"
      url: "https://backup.example.invalid"
      timeout: 5s
~~~

Dev file:

~~~yaml
# application-dev.yml
routing:
  endpoints:
    - name: "local"
      url: "http://localhost:9090"
~~~

When the dev List wins, the local endpoint lacks a timeout. It **does not inherit 3s** from the item at the same index in the common file.

An integration test with the dev profile and `RoutingProperties` containing `@NotNull Duration timeout` should confirm the context rejects this configuration. Likewise, the backup entry is no longer in the effective List.

**Note:** `ApplicationContextRunner.withPropertyValues(...)` supplies one flat set of test properties and does not automatically recreate **two Config Data PropertySources with different precedence and profiles**. True List replacement tests should model two sources or use a bootstrap/integration fixture loading profile files.

## 19. Map Merging Must Also Be Checked After Binding

Maps generally merge keys/fields across property sources by priority. If the common file has:

~~~yaml
# application.yml
clients:
  definitions:
    pricing:
      endpoint: "https://pricing.example.invalid"
      timeout: 3s
      pool-size: 5
~~~

and the dev file specifies only:

~~~yaml
# application-dev.yml
clients:
  definitions:
    pricing:
      endpoint: "http://localhost:9090"
~~~

the pricing Map entry can take endpoint from dev, and timeout/pool-size from base.

Validation runs on the **final bound object after sources combine**, not on each individual YAML file in isolation. A test expecting failure solely because the dev file omits timeout has wrong expectations if the Map is designed to inherit timeout from base config.

For security-sensitive configuration, clarify which fields may inherit across profiles and which must be explicitly provided per environment.

## 20. Why Is @SpringBootTest Inconvenient for Expected Startup Failures?

A negative test like:

~~~java
@SpringBootTest(properties = {
    "payment.client.max-retries=0"
})
class InvalidConfigurationSpringBootTest {

    @Test
    void shouldFail() {
        // Test method may never execute.
    }
}
~~~

Spring Test normally tries to create the ApplicationContext before running test methods. When startup fails intentionally, JUnit reports a setup error instead of letting the test method assert the expected failure.

For **positive integration tests**, `@SpringBootTest` is great. For **expected failures of a configuration module**, `ApplicationContextRunner` is usually far simpler.

If you want to test the **real bootstrap phase** (file imports, YAML parsing, profiles), spin up a minimal `SpringApplication` inside a test and assert the exception, or use a framework/version-specific test fixture. The goal remains a PASSING JUnit test when startup fails for the right reason.

## 21. Config Data Failures Happen Before Binding

Some failures cannot be reproduced using `withPropertyValues(...)` alone.

For example, a missing required location:

~~~yaml
spring:
  config:
    import: "file:./config/required-settings.properties"
~~~

If the file does not exist, Spring Boot fails during Config Data loading before creating beans.

Contrast with:

~~~yaml
spring:
  config:
    import: "optional:file:./config/local-settings.properties"
~~~

When the location does not exist, `optional:` allows skipping it per supported rules. It does **not**, however, excuse malformed types, invalid syntax in an existing file, or missing required secrets.

Tests should separate:

1. Missing required location -> bootstrap fails.
2. Missing optional location -> bootstrap can proceed.
3. Existing file with invalid YAML/properties syntax -> parse/load failure.
4. Valid file with wrong value type -> binding failure.
5. Valid file violating constraints -> validation failure.

These are five distinct situations even though all might print "Application failed to start."

## 22. A Standalone SpringApplication Bootstrap Test

Concept for catching an early-stage configuration error:

~~~java
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class MissingImportBootstrapTest {

    @SpringBootConfiguration
    static class MinimalApp {}

    @Test
    void missingRequiredImportFails() {
        SpringApplication app =
            new SpringApplication(MinimalApp.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.setDefaultProperties(Map.of(
            "spring.config.import",
            "file:./a-missing-required-test-file.properties"
        ));

        assertThatThrownBy(app::run)
            .isInstanceOf(Exception.class);
    }
}
~~~

This is a **conceptual pattern for a bootstrap test**, not a fully isolated fixture for every project. In real tests:

- Use a dedicated temporary path and confirm the file does not exist.
- Ensure `spring.config.import` is not overridden by other sources.
- Use an application fixture that loads only needed configurations.
- Isolate unintended Config Data/application resources.
- Assert the specific Config Data cause type rather than stopping at generic Exception.
- If startup unexpectedly succeeds, close the context to avoid resource leaks.
- Never connect to production services.

You can use a helper running `SpringApplication` inside `try-with-resources` and assert state using appropriate test APIs.

## 23. Malformed YAML Syntax Requires Reading Real Files

Example of invalid YAML:

~~~yaml
service:
  endpoints: [one, two
~~~

When loaded via Config Data, the parser fails. If a test only uses:

~~~java
runner.withPropertyValues(
    "service.endpoints[0]=one",
    "service.endpoints[1]=two"
)
~~~

you are **not testing the YAML parser**. The runner receives key/value pairs directly.

If the goal is testing the file-loading pipeline, use a YAML fixture or a bootstrap test loading that resource.

Avoid turning one generic negative test into a combined YAML, Binder, validation, and SpringApplication test. Layering makes results faster and easier to diagnose.

## 24. Unknown Properties Are Not Errors by Default

Typo example:

~~~yaml
payment:
  client:
    max-retreis: 3
~~~

instead of:

~~~yaml
payment:
  client:
    max-retries: 3
~~~

If typed properties have no `maxRetreis` field, Binder ignores the unknown field under `@ConfigurationProperties` defaults. The outcome depends on whether the target field has defaults or validation.

Strict handling can be requested:

~~~java
@ConfigurationProperties(
    prefix = "payment.client",
    ignoreUnknownFields = false
)
public record PaymentClientProperties(
        int maxRetries
) {}
~~~

However, strict unknown-field handling must be tested against **real structures and sources**, because other modules may share prefixes or unbound keys may belong to application extensions.

Do not treat `ignoreUnknownFields=false` as a guarantee that every typo in every file will be caught. Schema design and prefix-targeted tests remain necessary.

## 25. Conditionally Required Properties by Feature Flag

A feature might be disabled without needing an endpoint:

~~~yaml
billing:
  enabled: false
~~~

When enabled:

~~~yaml
billing:
  enabled: true
  endpoint: "https://billing.example.invalid"
~~~

To check conditional requirements, a record can use `@AssertTrue`:

~~~java
import jakarta.validation.constraints.AssertTrue;
import java.net.URI;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "billing")
public record BillingProperties(
        boolean enabled,
        URI endpoint
) {
    @AssertTrue(message = "endpoint is required when enabled")
    public boolean isEndpointPresentWhenEnabled() {
        return !enabled || endpoint != null;
    }
}
~~~

Negative tests must prove:

- `enabled=true` and endpoint missing -> context fails.
- `enabled=false` and endpoint missing -> context passes.
- `enabled=true` and endpoint present -> passes.

Note: `URI.create("relative-path")` is a valid Java URI, yet not an absolute HTTP endpoint. To restrict scheme/host, add corresponding validation.

## 26. Conditional Client Creation Does Not Skip Properties Validation

Example:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "billing",
    name = "enabled",
    havingValue = "true"
)
BillingClient billingClient(BillingProperties properties) {
    return new BillingClient(properties.endpoint());
}
~~~

If `BillingProperties` is always registered, it is still bound and validated even when the BillingClient bean is skipped by the condition. Two things:

- Registration/validation of BillingProperties.
- Conditional creation of BillingClient.

are separate responsibilities. If disabling a feature omits valid secrets/endpoints, design conditional constraints or matching registration boundaries and test both enabled and disabled states.

A test asserting only that the `BillingClient` bean is absent does not prove required configuration is validated properly when the feature is active.

## 27. Enforcing Positive Durations Is a Separate Rule

`@NotNull Duration timeout` is insufficient if the application forbids zero or negative durations.

Example:

~~~java
import jakarta.validation.constraints.AssertTrue;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Duration timeout
) {
    @AssertTrue(message = "timeout must be positive")
    public boolean isTimeoutPositive() {
        return timeout != null
            && timeout.compareTo(Duration.ZERO) > 0;
    }
}
~~~

Test matrix:

~~~text
timeout=3s             -> Pass
timeout=0s             -> Fail validation
timeout=-1s            -> Fail validation
timeout=not-a-duration -> Fail conversion
timeout absent         -> Fail @NotNull
~~~

Do not blindly place `@Min(1)` on `Duration` if the validator does not support that type. For business rules, class-level validation or custom constraints are clearer.

## 28. Isolating Externalized Property Sources in CI

Sources that can make tests behave differently between local and CI:

- OS environment variables.
- Java system properties.
- `application-*.yml` files.
- `@TestPropertySource` and `@SpringBootTest(properties=...)`.
- `@DynamicPropertySource` from Testcontainers.
- Mounted secret managers or config directories.
- Profiles activated by the test runner.
- Command-line parameters or custom PropertySources.

A negative test expecting "missing token must fail" can unexpectedly pass if CI already exports that key via an environment variable.

Reduce risk:

1. Use module/test-specific key namespaces.
2. Build minimal contexts and control inputs.
3. Avoid reading production resources/secrets.
4. For integration tests, declare profiles and locations explicitly.
5. When testing absence, use fixtures that cannot be supplied accidentally by the host machine.
6. Never print raw Environment or full secret-bearing beans.
7. When testing precedence, inspect only controlled dummy sources and values.

## 29. Tests Must Not Cause Side Effects

A full application context may instantiate beans **before** a properties bean is rejected by validation:

- Opening database connections.
- Connecting to message brokers.
- Sending HTTP requests.
- Registering scheduled jobs.
- Calling secret managers.
- Exporting telemetry to external endpoints.
- Writing files or spawning threads.

For negative configuration tests, use `ApplicationContextRunner` and load only relevant configurations. If full bootstrap is required:

- Disable or mock external integrations.
- Use test databases or Testcontainers, never production.
- Use fake secrets.
- Close the context if startup unexpectedly succeeds.
- Release temporary files and resources.
- Keep tests safe for parallel execution.

A test expecting startup failure must never alter real data simply because the framework created an earlier bean.

## 30. False-Positive Test Pitfalls

**False pass 1 — Context fails from missing bean.** Without `@EnableConfigurationProperties`, it fails on injection rather than validation.

**False pass 2 — Context fails because DB is unavailable.** The test does not prove `@Min` works.

**False pass 3 — Invalid input overridden by higher-priority source.** The test may behave unexpectedly because Binder received a different value.

**False pass 4 — Testing only wrong type instead of out-of-range.** `retries=abc` fails conversion and does not prove `@Min(1)`.

**False pass 5 — Missing validation provider.** Constraints exist in source code but are never enforced in the test context.

**False pass 6 — @Validated present, nested @Valid missing.** Map/List has entries, yet inner fields go unchecked.

**False pass 7 — Intentionally failing @SpringBootTest in setup.** JUnit turns red rather than a negative assertion passing.

**False pass 8 — Testing YAML files using withPropertyValues.** Never tested the YAML parser or Config Data.

**False pass 9 — Asserting full exception text.** Brittle across framework upgrades even when behavior stays right.

**False pass 10 — Using real secrets to reproduce errors.** Increases risk of leaking sensitive data into logs/artifacts.

These are why having a passing baseline, categorizing errors, and keeping test scope small matter so much.

## 31. Complete Test Matrix Table

| Scenario | endpoint | timeout | retries | api-key | Expected |
| --- | --- | --- | --- | --- | --- |
| Valid | Valid URI | 3s | 3 | fake | Startup passes |
| Missing endpoint | Absent | 3s | 3 | fake | Fails validation |
| Missing timeout | Valid URI | Absent | 3 | fake | Fails validation |
| Malformed timeout | Valid URI | bad | 3 | fake | Fails binding |
| Retries 0 | Valid URI | 3s | 0 | fake | Fails validation |
| Retries 6 | Valid URI | 3s | 6 | fake | Fails validation |
| Non-numeric retries | Valid URI | 3s | many | fake | Fails binding |
| Missing token | Valid URI | 3s | 3 | Absent | Fails validation |
| Blank token | Valid URI | 3s | 3 | spaces | Fails validation |
| Unknown key | Valid URI | 3s | 3 | fake | Depends on strict policy |

For each row, keep all non-target fields valid. When adding `@DefaultValue` or changing business rules, update the matrix to match the **new contract** rather than tweaking assertions just to make tests green.

## 32. Exercise 1: Batch Configuration

Prompt: a service uses configuration:

~~~yaml
batch:
  enabled: true
  max-threads: 4
  polling-interval: 5s
  queue-name: "orders"
~~~

Requirements:

- maxThreads between 1 and 16.
- pollingInterval present and positive.
- When enabled=true, queueName is non-blank.
- When enabled=false, queueName may be absent.

Record:

~~~java
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "batch")
public record BatchProperties(
        boolean enabled,
        @Min(1) @Max(16) int maxThreads,
        @NotNull Duration pollingInterval,
        String queueName
) {
    @AssertTrue(message = "queue-name is required when enabled")
    public boolean isQueueNameValid() {
        return !enabled ||
            (queueName != null && !queueName.isBlank());
    }

    @AssertTrue(message = "polling-interval must be positive")
    public boolean isPollingIntervalPositive() {
        return pollingInterval != null &&
            pollingInterval.compareTo(Duration.ZERO) > 0;
    }
}
~~~

Set up a runner with validation infrastructure, register BatchProperties, and verify:

1. Valid: passes.
2. `max-threads=0`: fails.
3. `max-threads=17`: fails.
4. `max-threads=abc`: conversion fails.
5. `polling-interval=0s`: validation fails.
6. `polling-interval=not-a-duration`: conversion fails.
7. Enabled true, blank queueName: validation fails.
8. Enabled false, missing queueName: passes if other fields are valid.

Question: if `@NotNull Duration pollingInterval` is changed to `@DefaultValue("5s")`, what should a missing-pollingInterval test expect? Answer: pass with the valid default, provided no other constraint requires explicit input.

## 33. Exercise 2: Map of Clients and Cascaded Validation

YAML:

~~~yaml
integrations:
  clients:
    inventory:
      endpoint: "https://inventory.example.invalid"
      max-connections: 5
    pricing:
      endpoint: "https://pricing.example.invalid"
      max-connections: 0
~~~

Properties:

~~~java
@Validated
@ConfigurationProperties(prefix = "integrations")
public record IntegrationProperties(
        @NotEmpty
        Map<String, @NotNull @Valid Client> clients
) {
    public record Client(
            @NotNull URI endpoint,
            @Min(1) int maxConnections
    ) {}
}
~~~

Tests:

- Valid inventory: passes.
- Pricing maxConnections 0: fails validation.
- Empty Map: fails.
- Missing endpoint in an entry: fails validation.
- Non-numeric maxConnections: fails conversion.
- Remove `@Valid` from the Map value and rerun to observe why nested validation needs cascading.

Do not merely test that the Map exists. The goal is confirming **values inside entries** are validated.

## 34. Exercise 3: Required Configuration Files and Secrets

The application uses:

~~~yaml
spring:
  config:
    import: "configtree:/run/secrets/orders/"
~~~

And a typed property:

~~~java
@Validated
@ConfigurationProperties(prefix = "orders")
public record OrdersProperties(
        @NotBlank String apiToken
) {}
~~~

Test fixtures must distinguish:

1. Directory does not exist and import is required: bootstrap fails.
2. Directory exists but token file is missing: validation fails.
3. Empty token file: validation fails.
4. File contains dummy token: startup passes.
5. `optional:configtree:` import with absent directory: bootstrap continues, yet token remains required if the module is enabled.
6. Secret supplied by another higher-priority source: check effective value from actual configuration rather than assuming file presence wins.

Never use production tokens. Tests must prepare directories/files before Config Data runs and clean up fixtures afterward.

## 35. Project Testing Implementation Workflow

A repeatable workflow:

**Step 1:** List critical configuration groups and distinguish required/default/optional properties.

**Step 2:** Define typed configuration via `@ConfigurationProperties`. Apply `@Validated`, appropriate constraints, and `@Valid` on nested objects.

**Step 3:** Register properties types with `@EnableConfigurationProperties` or scanning, without treating them like service `@Component` beans.

**Step 4:** Build a minimal `ApplicationContextRunner` for the configuration group.

**Step 5:** Write a passing baseline and assert bound values.

**Step 6:** Write negative cases: missing, blank, wrong type, out-of-range, nested missing fields.

**Step 7:** For key cases, assert cause types in the cause chain to avoid false positives.

**Step 8:** Write separate integration tests for profile-specific Config Data, import locations, and YAML parsing.

**Step 9:** Isolate environment/test data to guarantee zero real secrets or side effects.

**Step 10:** Run tests in CI on the project's JDK and Spring Boot versions; never disable validation just to turn a build green.

**Step 11:** When changing schemas, defaults, or constraints, update the test matrix as part of the configuration contract change.

**Step 12:** In staging, verify the app with real deployment configuration and health/readiness checks; do not substitute negative unit tests for smoke tests.

## 36. Summary Checklist

- [ ] A valid baseline starts successfully.
- [ ] Properties types are properly registered and carry `@Validated` where required.
- [ ] A compatible Bean Validation provider is present.
- [ ] Required fields have matching constraints.
- [ ] Wrapper/null/default semantics are accounted for.
- [ ] Conversion errors are tested separately from validation errors.
- [ ] `@Min`/`@Max` are tested with type-valid but out-of-range numbers.
- [ ] Nested Lists/Maps have `@Valid` and constraints at the right level.
- [ ] Each negative case triggers one intentional primary failure.
- [ ] Cause types are checked where needed to confirm the right failure reason.
- [ ] Brittle verbatim stack trace assertions are avoided.
- [ ] Config Data/profile tests exist when configuration spans multiple sources.
- [ ] `withPropertyValues` is not mistaken for testing the YAML parser.
- [ ] Misconfigured full `@SpringBootTest` setups are not misused as vague expected-failure tests.
- [ ] No production secrets or live external services are used.
- [ ] Startup failures are verified while the JUnit test PASSES.
- [ ] Tests run reliably locally and in CI without leaking resources.

## 37. Key Takeaways

**Testing invalid configuration means testing Spring Boot's startup contract.** A reliable negative test proves the application **rejects bad inputs for the right reason**. `ApplicationContextRunner` excels at binding and Bean Validation; `@SpringBootTest` fits positive integration better; and YAML parsing, profile-specific Config Data, and import locations may require real bootstrap tests.

Distinguish **binding/conversion failures**, **validation failures**, **missing properties**, **bean registration failures**, and **Config Data bootstrap failures**. Writing a valid baseline, purposeful single-fault invalid cases, sufficiently specific assertions, and isolated fixtures catches misconfigurations before deployment—preventing services from running half-configured with dangerous settings.

**Short formula:** valid configuration must start cleanly; invalid configuration must fail startup in a controlled way; tests must prove the exact cause without leaking secrets.
