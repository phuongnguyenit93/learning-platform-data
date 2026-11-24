# ConditionOutcome, Match Messages, and No-Match Messages

## 1. Goal: A Condition Needs Both an Outcome and a Reason

When Spring Boot processes auto-configuration, each condition answers one question: is the configuration or bean definition allowed to join the current context? A boolean value indicates **match or no-match**. When debugging, knowing only true/false is often not enough: we also need to know **why** the condition produced that result.

Spring Boot represents the answer with `ConditionOutcome`:

- `isMatch()` indicates whether the condition matched (`true`) or did not match (`false`).
- `getMessage()` provides the accompanying diagnostic message; it may be `null` if the outcome has no message.
- `match(...)` and `noMatch(...)` create the respective outcomes; you can pass a string or a `ConditionMessage` to explain the result.

Spring Boot collects outcomes into `ConditionEvaluationReport`. The report groups them by **source** (configuration class or `@Bean` method). Each `ConditionAndOutcome` entry pairs a `Condition` implementation with its `ConditionOutcome`; the `ConditionAndOutcomes` group indicates whether all conditions on that source matched together.

This lesson progresses from the smallest API to the application-wide report, including how to write custom conditions with messages, how to read outcomes in tests, how to distinguish Actuator's positive/negative matches, and a runnable Java 17/JUnit 5 project with Spring Boot 3.3.x.

## 2. What Is ConditionOutcome?

`ConditionOutcome` is a **result value**, not an annotation, and it does not itself decide when Spring runs the condition. A condition is invoked by Spring via the `Condition.matches(...)` contract. Spring Boot's internal conditions usually extend `SpringBootCondition`; this base class requires implementations to provide `getMatchOutcome(...)` instead of returning a plain boolean, then handles logging and recording the outcome through Boot's mechanism.

Model:

```text
Spring evaluates a Condition
          |
          v
SpringBootCondition.getMatchOutcome(...)
          |
          v
      ConditionOutcome
       /          \
  isMatch=true  isMatch=false
       |             |
       v             v
source allowed   source rejected
  to proceed      by condition
       \             /
        \           /
         ConditionEvaluationReport
                   |
                   v
        log / debug / Actuator / test
```

An outcome has two semantic components:

| Component | API | Question Answered |
| --- | --- | --- |
| Status | `isMatch()` | Did the condition match? |
| Reason | `getMessage()` / `getConditionMessage()` | What led to this result? |

Messages are data meant for human readers. They can change when implementations, versions, bean names, or inputs change. Therefore, control logic should rely on `isMatch()`; logs/reports use messages for explanation. Avoid parsing messages with regex to drive business logic.

### 2.1. Common Factory Methods

```java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;

ConditionOutcome positive =
        ConditionOutcome.match("Found bean 'catalogService'");

ConditionOutcome negative =
        ConditionOutcome.noMatch("No CatalogService bean was found");

ConditionOutcome positiveWithoutMessage = ConditionOutcome.match();
ConditionOutcome negativeWithoutMessage = ConditionOutcome.noMatch();
```

This is an illustrative Java snippet that compiles inside a Java 17 class with an appropriate method. The first two outcomes include messages; the last two carry only a boolean and the message may be `null`. When writing custom conditions for a library, produce helpful messages instead of using the no-message factories.

`ConditionOutcome` also has overloads accepting `ConditionMessage`. `ConditionMessage` is an API that helps construct messages with a consistent structure and style; it is useful for conditions with multiple result kinds or multiple discovered beans. When a single clear sentence suffices, the `String` overload is readable and appropriate.

### 2.2. Match and No-Match Do Not Mean Startup Success or Failure

A **no-match** condition usually just means Spring skipped a configuration or bean definition. This can be the right behavior, for example:

- `@ConditionalOnMissingBean` did not match because the user supplied a replacement bean.
- `@ConditionalOnClass` did not match because an optional dependency is absent.
- `@ConditionalOnProperty` did not match because the feature is turned off.

A **match** condition only means the source passed that condition. The configuration can still be skipped because another condition did not match, or the context can fail later due to binding, dependency injection, or bean instantiation.

Therefore:

- `match` does not guarantee the entire application will start successfully.
- `no-match` is not automatically an error.
- Looking at a single message is not enough to conclude the whole source was registered; you must check every condition belonging to that source.

## 3. Writing a Custom Condition with Messages Using SpringBootCondition

When you need a custom rule, extend `SpringBootCondition`. The API requires implementing `getMatchOutcome(ConditionContext, AnnotatedTypeMetadata)` and returning a `ConditionOutcome`.

Example: a configuration is enabled only when the container already has a bean of type `CatalogService`.

```java
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public class CatalogPresentCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String[] beanNames = context.getBeanFactory()
                .getBeanNamesForType(CatalogService.class, true, false);

        if (beanNames.length == 0) {
            return ConditionOutcome.noMatch(
                    "No CatalogService bean was visible at condition evaluation time");
        }

        return ConditionOutcome.match(
                "Found CatalogService bean(s): "
                        + String.join(", ", beanNames));
    }
}
```

This is an example condition; `CatalogService` is an application/library type and must be defined where used. The parameters of `getBeanNamesForType` in the example mean:

- `includeNonSingletons=true`: allows considering non-singleton beans as well.
- `allowEagerInit=false`: does not eagerly initialize `FactoryBean`s or beans just to infer types during this lookup; detection relies on metadata the container currently holds.
- An empty array leads to `noMatch` with a specific reason; if one or more bean names are found, it returns `match` with the list of names.

This condition is only an illustration of how to produce outcomes. If the goal is simply a standard bean check, prefer the built-in `@ConditionalOnBean` or `@ConditionalOnMissingBean` annotations because they express intent clearly and handle Boot's specific rules. Only create a custom condition when built-in annotations cannot sufficiently express the policy.

### 3.1. Why Extend SpringBootCondition?

`SpringBootCondition` is the base class for conditions integrated with Spring Boot's logging and condition reporting mechanism. It implements the final `matches(...)`, calls `getMatchOutcome(...)`, and records the outcome under the source being processed.

If you implement the Spring Framework `Condition` interface directly, you only return a boolean from `matches(...)`. That approach suits pure Spring conditions, but does not automatically get the same message/report experience as `SpringBootCondition`. When the goal is a condition with reasons in Spring Boot diagnostics, extending `SpringBootCondition` is the natural choice.

Do not override `matches(...)` on `SpringBootCondition`; that method is `final`. Put your logic in `getMatchOutcome(...)` and return the appropriate outcome.

### 3.2. Writing Actionable Messages

A good message should tell the operator what to check next:

| Vague Message | More Helpful Message |
| --- | --- |
| `Condition failed` | `No CatalogService bean was visible when CatalogDiagnosticConfiguration was evaluated` |
| `Feature disabled` | `demo.search.enabled was false; SearchClient configuration was skipped` |
| `Missing dependency` | `Required class com.example.sdk.SearchClient was not found on the runtime classpath` |
| `Invalid config` | `Property demo.search.endpoint must be an absolute HTTPS URI` |

Messages should be concise, state the exact failing input/condition, and hint at the remedy. Never write tokens, passwords, access keys, request bodies, personal data, or secret configurations into messages. The condition report is often written to logs or management endpoints; treat it as operational data readable by anyone with access.

## 4. How ConditionEvaluationReport Organizes Outcomes

`ConditionEvaluationReport` is Spring Boot's report that records condition evaluation details for logging and diagnostics. Key API:

| API | Meaning |
| --- | --- |
| `ConditionEvaluationReport.get(beanFactory)` | Retrieves the report for `ConfigurableListableBeanFactory`; if no report exists yet, the API may create a new one |
| `ConditionEvaluationReport.find(beanFactory)` | Attempts to find an existing report; may return `null` |
| `getConditionAndOutcomesBySource()` | Map of source → group of condition/outcome pairs |
| `getExclusions()` | List of excluded auto-configurations |
| `getUnconditionalClasses()` | Configuration classes evaluated that carried no conditions |
| `getParent()` | Parent BeanFactory's report, if any |

The source map can contain keys that are fully qualified class names or bean method names in the form:

```text
com.example.CatalogAutoConfiguration
com.example.CatalogAutoConfiguration#catalogService
com.example.CatalogAutoConfiguration#catalogDiagnostic
```

The `#` separates class and method. Do not guess names from runtime bean names: the source usually reflects **the evaluated `@Bean` method**, whereas the bean name can be customized with `@Bean("customName")`. For nested configurations, use `SomeConfiguration.class.getName()` to produce the exact class name, including the `$` character.

### 4.1. ConditionAndOutcome: One Condition and Outcome Pair

`ConditionEvaluationReport.ConditionAndOutcome` provides two accessors:

- `getCondition()` returns the `Condition` implementation that was evaluated.
- `getOutcome()` returns the corresponding `ConditionOutcome`.

This pair helps distinguish multiple condition types participating in one source. For example, a bean method can have both a property condition and a bean condition; when debugging, you need to know **which condition** produced the message you are reading.

### 4.2. ConditionAndOutcomes: All Conditions of One Source

`ConditionEvaluationReport.ConditionAndOutcomes` is an `Iterable` collection of `ConditionAndOutcome`. It provides `isFullMatch()`:

- `true` when **all** outcomes in the group match.
- `false` if at least one outcome is a no-match.

Suppose a single bean method is subject to three conditions:

| Condition | Outcome |
| --- | --- |
| SDK class present | match |
| Feature property enabled | match |
| Foundation bean already exists | no-match |

Each condition has its own message, yet the source's `isFullMatch()` is `false`. Therefore, never see a single “matched” message in the report and conclude the bean method was registered; read the whole group and identify which no-match outcome blocked the source.

### 4.3. Positive and Negative Matches in the Report

The Actuator Conditions Evaluation Report organizes data by application context:

- `contexts`: contexts indexed by context id.
- `positiveMatches`: sources whose recorded conditions all matched; each source has a list of conditions and messages.
- `negativeMatches`: rejected sources; each source has `notMatched` (unmatched conditions) and `matched` (other conditions that still matched).
- `unconditionalClasses`: list of configuration classes without conditions.
- `parentId`: id of the parent context, if any.

A common misreading: inside `negativeMatches`, the `matched` array can still contain passing conditions. The source is categorized as negative because **at least one condition did not match**, not because every condition failed.

Abbreviated structural example:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.CatalogAutoConfiguration#catalogService": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class"
          }
        ]
      },
      "negativeMatches": {
        "com.example.SearchAutoConfiguration#searchClient": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.search.enabled was false"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required SDK class was present"
            }
          ]
        }
      },
      "unconditionalClasses": []
    }
  }
}
```

This is illustrative JSON for reading the structure, not fixed output from an application. Actual messages are produced by conditions; source names and condition counts depend on the running configuration.

## 5. Reading the Report Directly in Code and Tests

After the context has refreshed, you can obtain the report and iterate by source:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> bySource =
        report.getConditionAndOutcomesBySource();

bySource.forEach((source, outcomes) -> {
    System.out.println(source + " -> fullMatch=" + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        Condition condition = item.getCondition();
        ConditionOutcome outcome = item.getOutcome();

        System.out.println("  condition="
                + condition.getClass().getSimpleName());
        System.out.println("  match=" + outcome.isMatch());
        System.out.println("  message=" + outcome.getMessage());
    }
});
```

This is an illustrative snippet inside a test callback or diagnostic component with access to `ConfigurableListableBeanFactory context`. Required imports:

```java
import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.context.annotation.Condition;
```

If `getMessage()` returns `null`, printing `null` is normal; do not assume every condition provides a message. If you only want to inspect one configuration, filter by source class prefix instead of printing the entire report.

When you want to avoid creating a new report just from checking, use `ConditionEvaluationReport.find(beanFactory)` and check for null. In tests where Spring Boot conditions have already run, `get(...)` is usually convenient because the report has already been recorded.

### 5.1. Filtering a Specific Bean Method

```java
String source = CatalogAutoConfiguration.class.getName()
        + "#catalogDiagnostic";

ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

ConditionEvaluationReport.ConditionAndOutcomes outcomes =
        report.getConditionAndOutcomesBySource().get(source);

if (outcomes != null) {
    System.out.println("fullMatch=" + outcomes.isFullMatch());
    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(item.getCondition().getClass().getName()
                + " => " + item.getOutcome().isMatch()
                + " : " + item.getOutcome().getMessage());
    }
}
```

The name `catalogDiagnostic` must match the exact `@Bean` method name in your example. If the key returns `null`, check:

1. Was the source class actually selected and evaluated?
2. Is the condition placed at the class level or method level? If at the class level, the key may just be the class name.
3. Are you reading the report of the right BeanFactory/context?
4. Was the configuration excluded or filtered out before the method condition was evaluated?
5. Does the custom condition extend `SpringBootCondition` so that messages are recorded in Boot's report?

Do not manually insert entries into the report to “fix” a missing key; find out why the configuration was not evaluated.

## 6. What Do Built-In Condition Messages Typically Say?

Spring Boot has familiar internal conditions. The report typically displays implementation names such as `OnClassCondition`, `OnBeanCondition`, `OnPropertyCondition`, or `OnWebApplicationCondition`.

| Condition | Example Match Message Meaning | Example No-Match Message Meaning |
| --- | --- | --- |
| `@ConditionalOnClass` | Required classes found on runtime classpath | Required class not found |
| `@ConditionalOnBean` | Found bean matching required type/name/annotation | No bean matching criteria found |
| `@ConditionalOnMissingBean` | No competing bean found, so default bean can register | Bean already exists, so default bean backs off |
| `@ConditionalOnProperty` | Property has a value matching `havingValue` | Property missing or value does not match |
| `@ConditionalOnWebApplication` | Current context matches required web type | Not a web application or wrong Servlet/Reactive type |

The phrases in the table are paraphrases, not literal messages to copy into assertions. Actual messages may contain class names, bean types, property names, search strategies, contexts, or version details.

For example, a positive message for `@ConditionalOnMissingBean` may state that no bean of the required type was found; a negative message may state that a specific bean already exists. Read according to the annotation's semantics:

- For `@ConditionalOnMissingBean`, **match** usually means “safe to register default”.
- For `@ConditionalOnBean`, **match** means “found required dependency”.
- The same phrase “did not find bean” can be good news for a MissingBean condition yet a failure reason for an OnBean condition. Always read the condition name before the message.

## 7. Hands-On: Generating a Report with Both Match and No-Match

The project below creates three cases on the same auto-configuration style:

1. Source bean present: `@ConditionalOnBean` match, `@ConditionalOnMissingBean` no-match, custom condition match.
2. Source bean absent: `@ConditionalOnBean` no-match, `@ConditionalOnMissingBean` match, custom condition no-match.
3. User provides source bean: conditions see the user bean and produce the corresponding outcomes.

The test suite verifies both **final beans** and **`ConditionOutcome` in the report**, rather than looking at only one side.

### 7.1. Project Structure

```text
condition-outcome-lab/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/ConditionOutcomeEvidenceTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'condition-outcome-lab'
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

Requires JDK 17+ and a compatible Gradle version. The test starter provides JUnit 5, AssertJ, Spring Boot test context runner, and the dependencies needed for the example.

### 7.2. Complete Java File

Create `src/test/java/demo/ConditionOutcomeEvidenceTest.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionOutcomeEvidenceTest {

    record CatalogService(String origin) {}

    record CatalogDependent(String description) {}

    record CatalogDiagnostic(String description) {}

    @AutoConfiguration
    static class CatalogSourceAutoConfiguration {

        @Bean
        CatalogService sourceCatalog() {
            return new CatalogService("auto-configuration");
        }
    }

    @AutoConfiguration(after = CatalogSourceAutoConfiguration.class)
    static class CatalogConditionAutoConfiguration {

        @Bean
        @ConditionalOnBean(CatalogService.class)
        CatalogDependent catalogDependent() {
            return new CatalogDependent("catalog is available");
        }

        @Bean
        @ConditionalOnMissingBean(CatalogService.class)
        CatalogService fallbackCatalog() {
            return new CatalogService("fallback");
        }

        @Bean
        @Conditional(CatalogPresentCondition.class)
        CatalogDiagnostic catalogDiagnostic() {
            return new CatalogDiagnostic("custom condition matched");
        }
    }

    public static class CatalogPresentCondition extends SpringBootCondition {

        @Override
        public ConditionOutcome getMatchOutcome(
                ConditionContext context,
                AnnotatedTypeMetadata metadata) {

            String[] names = context.getBeanFactory()
                    .getBeanNamesForType(CatalogService.class, true, false);

            if (names.length == 0) {
                return ConditionOutcome.noMatch(
                        "No CatalogService bean was visible at condition evaluation time");
            }

            return ConditionOutcome.match(
                    "Found CatalogService bean(s): "
                            + String.join(", ", names));
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCatalogConfiguration {

        @Bean
        CatalogService userCatalog() {
            return new CatalogService("user");
        }
    }

    private ApplicationContextRunner runner(Class<?>... autoConfigurations) {
        return new ApplicationContextRunner()
                .withConfiguration(AutoConfigurations.of(autoConfigurations));
    }

    private ConditionEvaluationReport.ConditionAndOutcome outcomeFor(
            AssertableApplicationContext context,
            String beanMethod) {

        String source = CatalogConditionAutoConfiguration.class.getName()
                + "#" + beanMethod;

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        var group = report.getConditionAndOutcomesBySource().get(source);
        assertThat(group).as("Report source " + source).isNotNull();

        List<ConditionEvaluationReport.ConditionAndOutcome> entries =
                new ArrayList<>();
        group.forEach(entries::add);

        assertThat(entries).as("Expected one condition for " + source)
                .hasSize(1);

        return entries.get(0);
    }

    @Test
    void sourceBeanProducesMatchAndMissingBeanNoMatch() {
        // Intentionally pass consumer first; 'after' metadata still orders source first.
        runner(CatalogConditionAutoConfiguration.class,
                CatalogSourceAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("sourceCatalog");
                    assertThat(context).hasBean("catalogDependent");
                    assertThat(context).doesNotHaveBean("fallbackCatalog");
                    assertThat(context).hasBean("catalogDiagnostic");

                    var dependent = outcomeFor(context, "catalogDependent");
                    assertThat(dependent.getOutcome().isMatch()).isTrue();
                    assertThat(dependent.getOutcome().getMessage()).isNotBlank();

                    var fallback = outcomeFor(context, "fallbackCatalog");
                    assertThat(fallback.getOutcome().isMatch()).isFalse();
                    assertThat(fallback.getOutcome().getMessage()).isNotBlank();

                    var custom = outcomeFor(context, "catalogDiagnostic");
                    assertThat(custom.getCondition())
                            .isInstanceOf(CatalogPresentCondition.class);
                    assertThat(custom.getOutcome().isMatch()).isTrue();
                    assertThat(custom.getOutcome().getMessage())
                            .contains("sourceCatalog");
                });
    }

    @Test
    void absentSourceProducesNoMatchAndFallbackMatch() {
        runner(CatalogConditionAutoConfiguration.class)
                .run(context -> {
                    assertThat(context).doesNotHaveBean("sourceCatalog");
                    assertThat(context).doesNotHaveBean("catalogDependent");
                    assertThat(context).hasBean("fallbackCatalog");
                    assertThat(context).doesNotHaveBean("catalogDiagnostic");

                    var dependent = outcomeFor(context, "catalogDependent");
                    assertThat(dependent.getOutcome().isMatch()).isFalse();
                    assertThat(dependent.getOutcome().getMessage()).isNotBlank();

                    var fallback = outcomeFor(context, "fallbackCatalog");
                    assertThat(fallback.getOutcome().isMatch()).isTrue();
                    assertThat(fallback.getOutcome().getMessage()).isNotBlank();

                    var custom = outcomeFor(context, "catalogDiagnostic");
                    assertThat(custom.getOutcome().isMatch()).isFalse();
                    assertThat(custom.getOutcome().getMessage())
                            .contains("No CatalogService bean");
                });
    }

    @Test
    void userBeanIsVisibleToAutoConfigurationConditions() {
        runner(CatalogConditionAutoConfiguration.class)
                .withUserConfiguration(UserCatalogConfiguration.class)
                .run(context -> {
                    assertThat(context).hasBean("userCatalog");
                    assertThat(context).hasBean("catalogDependent");
                    assertThat(context).doesNotHaveBean("fallbackCatalog");
                    assertThat(context).hasBean("catalogDiagnostic");
                    assertThat(context.getBean(CatalogService.class).origin())
                            .isEqualTo("user");

                    assertThat(outcomeFor(context, "catalogDependent")
                            .getOutcome().isMatch()).isTrue();
                    assertThat(outcomeFor(context, "fallbackCatalog")
                            .getOutcome().isMatch()).isFalse();
                    assertThat(outcomeFor(context, "catalogDiagnostic")
                            .getOutcome().getMessage()).contains("userCatalog");
                });
    }
}
```

### 7.3. Running and Understanding the Output

Run inside the project directory:

```bash
gradle test --tests demo.ConditionOutcomeEvidenceTest
```

If using the Gradle Wrapper on Linux/macOS:

```bash
./gradlew test --tests demo.ConditionOutcomeEvidenceTest
```

On Windows:

```powershell
.\gradlew.bat test --tests demo.ConditionOutcomeEvidenceTest
```

The expected result is **3 tests passed**. This is the expected result of the example; actual Gradle logs also depend on version, test logging, and environment. This lesson does not assume a fixed stdout.

Result reading matrix:

| Scenario | Final Beans | `catalogDependent` outcome | `fallbackCatalog` outcome | Custom outcome |
| --- | --- | --- | --- | --- |
| Source auto-config present | Source + dependent + diagnostic | match | no-match | match, message contains `sourceCatalog` |
| Source absent | Fallback | no-match | match | no-match, message states not found |
| User source present | User + dependent + diagnostic | match | no-match | match, message contains `userCatalog` |

Two important meanings:

- `@ConditionalOnMissingBean` matching when the source is absent means the fallback is allowed to register. It does not mean “found a bean”.
- In the test with the source present, `fallbackCatalog` does not exist and the MissingBean condition outcome is no-match. That is correct behavior, not a bug.

The test suite intentionally reverses the argument order passed to `AutoConfigurations.of` in the first test. The `after` relationship in metadata is the ordering contract; do not use input array order to conclude which condition runs first or last.

## 8. Viewing the Report in a Running Application

### 8.1. Enabling Debug Logs

The fastest way when investigating a Spring Boot application is to run with:

```bash
java -jar app.jar --debug
```

Or configure `debug=true`. Spring Boot will write the condition evaluation report to logs during startup. Locate the class/method source and read the condition name along with its message. Do not confuse these logs with instance initialization logs: the condition report covers **configuration decisions**, not the entire lifecycle timeline.

### 8.2. Using the Actuator Endpoint /actuator/conditions

If the application has Spring Boot Actuator, the `conditions` endpoint can return the report in JSON format. Example exposure configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: conditions,health,info
```

After the application starts, send a request:

```bash
curl http://localhost:8080/actuator/conditions
```

The endpoint may not be exposed or may be protected by a security policy; configure access appropriately for the environment. Do not open diagnostic endpoints to the public Internet just for debugging convenience. The report contains class names, properties, and internal configuration details; custom messages must never contain secrets.

### 8.3. Reading the Right JSON Section

When a source appears in `positiveMatches`, every condition recorded for that source matched. When a source appears in `negativeMatches`:

- `notMatched` shows which conditions did not match.
- `matched` shows other conditions on the source that still matched.
- The source is classified as negative because at least one condition did not match.

If a source does not appear at all, that does not prove the condition was no-match. The class may not have been selected as a candidate, may have been excluded, may not have been imported, or may belong to a different context than the report being viewed. Check `contexts`, `parentId`, `unconditionalClasses`, and `getExclusions()` when needed.

## 9. Analyzing Messages: Read by Condition, Not Just by Wording

Some common messages and how to interpret them:

| Condition in Report | Message (Illustrative Meaning) | Interpretation |
| --- | --- | --- |
| `OnClassCondition` | Required class was found | Dependency is on runtime classpath; class condition matched |
| `OnClassCondition` | Did not find required class | Optional dependency absent; source rejected |
| `OnBeanCondition` + `@ConditionalOnBean` | Found bean 'catalogService' | Found bean matching criteria |
| `OnBeanCondition` + `@ConditionalOnBean` | Did not find any beans | Dependency bean not yet present / insufficient metadata |
| `OnBeanCondition` + `@ConditionalOnMissingBean` | Did not find any beans | No competing bean; default can register |
| `OnBeanCondition` + `@ConditionalOnMissingBean` | Found bean 'catalogService' | Bean already exists; default must back off |
| `OnPropertyCondition` | Property matched | Property value satisfies configuration |
| `OnPropertyCondition` | Did not find property / did not match | Property missing or wrong value |
| `OnWebApplicationCondition` | Not a servlet web application | Context does not match required web type |

The exact same phrase “did not find any beans” can be a **match reason** for `@ConditionalOnMissingBean` and a **no-match reason** for `@ConditionalOnBean`. The condition name determines the meaning of the message.

When reading an actual report, note four elements:

1. **Source:** which class or method is being evaluated?
2. **Condition:** which annotation/implementation produced the outcome?
3. **Outcome:** match or no-match?
4. **Message:** which bean, class, property, or search strategy explains the result?

If the message only says “no beans found”, verify the requested type, bean name, parent context/search strategy, and factory method return type. Do not jump to ordering conclusions from a single message line.

## 10. Common Pitfalls and Limitations

### 10.1. Messages Can Be Null

`ConditionOutcome.getMessage()` can return `null`. When logging manually, handle null safely:

```java
String message = outcome.getMessage();
System.out.println(message == null ? "(no diagnostic message)" : message);
```

Do not call `message.contains(...)` without checking for null first.

### 10.2. One Source Can Have Multiple Outcomes

A bean method can be subject to multiple conditions. `isFullMatch()` is only true when all outcomes match. When the report places a source in negative matches, read both `notMatched` and `matched` to find the blocking condition.

### 10.3. The Report Is Not an Event Log

`ConditionEvaluationReport` does not record when constructors ran, which bean was instantiated first, method invocation counts, or request order. It is a **condition evaluation** report. To trace lifecycle events, use initialization logs, `ApplicationStartup`, or appropriate instrumentation; do not infer an instance timeline from JSON ordering.

### 10.4. Not Every Condition Automatically Has a Message in Boot's Report

A custom class directly implementing Spring's `Condition` can return a boolean without going through `SpringBootCondition`'s recording mechanism. If you want messages logged/reported through Boot's mechanism, extend `SpringBootCondition` and return `ConditionOutcome`. Do not inject fake messages into the report manually.

### 10.5. Source Missing from the Map

If a key is not found, do not immediately conclude the outcome was false. Possible reasons:

- The configuration was excluded.
- The configuration was not imported/discovered.
- A class-level condition rejected it before method conditions were evaluated.
- You are inspecting the report of another context (parent/child or management context).
- The source key was recorded at the class rather than the method.
- You used the bean name instead of the method name in the source key.

### 10.6. Messages Are Not a Stable API to Parse

Messages are meant for humans and can change across patch/minor releases. In tests, prefer asserting `isMatch()`, bean presence/absence, and condition type. Only assert part of a message from a custom condition you own when that message is a diagnostic contract you actively maintain. For Boot's internal messages, read them for debugging and avoid locking tests to exact full sentences.

### 10.7. Reading the Wrong Parent/Child Context Report

Each BeanFactory has its own report; `ConditionEvaluationReport` provides `getParent()` to inspect the parent report. In applications with a separate management context or context hierarchy, identify the right context id in Actuator. Beans in the parent may be visible to conditions depending on search strategy, yet the child's report remains grouped under its own context.

## 11. Step-by-Step Diagnostic Workflow

When a bean does not appear as expected, follow this sequence:

1. **Confirm the symptom via beans:** inspect bean names, types, counts, and the actual injected bean. Use `ApplicationContextRunner` to build a minimal context if needed.
2. **Locate the source:** use the full class name and `#beanMethod` in `getConditionAndOutcomesBySource()`.
3. **Read the whole group:** check `isFullMatch()` and iterate each `ConditionAndOutcome`; do not stop at the first condition.
4. **Classify the condition:** classpath, property, bean presence, web application, resource, expression, or custom condition?
5. **Read the message:** record the type/name/property and concrete reason; ensure the message is not null.
6. **Cross-check bean definition/type metadata:** for `@ConditionalOnBean`, verify whether the source definition was already processed, whether the `@Bean` return type is specific enough, and whether a `FactoryBean` exposes its object type.
7. **Check context and ordering:** was the auto-configuration imported, excluded, or ordered properly? In which context was the condition evaluated?
8. **Reproduce with tests:** create two contrasting contexts (with/without bean or with/without property), asserting both beans and outcomes.
9. **Fix at the right layer:** classpath dependency, property, type metadata, auto-config ordering, user override, or custom condition.
10. **Keep a regression test:** assert bean state and outcomes; do not just check that the application starts.

### 11.1. Quick Decision Table

| Symptom | Where to Check First | Common Fix |
| --- | --- | --- |
| Default bean still created even though user bean exists | `@ConditionalOnMissingBean` outcome and user bean type | Check return type, search strategy, and auto-config ordering |
| Dependent bean does not appear | `@ConditionalOnBean` outcome | Ensure source definition was already processed and type is detectable |
| Configuration rejected even though dependency is in build file | `OnClassCondition` and runtime classpath | Fix dependency scope / runtime classpath |
| Feature not enabled even though property is declared | `OnPropertyCondition` | Check prefix, key, value, `havingValue`, and `matchIfMissing` |
| Both matched and notMatched in negative report | All outcomes of the source | Identify the no-match condition blocking the source |
| Report lacks the target source | Exclusions, candidates, context id, and class-level condition | Check discovery/import and the right BeanFactory |
| Custom condition has no message in report | Does the condition class extend `SpringBootCondition`? | Override `getMatchOutcome` and return `ConditionOutcome` |

## 12. Checklist for Writing Custom Conditions

- [ ] Condition only reads necessary metadata/environment/registry; it does not instantiate full dependencies just to decide.
- [ ] Extend `SpringBootCondition` when Boot logging and condition reporting are needed.
- [ ] Implement `getMatchOutcome(...)`; do not override `matches(...)`.
- [ ] Return `ConditionOutcome.match(...)` or `ConditionOutcome.noMatch(...)` matching the outcome.
- [ ] Message explains the inspected data and reason; contains no secrets.
- [ ] Handle cases where BeanFactory/metadata is missing as expected.
- [ ] Do not use messages to drive logic; use `isMatch()`.
- [ ] Test both match and no-match with isolated test contexts.
- [ ] Read the report by source class/method and inspect all outcomes.
- [ ] Do not assert exact verbatim internal Spring Boot messages in long-lived tests.
- [ ] Check the right context if parent/child or management contexts exist.
- [ ] Distinguish legitimate no-match conditions from actual startup errors.

**Remember:** `ConditionOutcome` answers two things: **match or no-match**, and **why**. `ConditionEvaluationReport` collects those outcomes by source so operators and developers can trace configuration decisions. When debugging, read the condition name first, the status next, and only then interpret the message; afterwards, cross-check against actual beans in the context. This avoids mistaking an intentional no-match for an auto-configuration bug.

## Official Documentation

- Spring Boot 3.3 API — `ConditionOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.3 API — `SpringBootCondition`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 API — `ConditionEvaluationReport.ConditionAndOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html
- Spring Boot 3.3 API — `ConditionMessage`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- Spring Boot 3.3 Actuator — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
