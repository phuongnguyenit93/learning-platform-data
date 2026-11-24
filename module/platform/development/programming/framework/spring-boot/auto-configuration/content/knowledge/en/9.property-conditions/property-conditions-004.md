# `matchIfMissing` and Deciding Enable vs. Disable When a Property Is Not Declared

**Topic:** Spring Boot Auto Configuration  
**Knowledge area:** Property Conditions (`@ConditionalOnProperty`)  
**Core question:** When a user **omits** a configuration in `application.yml`, should Spring Boot register the corresponding bean or skip it? What does `matchIfMissing` decide, and how do you set defaults that are safe and easy to test?

## 1. Core Mechanism

In Spring Boot, `@ConditionalOnProperty` instructs Spring to check one or more properties in `Environment` before registering a configuration or bean:

```java
@Bean
@ConditionalOnProperty(prefix = "demo.reports", name = "enabled")
ReportJob reportJob() {
    return new ReportJob();
}
```

The checked property is `demo.reports.enabled`.

By default, the condition matches when **the property is present** and its string value **differs from `"false"`** (case-insensitive). When the property is completely absent from `Environment`, the condition **does not match**, so the bean will not be registered.

`matchIfMissing` allows changing **only the missing-property situation**:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    matchIfMissing = true
)
```

- `matchIfMissing = false` (default): missing property → **does not match** → bean/configuration branch is not registered.
- `matchIfMissing = true`: missing property → **matches** → bean/configuration branch is registered (unless excluded by other conditions).
- When the property **is present**, `matchIfMissing` does not decide the outcome; Spring evaluates the property's value against `havingValue` or the default rule.

`matchIfMissing` is a **default choice when configuration is absent**, not an instruction forcing the feature on regardless of what the user configures.

## 2. Standard Decision Table

Assume only a single condition applies to `demo.reports.enabled`, with no other auxiliary conditions, and `havingValue` left at its default (`""`):

| Effective value in `Environment` | `matchIfMissing = false` | `matchIfMissing = true` | Why? |
| --- | --- | --- | --- |
| Property absent | No match | **Match** | Based on `matchIfMissing` |
| `"true"` | **Match** | **Match** | Property present and not `"false"` |
| `"false"` | No match | No match | Property present, value equals `"false"` |
| `"FALSE"` | No match | No match | Case-insensitive comparison |
| `"off"` | **Match** | **Match** | With `havingValue=""`, string `"off"` is *not* `"false"` |
| `"0"` | **Match** | **Match** | `"0"` is not automatically synonymous with `"false"` in this condition |
| `""` (key declared but left blank) | **Match** | **Match** | Key exists and value is not `"false"` |

**Distinguishing "missing" from "present but empty":**

```properties
# Property absent:
# demo.reports.enabled does not appear at all

# Property present with empty value:
demo.reports.enabled=
```

These two cases can lead to different outcomes. In the default example, the second line is treated as a property with an empty value; the condition normally matches because an empty value does not equal `"false"`.

**Warning about `off`, `0`, `no`:** These strings may be interpreted as `false` in other Spring Boot Boolean binding mechanisms. `@ConditionalOnProperty` with default `havingValue` applies its own string comparison rule: do not assume every "false-like" string disables the feature. For strict Boolean feature flags, use `havingValue = "true"`.

## 3. Choosing Default OFF vs. ON by Design Intent

### 3.1. Default OFF: user must explicitly enable

Suitable for optional features, ones requiring infrastructure/cost preparation, or ones with sensitive impact:

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
ReportJob reportJob() {
    return new ReportJob();
}
```

Usage:

```yaml
# application.yml
demo:
  reports:
    enabled: true
```

When `demo.reports.enabled` is omitted or set to `false`, the condition does not match. Operators must explicitly enable it with `true`.

A common example is an automated email-sending service. If a new environment does not yet have SMTP fully configured, not registering the auto-send job by default avoids unintended dispatches. However, **Spring conditions only decide bean registration**; separate design is needed to ensure no other email-sending path is triggered.

### 3.2. Default ON: feature is standard behavior, allowing explicit opt-out

Suitable when the behavior is defined as the product default, omitting configuration is the normal case, and users are allowed to opt out:

```java
@Bean
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
ReportJob reportJob() {
    return new ReportJob();
}
```

Consequences:

- Property omitted → condition matches, creates `ReportJob`.
- `demo.reports.enabled=true` → condition matches.
- `demo.reports.enabled=false` → does not match.
- `demo.reports.enabled=off` → **does not match** when `havingValue="true"`; only the string `"true"` satisfies the required value.

Final note: `matchIfMissing=true` with `havingValue="true"` does **not** mean a missing property is equivalent to "having configured the value true". It means the condition permits a missing key. Both states can create the bean, but binding values into other configuration objects still follows its own mechanism.

## 4. `havingValue` and `matchIfMissing` Act on Two Different Branches

`@ConditionalOnProperty` follows a two-step evaluation:

1. **Is an effective property present?** If not, use `matchIfMissing`.
2. **If present, is the value right?** If `havingValue` is a non-empty string, perform a case-insensitive string comparison with the required value. If `havingValue=""` (default), check that the value differs from `"false"`.

Example when the key is present:

| Property value | `havingValue=""` | `havingValue="true"` | `havingValue="false"` | `havingValue="strict"` |
| --- | --- | --- | --- | --- |
| `"true"` | Match | Match | No | No |
| `"false"` | No | No | Match | No |
| `"strict"` | Match | No | No | Match |
| `"off"` | Match | No | No | No |

If the property is **absent**, all `havingValue` columns defer the decision to `matchIfMissing`.

Surprising example:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "mode",
    havingValue = "strict",
    matchIfMissing = true
)
```

The condition matches in **two** situations: `demo.reports.mode=strict` **or** `demo.reports.mode` is completely absent. If the business requirement is "only run strict mode when `strict` is explicitly specified", you must keep `matchIfMissing=false`.

## 5. Standalone Lab with `ApplicationContextRunner`

The lab uses **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**. It creates lightweight application contexts directly in tests without starting a web server.

### 5.1. File structure

```text
conditional-property-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── PropertyConditionTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>conditional-property-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

Create `src/test/java/demo/PropertyConditionTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyConditionTest {

    static final class ReportJob {
    }

    @AutoConfiguration
    static class DisabledByDefaultConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true"
        )
        ReportJob reportJob() {
            return new ReportJob();
        }
    }

    @AutoConfiguration
    static class EnabledByDefaultConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = true
        )
        ReportJob reportJob() {
            return new ReportJob();
        }
    }

    private final ApplicationContextRunner disabledByDefault =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(DisabledByDefaultConfiguration.class)
            );

    private final ApplicationContextRunner enabledByDefault =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(EnabledByDefaultConfiguration.class)
            );

    @Test
    void noPropertyMeansOffWhenMatchIfMissingIsFalse() {
        disabledByDefault.run(context ->
                assertThat(context).doesNotHaveBean(ReportJob.class)
        );
    }

    @Test
    void noPropertyMeansOnWhenMatchIfMissingIsTrue() {
        enabledByDefault.run(context ->
                assertThat(context).hasSingleBean(ReportJob.class)
        );
    }

    @Test
    void explicitTrueTurnsFeatureOnInEitherMode() {
        disabledByDefault
                .withPropertyValues("demo.reports.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(ReportJob.class)
                );

        enabledByDefault
                .withPropertyValues("demo.reports.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(ReportJob.class)
                );
    }

    @Test
    void explicitFalseTurnsFeatureOffEvenWithMatchIfMissingTrue() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }

    @Test
    void offStringDoesNotMatchExplicitHavingValueTrue() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=off")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }

    @Test
    void emptyPresentPropertyIsNotTheSameAsMissing() {
        enabledByDefault
                .withPropertyValues("demo.reports.enabled=")
                .run(context ->
                        assertThat(context).doesNotHaveBean(ReportJob.class)
                );
    }
}
```

Run:

```bash
mvn test
```

**Expected result:** `Tests run: 6, Failures: 0, Errors: 0, Skipped: 0` in the Maven Surefire report (log format may vary by plugin version). No custom stdout from the test code. The assertions precisely show:

- Omitting the key → the `disabledByDefault` context has no `ReportJob`, while the `enabledByDefault` context has one bean.
- When the key has value `false`, `matchIfMissing=true` does not "rescue" the condition.
- When combined with `havingValue="true"`, a present value that is `"off"` or empty is not treated as `"true"`.
- Each test method creates and closes its own context; it is unaffected by beans from other tests.

If you want to verify the **default** `havingValue=""` rule for the string `"off"` or empty values, remove `havingValue="true"` from **both** conditions and update the corresponding assertions. Do not change assertions to match desired output while keeping the old configuration.

## 6. `application.yml`, Environment Variables, and "Truly Missing Property"

In a real Spring Boot application, properties do not come only from `application.yml`. `Environment` can aggregate configuration from many sources such as properties/YAML files, profile-specific configs, environment variables, JVM system properties, command-line arguments, and application-added sources.

Example:

```yaml
# application.yml
demo:
  reports:
    enabled: false
```

Now, another place can override the value. For example, running the app with:

```bash
java -jar app.jar --demo.reports.enabled=true
```

`@ConditionalOnProperty` checks the **effective value** in `Environment` according to configuration-source precedence rules. You cannot conclude "missing" merely because the key is not seen in one specific YAML file. Check all applicable sources, including active profiles and deployment configuration.

In a standard deployment environment, for example the corresponding environment variable name:

```text
DEMO_REPORTS_ENABLED=false
```

When inspecting the condition, cross-check the canonical name (`demo.reports.enabled`), Spring Boot's relaxed configuration name mapping, and the final value in `Environment`. Do not guess presence or absence from a single file.

## 7. Easily Confused Differences

### 7.1. `matchIfMissing` is not the same as `@Value`'s default value

```java
@Value("${demo.reports.enabled:true}")
private boolean enabled;
```

The line above supplies a **fallback value at the injection site**; it does not automatically add the key to any `PropertySource` and is not synonymous with changing `@ConditionalOnProperty`. You can simultaneously have a Java field receiving `true` via a placeholder default and a conditional annotation evaluating the key as "missing".

Similarly, a field initializer:

```java
@ConfigurationProperties(prefix = "demo.reports")
class ReportsProperties {
    private boolean enabled = true;
}
```

sets the default for the bound object; it does not guarantee the condition sees the `demo.reports.enabled` property added to `Environment`. If both need the same policy, clarify the default configuration and test with a full context.

### 7.2. `matchIfMissing` is not a dynamic toggle

Bean registration conditions are evaluated when the container builds the application context. Editing environment variables or `application.yml` after startup **does not automatically** register or remove beans from the running context. If runtime toggling is needed, design a separate mechanism to alter behavior and consider bean lifecycle.

### 7.3. Multiple keys in `name` are an AND operation

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = {"enabled", "scheduler-enabled"},
    havingValue = "true",
    matchIfMissing = false
)
```

Both `demo.reports.enabled` **and** `demo.reports.scheduler-enabled` must be satisfied; if one key is missing, the condition does not match. If switched to `matchIfMissing=true`, a missing key is considered to **satisfy its own check**, yet if the other key is present with the wrong value, the entire condition still fails to match. A multi-element `name` cannot be interpreted as OR.

### 7.4. A collection key cannot be reliably evaluated like a scalar key

`@ConditionalOnProperty(name = "demo.targets")` may fail to match when only `demo.targets[0]` exists in `Environment`. If a condition depends on list/map contents, use a custom `Condition` or introduce an explicit scalar flag key in configuration. `matchIfMissing` does not solve the issue of resolving collection properties.

### 7.5. Condition outcome also depends on other conditions

```java
@AutoConfiguration
@ConditionalOnClass(ReportJob.class)
@ConditionalOnProperty(
        prefix = "demo.reports",
        name = "enabled",
        matchIfMissing = true
)
class ReportsAutoConfiguration {
    // ...
}
```

Even when `matchIfMissing=true` matches due to an absent key, the configuration still does not activate if a required class is missing or another `@Conditional` fails to match. Thus, "matchIfMissing enables the bean" is shorthand; more accurately, it allows the **property condition** to match on the missing branch.

## 8. Diagnosing Configuration Issues with Real Data

When expected default ON/OFF behavior does not happen, check step by step:

1. **Right key?** `prefix="demo.reports"` + `name="enabled"` forms `demo.reports.enabled`; check for typos, hyphens, or profiles.
2. **Key truly absent?** Inspect effective configuration sources, not just one file. Use `Environment.getProperty("demo.reports.enabled")` when safely observable in the app/test.
3. **Right value?** `false`, `off`, `0`, and empty can behave differently in the condition; check whether `havingValue` is declared.
4. **Right default?** Leaving `matchIfMissing` unspecified means `false`.
5. **Annotation at the right scope?** An annotation on a configuration class can exclude an entire group of beans; an annotation on a `@Bean` method applies only to that method's bean definition.
6. **Other conditions involved?** Check classpath, existing beans, web application type, or auto-configuration ordering.

Helpful tools:
- Start the Spring Boot app with `--debug` to inspect the *Condition Evaluation Report*.
- If Spring Boot Actuator is present and the endpoint is appropriately enabled/exposed, check `/actuator/conditions`.
- In tests, use `ApplicationContextRunner` to explicitly exercise every combination: missing, `true`, `false`, unexpected strings, and overridden configuration.

Avoid using `@ConditionalOnExpression` merely to replace `matchIfMissing`; SpEL introduces unnecessary complexity when the condition is just a configuration flag.

## 9. Self-Check Exercises

**Exercise 1.** Given `@ConditionalOnProperty(name="app.audit.enabled", matchIfMissing=true)` and `application.yml` does not contain the property. Is the bean registered?  
**Solution:** The property condition **matches**. The bean is registered if other conditions also allow it. There is no need to have `app.audit.enabled: true` in YAML for `matchIfMissing` to take effect.

**Exercise 2.** Keep the annotation above but set `app.audit.enabled=false`. Result?  
**Solution:** **No match**. The key is present so `matchIfMissing` is not used; default `havingValue=""` rejects `"false"`.

**Exercise 3.** To enable processing only when the user explicitly sets `app.audit.enabled=true`, what should be declared?  
**Solution:**

```java
@ConditionalOnProperty(
    name = "app.audit.enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

**Exercise 4.** Given `havingValue="strict", matchIfMissing=true`; what happens if the property is missing?  
**Solution:** **Matches** due to the missing branch. If the goal is "run only when strict is written", change to `matchIfMissing=false`.

**Exercise 5.** The property is written as `app.audit.enabled=off`; does a default condition without `havingValue` match?  
**Solution:** **Yes**, because `"off"` differs from `"false"`. For clear Boolean semantics, use `havingValue="true"` and test `"off"`/empty states.

## 10. Takeaways and Practical Rules

- When the **key is missing**, `matchIfMissing` decides whether the condition matches. Its default value is `false`.
- When the **key is present**, `havingValue` (or the "not false" rule if omitted) decides.
- Design **default OFF** for features requiring explicit opt-in; design **default ON** when it is genuinely the desired default behavior with a clear opt-out path.
- For Boolean feature flags, explicitly choosing `havingValue="true"` paired with `matchIfMissing` prevents strings like `"off"`, `"0"`, or empty from being interpreted as enabled.
- Always test *missing* and *explicit false* separately. They are two distinct logical branches of the condition.

### References

- [Spring Boot Reference — Creating Your Own Auto-configuration, Property Conditions](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — `@ConditionalOnProperty`](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot Reference — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
