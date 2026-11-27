# slowCallRateThreshold Differs from the Failure Rate Threshold

In Spring Cloud CircuitBreaker using Resilience4j, a circuit breaker can open when a dependent service returns errors too frequently or responds too slowly. These two signals are tracked separately: **failureRateThreshold** caps the percentage of failed calls, while **slowCallRateThreshold** caps the percentage of calls whose execution duration exceeds the threshold considered slow.

Distinguishing these two thresholds protects a service against both explicit errors and performance degradation. A service may still return HTTP 200 for most requests yet take several seconds to respond; if only the failure rate is measured, the circuit breaker may continue allowing many slow calls through and exhaust the caller's resources.

## Two types of signals measured by the circuit breaker

Resilience4j records both call outcomes and execution durations in the sliding window. From that sample set, it computes two independent rates:

| Setting | Measurement | Question answered |
|---|---|---|
| **failureRateThreshold** | Percentage of calls recorded as failed. | How many calls did not complete successfully? |
| **slowCallRateThreshold** | Percentage of calls with execution duration equal to or longer than the slow threshold. | How many calls are taking too long? |
| **slowCallDurationThreshold** | Absolute duration used to classify a single call as slow. | How long must a call take to be counted as slow? |

A common point of confusion is that **slowCallRateThreshold is not a wait timeout**. It is a percentage, just like failureRateThreshold. The duration used to identify each slow call is slowCallDurationThreshold.

For example, configuring slowCallDurationThreshold as 800 ms and slowCallRateThreshold as 60 means calls taking at least 800 ms are marked slow; when at least 60% of calls in the sample set are judged slow, the circuit breaker can open. The failureRateThreshold is evaluated independently over the same window.

## Slow calls and failed calls are not synonymous

A call is classified along two distinct dimensions:

- **Successful yet slow:** the service returns a valid result, but execution duration exceeds slowCallDurationThreshold. This call increases the slow call rate without necessarily increasing the failure rate.
- **Fast failure:** the call throws an exception or is classified as a failure before exceeding the slow duration threshold. This call increases the failure rate, without necessarily increasing the slow call rate.
- **Failed and slow:** the call is both classified as a failure and takes at least the slow duration threshold. It can contribute to both rates.

The two metric groups are not mutually exclusive. You must not add the failure rate and slow call rate together to infer the percentage of problematic requests, because a single call can appear in both groups.

Real-world example: the order service calls the inventory service. The inventory service still returns correct data, yet due to slow database queries, some calls take 1.5 seconds. Those calls succeed in outcome yet are still slow calls. If they occur frequently enough, the circuit breaker should open to relieve pressure on the degrading service, even when the failure rate is near zero.

## How the two thresholds open the circuit breaker

Resilience4j evaluates both the failure rate and the slow call rate after the minimum number of samples has been collected. When either rate meets or exceeds its respective threshold, the circuit breaker can transition from CLOSED to OPEN.

~~~mermaid
flowchart TD
    A[Call outcomes in sliding window] --> B{Reached minimumNumberOfCalls?}
    B -->|No| C[Continue collecting samples]
    B -->|Yes| D[Compute failure rate]
    D --> E[Compute slow call rate]
    E --> F{Failure rate reached threshold?}
    F -->|Yes| G[Transition to OPEN]
    F -->|No| H{Slow call rate reached threshold?}
    H -->|Yes| G
    H -->|No| I[Stay CLOSED]
~~~

The circuit-opening condition is an **OR** relationship between the two signals:

- Failure rate reaches the threshold, even if the remaining calls respond fast.
- Slow call rate reaches the threshold, even if most calls still return successful outcomes.

Both rates do not need to exceed their thresholds simultaneously. This mechanism lets the circuit breaker detect two different kinds of incidents: a service failing to complete requests and a service still returning results but no longer meeting acceptable response times.

While the circuit is OPEN, new calls fail fast. After the configured wait duration, the circuit breaker transitions to HALF_OPEN to permit a limited number of trial calls. Trial call results continue to be evaluated against both the failure rate and slow call rate; if the service has recovered, the circuit can close again, whereas if either threshold is still exceeded, the circuit reopens.

## Example calculating rates over the same sliding window

Suppose a circuit breaker has the following settings:

- slidingWindowType: COUNT_BASED
- slidingWindowSize: 20
- minimumNumberOfCalls: 10
- failureRateThreshold: 50
- slowCallDurationThreshold: 800 ms
- slowCallRateThreshold: 60

After 10 calls are recorded, consider these outcomes:

| Call | Outcome | Duration | Failed? | Slow? |
|---:|---|---:|---|---|
| 1 | Success | 200 ms | No | No |
| 2 | Success | 1,000 ms | No | Yes |
| 3 | Success | 1,200 ms | No | Yes |
| 4 | Success | 300 ms | No | No |
| 5 | Success | 900 ms | No | Yes |
| 6 | Failure | 250 ms | Yes | No |
| 7 | Success | 1,100 ms | No | Yes |
| 8 | Success | 1,300 ms | No | Yes |
| 9 | Success | 400 ms | No | No |
| 10 | Success | 950 ms | No | Yes |

Out of the 10 calls:

- There is 1 failed call, so the failure rate is 1/10 = 10%.
- There are 6 slow calls, so the slow call rate is 6/10 = 60%.

The 10% failure rate is below the 50% threshold, yet the slow call rate equals the 60% threshold. The circuit breaker can open because of the slow call signal. This is a situation where failureRateThreshold fails to catch the issue, whereas slowCallRateThreshold detects the performance degradation.

Consider another case: 5 calls fail fast and 5 calls succeed across 10 samples; no call exceeds 800 ms. Here the failure rate is 50% and the slow call rate is 0%. The circuit breaker opens because the failure rate reaches its threshold, even with no response-time issue.

Both examples show that each threshold protects a different objective. Failure rate detects unavailability or processing errors; slow call rate detects when a service still responds but no longer responds fast enough.

## Configuration in Spring Cloud CircuitBreaker

With Spring Cloud CircuitBreaker integrating Resilience4j, thresholds can be configured per instance in application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

In this configuration:

- slidingWindowSize is 20, so the window keeps outcomes of up to the 20 most recent calls.
- minimumNumberOfCalls is 10, so the circuit breaker requires at least 10 outcomes before evaluating rates.
- failureRateThreshold is 50, so a 50% failed call rate can open the circuit.
- slowCallDurationThreshold is 800 ms, so calls taking 800 ms or longer are classified as slow.
- slowCallRateThreshold is 60, so a 60% slow call rate can open the circuit.
- waitDurationInOpenState is 10 seconds, the wait duration before attempting recovery.
- permittedNumberOfCallsInHalfOpenState is 3, limiting the number of trial calls in HALF_OPEN.

The instance name inventory must match the circuit breaker name created by the application, such as inventory when calling CircuitBreakerFactory.create("inventory"). Instance naming and configuration must stay consistent between source code and application.yml.

If TIME_BASED is used, slidingWindowSize represents window length in seconds instead of call count. Both rates are still computed from calls falling within that time window. Under low traffic, pay attention to minimumNumberOfCalls: if there are not enough samples, there is no basis to evaluate rates even if a few calls were very slow.

## Choosing slowCallDurationThreshold and slowCallRateThreshold

The two slow-call parameters must be chosen together, yet they answer two different questions.

**slowCallDurationThreshold** sets the boundary between a normal call and a slow call. Base it on target response time, observed dependency latency, and the remaining time budget of the upstream request. If set too low, normal latency variance gets counted as slow. If set too high, the circuit breaker recognizes an issue only after users have already waited too long.

**slowCallRateThreshold** defines how widespread slowness must be before opening the circuit. If set too low, even a small fraction of slow calls can disrupt calls to the dependency. If set too high, the system may continue sending many slow requests and tying up resources for extended periods.

You can use p95 or p99 latency metrics under normal operating conditions to pick an initial duration threshold. Then observe the rate of calls exceeding that threshold under increased load or dependency degradation. Avoid blindly copying a single value set across services, because each service has different latency targets, traffic profiles, and criticality.

A practical approach:

1. Determine the response time the business accepts for the dependency call.
2. Measure normal latency and set slowCallDurationThreshold above ordinary variance, while staying within the time budget.
3. Choose slowCallRateThreshold according to the acceptable level of degradation before tripping the circuit.
4. Choose sliding window and minimumNumberOfCalls so rates reflect enough samples.
5. Observe metrics in a test environment and tune thresholds based on real behavior.

## Relationship with timeouts and fallbacks

slowCallRateThreshold does not replace timeouts. The circuit breaker evaluates the slow call rate from recorded outcomes and execution durations; it does not stop an in-flight call simply because it has exceeded slowCallDurationThreshold.

For example, a call might take 2 seconds before returning a successful result. The circuit breaker can record this as a slow call after the call completes, then open the circuit for subsequent calls if the slow call rate exceeds the threshold. The current call can still return its successful outcome to the caller.

Timeouts cap how long an individual call waits. When a timeout triggers and the call is classified as a failure, it can increase the failure rate; if execution duration also exceeded the slow threshold, it can contribute to the slow call rate as well. Configure HTTP client timeouts or TimeLimiter according to your response budget, and understand how the client handles task cancellation.

Fallbacks handle outcomes when a call fails or when the circuit breaker rejects a call because it is OPEN. A call that is slow yet ultimately succeeds does not necessarily trigger the fallback for that call itself. However, slow outcomes can still cause the circuit to open, routing subsequent calls to the fallback.

For an inventory service, the fallback might return the most recent cached data along with a status indicating the data may be stale. Do not return an assumed-accurate result when the business requires live stock levels to confirm an order. Design fallbacks according to each feature's tolerance for stale data.

## Testing and monitoring both thresholds

To validate the configuration, test each signal independently and in a combined scenario:

| Scenario | Expected outcome |
|---|---|
| Service returns fast errors exceeding failureRateThreshold, duration below slow threshold. | Circuit opens due to failure rate. |
| Service returns successes but latency exceeds slowCallDurationThreshold frequently enough. | Circuit opens due to slow call rate. |
| Some calls are both failed and slow. | Those calls can contribute to both rates. |
| Call count is below minimumNumberOfCalls. | Rate thresholds are not yet evaluated from an insufficient sample set. |
| Service recovers in HALF_OPEN and trial calls meet requirements. | Circuit transitions back to CLOSED. |
| Service remains slow or failing in HALF_OPEN. | Circuit returns to OPEN. |

In operations, monitor circuit breaker state alongside failure rate, slow call rate, and response time. If the circuit opens due to failure rate, investigate the root causes of exceptions, network failures, or business errors. If it opens due to slow call rate, check database queries, network latency, resource limits, queues, and load on the dependent service.

Also inspect fallback frequency and rejected call counts. Rising fallbacks may keep the API responsive, yet may indicate users are frequently receiving degraded data. After adjusting thresholds, retest both fast-failure and slow-response scenarios to avoid protecting well against one type of incident while missing the other.

## Design takeaways

failureRateThreshold measures the rate of failed calls; slowCallRateThreshold measures the rate of calls exceeding the slow duration threshold; slowCallDurationThreshold defines the duration that classifies a call as slow. Resilience4j evaluates both rates over the sliding window once enough samples are recorded and can open the circuit breaker when either rate meets its threshold.

Therefore, a service may still return successful responses while the circuit breaker opens to protect the calling system from prolonged latency. Combining both thresholds with appropriate timeouts, bulkheads, and fallbacks allows a service to both limit error impact and preserve availability when dependencies suffer performance degradation.
