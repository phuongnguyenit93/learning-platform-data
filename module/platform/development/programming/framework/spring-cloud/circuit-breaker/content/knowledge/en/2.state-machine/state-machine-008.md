# FORCED_OPEN, DISABLED, and METRICS_ONLY in Resilience4j

Resilience4j implements the Circuit Breaker using a finite state machine. The three common states are CLOSED, OPEN, and HALF_OPEN: the circuit permits calls and records outcomes, trips calls when the failure rate exceeds the threshold, and then probes recovery. Beyond these three states, Resilience4j also provides three special states: FORCED_OPEN, DISABLED, and METRICS_ONLY.

Special states allow the application or operator to explicitly alter how the Circuit Breaker handles calls. They are useful when you need to temporarily cut off a dependency, temporarily bypass protection, or observe service quality without rejecting requests yet. To use them properly, you must understand how each state permits calls, whether it records metrics, and what is required to return to normal protection mode.

## 1. Where the Three Special States Fit

The three special states are not automatic next steps from CLOSED, OPEN, or HALF_OPEN. They are operational modes activated by explicit state transition calls.

| State | Calls to Dependency | Metrics and Call Events | Automatic State Transition by Threshold |
| --- | --- | --- | --- |
| CLOSED | Permitted | Yes | Can transition to OPEN |
| OPEN | Rejected | Records events related to state and rejected calls | Can transition to HALF_OPEN after wait duration |
| HALF_OPEN | Only a limited number of probe calls permitted | Yes | Can transition to CLOSED or OPEN |
| FORCED_OPEN | All calls rejected | No metrics recorded and no call events emitted; state transition events are still emitted | No |
| DISABLED | All calls permitted | No metrics recorded and no call events emitted; state transition events are still emitted | No |
| METRICS_ONLY | All calls permitted | Records metrics and emits events | Does not automatically open even if thresholds are exceeded |

Key points to remember:

- FORCED_OPEN is a mode that explicitly blocks all calls.
- DISABLED permits all calls and skips Circuit Breaker metrics collection.
- METRICS_ONLY permits all calls while still collecting metrics for observation.

For all three special states, the Circuit Breaker does not automatically return to CLOSED simply because time passes or the dependent service becomes healthy again. The application must perform an explicit state transition to exit a special mode.

## 2. FORCED_OPEN — Explicitly Blocking All Calls

FORCED_OPEN forces the Circuit Breaker to reject all calls passing through it, regardless of the current failure rate, OPEN wait duration, or actual health of the dependent service. Unlike normal OPEN, FORCED_OPEN does not wait out a timer to automatically transition to HALF_OPEN.

When a call goes through a Circuit Breaker in FORCED_OPEN, Resilience4j denies execution permission. When using Resilience4j directly, the caller typically receives CallNotPermittedException. If the application wraps the call with Spring Cloud CircuitBreaker and declares a fallback, the fallback can handle the error from the rejected call. Without a fallback, the error propagates up to the caller.

### When Should You Use It?

Appropriate situations include:

- **Dependency under maintenance:** proactively stop sending requests to a service undergoing an upgrade or maintenance.
- **Confirmed incident:** operations teams want to isolate a dependency causing severe failures across calling services.
- **Stopping further load on a dependent system:** while coordinating incident response, proactively cut off calls to reduce pressure on the dependency.

For example, the Inventory service is experiencing a data incident. The Order service still accepts requests, but all inventory check calls need to be blocked while operations resolves the issue. If business rules allow, Order can return a message stating inventory cannot be confirmed temporarily. If business rules forbid proceeding without inventory data, Order should return a controlled error.

### Transitioning to FORCED_OPEN and Recovering

Resilience4j provides direct state transition methods on the CircuitBreaker object:

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Proactively block all calls
inventory.transitionToForcedOpenState();

// After the incident is resolved, restore normal protection
inventory.transitionToClosedState();
~~~

The snippet illustrates using a CircuitBreaker obtained from the registry. The name `inventory` must match the instance name used by the business call path. If you operate on a different instance, live calls may remain unaffected.

When recovering from FORCED_OPEN, you can explicitly transition back to CLOSED so the Circuit Breaker resumes collecting outcomes and automatically opens when thresholds are exceeded. Transitioning back to CLOSED means beginning to permit calls under normal protection; it does not prove the dependency is actually healthy. Before reopening traffic, operations still needs to rely on health checks, logs, dependent service metrics, and incident status.

## 3. DISABLED — Bypassing the Circuit Breaker

DISABLED is a mode where the Circuit Breaker performs no protection. Every call is permitted through. The Circuit Breaker neither records metrics for calls nor emits call events; state transition events are still emitted.

In this state, the Circuit Breaker does not compute failure rate or slow call rate to open the circuit. Thus, even if the dependency repeatedly returns errors or responds very slowly, the Circuit Breaker will not automatically transition to OPEN.

### When Should You Use It?

DISABLED can be useful in limited situations:

- Temporarily bypassing the Circuit Breaker while investigating an integration-layer issue to determine whether errors originate from the Circuit Breaker mechanism.
- Running a controlled experiment in a development or test environment.
- Temporarily pausing Circuit Breaker collection and handling under an explicit operational decision.

DISABLED removes both call blocking and Circuit Breaker metrics. If the dependency is slow, calls can still consume threads, connections, or other resources on the calling service. Therefore, before using it, clearly establish timeouts, concurrency limits, and error handling at other layers.

### Transitioning to DISABLED and Recovering

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Bypass the Circuit Breaker: all calls are permitted
inventory.transitionToDisabledState();

// Re-enable protection and outcome recording
inventory.transitionToClosedState();
~~~

DISABLED should not be treated as a way to handle a failing dependency. If the goal is to stop sending calls to the dependency, FORCED_OPEN is the appropriate state. If you want to observe errors while still letting calls pass through, consider METRICS_ONLY.

## 4. METRICS_ONLY — Observing Without Blocking Calls

METRICS_ONLY lets all calls pass through while still recording outcomes, metrics, and Circuit Breaker events. The difference from CLOSED is that the Circuit Breaker does not automatically transition to OPEN, even when the failure rate or slow call rate exceeds configured thresholds.

For example, suppose failureRateThreshold is 50% and minimumNumberOfCalls is 10. In the evaluation window, 8 out of 10 calls fail, giving an 80% failure rate. In CLOSED, this rate could cause the Circuit Breaker to transition to OPEN. In METRICS_ONLY, the Circuit Breaker still allows calls to continue reaching the dependency, records the failure rate, and emits related events, without tripping the circuit.

### When Should You Use It?

METRICS_ONLY is especially useful for phased rollouts of protection:

1. Start collecting metrics to understand real traffic, failure rate, and latency of the dependency.
2. Observe under normal load and peak periods.
3. Evaluate thresholds for failure rate, slow call rate, and minimum number of calls.
4. Tune configuration to reduce the risk of opening too early or reacting too late.
5. Once dependency behavior is understood, transition to CLOSED so the Circuit Breaker enforces automatic protection.

This mode is also useful when evaluating the potential impact of a new configuration. The system can continue serving traffic while the development team tracks threshold breaches and compares them against reliability targets.

### Transitioning to METRICS_ONLY and Re-enabling Protection

~~~java
CircuitBreaker inventory = circuitBreakerRegistry
    .circuitBreaker("inventory");

// Permit all calls while continuing to record metrics
inventory.transitionToMetricsOnlyState();

// Once thresholds are evaluated, enable automatic protection
inventory.transitionToClosedState();
~~~

In METRICS_ONLY, exceeding thresholds does not mean traffic is being protected. A dashboard might show a high failure rate while the Circuit Breaker still does not reject calls. Therefore, clearly distinguish METRICS_ONLY from CLOSED when reading dashboards and operational alerts.

## 5. Distinguishing Easily Confused States

### OPEN vs. FORCED_OPEN

Both states reject calls, but their purpose and recovery differ.

- OPEN is the automatic result of evaluating failures or slow calls. After the wait duration, the Circuit Breaker can transition to HALF_OPEN to probe the dependency.
- FORCED_OPEN is an intentional state transition decision. The Circuit Breaker keeps blocking calls until another state transition or reset occurs.

Therefore, do not wait for waitDurationInOpenState to expire to recover from FORCED_OPEN. An explicit operational action is required.

### CLOSED vs. METRICS_ONLY

Both permit calls and record outcomes. The difference lies in how they react when failure rate or slow call rate exceeds thresholds.

- CLOSED can transition to OPEN to block calls.
- METRICS_ONLY continues permitting calls and only provides observational data.

METRICS_ONLY is suited for measurement and tuning. CLOSED is suited when you are ready for automatic protection.

### DISABLED vs. METRICS_ONLY

Both permit all calls. However:

- DISABLED neither records metrics nor emits call events.
- METRICS_ONLY still records metrics and emits events, without automatically opening the circuit.

If you need to observe dependency behavior, choose METRICS_ONLY. DISABLED loses observational data from the Circuit Breaker itself, so use it only with a specific reason.

## 6. Managing State via CircuitBreakerRegistry

In a Spring Boot application using Resilience4j, CircuitBreakerRegistry manages Circuit Breaker instances by name. You can inject the registry into a management bean to transition a dependency's state when needed.

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import org.springframework.stereotype.Component;

@Component
public class InventoryCircuitBreakerControl {

    private final CircuitBreakerRegistry registry;

    public InventoryCircuitBreakerControl(CircuitBreakerRegistry registry) {
        this.registry = registry;
    }

    public void forceOpen() {
        breaker().transitionToForcedOpenState();
    }

    public void disable() {
        breaker().transitionToDisabledState();
    }

    public void observeOnly() {
        breaker().transitionToMetricsOnlyState();
    }

    public void resumeProtection() {
        breaker().transitionToClosedState();
    }

    public CircuitBreaker.State currentState() {
        return breaker().getState();
    }

    private CircuitBreaker breaker() {
        return registry.circuitBreaker("inventory");
    }
}
~~~

The example above illustrates a state management class for the `inventory` instance. In a real application, ensure the injected registry is the one managing the exact Circuit Breaker used on the business call path. When Spring Cloud CircuitBreaker creates instances through the Resilience4j provider, do not create an independent registry and assume state transitions on the new registry will affect the factory's instances.

Spring Cloud CircuitBreaker provides an abstract API for synchronous or reactive calls. Transitions to FORCED_OPEN, DISABLED, and METRICS_ONLY are Resilience4j-specific APIs. Thus, when you need to control special states, the application must access the right Resilience4j instance at the provider layer.

Instance names must be consistent. If business code calls a Circuit Breaker named `inventory` while the management class controls an instance named `inventory-service`, the two objects may not be the same Circuit Breaker. In that case, management actions will not change the behavior of live calls.

## 7. Combining with Fallbacks and Other Protection Mechanisms

Special states only change the behavior of the Circuit Breaker. Other mechanisms in the processing chain may still operate depending on how the application is configured.

| Mechanism | Impact When Circuit Breaker Is in a Special State |
| --- | --- |
| Fallback | Can handle errors when FORCED_OPEN rejects calls, if the call is wrapped with a fallback-capable API. |
| Timeout / TimeLimiter | Can still bound processing duration according to its own configuration. |
| Retry | Can continue retrying if configured at another layer; avoid generating many attempts while Circuit Breaker is FORCED_OPEN. |
| Bulkhead | Still limits concurrent calls if applied independently. |
| Application metrics | Metrics from HTTP clients, servers, or other observability systems can still exist even when Circuit Breaker is DISABLED or FORCED_OPEN. |

For example, with Spring Cloud CircuitBreaker, a synchronous call can supply a fallback like this:

~~~java
return circuitBreakerFactory.create("inventory").run(
    () -> inventoryClient.getInventory(sku),
    error -> Inventory.unavailable(sku)
);
~~~

When the Circuit Breaker is in FORCED_OPEN, the call to `inventoryClient` is not executed. The fallback receives the error from the rejected call and returns a backup result. The fallback result type must clearly indicate unavailable or alternative data; never fabricate a successful business outcome if the system has not actually verified the required conditions.

For reactive calls, you can apply the same idea using ReactiveCircuitBreakerFactory and a fallback returning an appropriate Mono or Flux. Controlling special states is still performed on the underlying Resilience4j Circuit Breaker behind the provider.

## 8. Safe Operational Procedures

Changing states can directly impact inter-service traffic. Define the objective, authorized operators, and recovery procedure in advance.

| Objective | Recommended State | What to Monitor |
| --- | --- | --- |
| Cut off calls to a dependency under maintenance | FORCED_OPEN | Rejected call count, fallbacks, maintenance status |
| Temporarily bypass Circuit Breaker in a controlled test | DISABLED | Timeouts, client errors, and resource usage at other layers |
| Observe failure rate without blocking traffic | METRICS_ONLY | Failure rate, slow call rate, sample count, and latency |
| Re-enable automatic protection | CLOSED | Failure rate, slow calls, dependency state, and response under rising load |

An operational procedure might include:

1. Identify the exact dependency and Circuit Breaker name.
2. Record the current state, reason for change, and operator.
3. Select the state matching the operational objective.
4. Monitor fallbacks, failure rate, latency, and caller service resources.
5. When conditions change, transition back to the desired mode, typically CLOSED to restore automatic protection.
6. Confirm live calls flow through the right instance and dashboards display the new state.

If exposing state control via an administrative endpoint, restrict access permissions and record audit logs. These actions can cause an application to stop calling a dependency or disable circuit breaking, so ordinary users or public endpoints must never be allowed to change states arbitrarily.

## 9. Monitoring and Interpreting Metrics

METRICS_ONLY is especially useful during observation because it continues recording metrics and emitting call-related events. Information to monitor includes:

- Failed call rate and slow call rate.
- Counts of successful, failed, and rejected calls.
- Average response time and latency percentiles.
- Threshold breach events for failure rate or slow call rate.
- Current Circuit Breaker state per dependency.

In DISABLED and FORCED_OPEN, Resilience4j does not record metrics or emit call events; only state transition events are emitted. Therefore, if dashboards rely solely on Circuit Breaker metrics, data may not reflect dependency activity in these two states. You may need to inspect additional metrics from HTTP clients, service meshes, servers, or external monitoring systems.

When reading dashboards, check both the current state and the type of metrics present. For instance, METRICS_ONLY with a 90% failure rate means the dependency is experiencing many errors while calls are still allowed through. FORCED_OPEN means the Circuit Breaker is proactively blocking calls; absence of call metrics from the Circuit Breaker does not mean the dependency's errors have stopped.

## 10. Key Takeaways

- FORCED_OPEN blocks all calls and requires an explicit state transition to recover.
- DISABLED permits all calls while stopping metrics recording and call event emission.
- METRICS_ONLY permits all calls, still records metrics and emits events, but does not automatically transition to OPEN when thresholds are exceeded.
- OPEN is an automatic circuit-breaking state that can transition to HALF_OPEN after a wait duration; FORCED_OPEN has no such automatic probing mechanism.
- METRICS_ONLY is useful for phased rollouts and tuning thresholds based on real data.
- DISABLED should not be used when the goal is observation; choose METRICS_ONLY for that purpose.
- State transition actions must target the exact Resilience4j instance used by the business call path.
- Fallback, timeout, retry, and bulkhead have their own scopes; verify how they interact when the Circuit Breaker changes state.

When implementing Circuit Breakers in Spring Cloud with Resilience4j, the three special states help development and operations teams proactively control traffic and observe dependencies across different scenarios. Choosing the right state, monitoring the right metrics, and following a clear recovery procedure help applications handle incidents in a controlled manner without adding load or obscuring the true health of dependent services.

## References

- [Resilience4j CircuitBreaker — official documentation](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j CircuitBreaker API — source code and state descriptions](https://github.com/resilience4j/resilience4j/blob/master/resilience4j-circuitbreaker/src/main/java/io/github/resilience4j/circuitbreaker/CircuitBreaker.java)
- [Spring Cloud CircuitBreaker — reference documentation](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
