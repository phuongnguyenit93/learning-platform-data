# Incrementing, Decrementing, and Controlling Counter Data Types in Spring Data Redis

Redis is well suited for managing **counters** that need fast updates: article view counts, request counts in a time window, login attempts, pending jobs, or completed task totals. Spring Data Redis lets you perform these operations through `StringRedisTemplate` and `ValueOperations` without writing raw Redis protocol handling yourself.

However, a proper counter is more than "read a number and add 1". A real-world system also has to address **the stored Redis data type, atomicity when multiple requests update concurrently, non-negative/maximum bounds, TTL, key scope, integer overflow, and discrepancies on connection failures**. This lesson focuses on those decisions, starting from basic commands and progressing to scenarios that safeguard correctness.

Code snippets use Java 17+, Spring Boot 3.x, Spring Data Redis 3.x, and a standard Redis server. The `StringRedisTemplate` API concepts apply broadly, though configuration properties and dependencies must match your active Spring Boot version.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain why an integer counter in Redis is usually a **Redis String containing an integer representation**, not a separate Redis type named `integer`.
2. Use `INCR`, `DECR`, `INCRBY`, `DECRBY`, and their corresponding Spring Data Redis APIs.
3. Understand what happens if a key **does not exist yet**, its value **is not an integer**, the key holds a **non-String data type**, or an arithmetic operation **exceeds 64-bit integer limits**.
4. Distinguish **atomic increments/decrements on Redis** from read-modify-write patterns prone to race conditions.
5. Design namespaces and serializers so multiple services do not accidentally overwrite counters with JSON or Java binary serialization.
6. Handle TTL for short-lived counters and know when to use an atomic operation combining increment and expiration.
7. Enforce rules such as non-negativity, maximum quotas, and request deduplication according to business needs.
8. Distinguish observability/cache counters from metrics requiring durable storage, auditing, or database consistency.

## 2. How Does Redis Actually Store Counters?

In Redis, a standard integer counter uses a **key of the Redis String type**; its value holds a digit string that Redis's integer commands read and update.

~~~redis
SET demo:counter:views "12"
TYPE demo:counter:views
GET demo:counter:views
INCR demo:counter:views
GET demo:counter:views
~~~

Key outputs:

~~~text
TYPE  -> string
GET   -> "12"
INCR  -> (integer) 13
GET   -> "13"
~~~

`TYPE` returns `string` even when the application treats the value as numeric. `INCR` requires the **content of the String** to be a valid integer; Redis does not store it as a Java `Long` field.

### 2.1. Each Key Has One Redis Data Type

Redis supports String, Hash, List, Set, Sorted Set, Stream, and more. A key that is currently a Hash cannot use `INCR` like a String:

~~~redis
HSET demo:user:42 name "Lan"
INCR demo:user:42
~~~

Redis returns an error similar to:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

To increment an **integer field inside a Redis Hash**, use `HINCRBY` instead of `INCR`:

~~~redis
HSET demo:article:42 views 10
HINCRBY demo:article:42 views 1
HGET demo:article:42 views
~~~

`HINCRBY` can increment or decrement a field by an integer; a missing field is treated as 0. It is an **atomic operation for the specified Hash field**, useful when grouping multiple fields of one entity into a single Hash. This lesson mainly covers String counters, though knowing the Hash option prevents picking the wrong API.

### 2.2. Integer Strings vs. JSON Containing a Number

Comparison:

| Redis Data | Usable Directly with `INCR`? | Explanation |
| --- | --- | --- |
| `"42"` | Yes | String holding a valid integer representation |
| `"-4"` | Yes | Negative integers are also supported |
| `"0"` | Yes | Zero is valid |
| `"42.0"` | No | Not an integer format accepted by `INCR` |
| `"{\"count\":42}"` | No | This is JSON text, not a standalone integer |
| `"42 views"` | No | Contains characters outside an integer representation |
| Redis Hash containing field `views=42` | No | Key has type Hash; use `HINCRBY` |
| Value written by JDK serializer | Typically no | Bytes are Java serialization, not a numeric string Redis can parse |

Once you choose a String counter, ensure **every writer** sharing that key follows the integer format. A service accidentally executing `SET key {"count":42}` will break subsequent increments.

## 3. Basic Redis Commands: INCR, DECR, INCRBY, DECRBY

### 3.1. `INCR`: Increment by 1

~~~redis
DEL demo:counter:signup
INCR demo:counter:signup
INCR demo:counter:signup
GET demo:counter:signup
~~~

For a **non-existent** key, Redis treats the initial value as 0 before incrementing, so the first `INCR` returns 1 and creates the key. The second returns 2.

### 3.2. `DECR`: Decrement by 1

~~~redis
SET demo:counter:stock 5
DECR demo:counter:stock
GET demo:counter:stock
~~~

The value after `DECR` is 4. If the key does not exist yet:

~~~redis
DEL demo:counter:test-decr
DECR demo:counter:test-decr
~~~

The result is **-1**. Redis does not automatically enforce a "counters cannot be negative" rule. If business rules forbid negative numbers, build protection into the Redis operation layer.

### 3.3. `INCRBY`: Increment by Multiple Units

~~~redis
SET demo:counter:downloads 10
INCRBY demo:counter:downloads 5
GET demo:counter:downloads
~~~

The result is 15. For a non-existent key, `INCRBY key 5` returns 5.

### 3.4. `DECRBY`: Decrement by Multiple Units

~~~redis
SET demo:counter:queue 25
DECRBY demo:counter:queue 7
GET demo:counter:queue
~~~

The result is 18. For a non-existent key, `DECRBY key 7` creates the value -7.

### 3.5. Behavior Summary Table

| Command | Value Before | Result After | Notes |
| --- | ---: | ---: | --- |
| `INCR k` | key missing | 1 | Treats initial value as 0 |
| `INCR k` | 10 | 11 | Increments by 1 |
| `DECR k` | key missing | -1 | Can produce negative numbers |
| `DECR k` | 10 | 9 | Decrements by 1 |
| `INCRBY k 4` | key missing | 4 | Increments by delta |
| `INCRBY k 4` | 10 | 14 | Integer delta |
| `DECRBY k 4` | key missing | -4 | Decrements starting from 0 |
| `DECRBY k 4` | 10 | 6 | Integer delta |

Increment/decrement commands return the **post-update value**. Do not confuse them with APIs that return the value *before* modification, such as `GETSET`/`getAndSet(...)`.

## 4. Why Are Atomic Increment/Decrement Operations Necessary?

Suppose a counter starts at 5. Two requests A and B increment concurrently:

~~~text
Error-prone approach: GET -> add in Java -> SET

Request A: GET => 5
Request B: GET => 5
Request A: SET 6
Request B: SET 6

Final result: 6
Correct value after two increments: 7
~~~

This is a **lost update**, a form of race condition. Adding `synchronized` in a single Java instance is not enough either if the system runs multiple processes or replicas.

Using `INCR`:

~~~text
Redis processes INCR from A: 5 -> 6
Redis processes INCR from B: 6 -> 7

Final result: 7
~~~

Redis performs the increment/decrement on the key atomically at the command level. Concurrent requests cannot interleave another update inside a single `INCR` command.

**Important limitation:** single-command atomicity **does not** turn a sequence of multiple commands into a transaction. For instance, `INCR key` followed by `EXPIRE key 60` is **two operations**; failures, disconnections, or commands from other clients can occur in between. When multi-step guarantees are required, use an appropriate primitive such as a Lua script, transaction, or a single Redis command that already satisfies the requirement.

## 5. Incrementing/Decrementing with StringRedisTemplate in Spring Data Redis

### 5.1. Preparing the Application

In a Spring Boot project with appropriate dependency version management, add:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-redis</artifactId>
</dependency>
~~~

Run Redis locally:

~~~bash
docker run --name redis-counter-lab -p 127.0.0.1:6379:6379 -d redis:7
docker exec -it redis-counter-lab redis-cli PING
~~~

Expected output from `PING` is `PONG`. If port 6379 is already in use, pick another host port and update the configuration. The example container binds to loopback for practice; never expose unauthenticated Redis to the Internet.

`application.yml` (Spring Boot 3.x):

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
~~~

When the application and Redis run in two containers under Docker Compose, the connection host is usually the **Redis service name**, not the application container's `localhost`. In production environments, also configure ACL/password/TLS, network restrictions, and appropriate timeouts.

### 5.2. Why Prefer StringRedisTemplate?

`StringRedisTemplate` uses String serializers by default for both keys and values. Redis counters store integer representations as text; writing `"10"` and then calling `INCR` avoids Java binary serialization conflicts.

Example service:

~~~java
package com.example.redis;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class CounterService {

    private final StringRedisTemplate redis;

    public CounterService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long increment(String key) {
        Long value = redis.opsForValue().increment(key);
        return requireResult(value);
    }

    public long decrement(String key) {
        Long value = redis.opsForValue().decrement(key);
        return requireResult(value);
    }

    public long incrementBy(String key, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        Long value = redis.opsForValue().increment(key, amount);
        return requireResult(value);
    }

    public long decrementBy(String key, long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("Amount must be positive");
        }
        Long value = redis.opsForValue().decrement(key, amount);
        return requireResult(value);
    }

    private long requireResult(Long value) {
        if (value == null) {
            throw new IllegalStateException(
                    "Redis did not return a counter result");
        }
        return value;
    }
}
~~~

This service demonstrates the four core APIs:

| Spring Data Redis | Corresponding Redis Command | Typical Return Value |
| --- | --- | --- |
| `opsForValue().increment(key)` | `INCR key` | New `Long` |
| `opsForValue().decrement(key)` | `DECR key` | New `Long` |
| `opsForValue().increment(key, amount)` | `INCRBY key amount` | New `Long` |
| `opsForValue().decrement(key, amount)` | `DECRBY key amount` | New `Long` |

When called directly on the template, these APIs return `Long`. In special contexts like pipelines/transactions, intermediate calls may return `null` because results are collected or processed later. The example assumes direct synchronous execution and throws if no result is returned; never omit null checks when the return type is `Long`.

### 5.3. Querying and Initializing Counter Values

You can read the raw value via:

~~~java
String raw = redis.opsForValue().get("shop:article:42:views");
~~~

For a non-existent key, `raw` is typically `null`; for a key containing a valid number, it is e.g. `"15"`. To convert to `long`:

~~~java
public long readCounter(String key) {
    String value = redis.opsForValue().get(key);
    if (value == null) {
        return 0L; // Business convention: missing key equals 0.
    }
    return Long.parseLong(value);
}
~~~

This method sits inside a service with field `redis`. If the current value does not represent a valid integer or exceeds `long` bounds, `Long.parseLong(...)` throws an exception. For critical data, do not catch every parse error and silently return 0, as that can hide schema issues or a misbehaving writer.

When simply incrementing from 0, **there is no need to call `SET key 0` beforehand**: `INCR` already handles non-existent keys. Pre-initialization makes sense only if you need a TTL from preparation time or a custom key creation rule.

### 5.4. Formatting Keys by Business Domain

Never accept arbitrary keys from user input and pass them straight to Redis. The service should construct keys from validated namespaces and IDs:

~~~java
public long recordArticleView(long articleId) {
    if (articleId <= 0) {
        throw new IllegalArgumentException("Invalid article ID");
    }
    String key = "shop:article:" + articleId + ":views";
    return increment(key);
}
~~~

Example structured keys:

~~~text
shop:article:42:views
shop:article:43:views
shop:product:42:views
shop:quota:user-17:2026-11-12
~~~

Keys should distinguish entity, feature, tenant, or time period when business logic requires it. Avoid putting tokens, passwords, or unnecessary personal data into key names since key names are frequently visible in admin tools and logs.

## 6. Controlling Counter Data Types

This is a common source of bugs: Java declares one type, while the Redis value is governed by the **serializer**.

### 6.1. RedisTemplate<K, V> Does Not Automatically Turn Long into a Numeric String

The following code can mislead developers:

~~~java
RedisTemplate<String, Long> template = new RedisTemplate<>();
template.setConnectionFactory(redisConnectionFactory);
~~~

The type parameter `Long` **does not guarantee** Redis stores the value as text `"42"`. If the template uses `JdkSerializationRedisSerializer`, the value consists of binary bytes; `INCR` then fails to parse it as an integer.

For clear counter operations, prefer:

~~~java
StringRedisTemplate redis = ...;
redis.opsForValue().set("demo:counter", "42");
redis.opsForValue().increment("demo:counter");
~~~

Alternatively, configure a template with a specific serializer suitable for Java types, such as `GenericToStringSerializer<Long>` for `Long` values when a `RedisTemplate<String, Long>` is needed. Choose that only with good reason; for simple counters, `StringRedisTemplate` is easy to inspect and coordinate across clients.

### 6.2. Do Not Mix Serializers on the Same Key

Suppose service A uses `StringRedisTemplate`:

~~~java
redis.opsForValue().set("demo:counter:views", "10");
~~~

Service B uses a template storing JSON:

~~~json
{"views":10}
~~~

If B writes JSON into the **exact same key** `demo:counter:views`, service A's `increment(...)` call will fail. Both the JSON object and `"10"` are Redis Strings, so `TYPE key` only reports `string` and **does not prove the value is incrementable**.

Good conventions:

1. Each namespace has **one data format contract**.
2. Integer counters use integer-formatted Strings with the same charset/serializer across all writers.
3. JSON DTOs use separate keys, such as `shop:article:42:detail`.
4. Redis Hash counters use `HINCRBY` or `HashOperations.increment(...)` accordingly.
5. When changing serializers, handle old keys and roll out explicit versions/prefixes instead of overwriting blindly.

### 6.3. Errors from Non-Integer Values

~~~redis
SET demo:bad-counter "12.5"
INCR demo:bad-counter
~~~

The error looks like:

~~~text
ERR value is not an integer or out of range
~~~

Likewise, `"abc"`, JSON, oversized numbers, or incompatible binary bytes all cause integer increment/decrement commands to fail.

**Do not catch the error and automatically delete the key to retry** if the key holds critical business data. First identify the writer, schema, serializer, and key role. For regenerable caches or temporary counters, apply a pre-agreed recovery policy.

## 7. 64-Bit Limits and Overflow

Redis integer increment/decrement commands operate on **signed 64-bit integers**. The corresponding valid range is:

\[
-2^{63} \leq n \leq 2^{63}-1
\]

That is, from **-9,223,372,036,854,775,808** to **9,223,372,036,854,775,807**. Java's `long` has the exact same range.

Testing with the maximum value:

~~~redis
SET demo:counter:max 9223372036854775807
INCR demo:counter:max
~~~

Redis rejects an increment that would overflow instead of silently wrapping around to negative numbers. Similarly, `DECR` on the minimum value also goes out of range.

### 7.1. Applications Must Decide How to Handle Overflow

Depending on business logic:

- View counters may persist periodic aggregates to a database and start a new key/window.
- Quota counters have limits far below `Long.MAX_VALUE`, so quotas should be checked before incrementing.
- If counts truly exceed 64 bits, a different data model or algorithm is required; switching the Java type to `BigInteger` will not make `INCR` support it.

Both Redis and Java return errors when a result cannot be represented. Do not switch to `double` simply to dodge integer limits, as that loses precision.

## 8. Floating-Point Counters and INCRBYFLOAT

Redis has `INCRBYFLOAT` to increment a String storing a decimal number:

~~~redis
SET demo:score "1.5"
INCRBYFLOAT demo:score 0.25
GET demo:score
~~~

The result is a string representing 1.75. In Spring Data Redis:

~~~java
Double value = stringRedisTemplate.opsForValue()
        .increment("demo:score", 0.25d);
~~~

**This is not integer addition.** If you later run `INCR demo:score` on a decimal value, Redis reports "not an integer". Therefore, separate namespaces for integer counters and floating-point accumulators:

~~~text
demo:counter:orders       # integer -> INCR / INCRBY
demo:score:rolling        # floating-point -> INCRBYFLOAT
~~~

### 8.1. When Should You Avoid INCRBYFLOAT?

Do not use binary floating-point numbers by default for **money, account balances, payment limits, or transactions requiring exact precision**. Even though Redis handles decimal representation for this command, converting through Java's `double` and representation/rounding differences can cause business discrepancies.

When the smallest unit is fixed (e.g., VND, cents, integer points), **convert to integers** and use `INCRBY` when 64-bit bounds suffice. For financial data requiring exactness, auditing, and transactions, choose an appropriate data store and business design; a standalone Redis counter does not replace a ledger.

## 9. TTL: How Long Should a Counter Live?

Not every counter needs to persist forever:

| Need | Suggested Lifecycle | What Must Be Decided |
| --- | --- | --- |
| All-time total views | May have no TTL, but needs persistence/sync if important | Is Redis the source of truth? |
| Requests per minute | Window-based TTL or time-stamped key structure | Fixed window, sliding window, or token bucket? |
| OTP attempts | Short TTL tied to protection window | Must it reset after success? |
| Currently running tasks | Tied to job lifecycle, with cleanup/timeout | Will the counter drift if a worker crashes? |
| Temporary dashboard counter | TTL of hours or days | Is there a fallback source when the key expires? |

Redis supports:

~~~redis
SET demo:attempts:42 0 EX 60
INCR demo:attempts:42
TTL demo:attempts:42
PTTL demo:attempts:42
~~~

`TTL` returns remaining seconds; `PTTL` returns remaining milliseconds. Special values:

- `-1`: key exists but **has no expiration**.
- `-2`: key **does not exist**.
- Non-negative value: remaining time in the command's unit.

For a key with an existing TTL, `INCR`/`DECR` normally **do not remove the existing TTL**; they update the value while preserving the deadline. Conversely, a plain `SET key value` command removes the old TTL unless an appropriate expiration-preserving option is used. Avoid accidentally calling `set(key, "0")` for periodic resets when you intend to preserve TTL.

### 9.1. Two Commands (Increment Then Set TTL) Leave a Gap

Easy-to-write example:

~~~java
String key = "demo:attempts:user-42";
redis.opsForValue().increment(key);
redis.expire(key, Duration.ofMinutes(5));
~~~

However, two problems arise:

1. If the process fails **after `INCR` but before `EXPIRE`**, the key can persist indefinitely.
2. Every `expire(...)` call **resets the TTL**; that gives a "5 minutes since the last update" lifetime, no longer "5 minutes from the first increment".

These two strategies have different semantics:

~~~text
Fixed lifetime from first event:
  attempt 1 -> TTL 5 minutes
  attempt 2 -> TTL 4 minutes left, not reset
  attempt 3 -> TTL 2 minutes left, not reset

Sliding idle timeout:
  attempt 1 -> TTL 5 minutes
  attempt 2 -> TTL resets to 5 minutes
  attempt 3 -> TTL resets to 5 minutes
~~~

Pick the right one according to business logic before writing code. When incrementing and setting TTL must obey an **atomic** rule, use a suitable command or Lua script.

## 10. Atomic Increment and TTL Setup with Lua

Redis executes a Lua script as an atomic operation on the server. The example below targets a **short-lived counter namespace** that needs to:

- Increment the value by 1.
- If the key has no TTL yet, set the TTL once.
- If the key already has a TTL, keep the current expiration.

Script:

~~~lua
local count = redis.call('INCR', KEYS[1])
local ttl = redis.call('TTL', KEYS[1])

if ttl == -1 then
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
end

return count
~~~

After `INCR`, the key definitely exists if no error occurred. Thus `TTL == -1` means no expiration was set yet, and the script sets it. Subsequent increments keep the active TTL unless another writer intentionally clears expiration. **Use this script only on namespaces where every counter is allowed to have a TTL**, because it will also attach a TTL to any existing key that previously had no expiration.

### 10.1. Creating a RedisScript Bean in Spring

~~~java
package com.example.redis;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration(proxyBeanMethods = false)
public class CounterScriptConfig {

    @Bean
    RedisScript<Long> incrementWithTtlScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
            local count = redis.call('INCR', KEYS[1])
            if redis.call('TTL', KEYS[1]) == -1 then
                redis.call('EXPIRE', KEYS[1], tonumber(ARGV[1]))
            end
            return count
            """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

### 10.2. Calling the Script from a Service

~~~java
package com.example.redis;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ExpiringCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementWithTtlScript;

    public ExpiringCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementWithTtlScript) {
        this.redis = redis;
        this.incrementWithTtlScript = incrementWithTtlScript;
    }

    public long increaseOnceAndStartTtl(String key, Duration ttl) {
        if (ttl == null || ttl.getSeconds() < 1) {
            throw new IllegalArgumentException("TTL must be at least 1 second");
        }

        Long result = redis.execute(
                incrementWithTtlScript,
                List.of(key),
                Long.toString(ttl.getSeconds())
        );
        if (result == null) {
            throw new IllegalStateException("Missing script result");
        }
        return result;
    }
}
~~~

The code uses `StringRedisTemplate` to serialize the key and script argument as Strings; the script receives the key via `KEYS[1]` and the TTL via `ARGV[1]`. Incrementing and setting TTL execute in **one Redis script execution**, eliminating the gap between two independent commands.

**Do not turn scripts into a place for long, complex business logic**: scripts run on Redis and can stall other commands if they occupy CPU too long. Short scripts operating on few keys with bounded runtime are the right fit.

### 10.3. TTL Is Still Not a Durability Guarantee

TTL determines when a key expires, not that Redis guarantees keeping the key across all failure modes. If Redis performs eviction due to memory pressure, keys may vanish early depending on `maxmemory-policy`; without proper persistence/replication, data can be lost on server crashes. Financial or auditable counters must have dedicated durable storage designs.

## 11. Non-Negative Counters: Why Is DECR Not Enough?

Suppose Redis holds an inventory count of 1, and two purchase requests run concurrently:

~~~text
Request A: GET stock -> 1
Request B: GET stock -> 1
Request A: sees stock available -> DECR -> 0
Request B: sees stock available -> DECR -> -1
~~~

`DECR` itself is atomic, yet the **condition "decrement only if stock remains"** lies outside the command, leaving a race condition. Checking with `GET` before `DECR` does not enforce the rule.

This can be solved with a Lua script checking and decrementing in one operation:

~~~lua
local current = redis.call('GET', KEYS[1])
if not current then
    return -1
end

local count = tonumber(current)
if not count then
    return redis.error_reply('counter must be numeric')
end

if count <= 0 then
    return -1
end

return redis.call('DECR', KEYS[1])
~~~

In this example:

- Returning `-1` signals **not decremented** because the key is missing or already at 0.
- Only when the key holds a valid numeric value greater than 0 does the script run `DECR`.
- The script prevents another command from interleaving between the check and the decrement on the Redis server.
- This is solely a **small-range non-negative counter** pattern. For real order inventory, you must also account for idempotency, payment, order cancellation, the database as source of truth, and post-failure reconciliation.

**Lua precision note:** traditional Redis Lua uses double-precision numbers for many `tonumber(...)` expressions. For very large counters near signed 64-bit bounds, do not rely on Lua double comparisons as an exact guard; design smaller business limits, validate ranges, or use a primitive supporting exact 64-bit integer comparisons.

## 12. Counters with Maximum Limits: You Cannot Just GET Then INCR

Suppose each user is allowed at most 3 attempts in a window. Error-prone code:

~~~java
long current = readCounter(key);
if (current < 3) {
    increment(key);
}
~~~

Two requests can both read 2, both see it is below 3, and both increment, yielding 4.

For small quotas, you can check and increment atomically with Lua:

~~~lua
local currentRaw = redis.call('GET', KEYS[1])
local current = 0

if currentRaw then
    current = tonumber(currentRaw)
    if not current then
        return redis.error_reply('counter must be numeric')
    end
end

local maximum = tonumber(ARGV[1])
if not maximum or maximum < 1 then
    return redis.error_reply('invalid maximum')
end

if current >= maximum then
    return -1
end

return redis.call('INCR', KEYS[1])
~~~

With `ARGV[1] = "3"`, the script returns 1, 2, 3 for successful increments and -1 when rejected. When both a maximum limit **and a window TTL** are required, extend the script to set expiration according to business rules.

### 12.1. A Simple Counter Is Not a Complete Rate Limiting Algorithm

A key-and-TTL limit can implement a **fixed-window** policy, but it has caveats:

- Bursts straddling a window boundary can exceed the intended short-term rate.
- You must define whether windows align to calendar boundaries (minute/hour) or start from the first request.
- Keying must be based on user/token/IP/tenant and trustworthy access attributes.
- You may need request deduplication and protection across multiple application instances.
- When Redis is disrupted, choose fail-open or fail-closed according to feature and risk.

Sliding-window log, sliding-window counter, token bucket, and leaky bucket each have distinct requirements. A Redis counter is a building block for them; it does not turn a single `INCR` into a rate limiter with every desired property.

## 13. Balances and Inventory: Distinguishing Atomic Operations from Business Transactions

An application might use Redis to count available product stock, held tickets, or active jobs. However, `DECR` atomicity does not enforce broader multi-step invariants:

~~~text
1. User places an order
2. Redis DECR inventory
3. Database INSERT order
4. System calls payment gateway
~~~

If step 3 or 4 fails, Redis already decremented inventory while the order was never recorded or completed. If the client loses the response at step 2, a retry may decrement again. You need a business design covering compensation, state machines, idempotency, source-of-truth transactions, or reconciliation.

In many systems, **the database is the authoritative inventory source**, while Redis assists with fast access or TTL-bound holds. Choose the source of truth based on consistency requirements, not speed alone.

### 13.1. Do Not Use Counters as the Sole Decision Maker for Auditable Cases

Event counters for dashboards may tolerate small drift depending on the product; monetary balances or ticket sales require stricter rules. Redis `INCR` prevents lost updates on a single key, yet does not provide transaction receipts, change logs, reconciliation, or exactly-once guarantees.

## 14. On Request Timeouts: An Increment May Have Already Happened

Suppose the application calls:

~~~java
redis.opsForValue().increment("shop:article:42:views");
~~~

Redis executes it successfully, yet the network fails before Java receives the response. The application sees a timeout and does not know **whether the command ran or not**.

If the client automatically retries:

~~~text
First command: Redis INCR 100 -> 101, response lost
Retry:         Redis INCR 101 -> 102, response received

One business request, yet the counter incremented twice.
~~~

**Atomicity does not mean idempotency**:

- Atomic: each `INCR` executes completely on Redis without interleaving.
- Idempotent: reprocessing the same request does not change the business outcome a second time.

To accurately count events requiring deduplication, use an **event/request ID** and verify the ID is processed only once, via a suitable Redis command/script or durable storage. Performing a `SET NX` dedup check and an `INCR` separately still leaves a gap if Redis or the process fails between them; when enforcing inside Redis, combine them atomically. Guarantees spanning both Redis and a database require deeper design.

For approximate metrics like page views, products can often tolerate minor drift. For payments, regulatory quotas, or auditable events, never casually accept duplicate counting.

## 15. Resetting and Reading Counters: Avoid Two Non-Atomic Commands

If you want to retrieve the current value and reset to 0, an error-prone pattern is:

~~~java
String current = redis.opsForValue().get(key);
redis.opsForValue().set(key, "0");
~~~

Between `GET` and `SET`, another request might call `INCR`; that increment is lost when setting 0.

Redis provides `GETSET`, exposed by Spring Data Redis via:

~~~java
String previous = redis.opsForValue().getAndSet(key, "0");
~~~

`getAndSet(...)` returns the **value before the change** and writes the new value as an atomic operation. For a non-existent key, the old value is typically `null`. However, a `SET`/`GETSET` write can affect the key's TTL; when resetting a counter with TTL, decide explicitly how to preserve or re-apply expiration.

Another approach is reading and deleting in one operation:

~~~java
String previous = redis.opsForValue().getAndDelete(key);
~~~

On Redis and Spring Data Redis versions supporting `GETDEL`, this command atomically retrieves the old value and deletes the key. The next `INCR` on the deleted key starts from 1. Consider time-bucketed keys or event logs if aggregate counts must never be lost during resets.

### 15.1. Rolling Window Counters via Time-Bucketed Keys

An approach often simpler than resetting a single key:

~~~text
shop:article:42:views:2026-11-12
shop:article:42:views:2026-11-13
shop:article:42:views:2026-11-14
~~~

Each day has its own key with a TTL long enough for aggregation. There is no need to reset a shared key right at midnight. Standardize the window timezone (e.g., UTC or business timezone) and handle late-arriving events.

## 16. When to Use INCRBYFLOAT, HINCRBY, or INCR in Spring?

| Problem | Redis Data Structure | Command | Spring Data Redis |
| --- | --- | --- | --- |
| Count integer requests/views | String holding integer | `INCR` | `StringRedisTemplate.opsForValue().increment(key)` |
| Increment in batches | String holding integer | `INCRBY` | `opsForValue().increment(key, long)` |
| Decrement quantity | String holding integer | `DECR`/`DECRBY` | `opsForValue().decrement(...)` |
| Increment a decimal value | String holding float | `INCRBYFLOAT` | `opsForValue().increment(key, double)` |
| Increment field in Hash | Hash holding integer field | `HINCRBY` | `opsForHash().increment(key, hashKey, long)` |
| Increment float field in Hash | Hash holding float field | `HINCRBYFLOAT` | `opsForHash().increment(key, hashKey, double)` |
| Conditional non-negative / max count | String/Hash | Lua script or suitable transaction | `RedisTemplate.execute(RedisScript, ...)` |

Note that the `increment(key, long)` and `increment(key, double)` overloads have different meanings. Example:

~~~java
redis.opsForValue().increment("demo:counter", 2L);   // INCRBY 2
redis.opsForValue().increment("demo:score", 2.0d);    // INCRBYFLOAT 2.0
~~~

Even though delta `2.0d` looks like a whole number, overload resolution follows the **Java type**, not the displayed value. Avoid accidentally turning an integer counter into a float.

## 17. Testing Critical Scenarios

Unit tests can verify that a service constructs the right keys and invokes expected template methods. However, behaviors like atomic increments, Redis TTL, and WRONGTYPE errors require **integration tests against a real Redis** (local Redis/Testcontainers).

### 17.1. Minimum Test Scenarios

1. **Missing key:** first `INCR` returns 1.
2. **Repeated increments:** call 1,000 times; final count reflects the exact number of successful operations.
3. **Decrement from 0:** `DECR` produces -1; compare against business rules on blocking negative values.
4. **Delta updates:** `INCRBY 5` from 10 gives 15; `DECRBY 3` gives 12.
5. **Invalid value format:** key containing `"12.5"` or JSON causes `INCR` to fail.
6. **Wrong Redis type:** Redis Hash at the same key causes `INCR` to return WRONGTYPE.
7. **Overflow:** incrementing from `Long.MAX_VALUE` fails.
8. **TTL:** `INCR` keeps current TTL; increment-with-TTL script does not reset TTL on later calls.
9. **Concurrency:** multiple threads concurrently calling `INCR` on one key yield the exact total of successful commands.
10. **Timeout/retry:** document or simulate uncertain execution outcomes and apply retry policies per business requirements.

### 17.2. Example JUnit Integration Test

This is a conceptual example assuming a real Redis configured for the test profile; in your project ensure an isolated test namespace and Spring Boot Test dependencies:

~~~java
@SpringBootTest
class CounterServiceIntegrationTest {

    @Autowired
    CounterService counterService;

    @Autowired
    StringRedisTemplate redis;

    @Test
    void incrementsMissingKeyFromZero() {
        String key = "test:counter:missing";
        redis.delete(key);

        assertEquals(1L, counterService.increment(key));
        assertEquals(2L, counterService.increment(key));
        assertEquals("2", redis.opsForValue().get(key));
    }

    @Test
    void preservesExpirationWhenIncrementing() {
        String key = "test:counter:ttl";
        redis.opsForValue().set(key, "0", Duration.ofMinutes(1));

        counterService.increment(key);

        Long ttl = redis.getExpire(key, TimeUnit.SECONDS);
        assertNotNull(ttl);
        assertTrue(ttl > 0);
    }
}
~~~

Add the JUnit 5 imports (`@Test`, `assertEquals`, `assertNotNull`, `assertTrue`), Spring Test imports (`@SpringBootTest`, `@Autowired`), `Duration`, `TimeUnit`, and corresponding application classes. The second test only asserts TTL remains positive afterward, avoiding exact second checks because execution timing varies. In real test suites, use randomized keys, a test database, or a dedicated container, and clean up test keys cleanly.

**Do not write tests assuming pipelined increments return Long immediately**; the API can defer results until the pipeline executes. Match tests to the execution context.

## 18. Inspecting Counters with Redis CLI

When investigating anomalous values:

~~~redis
TYPE shop:article:42:views
GET shop:article:42:views
TTL shop:article:42:views
PTTL shop:article:42:views
SCAN 0 MATCH shop:article:*:views COUNT 100
~~~

Sensible order:

1. Confirm both application and CLI point to the same **host/port/Redis logical database**.
2. Use `TYPE` to verify String vs. Hash.
3. For Strings, use `GET` to inspect the stored numeric format.
4. Use `TTL` to see whether the key expired, lacks TTL, or is missing.
5. If a key "disappeared", check namespace, key serializer, TTL, eviction, failover, and other writers.
6. If counts drift, check retries, duplicate requests, race conditions in conditional logic, and multiple writers.

`SCAN` iterates incrementally with a cursor: to scan all matches, loop with the returned cursor until it returns to 0. Avoid `KEYS *` on large systems and never run `FLUSHDB`/`FLUSHALL` to fix errors on Redis instances holding real data.

### 18.1. Monitoring Operational Errors

Monitor processed request counts, Redis latency, timeout errors, memory, and client counts. However, **an incremented Redis value does not prove a business event succeeded**. For example, an HTTP error occurring after `INCR` succeeds still leaves the counter incremented; decide clearly when an event counts as "occurred".

Redis servers can return errors due to memory pressure, connectivity, ACL permissions, read-only replicas, or bad formats. Services must never silently swallow errors and return a fake number as success.

## 19. Common Errors

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| `ERR value is not an integer or out of range` | Value contains JSON, decimal, invalid text, or exceeds 64-bit bounds | Check `GET`, serializer, and writers; fix schema |
| `WRONGTYPE` | Key is currently a Hash/List/Set… | Check `TYPE`; use `HINCRBY` if it is genuinely a Hash field |
| Key missing yet code wrote it | Different database, host, prefix, or key serializer | Compare endpoint/DB and key bytes; check TTL |
| Redis returns unexpected negative count | `DECR` on missing key or business logic did not block negatives | Add atomic check-and-decrement, not just `GET` then `DECR` |
| Counter suffers lost updates | Used `GET`/Java addition/`SET` under concurrency | Use `INCR`/`INCRBY` |
| Counter exceeds maximum limit | Checked and incremented in two separate commands | Use Lua/transaction with atomic condition |
| Key lives forever despite expected TTL | `INCR` ran then failed before `EXPIRE`, or legacy key lacked TTL | Use atomic script; audit TTL policy |
| TTL constantly resets to full duration | Called `expire(...)` after every increment | Distinguish fixed TTL from sliding timeout |
| TTL vanishes after reset | Overwrote key with `SET`/`GETSET` | Review reset rules and expiration preservation |
| Serialization error or binary value | Template uses incompatible serializer | Prefer `StringRedisTemplate` or String-compatible serializer |
| Double-counting after timeout | Non-idempotent `INCR` retry | Use request ID/dedup or accept approximate counts |
| Count drift after restart/failover | Persistence/replication/eviction insufficient for requirements | Design durability, backups, and reconciliation |
| Counter incremented yet business op failed | No unified transaction with source of truth | Add compensation/idempotency/reconciliation |
| `INCR` fails after `INCRBYFLOAT` write | Value became a decimal string | Separate keys and APIs for the two numeric kinds |

## 20. Capstone Practice Exercise

**Problem:** build a Spring Boot service managing article view counts and authentication attempt counts within a 5-minute window.

### 20.1. View Counter

Requirements:

- Each call to `recordView(articleId)` increments the value by 1 in an atomic command.
- Key follows `shop:article:{id}:views`.
- Supports reading the current count, treating a missing key as 0 at the business layer.
- Never uses `GET` then `SET` to increment.
- Can explain acceptable drift under duplicate requests or Redis outages.

### 20.2. Authentication Attempt Counter

Requirements:

- Key follows `shop:auth:attempts:{userId}`, containing no passwords/tokens.
- First increment sets a 5-minute TTL; subsequent increments **do not extend TTL** if fixed lifetime is chosen.
- Enforces an attempt limit, e.g., maximum 5; limit check and increment must be atomic.
- When the key expires, new attempts start again from 1.
- Defines an explicit policy when Redis is unavailable; never blindly assume fail-open is always safe.

You can start with the increment/TTL script from Section 10 and extend it with the maximum-limit check from Section 12 inside **the same script**. Splitting into two scripts for "increment first, check limit later" can still allow exceeding limits or require rollbacks.

### 20.3. Observations to Record

| Scenario | Service Check | Redis Check |
| --- | --- | --- |
| First view | Returns 1 | `GET` has `"1"` |
| Next two views | Returns 2, then 3 | Key remains String |
| Counter with TTL | Returns new value | `TTL` is positive and decreasing |
| Threshold reached | Over-limit requests rejected | Counter never exceeds max |
| Value overwritten with JSON | Service receives proper error | `GET` shows JSON, `INCR` errors |
| Key written as Hash | Service receives proper error | `TYPE` returns `hash` |
| Concurrent increments | Total successful ops reflected | No lost updates from read-modify-write |
| Redis timeout | Specific error policy applied | Consider possibility command already ran |

Do not fabricate benchmark numbers as if measured. The goal is to explain and verify counter behavior using code, Redis CLI, and real test data.

## 21. Self-Review Questions

1. Why does `TYPE counterKey` return `string` even though the Java application treats the value as `Long`?
2. If `INCR` is called on a non-existent key, what is the result?
3. If `DECR` is called on a non-existent key, what happens?
4. Why does Redis reject `INCR` on the value `"12.0"`?
5. How do `INCRBY`, `DECRBY`, and `INCRBYFLOAT` differ in numeric types and return types?
6. Which command should be used to increment a Redis Hash field?
7. How can two concurrent requests doing `GET`/add 1/`SET` lose an update?
8. Does an atomic `INCR` protect a "never go below 0" rule if the check is performed with a separate `GET`?
9. Why is `StringRedisTemplate` usually a good choice for String counters?
10. Does using `RedisTemplate<String, Long>` guarantee the Redis value is stored as an ASCII integer?
11. What is the maximum value reachable via `INCR`, and how is overflow handled?
12. How do `TTL` return values -1 and -2 differ?
13. Does `INCR` remove the TTL of an expiring key?
14. Why are `INCR` then `EXPIRE` two insufficient operations if TTL must be set atomically?
15. What is the difference between a fixed lifetime and a sliding idle timeout on a counter?
16. Why does retrying `INCR` after a timeout risk double-incrementing?
17. If a counter tracks inventory, what else is needed beyond an atomic `DECR`?
18. Why can using `double`/`INCRBYFLOAT` for money be unsuitable?
19. When reading and resetting a counter, why is `getAndSet(...)` more reliable than separate `GET` then `SET`?
20. How do you distinguish wrong Redis type, wrong value format, wrong key serializer, and expired TTL errors?

## 22. References

- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): integer incrementing, handling non-existent keys, and limits.
- [Redis — DECR](https://redis.io/docs/latest/commands/decr/), [INCRBY](https://redis.io/docs/latest/commands/incrby/), [DECRBY](https://redis.io/docs/latest/commands/decrby/): integer addition and subtraction operations.
- [Redis — INCRBYFLOAT](https://redis.io/docs/latest/commands/incrbyfloat/): incrementing floating-point decimal values.
- [Redis — HINCRBY](https://redis.io/docs/latest/commands/hincrby/): incrementing integer fields inside a Redis Hash.
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/), [TTL](https://redis.io/docs/latest/commands/ttl/): setting and checking key expiration times.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): executing Lua scripts server-side in Redis.
- [Spring Data Redis Reference](https://docs.spring.io/spring-data/redis/reference/): official documentation on RedisTemplate, StringRedisTemplate, serialization, scripting, and transactions.
- [Spring Data Redis — ValueOperations API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/core/ValueOperations.html): `increment(...)`, `decrement(...)`, `getAndSet(...)`, and `getAndDelete(...)` overloads.

**Core takeaway:** A proper Redis counter requires standardizing on **Redis Strings containing integers**, using **`INCR`/`DECR`/`INCRBY`/`DECRBY`** to prevent lost updates, and explicitly designing complex rules such as TTL, maximum quotas, non-negativity, or request deduplication. `StringRedisTemplate` provides a concise API; ultimate correctness still depends on data types, key lifecycles, and your application's business requirements.
