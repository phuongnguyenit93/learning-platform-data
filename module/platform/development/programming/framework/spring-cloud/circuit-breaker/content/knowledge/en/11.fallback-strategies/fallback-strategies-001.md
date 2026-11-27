# What Is Fallback and Appropriate Scenarios

## Fallback in Systems Using a Circuit Breaker

Fallback is how an application produces an alternative result when a call to a dependent service cannot complete as expected. In Spring Cloud Circuit Breaker, a call can fail due to connection errors, timeouts, error responses from the server, or because the Circuit Breaker is `OPEN` and rejecting new calls. Instead of letting all such errors break the entire business flow, the application can return backup data or a pre-designed degraded state.

Fallback does not bring the dependent service back to working order. It only decides how the application responds while the primary result is unavailable. Therefore, a fallback must preserve business semantics: if the data is only an estimate or is stale, the caller must be able to recognize that; if an operation has not been executed, the application must not report success as if the data had been written.

In Spring Cloud Circuit Breaker, the `run` API lets you pass a supplier that performs the primary call and a fallback function that receives the cause of the error:

```java
return circuitBreakerFactory.create("catalog").run(
    () -> catalogClient.find(productId),
    error -> fallbackCatalog(productId, error)
);
```

The supplier is the primary processing path. The fallback is invoked when the supplier terminates with an error that the integration forwards to the fallback handler, including when the Circuit Breaker rejects the call while open. The exact behavior and the error types passed in should be verified against the provider and version of Spring Cloud Circuit Breaker in use.

## When Is Fallback Appropriate?

Fallback is useful when the business flow can continue with a safe and meaningful alternative result. Some common scenarios include:

| Scenario | Appropriate Fallback | Condition to Maintain |
| --- | --- | --- |
| Product page fails to fetch live inventory data | Display an undetermined inventory status or cached data within the allowed age limit. | Do not turn stale data into a guarantee of current stock. |
| Product recommendation service is temporarily unavailable | Return a pre-prepared list of popular recommendations or omit the recommendation section. | Recommendations are optional and do not affect pricing or purchase eligibility. |
| Auxiliary profile service fails | Use partially cached profile data or hide secondary information. | Do not display another user's data or expired data. |
| Non-mandatory feature service is slow | Temporarily disable the secondary feature and continue the main flow. | Inform the user if the experience is significantly limited. |
| Non-essential event logging service encounters an error | Place the event into a durable queue to resend later. | Only acknowledge receipt if the event is actually persisted durably and has deduplication in place. |

A useful litmus test is to ask: "If the primary result is unavailable, is there an alternative result that is still accurate and will not cause the user to make a wrong decision?" If the answer is yes, a fallback may be appropriate. If every alternative result would be misleading or corrupt data, you should return a clear error for the caller to handle.

## Common Fallback Strategies

### Cached Data or Latest Known Data

Caching suits data that changes infrequently or can tolerate update lag. When the primary service does not respond, the application reads the latest copy and attaches the update timestamp. You should set a maximum age limit (*maximum staleness*). If the cache is too old, the fallback must switch to an undetermined state or return an error rather than continuing to use untrustworthy data.

For example, a product detail page can display descriptions and images from cache, but should not use stale inventory to claim a product is definitely in stock. Transaction-critical data such as final price, balance, or access permissions usually require an authoritative source and stricter policies.

### Meaningful Default Values

A default value is only appropriate when it represents a valid business state. For example, if the recommendation service is unavailable, returning an empty list may be acceptable because recommendations are optional. However, returning an account balance of 0 when the balance service fails is dangerous: users may interpret that as their real balance.

You should use a result type that expresses the alternative state, such as `AVAILABLE`, `STALE`, `UNKNOWN`, or `DEGRADED`, rather than overusing `null`, empty strings, or 0. An explicit result type helps the presentation layer and business layer decide how to display it appropriately.

### Graceful Degradation

An application can skip a non-essential feature to keep the core functionality running. For example, the checkout page still displays the shopping cart and payment methods when the behavioral analytics service is unavailable. An optional analytics service should not break the main transaction.

Degradation needs clear boundaries: define which features can be turned off, which data is no longer provided, and which operations must still be rejected. Never bypass security checks, access permissions, quotas, or mandatory rules just to create the appearance that the system is still working.

### Switching to an Alternative Data Source

A backup source can serve the same information, such as reading from a read-only replica or calling a secondary provider. This strategy only helps if the alternative source is sufficiently independent. If both sources share the same database, DNS, gateway, or fault domain, the fallback may fail at the same time as the primary path.

Limit the timeout and retry count for the backup source. If the fallback calls back into the very service that is failing or traverses a long dependency chain, it can amplify load and create an error loop. The backup source also needs rules to determine freshness, consistency, and which data source takes precedence when both produce results.

### Queuing Requests for Deferred Processing

For some write operations that do not need immediate completion, the application can store the request in a durable queue and process it later. For instance, sending notifications or syncing an event can be deferred. When using this approach, the response should clearly state that the request has been accepted for later processing, not claim that the final operation has already completed.

The queue needs durable persistence acknowledgments, an identifier, idempotency/deduplication protection, a bounded retry policy, and a place to track failed messages (dead-letter handling). If writing to the queue fails, the fallback fails too, and the application must return an appropriate error.

## Example: Cache Fallback for a Catalog Service

Suppose a product page needs description details from the catalog service. The application caches the latest description and tolerates data up to 15 minutes old. When the primary service fails, the application uses the cache if the entry is within that limit; otherwise, it returns an undetermined state.

```java
@Service
public class ProductViewService {
    private final CatalogClient catalogClient;
    private final ProductCache productCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ProductViewService(
            CatalogClient catalogClient,
            ProductCache productCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductView find(String productId) {
        return circuitBreakerFactory.create("catalog").run(
            () -> {
                ProductDetails details = catalogClient.find(productId);
                productCache.put(productId, details, Instant.now());
                return ProductView.current(details);
            },
            error -> productCache.find(productId)
                .filter(entry -> entry.cachedAt().isAfter(
                    Instant.now().minus(Duration.ofMinutes(15))))
                .map(entry -> ProductView.stale(entry.details(), entry.cachedAt()))
                .orElseGet(() -> ProductView.unavailable(productId))
        );
    }
}
```

`ProductCache`, `ProductDetails`, and `ProductView` are application-defined types. `ProductView.stale` should inform the presentation layer that the data comes from the cache along with the update timestamp; `ProductView.unavailable` indicates that information is not yet available. Since the example focuses on fallback selection, the cache must be designed to be thread-safe with its own capacity limits and expiration policies.

In a production system, consider writing to the cache only after confirming a valid response, avoiding storing error results or incomplete data. Sensitive fields should not be cached without proper protection and data partitioning policies.

## Fallback with Resilience4j Annotations

If the application uses Resilience4j annotations, you can declare the fallback method name on `@CircuitBreaker`:

```java
@Service
public class RecommendationService {

    @CircuitBreaker(name = "recommendations", fallbackMethod = "fallback")
    public List<Product> recommend(String customerId) {
        return recommendationClient.fetch(customerId);
    }

    private List<Product> fallback(String customerId, Throwable cause) {
        log.warn("Recommendations unavailable for customerId={}", customerId, cause);
        return popularProducts.forDisplay();
    }
}
```

The fallback method must have a return type compatible with the original method, accept the same business parameters, and may accept an additional exception parameter at the end. You can use a specific exception type instead of `Throwable` if you want to handle distinct error groups separately. When there are multiple overloaded fallback methods, ensure the signatures are unambiguous and compatible with the Resilience4j version.

Annotations operate via Spring AOP. Calls must go through the Spring proxy; internal calls like `this.recommend(...)` within the same bean can bypass the interceptor. If the fallback is not invoked, check how the bean is created, whether the call goes through the proxy, and the fallback method signature.

## Fallback for Reactive Calls

With Reactor, the fallback must return a publisher rather than blocking the thread to obtain a value. For example:

```java
public Mono<ProductView> find(String productId) {
    Mono<ProductDetails> primary = catalogClient.findReactive(productId);

    return reactiveCircuitBreakerFactory.create("catalog")
        .run(
            primary.map(ProductView::current),
            error -> productCache.findReactive(productId)
                .map(entry -> ProductView.stale(entry.details(), entry.cachedAt()))
                .defaultIfEmpty(ProductView.unavailable(productId))
        );
}
```

`reactiveCircuitBreakerFactory` is a `ReactiveCircuitBreakerFactory` injected by Spring; the `findReactive` methods on the client and cache are hypothetical APIs returning `Mono`. The fallback also returns `Mono<ProductView>`, so the entire pipeline remains non-blocking. Avoid calling `block()` inside a fallback or making a synchronous call that could block the event loop.

## When Should You Avoid Using Fallback?

Fallback is inappropriate if the alternative result could cause the user to make a wrong decision or violate mandatory rules. Some examples:

- Do not return a default balance of 0 when the account cannot be queried.
- Do not bypass authentication or authorization when the permission check service is unavailable.
- Do not confirm that a payment, order, or data update succeeded if the target service has not confirmed it.
- Do not return expired cached data for information requiring strict consistency, such as transaction prices or access permission status.
- Do not convert all programming exceptions, null errors, or configuration errors into a generic default result. Those bugs need to be detected and fixed.

For write operations, if the request can be stored for deferred processing, return a clear accepted status and provide a tracking ID. If there is no durable storage mechanism, return an error so the caller knows the operation has not been confirmed.

## Designing Fallbacks to Prevent Cascading Failures

Fallbacks also consume resources and can fail themselves. Several principles help prevent a fallback from becoming a new source of failure:

1. **Do not call the same failing service again:** the fallback should use a cache, static data, an independent source, or return a degraded state.
2. **Set timeouts for backup sources:** do not let the fallback wait indefinitely and hold onto the main request thread.
3. **Limit cost:** avoid heavy queries, creating new thread pools, or calling many other services inside the fallback.
4. **Preserve result semantics:** mark data as stale, undetermined, or pending.
5. **Limit retries:** if the fallback pushes to a queue or calls an alternative source, ensure bounded retry/backoff and deduplication mechanisms.
6. **Record the cause:** log the error type and dependent service ID so operations can distinguish between an open Circuit Breaker, timeouts, server errors, and fallback errors.

Fallbacks should generally not open another nested chain of Circuit Breakers without an explicit design. Multiple layers of fallback can mask the root cause and make it difficult to trace the request path. If you must call an alternative source, give it its own policy and monitor it as an independent dependency.

## Observing and Testing Fallbacks

Do not just verify that the user receives a response. You need to know how often fallbacks occur, for what reason, how stale the substitute data is, and whether the fallback itself fails.

Useful metrics include:

- Fallback count by Circuit Breaker name and error type.
- Rates of primary calls succeeding, failing, being slow, and being rejected.
- Ratio of fallbacks finding valid cached data versus having no data.
- Average and maximum age of cached data used.
- Number of requests queued for deferred processing and number of requests that failed processing.
- Total request latency when going through the fallback.

You should test at least the following scenarios:

| Scenario | Expected Outcome |
| --- | --- |
| Primary service succeeds | Return primary result and update cache if appropriate. |
| Primary service times out, cache is fresh | Return cached data with a stale-data indicator and update timestamp. |
| Primary service fails, cache is expired | Return an unavailable status or a clear error. |
| Circuit Breaker is `OPEN` | Primary call is rejected fast and fallback handles it according to policy. |
| Fallback also fails | Error is propagated or mapped clearly; no infinite call loop occurs. |
| Invalid request | Validation rejects the request; fallback is not used to mask input errors. |
| Service recovers | Primary calls succeed again and cached data is updated. |

During testing, observe both the final response and the Circuit Breaker metrics. A fallback returning HTTP 200 does not mean the dependent call succeeded; if you only monitor the final status, the system can conceal a dependency that is continuously failing.

## Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| Fallback fixes errors in the dependent service. | Fallback only provides an alternative response while the primary path is failing. |
| One default value can be used for every error. | The alternative value must match business semantics and consistency requirements. |
| Fallback is always invoked for every exception in the application. | It only applies to wrapped calls and errors forwarded to the fallback handler by the integration. |
| Ignoring an exception in metrics means no fallback is needed. | Failure recording classification and error handling for the caller are two separate decisions. |
| Any cache can be used as a fallback. | The cache must match the data scope, be properly protected, and not exceed the allowed age limit. |
| Fallback returning HTTP 200 means the dependency is healthy. | Primary path outcomes and fallback invocation counts must be monitored separately. |

Fallback is appropriate when the application has a safe, bounded, and explainable alternative response. Combining fallback with a Circuit Breaker allows remaining functional parts to keep serving while a dependency degrades, while ensuring users and downstream systems accurately understand the state of data or operations.
