# `havingValue` in `@ConditionalOnProperty`: Understanding `true`, `false`, and Custom Strings

## 1. Why Does `havingValue` Matter?

In Spring Boot Auto Configuration, an application can enable or disable bean registration using a configuration value. For example, the same data-export module can choose:

- `demo.export.enabled=true`: activate the export integration.
- `demo.export.enabled=false`: do not register the integration.
- `demo.export.mode=async`: select asynchronous processing mode.

The `@ConditionalOnProperty` annotation (package `org.springframework.boot.autoconfigure.condition`) checks values from the Spring `Environment` before Spring decides whether to register the corresponding configuration or bean.

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
ExportService exportService() {
    return new ExportService();
}
~~~

Here, the full key is `demo.export.enabled`. Only when the configuration value matches the string `"true"` does the `@Bean` method participate in bean registration. The snippet above is **only an illustrative excerpt**: to compile standalone, you must define `ExportService` and place it inside a configuration class; a runnable test example is in section 6.

The easiest mistake to make: **`havingValue` is a `String`**, not a Java boolean flag. Omitting `havingValue` is **not equivalent** to setting `havingValue="true"`.

## 2. Exact Matching Rules

Spring Boot 3.3 describes the rules based on the property value found in `Environment`:

| Property value | Default: `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="async"` |
| --- | :---: | :---: | :---: | :---: |
| `true` | Match | Match | No | No |
| `false` | No | No | Match | No |
| `async` | Match | No | No | Match |
| `sync` | Match | No | No | No |
| `0` | Match | No | No | No |
| `off` | Match | No | No | No |
| Empty string `""` when property **exists** | Match | No | No | No |
| Property **does not exist** | No* | No* | No* | No* |

*The last row assumes `matchIfMissing=false` (default). If `matchIfMissing=true` is used, a missing property can make the condition match regardless of what `havingValue` is declared; see section 4.

### 2.1. Omitting `havingValue`: "exists and not `false`"

~~~java
@ConditionalOnProperty(prefix = "demo.export", name = "enabled")
~~~

The default rule is:

> The key `demo.export.enabled` must be present, and its string value must not equal `"false"` (case-insensitive).

Therefore `true`, `yes`, `on`, `1`, `async`, `enabled`, and an empty string (if the key actually exists) **all match**. The annotation does not convert `yes/on/1` into boolean `true`; they simply **are not the string `false`**.

This can become a configuration bug: if a user types `demo.export.enabled=tru`, a default condition still matches. Do not use the default condition when the requirement truly demands boolean `true`.

### 2.2. `havingValue="true"`: accepts only the string `true`

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
~~~

Result:
- `demo.export.enabled=true` or `TRUE` → matches.
- `demo.export.enabled=false` → does not match.
- `demo.export.enabled=on`, `1`, `yes`, `tru`, `enabled` → does not match.
- Key is missing → does not match by default.

This is the clear choice for feature flags that must be turned on **intentionally**.

### 2.3. `havingValue="false"`: activates a branch when disabled

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "false"
)
~~~

Here the value `false` makes the **condition match**, because that is the expected value. There is no contradiction: the condition checks a string, rather than asking "is the feature enabled?".

A reasonable use case is registering a supporting bean or fallback implementation *when configuration explicitly declares* `enabled=false`. Remember: **a missing key** is not the same as `false`. To handle the missing-key case, evaluate `matchIfMissing` and design a separate default branch.

### 2.4. `havingValue="async"`: application-defined string

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "mode",
    havingValue = "async"
)
~~~

- `mode=async` or `mode=ASYNC` → matches.
- `mode=sync`, `mode=true`, `mode=false`, or missing property → does not match.
- `havingValue="async,scheduled"` does **not** mean "async **or** scheduled": it compares against a single whole string `async,scheduled`.

In Spring Boot 3.3, the value comparison part of the condition is case-insensitive. You should not rely on automatic whitespace trimming or typo correction: `mode=async ` may not be treated as the same value `async`, depending on how the configuration source supplies the string. Use normalized values and test actual configuration sources.

## 3. How Spring Boot Evaluates the Condition

Conceptual equivalent:

~~~text
key = prefix + "." + name
if key is not in Environment:
    return matchIfMissing
if havingValue is not empty string:
    return compare value with havingValue, case-insensitive
else:
    return value differs from "false", case-insensitive
~~~

This is an **algorithmic description**, not Java code to copy into a project.

Important consequences:

1. Spring Boot retrieves the property from `Environment` and the applicable precedence sources, such as `application.properties`/`application.yml`, environment variables, or command-line arguments. If the same key appears in multiple places, the condition receives the **effective value by precedence** from `Environment`, rather than reading each file separately for all values.
2. Comparison is based on the **string representation of the value**. This is not a boolean check under conventions like "`0` = false", "`on` = true".
3. The condition is evaluated when Spring prepares the context and registers beans. After beans have been created, changing a value in a configuration file does not cause the condition to re-run automatically to add/remove beans in the current context.
4. If a property exists with an empty value, it differs from a non-existent property. With `havingValue=""`, an empty string still matches because it differs from `false`.
5. With `havingValue="false"`, the property `FALSE` also matches. With `havingValue="async"`, `ASYNC` matches. Case-insensitivity here applies to **value** comparison; key naming should still follow conventions.

## 4. Combining `matchIfMissing`, `prefix`, and `name`

### 4.1. Missing property: `matchIfMissing` decides

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

This configuration matches if:
- `demo.export.enabled=true`; **or**
- `demo.export.enabled` does not exist in `Environment` at all.

However, `demo.export.enabled=false` still **does not match**, because the key exists and its value is not `true`.

This is a **default-on** strategy. It can fit features that are enabled by default, but carries a risk when an operator misspells a key name: a missing property accidentally still enables the feature. For resource-intensive functions, those with external side effects, or those requiring explicit opt-in, `havingValue="true", matchIfMissing=false` is usually chosen.

In particular, `matchIfMissing` **only** applies when the property is absent. It does not turn a wrong value like `enabled=maybe` into a default match.

### 4.2. Joining property names

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = "enabled",
    havingValue = "true"
)
~~~

Corresponding property:

~~~properties
demo.export.enabled=true
~~~

`prefix="demo.export"` can be written with a trailing dot; Spring Boot appends the separator dot when needed. `name` and `value` are alias attributes in `@ConditionalOnProperty`: either can be used to specify property names. Keys should follow **lowercase-kebab-case**, e.g., `demo.export.fast-mode` (instead of camelCase when declared in the annotation).

### 4.3. Multiple property names mean AND

~~~java
@ConditionalOnProperty(
    prefix = "demo.export",
    name = {"enabled", "audit-enabled"},
    havingValue = "true"
)
~~~

The condition matches only when **both** keys `demo.export.enabled` and `demo.export.audit-enabled` have the value `true`. If one key is `false` or missing (and `matchIfMissing=false`), the condition does not match.

`havingValue` is applied to **all** listed names. If keys need **different values**, such as `enabled=true` and `mode=async`, structure separate appropriate conditions (for example, a configuration class conditioned on one key and a bean method conditioned on another, or a custom `Condition`), rather than stuffing two names into one annotation with a single `havingValue` and expecting each name to have its own value.

## 5. Real Configuration with `application.yml` and `application.properties`

YAML configuration:

~~~yaml
demo:
  export:
    enabled: true
    mode: async
~~~

Equivalent by keys to check:

~~~properties
demo.export.enabled=true
demo.export.mode=async
~~~

An auto-configuration can define branches per mode:

~~~java
@AutoConfiguration
class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.export", name = "mode", havingValue = "async"
    )
    ExportEngine asyncExportEngine() {
        return new AsyncExportEngine();
    }

    @Bean
    @ConditionalOnProperty(
        prefix = "demo.export", name = "mode", havingValue = "sync"
    )
    ExportEngine syncExportEngine() {
        return new SyncExportEngine();
    }
}
~~~

This is **illustrative architectural code**: `ExportEngine`, `AsyncExportEngine`, and `SyncExportEngine` must be implemented in the application or library. With `mode=async`, only the async branch matches; with `mode=sync`, only the sync branch matches; with `mode=unknown` or missing mode, neither branch matches unless a default is designed. If another bean always requires `ExportEngine`, add configuration value validation or explicitly provide a default branch.

In a real application, decide whether `enabled` governs both modes. **Checking `mode` alone is not enough to express the `enabled=true` requirement.** You can apply `@ConditionalOnProperty(prefix="demo.export", name="enabled", havingValue="true")` on the enclosing configuration class, and then apply the `mode` condition on each `@Bean`.

## 6. Runnable Test: Proving Each Case

This example runs with **Java 17+ and Spring Boot 3.3**, in a Gradle/Maven project that already has `spring-boot-starter-test` (JUnit 5, AssertJ, `ApplicationContextRunner`). Create file:

`src/test/java/com/example/demo/HavingValueConditionTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class HavingValueConditionTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    @AutoConfiguration
    static class FeatureAutoConfiguration {

        @Bean("defaultEnabled")
        @ConditionalOnProperty(prefix = "demo.feature", name = "enabled")
        String defaultEnabled() {
            return "default";
        }

        @Bean("strictEnabled")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled", havingValue = "true"
        )
        String strictEnabled() {
            return "strict";
        }

        @Bean("whenDisabled")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled", havingValue = "false"
        )
        String whenDisabled() {
            return "disabled";
        }

        @Bean("asyncMode")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "mode", havingValue = "async"
        )
        String asyncMode() {
            return "async";
        }

        @Bean("defaultOn")
        @ConditionalOnProperty(
                prefix = "demo.feature", name = "enabled",
                havingValue = "true", matchIfMissing = true
        )
        String defaultOn() {
            return "default-on";
        }
    }

    @Test
    void missingProperty_usesMatchIfMissingOnly() {
        runner.run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isFalse();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isFalse();
            assertThat(context.containsBean("defaultOn")).isTrue();
        });
    }

    @Test
    void trueProperty_matchesDefaultAndStrictTrue() {
        runner.withPropertyValues(
                "demo.feature.enabled=true",
                "demo.feature.mode=async"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isTrue();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isTrue();
            assertThat(context.containsBean("defaultOn")).isTrue();
        });
    }

    @Test
    void falseProperty_matchesOnlyExplicitFalse() {
        runner.withPropertyValues(
                "demo.feature.enabled=FALSE",
                "demo.feature.mode=sync"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isFalse();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isTrue();
            assertThat(context.containsBean("asyncMode")).isFalse();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }

    @Test
    void arbitraryText_matchesDefaultButNotStrictTrue() {
        runner.withPropertyValues(
                "demo.feature.enabled=on",
                "demo.feature.mode=ASYNC"
        ).run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("asyncMode")).isTrue();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }

    @Test
    void emptyExistingValue_isNotMissing() {
        runner.withPropertyValues("demo.feature.enabled=").run(context -> {
            assertThat(context.containsBean("defaultEnabled")).isTrue();
            assertThat(context.containsBean("strictEnabled")).isFalse();
            assertThat(context.containsBean("whenDisabled")).isFalse();
            assertThat(context.containsBean("defaultOn")).isFalse();
        });
    }
}
~~~

Run in a project with Gradle wrapper and test dependency as stated:

~~~bash
./gradlew test --tests "com.example.demo.HavingValueConditionTest"
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests "com.example.demo.HavingValueConditionTest"
~~~

**Expected result:** 5 tests PASS. Assertions directly verify whether beans are registered by name; they do not require specific stdout. For `enabled=on`, the default bean is present while `strictEnabled` is absent: that is the core distinction of this lesson. With `enabled=FALSE`, `whenDisabled` is present; with mode `ASYNC`, `asyncMode` is present due to case-insensitive comparison. The beans returning `String` are simply minimal test objects to isolate condition behavior from business logic.

`@AutoConfiguration` in the test is supplied directly to `ApplicationContextRunner` via `AutoConfigurations.of(...)`, so no imports registration file is needed for this test fixture. If packaged into a real auto-configuration for Spring Boot auto-discovery, register the corresponding class in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

## 7. Common Errors and How to Diagnose

| Symptom | Common cause | Solution |
| --- | --- | --- |
| `enabled=on` still creates the bean when expecting only `true` to enable it | `havingValue` left empty, which by default only rejects the string `false` | Use `havingValue="true"` for strict boolean flags |
| `enabled=false` yet a bean using `havingValue="false"` appears | You required **matching the exact value false** | Only use that configuration for the "disabled" branch; use `havingValue="true"` for the "enabled" branch |
| Property not configured and bean does not appear | Default `matchIfMissing=false` | Add the property with the exact key; only set `matchIfMissing=true` when truly needing default-on |
| Wanting `mode=async` or `mode=queue` but writing `havingValue="async,queue"` | `havingValue` does not parse lists of values | Use a custom condition or split branches by design |
| Multiple keys in `name` and only one matches | The condition requires all names to match | Inspect each key and value, and check `matchIfMissing` |
| Configuring one way but condition receives a different value | A higher-precedence property source overrode it | Check the effective value in `Environment`/config data and precedence order |
| Using `@ConditionalOnProperty` for a list/indexed property | Parent property and indexed keys may not be seen uniformly | Use `@ConfigurationProperties`/custom `Condition` for complex data |
| Editing config file while app is running but beans do not change | Conditions are only evaluated during context creation | Restart the context or design a dedicated runtime state-change mechanism |

When debugging auto-configuration, you can enable `debug=true` or pass `--debug` to view the **Condition Evaluation Report**. With Spring Boot Actuator properly configured, the `/actuator/conditions` endpoint can also show matched/unmatched conditions. During testing, use `ApplicationContextRunner.withPropertyValues(...)` to build a matrix of values instead of running just one passing configuration.

## 8. Practical Design Principles

- **Boolean feature flags:** prefer `@ConditionalOnProperty(name = "...", havingValue = "true")` when an exact `true` value is needed. Use `matchIfMissing=true` only when the business logic genuinely wants enabled-by-default.
- **Explicit off branch:** `havingValue="false"` means "the key exists and its value is false", **not** a default representation covering a missing key as well.
- **String-based modes:** use `havingValue="async"` or `"sync"` for a fixed value; if a mode has multiple branches, define handling for invalid or missing cases. For complex configuration, consider `@ConfigurationProperties`, enums, and validation to catch errors early.
- **Separate existence from value:** checking whether a property exists differs from checking a boolean or matching a mode; writing `havingValue` explicitly helps readers understand the intent.
- **Do not assume input formatting:** `yes`, `1`, `on`, and empty string do not mean boolean `true` under `havingValue="true"`. They may, however, cause the default condition to match.
- **Test negative cases too:** for each important condition, verify `true`, `false`, custom strings, missing keys, and unexpected values.

## Official References

- [Spring Boot 3.3 — JavaDoc `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): `havingValue` table, `matchIfMissing`, `prefix`, `name` attributes, collection caveat.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): Property Conditions section and testing with `ApplicationContextRunner`.
