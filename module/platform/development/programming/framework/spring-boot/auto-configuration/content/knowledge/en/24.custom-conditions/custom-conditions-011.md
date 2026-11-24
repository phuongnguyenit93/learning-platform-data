# Avoiding Network Calls, Logging Secrets, or Instantiating Beans Inside Conditions

> **Objective:** Write safe, fast, and predictable custom Spring Conditions. A condition only decides whether a configuration or bean definition is registered. It is not the place to check whether an external service is alive, validate secrets, log sensitive data, or retrieve a bean to query its state.

This lesson belongs to the **Custom Conditions** topic, using Spring Boot 3.3.x, Spring Framework 6.1.x, and Java 17+. It focuses on the `Condition` contract, what data can be read via `ConditionContext`, three boundaries to uphold (network, secrets, bean lifecycle), how to write a `SpringBootCondition` with safe diagnostic messages, and how to test using `ApplicationContextRunner`.

## 1. What Is a Condition Called to Do?

Spring uses `@Conditional` to decide whether a component is eligible for registration. For auto-configuration, conditions can be placed on:

- An `@AutoConfiguration` or `@Configuration` class to decide whether the whole configuration applies.
- A `@Bean` method to decide whether that method's bean definition is registered.
- A composed annotation containing `@Conditional` to reuse rules.

Spring evaluates conditions during configuration processing, right before the corresponding bean definition is due to be registered. At this moment, Spring is building the context's bean model. Singletons are not necessarily created yet, and dependency injection and bean post-processors are not finished either.

Therefore, custom conditions must follow restrictions similar to `BeanFactoryPostProcessor`: work only with metadata and available configuration info, and never interact with bean instances. A condition should be a fast, side-effect-free decision that does not depend on mutable state outside the context.

Distinguish three tasks:

| Decision to make | Appropriate place |
| --- | --- |
| Is the feature enabled in configuration? | `@ConditionalOnProperty` or a custom condition reading `Environment` |
| Is the library/client class on the classpath? | `@ConditionalOnClass` or checking `ClassLoader` |
| Is a remote API/database/secret manager reachable? | Health check, readiness, retry, or connection logic after the application starts |

A condition decides **whether to register configuration**. It does not continuously monitor the system and does not re-run whenever the network or an external service changes state.

## 2. Prefer Built-In Conditions Before Writing Your Own

Spring Boot already provides common conditions:

| Requirement | Appropriate annotation |
| --- | --- |
| Class/library present on classpath | `@ConditionalOnClass` |
| Class/library absent from classpath | `@ConditionalOnMissingClass` |
| Bean present by type/name | `@ConditionalOnBean` |
| No bean present so a default can be registered | `@ConditionalOnMissingBean` |
| Property has a specific value | `@ConditionalOnProperty` |
| Local resource exists | `@ConditionalOnResource` |
| Application is Servlet/Reactive web | `@ConditionalOnWebApplication` |
| Application is not web | `@ConditionalOnNotWebApplication` |

Simple property example:

~~~java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false)
public class AuditAutoConfiguration {
    // Default @Beans.
}
~~~

For booleans, explicitly state `havingValue` and `matchIfMissing` so readers understand exactly which value enables configuration and what happens when the property is missing. If you only need to check one property, there is no need to create a new `Condition` class.

Write a custom condition only when the rule genuinely cannot be expressed clearly with built-in annotations, such as combining multiple configuration signals or reading a specialized annotation attribute. A hand-written condition adds code to test, document, and maintain.

## 3. What Does ConditionContext Provide?

The core method of a Spring Condition is:

~~~java
boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata);
~~~

`ConditionContext` provides several sources of information during the bean definition registration stage:

| API | Can be used to |
| --- | --- |
| `context.getEnvironment()` | Read properties, profiles, and environment info |
| `context.getClassLoader()` | Check whether a class can be loaded |
| `context.getResourceLoader()` | Locate resources at appropriate locations |
| `context.getRegistry()` | Read/check registered bean definitions |
| `context.getBeanFactory()` | Access BeanFactory metadata if available |
| `metadata` | Read annotations and attributes of the class/method being evaluated |

`getBeanFactory()` can return `null` if a BeanFactory is unavailable in the calling context. Even when a BeanFactory is present, that does not make the condition a place to fetch beans. Use these sources to read configuration and definition info, not to create or access business objects.

### Appropriate Operations

- Reading a non-sensitive configuration flag from `Environment`.
- Checking optional classes with `ClassUtils.isPresent` or the class loader.
- Checking resources on the classpath or local filesystem.
- Reading annotation attributes from `AnnotatedTypeMetadata`.
- When truly needing to check bean definitions, inspecting registration metadata only and paying attention to processing order. For standard needs, use `@ConditionalOnBean` or `@ConditionalOnMissingBean`.

### Inappropriate Operations

- Calling `context.getBeanFactory().getBean(...)` to retrieve a bean instance.
- Calling `getBean`, `getBeansOfType`, or `ObjectProvider.getObject()` to initialize dependencies.
- Creating a client/service with `new` and calling methods to query state.
- Making HTTP calls, opening sockets, pinging databases, querying DNS, or calling secret managers.
- Writing files, mutating system properties, manually registering beans, or spawning threads.
- Logging the entire `Environment`, annotation metadata, or connection URLs.

## 4. Why Must You Not Access the Network Inside a Condition?

Suppose an auto-configuration only wants to register `AuditClient` when the audit server is running. An intuitive yet unsafe approach is sending an HTTP request or opening a socket right inside `matches(...)`.

This causes several problems:

1. **Network-dependent startup:** slow DNS, firewalls, proxies, or temporarily unreachable services can delay or break context creation.
2. **Hard-to-control timeouts:** every refresh/test may have to wait for a request. A small unit test unexpectedly becomes an environment-dependent integration test.
3. **Unstable results:** the exact same configuration can match now and fail to match seconds later simply due to network fluctuations.
4. **Wrong timing:** conditions are evaluated when Spring processes configuration, not each time a user invokes the service.
5. **Hard to diagnose:** DNS/HTTP errors get turned into condition failures, obscuring the root cause of startup issues.
6. **Potential side effects:** probe requests can generate audit events, write data, consume rate limits, or trigger authentication flows.

Example of what not to do:

~~~java
public boolean matches(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    // Do not call HTTP, sockets, DNS, or databases here.
    return remoteAuditServerResponds();
}
~~~

If you only need to know whether the feature is configured as enabled, read a property. If you need to know whether the client library is available, check the classpath. If you need to know whether the server is actually healthy, run health checks after the context is created, for instance via a `HealthIndicator`, readiness check, or client retry/circuit-breaker logic.

**Do not turn startup conditions into health checks.** Connectivity is dynamic state; a condition is a configuration-registration decision at an initialization stage.

## 5. Do Not Leak Secrets into Diagnostic Messages or Logs

Spring Boot can record condition results in `ConditionEvaluationReport`. With `SpringBootCondition`, the `ConditionOutcome` message helps explain why the condition matched or did not match. The report can be printed when debug mode is enabled or via test listeners.

Therefore, condition messages must be treated as data that can appear in logs.

Do not write:

~~~java
String token = context.getEnvironment()
        .getProperty("acme.audit.token");

return ConditionOutcome.noMatch(
        "Invalid audit token: " + token);
~~~

Also never log usernames/passwords, bearer tokens, API keys, private keys, cookies, authorization headers, URLs containing user-info, or entire property sources. Never include secrets in exception messages, condition outcomes, assertion messages, or telemetry.

### 5.1. If You Only Need to Know Whether a Secret Is Configured

Use `Environment.containsProperty` to check key presence without reading the secret value:

~~~java
boolean credentialConfigured = context.getEnvironment()
        .containsProperty("acme.audit.token");

return credentialConfigured
        ? ConditionOutcome.match("Audit credential is configured")
        : ConditionOutcome.noMatch("Audit credential is not configured");
~~~

The message only states whether the secret has been configured; it does not reveal its contents. Note that `containsProperty` only checks whether the property exists; it does not prove the value is non-empty or valid.

If you need to validate the secret's format or mandatory presence, use configuration binding and proper validation, or let the client handle authentication errors at the appropriate lifecycle stage. Never print raw values when validation fails.

### 5.2. Writing Safe Condition Messages

Good messages should:

- Name non-sensitive properties and boolean outcomes.
- Name present or missing classes/resources using technical names.
- State a concise match/no-match reason.
- Not interpolate arbitrary property values unless you know they are non-sensitive.
- Not dump objects, Environment, requests, exceptions from remote services, or secret sources.

Safe examples:

~~~text
acme.audit.enabled is true
Optional audit transport class is not present
Audit credential is configured
Audit auto-configuration is disabled
~~~

These messages make the condition report readable without leaking credentials.

## 6. Do Not Instantiate or Fetch Beans Inside Conditions

Beans should be created according to Spring's lifecycle. If a condition calls BeanFactory to obtain an object, the bean may be instantiated too early, before required post-processors and configuration steps complete.

Example to avoid:

~~~java
@Override
public ConditionOutcome getMatchOutcome(
        ConditionContext context,
        AnnotatedTypeMetadata metadata) {

    AuditClient client = context.getBeanFactory()
            .getBean(AuditClient.class);

    return client.isReady()
            ? ConditionOutcome.match("Audit client is ready")
            : ConditionOutcome.noMatch("Audit client is not ready");
}
~~~

Risks:

- The bean may be created before `@ConfigurationProperties` binding finishes.
- The bean may not have passed through `BeanPostProcessor` or necessary proxies yet.
- The bean's dependencies may not be registered or ready yet.
- Creating the bean may open connections, spawn threads, or call external systems.
- The condition inadvertently mutates the very state it is trying to evaluate.

Do not call `getBean`, `getBeansOfType`, or `ObjectProvider.getObject()` inside a condition. Also do not invoke the client's constructor directly to bypass BeanFactory; that bypasses Spring's dependency injection and lifecycle.

### 6.1. Use Bean Conditions Instead of Fetching Bean Instances

If a default should appear only when the application has not provided a bean:

~~~java
@Bean
@ConditionalOnMissingBean(AuditClient.class)
AuditClient auditClient() {
    return new AuditClient();
}
~~~

If a secondary bean should appear only when a provider is registered:

~~~java
@Bean
@ConditionalOnBean(AuditTransport.class)
AuditPublisher auditPublisher(AuditTransport transport) {
    return new AuditPublisher(transport);
}
~~~

Spring Boot evaluates bean conditions based on bean definitions processed up to that point. Therefore, place them on auto-configurations and declare appropriate ordering when depending on another provider. Boot documentation recommends using `@ConditionalOnBean` and `@ConditionalOnMissingBean` in auto-configuration because they are processed after user-declared bean definitions.

### 6.2. Be Careful with @ConditionalOnExpression

`@ConditionalOnExpression` can use SpEL to decide conditions. However, if the expression references a bean using `@someBean` syntax, that bean will be initialized very early during context refresh. It may not yet be post-processed, may lack bound configuration, and may be in an incomplete state.

Do not write:

~~~java
@ConditionalOnExpression("@auditClient.ready")
@Configuration
class AuditConfiguration {
}
~~~

If you only check a property, use `@ConditionalOnProperty`. If you need a composite rule, write a custom `Condition` that reads `Environment` and metadata without calling beans.

## 7. Safe Custom Condition Pattern with SpringBootCondition

Spring Framework provides the `Condition` interface with a `matches` method returning boolean. Spring Boot adds the `SpringBootCondition` base class so conditions return a `ConditionOutcome` with an explanatory message.

The pattern below checks a non-sensitive property flag. The condition does not read credentials, make network calls, or fetch beans.

**File:** `src/main/java/com/acme/audit/autoconfigure/AuditFeatureEnabledCondition.java`

~~~java
package com.acme.audit.autoconfigure;

import org.springframework.boot.autoconfigure.condition.ConditionOutcome;
import org.springframework.boot.autoconfigure.condition.SpringBootCondition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

public final class AuditFeatureEnabledCondition extends SpringBootCondition {

    private static final String PROPERTY = "acme.audit.enabled";

    @Override
    public ConditionOutcome getMatchOutcome(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        boolean enabled = context.getEnvironment()
                .getProperty(PROPERTY, Boolean.class, Boolean.FALSE);

        if (enabled) {
            return ConditionOutcome.match(PROPERTY + " is true");
        }

        return ConditionOutcome.noMatch(PROPERTY + " is not true");
    }
}
~~~

Explanation:

- `SpringBootCondition` implements Spring's `Condition` contract.
- `getMatchOutcome` receives `ConditionContext` and class/method metadata.
- `getEnvironment()` only reads properties in the current Environment.
- The default value is `false`, so when the property is missing, the condition does not match.
- `ConditionOutcome.match(...)` and `noMatch(...)` return results along with diagnostic messages.
- Messages contain only the boolean property name and status; no secret values are exposed.

This is an example to understand custom conditions. In a real application, since the rule is just a single boolean property, `@ConditionalOnProperty` is shorter and more appropriate. Reserve custom conditions for cases with genuinely specialized logic.

## 8. Using a Custom Condition on Auto-Configuration

Sample client:

**File:** `src/main/java/com/acme/audit/AuditClient.java`

~~~java
package com.acme.audit;

public final class AuditClient {

    public AuditClient() {
        // Initialize local object; do not open network connections in the constructor.
    }

    public String name() {
        return "audit-client";
    }
}
~~~

Auto-configuration:

**File:** `src/main/java/com/acme/audit/autoconfigure/AuditAutoConfiguration.java`

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Conditional;
import org.springframework.context.annotation.Lazy;

@AutoConfiguration
@Conditional(AuditFeatureEnabledCondition.class)
public class AuditAutoConfiguration {

    @Bean
    @Lazy
    @ConditionalOnMissingBean(AuditClient.class)
    public AuditClient auditClient() {
        return new AuditClient();
    }
}
~~~

There are three separate decision layers:

1. `@Conditional(AuditFeatureEnabledCondition.class)` decides whether the entire auto-configuration is applied.
2. `@ConditionalOnMissingBean` lets the application provide its own `AuditClient` and makes the default bean back off.
3. `@Lazy` defers instance creation until another bean requests it or the application retrieves the bean. This annotation clearly demonstrates that a condition can register a bean definition without immediately creating the object.

In a published JAR, auto-configuration must still be registered via Spring Boot's imports mechanism:

**`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`**

~~~text
com.acme.audit.autoconfigure.AuditAutoConfiguration
~~~

The imports resource lets Boot discover the class. It does not change any safety principles for custom conditions.

## 9. Testing Conditions Without a Real Network

`ApplicationContextRunner` lets you test conditions in a small context, with each test setting its own properties. There is no need to open HTTP connections or use a real database to verify bean registration.

**File:** `src/test/java/com/acme/audit/autoconfigure/AuditAutoConfigurationTests.java`

~~~java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AuditAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(AuditAutoConfiguration.class));

    @Test
    void enabledPropertyRegistersLazyClientDefinition() {
        runner.withPropertyValues("acme.audit.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasBean("auditClient");

                    // Bean definition exists, but @Lazy has not created the singleton yet.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("auditClient")).isFalse();

                    AuditClient client = context.getBean(AuditClient.class);
                    assertThat(client.name()).isEqualTo("audit-client");

                    // Bean is created only after the test requests it.
                    assertThat(context.getBeanFactory()
                            .containsSingleton("auditClient")).isTrue();
                });
    }

    @Test
    void falsePropertyDoesNotRegisterClient() {
        runner.withPropertyValues("acme.audit.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(AuditClient.class);
                });
    }

    @Test
    void missingPropertyDoesNotRegisterClient() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(AuditClient.class);
        });
    }
}
~~~

The first test proves the condition permits bean-definition registration when the property is true, while instance creation still follows lazy lifecycle. The remaining two tests prove that when the property is false or missing, the configuration does not register the client.

Test dependencies with Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure:3.3.13'
    testImplementation 'org.springframework.boot:spring-boot-starter-test:3.3.13'
}
~~~

Run:

~~~bash
./gradlew test --tests com.acme.audit.autoconfigure.AuditAutoConfigurationTests
~~~

Or Maven:

~~~bash
mvn -Dtest=AuditAutoConfigurationTests test
~~~

**Expected result:** 3 PASS tests. These test conditions and bean registration in a local context; there are no network requests or database queries. The tests do not simulate audit server health checks because health checks belong to a different test layer.

## 10. Checking the Condition Report Without Leaking Secrets

Spring Boot stores condition evaluation results in `ConditionEvaluationReport`. The report groups outcomes by class or method and can be used to explain why an auto-configuration was applied or skipped.

You can enable the report when running the application:

~~~bash
java -jar app.jar --debug
~~~

Or use `ConditionEvaluationReportLoggingListener` in tests to print the report at an appropriate log level. When using these tools:

- Return only static, safe messages from `ConditionOutcome`.
- Never concatenate token/password/API key values into messages.
- Never log the entire Environment or property sources.
- Never leave debug enabled indefinitely in production if the report might expose internal configuration details.
- When diagnostics are needed, record the property name and whether it is configured.

Good message example:

~~~java
return ConditionOutcome.noMatch(
        "Audit integration is disabled by configuration");
~~~

Unsafe message example:

~~~java
return ConditionOutcome.noMatch(
        "Audit token rejected: " + token);
~~~

If authentication errors need investigation, log a standardized error code or non-sensitive correlation ID. Never log credentials for debugging convenience.

## 11. If You Must Check Bean Definitions, Avoid Instantiating Beans

Occasionally a custom condition needs to know whether a bean definition has already been registered. You can read metadata from `BeanDefinitionRegistry` via `context.getRegistry()`, while paying attention to timing and registration order.

Example checking the presence of a bean definition by name:

~~~java
boolean definitionExists =
        context.getRegistry().containsBeanDefinition("auditTransport");
~~~

The check above only asks the registry whether a definition with that name exists. It does not retrieve the object instance. However, if the goal is conditioning on a bean by type or allowing user beans to override, built-in annotations are usually clearer and safer:

~~~java
@Bean
@ConditionalOnBean(AuditTransport.class)
AuditPublisher auditPublisher(AuditTransport transport) {
    return new AuditPublisher(transport);
}
~~~

Do not manually iterate over all singletons or invoke factory methods to infer whether a bean is healthy. A bean definition can exist while the bean has not yet been created; that is normal for lazy beans. Connectivity or bean readiness must be evaluated at the proper lifecycle stage.

## 12. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Sending HTTP requests in `matches` | Slow startup, network dependency, and unstable results | Read only configuration/classpath; use health/readiness checks after startup |
| Pinging a database to decide bean registration | Context fails to start if the DB is temporarily unreachable | Register clients by configuration; check connectivity in lifecycle/health indicators |
| Logging raw tokens or passwords in `ConditionOutcome` | Secrets can appear in debug reports and logs | Record only property names and boolean/presence states |
| Calling `getBean` from BeanFactory | Instantiates beans prematurely, bypassing part of the expected lifecycle | Use metadata or built-in bean conditions |
| Using `@ConditionalOnExpression` referencing a bean | The bean is initialized early during refresh | Use property conditions or a custom Condition reading Environment |
| Creating a client with `new` inside a condition | Side effects and object outside Spring's lifecycle | Let `@Bean` methods create beans under the container's lifecycle |
| Checking a remote endpoint once at startup | Condition decision quickly goes stale when network state changes | Monitor health/readiness after the application starts |
| Condition holds mutable state or depends on time | Hard to reproduce and test results | Write stateless, deterministic, fast conditions |
| Using a custom condition for a single boolean property | Unnecessary code and maintenance overhead | Prefer `@ConditionalOnProperty` |
| Placing bean conditions in the wrong order | Condition does not see needed definitions at evaluation time | Use auto-configuration ordering and test ordering |

### 12.1. Custom Condition Review Checklist

- [ ] Condition only reads Environment, metadata, classpath, local resources, or bean definition metadata.
- [ ] No HTTP, sockets, DNS, database, secret manager, or remote I/O.
- [ ] Does not call `getBean`, `getBeansOfType`, or `ObjectProvider.getObject()`.
- [ ] Does not create clients/services or threads inside `matches` / `getMatchOutcome`.
- [ ] Does not log or return secret values in `ConditionOutcome`.
- [ ] Diagnostic messages are short, stable, and non-sensitive.
- [ ] Logic is stateless, deterministic, and fast to execute.
- [ ] Uses built-in conditions whenever possible.
- [ ] Includes tests for match, no-match, and boundary property/classpath cases.
- [ ] Health/readiness is handled after startup if external services must be observed.

## 13. Safe Condition Design Workflow

When a new requirement arrives, follow these steps in order:

1. Determine whether the decision concerns bean registration, property configuration, classpath, or operational runtime state.
2. Look for a suitable built-in annotation first.
3. If custom logic is needed, list the exact local signals the condition is permitted to read.
4. Never use network calls or secret values as diagnostic data.
5. Never fetch bean instances; if bean presence is needed, use built-in bean conditions.
6. Return match/no-match with non-sensitive messages.
7. Test match, no-match, missing property, and user bean override cases.
8. If connectivity must be checked, design separate health/readiness tests after context startup.

A good custom condition can be explained in one sentence: "Based on metadata and current configuration, this condition allows or denies bean registration." If you have to initialize sub-applications, call remote services, or fetch credentials to answer, that logic has stepped far beyond a condition's responsibility.

## 14. Knowledge Self-Check

1. When does Spring evaluate a `Condition`?  
   **Answer:** During configuration processing, right before the corresponding bean definition is registered.

2. Why must `getBean` not be called in a custom condition?  
   **Answer:** Conditions must follow `BeanFactoryPostProcessor` restrictions and not interact with bean instances; fetching a bean can instantiate it prematurely.

3. Why should you not ping an API/database from a condition?  
   **Answer:** It makes startup network-dependent, causes timeouts, and yields unstable results; conditions are also not re-evaluated continuously when connectivity changes.

4. Can a `ConditionOutcome` message contain a token?  
   **Answer:** No. Outcomes can appear in condition reports and logs; record only sanitized reasons, never secrets.

5. If you only need to know whether a secret property is configured, which API can you use?  
   **Answer:** `Environment.containsProperty` to check presence without fetching the raw value. It does not replace validation of valid values.

6. When only checking a boolean property, do you need a custom condition?  
   **Answer:** No. `@ConditionalOnProperty` is usually shorter and easier to maintain.

7. What problem can `@ConditionalOnExpression` referencing a bean cause?  
   **Answer:** The bean may be initialized very early, before post-processing and configuration-properties binding, leaving it in an incomplete state.

8. If you need to verify that a server is healthy after startup, what should you use?  
   **Answer:** A health indicator, readiness check, or runtime monitoring/retry logic—not a bean-registration condition.

## Official Documentation

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html): condition annotations, bean conditions, property conditions, and warnings about SpEL referencing beans.
- [Spring Boot 3.3 API — SpringBootCondition](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/SpringBootCondition.html): Boot's base condition class and `getMatchOutcome` method.
- [Spring Boot 3.3 API — ConditionOutcome](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionOutcome.html): match/no-match result along with diagnostic message.
- [Spring Boot 3.3 API — ConditionEvaluationReport](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionEvaluationReport.html): where condition evaluation details are stored for reporting/logging.
- [Spring Framework 6.1 — Condition Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html): the `Condition` contract, evaluation timing, and restriction against interacting with bean instances.
- [Spring Framework 6.1 — ConditionContext Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/ConditionContext.html): accessible Environment, ClassLoader, ResourceLoader, BeanDefinitionRegistry, and BeanFactory.

**Remember:** A custom condition should make decisions solely from local information available during the bean-definition registration stage. Do not access the network, do not include secrets in outcomes/logs, and do not instantiate or retrieve bean instances. Use built-in conditions when sufficient, custom conditions when genuinely needed, and check health/connectivity after startup.
