# Reading `Environment` to Decide Activation and Using Properties Objects to Configure Beans

## 1. Why Separate These Two Responsibilities?

When writing a library or Spring Boot auto-configuration, two questions typically arise together:

1. **Should the bean be created at all?** For example, only activate the HTTP client when `demo.remote.enabled=true` and `demo.remote.protocol=http`.
2. **If created, how should it be configured?** For example, endpoint as a `URI`, timeout as a `Duration`, and retry attempts as an `int`.

These two questions belong to **two different moments** in the startup lifecycle:

- A `Condition` reads data from `Environment` while Spring evaluates whether to register configurations/beans. At this point, you must not assume the configuration bean has already been created and bound.
- Once conditions match and configuration is registered, Spring Boot can bind keys into a `@ConfigurationProperties` object. The `@Bean` method receives a strongly typed object, checks validity, and constructs the business bean.

Use `Environment` for **activation decisions**, and use `@ConfigurationProperties` to convert **configuration data** into Java types. This design is especially useful for libraries shared across many applications: only applications that actually enable the feature get the library's beans.

> Both `Environment` and `@ConfigurationProperties` read from Spring Boot's externalized configuration system; the main differences are **purpose**, **API**, and **lifecycle stage**. Both mechanisms can be applied together in a single auto-configuration.

## 2. Execution Flow of an Auto-Configuration

Suppose a library provides `RemoteClient` and reads these keys:

```yaml
demo:
  remote:
    enabled: true
    protocol: http
    endpoint: https://api.example.test/v1
    timeout: 1500ms
    max-attempts: 4
```

We want the following rule:

```text
Environment:
    demo.remote.enabled == true
    AND demo.remote.protocol == "http"
             |
             v
        Condition.matches() ?
             |
       +-----+-----+
       |           |
      NO          YES
       |           |
 Do not register  Register configuration
 default bean         |
                      v
         @EnableConfigurationProperties
         binds demo.remote → RemoteProperties
                      |
                      v
         @Bean RemoteClient(RemoteProperties)
         endpoint: URI
         timeout: Duration
         maxAttempts: int
```

The important distinction:

| Question | Appropriate tool | Result |
|---|---|---|
| Should the feature be enabled? | `@ConditionalOnProperty` or custom `Condition` with `Environment` | `true`/`false` at condition evaluation time |
| Which source holds the property? | `Environment` and `PropertySource`/configuration reports | Effective value by source precedence |
| What types are endpoint/timeout? | `@ConfigurationProperties` and Spring Boot Binder | Type-converted `URI`, `Duration`, `int` |
| Is required configuration missing? | Validation on properties or checks during bean creation | Specific configuration error instead of a misconfigured bean |
| Did the user provide a replacement bean? | `@ConditionalOnMissingBean` | Default bean backs off for the custom bean |

`@ConditionalOnMissingBean` is used here because the library's goal also includes **backing off when the user already created a bean**. It is independent of the decision to enable the feature via `Environment`.

## 3. When Is `@ConditionalOnProperty` Alone Enough?

If the only requirement is an `enabled=true` flag, use the built-in annotation:

```java
@ConditionalOnProperty(
    prefix = "demo.remote",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

How to read it:

- `prefix` and `name` form the key `demo.remote.enabled`.
- `havingValue="true"` requires the value to match `true`; avoids treating any value other than `false` as enabled.
- `matchIfMissing=false` ensures an absent key does not auto-enable; this is the right choice for **opt-in** features.
- The annotation does not check endpoint, timeout, optional libraries, or user beans on its own.

The snippet above is an **illustrative annotation**, which must be placed on a configuration class or `@Bean` method. You can add `@ConditionalOnClass` and `@ConditionalOnMissingBean` if the problem requires them.

Only when the activation rule is more complex—such as checking **both enabled and protocol**—should you consider a custom `Condition`. Do not write a custom Condition for a simple boolean flag.

## 4. Reading `Environment` in a Custom `Condition`

A custom `Condition` must implement `org.springframework.context.annotation.Condition` and accept `ConditionContext`. From this context, obtain `Environment`:

```java
package demo;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.env.Environment;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class EnabledHttpCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Environment env = context.getEnvironment();

        boolean enabled = Boolean.TRUE.equals(
                env.getProperty("demo.remote.enabled", Boolean.class, false)
        );

        String protocol = env.getProperty(
                "demo.remote.protocol", "http"
        );

        return enabled && "http".equalsIgnoreCase(protocol.trim());
    }
}
```

The file `src/main/java/demo/EnabledHttpCondition.java` is a **standalone Java class** that compiles when the classpath includes Spring Framework and the appropriate Spring Boot starter.

Meaning of each part:

1. `context.getEnvironment()` retrieves property data for the context being processed. Data can come from `application.yml`, `application.properties`, profiles, environment variables, system properties, or command-line arguments.
2. `getProperty("demo.remote.enabled", Boolean.class, false)` requests converting the value to `Boolean` and defaults to `false` when the key is missing. `Boolean.TRUE.equals(...)` enables only when `true` is read.
3. `getProperty("demo.remote.protocol", "http")` defaults to HTTP if protocol is not declared; this is a **domain decision** in the example, not a universal default for every library.
4. `"http".equalsIgnoreCase(protocol.trim())` requires the intended protocol while tolerating case differences and surrounding whitespace.
5. Do not call `context.getBeanFactory().getBean(RemoteProperties.class)` to fetch a properties bean before deciding: the bean may not yet be registered or bound when the condition runs.

**Invalid data case:** `Boolean` conversion in `Environment` can throw an error if the value cannot be converted. Do not automatically treat every invalid configuration as "feature disabled" and hide operational errors. If the library needs specialized error reporting, define explicit behavior for invalid values and write matching tests.

### Are Conditions Re-Evaluated When Config Files Change?

`Condition` is evaluated during application context construction, mainly when registering configurations and beans. Editing a file or environment variable **after the context is created** does not automatically re-run all conditions to add/remove beans. Dynamic runtime toggling requires a different design.

## 5. Using `@ConfigurationProperties` to Receive Typed Data

Operational keys `endpoint`, `timeout`, and `max-attempts` should be bound into an object, rather than repeating `environment.getProperty(...)` in every bean creation method.

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo.remote")
public class RemoteProperties {

    private URI endpoint;
    private Duration timeout = Duration.ofSeconds(2);
    private int maxAttempts = 3;

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public void setTimeout(Duration timeout) {
        this.timeout = timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }
}
```

Place the file at `src/main/java/demo/RemoteProperties.java`. This is a complete Java class with JavaBean setters; the Spring Boot Binder uses the default constructor and setters to bind.

When reading the YAML in section 2:

| Configuration key | Java property | Result |
|---|---|---|
| `demo.remote.endpoint` | `URI endpoint` | `URI.create("https://api.example.test/v1")` |
| `demo.remote.timeout` | `Duration timeout` | `Duration.ofMillis(1500)` |
| `demo.remote.max-attempts` | `int maxAttempts` | `4` |
| Missing `timeout` | Initialized value | `Duration.ofSeconds(2)` |
| Missing `max-attempts` | Initialized value | `3` |

The name `max-attempts` binds to `maxAttempts` thanks to Spring Boot's **relaxed binding**. `Duration` is converted per the Binder's duration support; write explicit units (`ms`, `s`,...) to avoid misinterpretation.

In this example, `enabled` and `protocol` are **keys used solely for activation decisions**, so they do not strictly need fields in `RemoteProperties`. By default the Binder ignores keys sharing the prefix that do not match Java properties; client creation data is declared using only the needed fields. If the application needs to inspect enabled/disabled status at runtime, you can opt to add corresponding fields, but **never use the properties bean to decide a condition before it is created**.

### Why Not Use `@Value` Everywhere?

`@Value` is reasonable for a few isolated values, whereas multiple settings sharing a prefix are more convenient with `@ConfigurationProperties` because it provides clear field grouping, relaxed binding, type conversion, validation, and IDE metadata support. Do not mix both approaches haphazardly to the point where one key is read under two different names.

## 6. Wiring Both Parts Together in Auto-Configuration

Create `src/main/java/demo/RemoteAutoConfiguration.java`:

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;

@AutoConfiguration
@Conditional(EnabledHttpCondition.class)
@EnableConfigurationProperties(RemoteProperties.class)
public class RemoteAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RemoteClient.class)
    RemoteClient remoteClient(RemoteProperties properties) {

        URI endpoint = properties.getEndpoint();
        Duration timeout = properties.getTimeout();
        int maxAttempts = properties.getMaxAttempts();

        if (endpoint == null || !endpoint.isAbsolute()) {
            throw new IllegalArgumentException(
                    "demo.remote.endpoint must be an absolute URI"
            );
        }
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw new IllegalArgumentException(
                    "demo.remote.timeout must be positive"
            );
        }
        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "demo.remote.max-attempts must be >= 1"
            );
        }

        return new RemoteClient(endpoint, timeout, maxAttempts);
    }
}
```

This file is a **complete auto-configuration class**, building on the `EnabledHttpCondition` and `RemoteProperties` classes shown above, along with the `RemoteClient` class below.

```java
package demo;

import java.net.URI;
import java.time.Duration;

public final class RemoteClient {

    private final URI endpoint;
    private final Duration timeout;
    private final int maxAttempts;

    public RemoteClient(URI endpoint, Duration timeout, int maxAttempts) {
        this.endpoint = endpoint;
        this.timeout = timeout;
        this.maxAttempts = maxAttempts;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }
}
```

Create `src/main/java/demo/RemoteClient.java`. This is a **simulated configuration-holding client** meant for testing auto-configuration behavior; it makes no network calls and assumes no real API protocol. In a real application, the constructor can pass these values to an HTTP client/SDK.

### Why Are the Annotations Placed Where They Are?

- `@Conditional(EnabledHttpCondition.class)` on the **auto-configuration class** means that when it does not match, Spring Boot does not process the beans declared in this configuration.
- `@EnableConfigurationProperties(RemoteProperties.class)` registers binding support and the properties bean when the configuration is processed. `@ConfigurationProperties` **does not create a bean merely by sitting on a class**; a registration mechanism such as `@EnableConfigurationProperties`, scanning, or a bound `@Bean` is required.
- `@Bean remoteClient(RemoteProperties properties)` receives **already-bound properties** via dependency injection, rather than re-reading individual strings from `Environment`.
- `@ConditionalOnMissingBean(RemoteClient.class)` lets the application register a custom `RemoteClient` before auto-configuration; the default will back off.
- Checking endpoint/timeout/attempts belongs to **configuration validity**, not the feature-activation check. The example uses fail-fast checks in the bean method for clarity; in a real library, `@Validated` and Jakarta Bean Validation can be used to declare constraints explicitly.

When creating a starter using Spring Boot 3.x, declare the auto-configuration's FQCN in:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Corresponding content:

```text
demo.RemoteAutoConfiguration
```

Because this is a library auto-configuration, **do not rely on component scanning** to load it. In direct tests, `AutoConfigurations.of(RemoteAutoConfiguration.class)` registers the configuration so it does not depend on the imports file.

## 7. Standalone Test Example with `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

To keep the code runnable, the test below uses **the exact four production files from sections 4–6** and one test file at `src/test/java/demo/RemoteAutoConfigurationTest.java`. The project already contains `RemoteClient`, `RemoteProperties`, `EnabledHttpCondition`, and `RemoteAutoConfiguration` in package `demo`.

```java
package demo;

import java.net.URI;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RemoteAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(RemoteAutoConfiguration.class)
                    );

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        RemoteClient customRemoteClient() {
            return new RemoteClient(
                    URI.create("https://user.example.test"),
                    Duration.ofSeconds(5),
                    8
            );
        }
    }

    @Test
    void enabledHttpBindsTypedConfiguration() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http",
                        "demo.remote.endpoint=https://api.example.test/v1",
                        "demo.remote.timeout=1500ms",
                        "demo.remote.max-attempts=4"
                )
                .run(context -> {
                    assertTrue(context.containsBean("remoteClient"));
                    RemoteClient client = context.getBean(RemoteClient.class);
                    assertEquals(
                            URI.create("https://api.example.test/v1"),
                            client.getEndpoint()
                    );
                    assertEquals(
                            Duration.ofMillis(1500), client.getTimeout()
                    );
                    assertEquals(4, client.getMaxAttempts());
                });
    }

    @Test
    void missingEnabledDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void falseEnabledDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=false",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void otherProtocolDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=grpc",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void blankProtocolDoesNotActivate() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol= ",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context ->
                        assertFalse(context.containsBean("remoteClient"))
                );
    }

    @Test
    void omittedProtocolAndOptionalSettingsUseDefaults() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context -> {
                    RemoteClient client = context.getBean(RemoteClient.class);
                    assertEquals(
                            Duration.ofSeconds(2), client.getTimeout()
                    );
                    assertEquals(3, client.getMaxAttempts());
                });
    }

    @Test
    void userClientMakesDefaultBackOff() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http",
                        "demo.remote.endpoint=https://api.example.test"
                )
                .run(context -> {
                    assertTrue(context.containsBean("customRemoteClient"));
                    assertFalse(context.containsBean("remoteClient"));
                    assertEquals(
                            URI.create("https://user.example.test"),
                            context.getBean(RemoteClient.class).getEndpoint()
                    );
                });
    }

    @Test
    void enabledWithoutRequiredEndpointFailsFast() {
        runner.withPropertyValues(
                        "demo.remote.enabled=true",
                        "demo.remote.protocol=http"
                )
                .run(context ->
                        assertNotNull(context.getStartupFailure())
                );
    }
}
```

### Meaning of the Eight Tests

| Test | Verification |
|---|---|
| `enabledHttpBindsTypedConfiguration` | Condition matches; properties object is bound to `URI`, `Duration`, `int`; bean receives exact values |
| `missingEnabledDoesNotActivate` | Missing flag → bean is not created |
| `falseEnabledDoesNotActivate` | Flag off → bean is not created |
| `otherProtocolDoesNotActivate` | Non-HTTP protocol → bean is not created |
| `blankProtocolDoesNotActivate` | Blank protocol → not mistaken for HTTP |
| `omittedProtocolAndOptionalSettingsUseDefaults` | When enabled=true, protocol defaults to HTTP; timeout and maxAttempts take JavaBean defaults |
| `userClientMakesDefaultBackOff` | User bean is kept, default bean backs off |
| `enabledWithoutRequiredEndpointFailsFast` | Feature enabled without required config → meaningful startup failure, does not silently become disabled |

**Final note:** the fail-fast test only asserts `getStartupFailure()` is not `null`; in a real project, check the expected exception type/cause to distinguish configuration failures from other failures. These tests only illustrate expected correctness; they are not output from a run in this project.

### Dependencies and Run Commands

For a Gradle Spring Boot 3.3.x project already using the corresponding plugin/management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run on Linux/macOS:

```bash
./gradlew test --tests demo.RemoteAutoConfigurationTest
```

Run on Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.RemoteAutoConfigurationTest
```

With the exact four classes and one test in package `demo`, **the expected result is 8 passing tests**. File names and public class names in sections 4–6 must match per Java rules; do not put multiple `public class` definitions into a single source file.

## 8. `Environment` and Binder May View Properties Differently

### 8.1. Sources and Precedence

Spring Boot aggregates external configuration into `Environment`. Sources may include `application.yml`, `application.properties`, profiles, environment variables, system properties, and command-line arguments. The final value is governed by **property source precedence**. Therefore the `enabled` flag read by a condition must be the **effective value in the running context**, not necessarily one line you see in a single file.

For example, an initial `enabled=false` configuration may be overridden to `true` by a higher-precedence source. When diagnosing unexpected feature activation, check property sources and precedence before editing code.

### 8.2. Relaxed Binding and Property Names

For `@ConfigurationProperties`, Spring Boot supports relaxed binding, allowing a key like `max-attempts` to populate the `maxAttempts` field. When reading `Environment` directly, use **canonical kebab-case property names** to depend less on how the config source formats names.

Do not rely on `Environment#getProperty("demo.remote.maxAttempts")` assuming it is always equivalent to the Binder processing `demo.remote.max-attempts` across every `PropertySource` type. A properties object is a better home for multiple typed values.

### 8.3. Lists and Nested Objects

If a library needs a list of endpoints, proxies, or complex retry strategies, `@ConfigurationProperties` can bind `List`/nested POJOs under its own rules. A `Condition` calling `Environment#getProperty("demo.remote.servers")` **is not guaranteed** to see a parent key when data is declared as `demo.remote.servers[0]`. For conditions based on **list contents** (for example, having valid elements), use `Binder` inside a custom condition and inspect the bound data; do not infer from a scalar property.

### 8.4. Do Not Instantiate Beans Inside Conditions

Do not directly call `getBean(...)` or `new RemoteProperties()` inside `matches()`:

- `getBean(...)` can force premature bean initialization, or the bean may not exist yet at condition evaluation time.
- `new RemoteProperties()` only gives default fields and **does not bind** external configuration values.
- Injecting `RemoteProperties` into a `Condition` constructor is not standard: conditions do not go through normal dependency injection lifecycles like service beans.
- A custom `Condition` needing complex typed data should use `Binder.get(context.getEnvironment())`; use this only when structured data truly needs to be evaluated during the decision step.

## 9. Validation, Safety, and Configuration Consistency

**Rule 1 — Missing required data must produce a clear error.** If a feature is enabled without declaring an endpoint, silently disabling it hides operational errors. Validate inside the bean method as in the example, or use `@Validated` and Jakarta Bean Validation on `@ConfigurationProperties` (requiring a validation implementation on the classpath, usually via the validation starter).

**Rule 2 — Do not treat `enabled=true` as "all configuration is valid."** The condition only answers whether it is enabled. Endpoints need valid schemes, timeouts must be positive, and retries must stay within valid bounds. Keep the boundary between "enabled" and "valid configuration" clear.

**Rule 3 — Do not log the entire properties object if it holds credentials.** `@ConfigurationProperties` may store API keys or passwords. When diagnosing issues, avoid printing `toString()` on properties if it contains sensitive information; Actuator `env`/`configprops` endpoints must be secured and have data-masking policies.

**Rule 4 — Back off on the right bean type.** In library auto-configuration, users may want to replace the `RemoteClient` implementation. Place `@ConditionalOnMissingBean(RemoteClient.class)` on the bean method and keep the `RemoteClient` return signature clear. If there are multiple client types/interfaces, identify the exact abstraction users are permitted to override.

**Rule 5 — Auto-configuration ordering affects bean conditions.** `@ConditionalOnMissingBean` inspects definitions already processed; when a library depends on beans from another auto-configuration, use `@AutoConfiguration(after=...)` or `afterName` if necessary. Reading `Environment` generally does not depend on bean registration order, but **can** depend on when custom property sources are added to the context.

**Rule 6 — Distinguish conversion errors from missing keys.** The Binder can fail on `timeout=abc` or an invalid URI. Do not catch all errors and fall back to defaults, because the application might run with dangerous or unintended values.

## 10. Common Mistakes

1. **Using `@ConfigurationProperties` to decide whether to register the properties bean itself.** Condition evaluation time and binding time differ. Make simple activation decisions with `@ConditionalOnProperty` or a custom `Condition` reading `Environment`.
2. **Reading `Environment` directly for every field and passing strings.** Loses type safety and scatters parsing/validation logic; use a properties object in `@Bean`.
3. **Assuming `@ConfigurationProperties` self-registers a bean.** When writing library auto-configuration, use `@EnableConfigurationProperties(RemoteProperties.class)` or an appropriate mechanism; the class annotation only describes binding.
4. **Setting `matchIfMissing=true` for an opt-in feature.** The feature may activate even without declaring the flag. Use the default `false` when explicit enablement is required.
5. **Omitting `havingValue="true"` when only `true` should be allowed.** With `@ConditionalOnProperty`, by default any value other than `false` can cause the condition to match.
6. **Confusing Spring profiles with flag values.** Profiles help select configuration sources; a profile by itself does not prove a feature was enabled via `enabled=true`.
7. **Creating the bean and checking `enabled` in the constructor.** The check comes too late: the bean may already be registered, triggering dependencies or side effects before code aborts. Decide at conditional registration time.
8. **Forgetting invalid config checks when `enabled=true`.** An enable flag should lead to clear validation, not silently fall back to a broken default bean.
9. **Assuming property changes after startup will add/remove beans.** Conditions are mainly evaluated when the context is built; dynamic changes require a separate mechanism.
10. **Placing conditions on configurations not ordered properly.** For bean conditions and other auto-configurations, ensure proper registration order; do not assume a future bean already exists.

## 11. Diagnosing When a Bean Is Not Created or Misconfigured

Ask in order:

1. **Activation condition?** What are the effective values of `demo.remote.enabled` and `demo.remote.protocol` in `Environment`?
2. **Which source overrides?** Did a profile file, environment variable, system property, or CLI argument alter the application's value?
3. **Did it pass the condition?** Pass `--debug` when starting Boot to view the **Condition Evaluation Report**. If Spring Boot Actuator is present and accessible, `/actuator/conditions` shows match/no-match reasons.
4. **Are properties registered?** Check `@EnableConfigurationProperties`, package scanning, or `@Bean` methods; `@ConfigurationProperties` alone is not enough.
5. **Did types bind properly?** Confirm `endpoint` became a `URI`, `timeout` became a `Duration`, and `max-attempts` became an `int`; inspect any binding errors.
6. **Library bean or user bean?** `@ConditionalOnMissingBean` can suppress the default bean because the user supplied `RemoteClient`; that is valid behavior.
7. **Were negative scenarios actually tested?** Test missing flag, `false`, other protocols, blank values, missing endpoint, and replacement beans.

On applications with Actuator, `/actuator/env` and `/actuator/configprops` can help verify configuration values and bound objects. They require appropriate exposure and access protection; avoid leaking secrets when sharing reports.

## 12. Takeaways for Stable Library Design

- **`Environment`/`Condition`:** answers **"Should auto-configuration activate?"** at condition evaluation time.
- **`@ConfigurationProperties`:** answers **"What typed values configure the bean?"** after config is registered and binding runs.
- For a single flag, prefer **`@ConditionalOnProperty`**. For complex rules, use **`ConditionContext#getEnvironment()`**, or `Binder` if structured data must be inspected.
- **`@EnableConfigurationProperties`** registers the properties class inside auto-configuration. Never require applications to component-scan the library's internal packages.
- **`@ConditionalOnMissingBean`** lets users override the default bean while keeping the configuration mechanism.
- **Validation and a test matrix** catch both unintended activation and invalid configuration; never test only a single happy path.
- This design fits Spring Boot 3.3.x and Java 17+, while avoiding tying startup decisions to service instantiation time.

### Official Documentation

- Spring Boot 3.3 Reference — Externalized Configuration, `Environment`, `@ConfigurationProperties`, and relaxed binding: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 Javadoc — `ConditionalOnProperty`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 Javadoc — `ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Framework 6.1 Javadoc — `ConditionContext`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html
