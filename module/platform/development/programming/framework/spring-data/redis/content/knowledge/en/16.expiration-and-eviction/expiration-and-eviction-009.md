# Choosing TTL Based on Data Freshness and the Risk of Simultaneous Key Expiration

In Spring Data Redis, **TTL (Time To Live)** determines how long a cache entry can exist before Redis treats it as expired. Choosing a TTL is a decision about **data freshness, load on the origin system, and fault tolerance**, not merely picking a number of minutes for Redis.

If the TTL is too long, the application may serve stale information. If the TTL is too short, Redis constantly drops entries and the application must re-query the database or origin service. Even when individual TTLs seem reasonable, thousands of keys expiring around the same time can create a sudden load spike.

## 1. What does TTL actually guarantee?

Suppose the application reads product details from the database and writes them to Redis at 10:00:00 with a 120-second TTL. Without subsequent updates or deletions, that entry expires around 10:02:00.

- **Cached data age:** the elapsed time since the application wrote that version into Redis.
- **Synchronization lag (staleness):** how long the cache continues returning an older version after the source has changed.
- **TTL:** the lifetime cap of the entry from the latest TTL write; it does not automatically detect changes in the database.
- **Memory eviction policy:** Redis can evict the key *before the TTL ends* if memory limits and the eviction policy permit.

For instance, the database updates a price at 10:00:10, yet the cache has not been invalidated. With a 120-second TTL from 10:00:00, the old price can still be returned for nearly another 110 seconds. Thus, TTL sets an approximate upper bound on **how long stale data can be served** in a simple cache-aside model; it does not mean "data is always fresh."

A few Redis details to keep in mind:

| Behavior | Implication when choosing TTL |
|---|---|
| `SET key value EX 120` / `SET key value PX ...` | Writes the value and sets the expiration immediately in one command. |
| `EXPIRE key 120` | Sets or replaces the expiration on an existing key. |
| `TTL key` returns `-2` | The key no longer exists. |
| `TTL key` returns `-1` | The key exists but has **no expiration**. |
| `TTL key` returns a non-negative number | Remaining seconds; `PTTL` uses milliseconds. |
| `GET key` | Read-only; by default **does not extend TTL**. |
| `SET key value` without a TTL-preserving option | Usually strips the key's old TTL; expiration must be re-applied on write. |

Redis checks expiration both passively on access and actively in the background. Do not interpret TTL as a promise that Redis frees memory at the exact millisecond, though the application will not receive an expired value through normal reads.

## 2. Determining TTL from freshness requirements and business impact

Before configuring anything, answer four questions for **each type of data**:

1. **How fast does the data change?** Prices, inventory, configuration, articles, and catalogs change at different rates.
2. **What is the maximum staleness users can tolerate?** This is a business limit, often expressible as a freshness SLA.
3. **How harmful is serving stale data?** Display pricing differs from checkout pricing; authorization details differ from product descriptions.
4. **How expensive is it to rebuild a cache entry?** A simple lookup differs from aggregating millions of records or calling a metered API.

A starting point for design discussions:

| Illustrative data | Desired freshness | Initial TTL to experiment with | Complementary strategy |
|---|---|---|---|
| Price displayed on catalog listing | Lag up to ~30–60 seconds | 20–30 seconds | Invalidate cache on price-change events; **re-read price at checkout** |
| Approximate displayed stock | Lag of a few seconds | 2–5 seconds, or do not cache | Check/reserve stock at source when placing order |
| Rarely changing product details | Lag of a few minutes | 5–15 minutes | Invalidate when product is edited |
| Low-churn categories or config | Lag of 15–60 minutes depending on feature | 10–30 minutes | Refresh by version/event |
| Expensive statistical aggregates | Can lag a few minutes | 1–5 minutes | Early refresh, concurrency limiting, stale serving where allowed |
| "Not found" results | Tolerate only very brief lag | 5–30 seconds | Negative caching, separate TTL, and protection against repeated queries |
| Permissions, quotas, balances for critical decisions | May require current data | Do not rely on TTL alone | Validate at source or use appropriate consistency/active invalidation |

**Numbers in this table are examples to begin measuring from, not universal defaults.** In particular, never use a long cache TTL as the final authority for financial transactions, access control, or inventory enforcement.

### Establishing bounds

Let `F` be the maximum staleness accepted by the business, `S` be the safety cap specific to that data type, and `T` be the designed TTL. In cache-aside without reliable invalidation:

```text
T <= min(F, S)   (when both bounds apply)
```

This is a **boundary condition**, not yet a performance optimum. You still must measure source load, cache hit ratio, recovery time, and actual data drift. Even with a 60-second limit, a 60-second TTL may not be safe if cache writes/generation have significant latency or the source data was already stale when read.

A practical process to choose TTL:

1. Define allowable staleness from the user's or business decision's perspective.
2. Pick an initial TTL **not exceeding that limit**; shorten TTL when data changes rapidly.
3. Measure rebuild duration, miss traffic, database CPU/IO, and hit ratio under real load.
4. If origin load is too high, consider event-driven invalidation, early refresh, multi-tier caching, or recomputation changes; do not arbitrarily extend TTL past business limits.
5. Tune TTL per key group and observe behavior across load cycles.

## 3. Why is simultaneous expiration dangerous?

Redis can hold many keys with independent expirations. Trouble arises when **their expiration times cluster into the same short window**:

```text
10:00:00  Batch job writes 20,000 keys, each with TTL = 300 seconds
             |
10:05:00  Many keys expire together
             |
             +--> Flood of requests hit cache misses
                       |
                       +--> Database / origin API receives huge query spike
                       +--> Latency and error rates climb
                       +--> Retries can amplify the load wave
```

This is a form of **cache avalanche** (many keys expiring together or widespread cache loss). Distinguish it from a **cache stampede** on a single *hot key*: many requests concurrently find one key expired and all run the rebuild query. A system can suffer both simultaneously.

Situations that commonly synchronize expiration times:

- Prewarming large batches of keys at startup or during a new deployment.
- A batch job rewriting many keys within a few seconds.
- All keys sharing a round TTL and being populated together during a burst of concurrent traffic.
- Bulk deletion of keys upon a source update, followed by concurrent regeneration.
- Many requests depending on a single expensive aggregated key.

Equal TTLs **do not automatically** make every key expire at once; the problem is **close write timestamps combined with identical TTL durations**. Jitter spreads out expiration timestamps, though it does not stop multiple requests from competing to rebuild a single hot key.

## 4. Spreading expiration times with TTL jitter

**TTL jitter** adds or subtracts a random amount from each individual key's TTL, preventing synchronized expiration waves. There are two ways to pick the range:

- If `TTL_base` is merely a guideline and the business allows slightly higher staleness, you can use `TTL_base ± jitter`.
- If `TTL_max` is an **absolute staleness ceiling**, only **subtract** jitter:

```text
actual_TTL = TTL_max - random(0, J)
0 <= J < TTL_max
```

For example, with a 120-second max TTL and a 24-second jitter window, each key is written with a TTL in the range **96–120 seconds**. Keys written at the same moment will not all expire in the same second.

Choose `J` based on how many keys are written together, miss-handling capacity, and how short a TTL is acceptable. With 12,000 keys distributed *roughly evenly* across a 24-second window, the average expiration rate is about 500 keys/second instead of 12,000 keys at once. This is distribution intuition, **not a guarantee** of misses/second: actual access frequency and key distribution still govern origin load.

### Example with `StringRedisTemplate`

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWriter {
    private static final long MAX_TTL_SECONDS = 120;
    private static final long JITTER_WINDOW_SECONDS = 24;

    private final StringRedisTemplate redis;

    public ProductCacheWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void cacheProduct(String productId, String jsonPayload) {
        // Subtract 0..24 seconds without exceeding the 120-second ceiling.
        long subtractSeconds =
                ThreadLocalRandom.current().nextLong(JITTER_WINDOW_SECONDS + 1);
        long ttlSeconds = MAX_TTL_SECONDS - subtractSeconds;

        String key = "product:v1:" + productId;
        redis.opsForValue().set(key, jsonPayload, Duration.ofSeconds(ttlSeconds));
    }
}
```

The `set(key, value, Duration)` call stores the value and expiration in a single Redis operation. This avoids a window where the key exists without a TTL compared to sending `SET` followed by a separate `EXPIRE`.

In this example, jitter is picked **on every cache write**. If the application manages distinct data groups, set TTL ceilings and jitter windows per group; do not reuse a single random offset across all keys in a batch.

## 5. Setting TTL in Spring Data Redis

Spring Data Redis offers multiple write paths. Apply TTL in the right place for the API in use.

### 5.1. With Spring Cache (`@Cacheable`): per-cache TTL configuration

```java
import java.time.Duration;
import java.util.Map;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class CacheConfiguration {
    @Bean
    RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory) {

        RedisCacheConfiguration defaults =
                RedisCacheConfiguration.defaultCacheConfig()
                        .disableCachingNullValues()
                        .entryTtl(Duration.ofMinutes(5));

        Map<String, RedisCacheConfiguration> perCache = Map.of(
                "productDetail", defaults.entryTtl(Duration.ofMinutes(10)),
                "productPrice", defaults.entryTtl(Duration.ofSeconds(30))
        );

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .withInitialCacheConfigurations(perCache)
                .build();
    }
}
```

When a method uses `@Cacheable("productPrice")`, entries in that cache receive a 30-second TTL on write. `@Cacheable` handles lookup and reuse; it **does not automatically guarantee only one request queries the origin under all concurrent cases across all instances**. Multi-instance stampede protection requires additional coordination.

With the configuration above, TTL is fixed per cache. If you need **per-entry** jitter, write via `RedisTemplate` as shown earlier, or use a dynamic TTL mechanism supported by your Spring Data Redis version (such as `RedisCacheWriter.TtlFunction` in supported versions). Do not assume adding jitter to a cache-level default TTL produces different TTLs per key.

Note that `RedisCacheManager` and `RedisTemplate` are distinct layers. Align key generation, serializers, and cache eviction strategies so you do not end up with two separate datasets for the same business entity.

### 5.2. With `RedisTemplate`: explicit TTL control on writes

```java
// Data may be stale for at most 45 seconds:
redisTemplate.opsForValue()
        .set("price:v1:" + productId, priceJson, Duration.ofSeconds(45));

// Re-set expiration on an existing key if business logic truly requires it:
Boolean updated = redisTemplate.expire(
        "price:v1:" + productId, Duration.ofSeconds(15));

// Inspect remaining time (in seconds):
Long remaining = redisTemplate.getExpire("price:v1:" + productId);
```

`updated` can be `false` if the key does not exist. `remaining` can be `-2` (missing key) or `-1` (no TTL), so never treat any negative return value as a valid remaining time.

Do not call `expire` after **every read** if the goal is forcing data to refresh by a time ceiling: extending expiration on access turns an absolute TTL into *sliding expiration*-like behavior, allowing hot keys to linger indefinitely with stale versions.

### 5.3. Distinguishing Redis TTL from business record age

A verification code expiring at 10:05 has a **real deadline**. If a cache refreshes at 10:04 and grants another 5-minute TTL, the application could accept an expired code. For data with a business expiration timestamp, TTL should derive from **the remaining time until the deadline** (plus authoritative validation) rather than resetting a fixed duration on write.

Similarly, `@RedisHash(timeToLive = ...)` and `@TimeToLive` belong to Redis repositories for entities, whereas `RedisCacheManager` TTL belongs to Spring Cache. Know which mechanism you are using before expecting configurations to interact.

## 6. Combining TTL with stampede prevention and origin protection

**Jitter addresses many keys expiring together; it does not fully solve many requests rebuilding the same key.** For hot keys or expensive sources, consider combining these approaches.

### 6.1. Cache-aside with request coalescing

```text
Requests A/B/C concurrently access expired key K
                 |
       Check cache: MISS
                 |
    Only one thread/instance rebuilds K
                 |
       Read origin, write K + TTL
                 |
    Remaining requests re-read K
```

Within **one JVM**, concurrent work per key can be coalesced using futures/in-flight maps or equivalent mechanisms. Across **multiple instances**, distributed coordination is needed if the same key can trigger expensive rebuilds in multiple places. When using a Redis lock, include a lock TTL, an ownership token, and release only on token match (e.g., Lua compare-and-delete); never blindly `DEL` a lock another instance might now own.

Even with locking, failure paths must be designed: how long requests wait, how many times they retry reading cache, what happens if the lock holder fails, recomputation exceeding the lock TTL, and bounding concurrent origin queries. For writes requiring strict correctness, cache locks do not replace database transactions or consistency conditions.

### 6.2. Soft TTL and hard TTL when serving stale data is acceptable

A stored value can include `refreshAfter` and `expireAt` timestamps or similar metadata:

```text
Written at t0
   |
   +---- t0 + 60s: soft TTL -> prefer background refresh
   |
   +---- t0 + 180s: hard TTL -> stop serving stale data
```

Before the soft TTL, return data from Redis. Between soft TTL and hard TTL, one request triggers a coordinated refresh while others temporarily use the stale data, **if business rules permit**. Past hard TTL, force a refresh or return an approved error/fallback rather than serving stale data forever.

If Redis's actual TTL equals the soft TTL, the value disappears before the application has a chance to serve stale data; Redis's actual TTL must align with the hard TTL (or an equivalent storage strategy). Embed timing metadata in the payload and use sufficiently synchronized application clocks. Never casually apply stale-while-revalidate to balances, permissions, or sensitive transactional data.

### 6.3. Proactive refresh and event-driven invalidation

For event-driven changes (price changes, profile edits, configuration updates), delete or update the cache immediately once the source change succeeds. TTL then acts as a **safety net** if an event is dropped, rather than the sole refresh mechanism.

Account for stale overwrites after invalidation: request A reads old data, request B updates the DB and deletes the cache, and request A writes the old value back. You may need version numbers, pre-write version checks, or careful write/invalidate ordering. Match the strategy to required consistency.

### 6.4. Protection during mass cache misses

Depending on traffic and criticality, use rebuild concurrency limits, rate limits, circuit breakers, jittered backoff, controlled prewarming, and business-approved fallbacks. Avoid immediate retries across many instances when Redis or the database is slow; retries can amplify the very load spike the cache exists to absorb.

Negative caching (storing "no data found") with a short TTL prevents repeated queries for nonexistent keys. Distinguish "not found" from "origin error," and account for new data being created while the negative TTL is still active.

## 7. Design scenario: 10,000 products loaded simultaneously

An e-commerce site preloads 10,000 product detail records at deployment. The business tolerates description staleness up to roughly 5 minutes, but cannot accept wrong prices at checkout.

**Initial design:** all product details receive a 300-second TTL around 09:00. By 09:05, concurrent traffic triggers a surge in cache misses and database queries.

**Controlled design:**

1. Keep a **300-second max TTL** for descriptions; each key receives a random TTL between 240 and 300 seconds. The staleness ceiling remains honored.
2. Load caches in staggered batches rather than a single burst; for hot keys, consider refreshing ahead of a soft TTL.
3. Coordinate rebuilds per hot key, cap concurrent database queries, and handle fallbacks gracefully.
4. When admins edit descriptions, emit a cache invalidation event. TTL still prevents stale data from persisting indefinitely if event delivery fails.
5. Give **pricing** a separate cache strategy with a shorter TTL, and fetch authoritative prices from the source during checkout confirmation.

The trade-off to measure is **cache misses over time**, not only total hit ratio: two approaches with the same 10-minute hit ratio behave very differently in stability if one concentrates all misses into a few seconds.

## 8. Observing and tuning TTL in production

Select a metric set reflecting both freshness and load:

| Metric | What to detect |
|---|---|
| Hit/miss ratio by cache name, key group, and short time windows | Sudden miss spikes in a key group or following a batch job. |
| QPS, p95/p99 latency, and errors of the origin database/API | Whether cache misses are overloading downstream dependencies. |
| Rebuild count, duration, and concurrent requests for the same key | Whether hot-key stampedes are occurring. |
| Version lag or age of returned data | Whether actual data exceeds freshness bounds. |
| Redis `expired_keys`, `evicted_keys`, memory, and latency | Distinguish normal expiration from memory-pressure eviction. |
| Sampled remaining TTL distribution via `TTL` / `PTTL` | Whether many keys are set to expire together or unexpectedly lost TTLs. |

Note that `expired_keys` is a cumulative Redis counter; spotting abnormal spikes requires inspecting its **rate of increase** over intervals. When sampling keys, use safe scanning such as `SCAN` or appropriate observability tooling; never run `KEYS *` on a large production Redis instance for bulk statistics. Avoid logging sensitive data or keys containing personal information.

Measure under real traffic and intentionally test high-load scenarios: after deploys/prewarming, during batch updates, when a hot key expires, when the database slows down, and when Redis eviction occurs. Such measurement guides system TTL choices and does not replace application integration tests.

## 9. Mistakes to avoid

- **One TTL for every kind of data:** leaves freshness-sensitive data stale or forces stable data to rebuild too often.
- **Uniform round TTLs for large batches:** creates expiration clusters; use jitter and stagger data loading.
- **Adding jitter beyond the allowed staleness bound:** breaks the freshness ceiling; if TTL is a strict max, apply negative jitter.
- **Relying on jitter alone against cache stampedes:** concurrent requests can still race to recompute a single hot key.
- **Unintentionally extending TTL on every read:** keeps stale versions of hot keys alive indefinitely.
- **Overwriting a key and forgetting TTL:** creates non-expiring keys; watch out for `TTL = -1`.
- **Confusing TTL with eviction:** Redis can drop keys early when low on memory; never treat TTL as an availability guarantee.
- **Serving stale data indefinitely when the origin fails:** only allow within hard TTL bounds and for business-approved data types.
- **Watching only average hit ratio:** misses short bursts of cache misses that cause overload.

## 10. Decision flow for a new key group

When adding a cache to a Spring Data Redis application, walk through this decision chain:

```text
Does the data serve a decision requiring immediate accuracy?
    |
    +-- Yes --> Validate at source / design consistency first;
    |           caching is only a safe optimization with proper safeguards.
    |
    +-- No --> Define maximum acceptable staleness (F)
                   |
                   +--> Pick TTL <= F and measure rebuild load
                   |
                   +--> Are many keys written at the same time?
                   |       |
                   |       +-- Yes --> Add per-key jitter;
                   |                   stagger prewarm/refresh waves.
                   |
                   +--> Are there hot keys or expensive origin queries?
                   |       |
                   |       +-- Yes --> Coalesce requests, limit concurrency;
                   |                   consider soft/hard TTL.
                   |
                   +--> Does the origin emit reliable change events?
                           |
                           +-- Yes --> Invalidate/update proactively;
                                       keep TTL as a safety net.
```

**Design principle:** choose TTL from data freshness and business risk first, then optimize origin load by spreading expiration times and coordinating refreshes. In Spring Data Redis, cache-wide TTL fits entries sharing uniform characteristics; per-entry TTL fits when jitter, individual deadlines, or varying freshness rules are needed. Whichever path you choose, monitor **actual data staleness and cache-miss spikes** to validate your choices.
