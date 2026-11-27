# Returning Degraded Results While Preserving the Contract

When a dependent service is slow or unavailable, fallback helps the application continue serving partial needs instead of letting every request fail. However, a fallback is only useful when the alternative result still complies with a contract the caller understands. A structurally valid response that silently carries fabricated data, overly stale data, or an invalid business state can cause harder-to-detect bugs than returning a clear error.

With Spring Cloud Circuit Breaker and Resilience4j, a fallback can return a degraded result, such as cached data marked with an update timestamp, partial data that does not depend on the failing service, or a "temporarily unavailable" status. The design must preserve data types, field semantics, business rules, and how callers process the result.

## The Result Contract Must Clearly State What Happened

Suppose a catalog API returns product details. If the catalog service does not respond, the fallback can retrieve a copy from cache. The caller still receives the same response type, yet needs to know that it is cached data and when that data was last updated.

A result contract should distinguish at least:

- **Live data:** successfully retrieved from the dependent service.
- **Degraded data:** may be a stale cache copy, aggregated data, or a partial result; must describe the source and completeness level.
- **No alternative data:** the application cannot return a trustworthy business result; in that case it must return an appropriate error or an explicit unavailable status.

For example, the response can use `availability` and `dataAsOf` fields to express source and freshness:

```java
public enum Availability {
    LIVE,
    DEGRADED,
    UNAVAILABLE
}

public enum DataSource {
    CATALOG,
    CACHE,
    NONE
}

public record ProductView(
        String productId,
        String name,
        Availability availability,
        DataSource source,
        Instant dataAsOf
) {
    public static ProductView fromCatalog(Product product) {
        return new ProductView(
                product.id(), product.name(),
                Availability.LIVE, DataSource.CATALOG, Instant.now());
    }

    public static ProductView fromCache(CachedProduct product) {
        return new ProductView(
                product.id(), product.name(),
                Availability.DEGRADED, DataSource.CACHE,
                product.updatedAt());
    }

    public static ProductView unavailable(String productId) {
        return new ProductView(
                productId, null,
                Availability.UNAVAILABLE, DataSource.NONE, null);
    }
}
```

`ProductView` maintains a uniform schema across all three states. Callers do not have to guess where the data came from or mistake an empty product name for "not found" versus "service failing". If an existing API already has a public schema, extend it in a backward-compatible way and align with consumers before changing required fields.

Do not assign plausible-looking default values to critical fields. For instance, returning a product price of `0`, a balance of `0`, or an order status of `COMPLETED` just to avoid an empty response can cause callers to act on false assumptions. If a business-valid alternative result cannot be produced, represent unavailability or return a handleable error.

## Choosing Alternative Data According to Business Rules

Fallbacks should follow a clear order of precedence. For a catalog read API, a common strategy is:

1. Use live data when the dependent service responds successfully.
2. When the request fails, look for a cached copy that has all required fields and falls within the allowed data age limit.
3. If the cache is missing or too old, return an unavailable status per the API contract.

```java
public ProductView getProduct(String productId) {
    CircuitBreaker breaker = circuitBreakerFactory.create("catalog");

    return breaker.run(
            () -> ProductView.fromCatalog(catalogClient.findProduct(productId)),
            error -> cache.findProduct(productId)
                    .filter(cached -> cached.isFreshWithin(Duration.ofMinutes(15)))
                    .map(ProductView::fromCache)
                    .orElseGet(() -> ProductView.unavailable(productId))
    );
}
```

The example assumes `cache.findProduct` is a fast local operation that does not call the catalog service again. The 15-minute limit is illustrative only; maximum data age must come from business requirements. Pricing and inventory may require tighter limits than product descriptions. Personal data, access permissions, payment status, or order status generally must not use stale cached data if doing so could distort decisions or leak information.

A fallback should not intentionally call the very same failing service through another client or network path. Doing so can add extra load right when the service is struggling and prolong the failure chain. Prefer independent backup sources such as local caches, bounded read replicas, approved static data, or precomputed degraded results.

## Distinguishing Technical Errors from Business Outcomes

Not every situation should trigger the same fallback. A request where a product is not found is a valid business outcome; a timeout calling the catalog service is a technical error; a malformed request is a caller input error. Collapsing all of them into a single degraded result can hide programming bugs or turn "not found" into "service temporarily unavailable".

Define which exceptions the circuit breaker records as failures, which are ignored, and which must propagate straight to the caller. You can use `recordExceptions`, `ignoreExceptions`, `recordExceptionPredicate`, or `ignoreExceptionPredicate` in Resilience4j depending on the version and configuration.

| Scenario | Typically Appropriate Handling |
|---|---|
| Timeout or connection error to dependent service | Can use cache fallback if data is still fresh enough |
| Circuit breaker rejects call when `OPEN` | Use the same fallback policy designed for dependency errors |
| Product does not exist per business response | Return not-found result per contract; do not synthesize cached data |
| Invalid or unauthorized request | Return validation/authorization error; do not mask with backup data |
| Cache failure or expired entry | Return unavailable status or a clearly mapped exception |

The fallback can also inspect the error cause to choose an action. However, do not rely on a single exception class name if the backend might wrap exceptions. Inspect the cause chain or use predicates on the actual exception types and keep the classification policy consistent.

## Keeping HTTP Response Semantics Clear

Returning a DTO from a fallback does not by itself determine the HTTP status. The controller or API mapping layer must choose a status consistent with the contract:

- If cached data is considered a valid read result and the schema includes `availability=DEGRADED`, the API can return `200 OK` along with metadata indicating stale data.
- If no usable alternative result exists, the API can return `503 Service Unavailable` or a defined business error code.
- If the caller needs to retry later, consider `Retry-After` when a retry time is meaningful and can be estimated.

Do not return `200 OK` with an empty object if consumers will interpret it as a normal business result. Conversely, you do not necessarily have to return `503` just because a cache was used: if the API permits cached data and clearly advertises freshness, that response can still satisfy the contract.

Example of mapping a degraded response:

```java
@GetMapping("/products/{id}")
public ResponseEntity<ProductView> getProduct(@PathVariable String id) {
    ProductView result = catalogService.getProduct(id);

    if (result.availability() == Availability.UNAVAILABLE) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(result);
    }

    return ResponseEntity.ok()
            .header("X-Data-Availability", result.availability().name())
            .body(result);
}
```

This is one design option. If your existing API already mandates a different status code or error envelope, follow the existing contract and express the degraded state via compatible fields or metadata.

## Fallbacks with Reactive Publishers

With Spring Cloud `ReactiveCircuitBreaker`, the fallback must return the same publisher type and element type as the primary source. You can use a reactive cache or emit a predefined degraded result:

```java
public Mono<ProductView> getProduct(String productId) {
    ReactiveCircuitBreaker breaker =
            circuitBreakerFactory.create("catalog");

    Mono<ProductView> request = Mono.defer(() ->
            catalogClient.findProduct(productId)
                    .map(ProductView::fromCatalog)
    );

    return breaker.run(request, error ->
            cache.findProduct(productId)
                    .filter(cached -> cached.isFreshWithin(Duration.ofMinutes(15)))
                    .map(ProductView::fromCache)
                    .switchIfEmpty(Mono.just(ProductView.unavailable(productId)))
    );
}
```

The fallback returns `Mono<ProductView>` and does not subscribe itself. Here `switchIfEmpty` handles the case where the cache has no entry or the entry fails the age limit. If the cache client itself can emit errors, decide how to handle cache errors separately; do not let a fallback error accidentally produce a response that violates the contract.

With `Flux`, think carefully before using `Flux.empty()` as a fallback. An empty stream can mean "no matching results", whereas the actual situation is "search service unavailable". If those two meanings differ, return an envelope type with status metadata or emit an error mapped to an error response.

## Fallbacks Do Not Erase Original Errors

When a circuit breaker executes a supplier and the supplier fails, the backend evaluates the original call according to its configuration. The fallback supplies an alternative result for the caller; a fallback succeeding does not mean the dependent service is healthy. If the fallback hides all errors behind a default value, dashboards may show external API requests succeeding while the circuit breaker continues recording high dependency failure counts.

Therefore, observe separately:

- Error rate and slow-call rate of the circuit breaker.
- Fallback invocation rate and triggering causes.
- Ratio of degraded responses, data sources, and data age.
- Rate at which fallbacks fail or find no alternative data.

Logs should include correlation ID, dependency name, error type, fallback decision, and data source. Avoid logging sensitive data or entire payloads. Metrics should use bounded-cardinality tags; do not attach product ID, user ID, or request ID as labels.

## Testing Contracts and Degradation Limits

Testing a fallback is not just confirming that "no exception is thrown". You must verify that callers receive the right schema, right status, data from the right source, and data within the allowed age limit.

| Scenario | Expected Verification |
|---|---|
| Catalog returns live data | `availability=LIVE`, `source=CATALOG`, and data matches |
| Catalog times out, cache is fresh | `availability=DEGRADED`, `source=CACHE`, `dataAsOf` preserves cache timestamp |
| Catalog fails, cache is too old | Returns `UNAVAILABLE` status or contract-defined error |
| Breaker `OPEN` | Supplier is not invoked; fallback applies the same policy |
| Product does not exist | Returns not found, does not turn into default cached data |
| Cache emits error | Fallback error is mapped clearly, does not return a fake valid object |

Service tests can use mocks to control the dependency and cache:

```java
when(catalogClient.findProduct("p-10"))
        .thenThrow(new TimeoutException("catalog timeout"));
when(cache.findProduct("p-10"))
        .thenReturn(Optional.of(freshCachedProduct));

ProductView result = catalogService.getProduct("p-10");

assertEquals(Availability.DEGRADED, result.availability());
assertEquals(DataSource.CACHE, result.source());
assertEquals(freshCachedProduct.updatedAt(), result.dataAsOf());
```

In integration tests, force the circuit breaker to `OPEN` or generate enough failures to transition its state, then confirm the supplier is not called. With reactive code, use `StepVerifier` to verify the fallback publisher emits the expected state and does not execute before subscription.

## Design Principles

A good degraded result helps callers make safe decisions. Keep the schema and field meanings explicit; advertise the source and freshness; use cache only when business rules allow; separate technical errors from business outcomes; keep fallbacks independent, fast, and bounded; and monitor original failures separately from degraded outcomes. When trustworthy alternative data cannot be produced, transparently returning an unavailable status protects the contract far better than pretending the request succeeded.
