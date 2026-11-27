# Manual State Transitions, Reset, and Impact on Statistics

Resilience4j CircuitBreaker transitions automatically based on failure rate, slow-call rate, and its sliding window. In some operational or testing scenarios, an application also needs to explicitly transition a breaker to `OPEN`, `HALF_OPEN`, `CLOSED`, or a special state. These operations change how the breaker permits calls to pass through; they are not the same as clearing statistics.

The key distinction is between **state transitions** and **reset**. Manual state transitions control execution permission for subsequent calls. `reset()` returns the breaker to `CLOSED` and clears accumulated window statistics. Without understanding this difference, a dashboard may continue showing old failure rates after a breaker has closed, or an operations team may accidentally erase statistical evidence when they only meant to reopen service traffic.

## 1. Automatic States vs. Operator-Controlled States

Under normal conditions, the circuit breaker decides on its own:

- `CLOSED`: permits calls, records outcomes, and updates rates.
- `OPEN`: rejects new calls during the open wait duration.
- `HALF_OPEN`: permits a limited number of trial calls to evaluate whether the dependency has recovered.

The typical automatic state transition flow is:

```text
             enough samples and rate exceeds threshold
       CLOSED ----------------------------------------> OPEN
          ^                                              |
          |                                              |
          | good probe results                           | waitDurationInOpenState elapsed
          |                                              v
          +----------------------------------------- HALF_OPEN
                    probe fails or rate exceeds threshold
                                   |
                                   +-----------> OPEN
```

An application may intervene when it needs to isolate a dependency before enough samples are collected, allow a controlled round of probes, close the circuit after verifying an incident is resolved, or reset metrics to start a new observation period. Manual intervention should be a deliberate operational action with an accountable owner and a documented reason.

## 2. Obtaining the Right Instance from CircuitBreakerRegistry

In a Spring Boot application integrated with Resilience4j, the registry manages circuit breakers by name. Components that need to operate on the same breaker must use the exact instance managed by the integration or the same shared registry.

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Service;

@Service
public class CircuitBreakerOperations {

    private final CircuitBreaker inventoryBreaker;

    public CircuitBreakerOperations(CircuitBreakerRegistry registry) {
        this.inventoryBreaker = registry.circuitBreaker("inventory");
    }

    public CircuitBreaker.State currentState() {
        return inventoryBreaker.getState();
    }
}
```

The name `inventory` must match the Resilience4j configuration ID and the ID used by business code. Do not create a new `CircuitBreakerRegistry.ofDefaults()` inside a controller just to control a breaker. An independent registry can create a different instance with the same name whose state and metrics are unrelated to the breaker protecting real requests.

If using the Spring Cloud CircuitBreaker factory, check how to obtain the backend instance for your exact integration version. Do not assume a manually created registry is the registry used by the factory. You can place operational actions in a shared service and inject the right instance-managing bean.

## 3. Manual State Transitions

Resilience4j provides methods on the `CircuitBreaker` object to transition state:

| Method | Target State | Primary Behavior |
| --- | --- | --- |
| `transitionToOpenState()` | `OPEN` | Rejects new calls according to the breaker's open duration mechanism; after the wait duration, the breaker can allow transitioning to `HALF_OPEN` per configuration |
| `transitionToHalfOpenState()` | `HALF_OPEN` | Permits a limited number of probes according to `permittedNumberOfCallsInHalfOpenState` |
| `transitionToClosedState()` | `CLOSED` | Permits calls normally and continues recording statistics |
| `transitionToForcedOpenState()` | `FORCED_OPEN` | Forces the breaker to reject calls until another state transition is triggered |
| `transitionToDisabledState()` | `DISABLED` | Permits calls to pass without applying normal protection mechanisms |
| `transitionToMetricsOnlyState()` | `METRICS_ONLY` | Permits calls while still recording outcomes and metrics for observation |

Example:

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

// Manually open the circuit using the configured wait duration.
breaker.transitionToOpenState();

// When you want to allow a few requests to probe recovery.
breaker.transitionToHalfOpenState();

// After verifying the dependency is stable.
breaker.transitionToClosedState();
```

`transitionToOpenState()` and `transitionToForcedOpenState()` are not the same. `OPEN` is an open state with a wait duration and a transition mechanism to `HALF_OPEN`. `FORCED_OPEN` is a forced rejection mode that remains active until the application or an operator explicitly transitions to another state. Use `FORCED_OPEN` when you need to isolate a dependency by operational decision; use `OPEN` when you want to follow the normal wait-and-probe cycle.

`HALF_OPEN` limits the number of trial calls. Do not transition straight to `CLOSED` just because a single probe succeeded without sufficient evidence that the dependency is stable. Let the configured probes evaluate the outcome or run a controlled verification procedure before closing the circuit.

## 4. Special States: DISABLED, FORCED_OPEN, and METRICS_ONLY

The three special states serve different goals:

| State | New Calls | Statistics and Events | When to Consider |
| --- | --- | --- | --- |
| `DISABLED` | Always permitted | Does not record call metrics as in normal mode | Use only when intentionally bypassing protection, typically in testing or controlled operations |
| `FORCED_OPEN` | Always rejected | Does not record normal call statistics; still tracks state transitions | Emergency isolation of a dependency at risk of causing cascading failures |
| `METRICS_ONLY` | Always permitted | Still records outcomes, metrics, and events, but does not reject calls based on thresholds | Observe thresholds and rates during an evaluation phase before enabling active blocking |

`METRICS_ONLY` is useful when rolling out a new policy. Teams can observe failure rates and slow-call rates under production conditions before letting the circuit breaker reject requests. However, because calls still reach the dependency, this state does not protect the system from increased load or cascading failures. Use it only when both the dependency and the system can handle the load during observation.

`DISABLED` and `FORCED_OPEN` drastically alter behavior, so they should not be toggled through an unauthenticated admin endpoint or an uncontrolled feature flag. Restrict permissions, record audit logs, and have a plan to return to normal state.

## 5. Reset Differs from Transitioning to CLOSED

`reset()` returns the circuit breaker to `CLOSED` and clears the breaker's accumulated metrics, including statistics used to compute failure rate and slow-call rate in the sliding window. This is an operation that starts a fresh observation baseline.

```java
CircuitBreaker breaker = registry.circuitBreaker("inventory");

// Clear accumulated state and statistics, returning the breaker to CLOSED.
breaker.reset();
```

Comparison:

| Operation | State Change | Clears Window Statistics |
| --- | --- | --- |
| `transitionToOpenState()` | Transitions to `OPEN` | Not a statistics reset operation |
| `transitionToHalfOpenState()` | Transitions to `HALF_OPEN` | Not a statistics reset operation |
| `transitionToClosedState()` | Transitions to `CLOSED` | Should not be used to clear metrics |
| `transitionToForcedOpenState()` | Transitions to `FORCED_OPEN` | Not a statistics reset operation |
| `reset()` | Returns to `CLOSED` | Yes, clears accumulated metrics |

When merely transitioning from `OPEN` to `CLOSED`, do not assume dashboards will start from 0. Accumulated numbers may remain to reflect window history. If the goal is to wipe the window clean, use `reset()` and clearly record that a new baseline has begun.

Conversely, do not use `reset()` as a way to "fix" a failing dependency. Resetting reopens the call path and erases statistical evidence; if the dependency has not recovered, new requests can keep failing and trip the breaker open again. When you want to keep a dependency blocked, use `OPEN` or `FORCED_OPEN` appropriately.

## 6. Which Statistics Are Affected?

A circuit breaker aggregates call outcomes within its sliding window. Commonly observed metrics include:

- Number of calls recorded in the window (`numberOfBufferedCalls`).
- Successful and failed call counts.
- Slow call count and failed slow call count.
- `failureRate` and `slowCallRate`.
- Number of calls rejected because the breaker did not permit execution.

Failure rate and slow-call rate only trigger decisions once `minimumNumberOfCalls` is reached. With `COUNT_BASED`, the window evaluates the most recent calls. With `TIME_BASED`, the window evaluates outcomes within the configured time span. On reset, accumulated statistics are cleared; on manual state transitions, permission or rejection behavior changes, but it is not a statistics-history clearing operation.

A call rejected while the breaker is `OPEN` is not a failed dependency call. The supplier did not run, so that rejection must not be added to the dependency's failure rate. Tracking rejected calls separately helps distinguish two issues: whether the dependency received calls and returned errors, or whether the application blocked calls before sending requests.

In special states, recording behavior differs:

- `METRICS_ONLY` still permits requests and records outcomes so rates can be observed.
- `DISABLED` permits requests but does not record call metrics in the normal way.
- `FORCED_OPEN` rejects requests; do not interpret those rejections as the dependency returning more errors.

Therefore, when reading a dashboard, always cross-reference the breaker state with failure rate, slow-call rate, and rejected call counts. An unchanged failure rate while in `FORCED_OPEN` does not mean the dependency has recovered; it simply means no new calls are passing through to update the rate.

## 7. Tracking State Transitions and Resets with Events

Resilience4j's event publisher lets the application listen to a breaker's events. You can record state transitions, errors, successes, rejected calls, and resets:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class CircuitBreakerEventLogger {

    private static final Logger log =
        LoggerFactory.getLogger(CircuitBreakerEventLogger.class);

    public CircuitBreakerEventLogger(CircuitBreakerRegistry registry) {
        CircuitBreaker breaker = registry.circuitBreaker("inventory");

        breaker.getEventPublisher()
            .onStateTransition(event ->
                log.info("Circuit breaker inventory state transition: {}", event))
            .onReset(event ->
                log.info("Circuit breaker inventory was reset: {}", event))
            .onCallNotPermitted(event ->
                log.warn("Circuit breaker inventory rejected a call: {}", event))
            .onError(event ->
                log.warn("Circuit breaker inventory recorded an error: {}", event))
            .onSuccess(event ->
                log.debug("Circuit breaker inventory recorded success: {}", event));
    }
}
```

Event listeners should be registered once during the bean lifecycle, not repeatedly on every request. In real environments, send events to structured logging or a metrics pipeline; never put sensitive payloads, tokens, or personal data in logs. Events help explain why state changed, while metrics show trends over time.

## 8. Safe Operational Procedures

An administrative service can expose explicit actions such as "force open", "allow probe", "close after validation", and "reset statistics". Each action requires:

1. Dedicated authentication and authorization for personnel permitted to control breakers.
2. Operational reason, incident ID, or related ticket.
3. Audit trail including actor, timestamp, breaker ID, and before/after states.
4. Alerts when `DISABLED`, `METRICS_ONLY`, or `FORCED_OPEN` is enabled.
5. A recovery procedure and an owner responsible for closing or resetting.

Do not expose an unauthenticated endpoint allowing arbitrary breaker names and states to be passed in. If using Spring Boot Actuator or an internal API, expose only the strictly needed endpoints, restrict network access, and enforce authorization. Transitioning a breaker to `CLOSED` can send traffic surging back to the dependency immediately; verify recovery readiness before doing so.

Calls that were already permitted before a state transition may still be executing. Transitioning to `OPEN` or `FORCED_OPEN` only affects new calls; it does not cancel in-flight requests. To bound the duration of running requests, configure HTTP/RPC client timeouts or a TimeLimiter suited to your asynchronous model.

## 9. Testing State Transitions and Statistical Impact

Tests should use dedicated instances so state does not leak across tests. Example using the native API:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class CircuitBreakerManualStateTest {

    @Test
    void forcedOpenRejectsCallsAndResetClearsWindowMetrics() {
        CircuitBreaker breaker = CircuitBreaker.of(
            "inventory-test",
            CircuitBreakerConfig.custom()
                .slidingWindowSize(4)
                .minimumNumberOfCalls(2)
                .build()
        );

        breaker.executeRunnable(() -> { });
        assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(1);

        breaker.transitionToForcedOpenState();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.FORCED_OPEN);

        breaker.reset();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isZero();
    }
}
```

The test verifies three points: a successful call is recorded; transitioning to `FORCED_OPEN` changes execution permission; `reset()` returns the breaker to `CLOSED` and clears accumulated call counts. You can add tests to verify that the supplier does not execute in `FORCED_OPEN`, probe counts are capped in `HALF_OPEN`, and `METRICS_ONLY` still records outcomes without rejecting requests.

In Spring Boot integration tests, inject the application-managed registry and retrieve the exact instance ID. Do not create a second registry in tests if the goal is to test the breaker used by production services. After a test, reset the instance or create a fresh context/instance to prevent state and metrics from affecting other tests.

## 10. Usage Rules

- Use `transitionToOpenState()` when you need to open a breaker following the standard wait-and-probe cycle.
- Use `transitionToForcedOpenState()` when you need to forcefully reject calls until another operational action is taken.
- Use `transitionToHalfOpenState()` to permit a limited number of probes; avoid unleashing all traffic at once.
- Transition directly to `CLOSED` only after verifying the dependency can handle traffic again.
- Use `reset()` when you genuinely need to clear accumulated metrics and start a new baseline; do not confuse it with a state transition.
- Use `METRICS_ONLY` to observe a policy before blocking, while keeping in mind that this state does not protect the dependency.
- Monitor state transition, reset, error, success, and call-not-permitted events alongside metrics.
- Protect all administrative actions with authorization, auditing, and recovery procedures.

Manual state transitions are traffic-control tools; reset is an operation that refreshes statistics and state. Using each for its intended purpose enables operations teams to isolate dependencies when needed, probe recovery in a controlled manner, and preserve reliable data to explain circuit breaker behavior in Spring Cloud.
