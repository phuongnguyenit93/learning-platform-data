# Testing Missing or Invalid Configuration and Observing Fail-Fast Startup in Spring Boot

## 1. Practice Objectives

In Spring Boot, an application can load configuration from `application.yml`, `application.properties`, profile-specific files, environment variables, command-line arguments, and Config Data imports. These mechanisms make deployment flexible, yet they also create a risk that a value is missing, mistyped, or overridden without the development team noticing right away.

This practice builds a small application with clearly typed configuration, then intentionally introduces different kinds of errors and observes the **fail-fast** mechanism: the application **refuses to start successfully** when critical configuration is invalid.

After completing this lesson, learners will be able to:

1. Create a validated `@ConfigurationProperties` bean.
2. Distinguish **missing keys**, **empty/blank values**, **wrong types**, **constraint violations**, and **unbound keys**.
3. Know when Spring Boot may use defaults and when startup should fail.
4. Run the application with valid configuration and intentionally broken configurations.
5. Read startup messages and the cause chain without relying on a fixed log string.
6. Write tests asserting that the application context starts only when the configuration satisfies its contract.
7. Distinguish Config Data loading failures from binding/validation failures.
8. Inspect higher-precedence sources such as environment variables and CLI arguments.
9. Verify that the right profile is activated.
10. Write a deployment configuration checklist to catch errors before production.

All endpoints, tokens, and paths in the examples are learning data. Do not use real credentials in tests or logs.

## 2. What Does "Fail Fast" Mean?

In this practice, fail fast means: **if required configuration is incorrect, Spring application context initialization fails rather than letting the application serve traffic in an unintended state**.

Example:

~~~text
Start application
       |
       v
Load Config Data / PropertySources
       |
       v
Bind demo.delivery.* into DeliveryProperties
       |
       +-- conversion failed ------> startup failure
       |
       v
Validate DeliveryProperties
       |
       +-- constraints violated ---> startup failure
       |
       v
Create dependent beans
       |
       +-- invalid invariant -----> startup failure
       |
       v
Application context ready
       |
       v
Serve workload / run job
~~~

Note: not every error appears at the exact same step; a missing Config Data location can fail before the Binder runs, whereas an expired upstream credential may only be discovered when calling the service unless a startup check exists. "Fail fast" here focuses on conditions that **can and should be checked during startup**.

A Java program may print logs and exit with a non-zero exit code when an unhandled exception occurs. The exact exit code and message format depend on the launcher, operating system, Boot version, and test runner. Reliable evidence is that **the context failed for the right configuration cause**, not merely a log line containing the word ERROR.

## 3. Practice Scenario

Suppose a `delivery-worker` service pushes events to a partner API. It needs:

| Property | Type | Contract |
| --- | --- | --- |
| `demo.delivery.enabled` | Boolean | Must be explicitly declared true/false |
| `demo.delivery.endpoint` | String | Required and non-blank |
| `demo.delivery.request-timeout` | Duration | Required, greater than 0 |
| `demo.delivery.max-attempts` | Integer | Required, from 1 to 5 |

In this lesson `endpoint` is always required, even when `enabled=false`, to illustrate simple, easy-to-test constraints. If a real system requires `endpoint` **only when enabled**, use cross-field validation or mode-based schema/bean registration; an advanced section illustrates that at the end.

Valid configuration set:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

Scenarios to intentionally break:

- Omit `endpoint`.
- Provide `endpoint=""` or whitespace only.
- Provide `max-attempts=abc`.
- Provide `max-attempts=0` or 9.
- Provide `request-timeout=tomorrow`.
- Provide `request-timeout=0s`.
- Omit `enabled`.
- Misspell `max-attemtps`.
- Supply an invalid override via environment/CLI.
- Import a required Config Data location that does not exist.

These errors are not of the same nature; learning how to identify the **failure category** is a key goal.

## 4. Project Structure

An example Maven/Spring Boot Java structure:

~~~text
config-fail-fast-demo/
  pom.xml
  src/
    main/
      java/com/example/demo/
        DemoApplication.java
        config/
          DeliveryProperties.java
        service/
          DeliveryRunner.java
      resources/
        application.yml
        application-local.yml
        application-prod.yml
    test/
      java/com/example/demo/
        config/
          DeliveryPropertiesTests.java
~~~

No real HTTP API is needed to test binding; a `CommandLineRunner` can prove that the application context initialized. In production, the runner should not print secrets or the entire properties bean if it contains credentials.

If using Gradle, the source layout is similar; replace `pom.xml` with `build.gradle` or `build.gradle.kts` and use the corresponding tasks.

## 5. Required Dependencies

If the project already uses Spring Boot dependency management, the following dependencies are needed:

### Maven

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

The project must have a Spring Boot parent/BOM or an appropriate version management mechanism. This snippet is the `dependencies` section inserted into an already configured POM, not a standalone POM.

### Gradle Groovy DSL

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### Gradle Kotlin DSL

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
~~~

With Spring Boot 3.x, use the `jakarta.validation` namespace. Without a Bean Validation provider, merely declaring `@Validated` or `@NotBlank` does not guarantee that constraints are enforced as expected.

Do not confuse `spring-boot-configuration-processor`—which provides compile-time IDE metadata—with `spring-boot-starter-validation`, which provides runtime validation.

## 6. Declaring the Configuration Bean

Create `src/main/java/com/example/demo/config/DeliveryProperties.java`:

~~~java
package com.example.demo.config;

import java.time.Duration;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(
        prefix = "demo.delivery",
        ignoreUnknownFields = false
)
public record DeliveryProperties(
        @NotNull Boolean enabled,
        @NotBlank String endpoint,
        @NotNull Duration requestTimeout,
        @NotNull @Min(1) @Max(5) Integer maxAttempts
) {
    public DeliveryProperties {
        if (requestTimeout != null
                && (requestTimeout.isZero()
                    || requestTimeout.isNegative())) {
            throw new IllegalArgumentException(
                    "demo.delivery.request-timeout must be positive"
            );
        }
    }
}
~~~

Design choices:

- `Boolean` instead of `boolean` to distinguish "undeclared" from `false`.
- `@NotNull` on `enabled` requires a value, while both `true` and `false` are valid.
- `@NotBlank` on `endpoint` rejects null, empty strings, and whitespace.
- `Duration` accepts convertible values such as `5s` according to the Binder.
- `@NotNull` on timeout ensures it is not missing.
- The constructor invariant rejects `0s` and negative durations.
- `Integer` + `@NotNull` + `@Min`/`@Max` distinguishes missing values from out-of-range values.
- `ignoreUnknownFields=false` helps reject extra keys under the namespace owned by this class when the configuration source allows discovering unbound properties.

**Do not print `endpoint` or the entire properties bean inside exceptions in real projects** if the endpoint could contain query tokens or userinfo. Here only the key name is shown in the invariant message.

In this lesson the record has no defaults: that is an intentional decision so that omitting any of the four properties becomes an error.

## 7. Registering the Properties Bean and Application

`DemoApplication.java`:

~~~java
package com.example.demo;

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

`@ConfigurationPropertiesScan` lets Spring Boot discover the `DeliveryProperties` class under the appropriate package. Another option is `@EnableConfigurationProperties(DeliveryProperties.class)`.

If you forget to register the properties bean, there may be no bean to validate and the lab results can be misinterpreted. **Having `@ConfigurationProperties` on a class should not be treated as proof that every bean-creation path has been configured.**

Do not arbitrarily combine multiple registration strategies in a way that causes the bean to be registered twice.

## 8. A Runner Proving Successful Startup

`src/main/java/com/example/demo/service/DeliveryRunner.java`:

~~~java
package com.example.demo.service;

import com.example.demo.config.DeliveryProperties;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class DeliveryRunner implements CommandLineRunner {

    private static final Logger log =
            LoggerFactory.getLogger(DeliveryRunner.class);

    private final DeliveryProperties properties;

    public DeliveryRunner(DeliveryProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(String... args) {
        log.info(
                "Delivery configuration valid: enabled={} timeout={} maxAttempts={}",
                properties.enabled(),
                properties.requestTimeout(),
                properties.maxAttempts()
        );
    }
}
~~~

The runner logs three fields treated as non-secret in the example; do not log the whole record because a future version might add an API token.

When the properties bean is created successfully, the runner is invoked after the context is prepared per the Spring Boot lifecycle. When binding/validation fails during startup, you will not see the `"Delivery configuration valid"` message from this runner.

However, **not seeing the runner log by itself does not prove a validation failure**, because the application could also fail due to a dependency, Java code, or logger issue. You must read the cause chain.

## 9. Creating a Valid `application.yml`

~~~yaml
spring:
  application:
    name: config-fail-fast-demo

demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

This is a configuration **with no real credentials** and all four required fields.

With the runner above, the application does not need to call a real endpoint. The fact that the illustrative domain does not serve requests does not affect checks that only verify configuration.

If a real system creates an HTTP client and connects upstream immediately on startup, design mocks or clearly separate connection errors from config validation errors.

## 10. Running the Valid Configuration First

Maven Wrapper example:

~~~bash
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Expected result: the context starts successfully and the runner logs a message similar to:

~~~text
Delivery configuration valid: enabled=true timeout=PT5S maxAttempts=3
~~~

`Duration.toString()` displays in ISO-8601 format, so `5s` may be logged as `PT5S`. Do not use character-by-character comparison of the startup banner/stack trace as the sole criterion, because formatting depends on the Boot version and logger.

Stop the process after observing the baseline before moving on to the failure cases. Each failure case should start from **the same baseline configuration**, changing only the property under test.

## 11. Organizing Experiments Without Breaking the Baseline

To avoid editing a single file and forgetting to revert it, you can:

1. Keep a valid `application.yml` in the repository.
2. Use a command-line argument to override one value to trigger a failure.
3. Or create a separate profile file containing one failure case.
4. Use test code to pass `withPropertyValues(...)` directly.
5. Run each case in an independent process/test context.
6. Do not commit broken configurations to the approved baseline.

Using the CLI to **demonstrate non-secret errors** such as timeouts or retries is appropriate for learning. Never pass real passwords/tokens via command-line arguments because they can appear in process inspection, shell history, and logs.

In manual practice, start from a valid configuration and introduce exactly one error per run so symptoms can be cleanly tied to causes.

## 12. Failure Case 1 — Missing Required Property `endpoint`

Remove the line:

~~~yaml
endpoint: "https://delivery.example.org/v1/events"
~~~

Remaining configuration:

~~~yaml
demo:
  delivery:
    enabled: true
    request-timeout: 5s
    max-attempts: 3
~~~

With the `DeliveryProperties` record:

~~~java
@NotBlank String endpoint
~~~

the missing value can leave `endpoint` null while constructing the properties object. When validation runs, `@NotBlank` rejects it.

A startup error message **may** contain points like:

~~~text
Failed to bind properties under 'demo.delivery'
Property: demo.delivery.endpoint
Reason: must not be blank
~~~

This is only **an illustration of the content**. Do not assume every Spring Boot version or logger prints those exact lines. In some versions, the top-level exception is wrapped, and the property name or reason sits inside the cause chain.

What to confirm:

- The context failed.
- The cause originates from configuration binding/validation.
- The `endpoint` field is the violating field.
- The runner reporting valid configuration did not execute.

If a test still passes, check `@Validated`, the validation provider, bean registration, and whether another higher-precedence configuration source supplies `endpoint`.

## 13. Failure Case 2 — Key Present but Empty Value

Configuration:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: ""
    request-timeout: 5s
    max-attempts: 3
~~~

`@NotBlank` must also reject an empty string.

Try the variant:

~~~yaml
endpoint: "   "
~~~

Because it is all whitespace, `@NotBlank` continues to reject it.

Takeaway:

- `@NotNull` only detects null; it does not reject `""`.
- `@NotEmpty` rejects an empty string but can accept whitespace.
- `@NotBlank` is appropriate when a `String` must contain non-whitespace characters.

Do not lump missing and empty together into one case when analyzing failures; the two states can stem from different deployment causes.

## 14. Failure Case 3 — Wrong Type for `max-attempts`

Keep the other fields valid and change:

~~~yaml
max-attempts: many
~~~

The Java target is:

~~~java
Integer maxAttempts
~~~

The Binder cannot convert `many` into an integer. This failure happens at the **conversion/binding** step, which can occur before Bean Validation because a valid object cannot be constructed yet.

A typical message may contain:

~~~text
Failed to bind ... 'demo.delivery.max-attempts'
Failed to convert from type java.lang.String to type java.lang.Integer
~~~

Do not treat this as "`@Min(1)` is not working". `@Min` validates numbers that have already been converted successfully, whereas in this case there is no valid `Integer` yet.

Diagnostic steps:

1. Identify which property the Binder was reading.
2. Check the target Java type.
3. Identify the raw value or origin if it can be done safely.
4. Fix the source with the highest precedence.
5. Re-run the baseline.

If a field holds a secret, do not echo its raw value to logs/tickets. Here `many` is non-secret data used for learning.

## 15. Failure Case 4 — Valid Type but Out-of-Range Value

Change:

~~~yaml
max-attempts: 0
~~~

Or:

~~~yaml
max-attempts: 9
~~~

Both values can be converted into an `Integer`. However:

~~~java
@Min(1) @Max(5)
Integer maxAttempts
~~~

requires a value from 1 to 5.

With 0, `@Min(1)` is violated. With 9, `@Max(5)` is violated. This is a **Bean Validation failure**, different from the conversion failure in the previous section.

Points to observe:

- Binding to a Java integer is not the primary problem.
- Validation detects that the value violates policy.
- The application context fails before the runner reports success.
- Do not work around this by setting `ignoreInvalidFields=true` to ignore errors.

An accurate constraint helps prevent the application from running with retry counts that could overload an upstream service or lose resilience.

## 16. Failure Case 5 — Invalid `Duration` Format

Change:

~~~yaml
request-timeout: tomorrow
~~~

Target:

~~~java
Duration requestTimeout
~~~

The Spring Boot Binder supports duration representations such as `5s`, `250ms`, `2m`, or ISO-8601 durations per the framework's rules. The string `tomorrow` is not a valid duration.

The expected result is a conversion failure.

To fix:

~~~yaml
request-timeout: 5s
~~~

or another valid duration. Do not simply change it to the bare number `5` without understanding the default binding unit; for unitless durations, interpretation depends on binding rules and annotations such as `@DurationUnit` if present.

A configuration can have valid YAML syntax yet fail business typing in the Binder.

## 17. Failure Case 6 — `Duration.ZERO` Is Type-Valid but Violates Policy

Change:

~~~yaml
request-timeout: 0s
~~~

`0s` can bind into `Duration.ZERO` — meaning type conversion succeeds. However, the record constructor has an invariant:

~~~java
if (requestTimeout != null
        && (requestTimeout.isZero()
            || requestTimeout.isNegative())) {
    throw new IllegalArgumentException(
            "demo.delivery.request-timeout must be positive");
}
~~~

Therefore startup can fail during record creation rather than from an `@NotNull` constraint.

Comparison:

| Value | Type conversion result | Contract result |
| --- | --- | --- |
| `5s` | Valid | Valid |
| `0s` | Valid | Invalid — not positive |
| `-2s` | Valid if parser accepts representation | Invalid — negative |
| `tomorrow` | Invalid | Does not reach invariant step |
| Missing `request-timeout` | Can become null | Rejected by `@NotNull` |

This is why **conversion** and **validation/invariant** should be treated as two separate layers.

## 18. Failure Case 7 — Missing Required Boolean

Remove:

~~~yaml
enabled: true
~~~

The class uses:

~~~java
@NotNull Boolean enabled
~~~

Without a default, when no value is supplied, `enabled` can be null and be rejected by the validator.

If replaced with a primitive:

~~~java
boolean enabled
~~~

an absent value may be represented as `false`, preventing the application from distinguishing whether the deployer intentionally disabled the feature or forgot to declare it.

This lesson uses `Boolean` so required means **an explicit decision must be made**. In another system, a feature with a safe `false` default may be designed as optional; that choice must come from the configuration contract.

## 19. Failure Case 8 — Misspelled Property Name

Configuration:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
    max-attemtps: 4
~~~

The key `max-attemtps` is a typo; the record only has `maxAttempts`.

Because the class has:

~~~java
@ConfigurationProperties(
    prefix = "demo.delivery",
    ignoreUnknownFields = false
)
~~~

Spring Boot can reject the unbound property when the Binder detects it in a configuration source capable of enumerating property names.

Important: `@NotNull` or `@Min` **does not automatically detect an extra key**. If the valid value `max-attempts=3` is still present, the bean can satisfy all constraints while containing an ignored typo unless strict unknown-fields checking is enabled.

`ignoreUnknownFields=false` is not a tool that finds every typo in every namespace. A mistake changing the prefix to `demo.deliveries` falls outside the `demo.delivery` root. Both root presence and required fields must be tested.

## 20. Failure Case 9 — Key Present but Overridden by Another Source

Baseline:

~~~yaml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 3
~~~

Run from the command line with an invalid value:

~~~bash
java -jar target/config-fail-fast-demo.jar --demo.delivery.max-attempts=10
~~~

The JAR path is illustrative; use your actual built filename. In Spring Boot's standard precedence order, a command-line property can override the file configuration. Because `10` exceeds `@Max(5)`, the application context should reject startup.

Checks when it fails:

- Was the command-line argument passed to the application?
- Is the property name spelled properly?
- Is another source with even higher precedence present?
- Is Bean Validation actually running?

Do not just open the YAML file and say "`max-attempts` is 3 so validation cannot fail". The **effective value** may come from another source.

## 21. Failure Case 10 — Environment Variable Override

Canonical property:

~~~text
demo.delivery.max-attempts
~~~

Common environment variable name:

~~~text
DEMO_DELIVERY_MAXATTEMPTS
~~~

A Unix/Linux shell illustration:

~~~bash
DEMO_DELIVERY_MAXATTEMPTS=8 java -jar target/config-fail-fast-demo.jar
~~~

A PowerShell illustration:

~~~powershell
$env:DEMO_DELIVERY_MAXATTEMPTS = "8"
java -jar .\target\config-fail-fast-demo.jar
Remove-Item Env:DEMO_DELIVERY_MAXATTEMPTS
~~~

With Spring Boot's convention, env names are commonly formed by replacing dots with underscores, removing dashes, and uppercasing. If the application receives `8` from the environment, `@Max(5)` should reject it.

After testing, unset the environment variable or use an isolated test process; if you forget, subsequent cases may keep failing even after the YAML file has been fixed.

Do not use an environment variable containing a real token for a test that prints full diagnostics; secrets can still leak via process inspection, debugging, or logs.

## 22. Failure Case 11 — Importing a Missing Required Configuration Location

In `application.yml`, you might place:

~~~yaml
spring:
  config:
    import: "file:./required-override.properties"
~~~

If `required-override.properties` does not exist at runtime and the import is required, Spring Boot Config Data can reject startup **before the `DeliveryProperties` binding step**.

This is a **Config Data location** error, not an `@NotBlank` error on `endpoint`.

If you write:

~~~yaml
spring:
  config:
    import: "optional:file:./required-override.properties"
~~~

then **absence of the location** may be allowed. However, that does not make properties expected from that location business-optional.

For example, `endpoint` remains required if the properties bean is created and validation is active. A present file location also does not prove every key inside it has a value.

Do not mark every production import as `optional:` just to make startup "pass easily" when a mount/config deployment fails.

## 23. Failure Case 12 — Profile Missing Configuration

For example, the shared file does not have enough values to run:

~~~yaml
# application.yml
spring:
  application:
    name: config-fail-fast-demo
~~~

Local profile:

~~~yaml
# application-local.yml
demo:
  delivery:
    enabled: true
    endpoint: "https://local.example.org/v1/events"
    request-timeout: 5s
    max-attempts: 2
~~~

Prod profile:

~~~yaml
# application-prod.yml
demo:
  delivery:
    enabled: true
    endpoint: "https://delivery.example.org/v1/events"
    request-timeout: 3s
    max-attempts: 3
~~~

Run with the local profile:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=local
~~~

With the prod profile:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=prod
~~~

If no profile is activated and the shared file lacks `demo.delivery.*`, the application can fail when creating the required configuration bean. However, the exact exception also depends on the constructor binding and bean registration path; confirm it through tests.

**Do not put real secrets into `application-prod.yml`** merely because the profile file is only activated in production. The file may still reside in Git/JAR.

## 24. Risk of Multiple Active Profiles

Suppose you run:

~~~bash
java -jar target/config-fail-fast-demo.jar --spring.profiles.active=local,prod
~~~

If both profile files define `demo.delivery.endpoint` or `max-attempts`, the outcome depends on Config Data rules and profile/source ordering in the Spring Boot version in use.

A good workflow:

1. Define which profile combinations are allowed.
2. Avoid accidentally carrying the `local` or `test` profile into production.
3. Record active profiles in release metadata.
4. Maintain integration tests for realistic profile combinations.
5. Verify non-secret effective values.
6. Enforce environment policy in the deployment pipeline.

Validation can verify that individual fields have the right shape, but **it does not automatically enforce profile-combination policy**. If `local` must be forbidden in production, add a deploy-time guardrail or an appropriate startup check.

## 25. Failure Categories to Distinguish at Startup

| Category | Example | Where easily observed |
| --- | --- | --- |
| Config Data loading | Imported file does not exist | Before or during environment preparation |
| Conversion/binding | `max-attempts=many` | Bind exception / conversion cause |
| Bean validation | `endpoint=""`, `max-attempts=9` | Validation failure / constraint details |
| Constructor invariant | `request-timeout=0s` | Exception from constructor |
| Unknown field | `max-attemtps` | Unbound / unknown property handling |
| Bean registration | Forgot scan/enable properties | Missing bean or bean creation error |
| Runtime external failure | API down, credential revoked | Client / health / startup probe depending on design |

Note that failures in the runtime external category may **not** fail startup unless a dedicated startup check exists. A request failing after the service begins serving traffic does not mean the configuration binder was wrong.

A fail-fast test should assert the right failure category. Observing a non-zero process exit code alone is not enough to claim that validation is working.

## 26. Reading Startup Logs Properly

When running with invalid configuration:

1. Identify the first failure related to configuration.
2. Check the property name or prefix the framework was binding.
3. Identify the target Java type.
4. Determine whether the error is a missing value, parse failure, or constraint violation.
5. If the framework reports a file/line origin, inspect that exact source.
6. Check whether an env/CLI override is present.
7. Read the cause chain when the top-level exception only says `BeanCreationException` or `ConfigurationPropertiesBindException`.
8. Do not read only the last few lines and ignore the root cause.
9. Do not copy full logs containing real credentials into tickets/chat.
10. Fix the configuration and restart from a clean state.

Illustrative log example:

~~~text
APPLICATION FAILED TO START

Failed to bind properties under 'demo.delivery'

Property: demo.delivery.max-attempts
Value: 9
Reason: must be less than or equal to 5
~~~

Field names, log formatting, and the exception chain may vary. The program may also produce custom messages from constructor invariants.

## 27. Do Not Rely on a Fixed Error Message String in Tests

Tests should not merely search for the string:

~~~text
APPLICATION FAILED TO START
~~~

because Spring Boot may change its presentation or logger configuration.

Instead:

- Use `ApplicationContextRunner` or an equivalent test context.
- Assert that the context has failed.
- Inspect the startup failure / cause chain.
- Check that the root/cause exception relates to binding/validation.
- Check the reported property name when supported by the API.
- For constructor invariant errors, assert the message defined by your own code.

Also avoid asserting every line of the startup failure report too strictly, since that is a presentation layer rather than a stable API contract of the application.

## 28. Writing Tests with `ApplicationContextRunner`

`ApplicationContextRunner` from `spring-boot-test` creates a small context with property values without opening an HTTP port.

Create `src/test/java/com/example/demo/config/DeliveryPropertiesTests.java`:

~~~java
package com.example.demo.config;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class DeliveryPropertiesTests {

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class Config {}

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(Config.class);

    @Test
    void validConfigurationStarts() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.endpoint=https://delivery.example.org/v1/events",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=3"
        ).run(context -> {
            assertThat(context).hasNotFailed();
            DeliveryProperties props =
                    context.getBean(DeliveryProperties.class);
            assertThat(props.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void missingEndpointFails() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=3"
        ).run(context ->
                assertThat(context).hasFailed());
    }

    @Test
    void retryAboveLimitFails() {
        runner.withPropertyValues(
                "demo.delivery.enabled=true",
                "demo.delivery.endpoint=https://delivery.example.org/v1/events",
                "demo.delivery.request-timeout=5s",
                "demo.delivery.max-attempts=9"
        ).run(context ->
                assertThat(context).hasFailed());
    }
}
~~~

Simple `hasFailed()` checks are a minimum starting point for learning. In real projects, add assertions for **the right cause**; if a validation provider is missing and the context fails due to an unrelated bean error, the test must not be treated as proving the validation logic works.

With JUnit/AssertJ versions properly managed by Spring Boot, run:

~~~bash
./mvnw test
~~~

or:

~~~bash
./gradlew test
~~~

## 29. Testing Wrong Types Independently of Bean Validation

An additional test:

~~~java
@Test
void invalidIntegerFailsDuringConversion() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=many"
    ).run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure()).isNotNull();
    });
}
~~~

Here a binding/conversion failure is expected. For a stronger test, inspect the cause chain and confirm the error relates to `demo.delivery.max-attempts` or conversion to `Integer`.

Do not supply an input that both has a wrong type and misses another field if the test goal is to prove conversion failure. Another error might occur earlier and mask the cause you want to verify.

## 30. Testing Blank Values Separately

~~~java
@Test
void blankEndpointFailsValidation() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=   ",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=3"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

A string property in `ApplicationContextRunner` is provided as a `name=value` pair. For whitespace, ensure the value contains the exact characters you intend to test and verify the behavior of the test property source. You can also add an `endpoint=` test for an empty string.

If a missing or blank endpoint does not fail, check:

- Is `DeliveryProperties` actually being created?
- Is `@Validated` present?
- Is an active Bean Validation provider present?
- Is another property source supplying a value?
- Was the record modified to add a default?
- Did the test inadvertently disable validation?

## 31. Testing Duration Bounds

For the constructor invariant:

~~~java
@Test
void zeroTimeoutFailsEarly() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=0s",
            "demo.delivery.max-attempts=3"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

This test specifically verifies failure from the constructor. If you want to test `@NotNull`, omit the timeout altogether in a separate test.

Do not place `@Positive` on `java.time.Duration` assuming every Bean Validation provider understands that constraint the same way it does for numeric types. Use a custom validator or a constructor invariant for positive-duration rules.

## 32. Testing Unknown Properties

With `ignoreUnknownFields=false`:

~~~java
@Test
void unknownPropertyFails() {
    runner.withPropertyValues(
            "demo.delivery.enabled=true",
            "demo.delivery.endpoint=https://delivery.example.org/v1/events",
            "demo.delivery.request-timeout=5s",
            "demo.delivery.max-attempts=3",
            "demo.delivery.max-attemtps=4"
    ).run(context -> assertThat(context).hasFailed());
}
~~~

The property `max-attemtps` is a typo. Because the test property source has explicit key names, strict unknown-field behavior can detect the unbound key.

If a namespace in a real system is shared across multiple beans, do not apply a strict policy to an overly broad prefix without clear schema ownership.

Testing unknown properties and testing missing properties are two different tasks. A key with a misspelled prefix can sit outside the root and never be seen by the unbound handler.

## 33. Verifying Fail-Fast Behavior When the Entire Root Is Missing

With a baseline containing only:

~~~properties
spring.application.name=config-fail-fast-demo
~~~

where no key under `demo.delivery` exists, determine how the bean is registered and constructed when the entire prefix is absent.

A record whose fields are all required can fail when bound/instantiated/validated, but **do not guess the exception before running tests on your actual Spring Boot version**. Some binding paths when no data exists may not construct the object in the same way as when partial keys are present.

Practical approach:

1. Write an integration test running the app with controlled sources and without `demo.delivery.*`.
2. Assert that startup fails due to configuration.
3. If it does not fail as contracted, add an explicit fail-fast mechanism: a bean requiring the root, a custom precondition, or a targeted startup check.
4. Never let the application silently use a null object or wrong default.
5. Document this case in the deployment runbook.

This is why testing "missing one field" does not replace testing "missing the entire namespace".

## 34. When to Use `@DefaultValue`

An optional setting with a safe default:

~~~java
@ConfigurationProperties(prefix = "demo.retry")
public record RetryProperties(
        @org.springframework.boot.context.properties.bind.DefaultValue("3")
        int maxAttempts
) {}
~~~

When the property is missing, the Binder can supply the default `3`. However:

~~~properties
demo.retry.max-attempts=abc
~~~

will not be silently fixed to `3`. When an input is provided but fails conversion, an error must be reported.

This practice uses required fields, so `DeliveryProperties` has no defaults. If you unconditionally add a default to a required property, a missing-property test may switch from failing to passing and alter the contract.

Rule of thumb:

- Absence is **valid** → consider a default.
- Absence is **an error** → do not mask it with a default.
- Supplied value is **invalid** → validation/conversion reports an error.
- Supplied value is **unbound** → unknown-fields policy / schema check inspects it.

## 35. `ignoreInvalidFields` Is Not a Fix

An anti-pattern:

~~~java
@ConfigurationProperties(
        prefix = "demo.delivery",
        ignoreInvalidFields = true
)
~~~

Setting `ignoreInvalidFields=true` just so invalid configuration stops failing startup can cause the application to run with default values or in an unintended state.

This practice requires **observing the failure** and fixing the source:

- Invalid integer → fix input to a valid integer.
- Invalid duration → fix to a valid duration representation.
- Constraint violation → bring within the allowed range or change policy through review.
- Missing key → provide the key in the proper source.
- Typos → fix the property name.

Never silently switch from fail-fast to ignore-errors in production.

## 36. Identifying the Source Causing the Error

Spring Boot can pull a property from multiple sources. For example:

~~~yaml
demo:
  delivery:
    max-attempts: 3
~~~

Yet the container environment provides:

~~~text
DEMO_DELIVERY_MAXATTEMPTS=9
~~~

When the Binder receives `9`, `@Max(5)` fails. Changing YAML from `3` to `2` does not help if the environment still overrides it with `9`.

To locate the source:

1. Check the deployment manifest / pod template.
2. Check the startup command and allowed system properties.
3. Check Config Data imports and active profiles.
4. Use origin information from the startup failure if provided by the framework.
5. In protected environments, use diagnostics only for allowlisted non-secret fields.
6. Do not expose `/actuator/env` or dump the entire environment just to debug.
7. Fix the source that determines the effective value, not an overridden lower-precedence source.

To verify exact source ordering, consult the Externalized Configuration documentation for the Spring Boot version your project uses.

## 37. Testing Profiles Closer to Production

`ApplicationContextRunner` tests binding with property values, but it does not always recreate the full Config Data pipeline of a `SpringApplication` reading `application-prod.yml`.

Therefore, add an **integration test** or a real run with the profile you want to verify:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=prod
~~~

This syntax uses the Spring Boot Maven plugin parameter in an appropriate project. With Gradle:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=prod'
~~~

Ensure the profile file has complete non-secret configuration and secrets are supplied through an appropriate test source without accessing production credentials from CI.

Cases to test:

- `local` only.
- `prod` only.
- No active profile.
- Permitted profile combinations.
- Profile file missing a key.
- Env var overriding a profile file with an invalid value.
- Missing imported config file.
- Missing or blank secret reference.

The goal is to uncover differences between isolated binding tests and the real Config Data loading pipeline.

## 38. Fail Fast for Secrets Requires Careful Logging

A property may be a secret:

~~~yaml
demo:
  delivery:
    api-token: "${DELIVERY_API_TOKEN}"
~~~

If the secret is required, you can declare `@NotBlank String apiToken` on a properly validated properties bean. When the bean fails, however, do not write:

~~~java
log.error("Bad token value={}", apiToken);
~~~

or:

~~~java
throw new IllegalArgumentException(
        "Invalid token: " + apiToken
);
~~~

Messages should state the property name and rule without echoing the content. In tests, use a dummy sentinel:

~~~text
TEST_ONLY_DELIVERY_TOKEN
~~~

Never use real credentials in unit tests, terminal screenshots, or documentation.

If a deployment uses a secret manager or mounted file, fail-fast checks may include verifying the file/reference and required validation; do not treat the mere presence of a token `String` as proof that upstream authentication will succeed.

## 39. Advanced Example: Conditional Requirements by Feature Mode

Sometimes `endpoint` and a token are only needed when a feature is enabled:

~~~yaml
demo:
  delivery:
    enabled: false
~~~

A record with a conditional invariant:

~~~java
@ConfigurationProperties(prefix = "demo.delivery")
public record DeliveryFeatureProperties(
        boolean enabled,
        String endpoint,
        String apiToken
) {
    public DeliveryFeatureProperties {
        if (enabled) {
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalArgumentException(
                        "demo.delivery.endpoint is required when enabled");
            }
            if (apiToken == null || apiToken.isBlank()) {
                throw new IllegalArgumentException(
                        "demo.delivery.api-token is required when enabled");
            }
        }
    }
}
~~~

In disabled mode, missing endpoint/token can be valid. In enabled mode, they must be non-blank. This condition differs from `DeliveryProperties` in the main lab, where `endpoint` is always required.

If production policy requires the feature to be enabled, do not use a `boolean enabled` that defaults to false and silently runs in NoOp mode. Enforce environment policy and separate deployment tests.

## 40. How to Stop Before Receiving Traffic

Fail-fast configuration validation typically runs while the application context is starting up. For web applications, this helps prevent the application from reaching a ready state when a configuration bean cannot be constructed.

However, in an application with many asynchronous startup tasks or swallowed exceptions:

~~~java
try {
    initializeClient();
} catch (Exception ex) {
    log.warn("Client initialization failed, continuing");
}
~~~

the application may keep running even though a critical integration is not ready.

For critical dependencies:

- Never swallow required configuration exceptions.
- Never fall back to anonymous/stub mode outside policy.
- If a remote connection is a readiness requirement, implement appropriate readiness/health checks.
- Consider avoiding real network connections inside Bean Validation if they make startup slow or brittle.
- Distinguish startup validation (schema/values) from runtime health (dependency readiness).
- Test that orchestration does not route traffic to workloads that are not ready.

In this lab, there are no network calls, so the startup failure cause can be isolated cleanly to configuration.

## 41. Impact in Containers and Orchestration

When a Spring Boot process fails to start due to invalid configuration:

- A local terminal may return a non-zero exit code.
- A Docker container may stop.
- Kubernetes may attempt to restart the container according to its restart policy, leading to repeated startup failures.
- A Deployment may never reach readiness and a rollout may stall or fail.
- Alerting systems may record startup failures or rising restart counts.

Do not address this by increasing restart counts or disabling validation. Fix the configuration value, secret reference, or deployment artifact.

A runbook should record:

~~~text
Application version
Config revision
Active profile
Relevant non-secret property names
Source of override
Root-cause category
Fix / rollback decision
Validation result after redeploy
~~~

Never store plaintext secrets or a full environment dump in incident reports.

## 42. Observing the Process Exit Code

On Linux/macOS, after the process exits:

~~~bash
echo $?
~~~

In PowerShell:

~~~powershell
$LASTEXITCODE
~~~

Normally, an unhandled startup exception causes the program to fail and the launcher returns non-zero. However, if a wrapper/script or IDE catches errors and returns a different code, the observed exit code may not directly reflect the Spring context result.

Therefore combine:

1. Logs / cause chain showing the config failure.
2. Process never reaching ready state.
3. Runner never reporting success.
4. `ApplicationContextRunner` or integration tests failing for the right reason.
5. Deployment not being marked healthy.

Do not write tests asserting "exit code 1 guarantees `endpoint` is missing".

## 43. Quick Troubleshooting Table

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| `endpoint` missing yet app still runs | Bean not registered or validation not running | Check scan/enable, provider, tests |
| `endpoint=""` not rejected | Used `@NotNull` instead of `@NotBlank` | Check constraint |
| `max-attempts=many` errors | Converting String to Integer failed | Inspect conversion cause |
| `max-attempts=9` rejected | Violates `@Max(5)` | Inspect validation |
| `request-timeout=0s` fails | Constructor invariant requires positive | Inspect exception cause |
| `enabled` missing yet app uses false | Primitive or default masked absence | Use `Boolean` + `@NotNull` |
| `max-attemtps` ignored | Unknown-field policy not strict | `ignoreUnknownFields=false` or schema lint |
| YAML valid yet startup fails | Env/CLI override | Locate effective source |
| Imported file does not exist | Required Config Data location | Check `spring.config.import` |
| Optional import masks missing value | `optional:` applies to location | Validate required keys separately |
| `hasFailed()` passes due to unrelated bean | Assertion too broad | Inspect root cause and property name |
| Dev passes yet prod fails | Different profile/secret/overlay | Test profile matrix |
| Prod runs in local mode | Wrong active profile/policy | Add deployment guardrail |
| App keeps restarting in Pod | Unresolved startup failure | Check container logs and config revision |
| Log contains token on failure | Exception or record `toString()` printed secret | Redact and avoid logging values |

## 44. Step-by-Step Practice Checklist

### Preparation

- [ ] App has `@ConfigurationProperties` registered.
- [ ] Bean Validation provider is present.
- [ ] `@Validated` is placed on the properties bean.
- [ ] Required fields use appropriate wrappers and constraints.
- [ ] Positive-Duration invariant is in place.
- [ ] No real credentials appear in files or tests.
- [ ] A valid baseline `application.yml` exists.

### Fault Injection

- [ ] Omit endpoint.
- [ ] Set endpoint to empty string.
- [ ] Set endpoint to whitespace only.
- [ ] Set max-attempts to alphabetic text.
- [ ] Set max-attempts to 0 or above the upper limit.
- [ ] Set request-timeout to an invalid format.
- [ ] Set request-timeout to 0.
- [ ] Omit enabled.
- [ ] Add a misspelled key.
- [ ] Override via env and CLI.
- [ ] Import a missing required file.
- [ ] Test the intended active profile.

### Result Verification

- [ ] Application context failed for every failure case.
- [ ] Failures are classified as conversion / validation / config loading / invariant.
- [ ] Cause chain or property name matches the test case.
- [ ] Runner's startup success log does not appear in failure cases.
- [ ] No secrets appear in logs.
- [ ] After restoring baseline, the application starts cleanly.
- [ ] CI runs the tests against the deployed config artifact/version.

## 45. Extension Exercises

### Exercise 1 — Classification

`max-attempts=many` and `max-attempts=9` both fail. Why do they differ?

**Answer:** `many` cannot be converted to `Integer`; `9` converts successfully but violates `@Max(5)`.

### Exercise 2 — Null and Blank

For `String endpoint`, why is `@NotNull` insufficient?

**Answer:** an empty string or whitespace is not null. Use `@NotBlank` when non-whitespace content is required.

### Exercise 3 — Primitives

`enabled` is missing while the code uses `boolean`. Why might it not fail?

**Answer:** primitives have a default of `false`. When an explicit setting is required, use `Boolean` + `@NotNull`.

### Exercise 4 — Defaults

There is `@DefaultValue("3")` on `maxAttempts`. A missing property can use `3`; will the input `abc` be automatically fixed to `3`?

**Answer:** no. Defaults handle absence, not fixing values of the wrong type.

### Exercise 5 — Profiles

`application-local.yml` has `endpoint`, while `application-prod.yml` does not. Local tests pass, prod fails. Is this a Binder bug?

**Answer:** not necessarily. It may be an unsatisfied environment config contract; either supply the required value for prod or revise the design if `endpoint` is genuinely optional.

### Exercise 6 — Unknown Keys

`max-attemtps=4` is present while `max-attempts=3` is still valid. Why can validation pass?

**Answer:** the validator checks the bound object; it does not automatically inventory every source key. Use strict unknown-fields checking or schema linting to catch typos.

### Exercise 7 — Config Data Imports

`optional:file:missing.properties` does not exist. Why might the application still fail?

**Answer:** `optional` only allows the file location to be absent; required fields on the bean can still be missing and rejected by validation.

### Exercise 8 — Secrets

A missing API token error is handled with `log.error("token="+token)`. Should you do this?

**Answer:** no. Never log secrets or credential contents. Record only the property name, missing/invalid status, and a safe error code.

### Exercise 9 — Testing

A test only asserts `hasFailed()`. How do you ensure it failed due to validation rather than an unrelated error?

**Answer:** inspect `getStartupFailure()` and the cause chain; assert the specific constraint/property the test is targeting.

### Exercise 10 — Runtime Overrides

YAML has `maxAttempts=3` while env has `8`. Where should the fix be made?

**Answer:** find the effective source according to precedence; environment variables can override files. Fix the winning source or the override policy, not just the YAML file.

## 46. A CI/CD Workflow for Checking Fail Fast

A suggested pipeline:

~~~text
Commit app + config changes
         |
         v
Check YAML syntax and secret scan
         |
         v
Compile application
         |
         v
Run ApplicationContextRunner tests
         |
         v
Run profile-specific integration tests
         |
         v
Render environment configuration
         |
         v
Deploy to staging
         |
         v
Smoke/readiness and config diagnostics
         |
         v
Approve canary/production
~~~

If tests fail due to configuration, **halt the pipeline** rather than ignoring them. When a production rollout fails, apply the runbook to fix the configuration or roll back to a known-good app/config artifact.

Never place raw secrets into CI logs or artifacts. For required-token tests, use a dummy sentinel; for production, verify secret references and workload permissions through authorized mechanisms.

A committed configuration revision is not necessarily the final runtime value; controls are needed over env/CLI overrides and Config Data in the target deployment environment.

## 47. Limitations of Fail-Fast Mechanisms

Fail-fast checks via Bean Validation and the Binder are very useful, yet they do not prove the entire application is safe or that every dependency works.

For example:

- An endpoint has a valid URL yet DNS does not resolve.
- A token has content yet has expired.
- An integer is within valid bounds yet unsuitable for real traffic.
- A feature flag is changed dynamically after startup.
- An external configuration source changes while the application is running.
- A required bean is not created due to a faulty registration condition.
- A new ConfigMap has not yet been read by an older container because the Pod has not restarted.
- A secret was readable at startup yet access permissions were later changed.

Therefore, a complete design typically includes:

1. Startup schema/binding validation.
2. Runtime readiness/health checks.
3. Safe logging and metrics.
4. Profile/deployment policy.
5. Realistic integration tests.
6. Configuration revision management.
7. Rollback and incident response.

Do not build an "escape hatch" that catches all config exceptions and presses on if the system must refuse to start when the configuration contract is violated.

## 48. Summary

- **Missing property** differs from **empty/blank**, **wrong type**, **constraint violation**, and **unknown property**.
- `@ConfigurationProperties` creates a typed binding model; `@Validated` with a Bean Validation provider checks constraints.
- Use **`@NotBlank`** for Strings requiring non-whitespace content, **`@NotNull`** for required wrappers/objects, and **`@Min`/`@Max`** for numeric bounds.
- When missing Boolean keys must be detected, use **`Boolean` instead of `boolean`**.
- A type-valid `Duration` is not automatically greater than 0; use a custom constraint or constructor invariant.
- `ignoreUnknownFields=false` helps catch extra keys inside the managed namespace, rather than scanning the entire environment.
- Do not add defaults to mask deployment omissions on required fields.
- `optional:` on a Config Data location does not turn a business property into an optional one.
- **CLI and environment** sources can override YAML files; always verify effective configuration.
- **`ApplicationContextRunner`** suits isolated binding/validation tests; complement it with integration tests for real profiles and Config Data.
- Solid fail-fast behavior should be verified by **context failure with the right cause**, not only a generic message or exit code.
- Never let exceptions or logs expose real credentials when configuration fails.
- In production, fail-fast checks must pair with readiness probes, release policy, and the ability to roll back to a known-working configuration revision.

## References

- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot Reference — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties)
- [Spring Boot Reference — Config Data Imports](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.files.importing)
- [Spring Boot Reference — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot Test — ApplicationContextRunner](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Spring Boot API — ConfigurationProperties](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation.html)
- [Jakarta Bean Validation](https://jakarta.ee/specifications/bean-validation/)
