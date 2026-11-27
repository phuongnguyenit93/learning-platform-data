# Distinguishing HTTP Buffers, Business Caches, and Fallback Data

## Lesson Objectives

When protecting calls to a dependent service with Spring Cloud CircuitBreaker, an application may handle HTTP payloads, store data for reuse, and return degraded results when calls fail. These three activities often appear together in a gateway, yet they serve different purposes and have different lifecycles:

- **HTTP buffer** temporarily holds bytes or data chunks currently being transferred/decoded during a single network exchange.
- **Business cache** stores a domain-meaningful value so multiple requests can read it again according to a key and freshness policy.
- **Fallback data** is an alternative result returned when the primary operation cannot provide a valid outcome.

Confusing these three concepts can waste memory, silently return stale data, or cause fallback values to be cached as real data. After this lesson, you will be able to:

- Distinguish HTTP-layer buffers from caches with keys, TTLs, and business rules.
- Understand body buffering in WebClient and memory limits when decoding responses.
- Design a business cache with freshness metadata and a stale-use policy when dependencies fail.
- Choose appropriate fallback data and clearly represent degraded states.
- Place fallback after the circuit breaker boundary so the breaker still records failures.
- Avoid writing fallback data into the cache as though it were an authoritative result from the dependent service.

## 1. Three Concepts, Three Lifecycles

Suppose order-service calls catalog-service to fetch product information. During processing, the application may receive HTTP bytes, decode them into a Product, store the Product in a cache, and return a fallback result if catalog-service fails to respond.

| Concept | Purpose | Lifecycle | Example |
| --- | --- | --- | --- |
| HTTP buffer | Temporarily holds bytes in transit or aggregates body chunks for decoding. | Typically tied to one request/response and released after processing. | Socket buffer, Netty DataBuffer, body buffered by a codec for decoding. |
| Business cache | Reuses domain data across multiple requests. | Has keys, expiration, update policies, and eviction. | Product by SKU in Caffeine or Redis. |
| Fallback data | Provides an alternative response when the primary call fails or is rejected by circuit breaker. | Selected for a single execution; may come from cache or be constructed by rule. | ProductView in STALE or UNKNOWN state. |

An HTTP buffer does not automatically become a cache. Having read a response into memory does not mean the next request can retrieve that response again. A business cache can reuse data after the initial request finishes. Likewise, fallback is not automatically persisted; it is simply how the application responds when no reliable primary result is available.

## 2. HTTP Buffers Operate at the Transport Layer

HTTP clients and network runtimes can use buffers to receive, send, or forward bytes. In a Spring WebFlux application, Reactor Netty uses memory regions like `DataBuffer`/`ByteBuf` to handle network data. A codec may accumulate the response body in memory when it needs to decode it into an object.

Example:

    Mono<ProductDto> product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class);

`bodyToMono` asks the decoder to construct one `ProductDto`. For finite response bodies, the codec may need to accumulate data before completing decoding. This is buffering for transport and decoding. Once the publisher completes, the temporary buffer is managed and released according to the client/codec lifecycle.

Key points to remember:

- A buffer holds bytes or chunks; it has no understanding of Product, price, or stock.
- A buffer has no business key such as SKU or customerId.
- A buffer has no inherent TTL, invalidation rules, or stale-data policy.
- Bounding buffer size prevents an oversized response from consuming excessive heap or direct memory.
- For large payloads or streams, process incrementally instead of always buffering the entire body.

You can cap how much data codecs are allowed to buffer in memory when configuring WebClient:

    ExchangeStrategies strategies = ExchangeStrategies.builder()
        .codecs(codecs ->
            codecs.defaultCodecs().maxInMemorySize(2 * 1024 * 1024)
        )
        .build();

    WebClient client = WebClient.builder()
        .exchangeStrategies(strategies)
        .build();

The 2 MiB value is only an example. Choose based on valid API payload sizes and the application's memory budget. When a body exceeds the limit, the codec can emit `DataBufferLimitException`. This signals that a payload exceeded the decode limit; do not automatically treat every such case as the dependent service being unavailable. Classify it according to the API contract and circuit breaker's error-recording policy.

### Handling Large Responses or Streaming

If an API returns large datasets, consider `Flux` to process elements incrementally:

    Flux<ProductDto> products = webClient.get()
        .uri("/products/export")
        .retrieve()
        .bodyToFlux(ProductDto.class);

`Flux` allows streaming processing and leverages backpressure instead of holding the whole list in memory. If the application works directly with `DataBuffer`, follow buffer lifecycle rules and release buffers properly when manually retained or discarded. Holding `DataBuffer` references too long can increase memory pressure or cause direct-memory leaks.

Buffering is about transporting and decoding payloads. If you want to reuse decoded results across multiple requests, design a dedicated domain-level cache.

## 3. HTTP Caching Also Differs from Transport Buffering

Beyond buffers, HTTP also has caching governed by protocol semantics. Headers such as `Cache-Control`, `ETag`, `Last-Modified`, `Age`, and `Vary` can allow browsers, proxies, or HTTP caches to store responses and revalidate them later.

An HTTP cache differs from a buffer in that it can reuse responses across multiple requests according to HTTP rules. Still, it differs from a business cache:

- An HTTP cache primarily stores resource representations and follows protocol headers and cache keys.
- A business cache stores domain objects or processed data according to application keys and rules.
- A transport buffer only holds data temporarily during send/receive or decoding.

If catalog-service returns `Cache-Control` or `ETag`, a client or proxy can use HTTP caching or conditional requests when supported. However, do not assume WebClient automatically provides a full HTTP cache merely because a response includes a `Cache-Control` header. You need an explicit cache layer or HTTP caching client and must verify actual behavior.

For private or user-specific data, review `Cache-Control: private/no-store`, `Vary`, and user identity before allowing caching in shared proxies or devices. Caching at the wrong scope can leak data across users.

## 4. Business Caches Store Domain Data for Reuse

A business cache stores decoded values that are meaningful within the domain. For example, a catalog cache stores Product by SKU:

    product-cache
      key: product:{tenant}:{locale}:{currency}:{sku}
      value:
        name: "Mechanical keyboard"
        price: 1250000
        version: 18
        fetchedAt: 2026-11-24T10:00:00Z
        expiresAt: 2026-11-24T10:05:00Z

Unlike an HTTP buffer, a business cache requires decisions on:

- **Key:** is data looked up by SKU, tenant, locale, or what combination?
- **TTL:** how long is the data considered fresh?
- **Freshness:** may data past TTL be used temporarily when the service fails?
- **Invalidation:** when price or product details change, how is the cache updated or deleted?
- **Eviction:** how are entry counts or memory usage bounded?
- **Consistency:** how much staleness relative to the source of truth is acceptable?
- **Scope:** does the data depend on user, tenant, or access permissions?

A cache can reside in-process using Caffeine or in a distributed store like Redis. A local cache offers low latency, though each instance may hold different values. A distributed cache shares data across instances while adding another operational dependency. Whichever you choose, set clear capacity limits, TTLs, and update policies.

Do not cache data merely because a response arrived. Only store outcomes validated against the domain contract. If a response is an error, incomplete, or fails validation, do not write it to the cache as an authoritative value.

## 5. Fresh Cache, Stale Cache, and Usage Policies on Failure

Cached entries typically have freshness states over time:

| State | Meaning | Usage |
| --- | --- | --- |
| Fresh | Within the normal freshness window. | Can be returned directly if business rules allow. |
| Stale but usable | Past normal TTL but still within the allowed window for failure fallback. | Use only when a stale-if-error policy permits, and explicitly indicate stale data. |
| Expired/unusable | Past usage limit or invalidated. | Do not use as fallback; return an error or unknown state. |

For example, product descriptions might tolerate being several minutes stale, whereas price or stock levels may require fresher data. A cache policy should clearly define two thresholds: normal TTL and maximum stale window when the primary source is unavailable.

Do not apply one blanket stale window to every data type. Pricing, inventory, access permissions, credit limits, and payment status carry different risks. For data affecting transactions or security, stale fallback may be disallowed altogether.

When returning stale data, the response should include metadata so callers or clients know it is stale, for example:

    {
      "sku": "SKU-42",
      "name": "Mechanical keyboard",
      "availability": "STALE",
      "dataAsOf": "2026-11-24T10:00:00Z",
      "source": "CACHE"
    }

This is an illustrative structure defined by the application. Do not use a generic `availability` field if the domain already assigns a different concept to it; choose names that clearly express data state. The `dataAsOf` timestamp should be when the data was fetched from the authoritative source, not when the fallback was returned.

## 6. Fallback Is a Response Decision, Not a Type of Cache

Fallback is an alternative execution branch when the primary operation cannot deliver a normal result. There are several kinds of fallback:

- Reading fresh or stale cache if business rules permit.
- Returning an `UNKNOWN` status when data cannot be determined.
- Returning a default value for optional partial information.
- Calling another backup source if backed by an appropriate contract and limits.
- Propagating the error to the caller if no safe alternative response exists.

A fallback does not have to read a cache. A fallback may return an unavailable status or instruct the client to retry. Conversely, a cache can serve normal requests even when no failure has occurred.

Distinguish three cases:

1. Cache hit: the primary source does not need to be called because the cache holds usable data.
2. Fallback from cache: the primary source was called but failed or was rejected by the breaker, so the application falls back to cache under a stale-if-error policy.
3. Static/degraded fallback: no suitable cached data exists, so the application returns a substitute state or propagates the error.

Do not turn a fallback into a fake value that looks like authoritative data. For example, if price lookup fails, returning `price = 0` could make the system price orders as free. If inventory lookup fails, returning `quantity = 0` could make the application assert the product is out of stock. Represent `UNKNOWN`, `UNAVAILABLE`, or an equivalent domain state instead.

## 7. Place Fallback After Circuit Breaker to Avoid Hiding Failures

With Resilience4j Reactor operators, the circuit breaker must observe primary call errors before errors are converted into fallbacks. Example:

    Mono<ProductView> primary = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .map(ProductView::from)
        .doOnNext(productCache::putAuthoritative);

    Mono<ProductView> result = primary
        .transformDeferred(CircuitBreakerOperator.of(catalogCircuitBreaker))
        .onErrorResume(error -> {
            if (!isDependencyAvailabilityFailure(error)) {
                return Mono.error(error);
            }

            return productCache.findUsable(id)
                .map(CachedProduct::toFallbackView)
                .switchIfEmpty(Mono.error(error));
        });

In this example:

- `primary` calls catalog-service and maps the DTO into a domain view.
- `putAuthoritative` stores only primary results that arrived and converted successfully.
- `CircuitBreakerOperator` observes the primary call's outcome.
- `onErrorResume` runs after the operator, using the cache only for permitted error categories.
- If the cache has no usable entry, the original error is propagated.

If you place `onErrorResume` before `CircuitBreakerOperator` and turn every error into `Mono.just(...)`, the breaker may see only successes. Failure rate and slow-call statistics will no longer accurately reflect the dependency.

With Spring Cloud's `ReactiveCircuitBreakerFactory` API, the fallback is passed to `run`:

    return circuitBreakerFactory.create("catalog-read").run(
        primary,
        error -> {
            if (!isDependencyAvailabilityFailure(error)) {
                return Mono.error(error);
            }

            return productCache.findUsable(id)
                .map(CachedProduct::toFallbackView)
                .switchIfEmpty(Mono.error(error));
        }
    );

The factory API handles invoking the fallback when the publisher fails or the breaker denies permission. `isDependencyAvailabilityFailure` is an application-defined policy; avoid using an overly broad condition that turns programming bugs, validation failures, or decoding errors into fallback data.

For synchronous calls, the same principle applies to `CircuitBreaker.run`'s fallback function: only return substitute data when the error belongs to a category the business allows recovering from.

## 8. Do Not Write Fallback Data into the Cache as Authoritative Data

A common mistake is placing the cache write after the branch that merges primary and fallback results:

    Mono<ProductView> result = protectedCall
        .onErrorResume(error -> Mono.just(ProductView.unknown(id)))
        .doOnNext(productCache::putAuthoritative);

This code can write `ProductView.unknown` into the cache as though it came from catalog-service. Subsequent requests could keep reading the `UNKNOWN` state even after the service has recovered.

Only update the cache on the primary source's success path, before fallback:

    Mono<ProductView> primary = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .map(ProductView::from)
        .doOnNext(productCache::putAuthoritative);

    return circuitBreakerFactory.create("catalog-read").run(
        primary,
        error -> productCache.findUsable(id)
            .map(CachedProduct::toFallbackView)
            .switchIfEmpty(Mono.error(error))
    );

If the business intentionally wants to store a degraded state, store it in a separate namespace or record type with clear origin and timestamp. Never overwrite the primary cache with fallback data. When the service recovers, fresh authoritative data must replace old values per defined update rules.

Also avoid updating the cache from a late-arriving response if it is older than currently cached data. Under concurrent updates, you may need a version number, source timestamp, or compare-and-set so stale responses do not overwrite newer data.

## 9. Classify Errors to Choose the Right Fallback

Not every error should trigger the same fallback:

| Error type | Typical appropriate handling |
| --- | --- |
| Connection timeout or service unreachable | Can use stale cache if the domain permits. |
| Circuit breaker OPEN / `CallNotPermittedException` | Do not call primary source; consider usable cache or unavailable status. |
| HTTP 5xx | Can use cache per server-error policy. |
| HTTP 404 | May be a valid domain outcome; handle per contract rather than defaulting to stale data. |
| HTTP 401/403 | Propagate authentication/authorization error; never return cache scoped to another user. |
| Validation or programming error | Propagate error to surface the defect; do not mask with a generic fallback. |
| Payload exceeds decode limit | Check size contract and codec settings; do not automatically treat as transient service failure. |
| Bulkhead rejection | Return busy status or use cache if allowed; avoid immediate retries that add load. |

The error classification function should inspect actual HTTP client exceptions, status codes, and the API contract. Some 4xx codes carry special meaning such as `429 Too Many Requests`; do not lump all 4xx codes into a single business-error or ignore bucket.

Fallback does not replace security checks. If a cache stores data per tenant or user, verify access permissions before returning cached entries. Never use fallback to bypass authorization checks simply because the auth service is failing.

## 10. Cache Keys, Freshness, and Access Control

A cache key based solely on `productId` may be insufficient if results vary by tenant, language, currency, or user permissions. Identify every dimension that affects the representation:

    product:{tenant}:{locale}:{currency}:{sku}

This is an example key; include only dimensions that genuinely affect the data. Broader keys increase entry counts, so balance precision against capacity.

For permission-scoped data:

- Never return tenant A's cache to tenant B.
- Never skip authorization checks when the primary source fails.
- Never cache responses containing tokens, cookies, or unnecessary personal data.
- Explicitly define whether cache entries are shared across users.
- When access permissions are revoked, consider invalidation or re-checking permissions before serving cached entries.

Freshness also requires a trustworthy time source. Use the origin data's timestamp when available, or record `fetchedAt` when receiving an authoritative result. Do not refresh `fetchedAt` on cache reads, as that makes stale data look fresh.

## 11. Observe Buffer, Cache, and Fallback Separately

To pinpoint root causes during system degradation, monitor each layer independently:

| Layer | Metrics or events to observe |
| --- | --- |
| HTTP buffer/codec | Body sizes, `maxInMemorySize` limit breaches, decode errors, heap/direct memory pressure. |
| Business cache | Hit/miss, eviction, TTL expiration, data age on read, stale hits, and cache errors. |
| Fallback | Fallback count by cause, fallback type, ratio of UNKNOWN/STALE/UNAVAILABLE. |
| Circuit breaker | CLOSED/OPEN/HALF_OPEN state, failure rate, slow-call rate, rejected call count. |
| HTTP client | Connect/response timeouts, active connections, network errors, and latency. |

If cache hits rise alongside stale reads, review TTLs or invalidation. If fallbacks rise while the breaker opens, the dependency may be experiencing an outage. If `DataBufferLimitException` rises, response bodies may exceed the codec limit or the application may be buffering too large a stream. Do not blindly raise buffer limits without understanding payload sizes and memory impact.

Metrics should use tags with controlled cardinality. Avoid attaching SKU, `userId`, or `requestId` as metric tags if values can grow unbounded. Keep fine-grained identifiers in controlled logs compliant with data policies.

## 12. Practice Exercise: Using Cache as a Controlled Fallback

Build a catalog gateway to fetch product information and protect calls with a circuit breaker:

1. Create a `WebClient` calling `catalog-service` and returning `Mono<ProductDto>`.
2. Configure codec buffer limits matching valid response sizes.
3. Create a `ProductCache` keyed by tenant and SKU, with a normal TTL and maximum stale window.
4. Write to the cache only when the primary response decodes and passes validation.
5. Wrap the primary publisher with a circuit breaker whose ID is `catalog-read`.
6. Place the fallback after the breaker; use the cache only for permitted availability failures.
7. Return metadata indicating whether the outcome is `LIVE`, `STALE`, or `UNKNOWN` along with `dataAsOf`.
8. Force `catalog-service` to time out and verify the breaker records the failure before fallback returns stale cache.
9. Let the cache pass its stale window and verify the application propagates the error or returns unavailable per contract.
10. Restore `catalog-service` and verify fresh results update the primary cache, replacing old data.
11. Test a response body larger than the codec limit and distinguish buffer/decode errors from availability errors.
12. Verify cache keys never leak data across tenants or users.

When complete, you should be able to point out where the HTTP buffer lives and when it is released, what data the business cache stores and under what freshness rules, under what conditions fallback triggers, and why fallback must never be written into the authoritative cache. Separating these three layers helps control memory, data correctness, and behavior when dependent services become unavailable.
