# Designing Time-Window Counters

In **Spring Data Redis**, a simple counter often only requires `StringRedisTemplate.opsForValue().increment(key)`. However, when requirements become "count requests in 60 seconds", "limit to 100 API calls per minute", "aggregate orders by hour", or "allow at most 5 attempts in the last 15 minutes", incrementing an integer is not enough. You must decide **when a time window starts and ends, how keys are structured over time, when they expire, and which operations must be atomic**.

Two phrasings are easily confused:

- **Fixed-interval counting**: "How many orders occurred from 10:00 to just before 10:01?" Common for statistics, charts, aggregations, or rate limiting that allows quota resets at minute boundaries.
- **Rolling-interval counting**: "How many requests occurred in the exact last 60 seconds up to right now?" Requires tracking history relative to the current timestamp, rather than looking solely at a counter for the current minute.

Redis fits these problems well thanks to atomic `INCR`, TTL, String commands, Sorted Sets, and Lua scripts. Spring Data Redis provides the APIs to combine them without forcing the application to manage the raw byte protocol.

This lesson focuses on **designing time-bounded counters**, covering algorithm selection, Java/Spring examples, atomicity control, memory bounds, and issues that arise across multiple application instances.

## 1. Start with Business Requirements

Before creating keys, distinguish the following questions.

| Requirement | Window | Data to Retain | Required Precision |
|---|---|---|---|
| Total orders per minute for charting | Calendar minute or 60-second bucket | One count per minute | Total count per bucket |
| Limit 100 requests/minute, reset at top of minute | Fixed window | One counter/actor/bucket | Atomic when deciding allowance |
| At most 5 attempts in the **last 15 minutes** | Sliding window | Timestamp per attempt or small buckets | Needs an explicit sliding boundary |
| Display request count in the last 5 minutes | Rolling buckets | Recent minute/second counters | Bucket-level approximation acceptable |
| Smooth request rate while allowing small bursts | Token bucket | Remaining tokens, refill timestamp | Not counting a fixed time frame |

**A counter with a TTL does not automatically become a sliding-window counter.** If you simply create `counter:user:42` and attach a 60-second TTL, the result is a window starting from **when the key was created**; it does not represent the exact last 60 seconds at every point in time.

### 1.1. Decisions to Clarify Up Front

1. How long is the window: 1 second, 60 seconds, 15 minutes, one hour, or a calendar day?
2. Is the interval **fixed**, **rolling/sliding**, or anchored at the first activity?
3. Should you count **all attempts** or only **accepted requests**?
4. Which actor is the counter scoped to: user, IP, API key, tenant, product, or global system?
5. Do you need strict accuracy across network failures, retries, and Redis failovers, or is an approximation sufficient?
6. How long should old buckets be retained for statistics and when must they be deleted?
7. When Redis is unreachable, what policy does the API follow?

These answers dictate key design and algorithm choice. Do not apply a single `INCR + EXPIRE` pattern to every problem.

## 2. Core Redis Principles

### 2.1. INCR Is an Atomic Increment on One Key

Example:

~~~bash
redis-cli SET metrics:orders:current 0
redis-cli INCR metrics:orders:current
# (integer) 1
redis-cli INCR metrics:orders:current
# (integer) 2
redis-cli GET metrics:orders:current
# "2"
~~~

Each `INCR` command is processed atomically by Redis. When multiple Spring Boot instances increment **the same key**, they do not need to pull the value to Java and call `set(value + 1)`.

The following pattern easily loses increments due to race conditions:

~~~java
// Do not use read-modify-write to increment concurrent counters.
String oldValue = redis.opsForValue().get(key);
long next = Long.parseLong(oldValue == null ? "0" : oldValue) + 1;
redis.opsForValue().set(key, Long.toString(next));
~~~

Two threads can both read `10` and both write `11` even though two requests occurred. Use `increment`.

Redis `INCR` operates on string-encoded integers accepted by Redis. To keep keys and values as numeric strings, `StringRedisTemplate` is usually simpler than a `RedisTemplate<String, Long>` configured with a binary/JDK serializer.

### 2.2. INCR and EXPIRE Are Two Separate Commands

A common pattern:

~~~java
Long count = redis.opsForValue().increment(key);
if (count != null && count == 1L) {
    redis.expire(key, Duration.ofMinutes(1));
}
~~~

The issue: the process can stop **after INCR but before EXPIRE**. Then the first key persists with no TTL. With counters created continuously over time, these "orphaned" keys can accumulate.

Solution when incrementing and setting TTL must be consistent: use a **Lua script** so Redis executes them in one atomic turn, or use an appropriate command pattern combining expiration in the same operation.

### 2.3. Atomicity Does Not Mean Durability

Redis can execute `INCR` atomically on the primary, yet replication is usually asynchronous. During a failover, an increment already acknowledged to the client still risks not having reached the new replica. Therefore, an "atomic counter" differs from a "never-lose-an-event total".

If you need strictly accurate numbers for auditing, payments, or billing, Redis can serve as a temporary/real-time counting layer; an authoritative event source and reconciliation mechanism must still be designed separately.

## 3. Fixed Window: One Counter per Fixed Time Interval

With a 60-second window, time is partitioned into buckets:

~~~text
12:00:00                 12:01:00                 12:02:00
   |------- minute A --------|------- minute B --------|
   + 1 request              + 1 request
   + 1 request
   + 1 request              + 1 request
   counter[A] = 3           counter[B] = 2
~~~

How to compute the bucket for a Unix timestamp in seconds:

~~~text
bucketIndex = floor(epochSeconds / windowSeconds)

bucketStartEpochSeconds
    = floor(epochSeconds / windowSeconds) * windowSeconds
~~~

Here `epochSeconds` is a given timestamp (timezone-independent when using Unix epoch). With `windowSeconds = 60`, every request from the start of a minute until just before the next minute shares the same `bucketStartEpochSeconds`.

Reference keys:

~~~text
rate:api:user:42:bucket:1893456000
rate:api:user:42:bucket:1893456060
~~~

The epoch numbers here only illustrate the format. In code, compute them dynamically from the real timestamp rather than hardcoding.

### 3.1. Pros and Cons

**Pros:**

- One counter per active actor in a bucket.
- Each request requires a single increment or short script.
- Easy to aggregate per-minute/per-hour metrics.
- Key count stays bounded via TTL.
- Easy to inspect with Redis CLI.

**Biggest drawback: boundary bursts.**

Suppose the limit is 100 requests/minute:

~~~text
12:00:59.900 -> sends 100 requests (uses up 12:00 minute quota)
12:01:00.100 -> sends 100 requests (new 12:01 minute quota begins)

=> 200 requests within roughly 0.2 seconds,
   even though neither bucket exceeded 100.
~~~

If the API only enforces calendar-minute quotas, this may be acceptable. If the goal is "no more than 100 requests in **any** 60 seconds", fixed windows do not satisfy that exact requirement.

## 4. Designing TTL for Fixed Windows

Depending on purpose, counter TTLs take two forms.

### 4.1. Rate Limiting: Keep Until Bucket End Plus a Small Grace Margin

When each key holds one minute's counter, you can let it expire right after the minute boundary or keep it a few extra seconds for inspection.

~~~text
bucketStart = floor(nowSeconds / 60) * 60
bucketEnd   = bucketStart + 60
expireAt    = bucketEnd + 5 seconds
ttlSeconds  = expireAt - nowSeconds
~~~

Example at 12:00:45:

~~~text
15 seconds left until end of minute
5 seconds grace retention
=> TTL to set on key creation ≈ 20 seconds
~~~

**Do not always set TTL to 60 seconds** if the goal is cleanup at the bucket boundary. A first request arriving at 12:00:45 would keep the key alive until 12:01:45, well after the bucket ended. With bucket-ID keys this mainly wastes memory, though it also obscures cleanup timing.

### 4.2. Statistics: Keep According to Business Retention

An "orders per minute" counter might need 7-day retention for charts:

~~~text
bucketEnd = 12:01:00 day N
expireAt  = 12:01:00 day N+7
~~~

TTL should be fixed relative to **bucket end + retention**, rather than extended whenever a late event is recorded.

For metrics needing longer retention, flush closed buckets into an analytical database and remove short-term data from Redis.

## 5. Spring Data Redis: Atomic Fixed-Window Counter

The example below enforces **100 requests per 60-second bucket**. Only accepted requests increment the counter; once the limit is reached, the script returns a negative value to signal rejection.

The application uses Spring Boot 3.x, Java 17+, Spring Data Redis, and `StringRedisTemplate`.

### 5.1. Lua Script to Conditionally Increment and Set TTL

~~~lua
-- KEYS[1]: key holding the current bucket counter
-- ARGV[1]: limit (> 0)
-- ARGV[2]: TTL in seconds (> 0)

local limit = tonumber(ARGV[1])
local ttlSeconds = tonumber(ARGV[2])
local current = tonumber(redis.call('GET', KEYS[1]) or '0')

if current >= limit then
    return -current
end

local updated = redis.call('INCR', KEYS[1])

if redis.call('TTL', KEYS[1]) < 0 then
    redis.call('EXPIRE', KEYS[1], ttlSeconds)
end

return updated
~~~

In this example, this key is owned solely by the counter, values are always non-negative integers, and `limit > 0`. Outcomes:

- **Positive number**: request allowed; value is the counter after incrementing.
- **Negative number**: request rejected; absolute value is the count already accepted.
- `TTL < 0`: key has no TTL (or did not exist); since `INCR` just ran, this branch attaches expiration if missing.

The script runs atomically on Redis, so no other request interleaves between checking the limit, incrementing, and setting TTL. No Java `synchronized` lock is needed, which only synchronizes within one JVM and is insufficient across multiple instances anyway.

### 5.2. Java Service Executing the Script

~~~java
import java.time.Clock;
import java.time.Instant;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class FixedWindowRateLimiter {

    private static final long WINDOW_SECONDS = 60;
    private static final long EXPIRY_GRACE_SECONDS = 5;
    private static final long LIMIT = 100;

    private static final String LUA = """
            local limit = tonumber(ARGV[1])
            local ttlSeconds = tonumber(ARGV[2])
            local current = tonumber(redis.call('GET', KEYS[1]) or '0')

            if current >= limit then
                return -current
            end

            local updated = redis.call('INCR', KEYS[1])

            if redis.call('TTL', KEYS[1]) < 0 then
                redis.call('EXPIRE', KEYS[1], ttlSeconds)
            end

            return updated
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public FixedWindowRateLimiter(
            StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public Decision check(String userId) {
        long nowSeconds = Instant.now(clock).getEpochSecond();
        long bucketStart =
                Math.floorDiv(nowSeconds, WINDOW_SECONDS) * WINDOW_SECONDS;
        long secondsToBoundary =
                bucketStart + WINDOW_SECONDS - nowSeconds;

        String key = "rate:api:user:" + userId
                + ":bucket:" + bucketStart;

        long expiry = secondsToBoundary + EXPIRY_GRACE_SECONDS;

        Long result = redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(LIMIT),
                Long.toString(expiry)
        );

        if (result == null) {
            throw new IllegalStateException("Redis returned no counter");
        }

        boolean allowed = result > 0;
        long count = Math.abs(result);

        return new Decision(allowed, count, secondsToBoundary);
    }

    public record Decision(
            boolean allowed,
            long acceptedCount,
            long secondsToNextWindow) {}
}
~~~

`Clock` is a required dependency in the Spring context. You can declare a bean using system time:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

In production environments, restrict/normalize `userId` to prevent oversized keys, unintended key collisions, or leaking personal data. With multiple instances, synchronize system clocks; clock drift can cause instances to compute different buckets near boundaries.

### 5.3. Request Flow Walkthrough

~~~text
HTTP request
     |
     v
Identify userId and timestamp
     |
     v
Compute bucketStart and Redis key name
     |
     v
Spring Data Redis execute(Lua)
     |
     +--> LIMIT reached? ------> Yes --> return negative, reject
     |                           |
     +--> No --------------------+
             |
             v
          INCR key
             |
       TTL missing?
             |
       Yes -> EXPIRE
             |
             v
      Return positive
             |
             v
      Allow request processing
~~~

If the client times out while calling the script, you cannot automatically know whether Redis incremented the count. Sending it again may count an extra request. Rate limiters of this type can tolerate minor retry drift per policy, yet should not be mistaken for exact billable-event counting.

### 5.4. Why Return a Negative Number Instead of Two Commands (GET Then INCR)?

If Java reads the count with `GET`, checks `count < LIMIT`, and then calls `INCR`, multiple instances can simultaneously see the count below the limit and exceed it. Lua combines **check + write** into one atomic operation.

Encoding the result with a negative sign is only an illustrative convention; larger systems can return a multi-element Lua result or explicit status. When enforcing limits, also distinguish **counting all attempts**, **counting only accepted requests**, or **refunding quota on business failure**—those are three distinct policies.

## 6. Integrating the Rate Limiter into a Spring Web API

You can use this service in a controller or filter/interceptor. Simple controller example:

~~~java
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/products")
public class ProductController {

    private final FixedWindowRateLimiter limiter;

    public ProductController(FixedWindowRateLimiter limiter) {
        this.limiter = limiter;
    }

    @GetMapping
    public ResponseEntity<String> listProducts() {
        // Illustrative example; obtain principal from security context in real apps.
        String userId = "demo-user-42";
        FixedWindowRateLimiter.Decision result = limiter.check(userId);

        if (!result.allowed()) {
            return ResponseEntity.status(HttpStatus.TOO_MANY_REQUESTS)
                    .header("Retry-After",
                            Long.toString(result.secondsToNextWindow()))
                    .body("Rate limit exceeded");
        }

        return ResponseEntity.ok("Products");
    }
}
~~~

In production, never hardcode `userId`. Extract a stable identifier from the authenticated user, API key, or client identity policy. If using IP addresses, handle reverse proxies and trusted headers properly; never blindly trust a client-supplied header as identity.

HTTP `429 Too Many Requests` fits rate limiting. `Retry-After` can express the wait time in seconds. For fixed windows, time remaining until the bucket boundary is a reasonable estimate; account for response latency and clock skew when computing it.

If a policy applies across all endpoints, place the rate limiter in a filter or interceptor instead of duplicating logic in every controller. If policies vary by endpoint or tenant, include those dimensions in the key.

## 7. "From First Request" Fixed Windows vs. Calendar Buckets

Sometimes the requirement is: "At most 5 attempts within 15 minutes from the first attempt", rather than "reset at minutes :00, :15, :30, :45".

A stable key:

~~~text
attempts:login:user:42
~~~

is created on the first attempt, then incremented with `INCR` and given a 15-minute TTL. This is a **first-event anchored window**.

~~~text
First attempt at 12:07 -> key expires near 12:22
Attempts at 12:09, 12:14 -> still inside initial window
After 12:22 -> key expires, next cycle can start
~~~

Unlike a 15-minute calendar bucket:

~~~text
12:00-12:15: quota A
12:15-12:30: quota B
~~~

With a first-event anchored window, do not renew the TTL on subsequent requests if the rule is strictly 15 minutes from the first event. Conversely, if every request runs `EXPIRE 15 minutes`, that becomes a **sliding inactivity timeout**, a different policy.

Because there is only one key, `INCR` + TTL must be atomic as in the earlier script; the key has no time bucket in its name, and TTL is set when the window starts. This is simple, yet **does not guarantee "no more than N attempts in any W seconds"** if the key expires and is immediately recreated right across the boundary.

## 8. Sliding Window: Counting in the Exact Last W Seconds

Defined at time `t` with window length `W`:

~~~text
count(t) = number of events with timestamp in (t - W, t]
~~~

For example, W = 60 seconds, current time 12:01:10:

~~~text
12:00:10 --------------------------- 12:01:10
         |<----- last 60 seconds ----->|
         Events at or before 12:00:10 excluded
         Events after 12:00:10 counted
~~~

Because the window slides with every request, a single current-minute counter is insufficient. Three common design approaches exist:

1. **Sliding log** using a Redis Sorted Set: stores each event's timestamp, exact to recorded timestamps.
2. **Sliding window counter** using two adjacent buckets with weights: memory-efficient but approximate.
3. **Small sub-buckets** (e.g., per second) summed over W seconds: accuracy depends on bucket width.

### Algorithm Comparison Table

| Algorithm | Memory per Actor | Primary Operations | Pros | Limitations |
|---|---|---|---|---|
| Fixed window | O(1) counter in current bucket | `INCR`, TTL | Simple, lightweight | Boundary bursts |
| First-event window | O(1) | `INCR`, TTL | Easy to limit from first attempt | Not a true rolling window |
| Sliding log (ZSet) | O(N) events retained in window | `ZREMRANGEBYSCORE`, `ZCARD`, `ZADD` | Follows exact event timestamps | Higher RAM and ops cost at high event volume |
| Two-bucket sliding counter | O(1) counts across two buckets | Read two counters, weighted sum | Few keys, smoother than fixed window | Approximate estimate only |
| Small rolling buckets | O(W / bucket width) | Multiple counters and sum | Trade error via bucket width | More keys, TTLs, and operations |
| Token bucket | O(1) state | Time-based refill + consume tokens | Smooths rate and controls bursts | Different semantics from "exact count in W seconds" |

## 9. Sliding Log with Sorted Sets: Exact Timestamp Counting

A Redis Sorted Set (`ZSET`) stores unique members, each with a `score`. For a sliding log:

- **Score** = request timestamp, usually in milliseconds.
- **Member** = unique identifier of the request/event.
- **Key** = one actor and one policy, e.g. `rate:login:user:42`.

Example:

~~~text
ZSET key = rate:login:user:42

score (milliseconds)    member
--------------------    --------------------
100500                  100500:request-a
102000                  102000:request-b
116300                  116300:request-c
~~~

Each request must:

1. Remove events that have fallen outside the window.
2. Count the remaining members.
3. If the limit is reached, reject.
4. If quota remains, add a new member with the current timestamp.
5. Set or extend TTL so empty/inactive keys do not persist forever.

**Checking, writing, and setting TTL must be atomic** if the limit must hold under concurrent requests. A Redis Lua script is the natural choice.

### 9.1. Lua Script for Sliding Log

~~~lua
-- KEYS[1] : Actor's Sorted Set
-- ARGV[1] : current timestamp in milliseconds
-- ARGV[2] : window length in milliseconds (> 0)
-- ARGV[3] : limit (> 0)
-- ARGV[4] : unique event identifier

local now = tonumber(ARGV[1])
local windowMillis = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local eventId = ARGV[4]
local cutoff = now - windowMillis

redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

local current = redis.call('ZCARD', KEYS[1])

if current >= limit then
    return -current
end

local member = ARGV[1] .. ':' .. eventId
redis.call('ZADD', KEYS[1], now, member)
redis.call('PEXPIRE', KEYS[1], windowMillis + 1000)

return current + 1
~~~

This uses the half-open interval **(now − W, now]**: events with a score equal to `cutoff` are removed. If business rules define open/closed boundaries differently, adjust the condition accordingly.

`eventId` must genuinely distinguish events. **Do not use the timestamp alone as the member**, because multiple requests can arrive in the same millisecond; duplicate members cause `ZADD` to update the existing member rather than increasing the stored event count.

The script touches only one key, fitting Redis Cluster's single-slot script constraint. Return values follow the same convention: positive = allowed, negative = rejected.

### 9.2. Calling the Sliding-Log Lua Script from Spring Data Redis

~~~java
import java.time.Clock;
import java.util.List;
import java.util.UUID;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class SlidingLogRateLimiter {

    private static final long WINDOW_MILLIS = 60_000;
    private static final long LIMIT = 100;

    private static final String LUA = """
            local now = tonumber(ARGV[1])
            local windowMillis = tonumber(ARGV[2])
            local limit = tonumber(ARGV[3])
            local eventId = ARGV[4]
            local cutoff = now - windowMillis

            redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', cutoff)

            local current = redis.call('ZCARD', KEYS[1])

            if current >= limit then
                return -current
            end

            local member = ARGV[1] .. ':' .. eventId
            redis.call('ZADD', KEYS[1], now, member)
            redis.call('PEXPIRE', KEYS[1], windowMillis + 1000)

            return current + 1
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public SlidingLogRateLimiter(StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public boolean allow(String userId) {
        String key = "rate:api:sliding:user:" + userId;
        long nowMillis = clock.millis();

        Long result = redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(nowMillis),
                Long.toString(WINDOW_MILLIS),
                Long.toString(LIMIT),
                UUID.randomUUID().toString()
        );

        if (result == null) {
            throw new IllegalStateException("Redis script returned null");
        }

        return result > 0;
    }
}
~~~

This example uses a `Clock` bean as in the fixed-window section. Each call generates a new `UUID` for the member, fitting cases where **every invocation is an independent attempt**. If the system retries the same event from a message broker, generating a new UUID per retry will double-count the event. In that case, pass a **stable event ID** and design proper deduplication.

### 9.3. Why Does Sliding Log Consume More Memory?

With 100,000 active users, each storing up to 100 accepted events in the window, the system can hold millions of ZSet members. Every member includes the timestamp/ID plus Redis data-structure overhead. Text UUIDs as members take more space than compact identifiers or integers.

Estimate roughly:

~~~text
Total live members
≈ total events retained across active sliding windows
≤ concurrent actors × limit
  (assuming script rejects before inserting once quota is full)
~~~

This is only an upper bound on accepted members; also account for key overhead, ZSet metadata, and Redis memory allocation. For very high limits or huge actor counts, run real benchmarks to verify whether Sorted Sets remain viable.

### 9.4. Timing Issues Across Multiple Instances

The example uses application-side `clock.millis()`. If two instances have clock skew, timestamps may not reflect actual chronological order; an event recorded with a "future" timestamp can linger longer than expected.

Reduce drift with clock synchronization (NTP) and clock-skew monitoring. For strict requirements, consider sourcing timestamps from the **Redis server** or designing scripts compatible with your Redis version and replication mode so all requests share a single clock. When running Redis Cluster with multiple primaries, still monitor clock alignment across nodes.

## 10. Approximate Two-Bucket Sliding-Window Counter

Instead of storing every request, we can store **two adjacent fixed-window counters**: the current bucket and the previous bucket.

Suppose each bucket lasts `W = 60 seconds`, and `20 seconds` of the current bucket have elapsed.

~~~text
[  previous 60s bucket  ] [ 20s current bucket | 40s left ]
                          ^
                      bucket start

Last 60-second sliding window:
    last 40s of previous bucket + first 20s of current bucket
~~~

We only know the total of the previous bucket, not which exact second each event fell into. The estimation method assumes events in the previous bucket were roughly uniformly distributed:

\[
\text{estimatedCount}
=
\text{currentCount}
+
\text{previousCount}\times
\left(1-\frac{\text{elapsedInCurrentBucket}}{W}\right)
\]

Example:

~~~text
previousCount = 80
currentCount  = 30
elapsed       = 15 seconds
W             = 60 seconds

estimatedCount = 30 + 80 × (1 - 15/60)
               = 30 + 60
               = 90
~~~

This is **not the exact count** in the last 60 seconds, because we do not know whether the 80 requests in the previous bucket clustered near its start or its end.

### 10.1. Pros

- Keeps only a couple of counters per actor.
- Does not store individual event IDs.
- Smooths boundary transitions compared to pure fixed windows.
- Suits high-scale approximate rate limiting.

### 10.2. Limitations

- Can **underestimate or overestimate** when traffic is uneven.
- If checking and incrementing counters is not atomic, multiple instances can exceed the limit beyond algorithmic error.
- When reading two bucket keys in Redis Cluster, both must map to an appropriate slot if using a multi-key script.
- Requires choosing rounding rules and threshold comparisons; comparing a floating-point estimate to a limit differs from exact event counting.

Example same-slot schema per user when a two-key script is needed on Redis Cluster:

~~~text
rate:api:{user42}:bucket:1893456000
rate:api:{user42}:bucket:1893456060
~~~

The `{user42}` hash tag places both keys in the same slot. Never use a shared hash tag like `{api}` across all users, as that funnels all traffic into a single slot.

## 11. Small Rolling Buckets: Balancing Accuracy and Cost

Another approach divides W seconds into smaller sub-buckets. For example, limiting 100 requests in 60 seconds using 5-second buckets:

~~~text
12 buckets × 5 seconds = 60 seconds
~~~

Each request increments the active 5-second bucket counter. To estimate recent requests, read and sum the relevant buckets.

Smaller buckets reduce boundary error at the expense of more keys/data points and higher read cost.

| Bucket Width | Buckets for 60 Seconds | Characteristics |
|---|---:|---|
| 60 seconds | 1 | Simple fixed window; pronounced boundary bursts |
| 10 seconds | 6 | Less data than sliding log; moderate boundary error |
| 5 seconds | 12 | Smaller bucket error; more keys |
| 1 second | 60 | Higher granularity; increased operations and cardinality |
| Per timestamp | Depends on event count | Sliding log; exact but RAM-heavy |

Summing buckets is never 100% exact at boundaries when storing only bucket totals. You can weight the oldest boundary bucket assuming roughly uniform distribution to reduce error.

In Redis, representation choices include:

- One String key per actor/time bucket.
- One Hash per actor where fields are bucket IDs; however, you must clean up old fields manually because key-level TTL does not expire individual fields on separate schedules.
- Another structure with explicit trimming and age-based cleanup.

Never cram all actors into one giant Hash just to reduce key count. An oversized or hot key creates bottlenecks and cannot distribute across Redis Cluster shards.

## 12. Aggregating Statistics by Minute, Hour, and Calendar Day

Not every time-window counter enforces API limits. For business analytics, fixed buckets are usually clearest.

Example:

~~~text
metrics:orders:minute:1893456000 -> "120"
metrics:orders:minute:1893456060 -> "135"
metrics:orders:minute:1893456120 -> "98"
~~~

Each key holds the order count during `[bucketStart, bucketStart + 60s)`. Keys should have a TTL matching retention, such as 7 days after the bucket closes.

### 12.1. Lua Script to Increment and Set an Absolute Expiration Timestamp

If a bucket must be kept until a specific timestamp, Redis supports `EXPIREAT`. A script can increment the counter and set the exact expiration moment:

~~~lua
-- KEYS[1] = bucket key
-- ARGV[1] = expireAtEpochSeconds

local count = redis.call('INCR', KEYS[1])
redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[1]))
return count
~~~

If an event arrives very late, `expireAtEpochSeconds` may already be in the past; Redis will immediately delete the key. Therefore, define an explicit **late-event policy** before using this pattern.

### 12.2. Java Service Counting Orders per Minute

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class MinuteOrderCounter {

    private static final long WINDOW_SECONDS = 60;
    private static final long RETENTION_SECONDS =
            Duration.ofDays(7).getSeconds();

    private static final String LUA = """
            local count = redis.call('INCR', KEYS[1])
            redis.call('EXPIREAT', KEYS[1], tonumber(ARGV[1]))
            return count
            """;

    private static final RedisScript<Long> SCRIPT = createScript();

    private final StringRedisTemplate redis;
    private final Clock clock;

    public MinuteOrderCounter(StringRedisTemplate redis, Clock clock) {
        this.redis = redis;
        this.clock = clock;
    }

    private static RedisScript<Long> createScript() {
        DefaultRedisScript<Long> script = new DefaultRedisScript<>();
        script.setScriptText(LUA);
        script.setResultType(Long.class);
        return script;
    }

    public Long recordOrder() {
        long nowSeconds = clock.instant().getEpochSecond();
        long bucketStart =
                Math.floorDiv(nowSeconds, WINDOW_SECONDS) * WINDOW_SECONDS;
        long bucketEnd = bucketStart + WINDOW_SECONDS;
        long expireAt = bucketEnd + RETENTION_SECONDS;

        String key = "metrics:orders:minute:" + bucketStart;

        return redis.execute(
                SCRIPT,
                List.of(key),
                Long.toString(expireAt)
        );
    }
}
~~~

This example counts by **processing time**: an event is tallied into the minute the service receives and processes it. If an order occurred at 12:00 yet the message consumer processes it at 12:02, it enters the 12:02 bucket.

For **event-time** statistics, replace `clock.instant()` with a validated timestamp from the event. Specify how late events are accepted, how retries are deduplicated, and when buckets close. A Redis counter cannot automatically detect that a message broker redelivered the same event.

### 12.3. Daily Statistics: Calendar Days Differ from Fixed 86,400 Seconds

A "day" can mean:

- Any contiguous 24-hour span from a given moment.
- A UTC calendar day.
- A calendar day in a business timezone, such as `Asia/Ho_Chi_Minh`.

For "orders today in business hours", derive the key from `ZonedDateTime` or `LocalDate` in the specified timezone:

~~~java
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneId;

ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate businessDate = Instant.now()
        .atZone(businessZone)
        .toLocalDate();

String key = "metrics:orders:day:" + businessDate;
~~~

In timezones observing daylight saving time (DST), a calendar day can last 23 or 25 hours. Do not use `epochSeconds / 86400` when the requirement is a calendar day in a specific timezone. Compute the expiration timestamp from **the start of the next day in that same timezone** plus retention.

## 13. Key Design to Control Cardinality

For rate limits, cardinality is the product of the varying dimensions:

~~~text
active actors
× policies/endpoints
× concurrently retained buckets
~~~

Example:

~~~text
100,000 users
× 4 rate-limit policies
× 2 concurrent buckets (current bucket + grace)
≈ 800,000 keys
~~~

This estimate assumes every active user triggers every policy while previous buckets remain within their retention window. Real numbers may be lower or higher depending on traffic and retention.

The schema should be clear:

~~~text
rate:login:user:42:bucket:1893456000
rate:search:tenant:acme:bucket:1893456000
metrics:orders:minute:1893456000
~~~

Rules:

1. Never put full URL queries, access tokens, or raw request bodies into keys.
2. Actor IDs must be stable, canonicalized, and length-bounded.
3. Avoid putting request IDs into fixed-counter keys; requests must **increment the same** bucket key.
4. When using multiple policies, include the policy in the key so one endpoint's quota does not affect another.
5. In multi-tenant systems, bound how many dynamic actors and policies can be created.
6. When keeping metric buckets, define retention and an established export pipeline.

### 13.1. TTL Directly Affects Key Count

Simple estimation rule:

~~~text
Concurrent live keys ≈ unique key creation rate × key lifetime
~~~

For instance, if an API creates 300 new keys per second with a 15-minute TTL:

~~~text
300 × 15 × 60 = 270,000 keys
~~~

If requests repeatedly hit the same user/bucket key, new key creation rate is lower than request rate. Measure **distinct active actors/buckets**, rather than mechanically multiplying requests/second by TTL.

### 13.2. Hot Keys Differ from High Key Cardinality

If every request increments the same `metrics:orders:minute:...` key, that single counter can become a **hot key** even though it occupies only a few bytes. Redis executes commands very fast, yet an ultra-hot key still concentrates load on one shard.

Design options depending on requirements:

- Keep a single shared counter while traffic and latency remain comfortable.
- Shard the counter logically, e.g., `metrics:orders:minute:<bucket>:shard:<n>`, picking a shard deterministically or randomly per event; readers must sum all shards.
- Use a stream/broker for events and aggregating consumers if high throughput and replay are needed.
- When an **app-wide atomic rate limit** per actor is required, you cannot casually shard the counter and sum asynchronously while keeping the exact same semantics.

Sharding increases key count and read aggregation effort; apply it only when evidence shows a key is actually a bottleneck.

## 14. Redis Cluster and Multi-Key Scripts

In Redis Cluster, keys are partitioned across hash slots. A Lua script touching multiple keys usually requires all participating keys to be in the **same hash slot**.

Example two-bucket sliding-window counter:

~~~text
rate:api:{user42}:bucket:1893456000
rate:api:{user42}:bucket:1893456060
~~~

The `{user42}` hash tag puts keys for the same user in the same slot. If a script touches only **one key**, like the fixed-window and sliding-log scripts above, there is no need to force hash tags across unrelated keys.

Avoid:

~~~text
rate:{api}:user:1:bucket:...
rate:{api}:user:2:bucket:...
rate:{api}:user:3:bucket:...
~~~

Because every key carrying `{api}` hashes to one slot, losing load distribution across primaries.

During node scaling or failover, the Spring Data Redis client must be configured as Cluster-aware. Commands may briefly experience timeouts or redirections; an atomic script guarantees execution according to conditions at the target node, not that every request during an outage is counted exactly once.

## 15. Choosing a Time Source and Handling Clock Skew

Windowed counters depend heavily on timestamps.

### 15.1. Application-Side Time

Pros: simple code, easy unit testing with `Clock.fixed(...)`, and no extra round trip for time. Cons: multiple instances can drift, especially around bucket boundaries.

Example:

~~~text
Instance A thinks it is 12:00:59.990 -> bucket 12:00
Instance B thinks it is 12:01:00.020 -> bucket 12:01
~~~

Two instances can write to two different keys for requests occurring virtually simultaneously. Synchronize clocks and monitor drift. Never trust browser-supplied timestamps for server-side rate limiting.

### 15.2. Redis-Side Time

Redis provides the `TIME` command returning server time. When all decisions must rely on one time source, you can design scripts or flows fetching Redis time. However:

- Account for Redis version and script/replication determinism rules.
- In Redis Cluster, multiple primaries run on multiple hosts; host clocks still need synchronization.
- Using Redis time does not prevent retries, redeliveries, or failover write loss.

For event-time analytics, event timestamps and processing timestamps carry different meanings; never substitute one for the other implicitly.

### 15.3. Use Epoch for Fixed Durations, Timezones for Calendar Windows

- "Every 60 seconds since Unix epoch": compute via epoch seconds.
- "Business day in Vietnam": use `ZoneId` and `LocalDate`.
- "Last 60 seconds": subtract duration from current timestamp without rounding to minute boundaries.

Incorrect timestamp rounding is a common bug easily missed by unit tests that run only mid-minute.

## 16. Consistency and Retry Constraints

### 16.1. Redis Commands Are Atomic, Yet HTTP Requests Can Repeat

Flow:

~~~text
Client -> API -> Redis INCR succeeds
                 |
                 +-- API times out before sending response
Client retries same request
       -> Redis INCR runs again
~~~

From Redis's perspective, two increments occurred, even though the client considers it one logical request. For rate limiting that counts "every attempt", this may be fine. For order or invoice counts, this is **double-counting**.

To count each business event exactly once, use a stable event ID, deduplication, and an authoritative event source. Lua can check a marker and increment a counter in one script when keys share a slot, yet you must still handle TTL, retries, failovers, and source data. Never equate a single `INCR` with an exactly-once system.

### 16.2. INCR Is Not Atomic with Database Transactions by Default

Example order creation:

~~~text
INSERT order into PostgreSQL
INCR metrics:orders:minute:...
~~~

If the DB commits yet Redis fails, the counter undercounts. If Redis increments first yet the DB transaction rolls back, the counter overcounts. There is no automatic distributed transaction merely from using Spring Data Redis inside the same Spring Boot app.

For rebuildable metrics, a common approach is committing events/orders durably to the primary store, then updating Redis asynchronously via events/outbox with periodic reconciliation. Avoid relying on Redis counters alone for auditable financial figures.

### 16.3. Replication and Failover

If a Redis primary drops before replicas receive recent increments, some increments may disappear after failover. Redis Cluster or Sentinel improves availability, yet does not turn default asynchronous replication into zero-data-loss synchronous writes.

Strict quota counters must evaluate the risk of granting extra requests during failover. For high-security flows, define protective policies when Redis is unavailable and apply defense in depth.

## 17. When Redis Fails: Fail-Open or Fail-Closed?

For rate limiting, Redis errors require a business decision:

| Policy | Behavior on Redis Timeout | Typical Consideration |
|---|---|---|
| **Fail-open** | Allow request through and emit error metrics | High-availability endpoints where rate limiting is secondary protection |
| **Fail-closed** | Reject or return temporary error | Sensitive endpoints where quotas are a core security requirement |
| **Degraded mode** | Apply local/secondary limits, shed load, or use fallback quota | Systems designed with multi-layer defenses up front |

There is no single right answer for every API. For example, brute-force login protection on Redis failure may require a stricter policy than soft throttling on a public read endpoint.

**Never swallow every exception and return `allowed = true` without an explicit decision.** Nor should you retry counter-increment scripts indefinitely, because a timeout can happen after Redis already executed the command. Configure explicit timeouts, metrics, alerts, and bounded retries.

## 18. Expiration, Eviction, and Limit Accuracy

Redis has `maxmemory` and `maxmemory-policy` settings. If an active rate-limit counter gets evicted before its TTL expires, the next request creates a fresh counter and regains full quota.

Therefore:

- For critical rate limits, select an appropriate Redis deployment and eviction policy.
- Do not let evictable caches crowd out counters that must survive through their windows.
- Monitor `evicted_keys` and `expired_keys`; eviction is not scheduled expiration.
- Set TTLs on temporary keys to prevent unbounded growth, yet ensure TTLs are long enough for algorithm semantics.
- When Redis hits memory limits under `noeviction`, writes can fail; applications need corresponding error handling.

Sliding logs retain many members and create heavier memory pressure than fixed counters. Size capacity using **concurrent actors × limit × member size**.

## 19. Observing Counters in Redis and Spring

Redis CLI:

~~~bash
redis-cli GET rate:api:user:42:bucket:1893456000
redis-cli TTL rate:api:user:42:bucket:1893456000

redis-cli ZCARD rate:api:sliding:user:42
redis-cli ZRANGE rate:api:sliding:user:42 0 -1 WITHSCORES
redis-cli PTTL rate:api:sliding:user:42

redis-cli INFO keyspace
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO commandstats
~~~

Explanation:

- `GET`: reads String counter; returns nil when absent.
- `TTL`: remaining seconds; `-1` if key exists without TTL; `-2` if key absent.
- `ZCARD`: number of events/members stored in sliding log. If uncleaned during idle periods, this may include events already outside the window until the key expires or the next request triggers cleanup.
- `ZRANGE ... WITHSCORES`: inspect timestamps and IDs for small-scale debugging.
- `PTTL`: inspect expiration in milliseconds.
- `INFO`: key counts, RAM, expired/evicted keys, command stats.

Never run `KEYS *` routinely across large production keyspaces to count per-user keys. When investigating, use `SCAN` with prefix matching and reasonable batch counts, keeping in mind scan output is not a consistent snapshot.

### 19.1. Recommended Application-Side Metrics

| Metric | What It Reveals |
|---|---|
| Allowed vs. rejected requests per policy | Whether rate limits are impacting users |
| Redis script latency p50/p95/p99 | Whether latency grows with traffic or ZSet operations |
| Redis errors/timeouts | When fail-open/closed policies are triggering |
| Active actors/keys count | Actual key cardinality |
| Keyspace memory usage | When to scale capacity or change algorithms |
| Clock skew | Whether bucket boundaries across instances are reliable |
| Duplicate/late event ratio | Accuracy of time-based statistics |

Watching `INCR` latency alone is not enough to know the system is counting accurately. Track rejection rates, key counts, and late/lost event rates as well.

## 20. Exercises: Choosing the Right Algorithm for the Requirement

### Exercise 1 — Per-Calendar-Minute API Limit

**Prompt:** a user may send up to 120 requests per UTC minute. Sending 120 requests right before the minute ends and 120 right after the next starts is acceptable.

**Design:** fixed window, keys keyed by `userId + bucketStart`, Lua checking limit and incrementing atomically, TTL to bucket end + grace. Each actor/policy uses at most a couple of concurrent live keys.

### Exercise 2 — Limit Login Attempts in the Last 15 Minutes

**Prompt:** no more than 5 failed attempts in any contiguous 15-minute span.

**Design:** ZSet sliding log when strict timestamp semantics are needed. Unique member ID; score from chosen time source. Prune events `≤ now − 15 minutes`, count, and add atomically. Whether rejected requests also record attempts is a policy choice; the sample script counts accepted attempts only.

Also consider multi-layer credential-stuffing defenses, Redis error handling, and clock skew.

### Exercise 3 — Hourly Order Counts for a Dashboard

**Prompt:** display hourly order totals over 7 days; events can arrive up to 10 minutes late.

**Design:** one-hour fixed buckets, keys keyed by `bucketStartEpochSeconds`, expiration set to hour end + retention. Decide between event-time and processing-time; allow late events within the 10-minute window. If order counts must be exact, aggregate from the authoritative database and reconcile buckets on reprocessing.

### Exercise 4 — Smooth Rate Limiting at Very Large User Scale

**Prompt:** millions of actors, must curb boundary bursts, yet memory cannot hold per-request ZSets.

**Design:** consider a two-bucket sliding-window counter, small rolling buckets, or token bucket. Accept bounded estimation error and benchmark impact. For multi-key Lua on Redis Cluster, design per-actor hash tags.

### Exercise 5 — Why Can Two-Command INCR + EXPIRE Leave Keys Without TTL?

**Prompt:** after several days, Redis holds thousands of temporary counters with `TTL = -1`.

**Explanation:** the client or process can fail between the two commands. The fix is atomic execution via script, ensuring every new key gets its intended TTL and running a cleanup process for orphaned keys with known ownership.

### Exercise 6 — Estimating Key Count

**Prompt:** 50,000 active users, 3 rate-limit types, retaining current and one previous bucket counters.

~~~text
50,000 users × 3 policies × 2 buckets
= 300,000 counter keys (upper-bound estimate under assumptions)
~~~

Switching to a sliding log retaining 100 events per actor/policy could reach up to 15 million members if every actor uses full quota. Estimate payload and metadata sizes and measure on a real Redis instance.

## 21. Quick Selection Table

| Question | Recommended Direction |
|---|---|
| Only need per-minute/hour/day counts | Fixed buckets with time-based keys |
| Want limit starting from first request | Stable counter key + TTL set only on creation |
| Need exact count over last W seconds | Sliding-log Sorted Set |
| Want less RAM and tolerate estimation error | Sliding counter or rolling buckets |
| Want smooth rate with controlled bursts | Token bucket with its own semantics |
| Need accurate limits across concurrent instances | Redis atomic operation or Lua script |
| Need to prevent TTL-less keys | Set expiration inside the same atomic script/operation |
| Need Redis Cluster with multi-key scripts | All involved keys must share a hash slot |
| Need exact business event counts across retries | Event IDs, deduplication, and authoritative storage |
| Should requests pass when Redis fails | Endpoint-specific fail-open/closed policy |
| Can critical counters be evicted | Evaluate memory policy, durability, and workload isolation |

## 22. Design Decision Flowchart

~~~text
                      Need time-based counting
                                |
                    Calendar-aligned statistics?
                         /             \
                       Yes              No
                        |                |
              Fixed time bucket     Need exact last
              by min/hour/day         W seconds?
                                       /         \
                                     Yes          No
                                      |             |
                               Accept RAM for     Fixed window
                               timestamps?        sufficient?
                                  /       \          /     \
                                Yes       No       Yes      No
                                 |          |        |        |
                            Sliding ZSet  Sliding  Fixed   Review policy /
                                          counter  window  token bucket
                                 \           |        /
                                  +----------+-------+
                                             |
                              Multiple concurrent instances?
                                             |
                                   Atomic Redis / Lua
                                             |
                             Key schema + TTL + RAM bounds
                                             |
                            Clock + retry + failover policy
                                             |
                                   Metrics and alerts
~~~

**Guiding principle:** first define the **time window** precisely; only then choose Redis keys and commands. For bucketed counters, `INCR` and TTL suffice to track counts, provided they are combined atomically when lifecycle matters. For exact sliding windows, store event timestamps or an equivalent model; a single counter for the current minute cannot reconstruct the history of the last 60 seconds.

Spring Data Redis helps implement these choices cleanly with `StringRedisTemplate`, `RedisScript`, and String/Sorted Set operations. System correctness ultimately still depends on algorithm selection, time handling, retry semantics, data recovery, and Redis operational policies.
