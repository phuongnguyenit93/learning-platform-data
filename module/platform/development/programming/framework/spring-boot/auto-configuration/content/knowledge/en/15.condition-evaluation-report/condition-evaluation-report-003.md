# Identifying Conditions on the Outer Class vs. @Bean Methods in the Report

> **Goal:** When a bean does not appear after Spring Boot starts up, pinpoint exactly which condition blocked it and whether that condition lives on the **outer configuration class** or on a **`@Bean` method**. Spring Boot's `ConditionEvaluationReport` records condition outcomes by source (class or method), allowing you to compare the overall configuration against individual beans.

This lesson belongs to the **Condition Evaluation Report** group in Spring Boot Auto Configuration, using Spring Boot 3.3.x and Java 17+. The focus covers report structure, reading `ClassName` and `ClassName#beanMethod` keys, the relationship between class-level and method-level conditions, the Actuator endpoint, startup logs, and testing with `ApplicationContextRunner`.

## 1. Why Must You Distinguish Between the Two Condition Levels?

An auto-configuration can provide multiple beans:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.report",
        name = "enabled",
        havingValue = "true")
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService("default");
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "metrics-enabled",
            havingValue = "true")
    ReportMetrics reportMetrics() {
        return new ReportMetrics("default");
    }
}
~~~

The snippet shows two layers:

- **Class level:** `demo.report.enabled` must equal `true` for `ReportAutoConfiguration` to be applied.
- **Method level:** `reportService()` only registers a default if no matching `ReportService` bean exists yet; `reportMetrics()` only registers if `demo.report.metrics-enabled=true`.

Suppose the application enables reporting but disables metrics:

- The class condition matches.
- The `reportService()` condition can match if no custom bean exists.
- The `reportMetrics()` condition does not match.
- As a result, the service is present, and metrics are absent.

If `demo.report.enabled=false`, the class-level condition does not match. In that case, the `@Bean` methods inside are not evaluated for bean registration through this configuration. This is the core difference: **class-level conditions gate the entire configuration; method-level conditions gate a specific bean**.

Placing multiple conditions on the same class or method means all conditions attached at that location must be satisfied. Method conditions must also reside inside a configuration class that has passed its class-level conditions.

## 2. What Is ConditionEvaluationReport?

`ConditionEvaluationReport` is Spring Boot's object for storing condition evaluation outcomes for logging and reporting. It groups outcomes by **source** — where the condition was declared:

- A configuration class name, e.g., `com.example.ReportAutoConfiguration`.
- A bean method name in the form `com.example.ReportAutoConfiguration#reportService`.

A single source can have multiple conditions at once. For example, if a class has both `@ConditionalOnClass` and `@ConditionalOnProperty`, the report records outcomes for both conditions under that class source. A method with `@ConditionalOnMissingBean` and `@ConditionalOnProperty` can likewise have multiple outcomes under its corresponding method source.

A typical report includes these concepts:

| Component | Meaning | How to Use When Investigating |
| --- | --- | --- |
| `positiveMatches` | Sources where all recorded conditions matched | Confirm that the class or method passed its condition gates |
| `negativeMatches` | Sources with at least one condition that did not match | Find the condition that blocked the configuration or bean |
| `notMatched` | Conditions that did not match within a negative source | Read the direct cause |
| `matched` | Other conditions in the same source that still matched | See which conditions passed before a failing condition |
| `unconditionalClasses` | Classes evaluated that had no conditions | Distinguish unconditional configurations from conditional ones |
| `exclusions` | Auto-configurations that were excluded | Investigate when a configuration was excluded rather than failing a condition |

`positiveMatches` and `negativeMatches` are categorized by **source**, not a list of bean instances successfully instantiated. A condition match means the configuration/bean definition is eligible to be registered along that branch; object instantiation afterward can still fail due to dependencies, constructors, or runtime errors.

## 3. Reading Source Names to Pinpoint the Exact Location

Look at the key before reading the message:

~~~text
com.example.ReportAutoConfiguration
com.example.ReportAutoConfiguration#reportService
com.example.ReportAutoConfiguration#reportMetrics
~~~

- A key without `#` is a **class-level** source.
- A key with `#methodName` is a **`@Bean` method-level** source.
- The part after `#` is the Java method name, not necessarily the bean name if the method declares a custom bean name via `@Bean("...")`.
- The class name may be package-qualified; if the configuration is a nested class, the binary name may contain `$`.

For example, `@Bean(name = "mainReportService")` on method `reportService()` still has the report source keyed by method name `#reportService`, not `#mainReportService`. When mapping a source to a bean name, inspect the Java method and its `@Bean` declaration.

### Quick Reading Rules

1. Find the class source `ReportAutoConfiguration`.
2. If the class source is in `negativeMatches`, read `notMatched` first: which class-level condition is blocking the entire configuration?
3. If the class source is in `positiveMatches`, move on to the `#methodName` sources.
4. Find the missing bean method; read `notMatched` for that method.
5. If both class and method are positive yet the bean is unusable, switch to investigating bean definitions, dependency injection, and object initialization errors.

Do not conclude “the bean was disabled by the method” solely from not seeing a method key. If the class-level condition did not match, the methods inside may not have been evaluated and therefore have no separate entry.

## 4. Report Structure on Actuator

If the application has `spring-boot-starter-actuator`, the `conditions` endpoint can display the report as JSON. In a secured diagnostic environment, example exposure configuration:

~~~properties
management.endpoints.web.exposure.include=health,conditions
~~~

Then send a request:

~~~bash
curl http://localhost:8080/actuator/conditions
~~~

This endpoint is not automatically opened publicly just by adding Actuator. Configure appropriate exposure and protect it with authentication/network policy; do not expose internal configuration details to the internet.

### Abbreviated JSON Example

Suppose `ReportAutoConfiguration` matched, `reportService()` can create a default, but `reportMetrics()` is blocked because the property is not enabled. The abbreviated structure might look like this:

~~~json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.ReportAutoConfiguration": [
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (demo.report.enabled) matched"
          }
        ],
        "com.example.ReportAutoConfiguration#reportService": [
          {
            "condition": "OnBeanCondition",
            "message": "@ConditionalOnMissingBean did not find any beans"
          }
        ]
      },
      "negativeMatches": {
        "com.example.ReportAutoConfiguration#reportMetrics": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "@ConditionalOnProperty (demo.report.metrics-enabled) did not match"
            }
          ],
          "matched": []
        }
      },
      "unconditionalClasses": []
    }
  }
}
~~~

This is illustrative JSON showing how sources and conditions are grouped, not a verbatim copy of output from a specific application. Actual messages depend on annotations, properties, the bean registry, and the Boot version.

How to read the example:

- The class source is in `positiveMatches`: the outer condition matched.
- `#reportService` is also in `positiveMatches`: the missing-bean condition for the service matched.
- `#reportMetrics` is in `negativeMatches`: metrics were blocked at the method.
- `notMatched` indicates the specific property condition that failed; `matched` is empty because this example only has one condition on that method.

If there are multiple condition annotations on the same source, `negativeMatches` can contain both `matched` and `notMatched`. For example, a method may have `@ConditionalOnClass` match while `@ConditionalOnProperty` does not; the report shows both instead of vaguely saying “method was not created”.

## 5. When the Class-Level Condition Does Not Match

Suppose:

~~~properties
demo.report.enabled=false
demo.report.metrics-enabled=true
~~~

Result:

1. `ReportAutoConfiguration` is blocked by the class-level condition.
2. `reportService()` and `reportMetrics()` are not registered via this auto-configuration.
3. The report records the class source in `negativeMatches` with the unmatched property condition.
4. You should not expect the report to have two separate method sources for methods that were never evaluated.

Class-level conditions are generally suited for requirements shared by the entire group: a required library on the classpath, the application having to be a Servlet web application, or a property disabling the entire integration. They are not suitable if you only want to disable one bean while still needing the other beans in the same class.

One nuance: a class-level condition does not mean Spring skips all class metadata inspection. According to Boot's documentation, an important difference between class-level and method-level conditions is that class-level conditions also govern registering the configuration class itself as a bean; meanwhile, methods inside the class are not used to contribute beans when the class fails its condition.

## 6. When the Class Matches but a Method Does Not

This is a common case when an auto-configuration provides multiple independent beans.

Example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "demo.report",
        name = "enabled",
        havingValue = "true")
class ReportAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(ReportService.class)
    ReportService reportService() {
        return new ReportService("default");
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "metrics-enabled",
            havingValue = "true")
    ReportMetrics reportMetrics() {
        return new ReportMetrics("default");
    }
}
~~~

With:

~~~properties
demo.report.enabled=true
demo.report.metrics-enabled=false
~~~

The report can show the class as positive, method `reportService` as positive, and method `reportMetrics` as negative. This is evidence that the outer configuration is still active; only the metrics bean is blocked by its own condition.

If `reportService` is placed in `negativeMatches` because `@ConditionalOnMissingBean` found a bean of the same type, that may be an **intentional back-off**: the user already supplied a custom implementation. In that case, inspect the actual bean to confirm the custom bean is registered rather than forcing the default to appear.

## 7. Using ConditionEvaluationReport Directly in Java

Besides Actuator, Spring Boot provides the `ConditionEvaluationReport` API to access the report from the bean factory. The snippet below is an **illustrative method** that can be placed in a test or diagnostic code receiving an open `ConfigurableApplicationContext`:

~~~java
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.context.ConfigurableApplicationContext;

static void printConditionSources(ConfigurableApplicationContext context) {
    ConditionEvaluationReport report =
            ConditionEvaluationReport.get(context.getBeanFactory());

    Map<String, ConditionAndOutcomes> bySource =
            report.getConditionAndOutcomesBySource();

    bySource.forEach((source, outcomes) -> {
        System.out.println(
                source + " (allMatched=" + outcomes.isFullMatch() + ")");
        for (ConditionAndOutcome outcome : outcomes) {
            System.out.println("  " + outcome);
        }
    });

    System.out.println("Excluded: " + report.getExclusions());
    System.out.println("Unconditional: " + report.getUnconditionalClasses());
}
~~~

This method prints each source, whether all conditions in that source matched, each condition/outcome pair, the exclusion list, and the unconditional classes. It is not a standalone Java program: it must be called with an active context that has already gone through auto-configuration evaluation. Do not call it after the context has closed because the bean factory is no longer available.

Some important methods:

| API | Returns | How to Use |
| --- | --- | --- |
| `ConditionEvaluationReport.get(beanFactory)` | Report attached to the bean factory | Retrieve the context's report |
| `getConditionAndOutcomesBySource()` | Map of source → condition/outcomes | Look up classes and methods |
| `ConditionAndOutcomes.isFullMatch()` | Boolean | Check if all conditions at the source matched |
| `ConditionAndOutcome.getCondition()` | Condition | Identify the condition type |
| `ConditionAndOutcome.getOutcome()` | ConditionOutcome | Read the condition outcome |
| `getExclusions()` | List of excluded classes | Investigate excluded configurations |
| `getUnconditionalClasses()` | Set of classes without conditions | Distinguish from conditional sources |

This API is useful for testing and internal tooling. For routine operations, startup logs or Actuator are usually sufficient; avoid writing a custom debug endpoint when official endpoints already meet the need.

## 8. Enabling the Report in Startup Logs

The fastest way to view the Condition Evaluation Report in a real application is to run with:

~~~bash
java -jar app.jar --debug
~~~

Spring Boot will include condition details in startup logs, usually under the `CONDITIONS EVALUATION REPORT` heading. Read the positive and negative match groups, then locate the relevant class or method.

In tests, you can use `ConditionEvaluationReportLoggingListener` to print the report at a desired log level:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class ConditionReportLoggingTest {

    @Test
    void printsConditionReport() {
        new ApplicationContextRunner()
                .withConfiguration(
                        AutoConfigurations.of(ReportAutoConfiguration.class))
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    // Place bean assertions here.
                });
    }
}
~~~

The example assumes `ReportAutoConfiguration` is declared in the test or the source set under test. The listener is an `ApplicationContextInitializer` that writes the report to logs. Per the Boot API, the report is logged at DEBUG by default; `forLogLevel` lets you choose the log level. Do not share the same listener instance across multiple different contexts.

If the application fails during startup, the report in logs can be a helpful clue even before the HTTP server is running. The Actuator `/actuator/conditions` endpoint can only be called once the application/context has started up enough to serve endpoints.

## 9. Testing: Verifying Class-Level and Method-Level Appear Separately

The example below is **one complete Java test file** for Java 17+, Spring Boot 3.3.x, JUnit Jupiter, and AssertJ. It tests four states:

1. The class and both methods match.
2. The class-level condition fails, so methods are not evaluated.
3. The class matches, but one method's property condition fails.
4. The user supplies a custom bean, causing `@ConditionalOnMissingBean` on one method not to match while the other method still works.

**File:** `src/test/java/example/report/ConditionSourceReportTest.java`

~~~java
package example.report;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionSourceReportTest {

    record ReportService(String source) {}
    record ReportMetrics(String source) {}

    @AutoConfiguration
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true")
    static class ReportAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(ReportService.class)
        ReportService reportService() {
            return new ReportService("default");
        }

        @Bean
        @ConditionalOnProperty(
                prefix = "demo.report",
                name = "metrics-enabled",
                havingValue = "true")
        ReportMetrics reportMetrics() {
            return new ReportMetrics("default");
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserReportConfiguration {

        @Bean
        ReportService customReportService() {
            return new ReportService("user");
        }
    }

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner().withConfiguration(
                    AutoConfigurations.of(ReportAutoConfiguration.class));

    private static ConditionEvaluationReport report(
            AssertableApplicationContext context) {
        return ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory());
    }

    private static ConditionAndOutcomes source(
            AssertableApplicationContext context, String suffix) {
        return report(context).getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith(suffix))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError("Missing report source: " + suffix));
    }

    @Test
    void classAndBothBeanMethodsMatch() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasSingleBean(ReportMetrics.class);

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isTrue();
                });
    }

    @Test
    void classLevelFailurePreventsMethodConditionsFromBeingReached() {
        runner.withPropertyValues(
                "demo.report.enabled=false",
                "demo.report.metrics-enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean("reportService");
                    assertThat(context).doesNotHaveBean("reportMetrics");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isFalse();

                    var keys = report(context)
                            .getConditionAndOutcomesBySource().keySet();
                    assertThat(keys)
                            .noneMatch(key -> key.endsWith("#reportService")
                                    || key.endsWith("#reportMetrics"));
                });
    }

    @Test
    void methodLevelFailureOnlyBlocksThatBean() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).doesNotHaveBean("reportMetrics");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isFalse();
                });
    }

    @Test
    void userBeanMakesMethodLevelMissingBeanConditionFail() {
        runner.withPropertyValues(
                "demo.report.enabled=true",
                "demo.report.metrics-enabled=true")
                .withUserConfiguration(UserReportConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(ReportService.class);
                    assertThat(context).hasBean("customReportService");
                    assertThat(context).doesNotHaveBean("reportService");
                    assertThat(context).hasSingleBean(ReportMetrics.class);
                    assertThat(context.getBean(ReportService.class).source())
                            .isEqualTo("user");

                    assertThat(source(context, "ReportAutoConfiguration")
                            .isFullMatch()).isTrue();
                    assertThat(source(context, "#reportService")
                            .isFullMatch()).isFalse();
                    assertThat(source(context, "#reportMetrics")
                            .isFullMatch()).isTrue();
                });
    }
}
~~~

**How to run** in a Maven or Gradle project with Spring Boot 3.3 and `spring-boot-starter-test`:

~~~bash
mvn -Dtest=ConditionSourceReportTest test
# Or with Gradle wrapper on Linux/macOS:
./gradlew test --tests example.report.ConditionSourceReportTest
~~~

**Expected result:** **4 tests PASS**, with no fixed stdout because the tests only use assertions. The assertions on `ConditionEvaluationReport` prove:

- The class source has an entry independent of the method sources.
- When the class-level condition fails, there are no separate entries for the two methods.
- When one method-level condition fails, the remaining method can still match.
- When the user declares `ReportService`, the `#reportService` source records the missing-bean condition as not matched, while `#reportMetrics` still matches.

The nested auto-configuration classes in the example allow the test to load them directly via `AutoConfigurations.of(...)`. In a real library, use top-level classes and register them via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`; do not put test classes into the starter's imports file.

## 10. Distinguishing the Condition Report from Other Signals

| Observed Signal | What You Can Conclude | What to Check Next |
| --- | --- | --- |
| Class source in `negativeMatches` | A class-level condition did not match | Message in `notMatched` and actual Environment values |
| Class positive, method source negative | Outer configuration passed; bean method was blocked | Annotations on the method, bean type/name, properties |
| Class positive, method positive, yet bean is unusable | Conditions matched | Bean definition, dependency injection, object creation exceptions |
| Class source not found in report | Not enough evidence to conclude a condition failed | AutoConfiguration imports, exclusions, classpath, package scanning, and active context |
| Class appears in `exclusions` | Auto-configuration was excluded from application | `spring.autoconfigure.exclude` or the application's exclude attributes |
| Bean exists, yet expected method condition is missing | Bean may come from another source or bypass that method | `/actuator/beans`, bean name, bean definition resource |

A common mistake is seeing a missing bean and concluding a method condition failed. The bean might not be registered from another configuration, the auto-configuration might be excluded, the class might not be imported, or the application might be inspecting the wrong child/parent context. Identify the exact context and declaration source before changing annotations.

`ConditionEvaluationReport` focuses on Spring Boot's condition system. Spring Framework's own conditions (for example `@Profile`) do not necessarily appear with the same message format as `@ConditionalOnProperty` or `@ConditionalOnBean`. If a configuration depends on profiles, check active/default profiles via `Environment` alongside the report.

In addition, the report is the evaluation result during context construction, not a continuous monitoring screen. Changing properties after the application has started does not automatically re-evaluate conditions or register new beans.

## 11. Step-by-Step Investigation Workflow

When an expected bean does not appear, use the following workflow:

1. **Identify the context:** does the application have multiple parent/child contexts? Which context id does the report endpoint show?
2. **Locate the class source:** is the auto-configuration class in `positiveMatches`, `negativeMatches`, `unconditionalClasses`, or `exclusions`?
3. **If the class is negative:** read the first unmatched condition and check the corresponding data — classpath, properties, profiles, application type, or bean definitions.
4. **If the class is positive:** find the `#beanMethod` source matching the Java method.
5. **Read all conditions on the method:** `notMatched` is the blocking cause; `matched` shows conditions that passed. If `@ConditionalOnMissingBean` failed, check which bean exists and which type is being compared.
6. **If the method is positive yet the application still errors:** inspect startup exceptions, dependencies, and object creation; the condition report does not guarantee a bean instance initialized successfully.
7. **Write a reproduction test:** use `ApplicationContextRunner`, changing only one variable at a time (property, user bean, or classpath) to confirm the exact source flips.

This approach avoids mistakenly editing a class-level annotation when the real issue lies on one method, or deleting an entire auto-configuration when only one bean's property needs fixing.

## 12. Design Notes for Keeping Conditions Readable in the Report

- **Place shared conditions on the class:** for example, a required dependency for the entire integration or a master toggle for the whole group.
- **Place bean-specific conditions on the method:** for example, `@ConditionalOnMissingBean` per default or a property that applies only to one bean.
- **Use concrete return types for `@Bean`:** bean conditions rely on the type information present in the method signature during evaluation.
- **Do not depend on beans registered later:** `@ConditionalOnBean` and `@ConditionalOnMissingBean` only observe bean definitions already processed when the condition runs; order auto-configurations when there is a provider/consumer relationship.
- **Isolate optional dependencies into nested configurations:** especially when `@ConditionalOnClass` checks a class that may be absent from the classpath; do not let a method return type force the JVM to load an optional class before the condition has a chance to guard it.
- **Name methods meaningfully:** report sources use method names, so overly generic names like `client` or `configuration` make logs hard to read. Prefer `defaultReportService`, `reportMetrics`, or names that clearly reflect the bean.
- **Keep condition messages specific:** custom `Condition` implementations should return messages stating clearly which property/type/resource was found or missing. If writing a condition for Boot, consider extending `SpringBootCondition` to integrate with Boot's outcome/logging mechanism.

## 13. Self-Check Questions

1. The report has key `com.example.ReportAutoConfiguration#reportMetrics` in `negativeMatches`, while the class source is positive. What is blocked? **Only the `reportMetrics` bean method**; the outer configuration still passed its conditions.
2. The class source is in `negativeMatches` and there is no `#reportService` key. Can you conclude the method condition failed? **No.** The method may not have been evaluated because the class-level condition blocked the configuration.
3. `reportService` has a positive key, yet the application still fails with `UnsatisfiedDependencyException`. Is that a contradiction? **No.** A condition match allows registering the definition; dependencies or object creation can still fail.
4. Why is the `#` key important? It separates a bean method's outcome from the configuration class's outcome, helping pinpoint condition scope.
5. Where should you look for excluded auto-configurations? Check `exclusions` in the report and `spring.autoconfigure.exclude` or the exclude attributes of `@SpringBootApplication`.
6. Why do tests use `ApplicationContextRunner`? It creates a small context with specific properties/user beans/classpath, making it easy to compare report sources across cases.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): class/method conditions, ordering, `ApplicationContextRunner`, and testing auto-configuration.
- [Spring Boot 3.3 API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): report, source grouping, exclusions, unconditional classes.
- [Spring Boot 3.3 API — ConditionEvaluationReportLoggingListener](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html): writing the report to logs and choosing log level.
- [Spring Boot 3.3 Actuator — Conditions endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html): structure of `positiveMatches`, `negativeMatches`, `notMatched`, and `matched`.
- [Spring Boot 3.3 — Actuator Endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html): exposing and securing management endpoints.

**Remember:** Read the report in two layers: **class source first, method source second**. Class-level negative means the outer configuration failed its conditions; class-level positive with method-level negative means a specific bean was blocked. Match source keys to class/method names, then verify actual beans and startup exceptions before changing configuration.
