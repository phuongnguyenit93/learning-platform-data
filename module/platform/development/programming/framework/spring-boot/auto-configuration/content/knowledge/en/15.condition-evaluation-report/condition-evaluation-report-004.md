# ConditionEvaluationReport and Looking Up Outcomes by Configuration Source

## 1. Goal: Finding Why an Auto-Configured Feature Appears or Does Not Appear

When a bean provided by Spring Boot auto-configuration does not appear, looking at `application.yml` alone is often not enough to determine the cause. A `@ConditionalOnProperty` condition might not match, a dependent class might be missing from the classpath, a user bean might have caused `@ConditionalOnMissingBean` to back off, the application might have excluded the auto-configuration, or a web/servlet condition might not be satisfied.

Spring Boot records condition evaluation outcomes in **`ConditionEvaluationReport`**. This report shows:

- Which configuration class or bean method is the **source** of the condition.
- Which condition was evaluated.
- Whether the outcome matched or not.
- The explanatory message provided by the condition.
- Excluded auto-configuration classes and unconditional classes.

There is a very common point of confusion when investigating: **the source in `ConditionEvaluationReport` is where the condition was declared (configuration class or bean method); it is not the `PropertySource` that supplied the value for a configuration key.** To find out which file, environment variable, or command line provided the value of `acme.export.enabled`, you must inspect the `Environment` separately.

This lesson covers both directions:

1. Finding condition outcomes by class/bean method in the report.
2. Finding the source and origin of the property that caused the condition to match or fail.
3. Comparing raw values in the Environment against values bound into `@ConfigurationProperties`.
4. Verifying with Java 17+ and Spring Boot 3.3.

## 2. What Is ConditionEvaluationReport?

`org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport` is the Spring Boot class used to **record condition evaluation outcomes**. Common conditions include:

- `@ConditionalOnClass` / `@ConditionalOnMissingClass`: checks whether a class is present or absent on the classpath.
- `@ConditionalOnProperty`: checks a property in the Spring `Environment`.
- `@ConditionalOnBean` / `@ConditionalOnMissingBean`: checks whether a matching bean is already present or absent.
- `@ConditionalOnWebApplication` / `@ConditionalOnNotWebApplication`: checks the application type.
- Custom conditions implementing Spring's `Condition`.

Each time a condition is evaluated, the report stores a set of information consisting of:

| Component | Meaning |
|---|---|
| `source` | Configuration class or bean method to which the condition is attached |
| `condition` | The condition object performing the check |
| `outcome` | Match/no-match result along with an explanatory message |

One condition may match while another condition on the same source does not. Therefore, the report must show **each individual outcome**, not just a single overall status for the class.

### What Is a Source in the Report?

Example:

```java
@AutoConfiguration
public class ExportAutoConfiguration {

    @Bean
    @ConditionalOnProperty(
        prefix = "acme.export",
        name = "enabled",
        havingValue = "true")
    ExportClient exportClient() {
        return new ExportClient();
    }
}
```

If the condition is on the `exportClient()` method, the source in the report is typically represented as:

```text
com.acme.ExportAutoConfiguration#exportClient
```

If the condition is attached to the configuration class itself, the source can be the class name:

```text
com.acme.ExportAutoConfiguration
```

Accordingly, when looking up by source, search for **the fully qualified class name or the method name**. The `#` symbol separates the class and method in the common display format.

### The Report Is Not a List of Instantiated Beans

A condition match means the conditions allow the configuration/bean definition to proceed. It does not guarantee that the bean object was instantiated successfully: dependency injection, constructors, factory methods, or lifecycle hooks can still fail later. Conversely, a bean of the same type may be provided by another configuration even if the auto-configuration under inspection did not match.

Distinguish between:

- **Condition match:** conditions allow a configuration branch.
- **Bean definition:** the bean definition registered in the BeanFactory.
- **Bean instance:** the actual object created when Spring needs to instantiate the bean.

The report answers questions about **conditions**; it does not replace checking bean definitions, instances, or initialization errors.

## 3. Report Data Structure and Reading by Source

In the Spring Boot 3.3 API, `ConditionEvaluationReport` provides key methods:

| API | Purpose |
|---|---|
| `getConditionAndOutcomesBySource()` | Retrieves the `Map` of condition outcomes, grouped by source |
| `getExclusions()` | List of class names excluded from condition evaluation |
| `getUnconditionalClasses()` | Classes evaluated that had no conditions |
| `getParent()` | Parent BeanFactory's report, if any |
| `get(beanFactory)` | Retrieves the report attached to the BeanFactory |
| `find(beanFactory)` | Attempts to find the report; may return `null` |

The return type of `getConditionAndOutcomesBySource()` is:

```java
Map<String, ConditionEvaluationReport.ConditionAndOutcomes>
```

Each entry has a source key (class or method) and a collection of `ConditionAndOutcome` values. This collection can be iterated with a `for-each` loop; `isFullMatch()` returns `true` when **every outcome in the source matched**.

Each `ConditionAndOutcome` provides:

- `getCondition()`: the condition that ran.
- `getOutcome()`: the condition outcome.

For `ConditionOutcome`:

- `isMatch()` indicates whether the condition matched.
- `getMessage()` returns the explanatory message; may be `null`.

### Example Report Structure in Human-Readable Form

Suppose source `ExportAutoConfiguration#exportClient` has a matching property condition:

```text
source: com.acme.ExportAutoConfiguration#exportClient
  condition: OnPropertyCondition
  outcome: MATCH
  message: @ConditionalOnProperty (...) matched
```

If the configuration key is not satisfied:

```text
source: com.acme.ExportAutoConfiguration#exportClient
  condition: OnPropertyCondition
  outcome: NO MATCH
  message: @ConditionalOnProperty (...) did not find/does not match ...
```

This is an **illustrative model**; actual message contents depend on the condition, version, and input values. Do not write scripts that depend on exact full message sentences since they are diagnostic text; use the source key, condition name, and outcome status to classify, then read the message when you need details.

### Positive and Negative Matches

The report is commonly presented in two groups:

| Group | Meaning |
|---|---|
| `positiveMatches` | Sources whose conditions matched |
| `negativeMatches` | Sources that did not satisfy all conditions; you can inspect both unmatched and matched conditions |
| `unconditionalClasses` | Classes without conditions in the report |

For a source with multiple conditions, just one required condition failing to match prevents the configuration from being applied, even if the remaining conditions matched. When inspecting `negativeMatches`, do not stop at the first line; read both `notMatched` and `matched` to see exactly which condition blocked the configuration.

## 4. Approach 1: Enabling the Report at Startup with --debug

This is the fastest way when diagnosing a running application or one that fails to start.

If running an executable JAR:

```bash
java -jar app.jar --debug
```

Or enable the property:

```properties
debug=true
```

Spring Boot will print an additional auto-configuration decision report to the logs. The report typically contains positive matches and negative matches along with reasons.

**Debug mode does not mean every logger in the application switches to DEBUG.** Spring Boot only enables extra information for a core set of loggers; the goal here is viewing the condition report. If you need to enable a specific logger, you can configure:

```properties
logging.level.org.springframework.boot.autoconfigure.logging.ConditionEvaluationReportLoggingListener=DEBUG
```

Another API is `ConditionEvaluationReportLoggingListener`, an `ApplicationContextInitializer` that logs the report at DEBUG level; since Spring Boot 3.0 it includes a `forLogLevel(...)` factory method to select the log level for the report. Normally you do not need to register the listener manually if you only want to view the report with `--debug`.

### When to Use --debug?

- An auto-configured bean does not appear after startup.
- You want to know whether a classpath, property, or bean condition is failing to match.
- The application fails on startup and you need to view all auto-configuration decisions.
- You are developing a starter/auto-configuration and need to verify condition ordering.

When you only need to diagnose a property, do not stop at the report. Continue tracing the property source in Section 7 to determine why the value received by the condition differed from expectations.

## 5. Approach 2: Viewing the Report via Spring Boot Actuator /conditions

If the application already uses Spring Boot Actuator, the `conditions` endpoint returns the report as JSON.

Add the dependency to Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Configure endpoint exposure in `application.properties`:

```properties
management.endpoints.web.exposure.include=health,info,conditions,env,configprops
```

After the application starts, call:

```bash
curl http://localhost:8080/actuator/conditions
```

The default endpoint is `/actuator/conditions` if the base path is unchanged. If the application changes `management.endpoints.web.base-path`, the URL changes accordingly.

### Key JSON Structure

The response has this primary structure:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.acme.ExportAutoConfiguration#exportClient": [
          {
            "condition": "OnPropertyCondition",
            "message": "..."
          }
        ]
      },
      "negativeMatches": {
        "com.acme.CacheAutoConfiguration#cacheClient": {
          "notMatched": [
            {
              "condition": "OnClassCondition",
              "message": "..."
            }
          ],
          "matched": [
            {
              "condition": "OnPropertyCondition",
              "message": "..."
            }
          ]
        }
      },
      "unconditionalClasses": [
        "com.acme.CommonAutoConfiguration"
      ]
    }
  }
}
```

This is **structural illustrative JSON**, not output from a specific application.

| JSON path | Meaning |
|---|---|
| `contexts` | Application contexts, keyed by id |
| `contexts.*.positiveMatches` | Sources with matching conditions |
| `contexts.*.negativeMatches` | Sources that did not satisfy all conditions |
| `negativeMatches.*.notMatched` | Unmatched conditions |
| `negativeMatches.*.matched` | Other conditions that matched in the same source |
| `contexts.*.unconditionalClasses` | Classes without conditions |
| `contexts.*.parentId` | Id of the parent context, if present |

If the application has multiple contexts (such as root and child), you must select the right entry under `contexts`. Do not assume there is always only a single `application` key.

### Looking Up a Specific Source with jq

The endpoint returns the report; it is not a server-side search API by class name. You can filter the JSON locally:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.positiveMatches["com.acme.ExportAutoConfiguration#exportClient"]'
```

Look up a source in the negative group:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.negativeMatches["com.acme.ExportAutoConfiguration#exportClient"]'
```

If you do not know the exact source, list the keys first:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.positiveMatches | keys'
```

Or:

```bash
curl -s http://localhost:8080/actuator/conditions \
  | jq '.contexts.application.negativeMatches | keys'
```

Then copy the exact key into the filter command. The `#` in the source name is a character of the JSON key, not a URL fragment.

## 6. Approach 3: Reading ConditionEvaluationReport Directly in Java

When writing integration tests or internal diagnostic tools, you can access the report from the BeanFactory.

Example:

```java
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;

ConditionEvaluationReport report =
        ConditionEvaluationReport.get(context.getBeanFactory());

report.getConditionAndOutcomesBySource().forEach((source, outcomes) -> {
    System.out.println("SOURCE: " + source);
    System.out.println("FULL MATCH: " + outcomes.isFullMatch());

    for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
        System.out.println(
                "  condition=" + item.getCondition().getClass().getSimpleName());
        System.out.println(
                "  matched=" + item.getOutcome().isMatch());
        System.out.println(
                "  message=" + item.getOutcome().getMessage());
    }
});
```

This snippet assumes `context` is an `AnnotationConfigApplicationContext` or a specific context whose `getBeanFactory()` returns `ConfigurableListableBeanFactory`. For other context types, obtain the BeanFactory of the specific context under investigation.

To inspect just one source:

```java
var sourceEntry = report.getConditionAndOutcomesBySource()
        .entrySet()
        .stream()
        .filter(entry ->
                entry.getKey().contains("ExportAutoConfiguration#exportClient"))
        .findFirst();

sourceEntry.ifPresent(entry -> {
    System.out.println("Source: " + entry.getKey());
    System.out.println("Full match: " + entry.getValue().isFullMatch());

    for (var item : entry.getValue()) {
        System.out.println(item.getCondition().getClass().getSimpleName()
                + " -> " + item.getOutcome().isMatch()
                + " : " + item.getOutcome().getMessage());
    }
});
```

If the source is not found, check:
- Was the class actually loaded/evaluated in that context?
- Is the condition on the class or on a bean method?
- Does the actual source key match the expected package/class/method?
- Was the class excluded or not yet imported?
- Are you reading the report of a different parent/child BeanFactory?

Do not treat a missing source as either a matched or unmatched condition; the source may never have been evaluated and thus has no entry.

### Supporting APIs

```java
report.getExclusions();
report.getUnconditionalClasses();
report.getParent();
```

- `getExclusions()` is useful when you suspect an auto-configuration was excluded.
- `getUnconditionalClasses()` reveals classes recorded without conditions.
- `getParent()` lets you continue inspecting the parent BeanFactory's report when the application has a context hierarchy.

`ConditionEvaluationReport.get(beanFactory)` retrieves the report, whereas `find(beanFactory)` is used when you want to attempt lookup and accept the case where no report exists. Do not use a parent context's report to draw conclusions about conditions in a child context without verifying scope.

## 7. Condition “Source” vs. Property “Source”

This is the most important part when tasked with looking up outcomes by configuration source.

There are two different questions:

| Question | Where to Look | Example |
|---|---|---|
| Which class/method condition matched? | `ConditionEvaluationReport` / `/actuator/conditions` | `ExportAutoConfiguration#exportClient` |
| Which source did a property value come from? | Spring `Environment` / `/actuator/env/{property.name}` | `application-prod.yml`, environment variable, command line |
| What value was bound into the properties object? | `/actuator/configprops/{prefix}` or the object in code | `ExportProperties.format` |

**There is no one-to-one mapping between a source in the report and a PropertySource.** One `@Bean` method can have multiple conditions, and one condition can read multiple properties. The report records condition outcomes, but does not always identify the exact origin file/line of each property. To know the true source, you must ask the Environment.

### 7.1. Looking Up a Property with Actuator /env

Call:

```bash
curl http://localhost:8080/actuator/env/acme.export.enabled
```

When the property exists, the response provides information like:

```json
{
  "property": {
    "source": "Config resource 'class path resource [application-prod.yml]'",
    "value": "true"
  },
  "propertySources": [
    {
      "name": "commandLineArgs"
    },
    {
      "name": "systemProperties"
    },
    {
      "name": "systemEnvironment"
    },
    {
      "name": "Config resource 'class path resource [application-prod.yml]'",
      "property": {
        "value": "true",
        "origin": "class path resource [application-prod.yml] - 4:13"
      }
    }
  ]
}
```

This is an **illustrative** response to understand the data fields; actual sources, values, and origins depend on the application. Note:

- `property.source` shows the selected source for the queried property.
- `property.value` is the effective value, if present.
- `propertySources` lists the PropertySources in precedence order.
- `propertySources[].property.origin` can indicate the file/line or origin location of the property if the source supports origin tracking.
- If the key is absent from the Environment, the `property` field may be omitted.

The `env` endpoint also supports querying the entire Environment at `/actuator/env`, but when debugging you should query **a specific key** to reduce noise and avoid reading unrelated configuration.

### 7.2. Inspecting Configuration Source Precedence

If `application.yml` sets:

```yaml
acme:
  export:
    enabled: false
```

but the command line runs the application with:

```bash
java -jar app.jar --acme.export.enabled=true
```

then `/actuator/env/acme.export.enabled` can show the effective value `true` coming from the command-line source; the YAML file still exists but has lower precedence. `@ConditionalOnProperty(havingValue="true")` can therefore match.

Conversely, if the command line sets `false` while the YAML file sets `true`, the effective value is `false` and the condition does not match (with default SpringApplication behavior and no higher-precedence source).

Do not infer the winning source solely from the file order visible in the repository. Profiles, `spring.config.import`, custom PropertySources, and test property sources can change the actual precedence order.

### 7.3. Inspecting Values Bound into @ConfigurationProperties

If the library has:

```java
@ConfigurationProperties(prefix = "acme.export")
public class ExportProperties {
    private boolean enabled;
    private String format = "csv";

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public String getFormat() {
        return format;
    }

    public void setFormat(String format) {
        this.format = format;
    }
}
```

then the endpoint:

```bash
curl http://localhost:8080/actuator/configprops/acme.export
```

lets you inspect the `@ConfigurationProperties` bean bound under that prefix. Use `env` to find the property source and `configprops` to inspect the bound values; the two endpoints answer two different questions.

By default, endpoints may mask/sanitize sensitive values depending on policy. Do not disable sanitization merely for debugging convenience in a real environment.

## 8. Combining Three Pieces of Evidence to Find the Root Cause

Suppose the `exportClient` bean does not appear. A systematic investigation workflow:

1. Open `/actuator/conditions` or run `--debug`, and locate source `com.acme.ExportAutoConfiguration#exportClient`.
2. If the source is in `negativeMatches`, read `notMatched` to identify the blocking condition. If it is `OnPropertyCondition`, note the key and expected value in the message.
3. Call `/actuator/env/acme.export.enabled` to learn the effective value and PropertySource/origin.
4. If the condition involves a bean type, inspect `/actuator/beans` or the reports of auto-configs that create dependent beans.
5. If the condition matches yet the bean is still unusable, inspect initialization errors and the bean's dependencies; the report does not guarantee the constructor/factory method ran successfully.
6. If the property is right yet the configuration object differs from expectations, inspect `/actuator/configprops/acme.export` and check defaults, relaxed binding, validation, or data types.

### Outcome Reading Matrix

| Condition Report | Environment | Conclusion to Check |
|---|---|---|
| Property condition does not match | Value is missing | Check `matchIfMissing` and whether the key was loaded |
| Property condition does not match | Value `false` from command line | A higher-precedence source is disabling the feature |
| Property condition does not match | Invalid value such as `treu` | Typo / value does not match `havingValue` |
| Property condition matches | Value `true` is correct | Check other conditions, missing-bean, and instantiation errors |
| Bean condition does not match | Property condition still matches | Check existing bean of the same type, `SearchStrategy`, and registration timing |
| Condition source does not appear | Class not found among candidates | Check imports, exclusions, classpath, and which context is being inspected |
| Condition source does not appear | Bean still exists | Bean may come from user configuration or another auto-config |

Do not draw conclusions from a single line. A configuration can have conditions at the class level and on individual `@Bean` methods; the report can have multiple entries related to the same feature.

## 9. Runnable Example: Inspecting the Report by Source and Property Source

The example below uses **Java 17+**, Spring Boot 3.3.13, and Maven. It creates two simulated configuration sources: low-priority `applicationConfig` and high-priority `deployment`. Each scenario creates a fresh context, evaluates `@ConditionalOnProperty`, and prints:

- Effective property value.
- Winning PropertySource.
- Condition source found in `ConditionEvaluationReport`.
- Condition outcome and whether the bean exists in the context.

### 9.1. Structure

```text
condition-report-demo/
├── pom.xml
└── src/main/java/demo/report/
    └── ConditionReportDemo.java
```

### 9.2. pom.xml

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
    <artifactId>condition-report-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>
</project>
```

### 9.3. ConditionReportDemo.java

```java
package demo.report;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.MapPropertySource;
import org.springframework.core.env.PropertySource;

public class ConditionReportDemo {

    private static final String ENABLED = "acme.export.enabled";

    @Configuration(proxyBeanMethods = false)
    static class ExportConfiguration {

        @Bean
        @ConditionalOnProperty(
                prefix = "acme.export",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false)
        String exportClient() {
            return "export-ready";
        }
    }

    private static void inspect(String enabledValue) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            var propertySources = context.getEnvironment().getPropertySources();

            // Low-priority source: simulates application.yml.
            propertySources.addLast(new MapPropertySource(
                    "applicationConfig",
                    Map.of(ENABLED, "false")));

            // High-priority source: simulates deployment configuration.
            propertySources.addFirst(new MapPropertySource(
                    "deployment",
                    Map.of(ENABLED, enabledValue)));

            context.register(ExportConfiguration.class);
            context.refresh();

            String winningPropertySource = "<missing>";
            for (PropertySource<?> source : propertySources) {
                if (source.containsProperty(ENABLED)) {
                    winningPropertySource = source.getName();
                    break;
                }
            }

            ConditionEvaluationReport report =
                    ConditionEvaluationReport.get(context.getBeanFactory());

            var reportSource = report.getConditionAndOutcomesBySource()
                    .entrySet()
                    .stream()
                    .filter(entry ->
                            entry.getKey().contains(
                                    "ExportConfiguration#exportClient"))
                    .findFirst()
                    .orElseThrow(() -> new IllegalStateException(
                            "Condition source was not recorded"));

            System.out.printf(
                    "enabled=%s effective=%s propertySource=%s "
                            + "reportSourceFound=true conditionMatched=%s bean=%s%n",
                    enabledValue,
                    context.getEnvironment().getProperty(ENABLED),
                    winningPropertySource,
                    reportSource.getValue().isFullMatch(),
                    context.containsBean("exportClient"));
        }
    }

    public static void main(String[] args) {
        inspect("true");
        inspect("false");
    }
}
```

From the `condition-report-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.report.ConditionReportDemo
```

To use `exec:java`, add the plugin under `build/plugins` in `pom.xml` if the Maven project does not already have it:

```xml
<plugin>
    <groupId>org.codehaus.mojo</groupId>
    <artifactId>exec-maven-plugin</artifactId>
    <version>3.3.0</version>
</plugin>
```

**Two lines printed by the program:**

```text
enabled=true effective=true propertySource=deployment reportSourceFound=true conditionMatched=true bean=true
enabled=false effective=false propertySource=deployment reportSourceFound=true conditionMatched=false bean=false
```

Explanation:

1. `applicationConfig` is added with `addLast`; it provides `false` but has low precedence.
2. `deployment` is added with `addFirst`; it provides a higher-precedence value and is the winning source for the key.
3. Each `inspect(...)` call creates a fresh context, so the `true` scenario does not affect the `false` run.
4. `ConditionEvaluationReport.get(context.getBeanFactory())` retrieves the report attached to the current BeanFactory.
5. `getConditionAndOutcomesBySource()` returns the map; the code filters for the source containing `ExportConfiguration#exportClient` and reads `isFullMatch()`.
6. `containsBean("exportClient")` confirms the bean was actually registered in the context. This is a check separate from the report.
7. The output demonstrates that **the condition source** and **the value's PropertySource** are two distinct pieces of information: the condition source is the `exportClient` method; the winning property source is `deployment`.

This example uses `AnnotationConfigApplicationContext` to directly demonstrate Spring Boot's report and condition APIs; in a real application, auto-configuration is usually imported by Boot via `AutoConfiguration.imports` and Actuator provides JSON endpoints for remote investigation.

## 10. Common Mistakes When Reading the Report

| Mistake | Reality | How to Fix |
|---|---|---|
| Assuming the source in the report is a YAML file | The source is the class/method declaring the condition | Use `/actuator/env/{key}` to find the PropertySource |
| Looking only at positiveMatches | A bean may be absent because its condition is in negativeMatches | Check both positive and negative sources |
| Reading only the first message | A single source can have multiple conditions | Read every entry for the source and find the unmatched condition |
| Thinking a condition match means the bean constructor ran | The report only reflects conditions | Check the bean, dependencies, and initialization errors separately |
| Thinking a missing source means the condition was false | The source may not have been evaluated, was excluded, or was not imported | Check candidates/imports, exclusions, and context |
| Reading the parent context report to conclude about a child context | Reports are attached per BeanFactory/context | Inspect the right context id and `getParent()` |
| Value in `application.yml` differs from report so assuming Boot has a bug | Env/CLI/system properties/profiles may be overriding it | Use `/actuator/env/{property.name}` |
| `configprops` shows a default so assuming Environment has the key | A Java object's default may not come from a PropertySource | Compare `env` and `configprops` |
| Property condition matched yet bean is unusable | Another condition or bean creation step may have failed | Check the full source, dependencies, and startup logs |
| Searching for fixed message strings in scripts | Messages are diagnostic text that can change across versions | Rely on source key, condition class, and outcome |

## 11. Standard Investigation Workflow

When a library feature is not auto-configured as expected:

1. **Identify the bean to check** and the auto-configuration/method expected to create that bean.
2. Enable `--debug` or call `GET /actuator/conditions`.
3. Find the source key in the form `FullyQualifiedAutoConfiguration#beanMethod`; inspect all condition outcomes.
4. If `OnPropertyCondition` did not match, call `GET /actuator/env/{property.name}` to identify the final value, source, and origin.
5. If `@ConfigurationProperties` is used, call `GET /actuator/configprops/{prefix}` to compare the bound object.
6. If `OnBeanCondition` did not match, check bean type/name, `SearchStrategy`, context hierarchy, and bean definition registration timing.
7. If all conditions matched yet the application still errors, inspect bean initialization logs and dependencies; the report does not replace stack traces.
8. Record the source, condition, outcome, message, property key, winning PropertySource, and origin in bug reports so the issue can be reproduced.

## 12. Securing Diagnostic Endpoints

`conditions` often contains class names, bean names, and reasons why configurations were enabled/disabled. `env` can expose deployment configuration; `configprops` can reveal bound values. When exposing over HTTP:

- Expose only the endpoints actually needed.
- Restrict access using Spring Security, internal networks, or equivalent governance mechanisms.
- Keep sensitive value sanitization enabled; do not put passwords, tokens, or secrets into logs/debug reports.
- Do not open all Actuator endpoints to the Internet just to look up one condition.
- If you only need one-off debugging, enable `--debug` in a test environment rather than leaving management endpoints exposed long-term.

## 13. Self-Check Questions

**Question 1.** In `getConditionAndOutcomesBySource()`, what does the key `com.acme.ExportAutoConfiguration#exportClient` represent?

**Answer:** The condition source: the `ExportAutoConfiguration` class and the `exportClient` bean method. It is not a configuration file name or a PropertySource.

**Question 2.** To find out whether `acme.export.enabled=true` came from the command line or `application-prod.yml`, which endpoint do you inspect?

**Answer:** `/actuator/env/acme.export.enabled`. The conditions report shows whether the condition matched; the env endpoint shows the property source and origin.

**Question 3.** Does `positiveMatches` prove that the bean instance was instantiated successfully?

**Answer:** No. It proves the condition/source evaluated as a match. Instance creation and dependencies can still fail afterward.

**Question 4.** `negativeMatches` shows a source with one matched condition and one unmatched condition. Is the source considered a full match?

**Answer:** No. `ConditionAndOutcomes.isFullMatch()` is only true when all outcomes in the source match.

**Question 5.** A class is missing from both `positiveMatches` and `negativeMatches`. Can you conclude it was blocked by a property condition?

**Answer:** No. The class may not have been imported/evaluated, may have been excluded, may not be in the candidate list, or you may be viewing the wrong context. Check imports, exclusions, and context first.

## 14. Key Takeaways

- **`ConditionEvaluationReport`** records condition outcomes by source, which is a configuration class or bean method.
- **`getConditionAndOutcomesBySource()`** lets you query each source, iterate conditions, and read `isMatch()/getMessage()`.
- **`--debug`** is the fast way to view the report in logs.
- **`/actuator/conditions`** returns the JSON report by application context, positive matches, and negative matches.
- **`/actuator/env/{property.name}`** is where you look up property values, the winning PropertySource, and origin.
- **`/actuator/configprops/{prefix}`** shows values bound into `@ConfigurationProperties` beans.
- A condition report is not proof that a bean instance initialized successfully; combine it with bean state and runtime logs.

### Official Documentation

- [Spring Boot 3.3 — ConditionEvaluationReport API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Spring Boot 3.3 — ConditionEvaluationReportLoggingListener API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/logging/ConditionEvaluationReportLoggingListener.html)
- [Spring Boot 3.3 — Conditions Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
- [Spring Boot 3.3 — Environment Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/env.html)
- [Spring Boot 3.3 — Configuration Properties Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/configprops.html)
