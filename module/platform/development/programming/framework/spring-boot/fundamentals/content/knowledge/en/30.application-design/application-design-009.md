# Designing Shared Libraries with Clear Configuration and Customizability

A shared library in the Spring Boot ecosystem must satisfy two requirements: **provide sensible default behavior so applications can adopt it quickly**, while **allowing each application to customize behavior without modifying the library's source code**.

If a library reads environment variables directly, opens connections inside constructors, accesses ApplicationContext everywhere, or forces applications to use one fixed implementation, it becomes hard to test and hard to integrate. Conversely, if the library exposes too many internal details, users must understand the implementation just to use it.

Good design draws clear boundaries between:

- **Public API and core rules:** what functionality the library provides and which invariants must always hold.
- **Configuration:** choices that can vary by application or environment.
- **Spring initialization mechanics:** registering beans, binding properties, and selecting default implementations.
- **Extension points:** interfaces, strategies, callbacks, or beans that applications can override.
- **Infrastructure:** HTTP, databases, filesystems, schedulers, or framework-specific adapters.

This lesson uses a retry policy library as an example. The library supplies attempt counts and delay rules, provides default values, supports configuration via `application.yml`, and lets applications swap in custom policies. The same principles apply to client libraries, auditing, messaging, file processing, or internal modules.

## 1. What Must a Shared Library Protect?

A library used by multiple applications usually outlives any single feature. It can be upgraded independently, pulled into diverse dependency graphs, and run across different environments.

Before writing bean configuration, determine:

1. What is the library's public functionality?
2. Which business rules or algorithms belong to the library?
3. Which parameters do users need to configure?
4. What default behavior is safe and easy to understand?
5. Which components can users replace?
6. Does the library depend on Spring Boot, or does it expose a plain Java API as well?
7. When configuration is invalid, when are errors reported and with what messages?
8. How can the library be tested without starting a full application?

A good library has a clear contract. Users know which methods are stable, what each property means, which defaults apply, and how to customize behavior.

### 1.1. Example: Retry Policy Library

Suppose multiple internal applications call external services and need consistent retry rules. Applications may differ in maximum attempts, initial delay, backoff multiplier, maximum delay, and per-operation policies.

Instead of every application writing its own retry loop, the library provides an API:

~~~java
package com.example.retry;

import java.time.Duration;

public interface RetryPolicy {

    int maxAttempts();

    Duration delayBeforeAttempt(int failedAttempt);
}
~~~

This contract expresses two things: the maximum number of attempts and the wait duration before the next attempt after a failure.

The library does not need to know whether the application is calling HTTP, a database, or a message broker. It provides the policy only. Whatever component executes retries can use that policy at the appropriate layer.

### 1.2. Why Not Put Everything in One Class?

A single class that reads YAML, registers beans, runs retries, calls HTTP, and chooses fallbacks carries too many responsibilities.

When users want to change the policy, they may be forced to replace the transport too. When upgrading Spring Boot versions, business logic is affected. In unit tests, tests must set up unrelated dependencies.

Separating responsibilities gives each part an appropriate contract and lifecycle.

## 2. Distinguishing Library, Auto-Configuration, and Starter

A Spring Boot library can be packaged into multiple modules:

| Module | Responsibility | Requires Spring Boot? |
| --- | --- | --- |
| retry-api | Public interfaces and data types | No |
| retry-core | Default implementations, plain Java algorithms | No |
| retry-spring-boot-autoconfigure | Bind properties and register default beans | Yes |
| retry-spring-boot-starter | Convenience dependency for one-line adoption | Yes |

Not every project needs four modules. For small libraries, API and core can live in one module. When multiple applications use the Java API without Spring Boot, separating core from the integration layer avoids pulling in Spring dependencies.

### 2.1. Library Core

Core contains public interfaces, value objects, default algorithms or rules, contract-level exceptions if needed, and essential plain Java dependencies.

Core should not require `ApplicationContext`, `Environment`, `@Autowired`, or `@ConfigurationProperties` to run its primary logic.

### 2.2. Auto-Configuration Module

This module knows about Spring Boot and handles:

- Registering configuration properties.
- Creating default beans when the feature is enabled.
- Backing off when the application provides its own implementation.
- Checking classpath/property conditions.
- Wiring Spring-specific components together.

Auto-configuration is a composition mechanism. It decides which objects are created and wired together; it should not contain all business algorithms.

### 2.3. Starter Module

A starter primarily aggregates the appropriate dependencies so users add a single dependency to their application. It does not need to hold retry algorithms or business APIs.

### 2.4. When Should Modules Be Split?

Split when a real need exists: multiple applications need core without Spring, auto-configuration has different dependencies than core, a starter simplifies dependency graph management, or versioning/ownership differs.

Do not create extra modules just to add more directories. Module boundaries should reflect real dependency or distribution boundaries.

## 3. Placing Boundaries Between Core Rules and Spring

A common organization:

~~~text
Application
    |
    v
Application service / use case
    |
    v
Public library API
    |
    v
Core implementation
    |
    v
Ports / interfaces
    |
    +------ Application-supplied adapter
    |
    +------ Library default adapter
~~~

Spring Boot at the composition layer:

~~~text
Spring Boot ApplicationContext
    |
    +--> Bind configuration properties
    |
    +--> Register default beans
    |
    +--> Select user-provided overrides
    |
    +--> Inject dependencies
             |
             v
       Application services
             |
             v
          Core API
~~~

### 3.1. Core Should Not Look Up Beans Itself

Do not let retry logic call `ApplicationContext` to look up `RetryPolicy` via `getBean`. That is a service locator: the class hides dependencies from its constructor and forces tests to start a context or mock global state.

Pass dependencies explicitly:

~~~java
public final class RetryExecutor {

    private final RetryPolicy policy;

    public RetryExecutor(RetryPolicy policy) {
        this.policy = Objects.requireNonNull(policy);
    }
}
~~~

Callers decide whether to obtain the policy from Spring or instantiate it directly.

### 3.2. Do Not Let Core Depend on Environment

Avoid having core accept Spring `Environment` and read `company.retry.max-attempts` itself. Such a class both parses configuration and decides algorithms. It depends on Spring and is hard to reuse outside Spring.

Instead, Spring binds properties and passes the converted values into core constructors.

### 3.3. Spring Annotations in the Integration Layer Are Reasonable

Not every Spring annotation must be banished from every class. Application services can be registered with `@Service`, adapters can use `@Component`, and auto-configurations require `@Configuration`.

What must be avoided is **requiring Spring to boot just to run core rules**. Spring annotations in the integration layer are wiring mechanisms, not business rules.

## 4. Design the Public API Before Writing Auto-Configuration

The API is the contract other applications compile against. Keep it small, stable, and meaningful.

Interface:

~~~java
package com.example.retry;

import java.time.Duration;

public interface RetryPolicy {

    int maxAttempts();

    Duration delayBeforeAttempt(int failedAttempt);
}
~~~

A default implementation:

~~~java
package com.example.retry;

import java.time.Duration;
import java.util.Objects;

public final class DefaultRetryPolicy implements RetryPolicy {

    private final int maxAttempts;
    private final Duration initialDelay;
    private final int multiplier;
    private final Duration maxDelay;

    public DefaultRetryPolicy(
            int maxAttempts,
            Duration initialDelay,
            int multiplier,
            Duration maxDelay) {

        if (maxAttempts < 1) {
            throw new IllegalArgumentException(
                    "maxAttempts must be at least 1"
            );
        }

        this.initialDelay = Objects.requireNonNull(initialDelay);
        this.maxDelay = Objects.requireNonNull(maxDelay);

        if (initialDelay.isNegative() || initialDelay.isZero()) {
            throw new IllegalArgumentException(
                    "initialDelay must be positive"
            );
        }

        if (multiplier < 1) {
            throw new IllegalArgumentException(
                    "multiplier must be at least 1"
            );
        }

        if (maxDelay.compareTo(initialDelay) < 0) {
            throw new IllegalArgumentException(
                    "maxDelay must not be smaller than initialDelay"
            );
        }

        this.maxAttempts = maxAttempts;
        this.multiplier = multiplier;
    }

    @Override
    public int maxAttempts() {
        return maxAttempts;
    }

    @Override
    public Duration delayBeforeAttempt(int failedAttempt) {
        if (failedAttempt < 1) {
            throw new IllegalArgumentException(
                    "failedAttempt must be at least 1"
            );
        }

        Duration delay = initialDelay;

        for (int attempt = 1; attempt < failedAttempt; attempt++) {
            if (delay.compareTo(maxDelay) >= 0) {
                return maxDelay;
            }

            try {
                delay = delay.multipliedBy(multiplier);
            } catch (ArithmeticException overflow) {
                return maxDelay;
            }
        }

        return delay.compareTo(maxDelay) > 0
                ? maxDelay
                : delay;
    }
}
~~~

This implementation is plain Java. It reads no properties, knows nothing of Spring, and never sleeps threads.

### 4.1. Define Parameter Semantics Clearly

In the policy above:

- `maxAttempts = 3` means a maximum of three total executions, if the executor defines attempts that way.
- `failedAttempt = 1` returns the initial delay before the next retry.
- `multiplier = 2` produces the sequence 200 ms, 400 ms, 800 ms...
- `maxDelay` caps the delay duration.

Names and semantics must be documented. If one implementation treats `maxAttempts` as additional retries after the first attempt while another treats it as total executions, users will encounter subtle bugs.

### 4.2. Do Not Put Thread.sleep Inside the Policy

A policy should **return a decision**, not execute the wait itself. Waiting might use blocking sleep, a scheduler, reactive delays, or message broker mechanisms.

Separating decision from execution lets the same policy work across multiple runtimes.

### 4.3. Avoid Exposing Internal Details in Public APIs

Do not expose `ApplicationContext`, `BeanFactory`, internal implementation classes, or Spring-specific builders if users do not need them.

The smaller the API, the easier it is to swap implementations and upgrade versions.

## 5. Configuration Needs Clear Namespaces and Semantics

A library should not use overly generic property names:

~~~properties
enabled=true
timeout=5s
max-attempts=3
~~~

These names can collide with application configuration or other libraries.

Use a dedicated prefix:

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 3
    initial-delay: 200ms
    multiplier: 2
    max-delay: 5s
~~~

The prefix `company.retry` is only an example; real libraries should use the organization or product namespace.

### 5.1. Property Names Should Reflect Intent

| Property | Meaning |
| --- | --- |
| company.retry.enabled | Enable/disable the auto-configured retry policy |
| company.retry.max-attempts | Maximum total attempts per contract |
| company.retry.initial-delay | Wait duration after the first failure |
| company.retry.multiplier | Backoff multiplier for wait duration |
| company.retry.max-delay | Upper bound on wait duration |

Property names should remain stable across versions. If renaming is necessary, consider aliases/deprecation paths rather than silently deleting old properties.

### 5.2. Distinguish Defaults, Required, and Optional Settings

Configuration should specify defaults when omitted, required properties, properties needed only when a feature is enabled, valid values and bounds, time units, and what happens when a property is invalid.

Do not hide important implicit defaults that users cannot discover via documentation or IDE metadata.

### 5.3. Defaults Should Fit General Usage

Library defaults should be safe and predictable. For retries, balance attempt counts and delays so they do not overwhelm an already failing service.

Not every operation is safe to retry. Retrying a non-idempotent write can create duplicate transactions. A policy library should not claim that every exception is safe to retry.

## 6. Bind Properties into a Dedicated Configuration Type

In the auto-configuration module, create a properties class:

~~~java
package com.example.retry.autoconfigure;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@ConfigurationProperties(prefix = "company.retry")
@Validated
public class RetryProperties {

    private boolean enabled = true;

    @Min(1)
    private int maxAttempts = 3;

    @NotNull
    private Duration initialDelay = Duration.ofMillis(200);

    @Min(1)
    private int multiplier = 2;

    @NotNull
    private Duration maxDelay = Duration.ofSeconds(5);

    public boolean isEnabled() {
        return enabled;
    }

    public void setEnabled(boolean enabled) {
        this.enabled = enabled;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public void setMaxAttempts(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public Duration getInitialDelay() {
        return initialDelay;
    }

    public void setInitialDelay(Duration initialDelay) {
        this.initialDelay = initialDelay;
    }

    public int getMultiplier() {
        return multiplier;
    }

    public void setMultiplier(int multiplier) {
        this.multiplier = multiplier;
    }

    public Duration getMaxDelay() {
        return maxDelay;
    }

    public void setMaxDelay(Duration maxDelay) {
        this.maxDelay = maxDelay;
    }
}
~~~

These are JavaBean properties for the Spring Boot Binder to populate. `@ConfigurationProperties` separates reading configuration from the core implementation.

### 6.1. Why Not Inject @Value Everywhere?

If every class declares its own `@Value` fields, configuration gets scattered and the library's full contract becomes hard to see. A centralized properties object shows all settings in one place, enables grouped inspection and validation, simplifies documentation, and keeps core independent of Spring.

### 6.2. Validation Must Reflect Real Rules

`@Min(1)` checks the minimum attempt count; `@NotNull` ensures durations are non-null. `DefaultRetryPolicy`'s constructor still enforces critical invariants such as positive durations and `maxDelay` not smaller than `initialDelay`.

Configuration-layer validation reports errors early; core constructors protect invariants even when instantiated outside Spring.

### 6.3. Validation Dependencies

Jakarta Validation constraints require a validation provider and appropriate integration. In Spring Boot, applications usually add the validation starter when enabling Bean Validation. The auto-configuration module should declare dependencies and optionality aligned with its packaging strategy.

If the library does not want to mandate a validation provider, validate values in factory methods/core constructors and enable Bean Validation only when the dependency is present. Document clearly what happens when no provider is present.

### 6.4. Do Not Validate Unnecessary Properties When a Feature Is Disabled

If a feature has a property required only when enabled, design validation to reflect that. Do not validate an endpoint as mandatory in every environment if the feature is allowed to be disabled.

You can use nested properties, conditional configuration, or a validator that checks the `enabled` flag. Validation must reflect actual usage conditions.

## 7. Auto-Configuration Registers Default Beans

In Spring Boot 3, auto-configuration can use `@AutoConfiguration`:

~~~java
package com.example.retry.autoconfigure;

import com.example.retry.DefaultRetryPolicy;
import com.example.retry.RetryPolicy;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(RetryPolicy.class)
@ConditionalOnProperty(
        prefix = "company.retry",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
@EnableConfigurationProperties(RetryProperties.class)
public class RetryAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(RetryPolicy.class)
    RetryPolicy retryPolicy(RetryProperties properties) {
        return new DefaultRetryPolicy(
                properties.getMaxAttempts(),
                properties.getInitialDelay(),
                properties.getMultiplier(),
                properties.getMaxDelay()
        );
    }
}
~~~

Auto-configuration does three things:

1. Applies only when the API class is on the classpath.
2. Enables the feature according to `company.retry.enabled`, defaulting to enabled if omitted.
3. Creates a default `RetryPolicy` when the application has not already provided a bean for that contract.

### 7.1. @ConditionalOnClass

This condition skips registering configuration when required classes are absent from the classpath. It is useful for libraries with optional integrations.

### 7.2. @ConditionalOnProperty

The `enabled` property gives users control to turn off the feature:

~~~yaml
company:
  retry:
    enabled: false
~~~

With this setting, the auto-configuration above does not register the default `RetryPolicy`. The library may still reside in the artifact, yet automatic beans are not created.

### 7.3. @ConditionalOnMissingBean

This is crucial for customizability. If the application supplies its own `RetryPolicy` bean, auto-configuration backs off and skips creating the default bean.

As a result, applications can change behavior without forking the library or editing its source.

### 7.4. Auto-Configuration Must Be Discoverable

In Spring Boot 3, declare the file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

With one line of content:

~~~text
com.example.retry.autoconfigure.RetryAutoConfiguration
~~~

This file is packaged inside the auto-configuration JAR so Boot discovers the configuration.

Older Spring Boot lines used different registration mechanisms, such as `spring.factories` in earlier versions. Choose the mechanism compatible with the Boot versions your library supports.

## 8. Customizing via Properties vs. Replacing Beans

A library should support at least two customization levels:

1. **Data configuration:** users adjust parameters while keeping the default implementation.
2. **Strategy replacement:** users supply a different implementation when default behavior is insufficient.

### 8.1. Customizing via YAML

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 5
    initial-delay: 300ms
    multiplier: 2
    max-delay: 8s
~~~

The application does not need to declare a custom bean. Spring Binder populates `RetryProperties`, and auto-configuration passes the values into `DefaultRetryPolicy`.

### 8.2. Disabling the Feature

~~~yaml
company:
  retry:
    enabled: false
~~~

When disabled, the default bean is not created. Applications must understand that components strictly requiring `RetryPolicy` will fail injection if they remain registered. Therefore, consumers must configure those components conditionally or pick another contract for optional-feature scenarios.

### 8.3. Providing a Custom Bean

~~~java
@Configuration(proxyBeanMethods = false)
public class ApplicationRetryConfiguration {

    @Bean
    RetryPolicy applicationRetryPolicy() {
        return new RetryPolicy() {

            @Override
            public int maxAttempts() {
                return 2;
            }

            @Override
            public Duration delayBeforeAttempt(int failedAttempt) {
                return Duration.ofMillis(100);
            }
        };
    }
}
~~~

When this bean is present, `@ConditionalOnMissingBean` prevents registering the default bean.

### 8.4. Do Not Force Users to Exclude Entire Auto-Configurations to Swap One Bean

If a user only wants to replace the policy, they should not have to exclude `RetryAutoConfiguration`, manually bind properties, re-create every related bean, and duplicate internal wiring.

A good extension point lets users replace exactly the behavior they need while the rest of the library continues working.

## 9. Extension Points: Interfaces, Strategies, and Callbacks

Not every variation should become a property. Properties fit data-driven choices; differing behaviors should use strongly typed extension points.

### 9.1. Strategy Interfaces

`RetryPolicy` is a strategy. An application can install policies per tenant or operation type:

~~~java
public final class TenantRetryPolicy implements RetryPolicy {

    private final int maxAttempts;

    public TenantRetryPolicy(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    @Override
    public int maxAttempts() {
        return maxAttempts;
    }

    @Override
    public Duration delayBeforeAttempt(int failedAttempt) {
        return Duration.ofMillis(100L * failedAttempt);
    }
}
~~~

The application decides which policies to register and how to select the policy per use case.

### 9.2. Callbacks/Listeners

If a library should let applications observe retry attempts, provide an interface:

~~~java
public interface RetryListener {

    default void onRetry(
            String operation,
            int failedAttempt,
            Throwable failure,
            Duration nextDelay) {
    }
}
~~~

The executor can accept a collection of listeners or a callback. Users register listeners to record metrics, audits, or tracing.

Do not force users to subclass internal implementations just to receive callbacks. Small, stable interfaces are better extension points.

### 9.3. ObjectProvider When Multiple Optional Beans Are Supported

In auto-configuration, Spring's `ObjectProvider` can retrieve an optional bean or a list of extensions:

~~~java
@Bean
RetryObserver retryObserver(
        ObjectProvider<RetryListener> listeners) {

    return new CompositeRetryObserver(
            listeners.orderedStream().toList()
    );
}
~~~

`ObjectProvider` is useful when dependencies are optional or multiple candidates exist. Do not use it to hide required dependencies; direct constructor injection is clearer.

### 9.4. Specify Extension Ordering

If multiple listeners/customizers are invoked, define:

- Are `Ordered`/`@Order` supported?
- Does ordering affect outcomes?
- If two customizers mutate the same attribute, which wins?
- Should conflicting configurations fail?

Do not let behavior depend on accidental scan order when ordering matters.

## 10. Properties vs. Custom Beans: Choosing the Right Tool

| Need | Appropriate Mechanism |
| --- | --- |
| Change retry attempt count | Configuration property |
| Change wait duration | Configuration property |
| Enable/disable feature | Conditional property |
| Replace algorithm completely | Strategy bean |
| Add metric/audit callbacks | Listener bean |
| Supply custom transport | Adapter interface/bean |
| Replace entire composition | User configuration / auto-configuration exclusion |
| Vary value per request/tenant | Explicit context or argument in the API |

A property should not hold an arbitrary class name for the library to reflectively instantiate when an interface bean expresses the extension point better.

### 10.1. Avoid Over-Configuration

If a library exposes hundreds of properties, users struggle to tell which options matter. Keep configuration focused on meaningful decisions with good defaults.

### 10.2. Do Not Use Properties for Per-Request Business Decisions

Properties are application/environment-level configuration. If retry policy depends on transaction criticality or tenant, pass that information into typed APIs/strategies instead of reading global properties inside every method.

## 11. Let the Application Control Profiles and Environments

A library should not activate `dev`, `test`, or `prod` profiles itself. Profiles are deployment decisions owned by the application.

An application can set:

~~~yaml
# application-dev.yml
company:
  retry:
    max-attempts: 2
    initial-delay: 100ms
~~~

~~~yaml
# application-prod.yml
company:
  retry:
    max-attempts: 4
    initial-delay: 300ms
    max-delay: 5s
~~~

The library simply binds effective properties. It does not need to know which profile is active when logic does not depend on profile names.

### 11.1. Do Not Inspect Profiles Inside Core

Avoid algorithms calling `Environment.acceptsProfiles` or selecting behavior based on profile names.

If behavior differs across environments, let configuration select appropriate values or implementations at the composition layer.

### 11.2. Profiles Do Not Replace Validation

A profile file may be missing or overridden by environment variables. Regardless of source, bound properties must still satisfy the contract. Validate the final bound data, not just a single YAML file.

### 11.3. Avoid Hardcoding Deployment Environments

A library should not assume applications always run in Docker, Kubernetes, a local IDE, or a specific cloud provider. Expose neutral APIs/configuration and let applications provide infrastructure-specific adapters.

## 12. Avoid Initialization Side Effects in Constructors or Auto-Configuration

A common design mistake is connecting to an external service as soon as Spring creates a bean:

~~~java
public RemoteCatalogClient(CatalogProperties properties) {
    this.connection = connect(properties.getEndpoint());
}
~~~

If the network is not ready, startup fails even if the application has not called catalog features yet. It also forces context tests to stand up external services.

### 12.1. Constructors Should Set Up Objects

Constructors are suitable for validating arguments, assigning fields, creating lightweight internal objects, and establishing invariants without I/O.

Do not use constructors to issue HTTP requests, run large migrations, load full datasets, or wait for external services unless explicitly required at startup.

### 12.2. Connect on Demand or Through Intentional Lifecycles

Depending on the use case, create a lightweight HTTP client that connects on request, lazily initialize resources, use lifecycle callbacks when a resource must be ready before serving traffic, or use readiness/health checks to report dependency availability.

No single strategy fits every library. What matters is documenting clearly whether startup depends on external services.

### 12.3. Do Not Retry Infinitely During Startup

A bean factory method waiting forever on the network can prevent an application from ever becoming ready. If startup truly must verify a dependency, enforce timeouts, retry budgets, and specific error messages.

## 13. Keep Dependency Direction Stable

A module dependency graph can look like:

~~~text
retry-spring-boot-starter
          |
          v
retry-spring-boot-autoconfigure
          |
          v
retry-core
          |
          v
retry-api
~~~

Core does not depend back on auto-configuration.

### 13.1. Why Does Dependency Direction Matter?

If `retry-core` imports `org.springframework.context.ApplicationContext`, every application using core must pull in the Spring context. Core also becomes difficult to run in command-line tools, plain Java batch jobs, or other frameworks.

When auto-configuration depends on core, Spring Boot apps get full integration, while plain Java apps can still use API/core.

### 13.2. Avoid Circular Module Dependencies

Never have `retry-core` depend on `retry-spring` while `retry-spring` depends on `retry-core`. If two modules share a contract, place the contract in the lower module.

### 13.3. The API Module Does Not Always Have to Be Separate

For small libraries, `retry-core` can contain both interfaces and default implementations. Extract `retry-api` only when consumers need the contract without pulling in implementations or when multiple independent implementations share an API.

## 14. Structuring Auto-Configuration for Easy Overrides

Auto-configuration should have clear classpath/property conditions, create default beans with `@ConditionalOnMissingBean`, avoid overly broad component scanning, avoid registering beans colliding with user beans, separate features with independent conditions, and use constructor/parameter injection for bean factory dependencies.

### 14.1. Do Not Component-Scan the Entire Library Package

A library could declare `@ComponentScan` over its whole package, yet doing so risks registering internal components, unintended implementations, or beans for disabled features. It also makes it harder for users to control what gets created.

In auto-configuration, it is generally better to declare beans explicitly via `@Bean` methods and import needed configurations. That keeps the bean registration contract transparent.

### 14.2. Place @ConditionalOnMissingBean Correctly

~~~java
@Bean
@ConditionalOnMissingBean(RetryPolicy.class)
RetryPolicy retryPolicy(RetryProperties properties) {
    return new DefaultRetryPolicy(...);
}
~~~

This condition lets the application swap the policy. In auto-configuration, configuration processing order and conditions also matter; when multiple auto-configurations interact, use proper ordering/import rules and test with a context runner.

### 14.3. Do Not Rely on Accidental Bean Definition Order

If a default bean must back off when a user bean exists, use formal conditions rather than assuming component scanning will always run before or after in an unguaranteed order.

### 14.4. Separate Independent Features

If a library includes both retry policies and metrics integration, split metrics configuration behind classpath/property conditions. Applications without metrics dependencies can still use core retry.

## 15. Configuration Metadata Helps Users Discover Properties

Spring Boot can generate metadata so IDEs suggest property names, descriptions, and default values.

With Maven, add the configuration processor:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-configuration-processor</artifactId>
    <optional>true</optional>
</dependency>
~~~

With Gradle:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

During build, the processor generates metadata under `META-INF/spring-configuration-metadata.json`.

### 15.1. Write Practical Property Descriptions

Example:

- `max-attempts`: maximum total call attempts, including the initial attempt.
- `initial-delay`: wait duration after the first failure.
- `multiplier`: factor applied to compute subsequent delays.
- `max-delay`: upper bound on wait duration.

Clear descriptions prevent confusion between "retry count" and "total attempts."

### 15.2. Metadata Does Not Replace Documentation

IDE metadata helps with autocomplete and quick docs. Users still need guides covering semantics, examples, defaults, property interactions, and how to override beans.

### 15.3. Never Put Secrets into Metadata or Defaults

Never supply API keys, passwords, or tokens as defaults. If the library requires secrets, applications should pass them from a secret manager/environment following their security practices.

## 16. Testing Core Without Spring

Because `DefaultRetryPolicy` is plain Java, unit tests require no Spring Boot.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import org.junit.jupiter.api.Test;

class DefaultRetryPolicyTest {

    @Test
    void calculatesExponentialDelayWithMaximum() {
        RetryPolicy policy = new DefaultRetryPolicy(
                5,
                Duration.ofMillis(200),
                2,
                Duration.ofMillis(700)
        );

        assertEquals(
                Duration.ofMillis(200),
                policy.delayBeforeAttempt(1)
        );

        assertEquals(
                Duration.ofMillis(400),
                policy.delayBeforeAttempt(2)
        );

        assertEquals(
                Duration.ofMillis(700),
                policy.delayBeforeAttempt(3)
        );
    }

    @Test
    void rejectsInvalidAttemptNumber() {
        RetryPolicy policy = new DefaultRetryPolicy(
                3,
                Duration.ofMillis(100),
                2,
                Duration.ofSeconds(1)
        );

        assertThrows(
                IllegalArgumentException.class,
                () -> policy.delayBeforeAttempt(0)
        );
    }
}
~~~

This test verifies the algorithm and constructor invariants. No `@SpringBootTest` or YAML binding is required.

### 16.1. Test Boundary Conditions

Verify minimum `maxAttempts`, zero or negative `initialDelay`, `maxDelay` smaller than `initialDelay`, `multiplier` equal to 1, delays hitting the maximum cap, invalid attempt numbers, and large values that could overflow.

Fast core unit tests catch algorithmic bugs independently of Spring configuration.

## 17. Testing Properties and Auto-Configuration with ApplicationContextRunner

Auto-configuration is Spring-specific and needs context tests. `ApplicationContextRunner` creates lightweight contexts, supplies properties, and inspects beans.

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

class RetryAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    RetryAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultPolicy() {
        runner.run(context -> {
            assertThat(context)
                    .hasSingleBean(RetryPolicy.class);

            RetryPolicy policy =
                    context.getBean(RetryPolicy.class);

            assertThat(policy.maxAttempts()).isEqualTo(3);
        });
    }

    @Test
    void bindsCustomProperties() {
        runner.withPropertyValues(
                "company.retry.max-attempts=5",
                "company.retry.initial-delay=300ms",
                "company.retry.multiplier=3",
                "company.retry.max-delay=4s"
        ).run(context -> {
            assertThat(context).hasSingleBean(RetryPolicy.class);

            RetryPolicy policy =
                    context.getBean(RetryPolicy.class);

            assertThat(policy.maxAttempts()).isEqualTo(5);
            assertThat(policy.delayBeforeAttempt(1))
                    .isEqualTo(Duration.ofMillis(300));
        });
    }

    @Test
    void backsOffWhenUserProvidesPolicy() {
        RetryPolicy custom = new RetryPolicy() {

            @Override
            public int maxAttempts() {
                return 1;
            }

            @Override
            public Duration delayBeforeAttempt(int failedAttempt) {
                return Duration.ZERO;
            }
        };

        runner.withBean("customRetryPolicy", RetryPolicy.class, () -> custom)
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(RetryPolicy.class);

                    assertThat(context.getBean(RetryPolicy.class))
                            .isSameAs(custom);
                });
    }

    @Test
    void doesNotCreatePolicyWhenDisabled() {
        runner.withPropertyValues(
                "company.retry.enabled=false"
        ).run(context -> {
            assertThat(context)
                    .doesNotHaveBean(RetryPolicy.class);
        });
    }
}
~~~

This example assumes a Spring Boot Test and Spring Framework version supporting these APIs. When implementing, match imports and runner APIs to the version managed by your project.

### 17.1. Test Default Values

Do not only check that the bean exists. Verify defaults match the documented contract.

### 17.2. Test Custom Properties

Provide property values and verify the policy receives the expected values. This verifies the path from Binder to factory method.

### 17.3. Test Back-Off Behavior

Register a user bean and verify auto-configuration does not create an extra default bean.

### 17.4. Test Disabled Condition

Verify `enabled=false` omits the default bean. If consumer beans still require the policy, that is an application composition concern to design and test separately.

## 18. Testing Configuration Validation and Startup Failures

A misconfigured library should fail with a sufficiently clear message.

Example:

~~~yaml
company:
  retry:
    max-attempts: 0
    initial-delay: -5ms
~~~

You can test this via `ApplicationContextRunner` or a Boot context with validation infrastructure.

What to verify:

- Properties bean is registered.
- Binder reads properties.
- Constraint validation is triggered.
- Context reports the invalid property/field.
- No default bean is created with invalid values.

### 18.1. Fail Fast When Settings Are Truly Required

If a property is required for the library to function, failing at startup with a clear message is usually better than letting the application start and fail on the first request.

### 18.2. Do Not Validate Everything Rigidly

An optional property should not cause startup failure when a feature is disabled. Validation must consider real usage conditions.

### 18.3. Do Not Mask Errors with Unexpected Fallbacks

If a user supplies `max-attempts=0`, do not silently clamp it back to 3 unless that is an explicitly documented contract. Silent fallbacks make misconfigurations hard to detect.

## 19. Thread Safety and Lifecycle of Shared Beans

Spring singleton beans are typically shared across multiple requests and threads. If auto-configuration registers a singleton policy, the implementation should be immutable or thread-safe.

`DefaultRetryPolicy` in the example holds only `final` fields and has no mutable per-call state, so it can be shared safely under that design.

### 19.1. Do Not Store Per-Call State in Singleton Fields

Avoid:

~~~java
@Component
public class RetryExecutor {

    private int currentAttempt;

    public void execute() {
        currentAttempt = 0;
        // ...
    }
}
~~~

Multiple concurrent requests can overwrite each other's `currentAttempt`. Per-execution state should live in local variables or dedicated execution contexts.

### 19.2. Beans Owning Resources Must Manage Lifecycles

If a library creates executors, schedulers, connection pools, or threads, define who owns and closes them.

- Spring-managed singleton beans can use destroy callbacks.
- Manually created objects must expose explicit close/lifecycle APIs.
- Do not spawn background threads with no shutdown mechanism.
- Do not retain references to request-scoped objects beyond their scope.

### 19.3. Do Not Open Resources in Static Initializers

Static initializers run during JVM class initialization, making them hard to tie to Spring lifecycles and causing failures before the context has full configuration. Create resources intentionally within bean lifecycles or via factories.

## 20. Managing Transactions and Errors in Libraries

A shared library should be careful about deciding transaction boundaries.

The core retry policy should not open transactions itself. It only returns attempt counts and delays.

If a library provides database services, transaction boundaries may belong to the application service or adapter depending on semantics.

### 20.1. Retrying Transactions Is Not Just Calling a Method Again

If an operation fails mid-transaction, retrying must account for whether the previous transaction rolled back and whether the next attempt gets a clean transaction. Ordering `@Transactional` and retry advice improperly can cause retries to run inside a transaction already marked rollback-only.

A library should not promise to "retry every exception" without defining which exceptions are retryable, whether business errors are retried, whether each attempt runs in a fresh transaction, whether operations are idempotent, and whether prior side effects could repeat.

### 20.2. Let Applications Choose Policies per Use Case

A read operation may retry differently from a write operation. Rather than forcing one global policy onto every request, let the application layer pass policies or choose strategies per operation where needed.

### 20.3. Do Not Catch Exceptions Too Broadly

Avoid catching `Throwable` indiscriminately and retrying. Errors like `OutOfMemoryError`, linkage errors, or validation failures normally cannot be resolved by retrying the operation.

## 21. Library Versioning and Compatibility

A shared library needs an explicit versioning policy, especially when multiple applications upgrade independently.

### 21.1. The Public API Is a Long-Term Contract

Changes that can be breaking include:

- Removing methods or interfaces.
- Changing parameter or return types.
- Changing `maxAttempts` semantics.
- Changing defaults in ways that alter application behavior.
- Renaming properties without a migration path.
- Changing bean types or bean names that consumers inject by qualifier.

Not every breaking change breaks Java compilation—some break runtime behavior.

### 21.2. Properties Need a Migration Path

If renaming `company.retry.max-attempts`, consider deprecating the old property in metadata, supporting an alias for a transition period, logging a helpful warning when the old property is used, updating migration docs, and removing it only in an appropriate major version.

### 21.3. Spring Boot Compatibility

Auto-configuration APIs evolve across Spring Boot/Spring Framework versions. Publish a clear compatibility matrix: supported Boot versions, Java baseline, Spring Framework baseline, whether validation dependencies are required, and which runtime dependencies each module needs.

Do not mix arbitrary Spring Framework or Boot versions within the same dependency graph. For Boot apps, leverage a compatible dependency management/BOM.

### 21.4. Starters Should Not Force Conflicting Versions

Starters should generally let the consuming application's dependency management control the Spring Boot version. If a starter pins conflicting platform versions, users can encounter `NoSuchMethodError`, `ClassNotFoundException`, or binary incompatibilities.

## 22. Packaging and Publishing the Library

A Spring Boot auto-configuration library must ensure its artifacts contain the proper API/core classes, auto-configuration classes, configuration properties classes, `AutoConfiguration.imports`, metadata where applicable, and clean dependency graphs.

### 22.1. Dependency Direction

~~~text
retry-spring-boot-starter
    |
    +--> retry-spring-boot-autoconfigure
    |
    +--> retry-core
             |
             +--> retry-api (if separated)
~~~

The auto-configuration module depends on core and Spring Boot auto-configure. The starter aggregates the modules needed by users.

### 22.2. Optional Dependencies and Runtime Scope

Not every compile dependency of auto-configuration must become a mandatory dependency for every consuming application. Examine which classes load when each condition matches, which dependencies must exist on the runtime classpath, and how your Spring Boot version handles optional integrations.

Do not mark a dependency optional just to shrink the artifact if auto-configuration actually loads that class without an appropriate guard condition.

### 22.3. Inspect Published Artifacts

After building, inspect JAR contents:

~~~bash
jar tf retry-spring-boot-autoconfigure.jar
~~~

Confirm `AutoConfiguration.imports` and auto-configuration classes are included in the archive. IDE context tests can pass even if metadata files are missing from the published artifact due to build resource misconfiguration.

### 22.4. Do Not Require Users to Component-Scan Library Packages

Proper auto-configuration is discovered by Boot through metadata. Users should not have to manually add library packages to `@ComponentScan` if documentation states adding the starter is sufficient.

## 23. Consumer Application Usage Example

A Maven application adds the starter using a version managed by the organization's dependency management:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>company-retry-spring-boot-starter</artifactId>
</dependency>
~~~

Configuration:

~~~yaml
company:
  retry:
    enabled: true
    max-attempts: 4
    initial-delay: 250ms
    multiplier: 2
    max-delay: 3s
~~~

Service injects the contract:

~~~java
@Service
public class InventoryGateway {

    private final RetryPolicy retryPolicy;

    public InventoryGateway(RetryPolicy retryPolicy) {
        this.retryPolicy = retryPolicy;
    }

    public int maxAttempts() {
        return retryPolicy.maxAttempts();
    }
}
~~~

If the application wants its own policy, it registers its own `RetryPolicy` bean. No changes to library source code are required.

### 23.1. Applications Without Spring Boot

When core is kept independent, a plain Java application can instantiate the implementation directly:

~~~java
RetryPolicy policy = new DefaultRetryPolicy(
        3,
        Duration.ofMillis(200),
        2,
        Duration.ofSeconds(5)
);
~~~

This demonstrates that API/core do not need the Spring container to operate.

### 23.2. Applications Requiring Multiple Policies

If an application needs distinct policies across operation groups, a single bean may not suffice. Design a keyed registry/factory or pass strategies into use cases. Do not rely on Spring injecting a single bean type and force it to serve incompatible semantics.

## 24. Common Anti-patterns

### 24.1. Core Calling ApplicationContext

Logic looks up dependencies itself, complicating testing and reuse. Replace with constructor injection or passing dependencies via methods.

### 24.2. Every Class Reading Environment

Configuration becomes scattered, hard to validate, and obscures the property contract. Replace with a single `@ConfigurationProperties` object at the integration layer and pass values into core.

### 24.3. Forcing Users to Exclude Auto-Configuration to Replace One Bean

Users have to duplicate all internal wiring manually. Replace with `@ConditionalOnMissingBean` on the appropriate default beans.

### 24.4. Component-Scanning the Entire Library Package

Internal beans get registered unintentionally and feature conditions become hard to manage. Replace with auto-configuration and explicit `@Bean` methods.

### 24.5. Constructors Performing Network/Database I/O

Startup depends on external availability and tests are hard to isolate. Replace with lightweight clients, on-demand connections, or intentional lifecycle/readiness policies.

### 24.6. Defaults Silently Replacing Invalid Configuration

The application runs with behavior different from what operators intended. Replace with validation and clear errors on invalid inputs.

### 24.7. Using Properties to Pick Arbitrary Class Names

Reflection, classloading, and runtime failures are hard to diagnose; APIs lose type safety. Replace with strategy interfaces and bean customization.

### 24.8. Singletons Holding Per-Request State

Race conditions can happen across threads. Replace with execution-local state or an appropriate object scope.

### 24.9. Retrying Every Exception

Can repeat side effects and amplify load on unrecoverable failures. Replace with retry policies specifying allowed error types, budgets, and idempotency semantics.

### 24.10. Testing Only with @SpringBootTest

Core tests become slow and coupled to the framework. Replace with plain Java core unit tests, context runner tests for auto-configuration, and targeted integration tests.

## 25. Workflow for Designing a Shared Library

1. **Write the contract first.** Define interfaces, inputs/outputs, exceptions, and semantics.
2. **Separate core from framework.** Keep algorithms and invariants in plain Java whenever possible.
3. **Identify genuinely needed configuration.** Assign a dedicated namespace and document defaults.
4. **Create typed properties.** Bind once and validate explicitly.
5. **Implement defaults.** Keep state immutable or thread-safe.
6. **Write auto-configuration.** Use conditions and bean factory methods intentionally.
7. **Allow overrides.** Use interfaces/strategies and `@ConditionalOnMissingBean`.
8. **Define extension points.** Add listeners/customizers only when genuinely needed.
9. **Manage lifecycles.** Avoid unintended external side effects during startup.
10. **Write unit tests for core.** Without Spring.
11. **Write context tests for auto-configuration.** Verify defaults, properties, conditions, and back-off.
12. **Inspect artifacts.** Verify metadata and dependencies are packaged.
13. **Write consumer documentation.** Include configuration examples, overriding, disabling, and migration notes.
14. **Publish compatibility.** State Java/Spring Boot versions and versioning policy.

## 26. Practice Exercises

### Exercise A: Separate Core from Spring

Create `RetryPolicy` and `DefaultRetryPolicy` in a plain Java module. Do not import `org.springframework.*` in core.

Write unit tests for max attempts, delay sequences, max delay, and invalid arguments.

### Exercise B: Create Properties

Create `RetryProperties` with a dedicated prefix, defaults, and validation. Write YAML configuration overriding each parameter.

Explain which properties are optional, which are required, and the semantics of each unit.

### Exercise C: Auto-Configuration

Create `RetryAutoConfiguration` with `@AutoConfiguration`, `@EnableConfigurationProperties`, `@ConditionalOnProperty`, and `@ConditionalOnMissingBean`. Register it in `AutoConfiguration.imports`.

### Exercise D: Custom Bean

In a demo application, supply a custom `RetryPolicy` bean. Verify auto-configuration does not create an additional default bean.

### Exercise E: Disable the Feature

Set `company.retry.enabled=false`. Verify the default bean does not exist. If a service still requires the bean, redesign conditional composition so startup behavior stays consistent.

### Exercise F: Context Runner

Write tests for defaults, custom property values, user bean overrides, and disabled conditions using `ApplicationContextRunner`.

### Exercise G: Without Spring

Use the core library in a Java `main` method without starting Spring. Instantiate the policy directly and invoke the API.

### Exercise H: Extension Listener

Add `RetryListener` so consumers can record metrics. Define listener ordering, exception handling for callbacks, and whether callbacks fire on every retry.

### Exercise I: Profile Configuration

Provide two different profile configurations. Run the context with each profile and verify property binding. The library itself must not select profiles.

### Exercise J: Thread Safety

Have multiple threads concurrently call one `DefaultRetryPolicy` instance. Confirm the implementation stores no per-operation state in mutable fields.

### Exercise K: Startup Side Effects

Create an adapter simulating an external client. Compare connecting immediately in the constructor vs. connecting on demand. Observe impacts on context startup and tests.

### Exercise L: Inspect Artifact

Build the auto-configuration JAR and verify `AutoConfiguration.imports` and configuration metadata exist in the archive.

## 27. Self-Check Questions

**1. Why should core be separated from Spring auto-configuration?**

So rules and APIs can be used independently, unit tested in plain Java, and avoid forcing consumers to pull in Spring unnecessarily.

**2. What is the role of auto-configuration?**

Registering default beans based on classpath presence, properties, and existing beans.

**3. Should a starter contain business logic?**

No. A starter primarily aggregates dependencies for convenient consumer integration.

**4. Why do properties need a dedicated namespace?**

To avoid collisions, clarify ownership, and help users discover settings.

**5. Where should @ConfigurationProperties live?**

In the Spring Boot integration layer, with values converted into plain arguments/configuration for core.

**6. What does @ConditionalOnMissingBean enable?**

Allowing applications to supply their own implementations and causing default beans to back off.

**7. When should you use properties vs. strategy beans?**

Properties for data choices; strategy beans for substitutable behavior.

**8. Why should core not call ApplicationContext itself?**

It creates a service locator, hides dependencies, and couples core to the container.

**9. Why should constructors not perform network I/O?**

It ties startup to external service availability, complicates timeout control, and hinders testing.

**10. Why is ApplicationContextRunner needed?**

To test auto-configuration, property binding, conditions, and bean overrides in a lightweight context.

**11. Can a singleton bean hold per-request state?**

Not if state can be shared across threads; use local/execution state or an appropriate scope.

**12. Why is retrying every exception dangerous?**

Some failures are non-recoverable, and retries can repeat side effects, create duplicate data, or amplify load.

**13. Should auto-configuration component-scan the entire library package?**

Usually no; explicit bean registration makes conditions and composition easier to control.

**14. Why inspect published JARs?**

To confirm auto-configuration metadata, resources, and dependencies are actually packaged in the artifact consumers receive.

**15. Why must default behavior be documented?**

Users must know what happens when properties are omitted and understand semantics before deploying.

## 28. Conclusion

A well-designed shared library has **a small API, independent core rules, and a clean Spring integration layer**. Core handles behaviors and invariants; typed configuration properties express application choices; auto-configuration registers default implementations; `@ConditionalOnMissingBean` and strategy interfaces provide extension points for consumers to customize behavior.

Let the application control profiles and environments, and avoid having core read `Environment` or look up beans via `ApplicationContext`. Keep constructors lightweight, manage lifecycles intentionally, and never let singletons hold per-request state. Test core with plain Java JUnit, test binding/conditions/back-off with the context runner, and inspect the actual artifact before publishing.

When contracts, defaults, properties, and extension points are clear, applications can adopt the library quickly with defaults or tailor it to their own needs without forking the implementation. That is the foundation for sharing a capability across many applications while letting each retain control over its own composition and business behavior.
