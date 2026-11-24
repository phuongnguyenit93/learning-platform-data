# Distinguishing Intentional No-Match from Unexpected Misconfiguration

**Topic:** Spring Boot Auto Configuration  
**Knowledge Group:** Condition Evaluation Report  
**Goal:** Read the condition report to understand why an auto-configuration was applied or skipped, recognize when `no match` is normal designed behavior, and separate it from configuration or initialization errors that prevent the application from running.

## 1. `No match` Does Not Mean the Application Is Broken

Spring Boot uses conditions such as `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, `@ConditionalOnMissingBean`, and `@ConditionalOnWebApplication` to decide whether a configuration branch should participate.

Example:

```java
@Bean
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true"
)
FeatureService featureService() {
    return new FeatureService();
}
```

If `acme.feature.enabled` does not exist or has the value `false`, Spring skips the `featureService` bean. This is a **no-match condition outcome**. The context can still start normally. If the feature was designed to be opt-in, this is the exact expected result.

Another example:

```java
@Bean
@ConditionalOnMissingBean(FeatureService.class)
FeatureService defaultFeatureService() {
    return new FeatureService();
}
```

When the application already provides a `FeatureService` bean, the `@ConditionalOnMissingBean` condition does not match and the default bean is not registered. This is **intentional back-off** so the application can override the default.

Therefore, separate two questions:

- **Did the condition match?** Spring Boot answers with `match` or `no match`.
- **Does that result align with configuration intent?** The developer checks against the design policy and deployment environment.

`no match` only states that a condition was not satisfied. It does not by itself conclude that the user's configuration is wrong, nor does it prove that everything is fine.

## 2. What Does `ConditionEvaluationReport` Record?

`ConditionEvaluationReport` is the report collected by Spring Boot while evaluating auto-configuration conditions. Each outcome is attached to the **source** that declared the condition, usually a configuration class name or a `@Bean` method name.

Key concepts:

| Component | Meaning |
| --- | --- |
| Source | Class or `@Bean` method guarded by the condition |
| Condition | Type of condition evaluated, e.g., `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition` |
| Outcome | `match` or `no match` result |
| Message | Reason provided by the condition for the result |
| Positive matches | Sources whose relevant conditions matched |
| Negative matches | Sources with at least one condition that did not match |
| Exclusions | Auto-configuration classes excluded from evaluation |
| Unconditional classes | Classes recorded as having no conditions |

In the Spring Boot 3.3 API, you can access the report via:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> outcomes =
        report.getConditionAndOutcomesBySource();
```

`ConditionAndOutcomes.isFullMatch()` returns `true` when all outcomes in the source match. When at least one outcome does not match, the combined result is `false`. To see **which condition** caused the no-match, iterate each `ConditionAndOutcome` and read `getOutcome()`:

```java
for (Map.Entry<String, ConditionEvaluationReport.ConditionAndOutcomes> entry
        : outcomes.entrySet()) {

    String source = entry.getKey();
    var sourceOutcomes = entry.getValue();

    System.out.println(source + " => "
            + (sourceOutcomes.isFullMatch() ? "MATCH" : "NO MATCH"));

    for (ConditionEvaluationReport.ConditionAndOutcome item : sourceOutcomes) {
        var outcome = item.getOutcome();

        System.out.println("  "
                + item.getCondition().getClass().getSimpleName()
                + " | "
                + (outcome.isMatch() ? "matched" : "did not match")
                + " | "
                + outcome.getMessage());
    }
}
```

This is diagnostic code placed where a `ConfigurableListableBeanFactory` or active context is already available; it is not a standalone Java program. Specific messages depend on the condition and version. Read the actual content of the message rather than writing application logic against a fixed log string.

`ConditionEvaluationReport` is grouped by source, so you can tell **which bean method** or **which configuration class** is affected. That is far more helpful than looking only at a generic log line like “auto-configuration did not match”.

## 3. Types of `no match` That Are Usually Intentional

### 3.1. Feature Designed to Be Disabled by Default

```java
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

If the key is omitted or set to `false`, the bean is not registered. For a feature that operators must explicitly enable, a no-match is normal.

### 3.2. Optional Library Absent from the Classpath

```java
@ConditionalOnClass(name = "com.vendor.sdk.Client")
```

If the SDK dependency is not added, the corresponding integration is skipped. That is the purpose of classpath conditions in a starter with many optional features.

If the user **already declared** the dependency and expects the integration to run, a no-match can indicate the dependency did not make it onto the runtime classpath, versions drifted, or the classloader cannot see that class. The exact same condition outcome can be normal in one application and a configuration error in another.

### 3.3. Default Bean Backing Off for an Application Bean

```java
@ConditionalOnMissingBean(FeatureService.class)
```

If an application-supplied `FeatureService` bean is detected, the starter's default bean does not appear. The report records the condition as not matching because a matching bean was found. This is the expected outcome when a library supports overrides.

### 3.4. Application Is Not the Web Type Required by the Configuration

`@ConditionalOnWebApplication(type = SERVLET)` can fail to match in a non-Servlet application context. If the module is used inside a non-web or Reactive application, skipping Servlet configuration can be completely right.

### 3.5. Environment Does Not Yet Meet Cloud or Resource Conditions

A configuration that only runs on a specific cloud platform, when a resource file is present, or when a particular runtime condition is met may not match on a laptop or in tests. If that feature is only expected in the corresponding production environment, a local no-match can be normal behavior.

## 4. When `no match` Signals Unexpected Misconfiguration

The report states **that the condition was not satisfied and the technical reason supplied by the condition**. It does not know whether the operator configured it that way on purpose. Compare against the intended configuration.

### 4.1. Misspelled Property Name

The operator intended to enable:

```yaml
acme:
  feature:
    enabled: true
```

Yet actually wrote:

```yaml
acme:
  feature:
    enabld: true
```

For a condition looking for `acme.feature.enabled`, the `enabled` key is still considered missing. The report may show that the condition could not find property `enabled`. The application may still start up without creating the bean, making this mistake easy to confuse with a feature disabled by default.

Remediation: cross-check **canonical names** across annotations, YAML files, environment variables, and active profiles. Do not see a “similar-looking” property and assume the condition ought to match.

### 4.2. Value Does Not Match `havingValue`

```java
@ConditionalOnProperty(
        prefix = "acme.feature",
        name = "mode",
        havingValue = "strict"
)
```

If the effective value is `safe`, the condition does not match. This could be an intentional no-match or the user picking the wrong mode. The report identifies that the value failed the condition; product policy determines whether that value is valid.

Specifically with `@ConditionalOnProperty`, if `havingValue` is omitted, any present property whose value is not `"false"` matches by default. When using a Boolean feature flag, explicitly declare `havingValue = "true"` and `matchIfMissing` to avoid misinterpreting strings like `off`, `0`, or an empty value.

### 4.3. Active Profile or Configuration Source Differs from Expectations

A property may live in `application-prod.yml`, yet the application is running with the `dev` profile; or an environment variable/command-line argument overrides the YAML value. What the condition sees is the effective value in `Environment`, not the contents of a single file.

Remediation:

- Verify active profiles.
- Check canonical property names and higher-precedence configuration sources.
- Check the effective value via `/actuator/env` if the endpoint is enabled and properly secured, or inspect `Environment` in tests.
- Do not change annotations before knowing which configuration source is winning.

### 4.4. `@ConditionalOnMissingBean` Searching for the Wrong Type or Evaluating in the Wrong Order

If a fallback needs to back off for any implementation of `FeatureService`, yet the condition searches for one specific implementation, a custom bean may fail to make the condition back off as intended.

Furthermore, bean conditions rely on bean definitions already processed when the condition runs. Auto-configurations should be ordered appropriately, and `@Bean` methods should expose a specific enough return type so Spring can predict candidates. If the report says no bean was found, check types, return types, parent/child contexts, and auto-configuration ordering.

### 4.5. Auto-Configuration Missing from the Report

Not seeing a class in `positiveMatches` or `negativeMatches` **does not automatically mean its conditions returned no-match**. The class might not be a loaded candidate, might be excluded, might be missing from `AutoConfiguration.imports`, or might be absent from the classpath.

Check:

- The `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` file in the artifact.
- The `exclusions` list in the report and `spring.autoconfigure.exclude` configuration.
- Whether the starter/autoconfigure dependency is on the runtime classpath.
- Whether the package/class matches the artifact and version used by the application.

`ConditionEvaluationReport` provides the exclusions list and evaluated sources; it does not replace inspecting the dependency tree and JAR contents.

## 5. True Configuration Errors vs. an Unmatched Condition

An error that causes the context to fail usually leaves behind **an exception or startup failure**, not merely a no-match outcome.

| Situation | Typical Symptom | Where to Check |
| --- | --- | --- |
| Missing property leaves opt-in feature disabled | Negative match, context still runs | Confirm whether this is the desired default |
| Wrong property name or value | Negative match, context may still run | Cross-check canonical key, `havingValue`, profile, Environment |
| Optional class absent | Negative match from class condition | Dependencies / runtime classpath |
| YAML/Properties fails to parse | Error loading Config Data, context may fail to build | YAML syntax, file location, profile/import |
| Value cannot convert or validation fails | `BindException`, binding/validation error in startup failure | Property type, format, constraints |
| Bean method or constructor throws exception | `BeanCreationException` or another root cause | Stacktrace, inputs, external dependencies |
| Required dependency not found | `UnsatisfiedDependencyException` / `NoSuchBeanDefinitionException` | Bean definitions, conditions, wiring |
| Multiple beans cannot resolve a single dependency | `NoUniqueBeanDefinitionException` | `@Primary`, `@Qualifier`, bean candidates |
| Missing class or method at runtime | `NoClassDefFoundError`, `NoSuchMethodError` | Dependency tree and version compatibility |

Three points deserve special attention:

1. **A matched condition can still lead to startup failure.** The bean is allowed to register, yet its constructor/factory method or dependencies can fail.
2. **An unmatched condition usually does not fail the context.** It may simply skip an optional bean while other beans continue working.
3. **A configuration-loading error can happen before a complete report exists.** When the context fails to build, read the root exception and Failure Analysis; do not try to find a `negativeMatches` entry to explain every failure.

`ConditionEvaluationReport` is a tool to explain condition decisions, not a list of all exceptions and not a health report.

## 6. How to View the Report in a Real Application

### 6.1. Enabling `--debug`

Run the packaged Spring Boot application:

```bash
java -jar app.jar --debug
```

Or use configuration:

```properties
debug=true
```

`--debug` enables debug logging for a core group of loggers and prints the condition evaluation report. Look at the positive/negative matches sections to see which branches were enabled and which were skipped.

Do not leave debug enabled long-term in production just to compensate for missing intentional logging; use it during diagnosis and control logs under operational policy.

### 6.2. Viewing via Actuator `/actuator/conditions`

If the application has the `spring-boot-starter-actuator` dependency, the `conditions` endpoint can expose the report as JSON. Example exposure configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,conditions
```

After running the application:

```bash
curl http://localhost:8080/actuator/conditions
```

The Spring Boot 3.3 response includes sections such as:

- `contexts.*.positiveMatches`: classes/methods whose conditions matched.
- `contexts.*.negativeMatches`: classes/methods that did not match, with `notMatched`, `matched`, and messages.
- `contexts.*.exclusions`: excluded auto-configurations.
- `contexts.*.unconditionalClasses`: recorded unconditional classes.

This endpoint can reveal internal configuration structure and reasoning. Expose only in environments requiring diagnosis and protect with appropriate authentication/authorization; do not make it public just for debugging convenience.

### 6.3. Using `ConditionEvaluationReportLoggingListener` in Tests

Spring Boot provides `ConditionEvaluationReportLoggingListener`, an `ApplicationContextInitializer` that can log the report when running `ApplicationContextRunner`.

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(LogLevel.INFO))
        .withConfiguration(AutoConfigurations.of(FeatureAutoConfiguration.class))
        .run(context -> {
            // Assert bean outcomes and inspect the report here.
        });
```

By default the listener logs the report at DEBUG; `forLogLevel(LogLevel.INFO)` makes tests log at INFO. This listener should not be shared across multiple application context instances; create an appropriate initializer per test run.

`ApplicationContextRunner` is a great way to construct isolated contexts with well-defined classpath, properties, and user configurations. Each test should describe one case: missing property, false, true, missing dependency, or existing custom bean.

## 7. Hands-On Lab: Distinguishing Normal No-Match from Initialization Failures

This lab uses **Java 17**, **Spring Boot 3.3.5**, **JUnit 5**, Maven, and `ApplicationContextRunner`. It produces four outcome cases: missing property, property false, misspelled property, property true; plus a fallback back-off case and a case where the condition matches yet bean initialization fails.

### 7.1. Project Structure

```text
condition-diagnosis-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionDiagnosisTest.java
```

### 7.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>condition-diagnosis-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 7.3. `ConditionDiagnosisTest.java`

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ConditionDiagnosisTest {

    static class FeatureService {
    }

    static final class CustomFeatureService extends FeatureService {
    }

    @AutoConfiguration
    static class FeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService featureService() {
            return new FeatureService();
        }
    }

    @AutoConfiguration
    static class FallbackAutoConfiguration {

        @Bean
        @ConditionalOnMissingBean(FeatureService.class)
        FeatureService fallbackFeatureService() {
            return new FeatureService();
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFeatureConfiguration {

        @Bean
        CustomFeatureService customFeatureService() {
            return new CustomFeatureService();
        }
    }

    @AutoConfiguration
    static class BrokenFeatureAutoConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.feature",
                name = "enabled",
                havingValue = "true"
        )
        FeatureService brokenFeatureService() {
            throw new IllegalStateException(
                    "Required acme.feature.endpoint is missing");
        }
    }

    private final ApplicationContextRunner featureRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(FeatureAutoConfiguration.class));

    private static ConditionAndOutcomes outcomesFor(
            AssertableApplicationContext context, String methodName) {

        return ConditionEvaluationReport.get(context.getBeanFactory())
                .getConditionAndOutcomesBySource()
                .entrySet()
                .stream()
                .filter(entry -> entry.getKey().endsWith("#" + methodName))
                .map(Map.Entry::getValue)
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError("No condition report for " + methodName));
    }

    private static List<String> messagesFor(ConditionAndOutcomes outcomes) {
        List<String> messages = new ArrayList<>();
        for (ConditionAndOutcome item : outcomes) {
            String message = item.getOutcome().getMessage();
            if (message != null) {
                messages.add(message);
            }
        }
        return messages;
    }

    @Test
    void missingOptInPropertyIsANormalNoMatch() {
        featureRunner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(FeatureService.class);

            ConditionAndOutcomes outcomes = outcomesFor(context, "featureService");
            assertThat(outcomes.isFullMatch()).isFalse();
            assertThat(messagesFor(outcomes))
                    .anyMatch(message -> message.contains("enabled"));
        });
    }

    @Test
    void explicitFalseIsANormalNoMatch() {
        featureRunner.withPropertyValues("acme.feature.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FeatureService.class);
                    assertThat(outcomesFor(context, "featureService").isFullMatch())
                            .isFalse();
                });
    }

    @Test
    void typoInPropertyAlsoProducesNoMatchButIsUnexpectedToTheOperator() {
        featureRunner.withPropertyValues("acme.feature.enabld=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(FeatureService.class);

                    ConditionAndOutcomes outcomes = outcomesFor(context, "featureService");
                    assertThat(outcomes.isFullMatch()).isFalse();
                    assertThat(messagesFor(outcomes))
                            .anyMatch(message -> message.contains("enabled"));
                });
    }

    @Test
    void explicitTrueMatchesAndRegistersTheBean() {
        featureRunner.withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(outcomesFor(context, "featureService").isFullMatch())
                            .isTrue();
                });
    }

    @Test
    void existingUserBeanMakesFallbackBackOff() {
        new ApplicationContextRunner()
                .withUserConfiguration(UserFeatureConfiguration.class)
                .withConfiguration(
                        AutoConfigurations.of(FallbackAutoConfiguration.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(FeatureService.class);
                    assertThat(context.getBean(FeatureService.class))
                            .isInstanceOf(CustomFeatureService.class);

                    ConditionAndOutcomes outcomes =
                            outcomesFor(context, "fallbackFeatureService");
                    assertThat(outcomes.isFullMatch()).isFalse();
                });
    }

    @Test
    void matchedConditionCanStillBeFollowedByBeanCreationFailure() {
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO))
                .withConfiguration(AutoConfigurations.of(
                        BrokenFeatureAutoConfiguration.class))
                .withPropertyValues("acme.feature.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(context.getStartupFailure())
                            .hasRootCauseInstanceOf(IllegalStateException.class);
                });
    }
}
```

Run in the directory containing `pom.xml`:

```bash
mvn test
```

**Expected result:** six tests pass; Maven Surefire typically displays:

```text
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
```

The test code prints no custom stdout itself. Logs from `ConditionEvaluationReportLoggingListener` in the last test are written at INFO level and may appear in Maven logs.

Meaning of the six tests:

1. Property omitted: condition is no-match and the context still runs. This is intentional default OFF.
2. Property set to `false`: condition is no-match and the context still runs.
3. Typo `enabld`: condition outcome is also no-match, yet this is an unexpected error if the operator intended to enable the feature.
4. Property set to `true`: condition matches and the bean appears.
5. Application has a custom bean: fallback condition is no-match and the default backs off.
6. Property `true` makes the condition match, yet the factory method throws `IllegalStateException`; the context fails. This is an initialization error, not a no-match.

The third test makes the key point: **ConditionEvaluationReport cannot know on its own whether the user misspelled a property unintentionally.** The same no-match outcome can be policy-compliant or an operational mistake. Tests must compare against the expected state of each scenario.

## 8. Step-by-Step Diagnostic Workflow

When a bean or auto-configuration does not appear as expected, follow this sequence:

### Step 1: Determine the Application State

- Context starts successfully yet the bean is missing: start from the condition report.
- Context fails to start: inspect startup failures, the exception chain, and Failure Analysis first.
- Context starts yet the feature does not work even though the bean exists: this may be a runtime/logic error rather than a condition question.

### Step 2: Locate the Right Source in the Report

Find the auto-configuration class or `@Bean` method expected to create the bean. Check whether the source is in positive matches, negative matches, exclusions, or missing altogether.

- Positive: recorded conditions for the source matched.
- Negative: at least one condition did not match.
- Excluded: the class was removed from evaluation by exclude settings.
- Missing: verify whether the auto-configuration was actually a candidate and loaded.

### Step 3: Read Each Condition and Message

Do not stop at the words `NO MATCH`. Record:

- Condition type.
- Source class/method.
- The property, class, bean, resource, or application type the condition checks.
- What the message says was found or missing.

If multiple conditions guard one source, just one unmatched condition can prevent the source from applying.

### Step 4: Cross-Check Against the Expected Behavior Matrix

Example for an opt-in feature:

| Expected State | Property/Condition | Correct Outcome |
| --- | --- | --- |
| User did not enable | `acme.feature.enabled` missing | No-match, no bean |
| User disabled | `enabled=false` | No-match, no bean |
| User enabled | `enabled=true` | Match, bean present |
| User supplied implementation | `@ConditionalOnMissingBean` finds bean | Fallback no-match, custom bean present |
| Optional dependency not installed | `@ConditionalOnClass` does not find class | Integration no-match |

Only when actual results diverge from the matrix do you need to fix configuration/code.

### Step 5: If the Context Fails, Read the Root Exception

Do not conclude “condition no-match” from a missing bean if the application actually failed during refresh. Inspect the deepest meaningful `Caused by` and FailureAnalyzer. YAML, binding, validation, dependency injection, bean factory method, class loading, and external connection errors each have different remedies.

### Step 6: Reproduce in `ApplicationContextRunner`

Write one test for each combination of properties, classpath, and user beans. Keep tests small to verify specific conditions; you do not need to spin up an entire web application if a condition only depends on properties or beans.

## 9. Common Misconceptions

**Misconception 1: Every `negativeMatches` entry is an error.**  
False. Auto-configurations are designed not to apply when conditions are unmet. An application can legitimately have many negative matches.

**Misconception 2: A running context means every configuration is right.**  
False. An opt-in feature can remain disabled due to a property typo without failing startup. Verify expected behavior, not just process health.

**Misconception 3: Having the property in YAML means the condition definitely matches.**  
False. The name, prefix, or profile could be wrong, the value could be overridden, or `havingValue` might not match.

**Misconception 4: The condition report explains every startup failure.**  
False. The report records condition outcomes. Binding, constructor, bean factory method, class loading, or external connection failures must be read via exceptions/failure analysis.

**Misconception 5: A class missing from negative matches means a condition rejected it.**  
False. The class might not be loaded, might be absent from imports, might be excluded, or might be missing from the classpath. Check candidate lists, exclusions, and artifacts.

**Misconception 6: `@ConditionalOnMissingBean` not matching means the starter is broken.**  
False. If the application already supplied a matching replacement bean, the fallback not being created is the expected back-off behavior.

**Misconception 7: A no-match must be fixed by forcing the condition to match.**  
False. If a feature is designed to be optional or a default bean is meant to back off, forcing a match can violate policy and create unwanted beans.

**Misconception 8: Looking at a single `application.yml` file is enough.**  
False. `Environment` has multiple property sources and precedence rules; active profiles, environment variables, and command-line arguments can change the effective value.

## 10. Operational Conclusion

When reading the condition report, always classify along two independent axes:

- **Outcome:** did the condition match or no-match?
- **Intent:** does that outcome match deployment requirements?

If a condition no-match matches the configuration matrix, it is an intentional auto-configuration choice. If the no-match contradicts intent, inspect keys, values, profiles, classpath, bean types, and processing order. If the condition matched yet the application fails, switch to diagnosing exceptions, binding, and bean creation.

A good report helps answer “what did Spring decide and why.” It does not replace defining “what state does the application need,” nor does it replace startup exceptions or behavioral testing.

### Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration, Testing and Condition Reports](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReport`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 API — `ConditionEvaluationReportLoggingListener`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html)
- [Spring Boot 3.3 Actuator — Conditions Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [Spring Boot 3.3 API — `ConditionOutcome`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
