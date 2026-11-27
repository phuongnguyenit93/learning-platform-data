# Connection Drops After Sending a Command and Duplicate Write Risks in Spring Data Redis

## 1. Scenario: Did the Command Execute or Not?

A Spring Boot application uses `StringRedisTemplate` to increment an order submission counter:

```java
Long newValue = redis.opsForValue()
    .increment("orders:submitted");
```

Normally, Redis executes `INCR orders:submitted` and returns the new number. Now consider this timeline:

```text
Spring Application         Network                  Redis
       |                     |                       |
 t0    |--- INCR key ------->|---------------------->|
       |                     |                       |
 t1    |                     |               Redis increments 100 -> 101
       |                     |                       |
 t2    |                     |<------ response 101 --|
       |           connection drops, response lost   |
       |                     X                       |
 t3    |<-- timeout/error ---|                       |
       |                                             |
 t4    |---- retry INCR ---------------------------->|
       |                                     101 -> 102
       |<------------------------------------------ 102
```

The application receives an exception or timeout at `t3`. That **does not prove Redis did not execute the command**. If the application retries `INCR` without recognizing the prior request, the counter can increment **twice** for a single business operation.

This is an **ambiguous execution outcome** (*ambiguous outcome* or *unknown commit outcome*): the client does not know whether the first attempt was already applied.

The problem does not stop at `INCR`:

- `LPUSH` or `RPUSH` can insert the same item twice.
- `XADD ... *` can create two Redis Stream entries with different IDs carrying the same event.
- `PUBLISH` can send duplicate notifications to online subscribers.
- An inventory-updating Lua script can be invoked again after a timeout.
- An `EXEC` transaction may have executed even though the client never received the response.
- A payment request can duplicate side effects if Redis only held a check flag at an uncertain point.

Core takeaway of this lesson:

> **Once a command may have been sent, a connection drop or timeout may merely have lost the response. Blindly retrying a non-idempotent command can cause duplicate writes.**

In Spring Data Redis, the right response is not merely raising `timeout` or adding `@Retryable`. You must understand **command semantics**, **ambiguous execution states**, **idempotency**, **atomicity**, and **durability across restarts/failovers**.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish failures occurring before sending, while sending, after Redis execution, and after Redis response.
2. Explain why a successful TCP write or timeout is insufficient to prove a command's outcome.
3. Classify Redis commands by side effects when re-executed.
4. Understand that Spring Data Redis and Lettuce retry/reconnect must be governed by application semantics.
5. Design request IDs, Redis idempotency keys, and Lua scripts to prevent double increments.
6. Recognize limitations of `SET NX`, locks, transactions, pipelines, Redis Streams, and Pub/Sub.
7. Design stronger idempotency for workflows spanning Redis and external databases/HTTP APIs.
8. Understand failover, replication lag, RDB/AOF, and cases where deduplication records can also be lost.
9. Build practical retry policies, logging, metrics, and fault-injection tests.
10. Avoid confusing "at-least-once delivery" with "exactly-once business effect."

## 2. Lifecycle of a Redis Command

A Redis command sent via a client normally passes through several stages:

```text
Application                       Redis client                  Redis server

1. Build command
       |
2. Serialize key / args
       |
3. Queue onto connection
       |
4. Encode RESP + write socket -----------> Bytes across network
                                               |
5.                                       Redis receives full command
                                               |
6.                                       Redis executes command
                                               |
7.                                       Redis writes response
       |<------------------------------ Response across network
8. Decode reply
       |
9. Java method / Mono returns result
```

Depending on the connector, commands can be queued while a connection is unavailable, pipelined, or grouped in a command sequence/transaction.

Failures at each stage mean different things:

| Failure Location | What May Have Happened | Does the Client Know If the Command Executed? |
|---|---|---|
| Before application calls Redis | Command never constructed | Knows no command came from that call |
| Before queue/transport sends any bytes, with clear evidence | Command never reached the server from that attempt | May know in certain cases |
| While sending bytes | Redis may have received partial or full bytes | Usually cannot tell solely from exception |
| After Redis receives, before server executes | Command may execute or be lost on server crash | Uncertain |
| After Redis executed, before client receives reply | Side effect occurred yet reply was lost | Uncertain looking only at client |
| After client receives successful reply | Result confirmed at Redis command level | Does not automatically mean durable across failover |

A generic network error does not reveal exactly which stage occurred. **Never assume an exception always means "never ran."**

### 2.1. TCP ACK Is Not a Redis Application ACK

At the network layer, the OS accepting bytes to send or receiving a TCP acknowledgment does not mean Redis fully processed the command and produced the business outcome.

Conversely, Redis may have executed the command and sent a response, only for the response to drop on the network or be discarded by a client timeout.

Therefore:

```text
socket write completed != Redis command committed
socket timeout         != Redis command not committed
HTTP 500 from service  != Redis command not committed
```

### 2.2. Timeout Is a Client-Side Wait Limit

A command timeout usually means **the client did not receive a result within its wait window**. It is not necessarily a command cancellation on Redis.

If Redis already ran the command, cancelling a future/reactive subscription or timing out does not reverse the mutation.

Example:

```java
Mono<Long> result = reactiveRedisTemplate
    .opsForValue()
    .increment("orders:submitted")
    .timeout(Duration.ofSeconds(2));
```

If `.timeout(...)` emits an error, do not assume `INCR` never ran. Reactor's timeout manages the Publisher's wait expectation, not a Redis transaction rollback.

### 2.3. Redis Returning OK Also Has Limits

Even when the client receives a success reply, that result does not automatically guarantee:

- Every replica has received the write.
- AOF has been `fsync`ed to the desired durability level.
- The latest RDB snapshot includes the write.
- Another database committed the same write.
- A Pub/Sub message was processed by subscribers.
- After failover, the new primary definitely retains the write.

This lesson focuses on **duplicate writes from retries**. Yet when choosing anti-duplication defenses, also account for **writes lost after failover**, as the two issues are often intertwined.

## 3. Outcomes Possible After a Timeout

Suppose the command is:

```redis
INCR orders:submitted
```

A timed-out call can correspond to any of these states:

**Scenario A — Never executed:**

```text
Client never sent the command.
Redis did not modify the counter.
Retry is necessary if the business operation must still happen.
```

**Scenario B — Executed, response lost:**

```text
Redis incremented the counter.
Client does not know the result.
Directly retrying INCR increments a second time.
```

**Scenario C — Executed, response arrived late:**

```text
Application already treated the request as timed out.
Redis returned a response, yet the future is no longer listening.
An application retry may start while the old command is still in flight.
```

**Scenario D — Executed on old primary, later lost during failover:**

```text
Old primary accepted the write.
Write was not replicated/persisted sufficiently per architecture.
New primary does not have the result.
```

In Scenario D, whether the client saw `OK` or not, post-failover state may differ.

Because multiple scenarios are indistinguishable from a timeout alone, a good retry policy follows this rule:

```text
Has a stable request ID?
    |
    +-- Yes --> Retry with the exact same request ID via an idempotency mechanism.
    |
    +-- No  --> Do not auto-retry a non-idempotent write command;
                inspect business state or use reconciliation.
```

Do not guess "this looks like a network error" as justification to increment a counter again.

## 4. Idempotency: Re-Running a Command Without Changing Business Outcome

An operation is **idempotent** if applying the same operation multiple times produces no extra state changes beyond applying it once, within defined boundaries and preconditions.

Simple example:

```redis
SET config:banner "on"
SET config:banner "on"
```

With no interleaved writes and ignoring metadata/side effects, the key's final value remains `"on"`.

Conversely:

```redis
INCR sales:count
INCR sales:count
```

adds two units. `INCR` is **not idempotent**.

### 4.1. Final-State Idempotency Does Not Imply Identical Replies

Example:

```redis
SADD members user-7
```

The first call may return `1` (newly added), while the next returns `0` (already exists). The final set state matches, yet the replies differ.

Similarly:

```redis
DEL temp:key
```

The first call may return `1`, the next `0`. Repeated deletion is usually state-idempotent, **not return-value-idempotent**.

When a client times out after the first attempt, seeing `0` on retry does not prove the earlier attempt failed; it may have **succeeded**.

### 4.2. Idempotency Cannot Be Evaluated Apart from Concurrency

Example:

```text
Request A: SET order:101:status PAID
Request B: SET order:101:status CANCELLED
Request A times out and retries SET PAID
```

Timeline:

```text
t1: A -> PAID
t2: B -> CANCELLED
t3: A retries -> PAID
```

The retried `SET` overwrote B's newer state. Even though `SET key sameValue` looks idempotent in isolation, a late retry causes a **lost update** under interleaved operations.

Therefore, distinguish:

- **Idempotent operation:** repeating the exact request creates no extra side effects.
- **Concurrency correctness:** retries must not overwrite newer valid updates.
- **Durability:** results survive crashes/failovers.
- **Exactly-once business effect:** the business operation creates no duplicate side effects per request.

These four properties do not come automatically just because the Redis command is `SET`.

## 5. Classification Table of Redis Commands Under Retry

| Command | What Can Retrying the Raw Command Cause? | Notes |
|---|---|---|
| `GET key` | May read a different value updated by another writer | Read-only, no double write |
| `EXISTS key` | Return value varies with timing | Read-only |
| `TTL` / `PTTL` | TTL counts down naturally | Read-only, unstable reply |
| `SET key fixedValue` | May overwrite a newer record | Consider concurrency and TTL |
| `SET key value EX 60` | May **extend TTL** on retry | Not deadline-idempotent |
| `SET key value NX` | Retry may return false after initial success | Must check owner/request |
| `SET key value XX` | May overwrite a value changed by another request | No automatic concurrency guard |
| `DEL key` | Final state is usually absent if not recreated | Return count differs; a newly created key with same name can be deleted by mistake |
| `HSET hash field fixedValue` | May overwrite a newer value | Final-state idempotent only under proper conditions |
| `HINCRBY hash field 1` | Increments twice | Not idempotent |
| `INCR` / `INCRBY` | Increments twice | Not idempotent |
| `DECR` / `DECRBY` | Decrements twice | Not idempotent |
| `LPUSH` / `RPUSH` | Pushes element twice | Not idempotent |
| `LPOP` / `RPOP` | Pops two different elements | Retry can consume an extra work item |
| `SADD set member` | Same member is not duplicated | Reply differs; consider interleaved removals |
| `SREM set member` | Re-deleting changes nothing if not re-added | Consider concurrency |
| `ZADD zset score member` | May overwrite a newer score | Consider NX/XX/GT/LT flags and concurrency |
| `XADD stream * ...` | Appends another entry with a new Redis Stream ID | Easy to record duplicate events |
| `XACK stream group id` | Retry may return `0` | Usually safe for clearing PEL, does not prove business side effect |
| `PUBLISH channel payload` | Broadcasts message again | Subscribers may receive duplicates |
| `EVAL script ...` | Depends on script logic | Atomic execution does not equal idempotency |
| `EXEC` | Transaction may re-execute completely | Lost reply leaves commit status unknown |
| `RENAME old new` | Retry may fail or overwrite other data | Never blindly retry |

This table raises the right questions rather than declaring "all reads retry forever" or "every `SET` is safe." Each application must define the **business semantics** of a request.

### 5.1. TTL Is an Easily Overlooked Side Effect

Suppose:

```redis
SET otp:123 "123456" EX 60
```

Attempt 1 ran at `t0`. Client timed out and retried at `t0 + 10s`:

```redis
SET otp:123 "123456" EX 60
```

The new TTL starts from `t0 + 10s`, letting the OTP live 10 seconds longer than intended. If security policy mandates a fixed deadline, this is a logic bug.

One fix is storing an absolute deadline or keeping an idempotency record holding the initial request's deadline, rather than recomputing TTL from `now` on every retry.

### 5.2. Retrying SET NX Can Be Mistaken for Failure

Example:

```redis
SET payment:claim:evt-1 worker-A NX EX 300
```

Attempt 1 succeeded, reply lost. Retry returns `nil` because the key already exists. If the app interprets `nil` as "another worker claimed it," it might abandon work it actually owns.

Use a dedicated token/request ID:

```text
payment:claim:evt-1 -> requestId = req-42
```

After an error, check whether the current owner matches your request ID. Yet reading `GET` and seeing a match **still does not prove** external side effects finished. You also need processing states like `IN_PROGRESS`/`SUCCEEDED` and proper recovery.

## 6. Error Types in Spring Data Redis

Spring Data Redis typically translates connector errors into Spring DataAccess API exceptions. Exact class names and wrapping depth depend on command, library version, and connector such as Lettuce.

Commonly encountered types:

```text
RedisConnectionFailureException
QueryTimeoutException or translated timeout
RedisSystemException
DataAccessException
Lettuce RedisCommandTimeoutException (underlying cause)
Lettuce RedisConnectionException (underlying cause)
```

Do not build business logic on brittle error message strings like `"Connection closed"` or `"Command timed out"`; wrappers and messages can change across versions.

### 6.1. Which Exceptions Mean Definitely Not Committed?

When an error is **proven to arise before building/sending the command** (such as Java validation rejecting input prior to calling Redis), the application knows the operation was never sent.

However, for **network, timeout, or connection reset errors after an attempt begins**, treat write outcomes as **unknown** unless proven otherwise.

Even when a connector says "connection was closed," that rarely distinguishes:

```text
- Command never sent
- Partially sent
- Redis executed yet response lost
```

Retry policies based on exception types must combine **command type** and **an idempotency mechanism**, not just a list of "transient exceptions."

### 6.2. Never Catch Exception and Simply Call the Command Again

Dangerous pattern:

```java
public Long increment() {
    try {
        return redis.opsForValue().increment("sales:count");
    } catch (Exception ex) {
        return redis.opsForValue().increment("sales:count");
    }
}
```

If the first call incremented and lost the response, this code increments twice.

Increasing retry count does not make the bug go away:

```java
for (int attempt = 0; attempt < 5; attempt++) {
    try {
        return redis.opsForValue().increment("sales:count");
    } catch (Exception ignored) {
    }
}
```

During a prolonged glitch, the same business operation could execute multiple times.

### 6.3. Backoff Reduces Load, Does Not Fix Duplicates

Waiting between retries:

```text
100 ms -> 200 ms -> 400 ms -> 800 ms
```

prevents retry storms and eases network/Redis pressure after outages. Yet if the first command already ran, **waiting 800 ms and calling `INCR` again still runs it a second time**.

Backoff and idempotency solve **two separate problems**:

```text
Backoff       -> when to try again?
Idempotency   -> does trying again create extra side effects?
```

A sound retry strategy needs both whenever retrying non-idempotent work.

## 7. Lettuce: autoReconnect and In-Flight Commands

Spring Data Redis commonly uses **Lettuce** as its Redis driver. Lettuce includes connection management, auto-reconnect, command queuing, and asynchronous completion.

Distinguish:

- **Connection reconnect:** establishing a fresh Redis connection after the old one breaks.
- **Command resend/retry:** re-transmitting a previously issued request.
- **Application retry:** business service invoking a method again after an exception/timeout.
- **Idempotency:** ensuring the same request does not apply side effects twice.

These are not four synonyms.

### 7.1. Why Does Reconnect Not Guarantee Exactly-Once?

Suppose a command was sent over an old socket and Redis executed it. The client loses connectivity before the reply arrives. After reconnecting, if the command or business call is re-sent by client or application retry mechanisms, Redis can execute the same request a second time.

Do not make blanket claims that "the driver definitely always resends every command" or "the driver definitely never resends any command" without checking exact versions, configuration, and per-command state.

**Safe conclusion at the business layer:** neither driver retries nor application retries justify skipping idempotency for non-idempotent mutations.

### 7.2. Command Queueing While Disconnected

A client may let commands wait in a queue to send after reconnection, depending on options and connection mode. Trade-offs:

- Increases chance of commands completing after brief blips.
- Increases request latency.
- Can cause an HTTP request that already timed out to execute late.
- Grows queued commands and memory during extended outages.
- Creates risk of stale requests overwriting newer state upon reconnect.
- Makes it hard to separate user-cancelled requests from commands still queued.

Do not assume "HTTP request timed out" means every Redis command from that request vanished from all queues and transports.

### 7.3. Driver Options to Check by Version

When evaluating Lettuce, operators should know:

- Auto-reconnect policy.
- Disconnected command-queue behavior.
- Command timeout.
- Socket connect timeout.
- In-flight request limits.
- Cluster topology refresh/redirect handling.
- Service/framework retry policies.
- Whether calls are wrapped by Spring Retry, Resilience4j, or custom interceptors.

Do not assume you can configure a client to be "exactly-once safe" merely by raising timeouts or disabling reconnect. **Tweaking connection behavior can reduce certain cases, yet cannot eliminate lost responses after execution.**

## 8. Spring Retry and `@Retryable`: Scope Them Properly

A service can be annotated for automatic retries:

```java
@Retryable(
    maxAttempts = 3
)
public void submitOrder(String orderId) {
    redis.opsForValue().increment("orders:submitted");
}
```

If an attempt executes `INCR` yet throws because the reply was lost, the retry proxy calls the method again and increments once more.

`@Retryable` has no idea:

- Whether the business operation completed.
- Whether the Redis reply was lost.
- Whether side effects can be repeated.
- Whether an earlier attempt already emitted an event or sent an email.
- Which stable idempotency token to reuse.

### 8.1. Apply Retries at an Idempotency-Protected Layer

Better architecture:

```text
HTTP request has a stable requestId
     |
     v
Service calls command idempotent by requestId
     |
     +-- Succeeds --> return receipt/result
     |
     +-- Network timeout
              |
              +-- Backoff
              +-- Retry with same requestId
              +-- Retrieve existing receipt or execute once if absent
```

Spring Retry remains useful once the underlying operation handles duplicates safely.

### 8.2. Never Generate a Fresh requestId Inside Each Attempt

Wrong:

```java
@Retryable
public Result execute() {
    String requestId = UUID.randomUUID().toString();
    return performOnce(requestId);
}
```

Each retry gets a distinct ID; the server treats them as independent requests and cannot deduplicate across attempts.

Better:

```java
public Result execute(String stableRequestId) {
    return performOnce(stableRequestId);
}
```

Generate the request ID **before the retryable boundary**, or accept it from the client/API contract, and preserve it unchanged across every attempt of the same business operation.

If a caller retries HTTP after a timeout, the client must also resend **the exact same idempotency key**, never generating a new key per HTTP retry.

## 9. Idempotency Key: Identity of a Business Request

An **idempotency key** is a token identifying a single logical operation. Example:

```text
requestId = 0d50b92d-32aa-4e7e-8d0b-330f7a6bd3af
```

Over HTTP, clients can send:

```http
POST /api/orders/o-101/reserve
Idempotency-Key: 0d50b92d-32aa-4e7e-8d0b-330f7a6bd3af
Content-Type: application/json

{"sku":"sku-42","quantity":3}
```

If the client times out and retries the request, it reuses this exact key.

### 9.1. Bind an Idempotency Key to Immutable Payloads

If the same `requestId` is reused for two different actions:

```text
requestId = req-1, reserve quantity = 3
requestId = req-1, reserve quantity = 7
```

and the service merely returns the old receipt on the second call, the client might mistakenly believe quantity 7 was reserved.

Store or verify a **request fingerprint** alongside the idempotency key:

```text
requestId
operationName
tenantId
resourceId
canonicalPayloadHash
result/status
createdAt
expiresAt
```

When a key is reused with a different payload, reject with a conflict error rather than applying a second mutation.

### 9.2. Uniqueness Scope Must Be Explicit

A request ID often needs uniqueness scoped by:

```text
tenant + operation + requestId
```

Example:

```text
tenant=t-7
operation=reserve-stock
requestId=req-123
```

If only `requestId` is keyed while tenants can supply arbitrary strings, cross-tenant collisions can occur. If receipts share a namespace without checking operation, a request on one endpoint could collide with another endpoint.

Define the scope early to prevent bugs as the system grows.

### 9.3. Request IDs Do Not Replace Business Invariants

The same business order might still be submitted under **two different request IDs** due to a client bug or two separate processes. Request-ID idempotency prevents **replaying the same request**, not two independent requests attempting an invalid transition.

Still enforce invariants like:

```text
An Order can transition to PAID only once.
A Reservation can move to CONFIRMED only while PENDING.
A payment provider charge ID cannot be recorded twice.
```

That is why idempotency typically pairs with compare-and-set, unique constraints, versioning, or state machines.

## 10. Why `SET NX` Alone Before Doing Other Work Still Has Gaps

An initial idea:

```redis
SET dedupe:req-123 "processing" NX EX 3600
```

Followed in Java by:

```redis
INCR inventory:reserved
```

The flaw is that these are two independent steps.

**Case 1 — Guard written, business work never ran:**

```text
t1: SET dedupe:req-123 processing NX EX 3600 -> OK
t2: Process crashes before INCR
t3: Retry sees dedupe key and skips
```

The business operation never ran, yet the system thinks it succeeded.

**Case 2 — Business work ran before guard:**

```text
t1: INCR inventory:reserved -> succeeds
t2: Process crashes before SET dedupe
t3: Retry sees no guard
t4: INCR runs again
```

The business operation happened twice.

Conclusion:

> **A standalone Redis guard cannot guarantee exactly-once if it is not updated atomically with the side effect it protects.**

`SET NX` is useful for claims/locks with proper lifecycles, not as a transaction spanning separate commands or bridging Redis and external databases.

### 10.1. Guard TTL Is a Trade-Off

With a 1-hour guard TTL:

- Retries within 1 hour can be detected.
- Retries after 1 hour can re-execute the side effect.
- If the guard only stores `PROCESSING` and the worker crashes, one hour can leave the request stuck.
- If Redis eviction drops the guard early, duplicate protection expires prematurely.
- If Redis restores an older snapshot, both guard and state can roll back.

TTL must reflect the **business retry horizon and receipt retention obligation**, not an arbitrary constant.

## 11. Preventing Double Increments with a Lua Script

When both the side effect and idempotency receipt live in the **same Redis instance/hash slot**, you can combine request ID checking, mutation, and receipt storage inside one Lua script.

Example: increment a counter **at most once per request ID**, even if the client times out and retries.

Choose two keys:

```text
Counter:
    counter:{sku-42}:reserved

Request receipt:
    counter:{sku-42}:request:req-123
```

Both keys share the `{sku-42}` hash tag, required for Redis Cluster.

Script stored at `src/main/resources/lua/increment-once.lua`:

```lua
-- KEYS[1] = counter key
-- KEYS[2] = request receipt key
-- ARGV[1] = increment amount, positive integer string
-- ARGV[2] = receipt TTL milliseconds, positive integer string

if #KEYS ~= 2 or #ARGV ~= 2 then
    return redis.error_reply('INVALID_ARGUMENT_COUNT')
end

local amount = tonumber(ARGV[1])
local ttl = tonumber(ARGV[2])

if not amount or amount <= 0 or amount % 1 ~= 0 then
    return redis.error_reply('INVALID_INCREMENT')
end

if not ttl or ttl <= 0 or ttl % 1 ~= 0 then
    return redis.error_reply('INVALID_RECEIPT_TTL')
end

local existingResult = redis.call('GET', KEYS[2])

if existingResult then
    return tonumber(existingResult)
end

local updated = redis.call(
    'INCRBY',
    KEYS[1],
    amount
)

redis.call(
    'PSETEX',
    KEYS[2],
    ttl,
    tostring(updated)
)

return updated
```

### 11.1. Model When the First Command Succeeds but the Reply Is Lost

```text
Attempt 1: EVAL script, request req-123
    |
    +--> receipt absent
    +--> INCRBY counter 3
    +--> PSETEX receipt:req-123 -> result 103
    +--> Redis returns 103
    +--> network drops reply

Attempt 2: EVAL script, still request req-123
    |
    +--> receipt exists (103)
    +--> return 103
    +--> DOES NOT INCRBY a second time
```

Because commands in a Lua script execute without other clients' commands interleaving, two callers sending the same request ID cannot both take the "receipt absent" branch against the same live Redis state.

**Note:** Redis Lua scripts are atomic against command interleaving, **not automatically rolled back if a runtime error happens after writes**. In production, validate all inputs, types, overflows, and failure conditions before writing, and use explicit status/receipt contracts.

### 11.2. Spring Data Redis Service Example

Script configuration:

```java
package com.example.counter;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class IdempotentCounterScriptConfig {

    @Bean
    RedisScript<Long> incrementOnceScript() {
        return RedisScript.of(
            new ClassPathResource("lua/increment-once.lua"),
            Long.class
        );
    }
}
```

Service:

```java
package com.example.counter;

import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class ReservationCounterService {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> incrementOnceScript;

    public ReservationCounterService(
            StringRedisTemplate redis,
            RedisScript<Long> incrementOnceScript) {

        this.redis = redis;
        this.incrementOnceScript = incrementOnceScript;
    }

    public long reserveOnce(
            String sku,
            String requestId,
            long amount) {

        if (amount <= 0) {
            throw new IllegalArgumentException(
                "amount must be positive"
            );
        }

        if (requestId == null || requestId.isBlank()) {
            throw new IllegalArgumentException(
                "requestId is required"
            );
        }

        // In production: encode/validate sku and requestId
        // so {} characters are not injected and break the hash tag.
        String tag = "{" + sku + "}";
        String counterKey = "counter:" + tag + ":reserved";
        String receiptKey =
            "counter:" + tag + ":request:" + requestId;

        long receiptTtlMs =
            Duration.ofDays(1).toMillis();

        Long result = redis.execute(
            incrementOnceScript,
            List.of(counterKey, receiptKey),
            Long.toString(amount),
            Long.toString(receiptTtlMs)
        );

        if (result == null) {
            throw new IllegalStateException(
                "Redis script returned no result"
            );
        }

        return result;
    }
}
```

Key decisions:

- **The same `requestId`** is passed again on retry.
- `counterKey` and `receiptKey` share the **same hash tag**.
- Uses `StringRedisTemplate` so keys/ARGV serialize as strings expected by Lua.
- `RedisScript<Long>` maps Redis integer replies to `Long`.
- The receipt stores the **first execution's result**, so retries return the identical value.
- Receipt TTL bounds deduplication history, not counter TTL.
- `sku` and `requestId` here are illustrative; production must normalize/escape inputs so `{}` cannot corrupt hash tags or namespaces.

### 11.3. Bind Request ID to an Unchanging Payload

The simple script above uses the receipt key to recognize a request, yet **does not compare the new `amount` with the old `amount`**. If a caller reuses a request ID with a different increment amount, the script returns the old receipt and ignores the difference.

For public APIs, extend the receipt to store a fingerprint:

```text
receipt:req-123:
  requestHash = SHA256(canonicalPayload)
  status      = SUCCEEDED
  result      = 103
```

On retry:

- Matching hash: return receipt.
- Mismatched hash: return idempotency-key-reuse conflict error.
- Missing receipt: proceed with execution.
- Receipt in `PROCESSING`: handle per lease/recovery policy.

Store the receipt as a Hash controlled atomically in Lua, or use a transactional idempotency store.

### 11.4. Validate Data Types Before Writing

For instance, if `counterKey` holds a non-numeric String, `INCRBY` fails before writing the receipt. If `INCRBY` succeeds yet writing the receipt fails (e.g., OOM or runtime command error), the script could create a side effect without a receipt.

Therefore, use this Lua pattern to understand **atomic deduplication when steps succeed**; never mistake it for an absolute exactly-once guarantee under all Redis/storage/command faults.

A stricter design validates types, integer bounds, write policies, OOM, `noeviction`, receipt retention, and post-failover recovery.

### 11.5. Durability Limits Still Apply

Suppose attempt 1 executed `INCRBY` and saved the receipt, then the primary crashed before data was persisted or replicated to the new primary. Depending on persistence/failover, both counter and receipt can disappear.

If an external system already acted on `103`, a retry could mutate a rolled-back state; Lua alone cannot ensure end-to-end consistency.

Lua solves **races in live Redis within one slot**. It does not eliminate RDB/AOF/failover data loss, nor does it create a joint transaction with external databases.

## 12. Handling `SET NX` with a Request Token

For a task requiring only a temporary claim, you can use:

```redis
SET processing:{job-101} req-123 NX PX 30000
```

Replies:

- `OK`: key did not exist, claim created.
- `nil`: key already existed, claim not created.

Yet if the `OK` reply is lost, the retry receives `nil`. The application must inspect the owner:

```redis
GET processing:{job-101}
```

If the value is `req-123`, the earlier attempt may have created that claim. If it is another token, a different claimant owns it.

### 12.1. Do Not Merely Compare Tokens and Blindly Run Side Effects

Even when the key holds your token, two possibilities exist:

```text
- The earlier attempt only claimed the key and has not processed anything yet.
- The earlier attempt partially/fully processed the work, yet did not mark SUCCEEDED.
```

Thus, for serious business tasks, track states:

```text
NEW -> PROCESSING -> SUCCEEDED
                   -> FAILED_RETRYABLE
                   -> FAILED_FINAL
```

and you may need:

- Stored result/receipt.
- Lease ownership/expiry.
- Heartbeats or requeueing.
- Retries after timeout carrying the same request ID.
- Business checks when a `PROCESSING` state is abandoned.
- Safeguards against duplicate side effects while an old worker is still running.

A lock does not replace an idempotency record.

### 12.2. Token-Checked Lock Deletion

Never run:

```redis
DEL processing:{job-101}
```

in a `finally` block without checking ownership. The lock may have expired its TTL and been acquired by another process. A delayed `DEL` from the old process would delete the new owner's lock.

Use atomic compare-and-delete, such as Lua:

```lua
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end

return 0
```

This lock-safety rule directly relates to post-disconnect retries. Even with this, it still does not grant exactly-once semantics to work done outside Redis.

## 13. A `SET` with Request ID and Business State

Better than "SET and retry the raw SET" is turning the operation into a **conditional state transition**.

Example:

```text
Order o-101:
    PENDING -> PAID
```

If the `markPaid` HTTP request times out, a retry must not overwrite status to `PAID` if another flow already moved the order to `CANCELLED`.

A state transition considers:

```text
current status
expected status
new status
request ID
version
result/receipt
```

Implement via Lua across co-located keys, or inside a single Redis Hash with all relevant fields. Flow:

```text
Lua:
  receipt already exists?
      |
      +-- Yes -> return old result if payload hash matches
      |
      +-- No:
            does current status match expected?
                |
                +-- No -> return valid-state error
                |
                +-- Yes:
                     set nextStatus
                     record receipt
                     return success
```

This way, retrying the same request returns the recorded result without blindly overwriting newer state.

### 13.1. Idempotent Transition Differs from Blind SET

If you only run:

```redis
SET order:101:status PAID
```

a late retry overwrites newer transitions.

With an atomic check:

```text
PENDING -> PAID only if current == PENDING
```

a retry observing `PAID` must distinguish:

- This very request moved it to `PAID`.
- Another request moved it to `PAID`.
- There is a conflict/new version to handle.

Hence, a **request ID / result receipt** remains valuable even when the transition already checks `expectedState`.

## 14. Problems When Retrying Redis Streams XADD

A producer appends an event:

```redis
XADD orders:events * eventId evt-1001 type CREATED orderId o-101
```

Redis assigns a new ID, for example:

```text
1763000000123-0
```

If Redis recorded the entry yet the reply carrying the ID was lost, the producer may retry:

```redis
XADD orders:events * eventId evt-1001 type CREATED orderId o-101
```

Redis assigns a **different** ID:

```text
1763000000200-0
```

The stream now holds two entries:

```text
ID1 -> eventId evt-1001
ID2 -> eventId evt-1001
```

These are **two Redis records** for the same business event.

### 14.1. Redis Stream ID and Business eventId Are Different

- **Stream ID** identifies an entry in the Redis log.
- **Business eventId** identifies the business action to apply once.

The same `eventId` can appear in multiple Stream entries when producers retry `XADD *` after ambiguous outcomes.

Therefore, consumers need idempotency keyed by **`eventId`** when applying important side effects, not solely by Stream ID.

### 14.2. Should You Assign Fixed Stream IDs Manually to Deduplicate?

Redis `XADD` accepts explicit IDs per Stream semantics, yet IDs enforce strict monotonic ordering and should not be misused as a general-purpose idempotency key.

Retrying with an ID already present causes Redis to reject it for not being greater than the latest ID. If entries were trimmed or concurrent writes interleaved, interpreting that error is not as simple as "my event was already written."

Thus, choosing custom Redis Stream IDs **does not replace** requestId/business eventId design, deduplication receipts, and reconciliation.

### 14.3. Idempotent Producer XADD on the Same Slot

You can use Lua with:

```text
KEYS[1] = orders:{partition-7}:events   (Stream)
KEYS[2] = orders:{partition-7}:receipt:evt-1001
```

Pseudologic:

```text
If receipt already exists:
    return stored Stream ID.

If receipt does not exist:
    XADD to Stream.
    Store Stream ID in receipt.
    Return Stream ID.
```

Both keys must map to the same hash slot in Redis Cluster. Design TTL/retention carefully and keep in mind script runtime errors, eviction, and persistence rollbacks remain risks.

### 14.4. Producer DB Write and XADD Are Not Automatically Atomic

If a request runs:

```text
1. COMMIT order into PostgreSQL.
2. XADD OrderCreated into Redis Streams.
```

and loses connectivity after step 2, the client does not know whether the event was appended. Retrying `XADD` risks duplicates; not retrying risks dropping the event if the first attempt never ran.

A **transactional outbox** fits well when an event must reliably reflect a database commit:

```text
Inside one SQL transaction:
    INSERT/UPDATE order
    INSERT outbox_event(eventId, payload)

Worker:
    read outbox
    XADD into Redis Stream
    mark published (retryable)
```

Even with an outbox, an event can be published twice if `XADD` succeeds yet marking `published` fails. Consumers or producers still need idempotency by `eventId`.

## 15. Consumer Groups: Read Succeeded Yet XREADGROUP Response Lost

An easily overlooked scenario:

```text
worker-A calls XREADGROUP GROUP g worker-A STREAMS stream >
Redis picks entry E and adds E to the group's PEL.
Redis sends reply containing E.
Connection drops before worker receives the payload.
```

Redis already marked `E` as **pending** under `worker-A`, yet the application never saw or processed the payload.

When the worker reconnects and merely resumes:

```redis
XREADGROUP GROUP g worker-A STREAMS stream >
```

`>` reads **only new entries**, so `E` will not be redelivered on that read call.

### 15.1. PEL Enables Recovery

Monitor:

```redis
XPENDING stream g
XPENDING stream g - + 10
```

And handle recovery:

- Read **this consumer's own** pending history using `XREADGROUP ... 0`.
- Reclaim long-idle pending entries from dead/slow consumers via `XCLAIM` or `XAUTOCLAIM`.
- Call `XACK` only after processing completes per policy.
- For poison payloads, use retry limits/DLQ instead of ignoring the PEL.

Thus, a network drop after `XREADGROUP` can leave a **message stuck pending without the app ever seeing it**, not merely cause double processing.

### 15.2. XACK Timeout and Duplicate ACKs

After processing succeeds:

```redis
XACK stream g 1763000000123-0
```

If the reply is lost, the worker does not know whether the pending ID was removed.

Calling `XACK` again with the same ID usually causes no extra business side effect: it may return `0` since it was already ACKed. Yet **if the handler re-runs business logic before calling XACK**, side effects can repeat.

Rule:

```text
Retrying ACK for the same Stream ID
    differs from
Retrying the entire business handler + ACK
```

With a business handler idempotent by `eventId`, redelivery can still be handled safely.

## 16. Pub/Sub: Retrying PUBLISH Sends Duplicate Notifications

Suppose:

```redis
PUBLISH notifications.order '{"eventId":"evt-42","status":"PAID"}'
```

Redis delivers the message to active subscribers, yet the publisher's connection drops before receiving the subscriber count reply.

If the publisher retries:

```redis
PUBLISH notifications.order '{"eventId":"evt-42","status":"PAID"}'
```

online subscribers receive **two notifications** for the same business event.

Standard Redis Pub/Sub has no processing acknowledgment or backlog. Therefore:

- Never treat `PUBLISH`'s return count as a business ACK.
- Never assume retrying `PUBLISH` guarantees exactly-once delivery.
- Consumers can deduplicate by `eventId` when needed.
- If events must be processed reliably, consider Redis Streams or a durable message broker with consumer recovery.
- Real-time UIs can simply refresh current state rather than triggering irreversible side effects per Pub/Sub message.

### 16.1. Consumer Deduplication Lasts Only as Long as Its State Store

If a browser keeps an in-memory `Set` to ignore duplicate `eventId`s, refreshing the page clears that `Set`. To deduplicate across restarts, persist receipts in storage with suitable retention.

Not every notification needs strict deduplication; often "idempotent latest-state refresh" is cleaner than "increment once per notification."

## 17. MULTI/EXEC and Lost Responses

A Redis transaction runs:

```redis
MULTI
INCR orders:count
LPUSH orders:recent o-101
EXEC
```

If Redis executed `EXEC` yet the response was lost, the client cannot tell from a timeout alone whether the transaction ran.

Re-running the whole sequence:

```redis
MULTI
INCR orders:count
LPUSH orders:recent o-101
EXEC
```

increments the counter and pushes the item a second time.

**Transaction atomicity** only ensures inner commands run together per Redis transaction rules; **it does not make a transaction idempotent under replay**.

### 17.1. Redis Transactions Have No Built-In Request ID

To prevent replays, structure the transaction or Lua script to check a stored receipt/request ID inside the same atomic scope.

In Redis Cluster, all involved keys must obey the same-slot constraint for multi-key transactions/scripts.

### 17.2. Runtime Errors Must Also Be Distinguished

Redis `MULTI/EXEC` has no SQL-style rollback for runtime execution errors within individual commands. Succeeded commands can persist side effects even when another command in the transaction reports an error.

Design idempotency for **partial business effects caused by command failures**, not only dropped connections.

## 18. Pipelines and Batches: Multiple Commands Can Be Uncertain

Pipelining sends multiple commands to cut network round trips:

```text
SET key:A valueA
INCR count:B
LPUSH queue:C itemC
```

If the connection drops after Redis processes a subset of commands, the client may lack replies and not know which commands ran.

Pipelining does not turn a batch into a transaction and provides no all-or-nothing guarantee.

### 18.1. A Timeout Does Not Permit Retrying the Entire Batch

Suppose:

```text
Command 1 SET key:A -> ran
Command 2 INCR count:B -> ran
Command 3 LPUSH queue:C -> did not run
Connection drops.
```

If you retry the entire batch:

```text
SET key:A again
INCR count:B again
LPUSH queue:C first time
```

`count:B` increments twice.

Evaluate commands in a pipeline independently by ID/result and design batches for safe replay, or use transactions/scripts within an appropriate atomic scope.

### 18.2. Batch ACKs Do Not Equal Business Commits

Even when `executePipelined` returns a list of results, the app must map each entry to its command and account for dependencies. Never assume a set of Redis commands is atomic merely because they ran inside one Java method.

## 19. Redis Cluster and Failover: Writes Can Be Lost or Duplicated

Redis Cluster shards keys across hash slots and normally uses asynchronous replication between primaries and replicas. Disconnect scenarios can involve:

- Redis client hitting a node that no longer owns the slot.
- `MOVED`/`ASK` redirects.
- Primary restart/failover.
- Replica promoted before receiving recent writes.
- Network partition between application and nodes.
- Client retries during topology transitions.

### 19.1. Command Ran on Old Primary Yet Is Absent on New Primary

Example:

```text
t1: Primary A processes INCR count -> 101.
t2: Response lost.
t3: A dies before replica R receives the write.
t4: R is promoted; counter is still 100.
t5: Application retries INCR -> 101.
```

Here the retry sets the counter to `101` rather than `102`. Yet never cite this example to claim "retries are always safe after failover," because other cases exist where the replica did receive the first write, or a delayed response overlapped with a resend.

The takeaway is that **ambiguous outcomes depend on actual Redis state post-failover**, not just the exception type.

### 19.2. Deduplication Receipts Can Also Roll Back

If both receipt and mutation live in Redis:

```text
counter:{sku-42}:reserved
counter:{sku-42}:request:req-123
```

a Lua script updates both atomically while the primary is healthy. However, if neither was persisted/replicated before failover, the new primary lacks the receipt.

In that case, a retry can re-execute the side effect against the recovered state. External systems that observed the prior output may still need reconciliation.

When strict financial semantics are required, maintain **durable source-of-truth** records and durable idempotency rather than relying solely on volatile Redis state.

### 19.3. Same-Slot Is Required for Multi-Key Lua

Example:

```text
inventory:{sku-42}:available
inventory:{sku-42}:receipt:req-123
```

Both keys share `{sku-42}`, allowing them in a single Redis Cluster script under same-slot rules.

If the receipt key were instead:

```text
idempotency:req-123
```

it could map to another slot, causing `CROSSSLOT` or Cluster rejection.

Do not "solve" this by putting **all system-wide receipts** under a single `{global}` hash tag. That creates hot slots; partition receipts by business aggregate instead.

### 19.4. WAIT and WAITAOF Do Not Create Exactly-Once

Redis can support:

```redis
WAIT ...
WAITAOF ...
```

depending on version and config, to wait for specified replication/persistence progress. These commands improve durability visibility within supported bounds, yet:

- They are not distributed transactions between Redis and external databases.
- They do not make `INCR` idempotent on retry.
- They do not eliminate all failover/partition risks.
- You must respect connection/session ordering between writes and `WAIT`/`WAITAOF`.
- They reflect only the contract of your specific version/deployment.

Persistence, replication, fencing, and idempotency remain distinct architectural decisions.

## 20. RDB/AOF and Duplicate Writes After Restore

Suppose the application received a result from Redis, while the server uses periodic RDB snapshots. Redis crashes and restores an older snapshot:

```text
10:00 snapshot: counter = 100
10:02 INCR counter -> 101, client may or may not have reply
10:03 Redis crashes, restores snapshot counter = 100
```

Retrying the same request can increment the counter from 100 to 101 again.

If an external system already recorded `101`, we face an end-to-end reconciliation mismatch. The restored Redis state has no memory of the earlier request.

AOF with appropriate `fsync` policies narrows the data-loss window, yet still does not make writes exactly-once across all failures. When Redis is a rebuildable cache, rolling back and rebuilding from the durable source is normal. When Redis is the sole record of business effects, re-evaluate data architecture and SLAs.

### 20.1. One Request Can Be Both Lost and Duplicated Across Different Systems

Example:

```text
t1: Redis INCR stock:reserved -> 101.
t2: HTTP response records 101 in the database.
t3: Redis crashes, restores counter to 100.
t4: Caller retries request.
t5: Redis INCR stock:reserved -> 101.
```

From Redis's current viewpoint, the counter incremented once. From the business database's viewpoint, the event may have been processed twice across steps.

This is why you must define **which system is the source of truth**, where receipts live, and where transaction boundaries sit.

## 21. Preventing Duplicate Side Effects with an External Database

If a workflow updates PostgreSQL/MySQL and Redis, a Lua script cannot create an atomic transaction spanning both.

Pattern:

```text
HTTP request
    |
    +--> Redis SET dedupe:request
    |
    +--> SQL INSERT/UPDATE
```

has a gap if a crash occurs between the two steps.

### 21.1. Unique Constraint on eventId Inside an SQL Transaction

Example table:

```sql
CREATE TABLE processed_requests (
    request_id VARCHAR(100) PRIMARY KEY,
    payload_hash VARCHAR(128) NOT NULL,
    result_code VARCHAR(40) NOT NULL,
    processed_at TIMESTAMP NOT NULL
);
```

Inside the **same database transaction** as the business update:

```text
BEGIN
    INSERT processed_requests(requestId, payloadHash, ...)
    if conflict:
        verify same payload, read stored result
        do not apply business update a second time
    if new insert:
        update business tables
COMMIT
```

If Redis/HTTP fails after the SQL commit, retries hit the unique constraint and return the stored receipt/result without repeating the side effect.

Exact SQL syntax like `INSERT ... ON CONFLICT` or `INSERT IGNORE` depends on the database. Design transaction isolation and concurrency handling carefully.

### 21.2. Why Is Caching the Idempotency Record in Redis Insufficient?

You can cache receipts in Redis for fast lookups, yet when the authoritative receipt lives in SQL, a cache miss or Redis failover must never mean "this request never ran."

Flow:

```text
Check Redis receipt
    |
    +--> Found: return fast if receipt is valid
    |
    +--> Missing: check authoritative SQL receipt
          |
          +--> Found: repopulate cache, return result
          +--> Not found: create/apply business logic inside SQL transaction
```

Redis serves as an accelerator; **the final decision** relies on a receipt store matching the durability and atomicity of the business data.

### 21.3. External Side Effects Need Their Own Contract

Sending emails, calling payment gateways, or issuing invoices via external APIs sits outside the application's SQL transaction.

Strategies:

- Transactional outbox for outbound calls.
- Provider-supported idempotency keys.
- Storing request/response receipts and delivery status.
- Reconciliation/compensation on timeouts with ambiguous outcomes.
- Never generating a fresh request ID when retrying the same operation.

Payment charge example:

```text
requestId = charge-evt-1001

Attempt 1:
  paymentProvider.charge(idempotencyKey=charge-evt-1001)
  -> provider processes yet response times out

Attempt 2:
  paymentProvider.charge(idempotencyKey=charge-evt-1001)
  -> provider returns the earlier result
```

This works only if the provider **genuinely supports an idempotency contract** with well-understood retention and scope. Otherwise, perform a status lookup/reconciliation before retrying the charge.

## 22. Building an HTTP API with Explicit Idempotency

Example controller accepting a request ID:

```java
package com.example.inventory;

import java.util.UUID;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@RestController
@RequestMapping("/api/inventory")
public class InventoryController {

    private final ReservationCounterService reservations;

    public InventoryController(
            ReservationCounterService reservations) {
        this.reservations = reservations;
    }

    @PostMapping("/{sku}/reserve")
    public ReserveResponse reserve(
            @PathVariable String sku,
            @RequestHeader("Idempotency-Key") String requestId) {

        if (requestId.isBlank() || requestId.length() > 128) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Invalid idempotency key"
            );
        }

        long totalReserved =
            reservations.reserveOnce(sku, requestId, 1L);

        return new ReserveResponse(
            sku,
            requestId,
            totalReserved
        );
    }

    public record ReserveResponse(
        String sku,
        String requestId,
        long totalReserved
    ) {}
}
```

This example merely wires a `requestId` to the Redis script from Section 11. Production additionally needs:

- Authentication/authorization and scoping `requestId` per tenant.
- SKU validation so Redis key structure cannot be injected.
- Request body/query fingerprinting.
- Distinguishing Redis timeouts from business conflicts.
- Result receipt TTL policies.
- Business invariants on available stock, not only incrementing `reserved`.
- Rate limiting / abuse protection.
- Receipt durability matching business requirements.

Never generate `UUID.randomUUID()` inside the controller to substitute for a **client retry's missing header** when clients need a stable token across HTTP attempts. The server may issue tokens in a separate initialization step if the API contract follows that pattern.

### 22.1. HTTP Responses When the Outcome Is Uncertain

If a Redis write times out after it may have executed, returning an error claiming "not executed" is misleading.

Depending on business rules, you can:

- Return a temporary error asking the client to retry **with the exact same idempotency key**.
- Return `PROCESSING`/`UNKNOWN` status plus an operation ID so the client can query status.
- Return `202 Accepted` once work has been durably accepted in a suitable queue/DB.
- After retry, return the stored receipt if completed.
- Never return `200 SUCCESS` for a business operation without sufficient proof.

HTTP status codes are part of the business contract. `202 Accepted` does not prove persistence by itself; use it only when the architecture backs the commitment the response advertises.

## 23. Reactive Redis and Cancellation

A WebFlux application:

```java
Mono<Long> result = reactiveRedisTemplate
    .opsForValue()
    .increment("orders:submitted");
```

When an HTTP client disconnects or a `timeout` operator triggers, Reactor cancellation occurs. However, if the command was already sent to Redis, cancellation **does not necessarily abort the side effect**.

Flawed mental model:

```text
Client closes browser
    -> Reactor cancels
    -> Definitely Redis did not run INCR
```

Accurate view:

```text
Client closes browser
    -> downstream application stops waiting
    -> Redis command may be:
         not sent / queued / already executed / replying
```

For critical writes, do not tie business completion solely to whether the HTTP connection stays open. Persist a command/operation record and let a worker process it independently with idempotency.

### 23.1. Do Not Arbitrarily Call `.subscribe()` to "Ensure It Runs"

Dangerous example:

```java
public Mono<Void> submit() {
    redis.opsForValue()
        .increment("orders:submitted")
        .subscribe();

    return Mono.empty();
}
```

The system returns an HTTP response before knowing whether Redis succeeded or failed; exceptions escape the request flow, making retries and monitoring hard to control.

Return the Publisher instead:

```java
public Mono<Long> submit() {
    return redis.opsForValue()
        .increment("orders:submitted");
}
```

Still, if requests can be retried, replace direct `INCR` with an idempotent operation keyed by `requestId`. Reactive composition **does not provide exactly-once semantics automatically**.

### 23.2. Reactor retryWhen Is Not Automatically Idempotent

Example:

```java
return redis.opsForValue()
    .increment("orders:submitted")
    .retryWhen(
        Retry.backoff(
            3,
            Duration.ofMillis(200)
        )
    );
```

A `Mono` erroring after `INCR` can be resubscribed, re-executing the side effect. `retryWhen` is purely a subscription retry operator; it does not know Redis already applied an increment.

When retries are required, retry **a publisher representing an operation with an atomic `requestId` and receipt**, never an unprotected raw `INCR`.

## 24. Is Reading State After a Timeout Enough to Decide?

A commonly proposed workaround:

```text
INCR timed out.
GET counter.
If value increased, assume INCR succeeded.
```

This approach is usually **insufficient** under concurrency.

Example:

```text
Initial counter = 100.
Request A sends INCR, response lost.
Request B also runs INCR.
A reads GET -> 102.
```

Seeing `102`, A cannot tell whether:

- Both A and B incremented once.
- Only B incremented and another request C incremented.
- A retried and incremented twice.
- Another writer reset the counter.

An aggregate number cannot be attributed unambiguously to one operation ID without correlation metadata.

### 24.1. When Is Read-After-Timeout Useful?

It helps when:

- The operation has a distinct ID/receipt.
- There are no concurrent writers, or versioning/CAS is used.
- A business invariant allows verification.
- Reads target the appropriate source of truth.
- Failover/replica staleness is accounted for.

For instance, `GET receipt:req-123` after a timeout asks a far sharper question than `GET counter`, because the receipt binds directly to that request.

Still, a **missing receipt** does not prove the request never ran if the receipt could be lost to TTL, eviction, persistence rollback, or a failure between mutation and receipt write.

## 25. Choosing Retries by Operation Kind

A reasonable policy matrix:

| Operation Kind | Retry on Connection Timeout? | Conditions |
|---|---|---|
| `GET` cache | Yes | Bound attempts/time budget, avoid load storms |
| `EXISTS`/`TTL` | Yes | Tolerate state changing between reads |
| `SET fixed value` in rebuildable cache | Yes | Do not overwrite newer versions or extend TTL wrongly |
| `DEL` cache key | Yes | Do not unintentionally delete a fresh incarnation with the same name |
| `INCR` business counter | Do not blindly retry | Lua receipt / unique request ID or durable transaction |
| `LPUSH` job | Do not blindly retry | Dedupe / enqueue receipt or queue semantics |
| `XADD event` | Do not blindly retry | EventId + outbox/dedupe |
| `PUBLISH` telemetry | If duplicates acceptable | Consumers can dedupe or ignore duplicates |
| Critical business `PUBLISH` | Do not use as sole mechanism | Stream/broker with ACK/recovery |
| `XACK id` | Usually safe to repeat same ID | Do not re-run handler unless idempotent |
| Lua script idempotent by `requestId` | Yes | Receipt still valid, same slot, required durability met |
| SQL transaction with unique `requestId` | Yes | Retry policy based on transaction/result lookup |
| Payment API | Only per provider contract | Idempotency key, status lookup, and reconciliation |

### 25.1. Balancing Retries and Deadlines

Do not pick only an attempt count. Specify:

```text
Total request deadline
Per-attempt command timeout
Backoff + jitter
Max concurrency
Retryable exception categories
Circuit breaker / bulkhead
Idempotency retention horizon
```

If the HTTP client times out after 2 seconds while the backend keeps retrying a write for 30 seconds after the client gave up, the system must record the operation ID and let the client poll the result later.

### 25.2. Avoiding Retry Storms

When a Redis primary fails, thousands of application instances can time out together. If all retry immediately, the recovering Redis gets slammed with traffic.

Use:

- Exponential backoff.
- Random jitter.
- Retry budgets.
- Bounded concurrency.
- Circuit breakers during prolonged errors.
- Bounded queues when deferral is appropriate.
- Deadlines and cancellation for work not yet accepted.
- Monitoring Redis load, not just success rates.

These protect availability; **they do not replace idempotency**.

## 26. `@Transactional` and Redis Writes

A Java service might look like:

```java
@Transactional
public void payOrder(...) {
    orderRepository.save(...);
    redis.opsForValue().increment("payments:count");
}
```

When `@Transactional` manages an SQL database transaction, it **does not automatically** enroll Redis commands into the same ACID transaction.

If Redis `INCR` succeeds yet the SQL transaction rolls back, the two systems diverge. If SQL commits yet Redis times out, it is unknown whether the counter incremented.

Even with Spring Data Redis's transaction support, Redis `MULTI/EXEC` does not combine with an external database transaction into a distributed two-phase commit.

### 26.1. Outbox to Bridge SQL Commits with Event Emission

A common structure:

```text
SQL transaction:
    UPDATE order
    INSERT outbox_event(eventId, payload)
    COMMIT

Background publisher:
    read outbox_event
    XADD Redis Stream
    save published status after success
    retry on timeout

Consumer:
    process idempotently by eventId
    ACK after success
```

An outbox guarantees the **intent to publish** survives app crashes after SQL commit. Still, publishing from the outbox can create a duplicate entry if `XADD` succeeds yet the confirmation is lost.

Thus consumers still need inbox/processed-event uniqueness or idempotent producer enqueueing.

## 27. Idempotency Keys Have TTLs, Yet Business Retries Can Arrive Late

Suppose a receipt is stored as:

```redis
SET receipt:req-123 SUCCESS EX 3600
```

One hour later, the key expires. If a dead-letter queue replays the message two days later with the same request ID, the system may treat it as brand new and execute the side effect a second time.

Choosing receipt TTL must answer:

- What is the maximum delay before a client can retry?
- How long can a message sit in a queue?
- How late can a DLQ be replayed?
- Are there manual retries weeks later?
- How long does the business contract mandate retaining receipts?
- Are audit/legal records required?
- Does Redis have enough RAM to hold receipts that long?
- Could an eviction policy drop receipts before TTL?

If the retry horizon is long, store receipts in storage with matching durability and retention, such as a database.

### 27.1. Never Rely on Keyspace Expiration Events to Archive Mandatory Receipts

Redis keyspace notifications are best-effort Pub/Sub. Never rely on `expired` events to drive durable archiving/cleanup workflows after TTL.

If idempotency records require long retention for compliance or auditing, persist them in appropriate durable storage with dedicated retention jobs.

### 27.2. Goal: Request IDs Must Never Be Reused

Even after Redis TTL expires, if a client accidentally reuses the same key for a new business action, the app cannot easily tell a stale retry from a new request.

Enforce request ID uniqueness within scope and prohibit reuse throughout the system's committed retention window.

## 28. Newly Written Data Can Be Deleted by a Late `DEL` Retry

A subtle bug:

```text
t1: Request A deletes session:123 via DEL.
t2: A's DEL response is lost.
t3: Request B creates a new session with the same key session:123.
t4: A retries DEL session:123.
```

A's retry deletes **B's brand-new session**.

This is why `DEL` is not always safe simply because deleting an absent key twice leaves the same state when **no key recreation occurs in between**.

### 28.1. Generation/Version-Based Solutions

Instead of reusing the same key across generations:

```text
session:123
```

use:

```text
session:123:generation:7
session:123:generation:8
```

Or store an owner/version in the value and delete only if the version matches using Lua compare-and-delete.

Example:

```lua
-- KEYS[1]: key
-- ARGV[1]: expected token/version
if redis.call('GET', KEYS[1]) == ARGV[1] then
    return redis.call('DEL', KEYS[1])
end
return 0
```

Versioning lets retries delete the stale session without accidentally wiping a newly created session.

### 28.2. Delete-and-Recreate Also Affects Spring Cache

A cache invalidation:

```java
redis.delete("product:101");
```

can be retried late after another request already repopulated the cache. If the goal is simply "eventual cache reload," deleting again may be tolerable. Yet if deleting triggers expensive database load or the fresh entry carries a newer version, account for that side effect.

Idempotency must be evaluated at the **system and business level**, not only by a single key's final state.

## 29. Deduplicating with a Redis Set: Is It Enough?

One idea:

```redis
SADD processed-events evt-1001
```

`SADD` with the same member is membership-idempotent, yet if the app writes:

```text
SADD processed-events evt-1001
if returns 1:
    call payment API
```

flaws remain:

```text
SADD succeeds, reply lost.
Client retries, SADD returns 0.
Payment API may never have been called.
```

Or:

```text
Payment API succeeds.
Application crashes before SADD.
Retry -> payment API runs twice.
```

Adding `eventId` to a Redis Set shows a request was **registered** in a narrow sense, yet does not prove external side effects completed.

### 29.1. When Side Effects Live Inside Redis

If all logic updating both business state and the deduplication Set runs inside one Lua script on the same hash slot, it achieves atomicity in live Redis (subject to the runtime-error and failover caveats noted above).

### 29.2. When Side Effects Live Outside Redis

You need a transaction/contract in the system owning the side effect, or a workflow with persisted state and reconciliation. No single Redis command creates a joint ACID transaction with an email gateway or an independent SQL database.

## 30. Distinguishing an Executed Command from a Completed Operation

A business operation may involve:

```text
1. Validate request.
2. Reserve stock.
3. Charge payment.
4. Update order status.
5. Publish event.
6. Return HTTP response.
```

If Redis connectivity drops at step 2, you cannot equate retrying **the whole operation** with retrying one command. Potentially:

- Stock was reserved.
- Payment was not charged.
- Order was not updated.
- Event was not published.

Retrying the whole flow without a state machine can reserve stock twice.

### 30.1. Use an Operation State Machine

Example:

```text
NEW
  |
  v
RESERVING
  |
  +--> RESERVE_CONFIRMED
           |
           v
       CHARGING
           |
           +--> PAYMENT_CONFIRMED
                       |
                       v
                     DONE
```

Each step needs its own idempotency token or a provider-scoped step token, plus durable state persistence.

On timeout, the coordinator asks **which step completed** before retrying. If the outcome is uncertain and no lookup exists, transition to `UNKNOWN`/manual reconciliation rather than blindly repeating risky side effects.

### 30.2. Sagas and Compensation Are Not Automatic Rollbacks

If reservation succeeded yet charging failed, you may need a compensating action to release the reservation.

Yet compensation itself can time out, be retried, and cause duplicates unless idempotent. Therefore, every forward step and compensation step needs its own token and state tracking.

## 31. You Cannot Get End-to-End Exactly-Once from Retries Alone

To achieve an "executed once" business effect, systems typically rely on patterns such as:

- Storing the idempotency receipt **in the same transaction** as the business mutation.
- Enforcing unique constraints by `eventId`/`requestId` in the authoritative datastore.
- Using transactional outbox/inbox tables to record and dispatch side effects.
- Using external provider idempotency keys under explicit contracts.
- Designing deterministic/idempotent state transitions.
- Reconciling when outcomes are `unknown`.
- Governing duplicate delivery and ordering.

**Exactly-once message delivery** and **exactly-once business effect** are not synonyms. A broker may redeliver a message several times while the consumer applies one effect via inbox deduplication. Conversely, a command delivered once can trigger two side effects due to uncontrolled application retries.

### 31.1. Guarantee Comparison Table

| Concept | What Does It Mean? | Prevents Double Side Effects? |
|---|---|---|
| TCP transport | Transports bytes | No |
| Redis response `OK` | Command succeeded at command level | Does not stop late retries |
| Atomic Redis command | One command cannot be interleaved | No if the command is executed a second time |
| Atomic Lua script | Redis logic sequence runs uninterrupted | Only if script logic deduplicates |
| Redis transaction | Groups commands under `MULTI/EXEC` semantics | No if the transaction is replayed |
| Redis PEL / `XACK` | Tracks delivery in consumer group | Does not automatically prevent business duplicates |
| Idempotency receipt | Recognizes previously applied requests | Yes within receipt durability/retention/atomicity bounds |
| SQL unique constraint + transaction | Blocks duplicate writes in the same transaction | Stronger for business state stored in SQL |
| Outbox / inbox | Tracks publish/process across restarts | Reduces loss/duplicates when paired with idempotency |
| AOF / replication | Reduces state-loss risk | Does not make commands idempotent |

## 32. Observability and Logging When Redis Connections Drop

To investigate a double-write incident, logs need proper correlation.

Example structured log:

```json
{
  "operationId": "reserve-evt-1001",
  "requestId": "req-123",
  "commandFamily": "redis-lua-reserve-once",
  "aggregateId": "sku-42",
  "attempt": 2,
  "outcome": "TIMEOUT_UNKNOWN",
  "elapsedMs": 2150,
  "redisNode": "primary-2",
  "traceId": "trace-abc"
}
```

Never log Redis passwords, secret tokens, or payloads containing unnecessary PII. When keys contain sensitive data, log safe identifiers or hashes.

### 32.1. Metrics to Track

| Metric | Purpose |
|---|---|
| Redis command timeout count | Spot failures without replies |
| Connection disconnect/reconnect | Detect network instability |
| Retry attempt count | Monitor retry storms |
| Unknown-outcome operations | Count operations with uncertain outcomes |
| Idempotency hit count | Count retries resolved via existing receipts |
| Idempotency key conflicts | Spot keys reused with differing payloads |
| Receipt missing/expired count | Spot retention exhaustion risks |
| Lua business error rate | Separate validation/condition errors from timeouts |
| Event duplicate rate | Measure duplicate `eventId` occurrences |
| PEL pending / oldest idle | Spot Stream messages needing recovery |
| SQL unique-conflict count | Track already-processed events |
| Replication lag / failover | Correlate state loss after failover |
| RDB / AOF persistence health | Assess receipt/business-state durability |
| Handler latency p95/p99 | Tune timeouts and retry budgets |

Never assume every `RedisConnectionFailureException` means the business operation definitely failed. Label outcomes as `UNKNOWN` when appropriate.

### 32.2. Tracing from HTTP to Redis

A request ID should flow through:

```text
HTTP Idempotency-Key
       |
       v
Business operation
       |
       +--> Redis receipt key
       |
       +--> Logs and tracing
       |
       +--> Event envelope in Stream
       |
       +--> SQL processed_requests
```

During an investigation, operators can ask:

```text
Does request req-123 have a receipt?
What was the receipt result?
How many times did eventId enter the Stream?
Did the consumer apply the business effect?
Does the database hold the unique record?
Did a failover or backup rollback happen in that window?
```

Without a unifying ID across layers, it is nearly impossible to prove whether an operation ran after a reply was lost.

## 33. Testing Failures with Fault Injection

Standard tests only check that Redis works and returns OK. They miss the case where **the command executed yet the response never reached the client**.

A strong test suite needs at least two independent scenarios:

**A. Request never reached Redis:**

```text
Network blocked before command is sent.
Client times out.
Retry with same requestId.
Expected: mutation applied exactly once.
```

**B. Redis executed, yet reply was lost:**

```text
Command reaches Redis.
Redis applies mutation and saves receipt.
Network drops/blocks response.
Client times out.
Retry with same requestId.
Expected: result returned from receipt, no second increment.
```

Scenario B is vital. Simply shutting down Redis before sending commands only tests Scenario A.

### 33.1. Tools and Lab Setup

Locally, you can use:

- Toxiproxy or a testing network proxy.
- Network namespaces / firewall rules in a test environment.
- Testcontainers paired with a proxy.
- An adapter-layer mock/fake that deliberately throws a timeout **after calling real Redis successfully**.
- Real integration tests against a test standalone/Cluster Redis.
- Controlled chaos testing in staging environments.

Never sever networks or kill Redis in production to test these exercises without authorization and rollback runbooks.

### 33.2. Simulating a Lost Response at the Service Layer

Conceptual test adapter example:

```java
public final class FailAfterWriteAdapter {

    private final ReservationCounterService delegate;
    private boolean firstCall = true;

    public FailAfterWriteAdapter(
            ReservationCounterService delegate) {
        this.delegate = delegate;
    }

    public long reserveOnce(
            String sku,
            String requestId,
            long amount) {

        long applied = delegate.reserveOnce(
            sku, requestId, amount
        );

        if (firstCall) {
            firstCall = false;

            // Simulate: Redis finished running, client does not know.
            throw new IllegalStateException(
                "Simulated reply loss after successful write"
            );
        }

        return applied;
    }
}
```

This is an **application-layer simulation**, not an exact reproduction of TCP or Lettuce socket behavior. It verifies an essential invariant: retrying with the same `requestId` after an attempt that already executed **does not increment the counter a second time**.

### 33.3. Useful Assertions

```text
Given initial counter = 100.
Attempt 1 with requestId=req-123, amount=3:
    Redis executes, real state becomes 103
    test forces client to observe a timeout

Attempt 2 with requestId=req-123, amount=3:
    returns 103
    counter remains 103

Attempt 3 with requestId=req-456, amount=3:
    returns 106
    counter becomes 106
```

This test verifies request-ID deduplication in live Redis within the receipt TTL window. Add crash/failover and retention tests if business rules demand stronger durability.

## 34. Testing Races Between Two Concurrent Requests with the Same Idempotency Key

A race happens when two HTTP requests sharing the same `Idempotency-Key` arrive concurrently:

```text
Client retries very fast or gateway sends a duplicate.
Requests A and B hit two separate Spring instances.
```

If code does:

```text
GET receipt
if missing:
    INCR
    SET receipt
```

both requests can observe the receipt missing and increment twice.

Using a Lua script that updates both receipt and mutation in one execution on the same slot eliminates this race.

Test scenario:

```text
100 concurrent requests:
    same SKU = sku-42
    same request ID = req-same
    amount = 1

Expected:
    Counter increases by exactly 1.
    All successful responses return the same business result.
```

Next test:

```text
100 concurrent requests:
    same SKU
    distinct request IDs

Expected:
    Counter increases by 100, absent other errors and with
    each request accepted once.
```

This verifies correctness in live Redis. Do not treat a single passing run as proof against failover or retention losses.

## 35. Testing Concurrency with `SET` and Data Versioning

Another case tests lost updates:

```text
Initial order status = PENDING
Request A intends -> PAID
Request B intends -> CANCELLED
A times out and retries late
```

With a blind `SET`:

```redis
SET order:101:status PAID
```

after B wrote `CANCELLED`, A overwrites it.

Replace with version-aware transitions:

```text
State:
   status = PENDING
   version = 10

A:
   expectedVersion = 10
   target = PAID

B:
   expectedVersion = 10
   target = CANCELLED
```

A script checking `version == 10` and incrementing version on transition lets only one request succeed. Retries must also check the receipt for that same `requestId` so a replay is not misread as a business conflict.

**Version/CAS prevents lost updates; receipt/request ID prevents replaying the same operation.** The two complement each other.

## 36. Hands-On Exercise 1 — Why Does `INCR` Double-Increment?

Create a counter in a test Redis:

```redis
SET lab:counter 100
INCR lab:counter
INCR lab:counter
GET lab:counter
```

Explain why re-running `INCR` after a timeout can push the counter to `102` when the business intent was a single increment.

Write out two timelines: request never reached Redis vs. request executed yet reply was lost. From the perspective of a client observing a timeout, which cases can it distinguish?

## 37. Hands-On Exercise 2 — Retrying `SET` and TTL

Create:

```redis
SET lab:otp "123456" EX 30
```

Wait briefly, then repeat the exact same command. Compare `PTTL` before and after the retry.

Answer:

- Why does the final value match while the expiration deadline shifts?
- If the OTP must expire exactly 30 seconds after initial issuance, what should be stored?
- Is `SET ... KEEPTTL` a universal solution for every OTP-creation flow?

## 38. Hands-On Exercise 3 — Lua Idempotency

Use `increment-once.lua` from Section 11.

Initialize:

```redis
SET counter:{sku-42}:reserved 100
```

Call the service:

```java
reserveOnce("sku-42", "req-123", 3);
```

Then call again with **the exact same request ID**:

```java
reserveOnce("sku-42", "req-123", 3);
```

Expected:

```text
Call 1 returns 103.
Call 2 returns 103.
Final counter = 103.
```

Next call:

```java
reserveOnce("sku-42", "req-456", 3);
```

Expected counter becomes `106`.

Discuss what must be added if a second call with `req-123` passes `amount` 7.

## 39. Hands-On Exercise 4 — Simulating a Lost Response

Use a test adapter or fault proxy to make the first attempt **execute against Redis and then throw a timeout** toward the caller. Retry with the same `requestId`.

Compare two versions:

```text
Version A: direct INCR
Version B: Lua receipt + INCR
```

Measure the counter before and after and explain why Version B prevents double increments in live Redis.

You do not need to break production Redis to simulate lost responses.

## 40. Hands-On Exercise 5 — Redis Streams `XADD *`

In a lab:

```redis
XADD lab:events * eventId evt-1 type CREATED
XADD lab:events * eventId evt-1 type CREATED
XRANGE lab:events - +
```

Observe two entries with distinct Redis IDs despite identical `eventId`s.

Discuss:

- Why must business `eventId` and Stream ID stay separate?
- Where can consumers deduplicate by `eventId`?
- If a publisher commits SQL and runs `XADD` then times out, how does an outbox help?
- If deduplication receipts live in Redis, how do retention and failover affect them?

## 41. Hands-On Exercise 6 — PEL When `XREADGROUP` Reply Is Lost

Create:

```redis
XGROUP CREATE lab:jobs lab-workers 0 MKSTREAM
XADD lab:jobs * jobId job-1
```

Have `worker-A` read the entry while a test adapter drops the response before reaching the handler. Inspect:

```redis
XPENDING lab:jobs lab-workers
```

Then run:

```redis
XREADGROUP GROUP lab-workers worker-A STREAMS lab:jobs 0
```

or recover with `XAUTOCLAIM` from another worker after an idle threshold.

Explain why simply calling `XREADGROUP ... >` does not reprocess entries already pending from the prior read.

## 42. Hands-On Exercise 7 — Delete and Recreate

In a test environment:

```redis
SET lab:session:1 old-token
DEL lab:session:1
SET lab:session:1 new-token
```

Simulate a late retry of `DEL`. Observe the new session being deleted.

Design a compare-and-delete Lua script accepting an expected token or version so only the old incarnation is deleted.

## 43. Hands-On Exercise 8 — Redis Failover and Receipt Rollback

Use a test environment with configured replication/persistence where failover can be simulated safely.

Thought experiment steps:

1. Counter and receipt do not exist initially.
2. An attempt updates counter and receipt successfully.
3. Before a replica or durable storage saves the new state, the primary fails.
4. The new primary does not see the receipt.
5. The client retries with the same `requestId`.

Analyze:

- In which scenario does the earlier mutation survive?
- In which scenario can the receipt be lost?
- Why cannot a Lua script provide a transaction with an external source of truth?
- What do AOF/replication improve, and what do they not solve?
- When must you rely on SQL unique constraints / outboxes / reconciliation?

## 44. Hands-On Exercise 9 — Designing an Idempotent API

Specification:

```http
POST /api/inventory/sku-42/reserve
Idempotency-Key: req-777
Content-Type: application/json

{"quantity":2}
```

Requirements:

1. Stable request ID across retries.
2. Payload fingerprint.
3. Receipt returning the first attempt's response.
4. Two different payloads sharing the same key must be rejected.
5. Explicit deadlines/retention windows.
6. Defined source of truth if Redis loses state.
7. When outcome is `unknown`, clients can query status by `requestId`.
8. Never return `200 OK` without proving the business operation completed.

Draw sequence diagrams for a normal successful request and for a request that loses its Redis reply.

## 45. Hands-On Exercise 10 — Building a Retry Policy

Define a policy for each of:

```text
GET product cache
SET cache key, TTL 60s
INCR inventory counter
XADD OrderCreated
XACK Stream entry
PUBLISH dashboard refresh
Charge payment provider
```

For each item:

- Retry on timeout?
- Can it cause duplicate effects?
- Which idempotency token applies?
- Is read-after-timeout / result lookup needed?
- Are bounded attempts and backoff needed?
- When outcome is unknown, what status should the API return?
- How long must receipts/backups remain durable?

Explain why **a single `RetryTemplate`** cannot serve every command and remain business-correct.

## 46. Common Misconceptions

### "A Redis timeout means Redis did not run the command"

False. The command may have run while the response was lost.

### "Lettuce auto-reconnect guarantees exactly-once"

False. Reconnect restores connectivity; retries/replays and side effects must be evaluated separately.

### "Adding @Retryable fixes network errors"

It can aid availability, yet it causes double writes if the method is non-idempotent.

### "`INCR` is atomic so retrying is safe"

Each `INCR` is atomic individually, yet **two `INCR`s still increment twice**.

### "`MULTI/EXEC` is a transaction so duplicates cannot happen"

A replayed transaction is a new transaction; Redis does not recognize business requests automatically.

### "`SET` is always idempotent"

Not in every case: retries can refresh TTLs, overwrite newer updates, or violate versioning.

### "Running `DEL` twice changes nothing"

False whenever a key with the same name is recreated between deletions.

### "`SET NX` alone protects every side effect"

False when the guard and business operation span separate systems or non-atomic commands.

### "Lua guarantees exactly-once across all failures"

Lua provides atomic deduplication in live Redis within one slot, yet does not roll back runtime errors or prevent persistence/failover losses and external-system mismatches.

### "Retrying `XADD` with the same `eventId` is automatically ignored by Redis"

False. `XADD *` appends multiple entries with different Stream IDs carrying the same `eventId`.

### "A successful `XACK` means the business operation ran only once"

False. `XACK` only manages the consumer group's PEL; business side effects may already have been duplicated.

### "Retrying `PUBLISH` ensures subscribers receive once"

False. Pub/Sub can drop messages or deliver duplicates on retry.

### "Reading the counter after a timeout proves whether my request incremented it"

Unreliable whenever concurrent writers exist and no operation receipt is stored.

### "Enabling AOF/replicas prevents duplicate writes"

Persistence and replication reduce data loss; **they do not change command idempotency**.

### "A reactive timeout cancels Redis side effects"

Not guaranteed once the command has already been sent to Redis.

## 47. Self-Assessment Questions

1. At which points in a Redis command's lifecycle can a response be lost after execution?
2. Why is a connection exception insufficient to prove a command never ran?
3. What is the difference between an atomic command and an idempotent command?
4. Why can `INCR` still increment twice even though Redis executes each command atomically?
5. What can a late retry of `SET key value EX 60` alter?
6. Does a second `SADD` returning `0` prove the first attempt failed?
7. Why can retrying `DEL` accidentally delete a newly created key?
8. What role does Lettuce auto-reconnect play, and what does it not guarantee?
9. Why should `@Retryable` be added only after designing idempotency?
10. Where should a request ID be generated so it stays stable across HTTP/service retries?
11. Why must reusing an idempotency key with a different payload be rejected?
12. What gaps exist in running `SET NX` followed by `INCR` as two separate commands?
13. How does a same-slot Lua script help coordinate counters and receipts?
14. Why can a runtime error inside Lua still leave partial writes behind?
15. Why must idempotency receipt TTL match the retry horizon?
16. If a receipt is evicted or lost during failover, what risk arises?
17. How many Stream IDs can retrying `XADD *` create?
18. Why is a business `eventId` needed in addition to the Redis Stream ID?
19. How does dropping a connection right after `XREADGROUP` affect the PEL?
20. How does retrying `XACK` differ from retrying both the handler and `XACK`?
21. Why is `PUBLISH`'s return count not a business ACK?
22. Why can an `EXEC` timeout lead to wrongly retrying an entire transaction?
23. Are pipelines all-or-nothing?
24. Do `WAIT`/`WAITAOF` make `INCR` idempotent?
25. Why can an SQL unique constraint in the same transaction be stronger than a Redis receipt cache when side effects live in SQL?
26. In what scenario can a transactional outbox still publish duplicates?
27. What is an `UNKNOWN` API outcome, and how can clients check progress next?
28. When should concurrency be bounded (e.g., `concatMap`) to prevent retries from interleaving with newer updates?
29. Why does a distributed lock not replace request idempotency?
30. Which fault-injection test proves your code handles a lost response after Redis already executed?

## 48. Key Takeaways

- **A connection drop after sending a command leaves the execution outcome uncertain.** Redis may have applied the write before the response failed to reach the Spring Data Redis client.
- **Timeouts do not equal rollbacks.** Reactor cancellation, HTTP timeouts, and reconnects do not undo an already-executed command.
- Separate **atomicity**, **idempotency**, **concurrency correctness**, and **durability**; each solves a different problem.
- Blindly retrying `INCR`, `HINCRBY`, `LPUSH`, `XADD *`, `PUBLISH`, `EVAL`, or `EXEC` risks double writes and duplicate side effects.
- `SET`/`DEL` are safe only under explicit conditions; TTL refreshes, key recreation, and lost updates can make replays unsafe.
- **Backoff curbs load; idempotency prevents duplicate writes.** You need both when retrying critical mutations.
- Use a **stable request ID** across every retry, scoped by tenant/operation, bound to a payload hash, and stored alongside a result receipt.
- When both mutation and receipt live in Redis on the same hash slot, a **Lua script** can check the request ID and mutate atomically in live state—subject to runtime-error, TTL, eviction, and failover limits.
- **Redis Streams can receive duplicate `XADD` entries**, and consumer groups can accumulate pending messages when `XREADGROUP` replies drop. Consumers need `eventId`, PEL recovery, and idempotency.
- **`XACK` confirms delivery state**, not once-only business effects.
- When side effects reside in SQL or payment providers, use database transactions/unique keys, outbox/inbox patterns, provider idempotency, or reconciliation. Standalone Redis guards do not create cross-system transactions.
- Replication/RDB/AOF reduce state loss within configured limits, yet do not automatically guarantee end-to-end exactly-once semantics.
- For unknown operation outcomes, **never falsely claim "not executed" or resend with a new request ID**; support receipt lookups and retries under the same identity.
- Test both **command never sent** and **Redis executed yet reply lost**. Testing disconnects only before sending misses double-write bugs.

### Official References

- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/)
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis — SET](https://redis.io/docs/latest/commands/set/)
- [Redis — SADD](https://redis.io/docs/latest/commands/sadd/)
- [Redis — XADD](https://redis.io/docs/latest/commands/xadd/)
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/)
- [Redis — XPENDING](https://redis.io/docs/latest/commands/xpending/)
- [Redis — XACK](https://redis.io/docs/latest/commands/xack/)
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/)
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis — Replication](https://redis.io/docs/latest/operate/oss_and_stack/management/replication/)
- [Redis — Persistence](https://redis.io/docs/latest/operate/oss_and_stack/management/persistence/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html)
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — Redis Cluster](https://docs.spring.io/spring-data/redis/reference/redis/cluster.html)
- [Lettuce — Reference Guide](https://redis.github.io/lettuce/)
- [Project Reactor — Retry](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html)
