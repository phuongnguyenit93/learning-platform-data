# Distinguishing Configuration Groups and Actual Circuit Breaker IDs

## Objectives

When integrating Spring Cloud CircuitBreaker with Resilience4j, each circuit breaker is created with an ID. The factory also provides an overload that accepts a `groupName`. These two values serve different configuration purposes. If you confuse them with shared profile names in YAML, the application may apply the wrong timeout, unintentionally share state, or become hard to observe per dependency.

After this lesson, you can:

- Identify which ID represents the actual Circuit Breaker in application code.
- Explain how `groupName` is used when creating a Circuit Breaker with the Resilience4j integration.
- Distinguish instance ID, group name, and `configs` profiles inherited via `baseConfig`.
- Design names for multiple dependencies that can share a timeout while still keeping independent Circuit Breaker state.
- Cross-check YAML configuration, factory calls, metrics, and tests to detect incorrect mappings.

## Three types of names to distinguish

In an application with multiple dependent services, you may encounter three types of names:

| Name type | Example | Role |
|---|---|---|
| Circuit Breaker ID | `catalog-read`, `inventory-read` | Identifies a specific circuit breaker; used to select Circuit Breaker configuration and identify its state/metrics. |
| `groupName` passed to factory | `slow-remote`, `fast-remote` | In Spring Cloud CircuitBreaker's Resilience4j integration, used to select the TimeLimiter configuration for the call. |
| Configuration profile name | `remote-default`, `payment-strict` | Reusable profile declared under `resilience4j.circuitbreaker.configs` or `resilience4j.timelimiter.configs`, then inherited by instances via `baseConfig`. |

The three types of names can match as strings, yet their meanings are not identical. You should name them distinctly by purpose so readers can easily tell which key is being looked up.

One especially important point: `groupName` in `create(id, groupName)` is not a shared Circuit Breaker state group name. Circuit Breakers with different IDs still have separate state. In the Resilience4j integration, this parameter is used to select the TimeLimiter configuration. To reuse a set of Circuit Breaker properties, declare a profile under `configs` and have multiple instances share `baseConfig`.

## ID is the identifier of the actual Circuit Breaker

With Spring Cloud CircuitBreaker, synchronous code typically creates a circuit breaker via `CircuitBreakerFactory`:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogGateway {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    public CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    public Product findById(String id) {
        CircuitBreaker breaker = circuitBreakerFactory.create("catalog-read");

        return breaker.run(
                () -> catalogClient.findById(id),
                error -> Product.unavailable(id));
    }
}
```

In this example, `catalog-read` is the Circuit Breaker ID. This ID should be stable and describe a dependency or group of operations with the same failure characteristics. It should not contain per-request varying data such as product IDs, user IDs, or correlation IDs.

If every request to the same catalog service creates a different ID, the system can create many circuit breakers and many metric series instead of accumulating outcomes on a single meaningful protector. Conversely, if two dependencies with different failure characteristics share one ID, one failing service can trip the circuit for the other service as well.

Choose the ID along the failure boundary you want to isolate. For instance, `catalog-read` and `catalog-search` can be two separate IDs if they call endpoints or service clusters that can fail independently. If two operations always go through the same dependency and need the same protection decisions, a single shared ID may be more appropriate.

## groupName in the Resilience4j factory

Spring Cloud CircuitBreaker provides an overload that takes both an ID and a group name:

```java
CircuitBreaker breaker = circuitBreakerFactory.create("catalog-read", "slow-remote");
```

In the Resilience4j integration:

- `catalog-read` is used to determine the Circuit Breaker configuration and instance.
- `slow-remote` is used to determine the TimeLimiter configuration.

This allows multiple Circuit Breakers to have independent state while sharing one timeout limit. For example, `catalog-read` and `inventory-read` can both use the `slow-remote` group while each ID keeps its own statistics window, failure threshold, and state.

A reactive example using the same mapping rule:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

public class ReactiveCatalogGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final CatalogClient catalogClient;

    public ReactiveCatalogGateway(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            CatalogClient catalogClient) {
        this.factory = factory;
        this.catalogClient = catalogClient;
    }

    public Mono<Product> findById(String id) {
        ReactiveCircuitBreaker breaker = factory.create("catalog-read", "slow-remote");

        return breaker.run(
                catalogClient.findById(id),
                error -> Mono.just(Product.unavailable(id)));
    }
}
```

`groupName` is optional depending on the factory overload. Add this parameter only when you need to select TimeLimiter configuration using a key different from the Circuit Breaker ID. The exact mapping behavior must be verified against the Spring Cloud CircuitBreaker implementation and version in use; do not assume another implementation uses this parameter the same way Resilience4j does.

TimeLimiter is also not a mechanism that can arbitrarily stop any synchronous piece of code. With an overload that runs a synchronous `Supplier<T>` directly, do not expect `timeoutDuration` to interrupt an operation blocking the thread on its own. Configure timeouts on the HTTP client, database driver, or respective client library. TimeLimiter fits asynchronous/reactive execution models supported by the integration, such as `CompletionStage` or publishers; you still need to verify actual task cancellation because the underlying client may not immediately stop work when the future is cancelled.

## configs profiles and baseConfig

Resilience4j allows defining reusable profiles under `configs`. Each instance declared under `instances` can inherit a profile via `baseConfig`, then override only the properties it needs separately.

For example, two Circuit Breakers sharing a basic statistics policy but having different failure thresholds:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remote-default:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallRateThreshold: 60
        slowCallDurationThreshold: 1s
        waitDurationInOpenState: 8s
        permittedNumberOfCallsInHalfOpenState: 3
    instances:
      catalog-read:
        baseConfig: remote-default
      inventory-read:
        baseConfig: remote-default
        failureRateThreshold: 40
```

`remote-default` is a configuration profile name, not an ID passed to the factory. `catalog-read` and `inventory-read` are instance IDs. Both inherit shared values from the profile, but `inventory-read` overrides `failureRateThreshold` to 40%.

You can create multiple profiles for different dependency groups:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      remote-default:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-strict:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
    instances:
      catalog-read:
        baseConfig: remote-default
      inventory-read:
        baseConfig: remote-default
      payment-authorize:
        baseConfig: payment-strict
```

Instances remain independent even when inheriting the same profile. `baseConfig` reuses configuration values; it does not merge runtime state, statistics windows, or metrics across IDs.

## Configuring TimeLimiter by groupName

TimeLimiter has its own profiles and instances under the `resilience4j.timelimiter` namespace. When calling `create(id, groupName)`, the Resilience4j integration uses the first ID for the Circuit Breaker and the group name for the TimeLimiter.

```yaml
resilience4j:
  timelimiter:
    configs:
      timeout-default:
        timeoutDuration: 2s
        cancelRunningFuture: true
    instances:
      slow-remote:
        baseConfig: timeout-default
        timeoutDuration: 4s
      fast-remote:
        baseConfig: timeout-default
        timeoutDuration: 800ms
```

In this example, every call using the `slow-remote` group can inherit the four-second limit; the `fast-remote` group uses 800 milliseconds. This is TimeLimiter configuration. It does not cause Circuit Breakers in the same group to share failure rates or state.

Combining the two configuration sections:

```java
CircuitBreaker catalogBreaker = factory.create("catalog-read", "slow-remote");
CircuitBreaker inventoryBreaker = factory.create("inventory-read", "slow-remote");
CircuitBreaker paymentBreaker = factory.create("payment-authorize", "fast-remote");
```

| Factory call | Circuit Breaker configuration | TimeLimiter configuration |
|---|---|---|
| `create("catalog-read", "slow-remote")` | `circuitbreaker.instances.catalog-read` | `timelimiter.instances.slow-remote` |
| `create("inventory-read", "slow-remote")` | `circuitbreaker.instances.inventory-read` | `timelimiter.instances.slow-remote` |
| `create("payment-authorize", "fast-remote")` | `circuitbreaker.instances.payment-authorize` | `timelimiter.instances.fast-remote` |

This table describes how the Resilience4j integration maps ID and group name. Check your starter and version in use to confirm the corresponding factory overload is available and TimeLimiter properties bind as expected.

## Distinguishing groupName from baseConfig through a scenario

Suppose a system has three dependencies:

- Catalog responds slowly, needing a four-second timeout.
- Inventory also responds slowly, needing the same four-second timeout but a separate failure threshold.
- Payment must respond quickly, needing an 800-millisecond timeout and a stricter failure threshold.

We can configure it as follows:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      slow-dependency:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
      payment-dependency:
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 30
    instances:
      catalog-read:
        baseConfig: slow-dependency
      inventory-read:
        baseConfig: slow-dependency
        failureRateThreshold: 40
      payment-authorize:
        baseConfig: payment-dependency
  timelimiter:
    configs:
      timeout-default:
        timeoutDuration: 2s
    instances:
      slow-remote:
        baseConfig: timeout-default
        timeoutDuration: 4s
      fast-remote:
        baseConfig: timeout-default
        timeoutDuration: 800ms
```

And the calling code:

```java
CircuitBreaker catalog = factory.create("catalog-read", "slow-remote");
CircuitBreaker inventory = factory.create("inventory-read", "slow-remote");
CircuitBreaker payment = factory.create("payment-authorize", "fast-remote");
```

Design outcome:

- Catalog and inventory share the `slow-dependency` profile as the baseline for their Circuit Breakers, while still having separate instances. Inventory overrides the failure threshold.
- Catalog and inventory share the `slow-remote` group, thus using the same TimeLimiter configuration.
- Payment uses the `payment-dependency` Circuit Breaker profile and the `fast-remote` TimeLimiter group.
- No Circuit Breaker state is shared simply because two calls use the same `baseConfig` or the same `groupName`.

## Points to check when configuring

**Names must match:** The ID in `factory.create` must match the Circuit Breaker instance name in YAML. The group name must match the TimeLimiter instance key looked up by the integration. A single character mismatch can cause custom configuration not to be applied and the application to fall back to default settings.

**Profile must exist:** `baseConfig` must point to a profile in the right namespace. Circuit Breaker profiles live under `resilience4j.circuitbreaker.configs`; TimeLimiter profiles live under `resilience4j.timelimiter.configs`. Do not use a Circuit Breaker profile as `baseConfig` for a TimeLimiter.

**Do not confuse profile with instance:** `configs` is where reusable values are defined; `instances` is where configuration for concrete names used at runtime is defined. A profile name does not create a Circuit Breaker on its own.

**Understand timeout scope:** TimeLimiter bounds wait time in the ways the integration supports. It does not replace HTTP client connection or response timeouts in all cases. Coordinate deadlines and test task cancellation, especially for reactive calls.

**Do not create per-request IDs:** use stable IDs per dependency or operations sharing a failure boundary. Request data belongs in logs/traces, not in Circuit Breaker instance names.

**Verify effective configuration:** when multiple configuration sources exist such as YAML and `Customizer`, determine which source takes effect according to the integration version. Avoid declaring the same property in multiple places with conflicting values; when overrides are needed, verify through tests or runtime observation.

## Tracking IDs and groups in operations

The Circuit Breaker ID is a crucial label for distinguishing the state and metrics of each dependency. With Resilience4j and Micrometer, metrics typically carry a `name` tag corresponding to the Circuit Breaker instance. The TimeLimiter group should not be treated as a Circuit Breaker state label; it describes the timeout configuration group selected for the call.

When investigating a dependency, cross-reference:

- The Circuit Breaker ID appearing in metrics and logs.
- The `baseConfig` profile inherited by the instance and any overridden properties.
- The group name passed to the factory.
- The TimeLimiter instance configuration that the group name maps to.
- Actual call duration, timeouts, recorded errors, and fallback results.

If multiple IDs share a TimeLimiter group, dashboards still need to separate Circuit Breaker metrics by each ID. Sharing a timeout does not mean they share the same failure rate or health status.

## Practice verifying the mapping

Run in a test environment with three mock endpoints having different latencies:

1. Create two Circuit Breakers `catalog-read` and `inventory-read` sharing the `slow-remote` group; create `payment-authorize` using the `fast-remote` group.
2. Declare three Circuit Breaker instances and two corresponding TimeLimiter instances in YAML; have the instances inherit the appropriate `baseConfig` profiles.
3. Send successful requests to all three dependencies and observe metrics per ID.
4. Make catalog return continuous errors so the `catalog-read` circuit transitions to `OPEN`; confirm `inventory-read` still retains its own state despite sharing the timeout group.
5. Make inventory respond slower than four seconds and payment respond slower than 800 milliseconds; confirm each group's TimeLimiter is applied as configured.
6. Change inventory's own failure threshold while keeping `baseConfig` and group unchanged; observe the Circuit Breaker decision change while the timeout stays the same.
7. Switch payment's group to `slow-remote` in the test environment; confirm the selected timeout changes while the Circuit Breaker ID remains `payment-authorize`.

Record the ID, group, profile, response duration, outcome, and state for each test run. If the timeout does not match, check the group name, TimeLimiter instance configuration, and integration version before changing Circuit Breaker thresholds.

## Common mistakes

- **Assuming groupName is the Circuit Breaker ID:** in the Resilience4j integration, the first ID identifies the Circuit Breaker; group name is used to select TimeLimiter configuration.
- **Assuming groupName shares state:** different Circuit Breaker IDs still have separate state and metrics.
- **Using a profile name as a runtime ID:** profiles in `configs` only provide base values; an instance must be created with the matching ID.
- **Confusing `baseConfig` with groupName:** `baseConfig` is a YAML configuration inheritance mechanism; groupName is a parameter when calling the factory.
- **Using the same ID for independent dependencies:** an outage in one dependency can affect decisions of the shared circuit breaker.
- **Creating dynamic per-request IDs:** creates many instances and fragments metrics.
- **Using the wrong namespace:** Circuit Breaker and TimeLimiter profiles must sit in their respective configuration sections.
- **Assuming every implementation uses groupName identically:** the mapping described here applies to the Resilience4j integration; verify other implementations before switching.

Use the ID to identify each Circuit Breaker that needs to be observed and have isolated state. Use the Resilience4j integration's `groupName` when you want to select TimeLimiter configuration for a group of calls. Use `configs` and `baseConfig` to reuse properties in YAML. These three mechanisms work together without replacing one another.
