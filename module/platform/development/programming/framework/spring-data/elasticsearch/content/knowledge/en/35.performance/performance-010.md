# Distinguishing Query Cache, Request Cache, and Application Cache

Elasticsearch and Spring applications have multiple caching layers, each storing a different type of result. The **query cache** stores reusable results for parts of a query, primarily queries running in filter context. The **request cache** stores shard-level search results for eligible requests, which is especially useful for aggregations or requests needing no hits (`size: 0`). The **application cache** stores business results or processed responses on the application side, typically using Caffeine, Redis, or another cache provider.

All three caching layers can coexist within a single request. The application cache can return a response without calling Elasticsearch; on a cache miss, Elasticsearch can reuse the request cache; while executing the request, eligible filters can be assisted by the query cache. They do not replace one another because they differ in scope, cache keys, invalidation behavior, and storage cost.

To pick the right cache in Spring Data Elasticsearch, first identify what repeats, how often data changes, and how much staleness is acceptable. Only then choose the cache, configure TTL or invalidation policies, and measure hit ratios. Enabling every cache at once without understanding keys and refresh behavior can add complexity without improving performance.

## 1. Three caching layers in a search architecture

```text
Client request
     |
     v
Application cache
     | cache hit
     +------------------------------> Cached response
     |
     | cache miss
     v
Spring Data Elasticsearch
     |
     v
Elasticsearch search request
     |
     +--> Request cache: shard/request result already cached?
     |
     +--> Query cache: segment filter result already cached?
     |
     v
Search execution / aggregation
     |
     v
Response -> application mapping -> optional app cache
```

| Layer | Storage location | What is cached | Reuse scope |
|---|---|---|---|
| Query cache | Elasticsearch node heap | Matching document set for a query in filter context, per segment | A filter can be reused across many different search requests |
| Request cache | Elasticsearch node heap, per shard | Results of eligible search requests | Equivalent requests hitting the same shard copy |
| Application cache | Application JVM or external cache such as Redis | DTOs, result pages, aggregation responses, or business data | Multiple application requests sharing the same cache key |

### Example

A dashboard continually displays active product counts by category:

- Filters `tenantId = tenant-42` and `status = ACTIVE` can be reused by the query cache.
- A search request returning only aggregations with `size: 0` can have its shard results stored in the request cache.
- The API can cache the complete dashboard DTO in Redis for 30 seconds to avoid calling Elasticsearch on every page load.

Each cache eliminates a different slice of work. If data refreshes continuously, the request cache may invalidate frequently; if the app cache TTL is long, the dashboard may still serve stale data even after Elasticsearch has newer data.

## 2. What is the query cache?

Elasticsearch's query cache stores the results of queries running in **filter context** as matching document sets across segments. When the same filter is used again, Elasticsearch can reuse the cached result instead of re-evaluating the filter on that segment.

The query cache is especially useful for repeated filter conditions, such as:

- `tenantId = tenant-42`.
- `status = ACTIVE`.
- `categoryId = c-100`.
- `visibility = PUBLIC`.
- Stable range filters over a fixed time window.

Example:

```json
{
  "query": {
    "bool": {
      "must": [
        {
          "match": {
            "name": "wireless mouse"
          }
        }
      ],
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  }
}
```

Both `term` conditions inside `filter` are good candidates for query cache assistance when repeated frequently enough and meeting Elasticsearch's caching criteria. The `match` clause in `must` runs in query context to compute relevance scores; do not expect the query cache to cache its scoring output in the same way.

## 3. Filter context and query context

Elasticsearch distinguishes two contexts:

| Context | Question | Computes relevance score? | Common purpose |
|---|---|---:|---|
| Query context | How well does the document match? | Yes | Full-text search, relevance ranking |
| Filter context | Does the document satisfy the condition? | No | Tenant, status, category, date ranges, exact filters |

The query cache focuses on filter context results. Therefore, place business filter conditions inside `bool.filter` rather than putting everything into `must` when scoring is unneeded.

### Example using filter context properly

```json
{
  "query": {
    "bool": {
      "must": [
        { "multi_match": {
            "query": "wireless mouse",
            "fields": ["name^3", "description"]
        }}
      ],
      "filter": [
        { "term": { "status": "ACTIVE" } },
        { "term": { "categoryId": "c-100" } },
        { "range": { "priceAmount": { "gte": 10, "lte": 100 } } }
      ]
    }
  }
}
```

The full-text condition drives relevance; the status/category/price conditions only filter out non-matching documents. This structure expresses accurate semantics and lets Elasticsearch consider caching the filters.

### Do not move every query into filter just to cache it

If users expect relevance-based ranking, keep `match` inside `must`/`should` so scores are still computed. Moving full-text queries into `filter` drops scoring and alters result ordering. Cache optimization must never break search semantics.

## 4. The query cache operates per segment

Lucene stores an index as immutable segments. The query cache ties filter results to specific segments. A filter can be cached on an existing segment and reused as long as that segment remains.

When a refresh happens, new segments open for search. When merges happen, old segments are replaced by new ones. Cache entries tied to old segments can no longer be used once those segments are removed. Thus, the query cache can lose effectiveness on heavily written indexes.

```text
Segment A -- filter F is cached
Segment B -- filter F is cached

Refresh creates Segment C
  -> Need to evaluate/cache F for Segment C

Merge A + B -> Segment D
  -> Cache entries for A/B are no longer usable for D
```

This explains why the query cache tends to benefit relatively stable data with repeated filters. Continuously changing indexes can replace cache entries before they are reused many times.

## 5. The query cache does not cache every query

Elasticsearch automatically decides which queries are eligible and worth caching. Not every filter in every request is cached immediately. The mechanism uses heuristics, repetition frequency, segment size, and cache budget; details can change across versions.

Key points to remember:

- The query cache focuses on filter context.
- Infrequently repeated queries may not be worth caching.
- Small or newly created segments may not yet qualify under current heuristics.
- Cache entries drop when their corresponding segment disappears.
- The cache has finite capacity and uses eviction.
- Queries with shifting values such as ranges containing `now` are harder to reuse than fixed filters.

Do not write code relying on a specific filter definitely being cached. Use filter context for accurate semantics and measure hit/miss rates in real workloads.

## 6. Monitoring the query cache

Query cache statistics can be inspected at the node level:

```http
GET /_nodes/stats/indices/query_cache
```

Or for a specific index:

```http
GET /products/_stats/query_cache
```

Important metrics usually include:

| Metric | Meaning |
|---|---|
| `memory_size_in_bytes` | Memory currently used by the query cache |
| `total_count` | Total times the query cache was accessed/checked per stats |
| `hit_count` | Number of matching cache hits |
| `miss_count` | Number of cache misses |
| `cache_size` | Current number of cached entries |
| `evictions` | Number of entries evicted from cache |

Metric names and groupings may differ across APIs/versions. Use node stats to understand per-node cache behavior and index stats to isolate an index's workload.

### Computing hit ratio

A simple calculation:

\[
\text{Hit ratio} = \frac{\text{hit count}}{\text{hit count} + \text{miss count}}
\]

Read this figure alongside query volume, latency, and memory. A high hit ratio does not prove the system is faster; the cache might hit on very cheap filters while the real bottleneck sits in scoring, fetch, aggregations, or network.

## 7. What is the request cache?

Elasticsearch's request cache stores search results at the shard level for eligible search requests. It helps when the same request is sent repeatedly and the underlying shard data has not changed.

By default, Elasticsearch typically caches search requests with `size: 0`. This pattern is common for dashboards and aggregations that do not return document hits and only need total hits or aggregation results.

Example:

```http
POST /products/_search
Content-Type: application/json

{
  "size": 0,
  "query": {
    "bool": {
      "filter": [
        { "term": { "tenantId": "tenant-42" } },
        { "term": { "status": "ACTIVE" } }
      ]
    }
  },
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId",
        "size": 20
      }
    }
  }
}
```

The aggregation results of this request can be stored in the request cache and reused when an equivalent request hits the same shard copy before the shard refreshes.

## 8. `size: 0` and caching aggregations

Dashboards typically do not need document hits; they need summaries such as:

- Product counts by category.
- Order totals by status.
- Daily revenue.
- User counts by region.
- Price distributions by range.

Setting `size: 0` omits hits from the response. This is also the request shape supported by Elasticsearch's request cache by default.

Example status aggregation:

```json
{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-42"
    }
  },
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

If a dashboard issues the same request repeatedly while the index changes infrequently, the request cache can substantially cut aggregation work. If the index refreshes constantly, cache entries invalidate often and benefits shrink.

## 9. Enabling or disabling the request cache per request

You can control it using the `request_cache` URL parameter:

```http
POST /products/_search?request_cache=true
Content-Type: application/json

{
  "size": 0,
  "aggs": {
    "by_category": {
      "terms": {
        "field": "categoryId"
      }
    }
  }
}
```

`request_cache=true` asks to cache the request even when it does not match the `size: 0` default, provided the request and context qualify. `request_cache=false` disables the request cache for that request.

Do not turn on `request_cache=true` mechanically for all search requests. For requests with constantly changing hits, queries referencing current time, or nearly unique keys, caching yields few hits while consuming memory and creating churn.

## 10. Request cache keys and request equivalence

The request cache only helps when requests repeat with semantically identical content. Changing the query, aggregations, sort, runtime mappings, or result-affecting parameters yields a different cache key.

Example of two distinct requests:

```json
{ "size": 0, "query": { "term": { "status": "ACTIVE" } } }
```

```json
{ "size": 0, "query": { "term": { "status": "INACTIVE" } } }
```

They cannot share results because their conditions differ.

Guidelines to keep requests reusable:

- Use a stable query structure.
- Avoid generating multiple request variants purely from inconsistent JSON field ordering if serialized manually.
- Use `size: 0` for aggregation-only requests.
- Avoid unnecessary varying parameters.
- Keep `preference` stable if requests should target the same shard copies.
- Do not embed random timestamps or correlation IDs in the query body when they do not affect results.

Elasticsearch derives cache keys from the request content and shard context; do not construct application keys based on guesswork. When using REST/clients, keep request bodies deterministic and monitor cache stats.

## 11. `preference` and cache locality

A shard can have a primary and replicas. The request cache lives on the node hosting a specific shard copy. If two identical requests hit two different shard copies, they may not share the same cache entry.

The `preference` parameter can steer requests with the same preference consistently to the same shard copies:

```http
POST /products/_search?preference=dashboard-tenant-42
```

This can improve cache locality for repeated dashboards. However, `preference` also affects load balancing and shard copy selection. Do not use a single preference value across all workloads if it concentrates load onto one node.

For distributed user-facing searches, balance cache locality against load distribution. For periodic dashboards, a stable preference can help if measured gains confirm it.

## 12. When is the request cache invalidated?

The request cache is tied to shard state. Whenever a shard refreshes and search-visible data changes, stale request cache entries become invalid and are invalidated.

Consequences:

- Low-write, infrequently refreshed indexes enjoy higher request cache hit rates.
- Continuously written indexes invalidate the cache frequently.
- A dashboard running every second on an index refreshing every second may gain little from the request cache.
- Increasing `refresh_interval` can extend cache entry lifetimes, at the cost of delaying search visibility.

This is a trade-off between freshness and cache reuse. Never lengthen `refresh_interval` solely to increase cache hits if business needs near-real-time visibility.

### Caching does not alter the consistency model

The request cache does not make Elasticsearch strongly consistent across writers and readers. It simply reuses results for a refreshed shard state. After the next refresh, old cache entries are invalidated and a new search recomputes on the new state.

## 13. Configuring request cache at the index level

Indexes have the `index.requests.cache.enable` setting to enable or disable the request cache for an index:

```http
PUT /products/_settings
Content-Type: application/json

{
  "index": {
    "requests": {
      "cache": {
        "enable": true
      }
    }
  }
}
```

This setting controls request caching eligibility at the index level. Check current settings with:

```http
GET /products/_settings?include_defaults=true
```

Do not confuse this setting with the per-request `request_cache` parameter. A request can ask for caching, yet the index setting can still disable it.

## 14. Monitoring the request cache

View statistics:

```http
GET /_nodes/stats/indices/request_cache
```

Or per index:

```http
GET /products/_stats/request_cache
```

Key fields to inspect:

| Metric | Meaning |
|---|---|
| `memory_size_in_bytes` | Memory currently used by the request cache |
| `hit_count` | Number of request cache hits |
| `miss_count` | Number of request cache misses |
| `evictions` | Number of entries evicted due to cache/size pressure |

Compute hit ratio similarly to the query cache:

\[
\text{Hit ratio} = \frac{\text{hit count}}{\text{hit count} + \text{miss count}}
\]

Inspect metrics per node and per index alongside refresh count, search latency, aggregation latency, and indexing throughput. A low hit ratio can result from non-repeating requests, scattered shard copies, frequent refreshes, or cache evictions.

## 15. What is an application cache?

An application cache lives outside Elasticsearch and stores results at the application tier. It can cache:

- An enriched product DTO.
- A search result page already mapped to an API response.
- Aggregated dashboards.
- Rarely changing category or brand lists.
- Configuration or reference data.
- Business results aggregated from multiple sources.

Common choices:

| Technology | Scope | Characteristics |
|---|---|---|
| Caffeine | Within a single JVM | Fast, low latency, each instance holds its own cache |
| Redis | Shared across instances | Fits distributed caching, centralized TTL and eviction |
| Hazelcast or cache grid | Multiple nodes | Supports distributed caching per architecture |
| Spring Cache abstraction | Unified API | Enables annotations/`CacheManager` with a chosen provider |

An application cache can store results after Spring Data converts `SearchHits` into DTOs. On a cache hit, it avoids even the network round trip to Elasticsearch.

## 16. Application cache keys

The cache key must include every factor that can alter the result. For example, for product search:

```text
product-search:
  tenantId:
  normalizedText:
  categoryId:
  status:
  sort:
  page:
  size:
  locale:
  projectionVersion
```

Omitting `tenantId` can leak tenant A's results to tenant B. Omitting sort or page can return the wrong order or page. If responses depend on permissions or roles, the cache key must include the corresponding authorization scope.

### Components typically required in keys

- Tenant or organization ID.
- Normalized search text.
- Filter values.
- Sort order.
- Page/cursor and page size.
- Locale or timezone if responses are formatted regionally.
- User/role scope if visibility depends on permissions.
- Projection/index version when response schemas change.
- Any parameters affecting aggregation results.

Never put raw access tokens or secrets into cache keys. Use stable identifiers, hashes, or scope IDs per security policy.

## 17. Spring Cache example with search page results

The Spring Cache abstraction lets you annotate methods to cache. Example caching a response DTO with a bounded page size:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductSearchService {

    @Cacheable(
        cacheNames = "product-search",
        key = "#tenantId + ':' + #text + ':' + #categoryId + ':' + #page + ':' + #size"
    )
    public ProductSearchPage search(
            String tenantId,
            String text,
            String categoryId,
            int page,
            int size) {

        // Build a validated NativeQuery and execute Elasticsearch search.
        // Map hits to an immutable ProductSearchPage DTO.
        return executeSearch(tenantId, text, categoryId, page, size);
    }
}
```

This illustrates Spring Cache usage; the application needs `@EnableCaching` and a configured `CacheManager`. The method must return a type compatible with serialization/caching for your provider. Never cache an unbounded page or an object holding open resources.

### Watch out for Spring Cache proxies

Under default proxy mode, internal calls from one method to another `@Cacheable` method inside the same bean bypass the proxy and do not trigger caching. Place cached methods in a separate bean or invoke via the managed proxy rather than expecting `this.search(...)` to always cache.

### Reactive return types

For `Mono`/`Flux`, caching behavior depends on Spring Framework, Spring Cache abstraction, and provider versions. Do not assume `@Cacheable` on a `Flux` caches an unbounded stream as expected. For reactive results, cache a bounded DTO upon completion or use an explicitly reactive cache abstraction; avoid `collectList()` on unbounded sources solely for caching.

## 18. Cache-aside, write-through, and write-behind

Application caches typically follow one of these strategies:

### Cache-aside

1. The application checks the cache.
2. On a hit, return the cached value.
3. On a miss, read from Elasticsearch/data source.
4. Store the result in the cache with a TTL.

This is simple and widespread. The application manages invalidation or accepts the TTL window.

### Write-through

When data updates, the application updates both the source and the cache in a managed flow. The cache stays refreshed along the write path if the operation succeeds.

### Write-behind

The application writes to the cache first and updates the backing store asynchronously later. This can cut write latency, yet introduces much greater complexity around durability, retries, and data loss. Do not use write-behind to turn Elasticsearch into the source of truth when business rules require a database as the authoritative store.

For search projections, cache-aside with TTL or event-based eviction is usually easier to implement. When source-of-truth change events fire, evict affected caches once the projection is updated.

## 19. Application cache TTL and invalidation

TTL (time to live) defines the maximum lifespan of a cached entry. Short TTLs shrink staleness windows at the cost of higher miss rates and Elasticsearch load. Long TTLs boost hit ratios while serving stale data longer.

Example starting policies:

| Data | Reference TTL | Reason |
|---|---:|---|
| Rarely changing category/brand lists | Minutes to hours | Infrequent updates, easy event eviction |
| Product search pages | A few to tens of seconds | Prices/statuses may change |
| Summary dashboards | Tens of seconds to minutes | Minor delay is usually acceptable |
| Permission-dependent results | Short TTL or uncached | Must track permission and scope changes |
| Transactional data requiring latest state | Uncached or re-validated against source of truth | Stale results unacceptable |

These durations are starting points only. Real TTLs must reflect freshness SLAs, update rates, and miss cost.

### Explicit eviction

After updating a product, the application can evict the product detail cache and affected search caches:

```java
@CacheEvict(cacheNames = "product-by-id", key = "#productId")
public void updateProduct(String productId, UpdateProductRequest request) {
    // Update the source of truth and trigger projection update.
}
```

Evicting a `product-by-id` key is far simpler than evicting every search query combination that might match that product. For search caches, short TTLs, versioned keys, or namespace invalidation are usually used instead of enumerating every affected query.

### Evict after successful updates

Do not evict or populate new data before the source-of-truth transaction commits. With asynchronous projections, decide whether to evict on source commit or after projection update. Evicting too early lets cache misses read the stale projection and re-cache it; evicting too late leaves stale entries in cache during the lag window.

## 20. Event-driven invalidation and versioned keys

In event-driven systems, `ProductUpdated` events can trigger eviction of related caches. If cache keys include a namespace/version, bumping the version automatically invalidates old keys:

```text
product-search:v7:tenant-42:wireless:page-0
product-search:v8:tenant-42:wireless:page-0
```

After the projection version increments, the application switches to the `v8` namespace. `v7` keys expire via TTL instead of requiring key-by-key deletion.

Versioned keys help when query combinations are vast. However, maintain a single consistent version source so instances do not accidentally use mismatched versions.

## 21. Cache stampede and coalescing cache misses

A cache stampede happens when a hot key expires or is evicted and many concurrent requests miss simultaneously, all hitting Elasticsearch/data sources together. This can cause a sudden load spike right when the cache is empty.

Mitigations:

- Single-flight/request coalescing: only one request loads data per key while others await the result.
- TTL jitter: add slight randomness to TTLs so keys do not expire in unison.
- Stale-while-revalidate: serve slightly stale entries within bounds while refreshing asynchronously.
- Scheduled pre-warming of hot dashboards/keys when justified.
- Limit concurrency of cache-miss fetches to Elasticsearch.
- Short-TTL negative caching for missing results if semantics allow.

Do not apply stale-while-revalidate to data where users must see the latest transactional state. Negative caches must also distinguish "not found" from "unauthorized".

## 22. Comparing invalidation across the three caches

| Cache | Event making entries stale | Invalidation/refresh mechanism |
|---|---|---|
| Query cache | Segment changes, merges, or removal | Per-segment entries become unused; Elasticsearch manages eviction |
| Request cache | Shard refresh changes search-visible state | Elasticsearch invalidates affected request entries |
| Application cache | Source/projection changes, permission changes, or TTL expiry | TTL, explicit eviction, event invalidation, versioned keys |

The query cache and request cache are managed by Elasticsearch around index/shard lifecycles. The application cache sits outside shard lifecycles; the application must define freshness and invalidation.

## 23. How do caches interact with refresh policies?

Refresh makes newly indexed data visible to search. It also affects the request cache because refreshes invalidate shard request cache entries. The query cache is tied to segments, so new or merged segments change the set of reusable entries.

For example, an index with `refresh_interval = 1s` and a dashboard running every 5 seconds:

```text
T0: Dashboard request -> request cache miss
T1: Index refresh -> old request cache invalidated
T5: Dashboard request -> likely another miss
T6: Index refresh -> invalidated again
```

If the index receives few writes and has a longer refresh interval, the request cache can be reused across many dashboard polls.

Do not lengthen `refresh_interval` just to preserve the request cache when search freshness must stay low. Consider application-tier caching with an appropriate TTL, or separate dashboard aggregations onto an index/read model with its own update cadence.

## 24. Caching and dynamic time expressions

Queries using `now` yield changing results over time even without an index refresh:

```json
{
  "range": {
    "expiresAt": {
      "gte": "now-24h"
    }
  }
}
```

Two requests at different timestamps can match different documents. Requests with dynamic timestamps are generally poor candidates for request cache reuse compared to fixed queries. Application caches can also serve stale data beyond expectations if keys ignore timestamps or time buckets.

If business logic permits rounding time to the minute or hour, the application can compute a fixed bucket timestamp and put that timestamp into both the query and cache key. For example, a daily dashboard can use `startOfDay` in the business timezone instead of `now` per request.

## 25. Caching and personalization

Search results can depend on the user:

- Document access permissions.
- Customer-group pricing or catalogs.
- Locale/language.
- Personal history or preferences.
- Tenant or organization.

If an application cache key omits the relevant scope, one user may receive another user's results. This is both a correctness bug and a potential data leak.

Principles:

- Authenticate/authorize before consulting caches holding sensitive data.
- Keys must include tenant and relevant authorization scopes.
- Do not cache permission-filtered responses if a stable scope cannot be modeled.
- Evict on role/permission changes or include a version in the key.
- Never trust client-supplied `tenantId` to partition caches.

Elasticsearch's request/query caches do not replace authorization. The application must still enforce filters and permissions on every request; Elasticsearch credentials should hold least-privilege permissions.

## 26. Multi-layer caching can compound staleness

If both the request cache and application cache introduce their own TTLs/invalidation delays, total staleness can stack unpredictably.

Example:

1. An Elasticsearch refresh invalidates the request cache.
2. The application cache still retains the old entry for 60 more seconds.
3. Clients keep seeing stale results even though Elasticsearch already holds fresh data.

Therefore, freshness SLAs must be designed end-to-end. You cannot inspect each cache's TTL in isolation.

A coherent policy might be:

- Let Elasticsearch manage query/request caches automatically.
- Application cache TTL of 10 seconds for search pages.
- Event invalidation for product details and category metadata.
- No caching for transaction-critical endpoints.

Exact numbers depend on update rates and product requirements.

## 27. Spring Data Elasticsearch: structuring queries for the query cache

Spring Data Elasticsearch needs no special annotation to enable the query cache per filter. What matters is building queries with proper filter-context semantics.

Example `NativeQuery`:

```java
import org.springframework.data.elasticsearch.client.elc.NativeQuery;
import org.springframework.data.elasticsearch.core.query.Query;

Query query = NativeQuery.builder()
    .withQuery(q -> q.bool(b -> b
        .must(m -> m.multiMatch(mm -> mm
            .query("wireless mouse")
            .fields("name^3", "description")
        ))
        .filter(f -> f.term(t -> t
            .field("tenantId")
            .value("tenant-42")
        ))
        .filter(f -> f.term(t -> t
            .field("status")
            .value("ACTIVE")
        ))
    ))
    .build();
```

`must` handles full-text scoring; tenant/status constraints sit in filter context. Elasticsearch decides whether to cache filters based on workload and heuristics. Do not build a separate Java query cache for individual term filters.

### Query cache is not the `@Cacheable` API

Spring's `@Cacheable` caches method results at the application layer. It does not toggle Elasticsearch's query cache. Similarly, setting `request_cache=true` does not control the query cache.

## 28. Spring Data Elasticsearch: request cache for searches

When caching aggregation/search requests in Elasticsearch is needed, you can pass the request cache option via the Search API. REST example:

```http
POST /products/_search?request_cache=true
Content-Type: application/json

{
  "size": 0,
  "query": {
    "term": {
      "tenantId": "tenant-42"
    }
  },
  "aggs": {
    "by_status": {
      "terms": {
        "field": "status"
      }
    }
  }
}
```

With the Elasticsearch Java API Client, search requests offer a `requestCache` option in corresponding client versions. Spring Data Elasticsearch may expose configuration via `Query`/operations or allow calling the client directly; exact APIs and overloads vary by version. Consult your project dependency's Javadoc instead of assuming a builder method exists across all versions.

If calling via `ElasticsearchOperations.search(...)`, verify that the actual transport request includes the request cache option before relying on it in production. For aggregation-only queries, `size: 0` is usually the important first step.

## 29. Spring Cache with Caffeine or Redis

Applications can enable Spring Cache:

```java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Then configure a `CacheManager` with a provider. Conceptual Caffeine example:

```java
@Bean
CacheManager cacheManager() {
    CaffeineCacheManager manager = new CaffeineCacheManager("product-search");
    manager.setCaffeine(Caffeine.newBuilder()
        .maximumSize(10_000)
        .expireAfterWrite(Duration.ofSeconds(20))
        .recordStats());
    return manager;
}
```

This illustrates a local in-JVM cache. Each application instance maintains its own cache; after one instance updates data, other instances may hold stale entries until TTL expires or they receive explicit invalidation.

Redis fits when multiple instances must share a cache. However, Redis requires designing key namespaces, TTLs, serialization, eviction, and network/credential security. A shared cache does not solve consistency by itself; invalidation is still required.

## 30. Cache result DTOs, not arbitrary objects

Cache immutable DTOs designed specifically for the API:

```java
public record ProductSearchItem(
    String id,
    String name,
    double price,
    String categoryName) {
}

public record ProductSearchPage(
    List<ProductSearchItem> items,
    long total,
    int page,
    int size) {
}
```

DTOs keep cache serialization stable and avoid retaining objects with live resources, lazy state, or unneeded internal metadata.

Never cache raw `SearchHits`, client response objects, or mutable entities without understanding their lifecycle and serialization. When API schemas change, version keys or cache names to avoid reading incompatible legacy entries.

## 31. Measuring performance of each cache layer

To see which cache actually helps, measure each layer separately:

| Layer | Metrics to monitor |
|---|---|
| Query cache | hit/miss, memory size, cache size, evictions per node/index |
| Request cache | hit/miss, memory size, evictions, refresh frequency |
| Application cache | hit/miss, eviction, load latency, TTL expiry, entry count, memory |
| Search service | p50/p95/p99 latency, Elasticsearch calls, result size, timeouts |
| Cluster | CPU, heap, GC, search thread pool, indexing pressure, disk I/O |

### Controlled benchmarking

A simple measurement workflow:

1. Run queries with cold caches and record latency.
2. Repeat the same queries multiple times to observe cache warm-up.
3. Change one filter to test cache reuse.
4. Write a document and observe refresh/invalidation impact.
5. Run the same request with `request_cache=true` and `false`.
6. Measure application cache hits and misses separately.
7. Compare p95/p99, CPU, heap, and write throughput.

Benchmark on production-like data, shard counts, replicas, and workloads. Avoid drawing conclusions from a single run or an isolated cache hit.

## 32. When should you avoid caching?

Not all data belongs in a cache:

- Highly personalized results whose keys are hard to model safely.
- Data requiring latest transactional state for decisions.
- High-variance queries that rarely repeat.
- Sensitive responses that cannot be safely scope-partitioned.
- Results costing more to store/serialize than recompute, or adding heavy memory pressure.
- Rarely called endpoints that Elasticsearch already serves fast enough.

Caching introduces another stateful layer to operate. Without a healthy hit ratio or meaningful latency gain, do not add a cache just because you can.

## 33. Common mistakes

### Thinking the query cache stores entire responses

The query cache stores per-segment filter results; the request cache stores shard-level search results. The application cache stores DTOs/responses in the application tier.

### Moving full-text queries into filter to force caching

This alters scoring and relevance. Put only non-scoring conditions into filter context.

### Assuming every filter is guaranteed to be cached

Elasticsearch uses heuristics and cache budgets. Non-repeating filters or ineligible segments may skip caching.

### Assuming the request cache always caches all hits

By default, the request cache targets `size: 0` searches. Requests returning hits need explicit opt-in and still must meet caching rules.

### Forgetting request cache invalidation on refresh

Continuously written indexes can negate request cache benefits. Read refresh stats alongside cache hit ratios.

### Enabling `request_cache=true` for every query

Nearly unique requests only create cache churn. Enable only for repeated workloads with measured benefit.

### Missing tenant or role in application cache keys

This can serve another tenant's or user's data. Include every scope affecting results in keys and always authorize before consulting cache.

### Long TTLs without invalidation

Stale data can outlive SLAs. Align TTLs with freshness and evict via events where appropriate.

### Measuring only hit ratio

A high hit ratio does not guarantee good latency or efficient memory use. Measure p95/p99, CPU, heap, refreshes, and evictions.

### Multi-layer caching without defining end-to-end freshness

The application cache can retain stale entries after Elasticsearch's request cache has invalidated. Define an overall SLA and invalidation chain.

## 34. Process for selecting caching for a use case

When optimizing a Spring Data Elasticsearch endpoint, follow this order:

1. Measure current latency and identify what is expensive: query, aggregation, fetch, network, or DTO mapping.
2. Verify whether the query uses filter context appropriately to benefit from the query cache.
3. If aggregation-only, set `size: 0` and evaluate the request cache.
4. Check refresh frequency; will the request cache invalidate before reuse?
5. If multiple application requests repeat the exact same response, consider an application cache.
6. Design keys with tenant, authorization scope, filters, sort, page, locale, and projection version.
7. Set TTLs per freshness SLA alongside event/explicit invalidation.
8. Handle cache stampedes and limit cache-miss concurrency.
9. Measure hits/misses, evictions, memory, and latency per layer separately.
10. Remove caches that yield no measurable gain or add unnecessary complexity.

## 35. Conclusion

The query cache, request cache, and application cache solve three distinct problems. The query cache reuses filter-context results per segment; the request cache reuses shard-level search results, defaulting most usefully to `size: 0` requests like aggregations; and the application cache stores DTOs or business results in the application tier to bypass Elasticsearch calls.

The query cache and request cache are managed by Elasticsearch, where refreshes and segment lifecycles directly govern reuse. The application cache relies on keys, TTLs, and invalidation designed by the application; keys must reflect tenant, permissions, filters, and everything influencing responses. In Spring Data Elasticsearch, use `bool.filter` for non-scoring conditions, `size: 0` for aggregation-only requests, selective request caching, and bounded DTO caching in services when workloads repeat. Always evaluate hit ratios alongside latency, memory, evictions, and freshness; never enable caches on the assumption that more caching automatically means faster.

## References

- [Elasticsearch – Node query cache](https://www.elastic.co/docs/reference/elasticsearch/configuration-reference/node-query-cache-settings)
- [Elasticsearch – Shard request cache](https://www.elastic.co/docs/reference/elasticsearch/rest-apis/shard-request-cache)
- [Elasticsearch – Query and filter context](https://www.elastic.co/docs/reference/query-languages/query-dsl/query-filter-context)
- [Elasticsearch – Search API (`request_cache`)](https://www.elastic.co/docs/api/doc/elasticsearch/operation/operation-search)
- [Elasticsearch – Index settings](https://www.elastic.co/docs/reference/elasticsearch/index-settings/index-modules)
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Data Elasticsearch – NativeQuery and operations](https://docs.spring.io/spring-data/elasticsearch/reference/elasticsearch/template.html)
- [Caffeine – User guide](https://github.com/ben-manes/caffeine/wiki)
