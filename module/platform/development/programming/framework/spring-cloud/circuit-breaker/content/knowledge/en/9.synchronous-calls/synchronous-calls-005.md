# Handling Exception Wrappers and Identifying the Root Cause

When a synchronous call to a dependent service fails, the exception received by the circuit breaker is sometimes not the original exception. An HTTP library, proxy, reflection, or code waiting on a `Future` can wrap the underlying error inside another exception. If Resilience4j is configured only to record `SocketTimeoutException`, yet the actual call throws `ResourceAccessException` or `ExecutionException`, the classification rule may fail to match.

For the circuit breaker to accurately reflect dependency health, you need to understand the exception chain, identify the actual exception type escaping the protected work, and unwrap only known technical wrappers. Never discard the full exception context or blindly treat the deepest cause as a dependency failure.

## Why Are Exceptions Wrapped?

An exception can pass through multiple layers before reaching the circuit breaker:

1. The HTTP client encounters a network error or timeout.
2. An adapter translates the technical error into a service-domain exception.
3. A proxy or reflection wraps the exception in a wrapper.
4. The `Supplier` passed to the circuit breaker throws the final outer exception.

For example, the inventory service fails to respond in time. The HTTP client throws `SocketTimeoutException`, the adapter translates it into `InventoryUnavailableException`, and an asynchronous execution wrapper awaited with `Future.get()` places that error inside an `ExecutionException`. At that point, the circuit breaker sees `ExecutionException` at the call boundary rather than `SocketTimeoutException` directly.

~~~mermaid
flowchart TD
    A[Inventory service call] --> B[HTTP client]
    B -->|SocketTimeoutException| C[Adapter]
    C -->|InventoryUnavailableException| D[Future or proxy]
    D -->|ExecutionException / wrapper| E[Protected supplier]
    E --> F[Circuit breaker classifies Throwable]
    F --> G[Fallback or propagate error]
~~~

The circuit breaker classifies the exception thrown out of the work it protects. Therefore, it is critical to inspect the exception at that exact boundary rather than inferring solely from the first error printed in logs.

## Common Wrappers in Synchronous Calls

Several Java classes are commonly used to wrap errors:

| Wrapper | Common Context | How to Extract Inner Cause |
|---|---|---|
| CompletionException | Retrieving result from `CompletableFuture` via `join()`. | `getCause()` |
| ExecutionException | Retrieving result from `Future` via `get()`. | `getCause()` |
| InvocationTargetException | Invoking a method via reflection. | `getTargetException()` or `getCause()` |
| UndeclaredThrowableException | A call through a JDK dynamic proxy encounters a checked exception not declared in the signature. | `getUndeclaredThrowable()` or `getCause()` |

These wrappers typically carry no domain meaning of their own; they indicate which execution mechanism the error traversed. You can unwrap them to classify the underlying error when needed.

However, not every exception with a cause is merely a wrapper. Spring's `ResourceAccessException` expresses a resource access failure and wraps an `IOException`; `InventoryUnavailableException` may be a domain exception meaningful to the application. Do not unwrap every layer indiscriminately, as doing so can lose valuable information or misclassify a business error that happens to have a deeper cause.

## Controlled Root-Cause Extraction

A safe approach is to unwrap only known technical wrappers, bound the traversal depth, and detect cycles in the cause chain. For example:

~~~java
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.UndeclaredThrowableException;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutionException;

public final class ExceptionUtils {

    private static final int MAX_UNWRAP_DEPTH = 16;

    private ExceptionUtils() {
    }

    public static Throwable unwrapKnownWrappers(Throwable error) {
        Throwable current = error;

        Set<Throwable> visited = Collections.newSetFromMap(
                new IdentityHashMap<Throwable, Boolean>()
        );

        for (int depth = 0;
             current != null && depth < MAX_UNWRAP_DEPTH && visited.add(current);
             depth++) {

            Throwable next = null;

            if (current instanceof CompletionException
                    || current instanceof ExecutionException) {
                next = current.getCause();
            } else if (current instanceof InvocationTargetException) {
                next = ((InvocationTargetException) current).getTargetException();
            } else if (current instanceof UndeclaredThrowableException) {
                next = ((UndeclaredThrowableException) current)
                        .getUndeclaredThrowable();
            }

            if (next == null || next == current) {
                break;
            }

            current = next;
        }

        return current;
    }
}
~~~

This method unwraps only the four known wrapper types. It stops when there is no cause, when the cause points back to the current object, when an already-visited object is encountered, or when the depth limit is reached. Using an identity set detects cycles by `Throwable` object identity, independent of how exception classes implement `equals()`.

The method is named `unwrapKnownWrappers` because it does not try to find a single "root cause" by walking all the way through every cause. If it encounters a domain exception like `InventoryUnavailableException` or a meaningful wrapper like `ResourceAccessException`, it preserves that exception as is. The caller can decide how to classify that exception type or inspect its cause in a dedicated rule.

## Using Predicates to Classify Exceptions in Resilience4j

When classification must look inside wrappers, you can use `CircuitBreakerConfig` predicates. A predicate lets you inspect the actual `Throwable` received by the circuit breaker and unwrap known wrappers before deciding.

~~~java
import java.io.IOException;
import java.net.ConnectException;
import java.net.SocketTimeoutException;
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .recordException(error -> {
            Throwable cause = ExceptionUtils.unwrapKnownWrappers(error);

            return cause instanceof SocketTimeoutException
                    || cause instanceof ConnectException
                    || cause instanceof TimeoutException
                    || cause instanceof IOException
                    || cause instanceof InventoryUnavailableException;
        })
        .ignoreException(error -> {
            Throwable cause = ExceptionUtils.unwrapKnownWrappers(error);

            return cause instanceof InvalidSkuException
                    || cause instanceof ProductNotFoundException;
        })
        .slidingWindowSize(20)
        .minimumNumberOfCalls(10)
        .failureRateThreshold(50)
        .build();
~~~

In this example, connection errors, timeouts, and `InventoryUnavailableException` are counted as failures. `InvalidSkuException` and `ProductNotFoundException` are ignored because they represent business outcomes or invalid inputs rather than dependency health.

The ignore predicate takes precedence when an exception matches both the ignore condition and the record condition. An ignored exception increments neither the success nor the failure count. If the record predicate returns `false` and the exception is not ignored, Resilience4j treats the call as a success in its statistics.

When using predicates, align the rules with `recordExceptions` and `ignoreExceptions` if the project declares both. Avoid creating overlapping policies that make it hard for readers to tell which exceptions are actually recorded. Each instance should have one clear classification rule tested against real `Throwable` types.

## Translating Technical Errors into Domain Exceptions at the Client Boundary

In many applications, a more maintainable approach is converting underlying library errors into meaningful domain exceptions at the adapter boundary. That way, the circuit breaker can classify a small set of stable exception types without coupling to a specific HTTP library.

Example with Spring's synchronous client:

~~~java
import org.springframework.web.client.ResourceAccessException;
import org.springframework.web.client.RestClient;

public class InventoryRemoteClient {

    private final RestClient restClient;

    public InventoryRemoteClient(RestClient restClient) {
        this.restClient = restClient;
    }

    public Inventory find(String sku) {
        try {
            return restClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(Inventory.class);
        } catch (ResourceAccessException ex) {
            throw new InventoryUnavailableException(
                    "Cannot access inventory service", ex
            );
        }
    }
}
~~~

`InventoryUnavailableException` is an illustrative application domain exception. The adapter retains `ResourceAccessException` as the cause for logging and diagnostics, while the caller receives a stable error type indicating the inventory dependency is unavailable.

This provides a major benefit: the circuit breaker does not need to know implementation details of the HTTP client. When switching HTTP libraries or changing wrapper structures, the adapter can preserve the service domain's exception contract.

Do not translate every `ResourceAccessException` into the exact same error if their underlying causes carry different operational meanings. For example, URL misconfiguration or certificate errors may require dedicated operational alerts. Preserve the original cause and, when needed, classify into specific domain exceptions such as `InventoryTimeoutException` or `InventoryConnectionException`.

## Handling Wrappers When Awaiting a Future in Synchronous Code

A synchronous method might call `Future.get()` to wait for a result. When the inner task fails, `get()` throws `ExecutionException`, and the true cause resides in `getCause()`.

~~~java
public Inventory findInventory(String sku) {
    try {
        return inventoryExecutor.submit(
                () -> inventoryClient.find(sku)
        ).get();
    } catch (ExecutionException ex) {
        Throwable cause = ExceptionUtils.unwrapKnownWrappers(ex);
        throw new InventoryUnavailableException(
                "Inventory lookup failed", cause
        );
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new InventoryRequestInterruptedException(
                "Inventory lookup was interrupted", ex
        );
    }
}
~~~

This snippet illustrates converting task errors into domain exceptions while preserving interrupt status. `InterruptedException` signals thread control: the current thread was asked to stop waiting. Do not treat it as a dependent service timeout or swallow it and continue normally.

With `CompletableFuture.join()`, task failures are typically thrown as `CompletionException`. You can unwrap this wrapper to inspect the inner error, while keeping the original exception in the cause chain for diagnostics.

If the application does not need to wait synchronously, consider keeping the processing flow asynchronous instead of calling `get()` or `join()`. Blocking threads reduces serving capacity and adds pressure when a dependent service slows down.

## Combining Root Cause Analysis with Fallbacks

Spring Cloud CircuitBreaker provides a fallback function that receives a `Throwable` when the call fails or the circuit breaker rejects it. The fallback can unwrap known wrappers to pick an appropriate response, while still logging the outermost exception to retain context.

~~~java
public Inventory findInventory(String sku) {
    return circuitBreakerFactory.create("inventory-read").run(
            () -> inventoryClient.find(sku),
            error -> {
                Throwable cause =
                        ExceptionUtils.unwrapKnownWrappers(error);

                if (cause instanceof ProductNotFoundException) {
                    return Inventory.notFound(sku);
                }

                if (cause instanceof CallNotPermittedException) {
                    return Inventory.unavailable(sku);
                }

                log.warn(
                        "Inventory lookup failed; cause type: {}",
                        cause == null ? "unknown" : cause.getClass().getName(),
                        error
                );

                return Inventory.unavailable(sku);
            }
    );
}
~~~

`ProductNotFoundException` can be ignored in circuit breaker statistics yet still converted into a not-found result in the fallback. `CallNotPermittedException` indicates the circuit breaker rejected the call because the circuit is `OPEN`; it is an outcome of local protection rather than a new failed remote call.

The fallback should return a result appropriate to the business context. For informational screens, returning the latest cached data marked as stale may work. For stock confirmation or payment operations, never assume success when no response arrived from the dependency. Distinguish nonexistent data, temporarily unavailable data, and undetermined outcomes.

## Avoiding Context Loss When Finding the Root Cause

Certain handling patterns can make diagnostics harder:

| Approach | Risk | Better Approach |
|---|---|---|
| Unwrapping every cause until no cause remains | Can skip past meaningful domain exceptions. | Unwrap only known technical wrappers. |
| Logging only the root cause | Loses wrapper context showing which layer translated the error. | Log both the outermost exception and the classified cause type. |
| Configuring `recordExceptions` for a single root error type | Wrappers prevent the predicate from matching. | Normalize at the adapter or use a predicate with controlled wrapper unwrapping. |
| Catching exceptions and returning a default value inside the supplier | Circuit breaker sees a normal completion and records no failure. | Let countable exceptions escape the supplier and handle them in the fallback. |
| Ignoring all `RuntimeException`s | Programming bugs or dependency errors may be hidden. | Ignore only explicitly identified business exception types. |
| Swallowing `InterruptedException` | Loses the thread interruption signal. | Restore the interrupt flag and propagate according to application contract. |

Log fields such as circuit breaker ID, outermost exception type, classified cause type, and request correlation ID. Correlation IDs are for per-request logs; do not place them in circuit breaker names or metric tags because doing so creates high cardinality.

## Testing Unwrapping and Classification

Tests should verify both the classification result and the exception propagated to the caller. You can simulate synchronous calls that throw exception types directly or wrapped:

| Case | What to Verify |
|---|---|
| Supplier throws `SocketTimeoutException` directly | Predicate recognizes timeout and records a failure. |
| Supplier throws `ExecutionException` wrapping `IOException` | Unwrap helper opens the known wrapper and classifies the connection error. |
| Supplier throws `CompletionException` wrapping `SocketTimeoutException` | Inner cause is identified. |
| Supplier throws `InventoryUnavailableException` with cause `IOException` | Domain exception is preserved and recorded per policy. |
| Supplier throws `ProductNotFoundException` | Exception is ignored in statistics yet still passed to the fallback. |
| Supplier catches timeout and returns `Inventory.unavailable()` | Circuit breaker sees normal completion; test verifies this is not recorded as a failure. |
| Supplier triggers `CallNotPermittedException` due to `OPEN` circuit | Fallback handles the rejection without counting it as a new dependency call failure. |
| Thread is interrupted while awaiting `Future.get()` | Interrupt flag is restored and not swallowed. |

In circuit breaker tests, use a small sliding window and appropriate minimum call count to observe the `CLOSED` to `OPEN` transition. Also verify failure counts, ignored counts, or the corresponding metrics for your Resilience4j version. Do not check only the final fallback return value, since the same fallback value might be returned for multiple distinct causes.

## Workflow for Handling Exception Wrappers

1. Record the outermost `Throwable` type at the protected supplier boundary.
2. Inspect the cause chain and identify technical wrappers that can be safely unwrapped.
3. Preserve domain exceptions or meaningful wrappers such as `ResourceAccessException` when they provide useful context.
4. Normalize library errors into domain exceptions at the adapter when a stable contract is needed.
5. Configure record/ignore predicates around the actual error types reaching the circuit breaker.
6. Use the fallback to map errors to business responses while logging sufficient context.
7. Test direct errors, wrapped errors, caught errors, business errors, and interruptions.

With Spring Cloud CircuitBreaker and Resilience4j, accurately identifying exception wrappers and root causes ensures the circuit breaker records genuine dependent service failures. Unwrap technical wrappers intentionally, retain domain context, and configure predicates at the right call boundary. That way, the circuit breaker reacts to timeouts or connection failures without confusing them with business outcomes or thread-control signals.
