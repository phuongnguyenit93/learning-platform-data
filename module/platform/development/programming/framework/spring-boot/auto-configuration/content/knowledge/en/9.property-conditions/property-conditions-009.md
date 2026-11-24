# Distinguishing @ConfigurationProperties Default Values from Properties in Environment

## 1. An Easily Misunderstood Situation

When designing Spring Boot Auto Configuration, we often both declare a configuration class using `@ConfigurationProperties` and use `@ConditionalOnProperty` to toggle beans automatically.

Suppose the application has the following configuration:

```java
@ConfigurationProperties(prefix = "demo.feature")
public class FeatureProperties {
    private boolean enabled = true;

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }
}
```

There is no `demo.feature.enabled` in `application.properties` or any other configuration source. After Spring Boot creates and binds `FeatureProperties`, the value of `properties.isEnabled()` is still `true` thanks to the Java field initializer. Yet if you run:

```java
environment.getProperty("demo.feature.enabled");       // null
environment.containsProperty("demo.feature.enabled");  // false
```

the result indicates that the property **does not exist in Environment**. These are two queries about **two different sources of truth**:

- `FeatureProperties#getEnabled()` (in this example `isEnabled()`) reads the **state of the Java object after binding**, which may contain default values defined in code.
- `Environment#getProperty(...)` reads the **registered PropertySources** (such as `application.yml`, environment variables, system properties, command-line arguments). It does not read back fields of `FeatureProperties` to fill in missing properties.

Official Spring Boot documentation states clearly: default values defined in configuration properties **are not reflected back into Environment**. Therefore, a `@ConditionalOnProperty` condition can yield a different outcome from a `@ConfigurationProperties` bean getter value.

## 2. Two Phases and Two Kinds of "Default"

### 2.1. Values from Environment and the binding process

The usual processing flow can be pictured as follows:

```text
application.properties / application.yml / env vars / JVM -D / CLI args
                            |
                            v
               Environment + PropertySources
                    |                    |
                    v                    v
          Bean condition          ConfigurationProperties Binder
          @ConditionalOnProperty             |
          checks key/value                   v
                                    FeatureProperties object
                                    (keeps default or receives override)
```

- `Environment` aggregates configuration values actually present in the sources; it applies source precedence and can return `null` when a key is absent.
- `Binder` maps matching properties from `Environment` onto members of the `@ConfigurationProperties` object. If there is no value to bind, a field initialized in Java can keep its default. If a valid value exists, the binder updates the field according to the corresponding binding mechanism.
- `@ConditionalOnProperty` belongs to the condition mechanism when Spring registers configurations and bean definitions. It evaluates values from `Environment`; it **does not call getters on bound properties beans** to make its decision.

Having a default value in Java does not cause the corresponding property name to appear in `Environment`.

### 2.2. Places where defaults can be set

| Way to provide a default | Example | What does the `@ConfigurationProperties` bean see if key is missing? | Does `Environment` have that key? |
| --- | --- | --- | --- |
| Java field initializer | `private boolean enabled = true;` | `true` | No, if no other source |
| `@DefaultValue` for constructor binding | `@DefaultValue("true") boolean enabled` | `true` | No, if no other source |
| Java primitive default when uninitialized | `private boolean enabled;` | `false` | No, if no other source |
| Value in `application.properties` | `demo.feature.enabled=true` | `true` | Yes |
| Default PropertySource added to Environment | `SpringApplication.setDefaultProperties(...)` | Value bound from default source | Yes |
| Placeholder fallback at injection site | `@Value("${demo.feature.enabled:true}")` | Does not automatically change other properties beans | No, if no other source |

Read the table row by row independently: other configuration sources might already supply the key and override the default value. `@Value` is a way to inject a local value at the annotated site, not something that turns a placeholder fallback into a PropertySource.

### 2.3. Constructor binding and `@DefaultValue`

With Java 17+, defaults can be expressed using a record:

```java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "demo.feature")
public record FeatureSettings(
        @DefaultValue("true") boolean enabled,
        @DefaultValue("20") int batchSize
) {}
```

When registering this type via `@EnableConfigurationProperties(FeatureSettings.class)` or `@ConfigurationPropertiesScan`, if the two corresponding keys are absent, the binder creates an instance with `enabled() == true` and `batchSize() == 20`. However, `Environment#getProperty("demo.feature.enabled")` and `Environment#getProperty("demo.feature.batch-size")` can still be `null`. The `@DefaultValue` annotation belongs to binder logic; it does not add data to `Environment`.

Further distinction: `@DefaultValue` is subject to the binder's type conversion rules. With a mutable JavaBean, a field initializer is a common approach; with record/constructor binding, `@DefaultValue` is the direct way to declare parameter defaults.

## 3. Consequences for @ConditionalOnProperty

`@ConditionalOnProperty` checks **properties present in Environment**, with commonly used parameters:

- `prefix` + `name` determines the key, e.g., `prefix = "demo.feature", name = "enabled"` forms `demo.feature.enabled`.
- `havingValue = "true"` requires the key's value to match the string `true` under condition rules.
- If `havingValue` is not declared, the default condition matches when the key is **present** and its value **does not equal "false"**.
- `matchIfMissing = false` is the default: when the key does not exist, the condition does not match.
- `matchIfMissing = true`: when the key does not exist, the condition still matches, even though `Environment#getProperty(...)` may still return `null`.

Suppose `FeatureProperties.enabled` has Java default `true`. The two annotations below are **not equivalent**:

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true"
)
// Key missing: does not match.
```

```java
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
// Key missing: matches.
```

The second case accurately models the policy "enabled by default, disabled when the user sets false" when Java properties also default to `true`.

### Decision table

Assume no other PropertySource overrides it and the `FeatureProperties` class contains `private boolean enabled = true;`:

| Actually supplied configuration value | `properties.isEnabled()` after binding | `Environment#getProperty(...)` | `@ConditionalOnProperty(havingValue="true")` | With `matchIfMissing=true` |
| --- | --- | --- | --- | --- |
| Key not declared | `true` | `null` | No match | Match |
| `demo.feature.enabled=true` | `true` | `"true"` | Match | Match |
| `demo.feature.enabled=false` | `false` | `"false"` | No match | No match |

Note: `matchIfMissing` only controls the **missing key** situation; it does not treat any present value as valid. When using `havingValue = "true"`, non-matching values still cause the condition to fail. When `havingValue` is omitted, the default behavior is string comparison against `false`, not coercing every value to boolean like the binder.

**Point to remember:** `matchIfMissing=true` only changes the **condition outcome**; it does not modify `Environment` values, does not set fields on the properties bean, and does not register the missing key.

## 4. Runnable Test Example with Spring Boot 3.5 and Java 17

The following example simultaneously illustrates three states: property undeclared, set to `true`, and set to `false`. We create two bean types to compare:

- `StrictFeature`: appears only when Environment has `demo.feature.enabled=true`.
- `DefaultOnFeature`: appears when Environment has `true` **or the key is missing** thanks to `matchIfMissing=true`.

Both share a `FeatureProperties` class whose Java default is `true`. This clearly exposes that object defaults and condition defaults are two independent decisions.

Directory structure:

```text
parameter-default-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── example/
                └── PropertyDefaultAndConditionTest.java
```

**File `pom.xml`:**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>parameter-default-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

**File `src/test/java/example/PropertyDefaultAndConditionTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;

import static org.assertj.core.api.Assertions.assertThat;

class PropertyDefaultAndConditionTest {

    @ConfigurationProperties(prefix = "demo.feature")
    public static class FeatureProperties {
        private boolean enabled = true;

        public boolean isEnabled() {
            return this.enabled;
        }

        public void setEnabled(boolean enabled) {
            this.enabled = enabled;
        }
    }

    record StrictFeature() {}

    record DefaultOnFeature() {}

    @AutoConfiguration
    @EnableConfigurationProperties(FeatureProperties.class)
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
        )
        StrictFeature strictFeature() {
            return new StrictFeature();
        }

        @Bean
        @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true
        )
        DefaultOnFeature defaultOnFeature() {
            return new DefaultOnFeature();
        }
    }

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner().withConfiguration(
            AutoConfigurations.of(FeatureAutoConfiguration.class)
        );

    @Test
    void missingEnvironmentKeyDoesNotEraseJavaDefault() {
        runner.run(context -> {
            assertThat(context.getEnvironment()
                .containsProperty("demo.feature.enabled")).isFalse();
            assertThat(context.getEnvironment()
                .getProperty("demo.feature.enabled")).isNull();

            assertThat(context).hasSingleBean(FeatureProperties.class);
            assertThat(context.getBean(FeatureProperties.class)
                .isEnabled()).isTrue();

            assertThat(context).doesNotHaveBean(StrictFeature.class);
            assertThat(context).hasSingleBean(DefaultOnFeature.class);
        });
    }

    @Test
    void explicitTrueIsVisibleToBothBinderAndCondition() {
        runner.withPropertyValues("demo.feature.enabled=true")
            .run(context -> {
                assertThat(context.getEnvironment()
                    .getProperty("demo.feature.enabled"))
                    .isEqualTo("true");

                assertThat(context.getBean(FeatureProperties.class)
                    .isEnabled()).isTrue();

                assertThat(context).hasSingleBean(StrictFeature.class);
                assertThat(context).hasSingleBean(DefaultOnFeature.class);
            });
    }

    @Test
    void explicitFalseOverridesJavaDefaultAndDisablesFeatures() {
        runner.withPropertyValues("demo.feature.enabled=false")
            .run(context -> {
                assertThat(context.getEnvironment()
                    .getProperty("demo.feature.enabled"))
                    .isEqualTo("false");

                assertThat(context.getBean(FeatureProperties.class)
                    .isEnabled()).isFalse();

                assertThat(context).doesNotHaveBean(StrictFeature.class);
                assertThat(context).doesNotHaveBean(DefaultOnFeature.class);
            });
    }
}
```

Run in the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** all three JUnit tests pass, and Maven reports a successful build; the tests do not print a custom stdout string via `System.out.println`. You can check results in Surefire logs or `target/surefire-reports` report files. The example uses `ApplicationContextRunner` to create an isolated ApplicationContext for each case and avoid depending on configuration from a real application.

Explanation of each case:

1. **Missing key:** `Environment` confirms `demo.feature.enabled` does not exist. The binder keeps the field initializer `enabled=true`. `StrictFeature` is not created because `matchIfMissing=false` by default; `DefaultOnFeature` is created because `matchIfMissing=true` was declared.
2. **Key `true` present:** Environment holds the string `"true"`; the binder converts it to boolean `true`; both conditions match.
3. **Key `false` present:** Environment holds the string `"false"`; the binder overrides the Java default to `false`; neither condition matches.

The example places `@ConditionalOnProperty` directly on each `@Bean` method, while `@EnableConfigurationProperties` registers the properties bean separately. This verifies that the properties bean still exists even when a business bean is blocked by a condition.

## 5. How to Keep Default Policies Consistent?

### Approach A — Align Java default and matchIfMissing (usually suitable for starters)

If the feature defaults to **on**, the intentional declaration pair is:

```java
// In @ConfigurationProperties:
private boolean enabled = true;

// On the bean that should be enabled when the key is missing:
@ConditionalOnProperty(
    prefix = "demo.feature",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = true
)
```

Conversely, if the default is **off**, the field is left `false` (or Java default for primitive boolean) and the condition usually leaves `matchIfMissing=false`. This is a readable choice when the feature only needs default behavior at the decision point.

This requires maintainers to keep both declarations consistent. If one side changes its default without updating the other, auto-configuration branches can drift out of sync.

### Approach B — Put the default into an Environment configuration source

When multiple different components must read the default through `Environment`, register the default **as a real configuration source**. For example, in an application:

```properties
# src/main/resources/application.properties
demo.feature.enabled=true
```

When this file is loaded, `environment.containsProperty("demo.feature.enabled")` can return `true` and `getProperty(...)` returns `"true"`, unless a higher-precedence source overrides it. Another option for an application you launch is providing default properties:

```java
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(DemoApplication.class);
        application.setDefaultProperties(Map.of("demo.feature.enabled", "true"));
        application.run(args);
    }
}
```

This is a **conceptually standalone example** for a main application, not a required third file in the test in section 4. `setDefaultProperties` adds a source with default-level priority; higher-priority configuration sources can override it.

Practical limitation: an auto-configuration library should not arbitrarily mutate the Environment of the application using it. When writing a starter, `matchIfMissing` usually expresses the condition's default cleanly and within the proper scope.

### Approach C — Use a fallback directly where reading Environment

For code that needs to read a value regardless of whether the key is configured, you can explicitly supply a fallback:

```java
boolean enabled = environment.getProperty(
    "demo.feature.enabled", Boolean.class, true
);
```

When the property is absent, the statement above returns `true`. It **does not register** `demo.feature.enabled` into Environment. The same applies to `@Value`: `@Value("${demo.feature.enabled:true}")` uses a fallback for that injection site.

If writing a custom `Condition`, decide the fallback explicitly based on Environment; do not attempt to retrieve defaults by eagerly instantiating the `@ConfigurationProperties` bean during condition evaluation.

## 6. Common Misconceptions

1. **"If the field is initialized to `true`, then `@ConditionalOnProperty` must see `true`."** False: the field default belongs to the object, while the condition reads Environment. If the key is missing, decide policy using `matchIfMissing` or a real configuration source.
2. **"`@DefaultValue("true")` in a record automatically puts the key into Environment."** False: the annotation applies during constructor binding and does not create a PropertySource.
3. **"`@Value("${demo.feature.enabled:true}")` proves the key exists."** False: a placeholder with a fallback can produce an injected value even while `getProperty("demo.feature.enabled")` is still `null`.
4. **"Default `@ConditionalOnProperty` matches only when the value is boolean `true`."** Inaccurate: if `havingValue` is left at default, the condition matches when the key is present and not equal to the string `false`. For boolean switches, writing `havingValue = "true"` makes intent clear.
5. **"`matchIfMissing=true` is equivalent to assigning `enabled=true` on the bean."** False: this attribute only specifies how to evaluate the condition when the key is absent; it does not participate in bean binding.
6. **"Value `false` means missing key."** False: `demo.feature.enabled=false` is a **present** key with value `false`. `matchIfMissing=true` does not force the condition to match in that case.
7. **"Changing the properties bean field at runtime automatically creates/destroys conditional beans."** No: auto-configuration conditions are evaluated when building the context; mutating the object afterward does not re-trigger bean registration.
8. **"Any value visible in `@ConfigurationProperties` is a value declared in application.yml."** No: it may be a code-defined default, a result of type conversion during binding, or a value from other PropertySources.
9. **"Use the same default for every context without thinking about the source."** If code needs to expose a value through Environment for other parts to read, a field initializer may not suffice. Choose the mechanism based on where the value is consumed, especially for conditions that run early in the context lifecycle.

## 7. Checklist When Modifying an Auto Configuration

1. **Verify the exact key name:** e.g., `demo.feature.enabled`, aligned between `@ConfigurationProperties(prefix="demo.feature")` and `@ConditionalOnProperty(prefix="demo.feature", name="enabled")`.
2. **Determine desired behavior when the key is missing:** enable, disable, or depend on another condition; set `matchIfMissing` accordingly.
3. **Check the default when binder creates the object:** does the field initializer or `@DefaultValue` truly match the policy?
4. **Distinguish "missing", "true", "false":** write tests for all three states. Add tests for invalid values if config undergoes validation or boolean conversion.
5. **Check real configuration sources:** `application.yml`, env vars, CLI, test `withPropertyValues`, or default properties can inject keys into Environment without modifying Java classes.
6. **Avoid depending on beans when computing conditions:** conditions should rely on information available during bean registration; properties beans may not yet be instantiated/bound at that time.
7. **Document the starter's contract clearly:** if the feature defaults to on when the property is missing, document both the object value and how the condition selects its branch.

## 8. Self-Check Questions

**Question 1:** `FeatureProperties.enabled` defaults to `true`, and `demo.feature.enabled` is absent. What is `Environment#getProperty("demo.feature.enabled")`?  
**Answer:** `null`; the bound object can still have `enabled=true`.

**Question 2:** On a `@Bean`, there is `@ConditionalOnProperty(prefix="demo.feature", name="enabled", havingValue="true")`. Is the bean created when the key is missing?  
**Answer:** No, because `matchIfMissing` defaults to `false`.

**Question 3:** Add `matchIfMissing=true` and the user configures `demo.feature.enabled=false`. Does the condition match?  
**Answer:** No. `false` is a present value, not a missing-key case.

**Question 4:** Does `@DefaultValue("true")` let `@ConditionalOnProperty` read `true` from Environment?  
**Answer:** No. `@DefaultValue` only provides a default for binding.

**Question 5:** If you want `Environment#getProperty(...)` to also return a default when user configuration is missing, what must you do?  
**Answer:** Place the default in an actual `PropertySource`, such as a value in `application.properties` or the application's default properties. Calling `getProperty(key, type, default)` only supplies a fallback for that call; it does not modify Environment.

## Official Reference Documentation

- Spring Boot Reference — Externalized Configuration, **Default Values** and **@DefaultValue and Binding**: https://docs.spring.io/spring-boot/reference/features/external-config.html
- Spring Boot Reference — Creating Your Own Auto-configuration, **Property Conditions**: https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html
- Spring Boot API — `ConditionalOnProperty` (Spring Boot 3.5): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html

**Remember:** default values in `@ConfigurationProperties` belong to the **bound object**. `@ConditionalOnProperty` relies on **properties in Environment**, so to keep behavior consistent when a key is missing, choose the appropriate `matchIfMissing` or put the default into an actual PropertySource.
