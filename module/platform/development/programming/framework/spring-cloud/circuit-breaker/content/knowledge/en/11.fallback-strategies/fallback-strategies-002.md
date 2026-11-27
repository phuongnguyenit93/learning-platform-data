# Returning Cached Data with Clear Freshness Indicators

When a dependent service is slow or temporarily unavailable, a circuit breaker can stop sending further calls and route handling to a fallback. For read operations, a useful fallback is returning data stored in a cache, provided that copy is still within the staleness limit accepted by the business logic.

Cached data can keep screens displaying information and reduce the impact of dependency outages. However, stale data must be clearly identified. Users and API callers need to know when the data was updated, how old it is, and what purposes it can safely be used for. A response that looks normal while silently serving stale data can lead to wrong decisions.

## Why Should Data Freshness Be Exposed?

Suppose an order service calls an inventory service to display product quantities. The inventory service experiences an outage for a few minutes. If the application has the most recent inventory snapshot in cache, it can continue displaying reference data instead of returning a complete error page.

However, the cached inventory quantity may no longer be accurate. Another order might have reserved the product after the cache entry was created. Therefore, the fallback response needs to make it clear that the data is the latest known snapshot, not the current quantity confirmed by the authoritative source.

A response containing freshness information helps:

- Users recognize whether the data they are viewing is fresh or stale.
- Frontends display warning labels or restrict actions based on data reliability.
- Calling services decide whether to proceed with processing or require re-confirmation.
- Operations teams measure how many responses use stale data and how old that data is.
- The system avoid confusing nonexistent data with data that is temporarily unreachable.

Cache-based fallback is best suited for read queries that can tolerate a certain degree of data lag. It is not a transaction confirmation mechanism and does not guarantee that the cache reflects the current state of the source system.

## Distinguishing Source Update Time from Cache Write Time

To evaluate freshness accurately, you must distinguish at least two timestamps:

| Timestamp | Meaning | Used For |
|---|---|---|
| sourceAsOf | The point in time when the data reflected the state in the source system. | Calculating the actual age of the data. |
| cachedAt | The point in time when the entry was written into the current cache. | Diagnosing cache behavior, sync timing, and refreshes. |

Do not use `cachedAt` instead of `sourceAsOf` when calculating staleness. For example, a sync job might re-read stale data from an intermediate source and write it to the cache at 10:05. Looking only at `cachedAt`, the application might think the data is only seconds old even though the actual source state has been stale since 09:20.

Data age should be computed from the source timestamp that the data represents:

~~~java
Duration age = Duration.between(snapshot.sourceAsOf(), clock.instant());
~~~

If the source timestamp is in the future relative to the application clock, there may be clock skew or invalid data. Do not silently treat such data as fresh; validate and reject invalid records or apply an appropriate time-synchronization policy.

A data model can store both timestamps:

~~~java
public record InventorySnapshot(
        String sku,
        int available,
        Instant sourceAsOf,
        Instant cachedAt
) {
}
~~~

`sourceAsOf` should be provided by the source system or a trustworthy sync process. If a source timestamp cannot be obtained, explicitly document that data age is only estimated from observation or sync time, and do not describe it as the exact update time at the source.

## Setting Allowed Data Age Limits

Not every cached entry should be returned. Define two time thresholds:

- **Fresh TTL:** the duration during which a cached entry is considered fresh under normal policy.
- **Maximum stale age:** the maximum age at which data may still be returned as a fallback option.

For example, product catalog details might be considered fresh for 10 minutes and allowed to be displayed as stale for up to 24 hours. Inventory counts might only be allowed as fallback for 30 seconds on a reference view, while reservation operations must always confirm directly with the source service.

| Data Type | Illustrative Fresh TTL | Illustrative Maximum Stale Age | Usage |
|---|---:|---:|---|
| Product descriptions | 10 minutes | 24 hours | Can display stale copy with update timestamp. |
| Categories and filters | 5 minutes | 2 hours | Can continue browsing with a stale-data warning. |
| Reference exchange rates | 1 minute | 5 minutes | Must show timestamp and not be used to finalize transactions if business rules require live rates. |
| Reference inventory quantities | 15 seconds | 30 seconds | Display only; re-confirm before reserving stock. |
| Payment status or access permissions | Per source policy | Do not use stale fallback without business approval | Requires confirmed status from an authoritative source. |

The durations above are examples only. Business owners must decide the maximum staleness based on how fast the data changes and the consequences of users acting on outdated data.

Do not use a single global maximum stale age for every type of data. Slowly changing descriptive data can tolerate hours, whereas inventory, pricing, or access permissions may require very short limits or be disallowed entirely when the source is unavailable.

## Returning Data Along with Freshness Metadata

The API should express data status explicitly. You can use statuses such as:

| freshness | Meaning | Client-Side Behavior |
|---|---|---|
| FRESH | Data was just successfully fetched from the source or is within the policy's fresh window. | Display normally. |
| STALE | Data was served from cache because fresh data could not be retrieved; still within maximum stale age. | Display a stale-data badge and the source update timestamp. |
| UNAVAILABLE | No suitable cached data exists or the cached copy is too old. | Display a state indicating data could not be loaded; do not assume a default value is valid. |
| NOT_FOUND | The source confirmed the data does not exist. | Display a not-found outcome according to business rules. |

A response DTO can include the data, freshness status, source update timestamp, and data age:

~~~json
{
  "sku": "SKU-1024",
  "available": 12,
  "freshness": "STALE",
  "sourceAsOf": "2026-11-24T09:58:00Z",
  "ageSeconds": 420,
  "message": "Showing the latest cached data"
}
~~~

This is illustrative data. In an actual response, standardize field names, time zones, and timestamp formats. Return timestamps with an explicit time zone—typically UTC—and let the client format them for the user's time zone.

Do not return only a boolean such as `stale=true` if callers need to know how old the data is. You can provide `freshness`, `sourceAsOf`, `ageSeconds`, and `maximumStaleAgeSeconds`. However, only include metadata meaningful to clients; avoid exposing internal exception details or dependent service addresses.

## Integrating Cache Fallback with Spring Cloud CircuitBreaker

The following example illustrates an inventory read client. The call is protected by a circuit breaker with ID `inventory-read`. When fresh data is retrieved successfully, the application stores the snapshot in the cache. When the call fails or the circuit is `OPEN`, the fallback looks up the latest snapshot and returns it only if it has not exceeded `maximumStaleAge`.

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Optional;

import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryQueryService {

    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final Clock clock;

    private final Duration maximumStaleAge = Duration.ofSeconds(30);

    public InventoryQueryService(
            InventoryClient inventoryClient,
            InventoryCache inventoryCache,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            Clock clock) {
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.clock = clock;
    }

    public InventoryResult find(String sku) {
        return circuitBreakerFactory.create("inventory-read").run(
                () -> fetchAndCache(sku),
                error -> staleOrUnavailable(sku, error)
        );
    }

    private InventoryResult fetchAndCache(String sku) {
        InventorySnapshot snapshot = inventoryClient.fetch(sku);
        inventoryCache.put(sku, snapshot);
        return InventoryResult.fresh(snapshot, ageOf(snapshot));
    }

    private InventoryResult staleOrUnavailable(
            String sku,
            Throwable failure) {

        if (failure instanceof ProductNotFoundException) {
            return InventoryResult.notFound(sku);
        }

        Instant now = clock.instant();

        Optional<InventorySnapshot> cached =
                inventoryCache.find(sku)
                        .filter(snapshot ->
                                !snapshot.sourceAsOf().isAfter(now))
                        .filter(snapshot ->
                                Duration.between(snapshot.sourceAsOf(), now)
                                        .compareTo(maximumStaleAge) <= 0);

        return cached
                .map(snapshot -> InventoryResult.stale(
                        snapshot,
                        Duration.between(snapshot.sourceAsOf(), now)
                ))
                .orElseGet(() -> InventoryResult.unavailable(sku));
    }

    private Duration ageOf(InventorySnapshot snapshot) {
        return Duration.between(snapshot.sourceAsOf(), clock.instant());
    }
}
~~~

`InventoryClient`, `InventoryCache`, `InventorySnapshot`, and `InventoryResult` are illustrative application components. In a real implementation, add the appropriate imports, data types, and exception classification policies for your project.

The example highlights several important decisions:

- Fresh data is written to the cache only after the source call completes successfully.
- The fallback never invents a synthetic inventory count.
- Data with a `sourceAsOf` in the future is excluded from cache fallback.
- Data exceeding `maximumStaleAge` is rejected.
- `ProductNotFoundException` is mapped to `NOT_FOUND` instead of using a stale cached entry to mask a nonexistent record.
- If no suitable cache entry exists, the API returns `UNAVAILABLE`.

In a real application, classify errors before returning cached data. Do not serve stale data for every `Throwable`. Validation errors, invalid input, programming bugs, or business exceptions may need dedicated handling. Only transient source unavailability or calls rejected by the circuit breaker should trigger the stale fallback policy.

## Fallback Should Only Serve Appropriate Read Purposes

A stale cache entry can be useful for display queries but unsafe for write operations or irreversible decisions.

For example, with inventory:

- The product detail page can display the latest known quantity alongside a `STALE` label.
- The shopping cart can show reference information and prompt for re-verification before placing an order.
- Reserving or deducting inventory must call the authoritative service and confirm the actual result.
- Cached data must never be treated as proof that a transaction succeeded.

For payments, access permissions, balances, or order statuses, stale data can cause severe consequences. If business rules do not allow stale data, the fallback should return `UNAVAILABLE` or ask the caller to retry once the source recovers. Do not use default values such as `0`, `true`, or `false` to simulate a confirmed result.

## Stale-While-Revalidate and Data Refreshing

One strategy you can use is stale-while-revalidate: when a cached entry has passed its Fresh TTL but is still within its Maximum stale age, the application returns the stale data immediately and triggers a background refresh task.

High-level flow:

~~~mermaid
flowchart TD
    A[Read data request] --> B{Cache still fresh?}
    B -->|Yes| C[Return FRESH data]
    B -->|No| D{Source available?}
    D -->|Yes| E[Call source and update cache]
    E --> F[Return fresh data]
    D -->|No| G{Cache entry within maximum stale age?}
    G -->|Yes| H[Return STALE data]
    G -->|No| I[Return UNAVAILABLE]
    H --> J[Bounded refresh task]
~~~

Not every fallback needs stale-while-revalidate. For a simple application, returning a cached entry within bounds and letting the next request attempt to fetch fresh data is enough. If you implement background refreshes, ensure concurrency limits, timeouts, controlled retries, and a mechanism to prevent multiple requests from refreshing the same cache key simultaneously.

Measures to prevent cache stampede:

- Use single-flight or an appropriate distributed lock to coalesce refresh requests for the same key.
- Cap the number of concurrent refresh tasks.
- Set a dedicated timeout and circuit breaker for refresh calls.
- Add jitter to expiration times to avoid many keys expiring at the same TTL instant.
- Do not allow the refresh queue to grow unbounded.
- If a refresh fails, keep the old `sourceAsOf`; do not update the source timestamp merely because a refresh was attempted.

Background refreshes must not alter freshness metadata before valid new data is received. If a refresh task only re-fetches an old copy from an intermediate source, `sourceAsOf` must still reflect when the data was actually updated.

## Handling Cache Misses, Cache Failures, and Expired Entries

Because fallback depends on the cache, the cache itself needs a clear failure policy. Some common scenarios:

| Scenario | Handling |
|---|---|
| No cache entry | Return `UNAVAILABLE` or an appropriate status; do not fabricate dummy data. |
| Cache entry within maximum stale age | Return `STALE` with freshness metadata. |
| Cache entry too old | Do not return content; return `UNAVAILABLE`. |
| Cache unreachable | Log the cache failure and return an appropriate degraded status. |
| Source timestamp missing or invalid | Do not treat data as fresh; only use if an explicit estimation policy exists. |
| Cache holds a lower version than already known | Do not overwrite newer data with an older snapshot. |

If the cache is an external dependency such as Redis, cache unreachability can cause the fallback itself to fail. Decide whether the application will return a controlled error, local in-memory data if available, or an `UNAVAILABLE` response. Never assume a fallback will always succeed simply because a fallback function exists.

With multiple replicas, a distributed cache can share data but still requires synchronization and consistency policies. If using a local cache, each replica may hold different snapshots with different ages. The `sourceAsOf` metadata helps callers and operations teams see this discrepancy.

## Protecting Consistency During Data Updates

When source data changes, the cache can become outdated immediately. For write operations, update or invalidate the cache according to business consistency rules. If the cache cannot be updated immediately, metadata must continue showing the old `sourceAsOf` until new confirmation arrives.

You can use a version or sequence number from the source to avoid overwriting a newer snapshot with a late-arriving event. For instance, if the cache holds version 42, a late sync task carrying version 41 must not replace it. Timestamps can help, but source versions are usually more reliable when determining update ordering.

For composite data, clarify whether `sourceAsOf` represents the entire snapshot or individual fields. Do not combine fields from different points in time and publish a single timestamp as if they formed a consistent snapshot.

## Observing Stale Fallback Quality

Beyond circuit breaker state, measure whether the fallback is genuinely helping the application serve better or merely masking an outage.

Metrics to monitor:

- Count of `FRESH`, `STALE`, and `UNAVAILABLE` responses by data type.
- Data age at return time, especially p95 and p99 of `ageSeconds`.
- Cache miss count and entries rejected for exceeding `maximumStaleAge`.
- Fallback ratio over total read requests.
- Circuit breaker `OPEN` count and rejected call count.
- Count of refresh tasks succeeded, failed, throttled, or coalesced.
- Proportion of stale data used in subsequent operations, if measurable by the business logic.

Metric tags should have bounded cardinality, such as dependency name, data type, and freshness status. Do not attach SKU, user ID, or order ID as tags because cardinality can explode rapidly. Detailed IDs can be recorded in logs or traces according to the system's data policy.

Alerts should be based on both frequency and data age. A high `STALE` ratio over a brief period may be acceptable right when a source service degrades, but if data age steadily approaches `maximumStaleAge`, alert before the cache becomes ineligible to serve.

## Testing Fallbacks with Freshness Indicators

Test both cache-hit and cache-miss scenarios:

| Scenario | Expected Verification |
|---|---|
| Source call succeeds | Returns `FRESH` and updates cache with the correct `sourceAsOf`. |
| Source fails, cache within bounds | Returns `STALE`, preserves `sourceAsOf`, and computes age accurately. |
| Source fails, cache too old | Returns `UNAVAILABLE`, does not return expired data. |
| Source fails, cache miss | Returns `UNAVAILABLE`. |
| Cache has a future timestamp | Rejects snapshot or handles per clock-skew policy. |
| Product does not exist | Returns `NOT_FOUND`; does not mask with a stale snapshot. |
| Circuit `OPEN` | Does not call source; fallback uses only eligible cached entries. |
| Cache unreachable | Returns controlled degraded status and logs cache failure. |
| Two concurrent refreshes for same key | Verifies single-flight or concurrency limiting works. |
| Older snapshot arrives after newer snapshot | Does not overwrite the newer version. |

Use an injectable `Clock` in tests to control time without waiting for real TTLs. Verify `sourceAsOf` and `cachedAt` separately to ensure that re-writing a cache entry does not nominally turn stale data into fresh data.

## Design Checklist

1. Identify which read operations can continue with stale data and which require confirmed current data.
2. Define separate Fresh TTL and Maximum stale age values per data type.
3. Store `sourceAsOf` alongside `cachedAt` and, if available, the version from the source system.
4. Return freshness metadata in the response so callers know whether data is `FRESH`, `STALE`, or `UNAVAILABLE`.
5. Use cache fallback only for transient dependency errors or circuit breaker rejections; handle business errors separately.
6. Never return expired snapshots, invalid timestamps, or versions older than already-known data.
7. If using background refreshes, bound concurrency and prevent cache stampedes.
8. Monitor data age, stale fallback rate, cache misses, and circuit breaker state.
9. Test source failures, cache failures, expired caches, and nonexistent records.

Returning cached data is a practical way to preserve read availability when a dependent service fails. The value of this strategy depends on bounding data age and exposing freshness transparently. When callers know when data was updated and how old it is, the application can continue serving appropriate features while maintaining clarity about information reliability.
