# Verifying Order Through Bean Outcomes and Condition Evaluation Reports

## Lesson goal

In Spring Boot Auto-configuration, adding `@AutoConfiguration(after = ...)` or `@AutoConfigureBefore` only **expresses a configuration processing relationship**. To know whether that relationship produces the right behavior, you must verify both simultaneously:

1. **Bean outcomes:** which beans actually exist in the context, what are their names and types, which bean was selected, and did defaults yield to source/user beans?
2. **Condition outcomes:** which conditions did `ConditionEvaluationReport` record as matched or not matched, and why did `@ConditionalOnBean` or `@ConditionalOnMissingBean` yield that result?

Looking solely at the bean list after startup can confirm the final state, yet fails to explain decisions made at **the moment bean definitions were processed**. Conversely, reading only the condition report does not prove the application instantiated the expected beans. Both signals must be read **together**.

This lesson uses Spring Boot 3.3.x, Spring Framework 6.1, and Java 17+. The example includes a standalone `ApplicationContextRunner` test suite verifying right order, reversed order, and user-provided beans.

## 1. Understanding "order" accurately before testing

Several distinct orderings exist in the Spring lifecycle; only some relate directly to auto-configuration.

| Ordering layer | Timing | Right question | Appropriate mechanism |
| --- | --- | --- | --- |
| Auto-configuration discovery / import | Bootstrap and configuration parsing | Which auto-configurations are candidates? | `AutoConfiguration.imports`, classpath, exclusions |
| **Applying auto-configurations and registering bean definitions** | During configuration processing | Was the source bean declared before downstream conditions evaluated? | `@AutoConfiguration(before/after)`, `beforeName/afterName`, `@AutoConfigureBefore/After`, `@AutoConfigureOrder` |
| Condition evaluation | At a point during processing | Does the target bean have a definition and matching type metadata yet? | `@ConditionalOnBean`, `@ConditionalOnMissingBean`, `ConditionEvaluationReport` |
| **Instance creation** and injection | At context refresh, when beans are needed | Which constructor/`@Bean` method runs first? | Dependency graph, constructor injection, `@DependsOn`, lazy/prototype |
| Bean usage on requests/jobs | Runtime | In what sequence does business logic execute? | Scheduler, transactions, events, application flow |

**Important rule:** `@AutoConfiguration(after = SourceAutoConfiguration.class)` affects the **bean definition registration** order of auto-configurations; it **does not guarantee** every instance created by Source will initialize before instances in later configurations.

For example, the `@Bean` method below is parsed and registered by Spring as a *definition* even before the `CatalogService` object is instantiated:

```java
@Bean
CatalogService sourceCatalog() {
    return new CatalogService("source");
}
```

This snippet is **part of a `@Configuration` class**, not a standalone Java program. A `@ConditionalOnBean(CatalogService.class)` condition in an auto-configuration applied **after** it can recognize the bean via its declared definition/return type. The fact that the bean is instantiated later during refresh or on demand does not hinder that logic.

Do not use `@DependsOn` to "fix" a condition failing to see a definition: `@DependsOn` governs **initialization** order, whereas the bug is **configuration processing** order.

## 2. Annotations that actually govern auto-configuration order

Spring Boot 3.x allows expressing relationships directly:

```java
@AutoConfiguration(after = SourceAutoConfiguration.class)
class DependentAutoConfiguration {
}
```

Equivalent in meaning to placing `@AutoConfigureAfter(SourceAutoConfiguration.class)` on the auto-configuration that must be applied later. Reverse direction:

```java
@AutoConfiguration(before = OtherAutoConfiguration.class)
class EarlierAutoConfiguration {
}
```

When avoiding a direct class dependency, use the fully qualified name:

```java
@AutoConfiguration(
    afterName = "com.example.library.SourceAutoConfiguration")
class OptionalDependentAutoConfiguration {
}
```

These fragments assume the related classes exist; they illustrate annotations rather than complete files.

- `before` / `after` define relative relationships **between auto-configurations**; both must be selected as candidates for the relationship to take effect.
- `beforeName` / `afterName` use fully qualified class names; helpful when a library avoids compile-time class coupling or the target class only exists in another version.
- `@AutoConfigureOrder` provides general ordering for auto-configurations without direct relationships; when an explicit ordering dependency exists, express it via `before/after` rather than hard-to-maintain numbers.
- `@Order` placed on beans/handlers generally **does not replace** auto-configuration ordering relationships; neither does `@DependsOn`.
- Configuration order is **not** line-by-line order in the imports file, nor the order you pass classes into `AutoConfigurations.of(...)` in tests. Spring Boot sorts auto-configurations by metadata just as in a real running application.
- In Spring Boot 3.x, auto-configurations shipped by a starter are listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`, one class name per line. Do not rely on component scanning to load auto-configurations.

Also remember: if an auto-configuration is excluded, absent from the classpath, or filtered out by a class-level condition, `after` cannot force it to provide a bean. **Ordering is a prerequisite for certain dependency flows, not a substitute for ensuring the bean is actually registered.**

## 3. Bean conditions evaluate against "what has already been processed"

The two conditions most likely to expose ordering bugs are:

- `@ConditionalOnBean(CatalogService.class)`: creates the dependent bean only if a bean of type `CatalogService` has already been identified at check time.
- `@ConditionalOnMissingBean(CatalogService.class)`: creates a fallback if **no** candidate of type `CatalogService` has been identified yet at that moment.

These are not conditions that "wait until every `@Configuration` finishes processing and then re-evaluate." Spring Boot recommends placing bean conditions mainly in auto-configurations because user beans are normally registered before auto-configurations. Between auto-configurations themselves, authors must declare application order when one depends on another's definitions.

### 3.1. Same bean source, flipping order yields two outcomes

Suppose `SourceAutoConfiguration` always provides a `CatalogService` bean named `sourceCatalog`. `FallbackAutoConfiguration` has:

```java
@Bean
@ConditionalOnMissingBean(CatalogService.class)
CatalogService fallbackCatalog() {
    return new CatalogService("fallback");
}
```

If **fallback applies after source**:

```text
SourceAutoConfiguration        -> defines sourceCatalog : CatalogService
FallbackAutoConfiguration      -> checks MissingBean(CatalogService)
                               -> finds sourceCatalog -> skips registering fallback
Context refresh                -> 1 CatalogService bean
```

If **fallback applies before source**:

```text
FallbackAutoConfiguration      -> sees no CatalogService yet -> registers fallback
SourceAutoConfiguration        -> registers sourceCatalog (unconditional)
Context refresh                -> 2 CatalogService beans
```

Both diagrams depict **controlled scenarios**, not a default order guarantee when no constraint is declared. Having two differently named beans of the same type typically makes `getBean(CatalogService.class)` ambiguous unless `@Primary`, a qualifier, or an explicit bean name is used. It does **not necessarily** fail immediately on refresh if no bean demands a single candidate, yet it is a signal worth investigating.

### 3.2. OnBean conditions share a similar dependency direction

If `DependentAutoConfiguration` provides:

```java
@Bean
@ConditionalOnBean(CatalogService.class)
DiagnosticMarker diagnosticMarker() {
    return new DiagnosticMarker();
}
```

When the dependent configuration applies **after** source, the condition can detect the bean. When it applies **before** source and no other bean of that type exists yet, the condition can fail to match, leaving `diagnosticMarker` absent after startup **even though `sourceCatalog` ends up existing**.

Thus "a bean exists at the end" does not mean "the condition saw the bean when evaluated." Checking only at the end detects the symptom; the condition report supplies the cause.

## 4. Two sources of evidence to pair together

### 4.1. Bean outcome evidence: WHAT

After the `ApplicationContext` is created successfully, use these checks to inspect the outcome:

```java
assertThat(context).hasSingleBean(CatalogService.class);
assertThat(context).hasBean("sourceCatalog");
assertThat(context).doesNotHaveBean("fallbackCatalog");
assertThat(context.getBean(CatalogService.class).origin())
        .isEqualTo("source");
```

These are **assertions inside an `ApplicationContextRunner` callback**, with `context` and `CatalogService` already declared. They distinguish:

1. **How many beans?** Zero, one, or multiple candidates of the same type?
2. **Which bean names exist?** Source, fallback, or user override?
3. **Are observed values/settings right?** Did the bean come from the right source with expected properties?
4. **Did the application start cleanly?** Are there `NoSuchBeanDefinitionException`, `NoUniqueBeanDefinitionException`, or dependency cycles?

Note: `hasSingleBean` proves only the count of matching beans. It **does not prove** which condition matched. A duplicate-named bean or `@Primary` can let injection succeed while hiding an unintended fallback. Assert both **name** and **source value**.

### 4.2. Condition report evidence: WHY

Spring Boot records condition evaluations in `ConditionEvaluationReport`. The report groups outcomes by evaluation source (configuration class or `@Bean` method). One source can have multiple conditions; a single unmatched condition makes the entire source fail.

One way to retrieve the report **after context refresh**:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());
var outcomesBySource = report.getConditionAndOutcomesBySource();
```

This runs inside a test callback where `context` is an `AssertableApplicationContext`. The result maps keys `"package.AutoConfiguration#beanMethod"` (or class name for class-level conditions) to sets of `ConditionAndOutcome`. For nested classes, the JVM name contains `$` between outer and inner class names; therefore obtain the key via `SomeAutoConfiguration.class.getName()` rather than guessing.

For a specific method:

```java
String key = FallbackAutoConfiguration.class.getName()
        + "#fallbackCatalog";
var outcomes = report.getConditionAndOutcomesBySource().get(key);
if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());
    outcomes.forEach(item -> System.out.println(
            item.getCondition().getClass().getSimpleName()
                    + ": " + item.getOutcome().getMessage()));
}
```

This is an **illustrative code snippet**, assuming `report` and `FallbackAutoConfiguration` exist. `isFullMatch()` indicates **whether all conditions recorded for that source matched**; each `getOutcome()` provides the detailed result and message. Messages typically explain which bean was found or missing, the checked type, and the search strategy.

Do not treat any message text as fixed stdout: Spring Boot versions, actual bean names, companion conditions, and logging setup can change wording. In automated tests, assert boolean match states and bean names; when debugging, print messages to read the reason.

### 4.3. Keywords to cross-check in the report

| Signal from report | What to cross-check with final beans | Interpretation |
| --- | --- | --- |
| `OnBeanCondition` for `@ConditionalOnMissingBean`: **matched**, did not find `CatalogService` | `fallbackCatalog` is present | Fallback was permitted to register at condition time |
| `OnBeanCondition` for `@ConditionalOnMissingBean`: **not matched**, found `sourceCatalog` | `fallbackCatalog` absent, `sourceCatalog` still present | Fallback yielded properly |
| `OnBeanCondition` for `@ConditionalOnBean`: **matched** | Dependent bean present | Required bean was recognized when the condition ran |
| `OnBeanCondition` for `@ConditionalOnBean`: **not matched** | Dependent bean absent, yet source may appear later | Source was likely defined too late or type metadata did not match |
| `OnClassCondition`: library missing | Integration bean absent | Classpath issue, cannot immediately blame ordering |
| `OnPropertyCondition`: property disabled | Bean absent | Property configuration issue, cannot fix merely with `after` |
| Source appears in `unconditionalClasses` | Context may or may not have condition-dependent beans | That class has no class-level auto-configuration condition; not proof of bean creation timing |

**The condition report is not a bean initialization timeline.** It does not tell you when constructors ran, the order individual instances were created, or the history of `@Bean` method calls. It is a record of conditions evaluated during configuration. To observe initialization, use lifecycle logs, a controlled `BeanPostProcessor`, or application startup tracing tailored to that goal.

## 5. Runnable lab: proving order with 5 tests

This lab builds two opposing states on the same Spring Boot module. `SourceAutoConfiguration` always defines `CatalogService`; the "before" and "after" auto-configurations differ only in ordering relationship. Beyond asserting final beans, tests read `ConditionEvaluationReport` and assert `isFullMatch()` for the exact method.

### 5.1. Structure and dependencies

Create a standalone Gradle test directory:

```text
auto-configuration-order-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/AutoConfigurationOrderEvidenceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'auto-configuration-order-lab'
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
}

test {
    useJUnitPlatform()
}
```

Requires Java 17+ and a Gradle version compatible with your Java version. `spring-boot-starter-test` brings in `ApplicationContextRunner`, JUnit 5, AssertJ, and Spring Boot auto-configuration libraries. This lab needs no database, server, Docker, `application.properties`, or running a real `SpringApplication`.

### 5.2. Complete Java 17 test file

`src/test/java/demo/AutoConfigurationOrderEvidenceTest.java`:

```java
package demo;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class AutoConfigurationOrderEvidenceTest {

    record CatalogService(String origin) {}

    record DiagnosticMarker(String value) {}

    @AutoConfiguration
    static class SourceAutoConfiguration {
        @Bean
        CatalogService sourceCatalog() {
            return new CatalogService("source");
        }
    }

    @AutoConfiguration(after = SourceAutoConfiguration.class)
    static class LateFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService lateFallback() {
            return new CatalogService("fallback");
        }
    }

    @AutoConfiguration(before = SourceAutoConfiguration.class)
    static class EarlyFallbackAutoConfiguration {
        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService earlyFallback() {
            return new CatalogService("fallback");
        }
    }

    @AutoConfiguration(after = SourceAutoConfiguration.class)
    static class LateObserverAutoConfiguration {
        @Bean
        @ConditionalOnBean(CatalogService.class)
        DiagnosticMarker lateObserver() {
            return new DiagnosticMarker("seen");
        }
    }

    @AutoConfiguration(before = SourceAutoConfiguration.class)
    static class EarlyObserverAutoConfiguration {
        @Bean
        @ConditionalOnBean(CatalogService.class)
        DiagnosticMarker earlyObserver() {
            return new DiagnosticMarker("seen");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {
        @Bean
        CatalogService customCatalog() {
            return new CatalogService("user");
        }
    }

    private ApplicationContextRunner runner(Class<?>... configurations) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(configurations));
    }

    private boolean conditionMatched(
            AssertableApplicationContext context,
            Class<?> configurationClass,
            String beanMethod) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        Map<String, ConditionAndOutcomes> outcomesBySource =
                report.getConditionAndOutcomesBySource();

        String source = configurationClass.getName() + "#" + beanMethod;
        assertThat(outcomesBySource)
                .as("Condition report should contain " + source)
                .containsKey(source);

        return outcomesBySource.get(source).isFullMatch();
    }

    @Test
    void fallbackAfterSourceIsSkippedAndReportExplainsWhy() {
        // Intentionally pass LateFallback first; Boot still applies "after".
        runner(LateFallbackAutoConfiguration.class,
                SourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("lateFallback");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("source");

                    assertThat(conditionMatched(context,
                            LateFallbackAutoConfiguration.class,
                            "lateFallback")).isFalse();
                });
    }

    @Test
    void fallbackBeforeSourceCreatesTwoDefinitions() {
        // Intentionally pass Source first; the "before" relationship still wins.
        runner(SourceAutoConfiguration.class,
                EarlyFallbackAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("earlyFallback");
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context.getBeansOfType(CatalogService.class))
                            .containsOnlyKeys("earlyFallback", "sourceCatalog");

                    assertThat(conditionMatched(context,
                            EarlyFallbackAutoConfiguration.class,
                            "earlyFallback")).isTrue();
                });
    }

    @Test
    void observerAfterSourceSeesTheDefinition() {
        runner(LateObserverAutoConfiguration.class,
                SourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).hasSingleBean(DiagnosticMarker.class);
                    assertThat(context).hasBean("lateObserver");

                    assertThat(conditionMatched(context,
                            LateObserverAutoConfiguration.class,
                            "lateObserver")).isTrue();
                });
    }

    @Test
    void observerBeforeSourceDoesNotSeeTheFutureDefinition() {
        runner(SourceAutoConfiguration.class,
                EarlyObserverAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("earlyObserver");
                    assertThat(context).doesNotHaveBean(DiagnosticMarker.class);

                    assertThat(conditionMatched(context,
                            EarlyObserverAutoConfiguration.class,
                            "earlyObserver")).isFalse();
                });
    }

    @Test
    void userBeanBeatsFallbackWithoutSourceAutoConfiguration() {
        runner(LateFallbackAutoConfiguration.class)
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(CatalogService.class);
                    assertThat(context).hasBean("customCatalog");
                    assertThat(context).doesNotHaveBean("lateFallback");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("user");

                    assertThat(conditionMatched(context,
                            LateFallbackAutoConfiguration.class,
                            "lateFallback")).isFalse();
                });
    }
}
```

**Test note:** These are **five isolated contexts**. The early fallback and early observer scenarios are tested in **separate contexts**, avoiding an early-registered fallback accidentally serving as a candidate for the observer and skewing the comparison. This is how variables are controlled when testing order.

### 5.3. Running the tests and observing results

From the project directory:

```bash
gradle test --tests demo.AutoConfigurationOrderEvidenceTest
```

If the repo has a wrapper, on Linux/macOS:

```bash
./gradlew test --tests demo.AutoConfigurationOrderEvidenceTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.AutoConfigurationOrderEvidenceTest
```

**Expected result**: the test task completes with **5 tests passed** (with compatible dependencies). Do not treat full Gradle output or log order as fixed stdout. The test suite is a template for learners to build and run; if not yet run in your environment, that is the theoretical expectation based on the documented APIs.

### 5.4. Outcome matrix to verify

| Test | Source bean | Fallback bean | Observer bean | Match of checked condition |
| --- | --- | --- | --- | --- |
| `fallbackAfterSource...` | `sourceCatalog` present | `lateFallback` absent | Not evaluated | `@ConditionalOnMissingBean` = **false** |
| `fallbackBeforeSource...` | `sourceCatalog` present | `earlyFallback` present | Not evaluated | `@ConditionalOnMissingBean` = **true** |
| `observerAfterSource...` | `sourceCatalog` present | Not evaluated | `lateObserver` present | `@ConditionalOnBean` = **true** |
| `observerBeforeSource...` | `sourceCatalog` present **at the end** | Not evaluated | `earlyObserver` absent | `@ConditionalOnBean` = **false** |
| `userBeanBeatsFallback...` | `customCatalog` present | `lateFallback` absent | Not evaluated | `@ConditionalOnMissingBean` = **false** |

The "match" column corresponds to `ConditionAndOutcomes.isFullMatch()` for the method under inspection. That is **not** a flag storing "A before B" in the report; ordering is inferred from **outcomes when flipping annotations**, and confirmed via source/bean/condition in an isolated context.

The first two tests and the observer-before test prove why inspecting only the final bean list is insufficient. In `observerBeforeSource...`, `sourceCatalog` **exists after refresh**, yet the observer still does not exist: when the condition was evaluated, source had not been processed yet. The report shows `OnBeanCondition` did not match for `earlyObserver`; the condition is never "replayed" later.

## 6. Printing reasons from ConditionEvaluationReport without relying on log phrasing

The tests above check the boolean `isFullMatch()`. When you need to read the **specific message** produced by Spring Boot, add the following inside a test callback (this is an illustrative snippet, not a separate file):

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource()
        .forEach((source, outcomes) -> {
            if (!source.contains("FallbackAutoConfiguration")) {
                return;
            }
            System.out.println(source + " -> match=" + outcomes.isFullMatch());
            outcomes.forEach(item -> System.out.println(
                    "  " + item.getCondition().getClass().getSimpleName()
                    + ": matched=" + item.getOutcome().isMatch()
                    + "; message=" + item.getOutcome().getMessage()));
        });
```

This snippet reuses the `ConditionEvaluationReport` imports already present in the test file. It does not print a fixed "canonical line" because message content depends on the situation. Read both the **source key** and **condition name**: a configuration can fail to match due to `OnClassCondition` or `OnPropertyCondition`, even when source/fallback ordering is completely right.

You can also ask Spring Boot to log the report automatically when running tests:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
        .withConfiguration(
                AutoConfigurations.of(
                        SourceAutoConfiguration.class,
                        LateFallbackAutoConfiguration.class))
        .run(context -> {
            // Assert beans and conditions here.
        });
```

This example uses additional imports:

```java
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
```

The callback body is an **illustration of assertion placement**, not complete standalone copy-paste code. If Gradle or the logging backend hides stdout/test logging, configure `testLogging.showStandardStreams = true` (if needed) or inspect the report programmatically via the API as in Section 5. Never conclude there is no report merely because logs aren't shown.

In a real Spring Boot application, you can enable the report via `--debug` or `debug=true`. When using Spring Boot Actuator with the `conditions` endpoint properly enabled/exposed, `GET /actuator/conditions` provides the report as JSON.

### 6.1. Reading fields in the Actuator report

A **structurally abbreviated sample**, not fixed output from the tests above:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "demo.ExampleAutoConfiguration#fallback": [
          {
            "condition": "OnBeanCondition",
            "message": "explanation produced by Spring Boot"
          }
        ]
      },
      "negativeMatches": {
        "demo.OtherAutoConfiguration#other": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "why the condition failed"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

`positiveMatches` lists sources permitted by conditions; `negativeMatches` records excluded sources along with `notMatched` conditions and any other conditions that may have `matched`. `unconditionalClasses` lists auto-configurations not gated by a class-level condition. Method-level source keys typically include `#methodName`. With multiple contexts (management/parent/child), select the right context ID.

**Especially important:** entry order in the report, JSON key order, or log order **is not evidence** of bean creation order. Use bean assertions and match reasons to verify state; use metadata constraints and reversed-order tests to prove cause.

### 6.2. The report does not replace failure analysis

When an application fails to start, inspect failure logs and the condition report (if obtainable) to see why beans were excluded or duplicated. However, a `NoUniqueBeanDefinitionException` can occur **after** both bean definitions were registered. The report can explain why a fallback was allowed to register, yet does not explain the entire injection failure; cross-check the stack trace and bean graph.

When using `ApplicationContextRunner` and intentionally testing a failing context, you can assert:

```java
runner.run(context -> {
    assertThat(context).hasFailed();
    assertThat(context.getStartupFailure())
            .hasRootCauseInstanceOf(
                    org.springframework.beans.factory.NoUniqueBeanDefinitionException.class);
});
```

This is only a **test template for a case designed to fail** with an existing `runner` helper in another context. **Do not add this assertion to the 5 main tests**, because they do not introduce a dependency requiring a single candidate. Exception checks must be tailored to the actual exception chain of the scenario.

## 7. Investigation workflow when suspecting an ordering bug in a module

Follow this seven-step workflow to avoid wrong fixes:

1. **Capture the expected outcome.** Define clearly: "if the user provided `CatalogService`, fallback must be absent; if source exists, observer must exist." Record bean names and types as the test contract.
2. **Identify who provides the source bean.** User config bean, component scan, another auto-config's bean, a registrar, or a factory? `@ConditionalOnBean` checks already-processed definitions, so you cannot look only at beans present at the end. Ensure `@Bean` return types are sufficiently specific.
3. **Record the real ordering relationship.** Who needs `after` whom? Does `afterName` point to the exact fully qualified Java class name? Was the target class selected as an auto-config? Was it accidentally excluded or disabled by another condition?
4. **Check bean outcomes.** Use `ApplicationContextRunner` to assert `hasBean`/`doesNotHaveBean`, `hasSingleBean`, or `getBeansOfType`. Record bean names and their origins.
5. **Retrieve the report for the right context.** Use `ConditionEvaluationReport.get(context.getBeanFactory())`; match source key `AutoConfiguration#beanMethod` and `OnBeanCondition`, reading positive/negative matches. If the method condition was never evaluated because the class-level configuration was excluded earlier, inspect the corresponding **class-level source**.
6. **Change exactly one variable.** Compare `before` vs. `after` with identical classpath/properties; test with and without user beans. Never change order, properties, mocks, and dependencies all at once.
7. **Lock in behavioral tests.** Bean assertions protect the contract; report assertions protect the explanation. Keep those tests when refactoring starters/auto-configurations or upgrading Spring Boot.

To avoid "false-green tests," never assert only `context.containsBean("sourceCatalog")`. With a bug where fallback still exists, source can still be present and the test would pass. Assert **fallback absence**, **bean count**, **source value**, and at least one relevant **condition outcome**.

## 8. Causes that mimic ordering bugs

Not every unmatched `@ConditionalOnBean` is caused by a missing `after`.

| Symptom | Other cause to check | Distinguishing clue |
| --- | --- | --- |
| Bean appears at the end yet `@ConditionalOnBean` did not match | Definition registered late; or type metadata unrecognized | Report says candidate not found; check declared return type and processing order |
| `after` is right yet fallback still turns on | Source excluded by class/method condition, leaving no definition | Source's report shows negative `OnClassCondition`, `OnPropertyCondition`, or `OnBeanCondition` |
| Source bean exists yet fallback does not back off | `@Bean Object service()` or overly broad factory type | Condition on `CatalogService` misses the expected type; fix metadata/return type |
| User bean exists yet fallback is also present | User definition created at wrong branch/timing, or condition checks a different type | Test `withUserConfiguration` and verify exact type/name |
| Two beans exist yet app still starts | No single-bean injection, qualifier/primary present, or nobody consumes it | Assert `getBeansOfType` and source values, not just startup |
| App fails when injecting a single bean | Duplicate candidates from fallback and source, or another dependency | Stack trace identifies the failure; report explains only conditions |
| Negative reason mentions no beans | Classpath/property/web condition failed | Check condition name, fix the underlying layer |
| Changing `@Order` does not change results | `@Order` does not sort auto-configs by desired bean-definition relationships | Use `@AutoConfiguration(before/after)` and re-test |
| Adding `@DependsOn` does not change condition | `@DependsOn` controls initialization | Fix definition processing order |
| Test depends on order passed to `AutoConfigurations.of` | Misunderstanding Boot's sorter; test has unreliable coupling | Use ordering metadata and reverse argument order as in the example test |
| Condition outcome differs between app and runner | Runner lacks user configuration, environment, classpath, parent context, or auto-configs | Build a test context representative of the real scenario |

### 8.1. Do not use weak types as "proof" of wrong order

If a source bean is declared like this:

```java
@Bean
Object catalogService() {
    return new CatalogService("source");
}
```

then `@ConditionalOnBean(CatalogService.class)` is **not guaranteed** to recognize the concrete implementation before the bean is instantiated. Flipping `before/after` may not fix it because the source is registered yet **type metadata is insufficient**. The fix is declaring an accurate return type:

```java
@Bean
CatalogService catalogService() {
    return new CatalogService("source");
}
```

These illustrative snippets assume `CatalogService` has the constructor from the test record above. If the source is a `FactoryBean`, inspect the product type exposed via `getObjectType()` or corresponding metadata; a factory existing does not automatically tell the condition the product type. This is an extra check whenever the report and bean outcomes disagree.

### 8.2. Do not rely on `@Bean` order within the same config

Two `@Bean` methods with interdependent conditions inside the same `@Configuration` can create unclear processing-order dependencies. To verify auto-config relationships reliably, place source and dependent logic in **separate auto-configurations** and declare `after` explicitly as in Section 5's test suite. When the goal is user override, use the runner's `withUserConfiguration(...)` to model user configurations being processed before auto-configurations.

If multiple auto-configurations provide fallbacks for one interface, they can interact through `@ConditionalOnMissingBean`. Tests should cover cases where multiple sources are imported together while keeping each scenario isolated and asserting bean count, names, and origins.

## 9. Do not confuse order metadata with bean initialization order

A small experiment outside `ConditionEvaluationReport` clarifies the boundary:

```java
@AutoConfiguration(after = SourceAutoConfiguration.class)
class ConsumerAutoConfiguration {
    @Bean
    Consumer consumer(CatalogService catalogService) {
        return new Consumer(catalogService);
    }
}
```

This is an **illustrative snippet** assuming `SourceAutoConfiguration`, `CatalogService`, and `Consumer` exist. `Consumer` receiving `CatalogService` as a parameter tells the container the dependency relationship at instance creation time. `after` tells Spring Boot the auto-configuration application order. The two mechanisms complement each other rather than being identical.

If one bean must initialize before another **without injection**, `@DependsOn` can express that lifecycle relationship; it **cannot cause `@ConditionalOnBean` to re-evaluate**. For startup benchmarks, constructor timestamps do not prove condition order: a bean can be lazily instantiated long after the report was recorded.

## 10. QA criteria for an ordering change

When a PR modifies `@AutoConfiguration(after=...)`, record four reviewable pieces of evidence:

**(A) Controlled inputs.** List of auto-configs, source beans, user configs, classpath/properties, and the ordering direction under test.

**(B) Bean assertions.** Bean presence/absence by name, bean count by type, and actual bean used. For fallbacks: when source exists, fallback must be absent; when source is absent, fallback must exist (unless blocked by other conditions).

**(C) Condition outcomes.** Method/configuration source key, `isFullMatch()`, and the condition explaining the result. For real incidents, record the message read from the report to verify the reason, without hard-coding verbatim message text into brittle tests.

**(D) Control cases.** With user bean, without user bean, early/late or disabled source, and at least one case consuming the dependent bean if the feature requires `@ConditionalOnBean`.

Example of valid change evidence for a reviewer to read:

```text
Expected:
  Source enabled -> exactly one CatalogService named sourceCatalog.
  Fallback absent.
  OnBeanCondition for lateFallback -> not matched (source found).

Controlled inverse:
  Early fallback -> earlyFallback + sourceCatalog both registered.
  OnBeanCondition for earlyFallback -> matched (source not yet seen).

Reason:
  Auto-configuration ordering affects definition visibility
  when @ConditionalOnMissingBean evaluates.
```

This is an **illustration of expected observation results**, not a real log run in another environment.

`condition full match=false` is not a test failure when you are **intentionally** verifying a disabled fallback. That is the right behavior. What matters is pairing the condition's meaning with the corresponding presence/absence of beans.

## 11. Final checklist before concluding "order is fixed"

- [ ] Is there a concrete specification of which bean must appear, which must be absent, and when?
- [ ] Is **auto-configuration** application order distinguished from **bean instance initialization** order?
- [ ] Are `before/after` or `beforeName/afterName` declared based on actual relationships?
- [ ] Is the source genuinely selected, processed, and providing a **bean definition** of the right type?
- [ ] Are bean names + counts + values asserted, rather than only testing startup success?
- [ ] Was `ConditionEvaluationReport` read for the right context, class, or method?
- [ ] Were both match and non-match cases tested (especially `@ConditionalOnMissingBean`)?
- [ ] Was the context tested both with and without a user bean?
- [ ] Was confusing `@DependsOn`/`@Order` with auto-config order avoided?
- [ ] Were classpath, property, and type metadata errors checked before blaming every symptom on order?

**Remember:** **The bean list answers "what exists?"; the Condition Evaluation Report answers "why did conditions allow or reject it?"**. Pairing them in isolated tests, keeping inputs stable, and varying only the `before/after` relationship is the surest way to verify ordering effects in Spring Boot Auto-configuration.

## Official documentation for reference

- Spring Boot 3.3 — Creating Your Own Auto-configuration: ordering rules, bean conditions, and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 API — `@AutoConfiguration` and `before/after/afterName`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3 API — `@AutoConfigureAfter`, explaining it affects definition order only: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigureAfter.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReportLoggingListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
