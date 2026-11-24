# `ConditionEvaluationReport` to Explain Matching or Non-Matching Conditions

Spring Boot has multiple mechanisms for conditional bean registration. A configuration may only be activated when a class is on the classpath, a property has a specific value, another bean already exists, or the application is running in a web environment. This approach lets libraries and applications create only the components suited to the current environment.

When a bean does not appear as expected, a common question is: **which conditions were checked, which matched, and which caused the configuration to be skipped?** Spring Boot provides **`ConditionEvaluationReport`** to record the results of evaluating configuration conditions. This report helps explain why an auto-configuration or conditional configuration was applied or not applied.

In the **Conditional Configuration** chapter of *Spring Boot Fundamentals*, this lesson shows how to read the condition evaluation report, enable diagnostic logs, inspect the Actuator endpoint, write conditional configurations, and test both matching and non-matching cases.

## 1. Why Does Spring Boot Need to Evaluate Conditions?

Suppose an application has an optional audit feature. The team wants:

- When property `feature.audit.enabled=true`, Spring creates `AuditService`.
- When the property is absent or has another value, the audit feature is not enabled.
- If the application already has its own implementation, the default configuration can yield to the bean provided by the application.

Instead of writing manual conditional statements inside `main`, Spring Boot lets you describe conditions right on configuration classes or bean methods:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

When Spring processes the configuration class, it evaluates the `@ConditionalOnProperty` condition. If the condition matches, the configuration is processed and the bean definition can be registered. If the condition does not match, that configuration is skipped.

Common conditional annotations:

| Annotation | Typical condition |
| --- | --- |
| `@ConditionalOnClass` | One or more classes are present on the classpath |
| `@ConditionalOnMissingClass` | One or more classes are not on the classpath |
| `@ConditionalOnBean` | Matching bean already exists in context/registry at evaluation time |
| `@ConditionalOnMissingBean` | No matching bean exists yet at evaluation time |
| `@ConditionalOnProperty` | Property is present or has a value meeting the condition |
| `@ConditionalOnResource` | Specified resource exists |
| `@ConditionalOnWebApplication` | Application is of a matching web type |
| `@ConditionalOnNotWebApplication` | Application is not of the considered web type |
| `@ConditionalOnExpression` | SpEL expression evaluates to a matching result |

Conditions make configuration flexible, yet they also make figuring out why a bean did not appear harder if you only read Java classes. The condition evaluation report provides evidence of this process.

## 2. What Is `ConditionEvaluationReport`?

`ConditionEvaluationReport` is a Spring Boot data structure that records condition evaluation results during configuration processing. It is used to explain outcomes for auto-configurations and conditional configurations.

The report can store information such as:

- The configuration source or bean definition evaluated.
- The conditions that were checked.
- Whether each condition matched or did not match.
- Outcome messages explaining why the condition returned that result.
- Excluded auto-configurations.
- Configurations needing no conditions, recorded as unconditional classes.

Illustrative example result:

```text
Positive matches:
  AuditAutoConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true) matched
      (property 'feature.audit.enabled' found with value 'true')

Negative matches:
  MetricsExportAutoConfiguration:
    - @ConditionalOnClass did not find required class
      'com.example.metrics.Exporter'
```

This is simulated output to explain how to read it, not logs captured from a specific application.

### 2.1. The Report Is Not a List of All Existing Objects

`ConditionEvaluationReport` answers questions about **the configuration condition evaluation process**. It is not:

- A list of every existing bean instance.
- A Maven or Gradle dependency tree.
- A log of every method call in the application.
- A health report for databases or external systems.
- A tool tracking continuously changing conditions at runtime.

A bean may not exist because a class was not component-scanned, a configuration was not imported, a module is missing from the classpath, or a bean definition was registered another way. Not every cause corresponds to a negative match entry in the report.

### 2.2. The Report Is Built During Startup

Condition evaluation is tied to Spring's configuration processing and bean definition registration. The report reflects conditions evaluated during that process. If you change properties or the classpath, you normally need to create a new context or restart the application for conditions to be re-evaluated.

Do not treat the report as a dashboard that updates when properties change while the application is running. It is primarily a startup configuration diagnostic tool.

## 3. Understanding Positive Matches and Negative Matches

When reading the report, the two most important result groups are **Positive matches** and **Negative matches**.

### 3.1. Positive Match

A positive match shows that a condition or configuration satisfied its corresponding criteria. Example:

```text
Positive matches:
  AuditConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true) matched
```

This indicates the evaluated property matched. If the configuration has a `@Bean` method and no other condition prevents it, the bean definition can be registered.

However, a positive match for one condition **does not guarantee the entire application started successfully**. Another bean might still lack a dependency, a constructor might fail, or a subsequent condition might not match.

### 3.2. Negative Match

A negative match shows that a condition was evaluated and did not satisfy its criteria. Example:

```text
Negative matches:
  AuditConfiguration:
    - @ConditionalOnProperty (feature.audit.enabled=true)
      did not find property 'enabled'
```

The message helps distinguish cases:

- Property does not exist.
- Property has a value different from the required value.
- Required class is not on the classpath.
- A required bean was not registered yet at the time the condition was evaluated.
- The application is not the web type required by the configuration.

Do not immediately conclude "negative" means an error. Many negative matches are completely normal: MongoDB configurations do not need to be enabled when an application only uses PostgreSQL, and web configurations do not need to appear in a command-line application.

### 3.3. A Configuration Can Have Multiple Conditions

Example:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.audit.AuditClient")
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
class AuditAutoConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

For the configuration to be applied, all relevant conditions must be satisfied according to their semantics. If the class is present yet the property is not enabled, the configuration is still not activated. If the property is enabled yet the required class is missing, the configuration may likewise not be applied.

When reading the report, check **all relevant conditions**, rather than stopping at the first condition that says matched.

## 4. Common Information Structure in the Report

A report can be organized into groups:

| Group | Meaning |
| --- | --- |
| Positive matches | Configurations/conditions that matched |
| Negative matches | Configurations/conditions that did not match |
| Exclusions | Auto-configurations explicitly excluded |
| Unconditional classes | Configurations recorded as not needing typical condition evaluation |

Display names and structures may vary slightly across logs, the Actuator endpoint, and Spring Boot versions. When analyzing, focus on source, condition, and outcome message.

### 4.1. Source

Source is usually the configuration class name, bean method, or metadata source to which the condition is attached. Example:

```text
com.example.audit.AuditAutoConfiguration
com.example.audit.AuditAutoConfiguration#auditService
```

If the condition is on a class, source can point to the class. If the condition is on a `@Bean` method, source can point to the bean method. This helps pinpoint which exact configuration was affected.

### 4.2. Condition

Condition indicates the type of condition evaluated, such as:

- `OnClassCondition` for classpath conditions.
- `OnBeanCondition` for bean-related conditions.
- `OnPropertyCondition` for properties.
- `OnWebApplicationCondition` for web application types.

Condition names are Spring Boot's internal implementations for the corresponding conditional annotations/contracts. Fundamentals learners should prioritize reading the message and original annotation in source before digging deep into implementation classes.

### 4.3. Outcome Message

The message is the most useful part for diagnostics. It usually indicates whether the condition matched and which details were found or missing.

Example:

```text
@ConditionalOnProperty (feature.audit.enabled=true) matched
(found property 'enabled' with value 'true')
```

or:

```text
@ConditionalOnClass did not find required class
'com.example.audit.AuditClient'
```

Use the outcome message to decide the next check instead of guessing from the configuration name.

## 5. Enabling `ConditionEvaluationReport` with Debug Mode

A quick way to view the report during development is enabling Spring Boot's debug mode.

### 5.1. Using the Command Line

Run the application with the flag:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Or run the executable JAR:

```bash
java -jar target/app.jar --debug
```

With Gradle:

```bash
./gradlew bootRun --args='--debug'
```

On Windows PowerShell, you can use the corresponding wrappers:

```powershell
.\mvnw.cmd spring-boot:run -Dspring-boot.run.arguments=--debug
.\gradlew.bat bootRun --args='--debug'
```

The `--debug` flag enables Spring Boot's debug mode to display the condition evaluation report in startup logs according to current logging settings. It does not mean setting the entire application to `TRACE` level.

### 5.2. Enabling via `application.properties`

You can configure:

```properties
debug=true
```

Or YAML:

```yaml
debug: true
```

This configuration is useful in development environments or when investigating startup. Do not turn on debug arbitrarily in production without reviewing the volume of logs and exposed information.

### 5.3. Where Does the Report Appear?

When the application starts, look for a section with a heading similar to:

```text
CONDITIONS EVALUATION REPORT
```

In the report, focus on sources related to the bean/configuration under investigation. Logs can be long because Spring Boot evaluates many auto-configurations, so search for the relevant class or property name first.

### 5.4. Debug Mode Does Not Fix Conditions

`--debug` only helps display diagnostic information. It does not automatically:

- Enable missing properties.
- Add classes to the classpath.
- Register missing beans.
- Fix profile configurations.
- Change auto-configuration ordering.

If the report shows a condition did not match, fix the root cause in configuration or dependencies and restart.

## 6. Viewing the Condition Report via Spring Boot Actuator

If the application includes Spring Boot Actuator, the `conditions` endpoint can expose condition evaluation details as HTTP data.

### 6.1. Adding the Actuator Dependency

With Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

With Gradle:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

This dependency provides Actuator management endpoints, though it does not mean every endpoint is automatically public over HTTP.

### 6.2. Exposing the `conditions` Endpoint

Configuration example:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

After the application starts with a web server and suitable Actuator setup, the endpoint is typically accessible at:

```text
GET /actuator/conditions
```

If Actuator uses a different base path or the management server runs on a separate port, the actual URL will vary by configuration.

### 6.3. Reading the Endpoint Data

The response may have a JSON structure with sections:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.audit.AuditAutoConfiguration": [
          {
            "condition": "OnPropertyCondition",
            "message": "feature.audit.enabled matched"
          }
        ]
      },
      "negativeMatches": {
        "com.example.metrics.MetricsAutoConfiguration": [
          {
            "condition": "OnClassCondition",
            "message": "required class was not found"
          }
        ]
      },
      "exclusions": [],
      "unconditionalClasses": []
    }
  }
}
```

This is a shortened mock JSON to illustrate data structure. Real responses contain sources and messages generated by your application and Spring Boot version.

### 6.4. Securing the `conditions` Endpoint

The condition report can reveal:

- Which libraries are present on the classpath.
- Which features are enabled.
- Internal configuration names.
- Details about the environment and dependencies.

Therefore, do not expose this endpoint to everyone on the Internet. In production environments, restrict exposure, authentication, authorization, and network access according to operational policy. Only expose the endpoint when there is a clearly defined diagnostic need.

## 7. Example Investigating `@ConditionalOnProperty`

Consider an audit configuration:

```java
package com.example.audit;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
public class AuditConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

Assume `AuditService` has an appropriate constructor.

### 7.1. Case Where Property Equals `true`

`application.yml`:

```yaml
feature:
  audit:
    enabled: true
```

The condition can match because the property exists and its value satisfies `havingValue = "true"`. The report can record a positive match for `AuditConfiguration`.

### 7.2. Case Where Property Equals `false`

```yaml
feature:
  audit:
    enabled: false
```

The condition does not match because the actual value does not equal `true`. The report records a negative outcome and explains that the property did not meet the requirement.

### 7.3. Case Where Property Is Missing

If `feature.audit.enabled` is not declared, with `matchIfMissing = false`, the condition does not match. This is the common default behavior of `@ConditionalOnProperty` when a property is missing, unless `matchIfMissing = true` is explicitly set.

### 7.4. Case Where Property Exists with Different Spelling/Format

`@ConditionalOnProperty` compares values according to annotation and property source rules. If configuration uses a string like `yes` while the condition requires `true`, do not assume it is always treated as matching. Use explicit and consistent boolean values to avoid confusion.

## 8. Example Investigating `@ConditionalOnClass`

An auto-configuration should only be activated when the required library is present:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.example.search.SearchClient")
class SearchConfiguration {

    @Bean
    SearchService searchService() {
        return new SearchService();
    }
}
```

If `SearchClient` is present on the classpath, the condition can match. If the class does not exist, the configuration is skipped.

The report helps distinguish:

- Dependency was not declared or did not resolve.
- Dependency is present, yet configuration was still not imported/scanned.
- The class condition matched, yet another condition on the same configuration did not match.

When investigating the classpath, combine the report with Maven/Gradle's dependency tree. The condition report tells whether the class was found at runtime; the dependency tree explains which library brought that class in.

### 8.1. Why Use the `name` Attribute?

`@ConditionalOnClass` supports declaring classes using `value` or `name`. The `name` form is a class name string and is useful in cases where you need to avoid directly referencing an optional class when the configuration is loaded.

In auto-configurations targeting optional libraries, placing conditions on appropriate configuration classes can avoid loading types absent from the classpath. For complex setups, consult the auto-configuration design guide for your Spring Boot version.

## 9. Example Investigating `@ConditionalOnMissingBean`

An auto-configuration can supply a default implementation if the application has not declared one itself:

```java
@Configuration(proxyBeanMethods = false)
class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

If no `GreetingService` bean exists yet at the time the condition is evaluated, the default configuration can match. If the application already has a matching bean, the condition does not match and the default bean is skipped.

Example provided by the application:

```java
@Configuration
class CustomGreetingConfiguration {

    @Bean
    GreetingService greetingService() {
        return new CustomGreetingService();
    }
}
```

When both configurations are processed in the proper order, `GreetingAutoConfiguration` can back off because the application-supplied bean already exists.

### 9.1. Back-Off Is Intentional Behavior

In auto-configuration, `@ConditionalOnMissingBean` typically lets users override defaults. A negative match here is not necessarily a bug; it can prove the application supplied its own implementation.

The report helps answer:

- Was the default auto-configuration considered?
- Which bean caused `@ConditionalOnMissingBean` not to match?
- Was the default configuration skipped as expected?

### 9.2. Evaluation Timing Matters

`@ConditionalOnMissingBean` evaluates bean definitions Spring already knows at the time the condition runs. Thus, configuration and auto-configuration processing order can affect the outcome.

In auto-configuration, use the ordering and configuration mechanisms supported by Spring Boot. Do not rely on accidental component scan order to ensure custom beans are always seen first.

## 10. Exclusions in the Condition Report

An application can explicitly exclude an auto-configuration:

```java
@SpringBootApplication(
        exclude = DataSourceAutoConfiguration.class
)
public class ToolApplication {
    public static void main(String[] args) {
        SpringApplication.run(ToolApplication.class, args);
    }
}
```

Or using a property:

```properties
spring.autoconfigure.exclude=org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration
```

The report can record excluded auto-configurations in the exclusions section.

This differs from a negative match:

| Case | Meaning |
| --- | --- |
| Negative match | Condition was evaluated and not satisfied |
| Exclusion | Auto-configuration explicitly excluded by configuration |
| Absent from report | May not have been discovered/evaluated, or falls outside report scope |

If an auto-configuration is excluded, do not look for a negative condition message as if it had been evaluated normally. Check both the exclusions list and `spring.autoconfigure.exclude` or `exclude` attributes on annotations.

## 11. What Does Unconditional Classes Mean?

The report may contain an `unconditionalClasses` group. This group records configuration classes that did not require a typical conditional match result to be processed.

Do not interpret unconditional as meaning:

- All beans inside are guaranteed to be created successfully.
- No dependencies are needed.
- Beans are unaffected by other conditions on methods or nested configurations.

It only describes how the class was handled at the condition report layer. Beans can still encounter instance creation errors, missing dependencies, or individual method-level conditions.

## 12. Reading the Report with an Investigation Workflow

When a bean does not appear, investigate in order:

### Step 1: Identify the Missing Bean or Feature

Note down:

- Expected bean name or type.
- Configuration class or auto-configuration expected to create the bean.
- Relevant properties, dependencies, and profiles.

Do not start by searching for a random line in the report. Know which source is responsible for registering the bean.

### Step 2: Confirm the Configuration Was Discovered

Check:

- Is the class on the classpath?
- Is the package component-scanned?
- Was the configuration imported?
- Was the auto-configuration registered in the right metadata?
- Was it explicitly excluded?

If the class never entered configuration processing, the report may not show the negative match you expect.

### Step 3: Find the Source in the Report

Search for the configuration or bean method name. Read all related outcomes rather than only looking at the first line.

### Step 4: Identify the Non-Matching Condition

For example:

- Property missing or wrong value.
- Classpath missing a class.
- Required bean does not exist yet.
- Bean already exists, causing missing-bean condition to back off.
- Application is not of the matching web type.
- Required resource not found.

### Step 5: Fix at the Right Layer

| Cause | Where to check/fix |
| --- | --- |
| Wrong or missing property | `application.yml`, environment variables, command-line args, profiles |
| Class missing from classpath | Maven/Gradle dependencies and runtime packaging |
| Mandatory bean not registered | Component scan, `@Import`, `@Bean`, auto-configuration |
| Missing-bean condition back off | Custom bean, type/qualifier, configuration order |
| Auto-configuration excluded | `exclude` on annotation or `spring.autoconfigure.exclude` |
| Wrong web application type | Starters, application type, and web configuration |

### Step 6: Restart and Read the New Report

Conditions are normally evaluated during context construction. After changing properties or dependencies, run a fresh startup to verify the outcome. Comparing sources and outcomes before and after shows whether the change had the intended effect.

## 13. `ConditionEvaluationReport` and Startup Errors

The condition report is very useful when a configuration is skipped, yet not every startup error is a condition mismatch.

For example:

- `NoSuchBeanDefinitionException` can occur because a configuration was not imported, component scanning was wrong, or a condition did not match.
- `BeanCreationException` can occur after a condition matched and the bean definition was registered, yet the constructor or initialization failed.
- Database connection errors can happen once the datasource bean is registered and begins initializing.
- Class-loading errors can occur when a method or constructor executes, even if earlier classpath conditions matched.

Therefore, combine:

1. Condition evaluation report to understand which configurations were chosen.
2. Stack trace to understand which bean failed to create and the root cause.
3. Dependency tree to understand runtime libraries.
4. Active properties/profiles to verify configuration sources.

Do not use the report as a substitute for stack traces, or treat a positive match as proof that a bean initialized successfully.

## 14. Testing Conditions with `ApplicationContextRunner`

Spring Boot provides `ApplicationContextRunner` to test auto-configuration in a small context. It verifies whether conditions match or fail without launching a full web server.

Suppose the auto-configuration is:

```java
package com.example.audit;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true"
)
public class AuditAutoConfiguration {

    @Bean
    AuditService auditService() {
        return new AuditService();
    }
}
```

For an auto-configuration library packaged as a JAR, the class must be registered in the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This file contains the fully qualified names of auto-configuration classes, one class per line. In tests, `AutoConfigurations.of(...)` can load the configuration directly without relying on building a complete starter JAR.

### 14.1. Testing When Property Is Enabled

```java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class AuditAutoConfigurationTest {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class)
                    );

    @Test
    void createsAuditServiceWhenEnabled() {
        contextRunner
                .withPropertyValues("feature.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasSingleBean(AuditService.class);
                });
    }
}
```

When the property equals `true`, the condition matches and the bean is registered. The test verifies the context result.

### 14.2. Testing When Property Is Missing or `false`

```java
@Test
void doesNotCreateAuditServiceWhenPropertyIsMissing() {
    contextRunner.run(context -> {
        assertThat(context).doesNotHaveBean(AuditService.class);
    });
}

@Test
void doesNotCreateAuditServiceWhenDisabled() {
    contextRunner
            .withPropertyValues("feature.audit.enabled=false")
            .run(context -> {
                assertThat(context).doesNotHaveBean(AuditService.class);
            });
}
```

The three tests form a simple matrix:

| Property | Expected result |
| --- | --- |
| Missing | `AuditService` not registered |
| `true` | Single `AuditService` present |
| `false` | `AuditService` not registered |

### 14.3. Testing Back-Off When the Application Has Its Own Bean

If the auto-configuration uses `@ConditionalOnMissingBean`, you can supply a test bean beforehand:

```java
@Test
void backsOffWhenApplicationProvidesAuditService() {
    contextRunner
            .withUserConfiguration(CustomAuditConfiguration.class)
            .withPropertyValues("feature.audit.enabled=true")
            .run(context -> {
                assertThat(context).hasSingleBean(AuditService.class);
                assertThat(context.getBean(AuditService.class))
                        .isInstanceOf(CustomAuditService.class);
            });
}
```

The example assumes `CustomAuditConfiguration` declares a `@Bean AuditService` returning `CustomAuditService` and the auto-configuration includes `@ConditionalOnMissingBean(AuditService.class)`. The goal is proving the default configuration steps aside for the application-provided bean.

### 14.4. Why Use `ApplicationContextRunner`?

It creates a small-scoped test context that lets you:

- Add per-test property values.
- Load configurations or auto-configurations into the context.
- Add custom beans to verify back-off.
- Assert bean presence or absence.
- Close the context after each run.

This is a direct way to verify configuration conditions, much better than visually inspecting annotation definitions alone.

## 15. Inspecting the Report via API in Source Code

In situations requiring deeper diagnostics, Spring Boot has the `ConditionEvaluationReport` class in the `org.springframework.boot.autoconfigure.condition` package. The report is attached to the bean factory during configuration processing.

Conceptually, you can retrieve the report from a supporting bean factory and inspect recorded sources/outcomes. An API-level illustration:

```java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println("Source: " + source);
    System.out.println("Full match: " + outcomes.isFullMatch());
    outcomes.forEach(conditionAndOutcome -> {
        System.out.println(
                conditionAndOutcome.getOutcome().getMessage()
        );
    });
});
```

This is an advanced example depending on the specific Spring Boot release API. When using it directly in a project, import the right classes and check API signatures for your dependency version. For most applications, debug logs or the Actuator conditions endpoint are more convenient ways to observe it.

Do not build business logic based on reading the internal condition report. The report is a diagnostic tool; feature-toggling decisions should be expressed via configuration properties, conditional annotations, or public configuration mechanisms.

## 16. Limitations to Understand When Reading the Report

### 16.1. Absence of a Source in the Report Does Not Prove the Condition Matched

A configuration might not appear because:

- The class was not scanned/imported or is not in the auto-configuration list.
- The auto-configuration was excluded.
- The condition was never evaluated because the configuration did not enter processing.
- Another registration mechanism provided the bean.
- Versions or report display formats differ.

Therefore, first confirm whether the configuration was discovered.

### 16.2. The Report Is Not the Full Dependency Graph

If a classpath condition fails to match, the report may state the class was not found. It does not necessarily tell which dependency should have provided that class. Use Maven `dependency:tree` or Gradle `dependencyInsight` to trace dependency origins.

### 16.3. The Report Does Not Guarantee Bean Instances Create Successfully

A configuration may match and register a bean definition. When the container creates the instance, the constructor might fail due to missing dependencies or invalid configuration. Then you must read the stack trace and initialization errors.

### 16.4. Results Depend on Evaluation Timing

Especially with `@ConditionalOnBean` and `@ConditionalOnMissingBean`, the processing order of configurations and bean definitions matters. A bean registered too late may not be visible when the condition is evaluated.

### 16.5. The Report Is Somewhat Sensitive Information

Actuator endpoints or report logs can reveal library structure and features. Enable and share them only within the necessary scope, especially in production environments.

## 17. Common Errors and How to Handle Them

| Symptom | Possible cause | How to investigate |
| --- | --- | --- |
| Bean does not appear, no matching negative match seen | Configuration was not discovered/imported or was excluded | Check component scan, `@Import`, auto-configuration metadata, and exclusions |
| Property condition does not match | Wrong key, missing property, wrong value, or inactive profile | Check property sources, profiles, and outcome message |
| Class condition does not match | Class is not on runtime classpath or invisible to classloader | Check dependency tree and runtime artifact |
| Missing-bean condition does not match | A bean of matching type/identifier already exists | Check custom beans and bean creation sources |
| Positive match yet context still fails | Bean definition registered, yet instance or dependency creation failed | Read stack trace, constructors, and dependencies |
| `conditions` endpoint returns 404 | Actuator missing, endpoint unexposed, or different base path | Check dependency, exposure, and management path |
| Endpoint returns 401/403 | Security policy blocks access | Check authentication/authorization for management endpoints |
| Report is too long | Many auto-configurations are evaluated | Search for relevant source and filter logs instead of reading line by line |

### 17.1. Do Not Fix by Enabling All Features

If the report shows a condition did not match, do not arbitrarily turn on properties or add dependencies just to flip a negative match into a positive one. First determine whether that configuration is actually needed in the application.

For instance, a command-line application does not need a web server. Forcing a web auto-configuration to match can add dependencies and change the application type without providing value.

## 18. End-to-End Practical Workflow

Suppose a team reports that the `AuditService` bean was not created after deployment:

1. **Identify the configuration:** find `AuditConfiguration` or `AuditAutoConfiguration` responsible for creating the bean.
2. **Check the property:** confirm what value `feature.audit.enabled` has in the deployed environment, which profiles are active, and which source provides the property.
3. **Enable the report:** run with `--debug` in a diagnostic environment or use a secured Actuator `conditions` endpoint.
4. **Locate the source:** read the positive/negative outcomes for the audit configuration.
5. **Cross-check dependencies:** if a classpath condition failed, inspect the runtime dependency tree and packaged artifact.
6. **Check custom beans:** if a missing-bean condition backed off, identify which bean was supplied and whether it has the right type.
7. **Fix the root cause:** update the property, dependency, import, or bean configuration as needed.
8. **Restart and verify:** inspect the new report, confirm the bean appears, and test the actual audit flow.

When reporting to the team, document clearly:

```text
Configuration source:
Condition:
Expected value/state:
Observed value/state:
Report outcome:
Root cause:
Change made:
Verification:
```

This template helps distinguish evidence, root cause, and corrective action instead of just saying "Spring didn't create the bean."

## 19. Practice Exercises

### Exercise 1 – Reading a Property Condition

Create `AuditConfiguration` with:

```java
@ConditionalOnProperty(
        prefix = "feature.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
```

Start the application three times with the property missing, `false`, and `true` respectively. Enable `--debug`, find the audit source, and record the outcome of each run.

### Exercise 2 – Reading a Classpath Condition

Create a configuration with `@ConditionalOnClass(name = "com.example.search.SearchClient")`. Run the project with the dependency providing the class present and then with that dependency removed. Compare the report against the dependency tree.

### Exercise 3 – Verifying Back-Off

Create an auto-configuration using `@ConditionalOnMissingBean`. Run once without a custom bean and once with an application-declared bean. Check how the report explains why the default configuration matched or backed off.

### Exercise 4 – Distinguishing Exclusion from Negative Match

Exclude an auto-configuration using `spring.autoconfigure.exclude`. Observe the exclusions section and compare it with a configuration that was evaluated yet failed its condition.

### Exercise 5 – Inspecting via Actuator

Add `spring-boot-starter-actuator`, expose `conditions` locally, and call `GET /actuator/conditions`. Locate the configuration source under investigation in the JSON. Then remove exposure or secure the endpoint according to environment requirements.

### Exercise 6 – Writing `ApplicationContextRunner` Tests

Write three tests for a property condition:

- Property missing: bean does not exist.
- Property false: bean does not exist.
- Property true: bean exists.

Add a test supplying a custom bean to confirm the default auto-configuration backs off when `@ConditionalOnMissingBean` is present.

## 20. Things to Remember

`ConditionEvaluationReport` helps explain **why configuration conditions evaluated as matching or non-matching** during Spring context initialization. It is an important diagnostic tool when an auto-configuration or conditional bean does not appear as expected.

Remember:

- A positive match means the condition was satisfied; a negative match means the condition was evaluated and not satisfied.
- A negative match is not automatically an error. Some configurations are unnecessary in the current application.
- The report usually records source, condition, and outcome message; exclusions and unconditional classes are additional information groups.
- `--debug` or `debug=true` displays the condition evaluation report in startup logs.
- The Actuator endpoint `/actuator/conditions` provides data over HTTP when Actuator is present and the endpoint is exposed.
- `@ConditionalOnProperty`, `@ConditionalOnClass`, `@ConditionalOnBean`, and `@ConditionalOnMissingBean` address different kinds of conditions.
- A positive match does not guarantee bean instances instantiate successfully; always read stack traces when a context fails.
- If a source does not appear, check component scanning, imports, auto-configuration metadata, and exclusions before jumping to conclusions.
- Use `ApplicationContextRunner` to test matching, non-matching, and default back-off scenarios in a controlled manner.

When investigating a missing bean, trace the chain **configuration discovered → condition evaluated → outcome recorded → bean definition registered or skipped → bean instance created**. `ConditionEvaluationReport` reveals the conditional decision part; combining it with the dependency tree, active properties, and stack traces will pinpoint the exact root cause.
