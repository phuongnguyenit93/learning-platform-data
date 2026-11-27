# Regression Testing Metrics, Execution Flows, and Fallback Semantics

When switching Spring Cloud Circuit Breaker backends, upgrading Spring Cloud/Resilience4j versions, or changing configuration approaches, an application may still compile and start up while its protection behavior has shifted. A changed threshold, differently classified exception, differently timed fallback, or newly nested retry can alter both the response callers receive and the load sent to dependencies.

Regression testing must compare the application's **observable contract** before and after migration: returned data, exceptions, dependency call counts, breaker states, failure/slow-call metrics, fallbacks, and processing times. It is not enough to merely check that the `CircuitBreakerFactory` bean is created or that an endpoint returns HTTP 200.

In the Spring Cloud Circuit Breaker module, the backend may be Resilience4j or another implementation such as Spring Retry. Each backend has its own statistical model, event API, and metrics. Therefore, tests should separate two layers: verifying the business behavior every backend must preserve, and then verifying the specific properties of the new backend.

## Capturing a Baseline Before Migration

Before changing dependencies or configuration, capture a baseline from the running version. The baseline must use the same dataset, load, fault injection, and request deadlines so comparisons are fair.

| Category | Baseline to Record |
|---|---|
| Response | HTTP status, schema, data fields, headers, and degraded-result semantics |
| Dependency calls | Call count, retry count, timeouts, connection errors, and rejected requests |
| Circuit breaker | Instance ID, states, state transition timestamps, thresholds, and windows |
| Fallback | Trigger conditions, invocation count, returned output, and errors raised inside fallback |
| Latency | p50, p95, p99, dependency wait time, and end-to-end request duration |
| Resources | In-flight calls, connection pool, threads, Bulkhead rejections, and cancellations |
| Telemetry | Metrics, tags, events, logs, and traces usable for diagnostics |

Record the exact versions of Spring Boot, Spring Cloud release train, Circuit Breaker backend, and Resilience4j/Spring Retry. During migration, keep load and failure scenarios unchanged so observed differences stem primarily from the new integration. Changing timeouts, retries, and thresholds at the same time makes it hard to isolate the root cause of any difference.

## Building a Behavioral Regression Matrix

Each protected dependency should have a minimum regression matrix describing inputs, failure conditions, and behaviors to preserve:

| Scenario | Behavior to Verify |
|---|---|
| Dependency succeeds quickly | Caller receives expected data; fallback does not run; one business call produces the expected number of requests |
| Dependency returns recorded error | Breaker records failure; caller receives fallback or exception per contract |
| Ignored exception | Does not increase failure rate if exception is configured to be ignored |
| Dependency responds slowly | Slow-call rate increases per threshold; response may still succeed |
| Request exceeds timeout | Caller finishes within deadline; timeout is classified properly and does not hold resources indefinitely |
| Breaker `OPEN` | Supplier is not invoked; call is rejected; fallback or rejection error matches contract |
| Breaker `HALF_OPEN` | Probe count does not exceed quota; good/bad outcomes transition breaker to the right state |
| Fallback also fails | Exception from fallback propagates per contract; second failure is not masked |
| Retry is triggered | Attempt count, backoff, and total duration stay within defined bounds |
| Request is canceled | Cancellation propagates to publisher/client and resources are released |

The matrix must verify both external results and how many times the dependency was called. A fallback response with the right payload that unintentionally called the dependency three times is still a load regression and can trigger cascading failures.

## Checking Configuration and Sliding Window Semantics

When switching backends or versions, identically named properties may have different semantics, or the new backend may not support certain legacy properties. Explicitly verify:

- `slidingWindowType`, `slidingWindowSize`, and `minimumNumberOfCalls`.
- `failureRateThreshold` and `slowCallRateThreshold`.
- `slowCallDurationThreshold`.
- `waitDurationInOpenState`, `permittedNumberOfCallsInHalfOpenState`, and `maxWaitDurationInHalfOpenState`.
- `recordExceptions`, `ignoreExceptions`, and error-classification predicates.
- How auto-transition, TimeLimiter, Bulkhead, and metrics are enabled.

In Resilience4j, failure rate and slow-call rate are calculated separately over the same denominator. A call that is both failed and slow contributes to both specialized counts while incrementing total calls once. The breaker opens when either rate reaches its threshold once enough samples exist. Write boundary tests for rates exactly equal to the threshold, since the "reached threshold" condition includes equality.

If the old backend only had a retry policy or a time-based open/reset circuit breaker, its numbers cannot be compared directly to Resilience4j's sliding window. Document semantic differences explicitly and define application-level equivalence criteria, such as the maximum duration requests continue being sent after a dependency fails.

Example Resilience4j state-machine test with a small, deterministic window:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(30))
        .permittedNumberOfCallsInHalfOpenState(2)
        .build();

CircuitBreaker breaker = CircuitBreaker.of("catalog-test", config);

for (int i = 0; i < 2; i++) {
    assertThrows(IllegalStateException.class,
            () -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("dependency failed");
            }));
}
for (int i = 0; i < 2; i++) {
    assertEquals("ok", breaker.executeSupplier(() -> "ok"));
}

assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
assertEquals(50.0f, breaker.getMetrics().getFailureRate(), 0.01f);
assertThrows(CallNotPermittedException.class,
        () -> breaker.executeSupplier(() -> "must not run"));

breaker.transitionToHalfOpenState();
assertEquals("probe-1", breaker.executeSupplier(() -> "probe-1"));
assertEquals("probe-2", breaker.executeSupplier(() -> "probe-2"));
assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
```

This test uses explicit state transitions to verify how the breaker evaluates probes; it does not replace integration testing for automatic `OPEN` to `HALF_OPEN` transitions over real elapsed time. For timer tests, use test clocks or schedulers supported by the backend rather than relying on long sleeps.

## Testing Exception Classification

A small change in the exception type thrown by an HTTP client can swing the failure rate dramatically. For example, an older backend might receive `ResourceAccessException`, while a newer client throws `WebClientRequestException` or `TimeoutException`. If `recordExceptions` is not updated, the new breaker may treat connection errors as successes or accidentally ignore them.

Write dedicated tests for each exception category:

| Outcome Type | What to Verify |
|---|---|
| Recorded exception | Failure counter increments and failure rate updates |
| Ignored exception | Failure counter does not increment; confirm it is not miscounted as a success |
| Valid business exception | Does not open the breaker if the contract treats it as a normal outcome |
| Client timeout | Classified properly per policy; completion stays within deadline |
| `CallNotPermittedException` | Dependency is not called; verify fallback handles it per policy |
| `BulkheadFullException` | Distinguishes local concurrency rejection from remote dependency failure |

Do not assert only the final exception type the caller receives. A fallback may turn the original exception into a DTO; inspect the pre-fallback exception or the breaker's metrics/events to confirm the root failure was recorded properly.

## Regression Testing Fallback Semantics

Fallbacks are part of the application contract. When changing backends, verify both trigger conditions and outputs:

1. Fallback runs when the supplier fails according to the defined policy.
2. Fallback runs when the breaker rejects calls in `OPEN`, if required by design.
3. Fallback does not run when the dependency succeeds.
4. Fallback does not convert validation or authorization errors into valid-looking mock data.
5. Fallback returns the documented schema, status code, data source, and freshness guarantees.
6. Fallback runs only the expected number of times and never re-calls the failing dependency.
7. If the fallback throws an exception, the caller receives that error per contract while telemetry preserves the original cause.

Example fallback test using Spring Cloud's `CircuitBreaker` API:

```java
AtomicInteger dependencyCalls = new AtomicInteger();
AtomicInteger fallbackCalls = new AtomicInteger();

String result = circuitBreaker.run(
        () -> {
            dependencyCalls.incrementAndGet();
            throw new IOException("catalog unavailable");
        },
        error -> {
            fallbackCalls.incrementAndGet();
            return "cached-result";
        }
);

assertEquals("cached-result", result);
assertEquals(1, dependencyCalls.get());
assertEquals(1, fallbackCalls.get());
```

This is a synchronous API-level test for Spring Cloud Circuit Breaker. For reactive paths, the fallback must return a `Mono`/`Flux` of the same element type, and you should use `StepVerifier` to verify subscriptions, signals, and cancellation. Do not treat a fallback emitting `onNext` followed by `onComplete` as proof that the dependency succeeded; the breaker must still record the outcome of the protected source.

### Differentiating Fallbacks by Root Cause

If a fallback handles multiple causes, test each cause independently. `CallNotPermittedException` means the breaker denied permission to call; a timeout means the request ran but did not finish in time; a connection error may occur before the server receives the request. These situations can require different responses, especially for operations with side effects and uncertain outcomes.

Never retry a write operation with a fresh idempotency key merely because of a timeout. When you do not know whether the dependency processed the request, preserve the key and query status or retry with the same key per the downstream contract.

## Testing Retry, CircuitBreaker, and TimeLimiter Ordering

When changing how calls are wrapped, decorator ordering can change how many events the breaker records:

- `Retry(CircuitBreaker(call))`: each attempt passes through the breaker; the breaker can observe every individual failure.
- `CircuitBreaker(Retry(call))`: the breaker observes only the final outcome of the entire retry sequence.

Verify actual call counts, total elapsed time, and recorded failures. For example, if retries are capped at three attempts, tests must prove the dependency is called at most three times and total duration stays within the caller's deadline. When the breaker is `OPEN`, do not keep retrying `CallNotPermittedException`; that rejection is an intentional short-circuit decision.

TimeLimiter and HTTP client timeouts must also be verified separately. Per-attempt timeouts must fit the overall deadline; three retries with a four-second timeout can make the caller wait far longer than the SLO if no outer deadline exists. A timeout at one layer does not guarantee the remote request stopped, so check cancellation and in-flight resources.

## Normalizing Metrics for Backend Comparison

Metric names, tags, and event emission formats may vary across backends or versions. Avoid writing regression tests tightly coupled to every internal metric name unless the application treats them as a public API. Instead, build a normalized observation model at the application level:

```java
public record BreakerObservation(
        String dependency,
        String state,
        long successfulCalls,
        long failedCalls,
        long slowCalls,
        long notPermittedCalls,
        Double failureRate,
        Double slowCallRate
) {}
```

Each backend's telemetry adapter maps only the metrics it genuinely supports into this model. If the legacy backend lacked a slow-call metric, represent that field as unsupported/unavailable rather than assuming `0`. `0` means it was measured and zero slow calls occurred; `null` or an unsupported state means the backend does not provide that measurement.

When comparing before and after migration, use consistent definitions for:

- Successful, failed, slow, and rejected calls.
- Which denominator and time window rates are computed over.
- Dependency ID and replica identity.
- When events fire and how retry attempts are counted.
- Tag cardinality and aggregation across pods.

Resilience4j internal metrics can be exported through Micrometer when the required dependency is present. Verify metrics at the application's scrape/registry boundary and confirm `name`/dependency tags stay stable. Never put request IDs, user IDs, or URL parameters into metric labels.

## Testing Reactive Paths and Cancellation

With `ReactiveCircuitBreaker`, use `StepVerifier` to verify the signals observed by callers:

```java
when(catalogClient.findProduct("p-1"))
        .thenReturn(Mono.error(new IOException("catalog offline")));

StepVerifier.create(catalogService.findProduct("p-1"))
        .assertNext(product -> {
            assertEquals("p-1", product.id());
            assertFalse(product.isAvailable());
        })
        .verifyComplete();

verify(catalogClient, times(1)).findProduct("p-1");
```

Additionally verify:

- The source Publisher is subscribed to only when the caller subscribes.
- The fallback is subscribed to when the source errors or the breaker rejects.
- `Mono`/`Flux` emits no further signals after `onError` or `onComplete`.
- Cancellation propagates to the client and releases Bulkhead permits/resources.
- Retries do not trigger unexpected extra subscriptions.
- Timeouts sit inside the boundary that the circuit breaker needs to record.

`StepVerifier.withVirtualTime` can control Reactor's scheduler for delays, retry backoff, and `timeout(Duration)`. It does not automatically control the internal clock of every circuit breaker backend or HTTP client. Use the proper test clock/scheduler mechanism provided by each library when testing time-based state transitions.

## Spring Context Integration Testing

Unit tests with mocks are helpful for verifying fallback logic and call counts, but they do not prove auto-configuration or factory wiring works. Add integration tests that boot the Spring context with the target backend and verify:

1. The right starter/backend is loaded.
2. The factory receives the expected IDs and instance configs.
3. Properties/Customizers take effect as intended.
4. AOP proxies activate if using Resilience4j annotations.
5. Metrics/events emit after real calls through Spring beans.
6. WebFlux and blocking paths use their respective matching factories.
7. No two unintended circuit breaker wrappers surround the same operation.

Invoke services through beans injected from the context. Manually instantiating classes with `new` bypasses Spring proxies and fails to test annotations/AOP. When using the factory, check actual IDs and ensure registries/instances are not recreated per request.

## Load Comparison and Canary Rollout

Once functional tests pass, run the same load profile against both old and new versions. Compare throughput, p95/p99 latency, error rates, fallback counts, rejected request counts, concurrency, and resource utilization. Pay special attention to dependency degradation: does the new backend cut off requests early enough, does it generate more retries, and does it leave requests hanging after state transitions?

Roll out step by step:

1. Run regression and contract tests in CI.
2. Run integration tests against a mock dependency capable of fast success, errors, slowness, and unresponsiveness.
3. Run load tests and fault injection with identical data across both versions.
4. Deploy the new backend to a canary group or fraction of traffic.
5. Compare normalized metrics and live responses against the baseline.
6. Expand rollout once SLOs, fallbacks, and dependency load stay within bounds; roll back if user-impacting discrepancies appear.

Do not judge the entire cluster from a single breaker state on one replica. Each JVM normally maintains a local state machine; observe per replica and aggregate with consistent semantics.

## Migration Acceptance Criteria

A migration should only be considered passing when:

- Responses and business contracts remain unchanged aside from approved differences.
- Exceptions are classified accurately; recorded errors are not ignored and business errors do not unintentionally open the breaker.
- Attempt counts, retries, timeouts, and total duration stay within deadlines.
- `CLOSED`, `OPEN`, `HALF_OPEN`, and probe quotas operate per defined policy.
- Fallbacks run under the right conditions, the right number of times, and return the expected schema/semantics.
- Metrics/events are observable and mapped consistently; unmappable differences are documented clearly.
- Cancellation releases resources; no requests hang after timeouts or state transitions.
- Load tests and canary deployments do not degrade SLOs or create abnormal dependency load.

## Final Regression Checklist

1. Save pre-migration versions, configurations, and baseline.
2. List every dependency, breaker ID, and failure domain.
3. Test success, errors, ignored exceptions, slow calls, and timeouts.
4. Test window size, minimum calls, thresholds, OPEN duration, and HALF_OPEN quota.
5. Test fallbacks for dependency errors, open breaker, business errors, and fallback failures.
6. Test attempt counts and Retry/CircuitBreaker/TimeLimiter ordering.
7. Test reactive subscriptions, signals, cancellation, and backpressure where applicable.
8. Normalize metrics and events; do not confuse unsupported metrics with zero values.
9. Run integration tests through the Spring context and real factories.
10. Run fault/load tests, canary rollout, and compare against baseline before expanding.

Thorough regression testing proves that the new integration still protects the right dependencies and preserves caller contracts. Compare behavior, metrics, and execution flows using deterministic scenarios; accept only differences that are intentional, explained, and observable in production operations.
