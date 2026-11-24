# AllNestedConditions for Groups of Simultaneous Requirements

> **Spring Boot Auto Configuration → Custom Conditions.** This lesson explains how to use AllNestedConditions to combine multiple conditions into a composite condition that matches only when every member condition matches. The hands-on example uses Spring Boot 3.3.13, Java 17, and an optional JDBC integration: the history-recording feature is registered only when JdbcTemplate is on the classpath and the feature-enabling property is true. The lesson also distinguishes PARSE_CONFIGURATION from REGISTER_BEAN, compares with AnyNestedCondition and NoneNestedConditions, and tests every combination with ApplicationContextRunner.

## 1. The Problem: Multiple Conditions Must All Be True

An auto-configuration may be appropriate only when multiple requirements are simultaneously met. For example, a library has a module that persists notification history over JDBC. The history-writer bean should be created only when:

1. Spring JDBC is on the runtime classpath.
2. The user enables the feature with acme.notice.history.enabled=true.
3. The application already has a JdbcTemplate bean for the adapter to use.
4. The application has not provided its own alternative NoticeHistoryWriter bean.

These conditions belong to different layers:
- Classpath and properties can be checked while Spring is parsing configurations.
- Presence of the JdbcTemplate bean is checked during the bean registration phase.
- An alternative bean is evaluated by ConditionalOnMissingBean.

You can stack multiple condition annotations on the same configuration, but when a group of conditions needs to be named, reused, or tested as a unit, AllNestedConditions provides a clear way to express it.

What matters is not blindly lumping everything into one condition. Choose conditions that share the same evaluation phase, and keep bean-dependent conditions at the proper bean-method scope.

## 2. What Is AllNestedConditions?

org.springframework.boot.autoconfigure.condition.AllNestedConditions is a Spring Boot abstract class extending AbstractNestedCondition. It builds a composite condition from conditions placed on static nested classes inside it.

The composite condition matches only when **all nested class conditions match**. If even one member condition fails to match, the composite condition also fails to match.

Basic pattern:

~~~java
static class OnJndiAndProperty extends AllNestedConditions {

    OnJndiAndProperty() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnJndi
    static class OnJndi {
    }

    @ConditionalOnProperty("something")
    static class OnProperty {
    }
}
~~~

In this example:
- OnJndi is one member condition.
- OnProperty is the other member condition.
- Both must match for OnJndiAndProperty to match.
- The constructor passes ConfigurationPhase so Spring Boot knows when to evaluate the condition group.

Member classes do not need Java logic. The annotations on each class are the actual conditions Spring Boot evaluates. The composite class simply defines how those outcomes are combined.

### 2.1. Truth Table of AllNestedConditions

Suppose there are two conditions A and B:

| A | B | AllNestedConditions |
| --- | --- | --- |
| true | true | Match |
| true | false | No match |
| false | true | No match |
| false | false | No match |

With three conditions A, B, and C, only the combination true, true, true matches. If even a single condition is false, the combined result does not match.

This is logical AND:

~~~text
All(A, B, C) = A AND B AND C
~~~

Practical example:

~~~text
Spring JDBC is on classpath?         true
acme.notice.history.enabled=true?    true
-------------------------------------------
AllNestedConditions                  MATCH
~~~

If Spring JDBC is not on the classpath even when the property is true, the result is still no-match.

### 2.2. When Should You Use It?

Use AllNestedConditions when:
- Two or more conditions must hold simultaneously.
- You want to represent a composite rule with a readable name.
- You want to reuse the same group of conditions across multiple configurations.
- You want to group classpath/property conditions into a dedicated unit.
- You want the condition report to show one composite rule instead of repeating many annotations everywhere.

If there are only two simple annotations on a single class with no need for reuse, placing those annotations directly may be easier to read. AllNestedConditions is not mandatory for every logical AND.

## 3. Distinguishing AllNestedConditions, AnyNestedCondition, and NoneNestedConditions

Spring Boot provides three commonly used classes for combining nested conditions:

| Class | Rule | Meaning |
| --- | --- | --- |
| AllNestedConditions | All must match | AND |
| AnyNestedCondition | At least one condition must match | OR |
| NoneNestedConditions | No condition may match | NOR |

Example with the same two conditions A and B:

| A | B | All | Any | None |
| --- | --- | --- | --- | --- |
| true | true | Match | Match | No match |
| true | false | No match | Match | No match |
| false | true | No match | Match | No match |
| false | false | No match | No match | Match |

### 3.1. AnyNestedCondition: Only One Branch Needs to Be True

For example, a library can use one of two authentication mechanisms: API key or OAuth. If only one mechanism needs to be enabled, use AnyNestedCondition:

~~~java
static class OnApiKeyOrOAuth extends AnyNestedCondition {

    OnApiKeyOrOAuth() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.auth",
            name = "api-key-enabled",
            havingValue = "true"
    )
    static class ApiKeyEnabled {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.auth",
            name = "oauth-enabled",
            havingValue = "true"
    )
    static class OAuthEnabled {
    }
}
~~~

If either API key or OAuth is enabled, the condition matches. If both are disabled or undeclared, the condition does not match.

### 3.2. NoneNestedConditions: All Branches Must Be False

For example, a fallback feature is enabled only when no external provider has been selected:

~~~java
static class OnNoExternalProvider extends NoneNestedConditions {

    OnNoExternalProvider() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.provider",
            name = "cloud",
            havingValue = "true"
    )
    static class CloudProviderSelected {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.provider",
            name = "external",
            havingValue = "true"
    )
    static class ExternalProviderSelected {
    }
}
~~~

This condition matches when neither cloud nor external matches. Set clear defaults and property documentation so the fallback is not accidentally activated when users misconfigure properties.

### 3.3. Choosing the Right Combinator

- Use AND when every requirement is mandatory.
- Use OR when any single option suffices.
- Use NOR when it should apply only when no branch is active.

Do not pick a class based on a vague name. Write out the truth table for important combinations before implementing the condition.

## 4. ConfigurationPhase: Choosing When Evaluation Runs

The constructor of AllNestedConditions requires a ConfigurationPhase value:

~~~java
super(ConfigurationPhase.PARSE_CONFIGURATION);
~~~

The two primary phases are:

| Phase | Timing | Use when |
| --- | --- | --- |
| PARSE_CONFIGURATION | When Spring parses configuration classes | Conditions can be evaluated early, such as classpath and properties |
| REGISTER_BEAN | When Spring registers bean definitions | Conditions depend on bean definitions, such as ConditionalOnBean |

Spring Boot documentation requires choosing a phase appropriate for the member conditions. For example, classpath and properties are static conditions that can be evaluated early, so PARSE_CONFIGURATION fits.

### 4.1. Example Using PARSE_CONFIGURATION

The following group checks only classpath and properties:

~~~java
static class OnJdbcAndHistoryEnabled extends AllNestedConditions {

    OnJdbcAndHistoryEnabled() {
        super(ConfigurationPhase.PARSE_CONFIGURATION);
    }

    @ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
    static class JdbcTemplatePresent {
    }

    @ConditionalOnProperty(
            prefix = "acme.notice.history",
            name = "enabled",
            havingValue = "true"
    )
    static class HistoryFeatureEnabled {
    }
}
~~~

Both conditions can be evaluated during configuration parsing. This group does not check whether a JdbcTemplate bean has been created yet.

### 4.2. Why Not Put Every Condition into the Same Group?

ConditionalOnBean depends on already-registered bean definitions. If you mix this condition into a group using PARSE_CONFIGURATION, the composite condition's phase may no longer suit that member.

In the hands-on example, we keep ConditionalOnBean(JdbcTemplate.class) on the bean method. The AllNestedConditions group only checks classpath and properties; the bean method checks the presence of the bean dependency at the appropriate stage.

This layering clarifies three questions:

1. Does the environment support JDBC?
2. Did the user enable the history feature?
3. Does the application provide a JdbcTemplate to build the adapter?

If a custom condition genuinely needs to inspect beans, choose the appropriate phase for that group and verify that all nested conditions can be evaluated in the chosen phase. Do not pick a phase just because an online example uses it.

## 5. Applying AllNestedConditions to a Configuration

The composite condition class is typically attached to a configuration using Conditional:

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJdbcAndHistoryEnabled.class)
static class JdbcHistoryConfiguration {
    // Beans exist only when the entire condition group matches.
}
~~~

When the condition group does not match:
- Spring skips the configuration class.
- Beans inside that class are not registered.
- Beans in other independent configurations can still operate.

Place the condition at the right scope:
- On the entire auto-configuration if every bean inside needs the condition.
- On a nested configuration if only a group of beans needs the condition.
- On a bean method if the condition applies to just one bean.

For optional integrations, a nested configuration usually isolates dependencies and avoids blocking unrelated beans.

### 5.1. Combining with ConditionalOnBean and ConditionalOnMissingBean

A practical configuration may use:
- AllNestedConditions for classpath + feature property.
- ConditionalOnBean for the dependency bean.
- ConditionalOnMissingBean for user override capability.

These conditions have distinct roles. There is no need to cram all of them into the AllNestedConditions class.

~~~java
@Configuration(proxyBeanMethods = false)
@Conditional(OnJdbcAndHistoryEnabled.class)
static class JdbcHistoryConfiguration {

    @Bean
    @ConditionalOnBean(JdbcTemplate.class)
    @ConditionalOnMissingBean(NoticeHistoryWriter.class)
    NoticeHistoryWriter noticeHistoryWriter(JdbcTemplate jdbcTemplate) {
        return new NoticeHistoryWriter(
                jdbcTemplate.getClass().getSimpleName()
        );
    }
}
~~~

The factory method is applied only when the configuration group matches, a JdbcTemplate bean exists, and no NoticeHistoryWriter has been provided by the application.

## 6. Complete Project Example: Java 17 + Spring Boot 3.3.13

This lab creates a simple JDBC history adapter. The NoticeHistoryWriter bean is created when:
- The Spring JDBC class is on the classpath.
- acme.notice.history.enabled=true.
- The context has a JdbcTemplate bean.
- No custom NoticeHistoryWriter bean exists yet.

To avoid needing a real database, the sample bean merely records the JdbcTemplate class name; the goal is testing conditions without executing SQL statements.

### 6.1. Directory Structure

~~~text
notice-all-nested-conditions/
├── pom.xml
└── src/
    ├── main/
    │   └── java/com/acme/notice/autoconfigure/
    │       ├── NoticeHistoryWriter.java
    │       └── NoticeHistoryAutoConfiguration.java
    └── test/
        └── java/com/acme/notice/autoconfigure/
            └── NoticeHistoryAutoConfigurationTest.java
~~~

### 6.2. pom.xml

File pom.xml:

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

    <groupId>com.acme.notice</groupId>
    <artifactId>notice-all-nested-conditions</artifactId>
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
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <optional>true</optional>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-jdbc is marked optional because this module provides an optional JDBC integration. It is present on the module's compile/test classpath to compile the code, but Maven does not propagate this dependency transitively to every consumer. Applications wanting the integration must add Spring JDBC or the corresponding starter themselves.

spring-boot-autoconfigure is a required dependency because the module uses auto-configuration annotations and mechanisms.

### 6.3. NoticeHistoryWriter.java

File src/main/java/com/acme/notice/autoconfigure/NoticeHistoryWriter.java:

~~~java
package com.acme.notice.autoconfigure;

public record NoticeHistoryWriter(String jdbcTemplateType) {

    public String describe() {
        return "history-writer:" + jdbcTemplateType;
    }
}
~~~

This bean represents the history adapter in the lab. It does not retain JdbcTemplate and does not open a database connection; the field simply helps tests observe the dependency passed into the factory method.

### 6.4. NoticeHistoryAutoConfiguration.java

File src/main/java/com/acme/notice/autoconfigure/NoticeHistoryAutoConfiguration.java:

~~~java
package com.acme.notice.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.AllNestedConditions;
import org.springframework.boot.autoconfigure.condition.ConditionalOnBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ConfigurationCondition.ConfigurationPhase;
import org.springframework.jdbc.core.JdbcTemplate;

@AutoConfiguration
public class NoticeHistoryAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @Conditional(OnJdbcAndHistoryEnabled.class)
    static class JdbcHistoryConfiguration {

        @Bean
        @ConditionalOnBean(JdbcTemplate.class)
        @ConditionalOnMissingBean(NoticeHistoryWriter.class)
        NoticeHistoryWriter noticeHistoryWriter(
                JdbcTemplate jdbcTemplate) {

            return new NoticeHistoryWriter(
                    jdbcTemplate.getClass().getSimpleName()
            );
        }
    }

    static class OnJdbcAndHistoryEnabled extends AllNestedConditions {

        OnJdbcAndHistoryEnabled() {
            super(ConfigurationPhase.PARSE_CONFIGURATION);
        }

        @ConditionalOnClass(
                name = "org.springframework.jdbc.core.JdbcTemplate"
        )
        static class JdbcTemplatePresent {
        }

        @ConditionalOnProperty(
                prefix = "acme.notice.history",
                name = "enabled",
                havingValue = "true",
                matchIfMissing = false
        )
        static class HistoryFeatureEnabled {
        }
    }
}
~~~

Reading the configuration in order:

1. AutoConfiguration declares the primary auto-configuration.
2. JdbcHistoryConfiguration is the configuration group applied only when OnJdbcAndHistoryEnabled matches.
3. OnJdbcAndHistoryEnabled extends AllNestedConditions.
4. JdbcTemplatePresent checks the JDBC class by class name, avoiding class literals in an optional condition.
5. HistoryFeatureEnabled checks that the property has the value true.
6. The constructor selects PARSE_CONFIGURATION because both member conditions can be evaluated early.
7. The bean method checks for a JdbcTemplate bean and backs off if NoticeHistoryWriter has already been provided by the application.

The nested class JdbcHistoryConfiguration contains a method signature referencing JdbcTemplate. It is processed only when the classpath/property group matches, allowing applications without Spring JDBC to skip this integration safely.

### 6.5. Registering Auto-Configuration

When packaging the module as a JAR for Spring Boot 3, create the file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Contents:

~~~text
com.acme.notice.autoconfigure.NoticeHistoryAutoConfiguration
~~~

This file registers the auto-configuration with Spring Boot. Tests using AutoConfigurations.of(...) load the class directly, so those tests focus on condition and bean behavior; they do not by themselves prove that imports metadata was packaged properly in the JAR.

## 7. Testing Condition Combinations with ApplicationContextRunner

ApplicationContextRunner creates an isolated context for each run(...) call. This works well for testing every combination of classpath, properties, and beans without starting the whole application.

File src/test/java/com/acme/notice/autoconfigure/NoticeHistoryAutoConfigurationTest.java:

~~~java
package com.acme.notice.autoconfigure;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.assertj.core.api.Assertions.assertThat;

class NoticeHistoryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            NoticeHistoryAutoConfiguration.class
                    ));

    @Test
    void createsWriterWhenEveryRequirementMatches() {
        runner.withPropertyValues("acme.notice.history.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeHistoryWriter.class);

                    NoticeHistoryWriter writer =
                            context.getBean(NoticeHistoryWriter.class);

                    assertThat(writer.jdbcTemplateType())
                            .isEqualTo("JdbcTemplate");
                    assertThat(writer.describe())
                            .isEqualTo("history-writer:JdbcTemplate");
                });
    }

    @Test
    void propertyFalseMakesAllNestedConditionsNoMatch() {
        runner.withPropertyValues("acme.notice.history.enabled=false")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeHistoryWriter.class)
                );
    }

    @Test
    void missingJdbcClassMakesAllNestedConditionsNoMatch() {
        runner.withClassLoader(
                new FilteredClassLoader("org.springframework.jdbc")
        ).withPropertyValues("acme.notice.history.enabled=true")
         .run(context ->
                 assertThat(context)
                         .doesNotHaveBean(NoticeHistoryWriter.class)
         );
    }

    @Test
    void matchingGroupStillNeedsJdbcTemplateBean() {
        runner.withPropertyValues("acme.notice.history.enabled=true")
                .run(context ->
                        assertThat(context)
                                .doesNotHaveBean(NoticeHistoryWriter.class)
                );
    }

    @Test
    void userWriterMakesDefaultFactoryMethodBackOff() {
        NoticeHistoryWriter custom =
                new NoticeHistoryWriter("application");

        runner.withPropertyValues("acme.notice.history.enabled=true")
                .withBean(JdbcTemplate.class, JdbcTemplate::new)
                .withBean(NoticeHistoryWriter.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(NoticeHistoryWriter.class);

                    assertThat(context.getBean(NoticeHistoryWriter.class))
                            .isSameAs(custom);
                });
    }
}
~~~

### 7.1. Case Where All Conditions Match

Test createsWriterWhenEveryRequirementMatches provides:
- Spring JDBC present on the classpath.
- acme.notice.history.enabled=true.
- A JdbcTemplate bean.

The AllNestedConditions group matches and the bean method also matches, so NoticeHistoryWriter is created.

The test checks both the bean count and the jdbcTemplateType content to prove the factory method used the dependency.

### 7.2. Property False

Test propertyFalseMakesAllNestedConditionsNoMatch still provides JdbcTemplate, but the property is false.

One unmatched member condition causes the entire group not to match. Because the nested configuration is skipped, the writer does not appear.

### 7.3. Missing JDBC Class

Test missingJdbcClassMakesAllNestedConditionsNoMatch uses FilteredClassLoader to simulate a runtime classpath lacking the org.springframework.jdbc package.

The property is still true, but the classpath condition does not match. The composite group does not match and the nested configuration is not applied.

This is a useful way to test optional integrations: the library's core can run in consumers that do not install Spring JDBC, while the JDBC adapter is skipped automatically.

### 7.4. Class and Property Present but JdbcTemplate Bean Missing

Test matchingGroupStillNeedsJdbcTemplateBean has:
- Spring JDBC on the classpath.
- Property enabled.
- No JdbcTemplate bean.

Both nested conditions in AllNestedConditions match, but ConditionalOnBean(JdbcTemplate.class) on the bean method does not match. As a result, the writer still does not appear.

This case proves AllNestedConditions only resolves the declared classpath/property group. It does not replace the bean condition at the bean-registration layer.

### 7.5. Application Provides a Custom Writer

Test userWriterMakesDefaultFactoryMethodBackOff supplies all prerequisites plus a custom NoticeHistoryWriter bean.

The composite group matches. ConditionalOnBean(JdbcTemplate.class) also matches, but ConditionalOnMissingBean(NoticeHistoryWriter.class) does not match. The context keeps the application's instance.

This is the desired back-off behavior of auto-configuration.

## 8. Running Tests and Expected Results

From the project directory containing pom.xml:

~~~bash
mvn clean test
~~~

Expect all five tests in NoticeHistoryAutoConfigurationTest to PASS:

| Test | Classpath + property group | JdbcTemplate bean | Result |
| --- | --- | --- | --- |
| createsWriterWhenEveryRequirementMatches | Match | Present | Default writer created |
| propertyFalseMakesAllNestedConditionsNoMatch | No match | Present | No writer |
| missingJdbcClassMakesAllNestedConditionsNoMatch | No match | Cannot exist | No writer |
| matchingGroupStillNeedsJdbcTemplateBean | Match | Absent | No writer |
| userWriterMakesDefaultFactoryMethodBackOff | Match | Present | Custom writer kept |

Maven Surefire prints total tests, errors, failures, and execution time. Timing details can vary across machines; do not use them as assertions.

No database server is needed because the lab only tests bean creation and using JdbcTemplate as a dependency. In a real application, the adapter may execute SQL; in that case, write separate integration tests against an appropriate database.

## 9. Reading ConditionEvaluationReport to Understand Condition Groups

When a test fails, you can read ConditionEvaluationReport inside the runner callback to see which source matched or did not match.

Example helper:

~~~java
private static void printConditionReport(
        org.springframework.context.ApplicationContext context) {

    var report = ConditionEvaluationReport.find(
            ((org.springframework.context.ConfigurableApplicationContext) context)
                    .getBeanFactory()
    );

    if (report == null) {
        System.out.println("Condition report not available");
        return;
    }

    report.getConditionAndOutcomesBySource()
            .forEach((source, outcomes) -> {
                System.out.println(
                        source + " => "
                                + (outcomes.isFullMatch()
                                    ? "MATCH"
                                    : "NO MATCH")
                );

                outcomes.forEach(item -> {
                    var outcome = item.getOutcome();

                    System.out.println(
                            "  " + item.getCondition().getClass().getSimpleName()
                                    + " => "
                                    + (outcome.isMatch()
                                        ? "MATCH"
                                        : "NO MATCH")
                                    + " : "
                                    + outcome.getMessage()
                    );
                });
            });
}
~~~

Inside an ApplicationContextRunner callback, context is an AssertableApplicationContext. You can extract the source application context and pass it to the helper above. The helper uses ApplicationContext to illustrate retrieving the BeanFactory; when using it in tests, import ConditionEvaluationReport.

The report can show why the composite custom condition did not match along with aggregated messages from the nested conditions. Do not compare the entire message against a fixed string because wording can change across Spring Boot releases.

Distinguish:
- The report tells you which conditions matched/did not match.
- Bean assertions tell you the final outcome in the context.
- The stack trace tells you bean creation errors if conditions matched yet the factory method or constructor failed.

Use all three pieces of evidence when investigating failures.

## 10. Combining Property and Classpath Conditions Directly

If a configuration only has two conditions, you can place them directly:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "org.springframework.jdbc.core.JdbcTemplate")
@ConditionalOnProperty(
        prefix = "acme.notice.history",
        name = "enabled",
        havingValue = "true"
)
public class NoticeHistoryAutoConfiguration {
}
~~~

Multiple condition annotations on the same configuration are combined with AND. This is the simpler choice when you do not need a named composite condition or reuse.

Use AllNestedConditions when you want to encapsulate the condition group:

~~~java
@Conditional(OnJdbcAndHistoryEnabled.class)
class JdbcHistoryConfiguration {
}
~~~

Comparison:

| Criterion | Direct annotations | AllNestedConditions |
| --- | --- | --- |
| Simple AND conditions | Very suitable | Works, though more verbose |
| Reusing the condition group | Must repeat annotations or create a meta-annotation | Has a named condition class |
| Grouping many branches | Hard to organize when complex | Each branch is a nested class |
| Reading rule name | Read each annotation individually | Can read OnJdbcAndHistoryEnabled |
| Controlling ConfigurationPhase | Determined by the condition annotations | Specified in the constructor |

Do not use AllNestedConditions just to replace two annotations unless it adds real organizational or reuse value.

## 11. Notes on Optional Dependencies and Class Loading

When a condition checks an optional class:
- Use ConditionalOnClass(name = "...") to specify the class name as a string.
- Isolate method signatures needing the optional type inside a nested configuration guarded by the condition.
- Do not let the outer/core configuration directly reference optional types in fields, method signatures, or class literals if consumers may lack the dependency.
- The Maven dependency for the integration should be declared in the right module and can be marked optional if consumers should opt in to that module.
- Test with FilteredClassLoader to simulate a runtime classpath missing the class.

In this lab's example, JdbcTemplate only appears inside the nested configuration JdbcHistoryConfiguration. The outer auto-configuration and the custom condition do not use the JdbcTemplate class literal in condition metadata; ConditionalOnClass checks by name.

If the integration module is always published with spring-jdbc as a mandatory dependency, the classpath condition may be less critical. However, when designing an optional starter or multi-module library, conditions still keep configuration application explicit.

## 12. Common Mistakes When Using AllNestedConditions

1. **Confusing AND with OR.** AllNestedConditions requires every nested condition to match; one true condition is not enough.
2. **Using the wrong combinator class.** Choose AnyNestedCondition if only one branch is needed, NoneNestedConditions if no branch may match.
3. **Forgetting to call the parent constructor.** Subclasses must pass ConfigurationPhase to AllNestedConditions.
4. **Picking a phase arbitrarily.** The phase must match the nested conditions; classpath/properties typically use PARSE_CONFIGURATION.
5. **Mixing bean-dependent conditions into a parse-phase group.** ConditionalOnBean should be handled at the appropriate bean-registration scope and phase.
6. **Non-static nested member classes.** Condition member classes must be static so Boot can discover and evaluate them.
7. **Placing the condition at too broad a scope.** An optional feature can accidentally block all other beans in the auto-configuration.
8. **Putting optional classes in the outer config's signatures.** Applications missing the dependency can encounter class-loading errors before the condition can guard the configuration.
9. **Misusing class literals for optional classes.** For dependencies that may be absent, use class names in ConditionalOnClass and appropriate nested configurations.
10. **Assuming a group match guarantees bean creation.** The bean method can still be blocked by ConditionalOnBean or ConditionalOnMissingBean.
11. **Not testing every combination.** Testing only the all-conditions-true case misses property-false or missing-class branches.
12. **Not testing missing classpath.** Optional integrations can break core-only applications at runtime when the extra library is absent.
13. **Not testing missing bean dependencies.** Classpath and properties may be satisfied while the context still lacks the bean needed by the factory method.
14. **Not testing user overrides.** Default beans may compete with beans provided by the application.
15. **Using a composite condition for too small a group.** Two direct annotations can be more readable.
16. **Treating report messages as a stable API.** Assert status and key content rather than comparing the entire message verbatim.
17. **Failing to distinguish intentional no-match from errors.** An unmatched condition is typically how auto-configuration yields control to the application.
18. **Correct property name with wrong prefix.** A nested condition will not match if the property name does not follow the contract.
19. **Unclear matchIfMissing setting.** Decide and test behavior when the property does not exist.
20. **Not updating property documentation.** Users need to know every required condition for the feature to activate.

## 13. Design and Testing Workflow for Condition Groups

1. State the requirement in natural language: which conditions must all hold for the feature?
2. Classify each condition: classpath, property, bean, resource, environment, or custom condition.
3. Determine the appropriate phase for each condition.
4. Group only conditions with compatible phases into AllNestedConditions.
5. Create nested static classes, each representing one condition.
6. Attach the composite condition to the configuration or nested configuration at the right scope.
7. Keep bean conditions on the bean method if they belong to the bean-registration stage.
8. Keep ConditionalOnMissingBean to support user overrides when appropriate.
9. Write a truth table for important combinations.
10. Test all-match, single-condition no-match, and missing bean dependency cases.
11. Use FilteredClassLoader to test absent optional classes.
12. Read ConditionEvaluationReport when you need to explain the cause.
13. Run mvn clean test and inspect all results.
14. If testing the auto-configuration class directly, add consumer/packaged tests to verify imports metadata inside the JAR.

## 14. Acceptance Checklist

- [ ] AND rule is clearly described and fits AllNestedConditions.
- [ ] Each member condition has its own nested static class.
- [ ] Constructor calls super(ConfigurationPhase...).
- [ ] ConfigurationPhase fits the member conditions.
- [ ] Composite condition is attached to the right configuration.
- [ ] Property condition has exact prefix, name, and havingValue.
- [ ] Classpath condition guards optional dependencies.
- [ ] Optional types are isolated from outer/core configurations.
- [ ] Bean conditions are placed at the appropriate phase/scope.
- [ ] ConditionalOnMissingBean supports user overrides.
- [ ] Tested when all nested conditions match.
- [ ] Tested when each member condition does not match.
- [ ] Tested when optional classes are absent.
- [ ] Tested when bean dependencies are absent.
- [ ] Tested when the application supplies an alternative bean.
- [ ] Distinguished All, Any, and None with a truth table.
- [ ] Reports or assertions help explain no-match reasons.
- [ ] Ran mvn clean test.
- [ ] AutoConfiguration.imports metadata is verified separately if packaged as a JAR.

## 15. Self-Check Questions

**Question 1.** When does AllNestedConditions match?  
**Answer:** When all nested class conditions match. Even a single no-match condition makes the composite condition not match.

**Question 2.** How does AnyNestedCondition differ from AllNestedConditions?  
**Answer:** Any requires at least one nested condition to match; All requires every condition to match.

**Question 3.** When does NoneNestedConditions match?  
**Answer:** When no nested condition matches.

**Question 4.** Why do the classpath and property examples use PARSE_CONFIGURATION?  
**Answer:** Both conditions can be evaluated early while Spring parses configuration classes.

**Question 5.** Why was ConditionalOnBean(JdbcTemplate.class) not placed in the parse-phase group in the lab?  
**Answer:** Bean conditions depend on bean definitions and belong to the bean-registration stage; the lab keeps it on a separate factory method.

**Question 6.** If the property is enabled but the Spring JDBC class is absent, what happens?  
**Answer:** One nested condition does not match, so the entire AllNestedConditions does not match and the nested configuration is skipped.

**Question 7.** If the AllNestedConditions group matches but the context has no JdbcTemplate bean, what happens?  
**Answer:** The classpath/property group still matches, but ConditionalOnBean on the bean method does not match, so the writer is not created.

**Question 8.** Why should you test with FilteredClassLoader?  
**Answer:** To simulate a runtime classpath lacking an optional dependency and prove the integration is skipped safely.

**Question 9.** Does every AND group require AllNestedConditions?  
**Answer:** No. Simple conditions can be placed directly on the same configuration; All is useful when you need a name, reuse, or clear logical grouping.

## 16. Official References

- [Spring Boot 3.3.13 Javadoc — AllNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AllNestedConditions.html).
- [Spring Boot 3.3.13 Javadoc — AnyNestedCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/AnyNestedCondition.html).
- [Spring Boot 3.3.13 Javadoc — NoneNestedConditions](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/NoneNestedConditions.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnClass](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- [Spring Boot 3.3.13 Javadoc — FilteredClassLoader](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html).
- [Spring Boot Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).