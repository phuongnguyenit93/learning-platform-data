# Reading ConditionEvaluationReport When Conditions Do Not Match in Spring Boot

## 1. Why doesn't a bean appear even though the application starts?

When working with Spring Boot, you may run into cases where `@Autowired` reports a missing bean, a starter fails to create an expected client, caching stays inactive, or an auto-configuration appears "skipped". A common reaction is adding `@Import`, changing package scans, or tweaking configs by trial and error. That easily hides the real cause: **one or more conditions (`@Conditional`) did not match**.

Spring Boot maintains **`ConditionEvaluationReport`**, a record of condition evaluations made during `ApplicationContext` creation. The report helps answer:

- Which configurations or `@Bean` methods were evaluated?
- Which conditions returned `match=true` and which returned `match=false`?
- Why did `@ConditionalOnProperty` fail: missing property, wrong key, or wrong value?
- Is an optional class genuinely absent, or did `@ConditionalOnClass` filter the auto-configuration?
- Did `@ConditionalOnMissingBean` "fail to match" because **the user already supplied a replacement bean** — i.e., **by design**?
- Was only a single bean method skipped, or was the entire auto-configuration class excluded from the context?
- Did the context **start normally without the bean**, or did it **fail to start** due to another exception?

**Lesson focus:** knowing how to read the report to pinpoint *which condition did not match and why*, then writing `ApplicationContextRunner` tests covering both positive and negative branches. The lesson provides a Java 17+, Spring Boot 3.5.x, JUnit Jupiter, and AssertJ project with real conditional auto-configurations, API-based report extraction, and `ConditionEvaluationReportLoggingListener`. No HTTP server or database connection is required.

## 2. How it works: from annotation to outcome

Suppose a metrics starter automatically creates `MetricClient` when:
- Optional class `com.example.conditionlab.optional.MetricTransport` is present.
- Property `sample.metrics.enabled=true`.
- The application has not already defined a `MetricClient`.

Conceptual flow:

```text
                 AUTO-CONFIGURATION CANDIDATE
                            |
                 @ConditionalOnClass?
                        /        \
                     no          yes
                     |            |
                 no bean    @ConditionalOnProperty?
                                  /        \
                                no          yes
                                |            |
                            no bean   @Bean metricClient()
                                            |
                                   @ConditionalOnMissingBean?
                                        /         \
                      User bean exists            No user bean
                             |                         |
                       BACK OFF                   CREATE DEFAULT
                             |                         |
                      no default bean            default bean
```

Spring Boot may evaluate conditions across multiple phases (parsing configuration, registering bean definitions, import filtering). **Do not treat this diagram as the strict order of all condition evaluations**: the exact ordering and number of outcomes recorded in the report depend on metadata, phases, and Spring Boot version.

For each reported condition, a `ConditionOutcome` has two main parts:
- `isMatch()` — `true` or `false`.
- `getMessage()` — explanation of why it evaluated that way, whose wording can change across versions.

A single source can have **multiple condition outcomes**. If at least one required condition fails, `ConditionAndOutcomes.isFullMatch()` is `false`. If all recorded outcomes for that source match, `isFullMatch()` is `true`.

**Do not equate these terms:**
- `positive match`: the condition was satisfied.
- `negative match`: the condition was not satisfied.
- `bean created`: actual registration/initialization outcome.
- `application context started`: startup status of the entire context.

A source with positive matches **does not necessarily** correspond to a single business bean. A negative match **is not necessarily** an error. And the report does not replace checking actual beans with `context.getBean(...)`.

## 3. What sections of information does the report contain?

In condition logs (when debug is enabled) or Actuator's `conditions` endpoint, you commonly see:

| Group | Meaning | How to read properly |
|---|---|---|
| **Positive matches** | Sources whose conditions evaluated as matching | Do not infer the bean is already working end-to-end |
| **Negative matches** | At least one condition did not match | Check `OnPropertyCondition`, `OnClassCondition`, `OnBeanCondition`, and messages |
| **Unconditional classes** | Auto-configuration candidates with no conditions | Does not mean every bean inside was created |
| **Exclusions** | Auto-configurations removed by exclude rules | Not a "negative match" from conditions |
| **Source** | Configuration name or `ClassName#beanMethod` | Distinguish class-level conditions from method-level ones |
| **Condition** | Type of check, e.g., `OnClassCondition` | Understand what question it asked |
| **Message** | Description of why the condition passed/failed | Use for diagnosis; avoid asserting exact characters |
| **Parent report** | Conditions from parent BeanFactory/context (if any) | Watch for management contexts/parent-child apps |

**Important note:** In Actuator output, a negative source can contain both **`notMatched` and `matched`** lists. That is not a contradiction: one condition on that source failed while other conditions on the same source succeeded.

### 3.1. Example of reading a property negative match

This is an **illustrative log example**, not an exact transcript of a run:

```text
NEGATIVE MATCHES
----------------
MetricsAutoConfiguration:
   Did not match:
      - @ConditionalOnProperty
        (sample.metrics.enabled=true)
        did not find property 'enabled'
        (OnPropertyCondition)
   Matched:
      - @ConditionalOnClass found required class
        'com.example.conditionlab.optional.MetricTransport'
        (OnClassCondition)
```

How to reason from this:
1. Source is `MetricsAutoConfiguration`.
2. A property condition did not match — so the auto-configuration was not applied.
3. The optional class condition matched; **no dependency fix needed**.
4. What needs fixing is the property key/value (or confirming the feature is disabled **by design**).
5. Never copy a log line as a snapshot assertion: phrasing can vary across patch versions, log formats, ordering, or metadata.

### 3.2. Example of reading an *intentional* negative match

```text
NEGATIVE MATCHES
----------------
MetricsAutoConfiguration#metricClient:
   Did not match:
      - @ConditionalOnMissingBean found a bean of type
        'com.example.conditionlab.api.MetricClient'
        (OnBeanCondition)
```

If the application already has `customMetricClient`, this report entry **is not a bug**: auto-configuration should **back off** to yield to the user's bean. What tests must verify is that the context has **one user `MetricClient`** and no default `metricClient`.

### 3.3. Class-level source vs method-level source

A class:

```java
@AutoConfiguration
@ConditionalOnProperty(
    prefix = "sample.metrics",
    name = "enabled",
    havingValue = "true")
class MetricsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MetricClient.class)
    MetricClient metricClient() {
        return new DefaultMetricClient("metric");
    }
}
```

This is an illustrative snippet lacking full imports; the complete project is below. In the report you may see:
- `com.example.conditionlab.autoconfigure.MetricsAutoConfiguration` — **class-level** conditions.
- `com.example.conditionlab.autoconfigure.MetricsAutoConfiguration#metricClient` — **bean-method-level** condition.

If class-level `@ConditionalOnProperty` fails, the bean method **may not be evaluated at all**, so a method entry need not appear. **Absence of a method entry does not prove the method condition matched**; check whether its enclosing class was evaluated first.

## 4. Java API for reading `ConditionEvaluationReport`

In Spring Boot 3.5.x, the two primary imports:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
```

Retrieving the report inside `ApplicationContextRunner.run(...)`:

```java
runner.run(context -> {
    ConditionEvaluationReport report =
            ConditionEvaluationReport.get(
                    context.getBeanFactory());

    var bySource = report.getConditionAndOutcomesBySource();

    bySource.forEach((source, outcomes) -> {
        System.out.println(source + " -> fullMatch="
                + outcomes.isFullMatch());

        outcomes.forEach(pair -> {
            boolean matched = pair.getOutcome().isMatch();
            String message = pair.getOutcome().getMessage();
            String conditionName =
                    pair.getCondition().getClass().getSimpleName();
            System.out.println("  " + conditionName
                    + " matched=" + matched
                    + " reason=" + message);
        });
    });
});
```

This is a **fragment** inside a class declaring `ApplicationContextRunner runner`; it shows how to inspect the report in the callback. In real applications, **filter `source` to the auto-configuration under investigation**, rather than printing every condition of a large Boot app (potentially thousands of lines containing internal configuration details).

### 4.1. Methods and data structures

| API | Type/result | Role |
|---|---|---|
| `ConditionEvaluationReport.get(beanFactory)` | `ConditionEvaluationReport` | Gets/creates report attached to `ConfigurableListableBeanFactory` |
| `ConditionEvaluationReport.find(beanFactory)` | report or `null` | Looks up existing report without creating one |
| `report.getConditionAndOutcomesBySource()` | `Map<String, ConditionAndOutcomes>` | Looks up class/method sources |
| `outcomes.isFullMatch()` | `boolean` | Did all outcomes for the source match? |
| `outcomes.iterator()` | Iterator of `ConditionAndOutcome` | Iterates each condition |
| `outcomes.stream()` | Stream of `ConditionAndOutcome` | Supports predicates/filtering; available since Boot 3.5 |
| `pair.getCondition()` | Spring `Condition` | Condition type evaluated |
| `pair.getOutcome()` | `ConditionOutcome` | Match flag and message |
| `outcome.isMatch()` | `boolean` | True/false for that specific condition |
| `outcome.getMessage()` | `String` or `null` | Explanatory message |
| `report.getExclusions()` | `List<String>` | Recorded auto-config exclusions |
| `report.getUnconditionalClasses()` | `Set<String>` | Auto-config classes evaluated without conditions |
| `report.getParent()` | Parent report or `null` | Reads hierarchy if present |

**Never assume `Map.get(source)` always returns non-null.** If `null`, the source may never have been imported, was excluded/early-filtered, had no recorded conditions, belongs to another context, or uses a different source name than expected. Verify configuration sources and exact class/method names before jumping to conclusions.

### 4.2. Printing *only* non-matching reasons

```java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach(
    (source, outcomes) -> {
        if (!source.contains("MetricsAutoConfiguration")) {
            return;
        }
        outcomes.forEach(pair -> {
            if (!pair.getOutcome().isMatch()) {
                System.out.println(
                    source + " | "
                    + pair.getCondition().getClass().getSimpleName()
                    + " | "
                    + pair.getOutcome().getMessage());
            }
        });
    });
```

This fragment runs inside a runner callback; no exact output is claimed since wording varies by Boot patch/condition implementation. This keeps focus **on the actual reason** without scrolling the entire report.

### 4.3. Avoiding bugs when asserting against the report

Do not write:

```java
assertThat(report.getConditionAndOutcomesBySource()
        .get("SomeAutoConfiguration"))
        .isNull();
// and then conclude 'enabled by default'
```

This is an illustrative anti-pattern. A `null` entry does not mean enabled or disabled; it only says **no entry with that key exists in the current map**. Tests must verify:
1. Was the auto-config class passed into the runner/context?
2. Is the key a fully qualified name or `ClassName#beanMethod`?
3. Are `report.getExclusions()` or import condition filters involved?
4. Is the expected bean present/absent?
5. Did the context start cleanly or fail?

## 5. `ConditionEvaluationReportLoggingListener`: inspect reports without iterating the map

Spring Boot provides `ConditionEvaluationReportLoggingListener`, an `ApplicationContextInitializer` dedicated to condition reporting. In tests:

```java
new ApplicationContextRunner()
    .withConfiguration(
        AutoConfigurations.of(MetricsAutoConfiguration.class))
    .withInitializer(
        ConditionEvaluationReportLoggingListener.forLogLevel(
            LogLevel.INFO))
    .withPropertyValues(
        "sample.metrics.enabled=false")
    .run(context -> {
        assertThat(context)
            .doesNotHaveBean(MetricClient.class);
    });
```

This fragment requires the imports/demo classes below. `LogLevel.INFO` emits the report through the logging framework. **It is not guaranteed to appear verbatim in the JUnit console** if the runner/build/test logger capture or log levels suppress it. Do not snapshot output expecting immutable messages.

Options:
- `forLogLevel(LogLevel.INFO)`: useful for diagnostic tests.
- `forLogLevel(LogLevel.DEBUG)`: useful when reports should appear only at DEBUG.
- Inspect the API directly in tests for **logic assertions**, and use the listener for **human diagnostics**.

**Do not reuse the same listener instance across multiple ApplicationContexts** when Javadoc specifies a single-context lifecycle; `forLogLevel(...)` creates one for that runner. Avoid printing full reports across hundreds of CI tests, as it gets very noisy.

## 6. Minimal runnable project: Spring Boot 3.5.x / Java 17

Files in the example:

```text
build.gradle
src/main/java/com/example/conditionlab/app/
    ConditionLabApplication.java
src/main/java/com/example/conditionlab/api/
    MetricClient.java
    DefaultMetricClient.java
src/main/java/com/example/conditionlab/optional/
    MetricTransport.java
src/main/java/com/example/conditionlab/autoconfigure/
    MetricsAutoConfiguration.java
src/main/resources/META-INF/spring/
    org.springframework.boot.autoconfigure.AutoConfiguration.imports
src/test/java/com/example/conditionlab/autoconfigure/
    MetricsConditionReportTest.java
```

**Why split packages like this?** `ConditionLabApplication` sits in `com.example.conditionlab.app`, not the parent `com.example.conditionlab`. The demo app's component scan therefore does not pick up `MetricsAutoConfiguration` in another package. Production discovery uses `AutoConfiguration.imports`; `ApplicationContextRunner` registers the auto-config explicitly.

### 6.1. Gradle build (Groovy DSL)

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'

    annotationProcessor 'org.springframework.boot:spring-boot-autoconfigure-processor'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter` supplies core Boot/Spring logging and auto-configuration. `starter-test` brings JUnit Jupiter, AssertJ, and test runner classes. `spring-boot-autoconfigure-processor` generates optional auto-config metadata so Boot can early-filter some configurations; **it does not replace the `AutoConfiguration.imports` discovery file**. No `starter-web`, datasource, or Docker needed to test bean conditions in the example.

Java sources use fixed package names and make no Internet calls; running `./gradlew` requires an existing **Gradle wrapper**. The sample project does not fabricate "build successful" stdout without running an actual build.

### 6.2. Boot application class

File `src/main/java/com/example/conditionlab/app/ConditionLabApplication.java`:

```java
package com.example.conditionlab.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConditionLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ConditionLabApplication.class, args);
    }
}
```

Main can be used for a discovery smoke test, while `ApplicationContextRunner` tests do not launch main. Without a web starter, `bootRun` starts only a non-web application context.

### 6.3. Interface, default implementation, and optional marker

File `src/main/java/com/example/conditionlab/api/MetricClient.java`:

```java
package com.example.conditionlab.api;

@FunctionalInterface
public interface MetricClient {
    String emit(String eventName);
}
```

File `src/main/java/com/example/conditionlab/api/DefaultMetricClient.java`:

```java
package com.example.conditionlab.api;

import java.util.Objects;

public final class DefaultMetricClient
        implements MetricClient {

    private final String prefix;

    public DefaultMetricClient(String prefix) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    @Override
    public String emit(String eventName) {
        return prefix + ":" + Objects.requireNonNull(eventName);
    }
}
```

File `src/main/java/com/example/conditionlab/optional/MetricTransport.java`:

```java
package com.example.conditionlab.optional;

/**
 * Marker representing an optional dependency.
 */
public final class MetricTransport {
    private MetricTransport() {
    }
}
```

A real starter would use a class from Micrometer, an SDK, or an external transport module. Here the marker sits inside the project so code runs standalone; `FilteredClassLoader` simulates the class **missing from the classpath** without editing `build.gradle` between tests.

### 6.4. Auto-configuration with both class-level and bean-method conditions

File `src/main/java/com/example/conditionlab/autoconfigure/MetricsAutoConfiguration.java`:

```java
package com.example.conditionlab.autoconfigure;

import com.example.conditionlab.api.DefaultMetricClient;
import com.example.conditionlab.api.MetricClient;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(
    name = "com.example.conditionlab.optional.MetricTransport")
@ConditionalOnProperty(
    prefix = "sample.metrics",
    name = "enabled",
    havingValue = "true",
    matchIfMissing = false)
public class MetricsAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(MetricClient.class)
    public MetricClient metricClient(
            @Value("${sample.metrics.prefix:metric}") String prefix) {
        return new DefaultMetricClient(prefix);
    }
}
```

**Mechanism:**
- If `MetricTransport` is missing, the classpath condition fails and the auto-config class is excluded as expected.
- If `sample.metrics.enabled` is absent/false, `OnPropertyCondition` is negative. **This can be intentional**: the starter does not enable itself automatically.
- When both class and property match, `@ConditionalOnMissingBean` inspects the `MetricClient` bean type.
- If the user provides their own `MetricClient`, the default `metricClient` bean is not registered.
- When all required conditions match, the default implementation returns strings like `metric:order-created`; `sample.metrics.prefix` can change the prefix.

**Easy-to-confuse points:**
- `@ConditionalOnClass` and `@ConditionalOnProperty` sit at the **class level**.
- `@ConditionalOnMissingBean` sits at the **`@Bean` method level**.
- A `@Bean` method skipped by `@ConditionalOnMissingBean` **does not** mean the auto-config class itself failed to load.
- `@Value` resolution happens at bean creation time; property bind/injection failures differ from unmatched conditions.

### 6.5. Imports metadata for auto-configuration discovery

Exact file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Contents:

```text
com.example.conditionlab.autoconfigure.MetricsAutoConfiguration
```

When building the starter JAR, this resource must reside under `META-INF/spring/`. In Boot 3.x, `AutoConfiguration.imports` is the standard auto-configuration discovery mechanism.

**Unit test limitation:** `ApplicationContextRunner.withConfiguration(AutoConfigurations.of(MetricsAutoConfiguration.class))` loads the class **directly**. Thus runner tests can pass even if you accidentally delete `AutoConfiguration.imports`. Add artifact resource checks or a real `@SpringBootTest` smoke test when publishing a starter.

## 7. JUnit tests: reading the report programmatically and verifying outcomes

File `src/test/java/com/example/conditionlab/autoconfigure/MetricsConditionReportTest.java`:

```java
package com.example.conditionlab.autoconfigure;

import com.example.conditionlab.api.DefaultMetricClient;
import com.example.conditionlab.api.MetricClient;
import com.example.conditionlab.optional.MetricTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class MetricsConditionReportTest {

    private static final String AUTO_SOURCE =
            MetricsAutoConfiguration.class.getName();

    private static final String BEAN_SOURCE =
            AUTO_SOURCE + "#metricClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                        AutoConfigurations.of(
                            MetricsAutoConfiguration.class));

    private static ConditionAndOutcomes reportFor(
            org.springframework.boot.test.context.assertj
                    .AssertableApplicationContext context,
            String source) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getBeanFactory());

        ConditionAndOutcomes matches =
                report.getConditionAndOutcomesBySource()
                        .get(source);

        assertThat(matches)
                .as("Expected a recorded condition source: " + source)
                .isNotNull();

        return matches;
    }

    @Test
    void missingPropertyProducesOnPropertyNegativeMatch() {
        runner.run(context -> {
            assertThat(context.getStartupFailure()).isNull();
            assertThat(context)
                .doesNotHaveBean(MetricClient.class);

            ConditionAndOutcomes conditions =
                    reportFor(context, AUTO_SOURCE);

            assertThat(conditions.isFullMatch()).isFalse();

            assertThat(conditions.stream().anyMatch(pair ->
                !pair.getOutcome().isMatch()
                && pair.getCondition().getClass()
                        .getSimpleName()
                        .equals("OnPropertyCondition")))
                .isTrue();
        });
    }

    @Test
    void falsePropertyAlsoHasNegativeOutcome() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                ConditionAndOutcomes conditions =
                        reportFor(context, AUTO_SOURCE);

                assertThat(conditions.isFullMatch()).isFalse();

                assertThat(conditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()))
                    .isTrue();
            });
    }

    @Test
    void wrongPropertyKeyDoesNotEnableAutoConfiguration() {
        runner.withPropertyValues(
                "sample.metric.enabled=true")
            .run(context -> {
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                assertThat(reportFor(context, AUTO_SOURCE)
                    .isFullMatch()).isFalse();
            });
    }

    @Test
    void enabledPropertyHasPositiveMatchesAndDefaultBean() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context)
                    .hasBean("metricClient");

                MetricClient client =
                    context.getBean(MetricClient.class);

                assertThat(client)
                    .isInstanceOf(DefaultMetricClient.class);
                assertThat(client.emit("order-created"))
                    .isEqualTo("metric:order-created");

                assertThat(
                    reportFor(context, AUTO_SOURCE)
                        .isFullMatch()).isTrue();

                assertThat(
                    reportFor(context, BEAN_SOURCE)
                        .isFullMatch()).isTrue();
            });
    }

    @Test
    void userBeanBackOffIsNegativeOnBeanNotAnError() {
        runner.withUserConfiguration(
                CustomMetricConfiguration.class)
            .withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context)
                    .hasBean("customMetricClient");

                assertThat(context)
                    .doesNotHaveBean("metricClient");

                assertThat(
                    context.getBean(MetricClient.class)
                        .emit("order-created"))
                    .isEqualTo("custom:order-created");

                // Class-level conditions still match.
                assertThat(
                    reportFor(context, AUTO_SOURCE)
                        .isFullMatch()).isTrue();

                // Bean-method condition is negative because user bean exists.
                ConditionAndOutcomes methodConditions =
                        reportFor(context, BEAN_SOURCE);

                assertThat(methodConditions.isFullMatch())
                    .isFalse();

                assertThat(methodConditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()
                    && pair.getCondition().getClass()
                        .getSimpleName()
                        .equals("OnBeanCondition")))
                    .isTrue();
            });
    }

    @Test
    void absentOptionalClassPreventsDefaultBean() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .withClassLoader(
                new FilteredClassLoader(
                    MetricTransport.class))
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);

                // Some phases/metadata filters may record outcomes
                // at import level; test avoids forcing exact report key/message.
                ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(
                        context.getBeanFactory());

                assertThat(report).isNotNull();
            });
    }

    @Test
    void prefixPropertyChangesCreatedBeanBehavior() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true",
                "sample.metrics.prefix=custom-prefix")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(MetricClient.class);

                assertThat(context.getBean(MetricClient.class)
                    .emit("order-created"))
                    .isEqualTo("custom-prefix:order-created");
            });
    }

    @Test
    void reportMessagesExplainConditionsButAreNotSnapshots() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .run(context -> {
                ConditionAndOutcomes conditions =
                    reportFor(context, AUTO_SOURCE);

                assertThat(conditions.stream().anyMatch(pair ->
                    !pair.getOutcome().isMatch()
                    && pair.getOutcome().getMessage() != null))
                    .isTrue();

                // Do not assert exact message phrasing:
                // wording can change across Boot versions.
            });
    }

    @Test
    void separateRunnerScenariosDoNotLeakProperties() {
        runner.withPropertyValues(
                "sample.metrics.enabled=true")
            .run(context ->
                assertThat(context)
                    .hasSingleBean(MetricClient.class));

        runner.run(context ->
            assertThat(context)
                .doesNotHaveBean(MetricClient.class));
    }

    @Test
    void intentionalBeanFailureIsNotAConditionMismatch() {
        runner.withUserConfiguration(
                FailingConfiguration.class)
            .run(context -> {
                assertThat(context).hasFailed();
                assertThat(context.getStartupFailure())
                    .hasRootCauseInstanceOf(
                        IllegalStateException.class);
            });
    }

    @Test
    void diagnosticListenerCanLogConditionReport() {
        runner.withPropertyValues(
                "sample.metrics.enabled=false")
            .withInitializer(
                ConditionEvaluationReportLoggingListener
                    .forLogLevel(LogLevel.INFO))
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();
                assertThat(context)
                    .doesNotHaveBean(MetricClient.class);
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomMetricConfiguration {

        @Bean
        MetricClient customMetricClient() {
            return event -> "custom:" + event;
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class FailingConfiguration {

        @Bean
        String failingBean() {
            throw new IllegalStateException(
                "Synthetic bean initialization failure");
        }
    }
}
```

**Import note for `AssertableApplicationContext`:** In the `reportFor` helper above, the type name was line-wrapped across the qualified name to fit horizontally. In IDE Java code, replace it with a single-line import:

```java
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
```

and update the helper signature to `reportFor(AssertableApplicationContext context, String source)`. Note that **Java does not permit wrapping a qualified identifier around a lone dot without proper tokenization**; the explicit import version is safe for copy/paste. All other classes in the sample have explicit imports.

### 7.1. Key verifications performed

| Test | Simulated issue | Right evidence |
|---|---|---|
| `missingPropertyProducesOnPropertyNegativeMatch` | Enabled flag missing | Bean absent + class-level negative `OnPropertyCondition` |
| `falsePropertyAlsoHasNegativeOutcome` | `enabled=false` | Bean absent + `isFullMatch=false` |
| `wrongPropertyKeyDoesNotEnableAutoConfiguration` | Wrong key `sample.metric.enabled` | Correct property still missing |
| `enabledPropertyHasPositiveMatchesAndDefaultBean` | `enabled=true` | Default bean has right type/name/behavior and class/method positive |
| `userBeanBackOffIsNegativeOnBeanNotAnError` | User defined MetricClient | Custom bean wins; method `OnBeanCondition` negative |
| `absentOptionalClassPreventsDefaultBean` | Optional marker hidden | Class condition unmatched, context still starts |
| `prefixPropertyChangesCreatedBeanBehavior` | Custom prefix | Bean receives real property, output changes |
| `reportMessagesExplainConditionsButAreNotSnapshots` | Need to read reason | Message exists yet not asserted verbatim |
| `separateRunnerScenariosDoNotLeakProperties` | Multiple runner scenarios | No `Environment` leak from earlier case |
| `intentionalBeanFailureIsNotAConditionMismatch` | Factory method throws | `getStartupFailure()`, not mistaken for negative match |
| `diagnosticListenerCanLogConditionReport` | Need report logged | Listener registered at INFO, no stdout snapshot |

**Why not assert only the report?** The code also asserts bean presence/absence and `emit(...)` behavior, because a positive report is not a functional test. **Why not assert the full message text?** Message phrasing depends on Spring Boot version, formatting, bean names, and metadata. Tests should assert condition booleans/types, treating messages as investigative docs.

### 7.2. Crucial point when context startup fails

`ApplicationContextRunner` lets you observe startup errors in the callback. When `@Bean failingBean()` throws `IllegalStateException`, `assertThat(context).hasFailed()` and `getStartupFailure()` clearly indicate a **bean creation failure**, not a property condition mismatch.

In a failed context, some operations on `BeanFactory` or closed beans may no longer be safe. **Do not try fetching the report via `getBeanFactory()` after a failed refresh assuming it is always available.** Prefer reading the startup failure/root cause and enabling `--debug`/diagnostic listeners when needed.

## 8. When a source does not appear in the report: reasoning accurately

Not every "missing bean" scenario yields a tidy negative entry under the exact name you search for.

### 8.1. Auto-configuration was never imported

Causes:
- Missing entry in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- Misspelled package/class name or file not packaged in the JAR.
- Test runner loaded only another auto-config.
- Auto-configuration excluded via `spring.autoconfigure.exclude` or `@SpringBootApplication(exclude=...)`.

In these cases, the report may **contain no entry** for the target class. Check source discovery/imports before editing `@ConditionalOnProperty`. In runners, use `withConfiguration(AutoConfigurations.of(...))` explicitly. In real apps, inspect JAR resources and exclusions.

### 8.2. Condition checked during early auto-configuration filtering

Spring Boot includes `AutoConfigurationImportFilter` and metadata generated by `spring-boot-autoconfigure-processor`. Some `@ConditionalOnClass` checks can run before the configuration class is fully registered.

This can affect recorded report details, logging order, or bean method entries. **Do not tie tests to a specific source key/message if the class was filtered in an early phase.** Use `FilteredClassLoader` and assert the context lacks the bean; when an entry appears in the report, read its outcome as supporting diagnostics.

### 8.3. Method-level entry missing because class-level condition failed

If class-level `@ConditionalOnProperty` does not match, Spring usually does not process nested `@Bean` methods of that class. Hence the report may omit:
`MetricsAutoConfiguration#metricClient`

That **does not mean `@ConditionalOnMissingBean` always matches**. It may simply **never have been evaluated in that scenario**. User-override tests must ensure class conditions match first before inspecting bean-method outcomes.

### 8.4. Conditions not reported through Boot's mechanism

`ConditionEvaluationReport` is especially useful for auto-configuration's `SpringBootCondition`s. A custom `@Conditional` that does not extend/integrate with Boot's reporting mechanism may not appear like a built-in Boot condition. Read the condition's implementation, diagnostic logs, and bean registration results rather than treating the report as an absolute trace of every JVM decision.

## 9. Using the DEBUG report when running a Spring Boot application

When debugging a real app (not a runner), Spring Boot prints the **Conditions Evaluation Report** when debug mode is enabled.

Gradle wrapper example:

```bash
./gradlew bootRun --args='--debug'
```

With a built executable JAR:

```bash
java -jar build/libs/your-application.jar --debug
```

The JAR name in the second command is an **illustrative path**: replace it with your actual artifact. It is not fixed stdout. You can set `debug=true` via Spring `application.properties`/environment, noting that not every logger switches to DEBUG; Boot debug mode enables core loggers and the condition report.

**Runtime report reading workflow:**
1. Locate the source matching the auto-configuration near the missing feature.
2. Check `Negative matches` first to find the non-matching condition.
3. Read `OnClassCondition` to see which class is missing.
4. Read `OnPropertyCondition` to see which property/key failed.
5. Read `OnBeanCondition` to see which bean type/name is already present or still missing.
6. If class-level matched, look for method sources like `#beanMethod`.
7. If the source is absent, check discovery/imports, exclusions, and context hierarchy.
8. Cross-check whether the bean actually exists (`ApplicationContext`, Actuator `beans` when allowed).
9. Adjust conditions only when **expected behavior** differs from actual behavior; never "fix" an intentional negative match.
10. Dial logging back to safe operational levels once investigation finishes.

**Read logs calmly even on healthy startup:** A normal app startup can have hundreds of legitimate negative matches (e.g., no WebFlux classes in a Servlet app, no datasource, cache, or messaging). The report is not a list of errors that all need fixing.

## 10. Actuator `/actuator/conditions`: inspecting the report on a running app

When an application includes **`spring-boot-starter-actuator`**, Actuator exposes the `conditions` endpoint reflecting evaluated conditions and match/mismatch reasons.

Dependency snippet:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
```

Example properties for a **protected internal development environment**:

```properties
management.endpoints.web.exposure.include=health,conditions
```

By default, only a few endpoints like `health` are exposed over HTTP. Reading `/actuator/conditions` requires the actuator dependency, endpoint access permitted (Spring Boot 3.5 endpoint access policy), web exposure enabled, and proper authentication/authorization if Security is active.

**Security:** Conditions can reveal package names, library presence, bean names, and configuration internals. Never expose this endpoint on the public Internet. Use a private management port/network, RBAC, and appropriate masking/logging policies. **Only query the endpoint when already enabled and permitted**; never turn it on in production solely for test convenience.

### 10.1. Key JSON structure

The Actuator response can look like this **abbreviated illustration**:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "MetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "required class was found"
          }
        ]
      },
      "negativeMatches": {
        "MetricsAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "required property was not found"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "required class was found"
            }
          ]
        }
      },
      "unconditionalClasses": [],
      "parentId": null
    }
  }
}
```

This is **not** exact JSON emitted by the demo project: real keys/IDs, source names, and messages depend on context/version. Its purpose is showing:
- `contexts` grouped by application context ID.
- `positiveMatches` contains condition/name and message.
- `negativeMatches` has two arrays: `notMatched` and `matched`.
- `unconditionalClasses` lists unconditional auto-configurations.
- `parentId` (when present) shows context hierarchy relations.

In real reports, the same source does not simultaneously appear in both positive and negative sections like the condensed JSON illustration above; the diagram only illustrates field structure, **not claiming test results put one source in both states simultaneously**. When reading the live endpoint, follow Spring Boot 3.5's Actuator API schema.

### 10.2. Actuator `conditions` vs `beans` and `env`

- `/actuator/conditions`: **why** conditions matched or failed to match.
- `/actuator/beans`: **what is registered** in the bean factory.
- `/actuator/env`: property sources and values (subject to sanitization/access controls).
- `/actuator/configprops`: bound configuration properties of beans.

All four endpoints carry internal information-disclosure risk; never expose all of them just for one debugging session. When a data source misbehaves, combining `conditions` with **actual property keys** and the bean list isolates bugs quickly, provided access is restricted and audited.

## 11. Failure matrix and reading messages by condition type

### 11.1. `@ConditionalOnProperty`

Example:
`@ConditionalOnProperty(prefix="sample.metrics", name="enabled", havingValue="true", matchIfMissing=false)`.

| Environment input | Outcome | What to verify |
|---|---|---|
| No `sample.metrics.enabled` | Negative | Missing property is expected disabled |
| `sample.metrics.enabled=false` | Negative | Right disable value |
| `sample.metrics.enabled=enabled` | Negative | Value is not `true` |
| `sample.metric.enabled=true` | Negative | Wrong **prefix/key** |
| `sample.metrics.enabled=true` | Positive if other conditions hold | Default bean or back-off if user bean exists |
| Prefix present yet `enabled` missing | Negative | Prefix alone does not enable feature |

**Caution:** When `havingValue` is omitted, `@ConditionalOnProperty` has different semantics (property exists and is not `false` per Spring Boot), not requiring Boolean `true`. Read the exact annotation and outcome message before deciding.

### 11.2. `@ConditionalOnClass` / `@ConditionalOnMissingClass`

If a class-level condition is negative:
- Optional JAR may be absent from the runtime classpath.
- Artifact may be the wrong version or class moved packages.
- Test has a `FilteredClassLoader` intentionally hiding the class.
- Meta-annotation/custom condition may use the wrong class name.

**Do not blindly add the dependency** if the feature is intentionally disabled without using that library. When the class genuinely needs to be present, check Gradle/Maven dependency resolution and runtime classpath. If an optional class is referenced directly in a `@Bean` return type, isolate it inside a nested `@Configuration` with `@ConditionalOnClass` to avoid `NoClassDefFoundError` before condition evaluation.

### 11.3. `@ConditionalOnBean` / `@ConditionalOnMissingBean`

Suppose:

```java
@Bean
@ConditionalOnMissingBean(MetricClient.class)
MetricClient metricClient() {
    return new DefaultMetricClient("metric");
}
```

This is a fragment of `MetricsAutoConfiguration`. If a custom `MetricClient` exists, a **negative** condition is right. With the inverse condition `@ConditionalOnBean(DataSource.class)`, a missing datasource bean can block a dependent auto-configuration.

**Evaluation order of bean conditions is critical.** Spring Boot normally ensures auto-configurations run after user configurations; when two auto-configurations depend on each other, use `@AutoConfiguration(after=...) / before=...` to adjust evaluation order. A "missing bean" outcome may reflect that **the bean definition type was unknown at evaluation time**, not necessarily that Spring can never create that bean.

### 11.4. `@ConditionalOnWebApplication`

A Servlet-only auto-config may show negative inside a non-web `ApplicationContextRunner`. That is **expected** because the runner creates a narrow context.

To test accurately:
- Servlet: `WebApplicationContextRunner`.
- Reactive: `ReactiveWebApplicationContextRunner`.
- Web-independent: `ApplicationContextRunner`.

Do not switch to `@SpringBootTest(RANDOM_PORT)` just to test a simple condition when a web context runner suffices.

### 11.5. `@ConditionalOnResource` and `@ConditionalOnExpression`

`@ConditionalOnResource` depends on resource presence: wrong file paths/classpath resources cause negatives. In tests, use explicit test resources and avoid depending on current working directory unless the contract requires it.

`@ConditionalOnExpression` uses SpEL and can cause early bean initialization if expressions reference beans, leaving beans under-post-processed. Never use a complex expression in place of `@ConditionalOnProperty` when testing a simple property flag.

### 11.6. Combined conditions

A single source can show both `OnClassCondition` positive and `OnPropertyCondition` negative. Then **full match is false**, yet the positive classpath outcome narrows your search: stop hunting dependency issues when the real cause is a missing property.

Read **all recorded outcome entries**, not just the first negative line. Still, some conditions may not be evaluated due to phase/short-circuiting; the report records what actually ran, without forcing every condition to run after an earlier branch already failed.

## 12. When an auto-config is excluded: this is not a property mismatch

There are multiple ways to exclude an auto-configuration:

```java
@SpringBootApplication(
    exclude = MetricsAutoConfiguration.class)
class ExcludedApplication {
}
```

This is an illustrative fragment, outside the runnable project above. When an auto-config is excluded:
- It may not appear in positive/negative matches because it was **never placed on the evaluation list**.
- `report.getExclusions()` can list auto-configs removed by that pipeline.
- Check `spring.autoconfigure.exclude`, `exclude` annotation attributes, deployment profiles, and test `@ImportAutoConfiguration(exclude=...)` if used.

Never tweak `@ConditionalOnClass` to rescue a class excluded intentionally. **Distinguish:**
1. Not discovered/imported.
2. Imported yet excluded.
3. Evaluated and condition negative.
4. Registered yet bean initialization failed.
5. Created yet injected wrongly due to multiple candidates/qualifiers.

Each group calls for a different fix.

## 13. Startup failure does not automatically mean a negative condition

A context can start **successfully** while lacking an optional bean due to a negative condition. Conversely, it can **fail** to start because:
- A bean factory method throws an exception.
- A required property fails binding/conversion.
- Circular dependency or ambiguous injection.
- An optional library class loads too early causing `NoClassDefFoundError`.
- A required datasource/server/SDK fails to initialize.
- A bean is created yet its health/IO dependency errors.

`ConditionEvaluationReport` answers which conditions were evaluated; **it does not replace the `ApplicationContext` startup failure stack trace**.

In a runner:
```java
runner.withUserConfiguration(FailingConfiguration.class)
    .run(context -> {
        assertThat(context).hasFailed();
        assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                IllegalStateException.class);
    });
```

This fragment uses the test class from section 7. It shows a failure caused by an exception during bean initialization, not `OnPropertyCondition` producing a negative mismatch.

**Avoid a dangerous conclusion:** "The report has a positive match so the dependency is definitely ready." A `DataSourceAutoConfiguration` can match conditions yet still fail later when initializing the datasource bean or connecting to the database. Positive matches prove **conditions**, not end-to-end health.

## 14. Never write assertions tied to verbatim message text

A brittle test:

```java
assertThat(outcome.getMessage())
    .isEqualTo(
        "@ConditionalOnProperty (sample.metrics.enabled=true) did not find property");
```

This is an illustrative snippet in a test holding `outcome`. It breaks unnecessarily whenever Boot changes wording, whitespace, bean names, or rendering. A solid test focuses on:
- `outcomes.isFullMatch()` true/false.
- `getOutcome().isMatch()` for a specific condition.
- `getCondition().getClass().getSimpleName()` or condition-type checks.
- Bean presence/absence and exact implementation/values.
- Reading `getMessage()` for debugging rather than treating it as an immutable formatted API contract.

If a test is specifically for a **tool parsing reports**, you can test the parser's format while accepting Boot-version compatibility maintenance. Do not apply report-snapshot rules to ordinary auto-config tests.

### 14.1. A helper to filter results when debugging

```java
private static void printRelevantReasons(
        ConditionEvaluationReport report,
        String sourceFragment) {

    report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (!source.contains(sourceFragment)) {
                return;
            }
            outcomes.forEach(pair -> {
                String state =
                    pair.getOutcome().isMatch()
                        ? "MATCH"
                        : "NO MATCH";
                System.out.println(
                    state + " | " + source
                    + " | " + pair.getCondition()
                        .getClass().getSimpleName()
                    + " | " + pair.getOutcome().getMessage());
            });
        });
}
```

This is an **illustrative method** inside a Java test helper requiring `import ConditionEvaluationReport`. It does not print secrets directly unless a custom condition message embeds sensitive data. Even so, **never put API tokens/passwords inside custom condition messages**; reports/logs can be exported to CI or Actuator.

## 15. Condition reports in CI: enable only when helpful

A full condition report in a full Spring Boot app can be long and noisy. Effective workflow:
1. Write a small runner test for one auto-configuration.
2. Assert branch behavior via beans + condition booleans.
3. Enable `ConditionEvaluationReportLoggingListener` on **one diagnostic test** or use a source-filtering helper.
4. In CI, capture the report on test failure via appropriate logger/test infrastructure without leaking credentials/internal paths.
5. When debugging a full app, enable `--debug` locally or the `conditions` endpoint in a secured environment.
6. Once the root cause is found, fix the key, dependency, ordering, or expectation — **never "silence" the report by deleting conditions**.
7. Keep tests for **intentional non-matching** branches to prevent regressions when dependencies change or configs shift.

**QA note:** Never fail CI merely because a report contains negative matches. A healthy starter routinely has many intentional negative conditions when optional integrations are unused.

## 16. Case study: how to debug a missing bean?

Suppose `MetricClient` does not exist:

**Case A — `enabled` property missing:**
- Context starts cleanly.
- Report shows `OnPropertyCondition` negative.
- `MetricTransport` is present.
- Solution: if the feature should be on, set `sample.metrics.enabled=true` properly; if intentionally disabled, keep the negative test.

**Case B — `enabled=true` yet optional class missing:**
- Report shows `OnClassCondition` negative or early import filter skipped the class.
- No bean exists.
- Solution: check the optional dependency on the runtime classpath; if the feature is unused, that is the expected outcome.

**Case C — custom bean present:**
- Class conditions match.
- Method `#metricClient` `OnBeanCondition` is negative.
- Context still contains **custom `MetricClient`**.
- This is **back-off working**, not a bug.

**Case D — class imported properly yet bean factory method throws exception:**
- Context startup fails.
- Report may show positive class/method conditions.
- Root cause is the Java exception during bean initialization.
- Solution: fix factory/binding/dependency rather than tweaking properties.

**Case E — source not found in report:**
- Check `AutoConfiguration.imports`, actual package name, `AutoConfigurations.of`, exclusions, config phase, and context hierarchy.
- Never infer positive/negative from `null`.

**Case F — context is neither Servlet nor Reactive:**
- `OnWebApplicationCondition` is negative.
- If the test targets a Servlet/Reactive branch, pick the matching runner type rather than booting a full HTTP server unnecessarily.

## 17. Common errors and fixes table

| Symptom | Possible cause | Action |
|---|---|---|
| Bean missing, context starts fine | Condition negative (by design or bug) | Read source + reason, compare with contract |
| `OnPropertyCondition`: did not find property | Missing property/key/prefix | Check `withPropertyValues`, config profiles |
| Property exists yet value mismatches | Wrong `havingValue` or typo | Check annotation, enum/boolean semantics |
| `OnClassCondition` negative | Optional class missing on runtime classpath | Check JAR/dependency, `FilteredClassLoader` |
| `OnBeanCondition` negative for MissingBean | User bean already exists | Assert custom bean wins, do not force default |
| `OnBeanCondition` negative for OnBean | Dependency bean unknown yet | Check dependency ordering/type/registration |
| Class positive yet bean method negative | Method-level condition failed | Look up `Class#method` key, not just class |
| Missing method key | Class-level condition failed/method skipped | Check class report first |
| Missing source key | Excluded/unimported/early filtered/other context | Imports, exclusions, key, hierarchy |
| `ConditionEvaluationReport.get(...)` empty | Context did not run matching condition pipeline | Check runner `withConfiguration` and phase |
| `hasSingleBean` fails with multiple candidates | Broken back-off/type/ordering | Inspect names/types, `@Primary`, bean conditions |
| `@ConditionalOnProperty` unexpected match | Missing `havingValue` | Use explicit `havingValue="true"` if desired |
| `NoClassDefFoundError` when optional class absent | Early signature/class loading | Nested conditional configuration |
| Report shows class matched yet context fails | Bean init/binding/IO error | `getStartupFailure()` and root cause |
| `@WebApplication` condition fails in runner | Used plain context for web-only config | Web/Reactive `WebApplicationContextRunner` |
| Report too long | Full debug enabled on every test | Filter by source and enable only when debugging |
| Actuator 404/403 on `conditions` | Endpoint unexposed/access denied | Check actuator dependency/exposure/security |
| Starter tests pass yet app fails to auto-import | Missing `AutoConfiguration.imports` | Verify JAR resources + smoke test |
| Tests fail on Boot upgrade due to log text | Asserted verbatim message | Assert match flag/type/bean behavior |
| Report lacks custom condition | Custom condition not recorded like BootCondition | Review implementation and bean registration |
| `@ConditionalOnBean` order-sensitive | Evaluated before dependency defined | AutoConfig `after/before` + tests |
| Native image test fails with runner | Runner is not for native test execution | JVM runner tests and native smoke tests |
| Negative matches treated as warnings | Confusing report with error report | Distinguish expected optional outcomes |
| Startup logs show debug report yet bean unused | Feature disabled/custom bean/other candidate | Check bean map, qualifiers, actual injection |

## 18. Practice exercise: find the root cause in three minutes

Practice after creating the sample project:

1. Run `missingPropertyProducesOnPropertyNegativeMatch`; identify the class source and negative `OnPropertyCondition`.
2. Switch to `sample.metrics.enabled=true` in a scenario: default bean appears, class and method outcomes become full matches.
3. Add `CustomMetricConfiguration`: default bean backs off, custom bean still executes; inspect **the method source** rather than only the class.
4. Use `new FilteredClassLoader(MetricTransport.class)`: class-level condition no longer matches; confirm no default exists.
5. Enable `ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO)` in a scenario; compare log messages with structured assertions.
6. Intentionally mistype `sample.metric.enabled=true` (missing `s`): read `OnPropertyCondition` and pinpoint the exact typo.
7. Add a test whose bean throws an exception: prove startup failure **differs from a negative match**.
8. To see full runtime conditions, run the demo application with `--debug`, rather than writing a custom classpath scanner.

**Self-check questions:**

- Why does `ConditionAndOutcomes.isFullMatch()==false` not imply an auto-config bug?
- When `MetricsAutoConfiguration#metricClient` is negative, must the class-level condition also be negative?
- What causes a source not to appear in the report map?
- When the report is positive yet the context fails, what do you check next?
- Why shouldn't you snapshot `getMessage()` verbatim into a JUnit assertion?
- What is required to expose `/actuator/conditions` safely?
- Why does a passing runner test not prove discovery metadata was packaged properly?

## 19. Project run commands and interpreting results

When the project has a Gradle wrapper, run one test class:

```bash
./gradlew test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest"
```

Run a single method for fast investigation:

```bash
./gradlew test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest.missingPropertyProducesOnPropertyNegativeMatch"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.conditionlab.autoconfigure.MetricsConditionReportTest"
```

If the project uses a Maven wrapper with equivalent `pom.xml`/BOM/dependencies:

```bash
./mvnw -Dtest=MetricsConditionReportTest test
```

The project defines **11 designed JUnit `@Test` methods**. This is code and **expected behavior**, not execution results: there is no proof 11 tests ran in the current environment. Inspect `build/reports/tests/test/index.html` or `target/surefire-reports/` of your module to verify how many tests were discovered and their pass/fail/skip status.

When running the application via `bootRun`, default auto-configuration **does not create `MetricClient`** without the enabled property; that is expected. Do not expect the program to print `metric:order-created` to stdout, because the demo main neither invokes `MetricClient.emit(...)` nor `System.out.println`. When `--debug` is enabled, report formatting/verbosity depends on the Spring Boot patch and logging config.

## 20. QA checklist before finalizing a conditions test suite

- [ ] Identified exact auto-config sources (class and bean method) under investigation.
- [ ] Have an `ApplicationContextRunner` loading only the needed auto-configs.
- [ ] Tested negative missing/false/wrong-key properties and positive true.
- [ ] Tested absent optional dependency via `FilteredClassLoader` when needed.
- [ ] Tested user bean override/back-off via `withUserConfiguration`.
- [ ] Retrieved the report via `ConditionEvaluationReport.get(context.getBeanFactory())`.
- [ ] Distinguished a source's `isFullMatch` from individual `ConditionOutcome.isMatch`.
- [ ] Asserted only condition types and match flags, never snapshot verbatim `getMessage()`.
- [ ] Checked actual beans (type/name/behavior), not only report outcomes.
- [ ] Did not treat every negative match as a failure.
- [ ] When a source is missing from the map, checked imports/exclusions/phase/context key.
- [ ] Distinguished condition mismatches from bean startup failures; used `getStartupFailure()` when needed.
- [ ] Never retained contexts/beans past the `ApplicationContextRunner.run` callback.
- [ ] Used the proper Web/Reactive runner for `@ConditionalOnWebApplication`.
- [ ] When publishing a starter, verified `AutoConfiguration.imports` inside the JAR, not just runners.
- [ ] Actuator `conditions` endpoint used only in controlled environments.
- [ ] Never logged credentials/PII in custom condition messages.
- [ ] Did not try forcing all optional auto-configs positive just to make reports look clean.
- [ ] When using Spring Boot 4.x, checked packages/APIs for that version instead of copying 3.5 imports.
- [ ] Ran JUnit via Gradle/Maven and read real reports before reporting runtime PASS.

## 21. Official sources and APIs for verification

- [Spring Boot 3.5 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html): conditional annotations, `ApplicationContextRunner`, `FilteredClassLoader`, report logging listener.
- [ConditionEvaluationReport (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): `get`, `find`, `getConditionAndOutcomesBySource`, `getExclusions`.
- [ConditionAndOutcomes (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html): `isFullMatch`, `iterator`, `stream`.
- [ConditionOutcome (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html): `isMatch`, `getMessage`.
- [ConditionEvaluationReportLoggingListener (Boot 3.5 Javadoc)](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): logging report at INFO/DEBUG.
- [Spring Boot 3.5 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.5/reference/actuator/endpoints.html): `conditions` exposure/access and security notes.
- [Spring Boot 3.5 — Conditions Actuator REST API](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html): JSON structure `positiveMatches`/`negativeMatches`.
- [Spring Boot 3.5 — Auto-configuration](https://docs.spring.io/spring-boot/3.5/reference/using/auto-configuration.html): enabling debug to view the conditions report.
- [Spring Framework — Core Container / Java Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): Spring bean definitions and context lifecycle.

**Conclusion:** When an auto-configuration fails to create a bean, never guess the cause solely from its absence. Use `ConditionEvaluationReport` to locate the **exact source class/method**, inspect `ConditionAndOutcomes.isFullMatch()`, individual `ConditionOutcome.isMatch()`, and `getMessage()`, then cross-check against **actual beans**. A negative `OnPropertyCondition` may point to a misconfigured property, while a negative `OnBeanCondition` may prove user-override back-off succeeded. If the report lacks the source, check imports/exclusions/phases; if the context fails, read the startup exception. Use `ApplicationContextRunner` to guard both matching and non-matching branches with small, fast, stable tests; reserve full applications/Actuator for broader investigations.