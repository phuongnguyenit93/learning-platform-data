# Distinguishing Redis as a Data Store, Cache, Session Store, and Queue

> **Chapter:** Redis  
> **Module:** SPRING_BOOT_INTEGRATION — organizing system integrations in Spring Boot across HTTP clients, databases, caches, message brokers, and Spring Integration adapters, emphasizing data contracts, configuration, transactions, errors, duplicates, testing, and observability.  
> **Objective:** Select the right role for Redis, identify the source of truth, and explain how to protect data when Redis, the application, or downstream services fail.

Redis is an in-memory key-value datastore supporting Strings, Hashes, Lists, Sets, Sorted Sets, Streams, and other data structures. Redis can serve as a **data store**, **cache**, **session store**, or **queue**. Though it is one technology, the data-loss tolerance, lifetimes, consistency guarantees, and error handling of these four roles differ sharply.

Examples in an e-commerce Spring Boot system:

- PostgreSQL stores products and orders; Redis keeps a **cached copy** of products to reduce read load.
- Redis stores **web login sessions**, allowing multiple Spring Boot instances to share `HttpSession` state.
- Order service creates an **email job**; workers consume jobs from Redis Streams to send emails asynchronously.
- Redis manages **view counters**, leaderboards, short-lived state, or rate limiting.

If Redis drops a cache key, the system can reload from PostgreSQL. If Redis drops a session, users may have to log in again. If Redis loses a pending job message, business work may be skipped. If Redis holds primary data with no other copy, an outage can permanently lose business data. Therefore, before choosing any Redis API, ask: **If this key disappears, what is the actual impact?**

## 1. Where Do the Four Roles Differ?

| Role | Data Held in Redis | Source of Truth | Lifecycle | Impact of Losing a Key |
| --- | --- | --- | --- | --- |
| **Data store** | Counters, sets, business state, rankings, hot data | May be Redis itself | Business-driven; possibly no TTL | Loss of primary data or need for backup restore |
| **Cache** | Copy of DB/API results or recomputable data | Authoritative DB/API/dataset | TTL or invalidation | Cache miss, higher latency and origin load |
| **Session** | Session ID and active session attributes | Redis holds active session; long-term identity lives in user DB/IdP | Idle timeout, logout, revoke | Lost session; user must re-authenticate |
| **Queue** | Pending commands/events/jobs for workers | Depends on design; Stream or DB/outbox | ACK, retry, retention | Lost work, duplicate runs, or stuck backlogs |

**Decision keywords:** rebuildability, durability requirements, staleness bounds, partial-failure handling, and lifetime contracts. Never equate "a Redis key with a TTL" with a cache: sessions and idempotency keys also have TTLs, yet carry distinct business semantics.

~~~mermaid
flowchart LR
    C["Client"] --> A["Spring Boot API"]
    A --> P[("PostgreSQL<br/>Orders, Products")]
    A <--> CA[("Redis<br/>Cache")]
    A <--> SE[("Redis<br/>Sessions")]
    A <--> DA[("Redis<br/>Counters / Rankings")]
    A --> ST[("Redis Streams<br/>Jobs")]
    ST --> W["Async Worker"]
    W --> X["Email / Payment API"]
~~~

This is a **logical role** diagram; all roles do not need to share one Redis instance. Production setups often separate caches from sessions and queues to isolate resources, eviction, and failure domains.

## 2. Redis as a Data Store: Operational and Business State

In the data-store role, the application writes data directly to Redis and may have no secondary store to rebuild from. Common patterns:

- **`INCR`** for view counts and rate-limiting counters.
- **`SADD` / `SISMEMBER`** for membership sets and active keys.
- **`ZADD` / `ZREVRANGE`** for leaderboards.
- **`HSET` / `HGETALL`** for compact multi-field state.
- Short-lived state such as OTP challenges or transient processing markers.

Counter example:

~~~bash
INCR product:SKU-42:views
GET product:SKU-42:views
~~~

**`INCR`** is an atomic single-key increment, safer than `GET → add in Java → SET` under concurrency. However, **command atomicity does not equal crash durability**. Recently incremented values can still be lost within persistence or replication windows.

Spring Data Redis example:

~~~java
package example.integration.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductViewCounter {
    private final StringRedisTemplate redis;

    public ProductViewCounter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Long recordView(String sku) {
        // Validate/normalize sku before constructing actual key.
        return redis.opsForValue().increment(
                "product:" + sku + ":views");
    }
}
~~~

This sample assumes `spring-boot-starter-data-redis` and an active `RedisConnectionFactory`. Check null/error handling per API contract and validate inputs to prevent unbounded key creation. If view counts are approximate analytics, losing a few increments may be tolerable; for financial balances, the same trade-off is unacceptable.

### 2.1. Persistence and Failover

| Mechanism | Function | Limitations to Understand |
| --- | --- | --- |
| **RDB snapshot** | Periodic point-in-time snapshots | Updates after the last snapshot can be lost |
| **AOF (Append Only File)** | Logs write commands for recovery | `fsync` policy trades performance for durability; `everysec` can still lose recent writes on crash |
| **Replication** | Copies primary to replicas | Usually asynchronous; failovers can lose un-replicated writes |
| **Sentinel** | Detects failures, elects primary, coordinates failover | Does not turn Redis strongly consistent or eliminate write loss |
| **Redis Cluster** | Shards across hash slots with failover | Restricts cross-slot multi-key commands; replication/failover still have loss windows |
| **Backup/restore** | Recovers from data loss or operator mistakes | Requires defined RPO/RTO and periodic restore drills |

When Redis is the **primary datastore** with low tolerance for data loss, design persistence, backups, monitoring, and tested recovery procedures. RDB/AOF and replicas reduce risk, yet never make Redis a shared transaction manager across PostgreSQL, HTTP, or message brokers.

### 2.2. Atomicity Inside Redis

Redis supports **`MULTI`/`EXEC`**, **`WATCH`**, and Lua scripts to coordinate multiple operations inside Redis:

- **`MULTI`/`EXEC`** executes queued commands sequentially without interleaving from other clients, but **does not roll back prior commands** if a command fails during execution.
- **`WATCH`** provides optimistic concurrency; the transaction aborts if watched keys change before `EXEC`.
- **Lua scripts** run Redis logic atomically where appropriate, though long scripts block other command processing.
- In **Redis Cluster**, multi-key operations must respect hash-slot constraints (using hash tags when related keys must share a slot).

**`@Transactional`** for JDBC/JPA does not open a distributed transaction with Redis. If a method writes to PostgreSQL and Redis, the two side effects commit independently and require separate reconciliation or compensation.

## 3. Redis as a Cache: Speeding Reads While Tolerating Staleness

A cache holds **rebuildable copies** from databases, APIs, or computations. The standard pattern is **cache-aside**:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Product Service
    participant R as Redis Cache
    participant D as PostgreSQL
    C->>A: GET /products/SKU-42
    A->>R: GET product:SKU-42
    alt Cache hit
        R-->>A: Product
    else Cache miss
        R-->>A: nil
        A->>D: SELECT product
        D-->>A: Product
        A->>R: SET product with TTL
    end
    A-->>C: Product
~~~

When the DB updates, the cache can hold old values. TTL only **bounds staleness duration**; it does not keep the cache instantaneously synchronized. Endpoints requiring read-your-writes or strict invariants must read the source of truth, invalidate post-commit, use versioning, or adopt matching consistency mechanisms.

### 3.1. Spring Cache with RedisCacheManager

In Spring Boot, the Spring Cache abstraction can use `RedisCacheManager`; configuration example:

~~~java
package example.integration.redis;

import java.time.Duration;
import java.util.Map;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class ProductCacheConfiguration {
    @Bean
    CacheManager cacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(5))
                        .disableCachingNullValues();

        return RedisCacheManager.builder(factory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(Map.of(
                        "products", defaults.entryTtl(Duration.ofMinutes(15))))
                .build();
    }
}
~~~

Read example:

~~~java
package example.integration.redis;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {
    private final ProductRepository repository;

    public ProductQueryService(ProductRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public ProductDto findBySku(String sku) {
        return repository.findBySku(sku)
                .orElseThrow(() -> new ProductNotFoundException(sku));
    }
}
~~~

**`ProductRepository`**, **`ProductDto`**, and **`ProductNotFoundException`** are illustrative domain types. In standard proxy mode, calling a **`@Cacheable`** method from within the same bean (self-invocation) bypasses cache advice. Verify keys, serializers, TTLs, and error/empty results against your contract.

Invalidation example on update:

~~~java
@CacheEvict(cacheNames = "products", key = "#sku")
public void updateProduct(String sku, UpdateProductCommand command) {
    repository.update(sku, command);
}
~~~

**Caution:** cache proxies and DB transactions do not form an atomic commit. If the DB rolls back or the process dies between DB commit and cache eviction, the cache can stay stale. For stronger requirements, trigger invalidation **after DB commit** and use retry/outbox events for out-of-band caches.

### 3.2. How Do Caches Typically Fail?

| Issue | Symptom | Mitigation |
| --- | --- | --- |
| **Cache stampede** | Many concurrent requests miss a hot key and flood the DB | TTL jitter, single-flight, proactive refresh, controlled fallback |
| **Cache penetration** | Repeated queries for nonexistent keys | Input validation, rate limiting, short-TTL negative caching |
| **Cache avalanche** | Many keys expire simultaneously or Redis goes down | Staggered TTLs, warming, DB load shedding |
| **Stale values** | Stale data served after writes | Post-commit invalidation, versions, or tighter TTLs |
| **Eviction pressure** | Hit rate drops and DB overloads | Memory budgets, eviction policy tuning, tracking `evicted_keys` |

Cache unavailability needs explicit fallback behavior. Falling back to the DB works when protected by timeouts, backpressure, or circuit breakers, especially if multiple pods lose cache simultaneously.

## 4. Redis as a Session Store with Spring Session

**Spring Session Data Redis** stores web sessions in Redis so multiple Spring Boot instances can read the same session ID from browser cookies.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant A as Spring Boot Node A
    participant R as Redis Sessions
    participant C as Spring Boot Node B
    B->>A: Login / request
    A->>R: Create session and attributes
    A-->>B: Set-Cookie with session ID
    B->>C: Subsequent request with cookie
    C->>R: Read session by ID
    R-->>C: Session attributes
    C-->>B: Session-aware response
~~~

Redis holds **active sessions**; account profiles, password hashes, payment histories, and ownership records belong in the database or identity provider. If a session key expires or vanishes, you cannot treat it as a cache miss and silently reconstruct authenticated login state the way you reload a product.

### 4.1. Spring Boot MVC and HttpSession

Add **Spring Session Data Redis**, the Redis starter, and connection settings matching your Spring Boot version. Example:

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379

server:
  servlet:
    session:
      timeout: 30m
~~~

When Spring Session Redis is properly auto-configured for the Servlet stack, controllers can use **`HttpSession`**:

~~~java
package example.integration.redis;

import jakarta.servlet.http.HttpSession;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class SessionDemoController {
    @GetMapping("/session/visits")
    public int visits(HttpSession session) {
        Integer visits = (Integer) session.getAttribute("visits");
        int next = visits == null ? 1 : visits + 1;
        session.setAttribute("visits", next);
        return next;
    }
}
~~~

This applies to **Spring MVC/Servlet**. For **Spring WebFlux**, use **`WebSession`** and reactive Spring Session. For stateless REST APIs using self-verifying tokens, server-side sessions may be unnecessary.

### 4.2. TTL, Cookies, and Security

- Session timeouts typically track inactivity; **Spring Session** manages its keys and expirations automatically. Never modify Spring Session key TTLs with generic cache cleanup scripts.
- Protect session cookies with **`Secure`**, **`HttpOnly`**, appropriate **`SameSite`**, TLS, and CSRF controls matching your authentication model.
- Upon login or privilege elevation, rely on Spring Security for **session fixation protection**, session ID rotation, or invalidation.
- Store only minimal session attributes; avoid long-lived tokens, sensitive PII, or large object graphs.
- Across deployments, keep session DTOs and serializers backward-compatible with active sessions.
- If Redis evicts keys or failover drops data, sessions may end before timeout; ensure UX handles re-authentication cleanly.

Never place critical sessions on the same Redis instance as a cache configured with **`allkeys-lru`** without assessing impact. Cache eviction is normal for performance; session eviction prematurely logs users out. Logical Redis DB indexes do not isolate RAM, CPU, or failure domains.

## 5. Redis as a Queue: Pub/Sub, Lists, or Streams?

Redis offers multiple messaging primitives with **very different reliability guarantees**:

| Mechanism | When Consumer Is Offline | Ack / Recovery | Best Fit |
| --- | --- | --- | --- |
| **Pub/Sub** | Published messages are missed | No built-in ACK or replay | Ephemeral real-time signals where persistence is optional |
| **List + LPUSH/BRPOP** | Unpopped items stay in the list while Redis retains data | Popping before worker crash loses the task | Simple queues with low reliability demands |
| **List + BLMOVE** | Atomically moves tasks from ready to processing | Must build ACK, timeouts, and reclaim yourself | Small custom queues needing explicit failure control |
| **Redis Streams** | Records remain per retention/persistence | Consumer groups, PEL, `XACK`, claiming pending | Asynchronous jobs needing retries and replay |
| **Sorted Set** | Entries wait until scheduled timestamp | Must build claim/ACK and worker sync | Lightweight delayed queues |

**Pub/Sub is not a durable queue:** offline subscribers miss messages. **`BRPOP` is not an ACK:** items leave the List as soon as a worker pops them, before processing completes. **Streams support pending tracking and ACKs, yet do not guarantee exactly-once by default.**

### 5.1. Pub/Sub

~~~bash
# Client subscribes
SUBSCRIBE inventory-updates

# Another client publishes signal
PUBLISH inventory-updates "SKU-42 changed"
~~~

Connected subscribers receive signals to refresh data from the source of truth. Disconnected subscribers do not have missed messages buffered per subscriber. Therefore, if using Pub/Sub for cache invalidation, pair it with TTLs or periodic refreshes to converge after downtime.

### 5.2. Lists and Worker Crash Limits

~~~bash
LPUSH jobs:email email-1001
BRPOP jobs:email 0
~~~

If a worker pops **email-1001** and crashes before sending the email, the item is gone from the list. Using **`BLMOVE`** atomically moves tasks from a ready list to a processing list before deletion on completion, yet you must build a sweeper to reclaim timed-out tasks, retry limits, DLQs, and idempotency.

### 5.3. Redis Streams and Consumer Groups

An email worker can use Streams to retain records until processing succeeds and **`XACK`** runs:

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant S as Redis Stream
    participant W1 as Worker A
    participant W2 as Worker B
    participant E as Email Provider
    O->>S: XADD jobId=email-1001
    W1->>S: XREADGROUP email-workers
    S-->>W1: Record ID = 1700000000000-0
    W1->>E: Send email
    Note over W1: Crashes before XACK
    W2->>S: XAUTOCLAIM expired pending
    S-->>W2: Same record
    W2->>E: Retry with same idempotency key
    W2->>S: XACK after completion
~~~

Redis CLI example:

~~~bash
# Create stream and consumer group if they do not exist.
# ID 0 allows the group to read pre-existing records.
XGROUP CREATE jobs:emails email-workers 0 MKSTREAM

# Producer appends a record.
XADD jobs:emails * jobId email-1001 orderId order-42 template order-created

# Read new records not yet delivered to the group.
XREADGROUP GROUP email-workers worker-1 COUNT 10 BLOCK 2000 STREAMS jobs:emails >

# After completion, ACK using the actual received record ID.
XACK jobs:emails email-workers 1700000000000-0

# Inspect pending records.
XPENDING jobs:emails email-workers

# Claim records idle over 60 seconds (Redis 6.2+).
XAUTOCLAIM jobs:emails email-workers worker-2 60000 0-0 COUNT 10
~~~

ID **`0`** at group creation starts from existing records; **`$`** starts only from newly arriving records. With **`XREADGROUP ... >`**, workers fetch records **never yet delivered to the group**. Delivered but unacknowledged records sit in the **pending entries list (PEL)** and must be explicitly read/claimed rather than repeatedly polling **`>`**.

**`XACK` only clears pending state for that consumer group; it does not delete records from the stream.** **`XTRIM`/`XDEL`** or retention rules must account for slow consumers and pending entries; trimming an entry still referenced in the PEL leaves an ID with no payload left to reprocess.

### 5.4. At-Least-Once and Idempotency

With proper pending recovery, Streams operate under **at-least-once processing**, meaning **a record can be processed more than once**:

1. Worker calls the email/payment API successfully.
2. Worker crashes before `XACK`.
3. Another worker reclaims the same record.
4. Without deduplication, the side effect repeats.

Never use the Redis stream ID as the unique business identifier if an outbox event can be republished as a **new entry** with a new stream ID. Embed a stable **`jobId`/`eventId`** in the payload and enforce consumer/provider idempotency.

Example database table recording processed events:

~~~sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(80) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

With local DB transactions, insert `eventId` and update business tables inside the **same transaction**. ACK if the transaction commits; on rollback, leave the record pending for retry. For external HTTP side effects, DB transactions cannot roll back a remote API call; use provider idempotency keys or status queries after timeouts.

A Redis lock like **`SET key value NX EX`** reduces short-term duplicates, yet TTL expiration or Redis data loss can still permit repeats. It never replaces durable idempotency when duplicates carry severe business consequences.

## 6. Spring Boot: Writing Jobs to Redis Streams

Spring Data Redis exposes Stream operations via **`RedisTemplate.opsForStream()`** and listener containers. Producer example:

~~~java
package example.integration.redis;

import java.util.Map;
import java.util.UUID;
import org.springframework.data.redis.connection.stream.RecordId;
import org.springframework.data.redis.connection.stream.StreamRecords;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class EmailJobPublisher {
    private final StringRedisTemplate redis;

    public EmailJobPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public RecordId enqueue(String orderId, String jobId) {
        return redis.opsForStream().add(
                StreamRecords.string(Map.of(
                        "jobId", jobId,
                        "orderId", orderId,
                        "template", "order-created"))
                        .withStreamKey("jobs:emails"));
    }
}
~~~

**`jobId`** is supplied by the caller so it stays stable across retries. For standalone tasks, a UUID can be generated at task creation. If the job stems from a PostgreSQL order and event loss is unacceptable, **never call `XADD` directly and assume it commits atomically with the database**.

### 6.1. Transactional Outbox When Combining DB and Redis

~~~mermaid
flowchart LR
    A["POST /orders"] --> T["PostgreSQL transaction"]
    T --> O["orders"]
    T --> X["outbox_event"]
    X --> P["Outbox publisher"]
    P --> S["Redis Stream"]
    S --> W["Idempotent consumer"]
~~~

Write **`orders` + `outbox_event`** in one DB transaction; a publisher reads the outbox and calls **`XADD`**. If the publisher crashes after `XADD` before marking published, it republishes the **same `eventId`**, and the consumer deduplicates by `eventId`.

Consumers can use **`StreamMessageListenerContainer`** or poll groups directly. Processing outline:

~~~text
readGroup(stream, group, consumer)
for each record:
    try:
        processIdempotently(record.jobId, record.payload)
        ack(stream, group, record.streamId)
    catch transientFailure:
        leavePendingForBoundedRetryAndReclaim()
    catch permanentFailure:
        saveDeadLetterWithReason()
        ackOnlyAfterDeadLetterSafelyRecorded()

periodically:
    inspectPendingAndClaimExpiredRecords()
~~~

This is pseudocode, not built-in `RedisTemplate` methods. Real implementations need consumer group lifecycle management, properly timed ACKs, backoff retries, dead-letter streams or tables, retry caps, lag tracking, and PEL monitoring. Never promise "exactly-once" merely because Streams are used.

## 7. Comparing Redis Streams with Dedicated Brokers

Redis Streams fit moderate integration queues well, though not every messaging problem belongs in Redis.

| Criterion | Redis Streams | RabbitMQ | Kafka |
| --- | --- | --- | --- |
| Model | Stream + consumer group + PEL | Queue/exchange, ACKs, and routing | Partitioned event log + consumer offsets |
| Replay | Yes, while entries remain under retention | ACKed messages are normally removed | Per topic retention policy |
| Worker retries | App-built pending/claim and retry logic | ACK/requeue/DLX with broker retry policies | Consumer/topic retries, per-partition lag |
| Ordering | Increasing stream IDs; parallel consumers may finish out of order | Depends on queue, concurrency, requeues | Ordered within a single partition |
| Operations | PEL, trimming, AOF, memory, failover | Queue depth, prefetch, consumers, broker | Partitions, retention, replication, lag |
| When to choose | Queues fitting Redis capacity with app-managed ACK/idempotency | Complex routing or broker-managed worker queues | Long-retention event logs, replay, many consumer groups |

No broker alone guarantees exactly-once HTTP or database side effects. Producer confirmations, persistence, replication, consumer ACKs, and business idempotency determine actual guarantees.

## 8. Managing TTL, Eviction, and Retention

Three concepts to keep separate:

- **TTL:** expiration lifetime of a **key**, typically for caches, sessions, and short-term counters.
- **Eviction:** Redis proactively dropping keys upon hitting memory limits per policy, possibly before TTL.
- **Stream trimming/retention:** discarding **Stream entries** to bound stream size, independent of consumer group ACKs.

| Policy | Impact |
| --- | --- |
| **`noeviction`** | Once `maxmemory` is reached, memory-allocating writes fail with errors; safer when critical data must not be silently dropped, provided write failures are handled |
| **`allkeys-lru` / `allkeys-lfu`** | Evicts any key via approximate LRU/LFU; good for caches, dangerous for sessions/messages |
| **`volatile-lru` / `volatile-ttl`** | Considers only keys with TTLs; sessions normally have TTLs too, so they remain eligible for eviction |

Mixing caches, sessions, and Streams on one instance creates contention: caches filling RAM can evict sessions or make `XADD` fail. **Redis logical DB indexes do not isolate memory, CPU, permissions, or instance-wide failures.** Redis Cluster also supports only database 0. When workloads have differing criticality, separate instances/clusters with dedicated resource caps, ACLs, and alerts.

## 9. Configuration and Key Design

Sample Spring Boot connection configuration:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

Timeouts are illustrative. Production requires TLS, ACLs, secret management, and network isolation; never embed passwords in source code or expose public Redis endpoints.

Key conventions:

~~~text
shop:prod:cache:product:v2:SKU-42
shop:prod:counter:product:SKU-42:views
shop:prod:jobs:emails
shop:prod:dedup:email:email-1001
~~~

**Spring Session** owns its own key namespace and schema; never run generic prefix-scan scripts that sweep session keys. Keep emails, tokens, and sensitive data out of keys and logs. When cache DTOs evolve, version keys or implement backward-compatible serializers. Default Java native serialization in some Redis setups is unsafe for untrusted data; choose workload-appropriate serializers.

## 10. Coordination Failures Across PostgreSQL, HTTP, and Redis

### 10.1. DB Commits, Cache Eviction Fails

~~~text
T1: UPDATE product set price=100
T2: PostgreSQL COMMIT succeeds
T3: DEL product-cache fails
=> Redis retains old price until TTL or later invalidation.
~~~

Deleting cache before commit is also risky: another read misses and reloads the old price before commit, repopulating stale data. Critical paths need post-commit invalidation, versioned keys, or retryable sync mechanisms.

### 10.2. DB Commits Before XADD Executes

~~~text
T1: order COMMIT succeeds
T2: Process crashes
T3: jobs:emails XADD never runs
=> Order exists without an email job.
~~~

The standard remedy is a transactional outbox in the source DB, retrying publishers, and idempotent consumers. **`@Transactional`** on a Spring service never merges PostgreSQL and Redis into one atomic local transaction.

### 10.3. Worker Calls Remote API Successfully, Then Loses ACK

~~~text
T1: XREADGROUP fetches email-1001
T2: Email provider accepts and sends email
T3: Worker dies before XACK
T4: Another worker XAUTOCLAIMs the same record
=> Must deduplicate via business key/provider idempotency.
~~~

If the provider lacks idempotency keys, track delivery states, query status before retrying, and design uncertain-outcome handling. Never assume "timeout means the remote API never executed."

## 11. Role-Specific Testing

### 11.1. Data Store

1. Concurrent clients **`INCR`** one key; verify zero lost increments under normal operation.
2. Restart Redis with production-matching RDB/AOF settings; measure potential loss and recovery time.
3. Fail over primary/replica under active writes; verify how the app handles counter regressions or write retries.
4. Test memory limits, backups, restores, and command errors.

### 11.2. Cache

1. Miss → query DB and set TTL; hit → skip DB.
2. Update DB and re-read; verify staleness windows and invalidation.
3. Simulate Redis disconnect / cache stampede; confirm fallbacks do not overload the DB.
4. Change serializer/DTO schema during rolling deploy; verify old keys decode or invalidate safely.

### 11.3. Session

1. Log in via Node A, send next request with the same cookie to Node B, verify session persists.
2. Logout, session timeout, and revocation invalidate the session.
3. Redis restart/failover; verify whether sessions survive or drop within expected RPO.
4. Test cookie flags, session fixation protection, and serializer compatibility.

### 11.4. Queue

1. Producer `XADD`s; consumer group reads and `XACK`s after processing.
2. Kill worker before ACK; test **`XPENDING`/`XAUTOCLAIM`** and reprocessing.
3. Publish the same `eventId` twice; verify the business side effect occurs once.
4. Create groups with **`0`** vs. **`$`** to prove backlog behavior.
5. Feed a poison message; verify dead-lettering without infinite retries.
6. Test stream trimming with active PEL entries, Redis restarts, memory pressure, and consumer lag.
7. With outbox, crash between DB commit, `XADD`, and marking published; confirm no event intent is lost.

Integration tests can use real Redis via Testcontainers alongside a PostgreSQL test container when testing outboxes. Mocked unit tests validate orchestration code, yet cannot prove Redis PELs, TTLs, failover, or persistence.

## 12. Monitoring and Operations

| Role | Metrics to Track |
| --- | --- |
| Data store | Persistence failures, replica lag, RDB/AOF status, write errors, backup age |
| Cache | Hit/miss ratio, `evicted_keys`, Redis latency, DB fallback traffic, stale-data incidents |
| Session | Active session count, expirations, read/write failures, abnormal logout spikes during failover |
| Streams | Stream length, consumer group lag, pending count, oldest pending age, claims/retries/DLQ, processing latency |
| Infrastructure | `used_memory`/`maxmemory`, blocked clients, connection pools, CPU, network, TLS/ACL errors |

A short stream length does not mean a queue is healthy if pending entries stay stuck. An HTTP 200 response does not prove an email was delivered. Alert on **end-to-end job completion latency**, not solely Redis ping/uptime. Attach **`eventId`/`jobId`**, correlation IDs, and trace IDs to reconcile pipelines without logging secrets or PII.

## 13. Decision Flow for Choosing Redis on a New Feature

~~~mermaid
flowchart TD
    A["Does this value have another source<br/>to rebuild from if lost?"] -->|Yes| B["Cache: TTL + invalidation + fallback"]
    A -->|No| C{"Is this an expiring<br/>login session?"}
    C -->|Yes| D["Spring Session Redis<br/>expiry + security + HA"]
    C -->|No| E{"Is this a job/message<br/>needing worker ACK?"}
    E -->|Yes| F["Redis Streams / broker<br/>ACK + retry + dedup"]
    E -->|No| G["Evaluate Redis as data store<br/>persistence + RPO/RTO"]
~~~

Before implementation, answer:

1. **If the key vanishes, can it be rebuilt?** If not, what are the RPO, backup, and recovery plans?
2. **Who owns the authoritative data?** Redis, PostgreSQL, identity provider, or another service?
3. **What is the lifetime and expiration semantics?** Cache TTL, session idle timeout, stream retention, or business deadline?
4. **What if the task runs twice?** Do we need unique constraints, idempotency keys, deduplication, or reconciliation?
5. **How does the app react if Redis is slow or fails?** Fallback, fail-closed, bounded retry, or error response?
6. **Which metrics prove business correctness?** Cache staleness, session validity, backlog age, RPO/RTO, DLQ?

## 14. Misconceptions to Avoid

**"Redis is fast, so all data should move to Redis."** Speed does not replace querying, transactions, auditing, backups, and durability of the primary datastore.

**"Caches with TTLs are never stale."** Values can stay stale for the entire TTL if origin data changes and invalidation fails.

**"Redis sessions are just caches; early eviction is fine."** Evicting active sessions logs users out prematurely, hurting both security and UX.

**"Pub/Sub and Streams are identical queues."** Pub/Sub lacks replay for offline clients; Streams persist records with groups, pending tracking, and ACKs per retention.

**"`BRPOP` guarantees the worker finished processing."** Popping from a List before completion loses tasks if the worker crashes.

**"`XACK` deletes the record."** ACK only clears pending state for a group; deleting entries requires separate retention/trimming.

**"Redis Streams guarantee end-to-end exactly-once."** Workers can perform work and crash before ACK, causing redelivery; side effects must be idempotent.

**"AOF and replicas guarantee zero lost writes."** Async fsync and replication still have data-loss windows; test failover and restores.

**"`@Transactional` rolls back both PostgreSQL and Redis."** Normally it governs only one resource boundary; integration flows need outboxes, idempotency, or compensation.

**"One Redis instance can freely share caches, sessions, and queues."** Those three workloads contend for RAM, CPU, network, eviction, and failure domains. Plan isolation and capacity.

## 15. Production Checklist

- Classify keys as **data store / cache / session / queue**, documenting the source of truth and data-loss behavior.
- Enforce namespaces, schemas/versions, serializers, and sensitive-data contracts; block unbounded user-driven keys.
- Configure RDB/AOF, replication, backups, RPO/RTO, and restore drills matching criticality.
- Pick suitable `maxmemory`/eviction policies; consider isolating caches, sessions, and queues.
- Caches enforce TTLs, post-commit invalidation, fallbacks, and stampede protection.
- Sessions enforce timeouts, secure cookies/TLS/CSRF/security, multi-node tests, and logout/revocation.
- Queues implement ACKs, pending reclaim, backoff retries, DLQs, retention, and business idempotency.
- DB + messaging use transactional outbox when event intent must commit alongside business state.
- Monitor hit ratios, evictions, persistence, session errors, stream lag, pending age, and DLQ counts.
- Rehearse Redis loss, failovers, worker crashes after side effects, and work recovery.

## References

- [Redis Documentation — Data Types](https://redis.io/docs/latest/develop/data-types/)
- [Redis Documentation — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis Documentation — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis Documentation — Streams](https://redis.io/docs/latest/develop/data-types/streams/)
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Spring Session — Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html)
- [Spring Boot Reference — Redis](https://docs.spring.io/spring-boot/reference/data/nosql.html)

**Takeaway:** Redis is one technology capable of serving four distinct roles with different contracts. **Data stores** must define primary durability; **caches** accelerate reads while accepting misses and staleness; **sessions** hold time-bounded authentication state; **queues** demand ACKs, retries, retention, and deduplication. In Spring Boot Integration, source-of-truth boundaries and recovery workflows determine whether a Redis design is truly reliable.
