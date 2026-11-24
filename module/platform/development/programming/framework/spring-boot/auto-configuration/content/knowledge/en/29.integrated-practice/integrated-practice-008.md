# Writing Composite Conditions and Testing Messages for Each Branch

## 1. Why Are Composite Conditions Needed?

A real-world auto-configuration often depends on multiple conditions simultaneously. For instance, a search gateway should be registered only when:

- The search feature is enabled.
- The application has selected a supported region.
- At least one transport is enabled: HTTP **or** JMS.
- Legacy mode is not enabled.

Writing every condition on a bean method or repeating multiple annotations in many places easily scatters configuration. When a branch fails to match, developers also struggle to tell which condition caused the auto-configuration to be skipped.

Spring Boot provides three composite condition classes:

- **AllNestedConditions** — AND: all child conditions must match.
- **AnyNestedCondition** — OR: at least one child condition must match.
- **NoneNestedConditions** — NOR/NOT: none of the child conditions may match.

Beyond a boolean result, Spring Boot also has **ConditionOutcome** and **ConditionMessage** to explain why a condition matched or did not match. This guide combines both parts: writing composite conditions, then reading and testing messages for each branch.

Example scope: **Spring Boot 3.3.13, Spring Framework 6.1, and Java 17+**. After this lesson, you can:

1. Express AND, OR, and NOT using nested conditions.
2. Choose the right ConfigurationPhase for child conditions.
3. Package composite conditions into reusable annotations.
4. Generate per-branch match/no-match messages with SpringBootCondition.
5. Read ConditionEvaluationReport to find which child condition matched or failed.
6. Write tests for every branch, including messages, instead of checking only bean presence.

## 2. Modeling Logic Before Writing Code

Suppose the search feature requires four rules:

- enabled must be true.
- region must be ap-southeast-1.
- transport must be http or jms.
- legacy.enabled must not be true.

Logical expression:

~~~text
SEARCH_READY =
    ENABLED
    AND REGION_SUPPORTED
    AND (HTTP_TRANSPORT OR JMS_TRANSPORT)
    AND NOT LEGACY_ENABLED
~~~

Abbreviated truth table:

| Enabled | Valid region | HTTP | JMS | Legacy | Search gateway |
| --- | --- | --- | --- | --- | --- |
| true | true | true | false | false | Match |
| true | true | false | true | false | Match |
| true | true | false | false | false | No match |
| true | false | true | false | false | No match |
| false | true | true | true | false | No match |
| true | true | true | false | true | No match |

This table shows that a composite condition has many independent branches. When the final result is no-match, a generic message like "conditions did not match" is not helpful enough. We need to know whether the feature flag was wrong, the region was unsupported, both transports were disabled, or legacy mode was enabled.

## 3. Three Types of Nested Conditions in Spring Boot

These classes live in the package:

~~~java
org.springframework.boot.autoconfigure.condition
~~~

All three extend AbstractNestedCondition and implement both Condition and ConfigurationCondition.

### 3.1. AllNestedConditions — all branches must match

Used when the rule has the form A AND B AND C:

~~~java
public static class OnSearchEnabledAndRegion
        extends AllNestedConditions {

    public OnSearchEnabledAndRegion() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "enabled",
        havingValue = "true"
    )
    static class SearchEnabled {
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "region",
        havingValue = "ap-southeast-1"
    )
    static class SupportedRegion {
    }
}
~~~

AllNestedConditions matches only when all nested class conditions match. If one branch is no-match, the overall condition is no-match.

### 3.2. AnyNestedCondition — only one branch needs to match

Used when the rule has the form A OR B:

~~~java
public static class OnHttpOrJmsTransport
        extends AnyNestedCondition {

    public OnHttpOrJmsTransport() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "transport",
        havingValue = "http"
    )
    static class HttpTransport {
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "transport",
        havingValue = "jms"
    )
    static class JmsTransport {
    }
}
~~~

When acme.search.transport=http, the HTTP branch matches and the overall condition matches. When the property is jms, the JMS branch matches. If no branch matches, the overall condition is no-match.

One OR branch matching does not mean the remaining branches also match. The report can still show which branch matched and which did not.

### 3.3. NoneNestedConditions — no branch may match

Used when the rule requires none of the forbidden conditions to occur:

~~~java
public static class OnLegacyModeDisabled
        extends NoneNestedConditions {

    public OnLegacyModeDisabled() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
        prefix = "acme.search",
        name = "legacy.enabled",
        havingValue = "true"
    )
    static class LegacyModeEnabled {
    }
}
~~~

This condition matches when the nested LegacyModeEnabled condition does not match. Because the nested condition matches only when the property is true, false values or a missing property both cause OnLegacyModeDisabled to match.

This is a common point of confusion: NoneNestedConditions does not mean "all child conditions must be no-match to create each child bean". It creates **a single composite condition** that matches only when none of the child conditions match.

## 4. Choosing the Right ConfigurationPhase

Every nested condition must declare its phase in its constructor:

~~~java
super(ConfigurationPhase.PARSE_CONFIGURATION);
~~~

Or:

~~~java
super(ConfigurationPhase.REGISTER_BEAN);
~~~

| Phase | When evaluated | Suitable data types |
| --- | --- | --- |
| PARSE_CONFIGURATION | While Spring is parsing configurations/imports | Environment properties, classpath, resources, and metadata checkable early |
| REGISTER_BEAN | While Spring is registering bean definitions | Conditions depending on bean definitions or bean conditions |

The example in this article only checks properties from Environment, so PARSE_CONFIGURATION is appropriate.

If a child condition uses ConditionalOnBean, ConditionalOnMissingBean, or logic depending on bean definitions, consider REGISTER_BEAN. The phase of the composite condition must suit the child conditions it contains. When a composite has a branch needing bean definitions, choose the later phase so it is not evaluated too early.

**Do not pick a phase out of habit.** Choosing PARSE_CONFIGURATION for a condition requiring bean definitions can cause the condition to be evaluated before those beans are registered. Conversely, choosing REGISTER_BEAN for a condition needing only properties does not yield wrong results, but may unnecessarily delay evaluation.

## 5. Building a Reusable Composite Condition

We package the branches inside the SearchConditions class. All nested conditions are static classes; each member class carries its own condition annotation.

File src/main/java/demo/search/autoconfigure/SearchConditions.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.condition.AllNestedConditions;
import org.springframework.boot.autoconfigure.condition.AnyNestedCondition;
import org.springframework.boot.autoconfigure.condition.NoneNestedConditions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;

public final class SearchConditions {

    private SearchConditions() {
    }

    public static final class OnTransportAvailable
            extends AnyNestedCondition {

        public OnTransportAvailable() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "transport",
            havingValue = "http"
        )
        static class HttpTransport {
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "transport",
            havingValue = "jms"
        )
        static class JmsTransport {
        }
    }

    public static final class OnLegacyModeDisabled
            extends NoneNestedConditions {

        public OnLegacyModeDisabled() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "legacy.enabled",
            havingValue = "true"
        )
        static class LegacyModeEnabled {
        }
    }

    public static final class OnSearchReady
            extends AllNestedConditions {

        public OnSearchReady() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "enabled",
            havingValue = "true"
        )
        static class FeatureEnabled {
        }

        @ConditionalOnProperty(
            prefix = "acme.search",
            name = "region",
            havingValue = "ap-southeast-1"
        )
        static class SupportedRegion {
        }

        @Conditional(OnTransportAvailable.class)
        static class TransportAvailable {
        }

        @Conditional(OnLegacyModeDisabled.class)
        static class LegacyModeDisabled {
        }
    }
}
~~~

Logical structure:

- OnSearchReady uses AND to combine four top-level branches.
- TransportAvailable nests an OR condition: HTTP or JMS.
- LegacyModeDisabled nests a NOT condition: legacy mode must not be enabled.

This lets us read the logic directly from class structure instead of deciphering a long expression.

### 5.1. Packaging the condition into an annotation

File src/main/java/demo/search/autoconfigure/ConditionalOnSearchReady.java:

~~~java
package demo.search.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(SearchConditions.OnSearchReady.class)
public @interface ConditionalOnSearchReady {
}
~~~

Library users can apply this annotation to configuration classes or bean methods without needing to know the internal branches.

### 5.2. Using the annotation in auto-configuration

File src/main/java/demo/search/autoconfigure/SearchGateway.java:

~~~java
package demo.search.autoconfigure;

public record SearchGateway(String description) {
}
~~~

File src/main/java/demo/search/autoconfigure/SearchAutoConfiguration.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class SearchAutoConfiguration {

    @Bean
    @ConditionalOnSearchReady
    SearchGateway searchGateway() {
        return new SearchGateway("search gateway ready");
    }
}
~~~

Register the auto-configuration in the JAR via the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Content:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration
~~~

In tests, it can be loaded directly with AutoConfigurations.of(SearchAutoConfiguration.class). Consuming applications will discover the class through the imports file.

## 6. Condition Messages: A Boolean Result Needs a Reason

Spring Framework's Condition only requires the matches() method to return a boolean. If you write a condition directly against this interface, you have no standard API to attach detailed messages to outcomes.

Spring Boot provides SpringBootCondition:

~~~java
public abstract class SpringBootCondition implements Condition {

    public abstract ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata
    );
}
~~~

SpringBootCondition handles matches() and outcome logging for you. The base class's matches() method is final; subclasses must implement getMatchOutcome().

ConditionOutcome holds two pieces of information:

- isMatch() — whether the condition matched.
- getMessage() — message explaining the outcome.

Creating outcomes:

~~~java
ConditionOutcome.match("required property is available");
ConditionOutcome.noMatch("required property is missing");
~~~

Or use ConditionMessage to construct structured messages:

~~~java
ConditionMessage message =
    ConditionMessage.forCondition("Search transport")
        .because("acme.search.mode selects HTTP transport");

return ConditionOutcome.match(message);
~~~

For non-matching branches:

~~~java
ConditionMessage message =
    ConditionMessage.forCondition("Search transport")
        .because("acme.search.mode is missing; expected http or jms");

return ConditionOutcome.noMatch(message);
~~~

### 6.1. Distinguishing composite condition messages and per-branch messages

There are two message levels:

1. **Nested condition messages:** child conditions returned by ConditionalOnProperty or custom conditions. They explain which property/class/resource matched or did not match.
2. **Composite condition messages:** AllNestedConditions, AnyNestedCondition, or NoneNestedConditions aggregate outcomes of child branches.

Spring Boot retains outcomes of nested conditions in ConditionEvaluationReport. That way, when a composite condition fails to match, we can still inspect which branch failed.

If you need a distinct business reason for each branch, create a custom condition extending SpringBootCondition and return the corresponding ConditionOutcome. Do not merely return a generic message like "search condition failed" for every case.

## 7. Custom SpringBootCondition with Per-Branch Messages

This example selects a transport based on the acme.search.mode property. There are four branches:

- http — matches and selects HTTP.
- jms — matches and selects JMS.
- Missing or blank property — no-match with a specific reason.
- Unsupported value — no-match and records the received value.

### 7.1. Annotation

File src/main/java/demo/search/autoconfigure/ConditionalOnSearchMode.java:

~~~java
package demo.search.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(SearchModeCondition.class)
public @interface ConditionalOnSearchMode {
}
~~~

### 7.2. Condition implementation

File src/main/java/demo/search/autoconfigure/SearchModeCondition.java:

~~~java
package demo.search.autoconfigure;

import java.util.Locale;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class SearchModeCondition extends SpringBootCondition {

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        String configuredMode =
            context.getEnvironment().getProperty("acme.search.mode");

        if (configuredMode == null || configuredMode.isBlank()) {
            return noMatch(
                "acme.search.mode is missing; expected http or jms"
            );
        }

        String mode = configuredMode.trim().toLowerCase(Locale.ROOT);

        return switch (mode) {
            case "http" -> match(
                "acme.search.mode selects HTTP transport"
            );
            case "jms" -> match(
                "acme.search.mode selects JMS transport"
            );
            default -> noMatch(
                "unsupported acme.search.mode '" + configuredMode
                    + "'; expected http or jms"
            );
        };
    }

    private ConditionOutcome match(String reason) {
        ConditionMessage message =
            ConditionMessage.forCondition("Search mode")
                .because(reason);

        return ConditionOutcome.match(message);
    }

    private ConditionOutcome noMatch(String reason) {
        ConditionMessage message =
            ConditionMessage.forCondition("Search mode")
                .because(reason);

        return ConditionOutcome.noMatch(message);
    }
}
~~~

### 7.3. Using the custom condition on a bean method

File src/main/java/demo/search/autoconfigure/SearchModeClient.java:

~~~java
package demo.search.autoconfigure;

public record SearchModeClient(String transport) {
}
~~~

File src/main/java/demo/search/autoconfigure/SearchModeAutoConfiguration.java:

~~~java
package demo.search.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@AutoConfiguration
public class SearchModeAutoConfiguration {

    @Bean
    @ConditionalOnSearchMode
    SearchModeClient searchModeClient(Environment environment) {
        return new SearchModeClient(
            environment.getRequiredProperty("acme.search.mode")
        );
    }
}
~~~

This example illustrates per-branch messages. In a real library, if mode is bound into configuration properties, the bean method can accept the properties bean rather than reading Environment directly.

### 7.4. Expected messages per branch

| Property | Match? | Message fragment |
| --- | --- | --- |
| acme.search.mode=http | Yes | acme.search.mode selects HTTP transport |
| acme.search.mode=jms | Yes | acme.search.mode selects JMS transport |
| Missing property | No | acme.search.mode is missing; expected http or jms |
| acme.search.mode=kafka | No | unsupported acme.search.mode 'kafka'; expected http or jms |

Messages do not decide the outcome; the boolean inside ConditionOutcome does. Messages only explain the reason so developers can read the condition report and diagnose configuration.

## 8. Reading ConditionEvaluationReport to Verify Each Branch

Spring Boot records condition outcomes in ConditionEvaluationReport. The report groups results by source, usually a configuration class or bean method.

Useful APIs:

~~~java
ConditionEvaluationReport report =
    ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> outcomes =
    report.getConditionAndOutcomesBySource();
~~~

Each ConditionAndOutcomes is a collection that can be iterated over ConditionAndOutcome items. Each element provides:

- getCondition() — the condition that was evaluated.
- getOutcome() — the result of the condition.
- getOutcome().isMatch() — match/no-match status.
- getOutcome().getMessage() — diagnostic message.

Example reading the report in tests:

~~~java
private static List<String> conditionMessages(
        AssertableApplicationContext context) {

    ConditionEvaluationReport report =
        ConditionEvaluationReport.get(
            context.getSourceApplicationContext().getBeanFactory()
        );

    return report.getConditionAndOutcomesBySource()
        .values()
        .stream()
        .flatMap(outcomes ->
            StreamSupport.stream(outcomes.spliterator(), false)
        )
        .map(item -> item.getOutcome().getMessage())
        .toList();
}
~~~

ConditionAndOutcomes in Spring Boot 3.3 implements Iterable, so StreamSupport can be used as shown above. Do not use stream() if Spring Boot 3.3 compatibility is needed: that method was only introduced in Spring Boot 3.5.

### 8.1. The report may contain multiple sources

For example, a composite condition on a bean method can produce corresponding sources:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration#searchGateway
demo.search.autoconfigure.SearchConditions$OnSearchReady
demo.search.autoconfigure.SearchConditions$OnSearchReady$FeatureEnabled
demo.search.autoconfigure.SearchConditions$OnSearchReady$SupportedRegion
demo.search.autoconfigure.SearchConditions$OnTransportAvailable
demo.search.autoconfigure.SearchConditions$OnTransportAvailable$HttpTransport
demo.search.autoconfigure.SearchConditions$OnTransportAvailable$JmsTransport
demo.search.autoconfigure.SearchConditions$OnLegacyModeDisabled
~~~

Exact source names depend on class structure and how Spring records metadata. When writing tests, filter messages by stable content such as property names or business reasons rather than relying on full internal source names.

### 8.2. Viewing the report when running the application

You can enable the condition evaluation report with:

~~~bash
java -jar target/search-demo-1.0.0.jar --debug
~~~

Spring Boot will print positive matches and negative matches groups in startup logs.

If the application has Actuator and the endpoint is exposed, the /actuator/conditions endpoint can also provide the condition report. This report is for diagnostics; do not expose it broadly if messages might reveal internal configuration.

## 9. Maven Example and Testing Branches

This example uses Spring Boot 3.3.13, Java 17+, and ApplicationContextRunner. Tests verify:

1. AND/OR/NOT all match and the gateway is registered.
2. OR selects the HTTP branch.
3. OR selects the JMS branch.
4. Wrong region causes AND no-match.
5. Legacy enabled causes NOT no-match.
6. Custom condition returns exact messages for HTTP, JMS, missing property, and unsupported mode.

### 9.1. Project structure

~~~text
search-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/search/autoconfigure/
    │   │   ├── SearchConditions.java
    │   │   ├── ConditionalOnSearchReady.java
    │   │   ├── SearchGateway.java
    │   │   ├── SearchAutoConfiguration.java
    │   │   ├── ConditionalOnSearchMode.java
    │   │   ├── SearchModeCondition.java
    │   │   ├── SearchModeClient.java
    │   │   └── SearchModeAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/demo/search/autoconfigure/
            └── SearchConditionTests.java
~~~

### 9.2. File pom.xml

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

    <groupId>demo</groupId>
    <artifactId>search-condition-demo</artifactId>
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
~~~

### 9.3. Registering auto-configurations

File src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
demo.search.autoconfigure.SearchAutoConfiguration
demo.search.autoconfigure.SearchModeAutoConfiguration
~~~

In a real library project, these two classes reside in the JAR and are discovered by consumers via the imports file. In tests, we can load them directly via AutoConfigurations.of(...).

### 9.4. Complete test file

File src/test/java/demo/search/autoconfigure/SearchConditionTests.java:

~~~java
package demo.search.autoconfigure;

import java.util.List;
import java.util.stream.StreamSupport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class SearchConditionTests {

    private final ApplicationContextRunner compositeRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(SearchAutoConfiguration.class)
            );

    private final ApplicationContextRunner modeRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(SearchModeAutoConfiguration.class)
            );

    private static List<String> conditionMessages(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
            ConditionEvaluationReport.get(
                context.getSourceApplicationContext().getBeanFactory()
            );

        return report.getConditionAndOutcomesBySource()
            .values()
            .stream()
            .flatMap(outcomes ->
                StreamSupport.stream(outcomes.spliterator(), false)
            )
            .map(item -> item.getOutcome().getMessage())
            .toList();
    }

    @Test
    void matchesWhenAndOrAndNotBranchesAreSatisfied() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasNotFailed();
                assertThat(context).hasSingleBean(SearchGateway.class);

                List<String> messages = conditionMessages(context);

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.enabled"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.region"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.transport"));

                assertThat(messages)
                    .anyMatch(message ->
                        message.contains("acme.search.legacy.enabled"));
            });
    }

    @Test
    void anyNestedConditionCanSelectJmsBranch() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=jms",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("jms"));
            });
    }

    @Test
    void allNestedConditionDoesNotMatchWhenRegionIsUnsupported() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=eu-west-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.region"));
            });
    }

    @Test
    void noneNestedConditionRejectsLegacyMode() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.transport=http",
                "acme.search.legacy.enabled=true"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.legacy.enabled"));
            });
    }

    @Test
    void anyNestedConditionDoesNotMatchWhenNoTransportIsSelected() {
        this.compositeRunner
            .withPropertyValues(
                "acme.search.enabled=true",
                "acme.search.region=ap-southeast-1",
                "acme.search.legacy.enabled=false"
            )
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchGateway.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains("acme.search.transport"));
            });
    }

    @Test
    void customConditionReportsHttpBranchMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=http")
            .run(context -> {
                assertThat(context).hasSingleBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "acme.search.mode selects HTTP transport"
                        ));
            });
    }

    @Test
    void customConditionReportsJmsBranchMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=jms")
            .run(context -> {
                assertThat(context).hasSingleBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "acme.search.mode selects JMS transport"
                        ));
            });
    }

    @Test
    void customConditionReportsMissingPropertyMessage() {
        this.modeRunner.run(context -> {
            assertThat(context).doesNotHaveBean(SearchModeClient.class);

            assertThat(conditionMessages(context))
                .anyMatch(message ->
                    message.contains(
                        "acme.search.mode is missing; expected http or jms"
                    ));
        });
    }

    @Test
    void customConditionReportsUnsupportedValueMessage() {
        this.modeRunner
            .withPropertyValues("acme.search.mode=kafka")
            .run(context -> {
                assertThat(context).doesNotHaveBean(SearchModeClient.class);

                assertThat(conditionMessages(context))
                    .anyMatch(message ->
                        message.contains(
                            "unsupported acme.search.mode 'kafka'"
                        ));
            });
    }
}
~~~

### 9.5. Running the tests

Requirements: JDK 17+ and Maven 3.8+. From the project directory:

~~~bash
mvn clean test
~~~

There are nine independent tests. Expected result:

| Test | Tested branch | Main assertion |
| --- | --- | --- |
| matchesWhenAndOrAndNotBranchesAreSatisfied | AND + HTTP OR JMS + NOT legacy | Gateway created and report contains each property's message |
| anyNestedConditionCanSelectJmsBranch | OR / JMS | Gateway created via JMS branch |
| allNestedConditionDoesNotMatchWhenRegionIsUnsupported | AND / region | Gateway not created; report mentions region |
| noneNestedConditionRejectsLegacyMode | NOT / legacy | Gateway not created; report mentions legacy |
| anyNestedConditionDoesNotMatchWhenNoTransportIsSelected | OR / no branch | Gateway not created; report mentions transport |
| customConditionReportsHttpBranchMessage | Custom / HTTP | Client present and HTTP message |
| customConditionReportsJmsBranchMessage | Custom / JMS | Client present and JMS message |
| customConditionReportsMissingPropertyMessage | Custom / missing | No client; message reports missing property |
| customConditionReportsUnsupportedValueMessage | Custom / unsupported | No client; message states unsupported value |

Maven Surefire will report nine passing tests and BUILD SUCCESS if all assertions pass. This is the expected result from the test code, not stdout executed in the current environment.

## 10. How to Read Per-Branch Messages in Practice

Suppose the configuration is:

~~~properties
acme.search.enabled=true
acme.search.region=eu-west-1
acme.search.transport=http
acme.search.legacy.enabled=false
~~~

We can interpret the report:

| Branch | Outcome | Reason |
| --- | --- | --- |
| Feature enabled | Match | Property enabled is true |
| Supported region | No match | Current region is eu-west-1, required ap-southeast-1 |
| HTTP transport | Match | Transport is http |
| JMS transport | No match | Transport is not jms |
| Legacy mode enabled | No match | Legacy flag is false |
| Search ready (AND) | No match | At least one required condition did not pass |

A composite condition returning no-match does not mean every branch failed. In the example, feature and HTTP transport matched; only region caused AND to fail.

If transport is changed to jms, the JMS branch matches instead of HTTP. The OR condition still matches because at least one branch is true.

If legacy.enabled is changed to true, the nested LegacyModeEnabled condition matches, so NoneNestedConditions becomes no-match and the search gateway is excluded.

## 11. Rules for Writing Good Messages

A helpful message should answer three questions:

1. **Which condition is being evaluated?** For example Search mode, supported region, or transport availability.
2. **Which branch was checked?** HTTP, JMS, legacy, property, or class.
3. **Why did it match/not match?** Actual value, expected value, or missing prerequisite.

### 11.1. Write reasons instead of repeating annotation names

Weak message:

~~~text
Condition did not match
~~~

Better message:

~~~text
acme.search.region is 'eu-west-1'; expected 'ap-southeast-1'
~~~

Weak message:

~~~text
Search mode failed
~~~

Better message:

~~~text
unsupported acme.search.mode 'kafka'; expected http or jms
~~~

### 11.2. Messages should be stable and free of sensitive data

Condition messages often appear in startup logs, debug reports, or the Actuator conditions endpoint. Do not include passwords, tokens, secrets, private keys, or full URLs containing credentials in messages.

Include:

- Property key.
- Non-sensitive value or missing state.
- Supported values.
- Class/resource names when helpful.
- A brief remediation action.

If a property holds a secret, log "credential property is configured/missing" instead of logging the actual value.

### 11.3. Test messages using stable fragments

Do not assert the full default message generated by Spring Boot for ConditionalOnProperty. Formatting can include annotation names, prefixes, expected values, and internal wording.

Instead:

- For built-in conditions, assert stable fragments such as property keys or class names.
- For custom conditions, assert the reason phrasing you control yourself.
- Also check isMatch() or bean presence; messages do not replace logical results.
- Do not assert internal source class names unless they are an API committed to by the library.

## 12. Common Mistakes When Writing Composite Conditions

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Using AllNestedConditions for HTTP or JMS branches | AND requires both branches to match | Use AnyNestedCondition |
| Using AnyNestedCondition for a feature requiring every condition | A single passing branch makes the whole condition match | Use AllNestedConditions |
| Using NoneNestedConditions expecting one true branch to match | None matches only when zero nested conditions match | Rewrite the logical expression and test both sides |
| Forgetting constructor calling super(ConfigurationPhase...) | Nested conditions require a phase to evaluate | Choose PARSE_CONFIGURATION or REGISTER_BEAN |
| Using PARSE_CONFIGURATION for conditions needing bean definitions | May evaluate too early | Choose REGISTER_BEAN |
| Non-static nested member classes | Incompatible with the nested condition mechanism | Declare static classes |
| Stuffing all logic into one long expression | Hard to read and hard to separate branch messages | Split nested conditions by domain |
| Custom condition returning only a boolean | Loses structured diagnostic messages | Extend SpringBootCondition |
| Overriding matches() in SpringBootCondition | Base class method is final | Override getMatchOutcome() |
| Using a generic message for all no-matches | Cannot tell which branch failed | Create per-branch ConditionOutcomes |
| Asserting Boot's entire default message | Brittle when wording changes | Assert meaningful message fragments |
| Testing only one passing combination | Fails to check second OR branch or negated branches | Test match and no-match for every branch |
| Calling getBean() or I/O inside a condition | Conditions run in the configuration phase and must avoid side effects | Read only metadata/Environment; let beans/services do runtime work |
| Using conditions to replace data validation | Matching does not guarantee valid data | Bind/validate properties separately |

## 13. Workflow for Designing and Reviewing Composite Conditions

1. Write the logical expression before writing Java: A AND (B OR C) AND NOT D.
2. Name each branch in business terms.
3. Choose AllNestedConditions, AnyNestedCondition, and NoneNestedConditions matching the operators.
4. Make nested member classes static and attach condition annotations to each class.
5. Pick ConfigurationPhase according to the type of input the branches read.
6. Package the condition as an annotation if multiple auto-configurations will reuse it.
7. If domain-specific messages are needed, create a SpringBootCondition and return a ConditionOutcome per branch.
8. Inspect ConditionEvaluationReport to view each condition and outcome.
9. Write tests for each match/no-match branch, including missing and unsupported values.
10. Assert both bean presence/absence and message fragments.
11. Run the application with --debug to verify the report in startup logs.
12. Keep messages concise, stable, and free of secrets.

## 14. Self-Check Questions

**Question 1.** When do you use AllNestedConditions?  
**Answer:** When all nested conditions must match, equivalent to AND.

**Question 2.** When do you use AnyNestedCondition?  
**Answer:** When only at least one nested condition needs to match, equivalent to OR.

**Question 3.** When does NoneNestedConditions match?  
**Answer:** When none of the nested conditions match.

**Question 4.** Why does a nested condition need ConfigurationPhase?  
**Answer:** So Spring knows whether to evaluate the condition in the configuration parsing phase or bean definition registration phase; the phase must fit the data the branches read.

**Question 5.** How should nested condition classes be declared?  
**Answer:** As static nested classes, each annotated with its corresponding condition.

**Question 6.** What does ConditionOutcome contain?  
**Answer:** Match/no-match status and an explanatory message.

**Question 7.** Why extend SpringBootCondition instead of just implementing Condition?  
**Answer:** SpringBootCondition provides Spring Boot-aligned logging/reporting and lets you return a ConditionOutcome with a message.

**Question 8.** Which method must be overridden in a custom SpringBootCondition?  
**Answer:** getMatchOutcome(context, metadata). The base class's matches() method is final.

**Question 9.** What does ConditionEvaluationReport group results by?  
**Answer:** By the source of condition evaluation, typically a configuration class or bean method; each entry contains the condition and outcome.

**Question 10.** When testing ConditionalOnProperty messages, should you assert the entire string or fragments?  
**Answer:** Assert stable fragments such as property keys and reasons. For custom conditions, you can assert exact reason strings that you control.

**Question 11.** If HTTP matches and JMS is no-match, does AnyNestedCondition match?  
**Answer:** Yes. Only one branch needs to match.

**Question 12.** If one of four branches in AllNestedConditions is no-match, what is the outcome?  
**Answer:** The overall condition is no-match, even if the other branches match.

## 15. Key Takeaways and References

- AllNestedConditions is AND; AnyNestedCondition is OR; NoneNestedConditions is NOT over child conditions.
- Nested conditions use static member classes each having its own condition annotation.
- ConfigurationPhase.PARSE_CONFIGURATION fits properties/classpath/resources evaluable early; REGISTER_BEAN is for conditions depending on bean definitions.
- SpringBootCondition allows returning ConditionOutcome with messages and logging; override getMatchOutcome(), not matches().
- ConditionMessage.forCondition(...).because(...) creates consistent messages; ConditionOutcome.match/noMatch holds both status and message.
- ConditionEvaluationReport groups outcomes by source; iterate ConditionAndOutcomes to inspect per-branch messages.
- Tests must check both boolean/bean presence and messages. For built-in conditions, assert stable fragments; for custom conditions, assert specific reasons.
- Condition messages are diagnostic tools, not substitutes for validation, bean creation, or runtime error handling.

Official Spring Boot 3.3.13 documentation:

1. [AllNestedConditions Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html) — AND condition and ConfigurationPhase.
2. [AnyNestedCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html) — OR condition.
3. [NoneNestedConditions Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html) — negated condition.
4. [SpringBootCondition Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html) — getMatchOutcome() and logging.
5. [ConditionMessage Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html) — fluent message builder.
6. [ConditionOutcome Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html) — match/no-match outcome and message.
7. [ConditionEvaluationReport Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html) — per-source report and accessing outcomes.
8. [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — custom auto-configurations and testing with ApplicationContextRunner.
