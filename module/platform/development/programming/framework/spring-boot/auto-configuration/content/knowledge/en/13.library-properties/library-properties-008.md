# Designing Required Properties When a Feature Is Enabled and Behavior When Disabled

## 1. The Problem: "Required" Must Depend on Enabled vs. Disabled State

A Spring Boot library often provides an optional feature: sending notifications over HTTP, exporting reports to an external service, integrating with a storage repository, or syncing data. The feature needs a few properties to operate, such as `endpoint` and `api-key`. Yet if users **do not enable** that integration, forcing them to declare every property anyway will cause applications unrelated to the integration to fail startup.

Desired configuration contract:

- When `demo.notify.enabled=true`: a valid HTTPS endpoint and non-blank API key must be present; if missing/invalid, **fail fast** at startup, clearly identifying which property needs fixing. Only when valid does the library register the beans serving the feature.
- When `demo.notify.enabled=false`: the library **does not create** integration beans, does not validate properties meant only for the integration, and does not initialize clients, schedulers, connection pools, or open connections for that integration.
- When `demo.notify.enabled` is omitted: this example chooses **disabled by default** (`opt-in`), so behavior matches `false`. This is a library API decision, not a mandatory choice for every library.
- When the toggle key has an invalid value such as `tru`: it must **report invalid configuration**, avoiding silently disabling the feature due to a typo.
- When the user provides a custom bean: clarify whether the library backs off the default bean and whether required properties are still validated.

The goal of this lesson is not just adding `@NotBlank`; what matters is designing the right **boundary between auto-configuration registration conditions, binding, and validation**. Examples use Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+.

## 2. Three Distinct Questions in a Property Library

Separate three steps conceptually:

1. **Should the feature be enabled?** Read the `enabled` flag from `Environment` and decide whether to participate in integration configuration.
2. **When enabled, is the data valid?** Bind property keys into a `@ConfigurationProperties` object, checking for missing, blank, wrong-typed, and domain constraints.
3. **When data is valid, which components are created?** Register clients, adapters, filters, listeners, or schedulers based on valid properties; typically add `@ConditionalOnMissingBean` if users should be able to override.

These are three separate responsibilities. A property sitting on the classpath or present in YAML does not prove the feature is enabled. Likewise, omitting `endpoint` is not an error if the integration is disabled per contract.

Decision diagram:

```text
Environment: demo.notify.enabled
                |
                v
      Valid enable flag parsed?
         | no -> FAIL configuration
         v yes
  true ----------------------------- false or absent
   |                                        |
   v                                        v
Activate integration config          Skip integration section
   |                                 Do not bind/validate
   v                                 required properties
Bind endpoint/api-key                       |
   |                                        v
   +-- missing/invalid --> FAIL      No client created by
   |                                 auto-configuration
   v
Validate HTTPS endpoint,
non-blank api-key
   |
   +-- error --> FAIL
   |
   v
Register NotificationClient
(if no user override)
```

Distinguish **invalid configuration errors in ON mode** from **valid behavior in OFF mode**. If a library both errors on a missing token when OFF and creates a default client, both its conditions and lifecycle are broken.

## 3. Designing Keys and Default Values

Example notification library `demo.notify`:

| Property | Type | Default / contract | When ON | When OFF |
| --- | --- | --- | --- | --- |
| `demo.notify.enabled` | boolean | `false` (opt-in) | Must express a valid enabled value | `false` or absent |
| `demo.notify.endpoint` | `URI` | No default | **Required**, absolute HTTPS URI with host | Not required, unused |
| `demo.notify.api-key` | `String` | No default | **Required**, non-null / non-empty / non-whitespace | Not required, unused |

Two illustrative configurations:

**Enabled, complete data:**

```yaml
demo:
  notify:
    enabled: true
    endpoint: https://notify.example.test/api
    api-key: demo-token
```

`demo-token` is only a dummy value for the lab. In real deployments, supply secrets from a secret store/environment variables and never commit tokens into the repository.

**Disabled, integration keys unnecessary:**

```yaml
demo:
  notify:
    enabled: false
```

You can omit the entire `demo.notify` branch because the design defaults to off. A file containing `enabled: false` alongside an old/malformed `endpoint` must still start up normally **if required properties are bound only when ON**. If another independent component uses the same prefix, evaluate it separately; this example considers only beans registered by the library.

Never give `endpoint` or tokens fake default values just "so the app can start" when enabled. With real external connections, dangerous defaults hide misconfiguration or make clients connect to the wrong target. Default values belong to **optional** settings such as timeouts, retry counts, or batch sizes.

### 3.1. Choosing the Meaning of Omitting `enabled`

`@ConditionalOnProperty` has two important settings:

```java
@ConditionalOnProperty(
    prefix = "demo.notify",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false)
```

Here:

- `prefix` and `name` combine into `demo.notify.enabled`.
- `havingValue="true"` requires the config value to match `true`; arbitrary strings like `foo` are rejected.
- `matchIfMissing=false` forces **an absent flag** to not match the condition.
- Using only `@ConditionalOnProperty(prefix="demo.notify", name="enabled")` without `havingValue` defaults to accepting any value other than `false`; a typo could accidentally enable the feature. Always specify `havingValue` explicitly.
- Switching to `matchIfMissing=true` lets the feature auto-enable when the flag is absent; that is a **default-on** contract, carrying the requirement to supply mandatory data even when the user does not specify `enabled`.

Behavior table of **the condition above** (before flag validation):

| Value of `enabled` in Environment | Condition ON? | Meaning |
| --- | :---: | --- |
| Absent | No | Default OFF |
| `true` | Yes | Activates required configuration |
| `false` | No | OFF |
| `foo`, `tru` | No | Condition rejects; **not yet a configuration error** |
| `"true"` as YAML string | Yes | Value once read means true |

Key point: `@ConditionalOnProperty` is a **condition filter**, not a strict boolean validator. Relying on this annotation alone can cause `tru` to be treated the same as OFF. Section 5 shows how to validate the flag's type independently.

## 4. Why Misplaced `@NotBlank` Breaks Applications in OFF Mode

Suppose you write:

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record NotifyProperties(
        boolean enabled,
        @NotNull URI endpoint,
        @NotBlank String apiKey) {
}
```

and register it globally:

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifyProperties.class)
public class NotifyAutoConfiguration {
}
```

**These two snippets illustrate an unsuitable design** when `endpoint`/`apiKey` are only required when ON. `@EnableConfigurationProperties` registers the configuration bean to bind and validate **regardless of ON/OFF**. In `enabled=false` mode with endpoint and key absent, `@NotNull` and `@NotBlank` can still cause startup to fail.

Similarly, if `@ConfigurationPropertiesScan` in the application actively scans and registers `NotifyProperties`, adding `@ConditionalOnProperty` onto **each client `@Bean`** does not stop a props bean registered elsewhere from being bound/validated.

An insufficient design:

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifyProperties.class)
class BrokenNotifyAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.notify",
            name = "enabled",
            havingValue = "true")
    NotificationClient notificationClient(NotifyProperties properties) {
        return new NotificationClient(
                properties.endpoint(), properties.apiKey());
    }
}
```

The condition controls only **the client bean**. It does not control the existence of `NotifyProperties` registered at the class level. The result can be **OFF yet failing startup due to missing keys**.

There are two sensible designs depending on requirements:

1. **Split the toggle flag and required properties into two classes**, registering the required class only inside a conditional nested configuration. This is the approach used for this lesson's runnable example; it is easy to read and keeps the OFF boundary clean.
2. **Bind an always-present object yet validate conditionally** using custom Bean Validation such as `@AssertTrue` or a custom validator: allow empty integration fields when OFF, require them when ON. This is useful if the application needs to read the status alongside options in one object, though the object is still bound when OFF; type conversion errors on an optional field can still occur even if the validator ignores that field.

There is no mandatory rule that "every library must use two classes"; what matters is a **clear, verified policy**: OFF does not require keys, and ON cannot run with missing/invalid keys.

## 5. Sustainable Pattern: Always Validate the Flag, Bind Required Properties Only When ON

The complete pattern below separates:

- `NotifySwitchProperties`: holds only the `enabled` flag, registered **always** so it parses as a real boolean; a typo like `tru` causes a conversion/binding failure instead of silently turning OFF.
- `EnabledNotifyProperties`: exists only when the ON condition holds, containing required endpoint and token; bound and validated before the client consumes it.
- `NotifyAutoConfiguration.EnabledConfiguration`: nested configuration guarded by `@ConditionalOnProperty` right at **the class level**, so when OFF it does not bring the required props bean into the context.
- `NotificationClient`: simulated adapter bean receiving validated data; the constructor in the example makes **no** network connections for standalone testing.

### 5.1. Typed Flag, Default OFF

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record NotifySwitchProperties(
        @DefaultValue("false") boolean enabled) {
}
```

`@DefaultValue` is `org.springframework.boot.context.properties.bind.DefaultValue`. Because the record has a single canonical constructor, Spring Boot 3.3 automatically supports constructor binding when the bean is registered via `@EnableConfigurationProperties`; `@ConstructorBinding` is unnecessary.

Some implications:

- `enabled` has a typed `boolean` value; the binder knows the boolean representations supported by the conversion service and will fail on unparseable values.
- `@DefaultValue("false")` explicitly documents the library's policy even when the key is absent.
- The switch object declares no `endpoint`/`apiKey`, so they are not bound into the switch. This is crucial in OFF mode.
- Even though the condition already has `havingValue="true"`, the typed switch bean remains useful for catching mistyped enable inputs. Condition and binding are two independent mechanisms.

### 5.2. Required Properties Registered Only in the ON Branch

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record EnabledNotifyProperties(
        @NotNull URI endpoint,
        @NotBlank String apiKey) {

    @AssertTrue(message = "endpoint must be an absolute HTTPS URI with a host")
    public boolean isHttpsEndpoint() {
        return endpoint != null
                && "https".equalsIgnoreCase(endpoint.getScheme())
                && endpoint.getHost() != null;
    }
}
```

`@NotNull` checks that `endpoint` has a value; the binder is responsible for converting strings to `URI`. `@NotBlank` blocks missing, empty, and whitespace-only tokens. `@AssertTrue` adds a **semantic** constraint: `URI.create("relative/path")` is syntactically a valid URI yet unsuitable as a server endpoint; the example requires an HTTPS scheme and host.

Path, port, allowlist, or token expiration rules can be added if the product needs them, but avoid using an overly complex regex instead of standard URI checks. Constraints actually run only if a **Bean Validation provider** is on the classpath, such as `spring-boot-starter-validation`, and the properties bean is registered so the binder invokes validation.

### 5.3. Placing the Condition at the Exact Configuration Boundary

```java
@AutoConfiguration
@EnableConfigurationProperties(NotifySwitchProperties.class)
public class NotifyAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.notify",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @EnableConfigurationProperties(EnabledNotifyProperties.class)
    static class EnabledConfiguration {

        @Bean
        @ConditionalOnMissingBean(NotificationClient.class)
        NotificationClient notificationClient(
                EnabledNotifyProperties properties) {

            return new NotificationClient(
                    properties.endpoint(),
                    properties.apiKey());
        }
    }
}
```

This is a **structural illustration snippet**; complete declarations and actual imports are provided in section 7 as a runnable test file.

Mechanism in sequence:

1. Spring Boot processes `NotifyAutoConfiguration`. `NotifySwitchProperties` is registered to bind the declared flag, catching mistyped `enabled` values.
2. Spring evaluates the condition on `EnabledConfiguration`. If `enabled` is absent or `false`, the nested configuration does not participate. Because `@EnableConfigurationProperties(EnabledNotifyProperties.class)` **sits inside**, the required properties bean is not registered from this auto-configuration either.
3. If `enabled=true`, Spring registers `EnabledNotifyProperties`; the binder converts the URI, and Bean Validation checks constraints.
4. If properties are missing/invalid, context creation fails before a live `NotificationClient` exists. Never log a warning and silently proceed with a null token.
5. If data is valid, the default client bean is created provided no other `NotificationClient` bean exists and all remaining conditions pass.

Note: `@ConditionalOnMissingBean` **does not** change the required props contract of this pattern. Even if the user supplies their own `NotificationClient`, if `enabled=true` then `EnabledNotifyProperties` is still registered/validated. This is a consistent "when feature is enabled, config must be valid" policy, even when the client bean is overridden. If a product wants **a user override to skip required props too**, you must move the missing-bean condition up to the nested configuration level (or split branches) and test user-bean discovery order; never silently change this behavior.

### 5.4. How Exact Is OFF?

Under the design above, OFF means:

- No `NotificationClient` created by this **auto-configuration**.
- No `EnabledNotifyProperties` registered by this **auto-configuration**.
- No endpoint/key required and no validation for those two fields.
- No connections or schedulers created by the library for this feature.
- `NotifySwitchProperties` (a lightweight bean holding only the flag) may still exist, as it serves validation of the flag itself.
- If the consuming application **independently declares** a `NotificationClient` bean, auto-configuration must not delete that bean: "OFF" is a promise about what **the library** manages, not a license to delete application beans.
- Properties are not erased from `Environment`; an OFF configuration may still contain old keys. "Not bound/not used" does not mean "absent from configuration text."

For integrations with schedulers, listeners, or filters, the condition must cover **that entire group of beans**. Disabling only the client while letting a scheduler keep dispatching into a missing client or letting a health indicator open connections fails the OFF contract.

## 6. Error Cases to Handle When ON

| Case when `enabled=true` | Detection layer | Correct behavior |
| --- | --- | --- |
| Missing `endpoint` | Bean Validation `@NotNull` | Startup fails, clearly naming the missing config field |
| `endpoint=relative/path` | Validation `@AssertTrue` | Startup fails because it is not an absolute HTTPS URL |
| `endpoint=http://...` | Validation `@AssertTrue` | Startup fails because policy allows only HTTPS |
| Malformed URI, converter cannot parse | Binding/conversion | Startup fails, preserving conversion cause |
| Missing `api-key` | Bean Validation `@NotBlank` | Startup fails |
| `api-key="   "` | Bean Validation `@NotBlank` | Startup fails |
| Flag `enabled=tru` | Typed binding `NotifySwitchProperties` | Startup fails due to unparseable boolean |
| `enabled=false` with missing endpoint/token | Required props not registered | Startup succeeds, feature is not created |
| Absent `enabled` and other keys | Default OFF | Startup succeeds |
| `enabled=true`, complete endpoint/key | Binding + validation pass | Creates default bean or yields to user bean per contract |

**Fail fast** here means failing while building the context, before business flows actually use the integration. Some errors are only discovered during real network calls—DNS, TLS, HTTP 401, timeouts, temporary endpoint outages—and fall outside configuration validation. Never attempt to fire HTTP requests inside Bean Validation to "test the endpoint": doing so makes startup depend on the network and creates unwanted side effects.

Further distinctions:

- **Conversion failure**: a string cannot convert to the Java type, e.g., letters entered into an `Integer` port field or a malformed URI.
- **Constraint violation**: type bound successfully yet violates the contract, e.g., disallowed `http://` URI, whitespace-only apiKey.
- **Condition no-match**: feature is off so nested configuration is not registered. This is not a startup failure.

## 7. Runnable Practice with Java 17 and Spring Boot 3.3

The test uses `ApplicationContextRunner` to spin up an isolated context for each state. It opens no HTTP connections; `NotificationClient` is merely a record describing the configured client. All tests share the same classpath, varying only properties and user beans to verify ON/OFF.

### 7.1. Project Structure

```text
conditional-required-properties-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ConditionalRequiredPropertiesTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'conditional-required-properties-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-validation:3.3.13'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

test {
    useJUnitPlatform()
}
```

Only JDK 17+ and a compatible Gradle version are needed; the standard Java plugin suffices for tests. `-parameters` retains parameter names when the framework needs constructor inference. Artifacts from `spring-boot-starter-validation` supply the Jakarta Validation provider so `@NotNull`, `@NotBlank`, and `@AssertTrue` take effect.

### 7.2. Complete JUnit 5 File

`src/test/java/demo/ConditionalRequiredPropertiesTest.java`:

```java
package demo;

import java.net.URI;

import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.annotation.Validated;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalRequiredPropertiesTest {

    @ConfigurationProperties(prefix = "demo.notify")
    public record NotifySwitchProperties(
            @DefaultValue("false") boolean enabled) {
    }

    @Validated
    @ConfigurationProperties(prefix = "demo.notify")
    public record EnabledNotifyProperties(
            @NotNull URI endpoint,
            @NotBlank String apiKey) {

        @AssertTrue(message =
                "endpoint must be an absolute HTTPS URI with a host")
        public boolean isHttpsEndpoint() {
            return endpoint != null
                    && "https".equalsIgnoreCase(endpoint.getScheme())
                    && endpoint.getHost() != null;
        }
    }

    public record NotificationClient(URI endpoint, String apiKey) {
    }

    @AutoConfiguration
    @EnableConfigurationProperties(NotifySwitchProperties.class)
    public static class NotifyAutoConfiguration {

        @Configuration(proxyBeanMethods = false)
        @ConditionalOnProperty(
                prefix = "demo.notify",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        @EnableConfigurationProperties(EnabledNotifyProperties.class)
        static class EnabledConfiguration {

            @Bean
            @ConditionalOnMissingBean(NotificationClient.class)
            NotificationClient notificationClient(
                    EnabledNotifyProperties properties) {
                return new NotificationClient(
                        properties.endpoint(),
                        properties.apiKey());
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserClientConfiguration {

        @Bean
        NotificationClient customNotificationClient() {
            return new NotificationClient(
                    URI.create("https://custom.example.test/api"),
                    "custom-test-token");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(NotifyAutoConfiguration.class));

    @Test
    void absentFlagMeansDisabledAndRequiresNoIntegrationSettings() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context).hasSingleBean(NotifySwitchProperties.class);
            assertThat(context.getBean(NotifySwitchProperties.class).enabled())
                    .isFalse();
            assertThat(context).doesNotHaveBean(EnabledNotifyProperties.class);
            assertThat(context).doesNotHaveBean(NotificationClient.class);
        });
    }

    @Test
    void explicitFalseIgnoresInvalidUnusedEndpointAndMissingKey() {
        runner.withPropertyValues(
                "demo.notify.enabled=false",
                "demo.notify.endpoint=%%%")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).doesNotHaveBean(EnabledNotifyProperties.class);
                    assertThat(context).doesNotHaveBean(NotificationClient.class);
                });
    }

    @Test
    void trueWithValidSettingsCreatesExactlyOneClient() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=https://notify.example.test/api",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(EnabledNotifyProperties.class);
                    assertThat(context).hasSingleBean(NotificationClient.class);
                    assertThat(context).hasBean("notificationClient");
                    assertThat(context.getBean(NotificationClient.class).endpoint())
                            .isEqualTo(URI.create(
                                    "https://notify.example.test/api"));
                    assertThat(context.getBean(NotificationClient.class).apiKey())
                            .isEqualTo("demo-token");
                });
    }

    @Test
    void trueWithoutEndpointFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void trueWithBlankKeyFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=https://notify.example.test/api",
                "demo.notify.api-key=   ")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void trueWithNonHttpsEndpointFailsStartup() {
        runner.withPropertyValues(
                "demo.notify.enabled=true",
                "demo.notify.endpoint=http://notify.example.test/api",
                "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void malformedEnableFlagFailsRatherThanSilentlyDisabling() {
        runner.withPropertyValues("demo.notify.enabled=tru")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure()).isNotNull();
                });
    }

    @Test
    void userDefinedClientReplacesDefaultWhenEnabledAndConfigured() {
        runner.withUserConfiguration(UserClientConfiguration.class)
                .withPropertyValues(
                        "demo.notify.enabled=true",
                        "demo.notify.endpoint=https://notify.example.test/api",
                        "demo.notify.api-key=demo-token")
                .run(context -> {
                    assertThat(context.getStartupFailure()).isNull();
                    assertThat(context).hasSingleBean(NotificationClient.class);
                    assertThat(context).hasBean("customNotificationClient");
                    assertThat(context).doesNotHaveBean("notificationClient");
                    assertThat(context.getBean(NotificationClient.class).apiKey())
                            .isEqualTo("custom-test-token");
                });
    }
}
```

Run from the project directory (with Gradle installed):

```bash
gradle test --tests demo.ConditionalRequiredPropertiesTest
```

If a wrapper is present on Linux/macOS:

```bash
./gradlew test --tests demo.ConditionalRequiredPropertiesTest
```

On Windows:

```powershell
.\gradlew.bat test --tests demo.ConditionalRequiredPropertiesTest
```

**Expected result:** `test` completes with **8 tests passed** when JDK and dependencies are compatible. This is the expected result from the example's design; do not treat Gradle build logs or stdout as fixed and do not claim the test suite was actually executed on the learner's machine.

### 7.3. Explanation Table for the Eight Tests

| Test | Flag | Data | Expected |
| --- | --- | --- | --- |
| `absentFlag...` | Missing | No endpoint/key | Startup OK, no client |
| `explicitFalse...` | false | Broken endpoint, missing key | Startup OK, required props not bound |
| `trueWithValid...` | true | HTTPS + token | Startup OK, exactly one client |
| `trueWithoutEndpoint...` | true | Missing endpoint | Startup FAIL (validation) |
| `trueWithBlankKey...` | true | Whitespace-only token | Startup FAIL (validation) |
| `trueWithNonHttps...` | true | Syntactically valid HTTP violating policy | Startup FAIL (validation) |
| `malformedEnableFlag...` | `tru` | No key needed | Startup FAIL (typed flag binding) |
| `userDefinedClient...` | true | HTTPS + token and user bean | Startup OK, user client only |

The first test is crucial: it proves default OFF **is not constrained** by required configuration. The second test goes further: when `endpoint` contains a string `URI` cannot parse, no `EnabledNotifyProperties` bean exists, so no conversion error is raised from unused settings. The seventh test catches a flag typo—a hazard commonly missed when using `@ConditionalOnProperty` alone.

The last test illustrates the boundary of `@ConditionalOnMissingBean`: it makes the default client yield to the user bean. **This pattern still validates required props when enabled**, matching the stated policy. Never assume overriding the client automatically exempts you from validation.

## 8. Comparing Three Conditional Validation Design Options

| Design | OFF missing endpoint/key | ON missing endpoint/key | Pros | Limitations |
| --- | --- | --- | --- | --- |
| Globally registered `@Validated @ConfigurationProperties` with `@NotBlank` | Risks FAIL | FAIL | Simple code | Fails to express "required only when ON" |
| **Split switch + required properties inside nested conditional config** | PASS | FAIL | Neither binds nor validates required fields when OFF; clear ownership | Adds one class and requires care not to register props elsewhere |
| Single always-bound properties bean, custom `@AssertTrue` checking `!enabled || fieldsValid` | PASS if values are convertible | FAIL | Reads entire config from one object | Invalid conversion can FAIL when OFF; must test every logic branch |
| Catch exception during client creation, log and ignore | Can PASS | Violates fail-fast | Looks quick to implement | Hides operational errors, can leave beans/features in a half-baked state |

For libraries where OFF means **not using** any integration configuration, splitting classes is a strong choice. For products that need to expose the full configuration even when OFF, you can choose a single properties bean and a custom validator, but must decide how to handle unconvertible data when OFF.

### 8.1. Conditional Requirements Inside One Object

Another simple design (**illustrative** code, not a replacement for the test suite in section 7):

```java
@Validated
@ConfigurationProperties(prefix = "demo.notify")
public record CombinedNotifyProperties(
        boolean enabled,
        String endpoint,
        String apiKey) {

    @AssertTrue(message =
            "endpoint and apiKey are required when notify is enabled")
    public boolean isValidWhenEnabled() {
        if (!enabled) {
            return true;
        }
        return endpoint != null && !endpoint.isBlank()
                && apiKey != null && !apiKey.isBlank();
    }
}
```

This class can allow OFF with blank endpoint/key. However, a `String` endpoint still needs separate parsing/scheme validation when ON; switching the field to `URI` means an unparseable value can cause **binding to fail even when OFF**. That is the trade-off of always binding the same object. For complex multi-field conditional checks, a dedicated class-level constraint can report clearer errors than `@AssertTrue`.

## 9. Notes When Using Bean Overrides and Multiple Auto-Configurations

In real libraries, `@ConditionalOnMissingBean` and auto-config ordering matter:

- Spring Boot processes user application beans before auto-configuration in typical setups, so user overrides are usually recognized.
- If multiple auto-configs provide the same type, declare `@AutoConfiguration(after=...)` or `before` when they depend on bean presence/absence results.
- Conditions on nested configurations should target the actual contract type of the feature. If a client declares too broad a return type such as `Object`, `@ConditionalOnMissingBean(NotificationClient.class)` may fail to see the candidate as expected.
- When the feature is OFF, a custom client bean from the application can still exist. Never pretend "OFF deletes every bean in the JVM"; govern only beans owned by auto-configuration.
- If the policy is "a user bean replaces the feature completely, so endpoint/key are not required," wrap **the required properties section too** with the missing-bean condition. That alters the startup contract, so you must test: ON + user client + missing settings, ON + no user client + missing settings, ON + user client + valid settings.
- Do not let two separate branches accidentally create two `NotificationClient` beans; asserting `hasSingleBean` along with bean names catches this bug.

Example idea for placing conditions on the nested class (this is an **annotation fragment**, not a complete source file):

```java
@ConditionalOnProperty(
        prefix = "demo.notify", name = "enabled", havingValue = "true")
@ConditionalOnMissingBean(NotificationClient.class)
@EnableConfigurationProperties(EnabledNotifyProperties.class)
```

If you apply this variant, class-level `@ConditionalOnMissingBean` must be verified against auto-configuration and consumer bean registration order. Do not scatter conditions everywhere arbitrarily and treat two different contracts as equivalent.

## 10. Observing Conditions and Binding Errors in Spring Boot

Two complementary sources of information:

1. **Condition evaluation:** Why was the nested configuration `EnabledConfiguration` enabled/skipped? Use `ConditionEvaluationReport`, `--debug` logs, or Actuator `/actuator/conditions` (when enabled/exposed). Look for `OnPropertyCondition` referencing `demo.notify.enabled`.
2. **Binding/validation failure:** When ON with missing/invalid data, look at `Failed to bind properties under 'demo.notify'`, `BindException`, or Bean Validation property/reason details. The condition may have matched, yet the context still fails while creating the properties bean.

In a test context that started successfully, you can retrieve the report:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (source.contains("EnabledConfiguration")) {
                System.out.println(source);
                outcomes.forEach(item -> System.out.println(
                        item.getCondition().getClass().getSimpleName()
                        + ": matched=" + item.getOutcome().isMatch()
                        + ", reason=" + item.getOutcome().getMessage()));
            }
        });
```

This is an **illustrative snippet inside an `ApplicationContextRunner` callback**, requiring `import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` and the runner's `context` variable. It has no fixed stdout; condition reasons vary by environment. When startup FAILS, prioritize binding/validation error messages and startup failure rather than only looking for a report from a context that failed to initialize.

Diagnostic table:

| Symptom | Check first | Conclusion if confirmed |
| --- | --- | --- |
| OFF yet failing on missing token | Is `EnabledNotifyProperties` registered globally or scanned? | Required properties are not gated properly |
| ON without client, yet startup OK | `OnPropertyCondition`, `havingValue`, property name, and user override | Condition did not match or default bean backed off to user bean |
| ON with invalid key yet startup OK | Are `@Validated` and a validation provider present? Was the props bean created? | Validation was not triggered properly |
| `enabled=tru` yet startup OK, feature OFF | Is a typed switch bean always bound? | Flag was merely ignored by the condition, type not validated |
| OFF yet still opening network connections | Is another scheduler/health check/bean causing side effects? | Feature scope was not fully gated |
| ON fails on invalid URI | Binder conversion or custom URI constraint | Fail-fast is working |
| Startup FAILS even though user client overrode it | Does policy require props whenever ON, or only when creating default client? | Decide contract and shift condition boundary if you want to change it |

Never write secret values to the console during debugging. Spring Boot Actuator `/actuator/configprops` has sanitization mechanisms, yet still requires careful access control and secret handling; tests/logs should use dummy keys and avoid `toString()` on records containing real tokens.

## 11. Implementation Notes for Published Libraries

1. **Register auto-configuration per Boot 3.x standards.** In the published module, list the fully qualified class name of `NotifyAutoConfiguration` in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. The test uses `AutoConfigurations.of(...)` to import directly without needing the imports file; real applications have different requirements.
2. **Isolate packages/control scanning.** Do not let applications accidentally scan and register `EnabledNotifyProperties` globally when it is meant to be gated. Use `@EnableConfigurationProperties` inside the conditional nested class; if the framework/application has broad `@ConfigurationPropertiesScan`, verify whether this class gets scanned separately.
3. **Do not use `@Component` on constructor-bound record properties.** Spring Boot recommends registering via `@EnableConfigurationProperties` or configuration-properties scanning; constructor-bound records are not synonymous with ordinary Spring constructor injection.
4. **Pick a stable prefix.** Use lowercase/kebab-case names under the library namespace; the property name in `@ConditionalOnProperty` should use the canonical form, avoiding two synonymous flags that are hard to maintain.
5. **Secure tokens.** Prefer environment variables, secret managers, and protected configuration; never store real tokens in READMEs, test snapshots, or condition logs.
6. **No side effects in validation.** Validators should check pure configuration constraints. Networking and authentication are runtime concerns; if a separate startup probe is needed, it must have an explicit retry/timeout/failure policy.
7. **Keep reload policies separate.** `@ConditionalOnProperty` at bootstrap does not create a dynamic on/off toggle. Changing a property at runtime does not re-apply auto-configuration or create/destroy beans. If the library needs hot toggling, design dedicated lifecycle management and test state transitions.
8. **Validation provider dependency.** The library needs a way to document the `spring-boot-starter-validation` dependency or equivalent Jakarta Validation provider. Never assume `jakarta.validation` annotations alone suffice to enforce every constraint.
9. **Document both sides.** Operational guides must state the default of `enabled`, the list of fields required only when ON, error types when missing, how to keep OFF so deployments do not depend on the integration, and the user-override policy.
10. **Add IDE metadata if packaging a library.** The Spring Boot configuration processor can generate metadata for `@ConfigurationProperties`, helping IDEs suggest property names/types; metadata does not replace validation or conditions.

## 12. QA Checklist for the ON/OFF Contract

- [ ] When flag is missing and endpoint/key are absent: application starts, no feature bean exists.
- [ ] When flag is `false`, endpoint has syntax errors, and key is missing: application still starts, because required props are not bound.
- [ ] When flag is `true` and endpoint is missing: startup fails with a configuration error, no active client exists.
- [ ] When flag is `true` and token is blank/whitespace-only: startup fails.
- [ ] When endpoint has wrong scheme/host: startup fails with a meaningful constraint error.
- [ ] When flag is misspelled: startup fails (if the design promises strict boolean parsing).
- [ ] When ON and valid: exactly one client/adapter is registered.
- [ ] When a user bean exists: bean back-off and properties validation behave per the documented contract.
- [ ] When OFF: no schedulers, listeners, connection beans, or background tasks remain auto-registered by the feature.
- [ ] Verified class-level condition with `@ConditionalOnProperty`, not just on the client factory method.
- [ ] Confirmed `EnabledNotifyProperties` is not scanned/registered via another path.
- [ ] No "fake default" values for endpoint or token to bypass errors when ON.

**Key takeaway:** a property is truly **required only when a feature is enabled** only if registration, binding, and validation all reflect that condition. For opt-in features, the clean solution is validating the toggle flag independently, placing required properties inside a nested configuration guarded by `@ConditionalOnProperty`, failing fast when ON is misconfigured, and ensuring OFF constructs no integration components. Tests must prove both **the created case** and **the intentionally-not-created case**, along with policies for invalid flags or data.

## Official Documentation

- Spring Boot 3.3 — Externalized Configuration: constructor binding, `@EnableConfigurationProperties`, and validation: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration, Property Conditions, and testing: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 API — `@ConditionalOnProperty` and `havingValue` / `matchIfMissing` table: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html
- Spring Boot 3.3 API — `@ConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationProperties.html
- Spring Boot 3.3 API — `@EnableConfigurationProperties`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/EnableConfigurationProperties.html
- Spring Boot 3.3 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
