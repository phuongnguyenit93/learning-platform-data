# AnyNestedCondition for Alternative Options

## 1. When Is OR Logic Needed in Auto-Configuration?

An auto-configuration usually applies only when multiple conditions hold together. For example, a library needs an SDK on the classpath, a feature flag enabled, and no alternative bean supplied by the application. This is AND logic: every condition must match.

However, some features support multiple alternative configuration options. For instance, an application might connect to Catalog via JNDI **or** via a JDBC URL. Having just one of the two options configured is enough basis for the auto-configuration branch to participate.

If you place two independent `@ConditionalOnProperty` annotations on the same configuration class, Spring combines them with AND. As a result, the application would have to configure both JNDI and URL, contradicting the "either one" requirement.

Spring Boot provides `AnyNestedCondition` to represent this case. It is a composite condition: **the overall condition matches when at least one condition on its nested classes matches**.

This lesson uses Java 17+, Spring Boot 3.3.13, Maven, and `ApplicationContextRunner`. After this lesson, you will be able to:

- Properly recognize OR logic in auto-configuration.
- Write a condition extending `AnyNestedCondition`.
- Choose the appropriate `ConfigurationPhase`.
- Combine inner OR logic with outer AND conditions on the configuration.
- Test each branch individually, the case with no matching branch, and the case where multiple branches match simultaneously.
- Distinguish "at least one" from "exactly one".

## 2. Understanding AnyNestedCondition Logic Properly

Suppose there are two options:

- `J`: the application enables connection via JNDI.
- `U`: the application enables connection via URL.

`AnyNestedCondition` uses inclusive OR logic:

| J | U | Result |
|---|---|---|
| false | false | No match |
| true | false | Match |
| false | true | Match |
| true | true | Match |

The last point is crucial: the OR of `AnyNestedCondition` **is not XOR**. When both branches match simultaneously, the overall condition still matches. It does not pick JNDI or URL by itself, nor does it establish a priority order.

If the business requirement is "only one option may be configured", you must check the case where both are enabled at another layer, such as validation inside the `@Bean` factory method or a custom condition specifically checking mutual exclusion.

### 2.1. Comparison with AND and NOR

Spring Boot has three commonly used composite condition classes:

| Class | Rule | Meaning |
|---|---|---|
| `AnyNestedCondition` | Matches if at least one nested condition matches | OR |
| `AllNestedConditions` | Matches only if every nested condition matches | AND |
| `NoneNestedConditions` | Matches if no nested condition matches | NOR / NOT OR |

Example with two conditions J and U:

- `AnyNestedCondition`: J or U or both.
- `AllNestedConditions`: both J and U must be true.
- `NoneNestedConditions`: both J and U are false.

These classes belong to package `org.springframework.boot.autoconfigure.condition` and all extend `AbstractNestedCondition`.

### 2.2. Conditions Inside a Single Branch Still Combine with AND

Each nested class can carry one or more condition annotations. Conditions placed on the same nested class must all match for that branch to match.

Example:

```java
@ConditionalOnClass(name = "com.vendor.jndi.Client")
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "jndi-enabled",
        havingValue = "true")
static class JndiBranch {
}
```

This JNDI branch has the logic:

`Client is on classpath AND jndi-enabled=true`

If the URL nested class has the logic:

`HTTP client is on classpath AND url-enabled=true`

then the overall condition is:

`(JNDI classpath AND JNDI flag) OR (HTTP classpath AND URL flag)`

You can also place shared conditions on the outer configuration, such as `@ConditionalOnClass` for a shared API or `@ConditionalOnProperty` for an overall feature flag. Outer conditions combine with the composite condition using AND.

## 3. Why Not Put Two @ConditionalOnProperty Annotations on the Same Class?

Suppose you write:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "jndi-enabled",
        havingValue = "true")
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = "url-enabled",
        havingValue = "true")
class CatalogConfiguration {
}
```

The configuration above requires both properties to equal `true`. Two annotations do not mean "pick one of the two".

Another approach is passing multiple names into the same `@ConditionalOnProperty`:

```java
@ConditionalOnProperty(
        prefix = "acme.catalog",
        name = {"jndi-enabled", "url-enabled"},
        havingValue = "true")
```

This is also AND: every name in the `name` array must satisfy the condition.

When you need OR across multiple condition annotations, using `AnyNestedCondition` expresses intent more directly. `@ConditionalOnExpression` can express OR expressions, but for standard configuration conditions, nested conditions are easier to separate into branches, read, and diagnose. In particular, avoid referencing beans inside SpEL conditions because those beans may be initialized very early during refresh.

## 4. Structure and API of AnyNestedCondition

`AnyNestedCondition`:

- Resides in package `org.springframework.boot.autoconfigure.condition`.
- Extends `AbstractNestedCondition`.
- Implements `Condition` and `ConfigurationCondition`.
- Has a constructor taking `ConfigurationCondition.ConfigurationPhase`.
- Collects outcomes from nested classes and returns the combined result.

A minimal condition:

```java
static class OnJndiOrUrl extends AnyNestedCondition {

    OnJndiOrUrl() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "jndi-enabled",
            havingValue = "true")
    static class OnJndi {
    }

    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "url-enabled",
            havingValue = "true")
    static class OnUrl {
    }
}
```

The nested member classes are static classes, each representing one alternative. They do not need methods or beans; the annotations on each class are enough to describe that branch's condition.

Then attach the composite condition to the configuration using `@Conditional`:

```java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJndiOrUrl.class)
class CatalogConnectionConfiguration {
}
```

`AnyNestedCondition` does not create beans itself. It only decides whether the configuration or bean guarded by `@Conditional` continues processing. Bean registration is still performed by `@Bean`, components, or other configuration.

### 4.1. What Is ConfigurationPhase?

The constructor requires choosing one of two phases:

| Phase | Timing | Suitable cases |
|---|---|---|
| `PARSE_CONFIGURATION` | While Spring is parsing `@Configuration` classes | Conditions based on classpath, properties, profiles, or resources that can be evaluated early |
| `REGISTER_BEAN` | When Spring registers regular beans; configuration classes have already been parsed | Conditions that need to observe already-registered bean definitions |

The example in this lesson only uses `@ConditionalOnProperty`, so `PARSE_CONFIGURATION` is the right choice: Spring can check the properties before deciding whether to include the nested configuration.

If a nested condition relies on existing beans, such as `@ConditionalOnBean`, consider `REGISTER_BEAN` so the condition is evaluated after configuration classes have been parsed. Choose the phase according to the member conditions' requirements, not arbitrarily.

Note: `REGISTER_BEAN` does not mean the condition will prevent any `@Configuration` class from being parsed. This phase is meant for evaluation when registering regular beans. If you need to exclude an entire configuration class early, the phase and placement must be designed accordingly.

### 4.2. A Single Branch Can Contain Multiple Conditions

For example, each option requires both classpath and a property:

```java
static class OnCatalogTransport extends AnyNestedCondition {

    OnCatalogTransport() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnClass(name = "com.vendor.jndi.JndiCatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "jndi-enabled",
            havingValue = "true")
    static class JndiBranch {
    }

    @ConditionalOnClass(name = "com.vendor.http.HttpCatalogClient")
    @ConditionalOnProperty(
            prefix = "acme.catalog",
            name = "url-enabled",
            havingValue = "true")
    static class HttpBranch {
    }
}
```

Here, `JndiBranch` requires both conditions to match. `HttpBranch` also requires both conditions to match. `OnCatalogTransport` only needs one of the two branches to match.

If you want to add a common requirement across all branches, put that condition on the guarded configuration:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(CatalogService.class)
@Conditional(OnCatalogTransport.class)
class CatalogConnectionConfiguration {
}
```

The combined result is then:

`CatalogService is on classpath AND (JNDI branch OR HTTP branch)`

## 5. Practical Example: Accepting JNDI or URL

We build an auto-configuration that creates `CatalogConnectionSettings` if the user enables one of two options:

- `acme.catalog.jndi-enabled=true` and provides `acme.catalog.jndi-name`.
- `acme.catalog.url-enabled=true` and provides `acme.catalog.url`.

If neither option is enabled, the configuration is not applied and no bean is created. If both are enabled, `AnyNestedCondition` still matches because it is inclusive OR; the example rejects the ambiguous configuration with a clear error.

### 5.1. Project Structure

```text
any-nested-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/demo/catalog/
    │       ├── CatalogConnectionSettings.java
    │       └── autoconfigure/
    │           └── CatalogAutoConfiguration.java
    └── test/
        └── java/demo/catalog/autoconfigure/
            └── CatalogAutoConfigurationTests.java
```

### 5.2. pom.xml

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
    <artifactId>any-nested-condition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

`spring-boot-autoconfigure` provides the annotations and composite conditions. `spring-boot-starter-test` provides JUnit 5, AssertJ, and `ApplicationContextRunner` for the tests.

### 5.3. CatalogConnectionSettings.java

```java
package demo.catalog;

public record CatalogConnectionSettings(
        String strategy,
        String location) {
}
```

This record represents the configured connection choice. `strategy` has the value `jndi` or `url`; `location` holds the corresponding JNDI name or URL.

### 5.4. CatalogAutoConfiguration.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.CatalogConnectionSettings;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class CatalogAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @Conditional(OnCatalogConnectionConfigured.class)
    static class CatalogConnectionConfiguration {

        @Bean
        CatalogConnectionSettings catalogConnectionSettings(
                Environment environment) {

            boolean jndiEnabled = environment.getProperty(
                    "acme.catalog.jndi-enabled",
                    Boolean.class,
                    false);

            boolean urlEnabled = environment.getProperty(
                    "acme.catalog.url-enabled",
                    Boolean.class,
                    false);

            if (jndiEnabled == urlEnabled) {
                throw new IllegalStateException(
                        "Enable exactly one of acme.catalog.jndi-enabled "
                                + "or acme.catalog.url-enabled.");
            }

            if (jndiEnabled) {
                String jndiName = requireText(
                        environment.getProperty("acme.catalog.jndi-name"),
                        "acme.catalog.jndi-name");

                return new CatalogConnectionSettings("jndi", jndiName);
            }

            String url = requireText(
                    environment.getProperty("acme.catalog.url"),
                    "acme.catalog.url");

            return new CatalogConnectionSettings("url", url);
        }

        private static String requireText(String value, String propertyName) {
            if (value == null || value.isBlank()) {
                throw new IllegalStateException(
                        "Property " + propertyName + " must have a value.");
            }
            return value;
        }
    }

    static class OnCatalogConnectionConfigured extends AnyNestedCondition {

        OnCatalogConnectionConfigured() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
                prefix = "acme.catalog",
                name = "jndi-enabled",
                havingValue = "true")
        static class JndiEnabled {
        }

        @ConditionalOnProperty(
                prefix = "acme.catalog",
                name = "url-enabled",
                havingValue = "true")
        static class UrlEnabled {
        }
    }
}
```

Reading the configuration part by part:

1. `OnCatalogConnectionConfigured` extends `AnyNestedCondition`, so the overall condition matches if either `JndiEnabled` or `UrlEnabled` matches.
2. Each nested class uses `@ConditionalOnProperty` with `havingValue="true"`. Therefore missing values, `false`, or strings other than `true` do not enable that branch.
3. `CatalogConnectionConfiguration` is applied only when the composite condition matches.
4. The bean method re-reads the flags to see which branch the user chose, then retrieves the corresponding JNDI name or URL.
5. If both flags are true, the bean method fails because the example requires exactly one option.
6. If one flag is enabled while its location value is missing, the bean method fails fast naming the property that must be supplied.

The OR condition and the "exactly one" check are two separate responsibilities. `AnyNestedCondition` only ensures at least one branch matches; the mutual exclusion check lives inside the factory method.

### 5.5. Registering Auto-Configuration in a JAR

When publishing a library for Spring Boot auto-discovery, add the file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

```text
demo.catalog.autoconfigure.CatalogAutoConfiguration
```

The test example below loads the class directly via `AutoConfigurations.of(...)`, so it does not read the imports file. For a consumer integration test verifying a packaged JAR, confirm this imports resource is present in the artifact.

## 6. Testing Branches with ApplicationContextRunner

`ApplicationContextRunner` creates a small context for each property combination. This is a convenient way to verify which branch matches and which bean is registered.

### 6.1. CatalogAutoConfigurationTests.java

```java
package demo.catalog.autoconfigure;

import demo.catalog.CatalogConnectionSettings;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class CatalogAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    CatalogAutoConfiguration.class));

    @Test
    void noAlternativeDoesNotCreateTheBean() {
        contextRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context)
                    .doesNotHaveBean(CatalogConnectionSettings.class);
        });
    }

    @Test
    void jndiAlternativeCreatesTheBean() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.jndi-enabled=true",
                        "acme.catalog.jndi-name=java:comp/env/jdbc/catalog")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            CatalogConnectionSettings.class);

                    assertThat(context.getBean(
                            CatalogConnectionSettings.class))
                            .isEqualTo(new CatalogConnectionSettings(
                                    "jndi",
                                    "java:comp/env/jdbc/catalog"));
                });
    }

    @Test
    void urlAlternativeCreatesTheBean() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=https://catalog.example.test")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(
                            CatalogConnectionSettings.class);

                    assertThat(context.getBean(
                            CatalogConnectionSettings.class))
                            .isEqualTo(new CatalogConnectionSettings(
                                    "url",
                                    "https://catalog.example.test"));
                });
    }

    @Test
    void bothAlternativesAreRejectedAsAmbiguous() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.jndi-enabled=true",
                        "acme.catalog.jndi-name=java:comp/env/jdbc/catalog",
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=https://catalog.example.test")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Enable exactly one of acme.catalog.jndi-enabled");
                });
    }

    @Test
    void enabledUrlRequiresANonBlankUrl() {
        contextRunner
                .withPropertyValues(
                        "acme.catalog.url-enabled=true",
                        "acme.catalog.url=")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasStackTraceContaining(
                                    "Property acme.catalog.url must have a value.");
                });
    }
}
```

### 6.2. Running the Tests

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn test
```

With the five tests above, the expected result is:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

This is the expected result of the example, not a log of an executed run. Maven Surefire may also print test names and execution times.

### 6.3. Test Matrix

| Test | JNDI flag | URL flag | Result |
|---|---:|---:|---|
| `noAlternativeDoesNotCreateTheBean` | false/missing | false/missing | Context succeeds, no bean |
| `jndiAlternativeCreatesTheBean` | true | false/missing | Bean uses strategy `jndi` |
| `urlAlternativeCreatesTheBean` | false/missing | true | Bean uses strategy `url` |
| `bothAlternativesAreRejectedAsAmbiguous` | true | true | Composite condition matches; factory method rejects configuration |
| `enabledUrlRequiresANonBlankUrl` | false/missing | true | Composite condition matches; factory method reports missing URL |

The two separate passing tests prove each OR branch can activate the configuration. The no-option test proves that when neither branch matches, the configuration is not applied. The both-enabled test proves `AnyNestedCondition` is inclusive OR, not XOR.

## 7. ConfigurationPhase and Bean-Based Conditions

The previous example used property conditions, so `PARSE_CONFIGURATION` was appropriate. However, when a branch depends on bean definitions, the phase must be chosen carefully.

For example, an integration may be enabled if the application has already registered a `DataSource` **or** a `ConnectionFactory`:

```java
static class OnDataSourceOrConnectionFactory extends AnyNestedCondition {

    OnDataSourceOrConnectionFactory() {
        super(ConfigurationPhase.REGISTER_BEAN);
    }

    @ConditionalOnBean(DataSource.class)
    static class OnDataSource {
    }

    @ConditionalOnBean(ConnectionFactory.class)
    static class OnConnectionFactory {
    }
}
```

Here the branches rely on bean conditions, so `REGISTER_BEAN` is the phase to consider so configuration classes have been parsed before inspecting bean definitions.

However, `@ConditionalOnBean` only sees bean definitions that have been processed up to the moment the condition runs. If the dependent bean is registered by another auto-configuration, control auto-configuration ordering with `@AutoConfiguration(after=...)` or an appropriate ordering mechanism. Do not rely on accidental ordering.

For a composite condition containing both property/classpath conditions and bean conditions, review all members and the required phase. Do not pick `PARSE_CONFIGURATION` just because it is the common example in documentation.

## 8. Reading Results in ConditionEvaluationReport

When auto-configuration does not run as expected, enable debug mode:

```bash
java -jar app.jar --debug
```

The Condition Evaluation Report shows which conditions matched and which did not. For `AnyNestedCondition`, look for:

- Whether the overall condition matched.
- How many nested members matched.
- Which JNDI or URL branch did not match.
- Whether another condition on the outer configuration is blocking the configuration.

`AnyNestedCondition` aggregates the outcomes of nested members and the messages from each branch. If at least one branch matches, the overall outcome matches. If no branch matches, the guarded configuration is not applied.

If the overall condition matches yet the bean still does not appear, inspect other conditions on `@Bean` methods, `@ConditionalOnMissingBean`, bean creation errors, or exceptions in the factory method. The composite condition governs only one layer of bean registration.

In tests, you can add a listener to print the report:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(CatalogAutoConfiguration.class))
        .run(context -> {
            // Assertions
        });
```

Required imports:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

## 9. When Should You Use AnyNestedCondition?

Use `AnyNestedCondition` when:

- There are two or more alternative configuration options.
- Each option can be described by its own condition annotations.
- You want each branch to have a clear name and condition.
- You want Spring Boot to aggregate outcomes and include them in the Condition Evaluation Report.
- You want to combine OR branches with common conditions on the outer configuration.

Practical examples:

| Scenario | Condition branches |
|---|---|
| Connect via JNDI or URL | `@ConditionalOnJndi` OR `@ConditionalOnProperty` |
| SDK A or SDK B is present | `@ConditionalOnClass(A.class)` OR `@ConditionalOnClass(B.class)` |
| Either of two web server types is present | Servlet condition OR reactive condition |
| Config file A or resource B exists | Resource condition A OR resource condition B |
| Feature enabled by property A or profile B | Property condition OR profile condition |

### 9.1. When Should You Write a Manual Condition?

If the logic is simply an OR of standard condition annotations, `AnyNestedCondition` is usually easier to read than a class implementing `Condition` directly.

A manual custom `Condition` is suitable when you need to:

- Compare multiple property values with custom rules.
- Check relationships between properties, such as requiring two values together or excluding one another.
- Read a resource's content rather than merely checking existence.
- Compute a condition from multiple sources that built-in annotations cannot express.

When writing a `Condition` manually, implement `matches(ConditionContext, AnnotatedTypeMetadata)` and ensure diagnostic messages are clear enough. If you need phase control, implement `ConfigurationCondition` as well.

### 9.2. When Should You Not Use It?

Do not use `AnyNestedCondition` if:

- There is only one condition.
- All conditions must hold together: use normal AND conditions or `AllNestedConditions`.
- None of the options may be present: consider `NoneNestedConditions`.
- The OR logic is tiny and a simple custom condition is clearer.
- The branches need to create completely different bean implementations without sharing configuration: sometimes splitting into two separate auto-configurations is easier to manage.

Do not create a composite condition just to wrap a single `@ConditionalOnProperty`.

## 10. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Must enable both JNDI and URL to run | Placed two independent condition annotations on the same class, creating AND logic | Use `AnyNestedCondition` with one nested class per option |
| One of the two branches is true yet overall condition is false | The nested class has an additional AND condition that is not satisfied | Check all annotations on each nested class |
| Both branches are true yet the application still errors | `AnyNestedCondition` is inclusive OR; factory method did not handle both enabled | Add priority rules or mutual exclusion validation |
| Assuming `AnyNestedCondition` picks the implementation itself | Composite condition only returns an overall result | Use a factory method or separate beans per branch to pick the implementation |
| Property is present yet does not match | Wrong `havingValue` or value is `false` | Check the final value in Environment and declare `havingValue` explicitly |
| Using `name` array in `@ConditionalOnProperty` to create OR | Multiple names in one annotation must all match | Create separate nested classes inside `AnyNestedCondition` |
| Bean-based condition does not see a newly declared bean | Chose too early a phase or wrong auto-configuration order | Consider `REGISTER_BEAN` and ordering |
| Condition matches yet the bean does not exist | `@ConditionalOnMissingBean`, another condition, or factory method error | Read the full Condition Evaluation Report and startup exception |
| `@ConditionalOnExpression` is hard to debug | Long SpEL expression or referencing beans too early | Use nested conditions if the logic is an OR between built-in annotations |
| Nested class names do not reflect their purpose | Condition branches are hard to read in code/reports | Name them clearly, such as `JndiEnabled`, `UrlEnabled`, `OnVendorSdk` |

## 11. Design and Testing Workflow

When an auto-configuration needs multiple alternative options:

1. Write the logic in plain words first: branch A or B, and are there any common conditions?
2. Extract each option into a nested static class.
3. Attach specific conditions to each nested class.
4. Extend `AnyNestedCondition` and pick the appropriate `ConfigurationPhase`.
5. Attach the composite condition with `@Conditional` to the configuration to guard.
6. If there are shared conditions, place them on the outer configuration to create an AND with the combined OR.
7. Decide clearly what happens when multiple branches match: accept, prioritize, or fail.
8. Use `ApplicationContextRunner` to test no branches, each branch individually, and multiple branches matching together.
9. When a test fails, read the Condition Evaluation Report to identify which nested member did not match.
10. Check the final bean and initialization errors separately; a matching condition does not guarantee the factory method creates the bean without error.

## 12. Self-Check Questions

**Question 1.** When does `AnyNestedCondition` match?

**Answer:** When at least one nested class condition matches.

**Question 2.** If two nested conditions both match, does the composite condition match?

**Answer:** Yes. It is inclusive OR, not XOR.

**Question 3.** Do two `@ConditionalOnProperty` annotations placed on the same configuration class create an OR?

**Answer:** No. Conditions on the same class are combined with AND.

**Question 4.** Which class should you use when the composite condition should match only if every nested condition is true?

**Answer:** `AllNestedConditions`.

**Question 5.** Which class should you use when the composite condition should match only if no nested condition is true?

**Answer:** `NoneNestedConditions`.

**Question 6.** Why did the JNDI/URL example still need to check when both flags are true?

**Answer:** `AnyNestedCondition` only checks that at least one branch is true. If exactly one branch is required, you must add validation or mutual exclusion logic.

**Question 7.** When nested conditions rely on properties and classpath, which phase is typically appropriate?

**Answer:** `PARSE_CONFIGURATION`, because those conditions can be evaluated while Spring parses configuration classes.

**Question 8.** When nested conditions need to observe bean definitions, which phase should you consider?

**Answer:** `REGISTER_BEAN`, because configuration classes have already been parsed by then.

## 13. Takeaways

- `AnyNestedCondition` is a Spring Boot composite condition that matches when **at least one** nested class condition matches.
- OR is inclusive: multiple branches matching simultaneously still produces true.
- Conditions on the same nested class combine with AND; nested classes are combined by `AnyNestedCondition` with OR.
- Use `@Conditional(OnYourCondition.class)` to attach a composite condition to a configuration or bean.
- Choose `PARSE_CONFIGURATION` for conditions that can be evaluated early such as properties/classpath; consider `REGISTER_BEAN` when depending on bean definitions.
- `AnyNestedCondition` does not select a branch or create beans itself; the factory method must still handle the actual choice.
- Test thoroughly: no matching branch, each branch individually, and multiple branches matching simultaneously.
- Use the Condition Evaluation Report to find which specific branch matched or did not match.

### Official Documentation

- [Spring Boot 3.3.13 API — AnyNestedCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html)
- [Spring Boot 3.3.13 API — AllNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html)
- [Spring Boot 3.3.13 API — NoneNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html)
- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Framework 6.1 — ConfigurationCondition.ConfigurationPhase](https://docs.spring.io/spring-framework/docs/6.1.19/javadoc-api/org/springframework/context/annotation/ConfigurationCondition.ConfigurationPhase.html)
