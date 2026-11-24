# Designing Clear Feature-Flag Keys and Building an Input Case Table for Conditions

## 1. Objective: A Feature Flag Must Have a Verifiable Contract

In Spring Boot Auto Configuration, we often want to create a feature's bean only when the operator **explicitly turns on** that feature. For example: a reporting module only registers `ReportService` when the property `demo.reports.enabled=true`.

This lesson belongs to the **Property Conditions** group, focusing on two complementary skills:

1. **Designing a feature-flag key** with clear naming, semantics, defaults, and behavior when encountering invalid values.
2. **Building an input case table** for `@ConditionalOnProperty` to accurately predict when beans/configurations will be registered, then verifying with a runnable example.

The differences between **undeclared property**, **declared `false`**, **declared empty**, and **declared unexpected string** are central. These values can lead to different outcomes depending on how the condition is declared.

## 2. How @ConditionalOnProperty Actually Evaluates Conditions

The `org.springframework.boot.autoconfigure.condition.ConditionalOnProperty` annotation inspects property values in the Spring `Environment` while Spring is building the application context.

An explicit condition for a feature enabled only when receiving the value `true`:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false
)
```

This is an illustrative annotation snippet; it must be placed on an appropriate configuration class or `@Bean` method. The complete key is `demo.reports.enabled`:

- `prefix = "demo.reports"`: the start of the key; Spring adds a dot when joining if needed.
- `name = "enabled"`: the remaining name part. `value` is an alias for `name`, so only one of the two is needed.
- `havingValue = "true"`: **matches only when the property value equals the string `true`, case-insensitive**.
- `matchIfMissing = false`: **does not match when the key is absent** from `Environment`.

The four attributes have important defaults:

| Annotation attribute | Default | Meaning |
|---|---|---|
| `prefix` | `""` | No prefix |
| `name` / `value` | `{}` | Must specify key name(s) to check |
| `havingValue` | `""` | If unspecified, present value must **differ from `false`** |
| `matchIfMissing` | `false` | If key is missing, condition does not match |

**Specifically:** The default `havingValue=""` is **not synonymous** with `havingValue="true"`. With the default, strings like `yes`, `1`, `unexpected`, and even an empty string can make the condition match because they do not equal `false`. Therefore, for an intended Boolean on/off key, declare `havingValue="true"` explicitly.

Spring Boot compares values as strings; do not infer this as a Boolean conversion accepting synonyms like `yes` or `1`. Also do not interpret `matchIfMissing` as a default configuration value: it only takes effect when **the key is not found**.

### Rule for multiple key names

If declared as:

```java
@ConditionalOnProperty(
    prefix = "demo.reports",
    name = {"enabled", "storage-ready"},
    havingValue = "true",
    matchIfMissing = false
)
```

then **both** keys `demo.reports.enabled` and `demo.reports.storage-ready` must match. This is an **AND** operation, not OR. If one key is absent or has the value `false`, the whole condition does not match. Only use multiple keys when you truly want all conditions to hold together; if the intent is "one of multiple keys", design a different condition.

## 3. Designing a Feature-Flag Key with a Clear Contract

Take a batch report-generation feature as an example:

| Contract component | Choice for example | Reason |
|---|---|---|
| Key name | `demo.reports.enabled` | Name reflects specific namespace and function |
| Desired value type | Logical boolean: `true` or `false` | Avoid ambiguous states |
| Business default value | `false` | Feature only runs when explicitly enabled |
| Activation condition | `havingValue="true"` | Do not treat `yes`, `1`, or typos as enabled |
| Missing key | `matchIfMissing=false` | Absent config does not silently enable |
| When disabled | Do not create optional `ReportService` bean | Express feature boundary at context startup |
| When applied | On context startup/refresh | Config changes after context is running do not implicitly re-evaluate conditions |

**Naming and phrasing principles:**

- Use a full, concise, unambiguous name: `demo.reports.enabled` expresses "enable the reports feature" more clearly than `reports`, `flag1`, or `disable-reporting=false`.
- Prefer positive `enabled` keys with `true/false` values. Avoid double negatives like `disable-feature=false` which easily cause readers to invert the meaning.
- Use canonical **lowercase kebab-case** for multi-word segments, e.g., `demo.report-export.enabled`, and separate namespaces with dots.
- Decide the **missing-key default** before writing annotations. For new features with cost, dependencies, or side effects, typically choose an explicit off state when missing; if backward compatibility demands default-on, document the reason and test the missing case.
- Clarify the **unit of configuration**: toggles the bean across the entire application context, not per HTTP request or per user. If per-user or immediate runtime toggling is needed while the system is running, a separate runtime mechanism is required.
- Name properties and beans accurately for their function. If only disabling a bean, places that inject that bean must also be designed to tolerate its absence or have an appropriate default implementation.

Example `application.yml` (explicitly off in default config):

```yaml
demo:
  reports:
    enabled: false
```

To enable in a chosen environment, operators can write:

```properties
demo.reports.enabled=true
```

In a Spring Boot app launched with `SpringApplication`, properties can be passed from the command line such as `--demo.reports.enabled=true`. Writing in a file, environment, or command line are all configuration sources; **the final value in `Environment` according to source precedence** is what the condition evaluates. For instance, default command-line options can override values from `application.yml`.

For this example key, the common corresponding environment variable is `DEMO_REPORTS_ENABLED=true`. Spring Boot's environment variable naming rule replaces dots with underscores, removes hyphens in property names, and uppercases; verify the actual mapping if using complex names.

## 4. Input Matrix: Do Not Test Only true and false

To avoid confusion, distinguish four condition declarations checking the same key `demo.reports.enabled`:

- **A — Explicit enable:** `havingValue="true", matchIfMissing=false`. This is the contract of this lesson.
- **B — Annotation default:** `havingValue="", matchIfMissing=false`. Only rejects `false` when the key is present.
- **C — Enable if missing:** `havingValue="true", matchIfMissing=true`. Can suit features enabled by default, but must be chosen intentionally.
- **D — Match false or missing:** `havingValue="false", matchIfMissing=true`. Specifically illustrates the off branch; not synonymous with "anything other than true".

In the table, **Yes** = condition matches and the bean/configuration *may* be registered; **No** = condition does not match. Assume no other conditions block the bean.

| Actual value in Environment | A: true + missing=false | B: default + missing=false | C: true + missing=true | D: false + missing=true |
|---|:---:|:---:|:---:|:---:|
| **Key absent** | No | No | **Yes** | **Yes** |
| `"true"` | **Yes** | **Yes** | **Yes** | No |
| `"TRUE"` | **Yes** | **Yes** | **Yes** | No |
| `"false"` | No | No | No | **Yes** |
| `"FALSE"` | No | No | No | **Yes** |
| `""` (empty string present) | No | **Yes** | No | No |
| `"yes"` | No | **Yes** | No | No |
| `"1"` | No | **Yes** | No | No |
| `"0"` | No | **Yes** | No | No |
| `"unexpected"` | No | **Yes** | No | No |

Notes on the table:
- **Key absent** differs from **key with an empty value**. `matchIfMissing` is only consulted when the key is genuinely absent.
- `"TRUE"` and `"FALSE"` are compared case-insensitively. Even so, in config files consistently write lowercase `true` and `false` for readability.
- With the default `havingValue=""`, any string **not equal to `false`** matches. This is a very common cause of bugs when omitting `havingValue="true"`.
- An unexpected value can cause condition A **not to create the bean without throwing a configuration error**. If the operational contract requires rejecting invalid values immediately at startup, add configuration validation or a custom condition; the condition itself is not a full input validator.

### Business matrix to commit to for the reports feature

| Test scenario | Illustrative config | Expected outcome with condition A |
|---|---|---|
| Unconfigured | Remove key from all applicable PropertySources | Feature **off** |
| Standard on | `demo.reports.enabled=true` | Feature **on** |
| Standard off | `demo.reports.enabled=false` | Feature **off** |
| Case variant | `demo.reports.enabled=TRUE` | **On**, due to case-insensitive comparison |
| Empty value | `demo.reports.enabled=` | **Off** |
| Typo | `demo.reports.enabled=treu` | **Off**; consider adding validation for clearer error reporting |
| Non-standard Boolean value | `demo.reports.enabled=yes` or `1` | **Off** |
| Default file false, overridden true | Higher-precedence PropertySource sets `true` | **On**, because Spring uses the final value in Environment |
| Default file true, overridden false | Higher-precedence PropertySource sets `false` | **Off** |

When bringing a feature into CI, turn these rows into predictable tests: **specific input → context has or lacks bean → does the app still start cleanly when the feature is off?** Testing only `true/false` misses critical cases.

## 5. Runnable Example with Java 17 and Spring Boot 3.3

The following program creates a fresh `AnnotationConfigApplicationContext` **for each input**; each time it adds only one property value (or adds none to simulate a missing key), then checks whether the `reportService` bean is created.

Minimal Maven project structure:

```text
feature-flag-matrix/
├── pom.xml
└── src/main/java/demo/FeatureFlagMatrixDemo.java
```

**`pom.xml`** (choosing Spring Boot 3.3.13 as a stable illustrative version in the 3.3 line):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>feature-flag-matrix</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/FeatureFlagMatrixDemo.java`:**

```java
package demo;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;

public class FeatureFlagMatrixDemo {

    private static final String FLAG = "demo.reports.enabled";

    public static class ReportService {
        public String report() {
            return "Report ready";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ReportConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.reports",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        public ReportService reportService() {
            return new ReportService();
        }
    }

    private static void check(String label, String value) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            if (value != null) {
                context.getEnvironment().getPropertySources().addFirst(
                        new MapPropertySource("scenario",
                                Map.of(FLAG, value)));
            }

            context.register(ReportConfiguration.class);
            context.refresh();

            System.out.println(label + " -> "
                    + context.containsLocalBean("reportService"));
        }
    }

    public static void main(String[] args) {
        check("(missing)", null);
        check("true", "true");
        check("TRUE", "TRUE");
        check("false", "false");
        check("FALSE", "FALSE");
        check("(empty)", "");
        check("yes", "yes");
        check("1", "1");
        check("unexpected", "unexpected");
    }
}
```

From the directory containing `pom.xml`, requiring JDK 17+ and Maven, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FeatureFlagMatrixDemo
```

Lines printed by the program to `stdout`:

```text
(missing) -> false
true -> true
TRUE -> true
false -> false
FALSE -> false
(empty) -> false
yes -> false
1 -> false
unexpected -> false
```

**Why does the code produce the right result?**

1. On each call to `check`, the program creates a fresh context, preventing beans or PropertySources from an earlier scenario from affecting subsequent scenarios.
2. The `null` value is used **only in test code** to represent *not adding the key to Environment*. That value is not placed into `Map.of` because Java does not allow null values in `Map.of`.
3. `MapPropertySource` puts the concrete value into Environment before `context.refresh()`, so `@ConditionalOnProperty` evaluates the exact input.
4. `context.containsLocalBean("reportService")` confirms whether the bean was registered in that test context. Only when the input string equals `true` case-insensitively does condition A match.
5. Context closes after each case via `try-with-resources`. This is an **illustration of checking conditions at startup**, not an API for hot-toggling beans at runtime.

The example directly uses the needed Spring classes via `spring-boot-starter`; it requires no database, HTTP server, or writing `@SpringBootApplication`. To test real auto-configuration in Spring Boot code, another convenient choice is `ApplicationContextRunner` from `spring-boot-test`: pass `withPropertyValues(...)`, assert beans with AssertJ, and run a runner without the key to test the missing case.

## 6. Putting the Condition into Real Auto-Configuration

The snippet below illustrates how the condition guards a bean in auto-configuration. `ReportService` is the application-defined type from the example above:

```java
@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.reports",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService();
    }
}
```

This is an **illustrative snippet inside a starter/auto-configuration**, not a standalone runnable Java file: it needs imports for `@AutoConfiguration`, `@Bean`, `@ConditionalOnProperty`, `@ConditionalOnMissingBean`, the `ReportService` type, and auto-configuration registration via Spring Boot's mechanism.

The two conditions carry two distinct responsibilities:

- `@ConditionalOnProperty`: **does the feature flag allow creating this bean?**
- `@ConditionalOnMissingBean`: **if the feature is enabled, has the user already provided an appropriate replacement bean?**

When the flag is off, the default bean is not created, even if no bean of the same type exists. When the flag is on and the user has provided an appropriate bean, `@ConditionalOnMissingBean` lets auto-configuration back off.

Also test the case where the feature is off yet another component still strictly injects `ReportService`. If a controller/service cannot operate when the bean is missing, design an appropriate dependency flow: guard the related configuration as well, provide a fallback implementation, or change the optional-dependency boundary. "Bean is not created" does not guarantee "the whole application definitely starts cleanly".

## 7. Operating and Controlling Configuration Across Multiple Environments

In real systems, the same key can be set in `application.yml`, profile-specific files, environment variables, a config server, or the command line. Spring Boot merges PropertySources by precedence order; **the condition uses the winning value**.

Example deployment contract:

| Environment | Suggested configuration | Purpose |
|---|---|---|
| Local development | `demo.reports.enabled=false` | Do not enable unnecessary reporting tasks |
| Integration test feature on | `demo.reports.enabled=true` | Verify the branch with the bean |
| Integration test feature off | `demo.reports.enabled=false` or undeclared | Verify the branch without the bean |
| Production | Value explicitly decided in deployment config | Avoid relying on operator assumptions |

This is a **contract suggestion**, not a mandatory rule for every feature. If a feature must default to on for backward compatibility, clearly document the `matchIfMissing=true` choice and add tests for the missing-key case. Do not change `matchIfMissing` casually because that changes deployment behavior.

From an operations perspective, also document: flag owner, environments allowed to enable, side effects when enabled, required dependencies, how to check the bean/health, and a flag-cleanup plan once the feature stabilizes. For temporary rollout flags, track them to avoid accumulating dead configuration branches.

**Bean-enabling flags are conditions evaluated at context initialization.** Editing files or environment variables while the application is running does not cause `@ConditionalOnProperty` to re-evaluate and add/remove beans. Normally the context must be recreated or restarted; if runtime control is needed, use a dedicated runtime feature-flag mechanism and keep in-flight request state consistent.

**Do not use feature flags as authorization or security boundaries.** Bean presence/absence is only one aspect of application configuration; access permissions still need to be enforced at appropriate points.

## 8. Common Mistakes and How to Detect Them

| Symptom | Cause to check | How to handle |
|---|---|---|
| Typed `enabled=yes` yet bean is still created | Using default `havingValue=""`, which only rejects `false` | Set `havingValue="true"` |
| Flag not declared yet bean still exists | `matchIfMissing=true`, or bean created elsewhere | Confirm default, inspect bean definitions and condition report |
| Wrote `false` yet bean still exists | Another bean provides the same type/name, or higher-priority PropertySource overrides it | Check final value in Environment and bean origin |
| Configured `true` yet bean does not appear | Wrong key name, overridden, typo in `havingValue`, additional conditions, or registration failure | Check full key, list of conditions, and imported configurations |
| Two values `enabled` and `storage-ready`, one true one false; bean absent | When `name` is an array, all keys must match | Confirm AND semantics, test all combinations |
| Tests run only with `true/false` | Missed missing, blank, typo, and case variants | Use the input matrix in section 4 |
| Expecting instant flag changes after startup | Conditions were already evaluated during bean definition creation | Design a separate runtime mechanism or restart the context |
| List property has only `values[0]` while condition on `values` does not match | `@ConditionalOnProperty` does not check collections reliably | Use a custom condition for collection requirements |

### How to observe conditions

In a typical Spring Boot application, enable debug mode with `--debug` to view the **Condition Evaluation Report**. If using Spring Boot Actuator and the corresponding endpoint is enabled/exposed, `/actuator/conditions` provides condition match information for investigation.

When accurate diagnosis is needed, record simultaneously: the full key name, the final value in Environment (without printing secrets), `havingValue` / `matchIfMissing` attributes, the bean name expected to appear, and additional conditions such as `@ConditionalOnMissingBean`. Do not look only at a single line in `application.yml`, as it may be overridden by another source.

## 9. Applied Exercises

**Exercise 1 — Unintended activation risk.** A configuration uses:

```java
@ConditionalOnProperty(prefix = "demo.reports", name = "enabled")
```

An operator enters `demo.reports.enabled=treu`. Can the bean be created?

**Answer:** Yes. Because default `havingValue=""` only rejects `false`, the string `treu` still matches. If activation should only be accepted when `true`, change to `havingValue="true", matchIfMissing=false`.

**Exercise 2 — Default when missing.** A condition has `havingValue="true", matchIfMissing=true`, but the deployment file sets `enabled=false`. Does the condition match?

**Answer:** No. `matchIfMissing=true` only takes effect **when the key is missing**; here the key exists and contains `false`.

**Exercise 3 — Both conditions must be enabled.** Given `name={"enabled", "storage-ready"}`, `havingValue="true"`. Operator sets `enabled=true`, `storage-ready=false`. Result?

**Answer:** No match; every key name must match. Only when both are `true` is the condition satisfied.

**Exercise 4 — Environment override.** `application.yml` has `enabled=false` yet the Spring Boot startup command passes `--demo.reports.enabled=true`. Result?

**Answer:** With standard `SpringApplication` configuration allowing command-line properties, command-line values take higher precedence than config files, so the explicit-enable condition matches. If a custom application disables adding command-line properties, inspect the actual PropertySource order.

## 10. Takeaways and Pre-Handoff Checklist for a Feature Flag

1. Clear, stable, meaningful key: `<namespace>.<feature>.enabled`.
2. Define behavior for **true, false, missing, blank, unexpected value**.
3. For explicit opt-in, use `havingValue="true", matchIfMissing=false`.
4. Do not forget that default `havingValue=""` only checks values **not equal to false**.
5. Build a matrix and test at least: missing key, true, false, uppercase, empty string, invalid string, and override from a higher-priority source.
6. Verify both **whether the bean is created** and **whether the app starts cleanly when the feature is off**.
7. State clearly that auto-configuration feature flags are evaluated at context startup, and do not behave as runtime switches on their own.

### Official Documentation

- [Spring Boot 3.3 — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html)
- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
