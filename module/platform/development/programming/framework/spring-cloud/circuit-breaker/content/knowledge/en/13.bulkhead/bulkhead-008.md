# Distinguishing BulkheadFullException from CallNotPermittedException

In a Spring Cloud application using Resilience4j, both `Bulkhead` and `CircuitBreaker` can reject a call before the dependency-calling code executes. However, the two mechanisms reject for different reasons and throw different exceptions:

- `BulkheadFullException` indicates that the bulkhead's concurrent resource limit or queue capacity has been reached. The application is currently not accepting more work in the protected region.
- `CallNotPermittedException` indicates that the circuit breaker does not grant permission to execute the call, usually because the breaker is `OPEN` or no trial calls remain in `HALF_OPEN`.

Distinguishing these two exceptions helps the gateway select the right fallback, avoid retries that add load, and keep circuit breaker statistics accurately reflecting dependency health. Bulkhead controls how much work runs concurrently; circuit breaker evaluates recent call outcomes to decide whether to continue making calls.

## 1. Two Exceptions Represent Two Different Rejection Conditions

| Exception | Resilience4j Package | Triggering Mechanism | Did the call reach the target service? |
|---|---|---|---|
| `BulkheadFullException` | `io.github.resilience4j.bulkhead.BulkheadFullException` | Failed to acquire a permit or enqueue the task in the bulkhead | No, the call was rejected at the bulkhead |
| `CallNotPermittedException` | `io.github.resilience4j.circuitbreaker.CallNotPermittedException` | Circuit breaker did not grant permission to run the supplier | No, the protected supplier did not run |

Both exceptions can surface in a Spring Cloud CircuitBreaker fallback, but their operational meanings differ. `BulkheadFullException` typically signals concurrency pressure or queue limits in the calling process. `CallNotPermittedException` signals that the circuit breaker policy is blocking calls due to its state or available permissions.

A rejected request does not mean the target service just returned an error. In both cases, that specific call may never have sent any HTTP request to the backend. Therefore, do not log both as HTTP 5xx responses from the target service or lump them into the same network error category.

## 2. When Does BulkheadFullException Occur?

Bulkhead caps the amount of work allowed into a protected region. Its goal is to prevent a slow dependency or task group from exhausting threads, connections, or resources across the entire application.

Resilience4j has two commonly used bulkhead types:

- **Semaphore bulkhead:** limits concurrent calls using permits. When no permits remain and the call cannot wait further, the bulkhead rejects it with `BulkheadFullException`. If `maxWaitDuration` is greater than 0, the call can wait up to that duration for a permit; if none is acquired before the timeout expires, it is rejected.
- **Thread pool bulkhead:** uses a dedicated thread pool and queue to execute asynchronous tasks. When neither the thread pool nor the queue can accept more work, new tasks are rejected; Resilience4j represents this full state with `BulkheadFullException`.

For example, the inventory service's semaphore bulkhead allows only 20 concurrent calls:

```yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 20
        maxWaitDuration: 0
```

If 20 calls are holding permits, the 21st call is rejected immediately because `maxWaitDuration` is 0. The inventory service may still be healthy; the calling application is proactively capping how many requests may pass through to protect its own resources.

With a thread pool bulkhead, pool size and queue capacity can be configured separately:

```yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 5
        maxThreadPoolSize: 10
        queueCapacity: 20
        keepAliveDuration: 20ms
```

In this example, the thread pool can scale up to 10 threads and the queue holds at most 20 tasks. Once the pool reaches its limit and the queue is full, new tasks are not accepted. Actual values must be chosen based on processing time, CPU resources, connection counts, and the load the backend can sustain.

Bulkhead does not measure failure rates to decide whether to open a circuit. It only caps accepted work. `BulkheadFullException` is therefore typically a signal of overload or admission rejection at the calling application, not proof that the backend returned an error.

## 3. When Does CallNotPermittedException Occur?

Circuit breaker tracks call outcomes and dependency state. When `CLOSED`, the breaker allows the supplier to run and records outcomes. When the failure rate or slow-call rate exceeds a threshold after enough samples, the breaker transitions to `OPEN`.

In the `OPEN` state, the breaker rejects new calls immediately. Resilience4j throws `CallNotPermittedException` without invoking the supplier. After the wait duration elapses, the breaker can transition to `HALF_OPEN` to allow a limited number of trial calls. Once those trial permits are all handed out, additional calls can also be rejected with `CallNotPermittedException` until results arrive and the breaker transitions state.

Example circuit breaker configuration for the inventory service:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
```

If the breaker is `OPEN`, new requests are rejected without adding load to the inventory service. When it transitions to `HALF_OPEN`, at most three trial calls are allowed per the configuration. Calls arriving after all trial permissions have been allocated can be rejected with `CallNotPermittedException`.

`CallNotPermittedException` therefore does not indicate that the supplier just timed out or that the target service just returned a 500. It indicates that the breaker is enforcing its protective policy and refusing to let calls proceed.

## 4. Comparing Cause and Impact

| Aspect | `BulkheadFullException` | `CallNotPermittedException` |
|---|---|---|
| Reason | Out of concurrent execution or queue capacity | Circuit breaker did not grant execution permission |
| Scope | Concurrency/queue limits of a bulkhead | State and permissions of a circuit breaker |
| Operational signal | Resource pressure or admission limit | Dependency is being protected by the breaker or undergoing bounded probing |
| Supplier of current call | Not invoked if the bulkhead rejects before execution | Not invoked when the breaker rejects |
| Should we retry immediately? | Usually no; immediate retries increase pressure | No; wait for breaker state change or use a fallback |
| Remediation direction | Reduce concurrency, throttle traffic, inspect permit hold time and queue | Inspect breaker state, recent failures/slow calls, and recovery duration |

Practical example: the pricing service is processing many slow requests. The bulkhead limits concurrent calls to 15; once all 15 permits are taken, new requests receive `BulkheadFullException`. Meanwhile, the pricing service's circuit breaker may still be `CLOSED` because it has not collected enough samples or the failure rate has not crossed the threshold. If many requests subsequently time out and the breaker opens, subsequent requests may receive `CallNotPermittedException`.

## 5. Wrapping Order of Bulkhead and CircuitBreaker Affects Observed Exceptions

When both mechanisms are used together, decorator order determines which mechanism checks first. If both the bulkhead is full and the circuit breaker is `OPEN`, the exception observed depends on the outermost layer.

### CircuitBreaker Outside, Bulkhead Inside

```java
Supplier<InventoryView> protectedCall =
        CircuitBreaker.decorateSupplier(
                circuitBreaker,
                Bulkhead.decorateSupplier(
                        bulkhead,
                        () -> inventoryClient.find(sku)
                )
        );
```

Execution flow:

1. Circuit breaker checks and grants permission.
2. If the breaker is `OPEN`, it throws `CallNotPermittedException`; neither bulkhead nor HTTP client is called.
3. If the breaker permits, the bulkhead attempts to acquire a permit.
4. If the bulkhead is full, it throws `BulkheadFullException`; the HTTP supplier does not run.
5. If the bulkhead grants a permit, the call to the inventory service executes.

In this order, the circuit breaker wraps the bulkhead and can observe `BulkheadFullException` as an exception from the supplier. Without appropriate ignore configuration, local rejections can inflate the circuit breaker's failure rate even though the backend never received the request.

### Bulkhead Outside, CircuitBreaker Inside

```java
Supplier<InventoryView> protectedCall =
        Bulkhead.decorateSupplier(
                bulkhead,
                CircuitBreaker.decorateSupplier(
                        circuitBreaker,
                        () -> inventoryClient.find(sku)
                )
        );
```

Execution flow:

1. Bulkhead attempts to acquire a permit first.
2. If the bulkhead is full, it throws `BulkheadFullException`; the circuit breaker is not called.
3. If the bulkhead grants a permit, the circuit breaker checks its state.
4. If the breaker is `OPEN`, it throws `CallNotPermittedException`; the HTTP supplier does not run and the bulkhead permit is released when the call finishes with the exception.
5. If the breaker grants permission, the supplier executes the call.

In this order, the circuit breaker does not observe `BulkheadFullException` because the exception occurs in the outer layer. The two compositions exhibit different observable behavior; choose based on the application's failure-measurement and load-control policies.

## 6. Prevent Full-Bulkhead Errors from Distorting Failure Rate

When CircuitBreaker wraps Bulkhead, `BulkheadFullException` can pass through the breaker's supplier. By default, exceptions thrown by the supplier are typically counted as failures unless ignored or classified by a predicate. If the goal is to measure dependency errors, counting local rejection errors toward the failure rate can trip the breaker solely because of the calling application's concurrency limit.

You can ignore `BulkheadFullException` in the circuit breaker configuration:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        ignoreExceptions:
          - io.github.resilience4j.bulkhead.BulkheadFullException
```

An ignored exception is counted as neither a success nor a failure in the sliding window. It can still be handled in a fallback and recorded in dedicated metrics. This keeps bulkhead rejections separate from genuine dependency failures.

Do not treat `CallNotPermittedException` as a normal supplier failure either. The breaker throws this exception itself when rejecting a call; a blocked call is not a failed backend call. Track breaker rejections via their corresponding events/metrics instead of adding them to target-service HTTP errors.

If the application wants bulkhead rejections to contribute to an overall overload indicator, create dedicated metrics for rejection counts, active permits, and permit wait times. Do not use the circuit breaker's failure rate as a substitute for admission-control metrics.

## 7. Classifying Exceptions in Fallbacks

Spring Cloud CircuitBreaker lets you supply a fallback that accepts a `Throwable`. The gateway can distinguish the two exceptions to return an appropriate status:

```java
import io.github.resilience4j.bulkhead.BulkheadFullException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;

public InventoryView find(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.find(sku),
            failure -> {
                if (hasCause(failure, BulkheadFullException.class)) {
                    return InventoryView.busy(sku);
                }
                if (hasCause(failure, CallNotPermittedException.class)) {
                    return InventoryView.temporarilyUnavailable(sku);
                }
                return InventoryView.unavailable(sku);
            }
    );
}

private boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {
    for (Throwable current = error;
         current != null;
         current = current.getCause()) {
        if (expectedType.isInstance(current)) {
            return true;
        }
    }
    return false;
}
```

`InventoryView.busy`, `temporarilyUnavailable`, and `unavailable` are illustrative application states. Actual fallback types must match the API contract. Some integration layers or adapters may wrap exceptions inside another exception; traversing the cause chain helps avoid missing the root cause. If the system uses custom wrappers, verify the actual exception structure before classifying.

Do not return an inventory count of 0 for both cases. When the bulkhead is full or the circuit breaker is open, the application does not know the real inventory level. `BUSY` or `UNAVAILABLE` clearly communicates that the data is unconfirmed. If a cache exists, you can return the latest cached data along with a timestamp and stale flag when business logic allows.

## 8. Choosing Appropriate Retry Behavior

Retrying immediately on `BulkheadFullException` typically worsens congestion. Multiple clients may retry simultaneously and keep competing for permits. If retries are needed, use backoff and jitter, cap attempts, or let the calling layer throttle its rate. For interactive requests, returning a busy status early is often better than keeping requests waiting for a long time.

For `CallNotPermittedException`, the breaker is actively blocking calls. Retrying repeatedly while the breaker is `OPEN` only creates more rejected requests and noisy logs/metrics. Wait until recovery duration elapses or let a later request probe when the breaker transitions to `HALF_OPEN`. Avoid having many clients retry in lockstep right when the open duration expires; backoff and jitter help reduce sudden load spikes.

| Scenario | Appropriate response |
|---|---|
| Semaphore bulkhead out of permits | Reject fast or wait within the configured short limit; inspect concurrency and permit hold times |
| Thread pool bulkhead and queue full | Slow down work intake; review pool/queue sizes and processing times |
| Circuit breaker `OPEN` | Fallback or return temporarily unavailable status; do not retry continuously |
| Circuit breaker `HALF_OPEN` out of trial permits | Let the active trial calls complete; avoid generating extra concurrent requests |

When retrying an operation with side effects, such as creating an order or processing a payment, always use an idempotency key or duplicate-request detection. A request rejected by a bulkhead or breaker usually did not reach the backend through that supplier, yet you should never infer the outcome of earlier attempts from the current attempt's exception.

## 9. Monitoring Bulkhead and CircuitBreaker Separately

Do not merge all rejections into a single generic error metric. Tracking each mechanism separately shows whether the system lacks concurrent capacity or is protecting a degraded dependency.

**For Bulkhead**, monitor:

- Permits currently in use and remaining available permits.
- Calls rejected due to failing to acquire a permit.
- Permit wait duration if `maxWaitDuration` is greater than 0.
- Thread pool size, active threads, and queue length if using a thread pool bulkhead.
- Permit hold time and protected call latency.

**For CircuitBreaker**, monitor:

- States `CLOSED`, `OPEN`, `HALF_OPEN`, and state transition counts.
- Failure rate, slow-call rate, and sample count in the sliding window.
- Calls rejected because the breaker did not grant permission.
- Successful calls, failed calls, and fallback invocations.

Resilience4j exposes events and metrics per component when integrated with Micrometer/Actuator. Exact metric names depend on version and configuration; inspect your application's metrics endpoint rather than assuming identical names across all versions. Use breaker/bulkhead ID and dependency as bounded labels; avoid putting request IDs or user IDs into metric labels.

Ways to interpret signals:

- `BulkheadFullException` rises while circuit breaker stays `CLOSED`: inspect concurrency, queue, thread pool, and response times; you cannot yet conclude the backend is returning errors.
- `CallNotPermittedException` rises and breaker is `OPEN`: inspect failure/slow-call rates prior to opening and verify fallbacks are working.
- Both rise together: the system may face both concurrency pressure and an open breaker; check decorator order to understand which exception is observed per request.
- Bulkhead fills frequently while backend latency is normal: concurrency limits may be too low or traffic is spiking; tune based on measured load and backend capacity.
- Bulkhead is full alongside rising latency and exhausted connection pools: the dependency may be slowing down, causing permits to be held longer; evaluate timeouts and the circuit breaker together.

## 10. Testing Both Rejection Cases

Tests should verify the exception type, supplier invocation count, and statistics of each mechanism. You can build the following scenarios:

1. **Full bulkhead:** hold all permits with in-flight tasks, send one more call, and assert `BulkheadFullException` is thrown when waiting is exhausted.
2. **Bulkhead with wait duration:** hold permits longer than `maxWaitDuration`, then assert the waiting call is rejected upon timeout.
3. **Full thread pool and queue:** occupy all worker threads and fill the queue, then assert the next task is rejected.
4. **Circuit breaker `OPEN`:** transition the breaker to `OPEN`, invoke the supplier, and assert `CallNotPermittedException` is thrown while the supplier counter does not increment.
5. **Circuit breaker `HALF_OPEN`:** consume all trial permissions, send another call, and assert the extra call is rejected.
6. **Both mechanisms limiting simultaneously:** configure a full bulkhead and an `OPEN` breaker, then swap decorator order to confirm the exception originates from the outer layer evaluated first.
7. **Failure rate:** add `BulkheadFullException` to `ignoreExceptions` when the breaker wraps the bulkhead and assert rejection errors do not increment failure or success sample counts.
8. **Fallback:** verify the fallback distinguishes `BUSY` from `UNAVAILABLE` and does not trigger unintended extra HTTP requests.

In tests, use latches or publisher control hooks to hold permits deterministically, avoiding arbitrary `sleep` calls that cause flaky results. Test the happy path, direct exceptions, and wrapped exceptions if the application has custom adapter layers.

## 11. Diagnostic Workflow When Encountering Exceptions

When the gateway receives either exception, follow this sequence:

1. Inspect the outermost exception and cause chain to identify the actual exception type.
2. Determine whether the request hit the bulkhead or the circuit breaker first, based on decorator order and integration settings.
3. If `BulkheadFullException`, inspect permits, queue, thread pool, permit hold duration, and latency of running tasks.
4. If `CallNotPermittedException`, inspect breaker state, failure/slow-call rates, sample counts, and time in `OPEN` or `HALF_OPEN` permissions.
5. Verify the fallback distinguishes a busy status due to admission control from a dependency blocked by the breaker.
6. Review the retry policy to ensure no extra load is generated while requests are being rejected.
7. Cross-reference bulkhead and circuit breaker metrics with backend call traces before changing thresholds.

Both `BulkheadFullException` and `CallNotPermittedException` indicate that a call was not executed, yet they point to two different protective layers. Bulkhead rejects because work acceptance capacity is exhausted; circuit breaker rejects because its state policy does not permit calling the dependency. Classifying the two exceptions separately, understanding composition order, and tracking the corresponding metrics help a Spring Cloud application control concurrency, protect degraded services, and return meaningful fallbacks.
