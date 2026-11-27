# Comparing Circuit Breaking by Failure Rate vs. Slow Call Rate

A Resilience4j circuit breaker can open based on two independent signals: **failure rate** and **slow call rate**. Failure rate detects a dependency that frequently returns errors; slow call rate detects a dependency that still returns results but takes too long. These two signals address two different kinds of degradation and can appear together within the same sliding window.

In this hands-on practice, we create two controllable situations: a dependency that fails fast and a dependency that succeeds slowly. Then we configure the breaker, compute the rates from the samples, observe the state, and decide when to use the failure threshold, the slow call threshold, or both. The example is set in the context of Spring Cloud calling a dependent service with Resilience4j; the numbers are for the lab only and must be tuned to your real system's SLOs.

## 1. Practice Objectives

After completing this practice, you can:

- Explain how `failureRateThreshold` and `slowCallRateThreshold` measure two different signals.
- Distinguish between fast-failing calls, slow successful calls, and calls that are both failed and slow.
- Calculate both rates from the same sliding window.
- Configure `minimumNumberOfCalls`, `slowCallDurationThreshold`, and the circuit-opening thresholds.
- Create deterministic test scenarios to observe `CLOSED` and `OPEN`.
- Choose thresholds based on target latency and actual dependency behavior.

## 2. Where Failure Rate and Slow Call Rate Differ

**Failure rate** is the percentage of calls recorded as failures out of all calls counted toward the statistics. A call can fail quickly due to connection refused, DNS failure, or HTTP 5xx; a short execution time does not make it any less of a failure.

**Slow call rate** is the percentage of calls whose execution duration exceeds `slowCallDurationThreshold` within the statistical window. A slow call can still return a successful result. It signals that the dependency is holding resources for a long time, increasing latency and risking exhaustion of threads, connection pools, or queues.

| Situation | Failure rate | Slow call rate | Meaning |
|---|---:|---:|---|
| HTTP 503 returned after 80 ms | Increases | Does not increase if below duration threshold | Dependency fails fast |
| HTTP 200 returned after 1.8 seconds, slow threshold 700 ms | Does not increase | Increases | Dependency returns a result but too slowly |
| Request times out after 1.2 seconds, slow threshold 700 ms | Increases if timeout is recorded | Can increase because duration exceeded threshold | A single call can contribute to both rates |
| HTTP 200 returned after 150 ms | Does not increase | Does not increase | Normal call |

Resilience4j evaluates the two thresholds independently. The breaker can transition to `OPEN` when the failure rate reaches `failureRateThreshold` **or** the slow call rate reaches `slowCallRateThreshold`, once the minimum number of samples is met. Therefore, checking only the error count misses cases where a dependency is degrading through latency.

## 3. Formulas and Calculation from the Sliding Window

For calls included in the statistics, the two rates can be expressed as follows:

\[
\text{Failure rate} = \frac{\text{Number of failed calls}}{\text{Number of successful calls} + \text{Number of failed calls}} \times 100\%
\]

\[
\text{Slow call rate} = \frac{\text{Number of slow calls}}{\text{Number of recorded calls}} \times 100\%
\]

Exceptions configured in `ignoreExceptions` are not counted as successes or failures in the sliding window. Calls rejected by the breaker (`not permitted`) are also not supplier outcomes and are not treated as failed backend calls. A failed call can simultaneously be a slow call if its execution duration exceeds `slowCallDurationThreshold`.

Suppose the window contains 10 samples:

| Outcome group | Count | Failed? | Slow? |
|---|---:|---|---|
| Fast success | 4 | No | No |
| Slow success | 3 | No | Yes |
| Fast failure | 2 | Yes | No |
| Slow failure | 1 | Yes | Yes |
| **Total** | **10** | **3 failures** | **4 slow calls** |

From the table above:

- Failure rate = 3 / 10 = 30%.
- Slow call rate = 4 / 10 = 40%.
- A slow failed call is counted in both the failure count and the slow call count, while the total sample count for that call is still one.

If `failureRateThreshold` is 50% and `slowCallRateThreshold` is 35%, the breaker can open because the slow call rate reached its threshold even though the failure rate is still below threshold. This is why both metrics must be inspected together.

## 4. Shared Configuration for the Lab

Create a breaker instance named `catalogLab`. The configuration below uses a count-based window so sample calculations are easy to observe:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      catalogLab:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 700ms
        slowCallRateThreshold: 40
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 2
```

Meaning of the parameters:

| Property | Lab value | Meaning |
|---|---:|---|
| `slidingWindowType` | `COUNT_BASED` | Window stores the 10 most recent calls |
| `slidingWindowSize` | `10` | Window size by number of calls |
| `minimumNumberOfCalls` | `10` | Only evaluate rates after 10 samples are recorded |
| `failureRateThreshold` | `50` | Open the circuit if failure rate reaches or exceeds 50% |
| `slowCallDurationThreshold` | `700ms` | Calls taking longer than threshold are marked slow |
| `slowCallRateThreshold` | `40` | Open the circuit if slow call rate reaches or exceeds 40% |
| `waitDurationInOpenState` | `10s` | Time spent in `OPEN` before probing again |
| `permittedNumberOfCallsInHalfOpenState` | `2` | Maximum probe calls granted in `HALF_OPEN` |

`minimumNumberOfCalls` applies to evaluating both failure rate and slow call rate. In the lab, setting it equal to the window size lets you gather 10 samples before comparing results. In production, you can choose a value lower than the window size, provided it is grounded in traffic volume and sample representativeness.

## 5. Create a Gateway Calling the Dependency Through CircuitBreaker

This example uses Spring Cloud reactive circuit breaker with `WebClient`. The timeout is placed **inside the publisher passed to the breaker** so that a dependency timeout is observed as a failure outcome of the protected call.

```java
import java.time.Duration;
import java.time.Instant;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> breakerFactory;

    public CatalogGateway(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> breakerFactory) {
        this.webClient = builder
                .baseUrl("http://localhost:8091")
                .build();
        this.breakerFactory = breakerFactory;
    }

    public Mono<CatalogResult> find(String sku) {
        Mono<CatalogResult> dependencyCall = Mono.defer(() ->
                webClient.get()
                        .uri("/catalog/{sku}", sku)
                        .retrieve()
                        .bodyToMono(CatalogResult.class)
        ).timeout(Duration.ofSeconds(2));

        ReactiveCircuitBreaker breaker = breakerFactory.create("catalogLab");
        return breaker.run(
                dependencyCall,
                error -> Mono.just(CatalogResult.unavailable(sku, Instant.now()))
        );
    }
}
```

`CatalogResult` is an application DTO that can represent catalog data or an `UNAVAILABLE` status. In a real application, `WebClient` configuration should use service discovery/load balancing or an environment-specific URL rather than hardcoding `localhost`.

If using the synchronous API, you can obtain a `CircuitBreaker` from `CircuitBreakerFactory` and wrap a supplier similarly. The important point in the lab is that the timeout belongs to the protected publisher/supplier so the breaker can record it. If you place `timeout` outside the entire `breaker.run(...)`, the outer timeout may only cancel the subscription of the protected publisher; depending on the implementation, the breaker may observe a cancellation instead of a timeout exception. Verify the semantics for the version you are using.

## 6. Scenario A: Dependency Fails Fast

The first scenario simulates a dependency returning HTTP 503 almost immediately. Requests fail in well under 700 ms, so they increase the failure rate without increasing the slow call rate.

Example of a test endpoint in the dependency:

```java
@RestController
public class CatalogLabController {

    @GetMapping("/catalog/fail-fast/{sku}")
    public ResponseEntity<Void> failFast(@PathVariable String sku) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE).build();
    }
}
```

In the gateway, point the lab call to the `fail-fast` endpoint and let the HTTP client convert 5xx statuses into exceptions, for example using WebClient's default `retrieve()`. Make 10 calls through the breaker while it is `CLOSED`.

Expected results:

| Metric | Expected outcome |
|---|---:|
| Total samples | 10 |
| Failed | 10 |
| Successful | 0 |
| Slow calls | 0 if every request completes under 700 ms |
| Failure rate | 100% |
| Slow call rate | 0% |
| State after enough samples | `OPEN` due to failure rate |

This scenario shows that failure rate is useful when the dependency returns errors quickly. Slow call rate does not need to cross its threshold for the breaker to open.

## 7. Scenario B: Dependency Succeeds Slowly

The second scenario simulates a dependency that still returns HTTP 200 but takes 1.2 seconds, which is greater than the 700 ms `slowCallDurationThreshold`. There is no exception, so the failure rate does not increase; the slow call rate increases.

```java
@GetMapping("/catalog/slow/{sku}")
public CatalogResult slow(@PathVariable String sku) throws InterruptedException {
    Thread.sleep(1200);
    return new CatalogResult(sku, "AVAILABLE");
}
```

In the lab, switch the target endpoint to `/catalog/slow/{sku}` and make 10 calls through a fresh `CLOSED` breaker. Ensure the gateway timeout is longer than 1.2 seconds, for example 2 seconds, so the calls complete successfully instead of timing out.

Expected results:

| Metric | Expected outcome |
|---|---:|
| Total samples | 10 |
| Failed | 0 |
| Successful | 10 |
| Slow calls | 10 |
| Failure rate | 0% |
| Slow call rate | 100% |
| State after enough samples | `OPEN` due to slow call rate |

This is a case where failure rate cannot detect degradation. Every call returns a successful result, yet latency is high enough to tie up resources and slow down upstream requests. Slow call rate allows the breaker to protect the dependency even before the backend starts returning errors.

## 8. Scenario C: Comparing Both Thresholds with the Same Sample Set

Execute a deliberate batch of 10 outcomes:

| Call | Result | Duration | Failure? | Slow? |
|---:|---|---:|---|---|
| 1 | 200 | 100 ms | No | No |
| 2 | 200 | 120 ms | No | No |
| 3 | 503 | 90 ms | Yes | No |
| 4 | 200 | 1,000 ms | No | Yes |
| 5 | 503 | 110 ms | Yes | No |
| 6 | 200 | 1,100 ms | No | Yes |
| 7 | 200 | 150 ms | No | No |
| 8 | 503 | 130 ms | Yes | No |
| 9 | 200 | 900 ms | No | Yes |
| 10 | 200 | 1,200 ms | No | Yes |

The sample set has 3 failures and 4 slow calls:

- Failure rate = 3 / 10 = 30%.
- Slow call rate = 4 / 10 = 40%.
- With `failureRateThreshold: 50`, the error threshold is not reached.
- With `slowCallRateThreshold: 40`, the slow call threshold is reached.

The breaker can open because of the slow call rate. If only `failureRateThreshold` were configured, the system would remain `CLOSED` with this sample set even though 4 out of 10 calls exceeded the target duration.

To test the opposite case, keep the sample count at 10 but generate 6 fast failures and 4 fast successes. The failure rate is 60% and the slow call rate is 0%; the breaker opens due to failure rate. These two experiments confirm that the two thresholds operate independently.

## 9. Inspecting Breaker State and Metrics

While running the lab, observe both state and statistics. With the native Resilience4j API, you can fetch the breaker from `CircuitBreakerRegistry` to read its metrics:

```java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

public void printMetrics(CircuitBreakerRegistry registry) {
    CircuitBreaker breaker = registry.circuitBreaker("catalogLab");
    CircuitBreaker.Metrics metrics = breaker.getMetrics();

    System.out.println("state=" + breaker.getState());
    System.out.println("buffered=" + metrics.getNumberOfBufferedCalls());
    System.out.println("failed=" + metrics.getNumberOfFailedCalls());
    System.out.println("successful=" + metrics.getNumberOfSuccessfulCalls());
    System.out.println("failureRate=" + metrics.getFailureRate());
    System.out.println("slowCallRate=" + metrics.getSlowCallRate());
}
```

This snippet illustrates the native Resilience4j API. In Spring Boot, inject the registry managed by auto-configuration rather than creating a new registry yourself and accidentally reading a different breaker than the one the gateway uses.

Before `minimumNumberOfCalls` is reached, the failure rate or slow call rate may be undefined and is typically represented as `-1.0`. Do not interpret `-1.0` as a negative rate or as zero errors; it indicates that there are not yet enough samples to evaluate. Once enough samples exist, read both rates alongside the buffered call count and state.

## 10. Comparing the Circuit-Opening Cases

With the lab configuration above, the cases can be summarized as follows:

| Scenario | Failure rate | Slow call rate | Open condition met? | Reason for opening |
|---|---:|---:|---|---|
| 10 fast failures | 100% | 0% | Yes | Failure rate |
| 10 slow successes | 0% | 100% | Yes | Slow call rate |
| 3 fast failures, 4 slow successes, 3 fast successes | 30% | 40% | Yes | Slow call rate |
| 2 fast failures, 2 slow successes, 6 fast successes | 20% | 20% | No | Remains closed |
| 6 fast failures, 4 fast successes | 60% | 0% | Yes | Failure rate |

The two thresholds use a logical OR for the decision: only one threshold needs to meet its condition after sufficient samples for the breaker to transition to `OPEN`. Both failure rate and slow call rate do not have to exceed their thresholds simultaneously.

## 11. Tuning Thresholds to Your SLOs

`slowCallDurationThreshold` should be chosen based on the dependency's latency budget and the overall request deadline. If the SLO for the catalog call is p95 under 500 ms, a 700 ms threshold can be a reasonable starting point for the lab, whereas production requires analyzing actual latency histograms, network overhead, and peak load.

`slowCallRateThreshold` defines the acceptable proportion of slow calls in the window. Setting it to 20% means only one-fifth of calls need to be slow after reaching minimum samples for the breaker to open. Setting it to 80% lets the system tolerate more slow calls before opening the circuit, though resources may already be held for too long.

`failureRateThreshold` should reflect the error rate a dependency can tolerate before traffic should stop. Fast errors and slow errors carry different implications, so you do not need to use the same rate for every dependency.

When tuning, consider:

- p50/p95/p99 latency and response time distribution under normal conditions.
- Baseline error rate, including transient errors and classified business errors.
- Traffic volume per breaker ID and the time required to reach `minimumNumberOfCalls`.
- Overall deadline, HTTP client timeouts, and per-hop timeouts.
- Capacity of thread pools, connection pools, and queues.
- Fallback acceptability and impact on user-facing functionality.

Do not mechanically set `slowCallDurationThreshold` equal to the HTTP client timeout. If the client timeout is 2 seconds and the slow threshold is also 2 seconds, many timed-out requests may be recorded as failures without having much chance to be recorded as slow under the threshold. Setting the slow threshold lower than the timeout helps detect degradation before requests begin timing out.

## 12. Slow Call Rate Does Not Replace Timeouts or TimeLimiter

Slow call rate is a statistical and circuit-opening mechanism. It does not automatically abort an in-flight call when duration crosses `slowCallDurationThreshold`. For example, if the slow threshold is 700 ms but an HTTP request completes in 1.5 seconds, the breaker can record it as a slow call after completion; it does not cancel the request at the 700 ms mark.

To bound waiting time, you need to configure timeouts separately:

- Connect timeout bounds connection establishment time.
- Read/response timeout bounds waiting for data according to the HTTP client's semantics.
- Reactor `timeout` or Resilience4j TimeLimiter bounds waiting time for the publisher/task according to the API in use.
- Overall deadline bounds the entire request across multiple hops.

Therefore, use slow call rate to detect degrading latency trends and use timeouts/deadlines to cap wait times. The two mechanisms complement each other.

## 13. Impact of HALF_OPEN and Probes

After the breaker opens and `waitDurationInOpenState` elapses, the breaker can transition to `HALF_OPEN` and grant a number of probe calls. Probe outcomes are also evaluated against both failure rate and slow call rate. If probes fail or are slow at a high enough rate, the breaker can return to `OPEN`; if the results are good enough, the breaker can return to `CLOSED`.

When a dependency has fluctuating latency, successful probes alone may not be enough to conclude recovery. A fast probe during low load might not represent behavior under normal load. Choose the probe count and thresholds according to backend capacity, avoiding sending too many concurrent requests as soon as the service begins responding again.

## 14. Extension Exercises

Make the following changes and record the before/after results:

1. Keep `failureRateThreshold: 50` and raise `slowCallRateThreshold` from 40 to 70. Re-run the scenario with 3 fast failures and 4 slow calls; determine whether the breaker still opens due to slow call rate.
2. Keep `slowCallRateThreshold: 40` and increase `slowCallDurationThreshold` from 700 ms to 1,000 ms. Re-run the 900 ms and 1,200 ms calls; recalculate the slow call count.
3. Set `minimumNumberOfCalls: 5` and `slidingWindowSize: 10`. Send four failing calls and verify the breaker has not evaluated rates yet; send the fifth call and observe the state.
4. Create a call that times out after 1.2 seconds with `slowCallDurationThreshold: 700ms`. Confirm that it can be counted as both failed and slow if the timeout exception is recorded and execution duration exceeds the threshold.
5. Configure `ignoreExceptions` for a business error, generate ignored error samples, and verify they do not increase the failure rate or the success/failure sample count.
6. Compare a single breaker shared across multiple endpoints versus dedicated breakers per operation. Observe how one slow endpoint affects the others.

When recording results, capture successful calls, failed calls, slow calls, buffered calls, failure rate, slow call rate, and state. Do not record only the final state, because `OPEN` alone does not tell you which threshold triggered it.

## 15. Lab Summary Checklist

Before choosing a policy for a real dependency, verify:

- Failure rate detects fast errors such as HTTP 5xx or connection failures.
- Slow call rate detects cases where calls succeed but exceed the latency budget.
- A single call can be both failed and slow; do not count it as two separate samples.
- `minimumNumberOfCalls` has been met before interpreting either rate.
- `slowCallDurationThreshold` is chosen based on SLOs and lower than timeouts when early degradation detection is needed.
- Timeouts/TimeLimiter remain configured to cap actual wait times.
- Fallbacks do not turn uncertain data into incorrect business results.
- Metrics and logs indicate whether the breaker opened due to failure rate or slow call rate.

Failure rate and slow call rate are two complementary signals. Failure rate protects the system when a dependency frequently fails; slow call rate enables early detection of overly slow responses even when requests still succeed. By building two separate scenarios, calculating rates from the same sliding window, and comparing them against breaker state, development teams can select thresholds suited to target latency, traffic volume, and the level of protection needed for each dependency.
