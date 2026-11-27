# Rate Limiting with Fixed Window, Sliding Window, or Token Bucket in Spring Data Redis

## 1. Goal and Context

**Rate limiting** is the mechanism that decides how many operations a user, API key, tenant, or request source may perform within a period of time. It protects the system against overload, prevents abuse, reduces the cost of resource-intensive operations, and enforces quota policies.

For example, an order API has the following rules:

- An account may send at most **60 requests/minute** to the status endpoint.
- An account may attempt verification code entry at most **5 times/minute**.
- The search endpoint allows **10 consecutive requests**, then refills **2 access permits per second**.
- Spring Boot instances deployed behind a load balancer must share **the same quota**, rather than each instance maintaining an independent limit.

Redis fits well as a shared rate-limit state store because it supports counters, TTLs, Sorted Sets, Hashes, and Lua scripts that execute atomically on a Redis server. Spring Data Redis provides `StringRedisTemplate`/`RedisTemplate` to issue commands or execute scripts from Java.

Three commonly used algorithms:

1. **Fixed window:** counts requests within a time interval with fixed boundaries.
2. **Sliding window:** counts requests falling inside a rolling time window looking backward from the present.
3. **Token bucket:** maintains a bounded supply of tokens, consumes tokens per request, and refills at a configured rate.

This lesson walks through choosing an algorithm for your business needs, designing Redis keys, implementing Lua to avoid race conditions, integrating with Spring Boot, and handling Redis failures properly.

> **Scope:** These examples limit the number of **accepted requests**, not the count of successful HTTP responses. If you only want to deduct quota after business processing succeeds, you need a reservation/refund quota workflow different from pre-request blocking.

## 2. Define the Rate Limit Before Writing Code

A rate-limit policy typically includes these components:

| Component | Example | Meaning |
|---|---|---|
| Subject | User `u-42` | Who is subject to the limit |
| Resource/action | `POST /api/orders` | Which operation is being limited |
| Algorithm | Fixed / Sliding / Bucket | How permit eligibility is computed |
| Limit/capacity | `60` | Maximum count or bucket capacity |
| Window/refill | `60 seconds` or `2 tokens/second` | Measurement span or refill rate |
| Cost | `1 token` | Cost per request; can be higher for heavy operations |
| Scope | User, API key, tenant, IP | How quotas are partitioned |
| Failure policy | Fail-open / fail-closed | How to behave when Redis fails |
| HTTP behavior | `429` and `Retry-After` | Response returned to blocked clients |

For example, "60 requests/minute" is not enough to infer the exact desired behavior. Should a user sending 60 requests in the last second of the current minute and 60 requests in the first second of the next minute be allowed? A fixed window can allow that burst; a sliding window restricts it more tightly.

You also need to decide: does the limit apply **per user**, **per IP address**, or **across an entire tenant**? In a multi-instance system, if each instance keeps counters in JVM memory, the system-wide quota will not be shared accurately. Redis solves state sharing across instances, provided Redis operations are designed atomically so concurrent requests cannot exceed the quota.

## 3. Comparing the Three Algorithms

| Algorithm | How It Works | Pros | Cons | Best Suited For |
|---|---|---|---|---|
| **Fixed window** | Counts requests in a time frame aligned to fixed ticks | Simple; O(1) memory per subject; easy to implement | Can allow bursts near 2× the limit across two window boundaries | General API throttling, easy-to-understand quotas |
| **Sliding window log** | Stores each request's timestamp and removes entries outside the window | Accurate over rolling windows; no fixed-window boundary bursts | O(L) memory per subject storing up to L requests; ZSET overhead | Login/OTP, burst-sensitive endpoints |
| **Token bucket** | Bucket with capacity C; tokens refill at rate R/sec; each request costs tokens | Allows controlled bursts; steady average rate; O(1) state | Requires managing fractional tokens, refills, and timestamps | APIs with uneven traffic prioritizing short burst UX |

In the table, **L** is the maximum number of requests within one sliding window. Variants like **sliding-window counters** use multiple time buckets and interpolation to save memory, though they are more approximate than sliding logs and carry different trade-offs. This lesson uses **sliding log with a Redis Sorted Set** to clearly illustrate rolling-window behavior.

### Illustrating Boundary Bursts

Limit: 5 requests per 60 seconds.

```text
Minute A: [.................................xxxxx]
Minute B: [xxxxx.................................]
          ^ boundary between two windows

Fixed window:
  5 requests at the very end of minute A + 5 requests at the start of minute B
  => can allow 10 requests in a very short span.

60-second sliding window:
  The first 5 requests already consumed the quota for the most recent 60 seconds;
  the next 5 requests can be rejected until old entries leave the window.

Token bucket:
  Allows bursts up to the currently available tokens;
  once depleted, tokens refill at the configured rate.
```

No single algorithm is always best. The choice depends on burst risk, memory budget, key count, and how limits need to be explained to clients.

## 4. Designing Redis Keys Before Implementing

Each subject and policy needs an independent identifier.

Examples:

```text
rl:v1:order-read:{tenant42-user17}
rl:v1:checkout:{tenant42-user17}
rl:v1:login:{account-hash}
rl:v1:search:{api-key-hash}
```

In Redis Cluster, the segment inside braces `{...}` is a **hash tag**, allowing keys with the same tag to map to the same hash slot when multi-key operations are needed. The scripts in this lesson operate on **one key**, yet clear tagging avoids mistakes if the model expands.

Guidelines:

1. **Never take an untrusted header directly as the subject.** A client-supplied `X-User-Id` header does not prove identity; extract user IDs from authentication or verified API keys.
2. **Separate policies.** Order-read rate limits and checkout rate limits should not share a key if they have separate budgets.
3. **Avoid exposing personal information in keys.** If the subject involves an email, phone number, or API key, use an appropriate hash or opaque identifier.
4. **Version namespaces.** When changing algorithms or making incompatible configuration changes, a `rl:v2:...` prefix enables safer policy transitions.
5. **Bound length and cardinality.** Each new IP or user creates another key. TTL is essential to clean up inactive subjects.
6. **Account for multiple clients and proxies.** If rate-limiting by IP, resolve the client IP from a trusted reverse proxy; never trust arbitrary client-supplied `X-Forwarded-For` headers.
7. **A subject may face multiple rate-limit layers.** For example, per-account limits plus tenant-wide limits—though updating multiple keys requires considering atomicity of the overall decision.

In these examples, key names are built from a **trusted, normalized subject**. Never let clients freely choose the Redis key name passed to a Lua script.

## 5. Why Not Use a Naive GET Then SET?

Consider a fixed-window counter stored at `rl:v1:login:{u42}`:

```text
Request A: GET count -> 4
Request B: GET count -> 4

Request A: sees 4 < 5, SET count = 5 -> allow
Request B: sees 4 < 5, SET count = 5 -> allow
```

With a limit of 5, both requests are accepted even though only one slot remained. The cause is a **read–check–write race condition**.

A standalone Redis `INCR` is atomic, but if the application separately calls `EXPIRE`, compares quota, reads time, and updates multiple fields across separate commands, **the overall workflow can still interleave or fail partway**.

Options:

- A server-side Redis operation expressive enough to handle the condition.
- A Lua script executing both check and update in a single pass.
- A Redis Function or a properly designed lock/transaction with retries.
- For durable business quotas, another data source capable of enforcing consistency constraints.

This lesson uses **Lua scripts** via `StringRedisTemplate.execute(...)`. Redis executes a script atomically relative to other commands on the same server, so two concurrent requests cannot read the same stale state and both claim the last slot.

**Limitation:** script atomicity does not imply automatic rollback if a command inside the script errors after prior writes. Validate arguments beforehand and write scripts defensively to avoid mid-execution errors. On Redis Cluster, keys accessed by a script must be passed properly via `KEYS` and respect hash slot rules.

## 6. Fixed Window: Counter per Fixed Time Frame

### 6.1. Principle

With `limit = 5` and `windowSeconds = 60`, time is divided into frames:

```text
[12:00:00, 12:01:00) → window 1
[12:01:00, 12:02:00) → window 2
[12:02:00, 12:03:00) → window 3
```

Logically, each frame keeps its own count. Moving to a new frame resets the count to 0. A request is accepted if the current count is less than the limit.

Two common storage layouts:

- Create a new key per time frame, such as `rl:user:123:minute:123456`.
- Use **one fixed Redis Hash** per subject containing `window` and `count`, resetting `count` whenever the window index changes.

The example below chooses **one fixed hash** to avoid dynamically constructing key names inside the Lua script. This also works cleanly with the Redis server's `TIME`, avoiding clock skew across application instances.

### 6.2. Redis Hash Structure

```text
Key: rl:v1:fixed:checkout:{u42}
Type: hash

window = 28400001
count  = 4

TTL: windowSeconds + a small buffer from the most recent request
```

`window` represents the window index, calculated as:

```text
windowIndex = floor(redisEpochSeconds / windowSeconds)
```

When `windowIndex` changes, the script resets the counter even if the Redis key has not expired yet.

### 6.3. Lua Script: fixed-window.lua

Inputs:

- `KEYS[1]`: state key for the subject and policy.
- `ARGV[1]`: `limit`, positive integer.
- `ARGV[2]`: `windowSeconds`, positive integer.

Result: `{allowed, remaining, retryAfterMs}`.

```lua
-- redis/fixed-window.lua
-- Inputs validated in Java as limit > 0, windowSeconds > 0.

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowSeconds = tonumber(ARGV[2])

-- Use Redis clock so all instances share the same window boundary.
local nowSeconds = tonumber(redis.call('TIME')[1])
local windowIndex = math.floor(nowSeconds / windowSeconds)

local storedWindow = redis.call('HGET', key, 'window')
local count

if not storedWindow or tonumber(storedWindow) ~= windowIndex then
    redis.call('HSET', key, 'window', windowIndex, 'count', 0)
    count = 0
else
    count = tonumber(redis.call('HGET', key, 'count') or '0')
end

local allowed = 0

if count < limit then
    count = redis.call('HINCRBY', key, 'count', 1)
    allowed = 1
end

-- Key may survive into the next window, but windowIndex
-- ensures the counter resets on time.
redis.call('EXPIRE', key, windowSeconds + 2)

local remaining = math.max(0, limit - count)
local secondsUntilNextWindow =
    windowSeconds - (nowSeconds % windowSeconds)

local retryAfterMs = 0
if allowed == 0 then
    retryAfterMs = secondsUntilNextWindow * 1000
end

return {allowed, remaining, retryAfterMs}
```

### 6.4. Example Output Flow

```text
Policy: max 3 requests / 60 seconds
Key: rl:v1:fixed:checkout:{u42}

12:00:10  Request #1 → allowed=1, remaining=2
12:00:20  Request #2 → allowed=1, remaining=1
12:00:30  Request #3 → allowed=1, remaining=0
12:00:40  Request #4 → allowed=0, remaining=0,
                       retryAfter≈20 seconds
12:01:00  Request #5 → new window, allowed=1, remaining=2
```

The script **does not increment count when blocked**, so state only tracks accepted requests in the current window. If you want to count rejected requests, emit separate metrics rather than using this policy's counter to infer total attempts.

### 6.5. Cost and Characteristics

- Redis stores **one small hash per subject/policy**: O(1) memory.
- Each check runs one script, reading and mutating a couple of fields on the same key.
- Resets align with server time, independent of app instances.
- **Bursts approaching 2 × limit can occur at window boundaries.**
- If the policy changes while keys still exist, the script uses the new limit/window; changing window size can cause unexpected resets. Version the namespace when changing policies significantly.

If the business only needs "roughly N requests per minute" and favors low cost, fixed window is often sufficient.

## 7. Sliding Window Log: Accuracy Over Rolling Time

### 7.1. Principle

A sliding window does not divide time into fixed frames. At time `now`, it counts only requests falling within:

```text
(now - windowMs, now]
```

For example, at most 5 requests in any 60-second window. If a user made 5 requests between 12:00:50 and 12:00:54, a request at 12:01:00 is still blocked; the quota does not reset merely because the minute rolled over.

### 7.2. Using a Redis Sorted Set

Each accepted request is a member of a Redis Sorted Set:

- **score:** request timestamp in milliseconds from the Redis server.
- **member:** a **unique ID per attempt**, such as a UUID.
- **key:** identifies subject and policy.

```text
Key: rl:v1:sliding:otp:{u42}

Score (ms)       Member
1700000000100    6718d3d2-...
1700000000350    12a9fb10-...
1700000000600    cd1edb9f-...
```

A Redis ZSET **does not allow duplicate members** in the same set. If you used the timestamp as the member and two requests arrived in the same millisecond, one would overwrite the other. Thus, this example generates a **fresh UUID for each check**.

To evaluate quota:

1. Read current time from Redis `TIME`.
2. Evict elements with score **less than or equal to** `now - windowMs`.
3. Count remaining elements with `ZCARD`.
4. If below the limit, add the new member with `ZADD` and allow.
5. If at the limit, deny.
6. Set a TTL so the ZSET is cleaned up after the subject becomes inactive.
7. If denied, use the oldest entry's timestamp to estimate when quota reopens.

All steps run **inside a single script**.

### 7.3. Lua Script: sliding-window.lua

Inputs:

- `KEYS[1]`: policy ZSET key.
- `ARGV[1]`: `limit`.
- `ARGV[2]`: `windowMs`.
- `ARGV[3]`: unique request ID generated by the service.

Result: `{allowed, remaining, retryAfterMs}`.

```lua
-- redis/sliding-window.lua
-- Java validates limit > 0, windowMs > 0,
-- and generates a fresh UUID for every attempt.

local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local requestId = ARGV[3]

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
    + math.floor(tonumber(time[2]) / 1000)

local cutoff = nowMs - windowMs

-- Window is (cutoff, nowMs], so drop score == cutoff too.
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

local count = redis.call('ZCARD', key)
local allowed = 0

if count < limit then
    -- Every requestId must be unique so old members are not overwritten.
    local inserted = redis.call('ZADD', key, 'NX', nowMs, requestId)

    if inserted == 1 then
        count = count + 1
        allowed = 1
    end
end

-- Keep state long enough until the subject stops retrying.
-- Every request refreshes the cleanup deadline.
if count > 0 then
    redis.call('PEXPIRE', key, windowMs + 1000)
end

local remaining = math.max(0, limit - count)
local retryAfterMs = 0

if allowed == 0 then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')

    if #oldest >= 2 then
        local oldestMs = tonumber(oldest[2])
        retryAfterMs = math.max(
            1,
            math.ceil(oldestMs + windowMs - nowMs + 1)
        )
    else
        -- Unusual edge case such as a duplicate requestId.
        retryAfterMs = 1
    end
end

return {allowed, remaining, retryAfterMs}
```

**Note on request ID:** Java code must generate a new UUID on every quota check. Never reuse one ID across an entire session or user. If the same member is submitted again, `ZADD NX` does not add a new record; this example chooses not to grant a permit in that anomalous case. This is a request counter, not a business idempotency mechanism.

### 7.4. Explaining `retryAfter` in Sliding Window

If the key holds 5 accepted requests and the oldest has score `t0`, quota can reopen at the earliest when:

```text
now > t0 + windowMs
```

Because the script removes entries with score `<= now - windowMs`, the approximate wait is:

```text
retryAfterMs = max(1, t0 + windowMs - now + 1)
```

This is an estimate based on state at **check time**. Other clients might claim the slot right afterward, so the server does not guarantee that a request retried right at `Retry-After` will be accepted.

### 7.5. Cost

- Each subject can store up to roughly `limit` accepted members per window.
- `ZADD` complexity generally scales logarithmically with element count.
- `ZREMRANGEBYSCORE` incurs extra work proportional to expired entries removed.
- Memory grows with subjects multiplied by quota, not just subject count.
- With millions of subjects or huge limits, evaluate Redis memory and CPU costs carefully.

If you need 5 OTP attempts per minute per account, O(5) per subject is typically affordable. If you need to track 100,000 requests/minute per user across millions of users precisely, sliding log may be too expensive; consider sliding-window counters, token buckets, or a dedicated gateway.

## 8. Token Bucket: Allowing Bursts and Refilling Tokens

### 8.1. Principle

A bucket has:

- **capacity (C):** maximum tokens.
- **refill rate (R):** tokens added per second.
- **cost:** tokens consumed per request.
- **tokens:** current token count, possibly fractional.
- **lastUpdateMs:** timestamp of the last update.

Before evaluating a request, compute:

```text
elapsedSeconds = max(0, now - lastUpdate) / 1000

tokens = min(
    capacity,
    tokens + elapsedSeconds * refillRate
)

If tokens >= cost:
    tokens = tokens - cost
    ALLOW
Else:
    DENY
```

Example policy `capacity=10`, `refillRate=2 tokens/second`, `cost=1`:

```text
Initially: 10 tokens
10 consecutive requests → consume all 10 tokens
11th request immediately → blocked

After 0.5 seconds: recovers roughly 1 token
After 1 second: recovers roughly 2 tokens
After 5 seconds idle: bucket can be full at 10 tokens
```

Token bucket makes sense when you want to allow **bounded bursts** while forcing the average rate toward the refill rate under sustained traffic.

### 8.2. Redis Hash Structure

```text
Key: rl:v1:bucket:search:{u42}
Type: hash

tokens     = 7.500000000
updated_ms = 1700000000500
```

No per-request record is needed. A single hash holding the bucket state suffices.

### 8.3. Lua Script: token-bucket.lua

Inputs:

- `KEYS[1]`: bucket hash key.
- `ARGV[1]`: `capacity`, positive number.
- `ARGV[2]`: `refillTokensPerSecond`, positive number.
- `ARGV[3]`: `cost`, positive number not exceeding capacity.

Result: `{allowed, remainingMilliTokens, retryAfterMs}`. The `remainingMilliTokens` value is remaining tokens multiplied by 1,000 to return an integer for easy decoding via Spring Data Redis.

```lua
-- redis/token-bucket.lua
-- Java validates capacity > 0, rate > 0,
-- 0 < cost <= capacity.

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local cost = tonumber(ARGV[3])

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
    + math.floor(tonumber(time[2]) / 1000)

local state = redis.call(
    'HMGET', key, 'tokens', 'updated_ms'
)

local tokens = tonumber(state[1]) or capacity
local previousMs = tonumber(state[2]) or nowMs

-- Avoid negative elapsed time if the clock steps backward.
if nowMs < previousMs then
    nowMs = previousMs
end

local elapsedMs = nowMs - previousMs

tokens = math.min(
    capacity,
    tokens + elapsedMs * rate / 1000
)

local allowed = 0

if tokens >= cost then
    tokens = tokens - cost
    allowed = 1
end

-- Keep sufficient precision for typical API quotas.
redis.call(
    'HSET',
    key,
    'tokens', string.format('%.9f', tokens),
    'updated_ms', nowMs
)

-- After enough idle time for the bucket to refill completely,
-- old state is no longer needed.
local idleTtlSeconds = math.max(
    1,
    math.ceil(capacity / rate) + 1
)

redis.call('EXPIRE', key, idleTtlSeconds)

local retryAfterMs = 0

if allowed == 0 then
    retryAfterMs = math.max(
        1,
        math.ceil((cost - tokens) / rate * 1000)
    )
end

local remainingMilliTokens = math.max(
    0,
    math.floor(tokens * 1000)
)

return {allowed, remainingMilliTokens, retryAfterMs}
```

### 8.4. Why Does a Bucket Need a TTL?

If a user sends a few requests and never returns, their hash should not linger forever. Once the bucket has had enough time without requests to refill completely, the old state is equivalent to the initial `tokens = capacity` state. When the key expires, the next check treats it as a fresh full bucket.

Example:

```text
capacity = 10
rate = 2 tokens/second

Time to refill from empty = 10 / 2 = 5 seconds
Example idle TTL = ceil(5) + 1 = 6 seconds
```

If the application regularly receives requests, the script refreshes the TTL and retains state; if idle long enough, Redis reclaims the key.

**Limitation:** Lua uses floating-point numbers for token math. For quotas requiring ultra-high precision or tiny rates, use fixed-point integers with appropriate units instead of decimal formatting. The demo uses 9 decimal places for standard API quotas, not for monetary billing or financial limits.

### 8.5. Variable Request Costs

Not every request consumes 1 token:

```text
GET /api/search?q=...       cost = 1
POST /api/reports/export    cost = 5
POST /api/ai/batch          cost = 10
```

With policy `capacity = 20`, `refillRate = 1 token/second`, a report export costing 5 tokens is blocked when only 3 tokens remain and becomes eligible in roughly 2 seconds.

Cost-based policies control resources by relative weight. However, they **do not measure actual CPU, RAM, or real consumption incurred**; for tasks whose weight varies after starting, you need reservation/refund policies or actual usage metering.

## 9. Comparing Limits on the Same Traffic

Consider a user sending a burst of requests, then pausing:

| Scenario | Fixed window | Sliding log | Token bucket |
|---|---|---|---|
| Burst near minute boundary | Can approach 2 × limit | Enforces limit over actual rolling window | Bounded by available tokens |
| Steady, sustained requests | Tracks quota per frame | Enforces across all sliding windows | Average rate bounded by refill rate |
| Must store each timestamp | No | Yes | No |
| Wait time returned | Until next frame boundary | Until oldest request leaves window | Until enough tokens accumulate |
| Memory per subject | O(1) | O(limit) | O(1) |
| Behavior after long idle | New window resets to 0 | Old ZSET cleaned up | Bucket refills to full |
| Good for strict OTP limits | Has boundary bursts; evaluate carefully | Often better suited | Suitable if capacity is small |
| Good for bursty API traffic | Boundary bursts poorly controlled | May reject too harshly | Flexible with bounded bursts |

An API gateway may enforce **multiple limit tiers**, such as a per-user token bucket and a per-tenant fixed window. However, if two scripts update two independent keys, user quota may be deducted even when tenant quota rejects the request. When an atomic combined decision is needed, design a dedicated script accessing keys in the same slot (on Redis Cluster) or use a specialized quota manager.

## 10. Spring Boot and Spring Data Redis Integration

### 10.1. Dependencies

For Spring Boot and MVC REST APIs:

**Gradle:**

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-redis")
    implementation("org.springframework.boot:spring-boot-starter-web")
}
```

**Maven:**

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-redis</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
```

Local Redis configuration:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

`StringRedisTemplate` works well for string keys and Lua script arguments. In standard Spring Boot setups, the Redis starter provides a `RedisConnectionFactory` and suitable templates via auto-configuration. In production, add appropriate authentication, TLS, endpoints, topology, and timeouts.

### 10.2. Placing Lua Scripts in Resources

Create three resource files in the application:

```text
src/main/resources/
└── redis/
    ├── fixed-window.lua
    ├── sliding-window.lua
    └── token-bucket.lua
```

Their contents correspond to the three scripts presented above. Storing scripts under `resources` packages them inside the artifact, making versioning, review, and deployment straightforward.

**Note:** These paths illustrate a sample project layout; this lesson does not require you to create extra files. You can also use `DefaultRedisScript.setScriptText(...)` if your project prefers keeping Lua inline in Java code.

### 10.3. Configuring RedisScript Beans

**`RateLimitScriptConfig.java`**

```java
package com.example.ratelimit;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.ClassPathResource;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.data.redis.core.script.RedisScript;

@Configuration
public class RateLimitScriptConfig {

    @Bean("fixedWindowRateLimitScript")
    public RedisScript<List> fixedWindowRateLimitScript() {
        return load("redis/fixed-window.lua");
    }

    @Bean("slidingWindowRateLimitScript")
    public RedisScript<List> slidingWindowRateLimitScript() {
        return load("redis/sliding-window.lua");
    }

    @Bean("tokenBucketRateLimitScript")
    public RedisScript<List> tokenBucketRateLimitScript() {
        return load("redis/token-bucket.lua");
    }

    private RedisScript<List> load(String path) {
        DefaultRedisScript<List> script =
                new DefaultRedisScript<>();

        script.setLocation(new ClassPathResource(path));
        script.setResultType(List.class);

        return script;
    }
}
```

`DefaultRedisScript` manages the script text and SHA checksum so Spring Data Redis can leverage Redis script caching. `List.class` fits because all three Lua scripts return a table of three numeric values.

### 10.4. Shared Decision Result Type

**`RateLimitDecision.java`**

```java
package com.example.ratelimit;

import java.time.Duration;

public record RateLimitDecision(
        boolean allowed,
        double remaining,
        Duration retryAfter
) {
}
```

Meaning:

- `allowed`: whether the request stayed within quota.
- `remaining`: remaining quota; fixed/sliding report whole permits, token bucket reports tokens.
- `retryAfter`: estimated wait time when blocked, not a guarantee that the next attempt will succeed.

### 10.5. Service Executing All Three Scripts

**`RedisRateLimiter.java`**

```java
package com.example.ratelimit;

import java.time.Duration;
import java.util.List;
import java.util.UUID;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.RedisScript;
import org.springframework.stereotype.Service;

@Service
public class RedisRateLimiter {

    private final StringRedisTemplate redis;
    private final RedisScript<List> fixedScript;
    private final RedisScript<List> slidingScript;
    private final RedisScript<List> bucketScript;

    public RedisRateLimiter(
            StringRedisTemplate redis,
            @Qualifier("fixedWindowRateLimitScript")
            RedisScript<List> fixedScript,
            @Qualifier("slidingWindowRateLimitScript")
            RedisScript<List> slidingScript,
            @Qualifier("tokenBucketRateLimitScript")
            RedisScript<List> bucketScript
    ) {
        this.redis = redis;
        this.fixedScript = fixedScript;
        this.slidingScript = slidingScript;
        this.bucketScript = bucketScript;
    }

    public RateLimitDecision fixedWindow(
            String redisKey,
            int limit,
            long windowSeconds
    ) {
        if (limit <= 0 || windowSeconds <= 0) {
            throw new IllegalArgumentException("Invalid fixed-window config");
        }

        List<?> result = redis.execute(
                fixedScript,
                List.of(redisKey),
                Integer.toString(limit),
                Long.toString(windowSeconds)
        );

        return decode(result, 1.0);
    }

    public RateLimitDecision slidingWindow(
            String redisKey,
            int limit,
            long windowMs
    ) {
        if (limit <= 0 || windowMs <= 0) {
            throw new IllegalArgumentException("Invalid sliding-window config");
        }

        // Each quota check gets a unique member in the ZSET.
        String requestId = UUID.randomUUID().toString();

        List<?> result = redis.execute(
                slidingScript,
                List.of(redisKey),
                Integer.toString(limit),
                Long.toString(windowMs),
                requestId
        );

        return decode(result, 1.0);
    }

    public RateLimitDecision tokenBucket(
            String redisKey,
            double capacity,
            double refillPerSecond,
            double cost
    ) {
        if (!Double.isFinite(capacity)
                || !Double.isFinite(refillPerSecond)
                || !Double.isFinite(cost)
                || capacity <= 0
                || refillPerSecond <= 0
                || cost <= 0
                || cost > capacity) {
            throw new IllegalArgumentException("Invalid token-bucket config");
        }

        List<?> result = redis.execute(
                bucketScript,
                List.of(redisKey),
                Double.toString(capacity),
                Double.toString(refillPerSecond),
                Double.toString(cost)
        );

        // Lua returns remaining tokens multiplied by 1000.
        return decode(result, 1000.0);
    }

    private RateLimitDecision decode(
            List<?> values,
            double remainingDivisor
    ) {
        if (values == null || values.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis rate-limit result"
            );
        }

        long allowedFlag =
                ((Number) values.get(0)).longValue();

        long remainingRaw =
                ((Number) values.get(1)).longValue();

        long retryMs =
                ((Number) values.get(2)).longValue();

        return new RateLimitDecision(
                allowedFlag == 1L,
                remainingRaw / remainingDivisor,
                Duration.ofMillis(Math.max(0L, retryMs))
        );
    }
}
```

Using the API:

```java
RateLimitDecision fixed = limiter.fixedWindow(
        "rl:v1:fixed:read-order:{u42}",
        60,
        60
);

RateLimitDecision sliding = limiter.slidingWindow(
        "rl:v1:sliding:otp:{u42}",
        5,
        60_000
);

RateLimitDecision bucket = limiter.tokenBucket(
        "rl:v1:bucket:search:{u42}",
        10.0,
        2.0,
        1.0
);
```

You do not call all three algorithms for the same request. These calls illustrate **three independent policies**. In a real application, the service or middleware picks the right policy by endpoint, user, and tenant.

### Why Use Lua Scripts Instead of Multiple StringRedisTemplate Commands?

If the service called `opsForValue().get`, compared counts, then called `increment` and `expire` across multiple round trips, requests from multiple instances could interleave. In this example, quota verification and state updates run inside **a single atomic script command**, making acceptance decisions consistent on that Redis server.

Also note that Redis **does not roll back individual commands inside a script if a later command errors after earlier writes**. Scripts must validate parameters and constrain input data; here Java validates configuration before sending.

## 11. Returning HTTP 429 and Retry-After

When a client exceeds its limit, the standard HTTP status is **`429 Too Many Requests`**. The `Retry-After` header can indicate how long to wait before trying again.

Example response:

```http
HTTP/1.1 429 Too Many Requests
Content-Type: application/json
Retry-After: 12

{"error":"RATE_LIMITED","message":"Too many requests"}
```

When formatted as a number, `Retry-After` is a **non-negative integer number of seconds**, not milliseconds. Therefore, if the script returns `retryAfterMs=1500`, round up to 2 seconds:

```java
long seconds = Math.max(
        1L,
        (decision.retryAfter().toMillis() + 999L) / 1000L
);
```

When quota runs out at a fixed-window boundary, a retry after that tick may succeed. With sliding windows or token buckets, the wait time is an **estimate** based on state at check time; competing requests from other clients can consume newly refilled permits.

You may return supplemental headers such as `X-RateLimit-Limit` or `X-RateLimit-Remaining` per your API conventions, but do not treat custom headers as a universal guarantee across clients. If adopting a standardized rate-limit header specification, follow that specification's time units, formatting, and multi-policy semantics.

### Example Policy for an Authenticated Endpoint

Suppose `POST /api/orders` is restricted to logged-in accounts. You can enforce a token bucket at the Spring MVC layer via a `HandlerInterceptor`.

**`OrderRateLimitInterceptor.java`**

```java
package com.example.ratelimit;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.security.Principal;
import java.util.HexFormat;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.dao.DataAccessException;
import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;

@Component
public class OrderRateLimitInterceptor implements HandlerInterceptor {

    private final RedisRateLimiter limiter;

    public OrderRateLimitInterceptor(RedisRateLimiter limiter) {
        this.limiter = limiter;
    }

    @Override
    public boolean preHandle(
            HttpServletRequest request,
            HttpServletResponse response,
            Object handler
    ) throws IOException {
        Principal principal = request.getUserPrincipal();

        if (principal == null) {
            response.sendError(
                    HttpServletResponse.SC_UNAUTHORIZED,
                    "Authentication required"
            );
            return false;
        }

        String principalTag = sha256(principal.getName());
        String key = "rl:v1:orders:{" + principalTag + "}";

        RateLimitDecision decision;

        try {
            decision = limiter.tokenBucket(
                    key,
                    10.0, // Capacity: 10 requests
                    2.0,  // Refills 2 tokens per second
                    1.0   // Each request costs 1 token
            );
        } catch (DataAccessException ex) {
            // Illustrative fail-closed behavior for a sensitive write:
            // if quota cannot be verified, do not execute the request.
            response.sendError(
                    HttpServletResponse.SC_SERVICE_UNAVAILABLE,
                    "Rate-limit service unavailable"
            );
            return false;
        }

        if (!decision.allowed()) {
            long retryMs = decision.retryAfter().toMillis();
            long retrySeconds = Math.max(
                    1L,
                    (retryMs + 999L) / 1000L
            );

            response.setHeader(
                    "Retry-After",
                    Long.toString(retrySeconds)
            );
            response.setStatus(429);
            response.setContentType("application/json");
            response.getWriter().write(
                    "{\"error\":\"RATE_LIMITED\"}"
            );
            return false;
        }

        return true;
    }

    private static String sha256(String value) {
        try {
            byte[] digest = MessageDigest
                    .getInstance("SHA-256")
                    .digest(value.getBytes(StandardCharsets.UTF_8));

            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException ex) {
            throw new IllegalStateException(
                    "SHA-256 unavailable",
                    ex
            );
        }
    }
}
```

Key points:

- `request.getUserPrincipal()` must rely on a trustworthy application authentication mechanism. The interceptor does not authenticate requests on its own.
- The key name is hashed so usernames/emails are not stored directly in Redis keys; hashing does not replace personal data protection policies or brute-force resistance if identifiers have low entropy.
- When Redis fails on a critical write endpoint, the example chooses **fail-closed**, returning 503 rather than allowing all requests through.
- `DataAccessException` covers Spring's data-access error hierarchy; script execution errors should also be reviewed for your driver and version.
- If rate limiting covers all HTTP methods matching the path, verify whether GETs should be limited alongside POSTs. This example assumes the interceptor is scoped appropriately to write APIs.

### Registering the Interceptor

**`RateLimitWebConfig.java`**

```java
package com.example.ratelimit;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.InterceptorRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class RateLimitWebConfig implements WebMvcConfigurer {

    private final OrderRateLimitInterceptor interceptor;

    public RateLimitWebConfig(
            OrderRateLimitInterceptor interceptor
    ) {
        this.interceptor = interceptor;
    }

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(interceptor)
                .addPathPatterns("/api/orders/**");
    }
}
```

In a real system, if you want to limit **only POST**, add an HTTP method check in `preHandle` or separate policies per route/handler instead of sharing one quota across all methods matching the path.

When using Spring Security, ensure authentication runs before the interceptor reads the principal and that protected endpoints have proper authorization rules. A rate limiter **does not replace authentication or authorization**.

## 12. One Request Subject to Multiple Limit Tiers

Suppose user `u42` belongs to tenant `companyA`:

```text
User policy:   10 requests/second per user
Tenant policy: 100 requests/second across tenant
Global policy: 5000 requests/second system-wide
```

Suppose a request is checked:

1. User has quota → deduct 1 user token.
2. Tenant is out of quota → request is blocked.
3. User already lost 1 token even though the request was rejected.

If that behavior is undesirable, **do not** just make three separate `tokenBucket(...)` calls in Java. Those are three **separate** atomic scripts, not a shared transaction.

Design options:

- **Accept conservative deduction:** allow a request rejected at the second tier to still spend the first tier's token; document this explicitly in policy.
- **Evaluate multiple policies in one Lua script:** pass all required Redis keys in `KEYS`, evaluate all conditions first, and update them together only if all allow.
- **Offload to a dedicated gateway or rate-limiting service:** fits when many services and multi-tier quotas coexist.
- **Use Redis Functions:** encapsulate server-side logic into manageable modules on compatible Redis versions.

With Redis Cluster, if a Lua script accesses multiple keys, they must obey **same hash slot** rules or an appropriate partitioning strategy. Never construct dynamic key names inside Lua without declaring all accessed keys via `KEYS`.

## 13. Time Source and Clock Skew

Rate limiting is time-dependent. If each app instance computes `System.currentTimeMillis()` and sends timestamps to Redis, clock skew between instances can produce confusing behavior:

```text
Instance A: 12:00:59.900
Instance B: 12:01:00.400
Shared Redis state
```

The scripts in this lesson call Redis `TIME` to use **a single time source on the node handling the key**. That ensures requests targeting the same key on a Redis primary are evaluated against one consistent clock.

Limitations still exist:

- The Redis server's OS clock can be adjusted.
- Failing over to another node can shift the reference clock.
- The token-bucket script guards against backward clock jumps by clamping negative elapsed time.
- Fixed window aligns to epoch time; abnormal clock shifts can shift boundaries.
- In multi-region deployments, separate Redis primaries for the same policy split quotas.

Do not use Redis quotas as strict real-time billing meters without a durable business data source and reconciliation.

### Why Not Use Client Timestamps?

Clients can tamper with or forge clocks, especially timestamps sent from mobile apps or browsers. Client timestamps should never directly govern API rate-limit quotas.

A business deadline may require its own time reference, but for server request throttling, a trusted infrastructure clock is generally far better suited.

## 14. TTL and Memory Management

Every new subject can create a Redis key. If an API serves millions of IPs or accounts, the rate-limit keyspace can grow huge even though each key stores little data.

The scripts configure TTLs intentionally:

| Algorithm | State | Suggested TTL | Reason |
|---|---|---|---|
| Fixed window | Hash `window/count` | Window + buffer from last request | Cleans inactive subjects while resetting cleanly on window rollover |
| Sliding log | ZSET of accepted request timestamps | Window + buffer from last request | Evicts old members; key drops once user stops calling |
| Token bucket | Hash `tokens/updated_ms` | Full refill time + buffer | Once idle long enough, bucket equals full initial state |

Examples:

```text
Fixed window 60s   → TTL roughly 62s after last attempt
Sliding window 60s → TTL roughly 61s after last attempt
Bucket C=10, R=2/s → TTL roughly 6s after last attempt
```

**TTL does not cap total memory.** An attacker can fabricate many distinct subjects (such as spoofed IPs behind an untrusted proxy or unauthenticated API keys) and spawn massive numbers of keys. Systems still need defenses against **high-cardinality keys**.

Mitigations:

- Derive subjects only from verified identities.
- Rate-limit at the edge/gateway by connection source alongside in-app policies.
- Apply quotas at IP subnet or tenant level where appropriate.
- Cap creation of new subjects over an interval if necessary.
- Monitor `used_memory`, key count, eviction policy, and miss/expiration rates.
- Avoid sharing critical Redis instances across unrelated workloads without capacity sizing.

Do not rely on `maxmemory` eviction to enforce quotas accurately. If Redis evicts limiter keys under memory pressure, subjects can get an **early quota reset** and gain extra access.

## 15. Rate Limiting and Redis Cluster

Redis Cluster distributes keys across hash slots. The scripts in this lesson operate on **one key**, fitting cleanly with routing each policy state to one slot.

Example:

```text
rl:v1:fixed:read:{u42}
rl:v1:bucket:search:{u42}
```

Both keys share hash tag `{u42}`, placing them in the same slot—handy if you later write a script combining multiple policies for the same user.

Avoid a classic mistake: forcing **every subject** into a single global hash tag like `{rate-limit}` puts all keys into one slot, defeating cluster distribution and creating a hotspot.

Choose hash tags per subject or policy sensibly rather than collapsing the entire system into a single slot.

### How Does Redis Failover Affect Quotas?

In standard Redis replication, failover can happen before the latest state reaches a replica. If a newly promoted primary lacks recent quota updates, counters can step backward and allow extra requests unintentionally.

For routine traffic-protection rate limiting, minor drift is often tolerable. For fraud prevention or strict contractual caps, design appropriate consistency, durability, and enforcement layers; **Redis replication + atomic Lua alone does not guarantee exact quotas across failovers**.

## 16. Fail-Open vs. Fail-Closed When Redis Fails

Suppose the service invokes a rate-limit script and Redis times out:

```text
HTTP request
    |
    v
Redis rate-limit check
    |
    +--> Success: ALLOW or DENY
    |
    +--> Error: should the request proceed?
```

The choice depends on business impact.

| Endpoint | Suggestion When Redis Limiter Fails | Reason |
|---|---|---|
| Public product page reads | Controlled fail-open | Avoid outage caused by limiter, while protecting downstream |
| Expensive search | Local fallback quota or concurrency limit; fail-closed under high load | Prevent fallback traffic from crashing the database |
| Login / OTP | Usually fail-closed or another reliable limiter | Must not bypass brute-force protection |
| Payment / reservation creation | Risk-dependent, typically strict | Avoid losing load or fraud control |
| Authenticated internal high-SLA API | Fallback gateway-level limit | Keep at least one control layer active |

**Fail-open** does not mean disabling all safeguards. If bypassing the Redis limiter on a catalog read endpoint, keep overall load caps, authentication where needed, circuit breakers, and data-source protections in place.

**Fail-closed** does not mean returning 429 for every error. If Redis cannot answer so the system does not know whether the user exceeded quota, **`503 Service Unavailable`** may be more accurate than 429. Return 429 only when quota was actually evaluated and determined exceeded.

### Retrying When a Redis Script Times Out

A timeout does not prove the script never ran. Redis may have deducted quota before the response was lost on the wire.

If the client/service retries the same quota check, quota can be deducted a second time. For high-value endpoints, clarify semantics:

- Tolerate occasional extra token consumption in rare edge cases.
- Use an idempotency ID and cache the evaluation result per request ID.
- Or add another layer guarding against duplicate processing of the business request.

None of fixed window, sliding window, or token bucket solves **exactly-once** delivery for an HTTP request over an unreliable network on its own.

## 17. Safely Designing Subjects by IP, User, and API Key

### By User ID

Use IDs from verified sessions/tokens, never client-controlled query parameters or request bodies.

```text
rateLimitKey = hash("tenantId:userId:policy")
```

When a user has multiple devices, the same user ID shares the quota. If business rules want per-device quotas, require trusted device identifiers and prevent clients from minting unlimited new device IDs to bypass limits.

### By API Key

Do not store raw API keys in Redis keys or logs. Use an internal ID mapped after key validation, or hash appropriately.

### By IP

An IP address only signals network origin, not necessarily a single user. Many users may share NAT; one user may rotate IPs. Behind proxies, configure trusted proxy chains before extracting the real client IP.

Never trust raw `X-Forwarded-For` headers from the public Internet, as attackers can spoof them to bypass limits unless the gateway strips untrusted headers.

### Multi-Dimensional Limits

For instance, a login endpoint may need limits:

- Per normalized account/login identifier.
- Per IP or subnet to slow distributed brute-force attacks.
- Per tenant or globally to cap overall load.

Multi-dimensional limits must be designed as a unified policy. If checking keys separately without tolerating partial quota consumption, use a suitable atomic coordination algorithm.

## 18. Accuracy, Bursts, and Business Trade-Offs

The three algorithms differ in more than code; they express different **contracts with clients**.

### Fixed Window: Predictable by Clock Boundaries

A policy like "max 100 requests per clock minute" aligns naturally with fixed windows. However, if the backend cannot handle 200 requests concentrated across a minute boundary, fixed window alone is insufficient.

You can layer a **burst-protecting token bucket** alongside the per-minute fixed quota, or switch to a sliding window.

### Sliding Window: Strict Over Any Recent N Seconds

If an account may try at most 5 OTP codes in any rolling 60 seconds, a sliding log expresses that rule closely. It eliminates boundary bursts at the cost of memory per accepted attempt.

Note for OTPs: resending the same business request ID might need to return the previous result or avoid re-charging quota per idempotency policy. That is distinct from the per-check UUID used as the ZSET member.

### Token Bucket: Average Rate and Maximum Burst

Suppose:

```text
capacity = 20
refillRate = 5 tokens/second
cost = 1

User starts with 20 tokens:
  Can send 20 requests immediately.
Once depleted:
  Recovers roughly 1 token every 200ms.
```

Token buckets feel smoother for interactive real-time apps: idle users accumulate tokens for a short burst, while continuous senders are throttled to the refill rate.

However, if business rules mandate "never more than 5 requests in any 60 seconds," a large bucket capacity will violate that rule. Set capacity and refill based on **allowed burst size**, not just desired average throughput.

## 19. Using Redis TIME Instead of Client Clocks: Trade-Offs

The Lua scripts call:

```lua
local time = redis.call('TIME')
```

and use the Redis server's clock. This reduces skew across Spring Boot instances.

Because time is read **inside an atomic script**, two quota checks on the same Redis server cannot interleave state updates. Still, a Redis server clock is not an immutable business ledger clock. For deadlines tied to billing, contracts, or legal compliance, maintain independent business timestamps and state.

Also note that calling `TIME` inside a state-mutating Lua script requires Redis versions/replication modes supporting non-deterministic commands properly (modern Redis supports script effect replication as used here). If running legacy Redis or an incomplete compatible service, verify actual script behavior.

## 20. When Redis Should Not Be the Sole Quota Store

A Redis rate limiter is great for **traffic protection**, but not every quota belongs solely in Redis.

Examples:

- Monthly usage allowances on paid subscription plans.
- Contractual total transaction caps.
- Regulatory maximum refund counts.
- Document export counts tied to billing.

These limits may require auditing, reconciliation, durability, and transactional consistency alongside business records. Redis can serve as a fast front-end guardrail, while the source of truth normally belongs in a store with matching transactional guarantees.

Distinguish:

```text
Infrastructure-protection rate limit:
  "No more than 50 req/s on endpoint."
  → Redis is a great fit.

Billable commercial quota:
  "Max 10,000 exports per monthly plan."
  → Needs a durable/reconcilable source; Redis can act as cache or soft limit.
```

When both are needed, check the Redis rate limit first before processing, then use a transaction on the authoritative store to enforce billable quota.

## 21. Monitoring and Observability

An algorithmically correct rate limiter can still cause major incidents if misconfigured: blocking legitimate users, creating a Redis hotspot, or overwhelming data stores if the limiter fails.

Recommended metrics:

| Metric | Purpose |
|---|---|
| `rate_limit_allowed_total` | Requests permitted per policy |
| `rate_limit_denied_total` | Requests blocked |
| `rate_limit_error_total` | Redis/script errors per policy |
| Redis command latency | Track quota-decision latency |
| Key count per namespace | Spot cardinality growth |
| Redis memory/CPU | Capacity planning and hotspot detection |
| HTTP 429 rate | Detect overly aggressive throttling |
| HTTP 503 due to limiter | Distinguish Redis outages from quota exhaustion |
| Business request latency | Observe end-to-end impact |
| Auth/abuse alerts | Monitor abnormal login attempts, scraping, and DoS |

Avoid tagging metrics with **per-subject user IDs or API keys**: cardinality will explode and sensitive identifiers may leak. Tag by **policy name**, endpoint group, environment, outcome, and error category.

### Rate-Limit Event Logs

An appropriate log entry can contain:

```text
policy=otp-per-account
decision=DENY
retryAfterMs=18000
redisLatencyMs=3
traceId=...
```

Never log raw Redis keys or auth tokens. If investigating abuse by account, use an access-controlled audit pipeline with pseudonymized identifiers.

## 22. Test Scenarios to Understand

This lesson uses concrete scenarios to clarify semantics. In a real application, build integration tests with a real Redis instance and concurrent clients.

### 22.1. Fixed Window Around the Boundary

```text
Limit = 5/60s

12:00:59.900 → 5 requests accepted
12:01:00.100 → 5 more requests accepted
```

This is expected behavior for a fixed window, even though 10 requests landed within 200ms. If unacceptable, switch algorithms or add a burst layer.

### 22.2. Sliding Window After Old Requests Expire

```text
Limit = 3 per 10,000ms

t=1000ms  request A ALLOW
t=2000ms  request B ALLOW
t=3000ms  request C ALLOW
t=4000ms  request D DENY

t=11001ms request E can ALLOW
```

At `t=11001ms`, the `t=1000ms` entry is outside the most recent 10,000ms window and gets evicted. If a competing request claims the slot first, the result may change.

### 22.3. Token Bucket After Idle Time

```text
Capacity = 4
Rate = 1 token/s
Cost = 1

t=0s: 4 tokens available → 4 requests ALLOW
t=0s: 5th request DENY
t≈1s: ~1 token refilled → can ALLOW
t≈4s idle: bucket nearly refilled to full
```

Exact timing depends on when Redis runs the script and token representation; avoid overly brittle clock assertions in tests.

### 22.4. Multiple Instances Racing for the Last Slot

```text
1 permit remaining.

Instance A and Instance B both invoke the Lua script.
Redis runs one script first.
That script sees 1 permit and deducts quota.
The second script sees 0 permits and denies.
```

This is the core purpose of putting **check and update into a single atomic server-side operation**.

### 22.5. Redis Timeout After Script Execution

```text
Client sends script.
Redis deducts token successfully.
Connection drops before client reads reply.
Client does not know whether quota was granted.
```

If the client retries the script, another token may be deducted. Define system-level retry/idempotency semantics, especially when quota checks gate side-effecting operations.

## 23. Common Mistakes

| Mistake | Cause | How to Avoid |
|---|---|---|
| Exceeding quota under concurrency | Non-atomic `GET → if → SET` | Lua script or conditional server-side operation |
| Fixed window allowing ~2× burst | Reset on frame boundaries | Use sliding/token bucket or add a burst limiter |
| Sliding log recording fewer entries than requests | Using timestamp as ZSET member, causing collisions | Generate unique member ID per check |
| Sliding log consuming high RAM | Storing one member per accepted request | Lower limit, or use counter/token bucket variants |
| Token bucket refilling at wrong speed | Confusing tokens/sec with tokens/ms | Normalize units and refill formula |
| Token bucket growing unbounded | Missing `min(capacity, ...)` cap | Clamp tokens at capacity |
| Spring instances computing different quotas | In-memory state or skewed clocks | Shared Redis and server time inside scripts |
| TTL resetting limits too early | `EXPIRE` shorter than tracking interval | Match TTL to window/refill and policy |
| Keys never cleaned up | Missing TTL for inactive subjects | Set `EXPIRE`/`PEXPIRE` per policy |
| Key names containing API keys or emails | Raw identifiers in keys | Use opaque IDs or controlled hashes |
| Users rotating IPs to evade limits | Limiting solely by IP | Combine identity, gateway, and policy layers |
| Bypassing limits via spoofed headers | Trusting client `X-Forwarded-For`/`X-User-Id` | Trust only configured proxies and auth mechanisms |
| Wrong HTTP status on Redis failure | Treating Redis access errors as quota exceeded | Return 503 for availability failures, 429 for exceeded quota |
| Retries after timeout deducting twice | No idempotency for evaluation | Define retry semantics and request IDs |
| Inconsistent user and tenant quotas | Checking multiple policies via separate scripts | Accept partial deductions or design atomic multi-key logic |
| CROSSSLOT in Redis Cluster | Script accessing keys in different slots | Use appropriate hash tags and declare `KEYS` properly |
| Redis memory spiking | High subject/key count, large sliding logs | Cardinality controls, TTL, metrics, capacity planning |
| Rate limiter amplifying outages | Redis fails and unbounded fail-open floods DB | Protect downstream; fail-closed on sensitive endpoints |
| Confusing rate limits with billable quotas | Using Redis state as sole source | Durable business ledger and reconciliation |

## 24. Choosing an Algorithm for Sample Use Cases

### General Read API

For example, a product catalog: 300 requests/minute per API key.

**Suggestion:** fixed window if boundary burst risk is low and O(1) state is preferred. If the backend is sensitive to instantaneous bursts, add a suitably sized token bucket.

### OTP or Login Attempts

For example, at most 5 attempts per 60 seconds per account.

**Suggestion:** sliding window log to curb boundary bursts, combined with IP/subnet limits and additional brute-force protections. Never treat a rate limiter as the sole security control.

### Search or Report Generation API

For example, allow a short burst of 10 requests, then recover 2 permits per second.

**Suggestion:** token bucket with `capacity=10`, `refill=2/s`. For heavy reports, assign `cost` by estimated weight and bound concurrency at the worker tier.

### Multi-Tenant Service

For example, 10 requests/s per user and 100 requests/s per tenant.

**Suggestion:** multiple rate-limit layers may be needed, but define clearly how quota is counted when a request fails one tier. Never assume multiple independent Redis script calls form one atomic decision.

### Monthly Paid Plan Quotas

For example, a plan allowing 10,000 document exports per month.

**Suggestion:** a Redis rate limiter cannot replace an auditable business ledger. Use a database/event ledger as the source of truth, with Redis serving as a front-end rate-limit/load-protection layer if helpful.

## 25. Key Takeaways

The three strategies can be summarized by **stored state**:

```text
Fixed window:
  key -> {windowIndex, acceptedCount}

Sliding window log:
  key -> ZSET(timestampMs -> uniqueRequestId)

Token bucket:
  key -> {tokensRemaining, lastUpdatedMs}
```

And by **decision logic**:

```text
Fixed window:
  ALLOW if acceptedCount < limit in current frame.

Sliding window:
  Remove expired requests.
  ALLOW if remaining requests in window < limit.

Token bucket:
  Refill tokens based on elapsed time.
  ALLOW if tokens >= requestCost.
```

In Spring Data Redis, `StringRedisTemplate.execute(RedisScript, ...)` executes quota checks and updates atomically on Redis. Yet reliable rate limiting also requires careful design of **subjects**, **namespaces**, **TTLs**, **HTTP 429**, **Redis failure policies**, **Redis Cluster**, **retries**, **monitoring**, and **downstream load caps**.

**Quick pick:** fixed window for simplicity and low cost, sliding window for strict rolling-interval enforcement, and token bucket for controlled bursts with a steady average rate.

### References

- [Spring Data Redis — Redis Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html)
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html)
- [Spring Data Redis — DefaultRedisScript API](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/core/script/DefaultRedisScript.html)
- [Redis — Rate Limiting](https://redis.io/learn/howtos/ratelimiting/)
- [Redis — Scripting with Lua](https://redis.io/docs/latest/develop/programmability/eval-intro/)
- [Redis — INCR](https://redis.io/docs/latest/commands/incr/)
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/)
- [Redis — ZREMRANGEBYSCORE](https://redis.io/docs/latest/commands/zremrangebyscore/)
- [Redis — TIME](https://redis.io/docs/latest/commands/time/)
- [Redis — EXPIRE](https://redis.io/docs/latest/commands/expire/)
- [HTTP Semantics — 429 Too Many Requests (RFC 6585)](https://www.rfc-editor.org/rfc/rfc6585)
