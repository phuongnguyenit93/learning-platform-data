# Distinguishing Key Expiration from Memory Eviction in Redis

When calling `GET` and receiving `nil` (or `null` through Spring Data Redis), the application only knows that **the key no longer has a readable value at query time**. That result does not tell you why the key disappeared. In Redis, two easily confused causes are:

- **Expiration:** The key reached the lifetime (`TTL`) configured by the application.
- **Eviction (removal due to memory pressure):** Redis actively removes keys to free memory when a `maxmemory` limit and an eviction policy that permits key removal are active.

Both mechanisms can affect the same key. A key with a 30-minute TTL can still be evicted after a few seconds if Redis runs short of memory; conversely, Redis still expires keys by TTL even when eviction is disabled. This distinction matters when building caches, sessions, OTPs, rate limiters, and systems using Spring Data Redis.

## 1. Quick Comparison of Both Mechanisms

| Criterion | Expiration | Eviction (Memory Pressure) |
|---|---|---|
| Cause | Reached the expiration time attached to the key | Redis needs to free memory under the `maxmemory` limit |
| Governing config | `EX`, `PX`, `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PEXPIREAT`, or Spring Cache TTL | Redis Server's `maxmemory` and `maxmemory-policy` |
| Which keys are affected? | Only keys with an expiration time | Depends on policy: all keys (`allkeys-*`) or only keys with TTL (`volatile-*`) |
| Requires memory pressure? | No | Yes, per Redis memory management |
| Can a key vanish before its TTL? | Not due to expiration; can still be removed by other means | Yes |
| Are keys without TTL affected? | Not due to expiration | Possibly, if the policy is `allkeys-*` |
| Related metric | `expired_keys` in `INFO stats` | `evicted_keys` in `INFO stats` |
| App reading after key loss | Receives `nil`/`null` | Also receives `nil`/`null` |

**Core takeaway:** TTL expresses *the maximum duration for which a value is considered valid*, not a guarantee that Redis will keep that key in memory for the full duration.

## 2. Expiration: Keys Expiring by TTL

### 2.1. Setting and Checking Lifetimes

`TTL` (*time to live*) is the number of remaining seconds before a key expires. Redis also provides `PTTL` to return milliseconds.

```redis
SET session:1001 "user-1001" EX 120
TTL session:1001
GET session:1001
```

In this example, `session:1001` is given a 120-second lifetime. After that period, the key is no longer considered valid. You can also attach a TTL to an existing key:

```redis
SET report:temp "processing"
EXPIRE report:temp 300
TTL report:temp
```

Interpret `TTL` return values accurately:

| Result | Meaning |
|---|---|
| Integer `>= 0` | Key exists and has a TTL; remaining seconds (rounded down) |
| `-1` | Key exists with no TTL |
| `-2` | Key does not exist when Redis checked; does not indicate why it vanished |

`PTTL` uses the same `-1` and `-2` convention, returning remaining time in milliseconds. Do not assume `TTL = -2` automatically means *expired*: the key could also have been removed by `DEL`, `UNLINK`, eviction, or never created at all.

Note that an overwrite such as `SET session:1001 "new-value"` normally clears the key's existing TTL. To overwrite while keeping the current TTL, Redis supports the `KEEPTTL` option:

```redis
SET session:1001 "new-value" KEEPTTL
```

`PERSIST session:1001` removes the expiration, leaving the key alive with no TTL until deleted by other means.

### 2.2. How Does Redis Remove Expired Keys?

Redis uses two complementary mechanisms:

1. **Passive expiration (on access):** When a command accesses an expired key, Redis detects and expires it instead of returning the stale value.
2. **Active expiration (background sampling):** Redis periodically checks keys with a TTL and removes a portion of expired keys, even if no command accesses them.

Consequently, **a key is not necessarily removed physically at the exact millisecond its TTL hits 0**. Redis still will not return expired values to normal reads, but the expiration event and memory reclamation can happen later than the theoretical expiration timestamp.

```text
Time  ───────────────────────────────────────────────────────►
Key created       TTL deadline                 Physical cleanup
   │                   │                              │
   ├── normal reads ───┤                              │
   │                   └── key no longer valid ───────┘
   │                      (deleted on read or background sweep)
```

For example, an application sets an OTP with a 3-minute TTL. Once 3 minutes pass, the OTP is no longer accepted even if Redis has not yet swept the key physically in a background pass.

## 3. Eviction: Redis Actively Removes Keys Under Memory Pressure

### 3.1. `maxmemory` and `maxmemory-policy`

`maxmemory` is the memory threshold Redis uses to cap memory consumption; `maxmemory-policy` determines whether Redis may evict keys and how victims are chosen when memory needs to be freed.

```redis
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
```

Example configuration for a dedicated cache Redis instance:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

When a write command requires more memory while Redis is at/above the threshold, Redis can pick and evict keys matching the policy to make room. Redis does not wait for the chosen key's TTL to expire.

The `maxmemory` limit is a **Redis Server-level** setting, not a TTL setting in Spring Data Redis. If `maxmemory` has no effective cap (such as `0` on typical 64-bit Redis), Redis will not evict keys at an application-desired threshold. Exhausting physical OS RAM can lead to errors or process termination, which is **not the same** as Redis-managed eviction.

### 3.2. Common Eviction Policies

| Policy | Eligible Keys | Selection Principle |
|---|---|---|
| `noeviction` | No keys evicted | When memory cannot be allocated within the limit, commands needing more memory may return OOM errors; keys with TTL still expire normally |
| `allkeys-lru` | All keys | Prefers keys least recently used (*LRU*) |
| `allkeys-lfu` | All keys | Prefers keys least frequently used (*LFU*) |
| `allkeys-random` | All keys | Picks randomly |
| `volatile-lru` | Only keys with TTL | Prefers keys with TTL that are least recently used |
| `volatile-lfu` | Only keys with TTL | Prefers keys with TTL that are least frequently used |
| `volatile-random` | Only keys with TTL | Picks randomly among keys with TTL |
| `volatile-ttl` | Only keys with TTL | Prefers keys with the shortest remaining TTL |

Redis's LRU/LFU mechanisms rely on sampling and approximation for performance; do not interpret them as an exact, 100% global ordering across all keys. With `volatile-*` policies, if no eligible key with a TTL exists to evict, writes can still encounter out-of-memory errors.

**Two common sources of confusion:**

- Setting `maxmemory-policy noeviction` **does not disable TTL**. Keys with a TTL still expire even though Redis evicts nothing.
- Setting `maxmemory-policy allkeys-lru` allows **keys without a TTL to be evicted** due to memory pressure. `TTL = -1` does not protect a key from eviction.

### 3.3. A Key with a TTL Can Be Evicted Early

Suppose an application stores a temporary shopping cart:

```redis
SET cart:customer-42 "{\"items\":[101,205]}" EX 1800
```

At creation time, the cart has a 30-minute TTL. If Redis runs `allkeys-lru`, experiences memory pressure, and picks this key as a victim after 2 minutes, the timeline looks like this:

```text
00:00   SET cart:customer-42 ... EX 1800
        │
02:00   Redis low on memory → policy selects key → EVICTION
        │
02:01   GET cart:customer-42 → nil
        TTL cart:customer-42 → -2
        │
30:00   Expected TTL deadline (key was already gone at 02:00)
```

Without eviction or other deletions, the key would expire at the end of its TTL. **Spring Data Redis cannot tell from `GET == null` whether the key expired by TTL or was evicted.**

## 4. Observing and Determining Why Keys Disappeared

### 4.1. Inspecting via Redis CLI

```redis
TTL cart:customer-42
PTTL cart:customer-42
INFO memory
INFO stats
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

Most useful metrics:

| Metric | How to Use It |
|---|---|
| `expired_keys` (`INFO stats`) | Cumulative count of keys removed due to expiration over the counter's lifetime |
| `evicted_keys` (`INFO stats`) | Cumulative count of keys removed by eviction over the counter's lifetime |
| `used_memory` (`INFO memory`) | Memory usage currently tracked by Redis |
| `maxmemory` (`INFO memory`) | Effective memory limit currently configured in Redis |
| `maxmemory_policy` (`INFO memory`) | Effective eviction policy currently active |

Track **deltas over time intervals**, such as per minute, rather than looking solely at cumulative totals. A rapidly rising `expired_keys` count may be normal for systems using short TTLs; a rising `evicted_keys` count alongside rising cache miss rates can indicate insufficient cache capacity or an unsuitable policy.

These counters reflect the whole Redis instance (or individual node, depending on deployment), and **do not directly identify why one specific key vanished**. A `GET` returning `nil` carries no reason metadata.

### 4.2. Keyevent Notifications When Event Observation Is Needed

Redis can publish notifications when keys expire or are evicted. In a test environment, you can enable the corresponding event flags:

```redis
CONFIG SET notify-keyspace-events Exe
```

Here `E` enables *keyevent* notifications, `x` is expired, and `e` is evicted. Open a separate `redis-cli` session to subscribe:

```redis
PSUBSCRIBE __keyevent@0__:expired __keyevent@0__:evicted
```

Example channels received:

```text
__keyevent@0__:expired  → session:1001
__keyevent@0__:evicted  → cart:customer-42
```

This is an **observation channel**, not a durable audit log: Pub/Sub messages are not buffered for disconnected clients, and expired events fire when Redis actually processes the deletion, which can lag behind the TTL deadline. Some managed Redis services restrict `CONFIG SET`. In Redis Cluster, subscribe to the node owning the target key rather than expecting one connection to receive all cluster events.

## 5. Isolated Experiment to Observe Both Mechanisms

Run the following steps only on a dedicated test Redis instance; the load step intentionally triggers eviction.

### Step 1: Start Redis with a Small Memory Limit

```bash
docker run --rm --name redis-expiry-lab -p 6380:6379 redis:7 \
  redis-server --save "" --appendonly no \
  --maxmemory 8mb --maxmemory-policy allkeys-lru
```

Open another terminal to run `redis-cli -p 6380`. Port `6380` keeps the experiment separate from a default Redis on `6379`.

### Step 2: Observe Expiration

```bash
redis-cli -p 6380 SET lab:expire "short-lived" EX 2
redis-cli -p 6380 TTL lab:expire
# After more than 2 seconds:
redis-cli -p 6380 GET lab:expire
redis-cli -p 6380 TTL lab:expire
redis-cli -p 6380 INFO stats
```

After expiration, `GET` returns `(nil)` and `TTL` returns `-2`; `expired_keys` increases once Redis processes the expired key removal.

### Step 3: Observe Eviction

```bash
redis-cli -p 6380 SET lab:no-ttl "may-be-evicted"
redis-cli -p 6380 TTL lab:no-ttl
redis-cli -p 6380 INFO stats

# redis-benchmark writes many SET keys, each around 4 KB.
redis-benchmark -p 6380 -t set -n 5000 -d 4096 -r 100000

redis-cli -p 6380 INFO stats
redis-cli -p 6380 INFO memory
redis-cli -p 6380 EXISTS lab:no-ttl
```

Because total written payload exceeds the 8 MB budget, `evicted_keys` typically climbs noticeably. `lab:no-ttl` **may** be evicted even though its initial TTL was `-1`; because LRU uses sampling approximation, no specific key is guaranteed to be chosen. When comparing metrics on a long-running server, take the delta before and after the test.

## 6. Connecting to Spring Data Redis

### 6.1. Application-Configured TTL

`StringRedisTemplate` lets you write a value with a TTL using `Duration`:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OtpStore {
    private final StringRedisTemplate redis;

    public OtpStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void saveOtp(String accountId, String otp) {
        redis.opsForValue().set(
            "otp:" + accountId,
            otp,
            Duration.ofMinutes(3)
        );
    }

    public String findOtp(String accountId) {
        return redis.opsForValue().get("otp:" + accountId);
    }

    public Long remainingSeconds(String accountId) {
        return redis.getExpire("otp:" + accountId, TimeUnit.SECONDS);
    }
}
```

`findOtp()` can return `null` if the OTP expired, was evicted, or was deleted for another reason. `remainingSeconds()` can return `-2` if the key does not exist, `-1` if it has no TTL, or remaining seconds if a TTL is set; also handle `null` if the operation yields no result due to connection errors or context restrictions.

This Java code **only sets the TTL**. It does not configure `maxmemory`, choose an eviction policy, or guarantee the key stays alive for the full 3 minutes.

### 6.2. Spring Cache TTL Does Not Replace Redis Eviction Policy

With Spring Cache + Redis, entry TTL can be configured via `RedisCacheManager`:

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
public class CacheConfig {
    @Bean
    public RedisCacheManager redisCacheManager(RedisConnectionFactory factory) {
        RedisCacheConfiguration defaults = RedisCacheConfiguration
            .defaultCacheConfig()
            .entryTtl(Duration.ofMinutes(10));

        return RedisCacheManager.builder(factory)
            .cacheDefaults(defaults)
            .build();
    }
}
```

The 10-minute TTL here governs the cache entry's lifetime. If Redis Server uses `allkeys-lru` and hits `maxmemory`, an entry can still disappear before 10 minutes. In an application using `@Cacheable`, this simply causes a cache miss and reloads data from the source of truth on the next method call.

### 6.3. Choosing a Design by Data Category

| Data Category | Right Mindset About Key Loss |
|---|---|
| Recomputable query result cache | Accept expiration or eviction; handle cache misses and protect downstream sources |
| Temporary session or cart | TTL manages session lifecycle, but assess business impact of premature eviction |
| Short-lived OTP or token | TTL enforces validity window; if lost early, reject verification or allow safe regeneration |
| Idempotency / rate-limiter keys | Premature eviction can weaken duplicate prevention or rate limits; size and govern memory accordingly |
| Non-recoverable business state | Never rely on an evicting Redis cache as the sole store; use durable storage and proper recovery |

If you must shield non-TTL keys from eviction, `volatile-*` policies can serve certain mixed workloads, provided you accept write errors if no eligible TTL keys remain to evict. If Redis must never evict keys, choose `noeviction`, size memory carefully, and handle write errors; **that still does not protect against machine failure, persistence misconfiguration, or explicit deletion**.

## 7. How to Investigate When an App Reports “Redis Lost Keys on Its Own”

Move from observed evidence to hypotheses rather than jumping to conclusions from a single `GET`:

1. **Verify target key and Redis instance:** Correct hostname, database, Redis Cluster shard, key prefix, and `RedisTemplate` serializer? A different namespace can look like a missing key.
2. **Check TTL immediately after write:** Use `TTL`/`PTTL` to confirm the actual value; check for overwriting `SET` calls stripping TTL, overly short `EXPIRE` values, or unintended `PERSIST`.
3. **Inspect memory configuration:** Read `INFO memory`, `maxmemory`, and `maxmemory-policy`. An `allkeys-*` policy allows evicting keys without a TTL.
4. **Compare counters over time:** rising `expired_keys` indicates expiration is active; rising `evicted_keys` indicates Redis is evicting keys. Both can happen simultaneously.
5. **Check application-side deletions:** `DEL`, `UNLINK`, `FLUSHDB`, `FLUSHALL`, key updates, serializer mismatches, or key renames also cause misses outside these two mechanisms.
6. **Evaluate business impact:** For rebuildable caches, tune hit/miss ratios and origin protection; for critical state, revisit storage architecture and Redis Server configuration.

Avoid `KEYS *` when investigating instances with many keys, as it can stall the server; use batched `SCAN` if key inspection is truly needed. Note also that `used_memory` does not replace checking host/container OS memory usage, especially when AOF, replication, or co-located processes share resources.

## 8. Key Conclusions to Remember

- **Expiration** depends on each key's TTL and requires no memory pressure.
- **Eviction** depends on Redis Server memory limits and policy; it can delete keys before their TTL or delete keys with no TTL at all.
- `noeviction` only disables memory-pressure eviction; **it does not disable expiration**.
- `TTL = -2` and `GET = nil` only indicate the key is no longer readable; they do not prove why it vanished.
- Use `expired_keys`, `evicted_keys`, memory stats, and event timestamps to investigate at the Redis level; add application logs/context if you must trace one specific key.
- In Spring Data Redis, `Duration` and `RedisCacheConfiguration.entryTtl()` set data lifetimes, while `maxmemory`/`maxmemory-policy` are governed by Redis Server.

**Self-check question:** A cache key has a 1-hour TTL but disappears after 5 minutes while `evicted_keys` increases and Redis runs `allkeys-lru`. How can this be explained? → The key *may* have been evicted early due to memory pressure; additional evidence is needed to attribute that specific key's removal definitively. If Redis runs `noeviction` and `expired_keys` keeps increasing, is there a contradiction? → No, because the two mechanisms are independent.
