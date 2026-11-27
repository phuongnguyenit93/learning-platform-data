# Memory Growth, High Eviction, and Performance Degradation in Spring Data Redis

> **Module:** Spring Data Redis  
> **Chapter:** Troubleshooting  
> **Topic:** Analyzing Redis memory growth, high eviction, and latency degradation in a Spring Boot application; investigating via Redis metrics, Spring Cache, RedisTemplate, Repository, Stream, driver, and downstream metrics to choose a safe resolution.

## 1. Opening Scenario

A Spring Boot service uses Redis as a product cache. The dashboard reports:

~~~text
used_memory:          2.0 GiB -> 7.8 GiB
maxmemory:            8.0 GiB
evictions/sec:        0 -> 4,000
cache hit ratio:      96% -> 60%
DB queries/sec:      400 -> 6,000
HTTP p99:             140 ms -> 1,100 ms
~~~

It appears that Redis is "running out of RAM," yet there are at least three distinct phenomena here:

- **Memory growth:** Redis is holding more keys/values, metadata, buffers, or allocator memory.
- **Eviction:** Redis is removing keys due to memory pressure per `maxmemory-policy`.
- **Performance degradation:** Redis itself is slow, or increased cache misses are forcing the database/source API to work harder.

Not all memory growth is a leak, not all eviction is an error, and not every slow HTTP request is caused by slow Redis command execution.

### 1.1. Questions That Must Be Answered

1. Is this Redis instance purely a regenerable cache, or does it hold sessions, locks, counters, idempotency keys, or canonical data?
2. Is memory growing in the dataset or in RSS/allocator/client buffers?
3. Is the eviction rate increasing across all shards or on a single Redis primary?
4. Are there keys without TTL, overly large values, or cache keys that are rarely reused?
5. How did the cache hit ratio change, and how much did database fallback increase?
6. Did Redis command p95/p99 increase, or only HTTP p95/p99?
7. Is the Redis `maxmemory` policy appropriate for the data types stored?
8. Did a recent deploy change the serializer, cache prefix, data model, or TTL?

The goal is to find an **evidence-backed root cause**, not to shrink the RAM chart at any cost.

## 2. How Memory Pressure Causes Slowdowns

~~~mermaid
flowchart TD
    A["Cache key count or value size increases"] --> B["used_memory near maxmemory"]
    B --> C["Redis eviction increases"]
    C --> D["Cache hit ratio drops"]
    D --> E["DB / upstream fallback increases"]
    E --> F["HTTP latency increases"]
    F --> G["Concurrency and retries increase"]
    G --> E
    B --> H["Server CPU/queue/allocator overhead"]
    H --> F
~~~

There are two impact paths.

**Indirect path:** Redis `GET` stays fast, but a cache miss must query the database for 300 ms. When hot keys are evicted, the miss ratio climbs and the database becomes overloaded.

**Direct path:** The Redis server is busy handling memory eviction, large commands, persistence, or CPU/queue backlogs; Redis commands on the client slow down as well.

### 2.1. Impact of Hit Ratio

Suppose an API handles 10,000 requests/second, each checking the cache once:

| Hit Ratio | Cache Misses/Second |
|---|---:|
| 95% | 500 |
| 80% | 2,000 |
| 60% | 4,000 |

A hit ratio drop from 95% to 60% sends **8 times** more misses downstream in this model.

These numbers are illustrative; real systems also involve local caches, negative caching, request coalescing, and multiple Redis commands per request.

### 2.2. High Eviction Does Not Automatically Mean Redis Is Broken

For a cache-only Redis instance, `allkeys-lru` may intentionally evict cold keys to keep the dataset within the memory budget.

What matters is **whether the evicted keys are hot**, whether cache hits drop severely, whether downstream systems have sufficient capacity, and whether critical state is affected.

## 3. Understanding Redis Memory Categories

A conceptual breakdown:

~~~text
Redis process
├─ Key/value dataset
├─ Key dictionary + expiry metadata
├─ Data structure overhead
├─ Client input/output buffers
├─ Replication buffers
├─ Redis internal structures
├─ Allocator fragmentation / reserved pages
└─ Persistence fork / copy-on-write overhead
~~~

### 3.1. used_memory

`used_memory` is the memory reported by the Redis allocator accounting. A key holding a 100-byte value does not occupy only 100 bytes of RAM because there is also the key name, dictionary entry, metadata, expiry record, and allocator alignment.

### 3.2. used_memory_rss

`used_memory_rss` is the process resident memory as seen by the OS. It can exceed `used_memory` due to allocator fragmentation, retained pages, COW, or other process overhead.

If `used_memory` drops while RSS does not decrease immediately, you cannot conclude that data is still stored under the old keys.

### 3.3. mem_fragmentation_ratio

Example:

~~~text
used_memory:               3.0 GiB
used_memory_rss:           5.0 GiB
mem_fragmentation_ratio:   1.67
~~~

This is a signal to inspect the allocator, RSS, and host metrics. Do not use a fixed threshold like 1.5 to declare a "memory leak" across all Redis versions.

You can combine `allocator_frag_ratio`, `allocator_rss_ratio`, and `MEMORY STATS` if supported by your version.

### 3.4. maxmemory Is Not an Absolute RSS Limit

`maxmemory` determines when Redis triggers eviction or returns OOM errors per policy when memory accounting crosses the threshold.

It does not guarantee that Redis process RSS stays strictly below that exact value. There are still buffers, allocator fragmentation, persistence/replication overhead, and OS/container memory.

Some versions provide `mem_not_counted_for_evict` to help analyze memory excluded from eviction accounting.

### 3.5. used_memory_dataset and Overhead

`used_memory_dataset` helps estimate the dataset, while `used_memory_overhead` helps understand overhead. Do not sum fields that overlap to calculate total process memory; read the semantics for your exact Redis version.

### 3.6. Dataset Growth Differs from RSS Growth

Example:

~~~text
used_memory_dataset:  3.0 -> 3.1 GiB
used_memory:          4.0 -> 4.1 GiB
RSS:                  5.0 -> 7.2 GiB
keys:                 nearly stable
~~~

In this case, investigate fragmentation, OS memory, client buffers, and persistence before shortening cache TTLs.

## 4. First Redis Commands to Check

Run from an authorized environment with the right endpoint and credentials:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli INFO clients
redis-cli INFO commandstats
redis-cli INFO cpu
redis-cli INFO persistence
~~~

For Redis Cluster, inspect **each primary**, not just one node or a cluster-wide average.

Managed Redis providers may restrict `CONFIG`, `MEMORY`, or diagnostic commands; use the provider's monitoring tools when needed.

### 4.1. INFO memory

| Field | Meaning |
|---|---|
| `used_memory` | Memory recorded by the Redis allocator |
| `used_memory_rss` | Resident memory per the OS |
| `used_memory_peak` | Peak memory usage |
| `used_memory_dataset` | Dataset memory estimate |
| `used_memory_overhead` | Memory overhead estimate |
| `maxmemory` | Memory eviction limit |
| `maxmemory_policy` | Eviction strategy |
| `mem_fragmentation_ratio` | Fragmentation indicator |
| `allocator_frag_ratio` | Allocator fragmentation, if available |
| `mem_not_counted_for_evict` | Memory excluded from eviction accounting, if available |
| `lazyfree_pending_objects` | Objects queued for background freeing |

Fields depend on the Redis version; not every field exists on every instance.

### 4.2. INFO stats

Typically includes:

~~~text
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
total_commands_processed
instantaneous_ops_per_sec
rejected_connections
~~~

`evicted_keys` and `expired_keys` are usually **cumulative counters**, not current rates.

### 4.3. Calculating evictions/sec

Example:

~~~text
T1: evicted_keys = 120000
T2 after 60s:    = 150000
~~~

\[
\text{evictions/sec}=\frac{150000-120000}{60}=500
\]

If Redis restarts, counters can reset. When computing rates, detect resets and handle the time window properly.

### 4.4. INFO keyspace

Example:

~~~text
db0:keys=2000000,expires=800000,avg_ttl=600000
~~~

Roughly 40% of keys have an expiration, yet you cannot conclude the remaining 60% are leaked. They could be canonical state, secondary indexes, or keys meant to be kept long-term.

Classify **by namespace/owner**.

### 4.5. INFO clients

Client counts and output buffers can explain memory growth even when key counts are flat. A Redis client reading a very large response while processing slowly causes Redis to hold pending bytes in its buffer.

## 5. MEMORY STATS, MEMORY USAGE, and MEMORY DOCTOR

~~~bash
redis-cli MEMORY STATS
redis-cli MEMORY DOCTOR
redis-cli MEMORY USAGE app:prod:cache:product:101
~~~

### 5.1. MEMORY STATS

Helps break down dataset, overhead, allocator, fragmentation, and buffers depending on Redis version.

### 5.2. MEMORY USAGE

Measures the footprint of a single key. For collections, Redis may use sampling when estimating, so check the `SAMPLES` argument and measurement behavior for your specific version.

Do not fire millions of `MEMORY USAGE` calls in bursts against production.

### 5.3. MEMORY DOCTOR

Provides heuristic hints, not conclusive proof of root cause.

### 5.4. Command Set to Inspect a Key

~~~bash
redis-cli TYPE app:prod:cache:product:101
redis-cli MEMORY USAGE app:prod:cache:product:101
redis-cli PTTL app:prod:cache:product:101
~~~

If the key is not a String, do not use `GET` to try to read its contents.

## 6. Eviction and Expiration Are Two Different Things

### 6.1. Expiration

A key with a TTL:

~~~redis
SET cache:product:101 "json" EX 300
~~~

The key will expire according to expiration semantics. Redis may handle expiration lazily on access or through active expiration sampling.

Rising `expired_keys` indicates keys whose TTL elapsed were removed.

### 6.2. Eviction

When Redis experiences memory pressure per `maxmemory`, it can select keys to remove according to `maxmemory-policy`.

Rising `evicted_keys` indicates keys were removed due to eviction, not merely TTL expiration.

### 6.3. Comparison Table

| Aspect | Expiration | Eviction |
|---|---|---|
| Cause | TTL elapsed | Memory pressure |
| Counter | `expired_keys` | `evicted_keys` |
| Requires maxmemory? | No | Usually yes |
| Can non-expired keys be removed? | No, not by expiration | Yes, if policy allows |
| Are keys without TTL removed? | No, not by expiration | Yes, with `allkeys` policies |
| Can it increase cache misses? | Yes | Yes |

### 6.4. TTL Is Not a Guarantee of Retaining RAM

A key set with a 1-hour TTL can still be evicted after 5 minutes if Redis runs low on RAM and the policy permits it.

### 6.5. High Expiration Can Still Hurt Performance

An overly short TTL can cause frequent cache misses. `evicted_keys=0` does not mean the cache is effective.

## 7. maxmemory-policy and Eligible Key Sets

| Policy | Eligible Keys | Selection Method |
|---|---|---|
| `noeviction` | None evicted automatically | Memory-increasing writes may return OOM |
| `allkeys-lru` | All keys | Approximate least recently used |
| `allkeys-lfu` | All keys | Approximate least frequently used |
| `allkeys-random` | All keys | Random |
| `volatile-lru` | Only keys with TTL | Approximate LRU |
| `volatile-lfu` | Only keys with TTL | Approximate LFU |
| `volatile-random` | Only keys with TTL | Random |
| `volatile-ttl` | Only keys with TTL | Prefers shortest remaining TTL |

### 7.1. LRU/LFU Are Not Exact Algorithms

Redis makes selections based on approximation/sampling mechanisms. LFU can fit frequently accessed data well, but is not universally better than LRU for every workload.

### 7.2. volatile-lru and OOM Errors

Suppose:

~~~text
maxmemory:                 8 GiB
non-TTL keys:              7.4 GiB
TTL keys:                  0.3 GiB
maxmemory-policy:          volatile-lru
~~~

When there are too few keys with TTL or not enough memory can be freed, Redis may reject memory-increasing writes even though many non-TTL keys exist.

That is not a bug in the LRU algorithm, but **insufficient eligible keys**.

### 7.3. allkeys-lru for Cache-Only Redis

This can work well when all data is regenerable and eviction does not break business logic. Measure actual cache hits, miss penalties, memory, and latency.

### 7.4. allkeys-lru on Redis Holding Sessions/Locks/Idempotency

Dangerous if these critical states must not be lost. Redis can evict them just like ordinary cache keys.

Separate Redis caches from canonical/session/queue resources whenever retention requirements differ.

### 7.5. noeviction

Does not automatically evict keys under memory pressure, so memory-increasing writes may return:

~~~text
OOM command not allowed when used memory > 'maxmemory'
~~~

Applications must handle failures and have a capacity plan. `noeviction` does not replace persistence/backups.

## 8. Causes of Memory Growth

### 8.1. Normal Cache Warming

~~~text
10:00 used_memory 0.6 GiB
10:05 used_memory 2.0 GiB
10:15 used_memory 3.7 GiB
10:30 used_memory 4.0 GiB
10:50 used_memory 4.0 GiB
~~~

If memory reaches a plateau, eviction is low, and cache hits increase, memory growth is part of normal operation.

### 8.2. RedisTemplate Without Setting TTL

~~~java
redis.opsForValue().set("cache:product:" + id, json);
~~~

Without another expiration/lifecycle policy, new data can persist indefinitely.

### 8.3. Overly Long TTL

Caching a rarely repeated search query with a 30-day TTL keeps cold keys in RAM, potentially pushing hot keys out of the cache.

### 8.4. High Key Cardinality

~~~text
cache:search:desk:request:uuid1
cache:search:desk:request:uuid2
cache:search:desk:request:uuid3
~~~

If you include a request UUID, timestamp, or non-canonical query params in the key, nearly every request can create a brand-new key.

### 8.5. Big Values

A 5 MiB JSON multiplied by 10,000 keys already requires roughly 48.8 GiB of payload before counting overhead. Measure serialized bytes and key footprints.

### 8.6. Very Many Tiny Keys

Millions of keys holding 20-byte values still incur metadata, dictionary, and allocator overhead. Never estimate capacity using value bytes alone.

### 8.7. Repository Secondary Indexes

Spring Data Redis Repositories may add index keys, expiration metadata, and shadow copies depending on version and configuration. Entity count does not equal Redis key count.

### 8.8. Redis Streams and Collections

A Stream receiving `XADD` without retention can grow forever. The same applies to Lists, Sets, and ZSets if producers keep adding while consumers/cleanup fail to keep pace.

### 8.9. Buffers and RSS

Stable key counts alongside growing memory can stem from client output buffers, replication, persistence, or fragmentation.

### 8.10. Cache Namespace Version Overlap

After a deploy:

~~~text
products:v1::101
products:v2::101
~~~

V1 and V2 coexisting increases memory temporarily or permanently if old keys lack TTL/cleanup.

## 9. Finding Big Keys and Fast-Growing Namespaces

### 9.1. redis-cli --bigkeys

~~~bash
redis-cli --bigkeys
~~~

Used to survey collection/key sizes. The tool still generates server work; run only when authorized, limit its impact, and understand node scoping in Redis Cluster.

### 9.2. Using Cardinality Commands

~~~bash
redis-cli TYPE app:prod:cache:catalog
redis-cli HLEN app:prod:cache:catalog
redis-cli LLEN app:prod:queue:jobs
redis-cli SCARD app:prod:index:products
redis-cli ZCARD app:prod:ranking
redis-cli XLEN app:prod:stream:orders
redis-cli STRLEN app:prod:cache:product:101
~~~

Do not run `HGETALL` or `LRANGE 0 -1` on huge collections just to check their size.

### 9.3. Use SCAN Instead of KEYS Across All of Redis

~~~bash
redis-cli --scan --pattern 'app:prod:cache:*'
~~~

SCAN:

- Does not guarantee a consistent snapshot while the keyspace changes.
- May return duplicate keys.
- `COUNT` is only a hint.
- May need to scan each primary in Redis Cluster.
- Pattern matches raw key bytes, not necessarily every Java logical key representation.
- May expose tenant IDs/PII embedded in key names.

### 9.4. Assign Owners to Namespaces

| Namespace | Data | Retention | Owner to Check |
|---|---|---|---|
| `cache:products:*` | Product DTO | 5–30 minutes | Catalog |
| `cache:search:*` | Search results | Short and bounded | Search |
| `session:*` | Login sessions | Per session lifecycle | Identity |
| `idem:payment:*` | Idempotency | Per business retention | Billing |
| `stream:orders:*` | Events/work | Retention/ack | Order processor |

Do not delete keys just because their names look unfamiliar. Determine whether they belong to disposable cache or state that must not be lost.

## 10. TTL Is Not a Memory Quota

### 10.1. Estimating Live Key Count

When creating 1,000 unique keys/second with a 600-second TTL in steady state:

\[
N_{\text{live}}\approx 1000 \times 600 = 600000
\]

These numbers are illustrative, excluding overwrites, expiration, eviction, and uneven traffic.

### 10.2. Overly Short TTL

Increases cache misses, DB fallback, and HTTP p99, even though Redis memory drops.

### 10.3. Overly Long TTL

Retains many cold keys, increases memory pressure, and can cause hot keys to be removed by the eviction policy.

### 10.4. Basing TTL on Freshness and Reuse

Consider:

- Data update frequency.
- Maximum tolerated staleness.
- Cost of a cache miss.
- Value size.
- Reuse probability.
- Memory budget.
- Whether reliable invalidation exists after writes.

### 10.5. TTL Jitter

To prevent many keys from expiring at the same instant:

~~~java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

public Duration ttlWithJitter() {
    long seconds = ThreadLocalRandom.current()
            .nextLong(480, 601);
    return Duration.ofSeconds(seconds);
}
~~~

If the freshness bound is at most 600 seconds, choose jitter that does not exceed 600 seconds. Do not blindly add jitter past your SLA.

## 11. Setting Explicit TTLs with RedisTemplate

### 11.1. Writing Time-Bounded Cache Entries

~~~java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductCache {
    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String key, String json) {
        redis.opsForValue()
                .set(key, json, Duration.ofMinutes(10));
    }

    public String read(String key) {
        return redis.opsForValue().get(key);
    }
}
~~~

Illustrative code only. Keys should use a validated namespace/service/tenant scope, never trusting raw user headers.

### 11.2. Reading TTL

~~~java
Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
~~~

Typically:

- `ttl > 0`: key has remaining lifetime.
- `ttl == -1`: key exists with no expiration.
- `ttl == -2`: key does not exist.

Within a pipeline/transaction context, check the specific API return behavior.

### 11.3. Redis Hash

~~~java
redis.opsForHash().put(key, "name", "Desk");
redis.expire(key, Duration.ofMinutes(10));
~~~

Traditional TTL is the **TTL of the entire Hash key**, not automatically attached per field. Two separate calls are not atomic, so when persistence and TTL must be guaranteed together, design an appropriate transaction/script.

Some newer Redis versions offer hash field expiration commands, but do not assume every Spring Data Redis or Redis deployment supports that API.

### 11.4. List, Set, ZSet

`LPUSH`, `SADD`, and `ZADD` do not add a TTL automatically. Temporary indexes/queues require separate retention and cleanup.

## 12. Spring Cache and RedisCacheManager

### 12.1. Spring Cache Annotations

~~~java
@Cacheable(cacheNames = "products", key = "#id")
public ProductDto getProduct(String id) {
    return source.load(id);
}
~~~

Expiration and serializer are determined by the Redis Cache configuration, not by whatever custom `RedisTemplate` happens to exist in the project.

### 12.2. Spring Boot Properties

~~~yaml
spring:
  cache:
    type: redis
    redis:
      time-to-live: 10m
      cache-null-values: false
      use-key-prefix: true
~~~

Example for an appropriate Spring Boot version; actual configuration may be overridden by a custom `CacheManager`.

### 12.3. Different TTLs per Cache

~~~java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
class RedisCacheConfig {

    @Bean
    RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withCacheConfiguration(
                        "products",
                        defaults.entryTtl(Duration.ofMinutes(30)))
                .withCacheConfiguration(
                        "searchResults",
                        defaults.entryTtl(Duration.ofMinutes(2)))
                .build();
    }
}
~~~

Use the specific API/configuration for your Spring Data Redis version. Changing TTL applies to new writes and does not automatically migrate existing keys.

### 12.4. Too Many Cache Key Variants

Query params that do not affect the response should not contribute to the cache key. If a cache key includes a trace ID, timestamp, or unstable full object, Redis may end up creating millions of unique keys.

### 12.5. @CacheEvict Differs from Redis Eviction

`@CacheEvict` is the application deleting a key for business logic. `evicted_keys` is the Redis server removing keys under memory pressure.

Do not use the `evicted_keys` counter to count how often Spring `@CacheEvict` runs.

### 12.6. allEntries=true Can Trigger a Miss Storm

~~~java
@CacheEvict(cacheNames = "products", allEntries = true)
public void clearAllProducts() {}
~~~

On a shared cache, this operation can wipe out large numbers of entries, trigger DB fallback spikes, and even affect multiple tenants. Prefer key-specific invalidation or controlled cleanup.

## 13. Redis Repository and Metadata Memory

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "products", timeToLive = 600)
public class ProductEntity {
    @Id
    private String id;
    private String name;
}
~~~

`timeToLive` in the annotation example is typically in seconds per the Spring Data Redis contract.

In addition to the entity Hash, a Repository may create:

- Secondary index keys from `@Indexed`.
- Keyspace bookkeeping.
- TTL-related metadata.
- Phantom/shadow copies under expiration event configurations.

Do not assume each entity occupies only one key. Measure the entire keyspace and know the data owner.

If a Redis Repository stores **canonical data**, the `allkeys-lru` policy may be inappropriate because entities could be lost.

## 14. Redis Streams and Queue Data

### 14.1. Streams Without Retention

~~~redis
XADD orders:events * type CREATED orderId 101
~~~

If written continuously without trimming, the Stream grows over time.

Inspect:

~~~bash
redis-cli XLEN orders:events
redis-cli XINFO STREAM orders:events
redis-cli XINFO GROUPS orders:events
redis-cli XPENDING orders:events worker-group
~~~

Check the PEL, consumers, and retention before using `XTRIM` or `MAXLEN`. Trimming unprocessed entries can compromise delivery/replay guarantees.

### 14.2. Lists and Sorted Sets

~~~bash
redis-cli LLEN queue:jobs
redis-cli ZCARD queue:scheduled
~~~

If producers outpace consumers, collection length and RAM grow. TTLs on separate cache Strings do not help these collections.

### 14.3. Pub/Sub Differs from Streams

Redis Pub/Sub does not normally keep durable history like Streams, but slow subscribers/client output buffers can still drive up memory usage.

## 15. Serialization and Payload Bytes

Redis values may be JDK bytes, String JSON, generic JSON with `@class`, or binary DTO formats. Memory footprints differ by schema/serializer.

Factors:

- Class metadata.
- Repeated field names in JSON.
- Object graphs/nested arrays.
- Compression.
- Per-key metadata.
- Internal Hash encodings.

Do not assume JSON is always smaller than JDK serialization or vice versa. Measure raw serialized lengths and `MEMORY USAGE` on sample data.

### 15.1. Reducing Big Payloads

Instead of caching the entire product catalog when a request only needs name and price, consider:

- Field-level data.
- Pagination.
- Smaller DTOs.
- Splitting aggregates by access patterns.
- Bounded responses.

### 15.2. Compression Has Trade-Offs

It reduces bytes but adds encode/decode CPU cost and migration complexity. Apply it only after benchmarking Redis RAM, network, JVM GC, and p99 together.

## 16. Measuring Cache Hit/Miss Properly

### 16.1. Redis GET Can Be Fast Even When HTTP Is Slow

~~~text
HTTP GET /products/101     500 ms
├─ Redis GET                 2 ms
├─ Cache MISS                0 ms
├─ DB query                450 ms
└─ Response processing      48 ms
~~~

This is a cache effectiveness or DB fallback issue, not slow Redis server `GET` execution.

### 16.2. Sample Micrometer Timer

~~~java
import java.util.concurrent.TimeUnit;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.data.redis.core.StringRedisTemplate;

public class MeasuredRedisCache {

    private final StringRedisTemplate redis;
    private final MeterRegistry registry;

    public MeasuredRedisCache(
            StringRedisTemplate redis,
            MeterRegistry registry) {
        this.redis = redis;
        this.registry = registry;
    }

    public String get(String key) {
        long started = System.nanoTime();
        String outcome = "error";

        try {
            String result = redis.opsForValue().get(key);
            outcome = result == null ? "miss" : "hit";
            return result;
        } finally {
            Timer.builder("app.redis.cache.lookup.duration")
                    .tag("operation", "GET")
                    .tag("outcome", outcome)
                    .register(registry)
                    .record(
                            System.nanoTime() - started,
                            TimeUnit.NANOSECONDS);
        }
    }
}
~~~

In production, you can pre-register meters. Never use full keys, `userId`, or `tenantId` as metric labels due to high cardinality and potential data exposure.

### 16.3. Cache Miss Differs from a Redis Error

`GET` returning null means the key does not exist. Timeouts or connection exceptions should not be caught and unconditionally turned into null; doing so causes metrics to mistake a Redis outage for cache misses.

### 16.4. Hit Ratio

\[
HitRatio = \frac{\Delta hits}{\Delta hits+\Delta misses}
\]

`keyspace_hits`/`keyspace_misses` from the Redis server do not match application-level Spring Cache hits/misses one-to-one; Redis counters may aggregate multiple clients and multiple commands per business request.

## 17. Redis Latency vs. Database Fallback

Measure by layer:

| Layer | Tools |
|---|---|
| HTTP/API | Actuator metrics, tracing |
| RedisTemplate | Timer around operations |
| Lettuce/Jedis | Command latency, connection/pool metrics |
| Redis Server | INFO cpu/commandstats, SLOWLOG, LATENCY |
| Network | Redis PING from pod, TCP telemetry |
| Database | QPS, query p95/p99, connection wait |
| JVM | GC pauses, CPU, heap allocations |

### 17.1. SLOWLOG Measures Execution

~~~bash
redis-cli SLOWLOG GET 20
~~~

It does not measure network RTT or client queues. An empty SLOWLOG does not guarantee Redis is completely idle, because many fast commands can still cause queueing.

### 17.2. LATENCY Events

~~~bash
redis-cli LATENCY LATEST
redis-cli LATENCY DOCTOR
~~~

Latency monitoring may need to be enabled. Use it to find Redis server stalls such as forks, AOF fsync, or long Lua scripts. Do not treat it as an end-to-end HTTP timer.

### 17.3. JVM GC and Large Values

A Redis `GET` returning a value of several MiB can cause the JVM to allocate many bytes/objects, triggering GC or slow deserialization. Measure JFR/GC/CPU alongside Redis latency.

## 18. Cache Stampede After Eviction

~~~text
Hot key gets evicted
  -> Pod A: MISS -> DB query
  -> Pod B: MISS -> DB query
  -> Pod C: MISS -> DB query
  -> 1000 requests MISS -> DB overloaded
~~~

### 18.1. Mitigations

- Single-flight/request coalescing.
- Limiting DB fallback concurrency.
- Cache warming.
- TTL jitter.
- Negative caching with an appropriate TTL.
- Soft TTL/stale-while-revalidate if business rules allow.
- Background refresh.
- Bulkhead/circuit breaker.
- Distributed locks with lease/owner semantics when truly necessary.

Single-flight inside one pod does not automatically prevent other pods from also hitting the DB. Design according to your topology.

### 18.2. Do Not Trade Correctness for Cache Hits

Do not serve stale sensitive data such as balances, access permissions, or checkout inventory if the contract forbids it.

### 18.3. Retry Storms

Retrying Redis/DB excessively can multiply load during an existing overload. Use bounded retries, backoff, and a timeout budget. For Redis writes with side effects, a timeout does not prove the command did not execute; idempotency is required.

## 19. Diagnosing Across Scenarios

### 19.1. Memory Growing Due to Cache Without TTL

~~~text
used_memory grows daily
key count grows
expires/keys low
namespace cache:search:* grows very fast
~~~

Remediation: locate the writer, fix the TTL/key schema, inspect key reuse, and clean up scoped keys after confirming ownership.

### 19.2. High Eviction and High DB Fallback

~~~text
evictions/sec       3,000
Redis GET p95       2 ms
cache hit ratio     95% -> 60%
DB query p95        150 -> 500 ms
HTTP p99            200 -> 1,200 ms
~~~

Prioritize reducing cold key cardinality, improving cache admission quality, and handling stampedes; increase RAM if the hot working set genuinely requires it.

### 19.3. volatile-lru Yet Writes Hit OOM

~~~text
maxmemory-policy = volatile-lru
non-TTL keys = nearly full RAM
TTL keys = few
SET returns OOM
~~~

The bottleneck is an insufficient eligible eviction set. Classify the data, set TTLs on proper cache keys, separate state, or pick an appropriate policy without risking critical data loss.

### 19.4. High RSS While Dataset Remains Stable

~~~text
used_memory 2.0 -> 2.1 GiB
RSS         3.4 -> 5.5 GiB
key count   stable
evictions   low
~~~

Investigate fragmentation, allocator, client buffers, and persistence/CoW; do not just tweak cache TTLs.

### 19.5. Redis Cluster Hot Shard

~~~text
Primary A  95% maxmemory, evictions/sec=2000
Primary B  35% maxmemory, evictions/sec=0
Primary C  42% maxmemory, evictions/sec=0
~~~

Check hash tags, hot keys/tenants, slot distribution, and per-node capacity.

### 19.6. New Cache Prefix After Deploy

~~~text
products:v1::...
products:v2::...
~~~

Two keyspaces coexisting raise memory usage. Review rollback windows, TTLs, cross-version invalidation, and cleanup plans.

### 19.7. Untrimmed Redis Stream

~~~text
XLEN orders:events grows by millions of entries
XPENDING worker-group increases
cache key count barely changes
~~~

This is a retention/consumer backlog issue and will not be fixed by changing Spring Cache TTLs.

## 20. Redis Cluster and Unbalanced Memory

Redis Cluster distributes keys across 16,384 hash slots. A single primary can suffer memory pressure even while total cluster RAM appears plentiful.

### 20.1. Hot Hash Tag

~~~text
cache:{all}:tenant:A:product:101
cache:{all}:tenant:B:product:102
~~~

Sharing the `{all}` tag pins keys to the same slot, easily creating a hot shard. Adding more primary nodes does not split that slot automatically.

### 20.2. Monitor Each Primary Individually

Track:

- `used_memory`/`maxmemory`.
- Eviction rate.
- CPU/commands/sec.
- Hot slots/key distribution.
- Big key concentration.
- Replication/network overhead.

### 20.3. Rebalancing Also Has a Cost

Migrating slots/keys creates network/CPU work and can temporarily affect latency. Use canaries and monitoring when rebalancing.

## 21. Noisy Neighbor and Multi-Tenant Workloads

Redis keys with tenant prefixes:

~~~text
app:prod:tenant:A:cache:...
app:prod:tenant:B:cache:...
~~~

prevent key collisions, but do not create RAM/CPU quotas. Tenant B writing millions of keys can evict Tenant A's hot keys.

Options:

- Per-tenant rate/write limits.
- Cache value-size bounds.
- Workload-specific TTL/admission policies.
- Top-N tenant analytics.
- Dedicated Redis resources for tenants/workloads requiring hard isolation.

Never attach hundreds of thousands of tenant IDs as metric labels.

## 22. Big Keys and UNLINK

A large Hash, List, Set, or Stream can consume substantial RAM and cause latency when read or deleted.

### 22.1. Bounded Reads

If only a few fields are needed:

~~~redis
HMGET product:101 name price thumbnail
~~~

Avoid `HGETALL` on huge Hashes unless necessary. Use pagination or SCAN-like operations where appropriate.

### 22.2. UNLINK vs. DEL

~~~bash
redis-cli UNLINK app:prod:cache:legacy:big
~~~

`UNLINK` unlinks the key and performs memory reclamation asynchronously, reducing blocking compared to `DEL` in several cases.

It does not guarantee immediate RSS reduction. Monitor `lazyfree_pending_objects` and allocator metrics. Never delete state without confirming its owner.

### 22.3. Do Not Use FLUSHALL to Put Out Fires

`FLUSHALL` can wipe sessions, locks, counters, and pending events belonging to other services, while also triggering a cache miss storm.

Use cleanup scoped to validated namespaces, SCAN/batches, and a controlled plan.

## 23. Capacity Planning

A simple estimate:

\[
M_{\text{logical}} \approx
N_{\text{live keys}}
\times
(\text{average value bytes}+\text{per-key overhead})
\]

For example, creating 300 unique keys/second with a 20-minute TTL:

\[
N_{\text{live}}\approx 300 \times 1200 = 360000
\]

If `MEMORY USAGE` samples average 1.5 KiB/key:

\[
M\approx 360000\times1.5\ \mathrm{KiB}
\approx 527\ \mathrm{MiB}
\]

This is a starting estimate. Add headroom for size distributions, Redis overhead, RSS/fragmentation, buffers, replication, persistence/failover, and Cluster skew.

### 23.1. Working Set Differs from Total Dataset

If 5% of keys are reused frequently, retaining those hot keys can yield a strong hit ratio without storing every cold key.

If the hot working set exceeds RAM, continuous eviction can drive a high miss ratio. In that case, adding RAM is justified when reuse and miss penalties warrant it.

### 23.2. Adding RAM Does Not Cure a Key Leak

If every request puts a new UUID into the key, key count can grow unboundedly. Adding RAM only delays the time until it fills up again.

### 23.3. Headroom for Containers / Managed Redis

Do not set `maxmemory` equal to the entire container limit without leaving room for the allocator, RSS, buffers, replication, and persistence. Size according to your deployment/provider documentation.

## 24. Production Runbook

### Step 1 — Record Scope and Time Window

~~~text
Incident: Redis memory/eviction
Window: 10:00-10:30
Shard: primary-2
used/maxmemory: 94%
evictions/sec: 2,500
HTTP p99: 900 ms
DB QPS increase: +350%
~~~

### Step 2 — Classify the Data

Identify caches, sessions, idempotency, locks, counters, Streams, or canonical state. Never change policies before knowing which keys are allowed to be lost.

### Step 3 — Collect Metrics

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
redis-cli MEMORY STATS
~~~

Take snapshots over time and compute rates from deltas.

### Step 4 — Inspect the maxmemory Policy

Check the policy, TTL coverage, and OOM errors. Specifically inspect `volatile-*` when most memory is occupied by non-TTL keys.

### Step 5 — Find Fast-Growing Namespaces and Big Keys

Use bounded SCAN/`bigkeys`, grouped by owner. Do not paste raw sensitive keys/values into public tickets.

### Step 6 — Separate Dataset from RSS

Compare `used_memory_dataset`, `used_memory`, RSS, fragmentation, client buffers, and persistence events.

### Step 7 — Measure Application Impact

Correlate Redis `GET` p95/p99, cache hits/misses, DB fallback, HTTP p99, retries, and JVM GC within the same time window.

### Step 8 — Write a Falsifiable Hypothesis

Example:

> "Each search request generates a key containing a trace UUID with a 24-hour TTL. Removing the UUID and reducing TTL to match data freshness should reduce key creation rate and RAM usage while improving the hit ratio."

### Step 9 — Change One Primary Factor

Fix the TTL/key builder/cache admission, shrink big payloads, isolate critical state, switch policy, or scale RAM/shards based on evidence.

### Step 10 — Measure Before and After

Inspect `used_memory`, RSS, `evictions/sec`, key count, hit ratio, DB QPS/p99, Redis command p99, HTTP p99/error rate, and data correctness.

### Step 11 — Keep a Rollback Plan

If the new TTL/policy/cache namespace causes stale data or increases DB load, there must be a way to revert without wiping canonical state.

## 25. Common Pitfalls

1. **Rising Redis memory means a leak.** It could be warming, value growth, buffers, or fragmentation.
2. **High eviction means Redis commands are definitely slow.** Redis `GET` may be fast while downstream misses cause HTTP slowness.
3. **`expired_keys` and `evicted_keys` are the same.** They reflect two different mechanisms.
4. **`volatile-lru` will evict any old key.** Only keys with a TTL are eligible.
5. **`allkeys-lru` is always good.** It can evict sessions/locks/idempotency state.
6. **A short TTL prevents RAM from filling up.** A high unique-key creation rate can still yield a massive live key count.
7. **Increasing TTL always improves performance.** Cold keys lingering in RAM can push hot keys out.
8. **`used_memory` and RSS are identical.** Allocator and OS accounting differ.
9. **Setting `maxmemory` equal to OS RAM limit is safe.** Leaves no headroom for buffers/fragmentation/persistence.
10. **If Cluster total RAM has headroom, every node is fine.** A single primary may still be full.
11. **`RedisTemplate` automatically attaches a TTL to every cache key.** Do not assume this.
12. **Spring Cache uses `RedisTemplate`'s TTL.** `RedisCacheConfiguration` is a separate mechanism.
13. **Each Repository entity uses only one key.** Indexes and metadata also consume RAM.
14. **`UNLINK` returns RAM to the OS immediately.** Not guaranteed.
15. **You can run `FLUSHALL` to reset the cache when full.** Dangerous on a shared Redis.
16. **Retrying Redis OOM infinitely will self-heal.** Usually just amplifies load.
17. **Disabling persistence to save memory is harmless.** It can break recovery guarantees.
18. **A single RAM screenshot is enough to pick a fix.** You need trends, rates, and data classification.

## 26. Frequently Asked Questions

**1. Does rising `evicted_keys` mean Redis is failing?**  
Not by default. For disposable caches, eviction can be by design. Check hit ratio and SLOs.

**2. Why can a key disappear before its TTL expires?**  
Redis may evict it early under memory pressure, or the application may delete/overwrite the key.

**3. Why does RAM keep growing even with TTLs?**  
High key creation rate, long TTLs, growing value sizes, other namespaces without TTLs, buffers, or fragmentation.

**4. Can `volatile-lru` hit OOM?**  
Yes, if there are not enough keys with TTLs available to evict.

**5. Is `noeviction` better than `allkeys-lru`?**  
Depends on the role of the data. It prevents eviction, but writes can fail when memory is full.

**6. Why is Redis `GET` fast while HTTP p99 is high?**  
Increased cache misses can overload database fallbacks.

**7. If RSS is higher than `used_memory`, is there a leak?**  
Not enough evidence on its own. Inspect fragmentation, allocator, buffers, and persistence.

**8. Why is `maxmemory` lower than RSS?**  
Memory accounting differs from RSS, and overhead exists outside the dataset.

**9. Does Spring Cache set a TTL automatically?**  
Depends on `RedisCacheManager`/Boot configuration. Inspect the bean and the TTL of actual keys.

**10. What happens if `RedisTemplate.set` is called without a `Duration`?**  
Do not assume new keys have a TTL; define clear lifecycle/expiration policies and check overwrite semantics.

**11. Do Redis Repositories add extra index keys?**  
They can. Secondary indexes and expiration metadata must be included in capacity planning.

**12. Can a Redis Stream grow without bound?**  
Yes, if retention/trimming is misconfigured or producers outpace consumers. Inspect pending work before deleting.

**13. Should you run `redis-cli --bigkeys` in production?**  
Only when authorized and with impact controls; the scanning tool still generates load.

**14. Should you always use LFU instead of LRU?**  
No. Choose after benchmarking based on hotness/reuse patterns and miss penalties.

**15. Can Redis Cluster evict when total RAM still has headroom?**  
Yes, if an individual primary shard hits its memory limit.

**16. Will adding RAM permanently solve the issue?**  
Only if a legitimate working set lacks capacity. With unbounded key cardinality, it will fill up again.

**17. Should you delete a large key immediately?**  
Not before verifying its owner and data classification.

**18. Can you use `FLUSHALL` to reduce eviction?**  
Never on shared production Redis, as it can destroy critical state and trigger a cache miss storm.

**19. Is cache stampede related to eviction?**  
Yes. Losing a hot key causes many requests to hit the source of truth simultaneously.

**20. What are the most important metrics?**  
Never rely on one metric alone: monitor `used_memory`, RSS, `evictions/sec`, hit ratio, DB fallback, Redis p99, and HTTP p99 together.

## 27. Diagnostic Implementation Checklist

1. **Classify Redis data** into cache vs. critical state.
2. **Define SLOs** for Redis, HTTP, cache hit ratio, and database fallback.
3. **Collect `INFO memory`/`stats`/`keyspace`** on the right primary.
4. **Compute `evictions/sec`** from deltas and handle counter resets.
5. **Distinguish expiration from eviction**.
6. **Verify `maxmemory` and `maxmemory-policy`**.
7. **Check TTL coverage** by namespace.
8. **Locate big keys and millions of tiny keys**.
9. **Measure value bytes and serialization overhead**.
10. **Inspect cache key cardinality**.
11. **Check `RedisTemplate` TTL usage**.
12. **Check `RedisCacheConfiguration` and `@Cacheable`**.
13. **Check Repository indexes and TTL metadata**.
14. **Check Stream/List/ZSet retention**.
15. **Compare `used_memory` with RSS, fragmentation, and buffers**.
16. **Measure DB miss amplification and cache stampedes**.
17. **Bound retries, concurrency, and downstream fallbacks**.
18. **Pick TTLs based on freshness/reuse** with jitter where useful.
19. **Separate critical state from disposable cache** if policies conflict.
20. **Monitor every Cluster primary**, avoiding aggregate-only views.
21. **Reserve headroom for allocator, replication, and persistence**.
22. **Clean up scoped keys with owner validation**, never `FLUSHALL`.
23. **Measure before/after** on comparable workloads.
24. **Protect correctness, tenant isolation, and rollback paths**.

## 28. Summary

**Redis memory growth, high eviction, and Spring Boot performance degradation** form a chain of symptoms that must be analyzed layer by layer.

- **Memory:** separate dataset/key count/value bytes from RSS, buffers, fragmentation, and persistence.
- **Eviction:** identify eligible keys per `maxmemory-policy`, without confusing eviction with TTL expiration.
- **Application:** measure cache hits/misses, database fallback, Redis command latency, and HTTP p95/p99 to pinpoint what is actually slow.
- **Remediation:** fix key schemas/TTL/value sizes, bound Streams/collections, pick an appropriate eviction policy, scale capacity when the working set genuinely demands it, and guard against cache stampedes.
- **Safety:** never accidentally evict sessions/locks/idempotency state, never wipe all of Redis, and never sacrifice freshness, security, or durability merely to shrink RAM.

A reliable workflow is **measure trends → isolate causes by namespace and data type → make controlled changes → verify against SLOs, hit ratio, RAM, and data correctness**.

## References

- Redis — [Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- Redis — [INFO](https://redis.io/docs/latest/commands/info/).
- Redis — [MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/).
- Redis — [MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/).
- Redis — [MEMORY DOCTOR](https://redis.io/docs/latest/commands/memory-doctor/).
- Redis — [TTL](https://redis.io/docs/latest/commands/ttl/).
- Redis — [PTTL](https://redis.io/docs/latest/commands/pttl/).
- Redis — [SCAN](https://redis.io/docs/latest/commands/scan/).
- Redis — [UNLINK](https://redis.io/docs/latest/commands/unlink/).
- Redis — [SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- Redis — [Redis Streams](https://redis.io/docs/latest/develop/data-types/streams/).
- Redis — [Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- Spring Data Redis — [Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- Spring Data Redis — [Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html).
- Spring Data Redis — [Expirations](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html).
- Spring Boot — [Caching](https://docs.spring.io/spring-boot/reference/io/caching.html).
- Spring Boot — [Actuator metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
