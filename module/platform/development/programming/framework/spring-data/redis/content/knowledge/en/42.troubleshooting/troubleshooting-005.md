# TTL Disappearing, Not Being Renewed, or Locks Expiring Unexpectedly in Spring Data Redis

## 1. The Problem: TTL Not Behaving as Expected

A Spring Boot service uses Redis to store caches, sessions, verification codes, counters, and distributed locks. The development team observes confusing symptoms:

- A key is created with a 30-minute TTL, but after updating its value, `TTL` returns `-1`.
- Users continuously read the cache, yet the key still expires after exactly 10 minutes.
- A worker acquired a Redis lock and is running a job when the lock expires; another worker acquires the lock and does the same work concurrently.
- The application calls a TTL renewal method, but the actual result does not change.
- A key disappears while it still has many minutes of TTL left; Redis is simultaneously under memory pressure.
- After a Sentinel/Cluster failover, locks or expirations differ from the state the old primary had just acknowledged.

These incidents belong to different categories:

```text
Key "wrong TTL"
  |
  +-- PTTL = -1: Key exists, but has no expiry.
  |
  +-- PTTL = -2: Key does not exist.
  |                  |
  |                  +-- Expired by TTL?
  |                  +-- DEL/UNLINK/cache eviction?
  |                  +-- Eviction due to memory?
  |                  +-- Reading wrong key, DB, or Redis node?
  |
  +-- PTTL > 0: Key has an expiry.
                     |
                     +-- TTL decreasing normally?
                     +-- GET not renewing?
                     +-- Renewal failed or overwritten?
```

The starting point for diagnosis is **distinguishing between a deleted TTL, a TTL that was not renewed, and a key that actually disappeared**. Do not just increase the TTL to a large number and treat that as a universal fix for every root cause.

In this guide, we use Spring Data Redis with `StringRedisTemplate`, `RedisCacheConfiguration`, Redis Repositories, Lettuce, and Redis CLI. Examples focus on Spring Boot 3.x and Redis 6.2/7.x or newer for features that require specific versions.

## 2. TTL Is an Attribute of a Redis Key

Redis can set an expiration time on a key, then treat the key as non-existent once that time has passed.

```redis
SET session:user-42 active EX 1800
TTL session:user-42
PTTL session:user-42
```

- `EX 1800`: sets a time-to-live of 1,800 seconds.
- `TTL`: remaining seconds.
- `PTTL`: remaining milliseconds.

Redis uses **passive expiration** when a key is accessed and **active expiration** to clean up keys in the background. Internal memory reclamation may lag behind the expiration timestamp, but conforming access operations will not treat an expired key as valid data.

### 2.1. TTL on Hash, List, and Set Is Also Key-Level TTL

```redis
HSET profile:42 name Linh city HCM
EXPIRE profile:42 600
PTTL profile:42
```

When the key `profile:42` expires, the **entire Hash** disappears. An `HSET` command modifying a field of an existing key does not automatically renew the expiry of the whole Hash.

Newer Redis versions add separate expiration mechanisms for individual hash fields. That is a version-dependent feature and is **different** from the key-level `TTL`/`PTTL` covered in this article.

## 3. Interpreting TTL and PTTL Accurately

| Result | Meaning | Investigation Direction |
|---|---|---|
| Positive number | Key exists, has an expiry | Check creation/renewal timestamp |
| `TTL=0` | Key may have under one second of TTL left | Use `PTTL` for millisecond resolution |
| `-1` | Key exists **without an expiry** | Look for overwriting SET, PERSIST, wrong policy |
| `-2` | **Key does not exist** | Look for expire, delete, eviction, key mismatch |

**`-1` does not mean the key has expired.** On the contrary, it means the key exists, but Redis has no scheduled auto-deletion time for it.

**`-2` also does not prove on its own that the key expired.** A key that was never created, was deleted with `DEL`, or was evicted can all return this result.

### 3.1. Avoid Exact TTL Assertions

```redis
SET lab:ttl:k1 hello PX 1000
PTTL lab:ttl:k1
```

The second command may return around 997–999 ms depending on network/scheduling. An integration test should assert a reasonable range, not require exactly 1,000 ms.

### 3.2. Race Between Two Observation Commands

```text
T0: EXISTS key -> 1
T1: key expires
T2: PTTL key -> -2
```

Two commands run separately, so their results can reflect two different points in time. When you need an atomic snapshot of a set of observations on the same Redis node, you can use a read-only Lua script; however, do not add heavy diagnostic overhead to every request.

## 4. Most Common Cause: SET Removes TTL

Run this on a test Redis instance:

```redis
SET product:42 v1 EX 600
PTTL product:42

SET product:42 v2
PTTL product:42
```

A plain `SET product:42 v2` command **overwrites the value and removes the old expiration**. Getting `PTTL=-1` is correct Redis behavior, not a timer bug.

### 4.1. Fix If You Want to Reset TTL on Write

```redis
SET product:42 v2 EX 600
```

Both value and expiry are written in **one command**. Each update starts a fresh lifetime.

### 4.2. Fix If You Want to Keep the Old Expiry

```redis
SET product:42 v2 KEEPTTL
```

`KEEPTTL` preserves the existing expiration timestamp. If the key only had 30 seconds left, after the update it still has about 30 seconds left.

**Keeping TTL is different from renewing TTL.** `KEEPTTL` does not turn 30 seconds into 600 seconds, nor does it add an expiry to a key that already has `PTTL=-1`.

### 4.3. A Common Mistake in Java

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(10));
// ... another thread updates the same key:
redis.opsForValue().set(key, updatedValue); // TTL is removed.
```

When investigating, find **every writer** of the key, not just where the key is initially created.

## 5. SET Followed by EXPIRE Is Two Commands With a Failure Window

```redis
SET session:42 active
EXPIRE session:42 1800
```

Between the two commands, the process can crash, the connection can drop, or another writer can replace the value. The key may be left behind with `PTTL=-1`.

Prefer:

```redis
SET session:42 active EX 1800
```

For a distributed lock:

```redis
SET lock:report owner-token NX PX 30000
```

`NX` only creates the key if it does not already exist. `PX` sets the expiry in the **same atomic execution**.

**Do not use `SETNX` followed by `EXPIRE` as two commands to acquire a lock.** If the process crashes between the two commands, the lock can live indefinitely.

## 6. Which Commands Preserve or Remove TTL?

| Command / Case | Typical Effect |
|---|---|
| `SET key value` | Overwrites value, removes expiry |
| `SET key value EX n` or `PX n` | Sets new TTL |
| `SET key value KEEPTTL` | Preserves existing expiry |
| `MSET` overwriting a key | May remove expiry of the replaced key |
| Legacy `GETSET` | Replaces value and removes expiry |
| `PERSIST key` | Keeps key, removes expiry |
| `EXPIRE` / `PEXPIRE` | Sets or replaces expiry |
| `INCR` on an existing key | Preserves current TTL |
| `HSET` / `HDEL` on an existing Hash | Preserves TTL of the Hash key |
| `LPUSH` / `RPUSH` on an existing List | Preserves key-level TTL |
| `SADD` / `ZADD` on an existing key | Preserves key-level TTL |
| `DEL` / `UNLINK` | Deletes key; PTTL becomes -2 |
| `RENAME` | Transfers key along with expiry to new name per command semantics |

Do not apply a blanket rule such as "write commands renew TTL." Semantics vary by command, whether the key already exists, and the options passed.

### 6.1. INCR on a New Key Does Not Automatically Have a TTL

```redis
INCR rate:login:u42
PTTL rate:login:u42
```

If the key did not exist beforehand, `INCR` creates a counter **without an expiry**, so `PTTL=-1`.

This is a common bug in hand-rolled rate limiters: the counter is created successfully, but setting the TTL for the window is forgotten.

## 7. PERSIST Actively Removes Expiration

```redis
SET lab:ttl:persist temp EX 60
PERSIST lab:ttl:persist
PTTL lab:ttl:persist
```

After a successful `PERSIST`, the key still exists but no longer expires automatically.

Also search for:

- `RedisTemplate.persist(...)` in Java.
- Lua scripts calling `PERSIST`.
- Admin scripts/migration jobs.
- Operations converting a temporary key into a permanent one.

Do not blindly attach an expiry back to **every** key with `-1` without checking the namespace: some keys are intentionally designed to live permanently.

## 8. EXPIRE, PEXPIRE, and Actual Results

```redis
EXPIRE session:42 1800
PEXPIRE lock:report 15000
```

- `EXPIRE` takes seconds.
- `PEXPIRE` takes milliseconds.
- The command can return `0` if the key does not exist or a condition is not met.

### 8.1. Ignoring the Boolean Return Value Is a Diagnostic Bug

Unsafe code:

```java
redis.expire(key, Duration.ofMinutes(30));
log.info("TTL renewed");
```

If the key does not exist, the log still claims renewal succeeded.

Replace with:

```java
Boolean renewed = redis.expire(key, Duration.ofMinutes(30));
if (!Boolean.TRUE.equals(renewed)) {
    throw new IllegalStateException(
        "TTL was not renewed: key absent or condition not met"
    );
}
```

A `null` value can appear in pipeline/transaction contexts depending on the API; do not treat `null` as success.

### 8.2. Zero or Negative Duration Can Delete the Key

```redis
EXPIRE key 0
```

Redis treats a non-positive expiration as a request to delete the key according to command semantics. A `Duration.between(now, expiresAt)` calculation can return 0 or negative if the timestamp has already passed. Validate the duration before sending it to Redis.

## 9. EXPIRE with NX, XX, GT, and LT

Modern Redis versions support conditional options:

```redis
EXPIRE key 600 NX
EXPIRE key 600 XX
EXPIRE key 600 GT
EXPIRE key 600 LT
```

| Option | Sets expiry only when |
|---|---|
| `NX` | Key has no expiry |
| `XX` | Key already has an expiry |
| `GT` | New expiration time is greater than current one |
| `LT` | New expiration time is less than current one |

Redis treats a key with no expiry as having an infinite expiration time when comparing `GT`/`LT`. Therefore, `EXPIRE key 600 GT` will **not** attach a TTL to a permanent key.

### 9.1. Renewal with XX Rejected After SET

```text
SET key v1 EX 60   -> key has TTL
SET key v2         -> TTL removed, key still exists
EXPIRE key 60 XX   -> condition not met
```

If code only checks whether the key exists, it is very easy to misunderstand this. Distinguish **key absent** from **key exists without TTL** when analyzing results.

### 9.2. GT Does Not Verify Lock Ownership

`EXPIRE key 30 GT` can be useful to avoid shortening a deadline in certain workflows; it does **not** prove the calling worker still holds a distributed lock.

## 10. GETEX: Read and Renew in One Command

Redis 6.2+ supports `GETEX` for String keys:

```redis
GETEX session:42 EX 1800
GETEX session:42 PX 30000
GETEX session:42 PERSIST
```

`GETEX key EX n` reads the value and resets the expiry in a single command.

**Warning:** `GETEX key PERSIST` removes the TTL rather than renewing it.

### 10.1. GET and GETEX Are Not the Same

```text
GET key         -> read, does not renew
GETEX key EX n  -> read and set new expiry
```

If the requirement is "keep the session alive as long as there is activity," a regular `GET` call does not fulfill that contract.

### 10.2. GET Followed by EXPIRE Has a Race

```redis
GET session:42
EXPIRE session:42 1800
```

Between the two commands, the key can expire or be revoked by another thread. For String keys and a read-and-touch policy, `GETEX` eliminates this command-pair race.

Do not mistake `GETEX` for a complete session management protocol; logout, revocation, absolute lifetime, and authorization still require separate logic.

## 11. Fixed TTL, Sliding Expiration, and Time-to-Idle

| Policy | Key expires when | Does reading extend it? |
|---|---|---|
| Fixed TTL | N seconds after last write/TTL set | No |
| Sliding expiration | N seconds after most recent valid activity | Yes, if the client performs a touch |
| Time-to-idle (TTI) | N seconds with no access counted as activity | Yes, if the read path uses TTI |

Fixed TTL example:

```text
T0  SET key v EX 600
T5  GET key -> ~300 seconds TTL remaining
T8  GET key -> ~120 seconds TTL remaining
T10 key expires
```

Sliding example:

```text
T0  SET key v EX 600
T5  GETEX key EX 600 -> TTL reset
T8  GETEX key EX 600 -> TTL reset
T18 expires if no new touch occurs
```

**Do not infer from an HTTP GET method name that Redis is using GETEX.** You must inspect the actual commands emitted.

### 11.1. Idle Timeout Differs from Maximum Session Age

A session with a 30-minute idle timeout and a 24-hour maximum lifetime requires two separate conditions. If you only use `GETEX ... EX 1800`, the session can stay alive for days as long as activity continues.

## 12. Spring Data Redis with StringRedisTemplate

Example:

```java
package com.example.redis.ttl;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class SessionValueStore {

    private final StringRedisTemplate redis;

    public SessionValueStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void create(String id, String value) {
        redis.opsForValue().set(
            "session:" + id,
            value,
            Duration.ofMinutes(30)
        );
    }

    public void updateIncorrectly(String id, String value) {
        // Bug illustration: overload without TTL clears expiry.
        redis.opsForValue().set("session:" + id, value);
    }

    public Long remainingMillis(String id) {
        return redis.getExpire(
            "session:" + id, TimeUnit.MILLISECONDS
        );
    }
}
```

Points to check during diagnosis:

- Overload `set(key,value)` vs. `set(key,value,Duration)`?
- Is there another writer in the same namespace?
- Was the duration calculated as 0 or negative?
- Did the key already exist and get overwritten with `SET` instead of updating a field?

Do not assume Spring Data Redis automatically preserves TTL on every value-replacement operation.

## 13. Duration and Time-Unit Bugs

Some systems mix seconds, milliseconds, and configuration values:

```java
long ttl = 600; // 600 what? seconds or milliseconds?
```

Risks:

- Assuming 600 seconds while calling an API that expects milliseconds.
- `Duration.ofMillis(600)` causing the key to expire after 0.6 seconds.
- `Duration.between(Instant.now(), expiry)` returning a negative value.
- Passing milliseconds to `EXPIREAT`, which expects seconds.
- Checking `TTL` against a millisecond expectation and concluding it was shortened.

Prefer `Duration` with explicit units and log `requested_ttl_ms` after normalization. Validate minimum TTL, maximum TTL, and overflow per application policy.

### 13.1. Very Short Lock TTLs Do Not Fit Jittery Networks

If a lock TTL is 50 ms while a normal Redis RTT can be tens of milliseconds and Java experiences GC pauses, a renewal may not arrive in time. Choose the lease duration based on tail latency and the failure model, not only average processing time.

## 14. Spring Cache: Cache Reads Do Not Automatically Renew TTL

Example:

```java
@Cacheable(cacheNames = "products", key = "#productId")
public ProductDto getProduct(String productId) {
    return repository.findById(productId);
}
```

When an entry is written with a fixed TTL, cache hits through the normal GET path **do not automatically extend** its lifetime.

Users can call the API continuously and the cache will still expire after 10 minutes. This may be the intended design.

### 14.1. Fixed TTL Configuration

```java
import java.time.Duration;
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

@Bean
RedisCacheConfiguration redisCacheConfiguration() {
    return RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10));
}
```

Verify that `RedisCacheManager` actually uses the configuration above, rather than a per-cache override or another custom bean.

### 14.2. New Configuration Does Not Update TTL on Existing Entries

If you change TTL from 30 minutes to 5 minutes, previously cached keys can continue carrying the old expiry until rewritten or touched according to policy. Do not assume Spring Cache scans and updates all existing keys on deploy.

During migrations, decide whether to selectively clear the cache, wait for natural expiration, or run a migration job while controlling load on the data source.

## 15. Spring Data Redis Time-to-Idle

Spring Data Redis supports TTI emulation in supported versions, such as Spring Data Redis 3.2+, using `RedisCacheConfiguration.enableTimeToIdle()` combined with Redis `GETEX`.

```java
import java.time.Duration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;

RedisCacheConfiguration cfg =
    RedisCacheConfiguration.defaultCacheConfig()
        .entryTtl(Duration.ofMinutes(10))
        .enableTimeToIdle();
```

When the cache manager actually uses that configuration, cache reads going through the corresponding mechanism can renew the expiry.

**Conditions to verify:**

1. The Redis server supports `GETEX` (Redis 6.2+).
2. The Spring Data Redis version supports the TTI API.
3. The cache manager uses the right configuration.
4. No other access path reads the same key with plain `GET` when the business requirement expects every read to touch it.

Do not conclude TTI is active just because source code calls `enableTimeToIdle()` if runtime uses a different Redis driver or cache manager.

## 16. Dynamic TTL and Per-Cache Overrides

A single cache manager can govern:

```text
products: TTL 10 minutes
stock:    TTL 30 seconds
profile:  TTL 1 hour
```

Some Spring Data Redis versions also support value-dependent dynamic TTL, for instance via `RedisCacheWriter.TtlFunction`.

If a specific entry has an unexpected TTL, check:

- Does a per-cache configuration override the default?
- What value or null sentinel does the TTL function receive?
- Does the selected cache writer actually use that function?
- Does negative caching have a shorter TTL than positive caching?
- Are old keys still left over from before deployment?

Do not inspect only a single property in `application.yml` and conclude all cache entries share the same TTL.

## 17. Redis Repository: @RedisHash and @TimeToLive

A Spring Data Redis Repository can declare TTL on the entity:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "customerSession", timeToLive = 1800)
public class CustomerSession {
    @Id
    private String id;
    private String state;
}
```

Or per-instance TTL:

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("customerSession")
public class CustomerSession {
    @Id
    private String id;

    @TimeToLive
    private Long ttlSeconds;
}
```

When using repositories:

- Check whether TTL comes from the annotation, a property, or a method.
- Understand the unit of the numeric property according to the corresponding API.
- Avoid defining multiple TTL sources without a clear precedence order.
- Check whether repository `save(...)` updates expiration based on entity metadata.
- Do not treat saving a Redis entity as equivalent to a SQL `UPDATE` modifying a single column.

### 17.1. Save Can Reset TTL According to Mapping

Another application flow saving the entity with a stale or wrong TTL can alter the TTL. Under concurrency, inspect the read-modify-save sequence and any other update paths touching the same keyspace.

## 18. Keyspace Notifications and Phantom Copies

Spring Data Redis repositories can use Redis keyspace notifications for expiration events. In corresponding configurations/versions, the framework can also create a **phantom/shadow copy** of the entity to supply data when the primary key expires.

This can leave an auxiliary key in the keyspace after the primary entity key is gone. Naming and lifetimes of auxiliary keys depend on implementation/version, so do not rely on a hardcoded suffix.

Important notes:

- The presence of an auxiliary key does not prove the primary key has not expired.
- Secondary indexes must be handled according to the repository mechanism.
- Notifications rely on Redis Pub/Sub and can be missed if the subscriber is offline.
- Expiration events can be delayed and are not a real-time scheduler.

**Do not use notifications as the sole trigger for time-critical jobs or session revocation.**

## 19. TTL Is Correct Yet Key Still Disappears Early: Expiration vs. Eviction

```redis
INFO stats
INFO memory
CONFIG GET maxmemory
CONFIG GET maxmemory-policy
```

In `INFO stats`:

```text
expired_keys:...
evicted_keys:...
```

- **Expired:** Redis removed the key because its lifetime elapsed.
- **Evicted:** Redis removed the key due to its memory management policy.

A key with a 30-minute TTL can still be evicted after 5 minutes if `maxmemory` and the policy allow it.

### 19.1. Examples of Eviction Policies

- `allkeys-lru`: can select keys across the entire keyspace to evict using approximated LRU.
- `volatile-ttl`: considers keys with a TTL and prioritizes those closest to expiring.
- `noeviction`: does not actively drop keys to free memory under a cache policy, which can cause write commands to be rejected.

Do not say "TTL guarantees the key will exist for at least N minutes." It is an **expiration condition**, not a guarantee against eviction, `DEL`, or failover.

### 19.2. Node-Wide Counters Are Not Proof for a Single Key

A spike in `evicted_keys` is a useful signal, but it does not by itself prove `session:42` specifically was evicted. Correlate workload, time window, namespace, and logs/traces.

## 20. Keyspace Notifications Help Distinguish Expired From Evicted

Check:

```redis
CONFIG GET notify-keyspace-events
```

On an isolated test Redis instance, you can enable keyevent notifications for expiration and eviction:

```redis
CONFIG SET notify-keyspace-events Exe
```

Example channels:

```text
__keyevent@0__:expired
__keyevent@0__:evicted
```

In this example configuration string, `E` enables keyevent notifications, `x` covers expired, and `e` covers evicted. Production settings may need to preserve other notification flags that other applications rely on.

**Do not run CONFIG SET arbitrarily in production.** Notifications add overhead, and managed Redis services may disallow changing this via CLI. Events use Pub/Sub, are not durable, and do not provide a complete historical audit log of every key mutation.

## 21. Active Deletions Easily Mistaken for TTL Expiry

A key also disappears when code calls:

```redis
DEL product:42
UNLINK product:42
```

or via Spring:

```java
redis.delete("product:42");
```

Spring Cache can do:

```java
@CacheEvict(cacheNames = "products", key = "#productId")
public void updateProduct(String productId) {
    // Update database...
}
```

If a key is invalidated after a database change, that may be **correct behavior**, not premature expiration.

Search for:

- `@CacheEvict`, `@Caching`, `@CachePut`.
- `RedisTemplate.delete(...)` and `UNLINK`.
- Scheduled cleanup or migration scripts.
- Lua scripts containing `DEL`.
- Effects of `FLUSHDB`/`FLUSHALL` in test environments or operational mistakes.

Do not fix this by blindly repopulating cache entries, especially when deletion exists to prevent serving stale data.

## 22. Clocks, EXPIREAT, and Absolute Timestamps

Redis stores expiration timestamps; system clocks affect when keys expire and operations using absolute timestamps.

```redis
EXPIREAT key 1794500000
PEXPIREAT key 1794500000000
```

`EXPIREAT` accepts a Unix timestamp in **seconds**, whereas `PEXPIREAT` accepts **milliseconds**. Passing the wrong unit can produce an expiry that is too soon, too far in the future, or already in the past.

### 22.1. Duration Computed From an Already-Expired Timestamp

```java
Duration remain = Duration.between(
    Instant.now(), expiresAt
);
```

If `expiresAt` has passed, `remain` can be negative. Choose an explicit policy: reject, delete the key, or handle the expired session—do not pass a negative `Duration` into an `expire` helper and blame Redis.

### 22.2. Snapshots/Restores and Clocks

A key with an absolute expiry may already be expired when restoring an old snapshot. Do not treat its absence after loading as a restore failure.

For sessions or verification codes, refusing to resurrect expired credentials is usually a security requirement.

## 23. Reading the Wrong Key, Serializer, or Redis Database

One service:

```text
Service A:
  key: session:42
  StringRedisSerializer
  database 0

Service B:
  key looks like session:42 in code too
  JdkSerializationRedisSerializer
  database 1
```

Service B can read the wrong bytes/keyspace and get `PTTL=-2` even though the key written by A still exists.

Check:

1. Redis endpoint, environment, and logical DB.
2. Key prefix, cache prefix, and namespace.
3. Key serializer used by each template.
4. Redis Cache key generation.
5. Redis Cluster routing and slots (Cluster typically uses DB 0).
6. Read-from-replica settings and failover.

**Do not conclude Redis deleted a key on its own just because `redis-cli EXISTS session:42` returns 0** when the application actually writes keys with a different binary serializer.

## 24. Redis Replication and Failover

Standard Redis replication is asynchronous:

```text
Primary P:
   SET lock tokenA NX PX 30000 -> OK
   not yet replicated to R

P fails, R is promoted.

Client GET lock on R -> nil
```

Similarly, a TTL renewal may be acknowledged by the old primary yet not applied on the promoted replica. Reading from a replica can also show TTL/state that has not caught up to the primary.

When diagnosing:

```redis
ROLE
INFO replication
```

Record the node that returned `PTTL`, its primary/replica role, failover timing, and replication lag.

### 24.1. Do Not Treat Failover as Preserving Every Write

Successful client reconnection does not prove every write and expiration update before failover appeared on the new primary. For locks, sessions, and idempotency markers, understand the failure model and build reconciliation or an appropriate source of truth.

## 25. A Distributed Lock Is a Time-Bounded Lease

```redis
SET lock:job:nightly tokenA NX PX 30000
```

Worker A acquires the lock for a 30-second lease. But Redis does not know when the Java job finishes:

```text
T0  A acquires lock
T5  A calls slow API
T20 A hits GC pause
T30 Redis expires lock TTL
T31 B acquires same key with tokenB
T35 B starts processing
T40 A resumes after pause
```

**Redis cannot stop a Java thread or roll back A's side effects.** Once the TTL expires, another owner can acquire the lock.

### 25.1. Proper TTL Must Account for Tail Latency

If a job takes 4 seconds on average but occasionally 50 seconds, a 10-second lease risks overlap. Consider tail latency, GC, network, failover, and job cancellation capability—not just average duration.

An overly long TTL is also harmful: if a worker dies mid-job, other workers must wait longer.

## 26. Pitfall: Renewing a Lock With EXPIRE Without Verifying the Owner

```text
A holds lock, pauses past TTL.
B acquires lock with tokenB.
A wakes up and calls EXPIRE lock 30.
```

`EXPIRE` only modifies the key's expiry; **it does not know whether A still owns the key**. A can unintentionally extend B's lease.

Likewise, if A unconditionally runs `DEL lock` upon completion, it can delete B's lock.

**Every renew and release of a distributed lock must verify the owner token atomically.**

### 26.1. Owner Tokens Must Differ per Acquisition

Do not use the same `"locked"` value for all owners. Generate a fresh token:

```java
String ownerToken = UUID.randomUUID().toString();
```

The owner token compares who holds the right to renew/release. It is not by itself a monotonically ordered fencing token.

## 27. Lua Script to Renew Only If Owner Matches

```lua
-- KEYS[1] = lock key
-- ARGV[1] = owner token
-- ARGV[2] = new TTL (milliseconds)

if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('PEXPIRE', KEYS[1], ARGV[2])
end
return 0
```

The script checks the token and renews the TTL in a single atomic Redis execution.

| State | Expectation |
|---|---|
| Key present, token matches | Returns 1, renewed |
| Key present, different token | Returns 0, does not renew another owner's lock |
| Key already expired | Returns 0, does not recreate it |
| Network timeout | Outcome uncertain, must be handled per protocol |

Do not replace this script with `EXPIRE key n XX`, because `XX` only checks whether the key has an expiry—**it does not verify the owner**.

## 28. Spring Data Redis: Safe Lock Management Service

```java
package com.example.redis.lock;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

public final class RedisLeaseService {

    private static final DefaultRedisScript<Long> RENEW;
    private static final DefaultRedisScript<Long> RELEASE;

    static {
        RENEW = new DefaultRedisScript<>();
        RENEW.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('PEXPIRE', KEYS[1], ARGV[2])
            end
            return 0
            """);
        RENEW.setResultType(Long.class);

        RELEASE = new DefaultRedisScript<>();
        RELEASE.setScriptText("""
            if redis.call('GET', KEYS[1]) == ARGV[1] then
                return redis.call('DEL', KEYS[1])
            end
            return 0
            """);
        RELEASE.setResultType(Long.class);
    }

    private final StringRedisTemplate redis;

    public RedisLeaseService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String tryAcquire(String key, Duration lease) {
        validateLease(lease);
        String token = UUID.randomUUID().toString();
        Boolean ok = redis.opsForValue()
            .setIfAbsent(key, token, lease);
        return Boolean.TRUE.equals(ok) ? token : null;
    }

    public boolean renew(String key, String token, Duration lease) {
        validateLease(lease);
        Long result = redis.execute(
            RENEW,
            List.of(key),
            token,
            Long.toString(lease.toMillis())
        );
        return Long.valueOf(1L).equals(result);
    }

    public boolean release(String key, String token) {
        Long result = redis.execute(
            RELEASE, List.of(key), token
        );
        return Long.valueOf(1L).equals(result);
    }

    private static void validateLease(Duration lease) {
        if (lease == null || lease.isZero()
                || lease.isNegative() || lease.toMillis() <= 0) {
            throw new IllegalArgumentException(
                "Lease must be at least 1 ms"
            );
        }
    }
}
```

This illustrates the mechanism on a single Redis primary. It does not by itself create a distributed coordination protocol that is strictly safe across failovers or prevent a stale worker from performing side effects after TTL expiry.

### 28.1. Timeout During Renewal Is an Uncertain Outcome

A timed-out `renew(...)` may have already executed on Redis with its response lost. Never assume a timeout means success; equally, do not keep working once you lack evidence of ownership according to your protocol.

## 29. Periodic Watchdog Renewal: Benefits and Limits

A worker running a long job can renew periodically:

```text
Lease = 30s
Renew interval = 10s (example)

T0   Acquire
T10  Renew if token matches
T20  Renew if token matches
T30  Renew if token matches
...
Finish -> Release if token matches
```

A watchdog needs to:

- Keep the same token for a given acquisition.
- Renew via Lua compare-and-PEXPIRE.
- Check both `false` returns and timeouts.
- Stop sensitive work when there is insufficient proof it still holds the lease.
- Stop the scheduler when the job finishes or is canceled.
- Avoid silently acquiring a new lock under the old job and continuing.

### 29.1. Renewing Too Close to Expiry Easily Fails

Renewing at second 29 for a 30-second lease only takes one GC pause or network delay to arrive too late. Leave headroom based on real latency/GC behavior, while avoiding overly frequent renewals across huge lock counts.

### 29.2. A Watchdog Cannot Prevent Long JVM Pauses

If the process freezes longer than the TTL, the watchdog pauses too. When it wakes up, a new owner may already hold the lock. That is why owner checks and, for critical workflows, fencing/versioning are required.

## 30. Fencing Tokens: Blocking Stale Owners From Updating Data

A random owner token protects renew/release, but it does not stop an owner whose TTL expired from sending a late SQL update.

```text
Worker A fencing=41, pauses.
A's lease expires, Worker B fencing=42.
B writes resource version=42.
A wakes up, tries to write version=41.
Storage rejects stale generation.
```

Example condition at the authoritative database:

```sql
UPDATE protected_resource
SET payload = :new_payload,
    last_fencing = :new_fencing
WHERE id = :resource_id
  AND last_fencing < :new_fencing;
```

The check must be atomic where the side effect happens.

**Do not use a random UUID as a fencing token:** UUIDs have no ordering. Even a sequence from Redis `INCR` must be evaluated for rollback risk across asynchronous primary–replica failover if strict monotonicity is required.

## 31. Reading the Token Before Writing Does Not Prevent Races

An error-prone approach:

```text
T0: A GET lock -> tokenA
T1: A's lock TTL expires
T2: B acquires and updates data
T3: A proceeds to update data
```

Seeing the right token at T0 **does not prove** the lease is still valid at T3.

If a business operation must prevent stale writes, enforce ownership/version checks at the target resource or use a transactional/coordinator mechanism with appropriate guarantees. A standalone Redis `GET` does not provide atomicity across Redis and PostgreSQL.

## 32. Reactive Redis: Timeout Does Not Roll Back the Command

Example:

```java
Mono<Boolean> acquired =
    reactiveRedis.opsForValue()
        .setIfAbsent(
            "lock:job", ownerToken,
            Duration.ofSeconds(30)
        )
        .timeout(Duration.ofMillis(200));
```

If Redis executed `SET` but the response was lost, the `Mono` can time out even though the key was created. Reactor cancellation **does not roll back a Redis write**.

With reactive locks, you also need:

- Cleanup handling across success/error/cancellation, such as `usingWhen` where appropriate.
- Atomic compare-and-delete on release.
- Handling ambiguous acquisition outcomes.
- Never calling `block()` on a Reactor event loop.
- Not using `onErrorResume` to turn every timeout into "lock acquired."

Redis timeouts and network reconnects also do not automatically make non-idempotent operations safe to retry.

## 33. Testing TTL Against a Real Redis Instance

When verifying TTL semantics, do not rely solely on mocking `RedisTemplate` with a Java `Map`: mocks do not simulate expiration, atomic commands, event timing, and TTL races.

Example Gradle test dependencies (versions must match your project's dependency management):

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers'
    testImplementation 'org.awaitility:awaitility'
}
```

### 33.1. Spring Boot Testcontainers Setup

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.springframework.beans.factory.annotation.Autowired;

@Testcontainers
@SpringBootTest
class RedisTtlIntegrationTest {

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(
            DockerImageName.parse("redis:7.2-alpine")
        ).withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    // Place test methods inside this class.
}
```

Use an isolated test Redis instance only; never run key-deletion experiments, `CONFIG` changes, or fault injection against a Redis serving live users.

## 34. Test: SET Without TTL Removes Expiration

Inside an integration-test class with a `redis` field:

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import java.util.UUID;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

@Test
void plainSetRemovesExistingTtl() {
    String key = "test:ttl:" + UUID.randomUUID();

    redis.opsForValue().set(
        key, "v1", Duration.ofMinutes(5)
    );
    assertThat(redis.getExpire(key, TimeUnit.MILLISECONDS))
        .isPositive();

    redis.opsForValue().set(key, "v2");
    assertThat(redis.getExpire(key, TimeUnit.MILLISECONDS))
        .isEqualTo(-1L);

    redis.delete(key);
}
```

This test clearly shows `-1` after an overwriting write; it has nothing to do with the key being deleted.

## 35. Test: Key Actually Expires by TTL

Use Awaitility to wait for **Redis state**:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import java.util.UUID;

@Test
void keyEventuallyExpires() {
    String key = "test:expires:" + UUID.randomUUID();

    redis.opsForValue().set(
        key, "v1", Duration.ofMillis(500)
    );

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    assertThat(redis.getExpire(
        key, java.util.concurrent.TimeUnit.MILLISECONDS
    )).isEqualTo(-2L);
}
```

Do not require millisecond-exact scheduler precision. Tests should use bounded timeouts and isolated keyspaces to avoid interference from parallel tests.

## 36. Test: Old Owner Cannot Renew New Owner's Lock

Scenario:

1. A acquires a lock with a 250 ms TTL.
2. Wait until Redis reports A's lock is gone.
3. B acquires the same key with a longer TTL.
4. A renews using the old token.
5. The script must return false and B's lock must remain intact.

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.awaitility.Awaitility.await;
import java.time.Duration;
import java.util.UUID;

@Test
void expiredOwnerCannotRenewNewOwnersLock() {
    String key = "test:lock:" + UUID.randomUUID();
    RedisLeaseService lease = new RedisLeaseService(redis);

    String tokenA = lease.tryAcquire(
        key, Duration.ofMillis(250)
    );
    assertThat(tokenA).isNotNull();

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    String tokenB = lease.tryAcquire(
        key, Duration.ofSeconds(10)
    );
    assertThat(tokenB).isNotNull();

    assertThat(
        lease.renew(key, tokenA, Duration.ofSeconds(30))
    ).isFalse();

    assertThat(redis.opsForValue().get(key))
        .isEqualTo(tokenB);
    assertThat(lease.release(key, tokenB)).isTrue();
}
```

This proves the Lua script does not renew for the wrong owner. It does not prove worker A stopped producing side effects after losing its lease.

## 37. Test: Old Owner Cannot Delete B's Lock

```java
@Test
void expiredOwnerCannotReleaseNewOwnersLock() {
    String key = "test:unlock:" + UUID.randomUUID();
    RedisLeaseService lease = new RedisLeaseService(redis);

    String tokenA = lease.tryAcquire(
        key, Duration.ofMillis(250)
    );

    await()
        .atMost(Duration.ofSeconds(5))
        .until(() -> Boolean.FALSE.equals(redis.hasKey(key)));

    String tokenB = lease.tryAcquire(
        key, Duration.ofSeconds(10)
    );

    assertThat(lease.release(key, tokenA)).isFalse();
    assertThat(redis.opsForValue().get(key))
        .isEqualTo(tokenB);
    assertThat(lease.release(key, tokenB)).isTrue();
}
```

If unconditional `DEL key` were used instead of compare-owner-and-delete, this test would expose accidental deletion of the new owner's lease.

## 38. Testing Concurrency, GC Pauses, and Failover

An advanced test suite should reproduce event ordering deterministically rather than relying solely on `Thread.sleep`:

```text
Worker A acquires lock
A signals it entered critical section
Test holds A at a barrier
Wait for real TTL expiration on test Redis
Worker B acquires and writes new version
Release barrier so A resumes
Storage rejects A's stale version
```

Use `CountDownLatch`, `CyclicBarrier`, and bounded timeouts to coordinate; assert **final business state** rather than just counting log lines.

For failover tests:

- Use a test Redis Sentinel/Cluster matching the real topology.
- Record acknowledged writes/renewals around the role switch outside Redis.
- Check owner tokens and TTLs on the new primary.
- Do not assume locks survive every unplanned failover.
- Use fencing/versioning or a transactional store when correctness requires it.

A multi-threaded test in a single JVM does not replace multi-instance/container tests if code uses local `synchronized` state.

## 39. Diagnosing With Redis CLI

On a test Redis instance or keys you are authorized to inspect:

```redis
TYPE session:42
EXISTS session:42
PTTL session:42
INFO stats
INFO memory
INFO keyspace
INFO replication
ROLE
```

These queries help separate key type, availability, expiration, memory pressure, and node role.

### 39.1. MONITOR Is Useful, Not a Default Tool

`MONITOR` lets you watch `SET`, `EXPIRE`, or `PERSIST` commands hitting Redis while reproducing a bug.

However, `MONITOR` carries overhead and can expose keys, values, and credentials in its output. Use it only briefly in a lab or under approved operational procedures—never leave it running on busy production.

### 39.2. An Empty SLOWLOG Does Not Prove There Is No Other Writer

A `SET` that strips TTL can complete in a few microseconds and never appear in the slowlog. `SLOWLOG` is not a complete audit log of key mutations.

## 40. Logs and Metrics Should Be Collected by Semantic Operation

Example structured log:

```text
redis.operation=LEASE_RENEW
redis.key_type=job-lock
redis.result=owner_mismatch
redis.requested_ttl_ms=30000
redis.pttl_after_ms=-2
redis.node_role=primary
request_id=<safe-correlation-id>
```

Never log raw session tokens, Redis passwords, private keys, or full keys containing PII.

Metrics:

| Metric | Meaning |
|---|---|
| Key-without-TTL count by namespace | Detects stripped expirations |
| Unexpected key-absent rate | Detects unexpected key disappearances |
| Lease renewal success/failure | Tracks watchdog health |
| Owner token mismatch | Detects stale-owner races |
| Jobs exceeding lease duration | Evaluates lease TTL sizing |
| Expired/evicted keys rate | Separates expiration from eviction |
| Cache hit/miss by cache name | Evaluates TTI/fixed TTL behavior |
| Redis reconnect/command timeout | Identifies ambiguous outcomes |
| Redis role/failover events | Correlates with state changes |
| API p95/p99 and DB fallback | Measures business impact |

**Do not use keys or session IDs as metric tags:** high cardinality drives storage cost and leaks metadata.

## 41. Case Study: Cache Read Continuously Yet Still Expiring

Scenario:

```text
Cache entry TTL = 10 minutes
User calls GET every 30 seconds
After ~10 minutes a cache miss occurs
```

If Spring Cache uses a **fixed TTL**, this is expected behavior.

Procedure:

1. Check the `RedisCacheConfiguration` actually used by the cache manager.
2. Create a test entry and measure `PTTL`.
3. Trigger a cache hit and inspect whether TTL keeps counting down or is renewed.
4. If TTI is required, configure and verify `enableTimeToIdle()` together with Redis `GETEX`.
5. Check whether other access paths read via plain `GET`.
6. Check stale cache/invalidation behavior when entries stay alive longer.

Do not extend TTL by performing a fake write on every HTTP GET without understanding side effects and desired consistency.

## 42. Case Study: Rate Limiter Counter Without TTL

```redis
INCR rate:login:u42
PTTL rate:login:u42
```

If the counter is new, the result can be `-1`. For a fixed-window rate limiter, you can attach the TTL atomically when the count increments from 0 to 1:

```lua
-- KEYS[1] = counter key
-- ARGV[1] = TTL in ms
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
return count
```

**Limitation:** if a broken key already exists with a count greater than 1 and `PTTL=-1`, this simple script will not repair the old marker. A separate migration policy is needed. Retrying an increment after a timeout can also double-count; if the business logic requires exactly-once counting per request ID, deduplication/idempotency is required.

Do not call this scenario a sliding-window algorithm; it only illustrates fixed-window counter TTL initialization.

## 43. Case Study: Session Deleted During Renewal

```text
T0: GET session -> exists
T1: a logout request calls DEL session
T2: EXPIRE session 1800 -> false
T3: code ignores the Boolean and logs success
```

This can be a valid race between logout and refresh. **Do not automatically re-SET a revoked session** just to make the renewal method return success.

For session security, ensure a failed renewal cannot accidentally resurrect expired or revoked credentials, and enforce an absolute maximum session age.

## 44. Case Study: Lock Renewed Steadily Yet Job Runs Twice

```text
A acquires 30s lock
A renews every 10s
A hits a 40s GC pause
B acquires when A's lease expires
A wakes up and continues writing
```

A watchdog can be implemented correctly and still fail to run during a pause. The fix is not merely shrinking the renewal interval:

- Check ownership before starting new side effects.
- Stop new work when the lease is lost or uncertain.
- Use fencing/version checks at storage.
- Design jobs to be idempotent and include reconciliation.
- Test delayed stale writes when A resumes.

A homegrown distributed lock does not by itself guarantee strict mutual exclusion across pauses, network partitions, and failovers.

## 45. Ordered Diagnostic Checklist

1. Confirm the exact Redis endpoint, role, logical database, key prefix, and serializer.
2. Read `PTTL` and classify into `-1` / `-2` / positive number.
3. For `-1`, look for `SET` without expiry, `PERSIST`, `MSET`, or repository/cache saves.
4. For `-2`, look for expiration, `DEL`/`UNLINK`/cache invalidation, eviction, and key mismatches.
5. For positive TTL, look for a writer setting a shorter expiry or wrong absolute timestamp.
6. Check `EXPIRE` return true/false; inspect `NX`/`XX`/`GT`/`LT` conditions.
7. Check `Duration` seconds/ms units and possible 0 or negative values.
8. For caches, determine fixed TTL vs. TTI and `GET` vs. `GETEX`.
9. For Redis Repositories, check `@TimeToLive`, save paths, and shadow copies.
10. For locks, verify atomic owner-token compare/renew/release.
11. For long-running workers, examine GC pauses, scheduler lag, job tail latency, and fencing.
12. Inspect `expired_keys` vs. `evicted_keys`, memory pressure, and `maxmemory` policy.
13. Cross-check Redis replication lag and failover/Cluster role changes.
14. Reproduce the exact command sequence on a test Redis instance.
15. Re-measure TTL, duplicate job counts, cache misses, API latency, and business impact.

## 46. Misconceptions to Avoid

### "TTL=-1 means the key has expired"

False. The key still exists, just without an expiry.

### "TTL=-2 only means Redis expired the key by TTL"

False. `DEL`, eviction, key mismatch, or never having created the key can produce this result.

### "Every write command renews TTL"

False. `HSET`/`INCR` usually preserve the existing TTL; `SET` without `KEEPTTL` can clear it.

### "KEEPTTL means restarting the TTL"

False. It preserves the previous expiration timestamp.

### "GET always keeps a session alive longer"

False. `GET` does not automatically renew TTL.

### "Spring Cache @Cacheable enables TTI by default"

False. You must explicitly configure TTI support and use a compatible read path.

### "Calling expire() guarantees renewal succeeded"

False. You must check the `Boolean` return value and any expiry conditions.

### "EXPIRE XX sets a TTL on a permanent key"

No. `XX` requires the key to already have an expiry.

### "A key with a TTL cannot be deleted before expiration"

False. Eviction and explicit deletes can remove it early.

### "Not receiving an expired event means the key still exists"

False. Pub/Sub events can be missed or delayed.

### "When a lock's TTL expires, the Java thread stops"

False. Redis does not cancel worker execution.

### "EXPIRE XX is enough to renew a lock safely"

False. It does not verify the owner token.

### "A random UUID is a good fencing token"

No. UUIDs do not represent an increasing sequence.

### "Setting a huge TTL solves every race"

No. It slows recovery after worker crashes and does not fix stale-owner or failover races.

### "Failover always preserves acknowledged expiry updates"

Not guaranteed under asynchronous replication.

### "A different Redis PTTL definitely means a Redis bug"

Not if read from another node/role, at a different time, or after the key was rewritten.

## 47. Summary

Incidents of **disappearing TTL**, **unrenewed TTL**, and **unexpected lock expiration** usually stem from a mismatch between application assumptions and actual Redis semantics:

- An overwriting `SET` clears expiry unless a new TTL or `KEEPTTL` is specified.
- `PTTL=-1` means the key exists without an expiry; `PTTL=-2` means the key is absent and needs root-cause investigation.
- `GET` does not renew; `GETEX` or Spring Cache TTI performs read-and-touch only when configured properly.
- `EXPIRE` can fail if the key is gone or `NX`/`XX`/`GT`/`LT` conditions are unmet.
- Eviction, deletion, serializer mismatches, and failover can make keys look as though they expired early.
- A distributed lock with a TTL is a **temporary lease**; renewal/release must check ownership atomically, and critical operations must guard against stale writes.

**The most important diagnostic rule:** start with `PTTL` on the right key and node, locate the command that altered the value or expiry, and verify with an integration test. Do not fix a lost TTL by increasing timeouts, and do not fix a stale-owner race with an unconditional `EXPIRE`.

## References

- [Redis Documentation — SET](https://redis.io/docs/latest/commands/set/)
- [Redis Documentation — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [Redis Documentation — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/)
- [Redis Documentation — TTL](https://redis.io/docs/latest/commands/ttl/)
- [Redis Documentation — PTTL](https://redis.io/docs/latest/commands/pttl/)
- [Redis Documentation — GETEX](https://redis.io/docs/latest/commands/getex/)
- [Redis Documentation — PERSIST](https://redis.io/docs/latest/commands/persist/)
- [Redis Documentation — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis Documentation — Key eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Redis Documentation — Keyspace notifications](https://redis.io/docs/latest/develop/pubsub/keyspace-notifications/)
- [Redis Documentation — Distributed locks](https://redis.io/docs/latest/develop/use/patterns/distributed-locks/)
- [Redis Documentation — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis Documentation — INFO](https://redis.io/docs/latest/commands/info/)
- [Spring Data Redis Reference — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis Reference — Redis Cache](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html)
- [Spring Data Redis Reference — Redis Repositories](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories.html)
- [Spring Data Redis Reference — Time To Live](https://docs.spring.io/spring-data/redis/reference/redis/redis-repositories/expirations.html)
- [Spring Data Redis API — RedisCacheConfiguration](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/cache/RedisCacheConfiguration.html)
- [Spring Data Redis API — ValueOperations](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ValueOperations.html)
- [Spring Data Redis API — DefaultRedisScript](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Testcontainers — Java](https://java.testcontainers.org/)
- [Awaitility — Documentation](https://github.com/awaitility/awaitility/wiki/Usage)
