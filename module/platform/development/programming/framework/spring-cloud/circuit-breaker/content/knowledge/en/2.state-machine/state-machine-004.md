# Transition Conditions from CLOSED to OPEN

In Spring Cloud Circuit Breaker, the circuit breaker monitors the outcomes of calls to a dependent service. When the failure rate or slow call rate reaches or exceeds the configured threshold, it transitions from `CLOSED` to `OPEN` to prevent the application from continuing to send requests to a failing service. With the Resilience4j implementation, the transition decision is based on the minimum number of calls and metrics aggregated in a **sliding window**.

## Role of CLOSED and OPEN States

A circuit breaker is typically described using three states:

| State | Behavior |
| --- | --- |
| `CLOSED` | Permits calls to reach the dependent service and records outcomes to calculate failure rate and slow call rate. |
| `OPEN` | Rejects new calls immediately at the circuit breaker. The caller receives `CallNotPermittedException` and can switch to fallback handling. |
| `HALF_OPEN` | Permits a limited number of probe calls to test whether the service has recovered. |

While in `CLOSED`, the circuit breaker does not open just because a single call fails. It needs a sufficient number of samples to evaluate and then checks the rates against thresholds. The transition condition can be expressed as:

```text
minimumNumberOfCalls reached
                 AND
  (failureRate >= failureRateThreshold
       OR
   slowCallRate >= slowCallRateThreshold)
                 => OPEN
```

The two rates are evaluated independently. Either one reaching or exceeding its threshold is enough to open the circuit breaker.

## Four Factors Determining When the Circuit Opens

### 1. Minimum Number of Calls: minimumNumberOfCalls

`minimumNumberOfCalls` is the minimum number of recorded calls required in the sliding window before Resilience4j begins calculating the failure rate and slow call rate to decide whether to open the circuit.

For example, if `minimumNumberOfCalls` is `10`, after 3 failed calls the circuit breaker still cannot conclude based on rate that the service is failing. Only once at least 10 calls have been recorded does it calculate the rates and compare them against the thresholds.

This value helps avoid making premature decisions from too small a sample set. However, setting it too high can make the circuit breaker react slowly under low traffic; setting it too low can let a few random errors trip the circuit. Choose a value suited to the traffic volume and criticality of the service.

### 2. Failure Rate: failureRateThreshold

`failureRateThreshold` is the percentage threshold of calls recorded as failures. Resilience4j calculates the rate using the formula:

\[
\text{failureRate} = \frac{\text{number of failed calls}}{\text{total number of recorded calls in the window}} \times 100\%
\]

If `failureRate` is **greater than or equal to** `failureRateThreshold`, the circuit breaker transitions to `OPEN`, provided `minimumNumberOfCalls` has been reached.

Example: the current window has 10 recorded calls, of which 5 failed. The failure rate is `5 / 10 × 100% = 50%`. If the threshold is set to `50`, the condition is met and the circuit opens. The comparison uses `>=`, so a rate equal to the threshold also triggers the state transition.

A call is counted as a failure according to the circuit breaker's outcome and exception classification rules. When `recordExceptions` is configured, matching exceptions are counted as failures; non-matching exceptions are typically counted as successful calls. Exceptions in `ignoreExceptions` are ignored, counting as neither success nor failure. You can use predicates in Java configuration to define more granular classification rules.

### 3. Slow Call Rate: slowCallRateThreshold

A call can return successfully yet still harm the system if it takes too long. `slowCallDurationThreshold` defines the duration beyond which a call is considered slow; `slowCallRateThreshold` defines the maximum acceptable slow call percentage before opening the circuit.

Resilience4j calculates the slow call rate using the formula:

\[
\text{slowCallRate} = \frac{\text{number of slow calls}}{\text{total number of recorded calls in the window}} \times 100\%
\]

Example: out of 10 calls, 6 take longer than 2 seconds, even though all 6 return valid data. The slow call rate is `60%`. If `slowCallRateThreshold` is `60`, the circuit breaker transitions to `OPEN` once the minimum sample count is reached.

A call that is both failed and slow can contribute to both rates. The two rates are not added together; the circuit breaker evaluates each condition separately. Only either the failure rate or the slow call rate needs to reach its respective threshold for the circuit to open.

The circuit breaker identifies slow calls based on the actual execution duration of the call. It does not automatically interrupt an in-flight call when it exceeds `slowCallDurationThreshold`. To bound wait times and release resources, configure timeouts on the HTTP client or use an appropriate `TimeLimiter`. If a timeout produces an exception, that exception is only counted as a failure if allowed by the failure recording rules.

### 4. Sliding Window: slidingWindowType and slidingWindowSize

The sliding window determines the set of calls used to calculate the rates. Resilience4j supports two types:

| Window Type | How It Works | Configuration Example |
| --- | --- | --- |
| `COUNT_BASED` | Tracks outcomes of the most recent `slidingWindowSize` calls. When a new call completes, the oldest outcome leaves the window. | `slidingWindowSize: 20` means up to the 20 most recent calls are evaluated. |
| `TIME_BASED` | Tracks outcomes within the time period of the most recent `slidingWindowSize` seconds. | `slidingWindowSize: 30` means calls within the last 30 seconds are evaluated. |

`minimumNumberOfCalls` still plays a distinct role: the window determines which data remains valid, while the minimum number of calls determines when there is enough data to compute rates. For example, with a count-based window of 20 calls and a minimum sample count of 10, the circuit breaker starts evaluating after 10 recorded calls. Once the window is full, each new outcome replaces the oldest one.

With a time-based window, low traffic may leave the window without enough minimum calls. In that case, the circuit breaker remains `CLOSED` even if some recent calls failed; it only evaluates when enough samples exist in the current window.

## Configuring Resilience4j in Spring Cloud

The following example configures a circuit breaker named `inventoryService`. The instance name must match the ID the application uses when creating the circuit breaker via Spring Cloud CircuitBreaker or declaring the corresponding Resilience4j configuration.

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventoryService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
        recordExceptions:
          - java.util.concurrent.TimeoutException
```

Properties that directly govern the transition from `CLOSED` to `OPEN` in the example:

- `minimumNumberOfCalls: 10`: requires at least 10 recorded calls in the window before calculating rates.
- `failureRateThreshold: 50`: opens the circuit if the failure rate reaches 50% or higher.
- `slowCallDurationThreshold: 2s`: calls lasting longer than 2 seconds are counted as slow.
- `slowCallRateThreshold: 60`: opens the circuit if the slow call rate reaches 60% or higher.
- `slidingWindowType` and `slidingWindowSize`: choose how the set of tracked calls is defined.

`waitDurationInOpenState`, `permittedNumberOfCallsInHalfOpenState`, and `automaticTransitionFromOpenToHalfOpenEnabled` control the phase after the circuit has opened. They do not change the initial condition for transitioning from `CLOSED` to `OPEN`.

## Simulating the Transition Condition

Suppose the configuration has `minimumNumberOfCalls = 10`, `failureRateThreshold = 50`, and `slowCallRateThreshold = 60`. After 10 recorded calls, consider these cases:

| Outcomes in 10 Calls | Failure Rate | Slow Rate | Result |
| --- | ---: | ---: | --- |
| 4 failures, 2 slow calls | 40% | 20% | Remains `CLOSED` because both rates are below thresholds. |
| 5 failures, 1 slow call | 50% | 10% | Transitions to `OPEN` because the failure rate reaches the threshold. |
| 4 failures, 6 slow calls | 40% | 60% | Transitions to `OPEN` because the slow call rate reaches the threshold. |
| 3 failures, 5 slow calls | 30% | 50% | Remains `CLOSED` because both rates are below thresholds. |

In the last case, if the window size is 10 and a new slow call replaces an old non-slow call, the slow call rate rises to `60%` and the circuit transitions to `OPEN`. With a `COUNT_BASED` window, recalculate over the calls remaining in the window after each new outcome; do not take cumulative failures since application startup.

## What Happens After Transitioning to OPEN

When the open condition is satisfied, the circuit breaker changes its state to `OPEN` and emits a state transition event. New calls fail fast without continuing to consume resources on the dependent service. The application can handle `CallNotPermittedException` with a fallback to return backup data, report that the service is temporarily unavailable, or route the request to another suitable handler.

After `waitDurationInOpenState`, the circuit breaker can transition to `HALF_OPEN` to test recovery. Depending on configuration, this transition happens on the next call or automatically via a scheduler. In `HALF_OPEN`, only the number of probe calls limited by `permittedNumberOfCallsInHalfOpenState` is allowed. The probe outcomes determine whether the circuit closes again or reopens. This is the recovery verification phase; the initial opening condition remains based on the minimum sample count and the rates in the window.

Circuit breaker events and metrics should be monitored to determine why the circuit opened: high failure rate, increasing slow calls, or insufficient traffic to evaluate. When using Micrometer and a compatible monitoring system, you can observe state, successful/failed/rejected call counts, and related rates. Monitoring enables tuning thresholds based on actual behavior rather than arbitrary choices.

## Common Configuration Mistakes

- **Setting `minimumNumberOfCalls` higher than actual traffic:** the circuit breaker rarely accumulates enough samples in the window, so it does not open even when the service continuously fails.
- **Confusing `slidingWindowSize` with `minimumNumberOfCalls`:** one sets the window size, while the other sets the minimum sample count before calculating rates.
- **Configuring only the failure rate:** a service can respond very slowly while still returning success; set `slowCallDurationThreshold` and `slowCallRateThreshold` if latency is also a degradation signal.
- **Recording the wrong exceptions:** expected business errors or ignored exceptions can skew rates if classified improperly.
- **Assuming the circuit breaker replaces timeouts:** the circuit breaker detects and blocks new calls once conditions are met; timeouts bound the wait duration of an active call.
- **Misjudging concurrent calls:** calls already permitted prior to transitioning to `OPEN` can still continue to complete. Opening the circuit does not cancel in-flight calls.

When designing, choose a window suited to your traffic, set a representative minimum sample count, clearly define which exceptions count as failures, and configure thresholds for both failures and latency aligned with service objectives. This configuration lets the circuit breaker react on solid evidence, reduce repeated calls to a degraded service, and limit cascading failures in a Spring Cloud system.
