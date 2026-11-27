# Organizing resilience4j.circuitbreaker.configs and instances

In Spring Cloud CircuitBreaker using Resilience4j, Circuit Breaker configuration is organized into two main groups: `configs` and `instances`. `configs` holds reusable configuration profiles; `instances` declares the actual Circuit Breakers that the application creates for each dependent service or operation. This organization allows multiple calls to share common protection policies while still tuning specific thresholds according to each dependency's characteristics.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, we use Circuit Breakers to prevent cascading failures when a dependent service is slow or unavailable. Because each dependency has different traffic, latency, and criticality, organizing the configuration clearly helps control CLOSED, OPEN, and HALF_OPEN states, sliding windows, and fallback strategies consistently.

## 1. Roles of configs and instances

The two configuration groups serve different purposes:

| Group | Role | Examples |
| --- | --- | --- |
| `resilience4j.circuitbreaker.configs` | Declares reusable parameter sets, typically including a default configuration and dependency-category configurations | `default`, `read-service`, `payment-service` |
| `resilience4j.circuitbreaker.instances` | Declares each named Circuit Breaker used by the application | `inventory`, `payment`, `customer-profile` |

You can think of `configs` as policy templates, while `instances` are the Circuit Breakers created from those policies. An instance can reference a base configuration using the `baseConfig` property, and then override a few parameters if that dependency needs specific behavior.

For example, multiple services might share a sliding window size of 20 and a 50% failure rate threshold. However, the payment service might require a longer OPEN duration than the catalog read service. We place the shared parameters in one config, then override only the wait duration on the payment instance.

## 2. Basic YAML structure

Configuration is typically placed in the Spring Boot application's `application.yml` or in an active profile-specific configuration file:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        automaticTransitionFromOpenToHalfOpenEnabled: true
    instances:
      inventory:
        baseConfig: default
      customer-profile:
        baseConfig: default
      payment:
        baseConfig: default
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

In this example:

- `configs.default` defines the shared policy.
- `instances.inventory` and `instances.customer-profile` inherit parameters from `default`.
- `instances.payment` also inherits `default`, but changes the OPEN duration to 30 seconds and allows only 2 test calls in HALF_OPEN.

Instances must be named according to the identifier the application uses when creating the Circuit Breaker. With Spring Cloud CircuitBreaker, if the code calls `circuitBreakerFactory.create("inventory")`, the corresponding configuration section is `instances.inventory`. The names must match so that the intended configuration is applied to the right call.

## 3. Inheritance and overrides with baseConfig

The `baseConfig` property specifies which configuration profile an instance uses as its foundation. Properties not redeclared on the instance are taken from the base config; properties declared directly on the instance replace the corresponding inherited values. Each instance references a specific config; declare the full policy needed in that config rather than assuming other configs automatically inherit from one another.

For example, policies can be separated by operation group:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
      read-service:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        slowCallDurationThreshold: 1500ms
        slowCallRateThreshold: 60
      critical-write:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 30
        waitDurationInOpenState: 20s
        permittedNumberOfCallsInHalfOpenState: 5
    instances:
      product-catalog:
        baseConfig: read-service
      inventory:
        baseConfig: read-service
        slidingWindowSize: 40
      order-write:
        baseConfig: critical-write
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Here, `read-service` and `critical-write` are two independent policies. `product-catalog` uses the read policy. `inventory` uses the same policy but increases the window size. `order-write` uses the critical write policy and limits the number of trial calls in HALF_OPEN.

When reading configuration, trace from `instances.<name>.baseConfig` to the referenced config, then inspect the overridden properties on the instance. Avoid copying all shared parameters into every instance because that makes the configuration verbose and hard to keep in sync when the shared policy changes. Configs placed under `configs` are named policy profiles; an instance selects one via `baseConfig`.

The config name is an application-chosen name for referencing. The instance name is the Circuit Breaker identifier used in code. These two names can be the same or different; what matters is that `baseConfig` points to the right config and the instance name matches the name created in the application.

## 4. Commonly set parameters in config

Parameters in a config describe how the Circuit Breaker observes outcomes and decides state transitions:

| Property | Meaning | Selection notes |
| --- | --- | --- |
| `slidingWindowType` | Selects `COUNT_BASED` or `TIME_BASED` | Choose based on whether you want to observe call count or time duration |
| `slidingWindowSize` | Number of calls in a COUNT_BASED window or number of seconds in a TIME_BASED window | Larger windows are more stable but may react more slowly |
| `minimumNumberOfCalls` | Minimum number of outcomes before calculating rates | Avoids making decisions from too few samples |
| `failureRateThreshold` | Percentage threshold of failed calls to open the circuit | Balances failure detection against random noise |
| `slowCallDurationThreshold` | Duration from which a call is considered slow | Should be based on the normal latency of the dependency |
| `slowCallRateThreshold` | Percentage threshold of slow calls | Detects performance degradation even when calls still succeed |
| `waitDurationInOpenState` | Duration to stay OPEN before attempting recovery | Avoids retrying too early while the dependency is still unstable |
| `permittedNumberOfCallsInHalfOpenState` | Number of trial calls allowed in HALF_OPEN | Limits load when testing recovery |
| `automaticTransitionFromOpenToHalfOpenEnabled` | Allows automatic transition from OPEN to HALF_OPEN after the wait duration | Useful when you want state transition without waiting for a new call |

For example, with `COUNT_BASED` and `slidingWindowSize: 20`, the window observes the most recent 20 calls. With `TIME_BASED` and `slidingWindowSize: 10`, the window observes outcomes from the last 10 seconds. `minimumNumberOfCalls` still needs to be set reasonably high to avoid calculating rates when there is too little data in the window.

Duration values like `10s` and `1500ms` make YAML easy to read. Use the duration format supported by the Spring Boot and Resilience4j versions in use.

## 5. Creating dedicated configurations per dependency

Not every service should use the same thresholds. A profile read service might tolerate a few seconds of waiting and can use caching. A payment service might require fast responses while also needing caution when retrying because the operation has financial impact.

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
      fast-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 40
      payment-protection:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 30
        minimumNumberOfCalls: 15
        failureRateThreshold: 30
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 1
    instances:
      customer-profile:
        baseConfig: fast-read
      inventory:
        baseConfig: default
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
      payment:
        baseConfig: payment-protection
~~~

In this configuration, profile read calls are considered slow when exceeding 800 ms; inventory has a slow threshold of 2 seconds; payment uses a lower failure threshold, a longer OPEN duration, and allows only one trial call. These are illustrative values to demonstrate organization, not recommendations to apply verbatim to every system.

When designing configs by group, group together dependencies with similar latency goals and recovery behavior. Do not share a single policy solely because services use the same HTTP protocol; a search service and a payment service can have very different operational requirements.

## 6. Exception classification in configuration

Resilience4j allows specifying which exceptions are counted as failures and which are ignored. This is important because not every error indicates that the dependent service is broken. For example, a non-existent product may be a valid business result, whereas connection errors or server errors usually reflect a dependency outage.

Configuration example:

~~~yaml
resilience4j:
  circuitbreaker:
    configs:
      default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        recordExceptions:
          - java.io.IOException
        ignoreExceptions:
          - com.example.inventory.ProductNotFoundException
    instances:
      inventory:
        baseConfig: default
~~~

The exception names in the list must be the exact fully qualified class names from the actual application. In this example, I/O errors are recorded as failures; product-not-found errors are ignored when calculating the rate. It is important to understand Resilience4j's policy: when `recordExceptions` is declared, exceptions not matching the recorded list are not automatically treated as failures; `ignoreExceptions` are excluded from the calculation. Classify exceptions according to business meaning and the actual error types of your HTTP client or service access library.

If every exception is recorded, input or business errors can cause the Circuit Breaker to open falsely. Conversely, if too many exceptions are ignored, the circuit may fail to open even when the dependency is genuinely failing.

## 7. Connecting instance names with code

Configuration only applies to calls that use the matching Circuit Breaker identifier. With the Spring Cloud CircuitBreaker abstraction, code typically creates an instance by name:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult getInventory(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.get(sku),
                failure -> InventoryResult.unavailable(sku)
        );
    }
}
~~~

Because the code calls `create("inventory")`, the configuration needs `resilience4j.circuitbreaker.instances.inventory`. This instance can use `baseConfig: default`, `baseConfig: read-service`, or another suitable config.

If the name in code and the name in YAML do not match, the application may create a Circuit Breaker with default settings instead of the parameter set the developer intended. Therefore, when adding a new dependency call, update both the instance name and its corresponding configuration together.

## 8. Distinguishing Circuit Breaker config from other mechanisms

The `resilience4j.circuitbreaker` prefix is dedicated to Circuit Breaker policies. Timeouts and bulkheads have their own configuration groups; do not put their properties inside `circuitbreaker.configs` or `circuitbreaker.instances`.

| Mechanism | Common configuration group | Purpose |
| --- | --- | --- |
| Circuit Breaker | `resilience4j.circuitbreaker` | Opens the circuit when failure rate or slow call rate exceeds threshold |
| TimeLimiter | `resilience4j.timelimiter` | Limits the wait timeout for applicable operations |
| Bulkhead | `resilience4j.bulkhead` or `resilience4j.thread-pool-bulkhead` | Limits the number of concurrent calls or tasks |
| Retry | `resilience4j.retry` | Performs bounded retries when encountering selected errors |

These mechanisms can work together, but each must be configured and monitored in its proper role. For example, `slowCallDurationThreshold` helps the Circuit Breaker detect slow calls; it does not replace a timeout to terminate a hanging call. A bulkhead limits concurrent resources; it does not decide on its own whether a dependency has recovered.

## 9. Common mistakes when organizing configs and instances

| Configuration mistake | Possible consequence | How to check |
| --- | --- | --- |
| Setting parameters in `instances` while code creates a different name | Intended instance is not used | Match `create("...")` against the keys under `instances` |
| `baseConfig` pointing to a non-existent config name | Inherited configuration profile cannot be applied as intended | Check names under `configs` and `baseConfig` |
| Copying shared values into every instance | Duplicated configuration, hard to maintain | Move shared values into a base config |
| Window too small or `minimumNumberOfCalls` too low | Circuit may open due to a few random errors | Compare against actual traffic and sample counts |
| Slow call threshold not aligned with normal latency | Circuit opens too early or detects too late | Measure actual latency before setting thresholds |
| Recording all business errors as dependency failures | Circuit Breaker may open even though the service is healthy | Review `recordExceptions` and `ignoreExceptions` |
| Placing timeout or bulkhead under the wrong prefix | Configuration is not picked up by the corresponding mechanism's binder | Put each property in the correct configuration group |
| Incorrect YAML indentation or invalid value types | Spring Boot cannot bind the desired values | Check YAML structure and startup logs |

When diagnosing, verify in order: the configuration file being loaded, prefixes and indentation, instance names in code, referenced config names, and then individual parameters and runtime metrics.

## 10. Process for adding a new Circuit Breaker

When protecting a new dependency, you can follow this sequence:

1. Determine a stable name for the Circuit Breaker, for example `inventory`.
2. Choose a base config based on the dependency's traffic and latency characteristics.
3. Declare `instances.inventory` and point `baseConfig` to the chosen config.
4. Override only properties that genuinely differ from the shared policy.
5. Use the exact name `inventory` when creating the Circuit Breaker in code.
6. Verify behavior in CLOSED, OPEN, and HALF_OPEN; observe failure rate, slow call rate, and rejected call count.
7. Tune thresholds based on real metrics rather than relying solely on illustrative values.

For example, if the Inventory service has higher normal latency than the profile service, you can create a dedicated config for the inventory-read group with an appropriate `slowCallDurationThreshold`. If the payment service needs stricter protection, the payment instance can inherit the shared config and set a longer `waitDurationInOpenState` along with a limited number of trial calls.

## 11. Synthesis scenario

A system has three dependencies: Customer Profile service, Inventory service, and Payment service. The development team chooses a shared config to standardize the sliding window and failure threshold. Profile and Inventory use a read policy, while Payment uses a dedicated policy with a longer OPEN duration.

When the Inventory service slows down, the `inventory` instance records the slow call rate. If the rate reaches the threshold after sufficient samples, the circuit transitions from CLOSED to OPEN. After the wait duration, the circuit transitions to HALF_OPEN and allows only the configured number of trial calls. Meanwhile, Inventory's errors do not alter the Payment Circuit Breaker's state because the two dependencies use separate instances.

When analyzing this scenario, ask yourself:

- Why place shared policies in `configs.default`?
- When should you create a separate config instead of overriding multiple properties on each instance?
- How does the name `inventory` in code relate to `instances.inventory`?
- How do `baseConfig` and properties declared directly on an instance work together?
- Why do timeouts and bulkheads belong to different configuration groups than Circuit Breaker?
- Which metrics should be observed to know whether thresholds are protecting the system effectively?

Organizing `resilience4j.circuitbreaker.configs` and `instances` well makes protection policies reusable, readable, and tunable per dependency. By combining matching instance names, sliding window thresholds, and operational metrics, a Spring Cloud application can intentionally control Circuit Breaker state transitions and contain cascading failures.
