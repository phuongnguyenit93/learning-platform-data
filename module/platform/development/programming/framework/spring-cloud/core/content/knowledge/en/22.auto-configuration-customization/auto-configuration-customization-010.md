# Reading ConditionEvaluationReport to Verify Configuration

> **Chapter:** Auto-Configuration Customization
> **Module:** `SPRING_CLOUD_CORE` — understanding Spring Cloud's core foundations in distributed systems, especially Spring Cloud Commons, Context, externalized configuration, and version compatibility with Spring Boot. Learners explore refresh scope, discovery, service registry, service-to-service communication, and how to test and operate shared abstractions.
> **Focus:** `ConditionEvaluationReport` shows how Spring Boot auto-configuration conditions were evaluated and why a configuration was applied or skipped. This lesson teaches how to read the report from logs, Actuator, and tests to pinpoint which dependency, bean, or property is causing configuration to behave unexpectedly.

## 1. Why Read ConditionEvaluationReport?

Spring Boot auto-configures many components based on the classpath, existing beans, properties in `Environment`, application type, and other conditions. For example, an auto-configuration might create a bean only when a required library appears on the classpath; a default bean might be created only if the application has not declared a replacement bean.

When a component fails to appear, looking only at the final outcome is rarely enough to know why. A dependency might be missing, a property might not have the expected value, the application might be running in non-web mode, a user-declared bean might be causing auto-configuration to back off, or the configuration class might have been excluded.

`ConditionEvaluationReport` records the evaluation outcomes of conditions used by Spring Boot for configurations and auto-configurations. The report shows:

- which configuration sources or bean methods were evaluated;
- which conditions matched and which did not match;
- messages explaining the outcomes;
- excluded auto-configuration classes;
- classes evaluated without conditions;
- parent context relationships when a context hierarchy exists.

The report answers the question: *What did Spring Boot decide, and based on which conditions?* It is a diagnostic tool for configuration processing, not a complete inventory of active beans, nor a substitute for testing application behavior.

### Learning Outcomes

After this lesson, you will be able to:

1. explain the role of `ConditionEvaluationReport` in auto-configuration;
2. enable the report via `--debug` or `-Ddebug`;
3. read `positiveMatches` and `negativeMatches` from Actuator;
4. understand condition names, messages, and sources;
5. identify failures caused by classpath, bean, property, resource, or web application conditions;
6. inspect exclusion lists and context hierarchies;
7. query the report via Java API when diagnosing inside tests;
8. use `ApplicationContextRunner` and `ConditionEvaluationReportLoggingListener`;
9. establish a repeatable configuration verification workflow.

## 2. Conditions and Evaluation Outcomes

### 2.1. Auto-Configuration Uses Conditions

Auto-configuration classes are usually marked with `@AutoConfiguration`. Spring Boot loads candidates listed in `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` inside the corresponding JARs. `@Conditional*` annotations determine when configurations apply.

Common conditions:

| Annotation/condition | Question checked |
| --- | --- |
| `@ConditionalOnClass` | Is the required class on the classpath? |
| `@ConditionalOnMissingClass` | Is the specified class absent? |
| `@ConditionalOnBean` | Does a matching bean already exist in the BeanFactory? |
| `@ConditionalOnMissingBean` | Is no matching bean present yet so auto-configuration should create a default? |
| `@ConditionalOnProperty` | Does the property exist and satisfy the required value? |
| `@ConditionalOnResource` | Does the specified resource exist? |
| `@ConditionalOnWebApplication` | Is the context a web application of the requested type? |
| `@ConditionalOnExpression` | Does the SpEL expression evaluate to true? |

An auto-configuration can combine multiple conditions. If even one required condition fails to match, the corresponding configuration or bean method may not be registered.

### 2.2. ConditionOutcome

Each condition evaluation produces a `ConditionOutcome`. The outcome includes match status and an explanatory message.

- `isMatch()` returns `true` if the condition matched.
- `getMessage()` returns the explanatory message; it can be null if the condition supplied no message.

Example messages:

```text
@ConditionalOnClass found required class 'com.acme.Client'
@ConditionalOnProperty (acme.client.enabled=true) matched
@ConditionalOnMissingBean (types: com.acme.Client) found beans of type 'com.acme.Client'
@ConditionalOnClass did not find required class 'com.acme.Client'
```

Read the message as evidence of what was checked. For instance, a `@ConditionalOnMissingBean` message reveals whether a bean already existed, explaining why the default bean was created or skipped.

### 2.3. Source of an Outcome

The report groups conditions by source. A source is typically the fully qualified name of an auto-configuration class or a bean method, for example:

```text
com.acme.autoconfigure.AcmeClientAutoConfiguration
com.acme.autoconfigure.AcmeClientAutoConfiguration#acmeClient
```

When the source is a bean method, the part after `#` identifies which method was evaluated. This is helpful when an auto-configuration defines multiple beans and each bean has its own conditions.

### 2.4. Positive and Negative Matches

A source can appear under two main groups:

- **Positive match:** all required conditions for the source matched, so the source qualified to be applied.
- **Negative match:** at least one condition for the source did not match, so the source was not applied under that condition set.

In the detailed report, a negative match can also list:
- `notMatched`: conditions that failed to match;
- `matched`: other conditions on the same source that succeeded.

This is especially important for configurations combining multiple conditions. A source appearing in negative matches does not mean every condition on it failed. Look inside `notMatched` to find the immediate cause.

## 3. Enabling the Report at Startup

### 3.1. Using the --debug Flag

The fastest way to view auto-configuration decisions is adding `--debug` when launching the application:

```bash
java -jar application.jar --debug
```

With Maven or Gradle, pass the corresponding argument to the application run task. When launching directly on the JVM, you can use a system property:

```bash
java -Ddebug -jar application.jar
```

Spring Boot logs the condition evaluation report during startup. Look for the section titled `CONDITIONS EVALUATION REPORT` or search for the auto-configuration name you are inspecting.

`--debug` enables diagnostic reporting for auto-configuration decisions; it does not switch every logger in the application to DEBUG level.

### 3.2. Finding the Target Source

When logs contain many pages of conditions, avoid reading linearly from top to bottom. Instead:

1. search for the auto-configuration class name related to the missing feature;
2. search for the bean method if only one bean is missing;
3. read the condition name;
4. read the message of the non-matching condition;
5. cross-check against the application's dependencies, beans, and properties.

For example, if `AcmeClient` is not created, find the source `AcmeClientAutoConfiguration#acmeClient`. If the report says `@ConditionalOnClass` did not find `com.acme.Client`, check runtime dependencies and library versions.

### 3.3. When Should Debug Be Enabled?

Enable it in situations such as:

- an auto-configured feature fails to appear after adding a starter;
- a default bean backs off unexpectedly;
- upgrading Spring Boot or Spring Cloud changes condition outcomes;
- configuration works only in one profile or environment;
- test contexts behave differently from the running application.

You do not need it enabled on every production run. The report log can be long and expose class names, dependencies, properties, or internal structural details.

## 4. Reading the Report via Actuator

### 4.1. The Conditions Endpoint

If the application includes Spring Boot Actuator, the `conditions` endpoint exposes the report as JSON. The default HTTP path is:

```text
GET /actuator/conditions
```

To expose the endpoint over HTTP, configure:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

If `include` is already configured elsewhere, merge `conditions` into that list rather than accidentally removing existing endpoints. The endpoint requires the Actuator dependency and must be exposed in compliance with the application's governance policy.

Example request:

```bash
curl -sS http://localhost:8080/actuator/conditions
```

### 4.2. JSON Structure

The JSON report is structured by application context:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.acme.AcmeAutoConfiguration#acmeClient": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class 'com.acme.Client'"
          },
          {
            "condition": "OnPropertyCondition",
            "message": "@ConditionalOnProperty (acme.client.enabled=true) matched"
          }
        ]
      },
      "negativeMatches": {
        "com.acme.OtherAutoConfiguration#otherClient": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "@ConditionalOnProperty (acme.other.enabled=true) did not find property 'acme.other.enabled'"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "@ConditionalOnClass found required class 'com.acme.OtherClient'"
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

This is an abbreviated illustrative structure. Actual contents and condition counts depend on the application, classpath, and Spring Boot version.

Key fields:

| Field | Meaning |
| --- | --- |
| `contexts` | Application contexts indexed by ID |
| `positiveMatches` | Sources whose required conditions matched |
| `negativeMatches` | Sources where at least one condition failed to match |
| `notMatched` | Failed conditions for that source |
| `matched` | Passing conditions within a negative source |
| `unconditionalClasses` | Configuration classes evaluated without conditions |
| `parentId` | Parent context ID, if any |

### 4.3. Reading a Negative Match

Suppose the endpoint returns:

```json
{
  "negativeMatches": {
    "com.acme.AcmeClientAutoConfiguration#acmeClient": {
      "notMatched": [
        {
          "condition": "OnPropertyCondition",
          "message": "@ConditionalOnProperty (acme.client.enabled=true) did not find property 'acme.client.enabled'"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "@ConditionalOnClass found required class 'com.acme.Client'"
        }
      ]
    }
  }
}
```

Interpret it step by step:

1. The source being evaluated is the `acmeClient` bean method.
2. Class `com.acme.Client` is present, so the class condition matched.
3. Property `acme.client.enabled` was not found, so the property condition failed to match.
4. Because a required property condition is missing, the bean method was not applied.

The logical next step is checking the property in the effective Environment: whether the config file loaded, which profile is active, whether environment variables are named properly, and whether deployment config overrides the value.

### 4.4. Securing the Conditions Endpoint

The conditions endpoint reveals auto-configuration names, classpath details, and why features are enabled or disabled. Restrict access using Spring Security or your platform's administrative controls.

In production, expose the endpoint only on a management network with proper authentication and authorization; avoid exposing it over public HTTP. Do not paste full raw responses into public tickets or public logs if they reveal internal application details.

## 5. Identifying Root Causes by Condition Type

### 5.1. OnClassCondition

Example message:

```text
@ConditionalOnClass did not find required class 'com.acme.Client'
```

Check:

- whether the dependency is on the runtime classpath;
- whether the dependency is marked optional or excluded;
- whether the dependency scope is compile/test only;
- whether a library upgrade changed package/class names;
- whether the application uses custom classloaders or module boundaries.

Inspect the dependency tree for the exact artifact and runtime profile. Declaring a dependency in a build file does not prove the class appears on the final runtime classpath.

### 5.2. OnBeanCondition

Example:

```text
@ConditionalOnMissingBean found beans of type 'com.acme.Client'
```

This usually means the application already provided a matching bean, allowing the default bean to back off. This is standard extension-point behavior, not necessarily an error.

If a default bean disappeared unexpectedly:

- look for beans of the same type or name already declared;
- check `@Bean` methods, component scanning, and test configurations;
- check the context hierarchy and `SearchStrategy`;
- check `@Bean` method return types;
- verify bean definition ordering when multiple auto-configurations exist.

`@ConditionalOnBean` and `@ConditionalOnMissingBean` depend on bean definitions already processed at evaluation time. Spring Boot recommends using these bean conditions inside auto-configurations because auto-configurations load after user bean definitions.

### 5.3. OnPropertyCondition

Example:

```text
@ConditionalOnProperty (acme.client.enabled=true) did not find property 'acme.client.enabled'
```

Verify that the property actually exists in `Environment`, and check its value after profiles, environment variables, command-line arguments, and override sources apply.

With `@ConditionalOnProperty`:

- by default, a property that exists and does not equal the string `false` matches;
- `havingValue` lets you require a specific value;
- `matchIfMissing` determines whether the condition matches when the property is absent;
- if multiple property names are declared, all must satisfy the condition.

Example:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.client",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AcmeClientAutoConfiguration {
    // ...
}
```

With the configuration above, the property must equal `true`. If the property is missing or holds another value, the auto-configuration does not match.

### 5.4. OnWebApplicationCondition

If the message states that the application is not the required servlet or reactive web application, check:

- which web starter is present;
- what application type Spring Boot deduced;
- whether the test runner is creating the right context type;
- whether the application is running in non-web mode.

An auto-configuration for the servlet stack will not apply in a reactive context and vice versa. Do not add a web dependency just to turn a report entry into a positive match if the architecture does not require a web server.

### 5.5. OnResourceCondition

If a resource condition fails to match, check resource paths, classpath, profiles, and artifact packaging. A file sitting in the source tree might be excluded from the final JAR or reside at a different path when deployed.

### 5.6. Nested Conditions

Some conditions are composites such as `AnyNestedCondition`, `AllNestedConditions`, or `NoneNestedConditions`. Messages can be lengthy and describe multiple sub-branches.

Do not stop at the composite condition's name. Read the listed branches to see:
- which branches matched;
- which branches did not match;
- whether the overall rule requires all, at least one, or zero branches to match.

This prevents changing unrelated properties or dependencies by mistake.

## 6. Inspecting Exclusions and Context Hierarchy

### 6.1. Excluded Auto-Configurations

A class can be excluded from auto-configuration via:

- the `spring.autoconfigure.exclude` property;
- `exclude` or `excludeName` on `@SpringBootApplication` / `@EnableAutoConfiguration`;
- environment-specific test or bootstrap configurations.

Example:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.acme.autoconfigure.AcmeClientAutoConfiguration
```

If the class appears in the exclusions list, verify whether that was intentional for the application. Check profile-specific configs and deployment arguments too, since they can add exclusions at runtime.

### 6.2. Parent and Child ApplicationContexts

Some applications have multiple contexts, such as parent and child contexts for web servers or custom sub-contexts. The conditions endpoint groups reports by context ID and may include `parentId`.

When a bean does not appear, verify which context owns that bean. Beans in a parent context are visible from a child per hierarchy rules; beans in a child are not automatically visible from the parent.

`ConditionEvaluationReport` also provides `getParent()` to access the parent BeanFactory's report if present. Therefore, do not read only one context's report when the application uses a hierarchy.

### 6.3. Unconditional Classes

`unconditionalClasses` lists configuration classes that were evaluated without conditions. They are neither errors nor equivalent in semantics to positive matches. Use this field to understand configurations that are always loaded into the context.

## 7. Querying ConditionEvaluationReport in Java

### 7.1. Retrieving the Report from BeanFactory

`ConditionEvaluationReport.find(BeanFactory)` looks up an existing report and returns `null` if none is found. Use `find` when you only want to observe an existing report; `get` may create a report if one does not exist yet.

Example:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.context.ConfigurableApplicationContext;

public class ConditionReportPrinter {

    public void print(ConfigurableApplicationContext context) {
        ConditionEvaluationReport report =
                ConditionEvaluationReport.find(context.getBeanFactory());

        if (report == null) {
            System.out.println("No condition report found");
            return;
        }

        report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
            System.out.println(
                    source + " fullMatch=" + outcomes.isFullMatch()
            );

            outcomes.forEach(item -> {
                var outcome = item.getOutcome();
                System.out.printf(
                        "  condition=%s match=%s message=%s%n",
                        item.getCondition().getClass().getSimpleName(),
                        outcome.isMatch(),
                        outcome.getMessage()
                );
            });
        });

        System.out.println("Exclusions: " + report.getExclusions());
    }
}
```

`getConditionAndOutcomesBySource()` returns a map from source to condition outcome sets. Each `ConditionAndOutcome` exposes the condition and its outcome; `ConditionAndOutcomes.isFullMatch()` indicates whether every outcome in the group matched.

This is a low-level diagnostic API. In normal applications, prefer `--debug` logs or Actuator rather than writing business logic that depends on internal reports.

### 7.2. Reading the Parent Context's Report

If you need to investigate a context hierarchy:

```java
ConditionEvaluationReport parentReport = report.getParent();

if (parentReport != null) {
    System.out.println(
            parentReport.getConditionAndOutcomesBySource().keySet()
    );
}
```

Do not assume a parent report always exists. Check for null and identify which context contains the configuration you are analyzing.

### 7.3. Why You Should Not Use the Report as a Feature Flag

The condition report describes decisions made while configuring the context. It is not a runtime feature-toggle API and does not automatically reflect post-startup changes.

If the application needs business decisions based on properties or runtime state, use typed configuration, beans/services, or a feature flag service. Never query the condition report on a request path to drive business logic.

## 8. Testing with ApplicationContextRunner

### 8.1. Creating a Minimal Context for an Auto-Configuration

`ApplicationContextRunner` creates an isolated context with an explicit set of auto-configurations and properties. This is useful for verifying each combination of classpath, beans, and properties without booting the entire application.

Example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeClientAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeClientAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenEnabled() {
        this.contextRunner
                .withPropertyValues("acme.client.enabled=true")
                .run(context ->
                        assertThat(context).hasSingleBean(AcmeClient.class)
                );
    }

    @Test
    void doesNotCreateClientWhenDisabled() {
        this.contextRunner
                .withPropertyValues("acme.client.enabled=false")
                .run(context ->
                        assertThat(context).doesNotHaveBean(AcmeClient.class)
                );
    }
}
```

Each test describes one condition combination. Tests can add user configurations, property values, or custom classloaders to verify different branches.

### 8.2. Printing the Report in Tests

You can use `ConditionEvaluationReportLoggingListener` to print the report at INFO or DEBUG level:

```java
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener;
import org.springframework.boot.logging.LogLevel;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AcmeConditionReportTests {

    @Test
    void printsConditionReport() {
        new ApplicationContextRunner()
                .withInitializer(
                        ConditionEvaluationReportLoggingListener
                                .forLogLevel(LogLevel.INFO)
                )
                .run(context -> {
                    // Assertions for beans and configurations under test.
                });
    }
}
```

This listener is especially helpful when a test context produces a different outcome than the real application. Read the report alongside assertions: the report explains conditions, while assertions verify the required beans and behaviors.

### 8.3. Testing Missing Classpath Dependencies

`FilteredClassLoader` simulates a class or package being absent in the test context. This verifies whether `@ConditionalOnClass` truly causes auto-configuration to back off.

Example:

```java
import org.springframework.boot.test.context.FilteredClassLoader;

this.contextRunner
        .withClassLoader(new FilteredClassLoader(AcmeClient.class))
        .run(context ->
                assertThat(context).doesNotHaveBean(AcmeClient.class)
        );
```

This test verifies the missing-class branch. In real tests, ensure the filtered class is an optional dependency and that configuration does not reference that type directly in a way that loads the class before the condition is evaluated.

### 8.4. Testing User-Provided Beans

To verify auto-configuration backs off when a user supplies their own bean:

```java
@Configuration(proxyBeanMethods = false)
static class UserClientConfiguration {

    @Bean
    AcmeClient customAcmeClient() {
        return new AcmeClient("custom");
    }
}
```

```java
this.contextRunner
        .withUserConfiguration(UserClientConfiguration.class)
        .run(context -> {
            assertThat(context).hasSingleBean(AcmeClient.class);
            assertThat(context).hasBean("customAcmeClient");
        });
```

Tests must verify both the bean count and which bean is used. Asserting only that the context starts up is not enough to prove auto-configuration backed off properly.

## 9. Practical Debugging Workflow

When a feature is not auto-configured as expected, follow this sequence:

1. **Define the expected result.** Note which bean or feature should appear and in which profile.
2. **Confirm runtime dependencies.** Verify the starter and final dependencies contain the classes required by auto-configuration.
3. **Enable the report.** Run with `--debug` or call `/actuator/conditions` if secured and exposed.
4. **Find the exact source.** Locate the corresponding auto-configuration class or bean method.
5. **Read notMatched.** Identify the first or mandatory non-matching condition; check nested branches too.
6. **Check Environment.** Verify effective properties, active profiles, and override sources.
7. **Check existing beans.** Look for application or test beans causing `@ConditionalOnMissingBean` not to match.
8. **Check exclusions.** Confirm the class is not excluded by annotations or `spring.autoconfigure.exclude`.
9. **Read auto-configuration source.** Inspect condition annotations, ordering, and bean method return types.
10. **Write a reproducing test.** Use `ApplicationContextRunner` to isolate the failing combination of properties, beans, and classpath.
11. **Verify the outcome.** Check the actual bean and application behavior after fixing.

### Example: Default Bean Does Not Appear

Scenario: added the Acme starter, yet `AcmeClient` is not created.

The report shows:

```text
AcmeClientAutoConfiguration#acmeClient
OnClassCondition: matched
OnPropertyCondition: matched
OnBeanCondition: @ConditionalOnMissingBean found beans of type 'com.acme.AcmeClient'
```

Interpretation:

- Required dependencies are present.
- Feature-enabling property matched.
- An `AcmeClient` bean already exists, so the default bean was not created.

The next step is locating where that existing bean is declared and deciding whether it is an intentional replacement. If not, check component scanning, test configurations, or another auto-configuration creating that bean.

### Example: Property Exists in File Yet Condition Still Fails

Scenario: `application-prod.yml` has `acme.client.enabled=true`, yet the report says the property was not found.

Check in order:

- whether `prod` is among active profiles;
- whether the file is in the right location and loaded in the deployment environment;
- whether the property name has a prefix or spelling mismatch;
- whether an external config file overrides it from another source;
- whether an environment variable overrides it to empty or false;
- whether the auto-configuration reads the expected property namespace/version.

Use `/actuator/env` or controlled configuration logging to verify the effective Environment. The `env` endpoint can contain sensitive values, so secure it just like other management endpoints.

## 10. Limitations and Common Misinterpretations

| Misconception | Accurate understanding |
| --- | --- |
| Positive match means the bean is definitely instantiated | It means the source qualified; check the bean definition/instance and subsequent steps |
| Negative match means every condition failed | Only one required condition needs to fail; inspect `notMatched` and `matched` |
| Missing from positive matches means an error | The source may be in negative matches, excluded, or not a runtime candidate |
| Missing default bean means the starter is broken | `@ConditionalOnMissingBean` may intentionally back off when a user bean exists |
| Report reflects all runtime changes | The report records condition decisions made during context configuration |
| `--debug` enables DEBUG logging everywhere | It enables the auto-configuration decision report |
| Conditions endpoint is safe to expose publicly | It exposes internal structure and must be access-controlled |
| Fixing the first property you see is enough | Check effective Environment, profiles, and override sources |
| One report represents all contexts | Each context has its own report; inspect parent/child when a hierarchy exists |

The report also does not replace other diagnostic tools:

- `/actuator/beans` shows beans registered in the context;
- `/actuator/configprops` shows configuration bound into `@ConfigurationProperties`;
- `/actuator/env` shows property sources and Environment values according to sanitization policies;
- startup logs and exceptions pinpoint bean creation failures or runtime errors after conditions match.

## 11. Configuration Verification Checklist

Before concluding an auto-configuration is working properly, verify:

- [ ] Starter and required runtime dependencies are present.
- [ ] Auto-configuration class is loaded as a candidate.
- [ ] No unintended exclusions apply.
- [ ] All required class conditions match.
- [ ] Property conditions read the expected effective value and active profile.
- [ ] Bean conditions are not altered by an unexpected bean.
- [ ] Web application conditions match the context type.
- [ ] All nested condition branches have been read.
- [ ] Correct context ID and parent context checked when a hierarchy exists.
- [ ] Actual bean exists in the context with the right implementation.
- [ ] Key conditions have reproducing tests using `ApplicationContextRunner`.
- [ ] Conditions endpoint is exposed only to authorized administrators.

## 12. Practice Exercises

### Exercise 1 — Missing Class on Runtime Classpath

The report shows `OnClassCondition` could not find `com.acme.Client` even though the dependency is declared in the build file.

List possible reasons the class might be absent from the runtime classpath and how to verify the packaged artifact.

### Exercise 2 — Auto-Configuration Backs Off

`AcmeClientAutoConfiguration#acmeClient` did not match because `@ConditionalOnMissingBean` found a bean of the same type.

Identify possible sources that could have created that bean and suggest how to inspect bean names, types, and the context hierarchy.

### Exercise 3 — Property Condition Does Not Match

A property is set in a configuration file, yet the report says the property does not exist.

Establish a check order covering active profiles, property sources, environment variables, command-line arguments, spelling, `havingValue`, and `matchIfMissing`.

### Exercise 4 — Nested Condition

An auto-configuration uses `AnyNestedCondition` with two branches. One branch matches, the other does not, yet the source still appears in negative matches.

Explain the difference between individual branch outcomes and the final composite condition outcome.

### Exercise 5 — Conditions Endpoint

The application currently permits access only to `/actuator/health`. Operators want to read the conditions report over HTTP.

Propose exposure, authentication, authorization, and network policy settings so only operations personnel can access the endpoint.

### Exercise 6 — Test Context Differs from Production

Auto-configuration matches in tests but not in production.

List the factors to compare: classpath, active profiles, Environment, user beans, application context type, exclusions, and Spring Boot version.

### Quick Self-Check

1. What does `ConditionEvaluationReport` record? **Evaluation results of configuration and auto-configuration conditions.**
2. Which flag prints the auto-configuration report at startup? **`--debug` or system property `-Ddebug`.**
3. Which Actuator endpoint provides the JSON report? **`/actuator/conditions`.**
4. What does `positiveMatches` show? **Sources whose required conditions matched.**
5. What does `negativeMatches.notMatched` mean? **Conditions that failed to match on that source.**
6. What does `negativeMatches.matched` mean? **Other conditions that matched within a negative source.**
7. Which API looks up an existing report from a BeanFactory? **`ConditionEvaluationReport.find(beanFactory)`.**
8. Which API can create a report if one does not exist yet? **`ConditionEvaluationReport.get(beanFactory)`.**
9. Which tool tests auto-configurations in a small context? **`ApplicationContextRunner`.**
10. Which listener prints the report in tests? **`ConditionEvaluationReportLoggingListener`.**
11. Does the report prove a bean was instantiated? **No; verify the context and actual runtime behavior.**
12. Why must the conditions endpoint be protected? **It reveals class names, dependencies, and internal configuration details.**

**Core takeaway:** `ConditionEvaluationReport` explains why Spring Boot applied or skipped an auto-configuration by recording each condition and message. Locate the exact source, read non-matching conditions, inspect classpath, beans, properties, exclusions, and context hierarchies, and then confirm results against actual beans and controlled tests. Combining `--debug`, Actuator `conditions`, and `ApplicationContextRunner` makes diagnostics evidence-based and repeatable.

**References:**

- [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/4.0/how-to/application.html#howto.application.troubleshoot-auto-configuration)
- [Spring Boot Actuator — Conditions Evaluation Report](https://docs.spring.io/spring-boot/api/rest/actuator/conditions.html)
- [Spring Boot API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot API — ConditionAndOutcomes](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.ConditionAndOutcomes.html)

JSON structure, endpoint access, and certain APIs may differ across Spring Boot versions. Cross-check the reference documentation for the exact version in your project's dependency management before applying.