# baseConfig and Shared Configuration Inheritance

In a Spring Cloud CircuitBreaker application using Resilience4j, multiple dependencies may require very similar Circuit Breaker policies. If every instance redeclares the entire sliding window, failure threshold, OPEN duration, and probe call count, the configuration becomes verbose, hard to keep in sync, and prone to drift when changes are needed.

Resilience4j supports shared configuration profiles in the configs section and allows each instance to reference a profile using the baseConfig property. An instance inherits the shared values and can then declare specific values to tune behavior for its corresponding dependency.

This mechanism helps standardize configuration across dependent services, reduces duplication, and still preserves the ability to fine-tune settings based on each dependency's load, latency, and criticality characteristics.

## 1. Distinguishing configs and instances

In Resilience4j configuration, the two sections serve different roles:

- **configs** holds reusable template parameter groups. A configuration group does not represent a running Circuit Breaker yet.
- **instances** declares the actual Circuit Breakers used by the application. Each instance has an ID and can reference a configuration group in configs via baseConfig.

General structure:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        failureRateThreshold: 50
    instances:
      inventory:
        baseConfig: default
      payment:
        baseConfig: default
        failureRateThreshold: 30
~~~

In this example:

- default is the name of a shared configuration group.
- inventory and payment are two Circuit Breaker instances used by the application.
- inventory inherits properties from default.
- payment also inherits default but overrides failureRateThreshold to 30.

Names in configs can be chosen based on purpose or operational profile, such as default, shared, highLatency, or criticalDependency. Instance names should represent the dependency or business flow being protected, such as inventory, payment, or customer-profile.

## 2. How does baseConfig work?

The baseConfig property is placed inside an instance and points to the name of a configuration group in configs of the same Resilience4j module type. When creating the instance, values from the base group are used as the common configuration. Properties declared directly on the instance override the corresponding inherited values.

You can visualize the application order:

~~~mermaid
flowchart TD
    A[Shared configs group] --> B[Instance declares baseConfig]
    C[Instance-specific properties] --> D[Merge configuration]
    B --> D
    D --> E[Circuit Breaker with effective configuration]
~~~

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        slidingWindowSize: 100
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
~~~

Configuration outcome:

| Property | shared group | inventory | payment |
|---|---:|---:|---:|
| slidingWindowType | COUNT_BASED | COUNT_BASED | COUNT_BASED |
| slidingWindowSize | 50 | 50 | 100 |
| minimumNumberOfCalls | 10 | 10 | 10 |
| failureRateThreshold | 50 | 50 | 30 |
| slowCallDurationThreshold | 2s | 2s | 2s |
| slowCallRateThreshold | 50 | 50 | 50 |
| waitDurationInOpenState | 10s | 10s | 20s |
| permittedNumberOfCallsInHalfOpenState | 3 | 3 | 3 |

inventory uses all shared values. payment only overrides three properties: slidingWindowSize, failureRateThreshold, and waitDurationInOpenState; the remaining properties continue to come from shared.

You must distinguish inherited values from library default values. If an instance does not reference baseConfig, it does not automatically inherit an arbitrary group just because that group is named shared. Declare baseConfig explicitly and ensure the referenced name exists in the corresponding configs section.

## 3. Declaring a shared Circuit Breaker configuration group

A shared configuration group should contain properties that are consistently meaningful for dependencies in the same group. For example, typical HTTP dependencies can share the statistics window, failure threshold, and OPEN duration:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      inventory:
        baseConfig: default
      customer:
        baseConfig: default
      recommendation:
        baseConfig: default
~~~

The configuration above lets three instances share one policy. When you need to change the window size or OPEN duration for the entire group, you only need to update the default group.

However, you should not put every property into one shared group if dependencies have different characteristics. For example, a payment service might need a stricter failure threshold, while a product recommendation service might tolerate fallback or longer degradation. In that case, create separate configuration groups according to operational characteristics.

## 4. Creating multiple purpose-based configuration groups

An application can define multiple configuration groups in the same configs section. Each instance selects the appropriate group via baseConfig.

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      standard:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
      critical:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 40
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
      bestEffort:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 60
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 5
    instances:
      inventory:
        baseConfig: standard
      payment:
        baseConfig: critical
      recommendation:
        baseConfig: bestEffort
~~~

You can think of the groups as operational policies:

| Group | Example usage | Characteristics |
|---|---|---|
| standard | Typical dependencies | Balanced thresholds and recovery time |
| critical | Critical dependencies such as payment | Stricter failure detection, cautious probing |
| bestEffort | Recommendations, supplementary content | Allows higher failure rate and attempts recovery sooner |

The values above are examples only. Choosing thresholds should be based on SLA, traffic, and actual dependency behavior. Do not label a dependency critical or bestEffort solely based on its service name without determining the business impact when the dependency degrades.

## 5. Configuration inheritance and per-instance overrides

Per-instance overrides keep a shared policy without forcing every dependency to behave identically. Some common cases:

- A slow-responding dependency needs a higher or lower slowCallDurationThreshold depending on SLA.
- A high-traffic dependency may need a larger slidingWindowSize.
- A critical dependency can use a lower failureRateThreshold to open the circuit earlier.
- A fast-recovering dependency can use a shorter waitDurationInOpenState, provided probing does not create dangerous load.

For example, payment inherits the critical group but adjusts the OPEN duration and probe call count:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      critical:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 2
    instances:
      payment:
        baseConfig: critical
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
~~~

payment receives shared values from critical. The two properties declared on the instance take effect specifically for payment. Other instances referencing critical still keep a 20-second OPEN duration and allow two probe calls.

When overriding, declare only the properties that genuinely differ. Copying the entire shared configuration into each instance defeats the purpose of reuse and makes future changes hard to manage.

## 6. Separating shared configurations by Resilience4j module type

Resilience4j has multiple modules such as Circuit Breaker, Retry, TimeLimiter, Bulkhead, and RateLimiter. Each module has its own configs and instances sections. A configuration group under circuitbreaker does not automatically apply to retry or bulkhead.

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        failureRateThreshold: 30

  retry:
    configs:
      shared:
        maxAttempts: 2
        waitDuration: 200ms
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        maxAttempts: 1

  timelimiter:
    configs:
      shared:
        timeoutDuration: 2s
        cancelRunningFuture: true
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
        timeoutDuration: 3s
~~~

In this example:

- Circuit Breaker uses shared to reuse the window and failure threshold.
- Retry uses shared to reuse the attempt count and wait duration.
- TimeLimiter uses shared to reuse the timeout limit.
- The payment instance can override specific values within each module.

The name shared is used across three independent configuration sections. Each baseConfig only references the configs group belonging to its corresponding module. Therefore, retry.instances.payment.baseConfig must point to retry.configs, not circuitbreaker.configs.

This organization keeps policies consistently structured while separating responsibilities. For instance, TimeLimiter's timeout duration is not Circuit Breaker's OPEN duration; Retry's attempt count is also unrelated to the sliding window size.

## 7. Linking instance names with Spring Cloud CircuitBreaker

When using Spring Cloud CircuitBreaker with the Resilience4j implementation, code creates a breaker by ID. The ID must match the instance name in Resilience4j configuration.

Example:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryClient {

    private final CircuitBreaker inventoryBreaker;

    public InventoryClient(CircuitBreakerFactory<?, ?> factory) {
        this.inventoryBreaker = factory.create("inventory");
    }
}
~~~

With the reactive API:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class ReactiveInventoryClient {

    private final ReactiveCircuitBreaker inventoryBreaker;

    public ReactiveInventoryClient(
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.inventoryBreaker = factory.create("inventory");
    }
}
~~~

In both cases, the ID inventory is used to select the inventory instance configuration. If that instance declares baseConfig: shared, the shared values from shared are applied, and then inventory's own values override them.

Factory is Spring Cloud CircuitBreaker's API; baseConfig is Resilience4j's configuration reuse mechanism. The two components coordinate via the instance ID, but have distinct roles. Do not confuse baseConfig with the factory's default configuration method in Java or with the default configuration of another Circuit Breaker implementation.

## 8. Organizing configuration by environment

Local, test, staging, and production environments may need different values. You can keep the shared group and instance structure stable, then adjust certain values per Spring profile.

Example base configuration in application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      shared:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 50
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
    instances:
      inventory:
        baseConfig: shared
      payment:
        baseConfig: shared
~~~

Example application-prod.yml overriding some specific properties:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 100
        failureRateThreshold: 40
      payment:
        waitDurationInOpenState: 30s
        failureRateThreshold: 25
~~~

Configuration merging across profiles must be managed according to the project's Spring Boot configuration mechanism. When a profile is activated, check the effective values of each instance to ensure you did not accidentally alter the shared policy. Avoid copying the entire shared configuration into a profile file when only a few properties need adjustment.

Profiles should be tracked in source control or a version-controlled configuration management system. Do not arbitrarily change production thresholds without monitoring the impact on failure rates, fallbacks, and dependency load.

## 9. Common mistakes with baseConfig

- **Referencing the wrong group name**: baseConfig points to a name that does not exist in configs of the same module. Check spelling and declaration location.
- **Placing baseConfig at the wrong YAML level**: baseConfig must sit inside the instance, at the same level as overridden properties.
- **Mixing groups across modules**: a group in circuitbreaker is not a group in retry or timelimiter.
- **Assuming the shared group applies automatically to every instance**: an instance must reference it explicitly with baseConfig.
- **Copying the entire configuration into each instance**: this creates multiple sources of truth and makes changes difficult to synchronize.
- **Overriding too many properties**: an instance can drift away from the shared policy without a clear operational reason.
- **Using one shared group for dependencies with different characteristics**: shared thresholds may be too sensitive for one service yet too slow for another.
- **Failing to verify configuration after switching profiles**: final values may differ from expectations due to merged configuration layers.
- **Confusing baseConfig with request fallback**: baseConfig inherits configuration properties; fallback is the handling flow when a call fails or is rejected.

## 10. Process for building shared configurations

When organizing baseConfig for a Spring Cloud CircuitBreaker application, you can follow this sequence:

1. List dependencies and determine the operational characteristics of each dependency.
2. Group dependencies with similar requirements for failure sensitivity, recovery time, and traffic.
3. Create configuration groups in configs for each Resilience4j module.
4. Declare instances in instances and reference the appropriate group using baseConfig.
5. Override on an instance only the properties that truly need to differ.
6. Ensure the ID passed to CircuitBreakerFactory or ReactiveCircuitBreakerFactory matches the instance name.
7. Organize changes by Spring profile while keeping the shared group structure clear.
8. Observe Circuit Breaker state, retry, timeout, bulkhead, rate limiter, and fallback behavior to adjust policies based on data.

baseConfig enables instances to reuse a unified configuration policy. The configs group serves as a shared template; instances represent concrete Circuit Breakers; properties declared directly on an instance override inherited values. By grouping according to dependency characteristics and keeping IDs consistent between code and YAML, Resilience4j configuration in Spring Cloud becomes easier to read, easier to maintain, and less prone to drift as the system grows.
