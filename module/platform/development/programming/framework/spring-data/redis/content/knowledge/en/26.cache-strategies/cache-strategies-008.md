# Synchronizing Cache with Data Changes Using Events or Outbox in Spring Data Redis

In many Spring Boot applications, Redis acts as a cache in front of a primary database. `@Cacheable` reduces source reads and improves latency, yet raises an essential question: **when data in the database changes, how do we keep copies in Redis from being served for too long?**

Setting a short TTL is part of the answer, though it does not guarantee cache freshness right after data changes. When business rules require refreshing sooner than TTL expiration, the application needs a **cache synchronization strategy**. Two common approaches are:

1. **Emitting an event after the write transaction commits**, then deleting or refreshing the cache upon that event.
2. **Transactional outbox**: inserting an event record into an outbox table within **the same transaction** as the data change, after which an independent process relays the event to a messaging system so consumers update the cache.

These two approaches differ mainly in reliability during process crashes or network outages. Neither turns Redis and SQL into a single distributed transaction with shared rollback. This lesson progresses from basic cache-aside to fault-tolerant outbox designs, with examples using Spring Cache, Spring Data Redis, Spring Transactions, and failure modes where stale data can return to the cache.

## 1. The problem: cache hit with stale data

Suppose an application manages products:

```text
PostgreSQL (primary data source)
  products:
    id   = p-100
    name = "Laptop A"
    price = 1200
    version = 7

Redis (cached copy)
  products::p-100:
    {"id":"p-100","name":"Laptop A","price":1200,"version":7}
    TTL = 10 minutes
```

The application executes a database update:

```sql
UPDATE products
SET price = 1100, version = version + 1
WHERE id = 'p-100';
```

After commit, the database holds price `1100` while Redis still stores `1200`. If the read method has:

```java
@Cacheable(cacheNames = "products", key = "#id")
public ProductView findById(String id) {
    return productRepository.findViewById(id);
}
```

then the next read can be a cache hit and **skip the database**. Users keep seeing the old price until the entry expires or is explicitly updated/deleted.

### Key terminology

| Concept | Meaning |
|---|---|
| **Source of truth** | Store considered authoritative, e.g., PostgreSQL |
| **Cache-aside** | Read cache first; on miss, read DB and write result into cache |
| **Invalidation** | Delete or mark a cache entry as no longer valid |
| **Refresh** | Read fresh source data and write it back into cache |
| **TTL** | Maximum lifetime measured from when a cache entry is written or renewed |
| **Eventual consistency** | Cache may lag behind DB, but converges once sync mechanisms run |
| **Outbox** | Event table written in the same transaction as data changes |
| **Idempotency** | Processing the same event repeatedly produces no erroneous side effects |

For caches rebuildable from the DB, **invalidation** is generally a safer starting point than **direct refresh from event payloads**. When the key is deleted, the next read pulls fresh data from the source; by contrast, writing an old event payload into Redis can accidentally overwrite a newer version.

## 2. Cache-aside mechanics in Spring Cache

Read path:

```text
HTTP GET /products/p-100
          |
          v
@Cacheable("products", key="#id")
          |
       Redis GET
          |
    +-----+-----+
    |           |
  Cache hit   Cache miss
    |           |
    |        Read DB
    |           |
    |        Redis SET + TTL
    |           |
    +-----+-----+
          |
          v
    Return ProductView
```

Minimal setup using Redis as the Spring Cache provider:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
```

```yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
  data:
    redis:
      host: localhost
      port: 6379
```

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheConfiguration {
}
```

Example read service, assuming `ProductRepository` provides `findViewById` and `ProductView` is a DTO serializable by the configured cache serializer:

```java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final ProductRepository products;

    public ProductQueryService(ProductRepository products) {
        this.products = products;
    }

    @Cacheable(cacheNames = "products", key = "#id",
               unless = "#result == null")
    public ProductView findById(String id) {
        return products.findViewById(id)
                .orElse(null);
    }
}
```

With cache name `products` and logical key `p-100`, the Redis key typically takes the form `products::p-100`. Physical names can differ if the application customizes prefixes, serializers, or key converters.

The **write path** must coordinate with the invalidation strategy. A 10-minute TTL merely caps cache age; it does not know when the database was just updated.

## 3. Why deleting cache right before or right after UPDATE can be wrong

One might try something simple:

```java
public void changePrice(String id, BigDecimal newPrice) {
    cacheManager.getCache("products").evict(id);
    productRepository.updatePrice(id, newPrice);
}
```

Deleting **before** writing the DB introduces a risk:

```text
Writer                      Reader
------                      ------
Delete Redis key
                            Cache miss
                            Read DB -> old price
                            Write old price back into Redis
Commit new price to DB

Result: DB is new, yet Redis is still stale.
```

Deleting **after** writing the DB yet **before commit** can also fail:

```text
Writer (transaction)        Reader
--------------------        ------
UPDATE inside DB
Not COMMITTED yet
Delete Redis key
                            Cache miss
                            Read DB under normal isolation
                            -> still sees old committed data
                            Writes stale cache back
COMMIT DB
```

Therefore, the first rule is: **only emit invalidation signals after the data-writing transaction has committed successfully**.

Even **post-commit deletion** does not eliminate every race condition. A reader can start reading old DB state before commit and then write the old value to Redis **after** the writer deleted the cache. Section 10 explains this scenario in detail.

### Why `@CacheEvict` alone may not suffice

```java
@Transactional
@CacheEvict(cacheNames = "products", key = "#id")
public void changePrice(String id, BigDecimal price) {
    productRepository.updatePrice(id, price);
}
```

This looks clean, yet the proxy/AOP execution order of the cache interceptor and transaction interceptor must be understood clearly. By default `@CacheEvict` runs after the method returns normally, which **does not automatically mean after the database COMMIT** under every advice configuration. Do not rely on incidental aspect ordering as a consistency guarantee.

A clearer and more accurate approach is publishing an **internal event** and handling it during the `AFTER_COMMIT` transaction phase.

## 4. Approach 1: post-commit internal events in Spring

Spring allows publishing in-process events via `ApplicationEventPublisher` and registering listeners with `@TransactionalEventListener`. With `phase = TransactionPhase.AFTER_COMMIT`, the listener processes events only for transactions that committed successfully.

### 4.1. Processing diagram

```text
ProductCommandService
      |
      | @Transactional
      v
UPDATE products in SQL
      |
      v
publishEvent(ProductChanged)
      |
      | Do not invalidate yet
      v
SQL COMMIT succeeds
      |
      v
@TransactionalEventListener(AFTER_COMMIT)
      |
      v
Cache.evict("p-100")
      |
      v
Next GET: cache miss -> fresh DB -> write fresh cache
```

If the transaction rolls back, the `AFTER_COMMIT` listener **does not run** for that transaction. This avoids clearing cache for uncommitted changes.

### 4.2. Defining the event

Only pass information needed for invalidation; there is no need to put the entire entity in the event:

```java
public record ProductChanged(
        String productId,
        long version
) {
}
```

`productId` tells consumers which cache entry to handle. `version` helps later if stale events must be filtered, compared, or synchronized more carefully; the version must originate from the **primary data source**, never incremented inside the Redis listener.

### 4.3. Publishing the event inside the data-update transaction

Example using JPA, assuming `ProductJpaEntity` has a `changePrice` method, a `@Version` field, and `ProductRepository` is a JPA repository:

```java
import java.math.BigDecimal;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductCommandService {

    private final ProductRepository products;
    private final ApplicationEventPublisher events;

    public ProductCommandService(
            ProductRepository products,
            ApplicationEventPublisher events
    ) {
        this.products = products;
        this.events = events;
    }

    @Transactional
    public void changePrice(String id, BigDecimal newPrice) {
        ProductJpaEntity product = products.findById(id)
                .orElseThrow();

        product.changePrice(newPrice);
        products.saveAndFlush(product);

        events.publishEvent(new ProductChanged(
                product.getId(),
                product.getVersion()
        ));
    }
}
```

`saveAndFlush` executes the SQL statement to update the version before constructing the event, yet **flush is not commit**. The transaction can still roll back after the event is published to the internal event mechanism. `@TransactionalEventListener(AFTER_COMMIT)` is the safeguard preventing pre-commit invalidation.

Depending on your versioning mechanism, do not assume `product.getVersion()` increments immediately after calling a setter without flushing. Use a version confirmed by the ORM/DB data update.

### 4.4. Deleting cache via CacheManager in the listener

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class ProductCacheInvalidator {

    private final CacheManager cacheManager;

    public ProductCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterProductChanged(ProductChanged event) {
        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                    "Cache 'products' is not configured");
        }
        cache.evict(event.productId());
    }
}
```

Here, `cache.evict(event.productId())` uses the **logical key** Spring Cache uses for `@Cacheable(cacheNames = "products", key = "#id")`. Do not manually concatenate `"products::"` and send `DEL`: let `CacheManager` handle namespaces, serializers, and related configuration.

If a method uses `key = "#tenantId + ':' + #id"`, the listener must construct **the exact same logical key**; evicting by ID alone will not remove the right entry.

### 4.5. Strengths and limitations

**Strengths:**

- Concise code, no message broker or outbox table required.
- Avoids deleting cache for rolled-back transactions.
- Fits single-process apps or shared Redis caches when writes pass through the event-emitting service.
- Uses `CacheManager` without needing to know physical Redis keys.

**Important limitation:** `ApplicationEventPublisher` is not a durable queue. If the process crashes **after SQL commits yet before the listener evicts Redis**, the in-memory event can be lost permanently. If Redis is unavailable when the listener runs, there is no default durable retry.

With an `AFTER_COMMIT` listener, a cache deletion failure **cannot roll back the committed SQL transaction**. The application must log errors, monitor, and recover; never interpret an exception in the listener as proof the DB rolled back.

In addition, `@TransactionalEventListener` by default runs only if the event was published inside **an active transaction**. Outside a transaction, the listener is normally skipped unless `fallbackExecution = true` is enabled; enabling fallback should be weighed carefully since it changes "after commit" semantics.

## 5. When are internal events not enough?

Consider this sequence:

```text
T1: Application commits UPDATE products.price = 1100
T2: Process terminates abruptly
T3: AFTER_COMMIT listener never got to delete products::p-100
T4: Redis still holds price = 1200
```

Because the event lived only in process memory, after restart there is no reliable record that "product p-100 changed and its cache needs deletion." TTL will eventually expire the key, yet if TTL is long, stale data may be served longer than desired.

Similarly, if multiple applications write to PostgreSQL—a Java monolith, an import job, and an admin service—emitting internal events in one place will **not** cover other update paths.

When data changes must be emitted reliably, persist the **intent to publish an event** durably inside the same transaction that updates source data.

## 6. Approach 2: Transactional Outbox

**Transactional outbox** is a pattern that writes two things in **the same SQL transaction**:

1. The new business state, e.g., product price.
2. An outbox row describing the event to emit, e.g., `PRODUCT_CHANGED` for `p-100`.

After commit, an **outbox relay** (poller or CDC connector) reads outbox records and forwards them to a message broker. A cache invalidation consumer receives the event and deletes the Redis key.

### 6.1. Full diagram

```text
                  SQL Transaction
          +--------------------------------+
Command   |                                |
Service --+--> UPDATE products             |
          |           +                    |
          |      INSERT outbox_events      |
          |                                |
          +---------- COMMIT --------------+
                       |
                       v
              Outbox row is durable
                       |
                       v
             Outbox relay / CDC
                       |
                       v
            Durable broker / stream
                       |
                       v
              Cache invalidator
                       |
                       v
              RedisCache.evict(id)
                       |
                       v
          Next read loads from DB
```

If the SQL transaction rolls back, **both the product update and the outbox row roll back**. If SQL commits and the app crashes before publishing a message, **the outbox row survives**, so the relay can emit it once the system is back.

Outbox does not force Redis and SQL to commit simultaneously. It **closes the event-loss gap** between writing source data and persisting notification intent, provided all write paths use the same transaction and the relay implements retries.

### 6.2. Why not update the database and publish to the broker directly in one method?

Example:

```text
UPDATE product
PUBLISH event
COMMIT SQL
```

If the broker receives the event yet SQL rolls back, consumers delete cache even though data didn't change. Extra cache deletion might be tolerable, yet a false "changed" event misleads other consumers.

Reversing it to:

```text
UPDATE product
COMMIT SQL
PUBLISH event
```

If the process crashes between `COMMIT` and `PUBLISH`, the event is lost. This is the **dual-write problem**: there is no default shared transaction providing atomic commits across SQL and a broker/Redis.

Outbox turns "write database + send to broker" into "write **two rows in one database transaction**", then handles message delivery with retries and idempotency.

## 7. Designing the outbox table

Minimal PostgreSQL schema example:

```sql
CREATE TABLE products (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(15, 2) NOT NULL,
    version BIGINT NOT NULL DEFAULT 0
);

CREATE TABLE outbox_events (
    event_id UUID PRIMARY KEY,
    aggregate_type VARCHAR(60) NOT NULL,
    aggregate_id VARCHAR(64) NOT NULL,
    aggregate_version BIGINT NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ NULL,
    claim_token UUID NULL,
    claimed_until TIMESTAMPTZ NULL
);

CREATE INDEX outbox_unpublished_idx
    ON outbox_events (created_at, event_id)
    WHERE published_at IS NULL;
```

Column purposes:

| Column | Purpose |
|---|---|
| `event_id` | Unique event identifier for retries/deduplication |
| `aggregate_type` | Business object type, e.g., `product` |
| `aggregate_id` | Product ID needing invalidation |
| `aggregate_version` | Source data version after the update |
| `event_type` | Event kind, e.g., `PRODUCT_CHANGED`/`PRODUCT_DELETED` |
| `payload` | Event data containing only fields consumers genuinely need |
| `created_at` | Creation timestamp for observability and polling |
| `published_at` | Marked by relay after confirmed broker delivery |
| `claim_token`, `claimed_until` | Lets multiple relays claim work and recover from worker crashes |

As needed, you can add `schema_version`, `tenant_id`, `correlation_id`, attempt count, last error code, or operational columns. Do not put sensitive data into event payloads if consumers only need an ID to delete cache.

### Sample event envelope

```json
{
  "eventId": "1d4ee073-438d-44fc-8c44-d0dfe354c441",
  "eventType": "PRODUCT_CHANGED",
  "aggregateType": "product",
  "aggregateId": "p-100",
  "aggregateVersion": 8,
  "schemaVersion": 1,
  "occurredAt": "2026-11-13T02:00:00Z"
}
```

`occurredAt` is purely informational; never use timestamps across different instances as an absolute ordering guarantee. To compare events, prefer **monotonically increasing per-aggregate versions**.

## 8. Writing product and outbox in the same transaction

The example below uses PostgreSQL, `JdbcTemplate`, and `@Transactional` to make the transaction boundary explicit. `UPDATE ... RETURNING` is PostgreSQL syntax; other RDBMSs require equivalent syntax.

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.math.BigDecimal;
import java.util.Map;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ProductOutboxCommandService {

    private final JdbcTemplate jdbc;
    private final ObjectMapper json;

    public ProductOutboxCommandService(
            JdbcTemplate jdbc,
            ObjectMapper json
    ) {
        this.jdbc = jdbc;
        this.json = json;
    }

    @Transactional
    public void changePrice(String id, BigDecimal newPrice) {
        Long version = jdbc.queryForObject(
                """
                UPDATE products
                   SET price = ?, version = version + 1
                 WHERE id = ?
                RETURNING version
                """,
                Long.class,
                newPrice,
                id
        );

        if (version == null) {
            throw new IllegalStateException(
                    "Product not found or version unavailable: " + id);
        }

        UUID eventId = UUID.randomUUID();
        String payload;
        try {
            payload = json.writeValueAsString(Map.of(
                    "eventId", eventId.toString(),
                    "eventType", "PRODUCT_CHANGED",
                    "aggregateType", "product",
                    "aggregateId", id,
                    "aggregateVersion", version,
                    "schemaVersion", 1
            ));
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException(
                    "Cannot encode product change event", ex);
        }

        jdbc.update(
                """
                INSERT INTO outbox_events (
                    event_id, aggregate_type, aggregate_id,
                    aggregate_version, event_type, payload
                ) VALUES (?, 'product', ?, ?, 'PRODUCT_CHANGED', ?::jsonb)
                """,
                eventId, id, version, payload
        );
    }
}
```

This code needs a transaction manager for the SQL datasource; Spring Boot typically auto-configures it when a single suitable datasource is present. Both `products` and `outbox_events` must live in **the exact same real database transaction**. Never place the outbox in an independent datasource and assume `@Transactional` covers both.

Scenarios:

| Scenario | SQL outcome |
|---|---|
| `UPDATE` succeeds and `INSERT outbox` succeeds, commit | Both new data and event are persisted |
| `UPDATE` succeeds, `INSERT outbox` fails | Entire transaction rolls back |
| `INSERT outbox` succeeds, error before commit | Entire transaction rolls back |
| Commit succeeds, JVM crashes before relay runs | New data and outbox row persist |

**Note on the example:** `JdbcTemplate.queryForObject` may throw `EmptyResultDataAccessException` when `UPDATE ... RETURNING` matches no row rather than returning `null`. Applications should translate this exception into a "product not found" error appropriate to the API. That does not break the transactional guarantee of the outbox pattern.

### 8.1. Why is `aggregate_version` needed?

Two close updates:

```text
Product p-100 v7 -> v8 (price 1100)
Product p-100 v8 -> v9 (price 1050)
```

The outbox can contain two events:

```text
Event A: PRODUCT_CHANGED p-100 version 8
Event B: PRODUCT_CHANGED p-100 version 9
```

With multiple relays or different broker partitions, B can reach a consumer before A. If the consumer performs a **blind refresh** using A's payload after processing B, the cache gets overwritten backward from the newer price to the older price.

With an **invalidation** strategy, both events simply request deleting the key, so reordering is usually less dangerous. If writing values directly into cache, enforce atomic version comparison accepting only newer versions.

## 9. Outbox relay: reading, sending, acknowledging, and retrying

A relay moves events from the SQL table to a messaging system such as Kafka, RabbitMQ, or Redis Streams. Two common implementation styles:

- **Polling publisher:** periodically queries unpublished outbox rows.
- **Change Data Capture (CDC):** tails database change logs and emits new outbox rows, e.g., via Debezium.

Either choice keeps the core rule unchanged: **events must be persisted in the source transaction**, and consumers must handle duplicates.

### 9.1. Polling with multiple workers

With multiple relays, avoid having all of them select the same unpublished rows without claiming. In PostgreSQL, `FOR UPDATE SKIP LOCKED` lets workers pick distinct work batches.

Example short **claim** transaction:

```sql
WITH batch AS (
    SELECT event_id
    FROM outbox_events
    WHERE published_at IS NULL
      AND (claimed_until IS NULL OR claimed_until < NOW())
    ORDER BY created_at, event_id
    LIMIT 100
    FOR UPDATE SKIP LOCKED
)
UPDATE outbox_events AS e
   SET claim_token = :claim_token,
       claimed_until = NOW() + INTERVAL '30 seconds'
  FROM batch
 WHERE e.event_id = batch.event_id
RETURNING e.event_id, e.aggregate_id, e.aggregate_version,
          e.event_type, e.payload;
```

`:claim_token` is a worker-generated parameter, not literal SQL syntax. Keep the claim transaction short; then publish claimed events to the broker.

Once the broker acknowledges receipt per the configured producer protocol, the relay updates:

```sql
UPDATE outbox_events
   SET published_at = NOW(),
       claim_token = NULL,
       claimed_until = NULL
 WHERE event_id = :event_id
   AND claim_token = :claim_token
   AND published_at IS NULL;
```

If a worker crashes after claiming yet before publishing, `claimed_until` expires and another worker can reclaim the row. If a worker crashes **after the broker accepted the event yet before marking `published_at`**, the event can be published **again**.

Thus, outbox typically provides **at-least-once** delivery when relays and consumers are implemented properly. It **does not automatically guarantee exactly-once** end-to-end across database → broker → Redis.

### 9.2. Operational requirements for the relay

- Set lease/timeout long enough for normal publish latency and add renewal if batches are large.
- Bound batch sizes, worker counts, and retry counts to avoid overloading the broker.
- If a message fails due to unreadable schema, classify poison messages, log errors, and route to repair or dead-letter handling.
- On retries, set `published_at` only after receiving broker confirmation per the required durability level.
- Maintain a **cleanup or archival policy** for published events so the outbox table does not grow forever.
- Monitor lag from `created_at` until consumer invalidation completes, not just when the relay sends.
- If multiple events for the same product need ordering, partition by aggregate ID or compare versions.

### 9.3. Do not hold SQL locks across network calls

A naive variant keeps the SQL transaction open while sending to the broker and marking published. That holds database locks for the duration of network latency and causes contention. Claim-with-lease separates a **short claim transaction** from **publish I/O**, at the cost of handling lease expiration and duplicate deliveries.

With CDC, polling and claiming like this aren't needed, yet you still must handle event schemas, ordering, retries, connector errors, and duplicate deliveries at the consumer.

## 10. Consumer: receiving events and deleting Redis cache

A broker consumer receives events such as:

```json
{
  "eventId": "1d4ee073-438d-44fc-8c44-d0dfe354c441",
  "eventType": "PRODUCT_CHANGED",
  "aggregateId": "p-100",
  "aggregateVersion": 8
}
```

Its minimum responsibility is **deleting the right entry from the `products` cache**.

### 10.1. Separating invalidation logic from transport

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheInvalidationHandler {

    private final CacheManager cacheManager;

    public ProductCacheInvalidationHandler(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    public void handle(ProductChangedMessage message) {
        Cache cache = cacheManager.getCache("products");
        if (cache == null) {
            throw new IllegalStateException(
                    "No cache configured with name: products");
        }

        // Matches logical key from @Cacheable(key = "#id").
        cache.evict(message.aggregateId());
    }
}

public record ProductChangedMessage(
        String eventId,
        String aggregateId,
        long aggregateVersion
) {
}
```

The handler does not care whether events arrive from Kafka, RabbitMQ, or Redis Streams. The transport adapter solely decodes the message, calls `handle`, and acknowledges (acks) **after** the required work succeeds.

Example Kafka adapter (assuming the app configures `spring-kafka`, listener containers, and consumers appropriately):

```java
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class ProductChangedKafkaListener {

    private final ProductCacheInvalidationHandler handler;

    public ProductChangedKafkaListener(
            ProductCacheInvalidationHandler handler
    ) {
        this.handler = handler;
    }

    @KafkaListener(
        topics = "product-changes",
        groupId = "product-cache-invalidator"
    )
    public void onMessage(ProductChangedMessage message) {
        handler.handle(message);
        // Ack/commit offset according to listener container policy.
    }
}
```

To deserialize JSON messages into `ProductChangedMessage`, configure a suitable Kafka deserializer/message converter and trusted types; this snippet only illustrates the boundary between **broker listener** and **invalidation logic**. Never assume a Kafka Listener is fully configured by the annotation alone.

### 10.2. What about duplicate messages?

`cache.evict(id)` is generally **end-state idempotent**: if the key was already deleted, deleting it again still results in a cache miss on read. Hence invalidation handles duplicate delivery much more gracefully than "incrementing" or "overwriting with payload data".

Still, duplicate processing has effects:

- Extra Redis I/O cost.
- Can delete an entry that was just repopulated with fresh data, causing another cache miss.
- If an event also triggers emails, webhooks, or business metrics, separate idempotency is needed for those side effects.

When deduplication is necessary, store `event_id` in a processed-events table or a dedupe Redis key with a suitable TTL. Ordering between marking processed and completing side effects matters: **never mark success before the main work succeeds** if doing so would cause retries to be skipped.

### 10.3. When Redis is failing

If Redis is temporarily unreachable, the consumer must not acknowledge the message as synced when policy requires invalidation to succeed. Let the transport retry or route the message to an observable error queue.

`RedisCacheManager` may throw exceptions when `evict` fails. Do not configure a `CacheErrorHandler` that swallows all errors and reports sync as succeeded if reliable emission is required.

In apps where the DB is the source of truth, a fallback strategy can keep reads served from the DB while Redis is down, while ensuring reads do not serve stale cached data once Redis recovers.

## 11. Race condition: even after post-commit eviction, stale data can return

A scenario rarely caught in sequential tests:

```text
Time        Reader (cache miss)          Writer/Consumer
----------------------------------------------------------------
t1          GET Redis -> miss
t2          SELECT DB -> reads version 7
t3                                        UPDATE DB to version 8
t4                                        COMMIT DB
t5                                        Event -> EVICT Redis
t6          Redis SET value version 7
t7          Another GET -> gets version 7 (stale)
```

At `t5`, the key did not exist so eviction completed normally. Yet at `t6`, the earlier reader writes the **stale** value to Redis **after invalidation**. The stale entry can survive until TTL expires or another update arrives.

**Conclusion:** "Emit event after commit and delete cache" narrows the inconsistency window, yet **does not guarantee linearizability** across all concurrent reads and writes.

### 11.1. Mitigations

| Approach | Mechanism | Limitation |
|---|---|---|
| Sufficiently short TTL | Limits how long stale entries survive | Not instantaneous; raises cache misses |
| Post-commit delete + delayed second delete | Chance to clear old values written back by readers | Needs durable scheduler if reliability is required; does not prove race elimination |
| Versioned cache keys | Embed version/generation in the cache key | Must read current version from a reliable source |
| Version-based compare-and-set | Prevents older versions from overwriting newer ones | Needs atomic commands/scripts and versioned cache schema |
| Read database when high consistency required | Bypass cache for critical business decision steps | Increases DB load |
| Lock/version-coordinated cache writer | Coordinates read-fills with invalidations | Complex, contention-prone; needs timeout and failure design |

In many applications, **TTL + event-driven invalidation + bounded eventual consistency** is sufficient. If the requirement is "never read an old price after commit," a stronger mechanism is needed rather than adding one more listener.

### 11.2. Versioned keys

Instead of:

```text
products::p-100
```

use:

```text
products::p-100:v7
products::p-100:v8
```

The read path must learn the latest version from a trustworthy source (such as the database or a generation key updated with proper semantics). When the current version is 8, entry v7 is never selected even if it remains in Redis until TTL expires.

**Trade-off:** resolving the version has a cost, and if the version source itself is stale, this fails its goal. Older version keys also need TTLs/cleanup so memory does not grow forever.

### 11.3. Preventing late events from overwriting newer values

Suppose event v9 arrives before v8. If the consumer performs:

```text
event v9 -> cache SET "price = 1050"
event v8 -> cache SET "price = 1100"
```

the cache rolls backward to the old value.

If the consumer must **refresh** instead of evicting, avoid blind `SET` from message payloads. You can:

- Evict only and let the next read pull the latest DB state.
- On receiving an event, query the source DB for current data and current version, then update cache via an atomic version check.
- Write a Lua script comparing the version stored in Redis with the incoming version; update only if newer, preserving appropriate TTL.

With the Spring Cache abstraction, CAS/versioning strategies must be built with `RedisTemplate`/scripts or a custom `Cache` implementation. Default `RedisCacheManager` has no built-in "write only if `aggregateVersion` is greater" contract across entries.

## 12. Synchronizing caches when one change affects multiple keys

For instance, changing a product's price can make several caches stale:

```text
products::p-100                  - product details
productsByCategory::laptops      - category list
featuredProducts::homepage       - featured list
searchResults::laptop-cheap      - search results
priceSummary::category-laptops   - price summary
```

If the consumer deletes only `products::p-100`, lists and summaries still show the old price. Maintain a **dependency map** between data change types and affected cache regions:

| Change | Invalidations to consider |
|---|---|
| Update product description | Product details; search results displaying description |
| Change price | Details; lists showing price; price summaries, price rankings |
| Change category | Details; old and new category lists; search facets |
| Delete product | Details; all related lists/summaries; negative cache |
| Change visibility status | Homepage; search results; public listings |

An event can carry `productId`, `oldCategoryId`, `newCategoryId`, and `version` if needed to locate affected caches. However, avoid turning invalidation events into full copies of business data unnecessarily.

### 12.1. Clearing whole cache regions can be very expensive

Calling `cache.clear()` may delete every key in that cache. With `RedisCacheManager`, the default clear strategy may run `KEYS` and `DEL`, imposing heavy load on large keyspaces. Spring Data Redis supports `BatchStrategies.scan(...)` when configuring `RedisCacheWriter` in compatible driver/topology setups.

Prefer evicting identifiable keys. For composite query caches whose keys cannot be derived from a product ID alone:

- Maintain a reverse index from product ID to related cache keys.
- Use a namespace version/generation for the cache region.
- Use shorter TTLs for list/search caches.
- Choose a different data structure or query engine if invalidation dependencies are too complex.

Never design a `PRODUCT_CHANGED` event that makes every instance repeatedly call `clear()` on a large cache without measuring the load.

### 12.2. Multi-instance deployments and shared Redis

When multiple app instances share **the same Redis `CacheManager` backend**, evicting a Redis key is observed by other instances when they access that key. You do not have to broadcast an internal event to every instance **just to delete the same Redis key**.

However, if the application also uses **an L1 cache in JVM memory** (such as Caffeine) above Redis L2, invalidating Redis **does not automatically clear L1**. In that case, per-instance event fan-out or version/generation checks are required so stale copies do not remain in local memory.

## 13. Redis Pub/Sub, Redis Streams, and message brokers

Multiple transports can deliver events to consumers, each with different delivery contracts.

### 13.1. Redis Pub/Sub

Redis Pub/Sub fits lightweight, real-time notifications to active subscribers:

```redis
PUBLISH product:changed "{\"productId\":\"p-100\"}"
```

Connected subscribers receive the message; offline subscribers **do not automatically receive missed notifications**. Pub/Sub provides **at-most-once delivery**: once the server broadcasts a message, no durable history exists for reconnecting consumers to replay.

Thus, relying on Redis Pub/Sub alone for cache sync is acceptable only when losing an event merely leaves the cache stale within TTL limits. Do not treat it as guaranteed durable invalidation when business rules require processing every event.

In Spring Data Redis, `RedisMessageListenerContainer` is an option for subscribing to Redis Pub/Sub. Yet the listener container does not turn Pub/Sub into a durable message queue.

### 13.2. Redis Streams

Redis Streams support persisted event logs, consumer groups, pending entries, and acknowledgments (`XACK`). Conceptual example:

```redis
XADD stream:product-changes * eventType PRODUCT_CHANGED productId p-100 version 8
```

Compared to Pub/Sub, Streams let consumers resume reading and reprocess pending messages if events remain and recovery is designed properly. Still, durability depends on Redis persistence/replication config, trimming policies, acks, retention, and failover.

Writing an event to a Redis Stream **after** SQL commits still leaves a dual-write gap if the process crashes between the two steps. A SQL-side outbox closes that gap; Redis Streams is simply one **transport channel** a relay can publish to.

### 13.3. Kafka, RabbitMQ, and other brokers

Brokers provide retries, consumer groups, routing, and configurable durability. They fit well when multiple services consume the same product events. However, **brokers themselves do not guarantee SQL updates and message publishes share one transaction**. Transactional outbox or CDC remains helpful on the producer side.

| Mechanism | When to use | What to keep in mind |
|---|---|---|
| Spring `ApplicationEventPublisher` | Single app, lightweight invalidation | Event lives in process memory only; lost on crash |
| Redis Pub/Sub | Real-time notifications, missed events tolerable | No durable replay by default |
| Redis Streams | Need streams/consumer groups on Redis | Must design acks, retention, recovery |
| Kafka/RabbitMQ | Multiple consumers, dedicated durability/routing | Still must solve producer dual-write |
| SQL outbox + relay | Need durable event intent alongside DB changes | At-least-once; consumers must be idempotent |

## 14. Failures in the sync pipeline and recovery

A well-run outbox system must answer these failure cases:

**SQL transaction rolls back:** no event is committed; existing cache can remain accurate since source data didn't change.

**SQL commits, service crashes:** the outbox row persists. The relay resumes and emits the event.

**Relay publishes to broker yet fails before marking published:** relay re-publishes; consumers must tolerate duplicates.

**Broker or Redis outage:** retry with backoff, monitor unprocessed event counts and wait age. Never mark success before processing completes per contract.

**Malformed message payload:** log contextual errors, route to dead-letter/quarantine with repair procedures; avoid infinite retry loops on poison messages.

**Consumer v8 arrives after v9:** invalidation still deletes the newer key (raising cache misses), while blind refresh causes staleness. Optimizing this requires version checks.

**Cache fill writes stale data after invalidation:** mitigate with shorter TTLs or versioning/CAS if stronger bounds are needed; outbox **does not eliminate this race by itself**.

**Multiple caches or dependent regions:** define invalidation scope and avoid deleting only detail caches while leaving lists stale.

### 14.1. Metrics to monitor

| Metric | Problem detected |
|---|---|
| Unpublished outbox row count | Relay lagging or stopped |
| Age of oldest unprocessed outbox row | Data synchronization delay |
| Publish/consume attempts and error rates | Broker/Redis instability or poison messages |
| Consumer lag per partition/stream | Insufficient processing throughput or growing backlog |
| Time from SQL commit → Redis eviction | Pipeline-induced staleness window |
| Cache hits/misses and DB read latency | Cost of overly broad invalidation |
| Cache version vs. DB version | Stale detection via sampling |
| Key count and Redis memory | Impact of TTLs, namespaces, and event-driven refreshes |

Do not monitor only "broker accepted event"; what the business cares about is **whether caches synchronized successfully** and the worst-case lag from source change to read paths reflecting fresh data.

### 14.2. Periodic reconciliation

Even systems with retries need verification and recovery mechanisms:

- Count unprocessed events and alert when backlog age crosses thresholds.
- Periodically compare versions of sampled cache keys against the DB.
- Support replay by event ID or aggregate ID.
- Provide safe operational commands to delete cache by ID/prefix.
- Cap TTL so stale state cannot survive forever when a rare event is missed.

Reconciliation does not replace getting the write path right; it acts as a safety net for operational faults and historical drift.

## 15. Choosing invalidation vs. proactive refresh

### 15.1. Invalidation is usually simpler

```text
PRODUCT_CHANGED(p-100, v8)
       |
       v
Cache.evict(p-100)
       |
       v
Next read -> DB v8 or newer
```

Advantages:

- Small events, requiring only IDs.
- Low risk of overwriting data with stale payloads.
- Consumers do not need to understand full cache DTOs.
- When a product is deleted, deleting its cache entry is natural.

The trade-off is a cache miss on the first read after invalidation and added latency/DB load.

### 15.2. Proactive refresh reduces misses at higher complexity

```text
PRODUCT_CHANGED(p-100, v8)
       |
       v
Read current DB
       |
       v
Write cache with version check
```

Refreshing helps ultra-popular data, yet requires solving several subtleties:

- Multiple events for the same ID can arrive closely together.
- Late events must never overwrite newer data.
- If the source DB reads from a lagging replica, consumers can load stale data.
- Refreshing immediately on events can trigger burst reads on the DB.
- On product deletion, tombstones or invalidations are needed instead of trying to load a missing entity.

A practical approach is **evict on events**, while ultra-hot keys get controlled refreshes via background prewarming or version-checked refreshes.

## 16. Implementation roadmap by complexity

| Level | Approach | Best fit |
|---|---|---|
| 1 | Cache-aside + TTL | Caches not highly sensitive to staleness |
| 2 | TTL + `@TransactionalEventListener(AFTER_COMMIT)` + evict | Monolith or single writer service accepting potential in-memory event loss |
| 3 | TTL + transactional outbox + broker/stream + consumer evict | Multiple services or reliable synchronization needs |
| 4 | Outbox + versioning/CAS + idempotency + reconciliation | Order-sensitive data with high read/write concurrency |
| 5 | Skip cache on decision step or use suitable transactional storage | Zero tolerance for staleness, e.g., exact balance checks |

You do not need Kafka, CDC, and outbox for a small cache with a 20-second TTL. Match complexity to **cost of stale data**, system scale, latency targets, and operational maturity.

### A practical set of design rules

1. **Identify the source of truth.** Redis is typically a rebuildable copy, not the primary transaction authority.
2. **Inventory dependent caches.** One record update can affect detail, list, and aggregation caches.
3. **Invalidate only after DB commit.** Do not delete before commit if stale cache fills must be avoided.
4. **Pick the right durability tier.** In-process events are fast and tidy yet non-durable; outbox persists event intent.
5. **Design for at-least-once.** Outbox can emit duplicates; consumers must be idempotent.
6. **Handle ordering and races.** Invalidation cuts stale overwrites yet does not eliminate cache-fill races entirely.
7. **Keep TTL as a fallback.** It bounds cache age when sync pipelines hit trouble.
8. **Monitor end-to-end.** Track latency from DB commit until caches are invalidated, not merely published message counts.

## 17. Practice exercises

### Exercise A — Post-commit events

1. Create a `products` cache with `@Cacheable(cacheNames = "products", key = "#id")`.
2. Use `ProductCommandService.changePrice` to emit `ProductChanged` inside the transaction.
3. Configure `@TransactionalEventListener(AFTER_COMMIT)` to delete keys via `CacheManager`.
4. Call `findById("p-100")` to populate cache, update the price, and inspect `EXISTS products::p-100`.
5. Throw an exception before commit; observe the post-commit listener does not run on rollback.
6. Kill the app right around commit time to discuss why in-memory listeners can lose events.

### Exercise B — Transactional outbox

1. Create `products` and `outbox_events` as in section 7 in a test PostgreSQL database.
2. Write a `@Transactional` method updating price and inserting into outbox.
3. Force the outbox insert to fail; verify the product update also rolls back.
4. Run a polling relay with lease claiming, event publishing, and marking published.
5. Stop the relay after the broker receives a message yet before marking published; restart and observe duplicates.
6. Write a consumer evicting the cache key; verify re-processing the event causes no incorrect state.

### Exercise C — Simulating a cache-fill race

1. Have a reader miss cache and pause right after reading old DB state.
2. Have a writer update the DB, commit, and emit invalidation.
3. Resume the reader to write the old value to Redis.
4. Observe the stale key existing even though invalidation ran.
5. Propose mitigations using TTLs, versioned keys, or version-checked compare-and-set.

### Exercise D — Synchronizing multiple caches

Create `products`, `productsByCategory`, and `featuredProducts`. When a product changes price or is deleted, identify which caches require eviction. Compare an ID-only event against an event carrying old/new categories, and evaluate the cost of clearing a whole region vs. managing a reverse index.

## 18. Conclusion

Synchronizing caches with data changes is more than calling `DEL` after an `UPDATE`. In Spring Data Redis, the foundational strategy is **cache-aside + TTL + post-commit invalidation**. `@TransactionalEventListener(AFTER_COMMIT)` deletes caches in the right transaction phase, though in-memory events can still vanish on crashes.

When sync intent must never be lost, **transactional outbox** persists business updates and events in the same SQL transaction, after which a relay publishes messages and consumers delete Redis caches. This boosts recoverability while typically yielding **at-least-once delivery**: you must design for duplicates, ordering, retries, partial failures, and lag.

Even after commit, invalidation faces **cache-fill races** where a stale reader writes back old data. Therefore TTLs, versioning/CAS, and source-read strategies remain vital depending on requirements. For business logic that cannot tolerate stale data, never treat cache as the final authority for correctness.

## References

- [Spring Framework — Caching](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CacheEvict`, `@CachePut`, and proxy/abstraction principles.
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, Redis keys, TTLs, prefixes, serialization, and cache clearing.
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): `@TransactionalEventListener`, `AFTER_COMMIT`, and `fallbackExecution`.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): `@Transactional`, transaction synchronization, and commit/rollback timing.
- [Microservices Patterns — Transactional outbox](https://microservices.io/patterns/data/transactional-outbox.html): solving dual-writes and the message relay role.
- [Debezium — Outbox Event Router](https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html): CDC pattern converting outbox rows into events.
- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/): at-most-once nature of Pub/Sub.
- [Redis — Streams](https://redis.io/docs/latest/develop/data-types/streams/): streams, consumer groups, and message processing mechanics.
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/): reading remaining lifetime of individual Redis keys.
