# Applying Cache-Aside and Handling Cache Stampedes

In an e-commerce application, a product detail page may be read thousands of times per second while prices, stock, or descriptions change only a few times a day. If every HTTP request calls Azure SQL Database or Azure Cosmos DB, the database easily becomes overloaded during peak traffic. **Caching** serves repeated reads from fast memory, cutting latency and load on the authoritative data store. However, caching also introduces new failure modes: data can grow stale, keys can expire simultaneously, and when the cache is cold, a flood of requests can hit the database at the same instant.

**Cache-aside** (*lazy loading*) is a strategy where the application checks the cache before reading the authoritative source and populates the cache on a miss. A **cache stampede** (*thundering herd*) happens when many concurrent requests miss the same hot key or group of keys simultaneously and all query the backend or recompute expensive data together. Knowing how to implement cache-aside is only the first step; knowing how to prevent stampedes while preserving **data correctness, availability, and cost** is what production systems require.

This lesson belongs to the **Caching and Real-time Communication** chapter of the **CLOUD_PROVIDERS_AZURE** module. Examples connect Java/Spring Boot, Redis on Azure, Azure SQL or Cosmos DB, Azure Container Apps/AKS, Microsoft Entra ID, VNet/Private Endpoint, Azure Monitor, and Cost Management. Concepts are illustrated with a Redis-compatible cache, though the design patterns apply broadly to other distributed caches with similar capabilities.

> **Product scope:** Azure offers managed Redis options such as **Azure Managed Redis** as well as existing **Azure Cache for Redis** environments. SKU names, identity-based authentication mechanisms, clustering, replication, Private Endpoint support, and product lifecycles may change. For new deployments or legacy migrations, verify the **supported service/region/SKU and official lifecycle notices**. Illustrative commands and code must be adapted to the SDK, Redis protocol, and service approved by your organization.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain when caching accelerates a system and why the cache **is not the authoritative data source** in the cache-aside model.
2. Describe the **cache hit, cache miss, database load, and cache populate** flow alongside **database write followed by cache invalidation**.
3. Identify a **cache stampede** and distinguish it from *cache avalanche*, *cache penetration*, and *hot keys*.
4. Choose TTL, jitter, negative caching, soft/hard TTL, and refresh-ahead based on data characteristics.
5. Implement **singleflight/request coalescing** inside a single JVM and understand its limits across multiple pods/instances.
6. Design a **per-key distributed lock/lease** in Redis with tokens, expiration, and atomic release, while understanding why a lock alone cannot guarantee business correctness.
7. Analyze races between cache reads, database updates, and cache invalidation; evaluate versioning, events/outbox, and safeguards against stale overwrites.
8. Write a Java example using Spring Data Redis and a database repository for cache-aside.
9. Set up metrics, alerts, controlled load tests, Redis failure runbooks, and security policies.
10. Estimate impacts on backend throughput, latency, availability, and total cost.

## 2. Why cache?

Suppose an API returns product profiles:

- Direct database reads average **25 ms** in a test environment.
- Reading from Redis takes **2 ms** under the same network conditions.
- Traffic is **5,000 GET/s**, with 90% repeatedly accessing popular products.

If every GET hits the database, the backend receives nearly 5,000 reads/s. With a 90% cache hit rate where hits bypass the database, the backend receives roughly **500 reads/s** for this path (excluding refreshes, retries, and other work).

| Signal | Without cache | 90% cache hit (illustrative) |
|---|---:|---:|
| HTTP GETs per second | 5,000 | 5,000 |
| Database reads per second | 5,000 | Roughly 500 |
| Latency on cache hit | Not applicable | Roughly 2 ms for cache lookup |
| Stale data risk | Depends on DB/replication | Yes, if TTL/invalidation is wrong |
| Additional failure point | No Redis | Redis/network/client pool |

These numbers describe a **hypothetical workload**; actual latency varies by region, serialization, TLS, payload size, network, and DB query complexity. Even a cache with a high hit ratio can fail its SLO if every miss wave overwhelms the database.

### Putting caching in the right place

Caching helps when data is:

- Read far more often than written.
- Reused across many requests.
- Expensive to compute or query from the source.
- Able to tolerate clearly defined staleness.
- Looked up by simple, stable keys.
- Compliant with privacy requirements when stored outside the source data store.

**Never use caching to mask an unindexed query or a broken consistency model** without understanding the root cause. A cache is an optimization layer in front of the database, not a replacement for schema, index, or query tuning.

## 3. Comparing caching patterns

| Pattern | How data is loaded | How writes work | Characteristics |
|---|---|---|---|
| **Cache-aside** | App reads cache; on miss, reads DB and populates cache | DB is primary; app invalidates/updates cache | Simple, fine-grained control per use case |
| **Read-through** | Cache layer invokes loader automatically on miss | Depends on implementation | Less loading boilerplate in app, requires cache support |
| **Write-through** | Writes go through cache layer, updating source synchronously | Cache and source coordinate | Requires understanding atomicity/failure semantics |
| **Write-behind / write-back** | Cache accepts write first and flushes to source later | Asynchronous | Risk of data loss or lag if cache fails |
| **Local in-process cache** | Each process holds its own copy | Cross-process invalidation is harder | Very low latency, but memory and coherence are complex |
| **Distributed cache** | Multiple app instances share Redis/cache | Shared protocol | Shared state, adds a network dependency |

This lesson chooses **distributed Redis cache-aside**. For a Java service running across multiple AKS or Azure Container Apps replicas, a shared Redis backend avoids every pod maintaining completely isolated caches. However, **each pod still has local threads and connection pools**, so stampedes can happen at two levels: within a single pod and across multiple pods.

## 4. Cache-aside: standard read flow

~~~mermaid
sequenceDiagram
  participant U as Client
  participant A as Java API
  participant R as Redis cache
  participant D as Database
  U->>A: GET /products/42
  A->>R: GET catalog:tenant-A:42
  alt Cache hit
    R-->>A: Serialized Product
    A-->>U: 200 Product
  else Cache miss
    R-->>A: Nil
    A->>D: SELECT Product by tenant + id
    D-->>A: Product v3
    A->>R: SET key Product v3 EX TTL
    A-->>U: 200 Product
  end
~~~

Basic read algorithm:

~~~text
function getProduct(tenantId, productId):
    key = makeCacheKey(tenantId, productId)

    cached = redis.GET(key)
    if cached is valid:
        return deserialize(cached)             // cache hit

    product = repository.findByTenantAndId(...) // cache miss

    if product exists:
        redis.SET(key, serialize(product), TTL)
    else:
        redis.SET(key, NOT_FOUND_SENTINEL, shortTTL)  // optional

    return product
~~~

### Key details

- **The database is the source of truth**; the cache can be cleared and rebuilt.
- **TTL is not technically mandatory** for every cache-aside use case, but is typically used to bound staleness and memory.
- Never inadvertently serialize ORM entities containing lazy proxies, circular references, or secret fields. Use **explicit-schema DTOs**.
- Writing to the cache after a DB read can fail; the app needs a clear policy on whether to still return the DB result.
- If Redis returns network errors, enforce a **bounded fallback** or fail fast per business rules; never treat cache errors as routine misses that let full traffic crush the database.
- You cannot infer cache hit rates from HTTP 200 status codes; instrument cache lookups explicitly.

## 5. Cache-aside: write and invalidation flow

For mutable data, the intuitive flow is:

~~~text
function updateProduct(command):
    validate authorization and business rules
    database.TRANSACTION:
        update product
        increment productVersion
    COMMIT
    cache.DELETE(productKey)  // invalidate after DB commit
    return updated product
~~~

Why **write to the database first, then delete the cache**?

1. The DB is the source of truth, so the commit must succeed before declaring the write successful.
2. Deleting the cache beforehand when the DB update fails creates unnecessary cache misses.
3. Deleting after commit gives the next GET an opportunity to load the fresh value.

Still, this **does not guarantee a linearizable cache**. A concurrent GET can read old data from the DB right before the update commits, then write that stale value back to the cache right after the writer deletes the key. We analyze that race later.

### Invalidate or update the cache?

| Strategy | Pros | Risks |
|---|---|---|
| **Invalidate on write** | Easy to operate; next request loads authoritative data | Miss bursts; races with loaders; extra read cost |
| **Update cache on write** | Fresh data available immediately on write | Write-ordering races; failed cache updates; mismatched serialization |
| **Versioned cache key** | Reduces risk of old versions overwriting new ones | Needs reliable version lookup; old keys linger until TTL |
| **Event-based invalidation** | Useful when multiple services update shared data | Delivery lag/duplicates/loss; requires outbox/idempotency |

For workflows needing **strictly accurate live prices or transaction quotas**, many operations must **read the DB directly or use proper versioning/conditional checks** rather than blindly trusting a cached entry.

## 6. Using Redis on Azure

A typical architecture:

~~~mermaid
flowchart LR
  U["Clients"] --> G["APIM / Ingress"]
  G --> API["Java API: AKS / Container Apps"]
  API --> C["Azure-managed Redis cache over private network"]
  API --> DB["Azure SQL / Cosmos DB"]
  API --> MON["Azure Monitor / Application Insights"]
  C --> MON
  DB --> MON
  OPS["Entra ID / Key Vault / RBAC"] -.-> API
~~~

Components to define:

- **VNet/Private Endpoint or network access path** matching the Azure Redis service/SKU.
- **TLS and hostname validation** in the Redis client.
- **Authentication/authorization** via mechanisms supported by the product version/SKU; managed identity/Entra ID where supported, or credentials managed in Key Vault.
- **Client pooling and timeouts** to limit connections and prevent hung requests.
- **HA/replication/failover** behavior and client reconnection timing.
- **Memory capacity, eviction policy, and persistence** as needed within supported features.
- **Metrics/alerts**, DB backup strategy, and cost tagging.

### Redis is an acceleration layer, not a durable store of record

Managed caches may offer persistence/replication options, yet under cache-aside **never treat Redis as the sole store for orders or payment state**. If the entire cache is lost, the app must have a warm-up plan and protect the backend from sudden cache miss storms.

### Do not confuse Azure Managed Redis with Azure Cache for Redis

Both may exist in an organization depending on timeline and migration status. ARM resource types, CLI commands, tiers, private networking, Entra auth mechanisms, and lifecycle timelines **are not necessarily identical**. Avoid applying commands from one service blindly to the other. For new projects, verify Azure's recommended option at deployment time along with internal policy.

## 7. Designing safe, stable cache keys

A manageable key pattern:

~~~text
catalog:prod:tenant-A:product:42:v1
~~~

Broken down:

- `catalog`: domain.
- `prod`: environment if environments ever share a cache (resource-level isolation is usually preferable).
- `tenant-A`: tenant boundary in multi-tenant setups.
- `product`: entity type.
- `42`: business ID.
- `v1`: version of the **cache key/value schema**, not necessarily the item version.

### Design rules

1. **Never build keys directly from unvalidated raw URLs/headers**; enforce length and character limits.
2. Include tenant/security scope whenever data varies by caller.
3. Never place tokens, card numbers, passwords, raw emails, or PII in keys.
4. If keys involve sensitive IDs, consider hashing/HMAC or opaque namespaces.
5. Canonicalize consistently: casing, Unicode normalization, URL encoding, and ID formatting.
6. Bump a key version or migrate cleanly on breaking cache value schema changes.
7. Never use a **single global key** for tenant-specific data.
8. Separate data keys, lock keys, and metadata keys to prevent accidental deletion.

### Cache key cardinality

If every request generates a fresh UUID key, hit ratio nears 0 and the cache wastes RAM. Effective caching requires **reuse**; for search results with dozens of parameters, canonicalize queries, respect data permissions, and limit cached variants.

## 8. Choosing TTL from freshness requirements

**TTL (Time To Live)** is how long a key remains valid before expiring under Redis semantics. Long TTLs:

- Increase cache hit ratio.
- Reduce database queries.
- Increase stale-data risk if invalidation fails.

Short TTLs:

- Lower maximum staleness in most cases.
- Increase miss rate and backend load.
- Can trigger stampedes more frequently.

Examples for discussion:

| Data | Acceptable staleness | TTL guidance |
|---|---|---|
| Product catalog/descriptions | A few minutes if invalidated | Several minutes; measure in practice |
| Display inventory | A few seconds per business rules | Short; transactions still check DB |
| Checkout-time pricing | Strict correctness required | Never rely solely on cache |
| Infrequently changing config | Longer with event invalidation | Moderate + refresh on change |
| Not-found results | Only very brief stale-negative tolerance | Short negative TTL |
| Public reference data | Rarely changes, versioned | Long TTL + versioned key |

**Never treat TTL as an absolute freshness SLA** if backend updates or invalidation events can lag. TTL bounds part of storage time, while races, replication, and stale-serving policies also contribute.

### Setting TTL properly

~~~text
SET catalog:prod:tenant-A:product:42:v1 "{...json...}" EX 600
~~~

This illustrative Redis command stores the key for **600 seconds**. Redis-compatible systems vary in behavior by configuration and client; verify version command support. Avoid TTL-less `SET` calls for mutable data without guaranteed lifecycle/invalidation.

## 9. What is a cache stampede?

Suppose a highly popular product receives 3,000 GET/s. All prior requests hit the cache. At exactly 12:00:00, the key expires:

~~~mermaid
sequenceDiagram
  participant R as 3,000 concurrent requests
  participant A as API replicas
  participant C as Redis
  participant D as Database
  R->>A: GET hot product
  A->>C: GET product:42
  C-->>A: Nil (TTL expired)
  par Workers miss simultaneously
    A->>D: SELECT product 42
    A->>D: SELECT product 42
    A->>D: SELECT product 42
  end
  D-->>A: Product
  A->>C: SET product:42
~~~

If loading takes 40 ms, roughly **120 requests** arrive for that hot key during the miss window (3,000 × 0.040). If contention slows the backend down to 500 ms, concurrent waiting requests jump to around **1,500**. These numbers assume steady traffic; actual concurrency depends on scheduling, cache round-trips, and timeouts.

**Essence:** many requests perform **redundant reload work simultaneously**, slowing the backend, widening the miss window, and amplifying load.

### When stampedes happen

- A hot key's TTL expires.
- A cache node restarts or fails over and loses part of its keyspace.
- A deployment or schema version bump leaves keys unpopulated.
- Redis eviction drops a hot key due to memory pressure.
- Transient DB/Redis errors prevent earlier populates from succeeding.
- Multiple replicas scale out and hit a new key concurrently.

## 10. Comparing stampede, avalanche, penetration, and hot keys

| Phenomenon | Cause | Example | Primary mitigation |
|---|---|---|---|
| **Cache stampede** | Many requests concurrently recompute the same expensive key | Top product TTL expires | Singleflight, per-key lease, stale-while-revalidate |
| **Cache avalanche** | Huge numbers of keys expire or vanish simultaneously | 100,000 keys created together with 600s TTL | TTL jitter, warm-up, traffic partitioning, load shedding |
| **Cache penetration** | Continuous requests for nonexistent keys | Bot scanning random product IDs | Negative caching, validation, rate limiting, Bloom filter if apt |
| **Hot key** | One key receives extreme request volume | Featured banner/product | Local cache, sharding/replication if supported, throttling |
| **Hot partition / backing DB** | Skewed data distribution | One tenant consumes nearly all RU/s | Partition key design, not just caching |

These issues can overlap. A hot key is a **prime trigger for stampedes**, though being a hot key does not itself mean a cache miss. TTL jitter helps prevent **many keys expiring together**, but **is not enough** when thousands of requests miss **one single key**.

## 11. Strategy 1 — Singleflight inside a JVM

**Singleflight** (also called *request coalescing*) lets concurrent threads requesting the **same key** share one load operation rather than each calling the DB.

~~~text
GET product:42 -> miss
  Request A (leader) -> load DB once -> populate Redis
  Request B (follower) -> await result from A
  Request C (follower) -> await result from A
  Request D (follower) -> await result from A
~~~

### Algorithm

1. Check the Redis cache.
2. On a miss, look up an **in-flight future** by key in-process.
3. If present, wait on the future with an appropriate timeout.
4. Otherwise become the leader, **re-check the cache**, then load from DB.
5. Complete the future (with result or exception).
6. Remove the in-flight entry with compare-and-remove to prevent memory leaks.
7. Followers receive the result or handle the exception per policy.

### Java: simple singleflight component

Java 17 standalone example illustrating request coalescing. **Production requires max concurrent key bounds, timeouts, and circuit breakers**; this snippet focuses on the core mechanism:

~~~java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ConcurrentHashMap;

public final class SingleFlight {
    private final ConcurrentHashMap<String, CompletableFuture<Object>> inFlight =
        new ConcurrentHashMap<>();

    @SuppressWarnings("unchecked")
    public <T> T run(String key, Callable<T> load) {
        CompletableFuture<Object> mine = new CompletableFuture<>();
        CompletableFuture<Object> existing = inFlight.putIfAbsent(key, mine);

        if (existing != null) {
            // Follower: wait for the leader on the same key.
            return (T) existing.join();
        }

        try {
            // Leader: caller must re-check cache before querying DB.
            T result = load.call();
            mine.complete(result);
            return result;
        } catch (Exception ex) {
            mine.completeExceptionally(ex);
            throw new CompletionException(ex);
        } finally {
            inFlight.remove(key, mine);
        }
    }
}
~~~

### Limitations to understand

- All callers for **the same key must expect the same type**; never mix Java types under one key.
- `join()` can block indefinitely if the loader hangs; production needs timeouts, cancellation, and follower caps.
- If the loader throws, all followers receive the exception; plan budgeted fallbacks/retries.
- Recursive singleflight calls on the **exact same key** inside the loader can deadlock.
- `ConcurrentHashMap` is scoped to **a single JVM**. With 20 pods, you can still have 20 leaders for one Redis key.
- Never use an in-flight map as a transaction synchronizer or exactly-once guarantee.
- If the leader pod terminates abruptly, its in-flight futures vanish; other pods reload on the next miss.

**Takeaway:** singleflight is a low-complexity, effective defense against duplicate work **within each instance**. Pair it with cross-instance coordination if the backend is fragile.

## 12. Strategy 2 — Per-key distributed lease with Redis

Multiple Java replicas do not share a `ConcurrentHashMap`. You can coordinate using a **Redis per-key lock/lease**:

~~~text
data key: catalog:prod:tenant-A:product:42:v1
lock key: lock:catalog:prod:tenant-A:product:42:v1

Replica A: SET lockKey token-A NX PX 5000 -> OK
Replica B: SET lockKey token-B NX PX 5000 -> nil
Replica C: SET lockKey token-C NX PX 5000 -> nil

Replica A: re-check cache -> load DB -> SET data TTL
Replica A: release lock if value == token-A
Replica B/C: bounded wait + retry cache GET -> hit
~~~

This is a **time-bounded lease**, not a permanent lock. The lock TTL must cover typical load durations while still allowing recovery if a worker crashes.

### Why use a random token?

Calling `DEL lockKey` unconditionally in `finally` invites a dangerous bug:

1. A acquires the lock, loads slowly, and the lease expires.
2. B acquires a new lock and begins loading.
3. A finishes late and runs `DEL`.
4. A deletes **B's lock**, allowing C to acquire a concurrent lock.

Every lock holder must use a unique token and release via **atomic compare-and-delete**.

### Redis Lua: releasing only your own lock

~~~lua
-- KEYS[1] = lock key
-- ARGV[1] = unique token of current owner
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
end
return 0
~~~

The client sends this script atomically to the Redis instance/shard owning the key as supported by the server. Never split `GET` and `DEL` into two network round-trips, which reintroduces the race condition.

### Mandatory safeguards

1. Lock **per key**, never one global lock for the whole cache.
2. Re-check the data key **after acquiring the lock**, because another replica may have populated it.
3. Bound DB load duration, lock lease TTL, and follower wait time.
4. When lock acquisition fails, avoid tight busy-waiting; use short bounded backoff with jitter.
5. Account for **two concurrent loaders** if a lease expires or Redis fails over.
6. Never use a Redis lock as the **correctness authority** for payments, inventory deductions, or critical transactions.
7. A failing lock owner should still release if it holds the token; otherwise lease expiry self-heals.
8. Instrument lock contention, wait times, lease expirations, and backend load counts.

### Locks save work—they do not prove freshness

If A's lease expires while reading DB v1, B can acquire a new lock, read v2, and update the cache. When A finishes late and writes v1, a **stale overwrite** occurs. Preventing that requires **versioning/fencing/conditional writes** or source-ordered updates, not just lock token checks.

### Redis replication/failover and distributed locks

Do not assume a Redis cluster using asynchronous replication preserves every lock across a primary failover. If lock state is lost during failover, multiple owners can run simultaneously. For **cache recomputation**, that is usually acceptable if the only side effect is reading the DB and writing version-guarded cache entries; for **critical distributed mutual exclusion**, use stronger consensus-backed primitives.

## 13. Strategy 3 — TTL jitter

**TTL jitter** adds bounded randomness so keys do not expire on the exact same second.

Example:

~~~text
Base TTL = 600 seconds
Jitter   = random integer in [-60, +60]

Actual TTL falls within 540..660 seconds
~~~

Java:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public final class CacheTtl {
    public static Duration withJitterSeconds(long baseSeconds, long jitter) {
        if (baseSeconds <= jitter || jitter < 0) {
            throw new IllegalArgumentException("TTL must remain positive");
        }
        long adjustment = ThreadLocalRandom.current()
            .nextLong(-jitter, jitter + 1);
        return Duration.ofSeconds(baseSeconds + adjustment);
    }
}
~~~

**Fits well:** large batches of keys loaded at the same time with identical TTLs, such as deployments or warm-ups.

**Insufficient alone:** 10,000 requests hitting **a single** key right as it expires. That key still has one expiration timestamp for all readers; combine with singleflight, leases, or stale serving.

Note that jitter must not violate business freshness ceilings. If hard maximum freshness is 600s, use **base 540 + jitter 0..60** rather than allowing 660s.

## 14. Strategy 4 — Soft TTL, hard TTL, and stale-while-revalidate

For read-heavy data that tolerates brief staleness, **stale-while-revalidate** works well:

- **Soft TTL:** when data should be refreshed.
- **Hard TTL:** when stale data may no longer be served.
- Between soft and hard TTL, requests receive the **stale value** immediately while a single worker kicks off an async refresh.

Example:

~~~text
11:00:00   Value v4 is cached
11:04:00   Soft TTL reached
11:04:01   Request A returns v4, triggers one refresh
11:04:02   Request B returns v4, skips duplicate refresh
11:04:03   Refresh reads DB v5 and updates cache
11:10:00   Hard TTL ceiling if refresh never succeeds
~~~

### Envelope stored in Redis

~~~json
{
  "schemaVersion": 1,
  "dataVersion": 5,
  "cachedAt": "2026-11-20T11:00:00Z",
  "softExpiresAt": "2026-11-20T11:04:00Z",
  "hardExpiresAt": "2026-11-20T11:10:00Z",
  "value": {
    "id": "42",
    "name": "Thermos Bottle",
    "priceMinor": 259000
  }
}
~~~

The **physical Redis TTL** can be set to the hard TTL, while application logic evaluates the soft TTL. If refreshes fail, stale serving stops cleanly at the hard TTL limit.

### When must stale data never be served?

- Permission checks, revoked sessions, and access policies.
- Inventory confirmation prior to stock deduction.
- Account balances or payment limits.
- Authoritative checkout pricing.
- Data governed by legal immediacy mandates.

The same entity may allow a few seconds of staleness on a **display** endpoint while the **checkout** endpoint enforces authoritative DB reads/transactions.

### Async refreshes must be bounded

Never spawn an unbounded thread per stale request. Use bounded executors, queues/schedulers, and singleflight/leases. Track refresh failures and prevent thousands of redundant background jobs on hot entries.

## 15. Strategy 5 — Refresh-ahead and prewarming

**Refresh-ahead** proactively refreshes hot keys before expiration based on access patterns or schedules.

One approach:

1. Identify the top-N most accessed keys.
2. Before soft TTL, let one worker/lease holder refresh.
3. On success, store the new value and TTL.
4. On failure, serve stale within hard TTL or follow fallback policy.
5. Cap concurrency and rate so refreshes never create a batch DB spike.

**Prewarming** is useful after deployments, schema version bumps, or recovering an empty Redis instance. Fetch top products from the DB or a curated list and load them progressively.

Do not prewarm every product in the catalog if most are rarely read: you will pay for Redis memory and DB load for unused entries. **Warm the measured hot set** and rate-limit bulk loads.

## 16. Strategy 6 — Negative caching and preventing cache penetration

When clients request nonexistent product IDs, every cache miss hits the DB. A bot scanning millions of random IDs can generate massive DB load without reading any valid record.

**Negative caching** briefly stores "does not exist":

~~~text
GET product:unknown-123
  -> Redis miss
  -> DB NOT FOUND
  -> Redis SET key "NOT_FOUND" EX 15
  -> HTTP 404

Repeated request within 15s
  -> Redis NOT_FOUND
  -> HTTP 404, DB skipped
~~~

### Risks

- A key created right after caching 404 stays hidden until expiry → **stale negative**.
- Confusing a **true 404** with DB timeouts/500s: **never cache backend errors as NOT_FOUND**.
- If every request uses a fresh random ID, negative cache hit rate is zero and memory grows; enforce input validation and rate limits.
- Sentinels must be unambiguously typed so they never collide with valid JSON payloads or legitimate `null` values.
- Access control: never cache "hidden due to missing permission" in a key shared with other tenants or callers.

**Negative TTLs are typically shorter than positive TTLs** and should be invalidated when creating new entities.

### Is a Bloom filter appropriate?

A Bloom filter can short-circuit lookups for IDs guaranteed absent from a known set, but carries **false positives**, requires updates as data changes, and adds memory/operational overhead. It does not replace authorization or authoritative data stores and is unnecessary for many APIs.

## 17. Writing basic Java cache-aside with Spring Data Redis

This example demonstrates **cache-first reads + database fallback + TTL + negative caching + post-commit invalidation**. It assumes a Java 17+ Spring Boot project with Spring Data Redis, Jackson, and a repository implemented for Azure SQL/Cosmos DB. It is an architectural template, **not a runnable standalone Spring Boot app without adding datasources and dependencies**.

### Conceptual Maven dependencies

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
  </dependency>
  <!-- Add Azure SQL or Cosmos DB driver/repository as needed. -->
</dependencies>
~~~

Dependency versions are typically managed by the Spring Boot BOM; pick a Boot version compatible with Java 17. The Redis client can be Lettuce or Jedis per configuration. **Never pick arbitrary dependency versions** or embed account keys in the POM.

### Model and repository

~~~java
package com.example.catalog;

import java.util.Optional;

public record ProductDto(
    String id,
    String tenantId,
    String name,
    long priceMinor,
    long version
) {}

interface ProductRepository {
    Optional<ProductDto> findByTenantAndId(String tenantId, String id);
    ProductDto updatePrice(String tenantId, String id, long newPriceMinor);
}
~~~

`ProductRepository` here is an **illustrative interface**. Production requires implementation via Spring Data JDBC/JPA, Cosmos SDK, or an equivalent repository handling transactions, versions, permissions, and retries. Monetary amounts use minor units per business contract—never arbitrary `double` floats.

### Java service

~~~java
package com.example.catalog;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Duration;
import java.util.Optional;
import java.util.concurrent.ThreadLocalRandom;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public final class ProductCacheService {
    private static final String ABSENT = "__CACHE_NOT_FOUND__";

    private final StringRedisTemplate redis;
    private final ProductRepository repository;
    private final ObjectMapper json;

    public ProductCacheService(
            StringRedisTemplate redis,
            ProductRepository repository,
            ObjectMapper json) {
        this.redis = redis;
        this.repository = repository;
        this.json = json;
    }

    public Optional<ProductDto> find(String tenantId, String id) {
        String key = productKey(tenantId, id);
        String cached = redis.opsForValue().get(key);

        if (ABSENT.equals(cached)) {
            return Optional.empty(); // negative hit
        }
        if (cached != null) {
            return Optional.of(fromJson(cached)); // positive hit
        }

        Optional<ProductDto> result =
            repository.findByTenantAndId(tenantId, id);

        if (result.isPresent()) {
            long jitter = ThreadLocalRandom.current().nextLong(0, 61);
            redis.opsForValue().set(
                key, toJson(result.get()), Duration.ofSeconds(540 + jitter));
        } else {
            redis.opsForValue().set(key, ABSENT, Duration.ofSeconds(15));
        }
        return result;
    }

    public ProductDto updatePrice(
            String tenantId, String id, long priceMinor) {
        // Repository must commit the transaction before returning.
        ProductDto updated = repository.updatePrice(tenantId, id, priceMinor);

        // Invalidate after DB commit. See the race analysis below.
        redis.delete(productKey(tenantId, id));
        return updated;
    }

    private static String productKey(String tenantId, String id) {
        if (!tenantId.matches("[a-zA-Z0-9_-]{1,64}")
                || !id.matches("[a-zA-Z0-9_-]{1,64}")) {
            throw new IllegalArgumentException("Invalid cache key components");
        }
        return "catalog:prod:" + tenantId + ":product:" + id + ":v1";
    }

    private String toJson(ProductDto value) {
        try {
            return json.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Cannot serialize product", ex);
        }
    }

    private ProductDto fromJson(String value) {
        try {
            return json.readValue(value, ProductDto.class);
        } catch (JsonProcessingException ex) {
            throw new IllegalStateException("Invalid cached product JSON", ex);
        }
    }
}
~~~

### What this sample does **not** yet solve

- Stampedes across concurrent requests and multiple replicas.
- Redis/DB timeouts, circuit breakers, fallbacks, and rate limits.
- **Atomic** DB update + cache invalidation (they are not atomic in reality).
- Stale loader overwrites racing after a writer deletes the cache.
- Redis connection failures after DB commit: the write succeeds while invalidation fails.
- Concurrent price updates across multiple services, version conflicts, and reliable invalidation events.
- Serialization/schema migrations, malformed entry repair, and compression.
- Authorization and tenant-isolation checks derived from verified tokens.
- Negative cache invalidation when creating a new product.
- Telemetry, retries, timeouts, metrics, and load testing.

**This is a foundation for learning**, not production-ready financial transaction code. For production, layer in singleflight/per-key leases/stale policies and version protections as required.

## 18. Integrating singleflight into cache-aside

Using the `SingleFlight` class introduced earlier:

~~~java
private final SingleFlight singleFlight = new SingleFlight();

public Optional<ProductDto> findWithSingleFlight(
        String tenantId, String id) {
    String key = productKey(tenantId, id);

    // Read cache first; distinguish positive hit / negative hit / miss.
    CacheLookup<ProductDto> lookup = readCache(key);
    if (lookup.isHit()) {
        return lookup.value();
    }

    return singleFlight.run(key, () -> {
        // Re-check is critical: another leader may have just populated it.
        CacheLookup<ProductDto> second = readCache(key);
        if (second.isHit()) {
            return second.value();
        }

        Optional<ProductDto> source =
            repository.findByTenantAndId(tenantId, id);
        populateWithTtl(key, source);
        return source;
    });
}
~~~

`CacheLookup`, `readCache`, and `populateWithTtl` are **abstractions to implement**: you must distinguish a "negative hit" from a "cache miss". Returning `Optional.empty()` for both will misclassify misses and hits.

### Why does double-checking matter?

Suppose the leader waits 20 ms to enter, during which another replica populates the cache. Without a second cache GET, the leader queries the DB unnecessarily. Double-checking is equally important after acquiring a Redis lock.

### Never block indefinitely

In production, followers need finite timeouts, total request deadline awareness, and safe fallbacks. An HTTP request with a 300 ms SLO cannot wait 10 seconds on a leader's DB query and still meet its SLA. For endpoints that reject stale data, return controlled 503/429 responses rather than overloading downstream dependencies.

## 19. Combining singleflight, Redis leases, and stale serving

A policy for high-traffic data with low mutation frequency:

~~~mermaid
flowchart TD
  A["GET Product"] --> B{"Cache entry still fresh?"}
  B -->|Yes| H["Return fresh"]
  B -->|No| C{"Valid stale entry within hard TTL?"}
  C -->|Yes| S["Return stale fast"]
  S --> REF["Schedule 1 refresh per key"]
  C -->|No| L["Local singleflight per key"]
  L --> D{"Acquire distributed per-key lease?"}
  D -->|Yes| R["Double-check cache then load source"]
  R --> V["Publish version-safe cache value + TTL"]
  V --> OK["Return fresh"]
  D -->|No| W["Bounded wait + jitter + reread cache"]
  W --> E{"Cache now holds valid value?"}
  E -->|Yes| OK
  E -->|No| F["Fallback/503 per SLO, do not flood database"]
~~~

**Do not layer every mechanism unnecessarily.** For moderate traffic, cache-aside + TTL jitter may suffice. With hot keys, add local singleflight. Across many replicas with a constrained DB, evaluate per-key leases. When latency is paramount and brief staleness is acceptable, add soft/hard TTLs and background refresh.

### Fallback when failing to acquire the lease

Intentional options:

1. Sleep briefly with jitter, then re-read the cache.
2. Return stale data if still within hard TTL and permitted by business rules.
3. Use a bounded semaphore limiting direct DB fallback queries.
4. Return 503 or 429 per API contract to protect backend capacity.
5. For async workflows, enqueue a job and return 202 when semantically appropriate.

**Never** let all followers abandon the lock at once and hit the database: that defeats backend protection completely.

## 20. Dangerous race: cache-aside stale overwrite

Consider a key holding v1 while a writer updates it to v2.

~~~text
T1  Reader A: Redis GET -> miss
T2  Reader A: DB SELECT -> v1
T3  Writer B: DB UPDATE -> v2, COMMIT
T4  Writer B: Redis DEL key
T5  Reader A: Redis SET key = v1, TTL 10 min
T6  Reader C: GET -> v1, even though database holds v2
~~~

This is a **read-write race**. The "DB first, delete cache after" rule avoids several common bugs yet **cannot prevent** this interleaving on its own.

### Mitigations by severity

**A. Short TTL + invalidation:** accepts brief staleness for display data; simple to deploy. Insufficient for strict correctness.

**B. Versioned cache envelope:** DB records include reliable `version`/`updatedAt` fields. On cache write, use atomic compare-and-set (such as Redis Lua) so older versions never overwrite newer ones **if a newer version is currently cached**. Also plan for when the key was `DEL`eted (no version present in Redis) to avoid stale repopulation.

**C. Durable generation/version marker:** writers increment a generation or store the version reliably; loaders write only when the version matches. The marker must survive Redis failover/eviction or live in durable storage; otherwise a gap remains.

**D. Per-key coordination for both writers and loaders:** loaders and writers participate in shared locking/versioning. Plain Redis leases still suffer expiry/failover caveats, so never treat them as absolute correctness locks.

**E. Bypass caching on mandatory-truth paths:** checkout, inventory deduction, and settlement read/write the DB using transactions, ETags, or unique constraints.

### Versioning and cache keys

One pattern:

~~~text
product current version in authoritative source: 7
cache data: catalog:tenant-A:product:42:version:7

Reader knowing version 7 -> reads key v7
Writer updates to v8 -> new readers pick key v8
Key v7 expires naturally via TTL
~~~

However, **readers must discover the current version**; querying the DB for the version on every GET erodes cache gains. Reliable metadata updates, CDC/outbox, or a deliberate staleness policy can help. Never treat versioned keys as a zero-cost guarantee before solving version discovery.

## 21. Reliable invalidation with outbox and events

When products are modified across services, you cannot assume every instance always reaches its `DEL` call:

~~~text
DB commit succeeds
    -> application crashes
    -> Redis DEL never runs
    -> cache serves old price until TTL expires
~~~

The **transactional outbox** records change events within the same database transaction. A publisher forwards events to Service Bus/Event Grid/Queues as designed; a cache invalidator consumes events and deletes/refreshes keys.

~~~mermaid
flowchart LR
  W["Product service"] --> DB["DB transaction: Product v8 + Outbox"]
  DB --> P["Outbox publisher"]
  P --> B["Service Bus / event delivery"]
  B --> I["Cache invalidator"]
  I --> C["Redis DEL / version-aware update"]
  B --> M["Monitoring / replay"]
~~~

Key considerations:

- Events may be delivered **multiple times or out of order**. Handlers must be idempotent.
- If v8 arrives after v9, deleting a generic key merely causes an extra miss, whereas **overwriting cache with v8** reintroduces stale data unless version-checked.
- Standalone Pub/Sub notifications are not durable if subscribers disconnect; use a durable broker/outbox when reliable invalidation is required.
- Event propagation introduces lag; never rely purely on eventual invalidation for strong correctness requirements.
- Telemetry must track outbox lag, failed events, cache invalidations, and DLQs.
- Every service must construct identical keys from a shared cache-key specification.

### Cache key invalidation and multi-tenancy

When tenant-A updates `catalog:tenant-A:product:42`, ensure no scoping bug accidentally deletes or misses tenant-B's key. Conversely, omitting tenant scope in shared keys when data differs risks **cross-tenant data leaks**.

## 22. When the cache or Redis fails

Standard cache-aside treats the cache as **best effort**: if Redis cannot be read or written, the app falls back to the DB. Yet if 10,000 RPS fall back at once, the database can collapse.

### Controlled failure policy

- Set **short, finite timeouts** on Redis calls aligned with SLOs.
- Use circuit breakers so threads/connection pools do not pile up on a failing cache.
- Cap **DB fallback concurrency** with bulkheads/semaphores.
- Apply rate limiting or load shedding as the DB nears capacity.
- If a bounded local stale cache exists within policy, serve it temporarily for display data.
- Return 503/429 with controlled retry guidance when requests cannot be served safely.
- Monitor Redis reconnects, timeouts, failovers, memory/evictions, and backend QPS.
- After recovery, **rate-limit hot-key warm-up** to prevent a cold-cache avalanche.

### What not to do

~~~text
Redis timeout
  -> catch Exception
  -> 10,000 requests all SELECT DB
  -> DB pool exhausted
  -> API timeouts, client retries
  -> even heavier DB load
~~~

Catching exceptions is not enough. Fallbacks require **resource budgets** and endpoint priority tiers.

### Per-operation cache failures

- **Redis GET failure:** decide fallback vs fail-fast based on SLO and business sensitivity.
- **Redis SET failure after DB read:** usually return the DB result if allowed by policy; emit a cache-populate failure metric.
- **Redis DEL failure after DB commit:** never casually roll back the DB transaction; record to outbox/retry invalidation with TTL bounds.
- **Redis write timeout with unknown outcome:** the command may still have executed. Never treat a missing reply as proof that SET/DEL did not run.
- **Redis failover:** clients must reconnect per supported library behavior; cached entries and locks may be lost or shifted.

## 23. Eviction, memory, and hot keys

Redis enforces memory limits and eviction policies per service/configuration. Cache hit ratio depends on more than TTL; under RAM pressure, Redis can **evict keys** before TTL expiry, driving misses and stampedes.

### Evaluating memory

1. Number of unique keys actively accessed during the cache window.
2. Serialized item sizes, metadata/versions, key lengths, and Redis overhead.
3. Hit/miss ratio, eviction counts, and keyspace size.
4. Memory fragmentation/allocator behavior from available metrics.
5. Hot-set size and distribution across tenants.
6. Failover/restart behavior and warm-up duration.
7. Cost of scaling RAM/SKU versus trimming payloads or TTLs.

### A hot key can bottleneck Redis CPU or network

Even at a 100% hit rate, an ultra-hot key can cause **network bandwidth or CPU contention**, especially with large values and tens of thousands of GET/s. Consider:

- Very short-TTL local near-cache for popular read-only data.
- Shrinking serialized value sizes.
- Read scaling/replica caching within Redis service capabilities and consistency rules.
- CDN or HTTP caching for public data.
- Per-client QPS limits and bot filtering.
- Optimizing HTTP endpoints to avoid re-decoding huge JSON blobs on every request.

A **local near-cache** needs its own invalidation plan; do not add one to immediately mutable data solely to shave Redis QPS.

## 24. Security: don't turn the cache into a data leak

Caches often hold data accessed by multiple services. Security covers **networking, authentication, tenant isolation, and data retention**.

### Checklist

1. Enforce TLS and validate hostnames/certificates.
2. Prefer private access when supported by the Azure Redis service/SKU; verify DNS, routing, and VNet integration.
3. Use Microsoft Entra authentication/managed identity when **supported by the product/SDK**, or policy-managed credentials/ACLs.
4. Never embed passwords or access keys in source code, build logs, container images, or command lines.
5. Store secrets in Azure Key Vault or an approved secret store; rotate and test reconnects.
6. Scope Redis permissions per application and environment rather than sharing god-mode credentials.
7. Scope keys by tenant and authorized data; **a cache hit never replaces authorization**.
8. Avoid storing unnecessary tokens, card numbers, or personal data in Redis.
9. Align TTL/retention with compliance rules, including per-customer data.
10. Redact request logs, cache keys, diagnostic traces, and connection strings.
11. Restrict dangerous operational commands like `FLUSHALL` and `KEYS *` in production via proper policies and roles.
12. Maintain auditing and ownership for Redis access/configuration changes.

### Distinguishing 401/403 from a cache miss

Reading a cache key lacking tenant/authorization scope can expose another user's data. Always authenticate requests and authorize access before using cached values. **A technically valid cache hit does not prove the caller is allowed to see the object.**

## 25. Monitoring cache-aside and cache stampedes

Key metrics:

| Metric | Purpose |
|---|---|
| Cache hit count/rate | Measures DB reads avoided |
| Cache miss count/rate | Detects cold caches, evictions, or short TTLs |
| Cache lookup p50/p95/p99 | Tracks Redis/client network latency |
| Cache populate success/failure | Confirms cache fills succeed |
| DB loads per key/window | Directly measures stampedes |
| Singleflight followers/leaders | Shows whether coalescing cuts recomputes |
| Lease acquisition success/contended | Tracks distributed coordination |
| Lease wait duration/expiry | Catches lock timeouts or hung loaders |
| Stale served count and age | Tracks how stale served responses get |
| Evicted/expired keys | Shows memory pressure and TTL distribution |
| Backend DB QPS/CPU/latency | Verifies whether misses protect or overload backend |
| Redis connections/CPU/memory/network | Detects bottlenecks on the cache tier |
| API 5xx/429 and p95 latency | Measures user-facing impact |
| Business correctness metrics | Detects order/price/inventory mismatches |
| Cache cost + DB cost | Confirms net total-cost optimization |

### Hit ratio alone is not enough

~~~text
1,000,000 requests
  999,000 cache hits
  1,000 misses

Hit ratio = 99.9%
~~~

It looks great on paper, yet if those **1,000 misses arrive within 100 ms** for the same hot key, the backend can still go down. Track **miss bursts, per-key DB load amplification, and tail latency**, not just average hit ratios.

### Avoid high-cardinality metrics

Never attach every product ID, user ID, or trace ID as an unbounded time-series metric label. Use route, cache namespace, status/operation, and environment/region. To inspect specific hot keys, use **sampled diagnostic logs or safe top-N aggregates** with restricted access and short retention.

## 26. Azure Monitor, Application Insights, and Redis diagnostics

Combine telemetry sources:

- **Azure Monitor Metrics** on the Redis resource: memory, CPU, connections, operations, evictions, and latency/throttling per product capabilities.
- **Application Insights / OpenTelemetry** in the Java API: Redis dependency spans, custom cache hit/miss metrics, and DB dependency spans.
- **Azure SQL / Cosmos DB metrics**: DB CPU/DTU/vCore or RU/s/429s, latency, and connection load per service.
- **Log Analytics**: platform and application logs routed to a workspace.
- **Azure Service Health / Resource Health**: platform/service outage signals when available.
- **Cost Management**: cache SKU, database, compute, network, and log ingestion spend.

Depending on the Azure Redis service, **resource types, metric names, and dimensions differ**. Always inspect metric definitions on the target resource rather than copying Azure Cache for Redis metric names verbatim onto Azure Managed Redis.

### Read-only Azure CLI commands

~~~bash
az account show \
  --query "{subscription:name,id:id,tenant:tenantId}" \
  --output table

REDIS_ID="<EXISTING_AZURE_REDIS_RESOURCE_ID>"

az resource show \
  --ids "$REDIS_ID" \
  --query "{id:id,name:name,type:type,location:location,sku:sku}" \
  --output json

az monitor metrics list-definitions \
  --resource "$REDIS_ID" \
  --output table
~~~

Only after confirming **valid metric names**, run `az monitor metrics list` with appropriate time ranges and dimensions. Never print credentials, connection strings, or secrets from resource properties. Reading resource metadata does not prove the application can connect to Redis.

### Actionable alerts

1. Sudden drop in Redis hit rate **paired with rising DB QPS**.
2. Rising Redis evictions or memory pressure.
3. Cache populate failures or Redis GET timeouts exceeding thresholds.
4. Rising stampede amplification (DB loads per key in a few seconds).
5. Stale data age breaching business limits.
6. Redis connection pool exhaustion or repeated reconnects/failovers.
7. Rising API p95/p99 alongside database saturation.
8. Rising Redis spend without commensurate drops in backend query cost/latency.

Alerts should include owner, runbook, dashboard link, environment, and recent deployment markers—avoid paging an entire on-call team over a single transient GET error.

## 27. Measuring impact: hit ratio, amplification, and cost formulas

### Hit ratio

~~~text
HitRatio = CacheHits / (CacheHits + CacheMisses)
~~~

With 9,200 hits and 800 misses, hit ratio = **92%**. Counting rules must stay consistent: do negative hits count as hits? Do Redis timeouts count as misses or errors? Align definitions before comparing releases.

### DB amplification during a stampede

~~~text
Expected source loads for one expired key:
  without protection  ≈ number of concurrent misses
  with local singleflight ≈ number of API replicas that miss
  with effective distributed coalescing ≈ 1 loader (not an absolute guarantee)
~~~

With 12 pods and 50 concurrent misses per pod on one key:

- Without singleflight: up to roughly **600 source reads**.
- With per-pod singleflight: roughly **12 reads**.
- With well-coordinated leases and healthy Redis: near **1 read** per refresh wave.

These figures are illustrative, not an SLA. Lock timeouts, failovers, or failing loaders can raise source read counts.

### Estimating average latency

~~~text
AverageLatency ≈ HitRatio × CacheHitLatency
               + (1 - HitRatio) × MissEndToEndLatency
~~~

Assuming 95% hit rate, 3 ms cache path, and 45 ms miss path:

~~~text
≈ 0.95 × 3 + 0.05 × 45 = 5.10 ms
~~~

This illustrative average ignores **p95/p99**, network queuing, refresh contention, and tail distributions; a stampede can spike p99 dramatically while barely moving the mean.

### Total cost

~~~text
TotalCost =
  Azure-managed Redis capacity + network
  + API/worker compute
  + DB query/storage cost
  + monitoring/logging
  + invalidation/refresh overhead
  + engineering/operations risk
~~~

A larger Redis cluster adds fixed cost, yet can cut DB reads enough to **lower total cost**. Conversely, a cache with a 15% hit rate, low reuse, and high operational overhead may not pay for itself.

## 28. Controlled cache stampede load testing

### Preparation

- Isolated staging/lab Redis and database—never production.
- Realistic dataset including hot keys.
- Load generator with bounded RPS and concurrency.
- Telemetry for hits/misses, DB QPS, Redis CPU/memory, API latency, errors, and refresh counts.
- Rate limits/circuit breakers so the test cannot knock over shared infrastructure.
- Synchronized UTC clocks, recorded build versions, and cache policies.

### Scenario A — Baseline cache-aside

1. Warm a key with an initial GET.
2. Send 100–500 RPS within approved lab limits.
3. Measure hit ratio, DB reads, and latency.
4. Verify positive key TTL and clean serialization.
5. Record baseline numbers.

### Scenario B — Cache expiry stampede

1. Wait for TTL expiry or delete **only the specific lab key** (never `FLUSHALL`).
2. Fire 100 concurrent requests at the same hot key.
3. Count how many times the underlying repository is called.
4. Measure DB CPU/latency and API p95/p99.
5. Confirm cached/returned responses carry the same business version.

### Scenario C — Singleflight

1. Enable singleflight in each API instance.
2. Re-run the test against a single JVM.
3. Re-run across multiple replicas.
4. Verify local suppression reduces DB loads per instance without promising a single cluster-wide load.
5. Inspect follower timeouts, exception propagation, and in-flight map memory.

### Scenario D — Distributed lease

1. Add Redis per-key lease + token + TTL + Lua release.
2. Run across multiple replicas and re-check the cache after lock acquisition.
3. Inject latency into the repository to simulate a slow loader.
4. Verify expired leases never delete a newer owner's lock.
5. Confirm followers do not fall back to the DB en masse.
6. Test stale overwrite races when a writer updates the DB between loader read and cache set.
7. Add version guards/transaction policies if required by correctness.

### Scenario E — Redis unavailable

1. In the lab, simulate Redis timeouts or dropped connections.
2. Verify bounded fallback rather than every request hitting the DB.
3. Inspect API status codes/latency and circuit breaker state.
4. Restore Redis and rate-limit hot-key warm-up.
5. Measure recovery time and database load surge.

**Run fault injection only on authorized test resources.** Never kill production Redis, alter public networking/credentials, or run `FLUSHALL` on shared environments.

## 29. Case study: product pages and checkout

### Scenario

A retail platform runs a Java API on Azure Container Apps, Azure SQL for catalog and orders, and managed Redis caching reads.

- Product detail: 8,000 GET/s at peak, with 3% of products driving 70% of views.
- Catalog updates: a few times per minute.
- Checkout: must verify exact price and inventory at commit time.
- Redis TTL set to 10 minutes for product display.
- When a promotion launches, top products expire and DB CPU spikes to 95%.

### Analysis

1. **A high hit rate is not enough:** a single hot-key expiry triggers a wave of loaders.
2. Exact 600s TTLs on 10,000 preloaded keys cause an avalanche.
3. Hot top products need **singleflight + distributed coalescing** or stale serving.
4. Display prices tolerate brief staleness, while checkout requires authoritative DB verification.
5. Post-update cache invalidation races with concurrent loaders; use version-aware logic or an explicit staleness policy.
6. If Redis disconnects, never let 8,000 RPS hit SQL unchecked.

### Recommended design to validate

- **Product detail:** cache-aside + soft/hard TTL, singleflight, selective per-key leases, short negative caching, and TTL jitter.
- **Catalog writer:** commit DB first, emit outbox/invalidation events, and guard against stale overwrites per freshness target.
- **Checkout:** DB transactions/conditional updates with idempotency keys; never trust cache for stock deduction.
- **Security:** tenant scoping from verified request identity, private Redis/TLS/managed credentials.
- **Observability:** hits/misses, refresh tasks, lock contention, stale age, SQL QPS, p95 latency, and business correctness.
- **Cost:** balance Redis SKU, SQL read capacity, API compute, and monitoring spend.

~~~mermaid
flowchart LR
  U["Web/Mobile"] --> API["Java API"]
  API --> R["Redis cache: product display"]
  API --> SQL["Azure SQL: authoritative product/order"]
  SQL --> O["Transactional outbox"]
  O --> BUS["Service Bus event"]
  BUS --> INV["Cache invalidator"]
  INV --> R
  API --> OBS["Azure Monitor / App Insights"]
  R --> OBS
  SQL --> OBS
~~~

### Failure drills

- **Redis cold restart:** cap fallback, warm top-N keys, verify recovered hit ratio.
- **DB update while loader reads v1:** verify stale overwrite stays within policy; add version guards if strictness demands it.
- **Redelivered invalidation event:** delete/refresh handler behaves idempotently.
- **Expired Redis lease:** stale worker does not delete the new lock; no business side effects outside DB.
- **Bot traffic surge:** input validation, WAF/APIM rate limits, negative caching, and key-cardinality monitoring.

## 30. Practical troubleshooting matrix

| Symptom | Common cause | Investigation / remediation |
|---|---|---|
| Low hit rate | TTL too short, overly granular keys, serialization mismatch | Check top keys, key builder, TTL, traffic reuse |
| Periodic DB QPS spikes | Hot-key TTL expiry, cache avalanche | Plot miss spikes, TTL spread, singleflight/jitter |
| Many DB loads for one key | Stampede | Per-key load metric, double-check, coalescing |
| Ineffective across 20 pods | Singleflight is per-JVM only | Add distributed lease/stale-serving if needed |
| Redis lock stays stuck | Process crash, Lua/TTL/permission issue | Lease expiry, token compare, lock metrics |
| Old worker deletes new lock | Unconditional `DEL` | Atomic token-checked release |
| Old data reappears after update | Stale loader sets after `DEL` | Versioning/generation/fencing or direct source reads |
| Users see stale prices/stock | TTL/invalidation mismatch with semantics | DB check at checkout, versioning, tighter stale policy |
| 404s keep hitting DB | Missing negative cache / random keys | Negative TTL, validation, rate limit |
| Newly created product stays 404 | Negative cache not invalidated | Delete sentinel on create, keep negative TTL short |
| High Redis memory & evictions | Oversized values, key explosion, long TTLs | Sizing, key cleanup, selective compression |
| High Redis CPU despite high hits | Extreme hot key/QPS, large values | Short-TTL near-cache, rate limits, trim payloads |
| Redis timeout triggers DB outage | Unbounded fallback | Bulkhead, circuit breaker, load shedding |
| API 5xx after Redis failover | Bad reconnect/TLS/DNS/pooling | SDK diagnostics, network path, timeouts/retries |
| Cross-tenant data leak | Missing tenant/auth scope in key | Fix key scoping + authorization, run incident response |
| Cloud bill rises after caching | Fixed Redis cost exceeds DB savings | Cost comparison, hit ratio audit, rightsizing |
| Blank Redis metrics | Wrong resource type, metric name, or RBAC | List metric definitions, resource health, agents |
| Lost invalidations | Crash after DB commit or non-durable pub/sub | Transactional outbox + durable events, TTL bound |

### Root-cause investigation order

1. Identify affected endpoints, key namespaces, regions, and time windows.
2. Break down hits, misses, and errors—never lump Redis timeouts in with cache misses.
3. Measure concurrent DB loads per key.
4. Inspect Redis expirations, evictions, failovers, and client pools.
5. Inspect corresponding DB QPS, CPU, RU/s, locks, and query latency.
6. Check recent releases altering TTLs, key formats, serialization, or invalidation.
7. Reproduce race conditions in staging.
8. Remediate per freshness/SLO policy and verify both system health and cost.

## 31. Comprehensive hands-on lab

> **Safety:** only create and operate on authorized **lab** Redis/SQL/Cosmos DB resources. Load tests, key purges, and Azure resources incur charges. Never run broad data-deletion commands, shut down production caches, or access real tenant secrets.

### Part A — Design

1. Pick a `GET /products/{id}` endpoint backed by Azure SQL or Cosmos DB as source of truth.
2. Diagram the cache-aside read path: hit/miss/populate/return.
3. Design a key containing namespace, environment, tenant, productId, and schema version.
4. Choose a positive TTL from a freshness SLO.
5. Choose a negative TTL and specify when the sentinel must be invalidated.
6. Select an appropriate managed Redis SKU/region/network using current documentation.
7. Define at least 5 metrics spanning cache and DB.
8. Specify the fallback policy when Redis is unavailable.

### Part B — Java cache-aside

1. Add approved versions of Spring Data Redis, Jackson, and repository dependencies.
2. Implement `ProductDto` and `ProductRepository`.
3. Build cache-first GET, DB fallback, JSON serialization, and TTL handling.
4. Implement post-commit DB update invalidation and document race conditions.
5. Test positive hits, misses, negative hits, malformed JSON, and Redis timeouts.
6. Measure cache lookup and DB dependency spans via OpenTelemetry/Application Insights.
7. Ensure authorization never depends on cache hit/miss status.

### Part C — Stampede

1. Warm a top product key.
2. Delete **only the lab key** or wait for TTL expiry.
3. Send 100 concurrent GETs within controlled limits.
4. Count repository invocations.
5. Add Java singleflight and re-test on a single instance.
6. Scale to multiple replicas and count loaders.
7. If needed, add Redis lease/token/Lua release.
8. Re-check the cache after locking and bound follower waits.
9. Compare DB loads, API p95, and error rates before and after.
10. Test lease expiry and stale overwrite races.

### Part D — Freshness and operations

1. Add TTL jitter across multiple keys and verify staggered expirations.
2. Add soft/hard TTLs for display data while forbidding stale reads at checkout.
3. Update a product while cache refresh is in flight and compare DB versions.
4. Simulate Redis timeouts and verify bounded fallback.
5. Use Azure CLI to inspect the Redis resource and metric definitions.
6. Build a dashboard for hit ratio, DB QPS, Redis evictions, stampede count, and stale age.
7. Configure alerts for sudden backend read surges following cache expiry.
8. Estimate net cost impact across Redis + DB + compute.
9. Write a runbook for cold starts/failovers and lost invalidations.
10. Clean up lab resources properly without touching shared infrastructure.

### Self-check questions

**Q1.** How does cache-aside differ from read-through and write-through?

**Q2.** Why does cache-aside treat the database as the source of truth rather than assuming Redis is always accurate?

**Q3.** If 1,000 requests miss a hot key simultaneously, how does a stampede unfold?

**Q4.** How does a cache stampede differ from a cache avalanche and cache penetration?

**Q5.** TTL jitter prevents many keys from expiring simultaneously; does it prevent 10,000 requests from missing one key?

**Q6.** How many concurrent loaders does Java singleflight eliminate when running 20 replicas?

**Q7.** Why must you GET the cache again right after acquiring a distributed lock?

**Q8.** Why does a Redis lock need a unique token and Lua compare-and-delete on release?

**Q9.** If a Redis lease expires before the loader finishes, what races remain?

**Q10.** Why is a Redis lease insufficient to guarantee an exactly-once transaction?

**Q11.** Which endpoints benefit from soft/hard TTLs, and when must stale data never be served?

**Q12.** How can negative caching cause a stale 404 after creating a new item?

**Q13.** Why can a writer committing to the DB and deleting the cache still let an older loader write stale data back?

**Q14.** How do versioned keys or conditional writes help, and what reliable version source do they require?

**Q15.** How do outbox/invalidation events reduce risk if the app crashes right after a DB commit?

**Q16.** How does a Redis failover affect lock state and cache warm-up?

**Q17.** Is a 99.9% cache hit ratio enough to prove there are no stampedes?

**Q18.** Why should you avoid putting productId or userId into every metric dimension?

**Q19.** When Redis goes down, why does unbounded DB fallback trigger cascading failures?

**Q20.** In a multi-tenant app, how must cache keys and authorization be designed?

**Q21.** What factors influence total cost when adding Redis to an Azure architecture?

**Completion criteria:** accurately describe cache-aside, implement Java cache-first code, diagnose stampedes, distinguish TTL jitter from singleflight, explain safe leases and their limits, analyze invalidation races, define freshness policies, and prepare monitoring, fallback, and benchmark plans.

## Conclusion

**Cache-aside** is a flexible caching pattern: the application checks Redis first, loads from the authoritative source on misses, and repopulates the cache with an appropriate TTL. It can sharply reduce database reads and improve latency for Java APIs on Azure, provided cache keys, TTLs, serialization, invalidation, and authorization are designed consistently.

**Cache stampedes** show that a high average hit ratio alone cannot protect the backend: the moment a hot key expires, hundreds or thousands of requests can reload data concurrently. Risk drops with **in-JVM singleflight, per-key distributed leases, TTL jitter against avalanches, soft/hard TTLs with stale-while-revalidate, refresh-ahead, negative caching, and bounded fallbacks**. Just as crucial is understanding **read/write races, lease expiry, Redis failover, and consistency limits**: never substitute a cache lock for business transactions. On Azure, pairing managed Redis, private networking/identity, Azure Monitor, Application Insights, source-database backups/runbooks, and Cost Management lets systems scale while safeguarding data and controlling spend.
