# Testing Count-Based and Time-Based Sliding Windows

Resilience4j Circuit Breaker uses a sliding window to aggregate recent call outcomes, then computes the failure rate and slow call rate. The two common window types are COUNT_BASED and TIME_BASED. Testing must confirm that the window retains the right scope of data, evaluates rates only once the minimum number of samples is reached, and transitions state according to the configured thresholds.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, testing both window types verifies that service protection configurations behave properly under realistic traffic. You need to check successful outcomes, failures, slow calls, eviction of data from the window, and the CLOSED/OPEN/HALF_OPEN states. Tests should control timing and call ordering so that results remain stable and easy to explain.

## 1. Two Window Types Have Different Units

| Type | Meaning of `slidingWindowSize` | Data retained |
| --- | --- | --- |
| `COUNT_BASED` | Number of most recent completed calls | The N most recent outcomes |
| `TIME_BASED` | Number of seconds in the observation interval | Outcomes within the last N seconds, aggregated by time buckets |

Example:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-count:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
      inventory-time:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
~~~

With `inventory-count`, the window retains up to the 20 most recent call outcomes. With `inventory-time`, the window observes the last 10 seconds; the size 10 here means 10 seconds, not 10 requests.

COUNT_BASED fits cases where you want to evaluate by sample count regardless of request rate. TIME_BASED fits cases where you need to evaluate health over a fixed time span even as traffic fluctuates.

## 2. Parameters to Check Alongside the Sliding Window

Checking `slidingWindowSize` alone is not enough. The following parameters determine when the Circuit Breaker evaluates and transitions state:

| Property | Role during testing |
| --- | --- |
| `slidingWindowType` | Chooses a count-based or time-based window |
| `slidingWindowSize` | Specifies the sample count or duration of the time span |
| `minimumNumberOfCalls` | Minimum outcomes before computing rates |
| `failureRateThreshold` | Failure percentage threshold to open the circuit |
| `slowCallDurationThreshold` | Duration above which a call is considered slow |
| `slowCallRateThreshold` | Slow-call percentage threshold to open the circuit |
| `waitDurationInOpenState` | Duration the circuit stays OPEN before allowing recovery probes |
| `permittedNumberOfCallsInHalfOpenState` | Number of trial calls allowed in HALF_OPEN |

Example configuration used for testing:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-test:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 2s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

Small values make it quick to reproduce behavior in tests. They are meant for test configurations only; do not copy them verbatim into production without evaluating dependency traffic and latency.

## 3. Checking minimumNumberOfCalls

`minimumNumberOfCalls` prevents the Circuit Breaker from making decisions on too few samples. For example, suppose a window has size 10 and a 50% failure threshold, yet only 3 calls occur and all 3 fail. The observed rate is 100%, yet the Circuit Breaker will not open if `minimumNumberOfCalls` is 5.

Test scenario:

1. Create a Circuit Breaker with window size 10, minimum 5 calls, and a 50% failure threshold.
2. Record 3 failed outcomes.
3. Verify that the state remains CLOSED because 5 samples have not been reached yet.
4. Record 2 more failed outcomes.
5. Verify that the failure rate reaches 100% across 5 samples and the circuit transitions to OPEN.

When testing, confirm the number of recorded calls using the instance's metrics. Exceptions configured to be ignored are not counted as a success or failure outcome in the window. Calls rejected while the circuit is OPEN are also not new calls to the dependency to be added as samples.

## 4. Testing COUNT_BASED with JUnit

You can record outcomes directly on the Circuit Breaker via `onSuccess` and `onError`. This is useful for testing window logic without depending on a real HTTP server or client:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CountBasedWindowTest {
    @Test
    void opensOnlyAfterMinimumNumberOfCalls() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(4)
                .minimumNumberOfCalls(4)
                .failureRateThreshold(50)
                .build();

        CircuitBreaker breaker =
                CircuitBreaker.of("inventory-count-test", config);

        breaker.onError(10, TimeUnit.MILLISECONDS,
                new IOException("connection failed"));
        breaker.onError(10, TimeUnit.MILLISECONDS,
                new IOException("connection failed"));
        breaker.onSuccess(10, TimeUnit.MILLISECONDS);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

        breaker.onSuccess(10, TimeUnit.MILLISECONDS);

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
~~~

After 3 outcomes, the Circuit Breaker does not yet have enough samples to evaluate. The fourth outcome satisfies `minimumNumberOfCalls`; at that point 2 out of 4 calls have failed, so the failure rate is 50%, reaching the threshold and causing the circuit to transition to OPEN.

`onSuccess` and `onError` simulate the completed outcome of a call. In integration tests, you can replace them with real calls via `executeSupplier`, `executeCallable`, or an appropriate decorator to also verify the HTTP client, timeouts, and exception classification.

## 5. Checking Old-Outcome Eviction from a COUNT_BASED Window

COUNT_BASED retains only the N most recent outcomes. When a new outcome enters a full window, the oldest outcome is evicted from the statistics.

Example with window size 4, `minimumNumberOfCalls` equal to 4, and a 50% failure threshold:

| Order | New outcome | Four outcomes in window after recording | Failure rate |
| ---: | --- | --- | ---: |
| 1 | Success | Not enough samples | Not evaluated |
| 2 | Success | Not enough samples | Not evaluated |
| 3 | Success | Not enough samples | Not evaluated |
| 4 | Success | Success, success, success, success | 0% |
| 5 | Failure | Success, success, success, failure | 25% |
| 6 | Failure | Success, success, failure, failure | 50% |

After the fifth outcome, the first success has left the window. After the sixth outcome, the window holds two successes and two failures, so the failure rate reaches 50% and the Circuit Breaker opens the circuit.

Corresponding test:

~~~java
@Test
void evictsOldestResultWhenCountWindowIsFull() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("inventory-eviction-test", config);

    for (int i = 0; i < 4; i++) {
        breaker.onSuccess(5, TimeUnit.MILLISECONDS);
    }
    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

    breaker.onError(5, TimeUnit.MILLISECONDS, new IOException("first failure"));
    assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());

    breaker.onError(5, TimeUnit.MILLISECONDS, new IOException("second failure"));
    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
}
~~~

This test verifies that the window slides by call count, rather than computing the rate over the entire history since the instance was created.

## 6. Testing a TIME_BASED Window

With TIME_BASED, each bucket represents a time slice and the window retains only buckets falling within the configured number of seconds. For example, `slidingWindowSize: 5` tracks approximately the last 5 seconds. As time advances, old buckets expire and their statistics no longer contribute to the total.

Example configuration:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-time-test:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 5
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 200ms
        slowCallRateThreshold: 50
~~~

The test scenario should focus on three points:

1. Record several outcomes within the same time interval and verify that they are counted in the window.
2. Advance time past the interval containing old outcomes, then trigger or read a statistics snapshot to confirm that expired buckets are no longer counted.
3. Record new outcomes in the current bucket and verify that the rate is calculated over the still-valid buckets.

For stable tests, prefer controlling time with a mock clock if the Resilience4j version in use supports configuring a clock for the Circuit Breaker. If clock injection is unavailable, use integration tests with a short window and Awaitility to wait for statistical conditions to change; avoid relying on a fixed `Thread.sleep` and assuming the bucket rotated at that exact instant.

Checklist for TIME_BASED configuration:

- `slidingWindowSize` is in seconds, not number of requests.
- Multiple calls within the same time bucket are aggregated in that bucket.
- Old outcomes leave the window when their corresponding bucket expires.
- `minimumNumberOfCalls` must still be met before rates are used to open the circuit.
- Low traffic can prevent the time window from accumulating enough samples to evaluate.

## 7. Checking Differences When Traffic Changes

COUNT_BASED and TIME_BASED can yield different results when the request rate changes:

| Scenario | COUNT_BASED | TIME_BASED |
| --- | --- | --- |
| Traffic spike | Window of N calls spans a shorter time interval | Window keeps the same number of seconds but holds more calls |
| Sharp traffic drop | Window of N calls stretches over a longer time | Window retains only data within the chosen seconds |
| Need to evaluate the last N calls | Directly suitable | Does not guarantee exactly N calls |
| Need to evaluate the last 30 seconds | Actual time span varies with traffic | Directly suitable |

A good test should generate at least two traffic cadences: a burst with many calls in one second and a sparse cadence with few calls over several seconds. Observe the buffered outcome count and failure rate to confirm both window types respond according to their units.

## 8. Testing Slow Call Rate Separately from Failure Rate

A slow call can still complete successfully. Therefore, failure rate and slow call rate must be tested independently.

Example:

~~~java
@Test
void opensWhenSlowCallRateReachesThreshold() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(75)
            .slowCallDurationThreshold(java.time.Duration.ofMillis(100))
            .slowCallRateThreshold(50)
            .build();

    CircuitBreaker breaker =
            CircuitBreaker.of("inventory-slow-test", config);

    breaker.onSuccess(200, TimeUnit.MILLISECONDS);
    breaker.onSuccess(250, TimeUnit.MILLISECONDS);
    breaker.onSuccess(20, TimeUnit.MILLISECONDS);
    breaker.onSuccess(30, TimeUnit.MILLISECONDS);

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
}
~~~

Out of 4 calls, 2 calls are slower than 100 ms, yet all 4 succeed. The failure rate is 0%, while the slow call rate is 50%. Because the slow call threshold is 50%, the Circuit Breaker opens due to the slow call rate reaching the threshold, not because of exceptions.

This test helps catch configurations that only track exception errors while ignoring latency degradation. Choose clear durations and sample counts to avoid depending on the speed of the test runner; for example, using `onSuccess(duration, unit)` records deterministic durations without actually waiting in real time.

## 9. Checking States After the Window Reaches the Threshold

Once enough samples exist and a rate hits the threshold, the Circuit Breaker transitions from CLOSED to OPEN. When OPEN, new calls are rejected with `CallNotPermittedException` without running the supplier. After `waitDurationInOpenState`, the circuit can transition to HALF_OPEN and permit only the configured number of trial calls.

Points to verify:

| State | Behavior to check |
| --- | --- |
| CLOSED | Calls are executed and outcomes are entered into the window |
| OPEN | New calls are rejected; the supplier is not invoked |
| HALF_OPEN | Only the permitted number of trial calls pass through |
| Return to CLOSED | Trial calls meet requirements within thresholds |
| Return to OPEN | Trial calls continue failing or exceeding slow thresholds |

Do not check state transitions merely by asserting any arbitrary exception. Assert the current state, how many times the supplier was invoked, and the rejected exception type. This distinguishes genuine errors from the downstream dependency from the Circuit Breaker proactively blocking requests.

## 10. Testing Ignored Exceptions and Recorded Exceptions

The sliding window should only reflect outcomes configured to participate in statistics. Resilience4j allows ignoring certain business exceptions, such as a nonexistent product, so they do not inflate the failure rate of the Inventory service.

Example configuration:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .ignoreExceptions(InventoryNotFoundException.class)
        .build();
~~~

When testing, record an `InventoryNotFoundException` and verify that the buffered call count does not increment as a success or failure outcome. Then record enough counted outcomes and verify that the rate is computed over those outcomes.

Do not confuse ignored exceptions with exceptions treated as successes. Ignored errors neither contribute to the failure rate nor increase the sample count like a successful call. Rejections caused by an OPEN circuit are also not dependency call outcomes to be added to the window.

## 11. Structuring Tests to Avoid Interdependent Results

Each test should create its own Circuit Breaker instance or use a dedicated registry for that test. This prevents window history from a previous test from altering the outcome of the next test.

Some principles:

- Use a distinct instance name per test or create a fresh instance from a test configuration.
- Do not share a mutable Circuit Breaker across multiple tests running in parallel.
- Use `onSuccess` and `onError` to test statistics deterministically when testing the HTTP client is not required.
- Use a mock server or fake client when you need to verify actual exceptions reaching the Circuit Breaker.
- With TIME_BASED, control the clock if the version supports it; otherwise wait for conditions via bounded polling instead of hard-coded sleeps.
- Set a short `waitDurationInOpenState` in state-transition tests and keep production configuration separate.
- Verify state and metrics after each stage, not just the final returned result.

Do not share the application environment's singleton registry across independent tests if tests can mutate the state of the same instance. A shared registry is desirable in production runtime, whereas tests need data isolation for stable repeatability.

## 12. Common Mistakes When Testing Sliding Windows

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Confusing TIME_BASED size with request count | Test scenario produces the wrong number of samples | Explicitly note seconds as the unit in tests |
| Not checking minimumNumberOfCalls | Expecting the circuit to OPEN prematurely | Generate enough counted outcomes before asserting |
| Sharing one instance across multiple tests | Window history makes tests order-dependent | Create a separate instance per test |
| Checking only failure rate | Misses degradation caused by slow calls | Test slow call threshold and slow call rate |
| Using fixed Thread.sleep for TIME_BASED | Tests become flaky at bucket boundaries | Use a controllable clock or Awaitility |
| Treating an ignored exception as a success | Miscounts samples and rates | Verify ignored exceptions do not contribute to the window |
| Continuing to invoke supplier after circuit OPENs | Test fails to distinguish rejection from dependency errors | Assert supplier is not called when OPEN |
| Checking only the API return value | Unclear whether window or state updated properly | Inspect state, metrics, and invocation counts |

## 13. Minimum Set of Test Scenarios

Before accepting a configuration, include these scenarios:

1. COUNT_BASED below `minimumNumberOfCalls`: the circuit remains CLOSED even with a temporarily high failure rate.
2. COUNT_BASED with enough samples and rate reaching threshold: the circuit transitions to OPEN.
3. COUNT_BASED receiving new outcomes: the oldest outcome is evicted from the window.
4. TIME_BASED with outcomes inside the observation interval: outcomes are counted in the corresponding bucket.
5. TIME_BASED with old buckets expiring: outcomes outside the time interval no longer contribute to statistics.
6. Slow call rate reaching threshold while failure rate is low: the circuit can still OPEN due to slow calls.
7. Ignored exceptions: do not increase the failure rate or counted sample size.
8. OPEN rejecting calls: the supplier does not run and rejections are not mistaken for new dependency failures.
9. HALF_OPEN probing: only the permitted number of calls passes through.
10. Probe outcomes recovering or failing: the circuit transitions to CLOSED or OPEN as configured.

## 14. Test Execution Procedure

When testing sliding windows in a Spring Cloud module, follow this sequence:

1. Select the COUNT_BASED or TIME_BASED window type according to the observation goal.
2. Set the window size, minimumNumberOfCalls, and failure/slow thresholds to reproduce behavior quickly in tests.
3. Create a fresh Circuit Breaker instance to isolate state.
4. Record successful, failed, and slow outcomes in a deterministic order.
5. Inspect buffered sample count, failure rate, slow call rate, and state after each phase.
6. For COUNT_BASED, confirm old outcomes leave the window as new ones arrive.
7. For TIME_BASED, advance controlled time or wait for bucket expiration using bounded polling.
8. Verify ignored exceptions, rejected calls, and HALF_OPEN state transitions.
9. Run integration tests with an HTTP client to confirm real timeouts and error status codes are recorded accurately.
10. Keep test configuration separate from production configuration and clearly document the unit of every parameter.

Testing count-based windows confirms that the Circuit Breaker always evaluates over the N most recent outcomes; testing time-based windows confirms that old data expires according to the configured seconds. When you also verify `minimumNumberOfCalls`, slow call rate, and state transitions, the development team can trust that Resilience4j opens the circuit at the right time and protects dependent services according to the intended policy.
