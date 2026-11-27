# Testing Outcome Sequences to Verify CLOSED-to-OPEN Transitions

A valuable Circuit Breaker test must prove when the circuit changes state, what data causes it to change, and how the next call is handled. Merely testing that a request throws an exception is not enough: a Circuit Breaker has a sliding window, a minimum number of samples, and rate thresholds. The circuit may remain `CLOSED` after one or a few failures, and only transition to `OPEN` once the outcome sequence satisfies the configured conditions.

With Spring Cloud CircuitBreaker using Resilience4j, testing should be done at two layers. Unit tests directly against Resilience4j verify the state machine and sliding window deterministically. Service-layer tests verify that the application actually goes through `CircuitBreakerFactory` or `ReactiveCircuitBreakerFactory`, uses the right instance name, and applies the fallback as expected.

## Conditions for Transitioning from CLOSED to OPEN

In the `CLOSED` state, the Circuit Breaker allows calls through and records outcomes into the sliding window. Two key configurations when testing are:

- `minimumNumberOfCalls`: the minimum number of samples required before calculating the failure rate or slow call rate to decide whether to open the circuit.
- `failureRateThreshold`: the percentage threshold of failures. Once enough samples are collected and the failure rate meets or exceeds the threshold, the Circuit Breaker transitions to `OPEN`.

For a count-based window, `slidingWindowSize` is the number of most recent outcomes retained. The window is not a concurrency limit on simultaneous calls. For a time-based window, the size represents the number of most recent seconds. To test outcome sequences predictably, the example below uses `COUNT_BASED`.

Suppose the configuration is:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: false
```

With four minimum samples and a 50% threshold, the sequence `Success, Failure, Success, Failure` produces a failure rate of exactly 50%. Before the fourth sample, the Circuit Breaker does not yet have enough samples and therefore remains `CLOSED`. When the fourth sample is recorded, the circuit has enough data and reaches the threshold, so it transitions to `OPEN`.

| Call | Outcome | Samples collected | Failure rate | State after call |
|---:|---|---:|---:|---|
| 1 | Success | 1 | Not enough samples | `CLOSED` |
| 2 | Failure | 2 | Not enough samples | `CLOSED` |
| 3 | Success | 3 | Not enough samples | `CLOSED` |
| 4 | Failure | 4 | 2/4 = 50% | `OPEN` |
| 5 | Rejected | No sample added | Unchanged | `OPEN` |

What matters in the test is checking the state after each step, especially before the minimum number of samples is reached and immediately after the threshold is met. If only the final state is checked, the test may miss the circuit opening too early or failing to open at the right time.

## Writing Deterministic Unit Tests with Resilience4j

The example below uses JUnit 5 and AssertJ. `DependencyException` represents a technical failure of a downstream dependency. Each call is executed through the same Circuit Breaker instance so that outcomes are recorded in the same sliding window.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class CatalogCircuitBreakerTest {

    private CircuitBreaker circuitBreaker;

    @BeforeEach
    void setUp() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        circuitBreaker = CircuitBreaker.of("catalog", config);
    }

    @Test
    void opensOnlyAfterMinimumCallsAndFailureRateThresholdAreReached() {
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        // 1: Success
        assertThat(circuitBreaker.executeSupplier(() -> "item-1"))
            .isEqualTo("item-1");

        // 2: Failure
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("catalog unavailable");
        })).isInstanceOf(DependencyException.class);

        // 3: Success; only 3 samples so far, minimumNumberOfCalls = 4 not yet reached.
        assertThat(circuitBreaker.executeSupplier(() -> "item-2"))
            .isEqualTo("item-2");
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.CLOSED);

        // 4: Failure; 2 failures / 4 samples = 50%, circuit must transition to OPEN.
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("catalog still unavailable");
        })).isInstanceOf(DependencyException.class);

        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(circuitBreaker.getMetrics().getNumberOfBufferedCalls())
            .isEqualTo(4);
        assertThat(circuitBreaker.getMetrics().getNumberOfSuccessfulCalls())
            .isEqualTo(2);
        assertThat(circuitBreaker.getMetrics().getNumberOfFailedCalls())
            .isEqualTo(2);
        assertThat(circuitBreaker.getMetrics().getFailureRate())
            .isEqualTo(50.0f);
    }

    @Test
    void rejectsNextCallWithoutInvokingDependencyAfterOpening() {
        recordFourResultsToOpenCircuit();
        AtomicInteger dependencyCalls = new AtomicInteger();

        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            dependencyCalls.incrementAndGet();
            return "should-not-run";
        })).isInstanceOf(CallNotPermittedException.class);

        assertThat(dependencyCalls).hasValue(0);
        assertThat(circuitBreaker.getState())
            .isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(circuitBreaker.getMetrics().getNumberOfNotPermittedCalls())
            .isEqualTo(1);
    }

    private void recordFourResultsToOpenCircuit() {
        circuitBreaker.executeSupplier(() -> "one");
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("first failure");
        })).isInstanceOf(DependencyException.class);
        circuitBreaker.executeSupplier(() -> "two");
        assertThatThrownBy(() -> circuitBreaker.executeSupplier(() -> {
            throw new DependencyException("second failure");
        })).isInstanceOf(DependencyException.class);
    }

    static class DependencyException extends RuntimeException {
        DependencyException(String message) {
            super(message);
        }
    }
}
```

The first test verifies both the outcome sequence and the metrics. The second test verifies the protective effect after the circuit opens: the fifth call is rejected with `CallNotPermittedException`, the supplier is not executed, and the number of not-permitted calls increases. Rejected calls do not become success or failure samples in the sliding window.

In a real project, place the test class and exception in the appropriate package; add the JUnit 5 and AssertJ test dependencies according to the project's dependency manager. Do not share a Circuit Breaker across tests. Create a new instance in `@BeforeEach` so that outcomes from a previous test do not affect subsequent tests.

## Checking the Failure Rate Calculation

The failure rate is calculated as the number of failed calls divided by the total number of counted samples in the window:

\[
FailureRate = \frac{FailedCalls}{SuccessfulCalls + FailedCalls} \times 100\%
\]

Exceptions configured to be ignored are not included in the denominator. Calls rejected by the Circuit Breaker also do not enter the sliding window. Therefore, do not use the total number of HTTP requests arriving at the application as the denominator for calculating the Circuit Breaker's failure rate.

For example, if a sequence has two successes, one failure, and one ignored exception, only three samples are counted. The failure rate is 1/3, approximately 33.3%. If `minimumNumberOfCalls` is 4, the circuit does not yet have enough samples to decide whether to open based on the rate. An ignored exception is not treated as a success to lower the failure rate.

If `recordExceptions` is declared, keep in mind that an exception not matching the recorded exceptions list may be counted as a success, unless it matches the ignore policy. Inspect the actual exception type thrown by the client; an HTTP client may wrap a connection error in an exception different from the original one.

## Verifying That the Sliding Window Actually Slides

A COUNT_BASED window holds at most the `slidingWindowSize` most recent outcomes. When a new sample arrives and the window is full, the oldest sample is evicted from the statistics. An additional test can prove that the decision to open the circuit is based on the most recent samples, rather than the entire history since application startup.

For example, with a window size of 4 samples and a 50% threshold:

1. Record `Failure, Failure, Success, Success`: the failure rate is 50%, and the circuit opens once four samples are reached.
2. In a separate test, reset or create a new Circuit Breaker and record `Success, Success, Success, Failure`: the failure rate is 25%, and the circuit remains `CLOSED` after four samples.
3. With the circuit still `CLOSED`, continue adding `Success`. The window keeps only the four newest samples; the oldest sample is evicted and the failure rate is recalculated over the remaining four samples.

So that tests do not depend on execution order or state from other tests, each scenario should have its own Circuit Breaker. If you need to verify eviction of old samples, assert `getNumberOfBufferedCalls()`, the number of successes/failures, and the failure rate after each new outcome.

## Testing Slow Call Rate Separately from Failure Rate

A Circuit Breaker can open because the rate of slow calls exceeds `slowCallRateThreshold`, even when those calls eventually return a successful result. Therefore, tests that only check exceptions do not cover the latency-based circuit-opening branch.

A slow-call test configuration can use:

```java
CircuitBreakerConfig slowConfig = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(4)
    .minimumNumberOfCalls(4)
    .failureRateThreshold(100)
    .slowCallDurationThreshold(Duration.ofMillis(50))
    .slowCallRateThreshold(50)
    .build();
```

In tests, use a controllable clock or scheduler if the API and integration version support it; otherwise, use a small delay with a sufficient margin above the threshold and avoid depending on exact CI timing. Record four successful calls, of which at least two exceed `slowCallDurationThreshold`. Once enough samples are collected, the slow call rate reaches 50% and the circuit can open even though the failure rate is 0%.

Do not use long `Thread.sleep(...)` calls in unit tests just to wait for the Circuit Breaker to finish `waitDurationInOpenState`. A test for `CLOSED` → `OPEN` does not need to wait out the open-state wait duration. If you need to test `OPEN` → `HALF_OPEN`, configure an intentionally short duration or use the library version's controllable time mechanism.

## Testing the Spring Cloud CircuitBreaker Layer

Unit tests directly against Resilience4j prove the state machine. To confirm that the application uses the right factory and instance, include integration-level service tests. The service should invoke through the `CircuitBreakerFactory` abstraction instead of creating a standalone Circuit Breaker unrelated to the factory:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;

    CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
    }

    Product find(String sku) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.find(sku),
            error -> Product.unavailable(sku));
    }
}
```

In a `@SpringBootTest`, configure the `catalog` instance with a small window and easily reproducible thresholds, mock `CatalogClient` to return a deterministic sequence of outcomes, and call `CatalogService.find(...)` through the Spring bean. The test should verify:

- The service uses the exact configured id `catalog`.
- Client errors pass through the Circuit Breaker before the fallback handles them.
- Once enough samples are collected and the threshold is reached, subsequent calls no longer invoke the mock client.
- The fallback returns the expected contract when the Circuit Breaker rejects calls or the dependency fails.
- A fresh test context creates a fresh instance, without reusing an already-open state from a previous test.

If you need to inspect Resilience4j metrics in an integration test, inject the exact `CircuitBreakerRegistry` used by the backend factory and look up the existing instance. Avoid calling `registry.circuitBreaker("catalog")` in the assertion step unless you have verified that the factory uses that same registry; doing so can create a separate instance and cause the test to inspect the wrong circuit.

With Feign, test through the client interface and a mock HTTP server such as WireMock to control responses, latency, and request count. With a reactive factory, use `StepVerifier` to verify the publisher and the number of subscriptions. Do not block a reactive stream with `.block()` in production code just to make tests synchronous; in tests, use `StepVerifier` to inspect signals naturally.

## Common Mistakes That Make Tests Incorrect

- **Not checking `minimumNumberOfCalls`:** the test expects a single failure to open the circuit even before enough samples are collected.
- **Using a time-based window for tests that need an exact call count sequence:** results depend on execution timing and wall-clock time. Use `COUNT_BASED` when the goal is to verify sample counts.
- **Sharing a Circuit Breaker across tests:** state and sliding window data from a previous test alter the outcome of the next test. Create a new instance for each test.
- **Placing the fallback inside the protected call:** errors are converted into normal results before the Circuit Breaker records them, preventing the test from opening the circuit as expected.
- **Not checking whether the supplier is called after OPEN:** only asserting the exception without verifying that the dependency receives no further requests.
- **Treating `CallNotPermittedException` as a dependency error:** the circuit blocked the call so the client was never invoked; measure rejected calls separately.
- **Relying on long `Thread.sleep` calls:** makes tests slow and flaky. Only test wait duration when that is the specific objective of the test.
- **Reading the wrong registry:** assertions retrieve an instance from a registry different from the factory's registry, so the state does not match the service's behavior.

## Checklist for Testing CLOSED-to-OPEN Transitions

| What to verify | Expected outcome |
|---|---|
| Initial state | `CLOSED` |
| Fewer samples than `minimumNumberOfCalls` | Still `CLOSED`, no rate-based decision yet |
| Minimum samples reached, failure rate below threshold | Still `CLOSED` |
| Failure rate meets or exceeds threshold | Transitions to `OPEN` |
| Call after `OPEN` | Throws `CallNotPermittedException` |
| Supplier/client after `OPEN` | Not executed |
| Metrics | Buffered, success, failure, and not-permitted counts match the outcome sequence |
| Fallback | Executes at the API boundary and returns the contracted response |

A good test not only proves that the Circuit Breaker ends up in `OPEN`; it proves why the circuit opened, after which sample it opened, that metrics accurately reflect the outcome sequence, and that the next request is actually blocked before reaching the dependency. That is the basis for confidence that the Resilience4j configuration in Spring Cloud is protecting the service according to the designed thresholds.
