# Enforcing Validity with @Validated and Reporting Configuration Errors

> **Goal:** When building libraries and Spring Boot Auto-Configuration, external properties must be **bound into a typed object**, **validated against constraints**, and **reported with actionable errors** when values are wrong. `@ConfigurationProperties` handles binding values onto an object; Spring's `@Validated` combined with Jakarta Bean Validation verifies that values are valid; Spring Boot provides a mechanism to report binding/validation errors when creating the configuration bean.

The examples use **Spring Boot 3.3.x and Java 17+**. This lesson focuses on properties provided by a library to consuming applications—do not confuse configuration validation with HTTP controller request validation or business input validation in services.

## 1. Why Must Library Properties Be Validated?

A notification starter might require keys like:

~~~yaml
demo:
  mailer:
    enabled: true
    from-address: "alerts@example.org"
    max-attempts: 3
    transport:
      host: "smtp.example.org"
      port: 2525
~~~

A library cannot assume every value arriving from `application.yml`, environment variables, Java system properties, or the command line is valid. A single deployment change can cause:

- `demo.mailer.from-address` left blank, leaving the system with no sender address.
- `demo.mailer.max-attempts=0` or an excessively large number, producing a meaningless retry policy.
- `demo.mailer.transport.port=70000`, outside the standard TCP port range.
- `demo.mailer.transport.host` left undeclared.
- `demo.mailer.max-attempts=abc`, which cannot be converted from a string to an integer.

If errors only surface the first time an external service is called, root-cause diagnosis is slow and lacks context. For configuration **required to initialize components**, validate when the container creates the configuration properties bean so the application fails fast with the exact key name and reason.

These concepts are distinct:

| Check layer | Example | Primary mechanism |
| --- | --- | --- |
| Property lookup | Does key `demo.mailer.max-attempts` exist? | Configuration sources / `Environment` |
| Type conversion | Can `abc` be converted to `Integer`? | Spring Boot Binder + conversion |
| Constraint validation | Does `0` satisfy `@Min(1)`? | Jakarta Bean Validation via `@Validated` |
| Cross-field check | Do port and protocol match a custom policy? | Custom constraint/validator or custom check logic |
| Bean creation condition | Does `demo.mailer.enabled` equal `true`? | Spring Boot `@ConditionalOnProperty` |

**Validity of a value** and **whether to create a configuration at all** are two different questions. `@Validated` is not responsible for deciding whether an auto-configuration class is enabled; `@ConditionalOnProperty` does not automatically validate every field inside `@ConfigurationProperties`.

## 2. The Three Annotations and Required Dependencies

### @ConfigurationProperties: Defining the Configuration Contract

~~~java
@ConfigurationProperties(prefix = "demo.mailer")
public record MailerProperties(
        String fromAddress,
        Integer maxAttempts,
        Transport transport) {
    public record Transport(String host, Integer port) {}
}
~~~

This is a **structural outline** (imports appear in the complete example section). The Spring Boot binder maps canonical kebab-case names like `from-address` and `max-attempts` to record components `fromAddress` and `maxAttempts`. `transport.host` and `transport.port` belong to the nested object.

Using `@ConfigurationProperties` is much cleaner than scattered `@Value` placeholders when a library has a group of related keys. A record with a single constructor is supported by Spring Boot 3.x for **constructor binding** without needing `@ConstructorBinding` on the type. A JavaBean class with getters/setters is also a valid option.

### @Validated: Requesting Validation After Binding

~~~java
@ConfigurationProperties(prefix = "demo.mailer")
@Validated
public record MailerProperties(
        @NotBlank @Email String fromAddress,
        @NotNull @Min(1) @Max(8) Integer maxAttempts,
        @NotNull @Valid Transport transport) {
    public record Transport(
            @NotBlank String host,
            @NotNull @Min(1) @Max(65535) Integer port) {}
}
~~~

The annotations are:

- `org.springframework.validation.annotation.Validated`: instructs the configuration-properties mechanism to apply validation.
- `jakarta.validation.constraints.NotBlank`: string must not be `null`, empty, or whitespace-only.
- `jakarta.validation.constraints.Email`: checks email address syntax according to the Bean Validation provider. `@Email` alone does not make a field required; pair it with `@NotBlank`.
- `jakarta.validation.constraints.NotNull`: a value/reference must not be `null`; used for required fields.
- `jakarta.validation.constraints.Min` and `Max`: restrict integer ranges; these two constraints **do not forbid `null` by themselves**, so combine them with `@NotNull` when required.
- `jakarta.validation.Valid`: triggers **cascaded validation** for the nested `Transport` object. When you want to require the nested object to always exist, combine `@NotNull @Valid` on the field holding the object.

With `@NotNull @Valid Transport transport`, omitting the entire `transport` branch is caught by `@NotNull`; when `transport` exists, `@Valid` enables validating `host` and `port` inside it. If you place only `@Valid` without `@NotNull`, a `null` nested object can be skipped because cascaded validation does not treat `null` itself as an error.

### Adding a Jakarta Validation Implementation

Annotations alone are not enough: the running application needs a **Bean Validation provider**. In Spring Boot, add `spring-boot-starter-validation` to include a compatible implementation (commonly Hibernate Validator). Example in a Gradle Groovy project that already has Spring Boot dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

If the library is published as a standalone starter, ensure **the consuming application's runtime** has a validation provider. Adding only `jakarta.validation` annotations without a corresponding implementation may result in validation not actually being enforced as expected. On **Spring Boot 3.x**, use the `jakarta.validation.*` package, not `javax.validation.*` from older generations.

## 3. Registering the Properties Bean in Auto-Configuration

Create the properties class **separate from business beans**, then register it via `@EnableConfigurationProperties`:

~~~java
@AutoConfiguration
@EnableConfigurationProperties(MailerProperties.class)
class MailerAutoConfiguration {
    @Bean
    MailerClient mailerClient(MailerProperties properties) {
        return new MailerClient(
                properties.transport().host(),
                properties.transport().port(),
                properties.fromAddress(),
                properties.maxAttempts());
    }
}
~~~

This is a structural template; section 6 provides **complete files and imports**. When Spring needs to create `MailerProperties`, Boot binds the effective values from `Environment`, performs type conversion, and then checks constraints if `@Validated` and an appropriate validator are present. When configuration is invalid and the properties bean is created at startup, the container normally halts initialization with an error report.

Important points for **libraries**:

1. `@ConfigurationProperties` defines the key group and data types; it **is not enough** to guarantee the bean is registered.
2. `@EnableConfigurationProperties(MailerProperties.class)` registers the exact type the library wants to bind; this works cleanly in auto-configuration without requiring users to scan the library's internal packages.
3. The client bean receives the bound/validated object via injection, instead of calling `environment.getProperty(...)` in many places.
4. Putting `MailerProperties` on multiple independent registration paths (scan, component, and enable) can make lifecycle and error messages confusing. Pick one deliberate registration path in a starter.

In a starter published for users, keys should be written in **lowercase kebab-case** with a consistent prefix: `demo.mailer.from-address`, `demo.mailer.max-attempts`, `demo.mailer.transport.host`, `demo.mailer.transport.port`. Error messages and user documentation should reference these key names.

## 4. How Are Configuration Errors Reported?

In an application starting with Spring Boot, a problem while binding properties can trigger an exception in the bean creation chain and a **Failure Analysis** describing the cause. Distinguish two main categories:

**A. Type conversion failure (binding/conversion failure)**

~~~properties
demo.mailer.enabled=true
demo.mailer.from-address=alerts@example.org
demo.mailer.max-attempts=abc
demo.mailer.transport.host=smtp.example.org
demo.mailer.transport.port=2525
~~~

The `max-attempts` field requires `Integer` but received `abc`. The Binder **cannot produce a value of the right type**; the failure occurs at the conversion/binding step, so it must not be described as a `@Min(1)` error. The message typically points out the prefix/key, invalid value, and conversion cause.

**B. Type conversion succeeds, constraint fails (validation failure)**

~~~properties
demo.mailer.enabled=true
demo.mailer.from-address=alerts@example.org
demo.mailer.max-attempts=0
demo.mailer.transport.host=smtp.example.org
demo.mailer.transport.port=2525
~~~

`0` converts to `Integer` successfully but violates `@Min(1)`. This is a validation error during property binding. Spring Boot normally presents the error with details: property path, value, reason, and origin (if the source supports origin tracking).

An **illustrative mockup, not fixed stdout**, of Failure Analysis:

~~~text
APPLICATION FAILED TO START

Description:
Failed to bind properties under 'demo.mailer' ...

Property: demo.mailer.max-attempts
Value: 0
Reason: must be greater than or equal to 1

Action:
Review the application's configuration.
~~~

Exact wording, message locale, and exception chains can vary by Spring Boot version, Jakarta Validation provider, and property source. What to look for is **the offending key name, received value, reason, and value origin**; do not write tests matching the entire error banner verbatim.

### Conditions for Clear Errors

- A `@ConfigurationProperties` bean is registered and **actually created/bound**.
- `@Validated`/constraints and a Jakarta Validation implementation are present when constraint checking is desired.
- Errors are not hidden by options that ignore invalid values or swallow exceptions.
- The property to validate **resides inside the object** and the constraint is actually evaluated.

A value that already has a valid default will not necessarily error when omitted. Conversely, in the example using `@NotNull`, omitting `max-attempts` is blocked instead of silently defaulting to 0. If you use primitive `int` without a configured value, 0 may end up violating `@Min(1)`, but the message will be less clear about a "missing key" than the `Integer + @NotNull` design.

## 5. Effective Properties and Origin: Don't Edit the Wrong File

Spring Boot has multiple `PropertySource`s ordered by precedence. For instance:

- `application.yml` in the JAR declares `demo.mailer.max-attempts=3`.
- A container environment variable sets `DEMO_MAILER_MAXATTEMPTS=0`.
- No higher-precedence source overrides it.

During binding, the effective value can be `0`, and `@Min(1)` will fail even though the YAML file you look at still says `3`. Spring Boot applies relaxed binding: from canonical `demo.mailer.max-attempts` to the standard OS variable name `DEMO_MAILER_MAXATTEMPTS` (dots → underscores, drop hyphens, uppercase).

Investigation workflow:

1. Write down the **canonical property path** from `@ConfigurationProperties(prefix=...)` and the corresponding record field.
2. Check the effective value in **the actual process**: CLI arguments, system properties, OS env, profile-specific config, config imports.
3. Read the Failure Analysis to see whether it failed due to type conversion or a constraint, and on which property path.
4. Use **origin** information if provided: file/line or source name—do not guess the origin if metadata is absent.
5. Fix the value in **the winning source**, restart the context, and re-run tests.

With Spring Boot Actuator and secure access configuration, `/actuator/env/{name}` and `/actuator/configprops` help inspect property sources and bound values. However, if validation failure prevents the app from starting, you **cannot rely on the failed app's own HTTP endpoints** for diagnosis; logs, command-line flags, runtime environment manifests, or a test context are more practical sources.

Diagnostic endpoints can mask sensitive data and are not exposed over HTTP by default; do not expose `env`/`configprops` publicly just for debugging. Never print full secrets/tokens into logs or custom error messages.

## 6. Complete Java 17+ Example with Startup Validation

The example below creates a **configuration-simulating client**; it does **not** open SMTP connections or send email. That allows testing registration, binding, and validation deterministically without external services.

### 6.1. File MailerProperties.java

**Path:** `src/main/java/example/library/MailerProperties.java`

~~~java
package example.library;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "demo.mailer")
@Validated
public record MailerProperties(
        @NotBlank @Email String fromAddress,
        @NotNull @Min(1) @Max(8) Integer maxAttempts,
        @NotNull @Valid Transport transport) {

    public record Transport(
            @NotBlank String host,
            @NotNull @Min(1) @Max(65535) Integer port) {
    }
}
~~~

This is the configuration contract: email must be present and syntactically valid, attempt count must be 1–8, and the transport object must have a non-blank host and a port from 1–65535. `@Valid` on `transport` ensures validation cascades into the nested bean.

### 6.2. File MailerClient.java

**Path:** `src/main/java/example/library/MailerClient.java`

~~~java
package example.library;

public record MailerClient(
        String host,
        int port,
        String fromAddress,
        int maxAttempts) {

    public String description() {
        return "host=" + host
                + ", port=" + port
                + ", from=" + fromAddress
                + ", attempts=" + maxAttempts;
    }
}
~~~

This record only stores bound values and produces a description string for testing; **no network connections**. Passing a validated `Integer` into an `int` parameter relies on unboxing; thanks to `@NotNull`, valid configuration never unboxes `null`.

### 6.3. File MailerAutoConfiguration.java

**Path:** `src/main/java/example/library/MailerAutoConfiguration.java`

~~~java
package example.library;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.mailer",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailerProperties.class)
public class MailerAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MailerClient.class)
    public MailerClient mailerClient(MailerProperties properties) {
        return new MailerClient(
                properties.transport().host(),
                properties.transport().port(),
                properties.fromAddress(),
                properties.maxAttempts());
    }
}
~~~

Execution flow when `demo.mailer.enabled=true`:

1. Boot evaluates the property condition at the auto-configuration class level.
2. When the class is applied, `@EnableConfigurationProperties` registers the `MailerProperties` bean.
3. When the properties bean is created, the binder converts values and validation checks constraints.
4. If everything is valid and no application-supplied `MailerClient` exists, the `mailerClient` method creates the default client with the validated values.
5. If data is invalid, the context does not finish starting normally; tests can capture the failure state.

`@ConditionalOnMissingBean` is part of the back-off mechanism allowing users to replace the default bean; it does not replace `@Validated`. Note that if a user supplies their own `MailerClient` while auto-configuration is still applied, `@EnableConfigurationProperties` can still register/bind properties and trigger validation—this may be intentional for the library, or may require redesigning registration scope if completely unused configuration should be ignored.

For Boot to auto-discover auto-configuration when **packaging the library**, you need the file:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
example.library.MailerAutoConfiguration
~~~

Users do not need to component-scan the library package. In the unit test below, `AutoConfigurations.of(...)` loads the class directly, so the imports file is **not required** to run the tests.

### 6.4. File MailerValidationTest.java

**Path:** `src/test/java/example/library/MailerValidationTest.java`

~~~java
package example.library;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.context.properties.bind.validation.BindValidationException;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class MailerValidationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(MailerAutoConfiguration.class));

    private ApplicationContextRunner enabled(
            String fromAddress,
            String attempts,
            String host,
            String port) {

        return runner.withPropertyValues(
                "demo.mailer.enabled=true",
                "demo.mailer.from-address=" + fromAddress,
                "demo.mailer.max-attempts=" + attempts,
                "demo.mailer.transport.host=" + host,
                "demo.mailer.transport.port=" + port);
    }

    @Test
    void validConfigurationBindsAndCreatesClient() {
        enabled("alerts@example.org", "3", "smtp.example.org", "2525")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(MailerProperties.class);
                    assertThat(context).hasSingleBean(MailerClient.class);
                    assertThat(context.getBean(MailerClient.class).description())
                            .isEqualTo("host=smtp.example.org, port=2525"
                                    + ", from=alerts@example.org, attempts=3");
                });
    }

    @Test
    void invalidEmailFailsValidation() {
        enabled("not-an-email", "3", "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void zeroAttemptsFailsValidation() {
        enabled("alerts@example.org", "0", "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void blankNestedHostFailsValidation() {
        enabled("alerts@example.org", "3", "", "2525")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void outOfRangePortFailsValidation() {
        enabled("alerts@example.org", "3", "smtp.example.org", "70000")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void missingTransportFailsValidation() {
        runner.withPropertyValues(
                "demo.mailer.enabled=true",
                "demo.mailer.from-address=alerts@example.org",
                "demo.mailer.max-attempts=3")
                .run(context -> assertThat(context).hasFailed()
                        .getFailure()
                        .hasRootCauseInstanceOf(BindValidationException.class));
    }

    @Test
    void invalidNumberFailsDuringTypeConversion() {
        enabled("alerts@example.org", "not-a-number",
                "smtp.example.org", "2525")
                .run(context -> assertThat(context).hasFailed());
    }

    @Test
    void disabledAutoConfigurationDoesNotBindTheseProperties() {
        runner.withPropertyValues(
                "demo.mailer.enabled=false",
                "demo.mailer.max-attempts=not-a-number")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(MailerProperties.class);
                    assertThat(context).doesNotHaveBean(MailerClient.class);
                });
    }
}
~~~

**How to run** in a Java 17+ project with Spring Boot 3.3 and `spring-boot-starter-test`, `spring-boot-starter-validation` dependencies:

~~~bash
mvn -Dtest=MailerValidationTest test
# Or Gradle wrapper on Linux/macOS:
./gradlew test --tests example.library.MailerValidationTest
~~~

**Expected result:** **8 tests PASS**, provided the project has the appropriate dependencies and Java version configured. The tests have no fixed stdout because they only assert results against the Spring context. The `BindValidationException` checks confirm the validation error path when constraints fail; `invalidNumberFailsDuringTypeConversion` only asserts context failure, because the wrapper/cause of a conversion error can differ from validation.

In a real project, you can add assertions on specific bind failure details, while avoiding matching entire version-dependent error messages. The most important tests are: valid config binds, nested constraints are checked, invalid values prevent the context from starting, and disabling the feature does not create the properties bean through **this auto-configuration registration path**.

## 7. Distinguishing Disabled Configuration from Invalid Configuration

Library design needs to answer: **If the user sets `demo.mailer.enabled=false`, do required inner properties still need to be valid?**

In section 6's example, the condition:

~~~java
@ConditionalOnProperty(
        prefix = "demo.mailer",
        name = "enabled",
        havingValue = "true")
@EnableConfigurationProperties(MailerProperties.class)
~~~

sits on **the same auto-configuration class**. When `enabled=false` or the key is missing with the default `matchIfMissing=false`, the class is not applied; `MailerProperties` is not registered by that class. Therefore an invalid `max-attempts` can **avoid binding/validation on the disabled branch**. This is a useful design choice for optional integrations, though it must not be misunderstood as "every invalid config always fails startup."

Conversely, if `MailerProperties` is registered **independently** by `@ConfigurationPropertiesScan` or another `@EnableConfigurationProperties`, validation may still run even when the client is blocked by a condition. You must clearly identify **who owns registering the properties bean**.

Design choices:

| Library contract | Appropriate configuration approach | Consequence |
| --- | --- | --- |
| Optional feature; properties needed only when enabled | Put condition on the configuration group registering properties | Disabling the feature skips binding along that path |
| Properties shared across multiple features, always must be valid | Register properties in a shared configuration | Validation runs regardless of whether an individual client is enabled |
| Need to allow a custom client to replace the default while still enforcing all properties | Use `@ConditionalOnMissingBean` on the default client, keep properties registration | Validation still occurs if the properties bean is created |
| Need a custom client that does not use the default properties group | Consider splitting subgroups/nested configurations to register properties in the right scope | Avoids forcing users to supply config for a component they completely replaced |

Do not use `@ConditionalOnProperty` as a way to "hide" unintended configuration errors. If the application **has requested** enabling the feature, required fields must be clearly constrained and startup errors must tell users how to fix them.

## 8. Defaults, Missing Values, and Typos

### Intentional Default Design

Optional values can have defaults in the configuration model, for example via `@DefaultValue` for constructor binding, or field initializers for JavaBean binding. However:

- Defaults must **fall within the valid range** of the constraints.
- If a value must be decided by the deployer, do not supply a default that masks a missing setting.
- With records, distinguish nullable `Integer` from primitive `int`: `@NotNull` only detects missing values directly on references; primitives are never `null`.
- Do not automatically conclude "missing key is an error" when the model defines a valid default.

### Misspelled Keys May Not Be Caught

`@Validated` checks **the properties that were bound into the model**. It does not prove every configuration key in a file was spelled right. On `@ConfigurationProperties`, `ignoreUnknownFields` defaults to `true`. Thus, a misspelled key can be ignored, and if the corresponding field has a valid default, validation still PASSES.

You can consider `ignoreUnknownFields=false` when a stricter policy is desired, but understand its scope: **every key sharing the prefix can be treated as unknown if the model does not declare it**. In our example, `demo.mailer.enabled` is a flag read by `@ConditionalOnProperty` but **not declared in the `MailerProperties` record**. If you turn on strict unknown checking without adding that flag to the model or changing the prefix structure, valid configuration may be flagged as unknown. So do not enable strict mode mechanically.

Likewise, `ignoreInvalidFields=true` is not a fix for bad configuration; it can silently skip values that fail type conversion, losing important diagnostics. By default, invalid fields are not ignored.

### Be Careful with `@Email`

`@Email` mainly checks email **syntax**, not whether the mailbox exists or is authorized to send. Exact syntax rules depend on the Bean Validation provider. Business rules like "only allow company domains" or "port must match TLS mode" require a specialized constraint or a separate logic check.

### Validation Groups and Cross-Field Checks

Spring's `@Validated` can specify validation groups; Jakarta Validation supports group sequences and custom class-level constraints. Use them only when the product genuinely has complex rules. For most starters, a clear model with `@NotBlank`, `@NotNull`, `@Min`, `@Max`, `@Valid`, and a few targeted custom constraints is easier to maintain.

If a dedicated `org.springframework.validation.Validator` is needed for configuration properties, Spring Boot recognizes a bean named `configurationPropertiesValidator`. When declaring a `@Bean` for such a validator, Boot documentation recommends a `static` method because the validator is created very early in the lifecycle, avoiding premature initialization of the `@Configuration` class. Do not write a custom validator when Jakarta constraints already express the requirements.

## 9. Giving Actionable Configuration Error Feedback to Library Integrators

A helpful error message should tell deployers **what to fix**:

- **Exact key:** e.g., `demo.mailer.max-attempts` rather than just `attempts`.
- **Error category:** conversion, missing required value, constraint range, or cross-field rule.
- **Valid range:** "from 1 to 8" instead of a vague "invalid".
- **Origin if available:** file/line or property source; do not guess when origin is unavailable.
- **Action:** update configuration in the winning source and restart.
- **Security:** do not display tokens/passwords or values containing secrets in custom failure messages.

Illustrative rendering when an error occurs on `demo.mailer.transport.port`:

~~~text
Property: demo.mailer.transport.port
Value: 70000
Reason: must be less than or equal to 65535
Action: Set demo.mailer.transport.port to an integer from 1 to 65535.
~~~

This is a **clear message example**, not literal output always generated by Spring Boot 3.3. For sensitive data, avoid including the raw value itself in custom library messages.

**Standard mechanism and complementary role:** When Bean Validation fails, Spring Boot already provides failure analysis for many binding cases. Adding a custom `FailureAnalyzer` is only worth considering if the library needs to explain a domain-specific rule whose default error is hard to understand. A custom analyzer should match the specific exception and return a helpful description/action; never catch every exception and turn it into "invalid configuration," hiding programming bugs or missing dependencies.

## 10. Common Mistakes and How to Avoid Them

1. **Writing `@NotNull` while forgetting `@Validated` on the properties class**: constraints may not be applied automatically during binding as expected. Verify provider and registration.
2. **Forgetting `spring-boot-starter-validation` at runtime**: annotations compile, yet no compatible Bean Validation implementation is present. Check the consuming app's dependencies.
3. **Forgetting `@Valid` on nested objects**: constraints on deep fields are not guaranteed to run. Use `@NotNull @Valid` if the nested object is always required.
4. **Using `int` and assuming a missing key behaves like `null`**: primitives have defaults; use wrapper types + `@NotNull` when you want to detect omission directly.
5. **Calling a conversion error a `@Min` error**: `abc` fails to convert to `Integer`; that is a binding error, unlike `0` which binds and then violates a constraint.
6. **Ignoring override sources**: the YAML file looks valid, yet a higher-precedence env var supplies an invalid value. Diagnose the winning property source and origin.
7. **Assuming every typo is caught by `@Validated`**: unknown keys can be ignored; consider metadata/strict-binding policies and test key spellings.
8. **Automatically printing secrets into diagnostic logs**: mask or omit sensitive values, keeping only the property path and reason whenever possible.
9. **Registering properties via multiple paths**: a disabled condition may not stop binding if the bean is registered independently elsewhere.
10. **Writing tests that only check context failure**: include valid cases, each constraint, nested fields, invalid types, and the feature-disabled case to verify design intent.

## 11. Knowledge Self-Check

**Question 1.** `demo.mailer.max-attempts=abc`, where the field is `Integer` with `@Min(1)`. Where does the error occur first?  
**Answer:** Type conversion/binding fails before numeric constraint validation runs.

**Question 2.** Is `max-attempts=0` valid with `@NotNull @Min(1)`?  
**Answer:** No; `0` binds to `Integer` but violates `@Min(1)`.

**Question 3.** `Transport` has a `host` field annotated with `@NotBlank`, while the parent declares only `Transport transport` without `@Valid`. Is `host` guaranteed to be validated as expected?  
**Answer:** No; `@Valid` is needed for cascading. If the entire object is required, combine with `@NotNull`.

**Question 4.** A library has an enabled flag at the auto-configuration level; when disabled, does an invalid port necessarily fail startup?  
**Answer:** No; if properties are registered only inside the skipped auto-configuration, binding/validation does not run along that path. However, if the properties bean is registered elsewhere, it may still be checked.

**Question 5.** Why should `@Email` be paired with `@NotBlank` when the sender address is mandatory?  
**Answer:** `@Email` checks format; `@NotBlank` forbids missing/empty/whitespace-only values.

**Question 6.** With `@ConfigurationProperties` having `ignoreUnknownFields=true`, is an extra key in the config file always treated as an error?  
**Answer:** No. Validation on the bound model does not check every undeclared key across the entire file.

**Question 7.** What is the purpose of Failure Analysis in this scenario?  
**Answer:** To report the property name, value/reason, and origin if available, so deployers fix the right source instead of only seeing a cryptic stack trace.

## Reference Documentation

- [Spring Boot 3.3 — Externalized Configuration: Type-safe Configuration Properties and Validation](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): registering `@ConfigurationProperties`, binder, `@Validated`, nested `@Valid`, property sources, and origin.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): configuration conditions, `@EnableConfigurationProperties` in starters, and `ApplicationContextRunner` testing.
- [Spring Boot 3.3 — ConfigurationProperties API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html): `prefix`, `ignoreUnknownFields`, and `ignoreInvalidFields`.
- [Spring Boot 3.3 — BindValidationException API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/bind/validation/BindValidationException.html): constraint errors during property binding.
- [Jakarta Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@NotNull`, `@NotBlank`, `@Min`, `@Max`, `@Valid`, and validation providers.

**Remember:** A library should treat configuration properties as **a typed, constrained, and error-reporting contract**. `@ConfigurationProperties` binds effective values, `@Validated` with Jakarta constraints guards the valid domain, and `@Valid` checks nested objects; auto-configuration conditions decide **when** those properties are actually registered and validated.
