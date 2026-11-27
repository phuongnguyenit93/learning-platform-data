# Calculating failureRateThreshold from Recorded Calls

## What does failureRateThreshold represent?

In Spring Cloud Circuit Breaker using Resilience4j, `failureRateThreshold` is the failure percentage threshold that the Circuit Breaker uses to decide when to transition from `CLOSED` to `OPEN`. The configured value is a percentage from 0 to 100. For example, `failureRateThreshold: 50` means the circuit opens when the failure rate in the statistical window reaches at least 50%, provided there is at least the minimum number of calls to evaluate.

This threshold is calculated from the outcomes the Circuit Breaker actually records. It is not simply the number of errors divided by the total requests seen by the application or API gateway, because some exceptions may be ignored and calls rejected while the circuit is open are not part of the current window's statistical sample.

## Calculation formula

Let:

- \(F\) be the number of calls recorded as failed in the window.
- \(N\) be the total number of recorded calls in the window, including successes and failures.

The failure rate is calculated as follows:

\[
\text{failureRate} = \frac{F}{N} \times 100\%
\]

The Circuit Breaker compares this rate with `failureRateThreshold`. If `failureRate` is greater than or equal to the threshold, Resilience4j triggers a state transition from `CLOSED` to `OPEN`. If the rate is lower than the threshold, the circuit remains `CLOSED` and continues updating the window as new results arrive.

The sufficient-sample condition is also critical: the rate is only calculated for decision-making once the number of recorded calls reaches at least `minimumNumberOfCalls`. Before that point, a few consecutive failures are not enough to conclude that the dependent service is degrading.

## Step-by-step calculation example

Suppose the Circuit Breaker is configured with `slidingWindowSize = 10`, `minimumNumberOfCalls = 5`, and `failureRateThreshold = 50`. The window can hold up to the 10 most recent results, yet the Circuit Breaker begins evaluating as soon as 5 results are available.

After the first five calls, suppose the outcomes are:

| Call | Recorded outcome |
| --- | --- |
| 1 | Success |
| 2 | Failure |
| 3 | Failure |
| 4 | Success |
| 5 | Failure |

We have \(F = 3\) and \(N = 5\), therefore:

\[
\text{failureRate} = \frac{3}{5} \times 100\% = 60\%
\]

Because 60% is greater than the 50% threshold, the Circuit Breaker transitions to `OPEN`. It does not need to wait for all 10 results before evaluating. If only two of the five calls failed, the rate would be \(2/5 \times 100\% = 40\%\), which is below the threshold so the circuit stays `CLOSED`.

Matching the threshold exactly also opens the circuit. With five results containing two failures and a threshold of 40%, the rate equals 40%, so the condition to open the circuit is satisfied. This is why it is important to understand the comparison as “greater than or equal to”, not strictly “greater than”.

## Window and threshold configuration

Configuration example in `application.yml`:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      orderService:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        waitDurationInOpenState: 20s
```

The properties serve distinct roles:

| Property | Meaning |
| --- | --- |
| `slidingWindowType` | Selects a count-based window (`COUNT_BASED`) or time-based window (`TIME_BASED`). |
| `slidingWindowSize` | Maximum number of results for a count window, or number of seconds for a time window. |
| `minimumNumberOfCalls` | Minimum number of calls that must be recorded before calculating the rate to decide whether to open the circuit. |
| `failureRateThreshold` | Minimum failure rate, as a percentage, to transition to `OPEN`. |
| `waitDurationInOpenState` | Wait duration in `OPEN` before the Circuit Breaker can transition to `HALF_OPEN`. |

`minimumNumberOfCalls` must align with the window size. For example, a count window of size 10 cannot require 15 calls within that same window before evaluating. With `TIME_BASED`, the minimum number of calls is still the actual number of results recorded within the configured time interval; a 10-second window does not mean there will always be 10 calls.

## How do COUNT_BASED and TIME_BASED affect the denominator?

With `COUNT_BASED`, the window keeps the outcomes of a fixed number of most recent calls. When a new result enters a full window, the oldest result is evicted from the calculation. Therefore, the rate reflects the behavior of recent calls rather than the entire history since application startup.

For example, a window has 10 results, with 4 failures and 6 successes. The failure rate is 40%. When a new successful call enters and the oldest result—which was a success—is evicted, the window still has 4 failures out of 10 results. If the evicted result was a failure, the new window has 3 failures out of 10 results and the rate drops to 30%.

With `TIME_BASED`, Resilience4j aggregates results over the configured most recent time interval, using time buckets to update metrics. The denominator is the number of calls recorded within that interval. As time passes, results belonging to older buckets leave the window and the rate can change even without any configuration change.

## Determining which calls count as failures

Division is meaningful only when outcomes are classified properly. Under Resilience4j's default configuration, exceptions from calls are recorded as failures, except for exceptions configured to be ignored. You can customize classification using `recordExceptions` and `ignoreExceptions`.

- `recordExceptions` specifies the exception types counted as failures. When this list is configured, exceptions not in the list are treated as successes by the Circuit Breaker, unless ignored.
- `ignoreExceptions` specifies exceptions excluded from statistics: they increment neither the failure count nor the success count. Ignore rules take higher priority than failure recording.
- A call that completes normally is counted as a success, unless a custom result evaluation configuration is provided.

For example, if the window has 8 calls that completed normally, 2 exceptions recorded as failures, and 2 ignored exceptions, then \(N = 10\) and \(F = 2\). The failure rate is 20%. The two ignored exceptions are excluded from the denominator. Counting them as either two failed requests or two successful requests would yield the wrong result.

Several points to distinguish:

- Calls rejected by the Circuit Breaker while `OPEN` are typically tracked separately as not permitted calls (`not permitted`), and are not added to the window's failure count.
- Timeout calls are only counted as failures if the timeout error propagates to the Circuit Breaker and is configured to be recorded. Timeout is a wait-duration limiting mechanism; `failureRateThreshold` only evaluates recorded outcomes.
- Fallback is a way to produce an alternative response for the caller. When analyzing the failure rate, use the Circuit Breaker's metrics rather than counting final responses received by the client, because a fallback can mask exceptions at the application surface.

## Reading metrics to verify the calculation

Resilience4j exposes metrics for each Circuit Breaker instance. You can read the number of calls in the window, failed calls, and failure rate to verify against the calculation:

```java
CircuitBreaker.Metrics metrics = circuitBreaker.getMetrics();

int bufferedCalls = metrics.getNumberOfBufferedCalls();
int failedCalls = metrics.getNumberOfFailedCalls();
float failureRate = metrics.getFailureRate();

log.info(
    "bufferedCalls={}, failedCalls={}, failureRate={}%, state={}",
    bufferedCalls,
    failedCalls,
    failureRate,
    circuitBreaker.getState()
);
```

When the number of calls has not reached `minimumNumberOfCalls`, `getFailureRate()` can return `-1` to indicate insufficient data for evaluation. This value does not mean the failure rate is negative or zero. Dashboards should display a separate “insufficient samples” state so operators do not mistakenly assume the service is healthy.

When comparing metrics, read them at the same point in time because the window continues changing as calls complete. In an environment with multiple application instances, each instance may have its own Circuit Breaker and statistical window; one instance's rate does not necessarily equal the aggregated rate at the API gateway or centralized monitoring system.

## Choosing threshold and minimumNumberOfCalls

A low threshold makes the Circuit Breaker react quickly to a small number of errors, yet also opens the circuit easily during brief fluctuations. A high threshold reduces the chance of opening the circuit over a few sporadic errors, yet may let many calls continue hitting a failing service. Threshold selection should be based on the error level the application can tolerate and the consequences of continuing to call the dependent service.

`minimumNumberOfCalls` helps avoid drawing conclusions from too small a sample. For example, one failure out of one call gives a 100% rate, yet if a minimum of five calls is required, the Circuit Breaker does not open on that single outcome alone. When traffic is low, keep in mind that accumulating enough samples may take longer; when traffic is high, a window that is too small may overreact to a transient burst of errors.

Do not pick `failureRateThreshold` just so dashboards always show `CLOSED`. Test the calculation against concrete operational scenarios: normal error rate, a brief error burst, service disconnection, and slow service responses. Then verify whether the threshold and window size trigger circuit opening at a timing that matches your system protection goals.

## Common calculation mistakes

| Incorrect calculation | Correct calculation |
| --- | --- |
| Taking total requests from the gateway as the denominator. | Use the number of calls the Circuit Breaker recorded in the window. |
| Dividing failures by `slidingWindowSize` even when the window is not full. | Divide by the actual recorded results; only make decisions after reaching `minimumNumberOfCalls`. |
| Treating ignored exceptions as successes. | Ignored exceptions belong in neither the numerator nor the denominator. |
| Treating `failureRateThreshold: 50` as 0.5%. | It represents 50 percent. |
| Thinking the rate must strictly exceed the threshold to open the circuit. | Meeting the threshold exactly is also sufficient to transition to `OPEN`. |
| Adding calls rejected while the circuit is open to the failure count. | Track not-permitted calls separately from outcomes of executed calls. |

When you clearly understand the numerator, denominator, exception classification, and sufficient-sample condition, you can predict more accurately when the Circuit Breaker transitions from `CLOSED` to `OPEN`. This is the foundation for configuring Resilience4j to match actual traffic and protect dependent services in a Spring Cloud system.
