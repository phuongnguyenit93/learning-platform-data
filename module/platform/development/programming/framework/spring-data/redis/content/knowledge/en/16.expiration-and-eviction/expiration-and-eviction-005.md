# How Write Commands Affect Existing TTLs in Spring Data Redis

## 1. The problem: does overwriting data lose its lifetime?

Suppose an application stores a verification code in Redis and requires it to expire automatically after two minutes:

```redis
SET otp:user:42 "123456" EX 120
```

After 30 seconds, the application realizes the code must be changed and executes:

```redis
SET otp:user:42 "654321"
```

The value changed, yet **the expiration was also cleared**. A plain `SET` command replaces the key's value and leaves the key without a TTL, even though an expiration had been attached previously. If an application focuses only on the new data and overlooks expiration attributes, the verification code can live longer than policy permits.

Knowing accurately how each category of write command affects TTL is essential when implementing caches, sessions, shopping carts, OTPs, rate-limit counters, or temporary data with **Spring Data Redis**.

Learning outcomes from this lesson:

- Distinguish **replacing an entire value**, **modifying existing contents**, **changing expiration timestamps**, and **deleting keys**.
- Predict TTL after common Redis commands and corresponding `RedisTemplate` / `StringRedisTemplate` APIs.
- Choose the right write approach to **clear TTL**, **set a new TTL**, **preserve the existing expiration**, or **extend it intentionally**.
- Recognize real-world bugs when combining writes with `EXPIRE`, when keys have already expired, or when multiple clients write concurrently.

## 2. TTL is a property of the key, not of the value string

**TTL (Time To Live)** is the remaining duration before Redis considers a key expired. Redis stores the expiration timestamp attached to the **key**; TTL is not a field embedded inside a String, Hash, List, Set, or Sorted Set value. Once that timestamp passes, the key is treated as nonexistent and may be removed via active or passive expiration.

Two common inspection commands:

```redis
TTL cache:product:42
PTTL cache:product:42
```

| Result | Meaning |
|---|---|
| `TTL` returns non-negative integer | Remaining **seconds** of TTL, at second resolution. |
| `PTTL` returns non-negative integer | Remaining **milliseconds** of TTL. |
| `-1` | Key exists but has **no expiration timestamp**. |
| `-2` | Key **does not exist** (including when already expired). |

Example:

```text
> SET cache:product:42 "A" EX 120
OK
> TTL cache:product:42
(integer) 120
> PTTL cache:product:42
(integer) 119980
```

Actual TTL values count down over time; numbers in examples are illustrative. If `PTTL` drops from 90,000 to 89,000 milliseconds after a write command, that **does not mean the write reset the TTL**. First verify whether TTL is continuing to count down toward the old deadline or was refreshed to a different duration.

A key can have an unlimited lifetime with respect to TTL, yet that **does not guarantee the key always exists**: manual deletion, memory-pressure eviction, or Redis administration can still remove the key. TTL and eviction are two separate mechanisms.

## 3. Core Redis rules

Redis distinguishes between **overwriting/replacing a key's value** and **modifying content inside an existing value**.

1. **Replacing the entire value:** normally **clears the old TTL**. Examples: `SET` without expiration options, `GETSET`, `MSET`, and commands writing results into a destination key such as `SUNIONSTORE`.
2. **Modifying part of an existing value:** normally **preserves the old expiration timestamp**. Examples: `INCR`, `APPEND`, `HSET`, `LPUSH`, `SADD`, `ZADD`.
3. **Specifying expiration in the write command itself:** TTL is **replaced with the new deadline**, unless the command explicitly requests `KEEPTTL`.
4. **Operating directly on expiration:** `EXPIRE` / `PEXPIRE` set or update expiration; `PERSIST` removes expiration; `DEL` / `UNLINK` delete the key.

These rules follow the **semantics of the actual Redis command sent**, not whether a Java method name contains `set`, `update`, or `save`. A single application-layer method can emit different underlying Redis commands.

### Quick reference table

| Redis command | Effect on key with existing TTL | Notes |
|---|---|---|
| `SET key value` | **Clears TTL** | Value is replaced completely. |
| `SET key value EX 60`, `PX 60000` | **Sets new TTL** | Replaces both value and expiration in one command. |
| `SET key value KEEPTTL` | **Keeps old expiration** | Does not restart the TTL clock. |
| `SET ... NX` / `SET ... XX` | Depends on whether the command **succeeds** | If the condition fails, key and TTL stay unchanged; if it succeeds, `SET` and its expiration options apply. |
| `GETSET`, `MSET` | **Clears TTL** of overwritten keys | Value-replacing commands. |
| `INCR`, `DECR`, `INCRBY`, `APPEND`, `SETRANGE`, `SETBIT` | **Keeps TTL** | Modifies an existing String value. |
| `HSET`, `HINCRBY`, `HDEL` | **Keeps TTL**, if key still exists | Deleting the last field can cause the entire Hash to vanish. |
| `LPUSH`, `RPUSH`, `LSET`, `LTRIM` | **Keeps TTL**, if List still exists | Operations leaving the List empty can delete the key. |
| `SADD`, `SREM`, `ZADD`, `ZREM`, `XADD` | **Keeps TTL**, if key still exists | Modifies an existing data structure. |
| `SUNIONSTORE`, `ZUNIONSTORE`, `SORT ... STORE` | **Clears old TTL** of destination key | Output overwrites the destination key. |
| `EXPIRE`, `PEXPIRE`, `EXPIREAT`, `PEXPIREAT` | **Sets/updates expiration** | Can alter TTL without touching the value. |
| `PERSIST` | **Clears TTL** | Key stays, unless already gone. |
| `GETEX key EX 60` / `GETEX key PERSIST` | **Changes TTL** / **clears TTL** | Despite starting with GET, this can mutate state. |
| `DEL`, `UNLINK`, `GETDEL` | **Deletes key** | Subsequent TTL queries return `-2`. |
| `RENAME source destination` | Destination key **inherits source's TTL** | If destination already existed, both its value and old TTL are replaced. |

**Easy pitfall:** `HSET` updating a field does **not** reset the lifetime of the entire Hash; conversely, `SET` writing a new String normally **loses the TTL**, even if the new String has identical content to the old String.

## 4. Full overwrites: TTL disappears unless specified

### 4.1. Plain `SET`

```text
> SET session:42 "draft" EX 90
OK
> TTL session:42
(integer) 90
> SET session:42 "confirmed"
OK
> TTL session:42
(integer) -1
> GET session:42
"confirmed"
```

`TTL = -1` here means the key **still exists**, yet it no longer expires automatically per the old deadline. Redis does not remember the original number of seconds to reapply on the next `SET`.

`GETSET` (read old value and set new value) likewise replaces the whole value and clears TTL. Similarly, `MSET` writes multiple key/value pairs and clears prior TTLs on overwritten keys. Newer Redis releases may add extra commands by version, though you must not extrapolate `SET` options onto bulk write commands.

### 4.2. Success or failure of the write determines the outcome

`SET` supports conditions:

- `NX`: write only if the key does not exist.
- `XX`: write only if the key already exists.

Example with an existing key:

```text
> SET lock:42 "owner-A" EX 60
OK
> SET lock:42 "owner-B" NX
(nil)
> TTL lock:42
(integer) 58
> SET lock:42 "owner-B" XX
OK
> TTL lock:42
(integer) -1
```

`NX` failed so neither value nor TTL changed; `XX` succeeded, overwriting the value and clearing TTL because no expiration option was attached. Similarly, `MSETNX` failing when any key exists leaves all keys in the batch untouched.

In Spring Data Redis, `opsForValue().setIfAbsent(key, value)` is often used for locks or markers. If you want the new key to expire, use the variant accepting a `Duration`; creating keys without an expiration can leave data around longer than expected.

## 5. Setting a new deadline vs. keeping the old deadline when writing Strings

To solve replacing a value while controlling TTL, pick **one of three intents**.

### 5.1. Replace value and initialize a fresh TTL

```text
> SET otp:user:42 "123456" EX 120
OK
> SET otp:user:42 "654321" EX 120
OK
> TTL otp:user:42
(integer) 120
```

`EX` takes seconds, `PX` takes milliseconds; `EXAT` and `PXAT` take absolute Unix timestamps (seconds/milliseconds). Writing the value and setting expiration inside **the same `SET` command** is atomic on Redis.

This fits when a fresh record has an independent lifecycle—for instance, each new OTP may remain valid for up to two minutes from issuance.

### 5.2. Replace value while preserving the old deadline

```text
> SET ticket:42 "issued" EX 120
OK
> SET ticket:42 "used" KEEPTTL
OK
> TTL ticket:42
(integer) 110
```

`KEEPTTL` preserves the **remaining expiration time** rather than resetting a 120-second span. It is useful when a token, session, or cart must still end at its established deadline even when its status updates.

Redis has supported `SET ... KEEPTTL` since Redis 6.0. If the key does not exist or already expired before `SET` runs, there is no prior TTL to preserve: the new key is created without an expiration unless another expiration option is set. Thus, if business logic requires "only update an existing key and keep its TTL," consider `SET ... XX KEEPTTL`.

### 5.3. Replace value and intentionally clear TTL

```redis
SET feature:banner "permanent"
```

This is the right choice when promoting a key from temporary data to long-lived data. The key point is that **the intent to drop TTL must be explicit**; never arrive here accidentally when merely updating a status field.

## 6. In-place edits: TTL keeps counting down

Commands acting on the contents inside a key generally leave the deadline untouched. Redis treats them as **updating an existing value**, not replacing the entire key.

### 6.1. String used as a counter

```text
> SET rate:user:42 "0" EX 60
OK
> INCR rate:user:42
(integer) 1
> INCRBY rate:user:42 2
(integer) 3
> TTL rate:user:42
(integer) 57
```

`INCR` / `INCRBY` increment the value while keeping the initial deadline. Consequently, if the counter represents a fixed time window, each access **does not automatically extend the window**. `DECR`, `APPEND`, `SETRANGE`, and `SETBIT` also fall into this TTL-preserving content-edit group.

If the counter **expired before `INCR` ran**, Redis treats the key as missing, initializes a new value, and **does not attach any TTL** to the new key. That is why a rate-limiting algorithm must enforce setting the expiration when initializing a counter rather than assuming a previous TTL still exists.

### 6.2. Hash: updating fields does not reset the Hash's TTL

```text
> HSET cart:42 item:1 2
(integer) 1
> EXPIRE cart:42 300
(integer) 1
> HSET cart:42 item:2 1
(integer) 1
> HINCRBY cart:42 item:1 1
(integer) 3
> TTL cart:42
(integer) 295
```

TTL belongs to **`cart:42`**, not to `item:1` or `item:2` individually. Each `HSET` / `HINCRBY` does not extend the whole cart. Deleting a field with `HDEL` also keeps the key's expiration if other fields remain; deleting the final field can remove the key, making `TTL` return `-2`.

Likewise, operations on Lists, Sets, Sorted Sets, and Streams generally preserve TTL when modifying elements in an existing structure. If an operation leaves the key empty (such as removing the last element of a Set), no key remains to hold a TTL.

### 6.3. Comparing two representations of the same business entity

A shopping cart stored as a **JSON String**:

```text
SET cart:42 "{\"item1\":2}" EX 300
SET cart:42 "{\"item1\":3}"             # Old TTL cleared
```

A shopping cart stored as a **Redis Hash**:

```text
HSET cart:42 item1 2
EXPIRE cart:42 300
HSET cart:42 item1 3                    # TTL continues counting down
```

It is not that Redis "favors" Hashes; it is the difference between `SET` replacing a monolithic value and `HSET` editing a field inside an existing structure. When choosing a data model, account for the expiration behavior of your **planned update commands**.

## 7. Commands that modify TTL directly

### 7.1. `EXPIRE` can extend or shorten

```text
> SET cart:42 "content" EX 300
OK
> EXPIRE cart:42 30
(integer) 1
> TTL cart:42
(integer) 30
```

`EXPIRE` sets a new duration **from when the command executes**, rather than adding to the remaining time. Similarly, `PEXPIRE` works in milliseconds, and `EXPIREAT` / `PEXPIREAT` set absolute deadlines.

`EXPIRE` also supports conditions (Redis 7.0+):

| Option | Condition to apply expiration |
|---|---|
| `NX` | Key currently has no expiration. |
| `XX` | Key currently has an expiration. |
| `GT` | New deadline is later than current deadline. |
| `LT` | New deadline is earlier than current deadline. |

With `GT`, a key without a TTL counts as having an infinite deadline, so `GT` cannot assign a finite TTL to it. With `LT`, a key without a TTL counts as having an infinite deadline, so a shorter deadline can be attached. Conditional options help avoid unintended lengthening or shortening under concurrent traffic.

Setting `EXPIRE` / `PEXPIRE` with a non-positive duration, or `EXPIREAT` / `PEXPIREAT` in the past, causes Redis to **delete the key immediately**. Subsequent status is `TTL = -2`.

### 7.2. `PERSIST` removes expiration while keeping value

```text
> SET notice:42 "temporary" EX 60
OK
> PERSIST notice:42
(integer) 1
> TTL notice:42
(integer) -1
```

Do not confuse `PERSIST` with `DEL`: `PERSIST` only deletes expiration metadata; `DEL` deletes the key itself.

### 7.3. Commands starting with GET can still change TTL

Standard `GET` and `MGET` do not alter TTL. However:

- `GETEX key EX 30`: reads the value and sets a fresh 30-second TTL.
- `GETEX key PERSIST`: reads the value and removes TTL.
- `GETEX key` with no options: reads without altering TTL.
- `GETDEL key`: reads and then deletes the key.

When building **sliding expiration** (extending lifetime on each access), explicitly use `GETEX ... EX` or a matching mechanism. Plain `GET` alone never extends lifetime.

## 8. Writing to destination keys and renaming keys

### 8.1. `*STORE` commands with a separate destination key

```text
> SET result:42 "old" EX 60
OK
> SADD group:A alice bob
(integer) 2
> SADD group:B bob carol
(integer) 2
> SUNIONSTORE result:42 group:A group:B
(integer) 3
> TTL result:42
(integer) -1
```

`SUNIONSTORE` writes the resulting Set into `result:42`, replacing its value and discarding the destination key's old TTL. Similar commands such as `ZUNIONSTORE`, `SINTERSTORE`, and `SORT ... STORE` should be viewed as **writing a brand-new result to the destination key**, not editing elements in place.

### 8.2. `RENAME` carries over the source's TTL

```text
> SET temp:42 "A" EX 120
OK
> RENAME temp:42 active:42
OK
> TTL temp:42
(integer) -2
> TTL active:42
(integer) 115
```

The new key `active:42` receives both the value **and the expiration** from `temp:42`. If `active:42` already existed, its old TTL is not kept; the source key's attributes replace the destination's. If the source had no TTL, the destination after `RENAME` has no TTL either.

This is why workflows that "stage temporary data and promote it to official" must verify whether renaming aligns with lifetime requirements.

## 9. Impact through Spring Data Redis APIs

`StringRedisTemplate` is convenient when both key and value are Strings; `RedisTemplate<K, V>` behaves similarly with its configured serializers. Ultimately, TTL behavior always follows the Redis command emitted by the operation.

| Java call | Typical Redis command | Effect on existing TTL |
|---|---|---|
| `opsForValue().set(key, value)` | `SET` | Clears TTL. |
| `opsForValue().set(key, value, Duration.ofMinutes(5))` | `SET` with expiration | Resets TTL to five minutes. |
| `opsForValue().setIfAbsent(key, value, Duration.ofSeconds(30))` | `SET ... NX` with expiration | Creates key with TTL on success; existing key unchanged. |
| `opsForValue().setIfPresent(key, value)` | `SET ... XX` | On success, overwrites and clears TTL. |
| `opsForValue().getAndSet(key, value)` | `GETSET` or equivalent `SET GET` | Overwrites and clears TTL. |
| `opsForValue().multiSet(values)` | `MSET` | Clears old TTL on written keys. |
| `opsForValue().increment(key)` | `INCR` | Keeps TTL if key exists. |
| `opsForValue().set(key, value, offset)` | `SETRANGE` | Keeps TTL if key exists; **differs from `set(key, value)`**. |
| `opsForHash().put(key, field, value)` | `HSET` | Keeps Hash TTL if key exists. |
| `opsForList().rightPush(key, value)` | `RPUSH` | Keeps List TTL if key exists. |
| `expire(key, Duration.ofSeconds(30))` | `EXPIRE` / `PEXPIRE` | Replaces deadline. |
| `persist(key)` | `PERSIST` | Removes expiration. |
| `delete(key)` | `DEL` | Deletes key. |
| `rename(source, destination)` | `RENAME` | Transfers TTL from source to destination. |

### 9.1. Java service illustrating different intents

The example below uses Spring Boot and `spring-boot-starter-data-redis`, with `StringRedisTemplate` injected into the bean:

```java
import java.time.Duration;
import java.util.concurrent.TimeUnit;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ExpiringKeyService {

    private final StringRedisTemplate redis;

    public ExpiringKeyService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    // Replace entire value and clear prior TTL.
    public void replaceWithoutTtl(String key, String value) {
        redis.opsForValue().set(key, value);
    }

    // Replace value and restart a 5-minute lifetime.
    public void replaceWithFreshTtl(String key, String value) {
        redis.opsForValue().set(key, value, Duration.ofMinutes(5));
    }

    // Create only if missing; attach TTL immediately on success.
    public boolean createIfAbsent(String key, String value) {
        return Boolean.TRUE.equals(
            redis.opsForValue().setIfAbsent(
                key, value, Duration.ofSeconds(30)
            )
        );
    }

    // Write Hash field without changing existing Hash TTL.
    public void updateCartField(String key, String field, String quantity) {
        redis.opsForHash().put(key, field, quantity);
    }

    // Increment existing counter, preserving its current TTL.
    public Long incrementCounter(String key) {
        return redis.opsForValue().increment(key);
    }

    // Only when explicitly wanting to extend lifetime.
    public boolean refreshTtl(String key, Duration ttl) {
        return Boolean.TRUE.equals(redis.expire(key, ttl));
    }

    // Distinguish -2 (missing), -1 (no TTL), >=0 (remaining time).
    public Long remainingMillis(String key) {
        return redis.getExpire(key, TimeUnit.MILLISECONDS);
    }

    public boolean removeExpiration(String key) {
        return Boolean.TRUE.equals(redis.persist(key));
    }
}
```

In this example, `getExpire` returns `Long`, which can be `null` in pipelines or transactions per the Spring Data Redis contract. Never force-unbox to `long` or treat `null` as "does not exist" when using those mechanisms.

### 9.2. Keeping old TTL when replacing a full String via low-level connections

In Spring Data Redis 3.x, when `SET ... KEEPTTL` is needed, you can use `RedisCallback` and `RedisStringCommands`. The example below assumes keys and values are UTF-8 encoded, matching `StringRedisTemplate`'s default setup:

```java
import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.RedisStringCommands;
import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.types.Expiration;

public class KeepTtlWriter {

    private final StringRedisTemplate redis;

    public KeepTtlWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Boolean replaceAndKeepTtl(String key, String value) {
        byte[] keyBytes = key.getBytes(StandardCharsets.UTF_8);
        byte[] valueBytes = value.getBytes(StandardCharsets.UTF_8);

        return redis.execute((RedisCallback<Boolean>) connection ->
            connection.stringCommands().set(
                keyBytes,
                valueBytes,
                Expiration.keepTtl(),
                RedisStringCommands.SetOption.upsert()
            )
        );
    }
}
```

This issues **a single atomic `SET` command with `KEEPTTL`**, avoiding the race window of reading TTL, writing the value, and reapplying expiration across separate commands. The Redis server must support `KEEPTTL` (Redis 6.0+). With custom serializers, use the template's actual serializer instead of hardcoding `StandardCharsets.UTF_8`; otherwise key/value bytes may not match previously stored data. On other Spring Data Redis versions, check the exact API since low-level command surfaces may vary.

If business logic wants **to update only an existing key**, replace `SetOption.upsert()` with `SetOption.ifPresent()` to apply `XX` together with `KEEPTTL`; if the key vanishes before execution, the command will not recreate a key without an expiration.

### 9.3. Do not infer Redis Repository behavior from `HSET`

Object-mapped repositories (such as `@RedisHash`, `@TimeToLive`) may issue multiple writes, update secondary indexes, or re-apply expirations depending on configuration and version. Thus, you cannot assume `repository.save(entity)` always preserves TTL merely because the entity is stored as a Hash. When exact expiration semantics are required, understand the repository's mapping behavior or use Redis operations with explicit TTL semantics.

## 10. Two common expiration policies

### 10.1. Fixed expiration: fixed deadline from creation

Example: a shopping cart expires 15 minutes from creation. Updating item quantities must not extend the deadline:

```java
String key = "cart:42";

// Initialize and set initial TTL.
redis.opsForHash().put(key, "item:101", "1");
redis.expire(key, Duration.ofMinutes(15));

// Subsequent changes do not call expire().
redis.opsForHash().put(key, "item:101", "2");
redis.opsForHash().put(key, "item:102", "1");
```

In this simplified snippet, initial setup uses **two separate commands**; if the app fails in between, the key can remain without a TTL. Real systems must close that gap, such as via a Lua script or transaction when creation and TTL attachment must happen as a unit.

### 10.2. Sliding expiration: extended from latest activity

Example: a session expires after 15 minutes of **inactivity**. Updating a Hash with `HSET` is **not enough** to extend TTL. The application must explicitly renew it:

```java
String key = "session:42";
redis.opsForHash().put(key, "lastAction", "view-cart");
redis.expire(key, Duration.ofMinutes(15));
```

Policy comparison:

| Aspect | Fixed expiration | Sliding expiration |
|---|---|---|
| Updating value | Old deadline stays intact | Deadline is actively extended |
| Suitable operations | `HSET`, `INCR`, or `SET KEEPTTL` | Write with fresh TTL, `EXPIRE`, or combined operation |
| Risk if misimplemented | Key lifetime stretches beyond policy | Key expires despite active user traffic |

When ensuring "only extend if the key still exists" under concurrent requests, account for the key expiring between commands, or wrap conditional checks in a Lua script.

## 11. Common pitfalls when updating data with TTL

### Pitfall 1: `SET` then `EXPIRE` in two commands to create a cache

```java
redis.opsForValue().set(key, value);
redis.expire(key, Duration.ofMinutes(5));
```

If the application crashes or the second command fails, the key remains without a TTL. Cleaner when a fresh TTL is desired is **writing value and TTL in the same command**:

```java
redis.opsForValue().set(key, value, Duration.ofMinutes(5));
```

### Pitfall 2: Reading TTL, overwriting, and reapplying "remaining seconds"

```java
Long ttl = redis.getExpire(key);
redis.opsForValue().set(key, newValue);
if (ttl != null && ttl > 0) {
    redis.expire(key, Duration.ofSeconds(ttl));
}
```

This is not equivalent to `KEEPTTL`. TTL already ticked down between commands; the key could expire or be altered by another client; reapplying the old TTL can **shift the deadline**. Moreover, handling `ttl = -1` or `-2` here is very error-prone.

When you want to preserve an existing key's exact deadline, prefer `SET ... XX KEEPTTL` instead of reconstructing expiration from a read value.

### Pitfall 3: Assuming increment operations always have a TTL, even on new keys

`INCR` keeps the TTL of an **existing key**, but when the key is missing or expired, creating a new counter produces **no TTL**. In a one-minute rate-limit window, this pair risks leaving a permanent key if the process crashes midway:

```text
INCR rate:user:42
EXPIRE rate:user:42 60
```

A Lua script can make initializing and setting expiration atomic:

```lua
-- KEYS[1]: counter name; ARGV[1]: TTL in milliseconds, e.g. "60000"
local count = redis.call('INCR', KEYS[1])
if count == 1 then
    redis.call('PEXPIRE', KEYS[1], tonumber(ARGV[1]))
end
return count
```

This script illustrates a window starting on the first access when the counter is absent; if an older release may have left **existing counters without TTLs**, apply a dedicated remediation policy for legacy keys. Do not assume this script alone repairs pre-existing corrupted Redis keys.

### Pitfall 4: Accidentally extending TTL on every field edit

`HSET` itself preserves the deadline. Calling `EXPIRE key 900` after every cart update turns a 15-minute-from-creation policy into 15-minute-from-last-edit. Whether that is right or wrong depends on business rules; the extension comes from the **extra `EXPIRE` command**, not from `HSET`.

### Pitfall 5: Confusing `-1` with `-2`

A key overwritten with `SET` normally still exists and `TTL` returns `-1`. When deleted or expired, Redis returns `-2`. In Java, distinguish these two states clearly, especially when handling cache misses, key reallocation, and temporary-data metrics.

### Pitfall 6: Looking only at method names while ignoring underlying commands

A service method named `updateSession` might call `opsForValue().set` or `opsForHash().put`; the two have opposite TTL effects. Code calling `repository.save` may also emit commands beyond a direct `HSET`. When a key "suddenly stops expiring," find **the last Redis command that wrote to the key** and classify it using the table in Section 3.

## 12. Checking TTL behavior with redis-cli

You can reproduce each operation group on isolated test keys:

```text
# 1. Replacing full value strips TTL
SET demo:ttl:string "v1" EX 120
TTL demo:ttl:string
SET demo:ttl:string "v2"
TTL demo:ttl:string
# Final TTL: -1

# 2. Writing with KEEPTTL preserves running deadline
SET demo:ttl:keep "v1" EX 120
SET demo:ttl:keep "v2" KEEPTTL
PTTL demo:ttl:keep
# PTTL stays positive and is not reset to 120000 ms

# 3. Operating on Hash keeps TTL
HSET demo:ttl:hash field1 "A"
EXPIRE demo:ttl:hash 120
HSET demo:ttl:hash field2 "B"
TTL demo:ttl:hash
# TTL stays positive; keeps counting down

# 4. Removing expiration while keeping value
PERSIST demo:ttl:hash
TTL demo:ttl:hash
# -1

# 5. Deleting key and checking TTL
DEL demo:ttl:hash
TTL demo:ttl:hash
# -2
```

Lines starting with `#` are documentation comments; when running interactively in redis-cli, run only the Redis command lines. TTL can reach `-2` if you pause longer than the test duration.

When investigating real incidents, a useful sequence is: identify the **affected key**, capture `PTTL` before/after the operation in a controlled environment, trace the **actual Redis commands** emitted, and compare against the intended expiration policy. Never run `KEYS *` on production Redis just to find keys; use known key names or an appropriate scan mechanism.

## 13. Self-check reasoning scenario

Suppose at the start, keys are created as follows:

```redis
SET a "10" EX 100
SET b "hello" EX 100
HSET c field1 "x"
EXPIRE c 100
```

Then the application executes in sequence:

| Command | Expected result on TTL |
|---|---|
| `INCR a` | `a` keeps its TTL; does not reset to 100 seconds. |
| `SET a "11"` | `a` has `TTL = -1`. |
| `SET b "world" KEEPTTL` | `b` keeps counting down toward its old deadline. |
| `HSET c field2 "y"` | `c` keeps its TTL. |
| `EXPIRE c 200` | `c` gets a fresh TTL of roughly 200 seconds. |
| `PERSIST c` | `c` still exists but `TTL = -1`. |
| `DEL b` | `b` no longer exists, `TTL = -2`. |

Execution timing and command order may alter exact second counts, yet the **state category** (expiring, non-expiring, missing key) must match command semantics.

## 14. Design checklist to get it right

Whenever writing or updating a Redis write operation, answer three questions:

1. **Does the operation replace the entire key value?** If so, check the prior TTL; plain `SET` will clear it.
2. **Is the desired deadline from creation, from last update, or an absolute cutoff?** Choose `KEEPTTL`, fresh TTL, or conditional expiration accordingly.
3. **Can crashes or concurrent updates happen between commands?** When atomicity is needed, prefer a single command supporting expiration directly or use Lua/transactions appropriately.

The most practical rule of thumb: **full-value `SET` normally clears TTL; in-place edits normally keep TTL; `EXPIRE` changes the deadline; `KEEPTTL` preserves the old deadline.** Always verify against the actual commands Spring Data Redis sends and your data lifecycle policy.

## References

- [Redis – EXPIRE: conditions, clearing TTL on overwrite, and RENAME behavior](https://redis.io/docs/latest/commands/expire/)
- [Redis – SET: EX/PX/EXAT/PXAT, NX/XX, and KEEPTTL](https://redis.io/docs/latest/commands/set/)
- [Redis – GETEX: reading and modifying expiration together](https://redis.io/docs/latest/commands/getex/)
- [Spring Data Redis 3.3 – ValueOperations API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/ValueOperations.html)
- [Spring Data Redis 3.3 – RedisStringCommands API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/connection/RedisStringCommands.html)
- [Spring Data Redis 3.3 – Expiration.keepTtl() API](https://docs.spring.io/spring-data/redis/docs/3.3.7/api/org/springframework/data/redis/core/types/Expiration.html)
