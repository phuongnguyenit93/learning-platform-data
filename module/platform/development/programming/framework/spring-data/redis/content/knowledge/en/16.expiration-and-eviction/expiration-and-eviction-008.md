# Distinguishing Explicit Deletion, Expiration, and Memory-Pressure Eviction in Spring Data Redis

In Redis, a *key* can disappear for three different reasons: the application **explicitly deletes** it, the key **expires (TTL)**, or Redis **evicts the key to free memory (eviction)**. All three can cause `GET` to return `nil` and Spring Data Redis to return `null`, yet their causes, timing, level of control, and handling differ.

Understanding these three mechanisms helps design caches, login sessions, verification codes, temporary data, and event-tracking systems without confusing "expired per business rules" with "absent from Redis."

## 1. Overview: three reasons a key disappears

| Criterion | Explicit deletion (*deletion*) | Expiration (*expiration*) | Memory eviction (*eviction*) |
|---|---|---|---|
| Who decides? | Application or operator invokes delete command | Application sets TTL; Redis determines when TTL ends | Redis selects keys according to `maxmemory-policy` |
| Direct trigger | `DEL`, `UNLINK`, or equivalent delete operation | `EXPIRE`, `PEXPIRE`, `SET ... EX/PX` configured expiration | Memory pressure when Redis enforces `maxmemory` limit |
| Requires TTL? | No | Yes | Not necessarily; depends on eviction policy |
| Requires low memory? | No | No | Yes, when memory limit enforcement is active |
| When it becomes invalid | When the delete command executes | When the expiration timestamp arrives | Can occur **before TTL** or on keys without TTL |
| Level of control | Targets exact key to delete | Sets lifetime, though exact physical cleanup timing is not strictly guaranteed | Chooses policy and memory cap, usually not the exact evicted key |
| Typical Redis keyevent | `del` | `expired` | `evicted` |
| Related metrics | Application logs/metrics, deletion events if enabled | `expired_keys` | `evicted_keys` |

These three mechanisms are **not mutually exclusive**. A key with a 30-minute TTL can still be deleted via `DEL` after 5 minutes or evicted after 10 minutes. Once a key is removed, its previous TTL is gone as well.

## 2. Explicit deletion: the application knows when to discard data

### 2.1. `DEL` — delete on demand

`DEL key` deletes an existing key regardless of whether it has a TTL. This command is commonly used when data must be invalidated immediately by business logic, such as:

- User logs out: delete the active login session.
- Product record is updated: delete the product cache so the next read fetches fresh data.
- Task is canceled: remove temporary state that is no longer needed.
- Access code is revoked: discard the code ahead of its expected expiration.

Example in Redis CLI:

```redis
SET app:session:42 "user=42" EX 1800
TTL app:session:42
DEL app:session:42
EXISTS app:session:42
TTL app:session:42
```

After `DEL`, `EXISTS` returns `0` and `TTL` returns `-2` because the key does not exist. `DEL` returns the number of keys actually removed; calling it again on an already-missing key returns `0`. This operation is safely repeatable in the sense that "the key remains absent."

Under default behavior, `DEL` unlinks the key and frees its data structure during command execution. Deleting very large structures can introduce latency on the Redis command-processing thread.

### 2.2. `UNLINK` — logical removal now, memory reclamation later

`UNLINK key` detaches the key from the keyspace immediately, preventing applications from reading it; memory reclamation is offloaded to asynchronous background work where appropriate. It is helpful when deleting large values and wanting to minimize blocking on Redis's command thread.

```redis
UNLINK app:report:large
EXISTS app:report:large
```

Common misconception: `UNLINK` is **not** "scheduling key deletion for later." Once the command completes, the key is logically deleted; only the memory freeing may continue in the background. Do not use `UNLINK` assuming OS RAM usage drops instantaneously.

### 2.3. Deleting with Spring Data Redis

`RedisTemplate` and `StringRedisTemplate` provide corresponding operations:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionInvalidationService {

    private final StringRedisTemplate redis;

    public SessionInvalidationService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public boolean logout(String sessionId) {
        String key = "app:session:" + sessionId;
        return Boolean.TRUE.equals(redis.delete(key)); // DEL
    }

    public boolean removeLargeCachedObject(String reportId) {
        String key = "app:report:" + reportId;
        return Boolean.TRUE.equals(redis.unlink(key)); // UNLINK
    }
}
```

Here, returning `true` only indicates a key was removed at call time. If another process already deleted the key, `false` is not necessarily a business error. In critical code paths, be explicit about whether the requirement is "the key no longer exists at the end" or "this exact call must have deleted the key."

Do not confuse Spring Data Redis deletion with deleting the source record in a relational database. `redis.delete(...)` affects only Redis; if Redis acts as a cache, the source record remains intact and can be reloaded.

## 3. Expiration: Redis automatically invalidates keys by TTL

### 3.1. What does TTL represent?

TTL (*time to live*) is the remaining duration before Redis considers a key expired. An application can create a key with a TTL or set an expiration on an existing key:

```redis
SET app:otp:42 "837219" EX 120
SET app:cache:item:17 "{...}" PX 15000
EXPIRE app:cache:item:17 60
```

In this example:

- `EX 120` sets a 120-second expiration at the time of writing.
- `PX 15000` sets a 15,000-millisecond expiration.
- `EXPIRE ... 60` replaces the existing expiration with 60 seconds from the time the command is called.

`EXPIRE` does not make the key vanish immediately if the new TTL is positive. It attaches an expiration timestamp to the key. Once expired, subsequent accesses no longer return the old value; Redis also cleans up expired keys in the background.

### 3.2. Time-based expiration differs from memory reclamation timing

Redis combines two ways to process expired keys:

1. **Passive/lazy expiration:** when an expired key is accessed, Redis recognizes it as expired, removes it, and treats it as nonexistent.
2. **Active expiration:** Redis periodically samples a subset of keys with TTLs and removes those past their deadline, even if the application has not accessed them.

Therefore, distinguish **when a key becomes invalid for reads** from **when Redis actually frees the data structure in memory**. A key may reach its deadline yet briefly occupy memory before background cleanup processes it. Do not design tasks assuming an `expired` event arrives at the exact millisecond of expiration.

Example:

```text
10:00:00  SET app:otp:42 ... EX 120
10:02:00  TTL ends; key is no longer valid for reading
10:02:01  Next GET may trigger passive deletion
           (or Redis already cleaned it up via active expiration)
```

**TTL is a data validity limit, not a precision job execution clock.** When a task must run on time, use an appropriate scheduler/queue mechanism; keyspace notifications can only serve as an auxiliary signal.

### 3.3. Reading `TTL` and `PTTL`

```redis
TTL app:otp:42
PTTL app:otp:42
```

| Result | Meaning |
|---|---|
| Non-negative number | Remaining time: seconds for `TTL`, milliseconds for `PTTL` |
| `-1` | Key exists but has **no expiration** |
| `-2` | Key **does not exist**; the disappearance cause cannot be deduced from this value alone |

A key with a very short TTL may return `TTL = 0` because Redis returns whole seconds, even before the key expires. When higher resolution is needed, use `PTTL`.

To remove a key's expiration while preserving its value:

```redis
PERSIST app:cache:item:17
TTL app:cache:item:17
```

If `PERSIST` succeeds, `TTL` returns `-1`. This **does not protect** the key from eviction if Redis uses an `allkeys-*` policy.

### 3.4. Operations that affect TTL

- `EXPIRE`/`PEXPIRE` sets or replaces an existing key's expiration; the command fails if the key does not exist.
- Overwriting a key with a plain `SET` normally clears the prior TTL unless a TTL-preserving option supported by Redis is used. This is a common cause of caches accidentally living forever.
- Mutating contents in place within a data structure, such as incrementing a counter with `INCR`, normally preserves the key's TTL.
- `DEL` or `UNLINK` removes both the key and its TTL; creating a new key with the same name later starts a new lifecycle.
- Setting an expiration of 0 or a timestamp in the past causes immediate key deletion; this may emit a `del` event rather than `expired`.

If the entire requirement is "write a value and expire it after 15 minutes," use a single write operation **with TTL** instead of splitting `SET` and `EXPIRE` into two commands. Two separate commands leave a gap if the process crashes midway, leaving the key with a value but no TTL.

### 3.5. Writing and reading TTL with Spring Data Redis

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OneTimeCodeStore {

    private static final Duration CODE_TTL = Duration.ofMinutes(2);
    private final StringRedisTemplate redis;

    public OneTimeCodeStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void save(String userId, String hashedCode) {
        // Redis writes the value and TTL in a single operation.
        redis.opsForValue().set("app:otp:" + userId, hashedCode, CODE_TTL);
    }

    public String find(String userId) {
        return redis.opsForValue().get("app:otp:" + userId);
    }

    public Long remainingSeconds(String userId) {
        return redis.getExpire("app:otp:" + userId, TimeUnit.SECONDS);
    }

    public boolean extend(String userId) {
        return Boolean.TRUE.equals(
            redis.expire("app:otp:" + userId, Duration.ofMinutes(2))
        );
    }

    public boolean cancel(String userId) {
        return Boolean.TRUE.equals(redis.delete("app:otp:" + userId));
    }
}
```

Note the difference between `extend(...)` and `cancel(...)`: one **resets the expiration** on an existing key, while the other **deletes the key immediately**. When `find(...)` returns `null`, you cannot tell whether the key was manually deleted or expired; eviction produces the exact same symptom.

With Redis repositories, Spring Data Redis also supports object-level TTL, such as `@RedisHash(timeToLive = 900)` on the class or a `@TimeToLive` property. This is still simply configuring Redis expiration. The annotation does not mean the object is exempt from eviction or that expiration events are guaranteed to arrive on time.

## 4. Eviction: Redis drops data under memory pressure

### 4.1. How is eviction triggered?

Redis can be configured with a memory limit via `maxmemory`. When additional memory is needed while over the threshold, Redis applies `maxmemory-policy` to select keys for removal, or returns an error for certain write commands if the policy forbids eviction.

Example Redis-side configuration:

```conf
maxmemory 256mb
maxmemory-policy allkeys-lru
```

This is a Redis server setting, not a per-key TTL set by Spring Data Redis. These values are illustrative only; choose limits based on available memory, data characteristics, and deployment setup.

Characteristics of eviction:

- Keys can be deleted **while their TTL still has time left**. For example, 25 minutes remain on the TTL, yet the system must reclaim memory immediately.
- Keys **without a TTL** can also be evicted if an `allkeys-*` policy allows it.
- Key selection depends on the policy and metadata Redis tracks; do not treat LRU/LFU as an absolute guarantee that a specific key will definitely stay.
- Eviction relieves memory pressure on Redis. It does not signify that data has become invalid under business rules.

The `maxmemory` limit and Redis memory metrics do not align identically with OS-observed RAM (e.g., due to buffers and allocator overhead). Do not rely on a single number to conclude the system will never exceed physical RAM limits.

### 4.2. `maxmemory-policy` options

| Policy | Keys eligible for selection | Selection strategy |
|---|---|---|
| `noeviction` | None evicted automatically for memory | Write commands needing more memory may get an OOM error |
| `allkeys-lru` | All keys | Prefers least recently used keys via LRU approximation |
| `allkeys-lfu` | All keys | Prefers least frequently used keys via LFU approximation |
| `allkeys-random` | All keys | Random selection |
| `volatile-lru` | Only keys with TTL | Approximated LRU among keys with TTL |
| `volatile-lfu` | Only keys with TTL | Approximated LFU among keys with TTL |
| `volatile-random` | Only keys with TTL | Random selection among keys with TTL |
| `volatile-ttl` | Only keys with TTL | Prefers keys with nearer expiration deadlines |

**`volatile-*` does not mean Redis waits until a key's TTL expires.** Redis can still delete the key early; TTL is only the eligibility filter. If there are not enough keys carrying a TTL to evict, these policies can lead to write errors similar to `noeviction`.

**`noeviction` does not disable expiration or manual deletion.** Keys reaching TTL are still expired; `DEL`/`UNLINK` still work. It merely stops Redis from automatically dropping valid keys due to memory pressure policies.

LRU (*least recently used*) relies on access recency; LFU (*least frequently used*) relies on Redis-estimated access frequency. Redis algorithms use approximation and sampling, not a strict global ordering across every key.

### 4.3. Example: TTL has not expired yet, but data is evicted

Suppose a cache entry is given a 30-minute TTL while Redis uses `allkeys-lru`:

```text
12:00  SET app:cache:product:17 ... EX 1800
12:05  Redis hits memory pressure; less-accessed keys are chosen
12:05  app:cache:product:17 is evicted, despite ~25 minutes of TTL left
12:06  GET app:cache:product:17 -> nil
12:06  Application reloads data from source and writes fresh cache
```

Looking only at `GET -> nil`, the system cannot distinguish this event from an expiration miss or a recent application cache delete. Therefore, cache read paths must **handle missing data at any moment**, even right after a TTL was successfully set.

### 4.4. Which policy should you choose?

| Scenario | Approach to consider | Rationale |
|---|---|---|
| Redis acts mainly as a cache; data is rebuildable | `allkeys-lru` or `allkeys-lfu` | Allows all cache keys to compete for memory |
| Only one subset of keys is expendable, and all carry TTLs | Consider `volatile-*` | Isolates eviction eligibility, though write-error risk must be accounted for if that pool runs dry |
| Redis holds data that must not be lost to memory pressure | `noeviction` **with proper capacity planning and storage** | Prevents proactive eviction under low memory; in return, app must handle write errors and Redis does not replace durable storage |
| Want to prefer evicting keys nearest expiration | `volatile-ttl` | Uses TTL as a selection signal; does not wait for expiration |

When one Redis instance stores both rebuildable caches and critical sessions or state, sharing a single policy across all of them can produce unpredictable effects. Consider separating workloads or instances by data-loss tolerance and memory profile.

## 5. Relationships among the three mechanisms across scenarios

### Scenario A: User logs out early

A session is created with a 1-hour TTL. After 10 minutes, the application calls `DEL` or `UNLINK` when the user logs out. The session disappears **via explicit deletion**, without waiting the full hour. This is a business decision and must take effect immediately upon successful logout.

### Scenario B: OTP expires after two minutes unused

The application writes the code with a 120-second TTL. Once enough time passes, Redis treats the code as expired and subsequent reads no longer see it. This is **expiration**; it does not require memory pressure, nor does the application need to send `DEL` at second 120.

### Scenario C: Cache has not expired, but Redis is full

A cache key with a 30-minute TTL is removed by Redis after 3 minutes under `allkeys-lfu`. This is **eviction**; its content may still be "fresh" by TTL, yet Redis had to make room for other keys. The application must handle the cache miss and rebuild the data if appropriate.

### Scenario D: `volatile-lru` selected, yet no keys have a TTL

Redis has no eligible eviction candidates. When more memory is needed beyond the limit, certain write commands can fail with an out-of-memory error. Do not assume `volatile-lru` protects every key or causes Redis to automatically drop old data regardless of TTL.

### Scenario E: Deleted a key, then another process recreates the same name

One task calls `DEL app:cache:item:17`, while another immediately calls `SET app:cache:item:17` with a new value. Observing `EXISTS = 1` afterward **does not prove `DEL` failed**. It could be a brand-new key lifecycle. When preventing race conditions, define synchronization requirements clearly and use atomic operations or appropriate versioning.

## 6. Designing Spring Data Redis to tolerate both expiration and eviction

For reloadable caches, three behaviors typically map to three distinct needs:

```text
App writes cache ------- SET k v EX <ttl> ------> Redis
      |                                           |
      | source data changes                       | TTL ends
      +----------------- DEL k ------------------>+--> key disappears
                                                  |
                                                  | maxmemory pressure
                                                  +--> key may disappear early

App reads GET k ---> value present: use cache
                \--> nil: fetch from source then rewrite cache
```

Encapsulating cache operations with Spring Data Redis:

```java
import java.time.Duration;
import java.util.function.Supplier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Component;

@Component
public class ProductCache {

    private static final Duration CACHE_TTL = Duration.ofMinutes(20);
    private final StringRedisTemplate redis;

    public ProductCache(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getOrLoad(String productId, Supplier<String> loadFromDatabase) {
        String key = "app:cache:product:" + productId;
        String cached = redis.opsForValue().get(key);
        if (cached != null) {
            return cached;
        }

        // Cache miss may be due to never written, deleted, expired TTL, or eviction.
        String loaded = loadFromDatabase.get();
        if (loaded != null) {
            redis.opsForValue().set(key, loaded, CACHE_TTL);
        }
        return loaded;
    }

    public void invalidate(String productId) {
        redis.delete("app:cache:product:" + productId);
    }
}
```

This is an example for rebuildable cache data. In real systems, also account for cache stampedes (many concurrent requests rebuilding the same key), concurrent updates, and ordering between source writes and cache invalidation. Rewriting the cache can also hit an OOM error if Redis uses `noeviction` or lacks eviction candidates; error handling must match whether caching is mandatory for the request.

For verification data such as OTPs, TTL caps the usage window but **does not guarantee the data survives until the deadline** if eviction occurs. If a code must be consumed only once, a two-command `GET` then `DEL` sequence risks a race between concurrent requests. Use an atomic operation like `GETDEL` when supported by your Redis version and API, or an appropriate Lua script so two requests cannot consume the same code.

## 7. Observing and diagnosing disappearing keys

### 7.1. Start with key status and Redis configuration

Useful inspection commands:

```redis
EXISTS app:cache:product:17
TTL app:cache:product:17
PTTL app:cache:product:17
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
INFO memory
INFO stats
```

Focus on these metrics:

- `expired_keys`: number of keys Redis processed as expired; rises quickly when large amounts of data hit TTL.
- `evicted_keys`: number of keys removed by memory-pressure policies; increases signal a need to review capacity or eviction policy.
- `used_memory` and `maxmemory`: help assess how close Redis is to its memory limit.
- `keyspace_hits` and `keyspace_misses`: reflect cache access behavior, though they **do not directly reveal** the exact cause of an individual cache miss.

These statistics mainly describe the whole instance over an observation interval rather than pinpointing why an individual key vanished. Nor are `TTL = -2` or `EXISTS = 0` enough to claim "it expired." Deeper diagnosis requires correlating application action logs, Redis config, metrics, and previously captured events.

### 7.2. Keyspace notifications: distinguishing events if enabled

Redis can emit events by operation type, for example:

| Keyevent | Common interpretation |
|---|---|
| `del` | Key was deleted by a delete command or an operation with equivalent deletion effect |
| `expired` | Redis detected and deleted the key due to expiration |
| `evicted` | Redis removed the key due to memory pressure |

Example configuration on a test instance:

```redis
CONFIG SET notify-keyspace-events Egxe
PSUBSCRIBE __keyevent@0__:*
```

In the configuration string, `E` enables keyevent notifications, `g` includes generic commands like `del`, `x` covers expired events, and `e` covers evicted events. The `@0` channel targets database 0; other environments require the matching database and configuration. Managed Redis providers may disallow dynamic `CONFIG` changes.

**Keyspace notifications use Pub/Sub, not a durable log.** Subscribers can miss events on disconnect, when unconfigured, or before subscribing. The `expired` event does not necessarily fire the instant TTL hits 0; Redis emits it when the key is actually removed due to expiration. Do not use these notifications as the sole source of truth for financial transactions, durable deletions, or exactly-once processing guarantees.

In Spring Data Redis, expiration event listeners can be built with `RedisMessageListenerContainer`; Redis repositories also support expiration event listeners. These listeners remain subject to Pub/Sub's best-effort nature. If a business process requires guaranteed execution, use a durable queue/scheduler and store state in an appropriate data store.

### 7.3. Troubleshooting table

| Observed symptom | Causes to investigate | Direction to address |
|---|---|---|
| Key vanishes right after logout or data update | `delete`, `unlink`, invalidation commands, cache cleanup jobs | Inspect delete call paths and business logs |
| Key consistently disappears after a fixed duration | TTL via `SET ... EX`, `expire`, repository annotation | Check TTL values, rewrite paths, and expiration rules |
| Keys disappear early, especially as load or memory rises | Eviction | Inspect `evicted_keys`, `maxmemory`, eviction policy, and key size distribution |
| TTL suddenly becomes `-1` after updating value | Overwrite command stripped the TTL | Write value with TTL atomically or intentionally preserve TTL per design |
| Writes return OOM despite keys still in Redis | `noeviction`, or `volatile-*` lacks enough eligible candidates | Check policy, key TTLs, memory limits, and capacity |
| Not receiving `expired` events | Keyspace notifications disabled, subscriber interrupted, key removed for another reason | Check config/events; avoid relying on events for business guarantees |

## 8. Misconceptions to avoid

**"Once a TTL is set, the key is guaranteed to exist until the TTL expires."** False. Eviction and explicit deletion can remove the key sooner. TTL only specifies when Redis stops treating the value as valid due to time.

**"When Redis runs full, it deletes expired keys first, so unexpired keys are unaffected."** You cannot assume this. Redis has separate mechanisms for cleaning expired keys and enforcing eviction; depending on policy, valid keys can still be selected for removal.

**"`GET` returning `null` means the key just expired."** False. It might never have existed, been explicitly deleted, been evicted, or already been expired earlier. On cache read paths, treat it as a cache miss and handle per design.

**"`volatile-lru` protects all keys with a TTL from data loss."** On the contrary, keys with a TTL are precisely the eviction candidates. Keys without a TTL are outside this policy's candidate pool.

**"`noeviction` makes Redis keep keys forever."** False. TTLs and delete commands still apply. Meanwhile, `noeviction` can cause write operations to fail when memory is full.

**"`UNLINK` is delayed deletion; the app can still read the key briefly."** False. The key is removed from the keyspace immediately; only memory freeing may happen asynchronously.

**"Enabling keyspace notifications is enough to build a guaranteed scheduler."** False. Pub/Sub does not retain messages for disconnected subscribers, nor are expiration events guaranteed to fire the moment TTL reaches 0.

## 9. Rules for choosing operations in the application

1. **Need to discard data immediately because business state changed?** Call `delete` (`DEL`) or `unlink` (`UNLINK`); for large objects, consider `UNLINK` to reduce memory-freeing time on the command thread.
2. **Need data valid only for a period of time?** Write with a TTL via `opsForValue().set(key, value, Duration)` or an appropriate repository TTL config. Design readers to tolerate early key disappearance.
3. **Need to keep Redis within a RAM budget?** Configure `maxmemory` and `maxmemory-policy` on the server according to data traits; monitor `evicted_keys` and OOM errors. Eviction policies do not replace business TTLs.
4. **Need to analyze why a key disappeared?** Combine explicit-delete logs, expiration/eviction metrics, TTLs, and events if available. Never infer the cause from `GET`/`EXISTS` alone after a key is already gone.

The takeaway when using Spring Data Redis is that the three mechanisms operate at **three distinct layers**: the application commands deletion, the application declares expiration lifetimes, and Redis manages memory according to an instance-wide policy. A sound design allows them to happen independently and handles a missing key safely.
