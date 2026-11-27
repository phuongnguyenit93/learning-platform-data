# fallbackMethod Signature and Exception-Based Selection

In Resilience4j, the **@CircuitBreaker** annotation can declare **fallbackMethod** to specify a fallback method when the protected call fails or is rejected by the Circuit Breaker. The fallback method must have a return type compatible with the original method and accept all input parameters of the original method, followed by an additional exception parameter at the end of the parameter list.

When multiple error types need to be handled, you can declare multiple fallback methods with the same name but different trailing exception types. Resilience4j selects the method whose exception type best matches the actual error. Mastering signature rules and exception selection helps applications distinguish timeouts, an OPEN Circuit Breaker, dependent service errors, and business errors, while avoiding fallbacks that hide the real root cause.

## 1. Signature Structure of fallbackMethod

Suppose the original method accepts a product ID parameter and returns a Product object:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
public Product getProduct(String id) {
    return catalogClient.getProduct(id);
}
~~~

The corresponding fallback method takes the same input parameters, followed by an exception parameter at the end:

~~~java
private Product getProductFallback(
        String id,
        Throwable error) {
    return Product.unavailable(id);
}
~~~

There are three main rules:

1. The fallback method name must match the value declared in **fallbackMethod**.
2. The fallback's parameter list must preserve the order and types of the original method's parameters.
3. The last parameter of the fallback is an exception type capable of receiving the raised error, typically **Throwable**, **Exception**, or a specific exception class.

The fallback's return type must be compatible with the original method's return type. If the original method returns Product, the fallback returns Product. If the original method returns Mono<Product>, the fallback also returns Mono<Product>. A fallback is not the place to change the API contract of the original method.

## 2. Original Method with Multiple Parameters

The fallback must receive all parameters of the original method before the exception parameter. For example, a reservation method accepts a SKU, warehouse code, and quantity:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "reserveFallback")
public Reservation reserve(
        String sku,
        String warehouseCode,
        int quantity) {
    return inventoryClient.reserve(sku, warehouseCode, quantity);
}

private Reservation reserveFallback(
        String sku,
        String warehouseCode,
        int quantity,
        Throwable error) {
    return Reservation.unavailable(sku, warehouseCode, quantity);
}
~~~

Parameter order matters. The fallback signature above corresponds exactly to the three parameters of the original method plus Throwable at the end. Do not put the exception first, omit the quantity parameter, or change `int` to `Integer` if the signature would no longer match the original method as required by the resolver.

If the original method has a request object parameter, the fallback receives that exact object:

~~~java
@CircuitBreaker(name = "payment", fallbackMethod = "authorizeFallback")
public PaymentResult authorize(PaymentRequest request, String traceId) {
    return paymentClient.authorize(request, traceId);
}

private PaymentResult authorizeFallback(
        PaymentRequest request,
        String traceId,
        Throwable error) {
    return PaymentResult.pending(request.orderId(), traceId);
}
~~~

By retaining the original parameters, the fallback knows which request is being processed, can query a cache, or construct an appropriate response. However, do not log all sensitive request details just to diagnose failures; select only necessary fields and use a trace ID to correlate logs.

## 3. Selecting a Fallback by Specific Exception Type

You can define multiple fallbacks with the same name, each taking a different exception class as its last parameter. For example, a Catalog service wants to handle an OPEN Circuit Breaker, timeouts, and unclassified errors separately:

~~~java
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogService(
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
    public Product getProduct(String id) {
        return catalogClient.getProduct(id);
    }

    private Product getProductFallback(
            String id,
            CallNotPermittedException error) {
        log.warn("Circuit Breaker catalog rejected the call, id={}", id);
        return productCache.findById(id)
            .orElse(Product.unavailable(id));
    }

    private Product getProductFallback(
            String id,
            TimeoutException error) {
        log.warn("Catalog timeout, id={}", id);
        return productCache.findById(id)
            .orElse(Product.unavailable(id));
    }

    private Product getProductFallback(
            String id,
            Throwable error) {
        log.error("Failed to fetch product from Catalog, id={}", id, error);
        return Product.unavailable(id);
    }
}
~~~

These methods share the same name and the same business parameter `id`. They differ only in the type of the last parameter. Resilience4j finds the fallback with the exception type most compatible with the actual error. If the error is **CallNotPermittedException**, the specialized method for that error type takes precedence over the method taking Throwable. If the error is TimeoutException, the timeout fallback is selected. The fallback taking Throwable serves as the general handler for remaining errors.

Placing specific fallbacks before the general fallback in source code helps readers recognize intent easily, even though method selection is based on exception type rather than declaration order. Avoid creating multiple fallbacks with the same degree of match that make selection ambiguous; each error category should have one clear handler.

## 4. How the Resolver Selects the Best-Matching Exception

You can think of the selection rule as finding the closest exception type in the Java inheritance hierarchy. Suppose the actual exception is a subclass of RuntimeException:

~~~java
private Product fallback(String id, RuntimeException error) {
    return Product.unavailable(id);
}

private Product fallback(String id, Exception error) {
    return Product.unavailable(id);
}

private Product fallback(String id, Throwable error) {
    return Product.unavailable(id);
}
~~~

If the actual error is a RuntimeException, the fallback accepting RuntimeException is a more specific match than the fallback accepting Exception or Throwable. If the actual error is a distinct subclass of RuntimeException and a dedicated fallback exists for that class, the specialized method takes precedence.

Illustration table:

| Actual Error Type | Available Fallbacks | Better-Matching Fallback |
|---|---|---|
| **CallNotPermittedException** | CallNotPermittedException, RuntimeException, Throwable | CallNotPermittedException |
| **TimeoutException** | Exception, Throwable | Exception |
| **InvalidProductException** (extends RuntimeException) | InvalidProductException, RuntimeException, Throwable | InvalidProductException |
| An error with no dedicated fallback | Throwable | Throwable |

You do not need to write an `if`/`else` chain checking every exception if you only need type-based dispatch. Overloading fallbacks lets you declare policy close to the error type and keeps handling readable. If you need to classify by exception attributes such as HTTP status codes or business codes, you can inspect them inside the matching fallback body.

If an exception is wrapped inside another layer, the resolver operates on the exception passed to the fallback. Do not assume it always selects by the deepest cause automatically. When needed, inspect **getCause()** and classify the root cause intentionally while preserving the original exception in logs.

## 5. Using Throwable as a General Fallback

A fallback taking Throwable can catch many error types and is useful as a last-resort fallback branch:

~~~java
private Product getProductFallback(String id, Throwable error) {
    log.error("Error fetching product, id={}", id, error);
    return Product.unavailable(id);
}
~~~

However, a general fallback can mask business or programming errors if it always returns default data. For example, if the error is InvalidProductIdException caused by invalid client input, returning Product.unavailable can mislead the caller into thinking Catalog is temporarily unavailable.

For errors that should be returned as business errors, declare a specialized fallback to rethrow or transform them intentionally:

~~~java
private Product getProductFallback(
        String id,
        InvalidProductIdException error) {
    throw error;
}

private Product getProductFallback(
        String id,
        CallNotPermittedException error) {
    return productCache.findById(id)
        .orElse(Product.unavailable(id));
}

private Product getProductFallback(String id, Throwable error) {
    log.error("Catalog encountered an unclassified error, id={}", id, error);
    return Product.unavailable(id);
}
~~~

In this example, input errors are not turned into service errors. Calls rejected by the Circuit Breaker can use the cache; remaining errors go to the general fallback. Clearly define which exceptions count as technical failures, which are business outcomes, and which must propagate to the caller.

## 6. Fallback Signatures with Reactive Return Types

In WebFlux applications, original methods typically return Mono or Flux. The fallback must return the same Publisher type and still receive the original parameters before the exception.

Example with Mono:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveCatalogService {

    private final ReactiveCatalogClient catalogClient;
    private final ProductCache productCache;

    ReactiveCatalogService(
            ReactiveCatalogClient catalogClient,
            ProductCache productCache) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
    public Mono<Product> getProduct(String id) {
        return catalogClient.getProduct(id);
    }

    private Mono<Product> getProductFallback(
            String id,
            CallNotPermittedException error) {
        return productCache.findByIdReactive(id)
            .switchIfEmpty(Mono.just(Product.unavailable(id)));
    }

    private Mono<Product> getProductFallback(
            String id,
            Throwable error) {
        return Mono.just(Product.unavailable(id));
    }
}
~~~

With Flux, the fallback returns Flux:

~~~java
@CircuitBreaker(name = "catalog-search", fallbackMethod = "searchFallback")
public Flux<Product> search(String keyword, int limit) {
    return catalogClient.search(keyword, limit);
}

private Flux<Product> searchFallback(
        String keyword,
        int limit,
        Throwable error) {
    return productCache.search(keyword, limit);
}
~~~

Do not return Product directly from a fallback for a method returning Mono<Product>; nor return Mono<Product> from a fallback for a method returning Flux<Product>. Keep the Publisher type consistent so callers can continue composing with reactive operators.

A reactive fallback should build a fallback Publisher and must not call **block()**. If the fallback queries a cache via a reactive client, keep that operation inside Mono/Flux. If the cache API is blocking-only, offload the operation to an appropriate scheduler or provide a non-blocking API.

## 7. Fallbacks with Other Asynchronous Return Types

Resilience4j also supports asynchronous return types handled by the corresponding integration, such as CompletionStage. The fallback must return a type compatible with the original method:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "getProductAsyncFallback")
public CompletionStage<Product> getProductAsync(String id) {
    return catalogClient.getProductAsync(id);
}

private CompletionStage<Product> getProductAsyncFallback(
        String id,
        Throwable error) {
    return CompletableFuture.completedFuture(Product.unavailable(id));
}
~~~

The example illustrates the return-type contract: the original method returns CompletionStage<Product>, and the fallback also returns CompletionStage<Product>. When combining TimeLimiter or async annotations with a Circuit Breaker, verify aspect ordering and support in the Resilience4j version in use.

Do not use a synchronous fallback returning Product for a method whose contract is CompletionStage<Product> if the integration requires a matching return type. Keeping return types consistent clarifies completion timing and how callers receive results.

## 8. fallbackMethod and Common Errors

Several common mistakes prevent Resilience4j from finding a fallback or cause an unexpected branch to be chosen:

| Error | Cause | Fix |
|---|---|---|
| Fallback not found | Typo in the annotation | Check the exact `fallbackMethod` value |
| Signature mismatch | Missing original parameters, wrong order, or wrong types | Copy all original method parameters and add the exception at the end |
| Wrong return type | Fallback returns an incompatible type | Use the same return type as the original method |
| Unintended general branch chosen | No fallback for the specific exception, or actual exception is wrapped | Inspect the exception type passed and its cause |
| Business error masked | `Throwable` fallback always returns default data | Add a specialized fallback to rethrow or translate business errors |
| Fallback itself fails | Cache or fallback logic throws an exception | Keep fallback simple, use an independent source, and monitor fallback errors |
| Annotation not applied | Call does not pass through a Spring AOP proxy | Call the method via a bean proxy instead of self-invocation in the same bean |

If no matching fallback exists, the original error usually continues propagating outward. If a fallback is found but throws an error itself, the caller receives the error raised by the fallback. Therefore, monitor both primary operation errors and fallback failures.

## 9. Annotations Operate Through a Spring AOP Proxy

The **@CircuitBreaker** annotation is processed via Resilience4j's aspect in Spring. Spring AOP must intercept calls to a container-managed bean. If one method in the same class directly calls another annotated method, that internal call normally does not go through the proxy and the advice may not be triggered.

Example that should not rely on self-invocation:

~~~java
@Service
class ProductService {

    public Product load(String id) {
        // Internal call to an annotated method, does not go through the Spring proxy.
        return loadFromCatalog(id);
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "loadFallback")
    public Product loadFromCatalog(String id) {
        return catalogClient.getProduct(id);
    }

    private Product loadFallback(String id, Throwable error) {
        return Product.unavailable(id);
    }
}
~~~

A cleaner organization is to place the protected method in a separate bean and inject that bean into the calling service:

~~~java
@Service
class CatalogGateway {

    @CircuitBreaker(name = "catalog", fallbackMethod = "getFallback")
    public Product get(String id) {
        return catalogClient.getProduct(id);
    }

    private Product getFallback(String id, Throwable error) {
        return Product.unavailable(id);
    }
}

@Service
class ProductService {

    private final CatalogGateway catalogGateway;

    ProductService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    Product load(String id) {
        return catalogGateway.get(id);
    }
}
~~~

Here, ProductService calls CatalogGateway through a Spring-managed bean, so the call can pass through the proxy and be handled by the aspect. When designing with annotations, verify that AOP dependencies and the Resilience4j Spring integration are properly configured, the method is actually invoked through the proxy, and the fallback is visible to the resolver.

## 10. Combining Fallbacks with CallNotPermittedException and Timeouts

A fallback can branch by cause to select appropriate behavior. Example:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "getStockFallback")
public Stock getStock(String sku) {
    return inventoryClient.getStock(sku);
}

private Stock getStockFallback(
        String sku,
        CallNotPermittedException error) {
    log.warn("Inventory is OPEN, sku={}", sku);
    return inventoryCache.findBySku(sku)
        .orElse(Stock.unavailable(sku));
}

private Stock getStockFallback(
        String sku,
        TimeoutException error) {
    log.warn("Inventory timeout, sku={}", sku);
    return inventoryCache.findBySku(sku)
        .orElse(Stock.unavailable(sku));
}

private Stock getStockFallback(String sku, Throwable error) {
    log.error("Unclassified error from Inventory, sku={}", sku, error);
    return Stock.unavailable(sku);
}
~~~

**CallNotPermittedException** indicates that the Circuit Breaker rejected the call before the supplier executed. A timeout indicates that the operation was permitted but did not complete within the deadline set by the timeout mechanism. Both cases may use the same cache, but should be recorded separately so dashboards and logs reflect the exact cause.

If the `@CircuitBreaker` annotation is used standalone, a timeout may be thrown by the HTTP client or the protected operation. When combining TimeLimiter, Retry, or Bulkhead, the actual exception delivered to the fallback also depends on aspect ordering and integration behavior. Verify the exception received at runtime instead of assuming every timeout always produces one fixed exception class.

Do not let a fallback call back into the same protected method through the same proxy without bounds, as that can create a fallback loop or keep hitting an OPEN Circuit Breaker. A fallback should use a cache, an independent backup source, or return a meaningful error.

## 11. Designing Maintainable Fallbacks

A good fallback clearly expresses how the application reacts to failure while preserving data semantics.

- **Preserve the return type:** if Product, return Product; if Mono<Product>, return Mono<Product>.
- **Preserve original parameters:** the fallback needs to know which request is being processed.
- **Choose specific exceptions:** separate rejected calls, timeouts, and business errors when behavior must differ.
- **Include a general branch when needed:** a Throwable fallback can act as a last resort, but should not mask all errors with fake values.
- **Do not depend on the failing source:** use a cache or an independent backup service.
- **Log appropriately:** preserve the exception and trace ID while avoiding logging sensitive data.
- **Handle fallback failures:** the cache may also fail or lack data; clearly define the outcome in that case.

For business errors, you can rethrow the original exception or translate it into a dedicated business result type. For infrastructure failures, you can use cached data if staleness is acceptable to the business. Do not return default data that misleads the caller into thinking the dependency confirmed a valid result.

## 12. Practice Scenario

An order service calls Catalog to fetch product information and Inventory to check stock. Each method uses its own Circuit Breaker and has exception-based fallbacks.

- Catalog uses a cache fallback when the Circuit Breaker is OPEN.
- Catalog uses a dedicated fallback on timeout.
- An invalid SKU is propagated as a business error.
- Inventory uses a fallback marking unavailable status when the service does not respond.
- General fallbacks handle only unclassified errors.

Example for Catalog:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "findFallback")
public Product find(String id) {
    return catalogClient.getProduct(id);
}

private Product findFallback(
        String id,
        CallNotPermittedException error) {
    return productCache.findById(id)
        .orElse(Product.unavailable(id));
}

private Product findFallback(
        String id,
        InvalidProductIdException error) {
    throw error;
}

private Product findFallback(String id, Throwable error) {
    log.error("Catalog request failed, id={}", id, error);
    return Product.unavailable(id);
}
~~~

When testing, create separate scenarios:

1. Circuit Breaker is OPEN and the call is rejected; confirm the fallback receives CallNotPermittedException.
2. Client throws TimeoutException; confirm the timeout fallback is selected if that exception is passed directly.
3. Client throws InvalidProductIdException; confirm the business error is propagated.
4. Client throws an exception with no specialized fallback; confirm the Throwable branch is used.
5. Fallback cache also fails; confirm the caller receives the error from the fallback and logs preserve the cause.
6. Call the annotated method from another bean; compare with self-invocation to verify the AOP proxy.

Questions to answer after practicing:

- In what order does the fallback receive the original parameters?
- Where must the exception appear in the signature?
- Which fallback does Resilience4j choose when multiple overloads exist?
- When should Throwable be used and when is a specific exception needed?
- Why must a reactive fallback return Mono or Flux?
- How does self-invocation affect annotations?

## Conclusion

With Resilience4j **fallbackMethod**, the fallback preserves the return type and all parameters of the original method, then appends the exception at the end. You can overload the same fallback name to handle CallNotPermittedException, timeouts, or business errors separately; the resolver chooses the exception type best matching the actual error. Keep a general branch when needed, avoid hiding business errors, maintain Publisher types for reactive flows, and ensure annotated calls pass through a Spring AOP proxy so the Circuit Breaker and fallback execute properly.
