# Cache-Aside, TTL, Eviction, and Preventing Cache Stampedes

> **Chapter:** Bigtable and Memorystore  
> **Lesson:** Cache-Aside, TTL, Eviction, and Preventing Cache Stampedes  
> **Module:** CLOUD_PROVIDERS_GCP

In the **CLOUD_PROVIDERS_GCP** module, learners explore Google Cloud from projects, IAM, and VPCs to Compute Engine, GKE, Cloud Run, storage services, and databases; through deployment scenarios they learn to select services, secure resources, automate releases, and monitor reliability alongside cost. For Java applications repeatedly reading the same records, **Memorystore** serves as an in-memory cache layer that lowers latency and reduces queries against a primary datastore like **Bigtable**. Yet a misconfigured cache can cause **stale data, Redis out-of-memory errors, cascading failures, and traffic spikes when many keys expire simultaneously**.

This lesson centers on four tightly coupled concepts:

- **Cache-aside:** the application reads the cache first; on a miss, it fetches from the datastore and populates the cache.
- **TTL (time to live):** the duration a cache entry is considered valid from a storage standpoint.
- **Eviction:** Redis proactively removes keys when approaching memory limits according to `maxmemory-policy`.
- **Cache stampede:** many concurrent requests observe a cache miss/expiration for the same hot key and hit the backend together.

The example architecture is **Java Orders API on Cloud Run → Memorystore for Redis → Bigtable**. Bigtable holds the durable records; Redis holds **derived data that can be lost and reconstructed**. Several patterns apply similarly to Cloud SQL, Firestore, or AlloyDB. Never use a cache as a payment ledger, inventory authority, or sole proof of access rights.

**Scope:** primarily illustrates **Memorystore for Redis (non-cluster)**; **Memorystore for Redis Cluster** and **Memorystore for Valkey** differ in configuration, connectivity, HA, scaling, and IAM. Check product-specific docs before reusing commands. Commands that create or delete resources can incur charges; test only in an approved sandbox.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Diagram **cache hit, cache miss, refresh, and write-invalidate** flows, establishing Bigtable as the source of truth.
2. Select data suited for caching, structure **tenant/version-scoped cache keys**, and bound payload sizes.
3. Distinguish **TTL expiration** from **memory eviction**, and interpret `volatile-*`, `allkeys-*`, and `noeviction` policies.
4. Design **jittered TTLs**, negative caching, soft/hard TTLs, and stale-while-revalidate when business rules allow.
5. Distinguish **cache stampede**, cache avalanche, and cache penetration.
6. Mitigate stampedes using **local single-flight, distributed leases/locks, bounded waiting, request coalescing**, and backpressure.
7. Use Redis `SET ... NX PX` and **atomic compare-and-delete Lua** to avoid deleting another process's lock, while understanding its limits.
8. Write a Java **Lettuce client** implementing cache-aside with TTL jitter and concurrency bounds.
9. Design invalidation when Bigtable updates, avoiding race conditions and stale data.
10. Monitor hit ratio, evicted keys, expired keys, memory pressure, Bigtable latency, and cost.

## 2. Cache-Aside Architecture on Google Cloud

~~~mermaid
flowchart LR
    Client["Web/Mobile/API caller"] --> Java["Cloud Run Java Orders API"]
    Java -->|"GET key"| Redis["Memorystore for Redis<br/>in-memory cache"]
    Redis -->|"HIT: value"| Java
    Redis -. "MISS / expired / evicted" .-> Java
    Java -->|"ReadRow(rowKey)"| BT["Cloud Bigtable<br/>source of truth"]
    BT -->|"canonical value + version"| Java
    Java -->|"SET key EX ttl"| Redis
    Java --> Client
    Mon["Cloud Monitoring/Logging<br/>p95, hit ratio, memory"] -.-> Java
    Mon -.-> Redis
    Mon -.-> BT
~~~

**Why not read Bigtable on every request?** Bigtable is built for huge datasets, row-key/range lookups, and high throughput; an endpoint querying **the exact same hot row** thousands of times can consume I/O, drive cost, and raise p99 latency. A cache absorbs repeated reads. Still, **Bigtable must handle controlled cache misses**, and Redis must have a failover/fallback plan.

### 2.1. Which Data Should Enter the Cache?

| Data | Should it be cached? | Conditions |
|---|---|---|
| Infrequently changing product info | **Yes** | Minutes-long TTL, invalidate on update |
| Snapshot of a completed order status | **Yes, conditionally** | Bound acceptable lag; key includes tenant/order |
| Read-only metadata from Bigtable | **Yes** | Explicit row key, small payload, moderate update rate |
| Active promotional pricing | **Yes, with freshness controls** | Event invalidation + version, short TTL |
| User access permissions | **With extreme caution** | Never let stale cache leak data; revalidate sensitive policies |
| Balances, transfers, inventory needing strict consistency | **Never as final authority** | Read/write at source with concurrency control |
| Multi-MB payloads or unbounded lists | **Avoid** | Raises memory/network latency; cache bounded snapshots |
| Personalized search results | **Yes, if key includes scope** | Tenant, filters, permissions/version, and short TTL |

**Rule:** a cache is a copy that can vanish at any moment. Design business logic to remain **correct even if the cache returns MISS continuously**, while applying bounds so misses never overwhelm the source.

## 3. Cache-Aside Workflow: Reads, Writes, and Consistency

### 3.1. Read Path

~~~mermaid
sequenceDiagram
    participant C as Client
    participant J as Java API
    participant R as Redis
    participant B as Bigtable
    C->>J: GET /v1/orders/OD-42
    J->>R: GET orders:v1:tenantA:OD-42
    alt Cache hit
        R-->>J: Cached snapshot
    else Cache miss
        R-->>J: nil
        J->>B: ReadRow(tenantA#OD-42)
        B-->>J: Snapshot + version
        J->>R: SET key value EX 60
    end
    J-->>C: JSON response
~~~

Steps:

1. Java authenticates/authorizes the user and tenant **before building the cache key**.
2. Read Redis by namespaced key; return fast if a valid value is present.
3. On miss, query Bigtable via an **efficient row key**, never a full-table scan.
4. Serialize the payload with an **explicit schema/version** and write to Redis with a TTL.
5. If Redis fails (timeout/network), **distinguish cache errors from a MISS**; you may bypass the cache, but must bound concurrency to protect Bigtable.

A cache hit never bypasses authorization checks. **Never return tenant A's data to tenant B** just because both requests share an order ID.

### 3.2. Write Path: Update Source Then Invalidate

~~~mermaid
sequenceDiagram
    participant J as Java Service
    participant B as Bigtable
    participant R as Redis
    J->>B: MutateRow canonical record
    B-->>J: Commit succeeds
    J->>R: DEL orders:v1:tenantA:OD-42
    Note over R: Next read is a MISS and reloads
~~~

**Default order:** **Bigtable write succeeds → invalidate Redis**. Never update the cache before committing the source; if Bigtable fails, the cache would advertise state that never existed.

**Failure window to recognize:** Bigtable commit succeeds while Redis `DEL` fails → stale value lingers until TTL expires. Implement controlled retries/invalidation or an event/outbox pattern when strictness is required. **Bigtable + Redis operations are not atomic**; never advertise this pattern as strongly consistent across both services.

### 3.3. Cache-Aside vs. Write-Through and Write-Behind

| Strategy | Who writes the cache? | Trade-off |
|---|---|---|
| **Cache-aside** | Application populates on miss | Simple, clear control; cold first read, explicit invalidation needed |
| **Read-through** | Cache layer loads from backing store itself | Simpler client; requires a compatible loader/proxy |
| **Write-through** | Writes go through cache/coordinator to source | Easier freshness control, higher write latency; still has partial failures |
| **Write-behind / write-back** | Writes cache first, flushes to source asynchronously | Fast writes, but risks data loss if cache fails or queues lack durability |

For an Orders API protecting durable records, **cache-aside + source-first invalidation** is usually the easiest baseline to audit.

## 4. Designing Cache Keys and Payloads

### 4.1. Namespacing by Tenant and Schema

Examples:

~~~text
orders:v1:tenantA:OD-42
products:v3:shopA:SKU-102
feed:v2:tenantA:status=PAID:page=1
not-found:v1:tenantA:OD-999
refresh-lock:v1:tenantA:OD-42
~~~

A well-formed key should include:

- **Domain**, e.g., `orders`, `products`.
- **Schema version**, e.g., `v1`, preventing deserialization errors after deploys.
- **Tenant / audience / appropriate permission scope**, preventing cross-customer leaks.
- **Business identifier** or a deterministic hash of canonicalized query parameters.
- **Data scope** (locale, currency, pagination, feature flags) if it alters response content.

Never put **access tokens, passwords, phone numbers, personal emails, or raw PII JSON** directly in keys. Redis keys frequently appear in tooling, logs, and metrics; if an ID is sensitive, use HMAC/hashing per policy and never reuse keys across environments.

### 4.2. Versioned Payloads

~~~json
{
  "schemaVersion": 1,
  "sourceVersion": 1042,
  "fetchedAt": "2026-11-19T03:00:00Z",
  "order": {
    "id": "OD-42",
    "tenantId": "tenantA",
    "status": "PAID"
  }
}
~~~

`sourceVersion` is managed **by the source datastore**, not by Redis write time. If stale-writer protection is needed, compare versions **before updating the cache**; merely adding the field without comparing it does not fix race conditions.

**Bound entry sizes** and avoid caching full Bigtable rows with many columns/timestamps when an endpoint only needs a few fields. JSON serialization/deserialization and network transfer carry real costs.

## 5. TTL: Cache Lifetime and Data Freshness

**TTL** defines how long a key stays before **expiring**; Redis supports `EX` (seconds), `PX` (milliseconds), `EXPIRE`, and `TTL`/`PTTL` to inspect remaining lifetime.

~~~redis
SET orders:v1:tenantA:OD-42 '{"status":"PAID"}' EX 60
TTL orders:v1:tenantA:OD-42
GET orders:v1:tenantA:OD-42
~~~

Notes:

- `TTL > 0`: remaining seconds (subject to change).
- `TTL = -1`: key exists with **no expiration**.
- `TTL = -2`: key **does not exist**.
- Redis uses **lazy expiration** on access plus background **active expiration**; never assume Redis deletes/emits events on the exact millisecond boundary.
- A plain `SET` **overwrites the value and clears any prior TTL** unless `EX`/`PX`/`KEEPTTL` is specified. **Every cache `SET` must explicitly set a TTL**.

### 5.1. Choosing TTLs by Data Characteristics

| Data type | Example TTL | Risk |
|---|---|---|
| Infrequently changing product catalog | 5–15 minutes | Prices/attributes lag updates |
| Near-realtime order status | 10–60 seconds | Users see stale status if invalidation fails |
| Dashboard statistics | 1–5 minutes | Unsuitable for formal accounting/audits |
| **Not found** results | 5–30 seconds | Newly created entities stay hidden briefly |
| Session-scoped data | Depends on security policy | Never keep sessions/tokens indefinitely |

These numbers are **design starting points**, not universal defaults. Base TTLs on **freshness SLOs**, update frequency, source read cost, key cardinality, and invalidation reliability.

### 5.2. TTL Jitter to Avoid Simultaneous Expirations

If 100,000 keys are created at 12:00 with a fixed 300s TTL, huge batches can expire together at 12:05 → **cache avalanche**.

Replace fixed `300s` with a randomized range, for example:

~~~text
baseTtl = 300 seconds
jitter  = random integer [-30, +30]
actualTtl = max(30, baseTtl + jitter)
~~~

This **spreads expiration times**, while still respecting your **freshness budget**: if data must never be older than 300 seconds, **never add positive jitter pushing max TTL past 300**. Instead use `actualTtl = baseTtl - random(0, 60)` or soft/hard TTLs.

**Never share the same random seed/TTL across all instances**; compute fresh jitter per refresh or via a well-distributed deterministic hash.

### 5.3. Negative Caching

If an API repeatedly queries `orders:OD-DOES-NOT-EXIST`, every miss hits Bigtable. You can cache a **NOT_FOUND** sentinel with a **very short TTL**:

~~~text
GET orders:v1:tenantA:OD-404 → nil
Bigtable readRow → absent
SET orders:v1:tenantA:OD-404 __NOT_FOUND__ EX 10
Next request → returns 404 without calling Bigtable
~~~

Distinguish **"Bigtable confirmed no row"** from **"Bigtable timeout/403"**. Never negative-cache network or permission errors as if data does not exist. Invalidate the sentinel when the entity is created, and always include tenant and access scope in the key.

## 6. Eviction Differs from TTL Expiration

**TTL expiration** tracks **key age**; **eviction** triggers under **memory pressure** when reaching `maxmemory` during new writes. Keys with remaining TTL can be **evicted early**, while keys without TTL can occupy memory indefinitely depending on policy.

In **Memorystore for Redis**, the default `maxmemory-policy` is **`volatile-lru`**. Key options:

| Policy | When memory nears capacity | Best suited for |
|---|---|---|
| `volatile-lru` (**default**) | Evicts keys **with a TTL**, preferring least recently used | Caches with uniform TTLs, intentionally keeping non-TTL keys |
| `allkeys-lru` | Evicts LRU keys across the **entire keyspace** | Pure caches where every key can be regenerated |
| `allkeys-lfu` | Evicts least frequently used keys | Stable hot sets based on access frequency |
| `volatile-lfu` | LFU strictly among keys with TTL | Mixed workloads separating persistent vs. expirable keys |
| `volatile-ttl` | Evicts keys with the **shortest remaining TTL** | When business logic prefers keeping longer-lived entries |
| `allkeys-random` / `volatile-random` | Evicts random keys within the respective set | Specialized cases |
| `noeviction` | **No eviction**; writes needing more memory fail | Data that cannot be dropped arbitrarily, though Redis shouldn't be primary DB |

**`volatile-lru` trap:** If a cache key is **written without a TTL**, it is ineligible for eviction; once no TTL-bearing keys remain to evict, writes fail with **OOM errors**. Therefore, for pure cache-aside, either **set a TTL on every key** or evaluate **`allkeys-lru`** after benchmarking.

Select policies specifically for **Memorystore for Redis / Redis Cluster / Valkey**, as defaults and `maxmemory` behavior differ. Redis LRU/LFU use approximated sampling algorithms rather than exact global ordering.

### 6.1. Instance Memory vs. Cache Payloads

- **Instance capacity**: provisioned/billable memory resources.
- **`maxmemory-gb`** in Memorystore for Redis: cache threshold before eviction runs (defaults to instance capacity).
- **System memory usage ratio**: includes overhead/fragmentation; more critical than looking only at `used_memory`.
- **Eviction is not guaranteed to keep up with massive write bursts**; memory pressure and fragmentation can trigger errors before space is reclaimed.

Google Cloud recommends keeping **headroom**, monitoring **system memory usage ratio**, and alerting above **80%**. You can lower `maxmemory-gb`, enable defragmentation on supported versions, or scale the instance after measuring. Never lower limits or change eviction policies in production without modeling hit-ratio and Bigtable-load impacts.

## 7. Three Distinct Types of "Cache Miss Storms"

| Phenomenon | Cause | Mitigation |
|---|---|---|
| **Cache stampede** | A **hot key** expires; many requests miss and load simultaneously | Single-flight, lock/lease, stale-while-revalidate, bounded waits |
| **Cache avalanche** | **Many keys** expire/evict together or the cache cluster fails | TTL jitter, prewarming, resource headroom, circuit breakers |
| **Cache penetration** | Repeated requests for **nonexistent keys**, each hitting DB | Short negative cache, input validation, rate limits, Bloom filter if truly needed |

**Stampede example:** `products:v3:shopA:SKU-102` serves 5,000 RPS, its TTL expires, and a Bigtable read takes 30 ms. Without request coalescing, hundreds or thousands of concurrent reads hit the exact same row, spiking p99 and cost.

**Avalanche example:** a deploy prewarms every key at 12:00 with a 5-minute TTL; at 12:05 most keys miss together. Per-key jitter spreads expirations, though it cannot fix a full Redis outage alone.

**Penetration example:** bots scan millions of nonexistent `orderId`s; apply format validation, pre-query authorization, bounded negative caching, rate limiting, and never cache 403s as "not found" when semantics differ.

## 8. Layered Stampede Mitigation: Simple to Advanced

### 8.1. Local Single-Flight

Within **one Java instance**, use a `key -> CompletableFuture<Result>` map so 100 threads requesting the same key trigger **only one Bigtable read** while the rest await the shared future. In `finally`/`whenComplete`, **remove the entry** so it does not leak memory or cache indefinitely in RAM.

**Limitation:** when Cloud Run scales to 10 instances, local single-flight can still issue **10 Bigtable reads**. System-wide coalescing requires distributed coordination via a Redis lease or coordinating service.

### 8.2. Distributed Lease with Redis

Redis provides an atomic command:

~~~redis
SET refresh-lock:v1:tenantA:OD-42 random-token NX PX 15000
~~~

- `NX`: writes only if the lock key does not already exist.
- `PX 15000`: lock expires after **15,000 ms**, avoiding permanent deadlocks if an instance crashes.
- `random-token`: a **unique/unguessable** value per acquisition so unlocking never deletes a newer lock.

Flow:

~~~mermaid
sequenceDiagram
    participant A as Java instance A
    participant B as Java instance B
    participant R as Redis
    participant DB as Bigtable
    A->>R: GET hot-key → MISS
    B->>R: GET hot-key → MISS
    A->>R: SET lock token-A NX PX 15000 → OK
    B->>R: SET lock token-B NX PX 15000 → nil
    A->>DB: ReadRow hot row
    DB-->>A: Payload + source version
    A->>R: SET hot-key payload EX ttl
    A->>R: compare token then DEL lock
    B->>R: Poll GET hot-key → HIT
~~~

**Never run a plain `DEL lock`:** if A pauses longer than 15 seconds, the lock expires, B acquires a new lock, and A wakes up and calls `DEL`, **deleting B's lock**. Unlocking must compare tokens and delete **atomically**.

### 8.3. Lua Unlock Is Safer Than `GET` Followed by `DEL`

~~~lua
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("DEL", KEYS[1])
end
return 0
~~~

Invoke via `EVAL script 1 lock-key token` or client library helpers. **Never split into separate `GET` and `DEL` calls**, as two separate commands race.

**Design limitation:** a `SET NX PX` lock is only **lease coordination**, not a strict distributed transaction. If the loader runs longer than the TTL, multiple processes can still load/write the cache concurrently. For state-mutating writes, use **fencing tokens and version checks at the source of truth** rather than relying solely on a Redis lock. For pure derived cache entries, occasional duplicate work is acceptable as long as the backend stays protected.

### 8.4. Bounded Wait and Backpressure

Clients that fail to acquire the lock should:

1. Wait briefly with **backoff + jitter**, then recheck Redis.
2. Return the cache hit if populated.
3. If the **waiting budget** is exceeded, return **503/`Retry-After`**, or serve a **stale snapshot within an allowed window**, rather than bypassing the lock and hammering Bigtable.
4. Cap concurrent Bigtable reads per instance and globally, with timeouts and circuit breakers.
5. During a Redis outage, enforce a **bulkhead** on fallbacks instead of triggering an unbounded connection storm.

**Never spin-poll `GET` millions of times per second** while waiting on a lock; that turns a Bigtable stampede into a Redis stampede.

## 9. Soft TTL, Hard TTL, and Stale-While-Revalidate

For catalogs/feeds where **slightly stale data is acceptable**, store metadata:

~~~json
{
  "value": {"sku": "SKU-102", "priceMinor": 129900},
  "softExpiresAt": 1795057200,
  "hardExpiresAt": 1795057260,
  "sourceVersion": 1042
}
~~~

- **Before soft TTL:** serve cache normally.
- **Between soft TTL and hard TTL:** serve **stale** fast while a single background worker refreshes.
- **After hard TTL:** do not serve stale; wait boundedly for refresh or report temporary unavailability.
- The Redis key carries a **physical TTL equal to hard expiry** to reclaim memory—do not physically delete at soft expiry.

**Warning:** stale-while-revalidate is unsafe for revoked permissions, balances, payments, account locks, or compliance decisions requiring strict freshness. Define an explicit **maximum staleness** and audit it. On Cloud Run, do not rely arbitrarily on background threads outliving HTTP responses; use supported CPU/lifecycle settings or **Cloud Tasks/Pub/Sub** for durable refreshes.

### 9.1. Hot-Key Prewarming

For predictable high-traffic items (promo products), refresh before soft TTL expires. However:

- Never fire 100,000 refreshes simultaneously; use jitter/scheduling.
- Avoid refreshing cold entries: prewarm only the **hot set**.
- Never set infinite TTLs to prevent stampedes; that accumulates stale data and memory pressure.
- If a Redis failover drops entries, enforce fallback/rate limits when re-warming.

## 10. Java Lettuce: Cache-Aside with TTL Jitter and Redis Locks

Java 17 example illustrating an API reading an **order snapshot from Bigtable via a repository**. The code:

1. Checks cache by tenant/order.
2. On miss, attempts to acquire a `SET NX PX` lease.
3. The owner double-checks cache, loads from source, and writes Redis with a jittered TTL.
4. The owner releases the lock only if its token matches.
5. Non-owners wait boundedly; on timeout, they fail temporarily instead of piling reads onto Bigtable.

**Example scope:** connects to Redis inside a sandbox VPC and uses a plaintext URI without TLS/Redis AUTH **only when the lab instance is isolated and configured that way**. In production, enable Redis AUTH/TLS per product support and **load Lettuce TLS/certificates/passwords from Secret Manager**—never embed secrets in loggable URIs. This pattern does not replace optimistic version checks under concurrent writes.

### 10.1. Maven Dependencies

A project with `pom.xml`, Java 17, and the Lettuce dependency:

~~~xml
<dependencies>
  <dependency>
    <groupId>io.lettuce</groupId>
    <artifactId>lettuce-core</artifactId>
    <version>6.5.5.RELEASE</version>
  </dependency>
</dependencies>
~~~

`6.5.5.RELEASE` is an **illustrative version**, not a claim of the latest release; pin a JDK-compatible version and scan for CVEs before production. With Spring Boot, you can substitute **Spring Data Redis/`RedisTemplate`** following the exact same cache-aside, TTL, and mutex principles.

### 10.2. Java Implementation

~~~java
package com.example.cache;

import io.lettuce.core.RedisClient;
import io.lettuce.core.RedisURI;
import io.lettuce.core.ScriptOutputType;
import io.lettuce.core.SetArgs;
import io.lettuce.core.api.StatefulRedisConnection;
import io.lettuce.core.api.sync.RedisCommands;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.Supplier;

public final class OrdersCache implements AutoCloseable {
    private static final String UNLOCK = """
        if redis.call("GET",KEYS[1]) == ARGV[1] then
          return redis.call("DEL",KEYS[1])
        end
        return 0
        """;

    private final RedisClient client;
    private final StatefulRedisConnection<String, String> connection;
    private final RedisCommands<String, String> redis;

    public OrdersCache(String host, int port) {
        // LAB ONLY in an isolated VPC. Production: TLS + AUTH + Secret Manager.
        RedisURI uri = RedisURI.create("redis://" + host + ":" + port);
        uri.setTimeout(Duration.ofSeconds(2));
        client = RedisClient.create(uri);
        connection = client.connect();
        redis = connection.sync();
    }

    public String getOrder(String tenant, String orderId,
                           Supplier<String> bigtableLoader)
                           throws InterruptedException {
        String key = "orders:v1:" + tenant + ":" + orderId;
        String lock = "refresh-lock:" + key;
        String value = redis.get(key);
        if (value != null) return value;

        String token = UUID.randomUUID().toString();
        String acquired = redis.set(lock, token,
                SetArgs.Builder.nx().px(15_000));

        if ("OK".equals(acquired)) {
            try {
                // Double-check: another owner may have just populated the data.
                value = redis.get(key);
                if (value != null) return value;

                value = bigtableLoader.get(); // Source lookup with its own timeout.
                if (value != null) {
                    // TTL jitter 50–60s, staying within the 60s budget.
                    int ttl = 60 - ThreadLocalRandom.current().nextInt(11);
                    redis.setex(key, ttl, value);
                }
                return value; // null = not found; do not cache DB errors.
            } finally {
                // Atomically compare token + delete lock.
                redis.eval(UNLOCK, ScriptOutputType.INTEGER,
                        new String[] {lock}, token);
            }
        }

        // Did not acquire lock: wait for owner, DO NOT flood Bigtable.
        for (int i = 0; i < 20; i++) {
            Thread.sleep(100 + ThreadLocalRandom.current().nextInt(50));
            value = redis.get(key);
            if (value != null) return value;
        }
        throw new IllegalStateException("Cache refresh in progress");
        // HTTP layer: map to 503 + Retry-After depending on SLO.
    }

    @Override public void close() {
        connection.close();
        client.shutdown();
    }
}
~~~

**Usage in a Java service (abbreviated):**

~~~java
// Create OrdersCache as a singleton bean, NEVER per request.
String value = ordersCache.getOrder(
    "tenantA", "OD-42",
    () -> orderRepository.readSnapshot("tenantA", "OD-42")
);
~~~

`orderRepository.readSnapshot(...)` is a **hypothetical method** implemented by the app using the Bigtable Java client; it must query the exact row key, serialize JSON, enforce timeouts, and distinguish **row not found** from 403/timeout errors. The code above **demonstrates cache reads**, not a complete Spring Boot app.

### 10.3. Limitations to Address Before Production

- **Synchronous calls:** a single shared synchronous Redis connection can bottleneck across many Java threads; benchmark and choose async clients/pooling per workload without opening a connection per HTTP request.
- **Timeouts:** a 15-second lock is illustrative; if Bigtable read p99 runs longer, the lock can expire before the owner finishes. Cap loader timeouts and evaluate fencing/source versions.
- **Unlocking:** Redis or network errors in `finally` must be logged/monitored; the lock expires automatically if release fails. Never mask business exceptions with unlock errors.
- **Missing rows:** the sample does not negative-cache `null`, so hot missing keys retry after every wait cycle; in production add a short-TTL sentinel per Section 5.
- **Exceptions:** if Redis `GET`/`SET` times out, add a **circuit breaker + bounded Bigtable fallback**; never let all Java requests fan out to the source.
- **Stale data:** after Bigtable mutations, invalidate and guard against fill races.
- **Security:** validate tenant/order IDs; never embed unvalidated raw user input in keys or cache cross-scope responses.
- **Observability:** instrument cache hits/misses, lock contention, wait budgets, Bigtable fetch latency, and Bigtable read QPS.
- **Failure testing:** test lock owner crashes, lock expiry, Redis outages, Bigtable timeouts, concurrent writes, rolling deploys, and failovers.

**Note:** if the source row does not exist, the owner returns `null` while waiters still see an empty key; this is exactly why **negative caching with a dedicated sentinel** is needed rather than dropping concurrency controls.

## 11. Race Condition: Stale Values Overwriting Fresh Cache Entries

Consider this sequence:

~~~text
A: Cache MISS → starts Bigtable read (v1)
B: Updates Bigtable to v2 → DEL cache
B: New request reads v2 → SET cache = v2
A: Slow Bigtable read v1 finishes → SET cache = v1
Result: cache holds stale v1 despite post-update invalidation.
~~~

**A distributed lock on cache misses is insufficient to stop this** if the write/invalidation path does not participate in the same version/coordination scheme. Remediations depend on requirements:

1. **Accept bounded staleness:** short TTL when business logic tolerates lag; fits non-sensitive catalogs.
2. **Versioned cache entries:** every snapshot carries `sourceVersion`, and refreshes/invalidations apply only if the new version is not older than the cached version using an **atomic comparison** in Redis.
3. **Generation keys:** change key namespaces according to a durably stored source version/generation; readers need a reliable way to learn the current version.
4. **Event-driven invalidation:** after source commit, publish an event (with version) and have consumers delete/mark stale; must handle duplicate/out-of-order events.
5. **Strong-consistency path:** for critical orders/payments, read the source directly or verify version/authorization without relying on cache.

**Never assume "delete cache after write" guarantees absolute consistency.** If an update/invalidation fails between Bigtable and Redis or two processes race, stale data can reappear. In Bigtable, updating **one row** is atomic; never extend that assumption to a transaction spanning multiple rows plus Redis.

## 12. Operating Memorystore: Creating, Configuring, Connecting, and Cleanup

**The commands below are for sandbox learning only.** They can create a continuously billed Redis instance. If your team already owns a lab instance, prefer read-only observation instead of provisioning a new one.

### 12.1. Checking Connectivity and Configuration

~~~bash
gcloud auth list
gcloud config get-value project

gcloud redis instances list \
  --project=PROJECT_ID \
  --region=asia-southeast1

gcloud redis instances describe cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Inspect `host`, `port`, `tier`, `memorySizeGb`, `authorizedNetwork`, `redisConfigs`, state, and policies. **Never print AUTH strings/passwords** into logs or learning notes.

### 12.2. Creating an Illustrative Basic Tier Instance

~~~bash
# Run ONLY in a sandbox project with an approved VPC.
gcloud redis instances create cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --size=1 \
  --tier=basic \
  --network=projects/PROJECT_ID/global/networks/VPC_NAME \
  --redis-config=maxmemory-policy=allkeys-lru
~~~

This is **Memorystore for Redis** (non-cluster), not Redis Cluster or Valkey. `VPC_NAME` must exist, and IP ranges/peering/Private Service Access must match the connection mode. Basic Tier suits demos only; production typically evaluates **Standard Tier HA**, though HA does not mean cached data can never be lost.

If using **Private Services Access**, configure VPC/service networking beforehand per docs; never create test instances on a production VPC.

### 12.3. Observing Eviction and TTL with `redis-cli`

**Run `redis-cli` from a VM/GKE/workload with a VPC path to the private endpoint**; Cloud Shell or a laptop **cannot** reach Memorystore's private IP by default.

~~~bash
# Retrieve INSTANCE_HOST and INSTANCE_PORT from gcloud describe.
redis-cli -h INSTANCE_HOST -p INSTANCE_PORT PING

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  SET orders:v1:tenantA:OD-42 '{"status":"PAID"}' EX 60

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  TTL orders:v1:tenantA:OD-42

redis-cli -h INSTANCE_HOST -p INSTANCE_PORT \
  GET orders:v1:tenantA:OD-42
~~~

If the instance enforces **Redis AUTH or in-transit encryption**, pass matching **AUTH/TLS and certificate verification** flags; secrets are omitted here to avoid encouraging credential copying. Never run `KEYS *` or `FLUSHALL` on instances serving real workloads.

To inspect the instance policy without modifying anything:

~~~bash
gcloud redis instances describe cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1 \
  --format="yaml(redisConfigs,host,port,memorySizeGb,tier)"
~~~

If `redisConfigs` omits `maxmemory-policy`, the instance is likely using the **default**. Modify policies through supported service configuration rather than treating `CONFIG SET` from `redis-cli` as a standard Memorystore admin mechanism.

### 12.4. Connecting Cloud Run with the Right Network

Cloud Run needs **Direct VPC egress** or **Serverless VPC Access** to reach a private Memorystore endpoint. Google Cloud recommends **Direct VPC egress** where suitable for lower latency, higher throughput, and no managed connector instance charges. **Deploy/network config** permissions belong to Google Cloud IAM, while **Redis AUTH/TLS** is a separate data-plane layer.

~~~text
Cloud Run service
  → Valid VPC egress + firewalls/routes
  → Memorystore private IP:port
  → Redis AUTH/TLS per instance configuration
  → Bigtable API via service account + separate Bigtable IAM
~~~

Never open Redis to the public Internet, and never assign Owner/Editor roles to "fix a timeout." On `ECONNREFUSED`/timeout, inspect VPC, region, routes/firewalls, TLS, and DNS/host before blaming Bigtable IAM.

### 12.5. Cleaning Up the Sandbox

~~~bash
# DELETES a real instance; run only after verifying ownership and zero consumers.
gcloud redis instances delete cache-lab \
  --project=PROJECT_ID \
  --region=asia-southeast1
~~~

Deleting an instance wipes all cache entries and can trigger a miss storm for active apps. Never run cleanup without confirming the lab instance is not shared.

## 13. Monitoring: Measuring Effectiveness and Detecting Issues

| Signal | Cloud Monitoring / app metric | Interpretation |
|---|---|---|
| Cache hit ratio | `redis.googleapis.com/stats/memory/cache_hit_ratio` and app hit/miss | Share of reads served from cache |
| Redis keyspace misses | `redis.googleapis.com/stats/keyspace_misses` | Lookups finding no key |
| Evicted keys | `redis.googleapis.com/stats/evicted_keys` | Keys removed due to memory pressure |
| Expired keys | `redis.googleapis.com/stats/expired_keys` | Keys expired via TTL |
| Key count with TTL | `redis.googleapis.com/keyspace/keys_with_expiration` | Checks whether TTLs are being forgotten |
| Average key TTL | `redis.googleapis.com/keyspace/avg_ttl` | Evaluates cache entry lifetimes |
| Memory usage ratio | `redis.googleapis.com/stats/memory/usage_ratio` | Proximity to `maxmemory` |
| **System** memory usage ratio | `redis.googleapis.com/stats/memory/system_memory_usage_ratio` | System headroom; alert under high pressure |
| Redis main-thread CPU | `redis.googleapis.com/stats/cpu_utilization_main_thread` | Expensive commands or traffic spikes |
| Request latency | Java p50/p95/p99; Bigtable read latency | Is caching actually improving user latency? |
| Stampede rate | App lock contention, retries, coalesced requests | How many requests contend for a refresh |
| Source load | Bigtable read QPS/latency and billing | Is a miss storm overwhelming Bigtable? |

**A high hit ratio is not enough:** you could be caching wrong data/permissions or holding stale payloads too long. Simultaneously monitor **freshness violations, invalidation failures, backend error rates, p99, and cost**.

### 13.1. Interpreting Metrics by Cause

- **Expired keys rising while evictions stay flat:** TTLs are working; rising source load may come from synchronized expirations.
- **Evicted keys spiking with high memory usage ratio:** working set exceeds cache capacity; resize instance, review policy, shrink payloads.
- **Misses rising, Bigtable p99 rising, Redis healthy:** likely a stampede/avalanche or a deploy changing key schemas.
- **High Redis CPU and rising cache latency:** hot keys, expensive commands, connection churn, or excessive polling.
- **High hit ratio yet wrong prices shown:** invalidation/version bug; **never try to fix this by adding RAM**.
- **Redis disconnects after failover/maintenance:** clients must reconnect with **exponential backoff + jitter** instead of reusing dead sockets indefinitely.

### 13.2. Example SLOs

~~~text
Orders API (catalog snapshot):
- GET p95 < 150 ms under normal conditions
- Target cache hit ratio > 90% for the hot set
- Cache staleness <= 60 s after a source update
- Redis outages do not push Bigtable read QPS past provisioned limits
- Zero cross-tenant data leakage
~~~

These thresholds are **illustrative targets for a team to measure and own**, not Google Cloud SLAs. Where strong consistency is required, **freshness and authorization** outweigh hit-ratio targets.

## 14. Troubleshooting and Runbook

| Symptom | Likely cause | Action |
|---|---|---|
| Redis `GET` always misses | Namespace mismatch, overly short TTL, serialization, or eviction | Check key schema, `TTL`, app metrics |
| Newly written cache entry disappears early | Memory eviction | `evicted_keys`, policy/capacity |
| Redis OOM while many keys remain | `volatile-*` with non-TTL keys; memory overhead | Check `keys_with_expiration` and `maxmemory` |
| 5,000 requests hit Bigtable together | Hot key expired without coalescing | Single-flight/Redis lease, bounded stale if permitted |
| Many keys miss together at 12:05 | Synchronized TTLs | Jitter and rate-limited hot-set prewarming |
| Nonexistent IDs spike Bigtable QPS | Cache penetration | Validation, negative caching, rate limits |
| Lock never releases | Missing TTL or failed network unlock | `PX` lease, atomic compare-and-delete, monitoring |
| Instance A deletes B's lock | Plain `DEL` after lease expiry | Token + atomic Lua compare-and-delete |
| Cache holds v1 after v2 update | Slow-fill race or failed invalidation | `sourceVersion`/fencing and invalidation retries |
| Cloud Run cannot reach Redis private IP | Wrong VPC egress/routes/firewalls | Check Direct VPC egress, network, and endpoint |
| Cloud Run intermittently times out after maintenance | Client fails to reconnect/fail over | Keepalives, backoff+jitter, short timeouts |
| Bigtable returns 403 | Java runtime SA lacks Bigtable IAM | Fix source IAM—not Redis `maxmemory` |
| Redis cache returns another tenant's data | Key lacks tenant/permission scope | Stop faulty route, fix key/auth, and purge affected entries |
| Redis cost rises while p95 stays flat | Oversized working set/capacity | TCO analysis, sample hits/misses, shrink cached payloads |

**Seven-step runbook:**

1. Identify the request/tenant/key class, Cloud Run region, and onset time.
2. Separate **cache misses** from **cache connection errors** and **source errors**.
3. Inspect Redis memory/system memory, expired/evicted keys, and hit ratio; distinguish TTL from eviction.
4. Measure requests per hot key, lock contention, waiting budget, and Bigtable QPS.
5. Check invalidation/write `sourceVersion` so stale data is not restored.
6. Fix in sandbox: TTL jitter, policy/headroom, bounded waits, local/distributed coalescing; test failures.
7. Deploy with observability, alerts on p99/freshness/source overload, and cost tracking.

**Never remediate with `FLUSHALL` on a production cache**, as it triggers a **mass miss** that can crush Bigtable. If broad invalidation is unavoidable, use controlled prewarming, rate limiting, and canary rollouts.

## 15. Case Study: Flash Sale with Java, Bigtable, and Memorystore

**Hypothetical scenario:** RetailOne runs a Java Catalog API on Cloud Run; Bigtable stores product snapshots keyed by `tenant#productId`, and Memorystore for Redis serves as the cache. At 12:00, 20,000 shoppers view one discounted product simultaneously.

**Initial configuration:**

- Cache key `product:SKU-102` (missing tenant).
- Exact 300-second TTL, entire catalog prewarmed at once.
- Default `volatile-lru`, with some keys written without TTL.
- Java handles MISS by having **every request** query Bigtable directly.
- On price updates, code updates Bigtable and fires `DEL` without guaranteed retries.
- No locking and no Bigtable fallback concurrency limit.

### 15.1. Incident Analysis

| Symptom | Root cause |
|---|---|
| p99 spikes at 12:05 | Avalanche: synchronized TTL expiration |
| Bigtable reads the same row thousands of times | Stampede: missing coalescing |
| OOM when cache fills | Keys without TTL under `volatile-lru` |
| Stale prices occasionally appear after invalidation | Slow-fill race or failed cache `DEL` |
| Data leaks across shops | Cache key missing tenant scope |
| Redis failover spikes source QPS | Missing degraded-mode/backpressure |

### 15.2. Remediation Plan

1. Change key to `products:v3:tenantA:SKU-102` with schema version and tenant.
2. Set TTL **with jitter not exceeding freshness SLO**; choose soft/hard TTL if bounded staleness is allowed for catalogs.
3. Add **local single-flight** per Cloud Run instance and a **Redis lease** so only one refresher hits Bigtable.
4. Non-owners poll briefly with jitter; if waiting budget expires, return stale/503—**never flood Bigtable**.
5. Add `sourceVersion` with atomic version comparisons; mutate Bigtable first then invalidate reliably.
6. For a pure cache, evaluate `allkeys-lru` or guarantee every key has a TTL; monitor evictions/system memory.
7. Configure Direct VPC egress, production Redis AUTH/TLS, and a scoped runtime SA with Bigtable Reader.
8. Rehearse cache outages, failovers, source 503s, timeouts, concurrent writes, missing keys, and multi-tenant isolation.
9. Measure p95/p99, Bigtable QPS, hit ratio, hot-key lock contention, and **cost per successful request**.

**Never "fix" pricing freshness by raising TTL to 24 hours**: that cuts Bigtable reads at the cost of serving wrong prices. Security and freshness are hard constraints before optimizing hit ratio.

## 16. Exercises and Self-Assessment Questions

### Exercise 1 — TTL vs. Eviction

A key is written with `SET k v EX 300`, yet disappears after 20 seconds when Redis memory fills up.

**Question:** is this possible? Which metrics/policies should you inspect?

**Hint:** yes; eviction operates independently of TTL. Inspect `evicted_keys`, `maxmemory-policy`, and system memory usage.

### Exercise 2 — Default `volatile-lru`

A Memorystore for Redis instance using default `volatile-lru` holds 100,000 keys without TTLs; new writes start failing with OOM.

**Question:** why? Propose two fixes and how to measure them.

**Hint:** keys without TTLs are ineligible for eviction; add TTLs or switch to `allkeys-lru` for pure caches, and monitor memory headroom.

### Exercise 3 — Choosing TTLs Against SLOs

Business requires product prices to be at most 5 minutes stale; the cache uses `baseTTL=300s` with `±60s` jitter.

**Question:** does this violate the SLO? Propose proper jittering.

**Hint:** max TTL reaches 360s, breaching the budget; use non-positive jitter or soft/hard TTLs within bounds.

### Exercise 4 — Mitigating Stampedes

A hot key expires under 10,000 concurrent requests across 20 Cloud Run instances.

**Question:** roughly how many Bigtable reads remain with local single-flight alone? Why is distributed coordination needed?

**Hint:** roughly one read per instance (up to 20), not reduced to one globally.

### Exercise 5 — Safe Lock Deletion

A holds a lock with token A and a 15s TTL. After 16s, B acquires the lock with token B; A finishes and calls `DEL lock`.

**Question:** what went wrong? State the safe-release rule.

**Hint:** compare token + `DEL` atomically inside a Lua script; locks also do not replace version/fencing checks at the source.

### Exercise 6 — Cache-Aside Write Race

A begins loading version v1. B writes v2 to Bigtable and deletes the cache; B refreshes v2; A finishes late and overwrites the cache with v1.

**Question:** is single-shot TTL/invalidation enough? How do you prevent stale overwrites?

**Hint:** compare `sourceVersion` atomically, use generation keys, or read from source on paths needing strong consistency.

### Exercise 7 — Negative Caching

A bot sends 100,000 nonexistent order IDs. Java hits Bigtable on every miss.

**Question:** how should you size negative-cache TTLs, and why must you never negative-cache 403/timeout errors?

**Hint:** short TTL paired with input validation/rate limits; distinguish genuine nonexistence from system/auth errors.

### Exercise 8 — Redis Outage

Redis disconnects for 2 minutes; Java falls back to Bigtable unboundedly. Bigtable p99 spikes and hits quota limits.

**Question:** what degraded mode is appropriate?

**Hint:** circuit breakers, bounded fallback, rate limits, 503/`Retry-After`, or serving stale within policy bounds.

### Exercise 9 — Multi-Tenant Caching

Two tenants both have `orderId=OD-42`, yet the cache key is only `orders:OD-42`.

**Question:** what is the risk? How do you fix the key and authorization checks?

**Hint:** include tenant/authorization scope in the key, authorize the caller before reading cache, and never replace policy checks with cache lookups.

### Exercise 10 — Production Design

Design cache-aside for a Java Catalog API backed by Bigtable with Redis in a VPC. Specify: key schema, TTL jitter, `maxmemory` policy, two-level single-flight, concurrency bounds, source write invalidation/versioning, AUTH/TLS, monitoring, and cost. Include a **test when a hot key expires under 5,000 concurrent requests**.

## 17. Production Checklist

- [ ] Bigtable or the primary database is the **source of truth**; cache is expendable and reconstructible.
- [ ] Only cache data with an explicit freshness budget; never use cache as sole payment/authorization authority.
- [ ] Keys include namespace, schema version, tenant, and content-affecting parameters.
- [ ] Payloads are compact, versioned, free of tokens/secrets, and serialized per schema.
- [ ] Every cache write sets a TTL; expiration and memory eviction are clearly distinguished.
- [ ] TTL jitter never breaches freshness SLOs; negative caching is brief and strictly for confirmed not-found cases.
- [ ] Aware of Memorystore for Redis default `volatile-lru` and the risk of keys without TTLs.
- [ ] Measured `maxmemory-gb`, memory/system memory ratios, evictions, and expired keys.
- [ ] Implemented local single-flight and distributed leases where hot keys/scale warrant them.
- [ ] Locks use `SET NX PX` with unique tokens and atomic compare-and-delete unlocks.
- [ ] Implemented bounded waits, jitter, and backpressure; no spin-loops or unbounded fallbacks.
- [ ] Source update → invalidate; versioning/fallback paths exist for write/read races.
- [ ] Stale-while-revalidate enabled only for eligible data with hard freshness bounds.
- [ ] Redis outages/failovers cannot stampede Bigtable; clients reconnect with backoff.
- [ ] Cloud Run/VPC egress configured properly; Redis private networking, AUTH/TLS, and Secret Manager in place.
- [ ] Runtime SA holds least-privilege Bigtable IAM; Redis auth is separated from Google Cloud control-plane IAM.
- [ ] Alerts configured for p95/p99, hit ratio, source QPS, memory, evictions, and stampede/lock contention.
- [ ] Tested concurrency, malformed keys, not-found cases, concurrent writes, network failures, and Redis loss.
- [ ] Budgeted capacity/tier, networking, Cloud Run compute, Bigtable reads, and monitoring/logging.
- [ ] Never run `FLUSHALL` or delete production instances; sandbox cleanup verifies ownership first.

## 18. Official Documentation and References

Verify exact product versions, APIs, pricing, and configurations before deployment:

- [Memorystore for Redis — Overview](https://docs.cloud.google.com/memorystore/docs/redis/redis-overview)
- [Memorystore for Redis — Supported Redis configurations](https://docs.cloud.google.com/memorystore/docs/redis/supported-redis-configurations)
- [Memorystore for Redis — Memory management best practices](https://docs.cloud.google.com/memorystore/docs/redis/memory-management-best-practices)
- [Memorystore for Redis — General best practices](https://docs.cloud.google.com/memorystore/docs/redis/general-best-practices)
- [Memorystore for Redis — Create and manage instances](https://docs.cloud.google.com/memorystore/docs/redis/create-manage-instances)
- [Memorystore for Redis — Configure Redis](https://docs.cloud.google.com/memorystore/docs/redis/configure-redis)
- [Memorystore for Redis — Connect from Cloud Run](https://docs.cloud.google.com/memorystore/docs/redis/connect-redis-instance-cloud-run)
- [Memorystore for Redis — Supported monitoring metrics](https://docs.cloud.google.com/memorystore/docs/redis/supported-monitoring-metrics)
- [Memorystore for Redis Cluster — Supported configurations](https://docs.cloud.google.com/memorystore/docs/cluster/supported-instance-configurations)
- [Memorystore for Valkey — Best practices](https://docs.cloud.google.com/memorystore/docs/valkey/general-best-practices)
- [Bigtable — Schema design and row key practices](https://docs.cloud.google.com/bigtable/docs/schema-design)
- [Redis — Key eviction policies](https://redis.io/docs/latest/reference/eviction/)
- [Redis — SET NX/PX and safe lock release](https://redis.io/docs/latest/commands/set/)
- [Lettuce Java client](https://redis.github.io/lettuce/)
- [Google Cloud — Memorystore pricing](https://cloud.google.com/memorystore/pricing)

**Key takeaway:** **Cache-aside** excels when a Java API repeatedly reads the same Bigtable records, yet **Redis is only an expendable copy**. **TTL** governs entry lifetime; **eviction** depends on memory pressure and `maxmemory-policy`—defaulting to `volatile-lru` on Memorystore for Redis. Against hot-key misses, combine **TTL jitter, single-flight, tokenized Redis leases + atomic compare-and-delete, bounded waits, and bounded stale responses**. Pair with **safe source-versioned invalidation**, and monitor **freshness, p99, evictions, Bigtable QPS, and cost** without sacrificing correctness or security just to boost hit ratio.
