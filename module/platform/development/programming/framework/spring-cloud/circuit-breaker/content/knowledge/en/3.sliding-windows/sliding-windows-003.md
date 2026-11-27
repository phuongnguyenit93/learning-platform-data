# minimumNumberOfCalls and When Enough Samples Are Available for Evaluation

In Spring Cloud CircuitBreaker using Resilience4j, a circuit breaker does not open the circuit just because a single call fails. It needs to observe a sufficiently large number of outcomes in the *sliding window* before calculating the failure rate or slow call rate. The `minimumNumberOfCalls` parameter specifies the minimum number of calls that must be recorded in the current window before Resilience4j begins evaluating these rates.

This parameter prevents hasty decisions from too small a sample. For instance, if there is only one request and it fails, the failure rate is 100%, yet a single failure does not necessarily indicate that the dependent service is experiencing an outage. Conversely, if the minimum sample count is set too high relative to actual traffic, the circuit breaker may take a long time to detect an issue or never gather enough samples to evaluate.

## 1. What does `minimumNumberOfCalls` mean?

Resilience4j stores call results in a sliding window. Only when the number of recorded calls in the window reaches `minimumNumberOfCalls` does the circuit breaker compute the rates used to decide whether to open the circuit. With a configuration that includes both `failureRateThreshold` and `slowCallRateThreshold`, the circuit breaker can open when either the failure rate or the slow call rate reaches its respective threshold.

The two main rates are defined as follows:

\[
\text{Failure rate} = \frac{\text{Number of failed calls}}{\text{Total recorded calls}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Number of slow calls}}{\text{Total recorded calls}} \times 100\%
\]

For example, configuring `minimumNumberOfCalls: 8` means the circuit breaker needs at least 8 recorded results in the current window before evaluating rates. If there are only 7 results, even if 4 of them failed (an observed failure rate of about 57%), the circuit breaker will not yet use that rate to open the circuit. Only when the 8th result is recorded does it have enough samples to evaluate.

`minimumNumberOfCalls` is neither the number of requests since application startup nor the number of calls permitted in the `HALF_OPEN` state. It is the sample threshold in the active statistical window. As the window slides, older results leave the window one by one and new results enter; evaluation is always based on the samples currently inside that window.

## 2. When evaluation starts with a count-based window

With `COUNT_BASED`, `slidingWindowSize` is the number of most recent calls kept in the window. For example, `slidingWindowSize: 20` means the statistical window holds up to the 20 most recent results.

If `minimumNumberOfCalls` is smaller than the window size, the circuit breaker does not need to wait until the window is full to start evaluating. It can begin as soon as the number of recorded results reaches the minimum threshold. Once the window is full, each new incoming result replaces the oldest result; rates are updated based on the remaining data in the window.

Example with a 20-call window, a minimum threshold of 8, and a failure threshold of 50%:

| Recorded results in the window | Failed | Succeeded | Observed failure rate | Are rates evaluated? |
|---:|---:|---:|---:|---|
| 5 | 3 | 2 | 60% | No, fewer than 8 samples |
| 7 | 4 | 3 | 57.1% | No, fewer than 8 samples |
| 8 | 4 | 4 | 50% | Yes, rate reaches open-circuit threshold |
| 9 | 4 | 5 | 44.4% | Yes, rate below 50% threshold |

In the third row, when the 8th result is recorded, the circuit breaker has enough samples and the failure rate reaches 50%, so it can transition from `CLOSED` to `OPEN`. The table illustrates when enough samples are reached; actual behavior also depends on which exceptions are configured as failures, how slow calls are evaluated, and instance options.

With a count-based window, you should ensure `minimumNumberOfCalls` is not larger than `slidingWindowSize`. If the minimum threshold exceeds the maximum number of elements in the window, the window can never hold enough samples to start evaluating.

## 3. When evaluation starts with a time-based window

With `TIME_BASED`, `slidingWindowSize` is the window length in seconds. For example, `slidingWindowSize: 10` means the circuit breaker examines results from the last 10 seconds. `minimumNumberOfCalls` is still a minimum number of calls, not a duration.

Suppose you configure a 10-second window and `minimumNumberOfCalls: 20`:

- If only 12 results have been recorded in the last 10 seconds, the circuit breaker does not yet have enough samples to evaluate rates.
- Once the number of results in the window reaches 20, the circuit breaker begins evaluating.
- When traffic drops and old results expire from the window one by one, the number of available samples can fall below 20. At that point there is no longer enough data in the window to perform a new rate evaluation.

The key point to note is that traffic must be high enough within the window's time span itself. If an instance receives only one call per second on average, a 10-second window is unlikely to accumulate 20 results. The circuit breaker may remain `CLOSED` without enough samples to evaluate the failure rate, even while the dependent service is having problems.

## 4. Configuration in Resilience4j

The following example uses a count-based window for the inventory service:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 8
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 15s
        permittedNumberOfCallsInHalfOpenState: 3
```

In this configuration:

- `slidingWindowSize: 20` keeps outcomes of up to the 20 most recent calls.
- `minimumNumberOfCalls: 8` requires at least 8 results in the window before calculating rates.
- `failureRateThreshold: 50` sets the failure rate threshold at 50%.
- `slowCallDurationThreshold: 2s` defines calls taking 2 seconds or longer as slow calls.
- `slowCallRateThreshold: 50` sets the slow call rate threshold at 50%.
- `waitDurationInOpenState: 15s` specifies the wait duration in `OPEN` before transitioning to the trial phase.
- `permittedNumberOfCallsInHalfOpenState: 3` limits the number of trial calls permitted in `HALF_OPEN`.

If you want time-based evaluation, you can change the two window properties as follows:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 50
```

The second example requires at least 20 results within a 10-second window. You should choose values suited to the instance's actual traffic and desired incident detection latency.

## 5. Distinguishing Sample Thresholds from Related Parameters

The properties below are often configured together, yet serve different roles:

| Property | Role | Question answered |
|---|---|---|
| `slidingWindowType` | Selects a count-based or time-based window. | Is the window measured by calls or by seconds? |
| `slidingWindowSize` | Defines the maximum number of elements or time length of the window. | How many recent calls or recent seconds should be considered? |
| `minimumNumberOfCalls` | Defines the minimum number of results required in the window before evaluating rates. | When are there enough samples to begin evaluation? |
| `failureRateThreshold` | Defines the failure rate that causes the circuit breaker to open. | What percentage of failed calls is unacceptable? |
| `slowCallRateThreshold` | Defines the slow call rate that causes the circuit breaker to open. | What percentage of slow calls is concerning? |
| `permittedNumberOfCallsInHalfOpenState` | Limits the number of trial calls when the circuit is in `HALF_OPEN`. | After waiting, how many calls are permitted to test recovery? |

In particular, `minimumNumberOfCalls` and `permittedNumberOfCallsInHalfOpenState` are not interchangeable. The first controls when rates are evaluated in the window while the circuit breaker is `CLOSED`. The second limits the number of trial calls after the circuit breaker has been `OPEN` and transitions to `HALF_OPEN`.

## 6. How to Choose the Minimum Number of Samples

There is no single `minimumNumberOfCalls` value that suits every service. The choice must balance sample reliability against incident detection speed.

**If set too low**, a few random failures can spike the failure rate. The circuit breaker easily opens due to short-term noise, especially on services with low or uneven traffic.

**If set too high**, the circuit breaker takes a long time to accumulate enough results. When a dependent service first begins failing, calls continue to be sent while waiting for enough samples. With a time-based window, an overly high threshold can also prevent the circuit from ever getting enough samples if traffic falls short.

When choosing a value, consider:

1. **Per-instance traffic:** each instance typically has its own circuit breaker and statistical window. Use the actual traffic per instance, not just cluster-wide total traffic.
2. **Traffic volatility:** a service with bursty traffic needs to be evaluated with a window suited to its activity cycle. A time window that is too short may frequently lack samples between traffic bursts.
3. **Failure sensitivity:** critical dependencies such as payments may need fast incident detection, yet must still avoid opening the circuit over a single unrepresentative failure.
4. **Detection time target:** estimate the time needed for an instance to accumulate enough samples. The minimum threshold and window size must allow detection within an acceptable timeframe.
5. **Failure and latency characteristics:** in addition to failure rate, choose the slow call threshold based on response times the business can tolerate.

With a count-based window, a `minimumNumberOfCalls` smaller than the window size enables early evaluation before the window is full. With a time-based window, estimate how many calls can occur in the selected interval. If the minimum sample count cannot be met under normal operating conditions, revisit both the time size and the sample threshold.

## 7. Recorded Exceptions and Statistical Samples

The number of samples used for evaluation depends on how the circuit breaker classifies outcomes. Successful calls and calls recorded as failures contribute to statistics. Exceptions configured as *ignored* are counted as neither successes nor failures, so not every thrown exception should automatically be assumed to increase the failure sample count.

For example, an input validation error sent by a user might not reflect the health of the inventory service. If that error type is configured to be ignored, it should not inflate the dependency's failure rate. Conversely, timeouts or connection errors are usually signals that should be recorded if they indicate the dependent service cannot respond.

Therefore, when observing that the circuit breaker does not yet have enough samples, check both traffic volume and exception classification rules. Simply increasing test traffic or lowering `minimumNumberOfCalls` without reviewing recording rules can lead to misconfiguration.

## 8. Observing and Testing When Enough Samples Are Reached

To verify the configuration, observe successful calls, failed calls, failure rate, slow call rate, and circuit breaker state via the appropriate Resilience4j, Micrometer, and Spring Boot Actuator metrics. Compare the sample count in the window with `minimumNumberOfCalls` to understand why rates have not been evaluated yet.

A simple test scenario for a count-based configuration with a window of 20 and sample threshold of 8:

1. Send 7 calls, of which 4 fail. Confirm the circuit breaker does not open based on the rate of these 7 samples alone because the minimum threshold has not been reached.
2. Send the 8th call and produce a successful result. The failure rate is now 4/8 = 50%; if the failure threshold is 50%, confirm the circuit breaker transitions to `OPEN`.
3. Attempt another call while the circuit is `OPEN`; confirm the call is rejected early and the fallback or error is handled properly.
4. After the wait duration, confirm the circuit breaker transitions to `HALF_OPEN` and permits only the configured number of trial calls.
5. Let the trial calls succeed to confirm the circuit breaker can return to `CLOSED`.

When testing a time-based window, control both the number of calls and the timing of when they are sent. Sending 20 calls spread outside a 10-second window is not equivalent to having 20 results within the last 10 seconds. Testing should accurately reflect the traffic rate an instance can receive in a real environment.

In operations, if the circuit breaker frequently stays `CLOSED` despite dependency failures, inspect the sample count in the window, sample accumulation time, ignored exception types, and per-instance traffic levels. If the circuit opens too often, review overly small sample sizes, random error spikes, and the failure threshold. Adjust one parameter at a time in a controlled manner and re-observe the metrics to avoid weakening protection.
