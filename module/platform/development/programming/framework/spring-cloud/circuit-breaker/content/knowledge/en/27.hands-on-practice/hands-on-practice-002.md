# Measuring CLOSED, OPEN, HALF_OPEN, and Recovery

This hands-on practice builds a simulated dependency that can switch from a failing state to a healthy state, places a Resilience4j CircuitBreaker in front of the call, and measures the full `CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED` sequence. You will count how many times the supplier actually invokes the dependency, observe state transition events, and verify that the breaker rejects requests while `OPEN`.

The goal is to prove with metrics that the circuit breaker protects the call boundary properly: when dependency failures exceed the threshold, the breaker opens; while open, new requests do not touch the dependency; when the dependency recovers, a limited number of probes are allowed; if the probes succeed, the breaker closes again and normal traffic resumes.

## 1. Scenario and Expected Outcomes

We simulate an `Inventory Service` that an `Order Service` calls synchronously. The dependency initially always throws an error, and is then switched to a healthy state via an in-memory flag.

| Phase | Dependency | Circuit breaker | Expected result |
| --- | --- | --- | --- |
| Start | Failing | `CLOSED` | Calls are executed and results are recorded |
| Enough failure samples | Failing | Transitions to `OPEN` | Failure rate exceeds the threshold |
| Additional request sent | Not yet recovered | `OPEN` | Rejected; dependency call counter does not increase |
| Open duration elapsed | Recovered | `HALF_OPEN` | Only the configured number of probes is permitted to run |
| Probes succeed | Healthy | `CLOSED` | Breaker closes and allows normal calls |

In this lab, we configure a count-based window of four calls, require at least four samples, and set the failure threshold to 50%. Four consecutive failed calls produce a 100% failure rate, which qualifies to open the breaker. After two seconds, the breaker automatically transitions to `HALF_OPEN` and permits two probes. Both probes succeeding brings the breaker back to `CLOSED`.

## 2. Prepare Dependencies and Tests

In a Spring Boot application using Spring Cloud CircuitBreaker with Resilience4j, add the backend starter and test dependency. Versions should be managed by a Spring Cloud BOM compatible with the project's Spring Boot version:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Spring Cloud's Resilience4j starter provides the factory for application code to invoke the circuit breaker. This lab uses the native `io.github.resilience4j.circuitbreaker.CircuitBreaker` API in a standalone unit test so state, metrics, and events can be read directly. This is the same Resilience4j mechanism used by the Spring Cloud backend; later we will connect it back to the application's `CircuitBreakerFactory`.

## 3. Declare the Test Configuration

Create an equivalent configuration in `application-test.yml` to use when running the Spring Cloud application:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 4
        minimumNumberOfCalls: 4
        failureRateThreshold: 50
        slowCallDurationThreshold: 1s
        slowCallRateThreshold: 100
        waitDurationInOpenState: 2s
        permittedNumberOfCallsInHalfOpenState: 2
        automaticTransitionFromOpenToHalfOpenEnabled: true
```

Meaning of these values:

- `slidingWindowType: COUNT_BASED` and `slidingWindowSize: 4`: only evaluate the four most recent outcomes.
- `minimumNumberOfCalls: 4`: only calculate rates after at least four calls have been recorded.
- `failureRateThreshold: 50`: a failure rate of 50% or higher opens the breaker.
- `slowCallDurationThreshold: 1s`: calls taking longer than one second are classified as slow.
- `slowCallRateThreshold: 100`: do not use the slow-call rate to open the breaker in this scenario; the lab focuses on simulated errors.
- `waitDurationInOpenState: 2s`: time spent in `OPEN` before attempting recovery.
- `permittedNumberOfCallsInHalfOpenState: 2`: allow two probe calls.
- `automaticTransitionFromOpenToHalfOpenEnabled: true`: the breaker automatically transitions to `HALF_OPEN` after the open duration, without waiting for a new request to trigger the state transition.

In the unit test below, we construct `CircuitBreakerConfig` in Java with the same values so the test is self-contained, fast, and independent of Spring profile loading. When integrating into the application, keep the `inventory` ID consistent between YAML and the calling code.

## 4. Write a Test Simulating Failure Then Recovery

Create the test file `CircuitBreakerRecoveryTest.java` in the module's test sources. The simulated dependency uses an `AtomicBoolean` to control availability and an `AtomicInteger` to count how many times the supplier actually executes.

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CircuitBreakerRecoveryTest {

    @Test
    void measuresClosedOpenHalfOpenAndRecovery() throws InterruptedException {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(4)
            .minimumNumberOfCalls(4)
            .failureRateThreshold(50)
            .slowCallDurationThreshold(Duration.ofSeconds(1))
            .slowCallRateThreshold(100)
            .waitDurationInOpenState(Duration.ofSeconds(2))
            .permittedNumberOfCallsInHalfOpenState(2)
            .automaticTransitionFromOpenToHalfOpenEnabled(true)
            .build();

        CircuitBreaker breaker = CircuitBreaker.of("inventory", config);
        AtomicBoolean dependencyAvailable = new AtomicBoolean(false);
        AtomicInteger dependencyCalls = new AtomicInteger();
        CountDownLatch halfOpenReached = new CountDownLatch(1);
        List<String> transitions = new CopyOnWriteArrayList<>();

        Supplier<String> dependencyCall = () -> {
            dependencyCalls.incrementAndGet();
            if (!dependencyAvailable.get()) {
                throw new IllegalStateException("inventory is unavailable");
            }
            return "inventory:stock=12";
        };

        breaker.getEventPublisher().onStateTransition(event -> {
            CircuitBreaker.State from = event.getStateTransition().getFromState();
            CircuitBreaker.State to = event.getStateTransition().getToState();
            transitions.add(from + " -> " + to);
            if (to == CircuitBreaker.State.HALF_OPEN) {
                halfOpenReached.countDown();
            }
        });

        // Phase 1: breaker is CLOSED, all four dependency calls fail.
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        for (int i = 0; i < 4; i++) {
            assertThatThrownBy(() -> breaker.executeSupplier(dependencyCall))
                .isInstanceOf(IllegalStateException.class);
        }

        // Four samples reached with 100% failure rate, so the breaker transitions to OPEN.
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);
        assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(4);
        assertThat(breaker.getMetrics().getFailureRate()).isEqualTo(100.0f);
        assertThat(dependencyCalls.get()).isEqualTo(4);

        // Phase 2: new requests are rejected before the supplier runs.
        assertThatThrownBy(() -> breaker.executeSupplier(dependencyCall))
            .isInstanceOf(CallNotPermittedException.class);
        assertThat(breaker.getMetrics().getNumberOfNotPermittedCalls()).isEqualTo(1);
        assertThat(dependencyCalls.get()).isEqualTo(4);

        // Phase 3: dependency recovers; wait for the breaker to auto-transition to HALF_OPEN.
        dependencyAvailable.set(true);
        assertThat(halfOpenReached.await(5, TimeUnit.SECONDS)).isTrue();
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.HALF_OPEN);

        // Phase 4: two probes are permitted and both succeed.
        assertThat(breaker.executeSupplier(dependencyCall))
            .isEqualTo("inventory:stock=12");
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.HALF_OPEN);

        assertThat(breaker.executeSupplier(dependencyCall))
            .isEqualTo("inventory:stock=12");
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);

        // Total dependency invocations: 4 failures + 2 successful probes.
        // Calls rejected while OPEN do not increment the counter.
        assertThat(dependencyCalls.get()).isEqualTo(6);
        assertThat(transitions).contains(
            "CLOSED -> OPEN",
            "OPEN -> HALF_OPEN",
            "HALF_OPEN -> CLOSED"
        );
    }
}
```

The test uses a `CountDownLatch` to wait for the transition event to `HALF_OPEN` instead of guessing timing with a fixed `sleep`. The five-second maximum wait is simply a timeout bound so the test fails clearly if the scheduler does not transition the state. If the test times out, check `automaticTransitionFromOpenToHalfOpenEnabled`, the open duration setting, and the Resilience4j version.

## 5. Run the Test and Read the Results

Run the test on its own with the Maven Wrapper:

```bash
./mvnw -Dtest=CircuitBreakerRecoveryTest test
```

If using Gradle, run the corresponding test class using the `test` task and your project's filter. Expected results during the run:

| Milestone | State | Dependency calls | Metrics / observations |
| --- | --- | ---: | --- |
| Initialization | `CLOSED` | 0 | No samples yet |
| After four errors | `OPEN` | 4 | 4 failed, 100% failure rate |
| After one blocked request | `OPEN` | 4 | 1 not permitted; supplier did not run |
| After two seconds | `HALF_OPEN` | 4 | `OPEN -> HALF_OPEN` event |
| After first probe | `HALF_OPEN` | 5 | One probe succeeded; one permit left in the trial batch |
| After second probe | `CLOSED` | 6 | `HALF_OPEN -> CLOSED` event; normal traffic permitted |

The most important point is that the dependency call count is six, not seven. The fifth request sent while the breaker is `OPEN` is rejected right at the breaker, so the supplier does not increment the counter. The last two requests are real probes in `HALF_OPEN`.

## 6. Observe Events and Metrics at Runtime

The event listener in the test records the state transitions. When running a real application, you can log events as structured logs or export metrics via Micrometer. Key events to track:

- `CLOSED -> OPEN`: failure rate or slow call rate reached the threshold.
- `OPEN -> HALF_OPEN`: open duration elapsed and the breaker begins testing recovery.
- `HALF_OPEN -> CLOSED`: permitted probes met the success criteria.
- `HALF_OPEN -> OPEN`: probes failed or the trial failure rate did not meet the threshold.
- Call not permitted: request blocked while the breaker disallows calls.

With Resilience4j Micrometer integration, you can monitor meters such as `resilience4j.circuitbreaker.calls`, `resilience4j.circuitbreaker.state`, `resilience4j.circuitbreaker.failure.rate`, and `resilience4j.circuitbreaker.buffered.calls`. Meter names and tags should be verified through `/actuator/metrics` or `/actuator/prometheus` for the version in use.

Do not add rejected calls into the dependency's failure rate. When the breaker is `OPEN`, the supplier does not run; the count of rejected calls is a separate signal showing that the circuit breaker is protecting the dependency from new requests.

## 7. Connect the Lab to the Spring Cloud CircuitBreaker Factory

In a Spring Cloud service, business code usually calls through `CircuitBreakerFactory` rather than interacting directly with the native `CircuitBreaker`:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult fetch(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.fetch(sku),
            error -> InventoryResult.unavailable(sku)
        );
    }
}
```

The name `inventory` matches the ID in `resilience4j.circuitbreaker.instances.inventory`. The factory selects the Resilience4j backend configured by Spring Cloud. The fallback shown is appropriate for a read query if the business accepts an unavailable result; for commands with side effects such as reserving inventory or processing payment, do not return a fake success result when the breaker rejects the call or the dependency times out.

The earlier unit test measures state directly on a Resilience4j instance to clearly illustrate the mechanism. When testing the factory in an application, invoke it through the actual Spring bean and observe the corresponding backend instance via the metrics/event integration supported by the version in use. Do not create a separate `CircuitBreakerRegistry` and use its state to draw conclusions about the breaker managed by the factory; two different registries can hold two instances with the same name but separate states.

## 8. Experiment When a Probe Fails

Once the successful recovery test runs reliably, modify the scenario so one of the two probes still fails. For example, only mark the dependency healthy after the first probe, or set a flag so the first probe throws an exception.

Results to observe:

- The breaker does not close after a single successful probe if more probes are still required.
- When the probe outcome fails to meet the failure threshold, the breaker returns to `OPEN`.
- During the next `OPEN` phase, new requests continue to be rejected and the supplier does not run.
- After a new open duration, the breaker again allows a limited batch of probes.

This experiment demonstrates that `HALF_OPEN` is a recovery evaluation phase, not a temporary closed state. The number of probes is capped so the dependency is not flooded with full traffic as soon as it starts responding again.

## 9. Common Issues When Running the Lab

| Symptom | Cause to check | How to fix |
| --- | --- | --- |
| Breaker stays `CLOSED` after four errors | `minimumNumberOfCalls` not reached, exception ignored, or not recorded | Check window configuration and exception classification rules |
| Fifth call still executes the supplier | Test uses a different breaker, a new instance, or the call bypasses the breaker | Use the same instance across the whole scenario and place the counter inside the supplier |
| Never sees `HALF_OPEN` | Automatic transition is disabled or test waits with the wrong timeout | Enable `automaticTransitionFromOpenToHalfOpenEnabled` and wait for the state event |
| Breaker does not close after two probes | One probe failed, permit count differs from config, or not enough results yet | Check each probe's outcome and `permittedNumberOfCallsInHalfOpenState` |
| Flaky test results | Shared instance between tests, shared state in simulated dependency, or unsynchronized timing waits | Create a fresh breaker per test, use latches/events, and clean up resources |
| Metrics do not match call counts | Looking at a different registry or confusing call-not-permitted with call failures | Verify the same instance and separate `not_permitted` calls |

In Spring integration tests, be sure to use the same profile and breaker ID as the configuration. If multiple tests share an application context, breaker state may carry over from an earlier test; create dedicated instances or reset them appropriately in the test fixture.

## 10. Extending the Practice

After completing the basic scenario, you can perform these additional measurements:

1. **Change the threshold:** set `failureRateThreshold` to 75% and fail three out of four requests; verify that the breaker opens when the rate reaches the threshold.
2. **Sliding window:** increase `slidingWindowSize` to eight and `minimumNumberOfCalls` to four; alternate successes and failures to see how the sliding window updates the rate.
3. **Slow calls:** make the dependency wait longer than `slowCallDurationThreshold` while still succeeding; observe the slow-call rate independently of the failure rate.
4. **Timeout:** wrap the asynchronous operation with a TimeLimiter; verify that timeouts are recorded as configured and do not confuse the slow-call threshold with a request cancellation mechanism.
5. **Fallback:** count fallback invocations separately; verify that a fallback does not make the circuit breaker mistake a failed supplier for a success when the goal is to record dependency failures.
6. **Multiple replicas:** run two application instances and observe that each breaker maintains its own state; never assume one instance opening means the other instance opens as well.

## 11. Completion Criteria

- The first four calls execute while the breaker is `CLOSED` and all fail.
- The breaker transitions to `OPEN` after enough samples and exceeding the failure threshold.
- A request sent while `OPEN` receives `CallNotPermittedException` or enters fallback, without invoking the dependency.
- The dependency is switched to a healthy state before the probe phase.
- The breaker automatically transitions to `HALF_OPEN` after the configured wait duration.
- Two probes are allowed to run; when both succeed, the breaker transitions back to `CLOSED`.
- Events record all three primary state transitions and the dependency counter confirms no requests leak through while the breaker is `OPEN`.

By completing the steps above, you have measured the entire basic lifecycle of a circuit breaker: detecting errors, blocking new calls, testing recovery with limited probes, and reopening traffic when the dependency is healthy. Keep the configuration, event logs, and call counts as evidence when tuning thresholds or rolling out this policy into real Spring Cloud services.
