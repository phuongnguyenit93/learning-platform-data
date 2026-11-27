# Configuration Validation and Detecting Invalid Values

In a Spring Cloud application, configuration can arrive from JAR files, external files, environment variables, command-line arguments, or Config Server. Just because a value loads into `Environment` does not mean it is valid from a business standpoint. For example, `inventory.timeout=0ms` converts cleanly to a valid `Duration`, yet violates service-call policies; `inventory.max-attempts=-2` is a valid integer, yet not a valid attempt count.

**Configuration validation** catches these issues right at the startup boundary or during binding, before they cause hard-to-diagnose failures while handling requests. In **SPRING_CLOUD_CORE**, this capability is essential when working with `@ConfigurationProperties`, Spring Cloud Config, discovery, service registries, inter-service communication, and refresh scope.

This lesson belongs to the **Typed Configuration** chapter and focuses on validating typed configuration, distinguishing conversion errors from validation errors, testing, and handling invalid remote configuration in operations.

## 1. Learning Objectives

After this lesson, you will be able to:

- Explain the differences among missing properties, type conversion errors, and validation errors.
- Use Bean Validation with `@ConfigurationProperties`.
- Select appropriate constraints such as `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Positive`, `@Pattern`, and `@Valid`.
- Validate nested configuration, collection elements, and cross-property relationships.
- Understand the roles of `@Validated`, `@ConfigurationPropertiesScan`, and `@EnableConfigurationProperties`.
- Design clear defaults, required fields, and optional fields.
- Catch typos or unbound properties using appropriate options.
- Test both valid and invalid configurations.
- Handle invalid configuration from Config Server or external sources with a fail-fast policy.
- Account for validation when configuration refreshes in a running application.

## 2. Why Is Configuration Validation Needed?

Suppose `checkout-service` calls `inventory-service` using three properties:

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
```

Without validation, the following values could still be loaded or converted:

```yaml
inventory:
  base-url: ""
  timeout: 0ms
  max-attempts: -3
```

Some values cause errors during HTTP calls; others render retries meaningless or cause misbehavior without any startup error.

Configuration validation provides three benefits:

1. **Early detection:** errors surface when binding configuration instead of waiting until a request uses the value.
2. **Clear diagnostics:** errors pinpoint the exact property and violated constraint.
3. **Contract protection:** each service defines the bounds and cross-field invariants it accepts.

Validation does not replace connectivity checks to external services. A syntactically valid URI can still point to a nonexistent host; validation checks data shape and rules, while health checks or integration tests verify actual reachability.

## 3. Three Error Categories to Distinguish

| Error Type | Example | When Detected | How to Handle |
| --- | --- | --- | --- |
| Missing required property | No `inventory.base-url` | During binding or validation | Use constraints like `@NotNull`/`@NotBlank`; avoid fake defaults |
| Type conversion error | `inventory.timeout=abc` when field is `Duration` | During binding/conversion | Check format and data type |
| Semantic validation error | `inventory.timeout=0ms`, `max-attempts=-1` | After values have been bound | Use Bean Validation or domain validators |

### 3.1. Conversion Errors Are Not Validation Errors

Example:

```yaml
inventory:
  timeout: abc
  max-attempts: three
```

If fields are declared as `Duration` and `int`, the Binder cannot convert these strings to target types. Binding fails before Bean Validation can check rules like positive timeouts.

Conversely:

```yaml
inventory:
  timeout: 0ms
  max-attempts: 0
```

Both values convert cleanly to `Duration` and `int`, yet violate business rules. This is where validation helps.

### 3.2. Missing Properties and Default Values

For reference types like `URI`, `Duration`, or `String`, an omitted property becomes `null` if there is no default. For primitive types like `int` or `boolean`, Java defaults are `0` and `false` respectively.

This affects constraint selection:

- `@NotNull` suits reference types.
- `@NotBlank` suits required strings with meaningful content.
- `@Min(1)` can catch an `int` left at `0` when omitted.
- If `false` is a valid setting, do not use validation to treat it as "missing".

Decide explicitly which properties are required, which have defaults, and which are optional.

## 4. Bean Validation for @ConfigurationProperties

Spring Boot integrates Bean Validation into `@ConfigurationProperties` binding. For Spring Boot 3 and above, the validation API uses the `jakarta.validation` namespace.

To use it, add a Bean Validation implementation to the classpath. In Spring Boot projects, the standard starter is:

**Maven**

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

**Gradle**

```groovy
implementation 'org.springframework.boot:spring-boot-starter-validation'
```

Let the Spring Boot BOM manage the starter version rather than pinning an independent version if the project already uses Boot dependency management.

### 4.1. Commonly Used Constraints

| Annotation | Condition | Suitable Example |
| --- | --- | --- |
| `@NotNull` | Value must not be `null` | URI, Duration, config object |
| `@NotBlank` | String must not be null, empty, or whitespace-only | Service name, username |
| `@NotEmpty` | String/collection/map must not be null or empty | List of endpoints or allowed regions |
| `@Min(n)` | Number must be greater than or equal to `n` | Minimum attempt count |
| `@Max(n)` | Number must be less than or equal to `n` | Connection limit |
| `@Positive` | Number must be greater than 0 | Port, count, multiplier |
| `@PositiveOrZero` | Number must be greater than or equal to 0 | Extra retry count |
| `@Pattern` | String must match a regular expression | Region code, internal profile name |
| `@Email` | String matches email format per validator | Contact email |
| `@Valid` | Cascade validation into nested object | Nested config group |
| `@AssertTrue` | Boolean expression must be true | Multi-field relationship check |

Each constraint has distinct semantics. For example, `@NotEmpty` does not replace `@NotBlank`: `"   "` is non-empty yet lacks meaningful content.

### 4.2. Enabling Validation with @Validated

Example:

```java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "checkout")
public class CheckoutProperties {

    @NotBlank
    private String serviceName;

    @Min(1)
    @Max(100)
    private int maxItems;

    // getters and setters
}
```

`@Validated` instructs Spring to validate the configuration bean. Constraints declare the contract for each property. When values fail constraints, creating the configuration bean fails and the application typically refuses to start.

To register the bean, use `@ConfigurationPropertiesScan` on the application class or `@EnableConfigurationProperties(CheckoutProperties.class)` on a configuration class.

## 5. Complete Example: Typed Inventory Configuration

A client calling `inventory-service` needs a URL, timeout, attempt count, retry bounds, and a list of supported regions.

### 5.1. Declaring an Immutable Record

```java
package com.example.checkout.config;

import java.net.URI;
import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "inventory")
public record InventoryProperties(
        @NotNull URI baseUrl,
        @NotNull Duration timeout,
        @Min(1) @Max(10) int maxAttempts,
        @NotNull @Valid Retry retry,
        @NotEmpty List<@NotBlank String> allowedRegions) {

    @AssertTrue(message = "inventory.base-url must be an absolute HTTP(S) URI")
    public boolean isBaseUrlHttp() {
        if (baseUrl == null) {
            return true;
        }
        String scheme = baseUrl.getScheme();
        return baseUrl.isAbsolute()
                && baseUrl.getHost() != null
                && ("http".equalsIgnoreCase(scheme)
                    || "https".equalsIgnoreCase(scheme));
    }

    @AssertTrue(message = "inventory.timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout == null || (!timeout.isNegative() && !timeout.isZero());
    }

    @AssertTrue(message = "inventory.retry.min-attempts must not exceed max-attempts")
    public boolean isRetryRangeValid() {
        return retry == null || retry.minAttempts() <= retry.maxAttempts();
    }

    public record Retry(
            @Min(0) int minAttempts,
            @Min(1) @Max(10) int maxAttempts) {
    }
}
```

This example uses a Java record for an immutable configuration object. With a record's single constructor, modern Spring Boot supports constructor binding out of the box without needing setters for every field. With regular classes, use constructor binding or JavaBean binding depending on your design.

Meaning of the constraints in this example:

- `baseUrl` must be non-null; `isBaseUrlHttp()` checks for an absolute URI with an HTTP/HTTPS scheme.
- `timeout` must be non-null and greater than 0.
- `maxAttempts` must be between 1 and 10.
- `retry` is a required object and `@Valid` activates validation on its inner fields.
- `allowedRegions` must not be empty; every element must be non-blank.
- `isRetryRangeValid()` checks the relationship between two fields in the nested object.

The `@AssertTrue` methods return `true` when a referenced field is null (letting `@NotNull` report the missing field) or when the semantic condition holds. This avoids noisy secondary errors when a required value is absent.

### 5.2. Enabling Configuration Scanning

```java
package com.example.checkout;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class CheckoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckoutApplication.class, args);
    }
}
```

`@ConfigurationPropertiesScan` finds classes annotated with `@ConfigurationProperties` in the scan scope. An alternative is explicit declaration:

```java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(InventoryProperties.class)
class InventoryConfiguration {
}
```

Do not use both approaches for the same configuration bean if that causes duplicate registration.

### 5.3. Valid application.yaml

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
    - ap-southeast-2
```

Spring Boot converts `800ms` to `Duration`, the URI to `java.net.URI`, and binds lists and nested objects. After binding, Bean Validation checks all constraints.

### 5.4. Invalid Configuration Examples

**Missing URL:**

```yaml
inventory:
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
```

`baseUrl` is `null`, violating `@NotNull`.

**Zero timeout:**

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 0ms
  max-attempts: 3
  retry:
    min-attempts: 1
    max-attempts: 4
  allowed-regions:
    - ap-southeast-1
```

The value converts to `Duration` successfully, yet violates `isTimeoutPositive()`.

**Invalid retry range:**

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 800ms
  max-attempts: 3
  retry:
    min-attempts: 5
    max-attempts: 2
  allowed-regions:
    - ap-southeast-1
```

Each field individually satisfies its numeric constraints, yet `minAttempts <= maxAttempts` fails. This is why object-level or class-level validation is needed.

## 6. Validation for Nested Configuration and Collections

### 6.1. @Valid Is Required for Nested Objects

Put `@Valid` on the object field so Bean Validation descends into the child object's constraints:

```java
public record Retry(
        @Min(0) int minAttempts,
        @Min(1) int maxAttempts) {
}

public record InventoryProperties(
        @NotNull @Valid Retry retry) {
}
```

Without `@Valid`, constraints placed on `Retry` may not run when validating from `InventoryProperties`. `@NotNull` and `@Valid` do two separate jobs: one requires the object to exist, while the other activates inner validation.

### 6.2. Validating Collection Elements

Bean Validation supports constraints on collection elements:

```java
@NotEmpty
List<@NotBlank String> allowedRegions
```

This checks both the collection itself and each element:

```yaml
inventory:
  allowed-regions:
    - ap-southeast-1
    - ""
```

The collection is non-empty, yet contains an empty element, so validation fails. Putting only `@NotEmpty` on the list would miss empty elements.

### 6.3. Validating Cross-Field Relationships

Some rules cannot be expressed with single-field constraints:

- `min-pool-size` must not exceed `max-pool-size`.
- `connect-timeout` must be less than `read-timeout`.
- If TLS is enabled, a truststore must be configured.
- If retry is enabled, attempt count must exceed 0.

For simple rules, `@AssertTrue` on a method works well. For complex or reusable rules, build a custom class-level constraint (`@Constraint`) and `ConstraintValidator` to get reuse, clear error messages, and isolated unit tests.

Avoid cramming all business rules into one giant `@AssertTrue` method. As rules grow, extract named constraints reflecting domain intent so errors stay readable and maintainable.

## 7. Choosing Default Values and Required Fields

Validation only helps when the configuration contract is clear. Before adding annotations, decide which properties are mandatory and which may use defaults.

| Property Category | Example | Design Approach |
| --- | --- | --- |
| Required | Registry URL, tenant name, credential reference | Avoid fake defaults; use `@NotNull`/`@NotBlank` |
| Safe default | Internal timeout, small batch size | Declare intentional defaults and still validate bounds |
| Optional | Proxy URL, secondary feature flag | Allow `null` or a suitable default |
| Dependent on another property | Truststore when TLS is enabled | Enforce via cross-field validation |

### 7.1. Defaults in YAML

```yaml
inventory:
  timeout: 2s
  max-attempts: 3
```

When defaults live in configuration files, all environments share a baseline and higher-precedence sources can override them.

### 7.2. Defaults in Java

With JavaBean binding, initialize fields directly:

```java
@ConfigurationProperties("checkout")
@Validated
public class CheckoutProperties {

    @Min(1)
    private int maxItems = 20;

    public int getMaxItems() {
        return maxItems;
    }

    public void setMaxItems(int maxItems) {
        this.maxItems = maxItems;
    }
}
```

If the property is absent, `20` is preserved. If config sets `0`, validation catches the error.

With constructor-bound records, use Spring Boot's default value support for constructor parameters, or supply defaults in the constructor/configuration design matching your Boot version. Check the exact API for your release train rather than copying annotations across Boot generations.

### 7.3. Never Hide Required Config Behind Fake Defaults

Anti-pattern to avoid:

```java
String configServer = environment.getProperty(
        "spring.cloud.config.uri", "http://localhost:8888");
```

for a production application where Config Server is mandatory. Defaulting to `localhost` can let the application boot with the wrong configuration source. When critical properties are missing, failing fast with a clear message is safer.

## 8. Catching Typos and Unbound Properties

A common mistake is misspelling a property name:

```yaml
inventory:
  max-attemp: 3
```

while the configuration class declares `maxAttempts`. If unknown properties are ignored, the application may stay at `0` and only fail via `@Min(1)`, or worse, silently run with an unsafe default.

### 8.1. ignoreUnknownFields

`@ConfigurationProperties` has an `ignoreUnknownFields` attribute that defaults to `true`. Setting it to `false` causes unmapped properties under the prefix to fail binding.

```java
@ConfigurationProperties(
        prefix = "inventory",
        ignoreUnknownFields = false)
@Validated
public record InventoryProperties(
        @NotNull URI baseUrl,
        @Min(1) int maxAttempts) {
}
```

This option helps for groups with strict schemas. However, verify your YAML structure and prefixes so keys intentionally consumed by another component are not flagged as errors on this bean.

### 8.2. ignoreInvalidFields

`ignoreInvalidFields` defaults to `false`. Setting it to `true` lets certain invalid binding errors be skipped instead of halting startup.

Avoid enabling this for critical settings just to force startup. A malformed timeout or unconvertible retry count should usually fail startup, since falling back to unexpected defaults can cause unsafe runtime behavior.

### 8.3. Unknown Properties vs. Invalid Properties

| Scenario | Classification |
| --- | --- |
| `inventory.max-attemp` has no matching field | Unknown property |
| `inventory.max-attempts=three` while field is `int` | Invalid conversion |
| `inventory.max-attempts=0` with `@Min(1)` | Validation failure |
| `inventory.timeout` omitted with `@NotNull` | Missing/validation failure |

Do not reach for a single flag to solve all three categories. Identify the exact error type from Binder and validation messages.

## 9. Validation with Remote Configuration

In Spring Cloud applications, configuration can come from Spring Cloud Config, Consul Config, or custom sources. Once loaded into Environment and bound into `@ConfigurationProperties`, validation applies just as it does for local configuration.

Suppose Config Server returns:

```yaml
inventory:
  base-url: https://inventory.internal
  timeout: 0ms
  max-attempts: 3
```

If `timeout` is invalid, the application fails while initializing the configuration bean. A successful HTTP response from Config Server only proves the source returned data; it does not prove the data satisfies the service contract.

### 9.1. Optional Import Does Not Bypass Validation

```yaml
spring:
  config:
    import: optional:configserver:http://config-server:8888
```

`optional:` governs behavior when the Config Server source cannot be loaded via Config Data. If the source loads successfully yet contains invalid values, configuration bean validation still fails startup.

These are two separate decisions:

- **Is the source available?** Governed by import, fail-fast, and retry.
- **Is the data valid?** Governed by binding, conversion, and validation.

### 9.2. Configuration Contracts Across Services

If Config Server shares a repository across multiple services, separate prefixes and profiles clearly:

```yaml
checkout:
  timeout: 2s

inventory:
  timeout: 800ms
```

Each service binds only the configuration it owns. When schemas evolve, verify all consuming services; a renamed property or changed type can break binding on older service versions.

### 9.3. Fail-Fast Deployment

For mandatory settings such as service URLs, credential references, timeouts, and retry policies, allow startup to fail on invalid data. This prevents orchestrators from marking misconfigured instances Ready.

For optional settings, provide safe defaults and document missing-value behavior. Never use `optional:` or `ignoreInvalidFields=true` to mask schema errors.

## 10. Validation and Runtime Refresh

Validation normally runs when `@ConfigurationProperties` binds during context startup. When configuration changes after startup, distinguish four steps:

1. The property source changed in `Environment`.
2. The configuration bean was rebound or the refresh-scoped target was recreated.
3. Validation ran on the new object.
4. Components consuming the new configuration transitioned safely to the new state.

`@RefreshScope` does not detect changes from Config Server or external files automatically. A supported refresh trigger—such as an endpoint/event or Spring Cloud Bus for multiple instances—is required.

### 10.1. Refreshing a Configuration Bean

If a `@ConfigurationProperties` bean is managed via refresh/rebind, new values must be bound and checked against validation constraints. With `@RefreshScope`, a new target is created when the proxy is accessed after scope invalidation; creating that new target can fail if the new configuration is invalid.

Do not assume a failed refresh always rolls back the entire Environment to the prior version. Check your Spring Cloud release's behavior, design your deployment workflow, and keep a configuration-source rollback plan ready.

### 10.2. Updating Configuration Across Multiple Replicas

In a multi-instance cluster:

- One instance may receive a refresh before another.
- One instance may bind successfully while another fails due to differing profiles or sources.
- If new configuration is invalid, readiness and metrics must reflect the unhealthy state.
- Have a rollback or source-fix workflow before continuing rollout.

For values impacting service communication—timeouts, TLS, registry endpoints, or retry policies—test updated config on staging before rolling out to all replicas.

## 11. Testing Validation

A solid test suite covers valid config, missing properties, type mismatches, out-of-range values, nested objects, and cross-field rules.

### 11.1. ApplicationContextRunner

`ApplicationContextRunner` creates a small context with isolated properties for each test:

```java
class InventoryPropertiesTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(InventoryProperties.class)
    static class TestConfiguration {
    }

    @Test
    void bindsValidProperties() {
        contextRunner
                .withPropertyValues(
                        "inventory.base-url=https://inventory.internal",
                        "inventory.timeout=800ms",
                        "inventory.max-attempts=3",
                        "inventory.retry.min-attempts=1",
                        "inventory.retry.max-attempts=4",
                        "inventory.allowed-regions[0]=ap-southeast-1")
                .run(context -> {
                    assertThat(context).hasNotFailed();

                    InventoryProperties properties =
                            context.getBean(InventoryProperties.class);
                    assertThat(properties.timeout())
                            .isEqualTo(Duration.ofMillis(800));
                    assertThat(properties.maxAttempts()).isEqualTo(3);
                });
    }
}
```

This test exercises binding and validation without starting a web server or connecting to a real registry.

### 11.2. Invalid Configuration Must Fail Context Startup

```java
@Test
void rejectsZeroTimeout() {
    contextRunner
            .withPropertyValues(
                    "inventory.base-url=https://inventory.internal",
                    "inventory.timeout=0ms",
                    "inventory.max-attempts=3",
                    "inventory.retry.min-attempts=1",
                    "inventory.retry.max-attempts=4",
                    "inventory.allowed-regions[0]=ap-southeast-1")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("inventory.timeout");
            });
}
```

Exact error formatting varies across Spring Boot and validation provider versions. For stable tests, verify that the context failed and the error mentions the expected property/constraint rather than asserting entire stack traces.

### 11.3. Testing Conversion Errors

```java
@Test
void rejectsInvalidDurationFormat() {
    contextRunner
            .withPropertyValues(
                    "inventory.base-url=https://inventory.internal",
                    "inventory.timeout=not-a-duration",
                    "inventory.max-attempts=3",
                    "inventory.retry.min-attempts=1",
                    "inventory.retry.max-attempts=4",
                    "inventory.allowed-regions[0]=ap-southeast-1")
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                        .hasStackTraceContaining("inventory.timeout");
            });
}
```

This test verifies a conversion error. It differs from `timeout=0ms`, which is a validation error occurring after conversion succeeds.

### 11.4. Testing Nested Objects

Setting `inventory.retry.max-attempts=0` must fail validation because of `@Min(1)` on the nested object. This test catches forgetting `@Valid` on the `retry` field.

Setting `inventory.retry.min-attempts=5` and `inventory.retry.max-attempts=2` must fail cross-field validation even though each number alone is valid.

### 11.5. Testing Validation Standalone

To test constraints in isolation, use Jakarta Validator:

```java
Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();

Set<ConstraintViolation<InventoryProperties>> violations =
        validator.validate(properties);

assertThat(violations).isNotEmpty();
```

Standalone tests construct the input object directly. They verify Bean Validation rules, not whether Spring Boot's Binder converts YAML/environment properties properly; keep context tests for the real binding path.

## 12. Reading and Handling Error Messages

A validation failure typically identifies:

- Which configuration bean failed to create.
- Which property path violated a rule.
- Which constraint or message failed.
- That binding/validation failed during startup.

Illustrative message:

```text
Binding to target InventoryProperties failed:
  Property: inventory.timeout
  Value: 0ms
  Reason: inventory.timeout must be greater than zero
```

This is an illustrative representation, not a guaranteed log format across every Boot version. Actual exceptions may wrap `ConfigurationPropertiesBindException`, `BindException`, or validation provider exceptions.

### 12.1. Layer-by-Layer Analysis

| Layer | Question |
| --- | --- |
| Source | Did the property come from a file, env var, or Config Server? |
| Binding | Did the key map to the expected field? |
| Conversion | Could the string convert to URI, Duration, int, or DataSize? |
| Validation | Did the bound value satisfy constraints? |
| Initialization | Was the configuration bean registered and constructed properly? |
| Operations | Is this replica using the intended profile and config source? |

Never fix a validation failure by immediately disabling validation. First identify whether the root cause is the data source, key name, conversion, or domain contract.

### 12.2. Actuator and Configuration Observability

Spring Boot Actuator can aid diagnostics via endpoints like `configprops` and `env`, depending on dependencies and exposure settings. They reveal bound configuration and property sources.

These endpoints can expose internal URLs, usernames, or sensitive data if masking/sanitization is misconfigured. Expose them only when needed, protect them with authentication/authorization, and never dump full configs into logs.

## 13. Custom Validation

Standard constraints cover most needs. When a rule must be reused across multiple configuration classes, create a custom constraint.

Design steps:

1. Create an annotation `@HttpEndpoint`.
2. Annotate it with `@Constraint(validatedBy = HttpEndpointValidator.class)`.
3. Implement `ConstraintValidator<HttpEndpoint, URI>`.
4. Check for an absolute URI, allowed hosts, and allowed schemes.
5. Return error messages free of sensitive values.

Custom constraints fit well when a rule has a clear domain name and multiple call sites. For a single simple condition, `@AssertTrue` or standard constraints are usually easier to follow.

### 13.1. Cross-Field Validators

For rules such as `connectTimeout < readTimeout`, define a class-level annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = TimeoutRangeValidator.class)
public @interface ValidTimeoutRange {
    String message() default "connect-timeout must be less than read-timeout";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
```

The validator reads both fields and attaches a violation to the appropriate property. When writing custom validators, handle `null` deliberately so `@NotNull` stays responsible for missing required values.

Never write a custom validator that makes network calls to verify endpoint reachability. Configuration validation must be fast, deterministic, and independent of external services; connectivity checks belong in health checks or integration tests.

## 14. Common Design Mistakes

| Practice | Consequence | Fix |
| --- | --- | --- |
| Checking data types only | `0ms` or negative numbers still bind cleanly | Add domain constraints |
| Using `@NotEmpty` on strings requiring text | Whitespace-only strings pass | Use `@NotBlank` |
| Forgetting `@Valid` on nested objects | Child constraints do not run from parent bean | Add `@Valid` |
| Using primitives for required fields without constraints | `0` or `false` can be mistaken for valid defaults | Use `@Min`, `@AssertTrue`, or boxed types with `@NotNull` |
| Setting `ignoreInvalidFields=true` to avoid startup failures | Bad config gets skipped and runs with unexpected values | Keep fail-fast for critical configuration |
| Defaulting every property to localhost | Production may connect to the wrong endpoint | Only default genuinely safe values |
| Using `optional:` to hide bad configuration | Missing sources and invalid data get conflated | Separate loading errors from validation errors |
| Unit-testing validators only | Misses Binder or profile errors | Add `ApplicationContextRunner`/integration tests |
| Custom validator making HTTP calls | Startup depends on external services and risks timeouts | Separate validation from connectivity checks |
| Logging all config values on error | May leak credentials or secrets | Log only keys, sources, and safe messages |

## 15. Real-World Scenario: Invalid Retry Config from Config Server

`checkout-service` uses Config Server. A new configuration change is rolled out:

```yaml
inventory:
  timeout: 500ms
  max-attempts: 0
  retry:
    min-attempts: 2
    max-attempts: 5
```

Config Server responds successfully, Config Client fetches the data, and the Binder converts `500ms` to `Duration`. However, `max-attempts=0` violates `@Min(1)`.

Resolution workflow:

1. Verify the application requested the expected application name, profile, and label from Config Server.
2. Inspect the binding failure to identify `inventory.max-attempts`.
3. Confirm this is a validation failure, not a Config Server connection issue or conversion error.
4. Fix the value in the config source to a number between 1 and 10.
5. Run configuration tests before distributing.
6. Deploy/refresh following system procedures and confirm all replicas have valid configuration.

Do not disable `@Validated` or remove `@Min` just to let the app boot. The constraint is protecting the client contract; fixing the source data is the proper resolution.

## 16. Pre-Production Configuration Checklist

- [ ] Every property has a clear type, required/optional status, and default.
- [ ] Bounded values have matching constraints.
- [ ] Nested objects have `@Valid` when deep validation is required.
- [ ] Collections have constraints on both the collection and its elements.
- [ ] Cross-property rules are enforced via class-level validators or dedicated methods.
- [ ] A validation provider is present on the classpath.
- [ ] `@ConfigurationProperties` beans are registered properly via scan or enable.
- [ ] Unknown/invalid fields follow an explicit policy.
- [ ] Remote configuration is validated before rollout.
- [ ] Tests cover valid, missing, conversion failure, validation failure, and cross-field failure cases.
- [ ] Configuration refresh includes error handling and a rollback plan.
- [ ] Logs and management endpoints do not leak secrets.

## 17. Summary

Configuration validation guards the contract between an application and its deployment environment. Spring Boot binds data into `@ConfigurationProperties`; Bean Validation enforces constraints on bound objects; the Binder and converters handle type errors before or during validation.

Distinguish clearly between **missing properties**, **type conversion failures**, and **convertible yet invalid values**. Use `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid`, `@AssertTrue`, and custom constraints intentionally. Testing with `ApplicationContextRunner` verifies both binding and fail-fast context behavior.

In Spring Cloud, Config Server can serve syntactically valid data that breaks service rules. Validation must continue to apply when configuration loads remotely or refreshes. An application should adopt new configuration only once the data satisfies the contract and consuming components can transition safely.

## 18. References

- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Boot API — ConfigurationPropertiesScan](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesScan.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Cloud Commons — Application Context Services](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/application-context-services.html)
- [Spring Cloud Config — Client Side Usage](https://docs.spring.io/spring-cloud-config/reference/client.html)
