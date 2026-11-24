# Building ConditionMessage and Reporting Specific Missing Conditions

## 1. Why Does a Custom Condition Need Clear Messages?

Auto-configuration often registers beans only when multiple conditions are simultaneously satisfied: a property is enabled, an optional library is on the classpath, a prerequisite bean already exists, or the application is running in the right context type. When a condition is not met, the bean may not appear even though the application still starts normally.

A generic message like:

~~~text
Condition did not match
~~~

does not help developers know what needs to be fixed. A good message should point out **which condition is missing**, for example:

~~~text
Acme Reports readiness did not find required prerequisites
'property acme.reports.enabled is not set',
'non-blank property acme.reports.endpoint',
'class com.example.sdk.ReportSdk on the runtime classpath'
~~~

Readers can act immediately: enable the property, declare the endpoint, or add the dependency containing the SDK.

Spring Boot provides three cooperating components for this:

- **ConditionMessage**: builds a sentence describing the result in a consistent format.
- **ConditionOutcome**: carries the match/no-match result along with the message.
- **SpringBootCondition**: the base class for writing custom conditions using Spring Boot's logging and Condition Evaluation Report recording.

This lesson uses **Java 17 and Spring Boot 3.3.13** as an illustrative baseline. Align versions with your application's actual release line when applying it.

## 2. Distinguishing Condition, ConditionMessage, ConditionOutcome, and ConditionEvaluationReport

These APIs have distinct responsibilities:

| Component | Role |
| --- | --- |
| Condition | Spring's contract for deciding whether a configuration is applied |
| SpringBootCondition | Spring Boot's base class, supporting logging and recording condition results |
| ConditionMessage | Content explaining why the condition matched or did not match |
| ConditionOutcome | Boolean match or noMatch result, accompanied by a ConditionMessage |
| ConditionEvaluationReport | Collection of condition results grouped by class or bean method |

A ConditionMessage **does not itself decide** whether a bean is created. The boolean inside ConditionOutcome makes that decision. The message explains the result for logs and reports.

High-level flow:

~~~text
Spring encounters @Conditional(MyCondition.class)
                  |
                  v
SpringBootCondition.getMatchOutcome(...)
                  |
          +-------+-------+
          |               |
          v               v
ConditionOutcome.match   ConditionOutcome.noMatch
          |               |
          +-------+-------+
                  |
                  v
ConditionEvaluationReport stores outcome
                  |
                  v
Log / --debug / Actuator conditions
~~~

If a custom condition returns noMatch, the annotated bean method or configuration will not be applied. Spring Boot can still start normally if no other mandatory dependency causes an error.

## 3. The ConditionMessage API

The class resides in package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionMessage
~~~

ConditionMessage provides a fluent builder to construct explanatory sentences. Some commonly used factories/methods:

| API | Purpose |
| --- | --- |
| ConditionMessage.forCondition(...) | Starts a message for a condition |
| ConditionMessage.of(...) | Creates a message directly from a string/format |
| builder.foundExactly(...) | Describes a specific found result |
| builder.found(...) | Describes one or more found items |
| builder.didNotFind(...) | Describes missing items or prerequisites |
| items(...) | Adds a list of items into the message |
| atAll() | Expresses that no items were found |
| because(...) | States a specific reason |
| available(...) / notAvailable(...) | Expresses availability status |

### 3.1. Starting with forCondition

Example:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition("Acme Reports");
~~~

You can use a string condition name as a readable label. There is also an overload accepting an annotation class:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(ConditionalOnProperty.class);
~~~

The class overload is suitable when the message explains a specific condition annotation. For a custom condition without its own annotation, a string name like "Acme Reports readiness" is often clearer.

You can pass additional details:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(
                "Acme Reports readiness", "acme.reports");
~~~

### 3.2. Using didNotFind to State Missing Conditions

If one prerequisite is missing:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .didNotFind("required bean")
        .items(ConditionMessage.Style.QUOTE, "reportTransport");
~~~

If multiple prerequisites are missing:

~~~java
List<String> missing = List.of(
        "acme.reports.enabled must be true",
        "non-blank property acme.reports.endpoint");

ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports readiness")
        .didNotFind("required prerequisite", "required prerequisites")
        .items(ConditionMessage.Style.QUOTE, missing);
~~~

Style.QUOTE helps distinguish items in the list. didNotFind(singular, plural) lets the builder pick singular or plural phrasing.

If no items were found at all:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .didNotFind("required class")
        .atAll();
~~~

### 3.3. Using found When Prerequisites Are Present

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .found("required class", "required classes")
        .items(
                ConditionMessage.Style.QUOTE,
                "com.example.sdk.ReportSdk",
                "com.example.sdk.ReportTransport");
~~~

Or for a single result:

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .foundExactly("all required prerequisites");
~~~

### 3.4. Using because for Reasons

~~~java
ConditionMessage message = ConditionMessage
        .forCondition("Acme Reports")
        .because("the endpoint property is blank");
~~~

This message is helpful when you need to describe a specific cause or state rather than only listing missing items.

### 3.5. ConditionMessage.of for Simple Messages

~~~java
ConditionMessage message = ConditionMessage.of(
        "property '%s' must be set",
        "acme.reports.endpoint");
~~~

This works well for a single simple sentence. When there are multiple prerequisites, the builder is usually easier to extend and more consistent.

## 4. ConditionOutcome Decides Match or No-Match

ConditionOutcome resides in package:

~~~java
org.springframework.boot.autoconfigure.condition.ConditionOutcome
~~~

Create a match result:

~~~java
return ConditionOutcome.match(message);
~~~

Create a no-match result:

~~~java
return ConditionOutcome.noMatch(message);
~~~

There is an overload accepting a string, but once you have built a ConditionMessage, pass that object directly:

~~~java
ConditionOutcome.noMatch(
        ConditionMessage.of("required endpoint is missing"));
~~~

Do not just return ConditionOutcome.noMatch() with an empty message if the goal is to help users diagnose issues. A custom condition should return a reason specific enough for readers to know which property, class, or prerequisite needs to be added.

## 5. Why Should You Extend SpringBootCondition?

Spring Framework defines the Condition interface with the method:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

If you implement this interface directly, the method only returns a boolean. There is no standard way to return a ConditionOutcome containing a message.

Spring Boot provides the abstract class:

~~~java
org.springframework.boot.autoconfigure.condition.SpringBootCondition
~~~

A custom condition extends this class and implements:

~~~java
@Override
public ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {
    // Check prerequisites and return match/noMatch with a message.
}
~~~

Spring Boot manages integrating the condition with logging and the Condition Evaluation Report. Therefore, when you need diagnostic messages for a custom condition, prefer SpringBootCondition.

Do not write System.out.println or log manually and then return a boolean. Doing so makes it hard to tie information to the condition result, may cause duplication, and will not appear properly structured in the report.

## 6. Custom Condition Example: Listing All Missing Prerequisites

We will build an auto-configuration that creates ReportClient when three conditions are met:

1. acme.reports.enabled=true.
2. acme.reports.endpoint has a non-blank value.
3. Optional class com.example.sdk.ReportSdk is on the runtime classpath.

The goal is that if multiple conditions are missing simultaneously, the report must list **all causes** instead of only reporting the first one.

### 6.1. Project Structure

~~~text
condition-message-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/example/reports/
    │       ├── ReportClient.java
    │       └── autoconfigure/
    │           ├── ReportsAutoConfiguration.java
    │           └── ReportsReadyCondition.java
    └── test/
        └── java/
            ├── com/example/reports/autoconfigure/
            │   └── ReportsReadyConditionTests.java
            └── com/example/sdk/
                └── ReportSdk.java
~~~

Class ReportSdk is only a test fixture simulating an optional SDK. In a real library, that class resides in an external dependency and might not appear on the runtime classpath.

### 6.2. pom.xml

~~~xml
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
    <groupId>com.example</groupId>
    <artifactId>condition-message-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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

The Spring Boot parent manages the version of spring-boot-autoconfigure. The starter test provides JUnit, AssertJ, ApplicationContextRunner, and FilteredClassLoader.

### 6.3. ReportClient.java

**src/main/java/com/example/reports/ReportClient.java**

~~~java
package com.example.reports;

public record ReportClient(String endpoint) {
}
~~~

The bean merely holds the endpoint to demonstrate the auto-configuration result; it does not send network requests.

### 6.4. ReportsReadyCondition.java

**src/main/java/com/example/reports/autoconfigure/ReportsReadyCondition.java**

~~~java
package com.example.reports.autoconfigure;

import java.util.ArrayList;
import java.util.List;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionMessage.Style;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;
import org.springframework.util.StringUtils;

public final class ReportsReadyCondition extends SpringBootCondition {

    private static final String ENABLED_PROPERTY =
            "acme.reports.enabled";

    private static final String ENDPOINT_PROPERTY =
            "acme.reports.endpoint";

    private static final String SDK_CLASS =
            "com.example.sdk.ReportSdk";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        List<String> missing = new ArrayList<>();

        String enabled = context.getEnvironment()
                .getProperty(ENABLED_PROPERTY);

        if (!"true".equalsIgnoreCase(enabled)) {
            if (enabled == null) {
                missing.add(
                        "property " + ENABLED_PROPERTY + " is not set");
            }
            else {
                missing.add(
                        "property " + ENABLED_PROPERTY + " must be true");
            }
        }

        String endpoint = context.getEnvironment()
                .getProperty(ENDPOINT_PROPERTY);

        if (!StringUtils.hasText(endpoint)) {
            missing.add(
                    "non-blank property " + ENDPOINT_PROPERTY);
        }

        if (!ClassUtils.isPresent(SDK_CLASS, context.getClassLoader())) {
            missing.add(
                    "class " + SDK_CLASS + " on the runtime classpath");
        }

        ConditionMessage.Builder message =
                ConditionMessage.forCondition("Acme Reports readiness");

        if (!missing.isEmpty()) {
            ConditionMessage details = message
                    .didNotFind(
                            "required prerequisite",
                            "required prerequisites")
                    .items(Style.QUOTE, missing);

            return ConditionOutcome.noMatch(details);
        }

        ConditionMessage details =
                message.foundExactly("all required prerequisites");

        return ConditionOutcome.match(details);
    }
}
~~~

How it works:

- Reads properties via Environment without starting services or creating beans in the condition.
- Uses StringUtils.hasText to treat null, empty strings, and whitespace-only strings as a missing endpoint.
- Uses ClassUtils.isPresent with a String class name to check the optional dependency without creating a compile-time reference to the SDK.
- Collects all reasons into the missing list.
- If the list has elements, builds a message with didNotFind(...).items(...) and returns ConditionOutcome.noMatch.
- If no condition is missing, returns ConditionOutcome.match with a confirming message.

Because the condition does not directly reference ReportSdk.class, the library can still compile when the optional SDK is not a compile-time dependency. This is the right pattern when the checked class may be absent at runtime.

### 6.5. ReportsAutoConfiguration.java

**src/main/java/com/example/reports/autoconfigure/ReportsAutoConfiguration.java**

~~~java
package com.example.reports.autoconfigure;

import com.example.reports.ReportClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class ReportsAutoConfiguration {

    @Bean
    @Conditional(ReportsReadyCondition.class)
    ReportClient reportClient(Environment environment) {
        return new ReportClient(
                environment.getRequiredProperty("acme.reports.endpoint"));
    }
}
~~~

Conditional attaches the custom condition to the bean method. If the condition returns noMatch, the reportClient method does not register the bean.

Environment is injected into the method only after the condition has matched. getRequiredProperty helps detect missing configuration if unexpected changes occur between condition evaluation and bean creation.

## 7. Viewing Messages in the Condition Evaluation Report

Spring Boot records condition outcomes by source, typically the configuration class name or bean method. In this example, the method source looks like:

~~~text
com.example.reports.autoconfigure.ReportsAutoConfiguration#reportClient
~~~

If properties and the SDK are missing, the Negative matches section will contain a message listing the unmet prerequisites. Wording is formatted by ConditionMessage; do not rely on exact punctuation strings of a specific version.

Illustrative example of the meaning:

~~~text
Negative matches:
   ReportsAutoConfiguration#reportClient
      - ReportsReadyCondition:
        Acme Reports readiness did not find required prerequisites
        'property acme.reports.enabled is not set',
        'non-blank property acme.reports.endpoint'
~~~

If the SDK is also absent, the list will additionally include:

~~~text
'class com.example.sdk.ReportSdk on the runtime classpath'
~~~

This is a shortened illustrative output. Actual contents also depend on how the report logger renders them and the Spring Boot version.

### 7.1. Enabling the Report When Running the Application

To see all auto-configuration decisions:

~~~bash
java -jar target/condition-message-demo-1.0.0.jar --debug
~~~

Or:

~~~properties
debug=true
~~~

ConditionMessage is still built and conditions are still evaluated when debug is not enabled. Debug mode prints the condition report in the startup logs.

### 7.2. Printing the Report in Tests with ConditionEvaluationReportLoggingListener

Spring Boot includes a listener to print the report directly in tests:

~~~java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener.forLogLevel(
                        LogLevel.INFO))
        .run(context -> {
            // Test assertions
        });
~~~

This is helpful when investigating why a condition did not match. There is no need to add manual logging inside the custom condition.

### 7.3. Reading the Report via Actuator

If the application has Spring Boot Actuator and the endpoint is appropriately exposed, you can query:

~~~text
GET /actuator/conditions
~~~

The endpoint provides the condition report as JSON. --debug does not automatically add the Actuator dependency or expose the endpoint. In production, expose only necessary endpoints and protect access permissions.

## 8. Testing Both the Outcome and the Message Content

Tests should verify two things:

1. The bean is present or absent according to the prerequisites.
2. The Condition Evaluation Report contains the specific property/class names so readers know what to fix.

### 8.1. Test Fixture for the Optional SDK

**src/test/java/com/example/sdk/ReportSdk.java**

~~~java
package com.example.sdk;

public final class ReportSdk {
}
~~~

This class is on the test runtime classpath so positive tests can satisfy the SDK condition. Another test will use FilteredClassLoader to simulate a missing SDK.

### 8.2. ReportsReadyConditionTests.java

**src/test/java/com/example/reports/autoconfigure/ReportsReadyConditionTests.java**

~~~java
package com.example.reports.autoconfigure;

import java.util.ArrayList;
import java.util.List;

import com.example.reports.ReportClient;
import com.example.sdk.ReportSdk;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcome;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport.ConditionAndOutcomes;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.test.util.FilteredClassLoader;

import static org.assertj.core.api.Assertions.assertThat;

class ReportsReadyConditionTests {

    private static final String CONDITION_SOURCE =
            ReportsAutoConfiguration.class.getName() + "#reportClient";

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    ReportsAutoConfiguration.class));

    @Test
    void createsClientWhenEveryPrerequisiteIsPresent() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.endpoint=https://reports.example.test")
                .run(context -> {
                    assertThat(context).hasSingleBean(ReportClient.class);
                    assertThat(context.getBean(ReportClient.class).endpoint())
                            .isEqualTo("https://reports.example.test");

                    assertThat(conditionMessages(context))
                            .anyMatch(message ->
                                    message.contains(
                                            "all required prerequisites"));
                });
    }

    @Test
    void listsEveryMissingPrerequisite() {
        runner.run(context -> {
            assertThat(context).doesNotHaveBean(ReportClient.class);

            String messages = String.join("\n", conditionMessages(context));

            assertThat(messages)
                    .contains("acme.reports.enabled")
                    .contains("acme.reports.endpoint");
        });
    }

    @Test
    void explainsWhenEnabledPropertyIsFalse() {
        runner.withPropertyValues(
                "acme.reports.enabled=false",
                "acme.reports.endpoint=https://reports.example.test")
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    String messages =
                            String.join("\n", conditionMessages(context));

                    assertThat(messages)
                            .contains("acme.reports.enabled")
                            .contains("must be true");
                });
    }

    @Test
    void explainsWhenOptionalSdkIsMissing() {
        runner.withPropertyValues(
                "acme.reports.enabled=true",
                "acme.reports.endpoint=https://reports.example.test")
                .withClassLoader(new FilteredClassLoader(ReportSdk.class))
                .run(context -> {
                    assertThat(context).doesNotHaveBean(ReportClient.class);

                    String messages =
                            String.join("\n", conditionMessages(context));

                    assertThat(messages)
                            .contains("com.example.sdk.ReportSdk");
                });
    }

    private List<String> conditionMessages(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(
                        context.getSourceApplicationContext().getBeanFactory());

        ConditionAndOutcomes outcomes =
                report.getConditionAndOutcomesBySource()
                        .get(CONDITION_SOURCE);

        assertThat(outcomes).isNotNull();

        List<String> messages = new ArrayList<>();

        for (ConditionAndOutcome item : outcomes) {
            messages.add(item.getOutcome().getMessage());
        }

        return messages;
    }
}
~~~

The tests retrieve the report from the context's bean factory and read the outcome at the exact bean method. This verifies the message content returned by the condition instead of only checking that the bean does not exist.

### 8.3. Running the Tests

~~~bash
mvn clean test
~~~

Expect **four passing tests**:

| Test | Expected result |
| --- | --- |
| Properties and SDK present | Exactly one ReportClient |
| Missing properties | No bean; message lists enabled and endpoint |
| enabled=false | No bean; message states enabled must be true |
| Missing SDK | No bean; message names the SDK class |

If the test cannot find the report source, check whether the source key matches the fully qualified configuration class name plus #reportClient. If the bean exists when prerequisites are missing, check that Conditional is placed on the method and that the runner loads the right auto-configuration.

## 9. Combining ConditionMessage with Built-In Conditions

Do not write custom conditions for every case. Spring Boot already provides common conditions with helpful messages:

| Need | Annotation to prefer |
| --- | --- |
| A class must be on the classpath | @ConditionalOnClass |
| A property must exist/have a specific value | @ConditionalOnProperty |
| A bean must exist | @ConditionalOnBean |
| Create a default when no bean exists yet | @ConditionalOnMissingBean |
| Run only in a servlet/reactive web context | @ConditionalOnWebApplication |
| Run only when a resource exists | @ConditionalOnResource |
| Run only with a single identifiable candidate | @ConditionalOnSingleCandidate |

Example using built-in conditions:

~~~java
@Bean
@ConditionalOnClass(ReportSdk.class)
@ConditionalOnProperty(
        prefix = "acme.reports",
        name = "enabled",
        havingValue = "true")
@ConditionalOnMissingBean(ReportClient.class)
ReportClient reportClient() {
    return new ReportClient("https://reports.example.test");
}
~~~

These annotations already produce dedicated messages for classes/properties/beans. If your need is just checking standard individual conditions, a custom SpringBootCondition is unnecessary.

A custom condition is useful when:

- A rule combines multiple prerequisites and you want to report all missing items.
- The condition needs a specialized check without a corresponding annotation.
- You need a clear business reason for the match/no-match decision.
- You need to inspect combined state from Environment and classpath.

If you only need to check multiple independent conditions, you can stack multiple built-in annotations instead of writing one large condition. Doing so often lets the report identify the exact annotation that did not match.

## 10. Writing High-Quality Diagnostic Messages

A good message should follow these guidelines.

### 10.1. State the Full Name of the Prerequisite

Good:

~~~text
property acme.reports.endpoint is not set
~~~

Poor:

~~~text
configuration missing
~~~

For classes, use the fully qualified class name so users know which dependency to look for.

### 10.2. State the Condition and Required Action

Good:

~~~text
property acme.reports.enabled must be true
~~~

Poor:

~~~text
feature unavailable
~~~

The message should indicate the expected state, not merely repeat the feature name.

### 10.3. Report All Missing Conditions When Helpful

If a condition has three independent prerequisites, collect them into a list so the user can fix them in one pass. However, if a later condition only makes sense when an earlier one holds, returning the first cause can avoid misleading messages.

### 10.4. Do Not Expose Secrets

Do not put passwords, tokens, API keys, or sensitive configuration values into ConditionMessage. Record the property name and state:

~~~text
property acme.reports.api-key is not set
~~~

Do not log the API key value present in Environment. Condition reports can appear in logs, management endpoints, or log aggregation systems.

### 10.5. Keep Messages Stable Without Testing Full Sentences

Messages are a diagnostic tool and should not become a machine-readable API unless the library explicitly commits to that contract. Tests should verify key tokens such as property keys, class names, and reasons rather than comparing verbatim full sentences that may vary across Spring Boot formatting changes.

## 11. What Not to Do Inside a Custom Condition

Conditions may be evaluated during configuration processing and can run multiple times depending on context structure. Therefore:

- Do not create database connections, HTTP clients, or threads inside a condition.
- Do not instantiate a bean just to check whether the bean exists.
- Do not perform file writes, API calls, or state mutations.
- Do not rely on the order in which bean instances were created.
- Do not log raw Environment or full configurations that may contain secrets.
- Do not swallow exceptions and return match as if everything were valid.
- Do not write complex conditions if built-in annotations already express the rule.

Prefer lightweight, repeatable, side-effect-free operations: reading properties, checking classes via the classloader, checking resources, or checking bean metadata in the right phase.

### 11.1. Avoid Hard References to Optional Classes

If a class is a mandatory dependency of the module, you can use:

~~~java
@ConditionalOnClass(ReportSdk.class)
~~~

But if the dependency is optional and the class may be absent, avoid importing that class directly in a condition/configuration class that the JVM might load before the condition runs. Using the String class name with ClassUtils.isPresent or placing the condition on a separate nested configuration can prevent premature class-loading errors.

### 11.2. Do Not Turn a Missing Condition into a Startup Exception

An unmatched condition normally means the bean is not registered. This is expected behavior for an optional feature. Do not throw an exception merely to produce a noticeable log line unless the configuration truly violates a mandatory contract and the application must stop.

If a feature is mandatory by design, you can use validation/configuration-properties validation or an appropriate failure analyzer to report a clear startup error.

## 12. ConditionMessage and Other Diagnostic Tools

| Tool | Question it answers |
| --- | --- |
| ConditionMessage | Why did a custom condition match or not match? |
| ConditionOutcome | Did the condition return true or false? |
| ConditionEvaluationReport | Which conditions were evaluated in the context? |
| --debug | How to view the report in startup logs? |
| Actuator /actuator/conditions | How to query the report over HTTP when the endpoint is exposed? |
| Stack trace | Why did an already-registered bean fail during initialization? |
| ApplicationContextRunner | How to test each condition branch independently? |

A condition may match while the bean still fails in its constructor or factory method. In that case, read the stack trace; condition messages do not replace diagnosing bean creation failures.

Conversely, a condition no-match is not a startup failure. The report simply explains why Spring skipped the configuration or bean.

## 13. Common Mistakes

| Symptom | Cause | Fix |
| --- | --- | --- |
| Only a boolean is seen, no reason | Implemented Condition.matches directly | Extend SpringBootCondition and return ConditionOutcome |
| Message exists yet the bean is still created | Returned ConditionOutcome.match even though message said missing | Use noMatch when prerequisites are not satisfied |
| Condition does not appear in the report | Condition not attached via @Conditional or configuration not loaded | Check annotations and auto-configuration discovery |
| Message only says "not ready" | Did not list specific properties/classes/beans | Use didNotFind(...).items(...) |
| Only reports one missing condition despite several | Returned immediately on the first failing prerequisite | Collect independent causes into a list |
| Optional dependency causes NoClassDefFoundError | Hard reference to a class that may be absent | Use class name + ClassUtils.isPresent or nested configuration |
| Report is not printed in tests | Listener or appropriate log level not enabled | Use ConditionEvaluationReportLoggingListener |
| Bean absence test passes but message is wrong | Only asserted bean absence without reading the report | Assert ConditionEvaluationReport and important messages |
| Logs contain API keys/tokens | Logged raw property values into the message | Log only property names and states |
| Condition calls an external service | Side effect during evaluation | Move runtime checks to a bean/service after context creation |
| Formatting changes across Boot versions break tests | Compared full verbatim sentence text | Assert stable tokens: keys, classes, reasons |
| Custom condition duplicates built-in annotations | Reimplemented common logic | Prefer @ConditionalOnClass, @ConditionalOnProperty, @ConditionalOnBean |

## 14. Custom Condition Review Checklist

Before releasing the library:

1. Use built-in conditions if they already express the rule sufficiently.
2. If custom messages are needed, extend SpringBootCondition.
3. Return ConditionOutcome.match or noMatch matching the logic.
4. Build messages with ConditionMessage.forCondition.
5. List missing prerequisites using didNotFind(...).items(...).
6. State full property keys or fully qualified class names.
7. Do not put secrets or sensitive raw config into messages.
8. Conditions only read state; produce no side effects.
9. Test both match and no-match branches.
10. Read messages from ConditionEvaluationReport in tests.
11. Use --debug or the listener to inspect reports at runtime.
12. Distinguish condition no-match from exceptions during bean initialization.

## 15. Self-Check Questions

**Question 1.** Does ConditionMessage itself decide whether a bean is registered?  
**Answer:** No. ConditionOutcome carries the match/no-match result; ConditionMessage only explains the result.

**Question 2.** Why should Spring Boot custom conditions usually extend SpringBootCondition?  
**Answer:** This class integrates outcomes into logging and the Condition Evaluation Report. Custom conditions can return ConditionOutcome with messages.

**Question 3.** Which API is used to list missing prerequisites?  
**Answer:** ConditionMessage.forCondition(...).didNotFind(...).items(...).

**Question 4.** If you need to report multiple missing properties/classes, what should you do?  
**Answer:** Collect independent causes into a collection, pass it to items, and then return ConditionOutcome.noMatch.

**Question 5.** When a condition matches, which outcome should be returned?  
**Answer:** ConditionOutcome.match(message) with a message describing the satisfied prerequisites.

**Question 6.** How do you avoid NoClassDefFoundError when a dependency is optional?  
**Answer:** Avoid hard references to the optional class in eagerly loaded code; check by class name and ClassUtils.isPresent or use an appropriate nested configuration.

**Question 7.** Should an API key be included in ConditionMessage for easier debugging?  
**Answer:** No. Messages can appear in logs/reports; state only the property name and state, not secret values.

**Question 8.** How do you test messages produced by a custom condition?  
**Answer:** Use ApplicationContextRunner, retrieve ConditionEvaluationReport from the bean factory, locate the source class/method, and assert key tokens in the outcome message.

**Remember:** A good custom condition answers two questions: **did it match** and **if not, what is missing**. Extend SpringBootCondition, build ConditionMessage with the builder, return accurate ConditionOutcome values, and test messages in ConditionEvaluationReport. Prefer built-in conditions for common rules; write custom conditions only when combined logic or more specific diagnostics are needed.

## 16. Official References

- [ConditionMessage — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html)
- [ConditionOutcome — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html)
- [SpringBootCondition — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html)
- [ConditionEvaluationReport — Spring Boot 3.3.13 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html)
- [Creating Your Own Auto-configuration — Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Conditions Evaluation Report — Spring Boot Actuator 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/conditions.html)
