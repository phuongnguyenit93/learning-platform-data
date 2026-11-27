# Passing a Fallback Function Accepting Throwable

In Spring Cloud CircuitBreaker, a protected call typically has two parts: the primary operation to execute and a fallback function that runs when the primary operation cannot produce a result. In the synchronous API, the fallback function is passed as a `Function<Throwable, T>`. The `Throwable` parameter indicates why the primary call failed or was rejected by the Circuit Breaker; the return value `T` is the result the application passes back to the caller.

In the **SPRING_CLOUD_CIRCUIT_BREAKER** module, passing this function enables the application to respond appropriately when a dependent service is slow or unavailable. Instead of returning a single default value for every situation, the fallback can classify errors, log them, retrieve the most recent data from cache, or propagate business errors to the appropriate handler.

## 1. Contract of the Fallback Function

The synchronous Spring Cloud CircuitBreaker API has the general signature:

```java
<T> T run(
        Supplier<T> toRun,
        Function<Throwable, T> fallback
);
```

The two parameters play distinct roles:

| Parameter | Type | Role |
| --- | --- | --- |
| `toRun` | `Supplier<T>` | Provides the primary operation and produces a result of type `T` |
| `fallback` | `Function<Throwable, T>` | Receives the failure cause and produces an alternative result of the same type `T` |

`Supplier<T>` takes no input arguments. It simply describes the operation to execute when the Circuit Breaker allows the call through. `Function<Throwable, T>` takes one argument representing the failure cause and must return a value compatible with the return type of the primary operation.

For example, if the inventory lookup returns `InventoryResult`, the fallback function must also return `InventoryResult`:

```java
Function<Throwable, InventoryResult> fallback =
        failure -> InventoryResult.unavailable();

InventoryResult result = circuitBreaker.run(
        () -> inventoryClient.find("SKU-100"),
        fallback
);
```

The expression `failure -> ...` is a lambda implementing `Function`. The variable `failure` is the `Throwable` object passed by the API. The application can inspect its exception type, message, or root cause to decide how to respond.

The key point to remember is that a fallback accepts **a failure cause** and returns **a result of the same type as the primary call**. It is not a second `Supplier`, nor is it a zero-argument function.

## 2. Passing a Fallback with a Lambda

Suppose the Order service calls the Inventory service to read stock levels. When the Inventory service does not respond, the application can return an unavailable inventory status. We use `CircuitBreakerFactory` to obtain a Circuit Breaker and pass a lambda as the fallback:

```java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResult find(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> inventoryClient.find(sku),
                failure -> InventoryResult.unavailable(sku)
        );
    }
}
```

In this example:

1. `circuitBreakerFactory.create("inventory")` obtains the Circuit Breaker named `inventory`.
2. The lambda `() -> inventoryClient.find(sku)` describes the primary call to the Inventory service.
3. The lambda `failure -> InventoryResult.unavailable(sku)` is the fallback that receives the failure cause and produces a fallback result.
4. Both the primary call and the fallback return `InventoryResult`, so the `find` method maintains a consistent return type.

This snippet focuses on how the function is passed; `InventoryClient` and `InventoryResult` are illustrative business components. The `inventory` instance should be configured in `application.yml` according to the Circuit Breaker configuration the application uses.

The fallback in this example does not inspect the `failure` variable yet, but the lambda signature still accepts it. When you need to classify the cause, use this variable rather than ignoring it.

## 3. Classifying Throwable to Choose a Response

The `Throwable` type allows the fallback to receive many kinds of causes. For instance, a call can fail due to a timeout, connection error, server error, or because the Circuit Breaker is `OPEN`. These cases do not necessarily call for the same response.

With Resilience4j, when the Circuit Breaker is `OPEN` and blocks the call, the application typically receives `CallNotPermittedException`. The primary operation is not invoked against the dependent service. When the error originates from an HTTP client, the cause may be a client exception; when a `TimeLimiter` is present, the error may be timeout-related.

For example, a fallback can classify several scenarios:

```java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.web.client.ResourceAccessException;

private InventoryResult fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof CallNotPermittedException) {
        log.warn("Circuit Breaker is open; skipping inventory lookup call");
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    if (failure instanceof ResourceAccessException) {
        log.warn("Unable to connect to the Inventory service");
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    if (failure instanceof InventoryNotFoundException) {
        throw (InventoryNotFoundException) failure;
    }

    throw new IllegalStateException("Unable to retrieve inventory", failure);
}
```

The method above takes both `sku` and `Throwable` because it is a regular business method that the lambda invokes. You can pass it via:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        failure -> fallbackInventory(sku, failure)
);
```

Several points in this classification:

- **CallNotPermittedException**: the Circuit Breaker blocked the call because the circuit is `OPEN`. You can serve from cache or return a temporarily unavailable status.
- **ResourceAccessException**: an example of a resource access or connection error from Spring Web. You can return the most recent data if business rules allow.
- **InventoryNotFoundException**: an example of a business error. If "product not found" must be reported accurately, do not turn it into an "Inventory service temporarily unavailable" response.
- **Unrecognized cause**: preserve the original cause in a new exception so higher handling layers can still diagnose the issue.

Specific exception types depend on the libraries and clients your application uses. Classify based on your application's actual exception types; do not assume all HTTP errors share the same type.

## 4. Why Handle Throwable Selectively?

`Throwable` is the root class of both `Exception` and `Error`. Using `Throwable` in the API lets the fallback receive a broad cause type, but that does not mean the application should swallow everything it receives.

Business errors, connection errors, and timeout errors may require different responses. Conversely, serious JVM errors such as certain `Error` subtypes should generally not be turned into normal fallback results. If a fallback returns "out of stock" for every error, a critical failure can be masked and leave the system running in an invalid state.

When you need to rethrow errors, you can preserve runtime exceptions and `Error`s directly while wrapping checked exceptions in an appropriate exception:

```java
private static RuntimeException propagate(Throwable failure) {
    if (failure instanceof RuntimeException) {
        return (RuntimeException) failure;
    }
    if (failure instanceof Error) {
        throw (Error) failure;
    }
    return new IllegalStateException("Dependency call failed", failure);
}
```

Then the fallback can handle expected errors and propagate the rest:

```java
private InventoryResult fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof CallNotPermittedException
            || failure instanceof ResourceAccessException) {
        return inventoryCache.findRecent(sku)
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    throw propagate(failure);
}
```

In production code, choose the policy based on business needs and the libraries in use. The example above illustrates the principle: convert only anticipated errors into fallback results; preserve the cause of unexpected errors so error handling and observability do not lose information.

## 5. Using a Method Reference or a Helper Method

When a fallback has multiple branches, placing the logic in a dedicated method makes the main call easier to read. If the method takes a single `Throwable` parameter and returns the expected result type, you can pass a method reference:

```java
private InventoryResult fallback(Throwable failure) {
    if (failure instanceof CallNotPermittedException) {
        return InventoryResult.unavailable();
    }
    throw propagate(failure);
}

public InventoryResult find(String sku) {
    CircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            () -> inventoryClient.find(sku),
            this::fallback
    );
}
```

`this::fallback` is equivalent to the lambda `failure -> this.fallback(failure)`. Both match `Function<Throwable, InventoryResult>`.

If the fallback needs additional call-specific data such as `sku`, use a lambda to capture that variable:

```java
return circuitBreaker.run(
        () -> inventoryClient.find(sku),
        failure -> fallbackInventory(sku, failure)
);
```

You cannot pass `this::fallbackInventory` directly in this example if the method takes two parameters `String` and `Throwable`, because `Function<Throwable, T>` only passes one argument. The lambda bridges the contextual parameter `sku` with the `failure` argument supplied by the Circuit Breaker.

## 6. Fallback in Reactive Calls

In reactive applications, the return type is not a synchronous value `T` but typically a publisher such as `Mono<T>`. Spring Cloud CircuitBreaker's reactive API accepts a primary publisher and a fallback function of the form `Function<Throwable, Publisher<T>>` (typically using `Mono<T>` or `Flux<T>` depending on the call type).

Example with `Mono<InventoryResult>`:

```java
import reactor.core.publisher.Mono;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;

public Mono<InventoryResult> findReactive(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            reactiveCircuitBreakerFactory.create("inventory");

    Mono<InventoryResult> primary =
            webClient.get()
                    .uri("/items/{sku}", sku)
                    .retrieve()
                    .bodyToMono(InventoryResult.class);

    return circuitBreaker.run(
            primary,
            failure -> {
                if (failure instanceof CallNotPermittedException) {
                    return inventoryCache.findRecentReactive(sku)
                            .defaultIfEmpty(InventoryResult.unavailable(sku));
                }
                return Mono.just(InventoryResult.unavailable(sku));
            }
    );
}
```

Here, the fallback receives `Throwable` but must return a publisher compatible with the primary publisher's type. `Mono.just(...)` creates a `Mono` containing the fallback result. If you use `Flux<T>` for the primary call, the fallback must return a compatible publisher according to the API signature being used.

Do not call `block()` inside a reactive fallback just to obtain a synchronous value. Keep chaining operations onto the publisher pipeline to avoid blocking reactive threads. If the cache is also an asynchronous call, return the cache publisher directly as shown in the example.

## 7. Common Mistakes When Passing a Fallback Function

| Pattern or handling | Problem | Fix |
| --- | --- | --- |
| Passing `() -> fallback()` | This is a zero-argument lambda and does not match `Function<Throwable, T>` | Use `failure -> fallback(failure)` |
| Fallback returns a different type than the primary call | Does not match the API's type `T` | Return the same result type or a compatible subtype |
| Ignoring the `Throwable` parameter in all cases | Loses information needed to classify errors and diagnose issues | Use the cause to select an appropriate response |
| Returning default data for every exception | Can hide business errors or programming bugs | Handle only anticipated error types; propagate the rest |
| Calling the same dependent service inside the fallback | Can create loops or add load while the dependency is failing | Use cache, bounded results, or an unavailable response |
| Logging full sensitive data from exceptions | Can leak sensitive details into logs | Log error codes, dependency names, and sanitized details |
| Using a synchronous fallback lambda with the reactive API | Return type is no longer the expected publisher | Return `Mono<T>` or an appropriate publisher |

A fallback can also throw an exception of its own—for example, if the cache fails or fallback logic throws. In that case, the overall call can still fail and the fallback's exception will propagate up to the caller. Therefore, fallbacks should be concise, have minimal dependencies, and have appropriate error handling of their own.

## 8. Monitoring and Verifying Fallback Behavior

To know whether a fallback is effectively protecting the service or masking an outage, monitor at least:

- Number of primary call failures broken down by cause type.
- Number of fallback invocations, broken down by Circuit Breaker name and error type.
- Number of calls rejected due to an `OPEN` circuit, typically identified via `CallNotPermittedException`.
- Rate at which the fallback returns a successful result versus the rate at which the fallback itself fails.
- Latency of the primary call, the fallback, and the final response.

When testing, you can simulate three cases: when the primary call succeeds, the fallback is not invoked; when the primary call throws a supported exception, the fallback receives that exact exception and returns a fallback result; when the Circuit Breaker is `OPEN`, the call is blocked and the fallback handles the rejection cause. In addition, verify that an unanticipated error is propagated properly rather than turned into a default result.

Do not rely solely on counting successful HTTP responses at the outermost API. If the fallback always returns HTTP 200, dashboards may look healthy even while the Inventory service is down. Combine fallback metrics with Circuit Breaker state, failure rates, and the health of dependent services.

## 9. Key Takeaways

When using the common API of Spring Cloud CircuitBreaker, pass the primary call as a `Supplier<T>` and the fallback function as a `Function<Throwable, T>`. The `Throwable` parameter supplies the cause so the fallback can choose how to respond; the return value must match the primary call's result type. Use a lambda when you need to capture additional contextual data, use a method reference when the fallback method has the exact single-parameter signature, and convert only expected errors into fallback results.

For reactive calls, you still receive the cause via `Throwable`, but the fallback must return an appropriate publisher. In both models, preserving error information, separating infrastructure failures from business errors, and monitoring fallback frequency help the Circuit Breaker protect services without obscuring the system's true state.
