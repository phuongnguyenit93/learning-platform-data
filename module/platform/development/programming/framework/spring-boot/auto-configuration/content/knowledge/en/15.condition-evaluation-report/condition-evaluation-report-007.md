# The Actuator `/conditions` Endpoint and Per-Context Information Scope

When Spring Boot does not create a bean as expected, or an auto-configuration is skipped, the most important questions are usually: **which conditions were evaluated, which matched, which did not match, and in which context?** Spring Boot Actuator provides the `conditions` endpoint to answer these questions.

The default endpoint path is `GET /actuator/conditions`. It exposes the **Condition Evaluation Report** recorded by Spring Boot while processing configurations and auto-configurations. The report is grouped by **ApplicationContext**: each context has its own set of matching/non-matching conditions and can link to its parent context via `parentId`.

The single most important point of this lesson is: **the report is not a merged JVM-wide bean map**. The endpoint walks from the context hosting the endpoint upward through its parent contexts; each entry in `contexts` describes the condition outcomes of one context. Therefore, to read outcomes accurately, you must identify both the **configuration source** and the **context id**.

## 1. What Is `/actuator/conditions` Used For?

`conditions` is an Actuator endpoint with id `conditions`, implemented by `ConditionsReportEndpoint`, that exposes `ConditionEvaluationReport` as JSON data.

It is useful when investigating:

- Why was an auto-configuration not applied?
- Did `@ConditionalOnClass` find the required library on the classpath?
- Did `@ConditionalOnProperty` read the property and did its value match?
- Which beans did `@ConditionalOnBean` or `@ConditionalOnMissingBean` find?
- Why was a Servlet/WebFlux, database, messaging, or security branch not configured?
- Did a condition match in the application context or in the management context?
- Was an auto-configuration excluded from the processing list?

Example messages in the report might look like:

```text
@ConditionalOnClass found required class 'com.example.Driver'
@ConditionalOnProperty (demo.feature.enabled=true) matched
@ConditionalOnMissingBean (types: com.example.PaymentClient) did not find any beans
OnWebApplicationCondition: not a reactive web application
```

The messages above are **illustrative examples**, not fixed output across all applications. Actual content depends on versions, dependencies, configurations, and which conditions were evaluated.

### Distinguishing from Other Actuator Endpoints

| Endpoint | Which Question Does It Answer? |
| --- | --- |
| `/actuator/conditions` | Why did conditions on a configuration/auto-configuration match or not match? |
| `/actuator/beans` | Which beans are registered in the context, and what are their names and types? |
| `/actuator/env` | Which properties and property sources does the Environment contain? |
| `/actuator/configprops` | How were `@ConfigurationProperties` beans bound from configuration? |
| `/actuator/health` | What is the application's health status and what do contributors report? |

`conditions` explains **configuration decisions**; it does not replace checking bean instances, live properties, or health status. Nor is this endpoint a tool that re-runs every condition on each HTTP request. It presents the outcomes Spring Boot already recorded in `ConditionEvaluationReport`.

## 2. Enabling Actuator and Accessing the Endpoint

### 2.1. Adding the Dependency

With Maven, add the Actuator starter to your Spring Boot application:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

If the application needs HTTP endpoints, it must also include a web stack supported by Spring Boot, such as `spring-boot-starter-web` or `spring-boot-starter-webflux`.

### 2.2. Allowing Exposure Over HTTP

In Spring Boot 3.3, **only the `health` endpoint is exposed over HTTP and JMX by default**. Thus, even with the Actuator dependency present, accessing `/actuator/conditions` can still return `404 Not Found`.

To expose `health` and `conditions`, configure `src/main/resources/application.properties`:

```properties
management.endpoints.web.exposure.include=health,conditions
```

After the application starts, call:

```bash
curl -i http://localhost:8080/actuator/conditions
```

The default path is `/actuator` plus the endpoint id `conditions`. If the application changes `management.endpoints.web.base-path`, uses a separate management port, or changes path mappings, the actual URL will differ.

You can expose via JMX if your management environment uses JMX:

```properties
management.endpoints.jmx.exposure.include=health,conditions
```

`include` is the list of exposed endpoints. If `management.endpoints.web.exposure.exclude` or JMX exclude is present, the exclude list takes precedence over include.

### 2.3. Distinguishing Endpoint Enabled vs. Endpoint Exposed

These two steps are distinct:

- **Enabled:** whether the endpoint is created and added to the ApplicationContext.
- **Exposed:** whether the endpoint is published over HTTP or JMX.

Normally Actuator endpoints are enabled by default. If a project disables all endpoints globally:

```properties
management.endpoints.enabled-by-default=false
management.endpoint.conditions.enabled=true
management.endpoints.web.exposure.include=health,conditions
```

then you must explicitly enable `conditions` and expose it over the desired transport. If an endpoint is disabled, merely adding `conditions` to the exposure list will not make it appear.

### 2.4. Security and Sensitive Data

When `spring-security` is on the classpath and the application does not declare its own `SecurityFilterChain`, Spring Boot protects Actuator endpoints other than `health` by default. Therefore, requests to `/actuator/conditions` may return `401 Unauthorized` or `403 Forbidden` depending on authentication/authorization settings.

If the application declares a custom `SecurityFilterChain`, Actuator's security auto-configuration backs off; the application itself must configure protection for necessary endpoints. Restrict the endpoint to operators or a management network.

Do not expose `conditions` publicly. The report can reveal:

- Internal package, class, and configuration method names.
- Bean names and bean types found by conditions.
- Property keys, expected values, and reasons properties did not match.
- Libraries/classes present on or absent from the classpath.
- Configuration details of active integrations.

If you get `404`, check dependencies, endpoint enabled status, exposure include/exclude, and management base path. If you get `401/403`, check security. If the endpoint does not exist in a non-web application, view the report via `--debug` logs or JMX instead of HTTP.

## 3. Reading the JSON Response Structure

The response has a root `contexts` object. The keys inside are **ApplicationContext ids**. Each entry is a `ContextConditionsDescriptor`.

Abbreviated example:

```json
{
  "contexts": {
    "application": {
      "positiveMatches": {
        "com.example.ClientAutoConfiguration#client": [
          {
            "condition": "OnClassCondition",
            "message": "@ConditionalOnClass found required class 'com.example.Client'"
          }
        ]
      },
      "negativeMatches": {
        "com.example.CacheAutoConfiguration": {
          "notMatched": [
            {
              "condition": "OnPropertyCondition",
              "message": "Property 'demo.cache.enabled' did not match"
            }
          ],
          "matched": [
            {
              "condition": "OnClassCondition",
              "message": "Required cache API was found"
            }
          ]
        }
      },
      "unconditionalClasses": [
        "com.example.BaseInfrastructureAutoConfiguration"
      ],
      "exclusions": [],
      "parentId": null
    }
  }
}
```

This is structural illustrative JSON, abbreviated and using hypothetical class names. Depending on the context and evaluation results, some collections may be empty or omit entries.

### 3.1. `contexts`

`contexts` is a map of contexts keyed by id. Do not hard-code that the key is always `application`: names can differ when the application assigns custom ids or uses a context hierarchy. Read the actual keys in the response.

### 3.2. `positiveMatches`

`positiveMatches` contains configuration classes or bean methods whose **associated conditions matched**. Each key is an evaluated source:

- Class name only: conditions placed on the configuration class.
- `ClassName#methodName`: conditions attached to the `@Bean` method or corresponding method source.

Each source can have multiple conditions; each element provides:

- `condition`: condition name, usually in forms like `OnClassCondition`, `OnPropertyCondition`, `OnBeanCondition`, `OnWebApplicationCondition`.
- `message`: explanation of why that condition matched.

A source with multiple conditions only appears in positive matches when the required conditions of the source matched. Read all messages to see whether it matched due to classpath, property, bean, or web application type.

### 3.3. `negativeMatches`

`negativeMatches` contains configuration sources with **at least one condition that did not match**. Each source has two groups:

- `notMatched`: unmatched conditions, with reasons.
- `matched`: other conditions within the same source that matched.

This is especially useful for combined or nested conditions. A configuration may find its required class yet still not apply because a property has the wrong value. In that case, `matched` shows that the classpath check passed, while `notMatched` pinpoints the blocking cause.

Example:

```json
{
  "negativeMatches": {
    "com.example.RedisAutoConfiguration": {
      "notMatched": [
        {
          "condition": "OnPropertyCondition",
          "message": "Property 'app.redis.enabled' did not match"
        }
      ],
      "matched": [
        {
          "condition": "OnClassCondition",
          "message": "Redis client class was found"
        }
      ]
    }
  }
}
```

How to read it: the Redis client class is on the classpath, but the enabling property is incorrect so the Redis configuration is not applied. Do not just see a key in `negativeMatches` and conclude every condition on the class failed.

### 3.4. `unconditionalClasses`

This is the list of auto-configuration class names **with no conditions to evaluate** recorded in that context's report. It does not mean the beans inside were guaranteed to be instantiated or that every method succeeded. It is information about recorded unconditional configuration classes.

### 3.5. `exclusions`

When present, `exclusions` lists the auto-configuration classes that were excluded. For example, excluded via `@SpringBootApplication(exclude = …)` or `spring.autoconfigure.exclude`. An excluded class differs from a class that was evaluated and had an unmatched condition:

- **Excluded:** the class was removed from the auto-configuration application process.
- **Negative match:** the class was evaluated, and at least one condition did not match.

### 3.6. `parentId`

`parentId` is the id of the **parent ApplicationContext** if the current context has a parent. If there is no parent, the value is typically `null`.

It is a context structure link, not a statement that all beans in the parent were merged into the child's report. Each entry still describes the condition outcomes of its corresponding context.

## 4. Per-ApplicationContext Report Scope

This is the easiest part of the endpoint to misread.

`ConditionsReportEndpoint` is constructed with a `ConfigurableApplicationContext`. When generating the report, the endpoint walks from the context hosting the endpoint **up through each parent context** until no parent remains. Therefore:

1. The context hosting the endpoint is always the starting point.
2. Each parent context is added as a separate entry in `contexts`.
3. `parentId` lets you trace the context chain.
4. Child contexts, sibling contexts, or another independent context not on the endpoint's ancestor chain **do not automatically appear** in that report.

In other words, the scope is **the current context and its ancestors**, not the entire tree in both directions.

### 4.1. Parent and Child Example

Suppose the context structure is:

```text
application-context
       |
       v
management-context
       |
       v
monitoring-child
```

If the endpoint is served from `management-context`, its report will include `management-context` and `application-context`. It will not automatically list `monitoring-child` because that is a child of the context hosting the endpoint.

If the endpoint is served from `monitoring-child`, the report can trace back `monitoring-child` → `management-context` → `application-context`.

If the endpoint resides in `application-context`, that endpoint's report does not automatically descend into the management context or other child contexts.

### 4.2. Separate Management Port Case

When Actuator is configured to run on a management port different from the main server port, Spring Boot may create a **separate management context** in a parent/child relationship with the application context. In that setup, an endpoint served from the management context can return a report containing:

- An entry for the management context, where the endpoint lives.
- An entry for the parent application context, where the main application configuration is processed.
- `parentId` linking the management context to the application context.

Specific id names depend on how contexts are initialized; do not assume there are always exactly two keys or that names are always `management` and `application`. Inspect the actual response.

### 4.3. Can a Child Context Condition See Beans from the Parent?

This is a separate question from report scope.

Each entry stores the condition outcomes of its corresponding BeanFactory/context. However, **a specific condition can be configured to search for beans in the parent context**. For instance, a Boot condition may use a search strategy that includes beans in ancestor contexts. The message sometimes explicitly notes `SearchStrategy: all` or the corresponding search strategy.

Therefore, separate two questions:

- **In which context was the condition evaluated?** Look at the key in `contexts` and the `parentId` relationship.
- **In which scope did the condition search for beans?** Look at the condition message, bean type, bean name, and search strategy.

A child context can record its own condition while that condition still sees beans supplied by the parent if the search strategy allows it. The report is not a merged bean list between parent and child.

### 4.4. Independent or Sibling Contexts

Two applications running side by side or two child contexts sharing a single parent do not both appear in full inside a report served from an endpoint on one branch. The endpoint only walks the current context and its parents. To view the other branch, query the report served in that branch's context or capture the report separately from that context itself.

## 5. Workflow for Diagnosing an Auto-Configuration

When a bean does not appear, read the report in this order:

1. **Identify the context id.** Check `contexts` and `parentId` first. Do not conclude a condition failed if you are looking at the wrong context.
2. **Find the source class or method.** For example `DataSourceAutoConfiguration` or `DataSourceAutoConfiguration#dataSource`. If not found, check whether the class was loaded/included in the auto-configuration list.
3. **If in `positiveMatches`:** read each condition and message to understand why the configuration was applied.
4. **If in `negativeMatches`:** read `notMatched` first to identify the blocking condition; then read `matched` to see which parts already passed.
5. **Check exclusions.** If the class was excluded, investigate where the exclusion was declared before changing properties or classpath.
6. **Verify property/classpath/bean.** Check property keys, values, dependencies, bean types, bean names, and corresponding web stack conditions.
7. **Cross-check actual beans if needed.** Use `/actuator/beans` to view registered beans; use `/actuator/env` or `/actuator/configprops` when verifying configuration, keeping security in mind.
8. **Write an isolated test.** `ApplicationContextRunner` lets you swap properties, user configurations, and auto-configurations to reproduce the exact condition branch.

### Some Common Scenarios

| Symptom | Where to Check | Remediation |
| --- | --- | --- |
| Class appears in `negativeMatches` with `OnClassCondition` | `notMatched` message | Add the right dependency or check class name/version/optional dependency. |
| `OnPropertyCondition` does not match | Property key and expected value | Check profile, config source, spelling, `havingValue`, and `matchIfMissing`. |
| `OnBeanCondition` reports no bean found | Bean type/name and search strategy | Check whether the bean is registered before the condition runs, has the right type/interface, and lives in a parent context. |
| `OnWebApplicationCondition` does not match | Running context type | Identify whether the app is Servlet, Reactive, or non-web; classpath alone does not dictate context type. |
| Auto-configuration missing from both positive and negative | Candidate list and exclusions | Check starters, auto-configuration imports file, exclusions, and classpath. |
| Condition matched yet bean missing in `/actuator/beans` | Method source and initialization errors | Check the bean method, startup exceptions, and context id. |
| Management outcomes differ from application | `contexts`, `parentId` | Inspect each context's report separately; do not merge the two outcomes into one. |

### The Report Does Not Explain Every Bean Initialization Failure

A matched condition only indicates **that conditions allowed the configuration/bean definition to be processed**. It does not guarantee the bean instance was created successfully. The bean can still encounter constructor, dependency, post-processor, or resource connection failures afterward. When the report shows conditions matched yet the application still lacks the expected bean, inspect startup exceptions, `/actuator/beans`, and the dependency graph.

## 6. Runnable Example: Spring Boot 3.3.5, Java 17, and JUnit 5

The example includes two tests:

- Verifies the HTTP endpoint returns the report and explains why a configuration failed a property condition.
- Creates a parent context and a child context to verify that the report built from the child includes both child and ancestor entries, whereas the report built from the parent does not descend into the child.

### 6.1. Project Structure

```text
conditions-report-demo/
├── pom.xml
└── src/
    └── test/
        └── java/
            └── demo/
                └── ConditionsEndpointIntegrationTest.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>conditions-report-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

### 6.2. Complete Test Code

Create `src/test/java/demo/ConditionsEndpointIntegrationTest.java`:

```java
package demo;

import com.fasterxml.jackson.databind.JsonNode;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.actuate.autoconfigure.condition.ConditionsReportEndpoint;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ConditionsEndpointIntegrationTest.DemoApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
        properties = {
                "management.endpoints.web.exposure.include=health,conditions",
                "demo.feature.enabled=false"
        }
)
class ConditionsEndpointIntegrationTest {

    @Autowired
    private TestRestTemplate http;

    @Test
    void endpointReportsWhyFeatureConfigurationDidNotMatch() {
        ResponseEntity<JsonNode> response =
                http.getForEntity("/actuator/conditions", JsonNode.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);

        JsonNode body = response.getBody();
        assertThat(body).isNotNull();

        JsonNode contexts = body.path("contexts");
        assertThat(contexts.isObject()).isTrue();
        assertThat(contexts.isEmpty()).isFalse();

        String source = FeatureConfiguration.class.getName();
        boolean foundReason = false;

        var reports = contexts.elements();
        while (reports.hasNext()) {
            JsonNode negativeMatches =
                    reports.next().path("negativeMatches");
            JsonNode feature = negativeMatches.path(source);

            if (!feature.isMissingNode()) {
                foundReason = feature.path("notMatched")
                        .toString()
                        .contains("demo.feature.enabled");
            }
        }

        assertThat(foundReason).isTrue();
    }

    @Test
    void endpointReportContainsItsContextAndAncestorsOnly() {
        try (AnnotationConfigApplicationContext parent =
                     new AnnotationConfigApplicationContext();
             AnnotationConfigApplicationContext child =
                     new AnnotationConfigApplicationContext()) {

            parent.setId("parent-context");
            parent.refresh();

            child.setId("child-context");
            child.setParent(parent);
            child.refresh();

            var childContexts =
                    new ConditionsReportEndpoint(child)
                            .conditions()
                            .getContexts();

            assertThat(childContexts.keySet())
                    .containsExactlyInAnyOrder(
                            "child-context",
                            "parent-context"
                    );

            assertThat(childContexts.get("child-context").getParentId())
                    .isEqualTo("parent-context");

            assertThat(childContexts.get("parent-context").getParentId())
                    .isNull();

            var parentContexts =
                    new ConditionsReportEndpoint(parent)
                            .conditions()
                            .getContexts();

            assertThat(parentContexts.keySet())
                    .containsExactly("parent-context");
        }
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import(FeatureConfiguration.class)
    static class DemoApplication {
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "demo.feature",
            name = "enabled",
            havingValue = "true"
    )
    static class FeatureConfiguration {

        @Bean
        String featureMarker() {
            return "enabled";
        }
    }
}
```

Run from the `conditions-report-demo` directory using JDK 17+ and Maven:

```bash
mvn test
```

**Expected result:** both tests pass.

- The HTTP test receives `200 OK` and finds the `FeatureConfiguration` source in `negativeMatches`; the message in `notMatched` explains that property `demo.feature.enabled` did not match because the test set `false` while the condition requires `true`.
- The context hierarchy test confirms that an endpoint created from `child-context` returns two entries, `child-context` and `parent-context`; the child's `parentId` points to the parent. When the endpoint is created from the parent, the report contains only the parent and does not descend into the child.

The test suite uses `ConditionsReportEndpoint` directly in the second test to verify context scope without spinning up two web servers. The first test verifies HTTP exposure and actual report contents of a Boot application. The tests print no business stdout; embedded server and Maven startup logs may vary by environment.

### 6.3. Modifying the Property Yourself to Observe the Report

Change the test property:

```properties
demo.feature.enabled=true
```

Then `FeatureConfiguration` can match and the source moves to `positiveMatches`, while the `featureMarker` bean is registered. If you want to verify the bean instance, you can also inspect `/actuator/beans` or inject the bean in tests; do not rely solely on the condition report to claim a bean initialized successfully.

## 7. When You Do Not Want to Expose the HTTP Endpoint

You can view the Condition Evaluation Report via logs by starting the application with:

```bash
java -jar app.jar --debug
```

`--debug` enables auto-configuration report logging during startup. This is useful in local environments or when HTTP endpoints are not exposed.

In auto-configuration tests, Spring Boot also offers `ConditionEvaluationReportLoggingListener`. Example:

```java
ApplicationContextRunner runner = new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO
                )
        )
        .withConfiguration(
                AutoConfigurations.of(MyFeatureAutoConfiguration.class)
        );
```

This is a **snippet** to place inside a test class, with corresponding imports from Spring Boot Test and Logback. `ApplicationContextRunner` creates an isolated context; the listener writes the report at the chosen log level. This is convenient when you want to see why a test context did not apply an auto-configuration without running an HTTP server.

## 8. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| “Having Actuator means `/actuator/conditions` is immediately accessible.” | By default HTTP only exposes `health`; you must include `conditions`. |
| “`negativeMatches` means every condition in the class failed.” | Only one condition needs to fail; inspect `notMatched` and `matched` to tell them apart. |
| “`positiveMatches` proves the bean instance was created.” | It proves the source's conditions matched; instance creation can still fail afterward. |
| “`contexts` is every ApplicationContext in the JVM.” | It is the context chain starting from the context hosting the endpoint and walking up through parent contexts. |
| “An endpoint on the parent lists all children.” | No. The report does not automatically descend into child or sibling contexts. |
| “`parentId` is the parent bean name.” | It is the id of the parent ApplicationContext. |
| “Two contexts merge condition outcomes because they share beans.” | Each entry has its own report; a specific condition may look up beans in ancestors if its search strategy allows. |
| “A class missing from negative matches means its conditions matched.” | The class may not be a candidate, was excluded, or was not loaded; check `exclusions` and auto-configuration sources. |
| “GET on the endpoint re-runs all conditions.” | The endpoint serializes the report already recorded during configuration processing. |
| “`conditions` is the same as `beans`.” | Conditions explain configuration decisions; `beans` lists registered beans. |
| “Enabling include already secures the endpoint.” | Exposure does not replace authentication/authorization or a firewall. |

## 9. Quick Report Reading Checklist

When opening `/actuator/conditions`, go in order:

1. Identify the context key and `parentId`.
2. Locate the class or method to investigate.
3. If in `positiveMatches`, read the messages to see why it matched.
4. If in `negativeMatches`, read `notMatched` first, then compare with `matched`.
5. Check `exclusions` if the auto-configuration was not evaluated.
6. Cross-check properties, classpath, bean name/type, and web application type.
7. If conditions matched yet the bean is still missing, check `/actuator/beans` and initialization errors.
8. If the context hierarchy has multiple tiers, read each entry by `parentId` and remember the report only walks from the endpoint's context up to its parents.

**Remember:** `/actuator/conditions` is a window into **why conditions matched or did not match**. Read `positiveMatches`, `negativeMatches`, `unconditionalClasses`, `exclusions`, and especially `contexts`/`parentId`. Knowing which context the endpoint runs in and which ancestors the report includes prevents wrong conclusions when the application context and management context are configured differently.

### Official References

- Spring Boot 3.3 — Conditions Evaluation Report API: https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html
- Spring Boot 3.3 — Actuator Endpoints: https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html
- Spring Boot 3.3 API — `ConditionsReportEndpoint`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/condition/ConditionsReportEndpoint.html
- Spring Boot 3.3 API — `ConditionEvaluationReport`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.3 — Creating Your Own Auto-configuration and `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html