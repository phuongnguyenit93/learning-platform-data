# Reading Positive Matches, Negative Matches, Exclusions, and Unconditional Classes in the Condition Evaluation Report

## 1. Purpose of the Condition Report

Spring Boot may find an auto-configuration on the classpath yet **not register a bean** because one or more conditions are not satisfied. Conversely, an auto-configuration may be applied and create a default bean because no replacement bean exists. When an application starts differently from what you expected, just looking at dependencies or bean names is often not enough to know the cause.

The **Condition Evaluation Report** records the evaluation results of conditions on configurations and auto-configurations. The report helps answer:

- Which auto-configuration or bean method **matched** all conditions?
- Which source **did not match**, and which condition caused it to fail?
- Which auto-configurations were **excluded** from evaluation?
- Which auto-configurations were considered but had **no applicable conditions** at the class level?

These four groups are related but not synonymous. An excluded class is not a negative match; an unconditional class also does not mean every bean method inside it is guaranteed to be created.

## 2. Four Information Groups to Distinguish

| Group | Meaning | Where to Read |
|---|---|---|
| **Positive matches** | A source (configuration class or bean method) whose conditions were evaluated and all matched | Actuator `/actuator/conditions`; `getConditionAndOutcomesBySource()` |
| **Negative matches** | A source with at least one condition that did not match; the report shows the failed condition(s) and the matched ones | Actuator `/actuator/conditions`; `getConditionAndOutcomesBySource()` |
| **Exclusions** | Names of auto-configurations excluded from condition evaluation | `ConditionEvaluationReport.getExclusions()` |
| **Unconditional classes** | Names of auto-configurations that were evaluated but had no applicable conditions on the class itself | `ConditionEvaluationReport.getUnconditionalClasses()`; Actuator `unconditionalClasses` |

The report groups results by **source**: either the fully qualified name of a configuration class or a method name in the form `com.example.ReportAutoConfiguration#reportFeature`. Do not search only by bean name: the source in the report is the class/method that declared the condition.

Mental model example:

```text
ReportedAutoConfiguration#reportFeature
  @ConditionalOnProperty(enabled=true)       MATCH
  @ConditionalOnBean(ReportGateway.class)    NO MATCH
  => NEGATIVE MATCH: bean method is not registered

ExcludedAutoConfiguration
  added to the exclusion list
  => EXCLUSION: class conditions are not evaluated

UnconditionalAutoConfiguration
  no class-level conditions
  => UNCONDITIONAL CLASS
```

This is an illustrative diagram, not actual log output.

## 3. Positive Matches: Why Was a Configuration Accepted?

A positive match means all conditions applied to the source passed. For example:

```java
@AutoConfiguration
public class ReportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnBean(ReportGateway.class)
    ReportFeature reportFeature() {
        return new ReportFeature();
    }
}
```

This is an illustrative auto-configuration snippet; `ReportGateway` and `ReportFeature` are hypothetical application types.

If the context has `demo.report.enabled=true` and a `ReportGateway` bean already exists, the `reportFeature` method can match. In Actuator, the corresponding source appears under `positiveMatches`, along with condition names and messages explaining why each condition passed.

A positive match **does not prove the entire application ran successfully**. It indicates that the conditions allow registering the source. The bean can still fail during initialization due to constructors, dependencies, external connections, or runtime logic.

## 4. Negative Matches: Finding the Exact Condition That Filtered Out a Configuration

Keep the example above, but suppose the application does not have `ReportGateway`. The property condition matched, while the bean condition did not match. The `reportFeature` method is not registered.

In Actuator, `negativeMatches` is displayed by source. Each source typically has two lists:

- `notMatched`: conditions that **did not pass**; this is the first place to read to find the root cause.
- `matched`: conditions that passed; these help confirm which parts of the configuration are already right.

Abbreviated JSON structural example:

```json
{
  "contexts": {
    "application": {
      "negativeMatches": {
        "com.example.ReportAutoConfiguration#reportFeature": {
          "notMatched": [
            {
              "condition": "OnBeanCondition",
              "message": "ReportGateway bean not found"
            }
          ],
          "matched": [
            {
              "condition": "OnPropertyCondition",
              "message": "demo.report.enabled matched"
            }
          ]
        }
      }
    }
  }
}
```

The `message` strings in the example above are written to illustrate meaning; actual messages generated by Spring Boot conditions may vary by version or context.

**Systematic way to read:**

1. Find the source in `negativeMatches`.
2. Read each item in `notMatched` to identify the failed condition.
3. Read `matched` to see whether the other conditions passed.
4. From the condition name, identify the check category: classpath, property, bean, web application, resource, Java version, or custom condition.
5. Inspect actual data at the time the context was created: runtime dependencies, Environment values, bean definitions, and auto-configuration ordering.
6. After fixing, restart or run a new test context to observe the updated outcome.

### One Source with Multiple Conditions

Condition annotations on the same class or bean method typically combine with **AND** logic: every condition must match for the source to be accepted. A single false condition is enough to make the source a negative match.

With nested conditions such as `AnyNestedCondition`, `AllNestedConditions`, or `NoneNestedConditions`, the message may contain multiple nested layers and intermediate outcomes. Read the entire message instead of looking only at the outer `OnPropertyCondition` or `OnBeanCondition` name.

### A Negative Match Is Not Always a Bug

For example, `@ConditionalOnMissingBean` not matching because the application already supplied the corresponding bean is **intentional back-off** behavior. A web auto-configuration not matching in a CLI application can also be completely normal. Compare against the intended design before making changes.

## 5. Exclusions: Excluded Classes Are Not Evaluated as Negative Matches

An auto-configuration can be excluded via:

- `@SpringBootApplication(exclude = ...)` or `excludeName = ...`.
- `@EnableAutoConfiguration(exclude = ...)` or `excludeName = ...`.
- The `spring.autoconfigure.exclude` property in the Environment.

Example:

```java
@SpringBootApplication(
    excludeName =
        "org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration"
)
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

The name in `excludeName` must be the **fully qualified class name of the auto-configuration**. With `exclude`, you can use a class literal if the type is on the compile classpath. With the property, you can declare one or more names in an appropriate list format.

Important distinction:

- **Negative match:** the class or method had its conditions evaluated, and at least one condition failed.
- **Exclusion:** the auto-configuration was removed from the list to be evaluated. Therefore, there is no condition pass/fail result for that candidate itself.
- **Unconditional:** the class was evaluated, but had no class-level conditions applied.

In the API, `ConditionEvaluationReport.getExclusions()` returns the list of excluded class names. The Javadoc describes these as classes excluded from condition evaluation.

An easy-to-miss detail: the public JSON schema of Actuator `/actuator/conditions` describes `positiveMatches`, `negativeMatches`, and `unconditionalClasses`, but **does not list an `exclusions` field**. If you need to read the exclusions list directly, use `ConditionEvaluationReport.getExclusions()` in code or read the Condition Evaluation Report written to logs. Do not conclude “there are no exclusions” just because no exclusions field appears in Actuator JSON.

## 6. Unconditional Classes: No Conditions at the Auto-Configuration Class Level

`ConditionEvaluationReport.getUnconditionalClasses()` returns the set of class names that were evaluated but had no conditions applied. Actuator displays this group in `contexts.*.unconditionalClasses`.

An unconditional class **does not mean every bean method inside it is guaranteed to be registered**. For example:

```java
@AutoConfiguration
public class CommonInfrastructureAutoConfiguration {

    @Bean
    Object baseInfrastructureMarker() {
        return new Object();
    }

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.extra",
            name = "enabled",
            havingValue = "true"
    )
    Object optionalInfrastructureMarker() {
        return new Object();
    }
}
```

The class has no class-level condition, yet the second bean method still has its own condition. Thus, a class can appear in unconditional classes while one of its bean methods can still be a positive or negative match.

When reading unconditional classes:

- Treat this as information about **class-level conditions**, not the final conclusion for every method.
- If investigating a specific bean, continue looking for the source `ClassName#beanMethod` in positive/negative matches.
- Do not add a condition just to make a class disappear from the unconditional list; if a configuration is designed to always apply, this state is normal.

## 7. Reading the Report Directly in Java with `ConditionEvaluationReport`

Spring Boot 3.3 provides the API in package `org.springframework.boot.autoconfigure.condition`. The report is attached to the application context's `BeanFactory`.

The following example reads the outcomes after the context has refreshed:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.context.ConfigurableApplicationContext;

import java.util.Map;

public final class ConditionReportReader {

    private ConditionReportReader() {
    }

    public static void print(ConfigurableApplicationContext context) {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(context.getBeanFactory());

        if (report == null) {
            System.out.println("No condition report is available.");
            return;
        }

        System.out.println("=== EXCLUSIONS ===");
        report.getExclusions().forEach(System.out::println);

        System.out.println("=== UNCONDITIONAL CLASSES ===");
        report.getUnconditionalClasses().forEach(System.out::println);

        System.out.println("=== CONDITION OUTCOMES BY SOURCE ===");
        for (Map.Entry<String, ConditionAndOutcomes> entry
                : report.getConditionAndOutcomesBySource().entrySet()) {

            System.out.println("Source: " + entry.getKey());

            for (ConditionAndOutcome item : entry.getValue()) {
                String conditionName =
                        item.getCondition().getClass().getSimpleName();
                boolean matched = item.getOutcome().isMatch();

                System.out.println(
                        "  " + conditionName + " -> "
                                + (matched ? "MATCH" : "NO MATCH")
                );
            }
        }
    }
}
```

Place the file at `src/main/java/demo/ConditionReportReader.java` after adding an appropriate `package demo;`. This is a **utility class for reading the report**, not one that starts the application itself. Call `ConditionReportReader.print(context)` after the context is created if the application has access to the context.

### Why Use `find()` Instead of `get()`?

- `ConditionEvaluationReport.find(beanFactory)` attempts to locate an existing report and can return `null` if none exists yet.
- `ConditionEvaluationReport.get(beanFactory)` retrieves the current report or creates a new one if none exists yet.

When you only want to **read diagnostic data**, `find()` avoids creating an empty report and mistaking it for a report that recorded conditions.

### Important APIs

| API | Result |
|---|---|
| `getConditionAndOutcomesBySource()` | Map of source → condition outcomes |
| `ConditionAndOutcomes.isFullMatch()` | `true` when all outcomes for the source match |
| `ConditionAndOutcome.getCondition()` | The evaluated condition |
| `ConditionAndOutcome.getOutcome().isMatch()` | Whether that condition matched |
| `getExclusions()` | List of excluded classes |
| `getUnconditionalClasses()` | Set of classes with no applicable conditions |
| `getParent()` | Parent BeanFactory's report, if present |

When an application uses multiple contexts (for example, a separate management context), reports can differ per BeanFactory. Do not merge parent and child data and misattribute which context a source belongs to.

## 8. Enabling the Report in Startup Logs

The fastest way when debugging a Spring Boot application is to run with the argument:

```bash
java -jar application.jar --debug
```

`--debug` enables debug logging for a selection of core loggers and prints the Condition Evaluation Report to the console. It does not enable debug for every application package.

If you want to log the report at a specific log level using an initializer, Spring Boot 3.3 provides `ConditionEvaluationReportLoggingListener`:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;

public class ApplicationLauncher {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(Application.class);

        application.addInitializers(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        );

        application.run(args);
    }
}
```

This is an alternative launcher for the application's current `main` method. By default, the listener logs the report at DEBUG; `forLogLevel(LogLevel.INFO)` allows choosing a different log level. The Javadoc notes **not to share a single listener instance across multiple application contexts**; create an appropriate initializer for each context.

Logs can be long because a large application has many auto-configurations and nested conditions. Search by FQCN or relevant method name first, then read the full condition group for that source.

## 9. Using Actuator `/actuator/conditions`

If the application already uses Spring Boot Actuator, you can view the report over HTTP:

```properties
management.endpoints.web.exposure.include=health,conditions
```

Add the `spring-boot-starter-actuator` dependency if the project does not have it yet, then call:

```bash
curl http://localhost:8080/actuator/conditions
```

The default path is `/actuator/conditions`; if the application changes `management.endpoints.web.base-path`, the URL changes accordingly.

The JSON response has the following main structure:

| Field | Content |
|---|---|
| `contexts` | Application contexts, keyed by context id |
| `positiveMatches` | Classes/methods whose conditions matched |
| `negativeMatches` | Classes/methods with at least one condition that did not match |
| `negativeMatches.*.notMatched` | Unmatched conditions and reason messages |
| `negativeMatches.*.matched` | Other conditions that passed within the negative source |
| `unconditionalClasses` | Auto-configuration classes with no applicable conditions |
| `parentId` | Parent context ID, if any |

Real examples from the Spring Boot 3.3 documentation show conditions like `OnBeanCondition`, `OnClassCondition`, and `OnWebApplicationCondition` with explanatory messages. A negative match may specify “not a reactive web application” or a missing required class; those details help pick the right property, dependency, or application type to inspect.

**Actuator must be secured.** The conditions endpoint can reveal class names, bean names, and internal configuration details. Expose only when needed, and restrict network and access permissions with an appropriate security policy; do not expose all endpoints with `management.endpoints.web.exposure.include=*` just to debug.

## 10. Example: Testing the Report with `ApplicationContextRunner` (Spring Boot 3.3 / Java 17+)

`ApplicationContextRunner` creates a small context where properties and user beans can be controlled per test. This is a good way to verify that the condition report changes as expected without starting the full application.

Place the file `src/test/java/demo/ConditionEvaluationReportTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConditionEvaluationReportTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ReportedAutoConfiguration.class,
                            UnconditionalReportAutoConfiguration.class
                    ));

    private ConditionEvaluationReport report(
            AssertableApplicationContext context) {
        return ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory()
        );
    }

    @Test
    void positiveMatchAppearsWhenEveryConditionPasses() {
        runner.withUserConfiguration(GatewayConfiguration.class)
                .withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    assertTrue(context.containsBean("reportFeature"));

                    ConditionEvaluationReport report = report(context);
                    String source = ReportedAutoConfiguration.class.getName()
                            + "#reportFeature";

                    ConditionAndOutcomes outcomes =
                            report.getConditionAndOutcomesBySource().get(source);

                    assertNotNull(outcomes);
                    assertTrue(outcomes.isFullMatch());
                });
    }

    @Test
    void negativeMatchAppearsWhenRequiredBeanIsMissing() {
        runner.withPropertyValues("demo.report.enabled=true")
                .run(context -> {
                    assertFalse(context.containsBean("reportFeature"));

                    ConditionEvaluationReport report = report(context);
                    String source = ReportedAutoConfiguration.class.getName()
                            + "#reportFeature";

                    ConditionAndOutcomes outcomes =
                            report.getConditionAndOutcomesBySource().get(source);

                    assertNotNull(outcomes);
                    assertFalse(outcomes.isFullMatch());
                });
    }

    @Test
    void unconditionalAutoConfigurationIsListedSeparately() {
        runner.run(context -> {
            ConditionEvaluationReport report = report(context);

            assertTrue(report.getUnconditionalClasses().contains(
                    UnconditionalReportAutoConfiguration.class.getName()
            ));
            assertTrue(context.containsBean("unconditionalMarker"));
        });
    }

    @Configuration(proxyBeanMethods = false)
    static class GatewayConfiguration {
        @Bean
        ReportGateway reportGateway() {
            return new ReportGateway() {
            };
        }
    }
}

@AutoConfiguration
class ReportedAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "demo.report",
            name = "enabled",
            havingValue = "true"
    )
    @ConditionalOnBean(ReportGateway.class)
    ReportFeature reportFeature() {
        return new ReportFeature();
    }
}

@AutoConfiguration
class UnconditionalReportAutoConfiguration {

    @Bean
    String unconditionalMarker() {
        return "available";
    }
}

interface ReportGateway {
}

final class ReportFeature {
}
```

The `ReportedAutoConfiguration` class has two conditions: the property flag must be true and the `ReportGateway` bean must be present. The first test creates the gateway so the source is a positive match; the second test only sets the property so the source is a negative match. The third test confirms that an auto-configuration with no class-level conditions is listed in unconditional classes.

### Checking Exclusions in a Real Application

For exclusions, check the report API directly after the application is configured with exclusions:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.find(applicationContext.getBeanFactory());

if (report != null) {
    report.getExclusions().forEach(System.out::println);
}
```

This snippet is a **post-startup inspection pattern**, assuming `applicationContext` is a `ConfigurableApplicationContext` created by `SpringApplication` and exclusion configuration has been applied. The list will contain excluded auto-configuration names, such as those declared in `excludeName` or `spring.autoconfigure.exclude`. Do not look for an exclusion in `negativeMatches`.

### Dependencies and Run Commands

For a Gradle project configured with Spring Boot 3.3.x and Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Run:

```bash
./gradlew test --tests demo.ConditionEvaluationReportTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests demo.ConditionEvaluationReportTest
```

**Expected result:** 3 tests pass. This is the expected outcome from the test structure, not an actual run log; run on the project with your specific dependencies/version to confirm.

## 11. Common Mistakes When Reading the Report

1. **Treating a negative match as a startup error.** An unmatched configuration may be intended behavior because the application is running non-web, lacks an optional starter, or already provided a replacement bean.
2. **Looking for excluded classes in negative matches.** Excluded classes do not undergo condition evaluation; read `getExclusions()`.
3. **Assuming an unconditional class always creates every bean.** The list only states that the class has no applicable conditions; bean methods can still have their own conditions.
4. **Looking only at the condition name and ignoring the message.** `OnBeanCondition` can report which beans were found or missing; the message specifies the bean type, bean name, or search strategy.
5. **Seeing one matched condition and concluding the source matched.** With multiple conditions, one passing condition does not compensate for another failing condition.
6. **Reading the wrong source.** Conditions can be attached to a class or a bean method. A positive class does not mean every method in the class is positive.
7. **Forgetting context hierarchy.** Parent and child contexts have separate reports; use `getParent()` if you need to investigate the parent context.
8. **Not seeing exclusions in Actuator JSON and concluding there are no exclusions.** The conditions JSON schema does not list exclusions; read the raw report API or startup report.
9. **Changing code/properties without creating a new context.** The report reflects condition evaluation during that context's initialization; changing properties after startup does not re-evaluate all auto-configurations automatically.
10. **Exposing Actuator conditions publicly for quick debugging.** The endpoint can expose application structure; restrict access and expose only when truly needed.

## 12. Quick Diagnostic Workflow

When an auto-configured bean does not appear:

1. Find the bean method or auto-configuration name in `negativeMatches`.
2. Read `notMatched` to find the first meaningful failed condition.
3. If the source does not appear in positive/negative matches, check `exclusions` and `unconditionalClasses`; also verify whether the candidate was actually imported.
4. For `OnClassCondition`, check the runtime classpath and dependency versions.
5. For `OnPropertyCondition`, check the property name, final value, and profile/property source overrides.
6. For `OnBeanCondition`, check bean definitions, `@Bean` return types, and auto-configuration registration ordering.
7. For `OnWebApplicationCondition`, check the context's actual web application type.
8. After fixing, create a new context or run `ApplicationContextRunner` with the corresponding scenario; confirm both the actual bean and the new outcome.

When a bean appears unexpectedly:

- Find the corresponding source in `positiveMatches`.
- Read each message to see which conditions matched.
- Check final property values, classpath, replacement beans, and application type.
- If the source is unconditional, determine whether it is an auto-configuration designed to always apply; check bean method conditions.
- Verify that the exclusion was placed properly on the application configuration or property source.

## 13. Key Takeaways

- **Positive match:** all conditions of the source matched.
- **Negative match:** at least one condition did not match; read `notMatched` for the reason.
- **Exclusion:** candidate was removed prior to condition evaluation; read `ConditionEvaluationReport.getExclusions()`.
- **Unconditional class:** class was evaluated without class-level conditions; bean methods can still have conditions.
- **ConditionEvaluationReport:** Java API to read sources/outcomes, exclusions, unconditional classes, and parent report.
- **`--debug` / ConditionEvaluationReportLoggingListener:** ways to read the report via logs.
- **Actuator `/actuator/conditions`:** way to view positive/negative matches and unconditional classes via JSON; expose and secure the endpoint appropriately.

### Official Documentation

- Spring Boot 3.3 Javadoc — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 Javadoc — `ConditionEvaluationReport.ConditionAndOutcome`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcome.html
- Spring Boot 3.3 Javadoc — `ConditionEvaluationReportLoggingListener`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html
- Spring Boot 3.3 Actuator API — Conditions Evaluation Report: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 Reference — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
