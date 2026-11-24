# Normalizing Key Names to kebab-case and Checking the Effective Value Source

> **Key idea:** In Spring Boot Auto Configuration, you need to answer **two distinct questions** correctly: (1) **which configuration key** the condition is checking and whether that key is written in canonical form; (2) when the condition is evaluated, **which `PropertySource` the effective value of that key comes from** after Spring Boot applies precedence order. Looking at just one line in `application.yml` is usually not enough to conclude, because environment variables, Java system properties, command-line arguments, profiles, and external configuration files can override it.

This lesson uses Spring Boot **3.3.x** and Java **17+**, focusing on conditional configuration via `@ConditionalOnProperty`.

## 1. Canonical Key Form: lowercase kebab-case

Spring Boot's canonical convention is: use lowercase, dots to separate parts of a configuration path, and hyphens `-` between words within each part.

Example of a **canonical key**:

~~~properties
demo.feature.audit-enabled=true
~~~

In this example:

- `demo.feature` is the prefix, representing the configuration group.
- `audit-enabled` is the property name consisting of two words joined by `-`.
- The full key `demo.feature.audit-enabled` is the uniform reference for writing code, documentation, and troubleshooting.

### Same meaning across configuration sources

| Where declared | Example | Notes |
| --- | --- | --- |
| `application.properties` | `demo.feature.audit-enabled=true` | Canonical form to use. |
| `application.properties` (camelCase) | `demo.feature.auditEnabled=true` | Relaxed binding can recognize this when querying the canonical name; standardize on kebab-case for easy comparison. |
| `application.properties` (underscore) | `demo.feature.audit_enabled=true` | Another form supported in binding; do not mix notations for the same setting. |
| `application.yml` | `demo: { feature: { audit-enabled: true } }` | After flattening to a property path, the corresponding key is `demo.feature.audit-enabled`. |
| OS environment variable | `DEMO_FEATURE_AUDITENABLED=true` | Dots → `_`, **remove `-`**, then uppercase. |
| Command-line argument | `--demo.feature.audit-enabled=true` | Uses the canonical path. |
| Java system property | `-Ddemo.feature.audit-enabled=true` | Placed before `-jar` when launching the JVM. |

**Rules for converting names to environment variables** per Spring Boot documentation:

1. Replace dots with underscores: `demo.feature.audit-enabled` → `demo_feature_audit-enabled`.
2. **Remove** hyphens within a segment: → `demo_feature_auditenabled`.
3. Uppercase: → `DEMO_FEATURE_AUDITENABLED`.

Therefore, do not guess that `DEMO_FEATURE_AUDIT_ENABLED` is the equivalent of `demo.feature.audit-enabled`. Extra `_` characters can be interpreted as separating different path segments; derive the name from the canonical key using the exact three steps, then verify at actual runtime.

Equivalent YAML configuration, easier to read than inline form:

~~~yaml
demo:
  feature:
    audit-enabled: true
~~~

In the annotation, write:

~~~java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "audit-enabled",
    havingValue = "true"
)
~~~

Spring Boot joins `prefix` and `name` into `demo.feature.audit-enabled`. For `@ConditionalOnProperty`, the Javadoc recommends `name` in lowercase dashed notation. `@ConfigurationProperties(prefix = "demo.feature")` also requires a canonical prefix; when injecting a value with `@Value`, use a placeholder like `@Value("${demo.feature.audit-enabled}")` because canonical notation lets Boot recognize corresponding name variants.

**Distinction:** *relaxed binding* helps relate valid names across different sources; it does **not** mean any arbitrary string with dots/underscores/hyphens is treated as a single key. A malformed key can still fail to match the condition.

## 2. What Value Does the Condition Check?

`@ConditionalOnProperty` is a condition based on a property queryable from Spring `Environment` **at configuration evaluation time**. In the case above, it looks at `demo.feature.audit-enabled`; if the condition does not match, the annotated bean or configuration class will not be registered along that branch.

Read all four elements:

- `prefix` + `name`: full key name.
- `havingValue`: required value string; specify explicitly when toggling by a flag.
- `matchIfMissing`: whether to pass when the property cannot be found; defaults to `false`.
- Values in `name = {"a", "b"}`: **all** listed keys must satisfy the condition, not just one.

The table below illustrates the results (assuming the property exists and has the exact string shown in the first column):

| Effective value | Without `havingValue` | `havingValue="true"` | `havingValue="false"` |
| --- | --- | --- | --- |
| `true` | Match | Match | No match |
| `false` | No match | No match | Match |
| `custom` | Match | No match | No match |
| *Key absent* | No match if `matchIfMissing=false` | No match if `matchIfMissing=false` | No match if `matchIfMissing=false` |

The default `havingValue=""` means the property **must be present and not equal to `false`**; it is **not** equivalent to requiring boolean `true`. For features that should only be enabled when configuration is truly `true`, declare `havingValue = "true"` explicitly.

Set `matchIfMissing = true` only when intentionally treating the **undeclared** case as enabled. It does not turn an explicitly declared `false` value into "missing". `@ConditionalOnProperty` is also **not** suitable for reliably checking the existence of list elements, such as having only `demo.targets[0]` without `demo.targets`; when complex collection conditions are needed, use a custom condition or a different design.

## 3. What Does "Effective Value Source" Mean?

`Environment` aggregates many `PropertySource`s. A key can appear in multiple places with different values. Spring Boot has precedence rules; normally **the highest-priority source providing a valid value** determines the value read by the condition.

For common sources in **Spring Boot 3.3**, the order from highest to lowest priority can be pictured as follows:

| Relative priority | Source | Example |
| --- | --- | --- |
| High | Application command-line arguments (`--key=value`) | `--demo.feature.audit-enabled=false` |
| ↓ | `SPRING_APPLICATION_JSON` | `{"demo":{"feature":{"audit-enabled":true}}}` |
| ↓ | Java system properties (`-D...`) | `-Ddemo.feature.audit-enabled=true` |
| ↓ | OS environment variables | `DEMO_FEATURE_AUDITENABLED=true` |
| ↓ | Config data: `application.properties` / YAML, external files outside JAR, profile-specific documents, imported files | `demo.feature.audit-enabled=false` |
| Lower | `SpringApplication` default properties | Default values when no override exists |

This is an abbreviated view of common sources, not an exhaustive list: JNDI, servlet parameters, test-added sources, `@PropertySource`, and Devtools also have positions in the actual order. Test sources can rank higher than command-line arguments. Within the config data group, sources also have their own ordering; for instance, active-profile config normally overrides general config according to config data loading rules. Order is **not** determined alphabetically by filename or property name.

### Example with declarations in three places

Inside the JAR:

~~~yaml
# application.yml
demo:
  feature:
    audit-enabled: false
~~~

In the runtime environment (POSIX shell):

~~~bash
export DEMO_FEATURE_AUDITENABLED=true
~~~

When running via command line:

~~~bash
java -jar app.jar --demo.feature.audit-enabled=false
~~~

Result when the application starts under typical configuration:

1. Config data has `false`.
2. OS environment supplies `true` and beats config data if no higher source is present.
3. Command-line supplies `false` and beats both preceding sources.

**The effective value is `false`**, so `@ConditionalOnProperty(prefix = "demo.feature", name = "audit-enabled", havingValue = "true")` **does not match**. If you remove the command-line argument, the environment variable `true` can become the winning value. If you also remove the environment variable, `false` in YAML is the effective value.

Also check `spring.profiles.active`, `spring.config.import`, `spring.config.location`, and `spring.config.additional-location`: an activated profile/file or additional location may cause you to observe a **different source** from the file you just edited. If both `application.properties` and `application.yml` exist in the same location, Boot prefers `.properties`; avoid maintaining two files containing the same key.

A value appearing in `application.yml` only proves **it was declared in that file**, not that it is the value the condition will see. To verify, inspect the `Environment` state and effective sources at runtime.

## 4. Diagnostic Procedure from Key to Winning Source

When a bean is not created or is created contrary to expectations, proceed step by step:

**Step 1 — Write down the canonical key on paper.** From the annotation, determine the exact `prefix + name`. For example, `prefix = "demo.feature"` and `name = "audit-enabled"` yields `demo.feature.audit-enabled`. Check for dot, hyphen, singular/plural, and spelling mistakes.

**Step 2 — Check input variants.** Inspect the key in YAML/properties, OS env, `-D`, `--`, `SPRING_APPLICATION_JSON`. Apply the canonical environment-variable conversion, e.g., `DEMO_FEATURE_AUDITENABLED`. Pay attention to whether the environment variable is actually passed into the **Java process** or only exists in another terminal, IDE run configuration, container, or pod.

**Step 3 — Inspect profiles and config data.** Note active profiles and config loading locations. Cross-check files inside the JAR, external files outside the JAR, and imported files. Do not look only at the file you just edited if the app is launched with override sources.

**Step 4 — Observe the effective value via `Environment`.** Where `Environment` can be injected:

~~~java
// Illustration inside a Spring-managed bean/component
String canonicalKey = "demo.feature.audit-enabled";
String effectiveValue = environment.getProperty(canonicalKey);
System.out.println("Effective value = " + effectiveValue);
~~~

The snippet above assumes `environment` is an injected `org.springframework.core.env.Environment`; it is **not** a standalone Java program. A `null` value usually means the key is unresolved, not that a config file does not exist. Avoid printing values of passwords/tokens/secrets during diagnostics.

**Step 5 — Find the source and origin, do not stop at the value.** If `spring-boot-starter-actuator` is present, in a protected diagnostic environment you can allow access to:

~~~properties
management.endpoints.web.exposure.include=health,conditions,env,configprops
~~~

Then inspect:

~~~text
GET /actuator/env/demo.feature.audit-enabled
GET /actuator/conditions
GET /actuator/configprops
~~~

- `/actuator/env/{name}` helps check the chosen value and related configuration sources; `origin` data (e.g., filename/line) may appear when supported by the source.
- `/actuator/conditions` answers **why** an auto-configuration condition matched or did not match; useful when the property name is right but `havingValue` fails.
- `/actuator/configprops` helps cross-check binding results into `@ConfigurationProperties`; that binding result does not by itself prove the `@ConditionalOnProperty` branch matched.

The `env` and `configprops` endpoints have masking mechanisms for sensitive values. Actuator does **not** expose these endpoints over HTTP by default; when inspection is needed, configure exposure and protect access. In production, do not expose them publicly just to test conditions.

Additionally, running the application with `--debug` can display the **Condition Evaluation Report** in logs, depending on logging configuration. The condition report explains configuration creation decisions; the property source view explains where values came from. The two pieces of information complement each other.

### Determining origin in Java when deep verification is needed

Spring Boot provides the `ConfigurationPropertySources` API to query sources by **canonical name**. Below is an illustrative method that can be placed in an application class with Spring Boot 3.3 dependencies:

~~~java
import org.springframework.boot.context.properties.source.ConfigurationProperty;
import org.springframework.boot.context.properties.source.ConfigurationPropertyName;
import org.springframework.boot.context.properties.source.ConfigurationPropertySource;
import org.springframework.boot.context.properties.source.ConfigurationPropertySources;
import org.springframework.core.env.ConfigurableEnvironment;

public final class PropertyProbe {
    private PropertyProbe() {}

    public static void inspect(ConfigurableEnvironment environment) {
        ConfigurationPropertyName key =
                ConfigurationPropertyName.of("demo.feature.audit-enabled");

        for (ConfigurationPropertySource source :
                ConfigurationPropertySources.get(environment)) {
            ConfigurationProperty property =
                    source.getConfigurationProperty(key);
            if (property != null) {
                System.out.println("value=" + property.getValue());
                System.out.println("origin=" + property.getOrigin());
                return; // Take the first source with a value in precedence order
            }
        }
        System.out.println("property missing");
    }
}
~~~

This is a valid Java class but must be **called from a Spring Boot application that has a `ConfigurableEnvironment`**; it does not create a context on its own. If `Origin` is `null`, that source does not provide origin metadata. Do not guess file line numbers when metadata is absent; and do not print configuration secrets to logs. When using custom configuration source mechanisms, compare against `/actuator/env` or actual reports to confirm.

## 5. Runnable Example: Condition and Source Order with ApplicationContextRunner

The example below is a **complete Java test file** on Spring Boot 3.3 + JUnit 5 + AssertJ, suitable for a Java 17+ project with `spring-boot-starter` and test dependency `spring-boot-starter-test`.

**File:** `src/test/java/example/conditions/AuditConditionTest.java`

~~~java
package example.conditions;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.MapPropertySource;

import static org.assertj.core.api.Assertions.assertThat;

class AuditConditionTest {
    private static final String KEY = "demo.feature.audit-enabled";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void absentKeyDoesNotRegisterBean() {
        runner.run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void trueValueRegistersBean() {
        runner.withPropertyValues(KEY + "=true").run(context -> {
            assertThat(context).hasBean("auditMarker");
            assertThat(context.getEnvironment().getProperty(KEY))
                    .isEqualTo("true");
        });
    }

    @Test
    void falseValueDoesNotRegisterBean() {
        runner.withPropertyValues(KEY + "=false").run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void nonTrueValueDoesNotRegisterBean() {
        runner.withPropertyValues(KEY + "=custom").run(context ->
                assertThat(context).doesNotHaveBean("auditMarker"));
    }

    @Test
    void higherPriorityPropertySourceWins() {
        runner.withInitializer(context -> {
            var sources = context.getEnvironment().getPropertySources();
            sources.addLast(new MapPropertySource(
                    "example-low-priority",
                    Map.of(KEY, "false")));
            sources.addFirst(new MapPropertySource(
                    "example-high-priority",
                    Map.of(KEY, "true")));
        }).run(context -> {
            assertThat(context.getEnvironment().getProperty(KEY))
                    .isEqualTo("true");
            assertThat(context).hasBean("auditMarker");
        });
    }

    @AutoConfiguration
    static class AuditAutoConfiguration {
        @Bean
        @ConditionalOnProperty(
                prefix = "demo.feature",
                name = "audit-enabled",
                havingValue = "true")
        String auditMarker() {
            return "audit-active";
        }
    }
}
~~~

**Run the test** from the root directory of a Maven/Gradle project configured with Spring Boot 3.3 test dependencies:

~~~bash
mvn -Dtest=AuditConditionTest test
# Or using Gradle wrapper on Linux/macOS:
./gradlew test --tests example.conditions.AuditConditionTest
~~~

**Expected result:** **5 tests PASS**; there is no fixed stdout because these are JUnit assertions. The final test deliberately creates two `MapPropertySource`s both containing `demo.feature.audit-enabled`. `addFirst` prioritizes the `true` value from `example-high-priority` over `false` from `example-low-priority`; the `auditMarker` bean is created. This is a **direct simulation of source ordering**, not a simulation of "command line" or "OS environment" source names in a real Spring Boot run.

From there, you can extend the test to verify canonical keys appearing in `application.yml`, overrides when profiles are active, or adding higher-priority sources. Always check both the **Environment value** and **whether the bean is registered**; checking only one side can miss the root cause.

## 6. Decision Table for Unexpected Configuration Behavior

| Symptom | Quick check | Fix direction |
| --- | --- | --- |
| `@ConditionalOnProperty` does not match even though file has `true` | Is there a `false` override from `--`, `-D`, OS env, profile, or JSON? | Find the effective value and winning source; change it at the right source. |
| Bean is still registered when value is `custom` | Was `havingValue = "true"` forgotten? | Explicitly specify `havingValue` for on/off flags. |
| Environment variable has no effect on the condition | Is it named `DEMO_FEATURE_AUDITENABLED` and passed to the Java process? | Normalize the name from the canonical key; check actual env at runtime. |
| `matchIfMissing` produces confusing results | Is the key truly absent or does it have `false`/empty string? | Distinguish **key absent** from **key present with failing value**. |
| Wrong only on a specific profile | Does `application-{profile}.yml` or `spring.config.import` override it? | Inspect all loaded config data and precedence order. |
| Toggling property after context startup does not change the bean | Conditions are evaluated at configuration/bean registration time | A separate runtime feature flag mechanism is needed if changes must occur without restart. |

**Another common mistake:** Using `@ConfigurationProperties` binding results to assert that `@ConditionalOnProperty` must match. The two mechanisms relate to configuration sources but are not identical in purpose; the condition also checks `havingValue`, `matchIfMissing`, evaluation timing, and key declaration. In addition, do not guess the winning source by looking at line order inside a single YAML file.

## 7. Self-Check Questions

1. From `billing.invoice.retry-enabled`, what is the corresponding canonical environment variable? **`BILLING_INVOICE_RETRYENABLED`** — replace dots with `_`, remove `-`, uppercase.
2. `application.yml` sets `demo.feature.audit-enabled=false`; the environment sets `DEMO_FEATURE_AUDITENABLED=true`; command line has no override. What is the usual effective value? **`true`**, because OS environment takes precedence over config data.
3. Adding command-line `--demo.feature.audit-enabled=false`. Does the `havingValue="true"` condition still match? **No**, because the effective value becomes `false`.
4. `@ConditionalOnProperty(prefix="demo.feature", name="audit-enabled")` encounters value `custom`. Does it match? **Yes**, by default it only rejects `false` and missing-property cases; use `havingValue="true"` if exact `true` is desired.
5. Why are both `/actuator/conditions` and `/actuator/env/...` useful? **Conditions** shows the reason for matching or not matching; **env** helps locate the effective value/source. Both must be accessed in a secured environment.

## Reference Documentation

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): canonical keys, relaxed binding, `PropertySource` order, profile config, `env`/`configprops`.
- [Spring Boot 3.3 — ConditionalOnProperty API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html): dashed `name`, `havingValue`, `matchIfMissing`, and collection limitations.
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): property conditions in auto-configuration.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): `env`, `configprops`, `conditions`, and endpoint exposure.

**Remember:** Write **one canonical key name** across code and documentation; when behavior does not match expectations, trace down to the **effective value and winning source** at condition evaluation time, then verify with a small test context.
