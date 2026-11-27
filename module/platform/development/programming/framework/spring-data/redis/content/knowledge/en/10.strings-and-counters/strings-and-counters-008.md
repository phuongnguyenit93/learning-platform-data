# Analyzing Atomicity When Combining Counters with Expiration

## 1. The Problem: A Counter Valid Only for a Fixed Time Span

In Spring Data Redis, **StringRedisTemplate.opsForValue().increment(...)** is the standard way to increment a counter: page views, failed login attempts, API requests, or user action counts. Redis executes this increment as an **atomic command**. When two requests concurrently increment the same key, Redis never drops an increment due to both reading the old value and overwriting each other.

However, many problems also require the **counter to expire automatically**:

- Limit verification code requests to at most 5 within a 60-second window.
- Count failed login attempts over 15 minutes.
- Count accesses during an active 10-minute session.
- Keep temporary statistics counters for 1 day before automatically cleaning them from Redis.

A common pattern developers write is:

~~~java
Long count = redis.opsForValue().increment(key);
if (count != null && count == 1L) {
    redis.expire(key, Duration.ofSeconds(60));
}
~~~

The intent here is: when the key is created for the first time, increment from 0 to 1 and set a 60-second TTL; subsequent calls only increment the value without extending the expiration. However, the code makes **two separate Redis calls**. Even though each individual call is atomic, the overall **INCR then EXPIRE sequence is not atomic**.

If the application stops or loses connection after INCR yet before EXPIRE, the key can remain **forever** without a TTL. This is a correctness bug, not merely a performance issue.

This lesson explains the exact scope of atomicity, types of race conditions, how to choose time semantics, and how to safely combine counters with expiration using Redis and Spring Data Redis.

## 2. Three Concepts to Distinguish

### 2.1. A Single Atomic Redis Command

For a Redis key holding an integer, **INCR key** increments the value and returns the new value. Redis processes the entire command as a single step without interleaving commands from other clients.

Example:

~~~text
SET lesson:counter:views 10
INCR lesson:counter:views
INCR lesson:counter:views
GET lesson:counter:views
~~~

If no other client modifies it, the final value is **12**. If two clients concurrently send INCR, each INCR remains an atomic increment. Each client's returned value is determined by the order Redis executes them.

In Java:

~~~java
Long next = stringRedisTemplate.opsForValue()
        .increment("lesson:counter:views");
~~~

**Long** is the post-increment value. In normal synchronous execution, this result tells you which attempt number the request is; in pipelined/transactional modes, the return value may be null while commands are queued and results have not yet been collected.

### 2.2. Two Separate Commands Are Not Automatically Atomic

~~~text
INCR lesson:counter:attempts
EXPIRE lesson:counter:attempts 60
~~~

Each command runs independently, so commands from other clients, connection errors, or application shutdowns can occur between them. Redis has no way of knowing those two commands represent **a single business rule**.

Diagram:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Redis as Redis Server
    App->>Redis: INCR counter
    Redis-->>App: 1
    Note over App: Error, timeout, or process crash
    Note over Redis: Key exists without a TTL
    App--xRedis: EXPIRE is never sent
~~~

This issue is commonly called a **gap between operations**. It still exists regardless of how fast Redis is, whether the server has only one primary node, or whether the application uses a connection pool.

### 2.3. Atomicity Does Not Mean Durability or Idempotency

An operation executed atomically by Redis with respect to concurrent clients **does not by itself guarantee**:

- zero data loss if Redis Server crashes; durability depends on persistence and replication;
- a request will not be re-executed after an application timeout when Redis already finished processing it;
- Redis and the application's relational database commit together in a distributed transaction;
- completely exact counts if the application lacks deduplication rules;
- automatic rollback of every error inside a Redis transaction or Lua script.

These are related concerns that must be solved separately. When we say **atomic INCR + TTL assignment**, we primarily require that other clients cannot observe or interleave between incrementing and setting the expiration, and that the first step cannot complete while the second step is skipped on the normal execution path.

## 3. Analyzing Failures When INCR and EXPIRE Are Called Independently

### 3.1. Race Condition Across Concurrent Requests

Suppose key **login:attempts:user42** initially does not exist. Two Spring Boot instances concurrently process requests for user 42:

| Time | Instance A | Instance B | Redis State |
| --- | --- | --- | --- |
| T0 | | | Key does not exist |
| T1 | INCR returns **1** | | Key = 1, TTL = -1 |
| T2 | | INCR returns **2** | Key = 2, TTL = -1 |
| T3 | Crashes before EXPIRE | | Key = 2, TTL = -1 |
| T4 | | Since count = 2, skips EXPIRE | Key = 2, TTL = -1 |

At T4, the counter can live forever. Subsequent requests run INCR getting 3, 4, 5... and never enter the **count == 1** branch, leaving the missing TTL uncorrected.

Notice: **INCR is still arithmetically accurate**, yet the rule *the counter must auto-expire* has been violated.

### 3.2. Failure Happens Even Without Concurrency

With just a single request:

1. Redis receives INCR and returns 1.
2. Spring Boot loses connection or the process crashes.
3. EXPIRE is never sent.
4. The key remains with TTL = -1.

Therefore, **reducing thread count** or running **only one instance** does not eliminate the problem.

### 3.3. Calling EXPIRE on Every INCR Changes the Semantics

To avoid TTL-less keys, developers sometimes write:

~~~java
redis.opsForValue().increment(key);
redis.expire(key, Duration.ofSeconds(60));
~~~

Suppose a request arrives every 20 seconds. Every request resets TTL to 60 seconds, meaning the key expires **60 seconds after the most recent request**. Under steady traffic, the key may never expire.

This is a **sliding expiration / idle timeout**: the lifetime extends on every activity. It differs from **a 60-second window measured from the first increment**.

Moreover, the two commands remain separate. If code is interrupted between INCR and EXPIRE, expiration behavior still depends on request history and when the failure occurred.

### 3.4. Calling EXPIRE Before INCR Does Not Fix It Either

~~~text
EXPIRE lesson:counter:new 60
INCR lesson:counter:new
~~~

When the key does not exist yet, EXPIRE returns 0 because there is no key to attach TTL to. INCR then creates the key **with no expiration**.

Reversing the order of two commands does not solve creating a key and setting its expiration as one unit of work.

### 3.5. SET NX with TTL Followed by INCR Still Leaves a Gap

Another variation:

~~~text
SET lesson:counter:attempts 0 EX 60 NX
INCR lesson:counter:attempts
~~~

Conditional SET with TTL is atomic, avoiding an initial TTL-less key. However, if the application dies after SET yet before INCR, **the first attempt was never counted**. On other paths, concurrent requests can make tracking the first attempt or handling retries harder to reason about.

This technique can be used if its specific semantics are acceptable, yet it **does not form a single atomic "increment and set TTL"** operation.

## 4. Before Choosing a Solution: Identify the Time-Window Semantics

A counter with TTL can serve very different timing rules. Choosing the algorithm matters as much as choosing the Redis command.

| Requirement | Example | TTL Rule |
| --- | --- | --- |
| **Window starting from first access** | At most 5 attempts in 60 seconds from the first request | Set TTL on key creation; do not reset on later increments. |
| **Calendar-aligned window** | At most 100 requests per UTC minute | Key encodes the current minute; TTL cleans up after the minute passes. |
| **Expire on inactivity** | Retain count up to 10 minutes after last activity | Explicitly refresh TTL after each operation. |
| **More accurate sliding window** | At most 20 requests in any contiguous 60 seconds | Requires timestamped structures/algorithms, not just one INCR + TTL. |
| **Token bucket / leaky bucket** | Allow bounded bursts while smoothing rate | Uses extra state and time-based math. |

In this lesson, we focus on the first requirement:

> The first counter increment starts a **60-second** window. Subsequent increments add to the same window and **do not extend TTL**. Once the key expires, a new increment starts a new window.

This can be called a **key-creation-anchored fixed window**, which does not necessarily align with a *clock minute* (e.g., 10:00:00–10:00:59). When designing a rate limiter, state explicitly which reference boundary applies.

## 5. Common Solution: Lua Script for Atomic INCR and PEXPIRE

Redis executes a Lua script as an execution unit where commands from other clients **cannot interleave between commands inside the script**. Hence, the rule *increment and set TTL if newly created* can live inside one script.

### 5.1. Basic Script

~~~lua
-- KEYS[1] = counter key
-- ARGV[1] = lifetime in milliseconds, must be > 0

local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ARGV[1])
end

return count
~~~

How it works:

1. **INCR** returns the counter value after incrementing.
2. If the result equals 1, the script knows the key just started a new counting cycle (assuming the key did not exist prior to incrementing).
3. **PEXPIRE** sets the TTL in milliseconds within the same script execution.
4. Subsequent INCR calls do not extend the TTL.
5. **return count** sends the current count back to the application to enforce thresholds.

When multiple instances call this script for the **same key**, Redis processes each execution sequentially. The first processed request both creates the counter and sets the TTL before the next script runs.

~~~mermaid
sequenceDiagram
    participant A as Request A
    participant R as Redis
    participant B as Request B
    A->>R: EVAL script(KEYS[1], 60000)
    Note over R: INCR → 1
    Note over R: PEXPIRE → 60000ms
    R-->>A: 1
    B->>R: EVAL script(KEYS[1], 60000)
    Note over R: INCR → 2, keeps existing TTL
    R-->>B: 2
~~~

**Limitation to understand:** Redis Lua scripts do not automatically roll back prior writes if a later write fails. For example, if INCR succeeded and PEXPIRE then threw an error due to an invalid TTL argument, INCR will still have mutated data. Therefore, **validate arguments before writing** and ensure the key holds the right data type.

### 5.2. Script with Input TTL Validation

A more defensive version when accepting TTL from the application:

~~~lua
local ttlMillis = tonumber(ARGV[1])

if not ttlMillis or ttlMillis <= 0 or ttlMillis ~= math.floor(ttlMillis) then
    return redis.error_reply('TTL must be a positive integer in milliseconds')
end

local count = redis.call('INCR', KEYS[1])

if count == 1 then
    redis.call('PEXPIRE', KEYS[1], ttlMillis)
end

return count
~~~

Validating TTL **before INCR** avoids mutating the counter when an argument is invalid. The application should also validate the duration before calling Redis.

The script assumes the key either does not exist or is a Redis **String holding a valid integer**. If the key was written as a Hash or non-numeric String, INCR returns an error without incrementing. Dedicate a separate namespace for counters so they never share keys with other data types.

### 5.3. Verifying with redis-cli

On a practice Redis instance, open interactive mode:

~~~bash
redis-cli -h 127.0.0.1 -p 6379
~~~

Run the compact script with a test key:

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n" 1 lesson:counter:atomic:42 60000
GET lesson:counter:atomic:42
PTTL lesson:counter:atomic:42
~~~

The **EVAL** command takes:

- The Lua script body.
- Number of declared keys: **1**.
- Key name: **lesson:counter:atomic:42**.
- ARGV[1]: **60000** milliseconds.

Run EVAL a second time before expiration:

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[1])) end; return n" 1 lesson:counter:atomic:42 60000
GET lesson:counter:atomic:42
PTTL lesson:counter:atomic:42
~~~

With no other clients interfering, the first call returns 1 and the second returns 2. **PTTL decreases over time** instead of resetting back to 60000 after the second call.

Cleanup command for test data:

~~~text
DEL lesson:counter:atomic:42
~~~

**PTTL and GET are two separate read commands**, so they do not form an atomic snapshot of both value and TTL. They are fine for observing results in a lesson, yet should not be used as a GET-then-PTTL sequence for concurrency-sensitive decisions.

## 6. Using RedisScript and StringRedisTemplate in Spring Boot

Spring Data Redis provides the **RedisScript** abstraction to execute Lua on the Redis Server. **StringRedisTemplate** fits well here because keys and TTL arguments are sent as Strings, while the INCR result returned by the script is an integer.

### 6.1. Redis Configuration in Spring Boot

Example using Gradle and Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
~~~

~~~yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

A Redis Server must be running at this endpoint. For container environments, Redis Cluster, ACLs, or TLS, adjust configuration to match actual infrastructure. Never put real passwords into source code.

### 6.2. Declaring RedisScript as a Reusable Bean

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class CounterScriptConfiguration {

    @Bean
    RedisScript<Long> expiringCounterScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText("""
                local ttlMillis = tonumber(ARGV[1])
                if not ttlMillis or ttlMillis <= 0
                   or ttlMillis ~= math.floor(ttlMillis) then
                    return redis.error_reply('Invalid TTL')
                end

                local count = redis.call('INCR', KEYS[1])
                if count == 1 then
                    redis.call('PEXPIRE', KEYS[1], ttlMillis)
                end
                return count
                """);
        script.setResultType(Long.class);
        return script;
    }
}
~~~

Declaring the script once lets Spring Data Redis manage its body and SHA digest via supported execution paths; in supported environments, the library can leverage **EVALSHA** and fall back when the script is not yet cached on Redis. This is not business-data caching; Redis caching the script does not replace the counter's TTL rules.

### 6.3. Service That Increments and Evaluates Thresholds

~~~java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class LoginAttemptLimiter {

    private final StringRedisTemplate redis;
    private final RedisScript<Long> expiringCounterScript;

    public LoginAttemptLimiter(
            StringRedisTemplate redis,
            RedisScript<Long> expiringCounterScript) {
        this.redis = redis;
        this.expiringCounterScript = expiringCounterScript;
    }

    public AttemptDecision recordAttempt(
            String userId, long maxAttempts, Duration window) {

        if (userId == null || !userId.matches("[A-Za-z0-9_-]+")) {
            throw new IllegalArgumentException("Invalid userId");
        }
        if (maxAttempts <= 0) {
            throw new IllegalArgumentException("maxAttempts must be positive");
        }
        if (window == null || window.isNegative() || window.isZero()) {
            throw new IllegalArgumentException("Invalid window");
        }

        long ttlMillis = window.toMillis();
        if (ttlMillis <= 0) {
            throw new IllegalArgumentException("Window too short");
        }

        String key = "login:attempts:user:" + userId;

        Long count = redis.execute(
                expiringCounterScript,
                List.of(key),
                Long.toString(ttlMillis)
        );

        if (count == null) {
            throw new IllegalStateException("Redis returned no counter value");
        }

        return new AttemptDecision(
                count,
                count <= maxAttempts
        );
    }

    public record AttemptDecision(long attempts, boolean allowed) {}
}
~~~

Example call:

~~~java
var decision = limiter.recordAttempt(
        "user42",
        5,
        Duration.ofSeconds(60)
);

if (!decision.allowed()) {
    // Return HTTP 429 or apply the corresponding business policy
}
~~~

**Return semantics:** with **maxAttempts = 5**, attempts with count 1 through 5 are allowed, while attempt 6 onward is rejected until the window expires. Rejected attempts are still counted here; that is one specific policy and can be adjusted per business requirements.

This snippet assumes the application has a single matching **RedisScript<Long>** bean and is called from a request path not running on a reactive event loop. HTTP responses, auditing, account security rules, and fallback strategies on Redis errors must be decided at the application layer.

### 6.4. Why Not Use GET Then SET?

A manual increment implementation like this is also unsafe under concurrency:

~~~java
String current = redis.opsForValue().get(key);
long count = current == null ? 0 : Long.parseLong(current);
redis.opsForValue().set(key, Long.toString(count + 1));
~~~

Two requests can read the same value and overwrite each other, losing increments. **INCR** eliminates that race condition, while a **Lua script** extends atomicity to include setting the TTL.

## 7. Another Option: MULTI/EXEC with EXPIRE NX

In Redis **7.0 and later**, the **EXPIRE** command supports the **NX** option, which sets an expiration only when the key **does not already have an expiration**.

Combined with a Redis transaction:

~~~text
MULTI
INCR lesson:counter:tx:42
EXPIRE lesson:counter:tx:42 60 NX
EXEC
~~~

How it works:

1. MULTI begins queuing commands; calls inside the transaction normally return **QUEUED**.
2. INCR creates or increments the counter.
3. EXPIRE with NX sets TTL only when the key has no TTL yet; if the key already has a TTL, the existing expiration stays untouched.
4. EXEC executes all queued commands sequentially without interleaving commands from other clients.

On the happy path with a properly typed key:

- First call: INCR creates the key, EXPIRE NX assigns the TTL.
- Subsequent calls: INCR increments the count, EXPIRE NX does not reset the TTL.
- If the client disconnects **before EXEC**, queued commands have not run yet.

Because both commands execute inside the same EXEC, there is no gap where the application stops **between INCR and EXPIRE** like with two separate calls.

### 7.1. Why Must You Still Analyze Errors?

Redis transactions **do not roll back every command on runtime errors**. For instance, if the key holds a string that cannot be incremented by INCR, INCR fails yet EXPIRE still runs inside the transaction. Ensure the key is dedicated to the counter and holds a valid String type.

If the client times out or loses connection right when EXEC is sent, the client may **not know whether the transaction executed**. Blind retries can over-increment the counter. This is the **uncertain outcome after timeout** issue, which must be handled at the business layer.

**EXPIRE NX exists only in Redis versions supporting this option.** For older Redis versions or broader compatibility, a Lua script is the standard way to express conditional expiration assignment.

### 7.2. Is Standalone EXPIRE NX Enough?

No. If code calls:

~~~text
INCR lesson:counter:broken
EXPIRE lesson:counter:broken 60 NX
~~~

then even though EXPIRE NX prevents resetting an existing TTL, **there is still a gap between the two commands** where the application can stop. Adding NX without MULTI/EXEC or another atomic execution mechanism **does not fully solve the TTL-less key bug**.

### 7.3. Should You Choose Lua or MULTI/EXEC?

| Criterion | Lua script | MULTI/EXEC + EXPIRE NX |
| --- | --- | --- |
| Redis support | Lua scripting available in any Redis supporting scripting | EXPIRE NX requires Redis 7.0+ |
| Expressing TTL conditions | Can set TTL when count = 1 or use custom logic | EXPIRE NX sets TTL when key has no expiration |
| Atomic scope | Script runs without interleaving from other clients | Commands in EXEC run without interleaving from other clients |
| Returning counter result | Script returns count directly | Parse EXEC result list to extract INCR value |
| Algorithm extensibility | Convenient when adding checks inside the same script | Easy for short command sequences without arbitrary branching |
| Errors during execution | Does not auto-rollback completed writes | Does not auto-rollback runtime errors |

Both approaches require proper retry strategies, key-type validation, and Redis operations. Lua often **encapsulates the increment-and-TTL business logic** into a single call with a clear return type; MULTI/EXEC is useful when built-in NX semantics match the requirement.

## 8. Subtle TTL Behaviors to Understand

### 8.1. TTL Is Not an Application Timer

Redis guarantees expired keys are not treated as live keys when accessed. Redis also uses active and passive expiration cleanup. However, never assume a callback fires at the exact millisecond TTL hits 0.

If business logic needs to **trigger a task at an exact timestamp**, TTL and key-expiration events are not a reliable scheduling mechanism compared to a proper job scheduler or message queue.

### 8.2. TTL Can Be Reset or Removed

Common operations:

| Operation | Typical Impact on TTL |
| --- | --- |
| INCR key | Updates value; normally preserves existing TTL. |
| EXPIRE key seconds | Resets expiration to the given seconds. |
| PEXPIRE key milliseconds | Resets expiration to the given milliseconds. |
| PERSIST key | Removes expiration; key becomes non-expiring. |
| SET key value | Replaces value and normally removes TTL unless an expiration/keep-TTL option is given. |
| SET key value EX seconds | Writes value and sets TTL in one command. |
| DEL key | Deletes key; TTL no longer applies. |

Thus a counter created properly by a script can still be **overwritten with SET without TTL** by another code path. Reserve a dedicated namespace and restrict which components may write counter keys.

### 8.3. TTL = -1 and TTL = -2 Have Different Meanings

In redis-cli:

~~~text
TTL lesson:counter:some-key
PTTL lesson:counter:some-key
~~~

Special outputs:

- **-1:** key exists but has no expiration.
- **-2:** key does not exist.
- **Non-negative number:** remaining time (seconds for TTL; milliseconds for PTTL).

If a counter key that should always expire shows **TTL = -1**, investigate which write path created it or removed its TTL.

### 8.4. Does a Script Setting TTL Only When count == 1 Auto-Heal Legacy Broken Keys?

No. If a key created by older code already holds **7** with TTL = -1, the basic script increments it to 8 and **skips PEXPIRE** because count does not equal 1. The key remains without expiration.

If requirements allow auto-healing TTL-less keys, you can choose this variant:

~~~lua
local ttlMillis = tonumber(ARGV[1])
if not ttlMillis or ttlMillis <= 0
   or ttlMillis ~= math.floor(ttlMillis) then
    return redis.error_reply('Invalid TTL')
end

local count = redis.call('INCR', KEYS[1])
if count == 1 or redis.call('PTTL', KEYS[1]) == -1 then
    redis.call('PEXPIRE', KEYS[1], ttlMillis)
end
return count
~~~

This variant attaches a TTL whenever a key has no expiration, even if count exceeds 1. It helps recover anomalous state, yet **changes semantics**: a key previously intended to never expire will also receive a TTL. Use it only when the namespace and data policy confirm **every counter must have an expiration**.

If a legacy key holds an invalid format or reset data, a script cannot infer lost history on its own. Decide a cleanup or migration policy for legacy keys instead of expecting Lua to deduce missing data.

## 9. Clock-Minute Windows vs. First-Attempt Windows

Suppose you need to **limit 100 requests per UTC minute**. A simple approach computes the key name from a time bucket:

~~~text
api:minute:2026-11-12T10:30:user42
api:minute:2026-11-12T10:31:user42
~~~

In Java, you can use an integer bucket:

~~~java
long minuteBucket = Instant.now().getEpochSecond() / 60;
String key = "api:minute:" + minuteBucket + ":user:" + userId;
~~~

**Instant** comes from **java.time.Instant**. Each minute gets its own key; each key's counter can increment via an atomic script and auto-expire after a cleanup margin, e.g., 2 minutes.

However:

- Do not confuse TTL with the exact calendar-minute boundary; the **bucket name** determines which requests are counted together.
- If application servers have skewed clocks, requests near a minute boundary may land in different buckets; synchronize clocks or use a unified time source.
- Fixed calendar windows allow a burst at the end of one minute plus another burst at the start of the next, creating a **boundary burst**. This is an algorithmic property, not an atomicity bug.
- If you must limit **any contiguous 60 seconds**, consider sliding windows, token buckets, or a more suitable algorithm.

Hash tags in Redis Cluster can also group related keys into one slot when an algorithm touches multiple keys, though never group all users into one global tag that creates a hot slot.

## 10. Redis Cluster and Atomicity Scope

Redis Cluster partitions keys across **16,384 hash slots**. Scripts and transactions touching a single counter key route easily: the client only needs that key's slot.

Example:

~~~text
login:attempts:{user42}
~~~

When running a script with **one KEYS[1]**, Redis Cluster resolves the node owning that key's slot. If the script later needs another key, such as an idempotency marker:

~~~text
login:attempts:{user42}
login:requests:{user42}:request-abc
~~~

then shared keys must satisfy the **same hash slot** constraint. Adding **{user42}** ensures both keys belong to the same slot.

Notes:

- **StringRedisTemplate** still needs to connect via a Cluster-aware client.
- Redis Cluster does not provide atomic transactions spanning arbitrary slots.
- Scripts must declare all accessed keys through the **KEYS** list rather than constructing hidden key names dynamically inside Lua.
- Choose hash tags scoped tightly to keys operated on together. Tagging every counter with **{global}** forces all data and load onto a single slot.
- Slots can move to different primary nodes after resharding/failover; applications need clients capable of handling topology updates.

Using the same hash tag only satisfies key colocation constraints; it **does not guarantee duplicate-free retries or durability**.

## 11. Retries, Timeouts, and Idempotency: Atomic Does Not Guarantee Business Correctness

Consider this scenario:

1. Spring Boot calls the script; Redis increments the counter from 2 to 3 and sets/keeps the TTL properly.
2. Redis's response is lost due to a connection timeout.
3. Spring Boot does not know whether the operation succeeded.
4. The application retries the same operation.
5. Redis increments again from 3 to 4.

**Each script still executed atomically**, yet one business event was counted twice. This is a bug caused by **retrying an uncertain outcome**, not a race between INCR and EXPIRE.

### 11.1. When Is At-Least-Once Acceptable?

For click counts, occasional duplicate counts may fall within acceptable tolerance. For OTP attempts, quotas, or payment limits, double-counting can wrongly lock out users; in those cases, define explicit idempotency rules.

### 11.2. Request ID Pattern

The application assigns a stable request ID to each business event, for example:

~~~text
attempt:id:{user42}:req-abc
attempt:count:{user42}
~~~

A script can:

1. Check whether the request ID has already been recorded.
2. If already present, return the recorded result or an "already processed" status without incrementing again.
3. If absent, record the request ID marker and increment the counter.
4. Set appropriate expirations for both marker and counter in the same execution.

Keys must share a slot on Redis Cluster. Only this qualifies as an **idempotent counter** design; code must never simply split a `SETNX` marker and an `INCR` into two independent requests and claim the whole operation is atomic.

If a fresh request ID is generated on every retry, idempotency will fail. If the marker expires before a late retry arrives, the operation can still double-count; marker TTL must match retry windows and data requirements.

### 11.3. When Redis Is Unavailable

For rate limiters, choose a clear policy:

- **Fail-open:** on Redis errors, allow requests through; prioritizes availability but may bypass limits.
- **Fail-closed:** on Redis errors, block requests; preserves throttling policy but can disrupt legitimate users.
- **Other fallback:** e.g., local limits, backup systems, or special handling for critical endpoints.

The choice depends on business risk; never catch all exceptions and blindly treat them as "under threshold". A Redis error **does not mean GET null or count = 0**.

## 12. Impact of Connection Pools and Multiple Instances

Applications may use RedisConnectionFactory/Lettuce, shared connections, or pools as needed. Atomicity of INCR, Lua scripts, or EXEC is enforced **on Redis**, independent of whether Spring Boot uses one or many threads.

With separate INCR then EXPIRE calls:

~~~text
Instance A -> Redis: INCR
Instance B -> Redis: INCR
Instance A -> Redis: EXPIRE
~~~

A larger pool does not combine three commands into one transaction. On the contrary, multiple instances make interleaving far more likely.

With a script:

~~~text
Instance A -> Redis: EVAL (INCR + PEXPIRE)
Instance B -> Redis: EVAL (INCR + PEXPIRE)
~~~

Redis executes each script as a unit, so no other client can interleave between INCR and PEXPIRE within the same script. When scaling an application horizontally, ensure **all instances share the same key naming, TTL policy, and Redis deployment**.

### Note on Redis Persistence and Replication

If Redis suffers a severe crash, recently written data can be lost depending on persistence, replication, and failover settings. Guaranteeing atomicity against concurrent clients **does not mean** every incremented value is guaranteed to survive every type of failover.

If a counter serves security-critical or financial roles, separately evaluate data-loss tolerance, durability requirements, and the source of truth. Redis fits many rate limiters well, yet durability guarantees cannot be inferred merely because the code uses Lua.

## 13. Hands-On Analysis of Each Approach Using redis-cli

Practice on a learning Redis instance, never on production keys. Run the following lines in **interactive redis-cli**.

### Lab 1: Reproducing a Key Without TTL

~~~text
INCR lesson:counter:bad
GET lesson:counter:bad
TTL lesson:counter:bad
~~~

When the key does not exist yet, INCR creates count = 1 and TTL is **-1**. This is the exact state left behind if an application increments without sending EXPIRE.

One more increment:

~~~text
INCR lesson:counter:bad
TTL lesson:counter:bad
~~~

Count becomes 2 yet TTL stays -1. If code only sets EXPIRE when count == 1, subsequent calls never repair the missing expiration.

### Lab 2: Observing TTL Reset When EXPIRE Runs Every Time

~~~text
SET lesson:counter:sliding 0 EX 60
TTL lesson:counter:sliding
INCR lesson:counter:sliding
EXPIRE lesson:counter:sliding 60
TTL lesson:counter:sliding
~~~

If time elapses between the two observations, TTL jumps back near 60 after EXPIRE. This fits **"expire after last activity"**, not a window anchored to the first event.

### Lab 3: Observing an Atomic Script

~~~text
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],60000) end; return n" 1 lesson:counter:lua
PTTL lesson:counter:lua
EVAL "local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('PEXPIRE',KEYS[1],60000) end; return n" 1 lesson:counter:lua
PTTL lesson:counter:lua
GET lesson:counter:lua
~~~

Expected result: count increments while PTTL is not reset on the second increment. This snippet hardcodes a 60000-millisecond TTL to focus on command atomicity.

### Lab 4: If Redis Supports EXPIRE NX

~~~text
MULTI
INCR lesson:counter:tx
EXPIRE lesson:counter:tx 60 NX
EXEC
TTL lesson:counter:tx
~~~

Repeat the transaction before expiration:

~~~text
MULTI
INCR lesson:counter:tx
EXPIRE lesson:counter:tx 60 NX
EXEC
TTL lesson:counter:tx
~~~

TTL counts down over time without resetting because the key already has an expiration. If an older Redis version does not support EXPIRE NX, the command returns an error and this example cannot be used as written.

### Lab 5: Cleaning Up Test Keys

~~~text
DEL lesson:counter:bad lesson:counter:sliding lesson:counter:lua lesson:counter:tx
~~~

This multi-key DEL works on standalone Redis. On Redis Cluster, when a single DEL command lists multiple keys, they must satisfy slot constraints; delete keys individually or use suitable hash tags when batching into one command.

## 14. Common Symptoms and Causes in Spring Data Redis

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Counter lives forever, TTL = -1 | INCR completed but EXPIRE was skipped; another code path removed TTL | Use atomic Lua/EXEC; find and fix write paths; clean up legacy keys. |
| Continuous traffic keeps key from ever expiring | EXPIRE called after every INCR | Decide between sliding expiration and a first-attempt fixed window. |
| Count is lower than actual requests | Used GET then SET causing lost updates, or first attempt uncounted when splitting SET NX | Use INCR; combine related logic into a script/transaction. |
| Count exceeds business events | Retries after timeout or duplicate event delivery | Design request ID/idempotency and marker lifetimes. |
| INCR returns WRONGTYPE | Key is currently a Hash/List/Set or incompatible non-String data | Check TYPE/GET, separate namespaces, standardize serializers. |
| INCR reports value is not an integer | String key contains text/JSON or malformed value | Check serializers and value-storage conventions. |
| Script runs yet PTTL = -1 on old key | Script only sets TTL when count == 1; old key already has count > 1 | Plan legacy key remediation; consider PTTL == -1 healing variant if appropriate. |
| EVAL on Cluster reports CROSSSLOT | Script accesses keys in different slots | Declare KEYS explicitly and colocate related keys with hash tags. |
| Client times out yet Redis incremented | Response lost after server executed command | Avoid blind retries; design idempotency if exactness is needed. |
| Command returns null in transaction/pipeline | Client queued command and has not fetched results yet | Read result list after EXEC/pipeline; never treat null as count = 0. |
| Expiration does not fire event at exact millisecond | Redis expiration is not a real-time scheduler | Do not use key expiration as a precise business timer. |
| Window drift across instances | Instances generate different bucket keys due to clock skew | Synchronize clocks or use a unified time source. |

When troubleshooting, inspect at least **key name – count – PTTL**, and audit write paths in Spring Boot. **TYPE** helps uncover cases where the same key was reused for another Redis data structure.

## 15. Scenario Analysis Questions

### Scenario A: Can We Keep Separate INCR + EXPIRE?

A service logs non-critical visit stats on a single instance, calling INCR then EXPIRE on the first visit. What is the risk?

**Analysis:** even on a single instance, the application can crash or time out between the two commands, leaving a TTL-less key. If periodic batch cleanup is acceptable that may be a deliberate trade-off, yet whenever the requirement strictly states *every counter must self-expire*, combine the operations atomically.

### Scenario B: Does Adding EXPIRE After Every INCR Fix a Rate Limiter?

Suppose up to 5 requests are allowed within 60 seconds from the first request.

**Analysis:** calling EXPIRE on every request turns the lifetime into **60 seconds from the last request**, breaking the original rule's reference point. If requests keep arriving, the key can persist indefinitely and keep blocking the user. Preserve the initial TTL when the goal is a first-request-anchored window.

### Scenario C: Does MULTI/EXEC Work on Every Redis Version?

Someone proposes MULTI, INCR, EXPIRE NX, EXEC.

**Analysis:** this sequence relies on EXPIRE's NX option, available only in Redis 7.0+. It preserves existing TTLs properly, yet still requires handling wrong-type keys, command errors at EXEC, and uncertain timeout outcomes. On Redis versions without EXPIRE NX, use another mechanism.

### Scenario D: Does a Lua Script Prevent Every Duplicate Count?

A request is sent, the script executes successfully, yet the client times out and the service retries.

**Analysis:** the script makes INCR and expiration atomic, yet the retry is a brand-new invocation. Redis does not inherently know both belong to the same business event; an idempotency key or proper retry handling is still required.

### Scenario E: Should Total Views and Quota Share One Key?

An endpoint tracks both long-term total views and a 60-second view quota.

**Analysis:** these are two distinct data semantics. Total views may have no TTL or require durable storage, whereas the quota window must expire automatically. Use **two distinct keys and write paths**; never attach a TTL to a long-term counter just to serve a rate limiter.

## 16. Design Principles to Remember

1. **Single-command INCR atomicity does not make INCR + EXPIRE an atomic operation.**
2. If TTL is set only when count == 1, a failure between the two commands can leave the key persisting indefinitely.
3. Running EXPIRE after every increment implements **activity-based renewal**, not a fixed TTL from the first event.
4. **Lua scripts** let Redis execute INCR and expiration assignment as one unit, fitting multiple Spring Boot instances sharing one key.
5. **MULTI/EXEC + EXPIRE NX** is a valid option on Redis 7.0+ when setting TTL only if absent, yet does not roll back all runtime errors.
6. **Validate inputs and key types** before relying on scripts; Lua and transactions do not auto-repair malformed data or execution errors.
7. **Atomicity, idempotency, durability, and cross-system consistency are distinct guarantees.** Timeout retries and failovers still require separate design.
8. Clearly distinguish **first-event windows, calendar-minute buckets, idle timeouts, and sliding windows** before choosing an algorithm.
9. In **Redis Cluster**, every key accessed within a script/transaction must satisfy same-slot requirements.
10. Monitor counters using **GET**, **TTL/PTTL**, and **TYPE**, without mistaking separate inspection commands for an atomic snapshot.

Core lesson takeaway: **a correct counter is not just accurate arithmetic, it also has the right lifecycle**. In Spring Data Redis, specify the timing rules clearly and group operations that must succeed together into an appropriate atomic mechanism. Then handle retries, infrastructure failures, and cross-system consistency separately so counter behavior stays aligned with business requirements.
