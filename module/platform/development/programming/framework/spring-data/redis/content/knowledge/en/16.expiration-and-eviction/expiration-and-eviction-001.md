# Setting TTL on Key Creation and Key Update in Spring Data Redis

**TTL (Time To Live)** is the remaining time before a **Redis key** expires. TTL is widely used for caches, OTPs, login sessions, idempotency keys, rate-limit counters, and temporary data. Understanding TTL accurately helps prevent two opposite bugs:

- **Data living too long** because the application creates a key and forgets to set an expiration, or updates it with a command that clears the old TTL.
- **Data expiring too early or being extended unintentionally** because an update resets the TTL when business rules require keeping the original deadline.

In **Spring Data Redis**, TTL can be set via `StringRedisTemplate`, `RedisTemplate`, Spring Cache, or Redis Repository metadata. Each storage path has its own semantics. You should not infer that "every write command resets TTL" or that "every write command preserves TTL."

Key takeaway of this lesson:

> **TTL belongs to the Redis key, not to the Java object.** When creating a key, write the data together with its expiration in **a single Redis operation** whenever possible. When updating, choose explicitly: keep the existing TTL, extend from now, set a fixed deadline, or remove the TTL.

## 1. At what layer does TTL operate?

Redis stores data across many types: String, Hash, List, Set, Sorted Set, Stream, and more. With the standard `EXPIRE` mechanism, Redis manages **expiration for the entire key**.

Example:

```text
Redis database
│
├── otp:request-01           string        TTL = 120 seconds
├── cache:product:sku-42     string        TTL = 600 seconds
├── cart:customer-7          hash          TTL = 1800 seconds
├── queue:pending            list          TTL = -1 (no expiration)
└── ranking:weekly           sorted set    TTL = -1 (no expiration)
```

`EXPIRE cart:customer-7 1800` sets an expiration for the **entire Redis hash** keyed by `cart:customer-7`. It does not expire only one field inside the hash. Some newer Redis versions offer a separate hash-field expiration mechanism, but that is a different command group and model from the key-level TTL presented here.

### 1.1. TTL is remaining time, not creation time

If you create a key with a 300-second TTL at 10:00:00, Redis expects the key to expire around 10:05:00. After 40 seconds, roughly 260 seconds of TTL remain. Redis does not attach concepts like "cache" or "OTP" to a key; expiration is metadata set by the application.

Deadlines can be controlled in two ways:

| Setting style | Example | How to understand |
|---|---|---|
| **Relative duration** | `EXPIRE key 300` | Expires after roughly 300 seconds from when the command takes effect |
| **Absolute timestamp** | `EXPIREAT key <unix-seconds>` | Expires at a specific Unix timestamp |

Redis enforces expiration by checking on access and cleaning up expired keys in the background. Consequently, when physical memory is reclaimed or when an expiration notification is received does not necessarily match the deadline down to the millisecond. However, an expired key is never treated as valid data to be returned for normal read commands.

### 1.2. Distinguishing TTL and eviction

**Expiration** happens when a key's lifetime ends. **Eviction** happens when Redis must drop data due to memory limits and `maxmemory-policy`. A key with a 30-minute TTL can still be evicted before 30 minutes if the server runs out of memory and the policy allows it.

Thus, TTL **does not guarantee a key survives the full duration**; rather, it sets the maximum lifetime under the expiration mechanism. Applications must handle cache misses or missing-key states.

## 2. Inspecting TTL with the Redis CLI

Two common inspection commands:

```redis
TTL key
PTTL key
```

`TTL` returns remaining **seconds**; `PTTL` returns remaining **milliseconds**.

| Result | Meaning |
|---|---|
| Non-negative number | Remaining lifetime in the command's unit, possibly near 0 when about to expire |
| `-1` | Key exists **but has no expiration** |
| `-2` | Key **does not exist** (including when it has already expired) |

Example:

```redis
SET demo:ttl "hello" EX 120
TTL demo:ttl
# Usually near 120, decreasing over time

PTTL demo:ttl
# Usually near 120000, decreasing over time

PERSIST demo:ttl
TTL demo:ttl
# (integer) -1

DEL demo:ttl
TTL demo:ttl
# (integer) -2
```

**Do not misread `TTL = -1` as "already expired."** It means the opposite: the key exists and **has no TTL**. `-2` indicates the key does not exist.

When multiple clients update concurrently, the observed TTL is a **snapshot at a single call**, not a guarantee that the value remains intact right after the command finishes.

## 3. Setting TTL immediately when creating a Redis String

### 3.1. `SET` with `EX` or `PX`

Redis supports setting both the value and expiration in a single command:

```redis
SET otp:request-01 "482913" EX 120
SET cache:product:sku-42 "{\"id\":\"sku-42\"}" EX 600
SET temp:lock:job-7 "owner-123" PX 15000
```

Meaning:

- `EX 120`: TTL of 120 **seconds**.
- `PX 15000`: TTL of 15,000 **milliseconds**.
- Without `EX`/`PX`/another expiration option, `SET key value` creates a key with no TTL.
- `SET ... EX/PX` is **one command**: the new value and expiration are applied in a single Redis operation.

Setting TTL right at creation time is especially helpful for OTPs or temporary security data: it avoids the gap between two separate commands.

### 3.2. Why can `SET` followed by `EXPIRE` be risky?

The two-command pattern:

```redis
SET otp:request-02 "731204"
EXPIRE otp:request-02 120
```

leaves a window where the key is already written but **has no expiration yet**. If the application crashes, loses network connectivity, or throws an exception between the two commands, the key can live indefinitely.

```text
Application                        Redis
   │                                 │
   ├──── SET otp:... ───────────────►│ Writes key without TTL
   │◄── OK ──────────────────────────┤
   │
   X process crashes
   │
   └── EXPIRE ... IS NEVER SENT

Result: key still exists with TTL = -1
```

For **Redis Strings**, prefer `SET key value EX seconds` or the equivalent Spring Data Redis API for an atomic write-with-expiration operation.

### 3.3. Create only if the key does not exist: `NX`

The command:

```redis
SET otp:request-01 "482913" EX 120 NX
```

creates the key only if it **does not already exist**. If the key exists, Redis does not overwrite the value and does not reset the TTL via that failed call.

When an application needs to "register an idempotency key once" or "acquire a temporary key," use the `NX` condition combined with TTL in **the same command**. Note that a lock key is only one part of a distributed locking protocol; setting `NX EX` alone does not solve ownership, safe unlocking, fencing, or expiration issues during long-running processing.

### 3.4. Update only if the key already exists: `XX`

```redis
SET otp:request-01 "902184" EX 120 XX
```

`XX` updates only if the key still exists. If the key has expired or been deleted, the command does not create a new key. When it succeeds, it **resets the TTL** per `EX 120` from that update.

| Command | When key does not exist | When key already exists |
|---|---|---|
| `SET key v EX 120` | Creates key, TTL 120s | Overwrites value, resets TTL to 120s |
| `SET key v EX 120 NX` | Creates key, TTL 120s | Leaves value/TTL unchanged |
| `SET key v EX 120 XX` | Does not create key | Overwrites value, resets TTL to 120s |
| `SET key v` | Creates key with no TTL | Overwrites value, usually **clears old TTL** |

Conditional commands are very useful, but they are **not a general-purpose CAS** on the old content. `XX` only checks existence, not whether the value or version matches business expectations.

## 4. TTL on key updates: not all write commands behave alike

This is the most important part when working with Spring Data Redis.

### 4.1. Plain `SET` loses the old TTL

```redis
SET demo:update "v1" EX 300
TTL demo:update
# Near 300

SET demo:update "v2"
TTL demo:update
# (integer) -1
```

The `SET key value` command overwrites the entire Redis String value and **removes the existing expiration**, unless an option to keep the TTL or a new expiration is provided in the same command.

This easily happens if initial code writes:

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(5));
```

but another update path later runs:

```java
redis.opsForValue().set(key, updatedValue);
```

Result: the key can transition from a 5-minute TTL to **no TTL at all**, causing the cache to persist longer than expected.

### 4.2. `SET ... EX/PX` resets TTL from update time

```redis
SET demo:update "v1" EX 300
# After ~120 seconds, TTL is near 180

SET demo:update "v2" EX 300
TTL demo:update
# Near 300 — TTL has been refreshed
```

This is the **refresh TTL on write** pattern. It fits when each data update should extend lifetime by another 300 seconds from the latest write.

However, if the business rule is "OTP is valid for at most 5 minutes from initial issuance," updating the value with `SET ... EX 300` can **extend it in violation of policy**. Choose the expiration policy based on business rules.

### 4.3. `SET ... KEEPTTL` preserves the existing expiration

Redis supports:

```redis
SET demo:update "v1" EX 300
SET demo:update "v2" KEEPTTL

TTL demo:update
# TTL continues counting down from the first SET
```

`KEEPTTL` tells Redis to **keep the existing key's expiration** when replacing the value via `SET`. If the key does not exist yet, there is no prior TTL to retain; a new key created by `SET ... KEEPTTL` will not automatically get an expiration.

Do not use `KEEPTTL` expecting a newly created key to always have a default TTL. If you need the invariant "every key must expire," the creation path must explicitly set an expiration.

### 4.4. In-place update commands usually preserve TTL

Commands that modify the **contents of an existing key** without replacing the whole key—such as `INCR`, `HSET`, `LPUSH`, `ZADD`, or `APPEND`—normally **do not clear the existing TTL**.

Example:

```redis
SET demo:counter 10 EX 120
INCR demo:counter
TTL demo:counter
# TTL remains, continuing to count down
```

Redis Hash example:

```redis
HSET demo:profile name "An"
EXPIRE demo:profile 600
HSET demo:profile city "Hanoi"
TTL demo:profile
# Keeps TTL from the initial EXPIRE; HSET does not auto-refresh
```

Important note: if `HSET`/`LPUSH`/`ZADD` **creates a brand-new key**, that key **does not automatically receive a TTL** just because it is a Hash/List/ZSet. When initializing a new structure, the application must set a TTL separately or use an appropriate combined operation.

| Redis operation | On a key with existing TTL | When creating a new key |
|---|---|---|
| `SET key v` | Clears old TTL | No TTL |
| `SET key v EX 60` | Sets new 60s TTL | 60s TTL |
| `SET key v KEEPTTL` | Keeps remaining TTL | Does not auto-add TTL |
| `INCR key` | Usually keeps TTL | New counter key has no auto-TTL |
| `APPEND key suffix` | Usually keeps TTL | New String key has no auto-TTL |
| `HSET key field value` | Usually keeps Hash TTL | New Hash has no auto-TTL |
| `LPUSH`/`RPUSH` | Usually keeps List TTL | New List has no auto-TTL |
| `SADD` | Usually keeps Set TTL | New Set has no auto-TTL |
| `ZADD`/`ZINCRBY` | Usually keeps ZSet TTL | New ZSet has no auto-TTL |
| `EXPIRE key 60` | Sets or replaces TTL | Does not create key if missing |
| `PERSIST key` | Removes TTL | Does not create key if missing |
| `DEL key` | Deletes key and TTL metadata | No key left to hold TTL |

"Keeps TTL" in the table means **does not proactively reset the deadline**, not that the TTL stops counting down over time.

## 5. Using `EXPIRE` and related commands to reset expiration

### 5.1. `EXPIRE` and `PEXPIRE`

```redis
EXPIRE demo:key 300
PEXPIRE demo:key 1500
```

- `EXPIRE key seconds` sets a relative expiration in **seconds**.
- `PEXPIRE key milliseconds` sets a relative expiration in **milliseconds**.
- The command takes effect on an existing key regardless of whether it is a String, Hash, List, Set, or Sorted Set.
- If the key does not exist, Redis does not create it; the result indicates expiration could not be set.
- A zero or negative duration can cause the key to be deleted immediately, rather than configuring "no expiration." Applications should validate a positive `Duration` before calling.

Example:

```redis
SET demo:manual "hello"
TTL demo:manual
# -1

EXPIRE demo:manual 60
TTL demo:manual
# Near 60

EXPIRE demo:manual 180
TTL demo:manual
# Near 180 — replaces old expiration
```

`EXPIRE` is helpful when a key was created by a command that does not support simultaneous TTL, though the two separate steps `create -> EXPIRE` must be evaluated for atomicity.

### 5.2. `EXPIREAT`, `PEXPIREAT`, and absolute deadlines

If a session must only remain valid until **the exact same deadline**, regardless of how many updates happen, you can set expiration using a Unix timestamp:

```redis
EXPIREAT demo:session 1893456000
PEXPIREAT demo:session 1893456000000
```

The numbers in the example are illustrative Unix timestamps, not fixed business dates. The second and millisecond forms correspond to the two commands.

Redis `SET` also supports absolute-deadline options like `EXAT`/`PXAT` on compatible Redis versions:

```redis
SET demo:session "active" EXAT 1893456000
```

When an application enforces an explicit cutoff time (for example, a promo code ending at 23:59:59 UTC), an absolute deadline prevents each update from adding another relative TTL window.

**Clock caveat:** Absolute expiration uses Unix time; server clocks, application timestamps, and time synchronization are part of correctness. Passing a timestamp already in the past can cause the key to expire/be deleted immediately.

### 5.3. Conditional options for `EXPIRE`

Redis 7.0+ supports these conditions:

| Condition | Only replace expiration when... |
|---|---|
| `NX` | The key currently has no expiration |
| `XX` | The key already has an expiration |
| `GT` | The new expiration is **later than** the current expiration |
| `LT` | The new expiration is **earlier than** the current expiration |

Example:

```redis
SET demo:deadline "active"
EXPIRE demo:deadline 300 NX
# Succeeds if the key has no TTL yet

EXPIRE demo:deadline 600 GT
# Extends only if the new deadline is later

EXPIRE demo:deadline 120 LT
# Shortens only if the new deadline is earlier
```

When comparing with `GT`/`LT`, a key **without a TTL** is treated as having an infinite expiration. Thus, `EXPIRE key 60 GT` cannot turn a permanent key into an expiring key; conversely, `LT` can set a finite expiration shorter than infinity.

These options are Redis Server capabilities; not every `RedisTemplate.expire(...)` overload exposes every condition directly. When needed, use a command API supported by your library version or a suitable script.

## 6. Spring Data Redis: creating a String with TTL in one operation

In Spring Boot, `StringRedisTemplate` is normally auto-configured once the dependency and Redis connection are ready:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example `application.yml` for a local test Redis:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

`StringRedisTemplate` works with UTF-8 string keys and values. For other Java objects, `RedisTemplate<K,V>` needs matching serializers, though TTL semantics on Redis Server remain key-based.

### 6.1. Creating a key with TTL

```java
import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

StringRedisTemplate redis = /* Spring inject */;

redis.opsForValue().set(
    "cache:product:sku-42",
    "{\"name\":\"Keyboard\"}",
    Duration.ofMinutes(10)
);
```

The `set(key, value, Duration)` overload performs a value write with expiration, avoiding the `set(key, value)` followed by `expire(key, timeout)` pattern.

### 6.2. Creating only when absent

```java
Boolean created = redis.opsForValue().setIfAbsent(
    "idempotency:request-7",
    "IN_PROGRESS",
    Duration.ofMinutes(5)
);

if (Boolean.TRUE.equals(created)) {
    // This attempt created the key; proceed with the business protocol.
} else {
    // Key already exists, or immediate result is unavailable in special execution contexts.
}
```

`setIfAbsent(key, value, Duration)` uses semantics equivalent to `SET ... NX EX/PX` at the Redis level and performs **existence check + value write + TTL** in one operation. Inside a pipeline or transaction, many Spring Data Redis operations can return `null` because results are deferred; do not automatically equate `null` with "key already exists."

This idempotency-key snippet only illustrates **the single step of claiming a temporary key**. Ensuring a request never executes side effects twice also requires state conventions, timeout handling, completion markers, and idempotent business logic.

### 6.3. Updating only if the key exists and resetting TTL

```java
Boolean updated = redis.opsForValue().setIfPresent(
    "cache:product:sku-42",
    "{\"name\":\"New Keyboard\"}",
    Duration.ofMinutes(10)
);

if (Boolean.TRUE.equals(updated)) {
    // Value was updated and TTL was reset to the chosen Duration.
}
```

`setIfPresent(key, value, Duration)` corresponds to the `XX` condition: update only if the key exists. Do **not** use the overload without `Duration` if your intent is to refresh TTL, because a successful `SET` without a TTL can strip the existing TTL.

### 6.4. Setting TTL on an existing key

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

Boolean changed = redis.expire(
    "cache:product:sku-42",
    Duration.ofMinutes(10)
);

Long remainingSeconds = redis.getExpire(
    "cache:product:sku-42",
    TimeUnit.SECONDS
);

// remainingSeconds may be >= 0, -1, -2, or null in special execution contexts.
```

`redis.expire(key, duration)` can return:

- `true`: Redis applied the expiration change.
- `false`: for example, not applied because the key does not exist.
- `null` in certain deferred-result contexts.

For business logic, use `Boolean.TRUE.equals(changed)` if confirmation is needed. Do **not** treat `expire(...) == true` as a guarantee that the key will survive the full TTL: it can still be deleted, expire, be evicted, or be overwritten by another client afterward.

### 6.5. Removing TTL to keep a key long-term

```java
Boolean persisted = redis.persist("cache:product:sku-42");
```

`persist(key)` maps to `PERSIST key`, removing the expiration from an existing key. This differs from extending TTL. For sessions/OTPs/caches with mandatory expiration policies, calling `persist` unintentionally can cause serious retention bugs.

## 7. TTL policies on update: three common patterns

### 7.1. Fixed TTL from creation time

**Goal:** Data is valid for at most `T` from initial creation, even if its contents are updated.

Example: an OTP is valid for at most 2 minutes after issuance; failed verification attempts must not extend its lifetime.

```text
10:00:00   create OTP with 120s TTL
10:00:40   check OTP, do not reset TTL
10:01:20   update metadata, preserve remaining TTL
10:02:00   expires at original deadline
```

How to apply:

- Create Strings with `SET ... EX 120`.
- When a String must be modified while keeping its deadline, use `SET ... KEEPTTL` or a controlled storage strategy.
- If only updating a Redis Hash field with `HSET`, the existing hash's TTL normally continues counting down.
- If the system has an absolute deadline, use that timestamp as the source of truth and verify it in the application too.

Do not use `SET ... EX 120` on every edit if policy forbids **extension**. Validate initial state, update permissions, and race conditions.

### 7.2. Refresh TTL on write

**Goal:** Each successful application update extends the key's life by `T` from the update time.

Example: a computed cache is refreshed whenever a product changes.

```text
10:00:00  SET EX 600   → deadline around 10:10
10:06:00  SET EX 600   → deadline around 10:16
10:12:00  SET EX 600   → deadline around 10:22
```

In Spring:

```java
redis.opsForValue().set(key, newValue, Duration.ofMinutes(10));
```

Because this is a single Redis command, the new value and expiration are attached consistently for that write. However, it can **create a new key if the old one already expired**; when updates are allowed only on still-existing keys, use `setIfPresent(key, value, ttl)`.

### 7.3. Sliding expiration on read

**Goal:** Extend a key when accessed, such as extending a login session while the user remains active.

If you use:

```redis
GET session:user-42
EXPIRE session:user-42 1800
```

these are **two commands**. Between them, the key could expire, be deleted, or be updated by another client. `GET` could even find nothing, while another client creates a new key right before `EXPIRE`, causing `EXPIRE` to affect the new key.

Redis 6.2+ supports `GETEX` to **read a value and update its TTL in one command**:

```redis
GETEX session:user-42 EX 1800
```

If the key exists and is a Redis String, Redis returns the value and refreshes its expiration as requested. If the key does not exist, the command returns nil and does not create a key.

In Spring Data Redis, supported versions offer:

```java
String sessionData = redis.opsForValue().getAndExpire(
    "session:user-42",
    Duration.ofMinutes(30)
);
```

This API corresponds to reading and resetting expiration. Check your project's Spring Data Redis/Redis Server versions and actual serializer. Do **not** call `getAndExpire` when business rules require reading without extending.

Sliding expiration has a cost: every read that extends expiration is a **metadata write operation**, increasing state-mutating traffic and affecting replication/persistence depending on configuration. For very frequently accessed sessions, you may want a policy throttling refresh frequency, though batching refreshes means accepting coarser expiration-time accuracy.

### 7.4. Fixed absolute deadline

**Goal:** Never extend past a defined cutoff, such as a promotion ending at the end of the day. When all updates must share the same deadline, store/check that timestamp in the business layer and use `expireAt(key, instant)` or `SET ... EXAT/PXAT` where appropriate.

Spring example:

```java
import java.time.Instant;

Instant deadline = Instant.parse("2030-01-01T00:00:00Z");
Boolean applied = redis.expireAt("promo:campaign-7", deadline);
```

`expireAt` sets an absolute expiration on an existing key. If the application must **create a String with an absolute deadline in one step**, use Redis `SET EXAT/PXAT` options or a matching API/command path; `set()` followed by `expireAt()` remains two separate commands.

## 8. Redis Hash, List, Set, Sorted Set: data creation and TTL can be two commands

`StringRedisTemplate.opsForValue().set(key, value, Duration)` handles Redis Strings cleanly. For a new Hash:

```java
redis.opsForHash().put("cart:user-42", "itemCount", "3");
redis.expire("cart:user-42", Duration.ofMinutes(30));
```

`HSET` and `EXPIRE` are **two separate Redis operations**. If a crash happens between them, the Hash can be left behind with no TTL. The same applies when initializing a List with `LPUSH`, a Set with `SADD`, or a Sorted Set with `ZADD` before calling `EXPIRE`.

### 8.1. If the Hash already exists and has a TTL

```redis
HSET cart:user-42 itemCount "1"
EXPIRE cart:user-42 1800
HSET cart:user-42 itemCount "2"
TTL cart:user-42
# Retains previously set lifetime, does not auto-reset to 1800
```

`HSET` updates a field without proactively altering the hash's expiration. If policy requires **refreshing TTL on cart updates**, call `EXPIRE` after updating, or use a combined operation when atomicity is required.

### 8.2. Using a Lua script to write a Hash and TTL in one operation

When you must guarantee a Hash is updated together with its expiration, a Redis Lua script is one option:

```lua
-- KEYS[1] = Hash key
-- ARGV[1] = field
-- ARGV[2] = value
-- ARGV[3] = TTL in seconds, already validated > 0 by the application
redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
```

This script prevents **other client commands from interleaving between `HSET` and `EXPIRE`**. However, Redis Lua scripts do not provide relational-database-style rollback if a script partially executes and then errors. Validate inputs and key types, prepare exception handling, and do not deploy unvetted scripts to production.

Implementation in Spring Data Redis:

```java
import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class CartHashWriter {

    private static final String LUA = """
        redis.call('HSET', KEYS[1], ARGV[1], ARGV[2])
        return redis.call('EXPIRE', KEYS[1], tonumber(ARGV[3]))
        """;

    private final StringRedisTemplate redis;
    private final DefaultRedisScript<Long> script;

    public CartHashWriter(StringRedisTemplate redis) {
        this.redis = redis;
        this.script = new DefaultRedisScript<>();
        this.script.setScriptText(LUA);
        this.script.setResultType(Long.class);
    }

    public void writeWithTtl(
            String key,
            String field,
            String value,
            Duration ttl
    ) {
        if (ttl.isNegative() || ttl.isZero() || ttl.toSeconds() < 1) {
            throw new IllegalArgumentException("TTL must be >= 1 second");
        }

        Long result = redis.execute(
            script,
            List.of(key),
            field,
            value,
            Long.toString(ttl.toSeconds())
        );

        if (!Long.valueOf(1L).equals(result)) {
            throw new IllegalStateException("TTL could not be applied");
        }
    }
}
```

In this example, `StringRedisTemplate` encodes keys and arguments as strings; the script returns the integer result of `EXPIRE`. Using the same keys and serializer path is essential. When parameter counts, key types, or logic grow complex, package the script as a versioned component with dedicated integration tests.

### 8.3. Do Redis transactions solve everything?

Redis `MULTI`/`EXEC` can group commands, but it is not the default answer to every requirement:

- When logic depends on current data, you may also need `WATCH` or Lua/Redis Functions.
- Redis transactions do not offer RDBMS-style rollback if a command executes and triggers a runtime error.
- In Spring Data Redis, transaction configuration and connection binding must be understood properly; simply adding `@Transactional` does not automatically turn every Redis call into the desired transaction.
- For keys needing a value and TTL in one step, `SET EX/PX` is far simpler than wrapping `SET` and `EXPIRE` in a transaction.

For a Hash/List/ZSet key needing consistent update + TTL, a script expresses intent clearly, though performance and maintainability should be weighed.

## 9. Counters with TTL: avoiding missing expirations on creation

Redis is often used for rate-limit counters:

```redis
INCR rate-limit:user-42
EXPIRE rate-limit:user-42 60
```

These are two separate commands. If the application crashes between them, the counter can live forever. Furthermore, calling `EXPIRE key 60` **after every increment** resets the TTL on each request, producing behavior different from a "60-second window starting at the first request."

### 9.1. Distinguishing two strategies

| Strategy | How TTL is set | Behavior |
|---|---|---|
| Simple fixed window | Set TTL when the new counter is created | Expires roughly 60 seconds after counter creation |
| Refresh-on-increment | Set TTL after every increment | Counter expires if no further updates arrive for 60 seconds |

Neither strategy **equals** an exact sliding-window rate-limiting algorithm. For accurate business rate limiting, define the algorithm, bucket boundaries, concurrency limits, and distributed guarantees.

### 9.2. Lua: create/increment and attach TTL atomically

An illustrative script:

```lua
-- KEYS[1]: counter key
-- ARGV[1]: TTL in seconds > 0
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])
if count == 1 or ttl == -1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
```

Idea:

1. Increment the counter with `INCR`.
2. When the counter hits 1 or a key is detected **without a TTL**, set the expiration.
3. Subsequent increments keep the remaining expiration without extending the fixed window.

The `ttl == -1` check is a recovery guard for keys lacking a TTL (such as legacy data). It is not a complete definition of a production rate limiter. For calendar-aligned fixed windows, embed the time bucket in the key, compute TTL until the end of the bucket, and account for clock skew by design.

**Note:** Increment counts and state storage are only part of rate limiting. If a request was already processed upstream and retried, or if Redis failover loses recent updates per persistence settings, evaluate the required level of guarantee.

## 10. TTL in Spring Redis Cache

When using `@Cacheable` with `RedisCacheManager`, TTL is usually configured at the cache level:

```java
import java.time.Duration;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.cache.RedisCacheConfiguration;
import org.springframework.data.redis.cache.RedisCacheManager;
import org.springframework.data.redis.connection.RedisConnectionFactory;

@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public RedisCacheManager redisCacheManager(
            RedisConnectionFactory connectionFactory
    ) {
        RedisCacheConfiguration defaults =
            RedisCacheConfiguration.defaultCacheConfig()
                .entryTtl(Duration.ofMinutes(10))
                .computePrefixWith(name -> "shop:v1:cache:" + name + "::");

        return RedisCacheManager.builder(connectionFactory)
                .cacheDefaults(defaults)
                .build();
    }
}
```

When a cache entry is written through Redis Cache, the cache configuration determines its TTL. Keep in mind:

- A cache entry is Redis data stored under the cache key constructed by the CacheManager.
- When an entry is rewritten, the CacheManager may assign a fresh expiration per `entryTtl`; do not assume rewrites keep the old TTL.
- **`@Cacheable` cache hits** typically read the existing entry and **do not by default refresh TTL** in a sliding-expiration manner.
- If you want TTL to vary per entry or on reads, check the capabilities of your specific Spring Data Redis version (such as TTL functions or time-to-idle emulation in supported versions) and evaluate side effects.
- `RedisCacheManager` serializers and prefixes may differ from those used by a separate `RedisTemplate`.

### 10.1. Time-to-live and time-to-idle are not the same

| Concept | Expiration measured from |
|---|---|
| **TTL** | The latest write/expiration assignment per cache policy |
| **TTI (time to idle)** | The latest access, if the system implements refresh-on-read |

Some newer Spring Data Redis versions can emulate time-to-idle using commands like `GETEX`. However, if the application directly calls `RedisTemplate.opsForValue().get(...)` or Redis CLI on the same key, different read paths will not refresh idle timeouts uniformly. Standardize key ownership and cache read paths.

### 10.2. Should TTL be removed when a cache is refreshed?

If a cache is meant to retain entries for at most 10 minutes, another service calling `SET key value` without a TTL on the same physical key can turn the entry into a permanent key. Therefore:

- Do not directly overwrite raw keys managed by CacheManager without an explicit data and serializer contract.
- When updating cache entries, use `@CachePut` or the matching `Cache.put` API and let CacheManager manage TTL.
- With `@CacheEvict`, understand which keys are removed and how entries are repopulated.
- Never use `PERSIST` to "fix cache misses" when cached data is required by policy to expire.

## 11. TTL in Spring Data Redis Repositories

Redis Repositories support TTL metadata on entities mapped as Redis Hashes.

### 11.1. Fixed TTL at the entity class level

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;

@RedisHash(value = "sessions", timeToLive = 1800)
public class SessionRecord {
    @Id
    private String id;
    private String userId;

    public SessionRecord() {}

    public SessionRecord(String id, String userId) {
        this.id = id;
        this.userId = userId;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
}
```

`timeToLive = 1800` specifies a **1800-second** TTL for the stored aggregate. When the repository saves the entity, Spring Data Redis can set the expiration on the key holding the entity data based on the mapping metadata.

Example:

```java
SessionRecord saved = repository.save(
    new SessionRecord("session-42", "user-7")
);

// Default keyspace from annotation, e.g.:
// sessions:session-42
```

When calling `save` again, understand that repository persistence may **reset the TTL according to the entity configuration**. Do not treat repository `save` as "edit one field while preserving the old TTL" if business rules require a fixed deadline without verifying the mapping/update path.

### 11.2. Dynamic per-entity TTL with `@TimeToLive`

```java
import org.springframework.data.annotation.Id;
import org.springframework.data.redis.core.RedisHash;
import org.springframework.data.redis.core.TimeToLive;

@RedisHash("sessions")
public class SessionWithTtl {
    @Id
    private String id;

    private String userId;

    @TimeToLive
    private Long ttlSeconds;

    public SessionWithTtl() {}

    public SessionWithTtl(String id, String userId, Long ttlSeconds) {
        this.id = id;
        this.userId = userId;
        this.ttlSeconds = ttlSeconds;
    }

    public String getId() { return id; }
    public void setId(String id) { this.id = id; }
    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public Long getTtlSeconds() { return ttlSeconds; }
    public void setTtlSeconds(Long ttlSeconds) { this.ttlSeconds = ttlSeconds; }
}
```

With a `Long` numeric field, `ttlSeconds` represents seconds under the TTL mapping mechanism. When different entities need different TTLs, this metadata is more flexible than a fixed value on `@RedisHash`.

**Note on read-then-save:** The TTL value when a repository materializes an entity may reflect the key's **remaining time**, depending on mapping and configuration. If the application reuses that object and calls `save`, be explicit about whether you intend to keep the deadline or refresh TTL; avoid accidentally reapplying an original TTL value and extending the session.

### 11.3. Repositories may create auxiliary keys

Redis Repositories may manage ID sets, secondary indexes, and other keys tied to mapping or expiration. Setting a TTL on the aggregate **does not mean every auxiliary key shares the exact same TTL** or gets cleaned up the instant the key expires. Handling keyspace notifications and expiration events depends on listener setup and Redis operations.

If strict index synchronization or guaranteed retention-driven deletion is required, understand the repository model in use rather than relying solely on `TTL sessions:id`.

## 12. Changing TTL when updating only part of the data

In real systems, update operations typically fall into three cases:

### Case A — Updating an entire Redis String

The application may use:

```java
redis.opsForValue().set(key, newJson, Duration.ofMinutes(10));
```

This **overwrites the entire value and refreshes the TTL**. If you want to keep the remaining TTL, use Redis `SET ... KEEPTTL` via an appropriate API/command, or a designed atomic strategy. Never fall back to `set(key, value)`, because that drops the TTL.

### Case B — Updating a field in a Redis Hash

```java
redis.opsForHash().put(key, "status", "PAID");
```

If the Hash already has an expiration, the TTL keeps ticking down. If the Hash does not exist yet, the command can create a new Hash **without a TTL**.

When you want to refresh TTL on every update:

```java
redis.opsForHash().put(key, "status", "PAID");
redis.expire(key, Duration.ofDays(1));
```

These two commands are not atomic together. When a TTL invariant is mandatory, use a script or appropriate concurrent workflow.

### Case C — Updating a counter

```java
Long views = redis.opsForValue().increment("views:product:42");
```

`INCR` preserves the TTL attached to the key. However, if a new counter is created by `INCR`, the key will not automatically have a TTL. This differs from `SET ... EX` and is why time-window counters usually need a script or a bucketed key schema with explicitly managed expiration.

## 13. Concurrency issues and atomicity boundaries

### 13.1. Why isn't `GET` followed by `EXPIRE` atomic sliding expiration?

Example:

```text
Client A: GET session:42  → data found
Client B: DEL session:42
Client B: SET session:42 "different session"
Client A: EXPIRE session:42 1800
```

Client A ended up "refreshing the lifetime" of **the key created by B**, not necessarily the same session data it read. Using `GETEX` closes the gap between reading and changing TTL for a Redis String, though it **does not replace validating session identity or access rights**.

### 13.2. When multiple clients set TTL concurrently

Suppose:

```redis
EXPIRE shared:key 60
EXPIRE shared:key 600
```

If two clients send these commands sequentially, the final deadline depends on **which command Redis executes last**. There is no automatic rule that "shorter TTL always wins" or "longer TTL always wins."

When business rules require:

- **Never shorten an existing deadline:** consider `EXPIRE ... GT`.
- **Never extend past an existing deadline:** consider `EXPIRE ... LT`.
- **Set TTL only the first time:** consider `EXPIRE ... NX`.
- **Change only when a TTL already exists:** consider `EXPIRE ... XX`.

Conditional options must align with your Redis version and Spring Data Redis invocation style. They **do not automatically solve** all logical races when values change; comparing content or versions requires additional design.

### 13.3. Retries and ambiguous outcomes

On a network timeout, the client may not know whether Redis executed `SET EX` or `EXPIRE`. Retrying `SET ... EX 300` can **extend the TTL further** relative to the first command's deadline.

If a deadline must remain fixed:

- Compute an immutable deadline from the business event.
- Use an absolute timestamp or store the deadline alongside the data.
- Check ownership/version when multiple clients update the same key.
- Design retries to be idempotent toward the goal rather than assuming "re-running TTL setup" is always harmless.

## 14. Testing TTL on creation and update

Good tests verify not only return values but also **the expiration stored by Redis**.

### 14.1. Integration test example with `StringRedisTemplate`

The example below assumes a `@SpringBootTest` connected to a dedicated test Redis instance. Assertions avoid checking exact initial seconds because time elapses between commands.

```java
package com.example.redis.ttl;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.time.Duration;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;

@SpringBootTest
class RedisTtlIntegrationTest {

    private static final String KEY = "test:ttl:create-update";

    @Autowired
    StringRedisTemplate redis;

    @AfterEach
    void cleanup() {
        redis.delete(KEY);
    }

    @Test
    void setWithDurationCreatesExpiringKey() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 120);
    }

    @Test
    void plainSetRemovesOldExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.opsForValue().set(KEY, "v2");

        assertEquals("v2", redis.opsForValue().get(KEY));
        assertEquals(-1L, redis.getExpire(KEY, TimeUnit.SECONDS));
    }

    @Test
    void writingAgainWithDurationSetsExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.opsForValue().set(KEY, "v2", Duration.ofSeconds(180));

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 180);
        assertEquals("v2", redis.opsForValue().get(KEY));
    }

    @Test
    void hashUpdateKeepsExistingTtl() {
        redis.opsForHash().put(KEY, "name", "An");
        redis.expire(KEY, Duration.ofSeconds(120));
        redis.opsForHash().put(KEY, "city", "Hanoi");

        Long ttl = redis.getExpire(KEY, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0 && ttl <= 120);
    }

    @Test
    void persistRemovesExpiration() {
        redis.opsForValue().set(KEY, "v1", Duration.ofSeconds(120));
        redis.persist(KEY);
        assertEquals(-1L, redis.getExpire(KEY, TimeUnit.SECONDS));
    }
}
```

This is an **example of how to write tests**, not output from an executed test run. In a real project, tests need an isolated Redis instance, unique keys per test if run in parallel, and must never delete data in production Redis.

### 14.2. Additional cases to consider

| Situation | Expected behavior to verify |
|---|---|
| Create String with TTL | Key exists and `TTL > 0` |
| Create via `setIfAbsent` when missing | Both value and TTL are set |
| `setIfAbsent` when key already exists | Old value and TTL remain unchanged |
| `setIfPresent` when key has expired | Does not create a new key |
| Write using `SET` without TTL | Old expiration is cleared |
| Write using `SET KEEPTTL` | Old deadline continues |
| `HSET` into Hash with TTL | Old TTL keeps counting down |
| `HSET` creating a new Hash | Needs TTL-attaching mechanism if business requires it |
| `INCR` on counter with TTL | TTL is preserved |
| `INCR` creating a new counter | Key does not get an automatic TTL |
| `GETEX` | Returns data and refreshes TTL in one operation |
| `PERSIST` | Key remains but `TTL = -1` |
| Expired key | `TTL = -2` and read commands return no data |
| Redis eviction | Key may disappear before deadline |

If the application uses very short TTLs, verify with `PTTL` for millisecond resolution. Assertions still need tolerances for wall-clock drift, scheduling, and network overhead; avoid "must equal 1000 ms" checks that flake as time passes.

## 15. Observing and troubleshooting TTL in production

### 15.1. Diagnostic commands

In an environment with appropriate read permissions:

```redis
EXISTS cache:product:sku-42
TYPE cache:product:sku-42
TTL cache:product:sku-42
PTTL cache:product:sku-42

INFO stats
INFO memory
CONFIG GET maxmemory-policy
```

Be sure to distinguish:

- Key still exists with `TTL = -1`: there may be a `SET` path stripping TTL, or the key was created without a TTL.
- Key is gone (`TTL = -2`): may be due to expiration, eviction, manual deletion, or never having been created.
- `expired_keys` increasing: Redis has processed expired keys.
- `evicted_keys` increasing: keys were dropped due to memory policy. Do **not** blame every cache miss on TTL.
- Redis lacks expected `maxmemory`/eviction config: TTL and eviction are separate mechanisms and need targeted investigation.

On managed Redis services, some config/inspection commands may be restricted by permissions or provider policy; never modify production configuration just for exercises.

### 15.2. Common bugs by symptom

| Symptom | Likely cause | What to check |
|---|---|---|
| Cache keeps stale data forever | A `SET key value` stripped TTL, or key creation omitted TTL | Look for `TTL = -1`; trace all write paths |
| OTP lives longer than policy allows | Updates with `SET EX` extended the lifetime | Check fixed-deadline handling and retry rules |
| Session expires even while actively read | Only `GET` is used, no sliding TTL | Determine whether `GETEX` is needed |
| Session never expires under traffic | `GETEX` extends TTL on every single read | Check whether an absolute max age is required |
| Counter increments indefinitely without resetting | `INCR` created key without TTL or `EXPIRE` was missing | Inspect counter creation path and atomic script |
| Hash disappears mid-update | Old TTL was nearly up; `HSET` does not refresh TTL | Measure `PTTL` and review update policy |
| Cache disappears ahead of schedule | Eviction, deletion, failover, or other config | `INFO stats`, logs, metrics, topology |
| `expire(...)` returns false | Key no longer existed when setting TTL | Inspect key creation/change timing and races |
| Mass cache miss on every deploy | Prefix/schema version changed or cache was cleared | Compare keyspace and CacheManager config |
| New data has a different TTL than old data | Multiple APIs, serializers, or cache configs in use | Inspect the exact code path writing the key |

### 15.3. Do not abuse `KEYS *` to hunt down bad keys

On large Redis instances, `KEYS *` can degrade performance. If you must scan keys by namespace, use cursor-based `SCAN`, bound batch sizes, and keep in mind it is not a consistent snapshot; on Redis Cluster, account for node topology.

Counting keys by prefix in a single scan also does not prove every key has a TTL. Use sampling or proper instrumentation/observability to detect non-expiring keys in datasets that must expire.

## 16. Redis CLI lab: comparing update approaches

Run these steps only on a Redis instance dedicated to learning.

### Step 1 — Create a String with TTL from the start

```redis
DEL lab:ttl:string
SET lab:ttl:string "v1" EX 120
TTL lab:ttl:string
# Near 120
```

### Step 2 — Try an update that loses TTL

```redis
SET lab:ttl:string "v2"
TTL lab:ttl:string
# (integer) -1
```

This shows that **overwriting with `SET` without a TTL option** can turn a key into a non-expiring key.

### Step 3 — Reset expiration and preserve expiration

```redis
SET lab:ttl:string "v3" EX 120
SET lab:ttl:string "v4" KEEPTTL
TTL lab:ttl:string
# Continues counting down from EX 120, does not reset
```

### Step 4 — Explicitly refresh TTL on update

```redis
SET lab:ttl:string "v5" EX 300
TTL lab:ttl:string
# Near 300
```

### Step 5 — Try conditional creation/update

```redis
DEL lab:ttl:conditional

SET lab:ttl:conditional "first" EX 60 NX
# OK

SET lab:ttl:conditional "second" EX 60 NX
# nil / skipped because key already exists

GET lab:ttl:conditional
# "first"

SET lab:ttl:conditional "third" EX 90 XX
# OK

GET lab:ttl:conditional
# "third"

TTL lab:ttl:conditional
# Near 90
```

### Step 6 — Update a Hash and inspect TTL

```redis
DEL lab:ttl:hash
HSET lab:ttl:hash name "An"
EXPIRE lab:ttl:hash 120

HSET lab:ttl:hash city "Hanoi"
TTL lab:ttl:hash
# TTL remains; HSET does not reset it to 120
```

### Step 7 — Try `INCR` with expiration

```redis
DEL lab:ttl:counter
INCR lab:ttl:counter
TTL lab:ttl:counter
# -1 — key was created without TTL

EXPIRE lab:ttl:counter 60
INCR lab:ttl:counter
TTL lab:ttl:counter
# Retains TTL and keeps counting down
```

### Step 8 — Read and extend with `GETEX`

```redis
SET lab:ttl:session "active" EX 60
GETEX lab:ttl:session EX 180
# "active"

TTL lab:ttl:session
# Near 180
```

### Step 9 — Remove expiration and clean up test keys

```redis
PERSIST lab:ttl:string
TTL lab:ttl:string
# -1

DEL lab:ttl:string lab:ttl:conditional lab:ttl:hash lab:ttl:counter lab:ttl:session
```

Do not use `FLUSHDB` or `FLUSHALL` to clean up a handful of lab keys on a shared Redis server.

## 17. Principles for implementing TTL in applications

A reliable Spring Data Redis system typically defines **TTL policies per data type**, rather than letting individual controllers pick arbitrary timeouts.

| Data | Commonly suitable policy | Things to watch out for |
|---|---|---|
| Product cache | Relative TTL from write; optionally refresh on update | Reload from primary source on cache miss |
| OTP | Fixed TTL from issuance or absolute deadline | Do not extend on failed verification attempts |
| Session | Policy-driven TTL, optionally idle refresh plus absolute max age | Distinguish `GET` vs. `GETEX`; verify session validity |
| Idempotency key | Bounded TTL, conditional creation | Do not expire too early while side effects are still running |
| Rate-limit counter | Bucket/window-aligned TTL | Avoid non-atomic `INCR` then `EXPIRE` |
| Temporary lock | Conditional creation with TTL and owner token | TTL alone does not cover lock loss or overrun processing |
| Redis Hash cart | Key-level TTL with clear keep/refresh policy | `HSET` does not auto-refresh when editing fields |
| Redis Repository aggregate | TTL via `@RedisHash`/`@TimeToLive` | `save`, expiration events, and secondary indexes have specific behavior |

Key principles:

1. **Create Strings with TTL in one command** whenever possible: `SET EX/PX` or `opsForValue().set(key, value, Duration)`.
2. **Choose update behavior explicitly**: `SET` (clears TTL), `SET EX` (refreshes), `SET KEEPTTL` (keeps deadline).
3. **Do not forget new keys from structural commands**: `HSET`, `INCR`, `LPUSH`, and `ZADD` can create keys without TTLs.
4. **Do not confuse reading with extending**: `GET` only reads; `GETEX` can read and reset TTL.
5. **Use fixed deadlines when business requires them**: prevent retries or updates from extending lifetimes indefinitely.
6. **Control concurrency**: two separate commands leave a gap; use atomic APIs, scripts, or versioned protocols when needed.
7. **Verify actual TTLs**: `TTL`/`PTTL` return `-1` for non-expiring keys and `-2` for missing keys.
8. **Handle missing keys**: both expiration and eviction can cause cache misses; TTL is not a persistence guarantee.
9. **Stay consistent across all code paths**: Spring Cache, Repositories, Templates, and raw Redis commands may differ in storage and TTL handling.
10. **Never leave secrets or temporary keys immortal** due to error paths or writes missing a TTL.

## 18. Self-check questions

**1. How does `SET key value EX 60` differ from `SET key value`?**  
The first attaches a 60-second expiration alongside the value; the second writes a String without a TTL and, when replacing an existing expiring key, normally removes that expiration.

**2. Why can `SET` followed by `EXPIRE` cause a key to live longer than intended?**  
Because the application can crash between the two commands, leaving the key created while `EXPIRE` never runs.

**3. Does `SET key value KEEPTTL` guarantee a newly created key gets a TTL?**  
No. `KEEPTTL` only preserves an existing expiration; a brand-new key does not automatically receive a deadline.

**4. Does `HSET` on a Redis Hash with a TTL reset its TTL?**  
Normally no. It updates a field inside the Hash and the key's expiration keeps counting down.

**5. What is the TTL when `INCR` creates a missing key?**  
A key created by `INCR` normally has no automatic TTL, so `TTL` returns `-1` while the key exists.

**6. Every time a user opens a page, the session should live 30 more minutes; which Redis command reads a String and extends it in one operation?**  
`GETEX session:key EX 1800` or the matching Spring Data Redis API such as `getAndExpire(key, Duration.ofMinutes(30))` on supported versions.

**7. Why aren't `GET` followed by `EXPIRE` completely equivalent to `GETEX`?**  
Two separate commands allow another client to modify or delete the key in between; `GETEX` combines reading and updating expiration in one Redis command.

**8. How do `TTL = -1` and `TTL = -2` differ?**  
`-1`: the key exists without an expiration. `-2`: the key does not exist, whether because it expired or was never created.

**9. When updating with `SET ... EX 300` while 20 seconds remain on the old TTL, what happens?**  
If the write succeeds, the expiration is reset to roughly 300 seconds from the update; the old 20 seconds are not kept.

**10. Does a Redis Cache hit reset TTL by default?**  
Do not assume so. Spring Cache TTL normally runs from when the entry was written; sliding/TTI behavior requires dedicated mechanisms and version support.

**11. How do you set a TTL only if a key currently has no expiration?**  
Redis 7+ offers `EXPIRE key seconds NX`; verify your server version and appropriate Spring Data Redis invocation.

**12. With `@RedisHash(timeToLive=600)` on a Redis Repository, does calling `save` again guarantee keeping the original deadline?**  
Do not assume that. A repository may rewrite and apply TTL from metadata on save; inspect the mapping path and check fixed-deadline vs. refresh-on-save behavior.

**13. Why does setting a 10-minute TTL not guarantee a cache stays alive for 10 minutes?**  
Redis can evict keys early under memory pressure, or another task can delete the key.

**14. What is the `PERSIST` command for?**  
Removing the expiration from an existing key so it no longer automatically expires via its previous TTL.

**15. If two services update the same key's TTL to 60 seconds and 600 seconds respectively, does Redis automatically keep the shorter TTL?**  
No. By default the final expiration depends on command execution order. To enforce only lengthening or shortening deadlines, consider Redis's `GT`/`LT` options where supported.

### Conclusion

Configuring TTL properly is more than dropping `EXPIRE` somewhere in code. You must decide **whether a key expires from creation**, **whether updates keep or reset the deadline**, and **whether reads extend it**. With Spring Data Redis, prefer single-operation `Duration` write APIs for Redis Strings, understand `SET` versus `HSET`/`INCR` semantics, and use atomic coordination when compound structures require writing before attaching a TTL. By standardizing policies per data type and verifying actual `TTL`/`PTTL` behavior, your application avoids both "immortal" keys and unexpected premature expirations.
