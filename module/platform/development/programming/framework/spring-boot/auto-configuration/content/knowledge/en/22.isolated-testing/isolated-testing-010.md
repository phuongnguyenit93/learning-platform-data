# Reading the Condition Evaluation Report Inside Tests to Explain Outcomes

> **Spring Boot Auto Configuration → Isolated Testing.** This lesson guides you through reading `ConditionEvaluationReport` directly inside `ApplicationContextRunner` callbacks. We will look up results by source—either an auto-configuration class or a factory method—distinguish match/no-match conditions, read Spring Boot's explanatory messages, and write assertions for two cases: a property not enabling the configuration, and an application-provided bean causing the default bean to back off. Examples use Java 17+, Maven, and Spring Boot 3.3.13.

## 1. Why is asserting only bean presence or absence not enough?

A test often starts with:

~~~java
runner.run(context -> {
    assertThat(context).doesNotHaveBean(NoticeClient.class);
});
~~~

This assertion confirms the final outcome: the context has no `NoticeClient`. However, it does not explain **why** the bean did not appear.

Many causes can lead to the same outcome:
- The feature-enabling property was not set or is false.
- An optional class is absent from the classpath.
- A dependency bean required by the integration does not exist yet.
- The application already provided a bean of the same type, so `@ConditionalOnMissingBean` did not match.
- The auto-configuration was excluded.
- The configuration matched, yet the bean factory method threw an exception.

When a test only checks bean absence, these causes can be confused. For instance, a test intended to verify `acme.notice.enabled=false` might still pass even if the configuration was skipped due to a missing dependency. The test failed to prove the property condition was evaluated properly.

`ConditionEvaluationReport` lets you verify the reason behind every condition. It records:
- The evaluated source: configuration class or factory method.
- The condition object that ran.
- The match or no-match outcome.
- The explanatory message produced by the condition.

Combining bean assertions with the report lets tests answer both questions: **what happened** and **which condition produced that outcome**.

## 2. What is ConditionEvaluationReport?

`org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` is the object Spring Boot uses to record condition evaluation results for reporting and logging.

The report is attached to the application context's `BeanFactory`. Inside a context created by `ApplicationContextRunner`, you can retrieve the report once the context starts successfully:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.find(
                context.getSourceApplicationContext().getBeanFactory()
        );
~~~

Explanation:
- `context` is the `AssertableApplicationContext` passed to the runner callback.
- `getSourceApplicationContext()` returns the underlying real application context behind the assertion wrapper.
- `getBeanFactory()` retrieves the bean factory that processed the configuration.
- `ConditionEvaluationReport.find(...)` looks up an existing report; if none exists, it returns `null`.

In tests, use `find(...)` when you want to verify a report was actually created. `ConditionEvaluationReport.get(beanFactory)` returns an existing report or creates a new one; using `get(...)` can accidentally give your test an empty report and mask the fact that no condition data was recorded.

### 2.1. Key APIs

| API | Meaning |
| --- | --- |
| `ConditionEvaluationReport.find(beanFactory)` | Finds an existing report; may return null |
| `ConditionEvaluationReport.get(beanFactory)` | Gets an existing report or creates a new one |
| `getConditionAndOutcomesBySource()` | Map of condition outcomes keyed by source |
| `getExclusions()` | List of excluded auto-configurations |
| `getUnconditionalClasses()` | Classes evaluated without conditions |
| `ConditionAndOutcomes.isFullMatch()` | true when every condition on the source matched |
| `ConditionAndOutcome.getCondition()` | The evaluated Condition object |
| `ConditionAndOutcome.getOutcome()` | The evaluation outcome of the condition |
| `ConditionOutcome.isMatch()` | Whether the condition matched |
| `ConditionOutcome.getMessage()` | Explanatory message for the outcome |

These classes and methods belong to the Spring Boot 3.3.13 API. The report records results by source, allowing separate inspection of class-level conditions and conditions on individual bean factory methods.

### 2.2. Source is a class or factory method

The map from `getConditionAndOutcomesBySource()` uses the source name as its key. Two common forms:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
com.acme.notice.autoconfigure.NoticeAutoConfiguration#noticeClient
~~~

- The first key represents class-level conditions.
- The second key represents conditions on the `noticeClient()` factory method.

This distinction is very helpful because a class can match while an inner bean method still does not match. For example, a property enables the entire configuration, yet `@ConditionalOnMissingBean` on the method does not match because the application registered a replacement bean.

Do not just grab the first entry in the entire report and draw conclusions for a specific bean. Look up the exact source key your test is verifying.

## 3. Distinguishing condition state from bean state

`ConditionAndOutcomes` holds one or more `ConditionAndOutcome` entries.

- `isFullMatch()` returns true when every outcome in the source matches.
- `isMatch()` on each `ConditionOutcome` tells whether that specific condition matched.
- `getMessage()` provides the explanation for the outcome.

Example:

~~~java
var outcomes = report.getConditionAndOutcomesBySource()
        .get(NoticeAutoConfiguration.class.getName());

assertThat(outcomes).isNotNull();
assertThat(outcomes.isFullMatch()).isFalse();

assertThat(outcomes).anySatisfy(item -> {
    assertThat(item.getOutcome().isMatch()).isFalse();
    assertThat(item.getOutcome().getMessage()).contains("enabled");
});
~~~

Do not conflate three distinct concepts:
1. **Class condition:** decides whether the configuration is applied.
2. **Bean method condition:** decides whether a specific factory method is registered.
3. **Bean creation:** occurs after bean definitions are registered; a bean can still fail during instantiation.

The report explains the condition evaluation step. It does not prove every bean instantiated cleanly or that business operations will work.

### 3.1. A non-matching class can prevent method conditions from evaluating

Suppose the class has `@ConditionalOnProperty` and the factory method has `@ConditionalOnMissingBean`.

If the property does not match:
- Spring skips the configuration.
- Method `noticeClient()` is not registered.
- The condition on the method may have no separate entry in the report, because the method never reached evaluation.

If the property matches yet the application already supplied `NoticeClient`:
- The class condition matches.
- Spring evaluates the bean method.
- `@ConditionalOnMissingBean` does not match.
- The default bean is not created.

Both situations leave `NoticeClient` absent, yet the report reveals the different causes.

## 4. Sample project with Java 17 and Spring Boot 3.3.13

This lab builds a simple auto-configuration. The `NoticeClient` bean is created only when `acme.notice.enabled=true`; the factory method creates the default bean only if the application has not already supplied a bean of the same type.

### 4.1. Project structure

~~~text
notice-condition-report/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/notice/
    │   │   ├── NoticeClient.java
    │   │   └── autoconfigure/
    │   │       └── NoticeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeAutoConfigurationConditionReportTest.java
~~~

### 4.2. pom.xml

File `pom.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme</groupId>
    <artifactId>notice-condition-report</artifactId>
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
~~~

`spring-boot-autoconfigure` provides condition annotations and the report API. `spring-boot-starter-test` provides JUnit 5, AssertJ, and `ApplicationContextRunner`.

### 4.3. NoticeClient.java

File `src/main/java/com/acme/notice/NoticeClient.java`:

~~~java
package com.acme.notice;

public record NoticeClient(String origin) {

    public String send(String message) {
        return origin + ":" + message;
    }
}
~~~

The `origin` attribute helps tests distinguish whether the bean came from auto-configuration or the application.

### 4.4. NoticeAutoConfiguration.java

File `src/main/java/com/acme/notice/autoconfigure/NoticeAutoConfiguration.java`:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class NoticeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(NoticeClient.class)
    NoticeClient noticeClient() {
        return new NoticeClient("auto");
    }
}
~~~

There are two condition layers:
- `@ConditionalOnProperty` sits on the class. When the property is missing or not true, the configuration is not applied.
- `@ConditionalOnMissingBean` sits on the method. When the context already has `NoticeClient`, the default bean is not created.

### 4.5. Registering the auto-configuration

Create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
~~~

This file registers the configuration for Spring Boot applications when the module is packaged as a JAR. The tests below use `AutoConfigurations.of(NoticeAutoConfiguration.class)` to load the class directly and focus on reading the condition report; they do not test Boot's discovery of the imports file inside a JAR.

## 5. Creating helpers to read the report inside tests

The test file will include two helpers:
- `conditionReport(...)` retrieves the report from the context's BeanFactory.
- `outcomesFor(...)` retrieves outcomes by the exact source key and asserts the source exists in the report.

~~~java
private static ConditionEvaluationReport conditionReport(
        AssertableApplicationContext context) {

    var sourceContext = context.getSourceApplicationContext();

    ConditionEvaluationReport report =
            ConditionEvaluationReport.find(sourceContext.getBeanFactory());

    assertThat(report)
            .as("ConditionEvaluationReport should exist after refresh")
            .isNotNull();

    return report;
}

private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
        ConditionEvaluationReport report,
        String source) {

    var outcomes = report.getConditionAndOutcomesBySource().get(source);

    assertThat(outcomes)
            .as("Condition outcomes for " + source)
            .isNotNull();

    return outcomes;
}
~~~

Required imports:

~~~java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
~~~

Retrieve the report inside the `run(...)` callback, after the context has refreshed. Do not fetch the source context if context startup failed; `getSourceApplicationContext()` cannot be used when context startup fails.

### 5.1. Printing details for a source

When you want to inspect the report in test logs, you can add a helper:

~~~java
private static void printOutcomes(
        ConditionEvaluationReport report,
        String source) {

    var outcomes = outcomesFor(report, source);

    System.out.println("source: " + source);
    System.out.println("full match: " + outcomes.isFullMatch());

    for (var item : outcomes) {
        var outcome = item.getOutcome();

        System.out.println(
                "  " + item.getCondition().getClass().getSimpleName()
                        + " -> "
                        + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                        + " : "
                        + outcome.getMessage()
        );
    }
}
~~~

This helper does not decide test pass/fail. It merely prints data so readers can see which conditions matched and which messages explain the result. Assertions still must be written separately.

## 6. Three tests reading the report to explain three outcomes

File `src/test/java/com/acme/notice/autoconfigure/NoticeAutoConfigurationConditionReportTest.java`:

~~~java
package com.acme.notice.autoconfigure;

import com.acme.notice.NoticeClient;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeAutoConfigurationConditionReportTest {

    private static final String CONFIG_SOURCE =
            NoticeAutoConfiguration.class.getName();

    private static final String BEAN_METHOD_SOURCE =
            NoticeAutoConfiguration.class.getName() + "#noticeClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeAutoConfiguration.class
                    ));

    private static ConditionEvaluationReport conditionReport(
            AssertableApplicationContext context) {

        var sourceContext = context.getSourceApplicationContext();

        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(sourceContext.getBeanFactory());

        assertThat(report)
                .as("ConditionEvaluationReport should exist after refresh")
                .isNotNull();

        return report;
    }

    private static ConditionEvaluationReport.ConditionAndOutcomes outcomesFor(
            ConditionEvaluationReport report,
            String source) {

        var outcomes = report.getConditionAndOutcomesBySource().get(source);

        assertThat(outcomes)
                .as("Condition outcomes for " + source)
                .isNotNull();

        return outcomes;
    }

    private static void printOutcomes(
            ConditionEvaluationReport report,
            String source) {

        var outcomes = outcomesFor(report, source);

        System.out.println("source: " + source);
        System.out.println("full match: " + outcomes.isFullMatch());

        for (var item : outcomes) {
            var outcome = item.getOutcome();

            System.out.println(
                    "  " + item.getCondition().getClass().getSimpleName()
                            + " -> "
                            + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                            + " : "
                            + outcome.getMessage()
            );
        }
    }

    @Test
    void missingPropertyReportExplainsWhyConfigurationWasSkipped() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(NoticeClient.class);

            ConditionEvaluationReport report = conditionReport(context);
            var outcomes = outcomesFor(report, CONFIG_SOURCE);

            assertThat(outcomes.isFullMatch()).isFalse();

            assertThat(outcomes).anySatisfy(item -> {
                assertThat(item.getOutcome().isMatch()).isFalse();
                assertThat(item.getOutcome().getMessage())
                        .contains("enabled");
            });

            printOutcomes(report, CONFIG_SOURCE);
        });
    }

    @Test
    void enabledPropertyShowsPositiveClassAndBeanMethodOutcomes() {
        runner.withPropertyValues("acme.notice.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class).origin())
                            .isEqualTo("auto");

                    ConditionEvaluationReport report = conditionReport(context);

                    var classOutcomes =
                            outcomesFor(report, CONFIG_SOURCE);

                    var beanOutcomes =
                            outcomesFor(report, BEAN_METHOD_SOURCE);

                    assertThat(classOutcomes.isFullMatch()).isTrue();
                    assertThat(beanOutcomes.isFullMatch()).isTrue();

                    printOutcomes(report, CONFIG_SOURCE);
                    printOutcomes(report, BEAN_METHOD_SOURCE);
                });
    }

    @Test
    void userBeanExplainsWhyDefaultFactoryMethodWasSkipped() {
        NoticeClient customClient = new NoticeClient("application");

        runner.withPropertyValues("acme.notice.enabled=true")
                .withBean(NoticeClient.class, () -> customClient)
                .run(context -> {
                    assertThat(context).hasSingleBean(NoticeClient.class);
                    assertThat(context.getBean(NoticeClient.class))
                            .isSameAs(customClient);

                    ConditionEvaluationReport report = conditionReport(context);
                    var classOutcomes =
                            outcomesFor(report, CONFIG_SOURCE);
                    var beanOutcomes =
                            outcomesFor(report, BEAN_METHOD_SOURCE);

                    assertThat(classOutcomes.isFullMatch()).isTrue();
                    assertThat(beanOutcomes.isFullMatch()).isFalse();

                    assertThat(beanOutcomes).anySatisfy(item -> {
                        assertThat(item.getOutcome().isMatch()).isFalse();
                        assertThat(item.getOutcome().getMessage())
                                .contains("NoticeClient");
                    });

                    printOutcomes(report, CONFIG_SOURCE);
                    printOutcomes(report, BEAN_METHOD_SOURCE);
                });
    }
}
~~~

### 6.1. Case A: missing property

The `missingPropertyReportExplainsWhyConfigurationWasSkipped()` test passes no `acme.notice.enabled`.

Outcome:
- `NoticeClient` is not in the context.
- The class source has an entry in the report.
- `isFullMatch()` is false.
- At least one no-match outcome has a message mentioning the `enabled` property.

This proves the bean is absent because the class condition failed to match. No guessing from test names or bean-only assertions is needed.

### 6.2. Case B: property enabled

The `enabledPropertyShowsPositiveClassAndBeanMethodOutcomes()` test passes:

~~~java
.withPropertyValues("acme.notice.enabled=true")
~~~

Outcome:
- The class-level property condition matches.
- The method-level missing-bean condition matches because no `NoticeClient` exists yet.
- The default bean is created with `origin` equal to `auto`.

Both sources are verified separately. This confirms both the configuration and the factory method satisfied their conditions.

### 6.3. Case C: application supplies a replacement bean

The `userBeanExplainsWhyDefaultFactoryMethodWasSkipped()` test passes the enabled property and registers a custom bean using `withBean(...)`.

Outcome:
- The class-level property condition still matches.
- `@ConditionalOnMissingBean` on the factory method does not match.
- The context retains the application's custom instance.
- The report entry for source `NoticeAutoConfiguration#noticeClient` explains why the default bean was skipped.

This is a key example: the report can show **class matched yet method did not match**. If you only inspect the class's overall status, you will miss why a specific bean was not created.

## 7. Running tests and reading the report

From the project directory:

~~~bash
mvn clean test
~~~

Expect three tests to PASS:
- Missing property: configuration does not match.
- Property true: both class and bean method match.
- Property true with user bean: class matches, factory method does not match.

`printOutcomes(...)` prints the source, full match status, condition name, and Boot's message. Abbreviated example output:

~~~text
source: com.acme.notice.autoconfigure.NoticeAutoConfiguration
full match: false
  OnPropertyCondition -> NO MATCH : <message explaining enabled property was not satisfied>
~~~

For the user override case:

~~~text
source: com.acme.notice.autoconfigure.NoticeAutoConfiguration
full match: true

source: com.acme.notice.autoconfigure.NoticeAutoConfiguration#noticeClient
full match: false
  OnBeanCondition -> NO MATCH : <message indicating NoticeClient was found>
~~~

Text inside angle brackets describes the message format, not a fixed stdout string. Actual messages are generated by Spring Boot and may vary slightly across versions. Tests should check the status and a stable substring rather than comparing the entire message.

## 8. Reading the full report or filtering the needed parts

### 8.1. Iterating over all sources

When you do not yet know which condition caused an outcome, iterate through the whole map:

~~~java
ConditionEvaluationReport report = conditionReport(context);

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println(
            source + " => "
                    + (outcomes.isFullMatch() ? "MATCH" : "NO MATCH")
    );

    outcomes.forEach(item -> {
        var outcome = item.getOutcome();

        System.out.println(
                "  " + item.getCondition().getClass().getSimpleName()
                        + " => "
                        + (outcome.isMatch() ? "MATCH" : "NO MATCH")
                        + " : "
                        + outcome.getMessage()
        );
    });
});
~~~

This is useful when investigating an auto-configuration with many nested configurations and bean methods. Once you know the target bean, filter by its specific source so assertions are not affected by unrelated components' conditions.

### 8.2. Filtering no-match sources

~~~java
report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    if (!outcomes.isFullMatch()) {
        System.out.println("NO MATCH: " + source);

        outcomes.forEach(item -> {
            if (!item.getOutcome().isMatch()) {
                System.out.println(item.getOutcome().getMessage());
            }
        });
    }
});
~~~

This filter focuses on reasons a configuration or bean was skipped. A source can hold multiple conditions; `isFullMatch()` being false means at least one outcome did not match, so iterate over every outcome to find the exact cause.

### 8.3. Inspecting excluded auto-configurations

~~~java
ConditionEvaluationReport report = conditionReport(context);

assertThat(report.getExclusions()).isNotNull();

report.getExclusions().forEach(exclusion ->
        System.out.println("excluded: " + exclusion)
);
~~~

`getExclusions()` lists classes removed from condition evaluation due to exclusion settings. This differs from a condition being evaluated and returning no-match:
- Exclusion: the class was excluded from evaluation.
- No-match: the condition was evaluated and not satisfied.

Do not assume every source absent from the map was excluded. The class may not have been a candidate, may not have been imported, or may not have reached that condition step.

## 9. Combining the report with assertions and failure messages

The goal of the report in tests is making failures easy to diagnose. You can include the source key in assertion descriptions:

~~~java
assertThat(outcomes.isFullMatch())
        .as("Condition report for %s", CONFIG_SOURCE)
        .isFalse();
~~~

Or assert on the combined messages:

~~~java
String reasons = StreamSupport.stream(
        outcomes.spliterator(),
        false
).map(item -> item.getOutcome().getMessage())
 .filter(Objects::nonNull)
 .collect(Collectors.joining("; "));

assertThat(reasons)
        .as("Condition no-match explanation")
        .contains("enabled");
~~~

This snippet needs imports for `java.util.Objects`, `java.util.stream.Collectors`, and `java.util.stream.StreamSupport`. Use it only when combining multiple outcomes into one string; for a simple source, iterating directly is usually easier to read.

A good test typically follows this order:
1. Assert bean presence/absence per the contract.
2. Retrieve the report.
3. Assert the source has an entry.
4. Assert `isFullMatch()` according to the scenario.
5. Assert at least one no-match or match outcome for the condition under test.
6. Check a substring of the message to confirm the reason.

Do not assert only messages while ignoring the bean. A no-match condition might be right while the bean still appears from another configuration. Conversely, do not assert only bean absence without checking the report when the test's goal is verifying the reason.

## 10. When to read the report directly vs. using --debug?

The two approaches serve different purposes:

| Approach | Scope | When to use |
| --- | --- | --- |
| `ConditionEvaluationReport` in `ApplicationContextRunner` | Single test context | Asserting the cause for one auto-configuration or bean |
| `--debug` | Single application run | Overall configuration investigation in an application |
| Actuator `/actuator/conditions` | Running context with endpoint exposed | Inspecting conditions in a controlled environment |

In tests, reading the report object directly is better than parsing console logs. Logs can change format, be captured by test runners, or mix with logs from other configurations.

In a running application, `--debug` prints the overall Condition Evaluation Report. The Actuator `conditions` endpoint also supplies data on configuration/auto-configuration conditions when Actuator is properly configured and secured.

You do not need to enable `--debug` in every test just to read the report. `ConditionEvaluationReport` can be fetched directly from the BeanFactory inside the runner callback.

## 11. What the report does NOT prove

1. **The report does not prove beans instantiated successfully.** Matching conditions only allow the configuration/bean definition to proceed; constructors or factory methods can still throw exceptions.
2. **The report does not prove external connectivity works.** For instance, a matching DataSource condition does not prove the database accepts connections.
3. **The report does not replace bean assertions.** You must still verify the actual results in the context.
4. **The report does not necessarily contain entries for every Java condition.** Spring Boot conditions record outcomes into the report; custom `Condition` implementations may not supply messages the same way.
5. **The report belongs to a specific BeanFactory.** When a context has a parent, pay attention to child vs. parent context reports.
6. **The report is not a character-stable logging API.** Messages can change across Boot versions; avoid asserting entire sentences.
7. **`find(...)` can return null.** In tests, assert the report exists before reading its map.
8. **`get(...)` can create a new report.** Do not call `get(...)` and conclude Spring recorded conditions if no report existed beforehand.
9. **Context startup failures require separate handling.** `getSourceApplicationContext()` cannot return a source context that failed to start; inspect `context.getStartupFailure()` and the exception chain.
10. **`AutoConfigurations.of(...)` does not check JAR metadata.** It loads configuration classes directly; a separate consumer test is needed to check `AutoConfiguration.imports`.

## 12. Common mistakes when reading ConditionEvaluationReport

1. **Checking only `isFullMatch()` on the class source.** A bean method can be no-match even when the class matches.
2. **Reading the wrong source key.** A class and a method have two distinct keys.
3. **Calling `get(...)` without checking for an empty report.** The test might create a brand-new empty report with no condition outcomes.
4. **Calling `getSourceApplicationContext()` after startup failure.** The source context is unavailable in that state.
5. **Comparing full message strings verbatim.** Message wording can change across patch versions.
6. **Asserting only the report and not the bean.** Another bean might provide the same type or behavior.
7. **Asserting only the bean without reading the report.** The test cannot explain which condition kept the bean absent.
8. **Assuming no-match is always an error.** `@ConditionalOnMissingBean` returning no-match when a user bean exists is usually proper back-off.
9. **Assuming a source absent from the map was excluded.** There are many reasons a source was not evaluated.
10. **Reading the entire map in every test.** Easily creates assertions coupled to unrelated configurations; filter to the target source once known.
11. **Confusing condition match with successful bean creation.** Constructors/factory methods can fail after conditions match.
12. **Using logs instead of the report object in unit tests.** Parsing logs makes tests brittle and hard to isolate.

## 13. Workflow for writing tests that explain conditions

1. Identify the bean under test and its corresponding source: class or factory method.
2. Create an `ApplicationContextRunner` with the right auto-configuration.
3. Use `withPropertyValues(...)` to set up the property scenario under test.
4. Register foundational or replacement beans with `withBean(...)` if required by the scenario.
5. Inside the `run(...)` callback, assert bean presence/absence.
6. Retrieve the report from `context.getSourceApplicationContext().getBeanFactory()`.
7. Look up the source key in `getConditionAndOutcomesBySource()`.
8. Assert `isFullMatch()` and individual `ConditionOutcome.isMatch()` results.
9. Check a stable substring of the message to confirm the cause.
10. Print the report when helpful for CI diagnostics.
11. Run the tests and inspect Surefire reports when checking captured stdout.
12. Add a consumer test if discovery from JAR metadata must be verified.

## 14. Acceptance checklist

- [ ] Tests use `ApplicationContextRunner` for the target auto-configuration.
- [ ] Properties for each scenario are configured explicitly.
- [ ] Tests verify bean presence/absence.
- [ ] Report is retrieved from the right context's BeanFactory.
- [ ] Tests assert the report actually exists before reading it.
- [ ] Class source keys are distinguished from bean method source keys.
- [ ] Tests verify `ConditionAndOutcomes.isFullMatch()`.
- [ ] Tests inspect individual `ConditionOutcome.isMatch()` and `getMessage()`.
- [ ] Tests cover a property no-match scenario.
- [ ] Tests cover a property match scenario.
- [ ] Tests cover a user bean causing `@ConditionalOnMissingBean` to not match.
- [ ] Message assertions do not depend on full wording.
- [ ] Condition matches are not confused with bean creation or successful connectivity.
- [ ] Intentional no-match outcomes are not confused with errors.
- [ ] A separate consumer test exists if imports metadata in the JAR must be verified.

## 15. Self-check questions

**Question 1.** How do you retrieve ConditionEvaluationReport from ApplicationContextRunner?  
**Answer:** Retrieve the source context inside the callback, then call `ConditionEvaluationReport.find(sourceContext.getBeanFactory())`.

**Question 2.** What structure does `getConditionAndOutcomesBySource()` return?  
**Answer:** A map from source name (class or method) to `ConditionAndOutcomes`.

**Question 3.** What does `isFullMatch()` being false mean?  
**Answer:** At least one condition on that source did not match. Iterate over each outcome to see which condition and message explain the result.

**Question 4.** Can a class-level condition match while a bean method does not match?  
**Answer:** Yes. For example, the class property condition matches, yet `@ConditionalOnMissingBean` on the factory method does not match because the application already supplied the bean.

**Question 5.** Why should tests assert both beans and the report?  
**Answer:** Bean assertions confirm the final outcome; the report explains the conditions that produced it. Together they prevent one-sided false conclusions.

**Question 6.** Should you compare the entire `ConditionOutcome.getMessage()` against a fixed string?  
**Answer:** Usually no. Check the match status and a stable substring because wording can vary across Boot versions.

**Question 7.** How do `ConditionEvaluationReport.get(...)` and `find(...)` differ?  
**Answer:** `find(...)` searches for an existing report and may return null; `get(...)` returns an existing report or creates a new one.

**Question 8.** Does `AutoConfigurations.of(...)` prove the imports file in the JAR is right?  
**Answer:** No. It loads classes directly. A consumer or packaged integration test is needed to verify discovery metadata.

## 16. Official reference documentation

- [Spring Boot 3.3.13 Javadoc — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html).
- [Spring Boot 3.3.13 Javadoc — ConditionAndOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html).
- [Spring Boot 3.3.13 Javadoc — ConditionAndOutcomes](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html).
- [Spring Boot 3.3.13 Javadoc — ConditionOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html).
- [Spring Boot 3.3.13 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).
- [Spring Boot 3.3 — Conditions Evaluation Report Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)