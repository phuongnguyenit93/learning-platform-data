# Monitoring Memory, Eviction, Expiration, and Cache Hit Ratio

## 1. Why Can the Cache Still Work While the System Is Failing?

Suppose a Spring Boot application uses **Spring Data Redis** to cache product information. Initially, every Redis read is fast and the database receives few queries. After several weeks in operation, the engineering team notices:

- Redis memory grows close to its configured limit.
- Cache misses rise even though request volume has not changed much.
- Some newly written keys are removed early, before their TTL expires.
- Database CPU rises because the application has to reload the cache.
- Occasionally Redis returns errors when writing to the cache.
- Users complain that the API is slow, yet Redis `PING` still replies `PONG`.

You cannot pinpoint the root cause from a single number such as "Redis is using 85% memory". You need to distinguish **data memory**, **actual memory occupied by the Redis process**, **keys evicted due to memory pressure**, **keys expired due to TTL**, and **successful vs. failed cache lookups**.

```text
HTTP requests
      |
      v
Spring Cache / RedisTemplate
      |
      +--- CACHE HIT -----------------------> Return result
      |
      +--- CACHE MISS ---> Database ---> Write cache ---> Return result
      |                         ^
      |                         |
      +--- Redis ERROR ----------+ (fallback if designed)
                     |
                     v
                   Redis
                     |
       +-------------+--------------+
       |             |              |
   High memory    Eviction       Expiration
   usage          due to         by TTL
                  maxmemory
```

Four key groups of information:

1. **Memory:** How much memory is Redis using compared to `maxmemory` and physical RAM?
2. **Eviction:** How many keys are removed to free memory under the `maxmemory-policy`?
3. **Expiration:** How many keys are deleted because their TTL elapsed?
4. **Cache hit ratio:** Out of cache lookups, how many actually found data?

This lesson belongs to the **Observability** chapter in **Spring Data Redis**. The focus is on reading metrics from Redis, adding instrumentation at the Spring Boot layer, designing dashboards and alerts, and properly interpreting the relationships among them.

## 2. Four Concepts That Must Not Be Equated

### 2.1. Memory usage

Redis stores data in memory while also needing memory for metadata, client buffers, replication, the allocator, and internal structures.

An application should not look solely at:

```text
used_memory
```

while ignoring:

```text
used_memory_rss
maxmemory
used_memory_peak
used_memory_dataset
mem_not_counted_for_evict
```

These fields describe **different perspectives**, not interchangeable aliases for the same quantity.

### 2.2. Eviction

**Eviction** occurs when Redis removes keys according to its memory management policy, typically because a write causes the memory evaluated against `maxmemory` to exceed the budget.

Example:

```text
maxmemory = 1 GiB
memory pressure rises
policy = allkeys-lru
Redis selects one or more keys to remove
```

An evicted key **has not necessarily reached its TTL**. Redis is sacrificing data to free memory per policy.

### 2.3. Expiration

**Expiration** is when a key is deleted because its time-to-live (TTL) has ended.

Example:

```redis
SET cache:product:42 "data" EX 60
```

Redis can remove expired keys either upon access (*passive expiration*) or via periodic background checks (*active expiration*).

Expiration is usually a **normal** part of a TTL-based cache design.

### 2.4. Cache hit / miss

**Hit:** A lookup finds a valid cached value.

**Miss:** A valid lookup does not find a value.

Example:

```text
GET cache:product:42 -> value present  => hit
GET cache:product:43 -> key absent     => miss
```

**A Redis timeout is not a cache miss.** If Redis loses connectivity, the application does not know whether the key exists. Errors must be tracked separately.

### 2.5. Comparison Table

| Metric | Meaning | Must Not Be Inferred |
|---|---|---|
| `used_memory` | Memory Redis allocates for internal operations per allocator stats | Total OS RAM consumed by Redis |
| `used_memory_rss` | Resident memory reported by the operating system | All of it is useful cached data |
| `evicted_keys` | Total keys evicted by Redis since the counter started | All those keys had expired TTLs |
| `expired_keys` | Total keys deleted due to expiration | Every key is deleted at the exact millisecond TTL = 0 |
| `keyspace_hits` | Successful key lookups recorded by Redis | Hits specific to `@Cacheable("products")` |
| `keyspace_misses` | Unsuccessful key lookups recorded by Redis | All of them were caused by eviction |
| `INFO keyspace` | Reported key count, keys with expiry, and average TTL | Exact expiration time of each individual key |

## 3. Starting Observation with Redis Commands

Connect to a Redis server with appropriate permissions:

```bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO keyspace
```

Or run them inside an interactive CLI session:

```redis
INFO memory
INFO stats
INFO keyspace
```

Additional commands:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
MEMORY STATS
INFO clients
INFO commandstats
```

In managed Redis environments, commands like `CONFIG GET` or `MEMORY STATS` may be restricted by ACLs or the provider. In that case, use the metrics endpoints exposed by the service.

**Do not take a single `INFO` snapshot and declare a trend.** Memory may need snapshots, but eviction/expiration/hits/misses are **cumulative counters**, so most analysis requires multiple samples over time.

### 3.1. Four Command Groups and Their Questions

| Command | Primary Question |
|---|---|
| `INFO memory` | What do allocated memory and resident RAM look like? |
| `INFO stats` | At what rate are evictions, expirations, and hits/misses growing? |
| `INFO keyspace` | How many keys and TTL keys exist in each logical database? |
| `CONFIG GET maxmemory` | What is Redis's eviction memory budget? |
| `CONFIG GET maxmemory-policy` | Which strategy does Redis use to choose keys to evict? |
| `MEMORY STATS` | How is memory broken down across components? |
| `MEMORY USAGE <key>` | Roughly how much memory does a specific key occupy? |
| `INFO commandstats` | Which command groups are called most often or take the most time? |

## 4. Understanding `INFO memory`

Illustrative example output:

```text
# Memory
used_memory:524288000
used_memory_human:500.00M
used_memory_rss:629145600
used_memory_rss_human:600.00M
used_memory_peak:671088640
used_memory_peak_human:640.00M
maxmemory:1073741824
maxmemory_human:1.00G
maxmemory_policy:allkeys-lru
mem_fragmentation_ratio:1.20
```

These numbers are **examples only**, not metrics from a live system.

### 4.1. `used_memory`

This is the amount of memory Redis reports as allocated via its allocator for data and Redis structures.

It is not identical to:

- Container memory usage.
- Disk size of RDB/AOF files.
- Total bytes of raw cached JSON payloads alone.
- Free physical memory on the host.

Even if application values total only about 100 MiB, `used_memory` can be larger due to key names, metadata, data structures, internal overhead, and operational components.

### 4.2. `used_memory_rss`

`used_memory_rss` represents the resident memory held by the Redis process according to the operating system.

If:

```text
used_memory = 500 MiB
used_memory_rss = 800 MiB
```

examine allocator fragmentation, RSS overhead, allocation/free history, and memory configuration rather than concluding there are 300 MiB of unaccounted data keys.

RSS is also affected by allocator and OS behavior. Deleting a key does not necessarily cause RSS to drop immediately in the same proportion.

### 4.3. `used_memory_peak`

`used_memory_peak` shows the peak allocation during the process's lifetime.

Example:

```text
current used_memory = 500 MiB
used_memory_peak    = 900 MiB
```

The system previously used more memory than it does now. This is useful when investigating a bulk data import or cache warming event. However, peak values depend on process history and how Redis manages counters; they do not replace continuous time-series collection.

### 4.4. `maxmemory`

`maxmemory` is the configured memory limit for memory management/eviction.

```redis
CONFIG GET maxmemory
```

If the result is:

```text
maxmemory
1073741824
```

Redis has a limit of about 1 GiB.

`maxmemory = 0` typically means no maxmemory limit of this kind is applied in that configuration—**not that the server has infinite memory**. Redis is still constrained by RAM, container limits, the operating system, and infrastructure capacity.

### 4.5. `mem_not_counted_for_evict`

Redis may report:

```text
mem_not_counted_for_evict
```

This field represents memory excluded from the eviction threshold comparison under current mechanics, which can include buffers used for persistence/replication.

Therefore, comparing:

```text
used_memory / maxmemory
```

is a useful operational signal, **not an exact simulation of every internal eviction check**.

Likewise, **the `maxmemory` threshold is not a hard ceiling for RSS**. You must leave headroom for client buffers, replication, allocator fragmentation, fork/copy-on-write, the OS, and other components.

### 4.6. `used_memory_dataset` and `used_memory_overhead`

If your Redis version provides:

```text
used_memory_dataset
used_memory_overhead
```

they help separate memory tied to the dataset from internal overhead.

A cache with very long keys, many small objects, or Hashes with substantial metadata can incur higher overhead than expected.

Do not assume:

```text
used_memory_dataset == total raw JSON size
```

because Redis encodings, compression/serialization, and the allocator organize memory in their own ways.

## 5. Reading Memory Fragmentation Properly

You can observe:

```text
mem_fragmentation_ratio
allocator_frag_ratio
allocator_rss_ratio
rss_overhead_ratio
```

depending on Redis version and allocator.

### 5.1. Fragmentation Ratio Is Not Simply Percentage Wasted

If:

```text
used_memory_rss = 600 MiB
used_memory     = 500 MiB
```

then the RSS/allocated ratio is roughly `1.2`.

However, **do not assume** "Redis is wasting exactly 20% of RAM due to fragmentation". The difference also includes process, allocator, and environmental overhead.

In particular, when the dataset is very small, fixed overheads make the ratio look high even when total bytes are negligible.

### 5.2. Combine Ratios with Actual Byte Counts

Two cases:

```text
Cache A:
  used_memory = 10 MiB
  rss         = 20 MiB
  ratio       = 2.0

Cache B:
  used_memory = 10 GiB
  rss         = 15 GiB
  ratio       = 1.5
```

A's ratio is higher, yet B has a vastly larger gap in actual bytes.

So observe together:

- `used_memory`.
- `used_memory_rss`.
- RSS minus allocated difference.
- Allocator metrics.
- Host/container memory limit.
- Trends over time after heavy load or data deletion.

### 5.3. Active Defragmentation Is Not a Cure-All

Redis offers active defragmentation capabilities depending on version, allocator, and configuration. Do not enable or tune it blindly just because a ratio looks high.

First identify whether the root issue is:

- Growing cache data.
- Hitting the `maxmemory` limit.
- Growing client/replication buffers.
- Fragmentation following allocation churn.
- OS or container running out of RAM.

Each cause requires a different solution.

## 6. Monitoring Memory Per Key

When a cache region grows abnormally, you can investigate with narrowly scoped commands.

### 6.1. How Many Bytes Does One Key Occupy?

```redis
MEMORY USAGE cache:product:42
```

Redis returns an estimate based on how that key is stored. For complex structures, you can use the `SAMPLES` option where supported by your version:

```redis
MEMORY USAGE cache:product:42 SAMPLES 5
```

Do not run `MEMORY USAGE ... SAMPLES 0` in bulk across huge structures during peak traffic without evaluating cost; `0` requests sampling all elements in supported structures and can consume significant resources.

### 6.2. Inspecting Data Type and TTL

```redis
TYPE cache:product:42
PTTL cache:product:42
```

If the key is a Hash:

```redis
HLEN cache:product:42
```

If it is a List:

```redis
LLEN some:list
```

These commands tell you field/element counts, **not a substitute for measuring memory**.

### 6.3. Finding Large Keys Without Unbounded Scans

You can use big-key inspection tools in an appropriate environment, for example:

```bash
redis-cli --bigkeys
```

Depending on your needs, you can limit scope with patterns or parameters supported by your `redis-cli` version.

Understand that this tool still traverses the keyspace and issues measurement commands. Do not run it continuously every few seconds on a large Redis instance as a metric collector.

When you need to scan a namespace yourself:

```redis
SCAN 0 MATCH cache:product:* COUNT 100
```

Continue following the cursor until it returns `0`.

`SCAN` may return duplicates, is not a snapshot, and `COUNT` is only a hint. In **Redis Cluster**, scanning must cover all relevant primaries/partitions; running `SCAN` on one node does not prove you have seen every key across the cluster.

### 6.4. Why Can Many Small Objects Cause Overhead?

Compare two options:

```text
1 key holding a large JSON String
```

and:

```text
1,000 very small String keys
```

Total payload bytes may be similar, yet 1,000 keys require 1,000 key names, dictionary entries, and metadata structures.

Switching to a Hash or grouping entries can reduce overhead for some workloads, but it changes updates, TTL behavior, concurrency, and response sizes. Do not optimize purely on intuition; measure with `MEMORY USAGE` and real latency.

## 7. Eviction: What Happens When Redis Runs Out of Memory?

Redis uses a `maxmemory-policy` to determine how to behave when eviction-eligible memory reaches the threshold.

Check configuration:

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Example:

```text
maxmemory = 1073741824
maxmemory-policy = allkeys-lru
```

When a write occurs and Redis needs to free memory, this policy allows it to select keys for removal.

### 7.1. Common Eviction Policies

| Policy | Eligible Keys | Selection Principle |
|---|---|---|
| `noeviction` | Does not proactively evict keys for maxmemory | Write commands needing more memory may return OOM errors |
| `allkeys-lru` | All keys | Favors less recently used keys via approximated LRU |
| `allkeys-lfu` | All keys | Favors less frequently used keys via approximated LFU |
| `allkeys-random` | All keys | Picks randomly |
| `volatile-lru` | Only keys with an expiry | Approximated LRU |
| `volatile-lfu` | Only keys with an expiry | Approximated LFU |
| `volatile-random` | Only keys with an expiry | Random |
| `volatile-ttl` | Only keys with an expiry | Favors keys closer to expiring |

Redis "LRU" and "LFU" are approximated/tunable algorithms and should not be treated as an exact globally sorted list across every access.

### 7.2. `allkeys` vs. `volatile`

With:

```text
allkeys-lru
```

Redis can evict keys **even if they have no TTL**.

With:

```text
volatile-lru
```

only keys with an expiration are eligible for eviction. If no eligible keys remain and Redis is still short on memory, some write commands may fail with OOM errors instead of Redis deleting other keys.

This matters greatly if the same Redis stores:

```text
cache:product:...
session:...
lock:...
stream:...
fence:sequence:...
```

If all data shares one `allkeys-*` Redis, a key without a TTL that is meant to persist can still be evicted per policy. Do not store must-not-lose keys in the same eviction domain as arbitrary cache entries.

### 7.3. Eviction Differs from Explicit Deletion

When the application calls:

```redis
DEL cache:product:42
```

that is **explicit deletion**, not eviction under memory pressure.

Similarly, `@CacheEvict` in Spring Cache normally translates to deleting a key per the cache contract; it does not mean Redis's `evicted_keys` counter will increase.

Therefore:

```text
Keys removed = eviction + expiration + explicit delete + ...
```

and `evicted_keys` represents only one of those mechanisms.

## 8. Tracking Eviction via `INFO stats`

Example:

```redis
INFO stats
```

Output may contain:

```text
evicted_keys:1249
expired_keys:39842
keyspace_hits:721002
keyspace_misses:198332
```

These numbers are **cumulative over the lifetime of the Redis counter**, not the keys removed in the last second.

### 8.1. Do Not Use Cumulative Counts Directly as Rates

Suppose:

```text
12:00:00 evicted_keys = 1000
12:05:00 evicted_keys = 1300
```

Average eviction rate over 5 minutes:

\[
\frac{1300 - 1000}{300} = 1\ \text{key/second}
\]

This rate is far more informative than the number `1300` in isolation.

If Redis restarts, the counter may drop lower than before. Monitoring must handle **counter resets**; do not compute a negative delta as a meaningful negative rate.

### 8.2. Is Eviction Always a Bug?

**Not necessarily.** For a dedicated Redis cache using `allkeys-lru`, a steady rate of eviction can be expected behavior when the active dataset exceeds available memory.

However, eviction becomes a signal requiring investigation if:

- Eviction rate spikes suddenly.
- Cache hit ratio drops.
- Database load rises due to cache reloading.
- API p95/p99 increases.
- Redis works hard yet hit count stays low.
- Eviction touches keys the business expects never to be dropped.
- OOM command errors occur.

**Eviction rate and hit ratio must be viewed together.**

### 8.3. Eviction Can Cause Hot Keys to Reload Continuously

```text
GET product:42 -> MISS
      |
      v
DB query -> cache SET
      |
 Redis short on memory
      |
 Evict another key
      |
      v
GET just-evicted key -> MISS
      |
      v
Another DB query
```

This cycle can trigger *cache churn*: the application pays the cost to populate the cache, but entries are not retained long enough to pay off.

Even with LFU/LRU policies, workloads with skewed access distributions or rapidly shifting datasets can suffer churn. Measure hits per cache region and hot-key distributions.

## 9. Expiration: Tracking TTL and Expired Key Counts

Redis supports key expiration:

```redis
SET cache:product:42 "payload" EX 600
```

Then:

```redis
TTL cache:product:42
PTTL cache:product:42
```

`TTL` returns remaining seconds; `PTTL` returns milliseconds.

### 9.1. Special TTL Return Values

| Result | Meaning |
|---|---|
| Positive integer | Key has a deadline and time remaining |
| `-1` | Key exists but has no expiration |
| `-2` | Key does not exist |

A very low TTL value alone does not prove Redis deleted the key at that exact moment.

### 9.2. Passive Expiration vs. Active Expiration

Redis uses two common mechanisms:

**Passive expiration:** When a command accesses an already-expired key, Redis can detect and handle the expired key.

**Active expiration:** Redis periodically samples/runs internal work to find and remove expired keys without waiting for an application access.

```text
Key K has expireAt = T

T arrives:
  K is logically expired

After T:
  (1) Request GET K -> Redis detects K is expired
  or
  (2) Active expiration cycle -> Redis removes K

When Redis actually deletes due to expiration:
  expired_keys increments
```

Because Redis does not guarantee processing every expiration at the exact millisecond T, a logically expired key may not have its memory reclaimed immediately. Expiration metrics are operational signals, **not an absolute-precision business timer**.

### 9.3. Measuring Expiration Rate

Suppose:

```text
12:00 expired_keys = 50000
12:05 expired_keys = 56000
```

Average rate:

\[
\frac{56000 - 50000}{300}
= 20\ \text{keys/second}
\]

20 keys/second can be completely normal if the application actively creates many short-TTL cache keys.

Do not set an alert for `expired_keys increase > 0` across every system. Compare against key creation rate, TTLs, traffic, and cache misses.

### 9.4. Expiration vs. Eviction in Business Outcomes

| Scenario | Reason Key Disappeared | Typical Counter |
|---|---|---|
| Key has `EX 60` and reaches deadline | TTL elapsed | `expired_keys` may rise when Redis deletes it |
| Key still has TTL but Redis is low on memory | Policy eviction | `evicted_keys` may rise |
| Application calls `DEL` | Explicit deletion | Neither eviction nor expiration |
| `FLUSHDB`/`FLUSHALL` | Administrative clear | Not TTL |
| Data lost due to failover/restore | Recovery state | Not directly inferred from the two counters |

A **cache miss** can follow any of these scenarios, so a cache miss alone is not proof of either eviction or expiration.

## 10. `INFO keyspace`: keys, expires, and avg_ttl

Command:

```redis
INFO keyspace
```

Example:

```text
# Keyspace
db0:keys=180000,expires=150000,avg_ttl=420000
```

Meaning:

- `keys`: number of keys in the database reported by Redis at collection time.
- `expires`: number of keys with an expiration.
- `avg_ttl`: average TTL reported by Redis statistics, typically in milliseconds.

In Redis Cluster, database 0 is used; each node reports only the portion of data it holds, not all 16,384 slots.

### 10.1. Ratio of Keys with TTL

From the example:

\[
\text{TTL coverage} = \frac{150000}{180000} \times 100\%
\approx 83.3\%
\]

This is the percentage of keys with an expiration at measurement time, **not confirmation that all cache keys have proper TTLs set**.

Why?

- Redis may store non-cache keys that do not need a TTL.
- Some cache keys are designed without a TTL.
- Different cache namespaces have different lifetimes.
- `INFO keyspace` does not break down by cache region.
- A key with an overly long TTL also counts as a key "with TTL".

### 10.2. avg_ttl Is Not an Expiration SLA

`avg_ttl` is an aggregate statistic reported by Redis, not an application SLA. Do not use it to deduce the exact expiration time of a session or drive a real-time business decision.

To check a specific key, use `PTTL` or—when an absolute deadline is needed—the appropriate command for your Redis version such as `PEXPIRETIME`, combined with an authoritative source if business decisions require exactness.

## 11. Monitoring Cache Hit Ratio at the Redis Level

Redis reports:

```text
keyspace_hits
keyspace_misses
```

in `INFO stats`.

A commonly used calculation:

\[
\text{Hit ratio} =
\frac{\text{keyspace hits}}
{\text{keyspace hits} + \text{keyspace misses}}
\times 100\%
\]

Example:

```text
keyspace_hits   = 75,000
keyspace_misses = 25,000
```

Then:

\[
\text{Hit ratio} = 75\%
\]

### 11.1. Do Not Use Lifetime History to Assess a Live Incident

Suppose Redis has been serving for a month:

```text
Total hits:   9,900,000
Total misses:   100,000
```

Cumulative ratio = 99%. If over the last 5 minutes almost every request missed due to a namespace change or eviction, the lifetime ratio can still look high and **mask the incident**.

Compute over **time-window deltas**.

Example:

| Sample | Hits | Misses |
|---|---:|---:|
| 12:00 | 1,000,000 | 250,000 |
| 12:05 | 1,015,000 | 255,000 |

In 5 minutes:

```text
Delta hits   = 15,000
Delta misses =  5,000
```

Recent hit ratio:

\[
\frac{15000}{15000+5000} \times 100\% = 75\%
\]

This is the calculation you should use to evaluate cache effectiveness over a specific observation window.

### 11.2. What `keyspace_hits/misses` Actually Measures

These are **Redis server-level counters** for successful/failed key lookups according to the commands and semantics Redis tracks.

They **do not automatically distinguish**:

- A `products` cache from a `users` cache.
- One microservice from another.
- Customer requests from batch jobs.
- Lookups generated by `@Cacheable` from other commands accessing keys.
- Legitimate misses on requests intentionally probing non-existent keys.

Therefore, the hit ratio from `INFO stats` is a **whole-Redis-node metric**, not the exact hit rate of an individual cache region or Spring endpoint.

### 11.3. When a Sample Has Too Few Lookups

Suppose in 5 minutes:

```text
delta hits   = 0
delta misses = 0
```

The sample has no lookups to compute a ratio. The formula must return **no data (N/A)** rather than dividing by 0 or defaulting hit ratio to 100%.

If there is only one lookup and it misses:

```text
delta hits = 0
delta misses = 1
```

the hit ratio is 0%, yet the sample is too small to conclude the whole system is broken.

When alerting on hit ratio, pair it with a **minimum traffic threshold**.

## 12. Distinguishing Redis Cache Hit Ratio from Application Cache Hit Ratio

Suppose a Spring Boot service uses:

```java
@Cacheable("products")
public Product findProduct(long id) { ... }
```

An overall Redis hit ratio cannot tell you how `products` is performing if the same Redis also serves `sessions`, `carts`, and `rate_limits`.

Use two observation layers:

```text
Spring service
  |
  +--> App cache lookup metrics
  |      products: hit/miss/error
  |      users:    hit/miss/error
  |
  v
Redis
  |
  +--> INFO stats: keyspace_hits/misses
  +--> INFO memory: memory/eviction budget
```

### 12.1. Application-Layer Hits Also Involve Bypasses

Some requests may skip the cache:

- Methods without `@Cacheable`.
- A `condition` expression bypassing the cache.
- `unless` preventing the result from being cached.
- An application local cache checked before Redis.
- A request carrying a force-refresh flag.
- Redis failing and the application falling back to the database.

A well-instrumented system should define clearly:

```text
lookup_hit
lookup_miss
lookup_error
lookup_bypass
fallback_success
fallback_failure
```

If you use total HTTP requests as the cache hit ratio denominator without accounting for bypasses, the ratio may misrepresent the lookups that actually queried the cache.

### 12.2. Redis Errors Must Not Be Turned into Misses

Anti-pattern to avoid:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
```

This causes:

```text
Redis timeout -> recorded as miss
```

When Redis fails, the miss rate rises artificially and can overload the database if every request falls back.

Better to measure:

```text
GET returns value -> HIT
GET returns null  -> MISS
GET throws error  -> ERROR
```

If Redis data is a reconstructible cache, **fallback** is a separate decision after recording the error. Never erase the distinction between a Redis error and a cache miss.

## 13. Measuring Cache Hit/Miss Separately in Spring Boot with Micrometer

When you need to know whether a cache region is actually delivering value, instrument at the service layer. The example below uses **Spring Data Redis**, `StringRedisTemplate`, and **Micrometer**.

### 13.1. A Service with Three Explicit Counters

```java
package com.example.redis.metrics;

import java.util.Optional;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    private final Counter hits;
    private final Counter misses;
    private final Counter errors;

    public ProductCacheReader(
            StringRedisTemplate redis,
            MeterRegistry registry) {

        this.redis = redis;

        this.hits = Counter.builder("app.cache.lookup")
                .description("Product cache lookup outcomes")
                .tag("cache", "products")
                .tag("outcome", "hit")
                .register(registry);

        this.misses = Counter.builder("app.cache.lookup")
                .tag("cache", "products")
                .tag("outcome", "miss")
                .register(registry);

        this.errors = Counter.builder("app.cache.lookup")
                .tag("cache", "products")
                .tag("outcome", "error")
                .register(registry);
    }

    public Optional<String> findCachedProduct(long productId) {

        String key = "cache:products:v2:" + productId;

        try {
            String value = redis.opsForValue().get(key);

            if (value == null) {
                misses.increment();
                return Optional.empty();
            }

            hits.increment();
            return Optional.of(value);

        } catch (DataAccessException ex) {
            errors.increment();
            throw ex;
        }
    }
}
```

Meaning:

- `hits` increments when Redis returns data.
- `misses` increments when Redis returns `null`.
- `errors` increments when the Redis operation throws a caught data-access exception.
- Metrics carry only **bounded labels** `cache=products` and `outcome=hit/miss/error`.
- `productId`, full Redis key, and payload are never attached as metric labels.

This example targets a specific `GET` path via `StringRedisTemplate`. With other serializers or exception types, adjust error classification accordingly. If business data is JSON, also separate JSON decode errors from cache misses according to policy.

### 13.2. Why Not Attach the Full Key to the Metric?

If each request accesses:

```text
cache:products:v2:42
cache:products:v2:43
cache:products:v2:44
...
```

and you use the key as a tag, the system can create millions of time series. This causes a **cardinality explosion**, driving up RAM and metrics storage costs.

Additionally, cache keys may contain personal IDs, emails, or tokens. Use only allowlisted labels such as:

```text
cache=products
operation=read
outcome=hit
```

### 13.3. Querying and Metric Naming

With a Prometheus registry, Micrometer typically maps a counter named:

```text
app.cache.lookup
```

to a Prometheus metric name and labels per registry conventions, for example:

```text
app_cache_lookup_total{cache="products",outcome="hit"}
```

Verify the actual exported name via the application's metrics endpoint; do not guess from the Java name if a custom naming convention is configured.

Hit ratio over time can be computed from the **rate** of the hit and miss counters:

```promql
sum(rate(app_cache_lookup_total{cache="products",outcome="hit"}[5m]))
/
clamp_min(
  sum(rate(app_cache_lookup_total{cache="products",outcome=~"hit|miss"}[5m])),
  0.001
)
```

This expression is illustrative when the metric name and labels match the above. At very low traffic, add a sample volume condition before trusting the ratio.

In Grafana, you can multiply by `100` or select the Percent unit formatting based on your metric scale.

## 14. Spring Cache and RedisCacheManager Statistics

If the application uses Spring Cache annotations:

```java
@Cacheable(cacheNames = "products", key = "#id")
public Product findProduct(long id) {
    return productRepository.findById(id).orElse(null);
}
```

Spring Data Redis provides `RedisCacheManager`. In versions supporting statistics, you can enable **cache statistics**:

```java
package com.example.redis.config;

import java.time.Duration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfig {

    @Bean
    public RedisCacheManager cacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager
                .builder(connectionFactory)
                .cacheDefaults(defaults)
                .enableStatistics()
                .build();
    }
}
```

### 14.1. What Is the Scope of These Statistics?

A common pitfall: statistics provided by Spring Data Redis `CacheManager` are typically **local to each cache instance within the JVM process**, not an aggregated counter across the entire Redis server.

If there are 10 Spring Boot instances:

```text
App 1 -> local products hits/misses
App 2 -> local products hits/misses
...
App 10 -> local products hits/misses
```

To aggregate accurately, scrape each instance and compute the ratio from **summed hit/miss counts or summed rates**, never a simple average of the 10 percentages.

Statistics may reset when an instance restarts. Use proper counter/rate logic and understand version-specific behavior.

### 14.2. Example Reading Statistics

With a Spring Data Redis version providing `RedisCache.getStatistics()`:

```java
import org.springframework.data.redis.cache.RedisCache;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.cache.CacheStatistics;

RedisCache cache = (RedisCache) cacheManager.getCache("products");

if (cache != null) {
    CacheStatistics stats = cache.getStatistics();

    long hits = stats.getHitCount();
    long misses = stats.getMissCount();
}
```

These statistics are collected inside Spring Cache when enabled. Do not assume they include `RedisTemplate.opsForValue().get()` calls executed outside the Spring Cache abstraction.

Do not assume Spring Boot Actuator automatically exports all of these statistics under one fixed metric name across every version. Check the Micrometer/cache instrumentation integration of your actual dependencies, or export metrics explicitly from the application.

### 14.3. `@CacheEvict` Is Not Redis Eviction

A method:

```java
@CacheEvict(cacheNames = "products", key = "#id")
public void invalidate(long id) {
    // Business operation.
}
```

deletes a cache entry via intentional application invalidation.

Do not mechanically add `@CacheEvict` calls to Redis `evicted_keys`. The two metrics answer different questions:

```text
Application invalidation: how many entries were removed by business logic?
Redis eviction: how many keys did Redis remove due to memory policy?
```

## 15. Computing Cache Hit Ratio Across Multiple Applications or Nodes

### 15.1. Hit Ratios Should Not Be Unweighted Averages

Suppose:

```text
Service A:  9 hits / 10 lookups  => 90%
Service B: 10 hits / 100 lookups => 10%
```

Simple average:

```text
(90% + 10%) / 2 = 50%
```

Yet the true ratio across all lookups is:

\[
\frac{9+10}{10+100} \approx 17.27\%
\]

**Correct approach:** sum hits and misses before dividing, or sum rates across instances before computing the ratio.

### 15.2. Redis Cluster Must Collect Metrics Per Node

A Redis Cluster has multiple primaries:

```text
Primary A -> separate hits/misses, memory, evictions
Primary B -> separate hits/misses, memory, evictions
Primary C -> separate hits/misses, memory, evictions
```

`INFO stats` on Primary A does not represent the whole Cluster.

Dashboards should include:

- Per-node/per-shard metrics.
- Cluster totals aggregated by appropriate rules.
- Per-node maximums, especially for memory pressure.
- Key/hot-key distribution across slots.
- Node roles and failover timestamps.

**Do not look solely at cluster-wide total memory.** The Cluster as a whole may still have plenty of RAM while one specific shard is near its limit and evicting aggressively.

### 15.3. Should Replicas Be Added to the Totals?

It depends on the question.

If you want to measure **total physical memory used by Redis**, include all Redis processes—both primaries and replicas.

If you want to measure **authoritative lookups/evictions per primary**, define the scope clearly so you avoid double-counting or mixing in replica metrics that the application may not be reading.

With Lettuce `ReadFrom.REPLICA_PREFERRED`, replicas can directly serve part of the read traffic. In that setup:

- Hits/misses for **requests routed to a replica** will appear on that replica node.
- Primary-only metrics will miss replica read volume.
- Summing all nodes may require distinguishing application lookups from internal activity.

For evaluating cache effectiveness at the API layer, **application-level hits/misses** are usually easier to define cleanly than a cluster-wide Redis ratio.

### 15.4. Failover Shifts Time Series

When a replica is promoted, node roles change. If a dashboard only groups by:

```text
role=primary
```

without retaining `instance`, a time series can jump because the set of primary nodes changed.

Always keep:

```text
cluster
node/instance
role
environment
```

and handle counter resets, restarts, and role transitions.

## 16. Configuring TTL in Spring Data Redis and Its Impact on Metrics

With `RedisCacheManager`, you can set a default TTL and per-cache TTLs:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10));
```

And per region:

```java
Map<String, RedisCacheConfiguration> configs = Map.of(
        "products",
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(30)),
        "inventory",
        RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofSeconds(20))
);
```

This snippet illustrates a configuration map; in practice, pass it into the `RedisCacheManager` builder and verify against your Spring Data Redis version.

### 16.1. Overly Short TTL

```text
GET -> MISS -> load DB -> SET EX 5
5 seconds later
GET -> MISS -> load DB -> SET EX 5
```

Observed consequences:

- `expired_keys` rises.
- Cache misses rise.
- DB queries rise.
- Hit ratio drops.
- API latency rises.

If data changes infrequently yet expires too often, consider a longer TTL paired with explicit invalidation on updates.

### 16.2. Overly Long TTL

An overly long TTL can cause:

- Stale data.
- Memory occupied by rarely accessed entries.
- Cache churn/eviction if Redis cannot hold the entire dataset.
- Business updates not reflected promptly.

This shows why you should not optimize hit ratio alone by choosing an infinite TTL. **Data freshness and memory footprint** are also goals.

### 16.3. Using TTL Jitter to Avoid Mass Simultaneous Expiration

If thousands of keys are written at the same time with the exact same TTL, they can expire around the same moment:

```text
t0: SET 100,000 keys EX 600
t0 + 600s: many keys expire together
              |
              v
           Cache misses
              |
              v
         Database overload
```

Where appropriate, spread TTLs around a baseline to smooth load:

```text
TTL = 600s + random(-60s, +60s)
```

Only use jitter if the business permits a variable expiration window. For sessions or tokens that must expire strictly per security policy, **never extend TTLs** just to boost cache hit ratio.

## 17. Eviction, Expiration, and Cache Misses: Reading One Combined View

Suppose a dashboard shows:

```text
Memory usage       rising quickly
Evictions/second   rising sharply
Expired/second     unchanged
Cache hit ratio    dropping
DB queries/second  rising
```

A reasonable hypothesis is **the cache lacks sufficient memory for the working set**.

However, if:

```text
Memory usage       stable
Evictions/second   near 0
Expired/second     rising high
Cache hit ratio    dropping
DB queries/second  rising
```

then TTL may be too short, many keys may be expiring simultaneously, or traffic shifted to uncached keys.

### 17.1. Scenario Interpretation Table

| Memory | Eviction | Expiration | Hit Ratio | Hypothesis to Check |
|---|---|---|---|---|
| High | Rising | Normal | Dropping | Insufficient memory or large working set |
| Low/medium | Near 0 | High | Dropping | Short TTL or synchronized expiration |
| High | Near 0 | Low | Low | Cache holds low-utility data; misses due to namespace/workload |
| High | Rising | Rising | Good | Cache works as configured, though paying churn overhead |
| Low | Near 0 | Near 0 | Low | Cold cache after startup, missing keys, unwarmed, or wrong key lookup |
| High | Near 0 | Low | Good | Stable cache, though headroom still needs checking |
| Medium | Unchanged | Unchanged | Sudden drop | Deployment, serializer, key prefix, or traffic mix change |
| High | 0 with `noeviction` | Any | Any | Writes may hit OOM errors instead of evictions |

This table provides **hypotheses**, not guaranteed conclusions from four numbers alone.

### 17.2. An Example of Cache Churn

Every minute:

```text
New keys cached:          50,000
Keys evicted:             40,000
Keys expired:              1,000
Cache hit ratio:             35%
```

If most newly cached keys are read only once, the cache is absorbing high write cost with low reuse.

Measures to consider:

- Avoid caching one-off request types.
- Cap value sizes.
- Optimize key namespaces and serialization.
- Choose TTLs based on actual reuse.
- Adjust maxmemory/policy when budget allows.
- Separate cache regions from non-evictable data.
- Block cache penetration or invalid key requests.

Do not conclude "we just need more RAM" if the core issue is caching values that bring no reuse benefit.

## 18. Redis Returns OOM Errors While `evicted_keys` Remains 0

A common point of confusion:

```text
maxmemory = 512 MiB
maxmemory-policy = noeviction
```

When Redis needs to allocate more memory for certain write commands past the threshold, it can return an error like:

```text
OOM command not allowed when used memory > 'maxmemory'
```

In this case:

- `evicted_keys` can remain 0.
- Redis does not delete keys to keep writes succeeding.
- The application may see errors on `SET`, `HSET`, or other memory-allocating writes.
- `GET` may continue serving, depending on overall state.

Therefore, **`evicted_keys = 0` does not prove Redis has no memory pressure**.

When monitoring memory, also track:

- Memory usage relative to `maxmemory`.
- `maxmemory-policy`.
- OOM errors.
- Application write failure rates.
- Command latency and server health.

In some Redis versions, `INFO errorstats` or corresponding exporter metrics can help track OOM-category errors. Availability and naming depend on version and deployment, so verify on your target environment.

## 19. Monitoring with Redis Exporter, Prometheus, and Grafana

In production, running manual `INFO` commands is an investigation step, not a long-term monitoring strategy.

A typical architecture:

```text
Redis nodes
   |
   | INFO / telemetry
   v
Redis exporter / managed metrics
   |
   v
Prometheus or time-series store
   |
   v
Grafana dashboard + Alert rules
   ^
   |
Micrometer / Spring Actuator
   |
Spring Boot services
```

### 19.1. Separating Redis-Level and Application-Level Metrics

**Redis-level:**

```text
memory used
RSS
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
connected clients
commands per second
latency
```

**Application-level:**

```text
cache products hit/miss/error
cache users hit/miss/error
fallback to database
cache load duration
timeout/retry
business request p95/p99
database query volume
```

Both are needed to see how much **resource the cache costs** and what **benefit it delivers to the application**.

### 19.2. Exporter Metric Names May Differ

Some Redis exporters use names like:

```text
redis_memory_used_bytes
redis_memory_max_bytes
redis_evicted_keys_total
redis_expired_keys_total
redis_keyspace_hits_total
redis_keyspace_misses_total
```

These are **illustrative names**, not a universal contract across all Redis exporters or managed Redis services. Always inspect the `/metrics` endpoint and documentation for your version.

Do not build dashboards by guessing metric names and concluding there are no evictions when a query returns `No data`.

### 19.3. Illustrative PromQL Queries

**Memory utilization vs. configured limit:**

```promql
100 *
redis_memory_used_bytes
/
redis_memory_max_bytes
```

Only valid when `redis_memory_max_bytes > 0` and both metrics share the same node/instance. If `maxmemory` is 0 or unexposed, this ratio is meaningless and you must measure against another limit.

**Eviction rate over 5 minutes:**

```promql
rate(redis_evicted_keys_total[5m])
```

**Expiration rate over 5 minutes:**

```promql
rate(redis_expired_keys_total[5m])
```

**Redis-level hit ratio over 5 minutes:**

```promql
sum by (instance) (
  rate(redis_keyspace_hits_total[5m])
)
/
clamp_min(
  sum by (instance) (
    rate(redis_keyspace_hits_total[5m])
    +
    rate(redis_keyspace_misses_total[5m])
  ),
  0.001
)
```

Adjust these expressions to match the actual labels and metric names of your exporter. When aggregating multiple nodes, decide whether replicas are included and which metrics represent the application's read path.

**Note:** `clamp_min` prevents division by zero, yet when lookups are nearly zero the ratio is statistically meaningless. Exclude very low-traffic windows with a separate condition.

### 19.4. Counters Must Handle Restarts and Failovers

Prometheus `rate` handles many counter reset scenarios when a process restarts. Still, ensure:

- Regular scrape intervals.
- Labels distinguishing individual Redis instances.
- Awareness of node role changes after failover.
- Never blindly merging series across a primary and replica that swapped roles.
- Never using raw `counter_now - counter_previous` across a counter reset without checking.

## 20. Designing Dashboards Around Operational Questions

A useful dashboard can be organized into these sections.

### 20.1. Memory Capacity

```text
used_memory
used_memory_rss
maxmemory
memory utilization %
used_memory_peak
mem_not_counted_for_evict
fragmentation / allocator stats
```

Goal: How much headroom does Redis have, is physical RAM threatened, and is memory growing from data or overhead?

### 20.2. Eviction and Expiration

```text
evicted_keys/s
expired_keys/s
maxmemory-policy
keys with TTL / total keys
number of keys by logical DB
OOM error rate
```

Goal: Are keys disappearing due to RAM pressure or TTL? Are keys being evicted that should never be evicted?

### 20.3. Cache Effectiveness

```text
Redis-level hit ratio
Application cache hit ratio by region
Cache lookup errors
Cache load latency
Database fallback QPS
Cache invalidation count
Cache bypass count
```

Goal: Is the cache reducing database load and API latency?

### 20.4. Redis Performance

```text
Commands/s
Client latency p95/p99
Server latency
Connected clients
Rejected connections
CPU
Network throughput
Slowlog count
```

Goal: Are memory growth or cache misses tied to server resources, connections, or network behavior?

### 20.5. Topology

For Redis Cluster or Sentinel:

```text
Node role
Shard owner / primary
Replica lag
Failover events
Per-node memory
Per-node eviction rate
Per-node command rate
```

Goal: Is an individual node under pressure even if cluster-wide totals look healthy?

## 21. Setting Context-Aware Alerts

No single threshold fits every Redis server. For instance, a cache using `allkeys-lfu` with steady eviction can still achieve a 98% hit rate, whereas a Redis holding sessions with `noeviction` may treat any OOM write error as a severe outage.

### 21.1. An Illustrative Rule Set

| Alert | Illustrative Condition | Next Investigation |
|---|---|---|
| Memory pressure | Memory ratio above 85% sustained for 10 minutes | Check headroom/RSS/fragmentation |
| High eviction | Eviction rate many times above baseline | Check hit ratio and cache churn |
| Low hit ratio | Hit ratio drops below SLO with sufficient lookup volume | Check TTL, key prefix, traffic, serializer |
| OOM write errors | OOM write errors on a Redis that must accept writes | Check `noeviction`, memory, and application |
| High RSS | RSS near RAM/cgroup limit | Check overhead, buffers, fragmentation |
| Cache load storm | DB fallback QPS spikes sharply | Check Redis errors, eviction, or expiration burst |
| Replica issue | Lag rises or link goes down | Check stale reads and failover |
| Redis command timeout | Timeout rate exceeds baseline | Check server/network/client queues |

**85% and 10 minutes are example numbers** to illustrate time-windowed alerting. Real thresholds should reflect peak load, scaling capacity, write burst sizes, replication, persistence, and SLOs.

### 21.2. Multi-Signal Composite Alerts

A notable condition:

```text
memory_used/maxmemory high
AND eviction_rate rising
AND application_hit_ratio dropping
AND database_fallback_qps rising
```

This chain detects cache memory pressure that is genuinely impacting the application.

However, do not require every condition to fire before alerting on **OOM errors or critical RAM exhaustion risks**. Some failures warrant independent alerts.

### 21.3. Do Not Alert on `expired_keys > 0`

In a healthy TTL cache, expired keys are expected. What is worth watching:

- Expiration rate spiking abnormally relative to traffic.
- Misconfigured TTLs after a deployment.
- Many keys expiring together and causing a DB load spike.
- Cache hit ratio dropping or DB load rising alongside it.
- Session expirations diverging from the business contract.

## 22. Real-World Scenario: Investigating a Hit Ratio Drop

Suppose the application dashboard shows:

```text
09:00 - products cache hit ratio: 94%
09:15 - products cache hit ratio: 45%
09:15 - API p99 increases
09:15 - Database queries/s increases
```

### Step 1: Verify the Measurement

Check:

- Did hit/miss counters reset due to a deploy?
- Is lookup volume large enough?
- Did metric labels or cache names change?
- Are Redis errors being counted as misses?

If the numerator or denominator is wrong, the hit ratio chart is wrong too.

### Step 2: Check Redis Memory and Eviction

```redis
INFO memory
INFO stats
CONFIG GET maxmemory-policy
```

If `evicted_keys` spiked during the exact window hit ratio dropped, the cache may lack memory or the working set may have shifted.

### Step 3: Check Expiration

If evictions are near 0 yet expiration rate jumped suddenly:

- Was a TTL changed from 30 minutes to 30 seconds?
- Did a job create a huge batch of keys with the same TTL?
- Was a cache namespace just cleared or renamed?
- Were many keys created together after a cache warm?

### Step 4: Check Key Prefix and Serializer

After a deployment:

```text
V1: cache:product:42
V2: cache:products:v2:42
```

Even when Redis has plenty of free memory, new code cannot read old cache entries. Hit ratio drops due to a **cold namespace**, not eviction.

If a serializer changed, decode errors may occur; do not turn those errors into misses just to keep charts simple.

### Step 5: Inspect Per-Region Metrics

Perhaps only `products` has an issue:

```text
products hit: 45%
users hit:    97%
settings hit: 99%
```

The server-wide Redis hit ratio may remain high because other regions dominate traffic.

### Step 6: Pick a Remediation Matching the Cause

| Cause | Remediation |
|---|---|
| Memory budget too small | Evaluate increasing memory or shrinking footprint |
| Unsuitable eviction policy | Switch policy after workload testing |
| TTL too short | Adjust TTL / invalidation |
| Synchronized expiration | Add TTL jitter if business allows; bounded pre-warming |
| Namespace change | Plan warm/migration and preserve compatibility |
| Values too large | Shrink payloads, cache per field, or avoid caching certain data |
| Hot key / traffic skew | Optimize access patterns, shard, and protect origin |
| Redis connection error | Fix infrastructure errors; do not count as misses |
| Database fallback storm | Bulkhead, rate limit, or per-key single-flight if suitable |

## 23. Real-World Scenario: Memory Rises While Hit Ratio Stays High

Suppose:

```text
Redis hit ratio      = 98%
used_memory          = 950 MiB
maxmemory            = 1 GiB
used_memory_rss      = 1.3 GiB
evictions/second     = 0
```

The system may still be serving cache hits effectively, yet:

- Redis is close to its eviction budget.
- RSS exceeds allocated memory and may approach container/host RAM limits.
- A large write burst could trigger evictions or OOM.
- A high hit ratio does not prove adequate headroom.

Investigate:

1. What is `maxmemory-policy`?
2. How many bytes are not counted toward eviction?
3. Is RSS/allocator fragmentation growing over time?
4. How large are peak write bursts?
5. Does Redis run AOF rewrites or snapshots that raise memory demand?
6. Does the host have spare RAM for replication buffers and copy-on-write?

This illustrates that **cache effectiveness metrics do not replace capacity monitoring**.

## 24. Real-World Scenario: High Expiration Rate While the System Is Healthy

Suppose Redis serves OTPs and short-lived caches:

```text
expired_keys/s       = 1,000
evicted_keys/s       = 0
app cache hit ratio  = 92%
API p99              = stable
DB load              = stable
```

A high expiration rate can be completely expected for a short-TTL design. Do not blindly increase TTLs to lower expired key counts, because OTPs and sessions carry security constraints.

What to monitor:

- Do TTLs match business policy?
- Are entries past their deadline treated as invalid?
- Are synchronized bursts causing load spikes?
- Do hit/miss ratios and downstream load meet SLOs?

**Expiration rate is a behavioral signal, not automatically an error indicator.**

## 25. Can Keyspace Notifications Count Evictions/Expirations Accurately?

Redis provides **keyevent notifications**:

```text
__keyevent@0__:expired
__keyevent@0__:evicted
```

You can enable the corresponding event types via `notify-keyspace-events` when permitted.

Test example:

```redis
CONFIG SET notify-keyspace-events Exe
```

Then subscribe:

```redis
PSUBSCRIBE __keyevent@0__:expired
```

or:

```redis
PSUBSCRIBE __keyevent@0__:evicted
```

However, understand the limitations:

- Notifications rely on **Redis Pub/Sub**.
- When a subscriber is offline, messages can be lost.
- There is no built-in ACK or replay mechanism.
- In Redis Cluster, keyspace/keyevent notifications are **scoped to the node emitting the event**; subscribing to one node misses events from other nodes.
- Enabling notifications adds operational overhead.
- Multiple listener instances may receive the same event.

**Do not use Pub/Sub notification counts as an exact replacement for `expired_keys` or `evicted_keys`.**

Keyspace notifications are useful for certain event-driven reactions, but production rate monitoring should rely on counters and intentionally collected metrics.

## 26. TTL, Eviction, and Data Durability Requirements

Do not apply the same memory policy to every type of key.

Example:

```text
cache:product:*           -> eviction acceptable
cache:search:*            -> eviction acceptable
session:*                 -> evaluate security / fallback source
idempotency:*             -> may need retention across deduplication window
lock:*                    -> lease with TTL, coordination semantics
fencing:sequence:*        -> must not reset if used to guard resources
stream:orders             -> holds critical messages / consumer-group state
```

With `allkeys-*`, a Redis server can evict even keys without a TTL. Consider:

- Separating Redis caches from Redis instances holding coordination state or critical queues.
- Choosing dedicated memory policies per workload class.
- Backing critical non-cache data with an authoritative store.
- Setting TTLs on keys meant to expire.
- Providing appropriate backups, persistence, and failover.

**Redis replication does not prevent eviction or TTL expiration.** When the primary removes a key per policy, corresponding deletes are propagated through replication. A replica is not a backup for keys intentionally evicted by the primary under memory policy.

## 27. Observing Redis in Sentinel and Cluster

### 27.1. Sentinel

With Sentinel:

```text
Primary P      -> separate memory/stats metrics
Replica R1     -> separate memory/stats metrics
Replica R2     -> separate memory/stats metrics
```

After failover, R1 may become primary. Dashboards should track:

```text
node identity
role
replication status
failover timestamp
```

If you only look at a hostname without checking role, you may mistake an old replica for the current primary.

### 27.2. Redis Cluster

With Cluster:

```text
Cluster:
  Primary A -> slot group A, local memory/eviction
  Primary B -> slot group B, local memory/eviction
  Primary C -> slot group C, local memory/eviction
```

If Primary B approaches `maxmemory` while A and C have plenty of headroom, total free memory across the cluster does not stop B from evicting.

An effective dashboard should display:

```text
cluster_total_used_memory
max(primary_memory_utilization)
per_shard_eviction_rate
per_shard_expiration_rate
per_shard_hit_ratio
per_shard_commands_per_second
```

These are **metric concepts to design**, not guaranteed built-in names in every exporter.

### 27.3. Replica Read Routing Shifts Where Hits/Misses Increment

With Lettuce configured for replica reads, such as `REPLICA_PREFERRED`, read commands can be sent to replicas.

Then `keyspace_hits` on the primary cannot represent all application reads. Track client routing paths and aggregate accordingly.

**If your goal is the hit ratio of the `products` cache**, measure right in Spring Cache or your access abstraction, using Redis-level metrics for infrastructure analysis.

## 28. Reading Memory Properly in Container Environments

When Redis runs in Docker/Kubernetes, there are at least two budgets:

1. `maxmemory`: Redis configuration used for eviction.
2. Container/pod/host memory limit: actual physical resource limit.

Example:

```text
Container memory limit = 2 GiB
Redis maxmemory        = 1.8 GiB
```

Setting Redis `maxmemory` to 1.8 GiB is not guaranteed safe once you include:

- Process and allocator overhead.
- Client buffers.
- Replication and backlog.
- AOF rewrite / RDB snapshot and copy-on-write.
- Other workloads sharing the container.

If actual memory exceeds the container limit, the OS may OOM-kill the Redis process. This differs from Redis returning `OOM command not allowed` for writes under `maxmemory-policy`.

Monitor together:

```text
redis_used_memory
redis_used_memory_rss
redis_maxmemory
container_memory_working_set
container_memory_limit
pod_restarts / OOMKilled
```

Kubernetes and exporter metric names depend on your stack and should be verified directly.

### 28.1. Why Not Set maxmemory to 100% of RAM?

Because Redis needs memory beyond the dataset tracked by `maxmemory`. A configuration leaving room only for data without headroom for overhead, forks, and load spikes risks OS-level OOM kills.

There is no fixed headroom percentage for every Redis deployment; measure persistence events, replication, payload sizes, peak connections, and fragmentation.

## 29. Safe Testing and Diagnostic Procedures

Never simulate eviction by lowering `maxmemory` on a production Redis holding real data. Use a dedicated test Redis or container.

### 29.1. Baseline

Run:

```redis
INFO memory
INFO stats
INFO keyspace
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Record:

```text
used_memory
used_memory_rss
maxmemory
evicted_keys
expired_keys
keyspace_hits
keyspace_misses
```

### 29.2. Testing Expiration

```redis
SET it:cache:exp:1 "value" EX 2
```

After more than 2 seconds, check:

```redis
GET it:cache:exp:1
TTL it:cache:exp:1
INFO stats
```

Expect the key to become inaccessible per TTL and the expiration counter to increase when Redis deletes the key. Do not expect the event to fire at the exact millisecond.

### 29.3. Testing Hit/Miss

On a test Redis:

```redis
SET it:cache:hit:1 "value" EX 120
GET it:cache:hit:1
GET it:cache:hit:not-found
INFO stats
```

Compare counters **before and after** in an isolated environment with no other traffic to observe how they change. Some commands in a workflow may also affect lookup statistics, so do not assert an exact delta of 1 across every configuration.

### 29.4. Testing Eviction

On a test Redis **containing only disposable data**, configure a policy and `maxmemory` tight enough to create memory pressure:

```redis
CONFIG SET maxmemory-policy allkeys-lru
```

You can run `CONFIG SET maxmemory ...` to set an appropriate budget for your test container, then write many test keys with sizable payloads and observe:

```redis
INFO memory
INFO stats
```

Do not apply an arbitrarily tiny `maxmemory` value verbatim to every Redis instance because minimum baseline memory/overhead varies.

Observations to check:

- Does the eviction rate increase?
- Does `used_memory` approach the threshold?
- Can previously written keys be evicted even before their TTL expires?
- How do cache hit ratio and Redis latency change?
- When switching to `noeviction`, how do memory-allocating writes behave?

### 29.5. Cleaning Up After Testing

If using an isolated container, tear down the container/volume per your test procedure.

If using a shared test Redis, delete only the demo keys under the exercise namespace:

```text
it:cache:*
```

Never run `FLUSHALL` on a Redis instance unless you have verified it is completely isolated.

## 30. Hands-On Spring Boot Exercises

### Exercise A: Service-Level Hit/Miss Statistics

1. Implement `ProductCacheReader` with the three counters `hit`, `miss`, `error`.
2. Query an existing key.
3. Query a missing key.
4. Simulate a connection failure or use a controlled test environment.
5. Verify `error` is not miscounted as `miss`.
6. Inspect the application's metrics endpoint.

### Exercise B: Changing TTL and Observing Effects

1. Use a test cache region with a 5-minute TTL.
2. Record `hit ratio`, `expired_keys/s`, and DB queries/s.
3. In the test environment, change the TTL to 20 seconds.
4. Run the same workload and compare.
5. Explain why a shorter TTL can increase misses.

### Exercise C: Enabling Redis Cache Statistics

1. Configure `RedisCacheManager` with `enableStatistics()`.
2. Use a `@Cacheable("products")` method.
3. Call the same key multiple times to generate hits.
4. Call new keys to generate misses.
5. Inspect statistics collected in the application process.
6. Run a second instance to see why these metrics do not automatically reflect the whole Redis ratio.

### Exercise D: Comparing Eviction and Expiration

1. Create keys with TTLs in a test Redis.
2. Wait for them to expire and measure `expired_keys`.
3. Introduce controlled memory pressure with an eviction-enabled policy.
4. Measure `evicted_keys`.
5. Explain why the two counters differ even though in both cases the key no longer exists.

### Exercise E: Choosing the Denominator for Hit Ratio

Suppose two services report counters:

```text
Service A: hits=9, misses=1
Service B: hits=10, misses=90
```

Compute each service's hit ratio and the overall lookup hit ratio. Explain why averaging the two ratios is wrong.

### Exercise F: Reading Dashboards After a Deployment

Simulate a namespace change from `cache:products:v1:*` to `cache:products:v2:*` without backfill.

Analyze:

- Might memory rise or fall?
- Why does the v2 cache hit ratio drop?
- Must `evicted_keys` necessarily rise?
- How long does DB fallback stay elevated?
- Should you use bounded cache warming or lazy loading on demand?

### Exercise G: Redis Cluster

If you have a multi-primary test Cluster:

1. Identify how many slots each primary owns.
2. Collect `INFO memory` and `INFO stats` per node.
3. Create an unevenly distributed set of keys.
4. Compare memory pressure and evictions across shards.
5. Explain why cluster-wide total memory can look fine while one shard is out of memory.

## 31. Common Mistakes When Observing a Redis Cache

### Mistake 1: Looking Only at used_memory

Ignoring RSS, maxmemory, fragmentation, buffers, and container limits.

### Mistake 2: Treating maxmemory as an Absolute RAM Ceiling

The Redis process may require more RAM than the memory evaluated for eviction.

### Mistake 3: Evicted_keys = 0 Means Redis Has Plenty of RAM

With `noeviction`, writes can return OOM errors instead of evicting keys.

### Mistake 4: Treating expired_keys as Unintended Data Loss

TTL-backed cache keys are designed to expire; normal expiration is not an outage.

### Mistake 5: Treating Eviction and Expiration as the Same Thing

They have different causes and require different responses.

### Mistake 6: Reading Only Cumulative Totals

Lifetime counts obscure newly emerging failures. Check deltas/rates and counter resets.

### Mistake 7: Computing Cumulative Hit Ratio Since Startup

A 5-minute outage can be masked by millions of historical hits.

### Mistake 8: Dividing by Zero When There Are No Lookups

If delta hit + miss = 0, the ratio is undefined—do not default it to 100%.

### Mistake 9: Averaging Hit Ratios Across Multiple Nodes

Sum hits and misses before dividing; otherwise low-traffic nodes receive disproportionate weight.

### Mistake 10: Treating `keyspace_hits` as Spring Cache's Own Hit Count

Redis counters are node-wide and include lookups from multiple applications and commands.

### Mistake 11: Counting Redis Timeouts as Cache Misses

This hides connectivity failures and misrepresents cache effectiveness.

### Mistake 12: Using `@CacheEvict` to Explain `evicted_keys`

Application-driven invalidation differs from maxmemory eviction.

### Mistake 13: Collecting Metrics from Only One Cluster Node

This misses memory pressure and evictions on other shards.

### Mistake 14: Failing to Distinguish Primary and Replica

You may double-count footprints or miss reads routed to replicas.

### Mistake 15: Using Full Redis Keys as Metric Labels

This creates high cardinality and risks exposing user data.

### Mistake 16: Running `KEYS *` or Full Scans Continuously in Metrics Collection

Large scans create heavy load and raise latency. Rely on built-in telemetry and use bounded scans only when investigating.

### Mistake 17: Using Pub/Sub Notifications for Exact Expiration Counts

Offline subscribers miss events, and in Cluster notifications are node-scoped.

### Mistake 18: Raising TTLs Indefinitely to Boost Hit Ratio

This causes stale data and memory bloat. Hit ratio is only one goal among several.

### Mistake 19: Adding RAM Without Inspecting the Workload

If the cache stores write-once keys or oversized payloads, more memory may not fix DB cost or cache churn.

### Mistake 20: Storing Critical Keys in an `allkeys-lru` Redis Like Ordinary Cache

Keys without TTLs can still be evicted. Classify data and durability needs properly.

### Mistake 21: Using `SLOWLOG` or MONITOR as Public Metric Sources

These tools can expose sensitive keys/arguments and add overhead; restrict access and scope.

### Mistake 22: Ignoring Redis Restarts and Failovers

Counters can reset, roles swap, and nodes get replaced. Dashboards need proper node identity and aggregation logic.

### Mistake 23: Alerting Only When Cache Hit Ratio Drops

Redis can be near OOM even with an excellent hit ratio; alert on capacity independently.

### Mistake 24: Alerting Only When Memory Is High

A cache suffering 80% misses due to a bad namespace can overload the DB even while Redis uses very little memory.

## 32. Self-Check Questions

**1. How do `used_memory` and `used_memory_rss` differ?**

`used_memory` reflects memory allocated by Redis through its allocator; RSS is the process's resident memory reported by the OS. The two values need not match.

**2. Why is `used_memory / maxmemory` not the complete memory picture?**

Because allocator overhead, replication/client buffers, `mem_not_counted_for_evict`, RSS, RAM/container limits, and burst dynamics also apply.

**3. How does eviction differ from expiration?**

Eviction removes keys per memory policy under memory pressure; expiration removes keys because their TTL elapsed.

**4. Does `evicted_keys = 0` mean there is no memory pressure?**

No. With `noeviction`, writes can be rejected with OOM errors instead of Redis deleting keys.

**5. Is rising `expired_keys` always an error?**

No. TTL expiration is normal cache behavior when aligned with policy.

**6. Why calculate hit ratio over a 5-minute delta/rate instead of lifetime history?**

Because lifetime totals can hide recent regressions or active incidents.

**7. Do Redis `keyspace_hits/misses` separate the `products` cache from `users`?**

No. Those are Redis server/node statistics, not broken down by Spring cache region.

**8. If Redis `GET` times out, should you increment the cache miss counter?**

No. A timeout is a dependency error and must be counted separately.

**9. Why shouldn't you directly average hit ratios across multiple instances?**

Because each instance handles different lookup volumes. Sum hit/miss counts or rates before dividing.

**10. Does `@CacheEvict` increase Redis `evicted_keys`?**

Not under maxmemory eviction semantics; it is an explicit application-level deletion/invalidation.

**11. Can a Redis Cluster suffer memory pressure on one shard even if total Cluster RAM looks sufficient?**

Yes. Each primary/shard manages its own slice of data and workload.

**12. Does `INFO keyspace` showing `expires=1000` mean exactly 1,000 keys will expire in the next second?**

No. It only reports how many keys currently have an expiration, not a detailed expiration schedule.

**13. Can Redis keyspace notifications accurately count every expired event across an outage?**

No. Pub/Sub has no replay or ACK, and in Cluster notifications are node-scoped.

**14. When hit ratio drops, why should you also check DB load?**

To see whether cache misses are driving extra load onto the authoritative store and degrading the API.

**15. Why does `maxmemory` lower than the container memory limit still need headroom?**

Redis also requires memory for RSS/allocator overhead, buffers, persistence/replication, and other non-dataset allocations.

**16. If cache hit ratio rises after increasing TTLs, is optimization guaranteed successful?**

Not yet. Verify data freshness, memory footprint, eviction, and business expiration contracts.

## 33. Key Takeaways

- **Memory, eviction, expiration, and cache hit ratio answer different questions** and must be examined together to evaluate Redis cache effectiveness.
- **`INFO memory`** reports `used_memory`, RSS, peak, and `maxmemory`; **`maxmemory` is not a hard limit on total process RAM**.
- **`INFO stats`** provides cumulative counters `evicted_keys`, `expired_keys`, `keyspace_hits`, and `keyspace_misses`; compute deltas/rates and handle resets.
- **Eviction is driven by memory pressure**, whereas **expiration is driven by TTL**. `DEL` and `@CacheEvict` are explicit deletions, not Redis eviction.
- **A Redis node's hit ratio is not the hit ratio of an individual `@Cacheable` region**. Add Spring Cache/Micrometer instrumentation separating hits, misses, and errors.
- **Redis `CacheManager` statistics can be local per instance**; multi-instance deployments must aggregate counters weighted by lookup volume.
- **Redis Cluster must be monitored per shard/node**, covering primaries, replicas, and topology; cluster total memory cannot hide pressure on a hot shard.
- **Never optimize hit ratio in isolation**: always weigh TTL, data freshness, database fallback, p95/p99, OOM risk, and the working set.
- **Design dashboards and alerts around SLOs and workload traits**; high expiration or non-zero eviction does not automatically mean the system is failing.

### References

- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — MEMORY STATS](https://redis.io/docs/latest/commands/memory-stats/).
- [Redis — MEMORY USAGE](https://redis.io/docs/latest/commands/memory-usage/).
- [Redis — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/).
- [Redis — Key expiration](https://redis.io/docs/latest/develop/use/keyspace/).
- [Redis — TTL](https://redis.io/docs/latest/commands/ttl/).
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/).
- [Redis — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/).
- [Spring Data Redis — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Boot — Actuator Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html).
- [Micrometer — Concepts: Counters](https://docs.micrometer.io/micrometer/reference/concepts/counters.html).
