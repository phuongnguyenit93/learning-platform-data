# Distinguishing Fallbacks for Call Errors, Timeouts, and Open Circuits

Fallback is how an application produces an alternative response when a protected call cannot deliver a normal result. In Spring Cloud Circuit Breaker with Resilience4j, the fallback receives the `Throwable` that caused the recovery scenario. Because different causes can trigger a fallback, the application should classify the cause before selecting backup data or deciding to propagate the error to the caller.

Three cases that must be distinguished are errors from the dependent service, timeouts, and Circuit Breaker call rejections when `OPEN`. They carry different operational meanings: a call error indicates the dependency returned an error or failed to connect; a timeout indicates the result arrived too late; an open circuit indicates the application proactively withheld sending the request because risk was detected or probe permits in `HALF_OPEN` were exhausted.

## 1. Identifying the Cause Before Falling Back

| Cause | Common Exceptions | What Happened | Typical Handling |
| --- | --- | --- | --- |
| Error from dependent service | `HttpServerErrorException`, `WebClientResponseException`, `ResourceAccessException`, business exceptions | Request was sent or connection was attempted; dependency returned an error or failed to connect | Use valid cache, partial result, or report dependency unavailable |
| TimeLimiter timeout | `TimeoutException` | The protected call did not finish within the configured deadline | Use latest cached data, respond with undetermined status, or return timeout error |
| HTTP client timeout | E.g. `SocketTimeoutException` wrapped in `ResourceAccessException` or `WebClientRequestException` | The client layer timed out waiting for connection/response | Handle as communication failure while checking client timeout settings |
| Circuit Breaker rejection | `CallNotPermittedException` | Circuit is `OPEN`, or `HALF_OPEN` has exhausted permitted probe calls | Fast fallback, local cache, or return temporarily unavailable status |
| Bulkhead capacity full | `BulkheadFullException` from SemaphoreBulkhead or ThreadPoolBulkhead | System has no remaining slots or queue space to accept more work | Reject early, use local cache if safe, or report overload |

`CallNotPermittedException` does not mean the dependency just returned an error on the current request. The Circuit Breaker rejected the call before any call to the dependency was made. In `HALF_OPEN`, this exception can also appear once all permitted probe calls have been used.

Do not lump TimeLimiter timeouts and HTTP client timeouts into a single cause. TimeLimiter enforces a time limit at the protected execution layer; the HTTP client may time out while opening a connection or waiting for data. The exception types and cancellation behavior can differ. Inspect the `cause` chain to tell which layer expired.

## 2. Selecting Fallbacks by Business Semantics

Suppose an inventory-managing application calls `inventory-service` to retrieve the quantity of a SKU. Each error type should have its own policy:

- **Call errors or 5xx errors:** if the cache has data within the allowed age limit, return the cached data along with its update timestamp. If no cache exists, return an undetermined inventory status or a service-unavailable error.
- **Timeout:** prefer the latest cached data if business rules tolerate stale data. If stale data could lead to a wrong decision, return an undetermined status instead of assuming quantity equals 0.
- **Open circuit:** respond quickly with cache or a temporarily unavailable status. Never call the same dependency again from the fallback because the Circuit Breaker rejected the call to protect the system.
- **Bulkhead full:** treat this as an overload signal on the application or dependency. Do not enqueue additional work onto another unbounded queue; either return cached results or fail fast.
- **Business errors such as SKU not found:** generally preserve the 4xx error or business exception. Do not turn an input error into backup data that tricks the caller into thinking the SKU is valid.

Fallbacks must adhere to the API's data contract. When returning cached data, represent the data source and update timestamp so the caller knows it is stale. When no trustworthy value exists, returning an explicit error is usually safer than a plausible-looking default value.

## 3. Classifying Exceptions with Spring Cloud CircuitBreaker Factory

`CircuitBreakerFactory.create(id).run(supplier, fallback)` takes a `Supplier<T>` and a `Function<Throwable, T>`. The fallback function receives the exception that triggered the fallback. You can classify the exception right inside the function:

```java
public Stock getStock(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> inventoryFallback(sku, error)
    );
}

private Stock inventoryFallback(String sku, Throwable error) {
    Throwable cause = unwrapAsyncWrapper(error);

    if (cause instanceof CallNotPermittedException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    if (cause instanceof TimeoutException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"));
    }

    if (cause instanceof HttpServerErrorException
            || cause instanceof ResourceAccessException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }

    if (cause instanceof HttpClientErrorException clientError) {
        throw clientError; // Preserve 4xx business/input error
    }

    throw new InventoryLookupException("Unable to retrieve inventory", cause);
}
```

`inventoryClient`, `stockCache`, and the `Stock` types are illustrative application components. The snippet requires the corresponding Spring/Resilience4j imports, including `CallNotPermittedException`, `HttpServerErrorException`, `HttpClientErrorException`, `ResourceAccessException`, and `TimeoutException`.

For asynchronous calls, exceptions may be wrapped in `CompletionException` or `ExecutionException`. You can unwrap these layers before classifying:

```java
private Throwable unwrapAsyncWrapper(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Unwrap only known wrappers. Do not blindly traverse the entire `cause` chain because a business exception may intentionally wrap another exception as its cause. With WebClient, check both `WebClientResponseException` and `WebClientRequestException`; client-level timeout errors may sit deeper in the cause chain.

If the fallback does not recognize the error type, log the cause and propagate an appropriate error to the caller. Never convert every `Throwable` into a success response, as programming errors, authentication failures, or data errors could be masked.

## 4. Using Multiple Fallback Methods with Annotations

Resilience4j Spring Boot supports `fallbackMethod` on `@CircuitBreaker`, `@TimeLimiter`, `@Bulkhead`, and related aspects. Fallback selection behaves similarly to `catch` clauses: when multiple methods share the same name, Resilience4j picks the one with the most specific matching exception parameter type.

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;
    private final StockCache stockCache;

    public InventoryService(InventoryClient inventoryClient, StockCache stockCache) {
        this.inventoryClient = inventoryClient;
        this.stockCache = stockCache;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock stockFallback(String sku, CallNotPermittedException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    public Stock stockFallback(String sku, TimeoutException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"));
    }

    public Stock stockFallback(String sku, HttpServerErrorException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }

    public Stock stockFallback(String sku, HttpClientErrorException error) {
        throw error;
    }

    public Stock stockFallback(String sku, Throwable error) {
        throw new InventoryLookupException("Unable to retrieve inventory", error);
    }
}
```

Each fallback method resides in the same class as the protected method, has the same business parameters, and adds exactly one exception parameter at the end. Its return type must be compatible with the original method. You can declare a catch-all fallback accepting `Throwable` as the final branch, but preserve errors that do not belong to recoverable categories.

With `@TimeLimiter`, the protected method typically returns `CompletionStage` or `CompletableFuture`; the fallback must also return a compatible asynchronous type. Example:

```java
@TimeLimiter(name = "inventory", fallbackMethod = "stockTimeoutFallback")
public CompletableFuture<Stock> getStockAsync(String sku) {
    return inventoryClient.getStockAsync(sku);
}

public CompletableFuture<Stock> stockTimeoutFallback(
        String sku, TimeoutException error) {
    return CompletableFuture.completedFuture(
            stockCache.findFreshEnough(sku)
                    .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"))
    );
}
```

Annotation-based fallback methods execute as exception handlers and do not independently depend on the Circuit Breaker's current state. Thus, they can handle dependency errors when the circuit is `CLOSED`, timeouts, or `CallNotPermittedException` when the circuit rejects calls.

## 5. Fallbacks in Reactive Calls

With WebFlux, use `ReactiveCircuitBreakerFactory` and return a fallback publisher. Never call `.block()` inside a fallback:

```java
public Mono<Stock> getStock(String sku) {
    Mono<Stock> request = webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);

    return reactiveCircuitBreakerFactory.create("inventory").run(
            request,
            error -> {
                Throwable cause = unwrapAsyncWrapper(error);

                if (cause instanceof CallNotPermittedException) {
                    return stockCache.findFreshEnoughReactive(sku)
                            .switchIfEmpty(Mono.just(
                                    Stock.unavailable(sku, "CIRCUIT_OPEN")));
                }

                if (cause instanceof TimeoutException
                        || cause instanceof WebClientRequestException) {
                    return stockCache.findFreshEnoughReactive(sku)
                            .switchIfEmpty(Mono.just(
                                    Stock.unavailable(sku, "TIMEOUT_OR_NETWORK_ERROR")));
                }

                if (cause instanceof WebClientResponseException responseError
                        && responseError.getStatusCode().is5xxServerError()) {
                    return Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"));
                }

                return Mono.error(cause);
            }
    );
}
```

A reactive fallback must return a `Mono<T>` or `Flux<T>` matching the original publisher. Use `Mono.defer` if you need to defer cache lookup or fallback creation until subscription occurs. If the fallback itself emits an error, that error continues propagating to the subscriber and WebFlux handles it via the application's error mechanism.

For `Flux`, explicitly decide whether the fallback emits an alternative value, emits cached items, or completes with `Flux.empty()`. Returning `Flux.empty()` may cause callers to think no events occurred; use it only when that matches the API contract.

## 6. Timeouts, Open Circuits, and Call Errors Are Not the Same

Three causes may all return the same cached data, yet they must be tracked separately:

- **Call error:** the dependency returned an error or could not be reached. The Circuit Breaker records failures according to configured `recordExceptions`, `ignoreExceptions`, or predicates.
- **Timeout:** TimeLimiter or the HTTP client hit its wait deadline. With TimeLimiter, the result is usually `TimeoutException`; with clients, the exception may be `SocketTimeoutException` or a library-specific wrapper.
- **Open circuit:** the Circuit Breaker did not grant execution permission and threw `CallNotPermittedException`. Rejected requests do not place another call to the dependency.

Do not retry `CallNotPermittedException` immediately outside the Circuit Breaker in a tight loop. Subsequent attempts will still be rejected until the state allows calls, adding load to the application without actually probing the dependency. When using Retry for transient errors, configure retryable exception types and keep total retry duration within the request deadline.

If HTTP 4xx errors are expected business errors, consider configuring `ignoreExceptions` or `recordFailurePredicate` so the Circuit Breaker does not count them as dependency failures. Ignoring an error in failure metrics does not mean swallowing the exception; the caller can still receive the 4xx error.

A successful fallback does not prove the dependency has recovered. Monitor primary call outcomes, Circuit Breaker state, and fallback counts separately. When the circuit transitions to `HALF_OPEN`, only permitted probe calls provide evidence of recovery.

## 7. Designing Safe Fallbacks

Fallbacks should have bounded resources and isolated dependency paths:

- Use local caches or snapshots with an explicit maximum age; avoid calling back into the failing dependency.
- Do not introduce unbounded queues or infinite retries inside a fallback. Doing so can turn a fast failure into prolonged congestion.
- Configure timeouts and concurrency limits for remote cache sources if the fallback depends on another service.
- Distinguish `unavailable`, `unknown`, `stale`, and real business values. Never use zero or an empty list as an error signal if they are also valid domain data.
- Record clearly whether the fallback ran due to `CALL_ERROR`, `TIMEOUT`, `CIRCUIT_OPEN`, or `BULKHEAD_FULL` so operations can diagnose issues.

For HTTP APIs, the application can map backup results to a business response, `503 Service Unavailable` when no trustworthy substitute exists, or `504 Gateway Timeout` when a deadline expires. The choice depends on the API contract; not every fallback should return HTTP 200.

## 8. Monitoring Fallbacks and Circuit Breaker State

Add Actuator and `resilience4j-micrometer` to observe succeeded, failed, not-permitted, timed-out calls, and fallback invocations. Tag by instance name such as `inventory` to distinguish individual dependencies.

Signals to monitor together:

| Signal | Question to Answer |
| --- | --- |
| Circuit Breaker state and not-permitted calls | Is the circuit open or out of probe permits? |
| Circuit Breaker failed calls | Is the dependency returning errors or are timeouts counted as failures? |
| TimeLimiter timeout count | How many calls exceeded the deadline? |
| Fallback count by reason | Why are callers receiving backup data? |
| Cache hit rate and cache data age | Is the fallback serving sufficiently reliable data? |
| Bulkhead rejected calls | Is the application running out of capacity? |

Logs should include correlation ID, breaker ID, exception type, and fallback reason. Avoid logging sensitive content or full dependency response bodies.

## 9. Verification Scenarios

Use a mock server to trigger each scenario intentionally and verify the corresponding fallback:

1. Have the inventory service return 500. Confirm the `DEPENDENCY_ERROR` fallback runs and the Circuit Breaker records the failure per configuration.
2. Have the server respond slower than `timeoutDuration`. Confirm the `TIMEOUT` fallback runs, TimeLimiter emits a timeout event, and the caller receives the expected result type.
3. Trigger enough failed calls to transition the breaker to `OPEN`. Send more requests and verify `CallNotPermittedException` triggers the `CIRCUIT_OPEN` fallback without the mock server receiving new requests.
4. Put the breaker in `HALF_OPEN` and exhaust all probe permits. Confirm excess calls are also rejected and classified as `CallNotPermittedException`.
5. Saturate the Bulkhead to test `BulkheadFullException`; verify the overload fallback does not enqueue work into the same pool.
6. Have the inventory service return 404. Confirm the business error is preserved or mapped per contract rather than turning into unintended cached inventory data.
7. Make the fallback cache fail. Confirm the fallback error propagates to the caller with dedicated logs and metrics.
8. Restore the dependency, wait for probe calls to succeed, and verify the breaker returns to `CLOSED`; fallback count drops as live requests are served.

## 10. Common Pitfalls

- Sharing a single fallback for all exceptions and returning default data even when the cause is an input or programming error.
- Treating `CallNotPermittedException` as an error just returned by the dependency, even though the request was blocked before sending.
- Failing to distinguish TimeLimiter timeouts from HTTP client timeouts.
- Ignoring `CompletionException`/`ExecutionException` wrappers, preventing the fallback from recognizing the root cause.
- Having the fallback call the same dependency again, creating loops or continuing to load it while the circuit is open.
- Retrying `CallNotPermittedException` repeatedly while the Circuit Breaker does not yet permit requests.
- Using `Flux.empty()` as a fallback when the API needs to distinguish empty results from an unavailable dependency.
- Failing to track fallback counts separately from successful dependency calls.

## References

- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory.run`, `ReactiveCircuitBreakerFactory.run`, and the fallback `Function` accepting `Throwable`.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): fallback methods, closest exception match selection, annotations, and metrics.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): TimeLimiter, instance configuration, Bulkhead, and factory-based fallbacks.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): states, execution permits, sliding windows, and Circuit Breaker events.
