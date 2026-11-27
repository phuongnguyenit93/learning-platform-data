# Testing minimumNumberOfCalls and Insufficient-Sample Scenarios

In Resilience4j, a circuit breaker does not decide to open merely because a few errors have occurred. Before calculating the failure rate or slow call rate, the breaker needs to collect the minimum number of outcomes specified by `minimumNumberOfCalls`. If the statistics window does not yet have enough samples, the breaker remains `CLOSED` even if every observed call has failed.

This is intentional behavior to avoid drawing conclusions from too small a sample set. When testing, you need to verify both sides: the breaker does not open when the sample count is below the minimum threshold, and it begins evaluating rates once enough samples are present. You also need to distinguish the insufficient-sample case from a healthy dependency: both can leave the breaker `CLOSED`, but the cause and statistical data are different.

## 1. What Does `minimumNumberOfCalls` Control?

`minimumNumberOfCalls` is the minimum number of calls that must be recorded in the sliding window before Resilience4j calculates the failure rate and slow call rate to decide whether to open the breaker. This value is not a minimum number of errors. Samples can include both successful and failed calls; exceptions configured to be ignored do not contribute to the success/failure sample count.

For example, suppose a configuration has `minimumNumberOfCalls: 5` and `failureRateThreshold: 50`. If the breaker has recorded only three calls and all three failed, it still does not have enough samples to evaluate the failure rate. When the fourth call also fails, there are still fewer than five samples. Only after recording the fifth call does the breaker calculate the failure rate over the samples in the window.

| Samples recorded | Outcomes | Is failure rate evaluated? | Possible state |
|---:|---|---|---|
| 1 | 1 failure | Not yet | `CLOSED` |
| 2 | 2 failures | Not yet | `CLOSED` |
| 3 | 3 failures | Not yet | `CLOSED` |
| 4 | 4 failures | Not yet | `CLOSED` |
| 5 | 5 failures | Yes, 100% | Transitions to `OPEN` if threshold is 50% |

In this example, the breaker does not discard the first failures. They are still recorded in the statistics and can be observed through the buffered call count and failure count. Only the rate-based decision is deferred until enough samples are collected.

## 2. Distinguishing slidingWindowSize and minimumNumberOfCalls

These two properties are related but not interchangeable:

- `slidingWindowSize` defines the size of the statistics window.
- `minimumNumberOfCalls` defines the minimum number of samples that must exist in the window before calculating the failure rate or slow call rate.

For a `COUNT_BASED` window, `slidingWindowSize` is the number of most recent calls kept in the window. For a `TIME_BASED` window, it represents the number of time buckets forming the window interval. `minimumNumberOfCalls` is still the minimum number of outcomes required within that window.

Example configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 60
        slowCallDurationThreshold: 800ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
```

In this configuration, the breaker keeps at most the 10 most recent outcomes but only begins evaluating rates after there are at least 4 valid samples in the window. Once enough samples exist, if the failure rate meets or exceeds 60%, the breaker can transition to `OPEN`. The slow call rate also requires enough samples before it is used for evaluation.

Do not set `minimumNumberOfCalls` too high relative to actual traffic. If an operation receives only a few calls over a long period, the breaker may rarely reach the sample threshold. Conversely, setting the value too low allows a few isolated errors to open the circuit prematurely.

## 3. Undetermined Failure Rate When Samples Are Insufficient

Resilience4j represents an uncomputable failure rate with the value `-1.0` in the breaker's metrics when the sample count has not yet reached `minimumNumberOfCalls`. This value means **not enough data to evaluate**, not that the failure rate is minus one percent or that the system has no errors.

Useful metrics when checking insufficient-sample scenarios include:

- `getNumberOfBufferedCalls()`: the number of samples currently in the sliding window.
- `getNumberOfFailedCalls()`: the number of failed calls currently held in the window.
- `getNumberOfSuccessfulCalls()`: the number of successful calls currently held in the window.
- `getFailureRate()`: the failure rate, or `-1.0` when samples are insufficient.
- `getState()`: the current state of the breaker.

For example, if there are three failures and `minimumNumberOfCalls` is five, the metrics can show three buffered calls, three failures, zero successes, a failure rate of `-1.0`, and the state still `CLOSED`. This data differs from the case with five successful calls, a failure rate of 0%, and the state `CLOSED`.

## 4. Testing Directly with JUnit 5

You can test Resilience4j's behavior without starting a Spring context by creating a breaker with a small configuration. This keeps tests focused on the rules of `minimumNumberOfCalls` and avoids network timing dependencies.

The example below uses a count-based window of 10 samples, requiring a minimum of 4 samples and a 60% failure threshold:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class MinimumNumberOfCallsTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(10)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(60)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("inventory-test", config);
    }

    private void fail(CircuitBreaker breaker) {
        assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("inventory unavailable");
                })
        );
    }

    @Test
    void staysClosedWhenThereAreFewerSamplesThanMinimum() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        fail(breaker);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
        assertEquals(3, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(3, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(-1.0f, breaker.getMetrics().getFailureRate(), 0.001f);
    }

    @Test
    void evaluatesFailureRateWhenMinimumSamplesAreReached() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        fail(breaker);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

        assertEquals("ok", breaker.executeSupplier(() -> "ok"));

        assertEquals(4, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(3, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(75.0f, breaker.getMetrics().getFailureRate(), 0.001f);
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }

    @Test
    void remainsClosedWhenRateIsBelowThresholdAfterMinimumSamples() {
        CircuitBreaker breaker = newBreaker();

        fail(breaker);
        fail(breaker);
        breaker.executeSupplier(() -> "first success");
        breaker.executeSupplier(() -> "second success");

        assertEquals(4, breaker.getMetrics().getNumberOfBufferedCalls());
        assertEquals(2, breaker.getMetrics().getNumberOfFailedCalls());
        assertEquals(50.0f, breaker.getMetrics().getFailureRate(), 0.001f);
        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    }
}
```

The three tests illustrate three scenarios:

1. With three failure samples and fewer than the four required, the breaker stays `CLOSED` and the failure rate is undetermined.
2. When the fourth sample is recorded, the failure rate is 75%, exceeding the 60% threshold, so the breaker transitions to `OPEN`.
3. When four samples are collected but the failure rate is 50%, below the 60% threshold, the breaker remains `CLOSED`.

The tests use synchronous suppliers and deterministic exceptions, so they do not depend on DNS, HTTP servers, or real wait times. When adding them to a project, include the Resilience4j CircuitBreaker and JUnit Jupiter dependencies matching your project's dependency management.

## 5. Why Three Consecutive Failures May Not Open the Breaker

Suppose a production configuration has:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      pricing:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
```

If the `pricing` instance has just been created and the first three calls all time out, the breaker still does not have 10 samples to evaluate the failure rate. It can continue allowing new calls through to the pricing service until enough samples are collected. This is the trade-off between avoiding decisions based on too little data and detecting failures quickly.

Under high traffic, 10 samples may be collected in a short time. Under low traffic, reaching 10 samples can take many seconds or minutes. Therefore, the same `minimumNumberOfCalls` value can produce different detection times across different dependencies.

Do not interpret the `CLOSED` state during the insufficient-sample phase as "the dependency is healthy." It only indicates that the breaker does not yet have enough statistical evidence to open the circuit. You should read it alongside sample count, error count, latency, and HTTP client metrics.

## 6. Impact of COUNT_BASED and TIME_BASED

### COUNT_BASED

With `COUNT_BASED`, the window holds at most the `slidingWindowSize` most recent calls. When a new call arrives, the oldest sample is evicted from the window. `minimumNumberOfCalls` specifies the minimum number of outcomes that must be recorded before evaluating the rate.

For example, suppose a window has size 10 and requires at least 4 samples. After three calls, there are not enough samples yet. After the fourth call, rate evaluation begins. Once the window has 10 samples, each new call replaces an old sample and the rate is calculated over the latest set of samples.

### TIME_BASED

With `TIME_BASED`, the window covers a time span divided into buckets. Outcomes within that time span are aggregated; older samples gradually leave the window as time passes. `minimumNumberOfCalls` still requires enough calls within the window before evaluating the rate.

For example, suppose a 10-second window and `minimumNumberOfCalls: 5`. If only three requests occur in 10 seconds and all three fail, the breaker does not have enough samples to compute the failure rate. Under low traffic, `TIME_BASED` does not automatically solve insufficient samples; it only bounds the time span over which samples are considered.

| Window type | Size represents | Common insufficient-sample case |
|---|---|---|
| `COUNT_BASED` | Number of most recent calls | New instance or low-traffic operation that has not accumulated enough calls yet |
| `TIME_BASED` | Number of time buckets | Traffic within the observation interval is too low to reach `minimumNumberOfCalls` |

## 7. Testing Insufficient Samples with TIME_BASED

With `TIME_BASED`, you should verify the sample count within a defined time span. You do not need to rely on waiting for a real service to fail; you can call the breaker directly with a supplier that throws exceptions to generate controlled samples.

Example configuration:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.TIME_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .build();

CircuitBreaker breaker = CircuitBreaker.of("low-traffic", config);
```

If only three failed calls are made within the window period, verify that the breaker remains `CLOSED` and the failure rate is undetermined. Once enough samples are added, the rate begins to be evaluated. For stable tests, avoid long `Thread.sleep()` calls or assuming exact bucket rotation moments. If you need to test time boundaries, use the custom clock capability supported by the Resilience4j version in use, or test at the integration level with controlled time.

## 8. Do Ignored Exceptions Affect minimumNumberOfCalls?

Resilience4j distinguishes exceptions recorded as failures, exceptions treated as successes, and ignored exceptions. Ignored exceptions are not counted toward the failure rate or success rate, so they do not help reach the minimum number of samples.

For example, configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        ignoreExceptions:
          - com.example.inventory.InvalidSkuException
```

If three calls throw `InvalidSkuException` and one call times out and is recorded as a failure, do not treat that as four success/failure samples. Ignored exceptions do not contribute to the sample count used for rate calculation. Consequently, the total number of calls at the HTTP layer or the number of supplier executions may exceed the number of samples used for the failure rate.

When testing, inspect the total calls executed, buffered samples, successes, failures, and ignored counts separately. Do not simply count total requests and conclude that the breaker has reached `minimumNumberOfCalls`.

## 9. Testing That Fallbacks Do Not Distort Breaker Statistics

A fallback is typically executed after a protected call fails. If the fallback is applied outside the breaker, the breaker records the supplier's exception before the caller receives the fallback result. The fallback result does not turn a failed call into a breaker success.

Example:

```java
String result;
try {
    result = breaker.executeSupplier(() -> {
        throw new IllegalStateException("pricing unavailable");
    });
} catch (IllegalStateException error) {
    result = "cached-price";
}
```

In this example, the breaker records the supplier failure. Outer code catches the exception and produces the fallback. When testing, verify that `getNumberOfFailedCalls()` increases, rather than `getNumberOfSuccessfulCalls()` increasing because the fallback returned a value to the caller.

If you catch the exception inside the supplier and return the fallback as a normal result before the breaker observes the error, the breaker may record a success. Exception-handling structure therefore directly affects the meaning of the statistics.

## 10. Common Mistakes When Writing Tests

| Testing mistake | Why it is wrong | How to fix |
|---|---|---|
| Expecting the breaker to open right after the first failure | `minimumNumberOfCalls` has not been reached | Generate enough samples before checking the threshold |
| Asserting only that state is `CLOSED` | Does not distinguish insufficient samples from a low failure rate | Assert buffered calls, success/failure counts, and failure rate |
| Using `slidingWindowSize` in place of `minimumNumberOfCalls` | The two properties serve different roles | Configure and verify both separately |
| Counting all requests including ignored ones | Ignored exceptions do not participate in failure/success rates | Check ignored metrics and actual buffered sample count |
| Using a real HTTP server for simple unit tests | Slow tests that depend on network conditions | Use deterministic suppliers to test the state machine |
| Using `sleep` to wait out a `TIME_BASED` window | Produces flaky tests | Control the clock or test with intentional durations |
| Treating `CLOSED` as proof of a healthy dependency | There may not be enough samples to evaluate yet | Read failure rate, sample count, and latency alongside state |
| Putting the fallback inside the supplier while expecting the breaker to record a failure | The breaker may only see a normal return value | Place the fallback outside the protected boundary or configure for desired semantics |

## 11. Testing Configuration in Spring Boot

Unit tests that construct `CircuitBreaker` directly verify Resilience4j's rules. However, a Spring Cloud application also needs to verify that the actual configuration binds to the right ID. An integration test can load a test configuration and retrieve the breaker from the registry or call a Spring-managed gateway.

Example test configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-test:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 4
        failureRateThreshold: 60
```

In an integration test, verify that the `inventory-test` instance has the expected effective configuration. Then trigger three failures, check that the state remains `CLOSED` and the failure rate is undetermined; add a fourth sample to verify that rate evaluation begins. If a gateway uses `CircuitBreakerFactory`, call the exact ID from the gateway to ensure the name in code matches the name in configuration.

Do not check the YAML file merely by reading strings. What must be verified is that Spring Boot loaded the properties and Resilience4j created the instance with that configuration. You can use the registry/metrics or the breaker's behavior to confirm this.

## 12. Choosing minimumNumberOfCalls Based on Traffic

`minimumNumberOfCalls` should be chosen based on the traffic of each breaker instance, not total application traffic. A per-operation breaker may receive less traffic than a per-dependency breaker. If split too finely, each instance might never collect enough samples within the timeframe in which the system needs to detect an incident.

Consider:

- Average and off-peak traffic for each dependency/operation.
- Sliding window size and type.
- Acceptable time to collect enough samples.
- Tolerable failure rate before opening the circuit.
- Risk of continuing to call a failing dependency.
- Other protection mechanisms such as connect/read timeouts, overall deadlines, bulkheads, and rate limiters.

If traffic is low, do not lower `minimumNumberOfCalls` mechanically. You can group operations that share the same failure domain to increase sample volume, use timeouts and bulkheads to limit impact while samples are scarce, or choose an appropriate health-signal strategy. A circuit breaker can only evaluate rates from the samples actually recorded.

## 13. Procedure for Testing minimumNumberOfCalls

When writing tests for a breaker, follow this sequence:

1. Choose `slidingWindowType` and `slidingWindowSize` appropriate for the test.
2. Set `minimumNumberOfCalls` small enough to generate deterministic samples.
3. Set `failureRateThreshold` clearly, avoiding testing right on the boundary unless specifically testing the threshold comparison operator.
4. Generate fewer samples than `minimumNumberOfCalls`, including controlled failures.
5. Verify that the breaker remains `CLOSED`, the buffered call count is accurate, and the failure rate equals `-1.0` while samples are insufficient.
6. Generate additional calls to reach the minimum; verify that the failure rate is calculated and the state changes if the rate meets the threshold.
7. Create a case with enough samples but a rate below the threshold; verify that the breaker stays `CLOSED`.
8. If `ignoreExceptions` is configured, verify that ignored exceptions do not increase the success/failure sample count.
9. If a fallback exists, verify that the breaker still records the original failure when the fallback is handled outside the supplier.
10. With `TIME_BASED`, test behavior over a time interval and avoid tests relying on nondeterministic sleeps.

`minimumNumberOfCalls` prevents a circuit breaker from making decisions on too little data. When samples are insufficient, the state can remain `CLOSED` and the failure rate is represented as undetermined (`-1.0`). A good test verifies the sample count, success/failure counts, failure rate, and state together, thereby distinguishing a breaker waiting for data from a breaker that has evaluated the dependency as sufficiently stable.
