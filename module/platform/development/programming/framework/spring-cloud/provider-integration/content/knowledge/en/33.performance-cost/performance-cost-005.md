# Pagination, Caching, and Reducing Service Calls

## Learning objectives

In the **SPRING_CLOUD_PROVIDER_INTEGRATION** module, Spring Boot connects to databases, object storage, messaging, and managed services on AWS, Azure, and Google Cloud. Every database or remote service call carries costs: network latency, serialization, connections, compute, quotas, and potential failures.

This lesson focuses on three techniques that reduce those costs while preserving data semantics:

1. Choosing offset pagination, cursor pagination, or keyset scrolling based on datastore characteristics and how users browse data.
2. Using Spring Data `Page`, `Slice`, `Window`, and continuation-token APIs to read large datasets incrementally.
3. Using the Spring Cache abstraction, Caffeine, and Redis-compatible managed caches with cache-aside, TTL, and invalidation.
4. Eliminating N+1 queries through projections, batch queries, bulk APIs, and request aggregation.
5. Reducing duplicate calls with request coalescing, caching, and deduplication.
6. Reusing HTTP/Redis clients and connection pools; setting timeouts, concurrency limits, and controlled retries.
7. Measuring cache hit ratio, query count, latency, payload size, service call count, and cost before/after optimization.
8. Preserving tenant boundaries, access control, sensitive data protection, and freshness when caching or paginating.

## 1. Why do pagination, caching, and call reduction matter?

### 1.1. A single request can fan out into many backend calls

An API fetching an order list can trigger a chain of work:

~~~mermaid
flowchart TD
    USER["Client request"] --> API["Spring Boot controller"]
    API --> AUTH["Resolve tenant and permissions"]
    AUTH --> DB["Query orders"]
    DB --> CUSTOMER["Load customer for each order"]
    DB --> ASSET["Load asset for each order"]
    API --> CACHE["Read/write cache"]
    API --> CLOUD["Call managed service"]
    CUSTOMER --> RESP["Build response"]
    ASSET --> RESP
    CACHE --> RESP
    CLOUD --> RESP
    RESP --> USER
~~~

If a page has 30 orders and the service fetches customer and asset records individually per order, a single request can generate dozens or hundreds of queries. If a user jumps to page 20 with a large offset, the database may have to skip many records. If the same catalog is read repeatedly, the application keeps querying the database even though the data barely changes.

Three techniques address three distinct causes:

- **Pagination:** limits how much data is read and transferred at once.
- **Caching:** avoids re-reading data that can already be reused.
- **Batching/aggregation:** replaces many small calls with fewer larger calls.

### 1.2. Optimization goals must be measurable

Do not optimize merely to reduce lines of code or query logs. Before changing anything, measure:

| Metric | Meaning |
| --- | --- |
| Request latency p50/p95/p99 | How long users actually wait |
| Database query count/request | Average queries per API call |
| Rows scanned / rows returned | Degree of over-reading |
| Cache hit ratio | Fraction of requests served from cache |
| Cache miss latency | Cost when falling back to the origin |
| Remote calls/request | Number of calls to external services |
| Payload bytes | Data transferred over the network |
| Connection pool wait | Time spent waiting for a connection |
| Error/retry rate | Dependency reliability and failure impact |
| Cost per request | Equivalent database, cache, network, and compute cost |

A technique may cut query count while increasing memory, stale data, or cache cost. Evaluate latency, correctness, and total cost together.

## 2. Data pagination

### 2.1. Offset pagination

Offset pagination uses a page number and page size. Example:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
ORDER BY created_at DESC, id DESC
LIMIT :pageSize OFFSET :offset;
~~~

With page size 20:

- First page: LIMIT 20 OFFSET 0.
- Second page: LIMIT 20 OFFSET 20.
- Third page: LIMIT 20 OFFSET 40.

Advantages:
- Easy to implement and understand.
- Users can jump to an arbitrary page.
- Fits small admin tables or bounded datasets.

Disadvantages:
- As offset grows, the database often processes or skips many rows before returning the requested page.
- Inserts/deletes between two requests can shift rows, causing duplicates or skipped records as users page through.
- Total page count may require an extra count query.
- Allowing overly large page sizes can generate heavy responses and consume excessive memory.

Offset works when users need page numbers and datasets are modest. Do not default to it for infinite scroll or exporting millions of records.

### 2.2. Page, Slice, and List in Spring Data

Spring Data supports several return types:

| Type | Metadata | Typical cost | When to use |
| --- | --- | --- | --- |
| Page<T> | Content, page number, total elements, total pages | May require an extra count query | UI must display total pages |
| Slice<T> | Content and hasNext | Usually fetches one extra element to check if more exist | Next/Previous or infinite scroll |
| List<T> | Result list only | No Page metadata overhead; still bound query size | API builds a simple custom response |
| Window<T> | A window of results and scroll position | Supports offset/keyset scrolling depending on store | Traversing large datasets window by window |

`Page` is useful when the total record count is genuinely needed by the UI. Count queries can be expensive on large tables or queries with complex joins/filters. When only a “Next” button is needed, `Slice` is usually sufficient.

Repository example:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Page<Order> findPageByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);

    Slice<Order> findSliceByTenantIdAndStatus(
            String tenantId,
            OrderStatus status,
            Pageable pageable);
}
~~~

### 2.3. Creating Pageable with stable sorting

Example service accepting page and size from an API:

~~~java
public Page<OrderSummary> listOrders(
        String tenantId,
        OrderStatus status,
        int requestedPage,
        int requestedSize) {

    int page = Math.max(requestedPage, 0);
    int size = Math.max(1, Math.min(requestedSize, 100));

    Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                    Sort.Order.desc("createdAt"),
                    Sort.Order.desc("id")));

    return orderRepository
            .findPageByTenantIdAndStatus(tenantId, status, pageable)
            .map(orderMapper::toSummary);
}
~~~

Key points:

- `PageRequest` uses a 0-based page index.
- Always clamp page size on the server; never trust client-supplied values.
- Consider capping page index or requiring a cursor when clients paginate deeply; a huge page number still creates a huge offset.
- Sorting must be deterministic. If `createdAt` can collide, append a unique key such as `id` as a tie-breaker.
- Never pass client-supplied column names directly into `Sort` without checking an allowlist.
- Tenant filters must come from the security context or authenticated principal, not from an arbitrary tenant ID in a query string.
- Use projections/DTOs to avoid serializing full entities and lazy relations.

### 2.4. When does the count query become a bottleneck?

A `Page<T>` needs the total element count. Spring Data may generate a query like:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status;
~~~

When conditions include multiple joins, `DISTINCT`, or complex filters, counting can take substantial time even if fetching 20 rows is fast.

Three options:

1. Use `Slice<T>` if you only need to know whether a next page exists.
2. Use `List<T>` with `Pageable` if the service only needs bounded data and manages metadata itself.
3. Maintain a separate aggregate/count if total counts are displayed frequently and asynchronous updates are acceptable.

Do not cache total counts too long if business rules require exact numbers right after every change. When eventual consistency is acceptable, clearly surface the freshness timestamp.

### 2.5. Keyset pagination (seek pagination)

Keyset pagination uses the values of the last record from the previous page to locate the next slice. Instead of skipping `OFFSET` rows, the query applies a predicate on the sort keys.

Suppose we sort descending by `created_at`, then by `id`:

~~~sql
SELECT id, customer_id, status, created_at
FROM orders
WHERE tenant_id = :tenantId
  AND status = :status
  AND (
       created_at < :lastCreatedAt
       OR (
           created_at = :lastCreatedAt
           AND id < :lastId
       )
  )
ORDER BY created_at DESC, id DESC
LIMIT :pageSizePlusOne;
~~~

The first page has no cursor, so omit the keyset predicate and fetch `pageSize + 1` rows. Subsequent pages use the `created_at` and `id` of the last record from the prior page.

Fetching one extra row tells us whether another page exists:
- If the query returns more than `pageSize`, trim the extra item and return `hasNext = true`.
- If there is no extra item, this is the last page.

Keyset suits large datasets, infinite scroll, and sequential exports. It does not support jumping arbitrarily to page 500 like offset pagination.

### 2.6. Conditions for keyset pagination to work properly

- Sorting must define a deterministic total order, ideally ending with the primary key.
- Fields used in the cursor should be non-null.
- An index matching filter and sort must exist, such as `(tenant_id, status, created_at DESC, id DESC)`.
- The cursor must carry every required sort key.
- Do not change filters or sort order between pages while reusing an old cursor.
- If sort keys can mutate during traversal, records may shift across the cursor; pick immutable fields or use an appropriate snapshot/version boundary.

Keyset does not automatically create a consistent snapshot across the entire traversal. If business rules require a fixed snapshot, use a datastore-supported transaction/snapshot or watermark/version boundary.

### 2.7. Keyset scrolling with Spring Data

Spring Data Commons provides `Window<T>` and `ScrollPosition`. Datastore modules supporting scrolling can implement offset or keyset filtering.

Example with Spring Data JPA:

~~~java
public interface OrderRepository
        extends JpaRepository<Order, UUID> {

    Window<Order>
    findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
            String tenantId,
            OrderStatus status,
            ScrollPosition position);
}
~~~

Reading the first window and obtaining the next position:

~~~java
ScrollPosition position = ScrollPosition.keyset();

Window<Order> window =
        orderRepository
                .findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                        tenantId,
                        OrderStatus.PAID,
                        position);

if (!window.isEmpty() && !window.isLast()) {
    ScrollPosition nextPosition =
            window.positionAt(window.size() - 1);

    Window<Order> nextWindow =
            orderRepository
                    .findFirst50ByTenantIdAndStatusOrderByCreatedAtDescIdDesc(
                            tenantId,
                            OrderStatus.PAID,
                            nextPosition);
}
~~~

In this example, `createdAt` and `id` establish a stable ordering. Keyset fields must be mapped and returned in results; if using projections, include the necessary sort fields. Verify your datastore module and Spring Data version, as not every query or store supports `Window` and keyset scrolling.

### 2.8. Cursor pagination in APIs

For public APIs, avoid forcing clients to send raw sort keys or SQL conditions directly. Return an opaque cursor:

~~~json
{
  "items": [
    {
      "id": "ord-1001",
      "status": "PAID"
    }
  ],
  "nextCursor": "eyJ2IjoxLCJrZXkiOi4uLn0.signature",
  "hasMore": true
}
~~~

A cursor can contain:
- Cursor format version.
- Sort keys of the last element.
- Filter and sort fingerprint.
- Authenticated tenant/partition scope.
- Expiration timestamp if needed.

Sign cursors with HMAC or an equivalent mechanism so clients cannot tamper with keys or filters. Base64URL is encoding, not encryption. If a cursor holds sensitive data, encrypt it or store state server-side and return only a random token.

When receiving a cursor:
1. Verify signature and version.
2. Verify the cursor belongs to the current tenant/principal.
3. Verify current filters/sorts match the fingerprint.
4. Enforce a bounded page size.
5. Apply the datastore's native keyset/cursor.
6. Return a new cursor if more data remains.

### 2.9. Native pagination in managed datastores

Not every service uses `OFFSET`:

| Service | Continuation mechanism | Notes |
| --- | --- | --- |
| SQL database / Cloud SQL | LIMIT/OFFSET or keyset predicate | Deep offsets can cost heavy I/O; use indexes |
| Firestore Native | `orderBy`, `limit`, `startAfter`/document snapshot | Cursor must match the same query and ordering |
| Amazon DynamoDB | `LastEvaluatedKey` → `ExclusiveStartKey` | Continue until no key remains; filters can yield empty pages that still return a key |
| Azure Cosmos DB | Continuation token | Items per page may vary; continue until token is exhausted |
| BigQuery REST API | `pageToken` and `maxResults` | Token is bound to the corresponding query/list result |

Firestore Java example:

~~~java
Query firstPage = firestore.collection("orders")
        .whereEqualTo("tenantId", tenantId)
        .orderBy("createdAt", Query.Direction.DESCENDING)
        .orderBy(FieldPath.documentId(), Query.Direction.DESCENDING)
        .limit(50);

ApiFuture<QuerySnapshot> firstFuture = firstPage.get();
QuerySnapshot firstSnapshot = firstFuture.get();

if (!firstSnapshot.isEmpty()) {
    DocumentSnapshot lastDocument =
            firstSnapshot.getDocuments()
                    .get(firstSnapshot.size() - 1);

    Query nextPage = firestore.collection("orders")
            .whereEqualTo("tenantId", tenantId)
            .orderBy("createdAt", Query.Direction.DESCENDING)
            .orderBy(FieldPath.documentId(), Query.Direction.DESCENDING)
            .startAfter(lastDocument)
            .limit(50);
}
~~~

This example illustrates a native cursor. In a WebFlux application, do not call `get()` synchronously on an event loop; use the appropriate async/reactive API or offload blocking calls to a scheduler. The query may need a composite index on `tenantId`, `createdAt`, and document ID; check for index errors and deploy indexes before release.

With DynamoDB, a page may return few or zero items because `FilterExpression` is applied after reading; you must still continue as long as `LastEvaluatedKey` is present. With Cosmos DB, keep paging with the continuation token until it is null/empty. Never decode or fabricate provider tokens yourself.

### 2.10. Pagination for exports and batch processing

Exporting an entire dataset differs from serving one UI page. Never build a `List` holding millions of entities on the heap.

Options:
- Use cursors/keyset to read batch by batch and stream out to files/object storage.
- Use `Stream<T>` if the store supports cursors; always close streams with try-with-resources.
- Use a batch job or Dataflow/ETL for very large datasets.
- Persist a checkpoint/cursor after each batch so jobs can resume.
- Bound worker count and batch size to avoid overloading the database.

If a batch job may be re-run, use idempotency keys or batch/version-scoped output paths to prevent duplicate writes.

## 3. Caching

### 3.1. A cache is a time-bounded copy

A cache stores a copy of data in a faster location than the source of truth. Caching fits best when data is:
- Read repeatedly.
- Changed less often than it is read.
- Expensive to query or fetch over the network.
- Tolerant of a clearly defined freshness window.

Do not cache merely because a query is slow. Check indexes, query plans, projections, and call counts first. Caching a bad or unbounded query only masks the problem and complicates invalidation.

### 3.2. Cache layers

~~~mermaid
flowchart TD
    APP["Spring Boot instance"] --> L1["L1 local cache<br/>Caffeine"]
    L1 -->|"miss"| L2["L2 shared cache<br/>Redis-compatible"]
    L2 -->|"miss"| SOURCE["Database / remote service"]
    SOURCE --> L2
    L2 --> L1
    L1 --> APP
    OTHER["Other application instances"] --> L2
~~~

- **L1 local cache:** lives inside the JVM with ultra-low latency and no network hop. Each instance keeps its own copy and copies can diverge.
- **L2 shared cache:** distributed cache such as a Redis-compatible managed service. Multiple instances share one keyspace; incurs a network hop and requires connection management.
- **Source of truth:** the primary database or origin service. Caches may be evicted, expire, or lose data, and the application must still recover cleanly from the source.

You can combine L1 and L2. In that case, L1 should have a shorter TTL and either an invalidation/broadcast mechanism or a clearly accepted stale window.

### 3.3. Cache-aside (lazy loading)

Cache-aside is the standard pattern:

1. The application checks the cache by key.
2. On a hit, return the cached value.
3. On a miss, read from the source of truth.
4. Write the result into the cache with a TTL.
5. When origin data changes, evict or update the affected keys.

Advantages:
- Caches only data that is actually requested.
- An empty cache after restart never loses source data.
- Easy to layer onto existing databases or remote services.

Disadvantages:
- A cache miss incurs both a source read and a cache write.
- Cache entries can go stale if the source mutates without invalidation.
- Many concurrent misses on the same key can hit the source simultaneously, causing a cache stampede.

### 3.4. Spring Cache abstraction

Spring Framework provides an abstraction so services do not couple directly to Redis, Caffeine, or a specific provider. Spring Boot auto-configures a `CacheManager` when the corresponding provider is added.

Base dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-cache</artifactId>
</dependency>
~~~

Enable caching in configuration:

~~~java
@Configuration
@EnableCaching
public class CacheConfiguration {
}
~~~

You do not have to place `@EnableCaching` directly on the main application class if you want caching optional in tests or profiles; enable it in a dedicated configuration class.

Primary annotations:

| Annotation | Effect |
| --- | --- |
| `Cacheable` | Checks cache first; on miss, runs method and stores result |
| `CacheEvict` | Removes entry after operation |
| `CachePut` | Always executes method and updates cache with result |
| `Caching` | Combines multiple cache operations |
| `CacheConfig` | Shares cache configuration at the class level |

### 3.5. Cache-aside example with @Cacheable

~~~java
@Service
public class ProductReadService {

    private final ProductRepository products;

    public ProductReadService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(
            cacheNames = "productById",
            key = "'tenant:' + #tenantId + ':product:' + #productId")
    public ProductView getProduct(
            String tenantId, UUID productId) {

        return products
                .findByTenantIdAndId(tenantId, productId)
                .map(ProductView::from)
                .orElseThrow(ProductNotFoundException::new);
    }
}
~~~

The key includes both tenant ID and product ID. Using only product ID could cause one tenant to accidentally receive another tenant's cached data if IDs are not globally unique.

If results also depend on locale, currency, permissions, or feature flags, those values must also be part of the cache key or separated into scoped caches.

Annotation-based caching works via Spring proxies. If a method in the same class directly invokes a `@Cacheable` method, self-invocation bypasses the proxy and cache advice will not run. Place cached methods in a separate bean or invoke through the bean proxy.

### 3.6. Evicting or updating cache on writes

Example service updating the data source:

~~~java
@Service
public class ProductCommandService {

    private final ProductRepository products;

    public ProductCommandService(ProductRepository products) {
        this.products = products;
    }

    @Transactional
    public Product updateProduct(
            String tenantId, UUID productId, ProductUpdate update) {

        Product product = products
                .findByTenantIdAndId(tenantId, productId)
                .orElseThrow(ProductNotFoundException::new);

        product.apply(update);
        return products.save(product);
    }
}
~~~

You can apply `@CacheEvict` at an appropriate boundary, but watch transactions: evicting before the database transaction commits lets another request read old data and re-populate the cache with stale values. For data requiring ordering guarantees, publish an event after commit:

~~~java
public record ProductChanged(String tenantId, UUID productId) {
}

@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void updateProduct(
            String tenantId, UUID productId, ProductUpdate update) {

        Product product = products
                .findByTenantIdAndId(tenantId, productId)
                .orElseThrow(ProductNotFoundException::new);

        product.apply(update);
        products.save(product);

        events.publishEvent(new ProductChanged(tenantId, productId));
    }
}
~~~

Listener evicting the cache after transaction commit:

~~~java
@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void invalidate(ProductChanged event) {
        Cache cache = cacheManager.getCache("productById");

        if (cache != null) {
            cache.evict(
                    "tenant:" + event.tenantId()
                            + ":product:" + event.productId());
        }
    }
}
~~~

The event listener here runs within the same application process. If using an L1 local cache across multiple instances, broadcast invalidation or rely on short TTLs; an in-process event on one instance will not evict caches on other instances. For durable invalidation requirements, write an outbox record in the transaction and publish a message to instances after commit.

### 3.7. TTL and cache configuration

TTL (time to live) sets how long an entry remains in the cache. Base TTL on freshness SLAs and data mutation frequency.

Example using the Redis cache provider in Spring Boot:

~~~yaml
spring:
  cache:
    type: redis
    cache-names:
      - productById
      - productList
      - referenceData
    redis:
      time-to-live: 5m
      use-key-prefix: true
~~~

Key prefixes isolate identical keys across cache regions. Do not disable prefixes if creating multiple caches that might share keys.

When individual caches need distinct TTLs, configure `RedisCacheManagerBuilderCustomizer`:

~~~java
import java.time.Duration;

import org.springframework.boot.cache.autoconfigure.RedisCacheManagerBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Configuration
public class RedisCacheTtlConfiguration {

    @Bean
    RedisCacheManagerBuilderCustomizer cacheTtlCustomizer() {
        return builder -> builder
                .withCacheConfiguration(
                        "productById",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofMinutes(5)))
                .withCacheConfiguration(
                        "referenceData",
                        RedisCacheConfiguration.defaultCacheConfig()
                                .entryTtl(Duration.ofHours(1)));
    }
}
~~~

The example assumes Spring Boot has auto-configured the Redis cache provider and Redis connection factory. For a Caffeine local cache, configure the provider and size/TTL bounds:

~~~yaml
spring:
  cache:
    type: caffeine
    caffeine:
      spec: maximumSize=10000,expireAfterWrite=60s
~~~

A simple concurrent-map-backed cache provider suits quick experiments, but is not a production cache with full TTL, eviction, and shared state.

### 3.8. Choosing managed caches by cloud provider

The Spring Cache abstraction keeps business code independent of providers. Cache infrastructure can be:

| Cloud | Common managed cache | Notes |
| --- | --- | --- |
| AWS | Amazon ElastiCache for Valkey/Redis OSS | Choose compatible engine, topology, failover, and client |
| Azure | Azure Managed Redis | Microsoft's currently recommended service for new workloads; check lifecycle roadmap for existing Azure Cache for Redis |
| Google Cloud | Memorystore for Redis or Valkey | Choose tier, networking, failover, and runtime connectivity |

Regardless of service, a cache remains an evictable copy that can be lost during failover. The primary database or origin service must remain the authoritative store.

### 3.9. TTL, cache stampedes, and thundering herds

Suppose a popular key expires just as 500 requests arrive. If all miss, all 500 can hit the database and rewrite the cache simultaneously. This is a cache stampede.

Mitigations:

- `@Cacheable(sync = true)` synchronizes computation of the same key if supported by the cache provider. Check provider and annotation limits when combining `sync`.
- Add random jitter to TTLs so keys do not expire simultaneously.
- Pre-warm popular keys before peak traffic.
- Use stale-while-revalidate: serve a slightly stale value within an allowed window while refreshing in the background.
- Bound concurrent origin calls using a semaphore/bulkhead.
- For severe cross-instance stampedes, use a distributed lock with a lease and fencing/versioning only if truly needed; avoid turning the cache into a complex lock manager.

Never use locks without timeouts. If a lock-holding worker dies, other requests could hang or wait indefinitely.

### 3.10. Negative caching

Frequently queried missing keys can generate repeated origin lookups. You can cache “not found” results briefly if semantics permit.

Distinguish clearly between:
- Truly not found.
- Unauthorized request.
- Timeout or database error.
- Cache miss.

Never cache transient errors as if data did not exist. Caching negative results too long can also cause newly created records to return 404 until the TTL expires.

### 3.11. Caching lists and pages

You can cache a page of results, provided the key captures every parameter affecting content:

- Tenant/principal scope.
- Filters and search queries.
- Sort field/direction.
- Page size.
- Offset or cursor.
- Locale/currency if responses vary by them.
- API/schema version when formats evolve.

Conceptual key example:

~~~text
orders:list:v2:tenant-42:status-PAID:sort-created-desc:size-20:cursor-abc
~~~

First-page caches often achieve high hit ratios; deeper pages are rarely accessed. Do not cache every possible page unboundedly. Set TTLs, bound entry counts, and monitor memory.

Cursors can embed data state. Never build cache keys using unverified cursors or cursors belonging to another tenant. Even with signed cursor tokens, still enforce current request permissions.

### 3.12. When the cache fails

The application should decide whether the cache is a hard dependency:

- If the cache is purely an accelerator, a cache timeout can be treated as a miss and fall back to the origin under concurrency limits.
- If the cache holds critical session/coordination state, design dedicated fallback behavior.
- Never let a cache outage unleash unbounded traffic onto the database.
- Enforce short timeouts, circuit breakers, and rate limits for both cache and origin.
- Track cache error metrics separately from cache misses.

Cache failures must never silently serve wrong data or trigger cascading database overload.

### 3.13. Caching with reactive return types

Spring Cache adapts to `CompletableFuture`, `Mono`, and `Flux`. For `Mono`, the emitted value is cached on completion. For `Flux`, Spring collects all elements into a `List` before caching. Thus, annotation-based caching on `Flux` is unsuitable for very large streams, infinite streams, or backpressure-sensitive pipelines; cache individual pages/batches or use a purpose-built reactive caching strategy.

## 4. Reducing database and remote service calls

### 4.1. Eliminating N+1 queries

N+1 happens when fetching N records and then issuing one extra query per record to load a relation.

Anti-pattern:

~~~java
List<Order> orders = orderRepository.findByTenantId(tenantId);

for (Order order : orders) {
    Customer customer = customerRepository
            .findById(order.getCustomerId())
            .orElseThrow();
    // Build response.
}
~~~

With 100 orders, this code can issue 1 query for orders plus 100 queries for customers.

Fixes:
- Use `JOIN FETCH` or `EntityGraph` when relationships fit.
- Use projections/DTOs to select only needed fields.
- Collect IDs and run a single `WHERE id IN (...)` query.
- Use ORM batch fetching where supported.
- Pick sensible batch sizes and chunk batches when exceeding database/API limits.

Bulk lookup example:

~~~java
List<UUID> customerIds = orders.stream()
        .map(Order::getCustomerId)
        .distinct()
        .toList();

Map<UUID, CustomerSummary> customers =
        customerRepository.findAllById(customerIds)
                .stream()
                .collect(Collectors.toMap(
                        Customer::getId,
                        CustomerSummary::from));
~~~

Then join orders and customers in memory. This cuts query count, though you must still bound `IN`-list sizes and select only necessary columns.

### 4.2. Caution with fetch joins alongside pagination

Using a collection fetch join with `Pageable` can multiply rows per root entity and prevent the database/ORM from applying `LIMIT` accurately. In some cases Hibernate reads many rows and paginates in memory.

A safer strategy:

1. Query a page of root entity IDs with deterministic sorting.
2. Batch-fetch the full entities/relations for those IDs.
3. Restore ordering from the initial ID list.
4. Map to DTOs.

For large collections, consider separate queries or projections instead of loading the entire object graph.

### 4.3. Bulk APIs instead of per-item calls

If the target service supports batching, send one request for many keys instead of one request per key.

Internal API example:

~~~http
POST /customers:batchGet
Content-Type: application/json

{
  "ids": [
    "cus-1001",
    "cus-1002",
    "cus-1003"
  ]
}
~~~

The service returns a map or matching list of customers. Callers should:
- Deduplicate IDs before sending.
- Split batches according to provider limits.
- Handle missing elements.
- Handle partial failures when batch APIs can partially succeed.
- Preserve idempotency on batch writes.

Cloud services provide dedicated bulk APIs such as DynamoDB `BatchGet`/`BatchWrite`, Firestore `getAll` or batch writes, and batch/stream APIs on other data services. Read item-count, payload, and retry limits for each API.

### 4.4. API aggregation and BFF

A screen may require order, customer, asset, and pricing data. If the client calls four services sequentially, total latency approaches the sum of all four calls.

An aggregation API / BFF can:
- Accept one client request.
- Call the required backend services.
- Batch duplicate keys.
- Return only fields needed for that screen.
- Enforce timeouts and concurrency limits.

Aggregation reduces client round-trips, but does not automatically reduce backend calls if it still calls each service one by one. True call reduction comes from batch APIs, caching, or reshaping data ownership/read models.

### 4.5. Request coalescing and deduplication

Within a single request, multiple components may ask for the same customer or configuration. Deduplicate keys and fetch from the source once.

Across concurrent requests, multiple callers may miss the cache for the same key simultaneously. `@Cacheable(sync = true)` provides single-flight behavior on supported providers. For custom logic, maintain an in-flight future map keyed by request key and remove entries once futures complete.

Rules:
- Coalesce on the complete key, including tenant/security scope.
- Never share results across users with different permissions.
- Never retain failed futures in the map permanently.
- Enforce timeouts and cleanup.
- Never use a single global lock across all keys.

### 4.6. Reusing HTTP clients and connection pools

Do not construct a new `RestClient`, `WebClient`, or SDK client per request. Register shared beans and reuse connection pools.

Example configuring `WebClient` via Spring-managed builder:

~~~java
@Configuration
public class RemoteClientConfiguration {

    @Bean
    WebClient catalogWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("https://catalog.internal")
                .build();
    }
}
~~~

Service injecting the client:

~~~java
@Service
public class CatalogClient {

    private final WebClient webClient;

    public CatalogClient(WebClient catalogWebClient) {
        this.webClient = catalogWebClient;
    }

    public Mono<ProductView> getProduct(UUID id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(ProductView.class);
    }
}
~~~

In production, configure connection pools and timeouts on the underlying HTTP connector. Monitor:
- Max connections and pending acquires.
- Connect timeout.
- Response/read timeout.
- Keep-alive.
- DNS resolution.
- TLS handshakes.
- Connection reuse and pool saturation.

Co-locate applications and managed services in matching regions/network paths to avoid cross-region latency. Never open and close a connection per call.

### 4.7. HTTP caching and conditional requests

If the target service supports `ETag`, clients can send `If-None-Match`. When unchanged, the server replies `304 Not Modified` without resending the response body.

Conditional requests save bandwidth and serialization, though they still incur a network round-trip. To eliminate calls altogether, combine with local/shared caches and TTLs.

Never use `ETag` as a substitute for authorization or business versioning. HTTP response caching must honor `Cache-Control`, `Vary`, user scope, and sensitivity rules.

### 4.8. Bounded parallelization

For independent service calls, parallel execution reduces latency relative to sequential calls. However, call counts do not drop and downstream load spikes.

Use bounded concurrency, overall timeouts, and bulkheads. Never spawn thousands of futures simultaneously for one request. When a dependency slows down, prevent it from exhausting the entire thread/connection pool.

In reactive pipelines, `Mono.zip` can combine a few independent calls with proper timeouts and fallbacks. Do not use parallelism merely to mask a chatty API that ought to be batched.

### 4.9. Retries do not reduce calls

Retries recover from transient errors, yet increase call volume. If 1,000 concurrent requests all retry three times while a dependency is failing, the system amplifies the outage.

Rules:
- Retry only transient failures such as timeouts, connection resets, or selected HTTP 5xx errors.
- Never retry validation, permission denied, or business rejection errors.
- Retry writes only when idempotent or backed by an idempotency key.
- Use exponential backoff and jitter.
- Cap retry counts and overall deadlines.
- Use circuit breakers to stop calling failing dependencies.
- Use bulkheads to isolate resources per dependency.

Spring Cloud CircuitBreaker integrates Resilience4j and other implementations. Choose the right implementation for your blocking or reactive stack.

## 5. Combining pagination and caching

### 5.1. Cache the first page, use keyset for the rest

Lists often exhibit a clear access pattern:
- Most users view only the first page.
- A smaller subset navigates deeper.
- New records usually appear at the top of the list.

A balanced strategy:
1. Cache the first page with a short TTL.
2. Use keyset cursors for subsequent pages.
3. Evict the first page when new records arrive.
4. Do not cache arbitrary cursors indefinitely.
5. Cap page size and cached entry count.

This usually beats caching the entire list or caching every offset page.

### 5.2. Caching query results by fingerprint

A query page can be keyed by a fingerprint of:
- Tenant.
- Filters.
- Sort order.
- Page size.
- Cursor/offset.
- Schema/response version.

Whenever filters or sort order change, the cache key must change. Otherwise, users may receive results from a different query.

### 5.3. Freshness and invalidation

Define freshness per data category:

| Data | Recommended strategy |
| --- | --- |
| Rarely changing catalogs | Longer TTL, background refresh |
| Product details | Short/medium TTL and evict on update |
| Pricing and inventory | Short TTL or origin read on demand |
| Permissions/roles | Short TTL, strict invalidation |
| Dashboard aggregates | Scheduled refresh TTL, display data timestamp |
| Reservation/payment state | Never rely on stale cache for transactional decisions |

For critical transactional data, caching serves read optimization only where stale reads are business-acceptable. Write/checkout decisions must always re-verify against the source of truth.

## 6. Security and correctness

### 6.1. Cache keys must never leak tenant data

Cache keys must reflect data scope. If a response depends on:
- Tenant.
- User or role.
- Locale/currency.
- Feature entitlements.
- Data residency region.

then keys or cache regions must be partitioned by those dimensions.

Never cache personalized responses under a shared global key. Never place access tokens, secrets, or PII into cache keys that might show up in monitoring/logs.

### 6.2. Serialization and schema versioning

For distributed caches:
- Cache stable DTOs rather than serializing ORM entities with lazy proxies.
- Pick serializers with explicit formats/versions.
- Avoid deserializing native Java objects from untrusted sources.
- Plan how old cache entries are handled when deploying schema changes.
- Include a version in cache names/keys for safe rollouts.

Caches hold ephemeral data; new deployments should be able to bypass old caches and reload from the source.

### 6.3. Access control and networking

Managed caches usually reside inside private networks. Configure:
- Private endpoints/VPC/VNet or private service access.
- TLS/in-transit encryption where supported and required.
- Provider authentication/ACLs or identity integration.
- Secrets stored in a secret manager.
- Least privilege and network allowlists.
- Never expose caches directly to the public Internet without controlled requirements.

### 6.4. Caches are not durable databases

Never use a cache as the sole store for:
- Payment ledgers.
- Reservation state.
- Inventory source of truth.
- Mandatory audit records.
- Unpersisted events.

Failover, eviction, flushes, restarts, or scaling operations can drop cache entries. Applications must always recover cleanly from the database or origin system.

## 7. Performance measurement and testing

### 7.1. Metrics to monitor

**Pagination**
- Average and maximum page size.
- Offset depth.
- Query latency per page/cursor.
- Count query latency.
- Rows scanned/returned.
- Invalid/expired cursor rate.

**Cache**
- Hit/miss ratio by cache name.
- Eviction and expiration counts.
- Cache operation latency/errors.
- Memory usage and key cardinality.
- Invalidation lag.
- Origin requests triggered on cache misses.

**Service calls**
- Calls/request per dependency.
- Retry counts and timeout rates.
- Connection pool wait/pending acquires.
- Batch size and partial failures.
- Circuit breaker open duration.
- Payload size and serialization time.

Do not rely on aggregate hit ratio alone. A high hit ratio with slow misses or unbounded key cardinality can still cause severe issues.

### 7.2. Distributed tracing

Instrument traces/spans for:
- Incoming HTTP requests to Spring Boot.
- Database queries.
- Cache get/set/evict operations.
- HTTP/gRPC client calls.
- Messaging publish/consume operations.
- Batch jobs or exports.

Tracing reveals which paths generate excessive calls and isolates whether latency lives in the application, network, database, or cloud provider.

### 7.3. Load testing with cold and hot caches

A load test should cover these scenarios:
1. Cold cache right after deploy/restart.
2. Warm cache under steady traffic.
3. Hot keys with heavy concurrent traffic.
4. Temporary cache provider unavailability.
5. Elevated source database latency.
6. Cache eviction or failover events.
7. Continuous data mutations while clients paginate.

Use realistic key distributions mixing popular and rare keys. Testing a 100%-hit cache does not reflect production behavior.

### 7.4. Cost evaluation

Caching adds costs:
- Instance/cluster and memory cost.
- Network traffic.
- Serialization/deserialization CPU.
- Operations, monitoring, and invalidation complexity.
- Stale data and error handling.

Batching also carries trade-offs: larger requests raise memory and per-batch processing duration; partial failures require partial retries. Size batches using provider limits and benchmarks.

Compare total cost before and after:
- How much did database reads drop?
- How much did remote calls drop?
- How much did cache infrastructure cost increase?
- How did p95/p99 latency change?
- Did stale-read or error rates increase?

## 8. Workflow for optimizing a real API

Suppose `GET /orders` has high p95 latency and triggers many database queries:

1. **Measure baseline:** trace requests, count queries, inspect execution plans and remote calls.
2. **Bound results:** enforce a max page size and deterministic sorting.
3. **Choose pagination:** `Page` if total count is required; `Slice` if only next-page is needed; keyset for large sequential traversal.
4. **Eliminate N+1:** apply projections, batch lookups, or appropriate entity graphs.
5. **Cache hot reads:** cache catalogs/customer summaries scoped by tenant and TTL.
6. **Reduce duplicate calls:** deduplicate IDs and batch service APIs.
7. **Reuse clients:** configure connection pools, timeouts, and regional placement.
8. **Protect dependencies:** apply concurrency limits, circuit breakers, and bounded retries.
9. **Verify freshness:** invalidate after commit and test across multiple instances.
10. **Re-run load tests:** compare latency, calls/request, cache hit ratio, DB load, and cost.

Never turn on caching before understanding data semantics. Never switch from offset to cursors without deterministic sorting and matching indexes.

## 9. Common pitfalls and fixes

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Deep pages are very slow | Large offset | Keyset/cursor pagination with matching sort index |
| Duplicate rows across pages | Non-unique sort or concurrent mutations | Append ID tie-breaker, use stable cursors |
| Page endpoint slow despite returning 20 rows | Expensive count query | Switch to `Slice`/`List` or optimize counting |
| Items skipped across pages | Incorrect cursor or changed filters | Bind cursors to filter/sort fingerprints |
| Memory spikes during export | Materializing full `List` | Stream/`Window`/batch with checkpoints |
| Database queries scale with row count | N+1 problem | Batch queries, projections, entity graphs |
| Cache hit returns wrong tenant's data | Cache key omits tenant/scope | Include tenant/user/role in cache key |
| Stale data after updates | Missing invalidation or excessive TTL | Evict after commit, outbox/broadcast |
| Database overloaded on cache restart | Cache stampede | Single-flight, jitter, pre-warming, concurrency caps |
| Redis connections climbing steadily | Creating clients/connections per request or idle leaks | Reuse clients, pools, and idle timeouts |
| Cache memory exhausted | Missing TTL, high key cardinality, oversized values | Enforce TTLs, eviction policies, value size caps |
| Retries amplify load when dependency fails | Unbounded retries or missing jitter | Retry budgets, backoff, circuit breakers |
| Batch API returns partial failures | Batch too large or provider item limits | Split batches, retry failed items, idempotency |
| Parallel fan-out overwhelms downstream | Unbounded concurrency | Bulkheads, semaphores, and timeouts |
| Cached page returns results for wrong filters | Cache key missing query parameters | Key by filter/sort/cursor/version |

## 10. Hands-on exercises

### Exercise A — Offset and Slice

Build an endpoint listing reservations using `Pageable`. Measure query count and latency returning `Page` vs. `Slice`. Explain the cost of the count query.

### Exercise B — Keyset pagination

Build a query ordered by `createdAt DESC, id DESC`. Implement a keyset cursor, create the matching index, and traverse at least 100,000 records. Compare latency at the start vs. end of the dataset against offset pagination.

### Exercise C — Cursor API

Design a response with `items`, `nextCursor`, and `hasMore`. Sign the cursor and verify it cannot be reused across tenants or different filters.

### Exercise D — Native continuation tokens

Practice with a service offering native cursors such as Firestore, DynamoDB, or Cosmos DB. Handle empty pages that still return a token and stop only when the token indicates the end of data.

### Exercise E — Spring Cache

Enable `@EnableCaching`, cache product details with `@Cacheable`, update inside a transaction, and evict after commit. Verify repeated reads for the same key hit the repository only once.

### Exercise F — L1 and L2 caches

Use Caffeine for L1 and a Redis-compatible cache for L2. Run two application instances, update a product, and test cross-instance invalidation.

### Exercise G — Cache stampede

Fire many concurrent requests for an uncached key. Compare no coalescing, `sync=true`, and TTL jitter. Measure database query counts.

### Exercise H — N+1 and batching

Build an endpoint loading 50 orders and their customers. Measure query count before and after switching to `findAllById` or a projection/batch query.

### Exercise I — HTTP client reuse

Register a shared `WebClient` bean with configured connection pool and timeouts. Compare against creating a new client per request; observe connection reuse and pending acquires.

### Exercise J — Resilience and cost

Simulate a slow or failing dependency. Configure timeouts, bounded retries, circuit breakers, and bulkheads. Measure calls/request, p95, and errors as load rises.

### Self-check questions

1. How does offset pagination work?
2. Why can deep offsets become expensive?
3. Why does sorting require a unique tie-breaker?
4. How does `Page` differ from `Slice` in metadata and query cost?
5. When should you use `Window<T>`?
6. Which sort keys does keyset pagination require?
7. Why should keyset sort fields be non-null?
8. How should cursor tokens bind to filters and tenants?
9. How does DynamoDB use `LastEvaluatedKey`?
10. Why can DynamoDB return an empty page while still providing a continuation key?
11. What does Firestore use `startAfter` for?
12. What role does a Cosmos DB continuation token play?
13. What are the steps of cache-aside?
14. How do Spring's `@Cacheable`, `@CacheEvict`, and `@CachePut` differ?
15. Why do cache keys need tenant ID and authorization scope?
16. What are the risks of an overly long TTL?
17. What is a cache stampede and how is it mitigated?
18. Why should eviction happen after database commit?
19. How does a local cache differ from a shared cache in consistency?
20. What is an N+1 query and how do you eliminate it?
21. When should you use a batch API?
22. Why must you avoid creating a new HTTP client per request?
23. Do parallel calls reduce total call count?
24. Why can retries amplify an outage?
25. Which metrics prove pagination/caching/call-reduction optimizations succeeded?

**Expected outcome:** learners can design appropriate pagination for SQL and managed datastores, use Spring Data `Page`/`Slice`/`Window`, implement cache-aside and invalidation with Spring Cache, select local/shared caches per workload, eliminate N+1 queries with batching, reuse clients/connection pools, cut duplicate requests, and measure improvements in latency, call count, resource usage, and cost.

## References

- [Spring Data Commons — Scrolling and keyset filtering](https://docs.spring.io/spring-data/commons/reference/repositories/scrolling.html)
- [Spring Data JPA — Paging, sorting and query methods](https://docs.spring.io/spring-data/jpa/reference/repositories/query-methods-details.html)
- [Spring Boot — Caching](https://docs.spring.io/spring-boot/reference/io/caching.html)
- [Spring Framework — Annotation-based caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html)
- [Spring Cloud CircuitBreaker](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Amazon DynamoDB — Paginating query results](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.Pagination.html)
- [Firestore — Paginate data with query cursors](https://docs.cloud.google.com/firestore/native/docs/query-data/query-cursors)
- [Azure Cosmos DB — Pagination and continuation tokens](https://learn.microsoft.com/en-us/azure/cosmos-db/nosql/query/pagination)
- [BigQuery — Paging query results](https://docs.cloud.google.com/bigquery/docs/paging-results)
- [Amazon ElastiCache — Caching strategies](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/Strategies.html)
- [Azure Architecture Center — Caching guidance](https://learn.microsoft.com/en-us/azure/architecture/best-practices/caching)
- [Google Cloud Memorystore — Redis best practices](https://docs.cloud.google.com/memorystore/docs/redis/general-best-practices)
