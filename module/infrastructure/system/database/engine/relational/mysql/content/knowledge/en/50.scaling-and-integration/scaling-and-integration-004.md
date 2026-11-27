# Application-Side Caching and Post-Commit Invalidation Strategies

Application-side caching reduces MySQL read volume, lowers latency, and shields the database from traffic spikes. However, caching introduces a secondary copy of data alongside the database. When a transaction updates data, the cache must be handled at the right time; deleting the cache too early allows another request to reload stale data. Updating only the database while forgetting to invalidate the cache causes users to keep seeing old values until the TTL expires.

The common strategy is cache-aside: the application reads the cache first, queries MySQL on a cache miss, and writes the result into the cache; on writes, the application commits the MySQL transaction first and only then invalidates the affected cache keys. For systems requiring high reliability, invalidation events can be written to a transactional outbox within the same transaction as the data, after which a worker publishes the events and deletes cache entries with retries.

This lesson belongs to mastering MySQL from table design, queries, transactions, and concurrency control through system scaling. The focus is on understanding the consistency boundary between MySQL and the cache, choosing invalidation timing, handling race conditions, and testing so cached data does not drift from committed data.

## 1. What Problems Does Application-Side Caching Solve?

An application may receive thousands of reads for the same product, configuration, or catalog. If every read queries MySQL, the database repeats fetching the same rows, parsing SQL, executing query plans, and transmitting results over the network.

A cache keeps frequently read results in a faster access tier. The cache can live in a process's memory (local/in-process cache) or in a shared service across multiple instances (distributed cache). Common examples include cached configuration, product catalogs, infrequently changing profile info, aggregated query results, and metadata.

Caching is appropriate when:

- Data is read far more often than written.
- A clearly defined window of stale data is acceptable.
- The cost of querying MySQL exceeds the cost of storing and fetching from cache.
- Keys can be deterministically identified and invalidated when data changes.
- A TTL can be set to bound how long stale data survives.

Caching is not suitable as the sole source of truth for operations requiring strict correctness. Inventory, balances, payment states, or sensitive access permissions must be verified using transactions and authoritative data in MySQL or another system of record.

## 2. The Cache-Aside Model

Cache-aside (lazy loading) is a model where the application actively reads from and writes to the cache. The cache does not monitor MySQL automatically; the application is responsible for population and invalidation.

### 2.1. Read Flow

~~~mermaid
flowchart TD
    A["Read data request"] --> B["Build cache key"]
    B --> C{"Cache hit?"}
    C -->|Yes| D["Return data from cache"]
    C -->|No| E["Read MySQL"]
    E --> F["Store result in cache with TTL"]
    F --> G["Return data to request"]
~~~

Logic example:

~~~java
public Product getProduct(long productId) {
    String key = "product:" + productId;

    Product cached = cache.get(key, Product.class);
    if (cached != null) {
        return cached;
    }

    Product loaded = repository.findById(productId)
        .orElseThrow(ProductNotFoundException::new);

    cache.put(key, loaded, Duration.ofMinutes(5));
    return loaded;
}
~~~

This is illustrative code; real applications must handle concurrent cache misses, serialization, cache failures, and missing records. The cache should be treated as a fallible dependency; if the cache becomes temporarily unreachable, the application can fall back to MySQL within acceptable load limits.

### 2.2. Write and Invalidation Flow

With cache-aside, the commonly safe pattern is updating the database inside a transaction, waiting for commit to succeed, and then deleting the cache key:

~~~mermaid
sequenceDiagram
    participant App as Application
    participant DB as MySQL
    participant Cache as Cache
    App->>DB: BEGIN
    App->>DB: UPDATE data
    App->>DB: COMMIT
    DB-->>App: Commit succeeded
    App->>Cache: DELETE affected keys
    Cache-->>App: Deleted or key did not exist
~~~

If the transaction rolls back, the cache is not evicted for a change that never existed in the database. After commit, the next read request misses the cache and loads fresh data from MySQL.

Invalidating a key is usually simpler and less risky than reconstructing a new cache entry from write inputs. A business operation may update multiple columns, trigger side effects, generated values, or related data; if the application writes to the cache from an object before the database completes, the cache may not reflect the final persisted state.

## 3. Why Invalidate After Commit?

Operation ordering determines whether another reader can re-populate stale data into the cache.

### 3.1. Deleting Cache Before Commit Creates a Race Condition

Suppose the cache holds a product priced at 100. A transaction changes the price to 120:

~~~text
Writer A                         Reader B
DELETE cache key
                                 Cache miss
                                 SELECT MySQL -> price 100
                                 PUT cache price 100
UPDATE MySQL price = 120
COMMIT
~~~

Result: MySQL now has price 120 while the cache holds price 100. The cache stays wrong until the key is deleted again or the TTL expires. This bug can be hard to reproduce because it depends on interleaved request timing.

### 3.2. Commit First, Delete After

~~~text
Writer A                         Reader B
UPDATE MySQL price = 120
COMMIT
                                 Cache hit price 100 (brief window)
DELETE cache key
                                 Cache miss on next read
                                 SELECT MySQL -> price 120
                                 PUT cache price 120
~~~

Invalidating after commit eliminates the "reader reloads old data before writer commits" race condition. Still, between commit time and cache deletion time there is a brief window where a reader may receive the old value. For business flows tolerating eventual consistency, this window is usually managed via post-commit events, TTLs, and retries. For flows requiring strict read-after-write, stronger mechanisms are needed such as bypassing the cache on the writing request, version/generation tokens, or reading MySQL directly.

### 3.3. Never Populate Cache from Uncommitted Data

If the application writes a new value into the cache before the transaction commits, other requests can read uncommitted data. If the transaction subsequently rolls back, the cache holds a value that does not exist in MySQL.

Therefore, every cache operation representing persisted state must occur after commit. If a cache is used as part of a workflow with its own state, design those semantics explicitly rather than conflating them with caching MySQL data.

## 4. Spring Transactions and Post-Commit Cache Operations

In Spring, `@Transactional` manages transaction boundaries. A service method can publish an application event within the transaction; the listener executes only after the transaction commits.

### 4.1. Using `TransactionalEventListener`

Service example:

~~~java
public record ProductChangedEvent(long productId) {}

@Service
public class ProductService {

    private final ProductRepository repository;
    private final ApplicationEventPublisher events;

    public ProductService(
            ProductRepository repository,
            ApplicationEventPublisher events) {
        this.repository = repository;
        this.events = events;
    }

    @Transactional
    public void changePrice(long productId, BigDecimal newPrice) {
        Product product = repository.findById(productId)
            .orElseThrow(ProductNotFoundException::new);

        product.setPrice(newPrice);
        repository.save(product);

        events.publishEvent(new ProductChangedEvent(productId));
    }
}
~~~

Listener:

~~~java
@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onProductChanged(ProductChangedEvent event) {
        Cache cache = cacheManager.getCache("products");
        if (cache != null) {
            cache.evict("product:" + event.productId());
        }
    }
}
~~~

`TransactionalEventListener` binds the listener to the active transaction by default; `AFTER_COMMIT` runs only when the transaction commits. Without an active transaction, the listener does not run by default unless `fallbackExecution` is enabled, and enabling that option changes semantics. Use fallback only when you truly intend to handle events outside a transaction.

The example above assumes cache keys are built from product IDs. If the cache also holds keys by SKU, category, product lists, or search results, dependent entries must also be invalidated or managed via a version/tag mechanism.

### 4.2. `TransactionSynchronization`

When a dedicated domain event is unnecessary, you can register a post-commit callback:

~~~java
if (TransactionSynchronizationManager.isSynchronizationActive()) {
    TransactionSynchronizationManager.registerSynchronization(
        new TransactionSynchronization() {
            @Override
            public void afterCommit() {
                cache.evict(cacheKey);
            }
        }
    );
} else {
    // No enclosing transaction: handle per explicit policy.
}
~~~

Callback registration must occur inside the exact transaction containing the data changes. Do not register a callback after the transaction has already finished or on another thread not bound to the transaction.

### 4.3. Limitations of Post-Commit Callbacks

An `afterCommit` callback solves ordering, but does not by itself provide durable delivery guarantees. The process can crash after MySQL commits but before the callback deletes the cache. The cache may also be temporarily unreachable.

If a listener runs synchronously and throws an exception, the already-committed MySQL transaction cannot be rolled back. The caller may receive an error even though data was persisted; a client retry could then create duplicate operations if the API is not idempotent. Log errors, emit metrics, implement controlled retries, and design for idempotency.

`@Async` can offload the listener to another executor, but if the process stops before the task executes or the queue is non-durable, the event can be lost. Async decouples execution timing from the request; it does not automatically make events durable messages.

## 5. Transactional Outbox for Reliable Invalidation

When losing an invalidation event after commit is unacceptable, use a transactional outbox. The application writes both the business change and an outbox record within the same MySQL transaction. A worker reads the outbox after commit, publishes the event or deletes the cache, and then marks the record processed.

### 5.1. Why Does Outbox Solve the Dual-Write Gap?

If an application performs two independent operations:

1. Commit data to MySQL.
2. Send an event to a broker or cache.

The process can crash between the two steps. If the event is sent before commit, it may be published even though the transaction rolls back. If sent after commit, the process may crash before sending.

An outbox writes business data and the event in the same transaction. Either both commit together, or both roll back together:

~~~mermaid
flowchart TD
    A["BEGIN MySQL transaction"] --> B["UPDATE business row"]
    B --> C["INSERT outbox event"]
    C --> D{"COMMIT?"}
    D -->|Rollback| E["Neither change nor event persists"]
    D -->|Commit| F["Worker reads outbox"]
    F --> G["Publish event / invalidate cache"]
    G --> H["Mark event processed"]
    H --> I["Retry if error detected"]
~~~

### 5.2. Illustrative Outbox Table

~~~sql
CREATE TABLE outbox_event (
  event_id BIGINT NOT NULL AUTO_INCREMENT,
  aggregate_type VARCHAR(100) NOT NULL,
  aggregate_id VARCHAR(128) NOT NULL,
  event_type VARCHAR(100) NOT NULL,
  payload JSON NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  published_at TIMESTAMP(6) NULL,
  attempts INT NOT NULL DEFAULT 0,
  PRIMARY KEY (event_id),
  KEY ix_outbox_pending (published_at, event_id)
) ENGINE = InnoDB;
~~~

In the same transaction that updates the product:

~~~sql
START TRANSACTION;

UPDATE product
SET price = 120.00,
    version = version + 1
WHERE product_id = 101;

INSERT INTO outbox_event (
  aggregate_type,
  aggregate_id,
  event_type,
  payload
)
VALUES (
  'Product',
  '101',
  'ProductChanged',
  JSON_OBJECT('productId', 101)
);

COMMIT;
~~~

The example assumes the `product` table has a `version` column. In real applications, emit an event only when the UPDATE actually changed data per business rules; check affected rows before inserting an outbox event or publishing a domain event. UUID-style event IDs can be used if multiple writers need independent ID generation or to avoid relying on a single central sequence.

Workers fetch unprocessed events, issue invalidations, and update status. MySQL 8 supports `FOR UPDATE SKIP LOCKED`, which is useful when multiple workers claim work concurrently:

~~~sql
START TRANSACTION;

SELECT event_id, aggregate_type, aggregate_id, event_type, payload
FROM outbox_event
WHERE published_at IS NULL
ORDER BY event_id
LIMIT 100
FOR UPDATE SKIP LOCKED;

-- Application processes fetched events and updates status.
COMMIT;
~~~

This SQL snippet only illustrates claiming rows; the worker must keep transactions short and design event publishing carefully. Never hold row locks while calling a slow network service. You can use a claim/lease state, worker ID, and lease expiration to claim work in a short transaction, then publish events outside the transaction.

### 5.3. At-Least-Once and Idempotency

A worker can publish an event successfully and then crash before marking `published_at`. After restart, the event is published again. Therefore, an outbox typically provides at-least-once semantics, not end-to-end exactly-once.

For cache invalidation, deleting the same key multiple times is naturally idempotent: deleting an already-deleted key leaves it non-existent. For other side effects, consumers must store processed event IDs or use versions to prevent duplicate application.

Track retry counts, age of the oldest pending event, pending event counts, and publish errors. Have a dead-letter policy or alerting when events exceed retry thresholds; never delete failing events just to make the backlog disappear.

## 6. Cache Invalidation Across Multiple Key Types

A single MySQL record can appear in multiple cache entries:

- Detail cache by ID: `product:{id}`.
- Lookup cache by SKU: `product:sku:{sku}`.
- List cache by category: `products:category:{categoryId}`.
- Search result cache: `products:search:{queryHash}`.
- Homepage cache or aggregate statistics.

When updating a product, deleting only `product:{id}` may not suffice if lists or search results still retain the old version.

### 6.1. Dependency-Driven Key Design

Maintain documentation or a code registry showing which data depends on which tables/columns and which keys must be invalidated when a mutation occurs. For example:

| MySQL Change | Cache keys that may require invalidation |
|---|---|
| Product name/price change | `product:{id}`, `product:sku:{sku}`, category lists, and search results |
| Category reassignment | Detail cache, old and new category lists |
| Product deletion | Detail cache, SKU lookup, lists, and search results |
| Order status change | `order:{id}`, user order lists, and status metrics |
| User permission change | Profile/permission cache and all permission-scoped caches |

Never place data from different tenants or users into the same cache key if contents depend on permissions or data scope. Keys must include tenant ID, locale, currency, role/scope, or required filter parameters.

### 6.2. Invalidating Groups of Keys

If a change affects thousands of keys, deleting keys individually can be slow and generate heavy load. You can use namespace versioning:

- Actual key includes `catalog:v42:category:12`.
- When the catalog changes, increment the namespace version to `v43`.
- Old keys automatically become unreferenced and expire via TTL.

Namespace versioning makes group invalidation fast, but version updates must be observed consistently across all instances. If each process keeps its own local version, nodes can continue reading old namespaces. Use a shared version source or acknowledged event fan-out.

Avoid flushing the entire cache when a single record changes. A cache flush can trigger a cache stampede, sending many concurrent requests back to MySQL and overloading it right as the system processes mutations.

### 6.3. Do Not Use Key Scanning as the Default Strategy

Scanning all keys to find matching prefixes can be expensive and behaves differently across cache engines. Design keys, tags, membership sets, or namespace versions from the start. If you must use `SCAN` in Redis or an equivalent mechanism, rate-limit it, process results in batches, and test on production-sized keyspaces; never run synchronous scans inside write requests.

## 7. Race Conditions on Cache Miss and Stale Refill

Even when writers invalidate after commit, another race remains:

~~~text
Reader A                         Writer B
GET cache -> miss
SELECT MySQL -> price 100
                                 UPDATE MySQL price 120
                                 COMMIT
                                 DELETE cache key
PUT cache price 100
~~~

Reader A started reading before the writer committed, yet wrote to the cache after the writer deleted the key. The cache holds the old price again. This is a stale refill race.

Remediation depends on consistency requirements:

1. **Short TTL with accepted eventual consistency:** simple, suited to less sensitive data; bound the stale window.
2. **Single-flight or per-key locking:** only one reader populates the cache for a key at a time; writers must coordinate with the lock if strict guarantees are required.
3. **Version/generation tokens:** reader records the generation before reading MySQL, then populates the cache only if the generation remains unchanged.
4. **Version-aware cache writes:** entries carry a monotonically increasing version; an atomic operation allows only a newer version to overwrite an older one.
5. **Bypass cache after write:** the writing request reads directly from MySQL or uses the data returned from the committed transaction.

Generation token example:

~~~text
Reader:
  generation_before = GET generation:product:101
  value = SELECT product FROM MySQL
  atomic_if_equal(generation_before):
      SET product:101 = value

Writer after commit:
  INCREMENT generation:product:101
  DELETE product:101
~~~

Checking the generation and writing the cache must be a single atomic operation on the cache; if split into two commands, a writer can still increment the generation between the check and the write. Use an atomic script/transaction supported by the cache backend. The generation key must not be evicted or expire earlier than the entries it protects, otherwise old tokens could be reused. The reader must fetch the generation before opening the snapshot used to read data or ensure both generation and payload are verified against a consistent snapshot; if the reader uses a pre-opened `REPEATABLE READ` transaction and then fetches a new generation, it could still write a payload from the stale snapshot.

Another approach stores a version in the MySQL row and in the cache. The writer increments the version in the same data transaction. The reader publishes the result only if the read version still matches the current generation. Design generation storage so writers and readers can perform atomic checks; simply adding a version column to the row without a compare-and-set step does not fully resolve the race.

No single simple invalidation pattern guarantees absolute cache-MySQL consistency across all network failures and process crashes. Choose consistency semantics per business flow, measure the stale window, and document acceptance criteria.

## 8. Cache Stampede, TTL, and Cache Failures

### 8.1. Cache Stampede

When a popular key expires, hundreds of requests can miss the cache simultaneously and query MySQL concurrently. As a result, the database suffers a sudden load spike.

Mitigations:

- Single-flight/request coalescing so multiple requests share a single load.
- Bounded per-key locks so one worker reloads while others wait or serve stale data if permitted.
- TTL jitter so many keys do not expire at the exact same instant.
- Pre-expiration refresh with concurrency limits.
- Stale-while-revalidate for data that can be temporarily stale.
- Fallback load limiting toward MySQL during cache outages.

Locks must have leases/timeouts and handling for dead lock owners. Never use unbounded locks that can leave a key hung indefinitely.

### 8.2. TTL Is a Safety Net, Not a Replacement for Invalidation

TTL bounds how long an entry lives, but a 30-minute TTL means data can remain stale for nearly 30 minutes. For frequently changing data, post-commit invalidation shrinks the stale window; TTL acts as a fallback when events are lost or a node misses an invalidation.

Add random jitter to TTLs to avoid synchronized expiration of many keys. Choose TTLs based on data mutation frequency, business sensitivity, and MySQL's capacity to absorb increased cache misses.

### 8.3. Cache Unavailable

If the cache becomes unreachable:

- Fall back to MySQL for low-volume keys.
- Use circuit breakers or concurrency limits to avoid dumping all traffic onto the database.
- Do not trap failing cache calls in infinite retry loops within requests.
- Emit metrics for cache errors, hit/miss, fallbacks, and latency.
- When the cache recovers, avoid reloading the entire dataset simultaneously.

The cache is an acceleration layer. If the cache is a mandatory business dependency, explicitly classify it as a datastore or state store and design matching durability/HA rather than treating it merely as a cache.

## 9. Negative Caching and Non-Existent Data

Cache-aside normally stores only found records. For a non-existent ID, repeated requests can hit MySQL every time and create unnecessary load. Negative caching stores a "not found" marker with a short TTL.

Example:

~~~text
product:999 -> NOT_FOUND (TTL 20 seconds)
~~~

When product 999 is created, the post-commit event must delete the negative cache key. Otherwise, users may not see the new product until the marker expires.

Distinguish three states:

- Cache miss: key is not present in cache.
- Cached not found: MySQL was queried and confirmed non-existence.
- Cached value: data is present.

Do not rely on `null` as the sole signal if the cache API also returns `null` when a key is absent. Use a sentinel or an explicit stateful result type. Negative caches require short TTLs and must account for tenant, access permissions, and soft deletes.

## 10. Write-Through and Write-Behind Alternatives

Cache-aside is not the only pattern:

| Model | Write path | Characteristics |
|---|---|---|
| Cache-aside | Write MySQL, delete cache after commit | Simple; application controls cache misses and invalidation |
| Write-through | Writes pass through the cache layer, which updates synchronously with the datastore | Keeps cache warm but requires defining ordering and error handling across two systems |
| Write-behind/write-back | Write cache first; system flushes to MySQL asynchronously/in batches | Low write latency but higher data-loss risk and recovery complexity |

When MySQL is the authoritative source of truth, cache-aside plus post-commit invalidation is usually the easiest starting point to operate. Write-behind is unsuitable if the application treats a MySQL commit as business confirmation; if used, the cache becomes part of the write path and needs dedicated durability, replay, idempotency, backup, and recovery plans.

## 11. Testing Consistency Between MySQL and Cache

Do not only test that a cache hit returns expected data. Test commits, rollbacks, race conditions, multiple instances, and event delivery failures.

### 11.1. Commit and Rollback Tests

- When a transaction commits, affected cache keys are invalidated.
- When a transaction rolls back, existing valid cache entries remain intact and are not replaced by uncommitted data.
- When a transaction makes no actual changes, suppress redundant invalidations when feasible.
- If a post-commit invalidation callback fails, MySQL data remains committed and the failure is recorded for retry.

### 11.2. Concurrent Reader/Writer Tests

Create two threads coordinated by barriers:

1. Reader misses the cache and begins reading MySQL.
2. Writer updates the row, commits, and invalidates the key.
3. Reader finishes its query and attempts to populate the cache.
4. Read the cache again and verify it cannot retain the old value beyond the accepted stale window.

This test catches stale refill races. Use synchronization primitives such as `CountDownLatch`/`CyclicBarrier` rather than relying on `Thread.sleep` for random timing.

### 11.3. Outbox Tests

- Events are written inside the business transaction.
- Rollbacks leave no outbox events behind.
- Workers retry when the cache or broker temporarily fails.
- Crashing after invalidation but before marking `published` causes no corruption when the event is reprocessed.
- Multiple workers do not drop events.
- Aging pending events trigger alerts and have handling procedures.

### 11.4. Multi-Instance Tests

With local caches, each instance holds its own copy. Invalidation events must be broadcast to all instances, or the cache must have TTLs/namespaces bounding staleness. Test across at least two application instances: write via instance A, read via instance B, and verify B's cache is updated or invalidated according to policy.

With shared distributed caches, verify key namespaces, tenant isolation, serialization versioning, and behavior during cache cluster failover.

## 12. Observing and Operating Caches

Metrics to monitor:

| Metric | Meaning |
|---|---|
| Hit ratio | Percentage of requests served from cache |
| Miss rate | Rate of requests falling back to MySQL or another source |
| Eviction count | Entries removed due to TTL or memory pressure |
| Invalidation lag | Time elapsed from DB commit to cache invalidation |
| Outbox oldest age | Age of the oldest unprocessed event |
| Retry/dead-letter count | Number of failed and retried invalidation events |
| Cache operation latency | Duration of GET/SET/DELETE operations |
| Fallback rate | Percentage of requests bypassing cache to read MySQL |
| Stale-read indicator | Count of detected stale cache versions or reads exceeding stale SLO |

A high hit ratio alone does not prove a cache is healthy. A cache can serve stale data very efficiently. Monitor invalidation lag, stale reads, data accuracy, and MySQL load together.

Alert when outbox backlogs grow, invalidation lag breaches SLO, cache errors spike, or MySQL fallback traffic exceeds thresholds. For local caches, measure per instance to detect a node failing to receive events.

## 13. Practical Scenario

An e-commerce application caches product details for 10 minutes. An administrator updates a product's price in MySQL; the write API returns success, yet some users still see the old price. The system has four application replicas, each with a local cache.

Build a strategy:

1. Define cache keys for detail pages, SKU lookups, and category lists.
2. Wrap the price update in a MySQL transaction.
3. Publish `ProductChangedEvent` inside the transaction and handle it with an `AFTER_COMMIT` listener, or write an outbox record in the same transaction if events must survive process crashes.
4. Broadcast invalidation to all four replicas or switch to a shared distributed cache.
5. Set a TTL as a safety net and add an invalidation lag metric.
6. Test rollbacks so uncommitted changes never evict the cache.
7. Test stale refill races where a reader misses the cache before the writer commits.
8. Verify that writing through replica A causes subsequent reads through replica B to honor the consistency policy.

If the selling price must be exact at checkout, never use a cached price as the final price. Read/lock and verify the price inside the business transaction on MySQL, and record the finalized price on the order. The cache serves display only; the authoritative data source for billing must follow the defined business contract.

## 14. Cache Invalidation Design Checklist

### Before Enabling Cache

- [ ] Identify whether MySQL or another system is the authoritative data source.
- [ ] Document what data is cached and the acceptable staleness bound.
- [ ] Design keys containing tenant, locale, filters, and access permissions.
- [ ] Inventory every cache entry dependent on a data mutation.
- [ ] Choose TTLs, negative caching, and cache-unavailable handling.
- [ ] Specify read-after-write rules for each business flow.

### When Writing Data

- [ ] Commit the MySQL transaction before invalidating.
- [ ] Never publish cache values from uncommitted data.
- [ ] Use after-commit callbacks/events or a transactional outbox.
- [ ] Handle invalidation failures with retries, metrics, and alerts.
- [ ] Ensure event consumers are idempotent.
- [ ] Account for stale refill races and version/generation tokens if needed.

### In Operations

- [ ] Monitor hit/miss ratios, invalidation lag, and stale reads.
- [ ] Monitor outbox backlogs and failed events.
- [ ] Test multi-instance behavior, restarts, and cache failovers.
- [ ] Maintain controlled flush/namespace rollover procedures.
- [ ] Never flush the entire cache for a minor change.
- [ ] Verify sensitive data cannot leak across incorrectly scoped cache keys.

## 15. Self-Check Questions

1. How does cache-aside differ from write-through and write-behind?
2. Why can deleting the cache before commit cause a reader to reload stale data?
3. What does `AFTER_COMMIT` in Spring guarantee, and what does it not guarantee?
4. Why can a process crash after commit but before invalidation still leave the cache stale?
5. How does a transactional outbox close the dual-write gap?
6. Why do outbox consumers need idempotency even when an event represents a single change?
7. Under what interleaving does a stale refill race occur?
8. What atomic operation does a generation token require to prevent a reader from overwriting newer cache entries with stale data?
9. Why can TTL not replace invalidation?
10. When must you bypass the cache and read MySQL directly?

Caching helps MySQL serve read traffic more efficiently, but it is safe only when the application explicitly manages the source of truth, invalidation timing, and consistency levels. With cache-aside, commit MySQL first and then invalidate; use after-commit events for simple flows and a transactional outbox when durable delivery is required. Test rollbacks, concurrent refills, multiple instances, and worker failures so the cache always obeys the business consistency policy.
