# Dry-Running in Observe-Only Mode When Supported by the Implementation

Before enabling a circuit breaker to block real calls, operations teams may want to observe how the planned policy would react to current traffic. With the Resilience4j implementation, there is a special state called `METRICS_ONLY`: the breaker still lets calls pass through and records outcomes, but it does not transition to `OPEN` to reject subsequent calls when the failure rate or slow-call rate exceeds thresholds.

This mode is useful when rolling out a policy for the first time, tuning `minimumNumberOfCalls`, `failureRateThreshold`, or `slowCallRateThreshold`, and estimating expected fallback rates before enabling protection. However, this is an observation mode on **live traffic**: requests are still sent to the dependency and can still time out or fail. `METRICS_ONLY` is not a simulation environment, does not mirror traffic, and does not protect the backend from overload.

## 1. How Does `METRICS_ONLY` Work?

In the normal `CLOSED` state, Resilience4j allows the supplier to execute, records the result in the sliding window, and can transition to `OPEN` once enough samples have accumulated and configured thresholds are exceeded. When `OPEN`, the breaker rejects new calls. Once the wait duration expires, the breaker transitions to `HALF_OPEN` to probe recovery.

In `METRICS_ONLY`, calls are still permitted to execute and success/error outcomes are still recorded. The breaker does not open the circuit to block calls based on failure rate or slow-call rate. This enables observing errors and latency without altering traffic flow through circuit-opening decisions.

| State | Permits Calls? | Records Outcomes? | Can Auto-Transition to `OPEN` by Threshold? |
|---|---|---|---|
| `CLOSED` | Yes | Yes | Yes |
| `OPEN` | No, calls are rejected | Records not-permitted events | Already open |
| `HALF_OPEN` | Limited by probe count | Yes | Can return to `OPEN` if probes fail |
| `METRICS_ONLY` | Yes | Yes | No |
| `DISABLED` | Yes | Does not record breaker metrics/events as observe mode does | No |
| `FORCED_OPEN` | No | Does not evaluate supplier calls | Does not wait for thresholds |

The key difference between `METRICS_ONLY` and `DISABLED` is that observe-only mode still records successes, failures, and execution durations. `DISABLED` bypasses the breaker's recording mechanism. Therefore, if the goal is to evaluate thresholds before enabling protection, `METRICS_ONLY` is more suitable than `DISABLED`.

## 2. This Is an Implementation Capability, Not a Common Contract

Spring Cloud CircuitBreaker provides abstractions such as `CircuitBreakerFactory` and `ReactiveCircuitBreakerFactory`. The common contract lets applications invoke calls through a breaker without depending directly on the underlying library, but it does not guarantee that every implementation has a `METRICS_ONLY` state or corresponding state-transition API.

Resilience4j supports this state through the native `io.github.resilience4j.circuitbreaker.CircuitBreaker` API via the `transitionToMetricsOnlyState()` method. To use it, the application needs access to the exact `CircuitBreakerRegistry` managing the instance protecting the call. If the project uses a different implementation, consult that implementation's documentation; do not assume the same method exists or that a single YAML property works across all implementations.

With Spring Boot's Resilience4j integration, the registry is normally auto-configured and can be injected as a bean. Do not create a new registry arbitrarily in a gateway, because a breaker retrieved from a new registry may not be the instance used by Spring Cloud/OpenFeign. Verify that the factory, Feign integration, and state-transition code use the corresponding registry/instance.

## 3. Threshold Configuration Is Still Needed in Observe Mode

`METRICS_ONLY` does not replace sliding window configuration. Parameters such as `slidingWindowType`, `slidingWindowSize`, `minimumNumberOfCalls`, `failureRateThreshold`, `slowCallDurationThreshold`, and `slowCallRateThreshold` still determine how statistics are recorded and evaluated. They represent the intended policy that will take effect when the breaker switches back to normal protection mode.

Example configuration for an inventory dependency:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 100
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
```

In this example, the planned policy opens the breaker if at least 20 samples are recorded and the failure rate reaches 40%, or the slow-call rate reaches 50% as configured. While in `METRICS_ONLY`, metrics are still collected so operations can see how often those conditions occur; the breaker does not reject traffic just because thresholds are exceeded.

Do not invent a property like `mode: METRICS_ONLY` in YAML if the Spring Cloud/Resilience4j version in use does not define it. The transition approach shown below uses Resilience4j's native API. Spring Boot configuration properties and runtime APIs should be checked against the exact dependency version in your project.

## 4. Transitioning the Breaker to METRICS_ONLY at Application Startup

With Resilience4j, an instance can be switched to `METRICS_ONLY` using `transitionToMetricsOnlyState()`. The following example uses a dedicated profile to enable observe-only mode only when that profile is active:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import org.springframework.boot.ApplicationRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("observe-circuit-breaker")
public class CircuitBreakerObservationConfiguration {

    @Bean
    ApplicationRunner inventoryMetricsOnly(CircuitBreakerRegistry registry) {
        return args -> {
            CircuitBreaker breaker = registry.circuitBreaker("inventory");
            breaker.transitionToMetricsOnlyState();
        };
    }
}
```

When the application runs with the `observe-circuit-breaker` profile, the bean fetches the `inventory` instance from the registry and transitions it to `METRICS_ONLY`. Using a profile is an example deployment structure; ensure the ID `inventory` is the actual ID of the protected call.

If a breaker is created by the Spring Cloud CircuitBreaker factory or OpenFeign, confirm that the registry injected here is the same registry used by that integration. If names are generated by a `CircuitBreakerNameResolver`, use the actual runtime name rather than guessing from `@FeignClient(name = ...)`.

Do not transition state on every request. State transition is a breaker lifecycle management operation; repeating it can reset or alter statistics depending on the implementation's semantics. Place the transition in a controlled initialization phase or a protected administrative mechanism.

## 5. Verify the Actual Mode Before Trusting Dashboards

After transitioning state, confirm that the breaker is genuinely in `METRICS_ONLY`. You can read the state via the native API:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

if (breaker.getState() != CircuitBreaker.State.METRICS_ONLY) {
    throw new IllegalStateException(
            "Inventory circuit breaker is not in METRICS_ONLY mode");
}
```

Verifying the state is especially important when the application has multiple registries, multiple Feign clients, or auto-generated breaker names. If a dashboard displays metrics for a different instance than the one protecting traffic, conclusions drawn during observation will be wrong.

In addition to state, verify:

- The breaker ID actually used by the gateway or Feign client.
- That the registry injected into management code shares the same instance with the active integration.
- That success/error metrics for that exact ID increment as requests arrive.
- That requests still reach the dependency while the breaker is in `METRICS_ONLY`, even when the failure rate exceeds the threshold.
- That no other breaker in `OPEN` state sits outside or inside the same call path blocking traffic.

## 6. Testing That the Breaker Still Permits Calls After Exceeding Thresholds

A small test can verify the core property of `METRICS_ONLY`: failures are recorded, yet the breaker does not open and subsequent calls still execute.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class MetricsOnlyCircuitBreakerTest {

    @Test
    void recordsFailuresButContinuesToPermitCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(2)
                .failureRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(10))
                .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory-observe", config);
        breaker.transitionToMetricsOnlyState();

        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("dependency failed");
                }));

        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("dependency failed again");
                }));

        AtomicInteger executions = new AtomicInteger();
        String result = breaker.executeSupplier(() -> {
            executions.incrementAndGet();
            return "still-permitted";
        });

        assertEquals(CircuitBreaker.State.METRICS_ONLY, breaker.getState());
        assertEquals(2, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(1, breaker.getMetrics().getNumberOfSuccessfulCalls());
        assertEquals(1, executions.get());
        assertEquals("still-permitted", result);
    }
}
```

This test generates enough samples for the failure rate to exceed the 50% threshold, yet the breaker stays in `METRICS_ONLY`. The third call still runs and returns normally. When testing in a project, use a Resilience4j version that supports this state and ensure metric assertions match the API of the managed version.

## 7. Reading Metrics During Observe-Only Operation

While running `METRICS_ONLY`, dashboards should focus on metrics that help decide whether to turn on enforcement:

- Count of successful, failed, and ignored calls by breaker ID.
- Failure rate and slow-call rate along with buffered sample count.
- p50, p95, and p99 latencies from the HTTP client or tracing.
- Exception classes and cause chains, distinguishing timeouts, connection refused, DNS errors, HTTP 5xx, and business errors.
- Actual requests sent to the backend, compared with supplier execution counts.
- Fallback rate if the application still triggers fallbacks on real exceptions.
- Breaker state per replica and process startup timestamp.

With Micrometer/Actuator, Resilience4j can export metrics under `resilience4j.circuitbreaker`. A common meter is `resilience4j.circuitbreaker.calls`, tagged by `kind` such as `successful`, `failed`, `ignored`, or `not_permitted`. In `METRICS_ONLY`, the main expectation is that successes/errors continue being recorded and calls are not rejected by the breaker due to thresholds. Exact meter/tag names depend on the Micrometer version and exporter, so inspect the live metrics endpoint.

The failure rate metric is only meaningful alongside `minimumNumberOfCalls`. If sample count is insufficient, the failure rate value may be undefined. Do not conclude a policy is safe based solely on a low-traffic period or a dashboard without enough samples.

## 8. Comparing Observed Metrics with Planned Enforcement Decisions

During observation, the breaker does not open, so there are no `not_permitted` rejections caused by the `METRICS_ONLY` instance exceeding thresholds. To forecast the impact of enabling enforcement, use the collected sample counts and rates to estimate when the breaker would open, then examine how many requests would be blocked and whether fallbacks satisfy business needs.

| Observation in `METRICS_ONLY` | Question Before Enabling Enforcement |
|---|---|
| Failure rate frequently exceeds threshold | Is the threshold too low, or is the dependency genuinely unstable? |
| High slow-call rate but low failure rate | Do the timeout and slow-call threshold reflect the SLO? |
| Many DNS or connection refused errors | Should service discovery/network issues be fixed before enabling the breaker? |
| Many business errors counted as failed | Are `recordExceptions`/`ignoreExceptions` classifying errors properly? |
| Low traffic, rarely reaches minimum samples | Should failure domains be consolidated or window/minimum calls adjusted? |
| Fallback frequently returns unknown/unavailable data | Do upstream APIs and user experience handle that state? |
| Some replicas show different failure rates | Is there a node-, zone-, or network-path-specific issue? |

Do not observe a failure rate over a short window and immediately enable enforcement. Observe across peak hours, off-peak hours, rollouts, load changes, and varying network conditions. For low-traffic dependencies, a longer observation period may be required to gather representative samples.

## 9. `METRICS_ONLY` Does Not Replace Timeouts, Bulkheads, or Rate Limiters

Because `METRICS_ONLY` always lets calls pass through, it does not stop requests from continuing to hit a slow or failing backend. If a dependency holds connections open for a long time, in-flight request counts can still climb, thread/connection pools can still exhaust, and failures can still cascade to the calling service.

During observation, keep independent safeguards active:

- **Connect/read/response timeouts:** limit wait durations at the HTTP client.
- **Overall deadline:** bound total duration for an entire request spanning multiple dependencies.
- **Bulkhead:** limit concurrent tasks and protect thread/connection pools.
- **Rate limiter or gateway quota:** cap traffic if the backend has finite capacity.
- **Bounded retries:** avoid amplifying load via retries while a dependency is degraded.
- **Fallback:** provide a meaningful response when the supplier actually fails; fallbacks do not stop the initial call.

Do not put an already overloaded dependency into `METRICS_ONLY` unless appropriate timeout/concurrency limits are in place and the backend can handle ongoing requests. The purpose of this mode is to observe a policy under safe operating conditions, not to turn off all protections.

## 10. Fallbacks Can Still Run When the Supplier Actually Fails

`METRICS_ONLY` does not block calls due to breaker thresholds, yet the supplier can still throw exceptions. If the application uses `CircuitBreaker.run` with a fallback or a Feign fallback, genuine errors can still route to the fallback depending on the integration in use.

Example:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        error -> InventoryView.unavailable(sku)
);
```

In observe mode, when the supplier succeeds, the breaker records a success. When the supplier throws a timeout, the breaker records a failure and the fallback can return `unavailable`. When the next request arrives, the breaker still allows the supplier to run even if the failure rate has crossed the threshold. Thus, the fallback still handles real errors without being triggered merely because the breaker is open, since the breaker never transitions to `OPEN` by threshold in `METRICS_ONLY`.

This helps measure error rates and expected fallback rates while traffic continues flowing. However, fallbacks must not be used to hide every exception. Keep logs, traces, and metrics categorized by root cause, and return honest business states instead of turning unknown data into fake success responses.

## 11. Transitioning from Observation to Active Protection

After collecting sufficient data and confirming appropriate thresholds, transition the breaker back to normal operation. With the Resilience4j native API, `transitionToClosedState()` can switch the instance to `CLOSED`:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

if (breaker.getState() == CircuitBreaker.State.METRICS_ONLY) {
    breaker.transitionToClosedState();
}
```

This is a runtime state mutation. Perform it in a controlled manner and verify the reset/statistics semantics of your Resilience4j version; do not assume the sliding window accumulated during observation will be preserved after transitioning. Save or export observation metrics beforehand if comparative analysis is needed.

Before turning on enforcement:

1. Verify the exact breaker ID and registry protecting the traffic.
2. Collect sufficient samples across representative load conditions.
3. Inspect failure/slow-call rates and exception causes.
4. Confirm timeouts, bulkheads, rate limits, and fallbacks are protecting the system.
5. Assess how many requests could be blocked when the breaker opens and the business impact.
6. Choose appropriate `minimumNumberOfCalls`, sliding window, failure threshold, slow-call threshold, and wait duration.
7. Switch a small scope or subset of replicas to enforcement first if deployment processes allow.
8. Monitor `OPEN`, `HALF_OPEN`, `not_permitted`, fallbacks, and backend health after enabling.
9. Have a rollback plan to a safe configuration if the breaker opens too often or blocks critical functionality.

Transitioning to `CLOSED` is not proof that the dependency is healthy. It simply re-enables the state machine under the configured policy. If the backend is still failing, the breaker can quickly open again once enough samples arrive.

## 12. Limitations and Risks of Observe-Only Mode

`METRICS_ONLY` has several limitations that must factor into operational decisions:

- **Does not protect the backend from failing traffic:** all calls are still permitted, even when the failure rate exceeds thresholds.
- **Does not simulate rejection behavior:** the exact `not_permitted` count that would occur in `OPEN` cannot be observed directly; it can only be estimated from traffic and thresholds.
- **Does not mirror traffic:** it observes live requests. Dedicated shadow traffic requires a separate mirroring mechanism whose load impact must be evaluated.
- **State is typically process-local:** each replica may need to be switched to observe mode individually; sharing a name does not synchronize state across JVMs.
- **Metrics may still lack samples:** low traffic or ignored exceptions can keep the window below `minimumNumberOfCalls`.
- **Fallbacks can obscure impact:** maintain dedicated fallback metrics and distinguish supplier outcomes from caller responses.
- **Other implementations may not support it:** Spring Cloud's common API does not guarantee this mode exists across all backends.

If cluster-wide assessment is needed, aggregate metrics by replica and dependency. Do not look at a single pod or breaker instance and conclude a policy is safe for the entire system.

## 13. Testing and Verification Before Rollout

Before enabling observe mode in production, test the behavior with a standalone breaker and then verify Spring integration:

1. Transition the breaker to `METRICS_ONLY` and verify `getState()` returns the expected state.
2. Send successful calls; verify the success counter increments.
3. Send enough failures to exceed the failure rate threshold; verify the failed counter increments without transitioning to `OPEN`.
4. Send additional calls after exceeding the threshold; verify the supplier still executes.
5. Verify the fallback runs when the supplier genuinely throws an exception, but not merely because the threshold was exceeded.
6. Verify metrics/Actuator entries attach to the expected breaker ID.
7. Check each replica after enabling the profile or running the administrative action.
8. Transition back to `CLOSED` in a test environment and verify enforcement works as expected.
9. Verify timeouts, bulkheads, and rate limiters remain active during `METRICS_ONLY`.

Do not only verify that the application starts or that YAML loads. Verify actual state, counters, and supplier execution behavior once the failure rate exceeds the threshold.

## 14. Recommended Operational Workflow

An observe-only trial can be organized as follows:

1. Select a dependency with representative traffic and a stable breaker ID.
2. Declare the planned sliding window, minimum calls, and thresholds.
3. Enable `METRICS_ONLY` using an API supported by the implementation; with Resilience4j, use the native registry and `transitionToMetricsOnlyState()`.
4. Verify that the intended instance transitioned state and metrics are being recorded.
5. Observe successes, failures, ignored calls, latency, fallbacks, and exceptions per dependency across load conditions.
6. Estimate how often the policy would open the circuit, how many requests would be blocked, and the fallback impact.
7. Tune thresholds based on data rather than just the first few errors.
8. Transition to `CLOSED` to enable enforcement under a controlled plan.
9. Monitor state transitions, `not_permitted` rejections, `HALF_OPEN` probes, and SLOs after enabling.

Resilience4j's `METRICS_ONLY` mode makes it possible to observe dependency errors and latency while keeping calls flowing. It is useful for validating policies before enabling an active circuit breaker, yet it does not replace timeouts, bulkheads, or rate limiting and does not protect the backend during incidents. Switch to enforcement only after verifying the right instance, sufficient samples, appropriate thresholds, and fallbacks capable of handling failed or rejected calls.
