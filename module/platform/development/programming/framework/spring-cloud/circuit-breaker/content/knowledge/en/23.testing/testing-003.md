# Testing Slow Calls Independently from Failed Calls

A Resilience4j circuit breaker can open due to two distinct signals: the failed call rate and the slow call rate. When testing, you need to create two independent scenarios to prove that a call that returns a successful result but takes too long can still open the circuit, while a call that fails quickly increases the failure rate without increasing the slow call rate.

Distinguishing these two scenarios prevents configuring a circuit breaker that only detects HTTP errors or exceptions while missing latency degradation. A service may still return HTTP 200 yet take several seconds to respond; those calls still tie up threads, connections, and the caller's time budget.

## Two Independently Evaluated Signals

Resilience4j records the outcome and execution duration of each call in the sliding window. From those samples, it computes two rates:

| Signal | How it is calculated | Meaning |
|---|---|---|
| Failure rate | Number of calls recorded as failed divided by total evaluated calls. | The dependency did not complete the call successfully. |
| Slow call rate | Number of calls whose duration exceeds the slow threshold divided by total evaluated calls. | The dependency responds too slowly, even though it may still return a successful result. |

Three properties to distinguish:

- **failureRateThreshold**: maximum failure percentage before the circuit breaker opens.
- **slowCallDurationThreshold**: duration above which a call is classified as slow.
- **slowCallRateThreshold**: maximum slow-call percentage before the circuit breaker opens.

Slow call rate is not a timeout. It is a percentage. `slowCallDurationThreshold` is the time threshold used to classify each individual call.

Once at least `minimumNumberOfCalls` samples exist, the circuit breaker can transition from CLOSED to OPEN if the failure rate meets the threshold **or** the slow call rate meets the threshold. Both do not need to exceed their thresholds simultaneously. A call that is both slow and failed can contribute to both rates; therefore, do not add the two rates together to infer the count of problematic calls.

## Designing Three Separate Test Scenarios

To properly test each signal, create calls with controlled outcomes and durations:

| Scenario | HTTP/application outcome | Duration | Failure rate | Slow call rate |
|---|---|---|---|---|
| Slow but successful | Success, e.g., HTTP 200 | Greater than slowCallDurationThreshold | Does not increase | Increases |
| Fast failure | Throws an exception or returns a status converted to an error | Less than slowCallDurationThreshold | Increases | Does not increase |
| Slow and failed | Throws an exception after waiting long | Greater than slowCallDurationThreshold | Increases | Increases |

For example, use a 10-call window, `minimumNumberOfCalls` of 10, `failureRateThreshold` of 50%, `slowCallDurationThreshold` of 100 ms, and `slowCallRateThreshold` of 50%.

- Six successful calls taking 180 ms and four fast successful calls: failure rate is 0%, slow call rate is 60%. The circuit opens due to slow calls.
- Six failed calls taking 5 ms and four fast successful calls: failure rate is 60%, slow call rate is 0%. The circuit opens due to failures.
- Six calls that are both slow and failed: both rates increase. This scenario tests the intersection of the two signals and does not replace the two independent tests above.

It is important not to set timeouts shorter than the slow response duration in the first test. If a timeout fires before the call returns, the "slow but successful" scenario turns into a timeout failure and no longer isolates the slow call rate.

## Configuring Resilience4j for the Test

You can configure an instance in `application.yml`:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory-read:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 100ms
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
~~~

With this configuration:

- The count-based window holds at most the 10 most recent outcomes.
- The circuit breaker does not evaluate rates until there are at least 10 calls.
- Calls taking longer than the 100 ms threshold are classified as slow.
- When at least half of the evaluated samples are slow, the circuit can open even if all calls succeed.
- When at least half of the samples fail, the circuit can also open even if all failed calls finish quickly.

In tests, `COUNT_BASED` is usually easier to control than `TIME_BASED` because the sample count is deterministic. If using `TIME_BASED`, `slidingWindowSize` represents the length of the time window; ensure all test calls fall within the same window and meet `minimumNumberOfCalls`.

The values above are for a test environment only. Real operational thresholds should be based on the service's latency budget, latency distribution, and traffic volume.

## Unit Testing with Resilience4j CircuitBreaker

You can test Resilience4j's behavior directly without starting a Spring context. Each test creates a new circuit breaker so that the state and metrics from a previous test do not affect the next test.

JUnit 5 example:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

class CircuitBreakerSlowCallTest {

    private CircuitBreaker newBreaker(String name) {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED
                )
                .slidingWindowSize(10)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50)
                .slowCallDurationThreshold(Duration.ofMillis(100))
                .slowCallRateThreshold(50)
                .waitDurationInOpenState(Duration.ofSeconds(30))
                .build();

        return CircuitBreaker.of(name, config);
    }

    private String responseAfter(long delayMillis, boolean fail) {
        if (delayMillis > 0) {
            try {
                Thread.sleep(delayMillis);
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException("Test interrupted", ex);
            }
        }

        if (fail) {
            throw new IllegalStateException("Downstream failed");
        }

        return "OK";
    }

    @Test
    void slowSuccessfulCallsOpenBreakerWithoutFailures() {
        CircuitBreaker breaker = newBreaker("slow-success");

        for (int i = 0; i < 6; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(180, false))
            );
        }

        for (int i = 0; i < 4; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(0, false))
            );
        }

        assertEquals(
                0.0f,
                breaker.getMetrics().getFailureRate(),
                0.01f
        );
        assertTrue(breaker.getMetrics().getSlowCallRate() >= 50.0f);
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }

    @Test
    void fastFailuresOpenBreakerWithoutSlowCalls() {
        CircuitBreaker breaker = newBreaker("fast-failure");

        for (int i = 0; i < 6; i++) {
            assertThrows(
                    IllegalStateException.class,
                    () -> breaker.executeSupplier(
                            () -> responseAfter(0, true)
                    )
            );
        }

        for (int i = 0; i < 4; i++) {
            assertEquals(
                    "OK",
                    breaker.executeSupplier(() -> responseAfter(0, false))
            );
        }

        assertTrue(breaker.getMetrics().getFailureRate() >= 50.0f);
        assertEquals(
                0.0f,
                breaker.getMetrics().getSlowCallRate(),
                0.01f
        );
        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
~~~

The two tests verify two distinct circuit-opening paths:

- The first test has only successful calls. The failure rate must be 0%, while the slow call rate reaches 60% and the state transitions to OPEN.
- The second test has only fast failures. The failure rate reaches 60%, while the slow call rate is 0%.

The example uses wall-clock time to make calls slow. In CI or heavily loaded machines, the scheduler may delay a fast call unexpectedly. Leave a sufficiently wide margin between the slow duration and the threshold, avoid testing right on the boundary, and do not run timing-sensitive tests in parallel if the environment is overloaded. For integration tests, you can use an HTTP stub with a fixed delay to observe both the client and the circuit breaker.

## Integration Testing Through an HTTP Client

The unit tests above directly verify Resilience4j counters. An integration test should also verify the actual HTTP path: a slow successful response is measured as a slow call, while a fast error is measured as a failure.

You can use WireMock to create two responses:

~~~java
stubFor(get(urlEqualTo("/inventory/SKU-1"))
        .willReturn(aResponse()
                .withStatus(200)
                .withFixedDelay(250)
                .withHeader("Content-Type", "application/json")
                .withBody("{\"sku\":\"SKU-1\",\"available\":12}")));

stubFor(get(urlEqualTo("/inventory/SKU-2"))
        .willReturn(aResponse()
                .withStatus(500)
                .withFixedDelay(5)));
~~~

For the first response, the HTTP client receives status 200 after a 250 ms delay. If `slowCallDurationThreshold` is lower than 250 ms and the client/TimeLimiter timeout is longer than 250 ms, the circuit breaker records a slow yet successful call.

For the second response, the service returns status 500 quickly. You must configure the HTTP client or adapter to translate this status into an exception if you want the circuit breaker to record it as a failure. Some clients throw exceptions automatically for 5xx responses; some processing pipelines convert responses into normal objects. Verify the actual behavior of your client rather than assuming every HTTP 500 automatically becomes a failure.

Do not reuse an already-OPEN circuit breaker to run both scenarios back-to-back. Once the circuit opens, calls are rejected before reaching the stub and results no longer reflect service latency. Create a separate instance for each scenario or perform a controlled reset before starting.

## Setting Timeouts Long Enough to Isolate Slow Calls

A circuit breaker does not abort a call merely because its duration exceeds `slowCallDurationThreshold`. It records the duration when the call finishes, then uses the outcome in the sliding window to compute the slow call rate. If the rate exceeds the threshold, subsequent calls can be rejected once the circuit is OPEN.

Timeouts serve a different role: terminating waiting for a call when the deadline expires. If the timeout is shorter than `slowCallDurationThreshold`, calls may fail due to timeouts before they can be recorded as slow successes.

When testing slow successes:

1. Choose `slowCallDurationThreshold`, for example 100 ms.
2. Have the stub return a successful response after about 250 ms.
3. Set the HTTP client and TimeLimiter timeouts longer than that delay, for example 1 second.
4. Verify that the response still succeeds.
5. Verify that the slow call count increases while the failure count does not.

Then, test timeouts separately using a response slower than the timeout. That scenario verifies the timeout error path, not an isolated test for slow successful calls.

## Observing Metrics and State

Resilience4j exposes circuit breaker metrics to read failure rate and slow call rate independently. In unit tests, you can inspect them directly:

~~~java
CircuitBreaker.Metrics metrics = breaker.getMetrics();

float failureRate = metrics.getFailureRate();
float slowCallRate = metrics.getSlowCallRate();

int failedCalls = metrics.getNumberOfFailedCalls();
int slowCalls = metrics.getNumberOfSlowCalls();
~~~

When integrating Spring Boot Actuator and Micrometer, you can export Resilience4j metrics to monitor by instance name. Exact metric names and tags can vary by library version and registry configuration; inspect the actual metrics exposed in your application environment.

At minimum, monitor:

- Failure rate and failed call count.
- Slow call rate and slow call count.
- p50, p95, and p99 latency of dependency calls.
- CLOSED, OPEN, and HALF_OPEN states.
- Number of rejected calls while the circuit is OPEN.
- Number of fallback invocations.

Do not merge slow call rate into failure rate when building dashboards. Looking only at error rates can cause operations teams to miss situations where a service still returns 2xx while latency spikes. Conversely, looking only at latency can miss fast errors caused by connection or server failures.

## Common Mistakes When Writing Tests

| Mistake in test | Why the result is wrong | How to fix |
|---|---|---|
| Using a 500 response to test slow call rate | The test is measuring errors; if fast, it does not prove slow calls independently. | Use a successful response with a delay exceeding the threshold. |
| Setting a timeout shorter than the stub delay | Calls become timeout errors instead of slow successes. | Set the timeout longer than the delay in slow-success tests. |
| Not reaching minimumNumberOfCalls | The circuit breaker does not evaluate rates yet. | Send enough samples in the window. |
| Reusing an already-OPEN breaker across multiple tests | Subsequent calls are rejected before executing. | Create a separate breaker per test or do a controlled reset. |
| Setting delay right next to slowCallDurationThreshold | Tests become flaky due to scheduler and machine load. | Leave a large enough time margin. |
| Using TIME_BASED while the test runs too slowly | Old samples leave the window before reaching the required count. | Use COUNT_BASED or ensure all samples fall inside the window. |
| Assuming every HTTP 5xx is automatically an exception | Behavior depends on the HTTP client and response handling. | Check the adapter/client and convert status codes to errors when needed. |

A good test must prove the triggering condition, not just check the final state. Assert the response, failure rate, slow call rate, sample count, and circuit breaker state together.

## Checking HALF_OPEN After Opening Due to Slow Calls

After the circuit opens due to slow call rate, you can test recovery:

1. Configure a short `waitDurationInOpenState` in the test, such as 200 ms.
2. Once the circuit is OPEN, verify that the next call is rejected quickly.
3. Wait out the OPEN duration according to the test's timing mechanism.
4. Allow a small number of probe calls in HALF_OPEN.
5. Switch the stub to fast, successful responses.
6. Verify that the circuit breaker returns to CLOSED after the probe samples meet the requirements.

If the service still responds slowly in HALF_OPEN, the circuit can reopen. The number of probe calls is bounded by `permittedNumberOfCallsInHalfOpenState`. Do not generate a heavy burst of load when testing recovery.

HALF_OPEN tests should be separated from tests verifying slow success and fast failure. Each test should verify one primary behavior so that when it fails, the root cause can be identified clearly.

## Testing Checklist

1. Create a new circuit breaker for each scenario and use a window with a deterministic sample count.
2. Set `minimumNumberOfCalls` low enough for tests to finish while still verifying the condition properly.
3. Test slow success using a successful response with a delay greater than `slowCallDurationThreshold`.
4. Verify that the failure rate is 0 and the slow call rate exceeds the threshold in the slow-success scenario.
5. Test fast failure using an exception or status converted into an error with a duration below the slow threshold.
6. Verify that the failure rate exceeds the threshold and the slow call rate is 0 in the fast-failure scenario.
7. Test the slow-and-failed scenario separately to confirm both rates can increase together.
8. Set timeouts longer than the delay in slow-success tests; test timeouts separately.
9. Verify that an OPEN circuit breaker rejects subsequent calls and HALF_OPEN recovers according to configuration.
10. Observe separate metrics for errors and slow calls.

Testing slow calls independently from failed calls confirms that the circuit breaker protects both availability and latency of dependent services. A slow but successful response must be able to increase the slow call rate without increasing the failure rate; a fast error must increase the failure rate without being mistaken for a slow call. When tests isolate these two signals, the development team can trust the Resilience4j configuration more and detect performance degradation early before it cascades to calling services.
