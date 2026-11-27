# Reading Configuration, State, and Statistics Snapshots

Resilience4j manages Circuit Breakers through `CircuitBreakerRegistry`. The registry lets the application find already created circuits, inspect registered shared configurations, and receive events when a circuit is added or replaced. Each Circuit Breaker in turn provides its runtime state and sliding window metrics. When combining with Spring Cloud CircuitBreaker, distinguish Resilience4j's registry from the factory abstraction used by Feign or services so you do not inspect the wrong circuit.

The three groups of information to observe have different meanings:

- **Configuration:** the policy applied when the Circuit Breaker is created, such as sliding window size, failure threshold, slow call threshold, and wait duration in `OPEN`.
- **State:** the current runtime state `CLOSED`, `OPEN`, `HALF_OPEN`, or special states such as `DISABLED` and `FORCED_OPEN`.
- **Statistics snapshot:** the number of samples in the window, successful/failed call counts, slow call count, rejected call count, and current rates.

Reading each group separately helps answer the right operational questions: how the circuit is configured, whether it currently permits calls, and what data caused it to transition states.

## What Does the Registry Manage?

`CircuitBreakerRegistry` is where Resilience4j creates and looks up instances by name. Each instance has its own state, event publisher, and metrics. Instances with the same name in the same registry are shared, allowing calls to the same dependency to share a single sliding window and decide together when to open the circuit.

In a Spring Boot application integrated with Resilience4j, you can inject the registry provided by auto-configuration:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Component;

@Component
class CircuitBreakerRegistryAccess {

    private final CircuitBreakerRegistry registry;

    CircuitBreakerRegistryAccess(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }
}
```

Do not manually create a new `CircuitBreakerRegistry.ofDefaults()` just to read state if the application already has a configured registry. A new registry is a separate management domain; circuits inside it do not automatically reflect calls protected by the Spring Cloud CircuitBreaker factory.

One thing to note: `registry.circuitBreaker("catalog")` is a get-or-create operation. If the name does not exist yet, this call can create a new Circuit Breaker with the default configuration. When you only want to inspect active instances, iterate over `getAllCircuitBreakers()` and search by name:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

CircuitBreaker findExisting(String name) {
    return registry.getAllCircuitBreakers().stream()
        .filter(circuitBreaker -> circuitBreaker.getName().equals(name))
        .findFirst()
        .orElse(null);
}
```

If the result is `null`, the registry being inspected does not contain that instance. Do not call `circuitBreaker(name)` in monitoring code and mask this signal; first verify the name and the registry actually used by the factory.

## Reading Default and Shared Configurations

The registry provides the default configuration and registered shared configurations. You can read them using `getDefaultConfig()` and `getAllConfigurations()`:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

void logRegisteredConfigurations() {
    CircuitBreakerConfig defaults = registry.getDefaultConfig();
    log.info("Default Circuit Breaker: windowType={}, windowSize={}, minimumCalls={}, "
            + "failureThreshold={}%, slowThreshold={}%, slowDuration={}",
        defaults.getSlidingWindowType(),
        defaults.getSlidingWindowSize(),
        defaults.getMinimumNumberOfCalls(),
        defaults.getFailureRateThreshold(),
        defaults.getSlowCallRateThreshold(),
        defaults.getSlowCallDurationThreshold());

    registry.getAllConfigurations().forEach((name, config) ->
        log.info("Shared config {}: windowType={}, windowSize={}, minimumCalls={}",
            name,
            config.getSlidingWindowType(),
            config.getSlidingWindowSize(),
            config.getMinimumNumberOfCalls()));
}
```

You can query a shared configuration by name using `registry.getConfiguration("sharedProfile")`. This value is the configuration registered under that profile name. Do not assume an instance name `catalog` is also the shared configuration name `catalog`; the two concepts can differ.

Example properties declaring an instance and a shared config:

```yaml
resilience4j:
  circuitbreaker:
    configs:
      backendDefault:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
    instances:
      catalog:
        baseConfig: backendDefault
        waitDurationInOpenState: 5s
        permittedNumberOfCallsInHalfOpenState: 3
```

In this example, `backendDefault` is the shared configuration; `catalog` is an instance using that base configuration and adding its own overrides. When investigating effective configuration, inspect the shared profile, instance properties, and any customizers applied in the application.

### Distinguishing Registry Configuration from Factory Effective Configuration

Spring Cloud CircuitBreaker creates wrappers through `Resilience4JCircuitBreakerFactory` or the reactive factory. A registry only reflects the instances managed by that registry itself. If an application has multiple registries or customizers creating separate configurations for the factory, injecting an arbitrary registry does not guarantee reading the exact instance used by Feign or a service.

Additionally, the registry API lets you read default and named shared configurations, but `getConfiguration("catalog")` should not be treated as a guaranteed copy of all effective values on the `catalog` instance. For instance-specific configuration, verify the configuration source loaded by the application, the actual Circuit Breaker name, and the customizers applied when creating the circuit. In Spring Cloud CircuitBreaker, property-based configuration takes higher precedence than a Java `Customizer`; therefore, a customizer will not necessarily override values declared in `application.yml`.

A practical approach is to log the selected configuration right where the instance or customizer is created. Log only the properties needed for operations, avoiding predicates, internal objects, or data that could contain sensitive information.

## Reading Runtime State

After finding an existing instance, call `getState()` to read its state:

```java
CircuitBreaker circuitBreaker = findExisting("catalog");
if (circuitBreaker == null) {
    log.warn("Circuit Breaker catalog not found in this registry");
    return;
}

log.info("Circuit Breaker {} is in state {}",
    circuitBreaker.getName(), circuitBreaker.getState());
```

Common states:

| State | Meaning | Behavior on New Calls |
|---|---|---|
| `CLOSED` | Circuit is tracking outcomes in the sliding window | Permits calls and records outcomes |
| `OPEN` | Circuit is blocking calls because protection conditions were breached | Fails fast, typically throwing `CallNotPermittedException` |
| `HALF_OPEN` | Circuit is probing recovery capability | Grants permission only for the configured number of trial calls |
| `DISABLED` | Protection mechanism is disabled | Does not apply normal threshold blocking |
| `FORCED_OPEN` | Circuit was forced open by an administrative action | Rejects calls until the state is changed |

`getState()` is a snapshot of the state at the moment of reading. Another request can cause the state to change immediately afterward. Therefore, do not use the read state as a synchronization lock to decide whether to call the dependency; let the Circuit Breaker itself perform the permission check.

## Reading the Sliding Window Statistics Snapshot

`getMetrics()` returns the Circuit Breaker's metrics. Useful metrics include the number of buffered samples, successful, failed, and not-permitted calls, slow calls, and failure/slow call rates:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;

void logSnapshot(CircuitBreaker circuitBreaker) {
    CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

    int buffered = metrics.getNumberOfBufferedCalls();
    int successful = metrics.getNumberOfSuccessfulCalls();
    int failed = metrics.getNumberOfFailedCalls();
    int notPermitted = metrics.getNumberOfNotPermittedCalls();
    int slow = metrics.getNumberOfSlowCalls();
    float failureRate = metrics.getFailureRate();
    float slowCallRate = metrics.getSlowCallRate();

    log.info("CircuitBreaker {}: state={}, buffered={}, success={}, failed={}, "
            + "notPermitted={}, slow={}, failureRate={}%, slowCallRate={}%",
        circuitBreaker.getName(),
        circuitBreaker.getState(),
        buffered,
        successful,
        failed,
        notPermitted,
        slow,
        failureRate,
        slowCallRate);
}
```

`getNumberOfBufferedCalls()` reflects the number of outcomes currently held in the statistics window. `getNumberOfNotPermittedCalls()` is the number of rejected calls; rejected calls are not success or failure samples in the sliding window. Ignored calls also do not contribute to the success/failure rate.

When `minimumNumberOfCalls` has not been reached, the failure rate or slow call rate can return `-1.0`, indicating insufficient samples to compute the rate. Do not display this value as `-1%` failure; dashboards should represent it as "insufficient samples". Once enough samples are collected, rates are expressed as percentages from 0 to 100.

Because the getters are read sequentially, the snapshot in the log is a near-contemporaneous capture rather than an atomic transaction. In an environment with concurrent requests, metrics can change between reads. If you need a time-series view, record samples periodically or use Micrometer metrics instead of trying to reconstruct full history from a single snapshot.

## Creating a Snapshot DTO for an Admin Page

Do not return Resilience4j objects directly from a REST API. Map the required values into a stable DTO so the API does not depend on the library's internal structure:

```java
public record CircuitBreakerSnapshot(
    String name,
    String state,
    int bufferedCalls,
    int successfulCalls,
    int failedCalls,
    int notPermittedCalls,
    int slowCalls,
    float failureRate,
    float slowCallRate
) {}
```

```java
CircuitBreakerSnapshot snapshot(String name) {
    CircuitBreaker circuitBreaker = findExisting(name);
    if (circuitBreaker == null) {
        throw new IllegalArgumentException(
            "Circuit Breaker not found: " + name);
    }

    CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();
    return new CircuitBreakerSnapshot(
        circuitBreaker.getName(),
        circuitBreaker.getState().name(),
        metrics.getNumberOfBufferedCalls(),
        metrics.getNumberOfSuccessfulCalls(),
        metrics.getNumberOfFailedCalls(),
        metrics.getNumberOfNotPermittedCalls(),
        metrics.getNumberOfSlowCalls(),
        metrics.getFailureRate(),
        metrics.getSlowCallRate());
}
```

Administrative endpoints should only grant read access to authorized operators. Do not allow external clients to access the registry directly or pass arbitrary names that create new instances. You can list existing names using `getAllCircuitBreakers()` and return only selected fields in the DTO.

## Tracking Registry and State Changes with Events

A snapshot shows the state at the time of reading; events tell you what happened between two reads. The registry event publisher emits notifications when an instance is added, removed, or replaced:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class CircuitBreakerRegistryEvents {

    @Bean
    ApplicationRunner registerRegistryEvents(CircuitBreakerRegistry registry) {
        return args -> registry.getEventPublisher()
            .onEntryAdded(event -> log.info(
                "Registry added Circuit Breaker {}",
                event.getAddedEntry().getName()))
            .onEntryRemoved(event -> log.info(
                "Registry removed Circuit Breaker {}",
                event.getRemovedEntry().getName()))
            .onEntryReplaced(event -> log.info(
                "Registry replaced Circuit Breaker {}",
                event.getNewEntry().getName()));
    }
}
```

At the individual Circuit Breaker level, the event publisher can track state transitions, call outcomes, and rejected calls:

```java
void registerCircuitBreakerEvents(CircuitBreaker circuitBreaker) {
    circuitBreaker.getEventPublisher()
        .onStateTransition(event -> log.info(
            "{} transitioned state: {}",
            event.getCircuitBreakerName(),
            event.getStateTransition()))
        .onSuccess(event -> log.debug(
            "{} recorded successful call",
            event.getCircuitBreakerName()))
        .onError(event -> log.warn(
            "{} recorded error: {}",
            event.getCircuitBreakerName(),
            event.getThrowable().toString()))
        .onCallNotPermitted(event -> log.debug(
            "{} rejected call",
            event.getCircuitBreakerName()));
}
```

Register listeners once when an instance is created or when the registry emits `onEntryAdded`; do not re-register listeners on every request. Callbacks should be short and must not block the execution thread. If events need to be forwarded to another system, offload them to an appropriate queue or asynchronous handler. Do not log full payloads or credentials contained in exceptions.

## Observing with Actuator and Micrometer

In production, dashboards should use metrics to track trends and use the health endpoint to check overall status. With Spring Boot Actuator, you can expose the necessary endpoints:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics,prometheus
```

The Resilience4j Micrometer integration exports metrics for call counts by outcome type, Circuit Breaker state, and related rates. Exact metric names and tags can vary across versions, so inspect the actual metric list via `/actuator/metrics` or the Prometheus scrape endpoint rather than hard-coding names based on a different version.

Key metrics to observe include:

- Successful, failed, and rejected call counts.
- Current Circuit Breaker state.
- Failure rate and slow call rate.
- Number of calls currently buffered in the sliding window.
- Number of state transitions and how frequently the circuit oscillates between `CLOSED` and `OPEN`.

The Circuit Breaker health indicator may treat the `OPEN` state as `DOWN`, depending on configuration and integration version. If this status is wired into Kubernetes readiness/liveness probes without careful consideration, a single failing dependency could cause the entire application instance to be marked unready and trigger further cascading effects. Decide separately whether an `OPEN` Circuit Breaker should remove application readiness or serve strictly as an operational signal for a dependency.

## Example of Reading and Interpreting a Snapshot

Suppose a dashboard displays:

| Metric | Value |
|---|---:|
| State | `OPEN` |
| Buffered calls | 20 |
| Successful calls | 8 |
| Failed calls | 12 |
| Not permitted calls | 37 |
| Slow calls | 10 |
| Failure rate | 60% |
| Slow call rate | 50% |

In this example, the sliding window holds 20 samples and 12 of them failed, so the failure rate is 60%. There are 37 calls rejected after the circuit opened; they do not increase the sample count in the window. The 10 slow calls represent a separate measurement; a slow call can also be a failed call depending on its outcome and classification policy. Therefore, do not add `slow calls` to `failed calls` to infer the total number of calls.

If configured with `failureRateThreshold: 50`, the 60% rate explains why the circuit could transition to `OPEN`, provided the minimum number of calls was met. While the circuit is `OPEN`, seeing `notPermitted` continue to rise on the dashboard is normal: new requests are failing fast. After `waitDurationInOpenState`, the circuit can transition to `HALF_OPEN` and allow a limited number of probes. Subsequent snapshots should be read alongside state transition events to understand the sequence of events.

## Common Confusions

- **Reading the wrong registry:** injecting a newly created registry or one not used by the factory, causing real instances not to appear.
- **Accidentally creating an instance when only intending to read:** calling `registry.circuitBreaker(name)` for a nonexistent name can create a new circuit with the default configuration.
- **Confusing named config with instance config:** `getConfiguration(name)` queries the configuration registered under that name; a name matching an instance is not guaranteed to be that instance's effective configuration.
- **Treating state as history:** `getState()` only returns the current state; use events or time-series metrics to view progression over time.
- **Treating rejected calls as failures in the window:** `not permitted` is a separate metric, not a success/failure sample in the sliding window.
- **Interpreting `-1` as a negative rate:** failure/slow rates can be `-1` when the minimum number of samples has not been met.
- **Reading a snapshot as atomic data:** getters are read sequentially while the system may continue processing requests.
- **Using health status as a substitute for dashboards:** `OPEN` can affect the health indicator; carefully consider the impact on readiness and instance orchestration.

When investigating a Circuit Breaker, identify the right registry and instance name first, inspect the default and shared configurations, confirm the source of instance-specific settings, and then read the state and metrics. Combining snapshots with events and time-series metrics shows what state the circuit is in, why it transitioned, and whether the dependency has recovered enough to accept probes.
