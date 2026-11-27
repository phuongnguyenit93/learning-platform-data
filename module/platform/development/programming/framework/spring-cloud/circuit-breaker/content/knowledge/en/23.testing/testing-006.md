# Testing HALF_OPEN Successful Recovery and Reopening on Failure

After a circuit breaker transitions from `OPEN` to `HALF_OPEN`, it permits only a limited number of probe calls to the dependent service. The outcomes of these calls determine whether the circuit can return to `CLOSED` or must reopen to `OPEN`. This is a critical moment to test: if the probe calls succeed, the system must restore its ability to call the dependency; if they continue to fail or exceed the slow-call threshold, the circuit breaker must continue blocking traffic.

With Spring Cloud CircuitBreaker using Resilience4j, you can test the state machine directly with the Resilience4j API and additionally test the factory and fallback at the Spring layer. This lesson builds two deterministic scenarios: `HALF_OPEN` closing the circuit after successful probes and `HALF_OPEN` reopening after failed probes. The examples use a small number of probes for easy observation, then extend to checking wait durations, events, and application integration.

## 1. Conditions for Transitioning Out of HALF_OPEN

A circuit breaker has three common states:

- `CLOSED`: calls are permitted through; outcomes are recorded in the sliding window.
- `OPEN`: calls are rejected immediately; the supplier is not executed.
- `HALF_OPEN`: only a limited number of probe calls are allowed to run to assess recovery.

Once `waitDurationInOpenState` elapses, the circuit breaker can transition to `HALF_OPEN`. With Resilience4j, if `automaticTransitionFromOpenToHalfOpenEnabled` is disabled, the state usually transitions when the next call arrives after the open wait duration has expired. If enabled, a background task transitions the state without waiting for a new request.

In `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` defines the maximum number of probe calls. Once enough probe outcomes are collected, Resilience4j evaluates the failure rate and slow call rate against the configuration:

| Probe outcomes | Expected behavior |
|---|---|
| Probes complete and failure/slow-call rates are below thresholds | Transitions back to `CLOSED`. |
| Probes cause failure rate to meet or exceed threshold | Transitions back to `OPEN`. |
| Probes cause slow call rate to meet or exceed threshold | Transitions back to `OPEN`. |
| Permits in `HALF_OPEN` are exhausted | New calls are rejected with `CallNotPermittedException` until outcomes complete and the state is evaluated. |

`waitDurationInOpenState` and `permittedNumberOfCallsInHalfOpenState` serve different roles. The first determines how long to wait before probing; the second limits the number of probes. Do not use the probe count as a substitute for the open-state wait duration.

## 2. Designing a Deterministic Test Configuration

For stable state-machine tests, use a small configuration and explicitly control the number of probes. Example:

```java
import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(10)
    .minimumNumberOfCalls(5)
    .failureRateThreshold(50)
    .slowCallDurationThreshold(Duration.ofSeconds(2))
    .slowCallRateThreshold(50)
    .waitDurationInOpenState(Duration.ofSeconds(10))
    .permittedNumberOfCallsInHalfOpenState(2)
    .automaticTransitionFromOpenToHalfOpenEnabled(false)
    .build();

CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
```

With this configuration, the circuit breaker uses a 10-call count-based window and needs at least 5 samples to evaluate rates in `CLOSED`. When in `HALF_OPEN`, it permits at most 2 probes. Setting `automaticTransitionFromOpenToHalfOpenEnabled(false)` lets the state-machine test control when it transitions to `HALF_OPEN` without depending on a background scheduler.

In unit tests, you can use `transitionToOpenState()` and `transitionToHalfOpenState()` to put the circuit breaker into the state under test. Direct state-transition methods are appropriate for testing behavior once already in that state; they do not replace testing `waitDurationInOpenState` in production configurations.

## 3. Testing Successful Recovery and Returning to CLOSED

The first scenario simulates a dependency that has recovered. The circuit breaker is `OPEN`, is transitioned to `HALF_OPEN`, and then two probe calls both succeed. Once enough outcomes are received and the failure rate is below the threshold, the breaker must return to `CLOSED`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenRecoveryTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .slowCallDurationThreshold(Duration.ofSeconds(2))
            .slowCallRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        return CircuitBreaker.of("inventory", config);
    }

    @Test
    void closesAfterAllHalfOpenProbesSucceed() {
        CircuitBreaker breaker = newBreaker();
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState());

        String first = breaker.executeSupplier(() -> "stock-available");
        assertEquals("stock-available", first);

        String second = breaker.executeSupplier(() -> "stock-available");
        assertEquals("stock-available", second);

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
    }
}
```

This test verifies three things:

1. The circuit breaker starts in `HALF_OPEN` before probes execute.
2. Both permitted suppliers complete successfully.
3. After enough probes complete, the circuit breaker transitions back to `CLOSED`.

Do not check only the supplier return values. Asserting only the two return values does not prove that the state machine closed the circuit. Always assert the final state.

## 4. Testing Failed Probes Causing the Circuit Breaker to Reopen

The second scenario simulates a dependency that is still failing after the open wait duration. Both probes throw an exception recorded as a failure. Once enough outcomes are collected and the failure rate reaches the threshold, the circuit breaker must transition back to `OPEN`.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenReopenTest {

    private CircuitBreaker newBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();

        return CircuitBreaker.of("inventory", config);
    }

    @Test
    void reopensWhenHalfOpenProbesFail() {
        CircuitBreaker breaker = newBreaker();
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();

        assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState());

        assertThrows(IllegalStateException.class, () ->
            breaker.executeSupplier(() -> {
                throw new IllegalStateException("inventory still unavailable");
            })
        );

        assertThrows(IllegalStateException.class, () ->
            breaker.executeSupplier(() -> {
                throw new IllegalStateException("inventory still unavailable");
            })
        );

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    }
}
```

Both probes fail, so the probe failure rate reaches 100%, above the 50% threshold. After two outcomes, the circuit breaker reopens. Using two clear failures avoids depending on exact-threshold boundary behavior in a basic test.

If only one probe fails and no further probes run, the circuit breaker may stay in `HALF_OPEN` because the permitted number of outcomes has not been completed yet. In some configurations/versions, you can configure a maximum wait duration in `HALF_OPEN` to handle incomplete probes; check the `maxWaitDurationInHalfOpenState` property if supported by your Resilience4j version.

## 5. Verifying Calls Exceeding Permits Are Rejected

In `HALF_OPEN`, `permittedNumberOfCallsInHalfOpenState` is the number of permitted probe calls. When permits are exhausted before the state has finished evaluating, subsequent calls can be rejected. Once two probes fail and the breaker returns to `OPEN`, all new calls are immediately rejected as well.

You can verify that the supplier does not execute when the circuit breaker rejects a call:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenPermissionTest {

    @Test
    void rejectsCallsAfterFailedProbesReopenTheBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .failureRateThreshold(50)
            .waitDurationInOpenState(Duration.ofSeconds(10))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(false)
            .build();
        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();
        AtomicInteger supplierCalls = new AtomicInteger();

        for (int i = 0; i < 2; i++) {
            assertThrows(IllegalStateException.class, () ->
                breaker.executeSupplier(() -> {
                    throw new IllegalStateException("probe failed");
                })
            );
        }

        assertEquals(CircuitBreaker.State.OPEN, breaker.getState());

        assertThrows(CallNotPermittedException.class, () ->
            breaker.executeSupplier(() -> {
                supplierCalls.incrementAndGet();
                return "must not execute";
            })
        );

        assertEquals(0, supplierCalls.get());
    }
}
```

The test creates a breaker with two permits and transitions it to `HALF_OPEN`. The key part is checking `CallNotPermittedException` after the two probes fail and confirming that the supplier is never executed.

Do not treat `CallNotPermittedException` as a new failed probe. It is a circuit breaker rejection, not a request sent to the dependency that subsequently failed.

## 6. Testing the Transition Duration from OPEN to HALF_OPEN

Unit tests using `transitionToHalfOpenState()` provide fast, deterministic verification of behavior after the circuit has transitioned. However, you need a dedicated test for `waitDurationInOpenState` if you want to verify the actual wait duration.

There are two ways the state transitions:

- **Transition on next request:** `automaticTransitionFromOpenToHalfOpenEnabled(false)`. After the `OPEN` duration expires, the next call triggers the transition to `HALF_OPEN` and can serve as a probe.
- **Automatic transition:** `automaticTransitionFromOpenToHalfOpenEnabled(true)`. Resilience4j uses a scheduler to transition to `HALF_OPEN` when the wait duration ends, even before a new request arrives.

Example testing automatic mode with Awaitility:

```java
import static org.awaitility.Awaitility.await;
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Duration;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenTimerTest {

    @Test
    void movesToHalfOpenAfterOpenWaitDuration() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .waitDurationInOpenState(Duration.ofMillis(150))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory-timer", config);
        breaker.transitionToOpenState();

        await().atMost(Duration.ofSeconds(2)).untilAsserted(() ->
            assertEquals(CircuitBreaker.State.HALF_OPEN, breaker.getState())
        );
    }
}
```

The test requires the `org.awaitility:awaitility` dependency in test scope if the project does not already include it. Awaitility polls for the condition with an upper deadline instead of using a fixed `Thread.sleep()`. The 150 ms duration is for testing only; do not use it as a default production configuration. When using request-triggered transition mode, write a test that sends a request after the wait duration elapses and verifies that the request is handled as a probe.

## 7. Testing Slow Calls in HALF_OPEN

A circuit breaker does not evaluate exceptions alone. A probe may complete technically successfully yet take longer than `slowCallDurationThreshold`. If the slow call rate reaches `slowCallRateThreshold`, the breaker can still reopen.

Example test configuration:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slowCallDurationThreshold(Duration.ofMillis(20))
    .slowCallRateThreshold(50)
    .permittedNumberOfCallsInHalfOpenState(2)
    .build();
```

When testing slow calls, create a supplier whose execution duration exceeds the threshold. Because tests based on the system clock can fluctuate with machine load, use a threshold with a sufficiently wide margin below the execution time and avoid placing them too close together. For business logic, you can abstract the clock or use the library's test fixtures if supported by your version.

Do not conclude that a dependency has recovered just because a probe did not throw an exception. If responses arrive too slowly relative to the SLO, the circuit breaker must continue protecting callers.

## 8. Testing State-Transition Events

In addition to checking the final state, you can register an event listener to verify the sequence of state transitions:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.ArrayList;
import java.util.List;

import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

class HalfOpenTransitionEventTest {

    @Test
    void recordsOpenHalfOpenClosedTransitions() {
        CircuitBreaker breaker = CircuitBreaker.of(
            "inventory-events",
            CircuitBreakerConfig.custom()
                .permittedNumberOfCallsInHalfOpenState(2)
                .build()
        );
        List<CircuitBreaker.StateTransition> transitions = new ArrayList<>();

        breaker.getEventPublisher().onStateTransition(event ->
            transitions.add(event.getStateTransition())
        );

        breaker.transitionToOpenState();
        breaker.transitionToHalfOpenState();
        breaker.executeSupplier(() -> "probe-1-ok");
        breaker.executeSupplier(() -> "probe-2-ok");

        assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
        assertEquals(3, transitions.size());
        assertEquals(CircuitBreaker.StateTransition.CLOSED_TO_OPEN, transitions.get(0));
        assertEquals(CircuitBreaker.StateTransition.OPEN_TO_HALF_OPEN, transitions.get(1));
        assertEquals(CircuitBreaker.StateTransition.HALF_OPEN_TO_CLOSED, transitions.get(2));
    }
}
```

The event listener should be registered once during test setup. Do not attach a listener inside each supplier call, or a single state-transition event could trigger duplicate callbacks. For failure tests, the expected sequence is `CLOSED_TO_OPEN`, `OPEN_TO_HALF_OPEN`, and `HALF_OPEN_TO_OPEN`.

## 9. Testing Through the Spring Cloud CircuitBreaker Factory

Tests using `CircuitBreaker` directly focus on verifying Resilience4j's state machine. At the application layer, you must also verify that the Spring Cloud CircuitBreaker factory creates the right breaker ID and that the fallback is invoked properly when the supplier fails or the circuit rejects calls.

Example service:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> factory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> factory,
            InventoryClient inventoryClient) {
        this.factory = factory;
        this.inventoryClient = inventoryClient;
    }

    public String getStock(String sku) {
        return factory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> "temporarily-unavailable"
        );
    }
}
```

In a Spring context integration test, you can mock `InventoryClient`, configure the `inventory` circuit breaker instance with two probes, and then use the same Resilience4j registry to transition the breaker to `OPEN` and then `HALF_OPEN`. Call the service twice with the client returning success to verify that the breaker closes; run another test with the client continuing to throw exceptions to verify that the breaker reopens.

The key point to verify is that the registry and the factory are using the same instance with ID `inventory`. Do not create a standalone `CircuitBreakerRegistry` in the test and assume it controls the factory's internal breaker. If your integration version does not expose the registry directly, you can verify via the factory and dedicated test configuration, or test the state machine at the Resilience4j layer and test the factory/fallback independently.

## 10. Testing Concurrency and Permit Counts

In production, probes can execute concurrently. With `permittedNumberOfCallsInHalfOpenState: 2`, at most two probe calls are granted permits. Other requests may be rejected while those two probes have not yet finished.

To test concurrency, you can hold two running suppliers using a `CountDownLatch`, send a third request, and verify that it is rejected. Then release the latch so the two probes finish and verify the state transition based on their outcomes. When writing such tests:

- Use a finite timeout for `await()` on the latch so the test cannot hang indefinitely.
- Release the latch in a `finally` block so threads are not left blocked if an assertion fails.
- Do not rely on completion order of the two probes if the test does not control ordering.
- Distinguish rejection due to permit exhaustion from failure coming from the supplier.
- Verify that the third supplier is never executed.

Sequential tests are usually sufficient for basic state-transition logic. Concurrency tests provide additional evidence that the permit limit works correctly when multiple requests arrive simultaneously.

## 11. Common Testing Mistakes

| Symptom | Possible cause | Fix |
|---|---|---|
| Test expects `HALF_OPEN` but breaker stays `OPEN` | `waitDurationInOpenState` has not elapsed or state transition was not triggered per config. | Use explicit state transition in unit tests or wait with Awaitility for real timers. |
| Two probes succeed but breaker is not `CLOSED` | Not enough permits/probes completed or one probe has not finished yet. | Verify `permittedNumberOfCallsInHalfOpenState` and ensure all publishers/futures have completed. |
| One probe fails but breaker is not `OPEN` | Not enough outcomes to evaluate yet or rate has not met threshold. | Send enough probes and check `failureRateThreshold`. |
| Test fails intermittently due to timing | Using `Thread.sleep()` or slow-call threshold too close to execution time. | Use Awaitility for wait times and leave enough margin for slow-call thresholds. |
| Supplier still runs when breaker is thought to be `OPEN` | Test controls the wrong instance or factory uses a different ID. | Use the matching instance/registry and check the breaker ID. |
| Rejections counted as failed probes | Test lumps `CallNotPermittedException` together with supplier exceptions. | Distinguish rejected calls from executed calls. |
| Test hangs in HALF_OPEN | A probe does not complete or a reactive publisher was never subscribed/terminated. | Complete all probes, verify subscriptions, and set test timeouts. |

## 12. Checklist for the Two Primary Scenarios

**Successful recovery:**

- [ ] Transition the circuit breaker from `OPEN` to `HALF_OPEN`.
- [ ] Verify that the permitted probe count matches configuration.
- [ ] Let all probes complete successfully without exceeding the slow-call threshold.
- [ ] Verify that the final state is `CLOSED`.
- [ ] Verify that new calls are allowed through after closing the circuit.

**Failed recovery:**

- [ ] Transition the circuit breaker from `OPEN` to `HALF_OPEN`.
- [ ] Let the permitted number of probes execute.
- [ ] Make probes fail or run slowly enough to exceed the threshold.
- [ ] Verify that the final state returns to `OPEN`.
- [ ] Verify that new calls are rejected and the supplier does not run.
- [ ] Verify that events/metrics accurately reflect `HALF_OPEN_TO_OPEN` and not-permitted counts.

## 13. Reading Metrics and Events During Tests

When using Micrometer with Resilience4j, you can observe breaker state, successful calls, failed calls, rejected calls, failure rate, and slow call rate. Specific meter names and tags depend on library versions and binder configuration; check the actual meters via Actuator or the test registry.

For the two primary scenarios, expected results are:

| Metric / observation | Successful probes | Failed probes |
|---|---|---|
| Final state | `CLOSED` | `OPEN` |
| Final state transition | `HALF_OPEN_TO_CLOSED` | `HALF_OPEN_TO_OPEN` |
| Probe supplier | Executed up to permitted count | Executed up to permitted count |
| Post-evaluation requests | Allowed through | Rejected early |
| Probe failure rate | Below threshold | Meets/exceeds threshold |
| Fallback | Not needed if probes succeed | May run for rejected or failed requests depending on service integration |

Do not rely solely on logs to conclude that the state machine works properly. Combine state assertions, supplier invocation counts, events, and metrics to verify both behavior and observability.

## 14. Principles for Writing Stable Tests

Separate state-machine unit tests from Spring context integration tests. In unit tests, use small configurations and explicit state transitions to test successful/failed recovery branches without waiting on wall-clock timers. In integration tests, verify `waitDurationInOpenState`, auto-transition, factory ID, fallback, and metrics using bounded wait timeouts.

Do not use long `Thread.sleep()` calls to synchronize tests. Do not assume any arbitrary exception is a rejection; `CallNotPermittedException` indicates the supplier did not run, whereas an exception from the supplier is the result of an executed probe. Never assert only the fallback while ignoring the final state. Finally, always verify the probe count, supplier invocation count, and circuit breaker state.

A good test suite proves both directions: when the dependency recovers, `HALF_OPEN` closes the circuit and allows traffic back; when the dependency remains broken or slow, `HALF_OPEN` reopens the circuit and blocks new requests. That is vital evidence confirming that Spring Cloud CircuitBreaker with Resilience4j properly protects dependent services during recovery.
