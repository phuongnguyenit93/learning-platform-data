# SpringBootCondition and getMatchOutcome for Explainable Results

## 1. Why Does a Custom Condition Need Explainable Decisions?

Spring Boot uses conditions to decide whether to register a configuration or bean. Built-in annotations such as **@ConditionalOnClass**, **@ConditionalOnProperty**, and **@ConditionalOnMissingBean** already cover most common requirements.

When writing a custom condition, Spring's **Condition** interface lets you implement **matches(...)** and return a boolean. That result is enough for Spring to decide whether the configuration is applied, but a boolean does not explain why the condition matched or did not match.

For example, an integration gateway only activates when:

- Property **app.gateway.enabled** has the value **true**.
- **app.gateway.provider** equals the provider required by the configuration.
- Library **GatewayClient** is present on the classpath.

If the bean is not created, operators need to know which condition failed. Merely seeing that the bean is absent does not distinguish whether the property is disabled, the provider is wrong, or the dependency was not packaged.

**SpringBootCondition** is Spring Boot's base class for conditions whose results include diagnostic messages. Instead of writing matches returning a boolean yourself, you override **getMatchOutcome(...)** to return a **ConditionOutcome**, containing both the match/no-match state and a message describing the reason.

## 2. Spring Condition and SpringBootCondition

| Component | Responsibility |
| --- | --- |
| **org.springframework.context.annotation.Condition** | Spring's general contract: matches(context, metadata) returns boolean |
| **SpringBootCondition** | Boot's base class, adding logging and condition outcome recording |
| **getMatchOutcome(...)** | Custom callback that subclasses must implement |
| **ConditionOutcome** | Match/no-match result along with a message |
| **ConditionMessage** | Builder for producing consistent, readable messages |
| **ConditionEvaluationReport** | Stores condition results by evaluated class or method |

SpringBootCondition implements Condition. Its **matches(...)** method is **final**: Boot orchestrates evaluation, calls getMatchOutcome(...), logs the result, and records it in the report. Therefore, subclasses only override getMatchOutcome; do not override matches and do not call logOutcome directly.

Key signature:

~~~java
public abstract class SpringBootCondition implements Condition {

    public final boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {
        // Spring Boot controls evaluation and outcome recording.
    }

    public abstract ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata);
}
~~~

This is an overview signature illustrating the relationship between the two methods. When implementing, extend the actual class from package org.springframework.boot.autoconfigure.condition.

### 2.1. When Should You Use SpringBootCondition?

Use it when the condition has combined logic or domain-specific rules that built-in annotations do not express clearly, and operators need to know the cause of a match/no-match.

Good examples:

- Choosing an implementation based on properties and classpath capabilities.
- Checking a resource together with a special configuration setting.
- Evaluating a combination of multiple ordered conditions and needing distinct messages per branch.
- Checking a custom provider and then explaining which provider was accepted.

For simple conditions, prefer built-in annotations:

| Need | API to use first |
| --- | --- |
| Class present on classpath | **@ConditionalOnClass** |
| Property has a specific value | **@ConditionalOnProperty** |
| No alternative bean exists yet | **@ConditionalOnMissingBean** |
| Matching bean exists | **@ConditionalOnBean** |
| Single unique candidate exists | **@ConditionalOnSingleCandidate** |
| Resource exists | **@ConditionalOnResource** |
| Custom logic requiring messages | **SpringBootCondition** |

Custom conditions add maintenance responsibility. Only create one when the logic genuinely needs it; do not reimplement a built-in annotation just to change log phrasing.

## 3. Understanding the Parameters of getMatchOutcome

The method takes two parameters:

~~~java
public abstract ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

### 3.1. ConditionContext

ConditionContext provides the environment for evaluating the condition:

| API | Can be used to |
| --- | --- |
| getEnvironment() | Read properties, profiles, and Environment |
| getClassLoader() | Check whether a class can be loaded |
| getResourceLoader() | Locate resources using Spring's mechanism |
| getRegistry() | Access the bean definition registry if available |
| getBeanFactory() | Read BeanFactory info when available at the current phase |

In a condition, prefer checking metadata, properties, classpath, and bean definitions. Do not call databases, HTTP services, or instantiate business beans to decide a condition. Conditions are evaluated during configuration processing; side effects or I/O here make startup unpredictable and hard to test.

A condition should be fast, deterministic, and independent of randomly changing state.

### 3.2. AnnotatedTypeMetadata

AnnotatedTypeMetadata describes the class or method carrying the condition annotation. It lets you read attributes without creating a bean.

Commonly used APIs:

- isAnnotated(annotationName): checks whether the metadata has the annotation.
- getAnnotationAttributes(annotationName): retrieves a map of the annotation's attributes.
- getAllAnnotationAttributes(annotationName): retrieves annotation values in the metadata.

For example, a custom annotation has a provider attribute. The condition can read this value from metadata instead of hard-coding a single provider.

Do not assume metadata always represents a class. If the condition is placed on a @Bean method, metadata may describe that method. Write code suited to every location where the annotation is allowed to appear.

## 4. ConditionOutcome and ConditionMessage

### 4.1. ConditionOutcome

ConditionOutcome represents the result of a condition along with an accompanying message.

Important factory methods:

~~~java
ConditionOutcome.match();
ConditionOutcome.match("reason");
ConditionOutcome.match(conditionMessage);

ConditionOutcome.noMatch("reason");
ConditionOutcome.noMatch(conditionMessage);
~~~

Read the result via:

- isMatch(): whether the condition matched.
- getMessage(): the message as a String or null.
- getConditionMessage(): the message as a ConditionMessage or null.

When writing a new condition, return a meaningful message for both match and no-match branches. A specific reason helps readers understand which requirement was or was not satisfied.

### 4.2. ConditionMessage

ConditionMessage provides a fluent builder so messages follow a consistent structure.

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition("GatewayModeCondition");

ConditionMessage matched = message.foundExactly("primary gateway");
ConditionMessage rejected = message.because("provider is not configured");
~~~

Common ways to build messages:

| Builder method | Meaning |
| --- | --- |
| foundExactly(value) | Found the exact expected value |
| found("bean") | Found one or more items |
| didNotFind("required class") | Did not find a required item |
| available("resource") | Resource is available |
| notAvailable("resource") | Resource is not available |
| because(reason) | States the reason |
| items(Style.QUOTE, values) | Lists values with quotes |
| append(text) | Appends details to an already built message |

You can initialize the builder with a condition name and details:

~~~java
ConditionMessage.Builder message =
        ConditionMessage.forCondition(
                "GatewayModeCondition",
                "provider=primary"
        );
~~~

Use a stable condition name, keep descriptions concise, and avoid putting sensitive data such as passwords, tokens, or connection strings into messages.

### 4.3. Choosing match or noMatch Semantically

- Return ConditionOutcome.match(message) when all required conditions hold.
- Return ConditionOutcome.noMatch(message) when the configuration is valid but the condition is not satisfied.
- Only throw an exception when startup truly must fail according to the configuration contract; do not use exceptions in place of a normal no-match branch.

Never return null. Every code path in getMatchOutcome must produce an explicit outcome.

**Spring Boot 3.5 Note:** ConditionOutcome.inverse(...) was deprecated as of 3.5.0 and marked for removal in 4.0.0. When you need to invert a result, create a new outcome with an appropriate message instead of using this API.

## 5. Complete Example: Condition Selecting a Gateway by Provider

We will create a custom condition for an integration gateway. The configuration matches only when all of the following hold:

1. app.gateway.enabled has the value true.
2. app.gateway.provider equals primary, matching the annotation attribute.
3. Class example.gateway.GatewayClient is on the classpath.

The example uses Java 17 and Spring Boot 3.5.0.

### 5.1. Project Structure

~~~text
gateway-condition-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   ├── example/
    │   │   │   ├── gateway/
    │   │   │   │   └── GatewayClient.java
    │   │   │   └── autoconfigure/
    │   │   │       ├── ConditionalOnGatewayMode.java
    │   │   │       ├── GatewayModeCondition.java
    │   │   │       ├── GatewayFeature.java
    │   │   │       └── GatewayAutoConfiguration.java
    │   └── resources/
    │       └── META-INF/
    │           └── spring/
    │               └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/
            └── example/
                └── autoconfigure/
                    └── GatewayModeConditionTests.java
~~~

### 5.2. File pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>gateway-condition-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
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

### 5.3. File GatewayClient.java

This class represents an external gateway library. In a real starter, this class typically comes from a separate dependency.

~~~java
package example.gateway;

public final class GatewayClient {

    public String ping() {
        return "gateway-ready";
    }
}
~~~

### 5.4. File ConditionalOnGatewayMode.java

This annotation lets configurations declare the provider to select. It is meta-annotated with @Conditional so Spring invokes the corresponding condition.

~~~java
package example.autoconfigure;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(GatewayModeCondition.class)
public @interface ConditionalOnGatewayMode {

    String provider();
}
~~~

### 5.5. File GatewayModeCondition.java

~~~java
package example.autoconfigure;

import java.util.Map;

import org.springframework.boot.autoconfigure.condition.ConditionMessage;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;
import org.springframework.util.ClassUtils;

public final class GatewayModeCondition extends SpringBootCondition {

    private static final String ENABLED_PROPERTY = "app.gateway.enabled";
    private static final String PROVIDER_PROPERTY = "app.gateway.provider";
    private static final String REQUIRED_CLIENT = "example.gateway.GatewayClient";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        Map<String, Object> attributes =
                metadata.getAnnotationAttributes(
                        ConditionalOnGatewayMode.class.getName()
                );

        if (attributes == null) {
            return ConditionOutcome.noMatch(
                    ConditionMessage.forCondition("GatewayModeCondition")
                            .because("ConditionalOnGatewayMode metadata is missing")
            );
        }

        String expectedProvider = (String) attributes.get("provider");

        ConditionMessage.Builder message =
                ConditionMessage.forCondition(
                        "GatewayModeCondition",
                        "provider=" + expectedProvider
                );

        String enabled = context.getEnvironment()
                .getProperty(ENABLED_PROPERTY);

        if (!"true".equalsIgnoreCase(enabled)) {
            return ConditionOutcome.noMatch(
                    message.because(ENABLED_PROPERTY + " is not true")
            );
        }

        String actualProvider = context.getEnvironment()
                .getProperty(PROVIDER_PROPERTY);

        if (!expectedProvider.equals(actualProvider)) {
            String reason = (actualProvider == null || actualProvider.isBlank())
                    ? PROVIDER_PROPERTY + " is not set"
                    : PROVIDER_PROPERTY + " is " + actualProvider;

            return ConditionOutcome.noMatch(message.because(reason));
        }

        if (!ClassUtils.isPresent(REQUIRED_CLIENT, context.getClassLoader())) {
            return ConditionOutcome.noMatch(
                    message.didNotFind("required class")
                            .items(ConditionMessage.Style.QUOTE, REQUIRED_CLIENT)
            );
        }

        return ConditionOutcome.match(
                message.foundExactly(REQUIRED_CLIENT)
                        .append(" with " + ENABLED_PROPERTY + "=true"
                                + " and " + PROVIDER_PROPERTY + "=" + expectedProvider)
        );
    }
}
~~~

Reading the code in order:

1. Retrieve the provider value from annotation metadata.
2. Check the enable/disable property.
3. Check whether the actual provider matches the provider requested by the annotation.
4. Check the external library class.
5. Return match/no-match along with a message describing the deciding branch.

The condition does not create GatewayClient, open connections, or invoke beans. It only checks the Environment and classpath. Object creation occurs later inside the bean factory method.

### 5.6. File GatewayFeature.java

~~~java
package example.autoconfigure;

public record GatewayFeature(String provider, String status) {
}
~~~

### 5.7. File GatewayAutoConfiguration.java

The condition is placed on a nested configuration. This isolates method signatures referencing optional dependencies: when the condition does not match, Spring skips the nested configuration before processing its bean methods.

~~~java
package example.autoconfigure;

import example.gateway.GatewayClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class GatewayAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnGatewayMode(provider = "primary")
    static class PrimaryGatewayConfiguration {

        @Bean
        GatewayClient gatewayClient() {
            return new GatewayClient();
        }

        @Bean
        GatewayFeature gatewayFeature(GatewayClient client) {
            return new GatewayFeature("primary", client.ping());
        }
    }
}
~~~

Register the auto-configuration in META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports:

~~~text
example.autoconfigure.GatewayAutoConfiguration
~~~

In the test below, the runner loads the class directly with AutoConfigurations.of(...) so it does not rely on scanning imports resources. The imports file is still required when the starter is consumed by a real application.

### 5.8. File GatewayModeConditionTests.java

~~~java
package example.autoconfigure;

import example.gateway.GatewayClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.autoconfigure.condition.ConditionEvaluationReport;
import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.assertj.AssertableApplicationContext;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayModeConditionTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(GatewayAutoConfiguration.class)
                    );

    @Test
    void matchesWhenEnabledProviderAndClientAreAvailable() {
        runner.withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).hasSingleBean(GatewayFeature.class);

                    GatewayFeature feature =
                            context.getBean(GatewayFeature.class);

                    assertThat(feature.provider()).isEqualTo("primary");
                    assertThat(feature.status()).isEqualTo("gateway-ready");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isTrue();
                    assertThat(outcome.getMessage())
                            .contains("example.gateway.GatewayClient")
                            .contains("app.gateway.enabled=true");
                });
    }

    @Test
    void doesNotMatchWhenFeatureIsDisabled() {
        runner.withPropertyValues(
                        "app.gateway.enabled=false",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("app.gateway.enabled is not true");
                });
    }

    @Test
    void doesNotMatchWhenProviderIsDifferent() {
        runner.withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=backup"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("app.gateway.provider is backup");
                });
    }

    @Test
    void doesNotMatchWhenRequiredClientIsMissing() {
        runner.withClassLoader(new FilteredClassLoader(GatewayClient.class))
                .withPropertyValues(
                        "app.gateway.enabled=true",
                        "app.gateway.provider=primary"
                )
                .run(context -> {
                    assertThat(context).doesNotHaveBean("gatewayFeature");

                    ConditionOutcome outcome = gatewayOutcome(context);
                    assertThat(outcome.isMatch()).isFalse();
                    assertThat(outcome.getMessage())
                            .contains("required class")
                            .contains("example.gateway.GatewayClient");
                });
    }

    private ConditionOutcome gatewayOutcome(
            AssertableApplicationContext context) {

        ConditionEvaluationReport report =
                ConditionEvaluationReport.get(context.getBeanFactory());

        for (ConditionEvaluationReport.ConditionAndOutcomes outcomes
                : report.getConditionAndOutcomesBySource().values()) {

            for (ConditionEvaluationReport.ConditionAndOutcome item : outcomes) {
                if (item.getCondition() instanceof GatewayModeCondition) {
                    return item.getOutcome();
                }
            }
        }

        throw new AssertionError("GatewayModeCondition was not recorded");
    }
}
~~~

### 5.9. Running the Tests

Use JDK 17+ and Maven in the directory containing pom.xml:

~~~bash
java -version
mvn -version
mvn test
~~~

**Expected result:** four JUnit tests pass and Maven finishes with BUILD SUCCESS if dependencies resolve successfully. The tests do not call System.out.println, so there is no fixed business stdout. Test reports are placed in target/surefire-reports.

This is the expected outcome from the example; run Maven on the project to verify in your actual environment. The example uses FilteredClassLoader to simulate a missing dependency even though the sample class still exists in the test project.

## 6. How Does Spring Boot Record and Explain Conditions?

### 6.1. Logging During Evaluation

SpringBootCondition.matches coordinates evaluation and logs based on ConditionOutcome. The message built in getMatchOutcome helps logs explain why the condition matched or did not match.

If a message only says "matched" without stating why, operators still have to infer the cause. Explicitly include which property, class, or provider satisfied the condition.

Examples of meaningful diagnostic content:

| Result | Message |
| --- | --- |
| Match | Found GatewayClient with enabled=true and provider=primary |
| No match | app.gateway.enabled is not true |
| No match | app.gateway.provider is backup |
| No match | Did not find required class GatewayClient |

The actual message is rendered according to ConditionMessage and the Boot version; the table above illustrates the meaning rather than verbatim log output.

### 6.2. ConditionEvaluationReport

ConditionEvaluationReport stores condition evaluation results grouped by source, which is the configuration class or bean method. Each entry contains the condition and its corresponding outcome.

Commonly used API:

~~~java
ConditionEvaluationReport report =
        ConditionEvaluationReport.get(beanFactory);

Map<String, ConditionEvaluationReport.ConditionAndOutcomes> results =
        report.getConditionAndOutcomesBySource();
~~~

Each ConditionAndOutcome provides:

- getCondition(): the condition that was evaluated.
- getOutcome(): the match/no-match result along with its message.

This report is useful when an auto-configuration has multiple nested configurations or multiple conditional bean methods. You can pinpoint exactly which branch was skipped and why.

### 6.3. Viewing the Report When Running the Application

There are two common ways:

- Run the application with --debug so Spring Boot prints the condition evaluation report in the startup logs.
- If the application includes Spring Boot Actuator, use the /actuator/conditions endpoint when it is properly configured and exposed.

The conditions endpoint presents positive/negative matches, conditions, and messages. It is intended for configuration diagnostics; do not use responses from this endpoint as a business API for application code.

## 7. Rules for Writing Maintainable getMatchOutcome Implementations

### 7.1. Every No-Match Branch Must Have Its Own Reason

Avoid writing a single catch-all branch such as:

~~~java
if (!enabled || !providerMatches || !clientPresent) {
    return ConditionOutcome.noMatch("Condition not satisfied");
}
~~~

That message does not tell the operator whether to fix the property, the provider, or a dependency.

Instead, check sequentially and return a specific message for the first failing branch. If you need to display multiple conditions at once, aggregate ConditionMessages or use an appropriate nested condition structure.

### 7.2. Do Not Use Conditions as a Replacement for Validation

A condition answers the question "should this configuration be applied?". Validation answers "is the configuration entered by the user valid?".

For example:

- app.gateway.enabled=false: condition not matching is normal.
- app.gateway.provider=unknown: may be a no-match or a validation error, depending on the product contract.
- app.gateway.timeout=-1: this is typically a configuration error needing validation, and should not silently turn into a condition no-match.

Choose clear behavior and document it. If enabling a feature while missing a dependency must fail startup, design an intentional fail-fast check rather than letting a NoClassDefFoundError occur later in another bean.

### 7.3. Avoid Side Effects and Early Bean Access

Inside getMatchOutcome, do not:

- Call context.getBeanFactory().getBean(...) to instantiate a bean.
- Open a connection to a database or broker.
- Send an HTTP request to check an external service.
- Modify the Environment or register bean definitions.
- Write files or mutate application state.
- Rely on unguaranteed bean initialization order.

Conditions may be evaluated before regular beans exist. Read only the metadata and configuration state needed for the decision.

### 7.4. Do Not Duplicate Built-In Conditions

If you only need to check class presence, use @ConditionalOnClass. If you only check a property, use @ConditionalOnProperty. These annotations already include Boot's built-in messages and reporting.

Custom conditions should focus on specialized logic, such as combining an annotation's provider attribute, properties, and classpath capability as in the example.

### 7.5. Choose the Right Phase When Depending on Bean Definitions

Conditions can be evaluated at different stages of configuration processing. If your logic depends on whether bean definitions have already been fully registered, study ConfigurationCondition and ConfigurationPhase before implementing. Do not assume every condition runs after all beans already exist.

For typical bean checks, prefer @ConditionalOnBean or @ConditionalOnMissingBean and place them in auto-configurations ordered appropriately by Spring Boot.

## 8. Common Mistakes

1. **Returning only a boolean with Condition.** It still works, but lacks outcome messages and Spring Boot's built-in diagnostic reporting.
2. **Overriding matches in SpringBootCondition.** That method is final; override getMatchOutcome instead.
3. **Returning null from getMatchOutcome.** Always return ConditionOutcome.match(...) or ConditionOutcome.noMatch(...).
4. **Overly generic messages.** "Condition failed" does not indicate which property, class, or provider needs fixing.
5. **Only crafting messages for the match branch.** No-match is the branch operators need to diagnose most often; explain the reason.
6. **Reading the annotation with the wrong name.** Use the exact fully qualified name of the custom annotation when calling getAnnotationAttributes.
7. **Assuming metadata always describes a class.** A condition placed on a @Bean method can receive method metadata.
8. **Referencing optional classes directly in the root configuration.** Isolate method signatures inside a nested configuration with an appropriate class condition.
9. **Using a class literal to check an optional dependency inside the condition itself.** If the class is missing, a class literal can cause loading errors; use a class name with the classloader or @ConditionalOnClass.
10. **Creating beans or making network calls in a condition.** This causes side effects during configuration processing and makes startup unpredictable.
11. **Using no-match to hide missing mandatory configuration.** If the product requires startup to fail, provide explicit validation/fail-fast behavior.
12. **Repeating built-in annotations.** Use a custom condition only when the logic cannot be expressed clearly with built-in APIs.
13. **Using ConditionEvaluationReport as a business API.** The report is for diagnostics; do not let runtime logic depend on log output or the Actuator endpoint.
14. **Not testing both outcomes.** Test match and every significant no-match cause.
15. **Not checking messages in tests.** Bean absence alone does not prove the condition explained the right cause.
16. **Using ConditionOutcome.inverse in Boot 3.5.** The API is deprecated for removal; create a new outcome with a semantically accurate message.
17. **Forgetting classpath tests.** Tests often have optional dependencies present; use FilteredClassLoader to verify the missing-dependency branch.
18. **Putting sensitive data in messages.** Never log passwords, tokens, or connection strings in the condition report.

## 9. Custom Condition Review Checklist

- [ ] Have you checked whether built-in annotations already satisfy the requirement?
- [ ] Does the condition genuinely need to extend SpringBootCondition?
- [ ] Only getMatchOutcome is overridden, not matches.
- [ ] Every code path returns a ConditionOutcome.
- [ ] Clear messages exist for match and each important no-match cause.
- [ ] ConditionContext and AnnotatedTypeMetadata are read appropriately.
- [ ] No beans created, no network calls, no database connections, and no side effects.
- [ ] Optional classes are checked safely and isolated in nested configurations if needed.
- [ ] Bean conditions use @ConditionalOnBean/@ConditionalOnMissingBean when appropriate.
- [ ] Tests cover match, no-match, missing/invalid property, different provider, and missing classpath.
- [ ] Tests check both ConditionOutcome.isMatch() and the message.
- [ ] Condition report can be used for startup diagnostics.
- [ ] No deprecated APIs such as ConditionOutcome.inverse are used.

## 10. Self-Check Questions

**Question 1.** How does SpringBootCondition differ from basic Condition?  
**Answer:** It adds logging and message-bearing outcome recording; subclasses return ConditionOutcome instead of just a boolean.

**Question 2.** Which method must be overridden when extending SpringBootCondition?  
**Answer:** getMatchOutcome(ConditionContext, AnnotatedTypeMetadata).

**Question 3.** Can matches(...) be overridden?  
**Answer:** No. matches is final; Spring Boot uses it to orchestrate evaluation and record the outcome.

**Question 4.** What does ConditionOutcome contain?  
**Answer:** The match/no-match state and a message explaining the result.

**Question 5.** What is ConditionMessage.forCondition(...) used for?  
**Answer:** Creating a builder to construct consistently structured messages, with parts such as found, didNotFind, and because.

**Question 6.** What is AnnotatedTypeMetadata used for?  
**Answer:** Reading attributes of annotations attached to a class or method without creating a bean.

**Question 7.** Should a condition call a database to confirm the server is running?  
**Answer:** No. Conditions should be fast and deterministic; health checks or integration tests are better suited for real connections.

**Question 8.** How do you view the condition evaluation report?  
**Answer:** Use --debug, read ConditionEvaluationReport, or use Actuator /actuator/conditions when the endpoint is enabled and properly exposed.

**Question 9.** When an optional dependency may be absent, how should you check for the class?  
**Answer:** Use ClassUtils.isPresent(className, context.getClassLoader()) or built-in @ConditionalOnClass; avoid class literals in code that must load when the dependency is absent.

**Question 10.** Why do no-match messages need to be specific?  
**Answer:** They identify the exact property, provider, or class that failed the condition, helping operators fix configuration faster.

## Official References

- Spring Boot 3.5 API — SpringBootCondition: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html
- Spring Boot 3.5 API — ConditionOutcome: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html
- Spring Boot 3.5 API — ConditionMessage: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.html
- Spring Boot 3.5 API — ConditionMessage.Builder: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionMessage.Builder.html
- Spring Boot 3.5 API — ConditionEvaluationReport: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html
- Spring Boot 3.5 Reference — Creating Your Own Auto-configuration: https://docs.spring.io/spring-boot/3.5/reference/features/developing-auto-configuration.html
- Spring Boot 3.5 Actuator API — Conditions Evaluation Report endpoint: https://docs.spring.io/spring-boot/3.5/api/rest/actuator/conditions.html

**Remember:** SpringBootCondition lets a custom condition answer two questions at once: whether the configuration matches and why. Override getMatchOutcome, build ConditionOutcome with ConditionMessage, let Spring Boot record the result in ConditionEvaluationReport, and test both match and every no-match cause.
