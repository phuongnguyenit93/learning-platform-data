# Designing a Stale-Data Fallback with Freshness Metadata

A stale-data fallback enables a read API to continue returning useful information when a dependency is temporarily unavailable. However, returning cached data without clearly stating when it was updated can mislead callers into thinking it is the latest data. A good fallback must decide whether stale data is still permitted and return metadata indicating its source, update timestamp, and age.

In Spring Cloud CircuitBreaker, the fallback is invoked when a protected call fails or is rejected. The fallback can read a previously saved snapshot from cache and build a degraded response. You must distinguish between when the data was updated at the source and when the application stored it in cache. If you only use the cache write time, old data can be mistaken for fresh data.

This lesson designs a fallback based on the stale-if-error principle: only use stale data when the dependency fails with an eligible error, the data is still within its maximum age limit, and the business use case tolerates staleness. The response must explicitly convey freshness so clients do not treat stale data as current.

## 1. What Problem Does a Stale-Data Fallback Solve?

Suppose Catalog Service provides product names, descriptions, and categories. Order API calls Catalog Service to display product details. When Catalog Service temporarily times out, the API can use a previously stored snapshot to keep serving the read screen.

There are three outcomes to distinguish:

- **Fresh**: new data was successfully retrieved from the source and is within the age limit considered fresh.
- **Stale but acceptable**: new data could not be retrieved, but the cached snapshot has not exceeded the maximum stale age limit and the business allows temporary use.
- **Unavailable**: no snapshot exists, or the snapshot is too old, invalid, or unsafe to use.

Not all cached data should be treated as a valid fallback. A cache may hold revoked data, changed permissions, or expired entries. The fallback must enforce an explicit freshness policy instead of merely checking whether a cache key exists.

Stale fallback fits certain read flows better, such as product names, descriptions, display settings, or reference content. For inventory counts, account balances, access permissions, payment statuses, and transactional decisions, stale data can cause serious harm. Even if an inventory snapshot is displayed for reference, it must be re-verified against the authoritative source before confirming an order.

## 2. Distinguishing sourceUpdatedAt and cachedAt

A snapshot should store at least two timestamps:

- **sourceUpdatedAt**: the time the data was updated at the authoritative source.
- **cachedAt**: the time the application received and stored the snapshot in cache.

These two timestamps do not carry the same meaning.

For example, Catalog Service returns a record with `sourceUpdatedAt` at 09:00. The application receives the data at 09:10 and caches it. At 09:20, the dependency times out. The data's age at fallback time is 20 minutes, not 10 minutes.

If the application overwrites `sourceUpdatedAt` with the cache read time or fallback execution time, old data gets artificially refreshed. Only update `cachedAt` when genuinely receiving a new snapshot from the source; never update timestamps simply because the cache was read or a fallback was returned.

Snapshot model:

~~~java
public record CachedCatalog(
        CatalogItem value,
        Instant sourceUpdatedAt,
        Instant cachedAt,
        String sourceVersion) {
}
~~~

If upstream does not provide a source update timestamp, do not assign `sourceUpdatedAt` using the current clock and claim the data is definitely fresh. You can store `observedAt` to indicate when the application last received a response, while making clear that data age is only measured since that observation and does not prove when the underlying data changed.

## 3. Defining a Freshness Policy

A simple policy has two thresholds:

- **freshFor**: maximum age for a snapshot to be considered fresh.
- **maxStale**: maximum age still permitted in fallback.

Example:

~~~yaml
app:
  fallback:
    catalog:
      fresh-for: 2m
      max-stale: 30m
~~~

This is application-specific configuration, not a standard Resilience4j property. The application must bind it to configuration properties and validate that `maxStale` is not less than `freshFor`.

Suppose the current time is 10:20:

| sourceUpdatedAt | Data age | Classification |
|---|---:|---|
| 10:19 | 1 minute | Fresh |
| 10:17 | 3 minutes | Stale, usable on error |
| 10:00 | 20 minutes | Stale, usable on error |
| 09:40 | 40 minutes | Too old, do not use |
| No valid timestamp | Unknown | Do not claim fresh; handle via safe policy |

Rule:

\[
age = now - sourceUpdatedAt
\]

- If `age` is negative because the timestamp is in the future, the data may suffer from clock skew or invalid metadata. Do not automatically treat it as fresh.
- If `age` is less than or equal to `freshFor`, the data is still fresh.
- If `age` is greater than `freshFor` and less than or equal to `maxStale`, the data is stale but acceptable on failure.
- If `age` is greater than `maxStale`, return an unavailable status or error according to the API contract.

Thresholds must be driven by business requirements. Catalog content might tolerate 30 minutes; listed prices, access permissions, or transaction statuses may require a stricter policy or disallow stale fallback altogether.

## 4. Responses Must Clearly State Data Freshness

Clients need to know whether data is fresh or stale to choose how to display it and decide whether to proceed. Never return only the business object without metadata.

Example response:

~~~json
{
  "data": {
    "id": "SKU-100",
    "name": "Mechanical Keyboard",
    "description": "Compact keyboard"
  },
  "freshness": {
    "status": "STALE",
    "sourceUpdatedAt": "2026-11-24T09:00:00Z",
    "cachedAt": "2026-11-24T09:10:00Z",
    "ageSeconds": 1200,
    "maxStaleSeconds": 1800,
    "sourceVersion": "catalog-v184"
  },
  "fallback": {
    "used": true,
    "reasonCode": "DEPENDENCY_UNAVAILABLE"
  }
}
~~~

The response communicates:

- `status`: FRESH, STALE, or UNAVAILABLE.
- `sourceUpdatedAt`: when the source updated the snapshot.
- `cachedAt`: when the application received the snapshot.
- `ageSeconds`: age of the data when the response was generated.
- `maxStaleSeconds`: the active stale limit.
- `sourceVersion`: version or revision provided by upstream, if available.
- `fallback.used`: indicates whether the response used a fallback.
- `reasonCode`: standardized reason code, without exception messages.

Do not include hostnames, internal URIs, stack traces, tokens, or exception details in the response. Failure details belong in internal logs and traces. If the response has no valid data, return null `data` with `UNAVAILABLE` freshness or use an HTTP status matching the API contract.

## 5. Create Data Types for Freshness Metadata

Metadata can be modeled as dedicated records:

~~~java
public enum FreshnessStatus {
    FRESH,
    STALE,
    UNAVAILABLE
}

public record FreshnessMetadata(
        FreshnessStatus status,
        Instant sourceUpdatedAt,
        Instant cachedAt,
        long ageSeconds,
        long maxStaleSeconds,
        String sourceVersion) {
}

public record FallbackMetadata(
        boolean used,
        String reasonCode) {
}

public record CatalogResponse(
        CatalogItem data,
        FreshnessMetadata freshness,
        FallbackMetadata fallback) {
}
~~~

If no valid snapshot exists, `data` can be null or the response can use a separate result type to represent unavailable. For new APIs, pick a consistent schema and avoid forcing clients to guess what null means.

Metadata must clearly distinguish:
- Fresh data from upstream.
- Data read from cache that is still within the fresh window.
- Stale data used because the dependency failed.
- No eligible data available to return.

If older clients must be supported, you can preserve the existing response schema and add compatible metadata fields. Clearly define API versioning and rules for how clients that do not understand `STALE` status are handled.

## 6. Compute Data Age Using a Controllable Clock

Inject `Clock` instead of calling `Instant.now()` directly across multiple places. This keeps freshness logic consistent and testable with fixed timestamps.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

public class FreshnessPolicy {

    private final Clock clock;
    private final Duration freshFor;
    private final Duration maxStale;

    public FreshnessPolicy(
            Clock clock,
            Duration freshFor,
            Duration maxStale) {

        if (freshFor.isNegative()
                || maxStale.isNegative()
                || maxStale.compareTo(freshFor) < 0) {
            throw new IllegalArgumentException(
                    "maxStale must be >= freshFor >= 0");
        }

        this.clock = clock;
        this.freshFor = freshFor;
        this.maxStale = maxStale;
    }

    public Optional<Duration> ageOf(Instant sourceUpdatedAt) {
        if (sourceUpdatedAt == null) {
            return Optional.empty();
        }

        Instant now = clock.instant();
        if (sourceUpdatedAt.isAfter(now)) {
            return Optional.empty();
        }

        return Optional.of(Duration.between(sourceUpdatedAt, now));
    }

    public FreshnessStatus classify(Duration age) {
        if (age.compareTo(freshFor) <= 0) {
            return FreshnessStatus.FRESH;
        }

        if (age.compareTo(maxStale) <= 0) {
            return FreshnessStatus.STALE;
        }

        return FreshnessStatus.UNAVAILABLE;
    }
}
~~~

This example rejects future timestamps to prevent negative ages. If a system has known clock skew, a bounded tolerance can be added, provided its handling is explicitly defined. Do not silently clamp every future timestamp to the current time, as that can mask clock or metadata bugs.

`maxStale` is the age limit at response generation time. If the cache has a shorter TTL, the snapshot may already be evicted before the fallback checks it. Cache TTL should be long enough to retain data through the fallback window, or use a dedicated controlled store for stale snapshots.

## 7. Write to Cache Only After Receiving a Valid Response

New data should only replace an old snapshot after the upstream response has been validated and decoded successfully.

Synchronous service example:

~~~java
public CatalogResponse fetchCatalogItem(String id) {
    return catalogCircuitBreaker.run(
            () -> fetchAndCache(id),
            cause -> staleFallback(id, cause)
    );
}

private CatalogResponse fetchAndCache(String id) {
    CatalogItem item = catalogClient.fetch(id);

    validate(item);

    Instant cachedAt = clock.instant();
    CachedCatalog snapshot = new CachedCatalog(
            item,
            item.sourceUpdatedAt(),
            cachedAt,
            item.sourceVersion()
    );

    catalogCache.put(id, snapshot);

    return responseForFreshSnapshot(snapshot);
}
~~~

In this example, `sourceUpdatedAt` and `sourceVersion` come from upstream data. `cachedAt` is when the application received the valid response. If validation fails, do not overwrite a valid older snapshot with incomplete data.

If upstream returns data without a version, `sourceVersion` can be left empty or null per the schema. Do not fabricate a synthetic version and treat it as the source revision.

For distributed caches, ensure snapshot writes are atomic or versioned so a slow, older response cannot overwrite a newer one. For example, two requests run concurrently: request A fetches version 10 slowly; request B fetches version 11 and writes first; if A writes later, the cache could regress to version 10. You can use compare-and-set based on `sourceVersion` or an authoritative timestamp.

## 8. Selecting a Stale Snapshot in Fallback

The fallback must read the snapshot, verify timestamps, and decide whether returning it is permitted. Never return stale data just because the cache has an entry.

~~~java
private CatalogResponse staleFallback(String id, Throwable cause) {
    if (!isTransientDependencyFailure(cause)) {
        throw new CatalogFallbackNotApplicableException(cause);
    }

    Optional<CachedCatalog> cached = catalogCache.find(id);
    if (cached.isEmpty()) {
        return unavailableResponse("NO_CACHED_SNAPSHOT");
    }

    CachedCatalog snapshot = cached.get();

    Optional<Duration> age =
            freshnessPolicy.ageOf(snapshot.sourceUpdatedAt());

    if (age.isEmpty()) {
        return unavailableResponse("INVALID_SOURCE_TIMESTAMP");
    }

    FreshnessStatus status = freshnessPolicy.classify(age.get());

    if (status == FreshnessStatus.UNAVAILABLE) {
        return unavailableResponse("SNAPSHOT_TOO_OLD");
    }

    return responseForSnapshot(
            snapshot,
            status,
            age.get(),
            true,
            "DEPENDENCY_UNAVAILABLE"
    );
}
~~~

Helpers such as `isTransientDependencyFailure`, `unavailableResponse`, and `responseForSnapshot` must be implemented according to the application's exception types, cache, and response model.

A sound policy typically enables stale fallback only for transient failures like timeouts, connection failures, or 503. Business or security errors such as 404, validation errors, 401, or 403 should not automatically return stale data because doing so can mask deleted resources or revoked caller permissions.

If the cache entry is ineligible, the fallback must return an unavailable state or let the exception flow to the error handler. Do not turn every error into a stale response.

## 9. Classify Errors Before Using Stale Data

Not every exception means the dependency is temporarily unavailable.

| Error group | Use stale snapshot? | Reason |
|---|---|---|
| Timeout | Maybe | Source did not respond in time |
| Connection refused/reset | Maybe | Connection issue may be transient |
| HTTP 503/502 | Maybe | Upstream or gateway is temporarily unavailable |
| Circuit Breaker OPEN | Maybe | Call was blocked due to prior dependency failures |
| HTTP 404 | Usually not | Resource may have been deleted or does not exist |
| HTTP 401/403 | Should not | Likely an authentication or authorization failure |
| Validation/mapping error | Should not | Data or contract may be invalid |
| Business rejection | No | Not a dependency availability issue |

Classification must be based on exception type, HTTP status, and the API contract. Do not classify by searching for the substring "timeout" in exception messages.

With Resilience4j, you can configure `recordExceptions`, `ignoreExceptions`, or predicates to decide which errors affect the failure rate. Whether fallback runs still depends on how the adapter invokes the fallback. Verify separately:
- Which errors are recorded by the Circuit Breaker.
- Which errors trigger the fallback.
- Which errors must be propagated as-is to the caller.

If the fallback handler throws a new exception, preserve the cause so logs and traces can identify the root cause. Never replace an authorization error with a successful cached response.

## 10. Building FRESH, STALE, and UNAVAILABLE Responses

A centralized helper ensures every endpoint returns consistent metadata:

~~~java
private CatalogResponse responseForSnapshot(
        CachedCatalog snapshot,
        FreshnessStatus status,
        Duration age,
        boolean fallbackUsed,
        String reasonCode) {

    FreshnessMetadata freshness = new FreshnessMetadata(
            status,
            snapshot.sourceUpdatedAt(),
            snapshot.cachedAt(),
            age.toSeconds(),
            maxStale.toSeconds(),
            snapshot.sourceVersion()
    );

    FallbackMetadata fallback = new FallbackMetadata(
            fallbackUsed,
            fallbackUsed ? reasonCode : null
    );

    return new CatalogResponse(snapshot.value(), freshness, fallback);
}
~~~

When fetching new data from upstream, status is usually `FRESH` if `sourceUpdatedAt` age does not exceed `freshFor`. If the source returns an already-old timestamp, a newly fetched network response may still contain data that is stale relative to the source. Do not mark it `FRESH` merely because the HTTP request just succeeded.

When the fallback reads from cache:
- If the age is still within `freshFor`, the response can record `FRESH` freshness while setting `fallback.used` to true, since the data was served from cache while the dependency failed.
- If the age exceeds `freshFor` but does not exceed `maxStale`, status is `STALE`.
- If it exceeds `maxStale`, do not return the snapshot.

This distinction prevents confusion between data origin and content freshness. `fallback.used` answers "did the response use the fallback path?", while `freshness.status` answers "is the content fresh according to policy?".

## 11. Reactive Fallback with WebClient

In WebFlux, caching and fallback should remain reactive. Never call a blocking cache directly on the event loop. You can use a reactive cache repository returning `Mono<Optional<CachedCatalog>>` or a similar reactive abstraction.

~~~java
public Mono<CatalogResponse> getCatalogItem(String id) {
    Mono<CatalogItem> remote = webClient.get()
            .uri("/catalog/{id}", id)
            .retrieve()
            .bodyToMono(CatalogItem.class)
            .doOnNext(this::validate);

    Mono<CatalogResponse> cachedAndStored = remote
            .flatMap(item -> {
                CachedCatalog snapshot = toSnapshot(item, clock.instant());

                return reactiveCatalogCache.put(id, snapshot)
                        .thenReturn(responseForFreshSnapshot(snapshot));
            });

    return reactiveCircuitBreaker.run(
            cachedAndStored,
            cause -> reactiveCatalogCache.find(id)
                    .flatMap(snapshot -> staleOrUnavailable(id, snapshot, cause))
                    .switchIfEmpty(Mono.just(
                            unavailableResponse("NO_CACHED_SNAPSHOT")))
    );
}
~~~

This snippet assumes `reactiveCatalogCache.put` and `find` return non-blocking publishers. If the current cache library is blocking, offload the operation to an appropriate scheduler or use a reactive client; never call `block()` on a WebFlux event loop.

`staleOrUnavailable` must apply the same freshness rules and exception classification as the synchronous version. If `cause` is not a transient error, emit an error instead of a stale snapshot.

Do not place cache-write side effects before the response is validated. `doOnNext` is suitable for lightweight side effects, but if the cache write is asynchronous and must complete before returning the response, compose it with `flatMap` as shown.

## 12. Stale-if-error vs. Stale-while-revalidate

These two strategies have different goals:

- **Stale-if-error**: only uses stale data when a fresh read fails or the dependency is unavailable.
- **Stale-while-revalidate**: returns stale data immediately upon expiry while triggering a background refresh.

Do not mix the two strategies without clearly defining the API contract. With stale-while-revalidate, callers can receive stale data even when the dependency is healthy. With stale-if-error, callers only receive stale data after an eligible error.

If implementing background refresh:
- Allow only one refresh task per key within the same window to avoid stampedes.
- Bound refresh concurrency and timeouts.
- Do not let a failed refresh overwrite a good snapshot.
- Use versioning or compare-and-set to prevent an older response from overwriting a newer one.
- Monitor refresh success/failure and snapshot age.

Fallbacks should not launch bursts of synchronous refresh requests for every caller. When a dependency is already failing, doing so amplifies load and delays recovery.

## 13. Protecting Business Logic When Using Stale Data

Freshness is not just a caching concern. Each data field may have a different tolerance for staleness.

| Data type | Recommended policy |
|---|---|
| Product name and description | Can allow stale within a short window |
| Thumbnail images or static content | Typically tolerates longer staleness |
| Displayed price | Use only if business allows and display update time |
| Inventory | Can be used for reference, but must be re-confirmed before ordering |
| Account balance | Do not use stale data to confirm transactions |
| Access permissions | Do not use stale cache to grant access when current status cannot be verified |
| Payment status | Must query the authoritative source before concluding |

A stale response should prompt the client to display clear context, such as "Data updated at 09:00". Never merely change colors or hide the stale status in the UI.

If an operation has side effects, never use a stale snapshot to decide whether to execute the transaction. You can use stale data to render suggestions, but the write step must re-verify against the authoritative source or use a dedicated consistency workflow.

## 14. Cache Security and Data Isolation

Fallback caches must follow the same security rules as the data source:

- Keys must include tenant or data scope when data is partitioned by tenant.
- Never serve one tenant's snapshot to another tenant.
- When access is revoked, provide an invalidation mechanism or independent permission check.
- Sensitive data requires appropriate TTLs, encryption, and access controls.
- Do not log sensitive payloads or tokens during fallback.
- When a snapshot lacks a valid version or timestamp, apply a safe fallback policy.

In particular, 401/403 errors should never automatically trigger stale fallback for access-controlled data. If a caller no longer has access, returning cached data can leak revoked information.

Caches must have size limits and eviction policies. Stale fallback is not a reason to retain data indefinitely. `maxStale` bounds content age; TTL and eviction bound storage lifetime. Both must be configured.

## 15. Monitoring Freshness and Fallback

Counting fallback invocations alone does not reveal the quality of the data being served. Track:

- Count of fresh vs. stale responses.
- Fallback counts by dependency and reason category.
- Snapshot age at response time, including p50, p95, and p99.
- Number of snapshots rejected for exceeding `maxStale`.
- Number of cache misses (no entry).
- Number of missing or future timestamp errors.
- Time elapsed between `sourceUpdatedAt` and `cachedAt`.
- Refresh success and failure rates.
- Count of stale responses served on critical business flows.

Metric labels should have low cardinality: dependency, route, and freshness status. Do not include product IDs, tenant IDs, request IDs, or exception messages in metric labels. Use logs/traces with correlation IDs to investigate individual requests.

You can emit structured logs:

~~~text
event=circuit_breaker_fallback
dependency=catalog
freshness=STALE
age_seconds=1200
max_stale_seconds=1800
reason_code=DEPENDENCY_UNAVAILABLE
request_id=server-generated-id
~~~

Do not include raw exception messages in responses. Keep stack traces in internal logs with proper access controls.

## 16. Testing Freshness with a Fixed Clock

Do not use `Thread.sleep` to wait for a snapshot to become stale. Injecting `Clock` and using `Clock.fixed` makes data age deterministic in tests.

Example:

~~~java
Instant now = Instant.parse("2026-11-24T10:00:00Z");
Clock clock = Clock.fixed(now, ZoneOffset.UTC);

CachedCatalog snapshot = new CachedCatalog(
        catalogItem,
        now.minus(Duration.ofMinutes(10)),
        now.minus(Duration.ofMinutes(9)),
        "catalog-v184"
);
~~~

With `freshFor` of 2 minutes and `maxStale` of 30 minutes, the snapshot above is 10 minutes old and classified as `STALE`. Tests must verify that the response preserves `sourceUpdatedAt`, `cachedAt`, `ageSeconds`, and `sourceVersion`.

Cases to test:

1. Snapshot 1 minute old: `FRESH` status.
2. Snapshot exactly at `freshFor`: still `FRESH` if the rule uses `<=`.
3. Snapshot older than `freshFor` but younger than `maxStale`: `STALE` status.
4. Snapshot exactly at `maxStale`: accepted if the rule uses `<=`.
5. Snapshot older than `maxStale`: `UNAVAILABLE`.
6. No cache entry: `NO_CACHED_SNAPSHOT`.
7. Null or future timestamp: do not claim freshness.
8. 404 or 403 error: do not use stale fallback when disallowed by policy.
9. Timeout or connection failure: use stale if within limits.
10. Reading fallback does not alter `sourceUpdatedAt` or `cachedAt`.

## 17. Testing Fallback Through Circuit Breaker

You can use a mock client and cache to verify end-to-end behavior:

- When upstream succeeds, the service returns source data and updates the cache.
- When upstream times out, the fallback reads the snapshot and returns `STALE` metadata.
- When the snapshot is too old, the response is `UNAVAILABLE` or an error per contract.
- When the cache is empty, the response does not fabricate data.
- When the error is 401/403/404, do not return a snapshot if it is a business or authorization error.
- When Circuit Breaker is `OPEN`, the upstream supplier is not called, while fallback can still read the cache.
- When fallback cache lookup fails, the application returns a safe fallback error and records cache errors separately.

Check upstream invocation counts to confirm that an `OPEN` Circuit Breaker does not continue issuing requests. Also verify cache read counts and response metadata. Do not only assert that the response body contains data; assert freshness status, timestamps, and reason codes.

For reactive pipelines, use `StepVerifier` and lazy publishers to control subscriptions. If the cache client is reactive, verify the fallback publisher is subscribed to only when the fallback path is chosen. If using a blocking cache, verify the operation does not run on the event loop.

## 18. Common Mistakes

- **Using `cachedAt` instead of `sourceUpdatedAt` to calculate age**: old data can be artificially refreshed.
- **Updating timestamps when reading cache**: every fallback makes the snapshot appear newer than it is.
- **Returning cached data without freshness metadata**: clients cannot tell the data is stale.
- **Serving stale data for every exception**: can mask 401, 403, 404, or business errors.
- **Not setting `maxStale`**: data can be served indefinitely.
- **Confusing stale-if-error with stale-while-revalidate**: the two strategies have different triggers.
- **Using stale data to confirm transactions**: old data can cause wrong decisions or side effects.
- **Writing to cache before validation**: corrupt data can overwrite a valid snapshot.
- **Ignoring concurrent writes**: slow older responses can overwrite newer versions.
- **Calling a blocking cache on the event loop**: stalls reactive applications.
- **Not isolating cache by tenant or permissions**: risks leaking out-of-scope data.
- **Measuring only fallback counts**: hides the actual age of data callers receive.
- **Excessive retries or refreshes inside fallback**: can trigger a stampede while the dependency is failing.

## 19. Implementation Workflow

When designing a stale fallback in Spring Cloud CircuitBreaker, follow this sequence:

1. Identify data types and decide which business flows may use stale snapshots.
2. Require upstream to provide `sourceUpdatedAt` or an authoritative version.
3. Store `sourceUpdatedAt`, `cachedAt`, and source version separately.
4. Define `freshFor` and `maxStale` per data type.
5. Write to cache only after the upstream response is validated.
6. Classify exceptions and enable stale fallback only for eligible transient errors.
7. In the fallback, compute age using `Clock` and reject invalid timestamps or snapshots that are too old.
8. Return explicit freshness metadata alongside a standardized fallback reason code.
9. Secure the cache by tenant, access permissions, TTL, and capacity.
10. For reactive flows, use a reactive cache or appropriate scheduler; never block the event loop.
11. Test `freshFor`/`maxStale` boundaries, business errors, timeouts, Circuit Breaker `OPEN`, and empty cache cases.
12. Monitor data age, stale rate, refresh failures, and unavailable response counts.

A stale-data fallback is only safe when callers know when the data was last updated and the application enforces business-driven age limits. Keeping `sourceUpdatedAt` and `cachedAt` separate, using stale data only for eligible errors, enforcing `maxStale`, and returning `FRESH`/`STALE`/`UNAVAILABLE` metadata empowers clients to make the right decisions. The Circuit Breaker protects the dependency; the freshness policy protects the meaning of the data returned by the fallback.
