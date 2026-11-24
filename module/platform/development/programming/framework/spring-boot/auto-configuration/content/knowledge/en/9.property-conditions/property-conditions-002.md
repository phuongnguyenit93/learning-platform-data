# @ConditionalOnProperty: Default Meaning When Property Exists and Value Is Not `false`

## Lesson Objectives

In Spring Boot Auto Configuration, `@ConditionalOnProperty` decides whether a configuration or a bean is registered based on a property value in `Environment`. This lesson focuses on the **default behavior**: when `havingValue` and `matchIfMissing` are not specified, the condition matches only if the property **exists** and its value **differs from the string `false` (case-insensitive)**.

After this lesson, you can read the condition accurately; predict outcomes for a missing property, `true`, `false`, or an arbitrary string; distinguish the default from `havingValue="true"` and `matchIfMissing=true`; and write tests to verify actual behavior.

## 1. Why Are Property-Based Conditions Needed?

A library may provide event logging, notification sending, or an integration module. Applications need to enable/disable features through configuration rather than modifying source code.

Example of a bean registered only when the configuration `demo.audit.enabled` satisfies the condition:

~~~java
@AutoConfiguration
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
    AuditSink auditSink() {
        return event -> "AUDIT: " + event;
    }
}
~~~

This is an **illustrative snippet**: `AuditSink` is assumed to be a functional interface with the method `String write(String event)`. In a real project, the interface definition and auto-configuration registration need to live in appropriate files.

The checked property has the full name `demo.audit.enabled` (`prefix` + dot + `name`). Spring Boot uses the effective value in `Environment` at the time the condition is evaluated. When the condition does not match, the bean definition of the annotated method is not registered. That differs from creating the bean and setting an `enabled=false` state inside the object.

## 2. Default Rule: **Exists** and **Not `false`**

The definition:

~~~java
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
~~~

is semantically equivalent to using the annotation's default attribute values:

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "",
    matchIfMissing = false
)
~~~

Note: `havingValue=""` here is the **annotation's default marker**, meaning "no specific value is required; accept any value except `false`". It does **not** mean "only match when the property value is empty".

For the condition to match, both requirements must hold:

1. `Environment` contains the property `demo.audit.enabled` with a non-`null` value.
2. That value, when compared as a string case-insensitively, **does not equal `"false"`**.

If the property is not declared at all, `matchIfMissing=false` causes the condition not to match. This is the distinction between **not existing** and **existing with a value other than `false`**.

### Truth Table of Default Behavior

| Effective value of `demo.audit.enabled` | Default condition matches? | Explanation |
| --- | --- | --- |
| Undeclared / absent from `Environment` | **No** | `matchIfMissing=false` |
| `true` | **Yes** | Property present, value differs from `false` |
| `TRUE`, `TrUe` | **Yes** | Case-insensitive comparison |
| `false` | **No** | Equals the string `false` |
| `FALSE`, `FaLsE` | **No** | Still equals `false` ignoring case |
| `yes`, `on` | **Yes** | Differs from the string `false` |
| `no`, `off` | **Yes** | Even though a reader might interpret them as "off", they are not the string `false` |
| `0` or `1` | **Yes** | Not converted to boolean before evaluation |
| `staging` or an arbitrary string | **Yes** | Still differs from `false` |
| Empty string `""` when the property is **actually present** | **Yes** | Property key exists and value does not equal `false` |

**Common pitfall:** Default `@ConditionalOnProperty` does **not** mean "only match when the boolean value is `true`". It checks the effective value string. Hence `enabled=off` or `enabled=0` can still register the bean. If the goal is to enable only when configuration explicitly says `true`, write `havingValue="true"`.

With configuration loaded from YAML, properties, environment variables, or command-line arguments, value representation may be affected by the configuration-reading mechanism. When analyzing, examine **the actual string value supplied by `Environment`**, instead of guessing from how readers interpret words like "off".

## 3. How Does `havingValue` Change the Comparison?

The `havingValue` attribute allows requiring a specific value:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true"
)
AuditSink auditSink() {
    return event -> "AUDIT: " + event;
}
~~~

With this configuration, `demo.audit.enabled=off`, `0`, and `staging` **no longer** match. The values `true` or `TRUE` match. If the property is absent, by default it still does **not** match.

Comparison table of common choices:

| Property value | Without `havingValue` | `havingValue="true"` | `havingValue="false"` | `havingValue="staging"` |
| --- | --- | --- | --- | --- |
| `true` | Yes | Yes | No | No |
| `false` | No | No | Yes | No |
| `staging` | Yes | No | No | Yes |
| `off` | Yes | No | No | No |
| Missing property | No | No | No | No |

`havingValue` comparison is also case-insensitive. For example, `havingValue="staging"` can match `STAGING`.

**Practical choice:** For an explicit on/off flag, use `havingValue="true"` to avoid accidentally enabling functionality due to an unexpected value. For a property meant as "any value except `false` enables it", the default may be the right intent, but it should be clearly documented in configuration docs.

## 4. `matchIfMissing` Only Changes the **Missing Property** Case

By default `matchIfMissing=false`. If you want the feature enabled when the user does not declare the configuration, you can set `matchIfMissing=true`:

~~~java
@Bean
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
AuditSink auditSink() {
    return event -> "AUDIT: " + event;
}
~~~

Then:

- **Missing** `demo.audit.enabled`: condition matches, because `matchIfMissing=true`.
- `demo.audit.enabled=true`: condition matches, because it satisfies `havingValue="true"`.
- `demo.audit.enabled=false`: condition does **not** match.
- `demo.audit.enabled=off`: condition does **not** match, because `off` differs from `true`.

`matchIfMissing=true` does **not** mean "skip value checking". It only decides the result when the property is **actually absent**. A value that is present but fails `havingValue` still causes the condition to fail.

Two design styles have different meanings:

~~~java
// Runs when present and not "false"; does not run when property is missing.
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")

// Runs when property is missing as well; if present, must equal "true".
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
~~~

## 5. Runnable Verification Example: Spring Boot 3.3 + JUnit 5

The example below uses `ApplicationContextRunner` to create isolated contexts to verify each branch. Three different auto-configurations use the **same `AuditSink` type**, but are loaded by **three separate runners**, so they do not compete for bean registration with one another.

**File:** `src/test/java/example/condition/ConditionalOnPropertyDefaultTest.java`

~~~java
package example.condition;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionalOnPropertyDefaultTest {

    private final ApplicationContextRunner defaultRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(DefaultAuditConfiguration.class));

    private final ApplicationContextRunner strictRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(StrictAuditConfiguration.class));

    private final ApplicationContextRunner missingAllowedRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(MissingAllowedAuditConfiguration.class));

    @Test
    void missingPropertyDoesNotMatchByDefault() {
        defaultRunner.run(context ->
                assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void anyPresentValueExceptFalseMatchesByDefault() {
        for (String value :
                new String[] {"true", "TRUE", "yes", "off", "0", "staging", ""}) {
            defaultRunner.withPropertyValues("demo.audit.enabled=" + value)
                    .run(context -> {
                        assertThat(context).hasSingleBean(AuditSink.class);
                        assertThat(context.getBean(AuditSink.class).write("ok"))
                                .isEqualTo("AUDIT: ok");
                    });
        }
    }

    @Test
    void falseIsRejectedRegardlessOfLetterCase() {
        for (String value : new String[] {"false", "FALSE", "FaLsE"}) {
            defaultRunner.withPropertyValues("demo.audit.enabled=" + value)
                    .run(context ->
                            assertThat(context).doesNotHaveBean(AuditSink.class));
        }
    }

    @Test
    void havingValueTrueRequiresTheWordTrue() {
        strictRunner.withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        strictRunner.withPropertyValues("demo.audit.enabled=TRUE")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        strictRunner.withPropertyValues("demo.audit.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));

        strictRunner.run(context ->
                assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    @Test
    void matchIfMissingAllowsAbsenceButNotExplicitlyWrongValues() {
        missingAllowedRunner.run(context ->
                assertThat(context).hasSingleBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));

        missingAllowedRunner.withPropertyValues("demo.audit.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AuditSink.class));
    }

    interface AuditSink {
        String write(String event);
    }

    @AutoConfiguration
    static class DefaultAuditConfiguration {

        @Bean
        @ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }

    @AutoConfiguration
    static class StrictAuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true")
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }

    @AutoConfiguration
    static class MissingAllowedAuditConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.audit",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true)
        AuditSink auditSink() {
            return event -> "AUDIT: " + event;
        }
    }
}
~~~

**Requirements to run:** Java 17+, Spring Boot 3.3.x; test classpath includes `spring-boot-starter-test`. In a Gradle project with the Spring Boot plugin/BOM managing dependencies, the test section can declare:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Command to run in the module/project containing the test file:

~~~bash
# Linux / macOS
./gradlew test --tests "example.condition.ConditionalOnPropertyDefaultTest"

# Windows PowerShell / CMD
gradlew.bat test --tests "example.condition.ConditionalOnPropertyDefaultTest"
~~~

**Expected result:** 5 tests pass. `ApplicationContextRunner` closes each context after the callback. In the second test, the strings `"off"`, `"0"`, and empty string still create `AuditSink`, proving the annotation does not perform boolean coercion before comparing. The third test confirms `false` is recognized case-insensitively. The last two tests clarify the independent roles of `havingValue` and `matchIfMissing`. The assertions do not print `AUDIT: ok` to stdout; Gradle output depends on test logging configuration.

The example is a standalone single-file test: the nested `@AutoConfiguration` classes are loaded **explicitly** via `AutoConfigurations.of(...)`. If moved to a production auto-configuration in a library, the production class must be declared in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` for Spring Boot to auto-discover it.

## 6. Looking at Real Configuration

Example `application.yml`:

~~~yaml
demo:
  audit:
    enabled: true
~~~

The bean with the default condition will be registered. Changing it to `enabled: false` causes the condition not to match. Removing `enabled` altogether also **does not match**, because `matchIfMissing=false`.

With `application.properties`:

~~~properties
demo.audit.enabled=off
~~~

If the effective value in `Environment` is indeed the string `off`, **the default condition still matches**. This is why ordinary on/off flags should specify `havingValue="true"` when the application only wants to allow the value `true`.

Example when running the program:

~~~bash
java -jar app.jar --demo.audit.enabled=false
~~~

Command-line properties usually take higher precedence than default values in configuration files. Check the **final** value seen by `Environment`: a value in `application.yml` does not guarantee that is the value used by the condition if another property source overrides it.

In auto-configuration, use short, meaningful prefixes and lowercase hyphenated keys when multi-word, e.g., `demo.audit.log-enabled`.

## 7. Directly Related Additional Details

### Multiple properties in `name`

~~~java
@ConditionalOnProperty(
    prefix = "demo.audit",
    name = {"enabled", "remote-enabled"}
)
~~~

Both `demo.audit.enabled` **and** `demo.audit.remote-enabled` must be present, and each value must differ from `false`, for the default condition to match. Missing one key or having one key equal to `false` causes the condition not to match. `havingValue`, if set, applies to every listed property.

### Placing on class vs on `@Bean`

~~~java
@AutoConfiguration
@ConditionalOnProperty(prefix = "demo.audit", name = "enabled")
public class AuditAutoConfiguration {
    // @Bean methods inside are processed only when the class condition matches.
}
~~~

If placed on the **class**, the condition controls whether that configuration class is registered and processed. If placed on a **`@Bean` method**, the condition controls only the bean declared by that method. Choose the smallest scope that accurately reflects intent: do not accidentally disable independent beans because of a single feature flag.

### Do not use to check collections by root name

`@ConditionalOnProperty(prefix="demo", name="items")` is not guaranteed to match when the configuration source only has `demo.items[0]`, `demo.items[1]` without `demo.items`. For conditions depending on collection contents, consider writing a dedicated `Condition` or designing a simple flag property rather than relying on this kind of key check.

### Difference from boolean binding

`@ConfigurationProperties` can map configuration to a Java `boolean` property; that does not mean default `@ConditionalOnProperty` applies the same boolean conversion. This condition inspects the **string property value** in `Environment`. Therefore, checking "not `false`" is the condition rule, not a claim that every other value is boolean `true`.

## 8. Common Mistakes and How to Diagnose

1. **Thinking a missing property enables the feature by default.** In reality the default is `matchIfMissing=false`; to enable when missing, explicitly declare `matchIfMissing=true`.
2. **Thinking `0`, `no`, or `off` behave like `false`.** With the default `havingValue`, these are strings other than `false` and can make the condition match. Use `havingValue="true"` if an explicit boolean flag is required.
3. **Interpreting `havingValue=""` as matching only empty values.** This is a special value indicating the default check; it is not equivalent to checking `property.equals("")`.
4. **Assuming `matchIfMissing=true` makes every value valid.** It only affects the missing case; a present value must still satisfy the comparison.
5. **Confusing `prefix` and `name`.** `prefix="demo.audit", name="enabled"` forms the key `demo.audit.enabled`; misreading it as `demo.enabled` leads to wrong conclusions.
6. **Looking only at values in a single configuration file.** The final value may come from a higher-precedence source such as command-line or environment variables. Diagnose based on the merged `Environment`.
7. **Attaching the condition to the entire auto-configuration when only one bean should be controlled.** Annotation scope affects the set of registered beans.
8. **Not testing the missing-property branch.** Testing only with `true` and `false` will not catch misconfigured `matchIfMissing`.

You can start the application with `--debug` to view the **Condition Evaluation Report**, or add `ConditionEvaluationReportLoggingListener` to `ApplicationContextRunner` when debugging tests. The report shows which conditions matched/did not match; look for `OnPropertyCondition`, the key name checked, and the expected value.

## 9. Self-Check

**Question 1:** `@ConditionalOnProperty(name="demo.feature.enabled")`, and `Environment` does not contain this key. Is the bean created?

**Answer:** No. `matchIfMissing=false` is the default.

**Question 2:** The key exists with `demo.feature.enabled=off`. Does it match when `havingValue` is not declared?

**Answer:** Yes. `off` is a string different from `false`; the annotation does not implicitly convert `off` to boolean false.

**Question 3:** Same key, with `havingValue="true"` and `matchIfMissing=true`. With the value `false`, does the condition match?

**Answer:** No. `matchIfMissing` only handles when the key is absent; it does not ignore a wrong value that is present.

**Question 4:** `name={"enabled","ready"}`; `enabled=true`, `ready=false`. Does it match by default?

**Answer:** No. All specified keys must satisfy the condition, and `ready=false` causes the condition to fail.

## 10. Practical Conclusion

Remember the formula when **no extra parameters are configured**:

> `@ConditionalOnProperty` matches when **the key exists** in `Environment` **and the value does not equal the string `false`** (case-insensitive).

For on/off flags requiring the user to explicitly write `true`, use `havingValue="true"`. For features enabled by default when unconfigured, combine `havingValue="true", matchIfMissing=true`. Always test three separate branches: **missing key**, **`false`**, and **value other than `false`** to avoid misunderstanding the default semantics.

### Official Documentation

- [Spring Boot 3.3 — Javadoc `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration (Property Conditions, Testing)](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
