# Retrying Based on Per-Command Idempotency in Spring Data Redis

## 1. The Problem: Connection Errors Do Not Tell Whether a Command Ran

A Spring Data Redis application can encounter a timeout, dropped connection, primary failover, or network failure right while sending a Redis command. The hardest part is not always **reconnecting**, but determining whether the earlier command **already mutated data**.

Example incrementing a counter:

```text
Application                Redis primary
    |                           |
    |---- INCR order:count ---->|
    |                           |  count: 7 -> 8
    |<--- reply lost -----------X
    |
    |---- INCR order:count ---->|  Retry
    |                           |  count: 8 -> 9
    |<----------- 9 ------------|
```

The application intended to increment once, yet incremented **twice**. Both `INCR` commands were valid on Redis, so no Redis error surfaces after the retry.

This is why you cannot apply a naive rule like "on `RedisConnectionFailureException`, retry every command." First evaluate each command's **idempotency**, how to verify outcomes when responses are lost, and accompanying business side effects.

This lesson focuses on:

1. Distinguishing safe retries from retries that duplicate side effects.
2. Identifying idempotency properties of common Redis command groups in Spring Data Redis.
3. Designing retries around **command + arguments + contention + result expectations**.
4. Applying distinct policies to `RedisTemplate` and `ReactiveRedisTemplate`.
5. Using idempotency keys, atomic commands, or Lua when commands are inherently non-idempotent.
6. Bounding retry attempts, handling unknown outcomes, and measuring operational impact.

## 2. What Is Idempotency?

An update operation is **idempotent with respect to a target state** when executing it multiple times with identical arguments yields the same resulting state as executing it once.

For a state transformation `f`:

```text
f(f(state)) = f(state)
```

Example:

```redis
SET profile:42:status ACTIVE
SET profile:42:status ACTIVE
```

Without interleaved writes, without TTLs, and considering only the key's value, running `SET` once or twice leaves the final value as `ACTIVE`. That operation is idempotent **within the scope of that value state**.

Conversely:

```redis
INCR profile:42:loginCount
INCR profile:42:loginCount
```

One increment differs from two increments. `INCR` is **not idempotent**.

### Idempotency Has Multiple Levels

Distinguish:

| Level | Question | Example |
| --- | --- | --- |
| Final Redis state | Does repeating the command yield the same state? | Repeated `SET key X` still leaves `X`. |
| Expiration / metadata | Do TTL, version, timestamp, or ordering change? | Repeated `SET key X EX 600` refreshes the TTL. |
| Return value | Do two calls return the same code/value? | First `DEL key` returns `1`; second returns `0`. |
| Side effects | Does it emit extra events, audit entries, or increment counters? | Repeated `PUBLISH` broadcasts two messages. |
| End-to-end business | Is an order or payment processed twice? | An idempotent `SET` does not make a subsequent email call idempotent. |

A command can be idempotent regarding **key value** while **not idempotent regarding TTL, return value, or observable side effects**.

Therefore, the right question is not merely "is this command idempotent?", but:

> Does retrying the exact same command, key, and payload while concurrent clients may be writing or deleting still satisfy the business contract?

## 3. Distinguishing Three Failure Cases

When a Redis command fails, the application falls into one of three situations.

### 3.1. Definitely Never Sent the Command

For example, Java input validation fails before building a command, or the application decides not to call Redis. Here there are no Redis side effects to worry about.

However, a client-side connection exception **does not automatically prove** the command was never sent. Bytes may have left the client before the connection closed.

### 3.2. Command Definitely Failed Before Mutating State

For example, Redis returns a syntax or data-type error on a single command that performed no mutation. Deterministic errors such as `WRONGTYPE`, `NOPERM`, and invalid arguments normally require fixing data/config, **not retrying the same command repeatedly**.

Yet with **Lua scripts or multi-command workflows**, an error in a later step can happen after an earlier step already mutated data. Do not assume an entire script rolled back on exception.

### 3.3. Unknown Whether the Command Applied

This is the hard case:

```text
Client sends SET/INCR/XADD
Redis may have executed it
Response is lost due to timeout or connection drop
Client has no certain outcome
```

A connection failure or client-side timeout usually **cannot distinguish** "Redis never executed it" from "Redis executed it and the reply was lost."

For idempotent commands, retrying with the same arguments can be safe if concurrency conditions permit. For non-idempotent commands, you need a mechanism to detect prior execution.

## 4. Classification Table of Common Redis Commands

The table below examines **retrying with identical arguments** and focuses on Redis operation idempotency; correctness under concurrent writers must be evaluated separately.

| Command / Spring Data Redis | State Under Repeated Execution | Practical Conclusion |
| --- | --- | --- |
| `GET key` / `opsForValue().get` | Does not mutate key | Safe to retry on transient errors; value may change if another writer updates it. |
| `MGET` / reading Hash, Set, ZSet | Read-only | Usually retryable, though no immutable snapshot guarantee. |
| `EXISTS key` / `hasKey` | Does not mutate key | Retryable for observation; result can change over time. |
| `TTL key` / `getExpire` | Reads metadata only | Retryable, though remaining time decreases. |
| `SET key fixedValue` without expiration | Overwrites same value | Usually idempotent on final value; unsafe if an old write overwrites newer updates. |
| `SET key value EX 60` | Value stays same, yet deadline refreshes | Not TTL-idempotent; retries can extend lifetime. |
| `HSET hash field fixedValue` | Same field receives same value | Usually idempotent on field value; return count may differ. |
| `SADD set member` | Member ends up present | Idempotent for membership; returned added count differs. |
| `SREM set member` | Member ends up absent | Idempotent for membership; return count may differ. |
| `DEL key` | Key ends up absent | Idempotent for absence, yet return count differs and key may be recreated between attempts. |
| `EXPIRE key seconds` | Sets deadline relative to each call time | Not idempotent for absolute deadline. |
| `PEXPIREAT key absoluteTimestamp` | Same absolute expiration timestamp | Idempotent for deadline if key is not replaced; return value may differ. |
| `INCR`, `DECR`, `INCRBY` | Each call modifies counter | Not idempotent. |
| `APPEND` | Each call appends data | Not idempotent. |
| `LPUSH` / `RPUSH` | Each call pushes element | Not idempotent. |
| `LPOP` / `RPOP` / `BRPOP` | Each call removes/returns an element | Not idempotent; retry may pop the next element. |
| `XADD stream * ...` | Each call generates a new record ID | Not idempotent. |
| `PUBLISH channel msg` | Each call broadcasts to online subscribers | Not delivery-idempotent; no business ACK. |
| `GETDEL key` | First call gets and deletes; next returns nil | Not idempotent for result/delivery. |
| `SET NX` / `setIfAbsent` | Only the first call can create | Does not duplicate state, yet retry returning `false` does not prove first call failed. |
| `XACK stream group id` | Pending entry ends up removed | Can retry to ensure ACK state; returned ACK count may shift from 1 to 0. |

**Do not treat this table as a list of "commands safe to retry unconditionally."** Re-reading can observe changed state under concurrency, and a command idempotent for an old key can become dangerous if another request reused that key name.

## 5. Retrying Reads: Usually Side-Effect Safe, Yet Not Free

Spring Data Redis example:

```java
String value = stringRedisTemplate.opsForValue()
        .get("catalog:sku-42");
```

`GET` does not mutate Redis state. On transient connection failures, a retry can retrieve the value without modifying the key.

However:

- Data may change between the initial read and the retry.
- The key may expire or be evicted.
- In Redis Cluster, post-failover reads from primary/replica may reflect different replication progress.
- An external read flow may require a consistent snapshot/version; retrying `GET` does not provide that guarantee.
- Excessive retries amplify load while Redis is degraded.

If the application must inspect consistent state across an entire request, define versioning, transactions, or optimistic concurrency rather than expecting repeated reads to return identical values.

### Read Commands with Side Effects

Not every command with "get" in its name is read-only. For example:

```redis
GETEX session:42 EX 600
```

`GETEX` both reads and resets the expiration. Retrying it extends TTL again. Similarly, `GETDEL` reads and deletes. **Classify by actual command effects**, not by Java method names.

## 6. Retrying `SET`: Value Idempotency, TTLs, and Lost Updates

### 6.1. Writing the Exact Same Value

```redis
SET profile:42:status ACTIVE
SET profile:42:status ACTIVE
```

With the same key, same value, and no other writers, repeating leaves the state as `ACTIVE`.

Spring Data Redis:

```java
stringRedisTemplate.opsForValue()
        .set("profile:42:status", "ACTIVE");
```

You can retry this operation after transient errors **when business rules permit overwriting with the same value**.

### 6.2. With Concurrent Writers, Retries Can Break Business Ordering

```text
Request A: SET status ACTIVE -> server executes, response lost
Request B: SET status SUSPENDED -> server executes
Request A: retries SET status ACTIVE -> overwrites B's newer update
```

Even though `SET key ACTIVE` is idempotent in isolation, retrying A is **unsafe for correctness under concurrency**.

If you need "update only when version is still v3," use compare-and-set via Lua or `WATCH/MULTI/EXEC`, verifying business versions rather than overwriting unconditionally.

### 6.3. `SET EX` Is Not Idempotent for TTL

```redis
SET session:42 ACTIVE EX 600
```

Attempt 1 runs at 10:00, setting deadline ~10:10. Retrying the exact command at 10:02 shifts the deadline to ~10:12. The final value matches, yet **the session lives longer**.

If business rules require expiring at a **fixed instant**, design expiration using a consistent absolute timestamp computed up front—for instance Redis `EXAT`/`PXAT` syntax—or conditional writes.

```redis
SET session:42 ACTIVE EXAT 1790000000
```

The timestamp is illustrative; in real code, compute and freeze the deadline before retries instead of generating a new deadline on each attempt.

### 6.4. `SET NX` Does Not Return the Same Result on Retry

```redis
SET lease:resource:42 token-A NX EX 60
```

Attempt 1 may create the key, yet lose the response. The retry returns nil/false because the key already exists. If the app interprets `false` as "another owner grabbed the lease," it misinterprets its own earlier success.

To check whether the lease belongs to the request, you can read the token, yet **a separate check read** still races with TTL expiration/other owners. Proper lease design requires unique tokens, atomic compare-and-set/compare-and-delete, and handling ambiguous outcomes. For critical locks, pass fencing tokens when interacting with stores outside Redis.

## 7. Retrying `DEL`: Final State vs. Key Recreation

```redis
DEL temp:job:42
DEL temp:job:42
```

If nobody recreates the key, both calls leave the key absent. Yet the return count differs:

```text
First call: 1
Second call: 0
```

In Spring Data Redis:

```java
Boolean deleted = stringRedisTemplate.delete("temp:job:42");
```

A `false` response on retry **does not prove** the first delete failed. The first attempt may have already removed the key.

More dangerously:

```text
t0: Request A DEL session:42, reply lost
t1: Request B recreates session:42 for a new owner
t2: Request A retries DEL session:42
t3: The new session is deleted
```

If a key can be recreated during the retry window, `DEL` is unsafe for "delete that exact old instance." Use generation/versioned identifiers in the key, or a Lua script that checks token/version and deletes atomically.

**Rule:** idempotency defined as "key ends up absent" is insufficient when correctness requires protecting a newly created incarnation of the key.

## 8. Collection Operations: Idempotent on Membership, Not Necessarily on Output

### Set

```redis
SADD members:active user-42
SADD members:active user-42
```

In the end, `user-42` appears once. `SADD` is idempotent for membership with unchanged arguments.

However, the return count can be `1` on the first call and `0` on the retry. If the app relies on "returns 1 means newly added" to trigger an email, retries can lose that initial trigger or produce inconsistent side effects.

```java
Long added = stringRedisTemplate.opsForSet()
        .add("members:active", "user-42");
```

Similarly, repeated `SREM` leaves the member absent, yet removed counts differ. State idempotency does not imply return-value idempotency.

### Hash

```redis
HSET profile:42 name Linh
HSET profile:42 name Linh
```

Writing the same field/value usually yields the same state. Yet if another writer concurrently updated `name` to a new value, a retry can overwrite it. Evaluate ownership, concurrency, and Hash versioning.

### Sorted Set

```redis
ZADD leaderboard 125 user-42
ZADD leaderboard 125 user-42
```

One or two calls yield the same final score absent interleaved writes; by contrast, `ZINCRBY` adds to the score each time and is **not idempotent**.

Classify by score update mode: setting an absolute score differs from incrementing a relative score.

## 9. Non-Idempotent Commands: Counters, Lists, Streams, and Pub/Sub

### 9.1. Counters

```java
Long next = stringRedisTemplate.opsForValue()
        .increment("orders:sequence");
```

Retries can increment again, creating unwanted gaps or skewing totals. Sequences sometimes tolerate gaps, yet **one request receiving two numbers** still needs an explicit contract.

### 9.2. List Push/Pop

```java
stringRedisTemplate.opsForList()
        .rightPush("jobs:pending", "job-42");
```

Retrying `RPUSH` can enqueue two copies of `job-42`. Retrying `LPOP` after a lost response can pop **a different job**, stranding the first job from the application.

If you need a queue with pending/ACK/retry states, avoid naive List pops with blind retries. Consider Redis Streams consumer groups or a durable queue suited to the job.

### 9.3. Redis Streams

```redis
XADD jobs:events * type created id 42
```

`*` generates a fresh stream ID every time. Retrying creates **two separate records** if the first attempt succeeded and lost its reply.

To ensure a business event is recorded once, attach a stable event ID and use deduplication or a transactional outbox. Manually computing conditional stream IDs must account for monotonic ID rules, races, and Redis semantics; do not replace `*` with an arbitrary ID assuming retries always succeed cleanly.

### 9.4. Redis Pub/Sub

```java
stringRedisTemplate.convertAndSend(
        "orders.created", "{\"orderId\":\"42\"}");
```

Retrying can publish the same message again. Subscribers receive no business ACK metadata from `PUBLISH`'s return value, so a retry count cannot guarantee exactly-once delivery.

If business logic tolerates duplicates, embed a stable `eventId` in the payload and make handlers idempotent. If offline subscribers need replay, Pub/Sub cannot provide it; choose a durable event log or queue.

### 9.5. Lua Scripts

A Lua script may combine idempotent and non-idempotent commands. **`EVAL`/`EVALSHA` itself is not inherently idempotent**; its behavior depends on script logic.

For example, a script calling `INCRBY` unconditionally increments on every retry. A script checking an idempotency key before mutating can curb duplicates, provided you understand atomicity, per-command errors, and persistence/failover limits.

## 10. Do Not Turn Business Errors into Retryable Errors

Never retry every `DataAccessException` or every exception.

Categories to separate:

| Error Group | Example | Handling Direction |
| --- | --- | --- |
| Transient connect/timeout | Lost connection, network timeout, Redis failover | Can retry **if command is suitable**, with bounded attempts. |
| Config/permissions | `NOAUTH`, `NOPERM`, wrong host, unauthorized command | Fix config/ACL; retrying the same command solves nothing. |
| Data/type | `WRONGTYPE`, non-numeric value for `INCR` | Fix data or logic; do not blindly retry. |
| Resource limits | Redis out of memory, AOF/RDB/disk failure | Alert and shed load; infinite retries worsen overload. |
| Business conflict | `SET NX` skipped because key exists, optimistic lock failed | Normal domain outcome, not a connection failure. |
| Topology | `MOVED`/`ASK`, Redis Cluster failover | Rely on cluster-aware driver/topology refresh; separate persistent faults from retryable ones. |

Spring Data Redis translates many driver errors into Spring's exception hierarchy, typically `DataAccessException` or subtypes like `RedisConnectionFailureException`. Timeouts may appear under different types depending on driver, version, and call path.

**Classify the actual exceptions** in your project rather than assuming every timeout is one exact class. Furthermore, if a command has side effects, even a technically transient error must still pass idempotency checks before retrying.

## 11. Retry Policies Should Belong to Operations, Not Just Exceptions

A good policy has four dimensions:

1. **Command kind:** read-only, state assignment, increment/append/pop, publish, script...
2. **Arguments and conditions:** is the value fixed, is TTL preserved, are there competing writers?
3. **Failure type:** transient network/timeout or logic/config error?
4. **Budget:** max attempts, total time, backoff, jitter, and concurrency cap?

Example decision table:

| Business Operation | Redis Command | Auto-Retry? | Conditions |
| --- | --- | --- | --- |
| Read cache value | `GET` | Usually yes | Retry only transient errors, bound within request deadline. |
| Write fixed config | `SET key fixedValue` | Conditional | Allowed to overwrite, no version/concurrency violation, no unintended TTL reset. |
| Set state with fixed deadline | `SET ... EXAT/PXAT` | Conditional | Keep original deadline across retries, handle concurrent writers. |
| Remove a member | `SREM` | Conditional | Return count must not be relied upon as the sole required signal. |
| Release a lock | `DEL` | Not blindly | Must compare owner token atomically. |
| Increment balance/counter | `INCRBY` | Not automatically | Use idempotency operation ID or design tolerating duplicates. |
| Enqueue job in List | `RPUSH` | Not automatically | Can duplicate jobs; switch to deduplicated queue if needed. |
| Append stream entry | `XADD *` | Not automatically | Needs event ID/dedup and durable write strategy. |
| Broadcast notification | `PUBLISH` | Not automatically unless duplicates OK | Subscribers must dedupe; Pub/Sub has no replay. |
| ACK stream message | `XACK` | Conditional | Safe to retry toward "no longer pending"; response count may differ. |

Define policies on **business service methods**, rather than attaching a global interceptor that retries every Redis command.

## 12. Example with Imperative `StringRedisTemplate` and Spring Retry

### 12.1. Dependencies and Scope

If the project uses Spring Retry, it typically needs `spring-retry` and appropriate AOP integration. Maven example:

```xml
<dependency>
    <groupId>org.springframework.retry</groupId>
    <artifactId>spring-retry</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-aop</artifactId>
</dependency>
```

Depending on Spring Boot/dependency management, library versions and bean setup may vary. This lesson uses `RetryTemplate` to illustrate explicit per-operation policies; avoid global driver-level retries without evaluating idempotency.

### 12.2. Bounded Retry Bean for Connection Failures

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.retry.support.RetryTemplate;

@Configuration
public class RedisRetryConfiguration {

    @Bean
    public RetryTemplate redisReadRetryTemplate() {
        return RetryTemplate.builder()
                .maxAttempts(3)
                .exponentialBackoff(100, 2.0, 1000)
                .retryOn(RedisConnectionFailureException.class)
                .build();
    }
}
```

Meaning:

- Maximum **3 total executions**, including the initial attempt and retries; not 3 retries after the first attempt.
- Exponential backoff avoids hammering Redis right after an error.
- This illustrative policy catches only the specified connection exception. Timeouts may surface differently by driver; applications should add controlled classification after observing real exceptions.

In production, add jitter/backoff budgets and circuit breakers as needed; not every version of `RetryTemplate` builder exposes the exact same jitter API, so check your dependency version.

### 12.3. Applying to `GET`

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;
    private final RetryTemplate redisReadRetryTemplate;

    public ProductCacheReader(
            StringRedisTemplate redis,
            RetryTemplate redisReadRetryTemplate) {
        this.redis = redis;
        this.redisReadRetryTemplate = redisReadRetryTemplate;
    }

    public String findStatus(String productId) {
        String key = "product:" + productId + ":status";

        return redisReadRetryTemplate.execute(
                context -> redis.opsForValue().get(key));
    }
}
```

Here, the retry wraps **a single `GET` command**. No email sending or database mutation occurs inside the retry callback, so retries do not duplicate external side effects.

If the key does not exist, `get(key)` returns `null` per the imperative API. That is a valid result, **not an exception to retry**. Never trigger retries merely because a value is absent.

### 12.4. Separate Policy for Idempotent Writes

Suppose an API sets an absolute flag without a TTL:

```java
public void setMaintenanceMode(String value) {
    if (!"ON".equals(value) && !"OFF".equals(value)) {
        throw new IllegalArgumentException("Invalid value");
    }

    redisReadRetryTemplate.execute(context -> {
        redis.opsForValue().set("config:maintenance", value);
        return null;
    });
}
```

This merely illustrates retrying `SET` with identical arguments. Reusing the variable name `redisReadRetryTemplate` can be misleading; in real apps name policies by scope, such as `redisIdempotentWriteRetryTemplate`, and verify whether business logic allows overwriting if another writer changes the value during a retry.

If maintenance mode must be updated with version control, do not use the unconditional `SET` in this snippet; upgrade to compare-and-set/versioning.

### 12.5. Do Not Put `INCR` in the Same Retry Template Just Because the Exception Matches

```java
// DO NOT DO THIS:
return redisReadRetryTemplate.execute(context ->
        redis.opsForValue().increment("metrics:orders"));
```

If the first attempt incremented and lost the reply, the retry increments again. Wrapping with `RetryTemplate` does not make a non-idempotent command idempotent.

## 13. Retries in Reactive Redis: `retryWhen` Means Resubscription

With `ReactiveStringRedisTemplate`, every operation returns a Reactor publisher. Retrying via `retryWhen` **resubscribes to upstream** after an error, typically sending the Redis command again.

### 13.1. Bounded Retry for `GET`

```java
import java.time.Duration;

import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Service
public class ReactiveProductReader {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProductReader(ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> findStatus(String id) {
        return redis.opsForValue()
                .get("product:" + id + ":status")
                .retryWhen(
                        Retry.backoff(2, Duration.ofMillis(100))
                                .maxBackoff(Duration.ofSeconds(1))
                                .jitter(0.3)
                                .filter(ex ->
                                        ex instanceof RedisConnectionFailureException));
    }
}
```

In Reactor, `Retry.backoff(2, ...)` means **at most 2 retries after the initial attempt**, unlike `maxAttempts(3)` in the earlier `RetryTemplate` example.

If the Redis key does not exist, `Mono.empty()` completes normally; `retryWhen` does not trigger retries merely because no value was emitted.

### 13.2. Be Careful with `INCR` and `retryWhen`

```java
// DANGEROUS IF DUPLICATE INCREMENTS ARE UNACCEPTABLE:
return redis.opsForValue()
        .increment("counter:orders")
        .retryWhen(Retry.backoff(2, Duration.ofMillis(100)));
```

A timeout or disconnect after Redis incremented the counter causes the next subscription to resend `INCR`.

### 13.3. Scope Retries Properly in the Pipeline

```java
return redis.opsForValue()
        .get(key)
        .retryWhen(readRetryPolicy)
        .flatMap(value -> externalService.process(value));
```

Placing `retryWhen` **before** calling the external service scopes retries to the Redis read. Placing retry after the whole pipeline allows failures from `externalService.process` to re-run upstream steps.

Conversely, if `externalService.process` has side effects and callers need to retry it, design a dedicated idempotency policy for that service.

## 14. Creating Idempotency Keys for Non-Idempotent Business Logic

To retry an operation like `INCRBY` without incrementing twice, the request needs an **operation ID stable across all retries**.

Example:

```text
Business request: adjust inventory counter
operationId = inventory-adjust-req-9f3a
counterKey  = stock:{sku42}:reserved
markerKey   = op:{sku42}:inventory-adjust-req-9f3a
delta       = +3
```

Idea:

1. Redis checks the marker for the operation ID.
2. If the marker exists, return the recorded result without applying the mutation again.
3. If the marker is absent, apply the mutation and save the marker/result **in the same atomic operation**.

Crucially, if Java executes:

```java
if (!redis.hasKey(markerKey)) {
    redis.opsForValue().increment(counterKey, delta);
    redis.opsForValue().set(markerKey, "done");
}
```

those are **three separate commands**. Two requests or a retry can both see the marker missing and increment before the marker is written. Moreover, a failure between incrementing and writing the marker loses deduplication state.

Use a Lua script or an appropriate server-side atomic mechanism in Redis.

## 15. Lua Example: `INCRBY` with Request ID Checking

Example script illustrating a counter and marker in the same hash slot. Inputs:

```text
KEYS[1] = stock:{sku42}:reserved
KEYS[2] = op:{sku42}:inventory-adjust-req-9f3a
ARGV[1] = "3"       -- delta
ARGV[2] = "86400"   -- marker retention in seconds
```

Lua code:

```lua
-- KEYS[1]: counter key
-- KEYS[2]: idempotency marker that can store the result
-- ARGV[1]: delta in Redis integer syntax
-- ARGV[2]: marker TTL in seconds

local prior = redis.call('GET', KEYS[2])
if prior then
    return tonumber(prior)
end

local ttl = tonumber(ARGV[2])
if ttl == nil or ttl <= 0 or ttl % 1 ~= 0 then
    return redis.error_reply('ERR invalid marker TTL')
end

-- Basic validation before writing.
if string.match(ARGV[1], '^%-?%d+$') == nil then
    return redis.error_reply('ERR invalid delta')
end

local counterType = redis.call('TYPE', KEYS[1]).ok
local markerType = redis.call('TYPE', KEYS[2]).ok
if counterType ~= 'none' and counterType ~= 'string' then
    return redis.error_reply('ERR counter wrong type')
end
if markerType ~= 'none' and markerType ~= 'string' then
    return redis.error_reply('ERR marker wrong type')
end

-- Redis checks INCRBY integer overflow itself.
local value = redis.call('INCRBY', KEYS[1], ARGV[1])
redis.call('SET', KEYS[2], tostring(value), 'EX', ttl)
return value
```

When the script executes sequentially on the same primary, no other client commands interleave between steps. If Redis succeeds yet the response is lost, a retry with the same marker sees `prior` and returns the same value instead of incrementing again.

### Limitations of the Example

This is an **idempotency design pattern in Redis**, not an absolute guarantee of exactly-once execution:

- Markers have TTLs: once expired, a very late retry can re-execute the operation.
- Redis Cluster requires related keys in the same hash slot; this example uses the `{sku42}` tag.
- If the script errors after `INCRBY` but before saving the marker, Redis Lua **does not roll back** the completed write. Pre-validate inputs, permissions, and resource limits thoroughly, and maintain recovery procedures for partial failures.
- Asynchronous Redis replication/failover can lose both the counter update and marker if not yet replicated; atomicity on a primary does not replace durability.
- Reusing an old `operationId` with a different `delta` produces misleading results. IDs must be unique per **logical operation**; every retry of that operation must carry identical payloads.
- Using `tonumber(prior)` to return integers via Lua requires care for very large numbers; for values exceeding Lua's exact integer range, return strings or use another representation.
- Retaining markers for millions of requests requires sizing RAM, TTLs, and max retry/duplicate-delivery windows.

### Calling the Script from Spring Data Redis

```java
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;

public class StockCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementOnceScript;

    public StockCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementOnceScript) {
        this.redis = redis;
        this.incrementOnceScript = incrementOnceScript;
    }

    public Long incrementOnce(
            String sku,
            String operationId,
            long delta) {

        String tag = "{" + sku + "}";
        String counterKey = "stock:" + tag + ":reserved";
        String markerKey = "op:" + tag + ":" + operationId;

        return redis.execute(
                incrementOnceScript,
                List.of(counterKey, markerKey),
                Long.toString(delta),
                "86400"
        );
    }
}
```

`incrementOnceScript` is a `RedisScript<Long>` bean loading the Lua script above, for example from `ClassPathResource` with `setResultType(Long.class)`.

Before calling, validate `sku` and `operationId` so clients cannot inject `{}` hash tags or traverse namespaces, and ensure the operation ID is generated **once when the business operation starts**, not a new UUID on every retry.

Only when retries after failures can observe the preserved marker does the script protect against duplicates; **simply wrapping a plain `INCRBY` in `RetryTemplate` offers no such protection**.

## 16. What Data Should an Idempotency Key Store?

A good marker needs more than `"done"` if callers also need the original execution's result.

The contract can include:

| Field or Data | Purpose |
| --- | --- |
| `operationId` | Immutable identifier of the logical operation. |
| `requestHash` or payload fingerprint | Prevents reusing the same ID with different arguments. |
| `status` | `PROCESSING`, `COMPLETED`, or equivalent states for multi-step workflows. |
| `result` | Returns a consistent result when the caller retries after a lost response. |
| `createdAt`/`expiresAt` | Manages idempotency retention window. |
| `owner/version` if needed | Supports contention control and conditional updates. |

Using a single Redis script to update a counter and store a marker can be simpler than multi-step workflows. However, when business logic also invokes SQL or HTTP during processing, **you cannot use one Lua script to atomically commit Redis alongside external systems**.

For end-to-end reliability:

- Choose a transactional source of truth, such as a database with a unique constraint on `operationId`.
- Use a transactional outbox to emit events after the business transaction commits.
- Design consumers to be idempotent by event ID.
- Acknowledge only once business outcomes are durably stored.
- Separate Redis cache retries from business transaction retries so external side effects are never duplicated.

## 17. Timeouts, Failover, and Durability: Know Idempotency's Limits

Even with a marker:

```text
Primary Redis:
  INCRBY counter succeeds
  SET marker succeeds
  client gets network error

Replica:
  has not received the latest updates yet

Primary fails:
  replica is promoted, missing latest counter/marker
```

After failover, a retry can run again because the marker is absent on the new primary. This demonstrates that **atomicity on a single Redis primary does not guarantee durability across the whole topology**.

Mechanisms like AOF, RDB, replication, `WAIT`, and deployment architecture alter data-loss risk, yet do not automatically create distributed exactly-once behavior between Redis and another system.

### When to Use `WAIT`?

`WAIT` lets a caller wait for a given number of replicas to acknowledge replication progress for prior writes on the **same connection** per Redis semantics. However:

- It does not guarantee zero data loss across all failovers.
- It does not prove durable `fsync` on replicas.
- When a Spring template uses connection pools/transactions, do not assume a separate `WAIT` always binds to the exact write history of the prior connection.

Thus `WAIT` is a risk-reduction tool in carefully designed architectures, not a cure-all for non-idempotent retries.

## 18. Budgeted Retries: Attempts, Backoff, Jitter, and Deadlines

Unbounded retries cause three problems:

1. An ailing Redis receives even more commands, slowing recovery.
2. APIs/requests blow past deadlines, tying up threads or pipelines.
3. Non-idempotent operations face higher odds of executing multiple times.

A typical bounded policy:

```text
Attempt 1: call immediately
Transient error:
  wait 100 ms + jitter
Attempt 2: retry
Transient error:
  wait 200 ms + jitter
Attempt 3: retry
If still failing -> return error or fallback per contract
```

Choose:

- Small, explicit **max attempts** per operation.
- **Exponential backoff** to curb retry storms.
- **Jitter** to prevent synchronized client retries.
- **Overall timeout/deadline** for the entire request, not only per command.
- **Circuit breaker/bulkhead** when Redis remains degraded.
- **Concurrency limits** so concurrent requests do not multiply Redis load.
- **Metrics** separating initial calls from retry attempts.

With an HTTP API deadline of 500 ms, configuring three 1-second timeouts plus backoff is pointless: the request times out long before the policy finishes.

Do not retry independently at the driver, service, and gateway layers without controlling the total budget. **Nested retries** can multiply commands dramatically even if each layer only retries 2–3 times.

## 19. Retry at the Right Transaction Boundary

An error-prone example:

```java
@Retryable
@Transactional
public void createOrderAndUpdateCounter(Order order) {
    orderRepository.save(order);
    redis.opsForValue().increment("orders:count");
    emailSender.sendConfirmation(order);
}
```

If a Redis error occurs after partial commits in a real workflow, or an email error occurs after Redis increments, retrying the whole method can cause:

- Duplicate orders or unique constraint violations.
- Incrementing the counter multiple times.
- Sending multiple emails.
- Inconsistent state between the database and Redis.

This example illustrates scope risk; exact commit/rollback ordering depends on how transaction proxies and non-transactional calls interact.

Do not treat `@Transactional` as a magic wand uniting SQL + Redis + email into one distributed transaction.

Instead:

- Scope retries around operations with suitable idempotency.
- For critical side effects, assign a stable business operation ID.
- Use database unique constraints/outboxes to decouple business commits from event emission.
- Use idempotent consumers and contract-compliant ACK/retry handling.
- For Redis caches, tolerate misses/fallbacks rather than aborting a business transaction solely because a cache is temporarily unreachable when unnecessary.

## 20. Retry Tests Must Simulate "Executed but Response Lost"

A test that only mocks "Redis errors before running the command" **misses the biggest risk**. Test the scenario where the command executed and the reply was lost.

### 20.1. Testing Read Commands

A mock throws `RedisConnectionFailureException` on the first `GET`, then returns a value on the second:

```text
GET attempt 1 -> transient error
GET attempt 2 -> "ACTIVE"
Expected:
  returns "ACTIVE"
  total GETs match policy
  no unintended write commands
```

### 20.2. Testing `SET` with Fixed State

```text
SET status ACTIVE attempt 1 -> Redis wrote, client receives error
SET status ACTIVE attempt 2 -> Redis receives command again
Expected:
  final value = ACTIVE
  if TTL applies, deadline follows chosen contract
```

If a concurrent writer updates state during the retry, the test should verify the application's version/compare-and-set policy rather than checking only single-writer final state.

### 20.3. Testing `INCR` Without Idempotency

```text
initial counter = 7
INCR attempt 1 executes -> 8, response lost
INCR attempt 2 executes -> 9

Expected test observation:
  logical operation incremented twice
```

This test demonstrates **what not to do**.

### 20.4. Testing `INCR` with an Operation Marker

```text
initial counter = 7
operationId = "req-42"

Script attempt 1:
  counter -> 8
  marker req-42 -> result 8
  response lost

Script attempt 2, same operationId:
  reads marker -> 8
  does not INCR
  returns 8

Expected:
  final counter = 8
  both attempts yield same logical result
```

Additional tests:

- Same operation ID with a different payload must be rejected per contract.
- Marker expires before a late retry: know which risk the system accepts.
- Two concurrent requests with the same ID: only one executes under the atomic mechanism.
- Redis Cluster: counter and marker map to the same hash slot.
- Failover mid-execution: evaluate potential loss of marker and data.
- Script failure after an initial mutation: have a recovery/reconciliation plan.

### 20.5. Testing in Spring with `StepVerifier`

For reactive `GET` retries, use Reactor Test:

```java
StepVerifier.create(reader.findStatus("42"))
        .expectNext("ACTIVE")
        .verifyComplete();
```

`StepVerifier` subscribes to the publisher, actually triggering the command. Use mocks or an isolated test Redis to verify subscription counts and transient error behavior. Never conclude an idempotent policy is correct from a happy-path test alone.

For Redis integration tests, never intentionally sever networks or kill primaries in production. Use Testcontainers/labs to simulate disconnects and a proxy capable of dropping responses after commands reach Redis when testing exact failure modes.

## 21. When a Command Outcome Is Lost, Should You Read Back to Verify?

You can, provided you understand its limits.

For example, `SET key ACTIVE` times out. Later `GET key` returns `ACTIVE`. That confirms **at the time of `GET`**, the state is `ACTIVE`; it does not prove your timed-out command was the one that wrote it, especially with concurrent writers.

For example, `INCR` times out. Reading the new counter as `9` does not tell the app whether it incremented or another request did—unless you have an operation ID/marker, version, or authoritative source to reconcile against.

With `SET NX`, reading the token can confirm temporary ownership, yet TTL expiration/failover and owner rotation still mean a simple read is insufficient for high-assurance locks.

**Read-after-error is a fresh observation**, not a rollback or exact confirmation of the prior command.

## 22. Relationship to Redis Streams Consumer Groups

Redis Streams tracks pending entries and ACKs to support recovery when consumers crash:

```text
XREADGROUP -> message delivered, added to PEL
worker runs business logic
XACK -> removes message from PEL
```

If the handler finished yet `XACK` timed out, retrying `XACK` may return `0` because the record was already ACKed. That **aligns with the end goal of clearing the pending entry**, yet it does not guarantee the handler ran only once if the message was claimed and reprocessed earlier.

Separate:

- Retrying **`XACK`** for the same stream/group/record ID.
- Retrying **business processing** when a message is un-ACKed.
- Idempotency of external side effects such as SQL writes or sending emails.

Consumer groups do not automatically give application-level exactly-once semantics. Maintain event IDs, unique constraints, or idempotency tables when side effects matter.

## 23. Observing and Alerting on Retries in Operations

Metrics to track:

| Metric | Meaning |
| --- | --- |
| `redis_command_attempts_total{operation}` | Total calls, including retries. |
| `redis_command_retries_total{operation,reason}` | Which operations are retrying heavily. |
| `redis_command_failed_total{operation,reason}` | Operations failing after retry policy exhaustion. |
| `redis_retry_delay_seconds` | Total backoff delay and latency impact. |
| `redis_ambiguous_write_total{operation}` | Cases where the client does not know if a write ran. |
| `idempotency_marker_hit_total{operation}` | Retries/dedups hitting a prior marker. |
| `idempotency_conflict_total` | Same operation ID reused with different arguments; needs investigation. |
| `redis_connection_failure_total` | Connection instability requiring root-cause analysis. |
| `redis_failover_total` | Primary/topology changes correlated with retries. |
| `business_duplicate_suppressed_total` | Duplicate side effects prevented at the business layer. |

These are suggested metric names, not metrics automatically emitted by Spring Data Redis. Implement proper instrumentation and cap label cardinality; **never attach raw operation IDs or Redis keys as metric labels**, as unbounded values blow up cardinality and leak sensitive data.

Alerting on spiking retries is often more informative than watching HTTP 500 rates alone: the system may return 200 after three Redis attempts while silently multiplying backend load.

When retries spike unexpectedly, investigate in order: Redis latency, connections, CPU, memory, persistence/I/O, replication/failover, topology, request volume, and retry configs across layers.

## 24. Checklist for Designing a Retryable Redis Operation

Before adding retries to a service method, answer:

1. What is the actual Redis command? Are there scripts, side effects, or implicit commands?
2. If the command runs **twice with identical arguments**, does the final state differ?
3. Do TTL, expiration, version, or return values differ?
4. If another client writes/deletes between attempts, can the retry overwrite or delete newer data?
5. When a response is lost, is there a way to confirm completion without causing extra side effects?
6. Is the operation ID stable across every retry attempt?
7. Do you need to persist results/fingerprints and set a marker TTL?
8. If a script fails mid-way, can partial writes remain without rollback?
9. Do coordinated keys need the same Redis Cluster hash slot?
10. Can a Redis failover drop markers or unreplicated recent writes?
11. Which exceptions are genuinely transient, and which are logic/config bugs?
12. What are max attempts, backoff, jitter, and total request deadline?
13. Is another layer already retrying the same operation?
14. Might users double-click or gateways replay POST requests?
15. Which metrics, logs, alerts, and reconciliations will detect duplicates?
16. If business logic fails after a Redis operation succeeded, is a transaction/outbox needed in another datastore?

Enable automatic retries only once these core questions are answered.

## 25. Common Mental Pitfalls

**"A timeout error means the command didn't run."**  
No. Redis may have executed it and the response was lost.

**"`SET` is always idempotent."**  
Not in every context: TTLs may reset, concurrent writers may be overwritten, and application outputs/side effects can differ.

**"`DEL` is idempotent so retrying endlessly is fine."**  
No. Keys can be recreated between attempts and wrongly deleted.

**"Retrying reads can never be wrong."**  
Reads do not mutate Redis, yet retries can observe newer state, lagging replicas, or inconsistent snapshots. Timeouts/retries also add load.

**"`SET NX` returning false means the first request didn't create the key."**  
No. The first request may have created the key and lost the reply; the retry sees the key already exists.

**"Retrying `XADD *` just resends the same record."**  
No. Normally each call generates a fresh stream ID and appends a duplicate entry.

**"Redis transactions or Lua roll back automatically on error."**  
Not like SQL transactions. Redis does not undo prior commands in a script when a later command errors.

**"Spring Retry makes all Redis operations safe."**  
No. `RetryTemplate`/`@Retryable` only repeats calls; idempotency still depends on the operation and business logic.

**"Reactive `retryWhen` just fetches the old response."**  
No. It resubscribes upstream and typically executes the Redis command again.

**"Having an idempotency marker guarantees exactly-once across all systems."**  
No. Markers have TTLs, can be lost in failovers, scripts have partial-failure risks, and external systems do not commit atomically with Redis.

**"Retrying more increases reliability infinitely."**  
No. Retry storms degrade Redis further and raise the risk of duplicate side effects.

## 26. Per-Command Hands-On Exercises

Use only a test Redis instance and the `demo:retry:*` namespace. Never run duplicate-inducing tests on real business data.

### Exercise A — Comparing `SET` and `INCR`

```redis
SET demo:retry:state ACTIVE
SET demo:retry:state ACTIVE
GET demo:retry:state

SET demo:retry:count 0
INCR demo:retry:count
INCR demo:retry:count
GET demo:retry:count
```

Result: state stays `ACTIVE`, counter becomes `2`. Observe the difference between state assignment and relative increment.

### Exercise B — Observing TTL Refresh

```redis
SET demo:retry:ttl ACTIVE EX 60
TTL demo:retry:ttl
```

Wait briefly, then repeat the exact command:

```redis
SET demo:retry:ttl ACTIVE EX 60
TTL demo:retry:ttl
```

The TTL resets near 60 seconds. This shows why retrying the same value can alter session/lease expiration semantics.

### Exercise C — First vs. Second `DEL` Output

```redis
SET demo:retry:del VALUE
DEL demo:retry:del
DEL demo:retry:del
```

The first returns `1`, the second `0`. Both produce the same absent state, yet outputs differ.

### Exercise D — `SET NX` and Ambiguous Outcomes

```redis
SET demo:retry:nx request-42 NX EX 60
SET demo:retry:nx request-42 NX EX 60
GET demo:retry:nx
```

The first returns `OK`, the second nil; `GET` still returns `request-42`. In real systems, if the first reply is lost, do not treat the second nil as "first write never happened."

### Exercise E — Re-publishing Pub/Sub Events

Have one terminal subscribe to `demo:retry:events` and another run:

```redis
PUBLISH demo:retry:events event-42
PUBLISH demo:retry:events event-42
```

Online subscribers receive two messages. Redis does not deduplicate payloads merely because message strings match.

### Exercise F — Simulating Lost Responses

In a lab environment, use a test proxy or mock driver to:

1. Let Redis execute `INCR`.
2. Drop the response before it reaches the client.
3. Trigger a retry without a marker and watch the counter increment twice.
4. Switch to the script with an idempotency marker and the same operation ID.
5. Repeat to observe the marker preventing duplicate updates within the TTL window.
6. Test what happens once the marker expires or when retrying with a different operation ID.

This exercise does not require crashing Redis or losing real data. Never inject failovers or network cuts in production to test.

## 27. Self-Check Questions

1. If `INCR` times out, why can re-running the same command corrupt the counter?
2. Why can `SET key value` be value-idempotent yet not TTL-idempotent?
3. A `DEL` executed yet its reply was lost; why can the retry return `0` and still meet the deletion goal?
4. When a key is recreated between two `DEL` attempts, how can the outcome break?
5. How do `HSET`, `SADD`, and fixed-score `ZADD` behave similarly and differently regarding final state vs. output?
6. Why does `SET NX` returning `false` on retry not prove the first attempt failed?
7. When is auto-retrying `GET` appropriate, and why must retries still be bounded?
8. Is Redis `GETEX` truly read-only?
9. Why cannot `XADD stream * ...` and `PUBLISH` be retried blindly?
10. How does Reactor `retryWhen` affect the upstream Redis operation?
11. Why should retries wrap the `GET` call rather than the entire pipeline calling an external service?
12. Which keys are needed to deduplicate `INCRBY` with Lua, and why must they share a hash slot in Redis Cluster?
13. Why must an idempotency marker have an adequate TTL and an operation ID stay immutable across retries?
14. Does a Lua script guarantee rollback if its last command fails?
15. Why can replication/failover lose a marker even after the script succeeded on the old primary?
16. Why does `WAIT` not guarantee exactly-once behavior?
17. When calling Redis inside a `@Transactional` method, why can retrying the whole method duplicate side effects?
18. Which factors should govern error filtering and total time budget in a good retry policy?
19. Why is it essential to test the "server executed yet client received no reply" failure mode?
20. Why is an identical final Redis state insufficient to conclude a business operation ran only once?

**Takeaway:** In Spring Data Redis, retry decisions must be grounded in the **actual idempotency of each Redis command within its business context**, not just exception classes. Reads are generally retryable; state assignments are conditionally retryable; increments, pushes/pops, stream appends, and publishes risk duplicating effects. For non-idempotent commands, use **stable operation IDs, atomic check/dedup, bounded retries, and proper recovery mechanisms**. Never confuse Lua atomicity, Redis replication, or Spring Retry with end-to-end exactly-once guarantees.

## References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): invoking Redis operations and handling results.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): executing atomic Lua scripts in Redis.
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): Reactor Mono/Flux and reactive Redis operations.
- [Spring Retry — Reference](https://docs.spring.io/spring-retry/docs/current/reference/html/): retry policies, backoff, and attempt limits.
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): retry/retryWhen and upstream resubscription effects.
- [Redis — SET](https://redis.io/docs/latest/commands/set/): NX/XX, TTL, and conditional writes.
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): atomic counter increment command.
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/): creating stream entries and IDs.
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/): Pub/Sub message broadcasting mechanism.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): passing KEYS/ARGV and executing scripts.
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/): data limits during asynchronous failover.
