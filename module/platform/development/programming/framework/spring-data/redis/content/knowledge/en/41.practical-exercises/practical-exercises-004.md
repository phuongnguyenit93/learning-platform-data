# Building a Rate Limiter Using Counters and Lua in Spring Data Redis

An API can receive thousands of requests within seconds, even though each client is only allowed a fixed number of calls. Without a **rate limiter**, a user calling repeatedly can overload the database, consume resources unfairly, exhaust external service quotas, or drive up operational costs. When a Spring Boot application runs multiple instances, counters kept in each JVM's memory no longer enforce a shared limit: each instance counts independently and can allow exceeding the system-wide threshold.

**Redis** is well suited to sharing counter state across multiple instances. However, a Java pattern calling `INCR` then `EXPIRE` as two separate commands can leave keys **without a TTL** if the application crashes between the two commands. A `GET` then `SET` pattern also suffers from race conditions across multiple workers. We use an **atomic Lua script running on the Redis server** to read state, check the limit, increment the counter, and set the TTL in a single call from Spring Data Redis.

This exercise includes a complete **fixed-window counter** implementation with `StringRedisTemplate`, `DefaultRedisScript`, HTTP `429 Too Many Requests`, `Retry-After`, Testcontainers integration tests, and a **sliding-window log** example using Redis Sorted Sets. Later sections explain the trade-offs of each algorithm, identity key selection, timeout handling, Redis Cluster, ACLs, failover, memory, and monitoring.

> The goal is **traffic shaping and fair allocation under a defined policy**. Rate limiting on a single Redis primary is not an absolute guarantee against all attack classes or linearizable consistency across asynchronous failover. Cost/quota limits with severe financial consequences require additional transactional controls at the authoritative data source.

## 1. Problem Statement: Limiting Requests Across Multiple Instances

Suppose a service runs three Spring Boot instances with the requirement:

**Each account may call the report-generation API at most 5 times in 60 seconds.**

```text
                 Client / Gateway
                       |
                Load balancer
             /         |         \
            v          v          v
         API-A        API-B       API-C
            \          |         /
             \         |        /
              v        v       v
                   Redis
         key rl:reports:{user42}
          count=3, TTL=41s
```

API-A receives request 1, API-B receives request 2, API-C receives request 3; **the exact same Redis key** must reflect all three. Once the allowed count is exhausted, the service returns HTTP `429` instead of performing expensive work.

### 1.1. Expected Results

Example for one window:

| Request | Accepted Counter | Decision | Remaining |
|---|---:|---|---:|
| 1 | 1 | Allow | 4 |
| 2 | 2 | Allow | 3 |
| 3 | 3 | Allow | 2 |
| 4 | 4 | Allow | 1 |
| 5 | 5 | Allow | 0 |
| 6 | 5 | Deny: HTTP 429 | 0 |
| 7 | 5 | Deny: HTTP 429 | 0 |
| After key TTL expires | 1 in new window | Allow | 4 |

In this exercise's policy, **blocked requests do not increment the counter**. This is a deliberate choice so the counter does not grow unboundedly under spam. Some other rate limiters count **every attempt**; clarify semantics before writing code or comparing results.

### 1.2. Scoping Quotas to the Resources Actually Needing Protection

There are multiple identity dimensions:

- `userId`: allocate quotas per authenticated account.
- `apiKeyId`: allocate quotas for an external integration.
- `tenantId`: limit all users within a tenant.
- `routeGroup`: lightweight and heavy APIs have different thresholds.
- `IP address`: helps limit unauthenticated endpoints, provided proxies/gateways are trusted.
- `organizationId + plan`: quotas by service tier and workload type.

A system often needs **multiple concurrent quotas**, for example 10 req/sec per user and 1,000 req/min per tenant. You cannot rely on a single global counter across all APIs when resource costs differ.

## 2. Choosing the Right Algorithm

Before writing Lua, define **what a time window means**.

| Algorithm | Redis State | Characteristics | Limitations |
|---|---|---|---|
| Fixed-window counter | One String counter with TTL per subject/window | Lightweight, O(1) memory per active subject | Can concentrate bursts near the boundary of two windows |
| Sliding-window counter | Two bucket counters, usually weighted | Reduces boundary bursts, low memory | Approximate rather than counting every exact request in the sliding window |
| Sliding-window log | Sorted Set storing timestamp of each accepted call | Exact limit over the rolling window | RAM and prune cost grow with retained request count |
| Token bucket | Remaining tokens + last refill time | Allows controlled bursts, continuous refill | Must manage floating-point/timestamps and TTL |
| Leaky bucket | Queue state or water level | Smooths processing rate | May require queuing/scheduling rather than simple allow/deny |

**Choice for the main exercise:** fixed-window counter because it is simple, easy to concurrency-test, and fits many endpoints. We supplement with a sliding-window log when boundary bursts must be curtailed.

### 2.1. First-Hit Fixed Window vs Calendar-Aligned Fixed Window

In this lesson, the window **starts from the first accepted request**:

```text
t=0s     Request 1 creates key, TTL 60s
t=10s    Request 2; remaining TTL ~50s
t=30s    Request 3; remaining TTL ~30s
t=59s    Request 4; remaining TTL ~1s
t=60s    Key expires; next request opens a new window
```

This is a **fixed-duration window anchored to the first access**, not necessarily aligned to UTC clock ticks like 00:00, 00:01. A calendar-aligned algorithm keys by window bucket number or uses different server-time logic, and carries clock-skew risks if clients compute buckets themselves.

### 2.2. The Boundary Burst Problem

With a quota of 5 requests/60 seconds:

```text
Window A              Window B
 ... 55 56 57 58 59 | 60 61 62 63 64 ...
             5 req  | 5 req
```

A client can use 5 requests near the end of Window A and 5 requests right at the start of Window B. Over a short span straddling the boundary, the total can reach **2 × quota**. Lua guarantees counter atomicity, **not the elimination** of this algorithmic behavior.

If an endpoint cannot tolerate such bursts, use a sliding window or a token bucket with suitable capacity and refill rates.

## 3. Why Standalone GET/SET or INCR/EXPIRE Are Insufficient

### 3.1. Race Condition in GET Then SET

Broken pattern:

```java
String raw = redis.opsForValue().get(key);
long current = raw == null ? 0 : Long.parseLong(raw);

if (current < limit) {
    redis.opsForValue().set(key, Long.toString(current + 1));
    return true;
}
return false;
```

Two API instances can concurrently read `current=4`, both conclude the request is allowed, and both write `5`. Redis ends up showing only one increment despite two requests. This is a **lost update**.

### 3.2. INCR Is Atomic, but TTL Still Races

`INCR` is an atomic integer increment on the Redis primary:

```redis
INCR rl:reports:user42
EXPIRE rl:reports:user42 60
```

Between the two commands, a worker can crash or lose its connection. If `EXPIRE` never runs, the new key can **never expire**, permanently blocking the client once the counter exceeds the quota.

Calling `EXPIRE` after **every** `INCR` ceases to be a fixed window: each request resets the TTL back to 60 seconds, creating idle-timeout-like semantics where continuous client traffic keeps the key alive forever.

### 3.3. MULTI/EXEC and Lua

`MULTI`/`EXEC` executes a batch of commands atomically, but the logic "only set TTL when the counter is first created" requires **branching on the INCR result**. In standard transactions, commands are queued before reading responses; `WATCH` requires retrying under contention.

Lua allows:

```text
Redis server:
  read count
  if count < limit:
      INCR
      if key newly created: PEXPIRE
  return allowed/count/TTL
```

No commands from other clients interleave between script steps on **a single Redis node**. This keeps the counter consistent under normal node operation.

## 4. Data Contract of the Fixed-Window Rate Limiter

Assume:

```text
Redis key:  rl:reports:{user42}:fixed:v1
Redis type: String containing an integer
Limit:      5
Window:     60000 milliseconds
TTL:        60000ms from the first accepted request
```

Script inputs:

| Parameter | Example | Meaning |
|---|---|---|
| `KEYS[1]` | `rl:reports:{user42}:fixed:v1` | Counter key |
| `ARGV[1]` | `5` | Maximum accepted requests |
| `ARGV[2]` | `60000` | Window duration, milliseconds |

Output:

```text
{ allowedFlag, acceptedCount, remainingTtlMs }

{ 1, 1, 60000 }    Allow, attempt 1
{ 1, 5, 43000 }    Allow, all 5 used
{ 0, 5, 42000 }    Deny, count unchanged
```

`PTTL` is measured by Redis when the script runs, so the sample TTL numbers are illustrative; do not assert exact 60,000 values on every call.

### 4.1. Why Should Keys Have a Namespace and Version?

- `rl:`: identifies keys belonging to the rate-limiting system.
- `reports:`: route group/policy dimension being protected.
- `{user42}`: stable subject, with a hash tag helpful for multi-policy scripts in Redis Cluster.
- `fixed:v1`: distinguishes the algorithm and policy version.

Avoid putting secret tokens or raw emails/PII into keys whenever possible. For `userId`, use an internal opaque ID; if the subject must be obscured, use a stable HMAC with a separately managed secret (not just a plain hash if IDs are guessable). Do not let clients submit an unverified `userId` and pick someone else's counter.

## 5. Fixed-Window Lua Script: Atomic Check and Increment

The script below **does not increment the counter for rejected requests**. If an old key unexpectedly exists **without a TTL**, the script raises an error rather than silently creating an immortal quota.

```lua
-- fixed_window.lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])

if not limit or limit < 1 or limit ~= math.floor(limit) then
    return redis.error_reply('Invalid rate limit')
end
if not windowMs or windowMs < 1
        or windowMs ~= math.floor(windowMs) then
    return redis.error_reply('Invalid window milliseconds')
end

local value = redis.call('GET', key)

if value then
    local count = tonumber(value)
    if not count or count < 0 then
        return redis.error_reply('Corrupted rate-limit counter')
    end

    local ttl = redis.call('PTTL', key)
    if ttl < 0 then
        return redis.error_reply('Counter exists without valid TTL')
    end

    if count >= limit then
        -- Blocked: preserve count and expiration.
        return {0, count, ttl}
    end
end

local current = redis.call('INCR', key)
if current == 1 then
    redis.call('PEXPIRE', key, windowMs)
end

local remainingTtl = redis.call('PTTL', key)
if remainingTtl < 0 then
    return redis.error_reply('Rate-limit TTL invariant violated')
end

return {1, current, remainingTtl}
```

### 5.1. Script Walkthrough

**Attempt 1:** `GET` finds no key, `INCR` creates value `1`, `PEXPIRE` sets TTL, returns allow.

**Attempts 2–5:** `GET` sees `count < 5` and a valid TTL; `INCR` increments without altering the initial expiration timestamp.

**Attempt 6 onward:** `count >= 5`; script returns deny while **neither incrementing the counter nor resetting TTL**.

**After TTL:** Redis treats the key as expired; the next attempt creates counter `1` and opens a new window.

### 5.2. Why Check `PTTL = -1`?

`PTTL key` returns:

| Value | Meaning |
|---|---|
| Non-negative | Key exists, with that many milliseconds remaining |
| `-1` | Key exists without an expiration |
| `-2` | Key does not exist |

A counter without a TTL can appear due to legacy code or manual edits. Instead of "counting forever", the script treats this as an **invariant violation** and returns an error for operations to investigate. An alternative implementation might repair it with `PEXPIRE`, provided the policy is explicit and does not mask stale data bugs.

### 5.3. Atomic Lua Does Not Mean Transactional Rollback

Redis executes a script without other commands interleaving, but if a script **modifies data and later hits a runtime error**, Redis does not automatically roll back those changes like a SQL transaction. Therefore **validate data types, parameters, and preconditions before writing**, keep scripts short, and use a small number of O(1) commands.

In this script, all checks and deny paths occur before `INCR`; incrementing and setting TTL only run when admitting.

## 6. Testing Directly on Redis CLI

Create a dedicated lab Redis and use the key:

```text
rl:lab:{user42}:fixed:v1
```

In Redis CLI, `EVAL` takes the Lua source, key count, key list, and arguments:

```redis
EVAL "local c=redis.call('INCR',KEYS[1]); if c==1 then redis.call('PEXPIRE',KEYS[1],tonumber(ARGV[2])) end; local ttl=redis.call('PTTL',KEYS[1]); if c>tonumber(ARGV[1]) then return {0,c,ttl} else return {1,c,ttl} end" 1 rl:lab:{user42}:fixed:v1 5 60000
```

This one-liner is a **simplified variant that counts rejected requests too** to illustrate `EVAL` on the CLI; it does **not share the same semantics** as the full script in Section 5. For the main exercise, save the Section 5 script into `fixed_window.lua` and run:

```bash
redis-cli -h 127.0.0.1 -p 6379 \
  --eval fixed_window.lua 'rl:lab:{user42}:fixed:v1' , 5 60000
```

Repeat six times faster than 60 seconds. Attempts 1–5 should return `allowedFlag=1`, and attempt 6 `allowedFlag=0`. Check:

```redis
GET rl:lab:{user42}:fixed:v1
PTTL rl:lab:{user42}:fixed:v1
TYPE rl:lab:{user42}:fixed:v1
```

Under the full script, count must stay at `5` when denied. Do not run `FLUSHALL` just to reset one lab exercise; use `UNLINK`/`DEL` on your specific test key if permitted.

### 6.1. Script Cache and EVALSHA

`SCRIPT LOAD` loads a script and returns its SHA1; `EVALSHA` executes a cached script:

```redis
SCRIPT LOAD "return 1"
```

Spring Data Redis `DefaultRedisScript`/`ScriptExecutor` generally **tries EVALSHA first and falls back to EVAL** when needed. After `SCRIPT FLUSH` or failover, the script cache may be empty; the application must allow the fallback path or use Redis Functions/another versioned management mechanism.

Do not embed dynamic request/user IDs inside the **Lua source code** on every request. Keep the script static and pass keys via `KEYS` and limit/window/members via `ARGV`; Redis can then reuse the script cache without client-specific bloat.

## 7. Creating a Spring Boot Project for the Exercise

Target example environment: Java 17, Spring Boot 3.x, Spring Data Redis 3.x, Redis 7.x. For other versions, verify actual APIs and dependencies.

### 7.1. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

If the project uses Spring Security, integrate quotas after authentication or in a filter/gateway that establishes a trusted identity. The demo controller below uses `Principal` from application authentication; never let clients supply an arbitrary ID to impersonate another user.

### 7.2. application.yml

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
      timeout: 2s
```

Production Redis should use TLS, ACL username/password, a secret manager, and an appropriate private network. Rate-limit scripts must run against **data nodes**, not a Redis Sentinel endpoint.

### 7.3. Do You Need an Extra StringRedisTemplate Bean?

With the Spring Boot Redis starter, auto-configuration normally provides `StringRedisTemplate` and `RedisConnectionFactory` unless overridden. If configuring a custom template, ensure keys and arguments are encoded as String/UTF-8 so Redis receives the exact `rl:...` key and decimal numbers in `ARGV`.

## 8. Complete Spring Service: RateLimitService

This is a synchronous implementation with a static script. The returned result contains:

- `allowed`: whether the request may proceed to business logic;
- `limit`: configured quota;
- `used`: number of **accepted** calls in the window;
- `remaining`: remaining allowed calls;
- `resetAfter`: time until key expiration, based on Redis's response.

```java
package example.ratelimit;

import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Service;

@Service
public class RateLimitService {

    private static final String SCRIPT_TEXT = """
        local key = KEYS[1]
        local limit = tonumber(ARGV[1])
        local windowMs = tonumber(ARGV[2])

        if not limit or limit < 1
                or limit ~= math.floor(limit) then
            return redis.error_reply('Invalid rate limit')
        end
        if not windowMs or windowMs < 1
                or windowMs ~= math.floor(windowMs) then
            return redis.error_reply('Invalid window milliseconds')
        end

        local raw = redis.call('GET', key)
        if raw then
            local count = tonumber(raw)
            if not count or count < 0 then
                return redis.error_reply('Corrupted rate-limit counter')
            end
            local ttl = redis.call('PTTL', key)
            if ttl < 0 then
                return redis.error_reply('Counter exists without valid TTL')
            end
            if count >= limit then
                return {0, count, ttl}
            end
        end

        local current = redis.call('INCR', key)
        if current == 1 then
            redis.call('PEXPIRE', key, windowMs)
        end
        local ttl = redis.call('PTTL', key)
        if ttl < 0 then
            return redis.error_reply('Rate-limit TTL invariant violated')
        end
        return {1, current, ttl}
        """;

    // RedisScript<List> returns an array of Redis integers.
    @SuppressWarnings("rawtypes")
    private static final DefaultRedisScript<List> SCRIPT =
            new DefaultRedisScript<>(SCRIPT_TEXT, List.class);

    private final StringRedisTemplate redis;

    public RateLimitService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record Decision(
            boolean allowed,
            int limit,
            long used,
            long remaining,
            Duration resetAfter) {
    }

    public Decision check(
            String subjectId, int limit, Duration window) {

        // Use a stable opaque ID obtained from trusted authentication.
        if (subjectId == null ||
                !subjectId.matches("[A-Za-z0-9_-]{1,80}")) {
            throw new IllegalArgumentException("Invalid subject ID");
        }
        if (limit < 1 || limit > 1_000_000) {
            throw new IllegalArgumentException("Invalid limit");
        }
        if (window == null || window.isNegative() ||
                window.isZero()) {
            throw new IllegalArgumentException("Invalid window");
        }

        long windowMs = window.toMillis();
        if (windowMs < 1 ||
                windowMs > Duration.ofDays(1).toMillis()) {
            throw new IllegalArgumentException("Window out of range");
        }

        String key =
                "rl:reports:{" + subjectId + "}:fixed:v1";

        List<?> reply = redis.execute(
                SCRIPT,
                List.of(key),
                Integer.toString(limit),
                Long.toString(windowMs));

        if (reply == null || reply.size() != 3) {
            throw new IllegalStateException(
                    "Unexpected Redis rate-limit reply");
        }

        long allowFlag = asLong(reply.get(0));
        long used = asLong(reply.get(1));
        long ttlMs = asLong(reply.get(2));

        if ((allowFlag != 0 && allowFlag != 1)
                || used < 0 || ttlMs < 0) {
            throw new IllegalStateException(
                    "Invalid rate-limit state");
        }

        return new Decision(
                allowFlag == 1,
                limit,
                used,
                Math.max(0, (long) limit - used),
                Duration.ofMillis(ttlMs));
    }

    private static long asLong(Object raw) {
        if (!(raw instanceof Number number)) {
            throw new IllegalStateException(
                    "Expected Redis integer, got: " + raw);
        }
        return number.longValue();
    }
}
```

**Important:**

1. `DefaultRedisScript<List>` binds a static script source to a Redis array result type. Spring Data Redis 3.x may return numeric elements as `Long`, so read through `Number` rather than casting to `Integer`.
2. `StringRedisTemplate` ensures arguments `"5"`, `"60000"`, and the key are Strings matching the script.
3. `subjectId` is validated against an allowed pattern. Production can use internal account IDs rather than accepting IDs directly from untrusted request headers.
4. `limit` and `window` are validated in both Java and Lua. Java guards the policy API; Lua prevents another caller from passing invalid ARGV.
5. Near expiration, `PTTL` can still be non-zero depending on timing; do not use this `Duration` as an exact deadline for financial transactions.
6. On Redis timeout or script failure, the method **throws an exception**. Choose fail-open/fail-closed at the **policy layer**; do not silently treat Redis errors as "quota remaining".

### 8.1. Why Not Create a New RedisScript per Request?

`DefaultRedisScript` caches the script's SHA1/source so the executor can leverage the script cache. Creating a new script whose source varies per request adds overhead and loses caching benefits; a static singleton or bean holding a constant source is the standard approach.

If the application manages scripts on the classpath, you can use `RedisScript.of(new ClassPathResource("scripts/fixed_window.lua"), List.class)` per your Spring Data Redis version's API. The lesson keeps it inline to be self-contained in one snippet.

## 9. Integrating with HTTP 429 and Retry-After

HTTP `429 Too Many Requests` tells the client it sent too many requests. The `Retry-After` header can specify how many seconds to wait before retrying. Additionally, you can emit `X-RateLimit-Limit` and `X-RateLimit-Remaining` so clients can self-throttle.

Example controller when the endpoint has trusted authentication:

```java
package example.ratelimit;

import java.security.Principal;
import java.time.Duration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/reports")
public class ReportController {

    private final RateLimitService limiter;

    public ReportController(RateLimitService limiter) {
        this.limiter = limiter;
    }

    @GetMapping
    public ResponseEntity<String> generate(Principal principal) {
        // Endpoint must be protected by real authentication.
        // In this example, principal.getName() must be an opaque ID
        // matching the pattern in RateLimitService.
        if (principal == null) {
            return ResponseEntity.status(401)
                    .body("Authentication required");
        }

        RateLimitService.Decision decision = limiter.check(
                principal.getName(),
                5,
                Duration.ofSeconds(60));

        if (!decision.allowed()) {
            long remainingMs = decision.resetAfter().toMillis();
            long retrySeconds =
                    Math.max(1L, (remainingMs + 999L) / 1000L);

            return ResponseEntity.status(429)
                    .header(HttpHeaders.RETRY_AFTER,
                            Long.toString(retrySeconds))
                    .header("X-RateLimit-Limit",
                            Integer.toString(decision.limit()))
                    .header("X-RateLimit-Remaining", "0")
                    .body("Too many requests");
        }

        // Only execute expensive work after being allowed.
        // This is a demo payload; real business services are invoked here.
        return ResponseEntity.ok()
                .header("X-RateLimit-Limit",
                        Integer.toString(decision.limit()))
                .header("X-RateLimit-Remaining",
                        Long.toString(decision.remaining()))
                .body("Report accepted");
    }
}
```

### 9.1. Where to Attach the Limiter in the Request Lifecycle?

Several options exist:

| Location | Best For | Risks to Handle |
|---|---|---|
| API gateway/ingress | Early blocking, protecting multiple services | Forwarded identity must be trusted, route/quota config |
| Servlet filter / Spring Security filter | Limiting most endpoints | Authentication ordering, async dispatches, exempt paths |
| HandlerInterceptor | Binding to MVC routes | Must normalize route templates, async dispatch handling |
| Controller/service method | Fine-grained business quotas | Easy to miss endpoints; cost already incurred before limiter |
| WebFlux WebFilter | Reactive gateways/apps | Must not block event loop; requires reactive Redis |

A demo controller is easy to understand, but production typically extracts policy enforcement into a filter/interceptor or unified service boundary. When using Spring Security, ensure the limiter **receives identity after authentication** for per-user quotas. Pre-authentication login endpoints can use IP or a normalized account attempt identifier under a separate policy.

### 9.2. Retry-After Is Not a Slot Reservation

`Retry-After` is computed from the TTL observed inside the script; by the time the client retries, server time and traffic have changed. The header is advisory, not a quota reservation. Clients should add jitter/backoff to avoid thousands of requests returning at the exact reset second.

If an API enforces multi-tier quotas, the wait time may need to come from **whichever violated constraint lasts longest**, not just one counter's TTL.

## 10. Choosing Identifier Keys to Prevent Quota Bypass

An atomically correct rate limiter can still be bypassed if callers choose their own keys.

### 10.1. Do Not Use Self-Declared Headers as Identity

Wrong if an endpoint allows:

```text
X-User-Id: user-42
```

and uses that header straight as the Redis key. A client can simply change it to `user-43` on the next request to get a fresh quota.

Better:

- After login: use the subject ID from a verified token or security context.
- API key: use the ID of a verified API key, not the raw secret as the key.
- IP: extract only from trusted proxies/gateways and process `Forwarded`/`X-Forwarded-For` against a trusted proxy list. Never trust headers sent directly by Internet clients.
- Tenant: verify user membership and scope before applying tenant quotas.

### 10.2. Multi-Dimensional Limits

```text
rl:user:{user42}:api:reports
rl:tenant:{tenant7}:api:reports
rl:ip:{ipHash}:login
```

If both user and tenant quotas are mandatory, decide:

- Allow only when **all** quotas still have capacity.
- When one quota is exhausted, should the other counter increment?
- Do both policies need atomic updates to avoid inconsistently "burning quota"?
- Do the keys map to the same slot when using Redis Cluster?

Do not simply call `check(user)` followed by `check(tenant)` and treat them as one transaction. If the user quota is charged a hit while the tenant quota denies, one quota was consumed even though the request was rejected.

## 11. Two Quotas in One Lua Script: Extension Idea

If **user quota** and **route quota** must be granted or denied together, one script can check both counters before incrementing either.

```text
KEYS[1] = rl:{user42}:reports:short
KEYS[2] = rl:{user42}:reports:long

ARGV[1] = 5       (short limit)
ARGV[2] = 10000   (short window ms)
ARGV[3] = 100     (long limit)
ARGV[4] = 600000  (long window ms)
```

Model:

```lua
-- Algorithmic pseudocode, not a complete production script.
-- 1. Validate KEYS, ARGV, and types/TTLs of BOTH keys.
-- 2. GET countShort and countLong.
-- 3. If either quota is full:
--      do not INCR either key;
--      return deny with the blocking quota's TTL.
-- 4. If both have remaining quota:
--      INCR both keys;
--      PEXPIRE any newly created key;
--      return allow and counters/TTLs.
```

To guarantee atomicity in Redis Cluster, keys accessed by the script must share **the same hash slot**. A common hash tag `{user42}` groups one user's quotas onto the same slot, though it also concentrates that user's traffic on one master. Do not put every user into `{global}` if scalability is needed.

If the quotas are **user** and **tenant**, two distinct identities normally map to different slots. You cannot assume a cross-slot Lua script can update both atomically in Redis Cluster. Options:

1. Use a shared partitioning key by tenant if per-tenant load concentration is acceptable.
2. Separate limiters per dimension and accept explicit semantics/trade-offs.
3. Place an authoritative gateway/quota tier elsewhere when cross-shard strong consistency is genuinely required.

Do not work around this by dynamically constructing Redis key names inside Lua from `ARGV` on Cluster. Keys touched by a script must be declared/routed according to Redis rules.

## 12. Fixed-Window and Counting Rejected Requests

Two common policies:

**A. Count accepted only (this lesson):**

```text
count < limit  -> INCR then allow
count >= limit -> deny, do not INCR
```

Pros: counter stays capped at the limit, stable even with millions of rejected requests. Cons: the counter itself cannot reveal total spam volume; a separate `rate_limit_rejected_total` metric is needed.

**B. Count every attempt:**

```text
INCR first, if count > limit -> deny
```

Pros: counter reflects total attempts, including blocked ones. Cons: counter grows with every spam attempt, risking extreme values and obscuring "allowed calls used" semantics. In a fixed window, rejections should not continuously reset TTL unless intentionally penalizing prolonged attacks.

**Both policies can be valid**, but `remaining`, analytics, and retry policies will differ. Document the contract in tests and API docs.

## 13. Building a Sliding-Window Log with Lua and Sorted Sets

If fixed-window boundary bursts are unacceptable, store the timestamp of **each accepted request** in a `Sorted Set`.

```text
Redis key: rl:reports:{user42}:rolling:v1

ZSET members:
  score=nowMs of req-1, member=random-uuid-1
  score=nowMs of req-2, member=random-uuid-2
  score=nowMs of req-3, member=random-uuid-3
```

When a new request arrives:

1. Read Redis server time.
2. Remove all members whose scores have fallen outside the window.
3. Count via `ZCARD`.
4. If count is below limit, `ZADD` the new member and set TTL.
5. If count is full, reject and calculate wait time until the oldest event exits the window.

### 13.1. Lua Sliding-Window Script

```lua
-- sliding_window.lua
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local windowMs = tonumber(ARGV[2])
local eventId = ARGV[3]

if not limit or limit < 1 or limit ~= math.floor(limit)
        or not windowMs or windowMs < 1
        or windowMs ~= math.floor(windowMs) then
    return redis.error_reply('Invalid policy')
end
if not eventId or eventId == '' then
    return redis.error_reply('Missing event id')
end

local time = redis.call('TIME')
local nowMs = tonumber(time[1]) * 1000
        + math.floor(tonumber(time[2]) / 1000)
local cutoff = nowMs - windowMs

-- Scores <= cutoff are no longer inside the rolling window.
redis.call('ZREMRANGEBYSCORE', key, '-inf', cutoff)

local count = redis.call('ZCARD', key)
if count < limit then
    local inserted =
            redis.call('ZADD', key, 'NX', nowMs, eventId)
    if inserted ~= 1 then
        return redis.error_reply('Duplicate event id')
    end
    redis.call('PEXPIRE', key, windowMs)
    return {1, count + 1, 0}
end

local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
local retryMs = math.max(
        1,
        math.floor(tonumber(oldest[2]) + windowMs - nowMs + 1)
)
return {0, count, retryMs}
```

### 13.2. Key Differences from Fixed Window

| Aspect | Fixed Counter | Sliding ZSet |
|---|---|---|
| State | A single integer | One entry per accepted request in the window |
| TTL | From first request in window | Reset whenever a request is accepted |
| Removing old members | Key auto-expires | `ZREMRANGEBYSCORE` on incoming requests |
| Boundary bursts | Yes | No, under exact rolling semantics |
| Memory | Small, O(1) / subject | O(accepted requests remaining in window) |
| Cost per request | A few O(1) String ops | ZSet ops and pruning stale entries |
| Retry-After | Key TTL | Based on oldest member timestamp |

The script uses `redis.call('TIME')` so Spring instances do not depend on individual JVM clocks. Ensure it runs on a Redis version supporting `TIME` with writing scripts as required; this example targets Redis 7.x and should be tested on a real server. For extreme timing precision or multi-region setups, consider Redis primary clock and replication limits.

**Caution:** `eventId` must be unique per admission attempt. Reusing a member name prevents `ZADD NX` from increasing cardinality and triggers an error from the script. Applications can use UUID v4. If a Redis response is lost, retrying with a new `eventId` can **double-count the request**; reusing an old `eventId` requires explicit idempotency semantics rather than assuming `NX` handles every case.

### 13.3. Calling the Sliding-Window Script from Spring Data Redis

```java
import java.util.List;
import java.util.UUID;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;

String lua = """
    -- Use the exact sliding_window.lua source from above here.
    """;

// Illustrates the call shape; replace placeholder with full script.
DefaultRedisScript<List> rollingScript =
        new DefaultRedisScript<>(lua, List.class);

String key = "rl:reports:{user42}:rolling:v1";
String eventId = UUID.randomUUID().toString();

List<?> result = strings.execute(
        rollingScript,
        List.of(key),
        "5",
        "60000",
        eventId);
```

`strings` is the `StringRedisTemplate` bean. The snippet illustrates the API and is not a standalone runnable class: use the **full script source**, declare beans/constructors in a real class, and parse the response using the same principles as `RateLimitService`. In production, keep scripts on the classpath rather than copying source strings manually.

### 13.4. Why Must You Use a Unique ZSet Member?

`ZADD` updates the score if a member already exists. If you use `userId` as the member instead of a request ID, a user sending 100 requests still has only **one member** in the ZSet, causing the rate limiter to miscount drastically. The member must distinguish **each accepted request**.

## 14. When Is Token Bucket Better?

For example, a policy like "allow bursts up to 20 requests, then refill 5 tokens per second" fits a **token bucket**:

```text
State per subject:
  availableTokens = 12.5
  lastRefillMs = 1763000000000

On request:
  nowMs = Redis TIME
  tokens = min(capacity, oldTokens + elapsed * refillRate)
  if tokens >= requestCost:
      tokens -= requestCost
      ALLOW
  else:
      DENY, retryAfter based on refill rate
  persist tokens,lastRefill atomically
```

With Lua, you can store `tokens` and `lastRefillMs` in a Hash, validate params before writing, use `HGET`/`HSET` within one script, and set a TTL long enough to discard state once the bucket refills. Token buckets fit workloads with natural bursts; however, floating-point values and timestamps must be defined precisely, especially when multiple clients share an identity or during Redis failover.

**Do not automatically equate a token bucket with "strictly X requests in 60 seconds".** It caps capacity and refill rate, which can allow a different count than a fixed or rolling window even if all three are loosely described as "60 req/min".

## 15. Configuring Limits and Windows via Properties

Do not scatter `5` and `60000` across controllers. A cleaner design uses:

```yaml
app:
  rate-limit:
    reports:
      requests: 5
      window: 60s
    search:
      requests: 100
      window: 1m
```

Bind with `@ConfigurationProperties`:

```java
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.rate-limit.reports")
public record ReportsRateLimitProperties(
        int requests,
        Duration window) {
}
```

Register via `@EnableConfigurationProperties(ReportsRateLimitProperties.class)` or configuration properties scanning, depending on your project. Validate positive limits and durations at startup using Bean Validation or config guards when policies come from configuration.

If you change `limit` from 5 to 10 while an old counter is still alive, the existing value remains. If you lower `limit`, the existing count may be denied immediately; if you change `duration`, old TTLs do not automatically adapt to the new window. When migrating policies **without affecting old keys**, change the key suffix:

```text
rl:reports:{user42}:fixed:v1
rl:reports:{user42}:fixed:v2
```

That also **resets the quota** for each user at cutover. Decide whether a reset is acceptable and roll out uniformly across instances; switching key suffixes on instances at different times can grant parallel quotas.

## 16. Retry-After, Timeouts, and Fail-Open vs Fail-Closed Decisions

If Redis stops responding, what should the API do?

| Policy | Behavior on Redis Error | When Appropriate | Risks |
|---|---|---|---|
| **Fail-open** | Allow requests through in a controlled manner | Low-risk APIs prioritizing availability | Downstream overload, potential abuse during outage |
| **Fail-closed** | Reject/halt requests | Expensive resource quotas, strict abuse prevention | Redis failures cause service disruption |
| **Degraded fallback** | Use a temporary local limiter with a lower cap | Want to shed load when Redis fails | Each JVM counts separately; no global cap |

Do not turn a timeout into `Decision(allowed=true, remaining=...)` and quietly pretend quota remains if business rules mandate fail-closed. Likewise, do not return `429` for **every Redis error**: `429` signals the client exceeded its limit; infrastructure errors may warrant `503 Service Unavailable`/`Retry-After` per policy. Distinguish **quota exceeded** from **limiter unavailable** in metrics, logs, and HTTP responses.

### 16.1. Unknown Outcome on Command Timeout

Scenario:

```text
Java ---------- EVAL ---------> Redis
Java <-- lost response -------- Redis already ran INCR
```

The client does not know whether the command incremented the counter. Retrying automatically can run the script a **second time**, counting two attempts for a single client HTTP request. For ordinary rate limits this may be acceptable or require idempotency. For monetary quotas, use a more durable allocation/recording mechanism or a request-id ledger with explicit cleanup and semantics.

### 16.2. Timeout Budget on the Request Path

Because the limiter sits on the hot path of HTTP requests:

- Connect to Redis over an internal network with measured latency.
- Set timeouts aligned with your SLO.
- Cap excessive concurrency.
- Use a circuit breaker or policy-driven fallback.
- Distinguish script errors, connection errors, permission denied, and quota denied.
- Avoid unbounded retries that pile load onto Redis right when it is struggling.

## 17. Redis Cluster and Key Selection

Redis Cluster partitions keys by hash slot. The fixed-window script touches only **one key**, so cluster-aware drivers like Lettuce route directly to the node owning that slot.

```text
rl:reports:{user42}:fixed:v1
                  |
               hash tag
                  |
                slot S
                  |
         Master of slot S
```

For the same user, two quotas using:

```text
rl:reports:{user42}:short
rl:reports:{user42}:long
```

share the same hash tag and therefore the same slot, which is convenient if a single Lua script updates both. However, **do not** use `{all}` for all users: all traffic would land on one slot/master.

### 17.1. One Hot Key Can Overload One Master

If a limiter uses a **global key**:

```text
rl:reports:global
```

and every request invokes the script on that key, every command goes to the same master. Redis Cluster does not shard **a single key** across multiple shards. Under very high total traffic:

- Partition by user/tenant and apply global quotas at a gateway layer or purpose-built system.
- Use a small local token bucket to reduce Redis call frequency when semantics allow.
- Never run O(N) Lua scripts on a key handling tens of thousands of requests/second.
- Measure p99 Redis command latency, CPU per master, and bandwidth.

### 17.2. Multiple Keys in One Script

Redis Cluster requires all keys accessed by a script to satisfy hash-slot rules and be declared in `KEYS`. If a user quota and a tenant quota fall into different slots, you cannot expect `EVAL` to update both atomically on Redis Cluster like a cross-shard SQL transaction.

## 18. Redis Sentinel/Replication and Safety Limits

A Lua script is atomic on **a single Redis primary while executing**. Redis Sentinel/Cluster normally uses **asynchronous** replication:

```text
t0  Master A runs script, count 4 -> 5, returns ALLOW
t1  Write has not yet replicated to Replica B
t2  Master A fails
t3  Replica B is promoted to master, counter is still 4
t4  A new request can be ALLOWED again
```

Hence, a single-primary Redis limiter can **permit exceeding the quota** during certain failover windows. `WAIT` or durability settings can reduce write loss in some scenarios, **but do not turn Redis replication into a consensus-based linearizable commit**.

If the quota only guards against traffic spikes, slight drift during failover may be acceptable. If protecting funds, privileged order counts, or strict safety policies where even one extra request is unacceptable, consider a **quota ledger/transactional guard** on an appropriately consistent store.

### 18.1. Multi-Region

Regional limiters backed by separate Redis instances give each region its own quota, allowing total global usage to exceed the intended global cap. Choose explicitly:

- **Per-region** independent quotas.
- **Global** quotas routed through a shared authority with latency/availability trade-offs.
- Pre-allocated regional quotas reconciled periodically per policy.

Do not claim to enforce a global rate limit simply because every region uses the same key string against **independent Redis deployments**.

## 19. ACLs for a Lua Rate Limiter

Spring Boot's Redis user must be allowed to execute scripting commands and the underlying commands on the target keys:

```text
Key namespace:   ~rl:reports:*
Needed commands: EVAL/EVALSHA (or the scripting mechanism used),
                 GET, INCR, PEXPIRE, PTTL
```

For the sliding-window log:

```text
Key namespace:   ~rl:reports:*
Needed commands: TIME, ZREMRANGEBYSCORE, ZCARD,
                 ZADD, PEXPIRE, ZRANGE,
                 scripting commands
```

Redis ACLs apply per command, key pattern, and scripting rules. Do not grant `+@all ~*` just because a script returns `NOPERM`. Test against your real Redis version, including framework/driver handshake commands like `PING`/`CLIENT SETINFO` and script-cache fallbacks. Application credentials should not have `FLUSHALL`, `CONFIG SET`, or permission to read user secrets.

**Note:** Never interpolate raw user input into Redis key patterns without validating identity. An ACL restricting `~rl:reports:*` limits a credential's blast radius, but does not protect individual user quotas if the application builds keys from spoofed subjects.

## 20. Testcontainers: Testing Real Redis Instead of Only Mocks

A mocked `RedisTemplate` only checks which Java methods were called; it does not prove `INCR` and `PEXPIRE` are atomic, that TTLs work, or that two JVMs share a counter.

Example using JUnit 5 + Testcontainers + Spring Boot:

```java
package example.ratelimit;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RateLimitIntegrationTest {

    @Container
    static final GenericContainer<?> redis =
            new GenericContainer<>(
                    DockerImageName.parse("redis:7.4-alpine"))
                    .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", redis::getHost);
        registry.add("spring.data.redis.port",
                () -> redis.getMappedPort(6379));
    }

    @Autowired
    RateLimitService limiter;

    @Test
    void contextLoads() {
        // Add functional tests in the sections below.
    }
}
```

Testcontainers requires Docker or a compatible runtime on the test host. The test class must run inside a Spring Boot application context containing `RateLimitService` and Redis auto-configuration. Never run load tests against production Redis, and do not modify project code just because the example pins a fixed image version.

### 20.1. Single-Threaded Test: Exact Limit, Remaining, and Reset

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.time.Duration;
import java.util.UUID;

@Test
void admitsExactlyFiveRequestsPerFreshWindow() {
    String subject = "user" +
            UUID.randomUUID().toString().replace("-", "");

    for (int i = 1; i <= 5; i++) {
        RateLimitService.Decision decision =
                limiter.check(subject, 5, Duration.ofSeconds(60));

        assertThat(decision.allowed()).isTrue();
        assertThat(decision.used()).isEqualTo(i);
        assertThat(decision.remaining()).isEqualTo(5 - i);
        assertThat(decision.resetAfter()).isPositive();
    }

    RateLimitService.Decision blocked =
            limiter.check(subject, 5, Duration.ofSeconds(60));

    assertThat(blocked.allowed()).isFalse();
    assertThat(blocked.used()).isEqualTo(5);
    assertThat(blocked.remaining()).isZero();
    assertThat(blocked.resetAfter()).isPositive();
}
```

Generate a fresh subject per test instead of sharing `user42` so parallel tests do not interfere. Here `resetAfter` is a `Duration`, and AssertJ supports checking positive durations via version-appropriate assertions; if your library version lacks `isPositive()` on `Duration`, compare with `isGreaterThan(Duration.ZERO)`.

### 20.2. Concurrency Test: 50 Concurrent Tasks, Only 10 Admitted

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import org.junit.jupiter.api.Test;

@Test
void concurrentRequestsNeverExceedLimitOnOneRedisPrimary()
        throws Exception {

    String subject = "user" +
            UUID.randomUUID().toString().replace("-", "");

    int attempts = 50;
    int quota = 10;
    ExecutorService pool = Executors.newFixedThreadPool(20);
    CountDownLatch start = new CountDownLatch(1);

    try {
        List<Future<Boolean>> results = new ArrayList<>();

        for (int i = 0; i < attempts; i++) {
            Callable<Boolean> call = () -> {
                start.await();
                return limiter.check(
                        subject, quota, Duration.ofSeconds(60))
                        .allowed();
            };
            results.add(pool.submit(call));
        }

        start.countDown();

        long allowed = 0;
        for (Future<Boolean> result : results) {
            if (result.get(10, TimeUnit.SECONDS)) {
                allowed++;
            }
        }

        assertThat(allowed).isEqualTo(quota);
    } finally {
        pool.shutdownNow();
    }
}
```

This tests **safety under concurrency on a single healthy Redis primary**, not absolute safety across failover. In slow CI environments, configure timeouts sensibly; never use `Thread.sleep` to "create concurrency" and treat failing to reproduce a race as proof of algorithm correctness.

### 20.3. Test That TTL Is Created and Not Extended on Deny

Conceptual test:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import org.springframework.data.redis.core.StringRedisTemplate;

String subject = "ttlTest" + UUID.randomUUID()
        .toString().replace("-", "");
String key = "rl:reports:{" + subject + "}:fixed:v1";

limiter.check(subject, 1, Duration.ofSeconds(30));
Duration initialTtl = strings.getExpire(key);

RateLimitService.Decision denied =
        limiter.check(subject, 1, Duration.ofSeconds(30));
Duration afterDenied = strings.getExpire(key);

assertThat(denied.allowed()).isFalse();
assertThat(initialTtl).isGreaterThan(Duration.ZERO);
assertThat(afterDenied).isLessThanOrEqualTo(initialTtl);
```

`strings` is the `StringRedisTemplate` bean. Place this snippet inside a properly configured test class with injected beans. TTL decreases over time; do not assert equality to `Duration.ofSeconds(30)`. Do not run `sleep(30s)` in every test waiting for expiration: use a dedicated short window for an integration test or Redis test clock capabilities where supported.

### 20.4. Testing Missing-TTL Errors

Scenario:

1. In test Redis, execute `SET rl:reports:{subject}:fixed:v1 2` **without a TTL**.
2. Call the limiter for that subject.
3. Expect the script to raise an invariant error rather than allowing indefinitely or silently resetting the key.
4. Clean up only the test key using an authorized test account.

This tests corrupt/legacy state handling. It verifies how code behaves when another writer violates the key contract, rather than a normal path.

## 21. Testing HTTP Responses and Integration Boundaries

A Spring MVC/MockMvc test should check:

1. Calls 1–5 return HTTP 200 (or the expected business status).
2. The 6th call returns `429`.
3. Header `Retry-After` is a positive integer number of seconds.
4. `X-RateLimit-Remaining` is 0.
5. The business method is **not invoked** when the limiter denies.

When using Spring Security in tests, supply a valid authenticated principal with a short subject ID instead of spoofing users via arbitrary headers. For unauthenticated failure paths, explicitly decide whether `401` responses count against quotas (e.g., IP rate limits on login attempts).

### 21.1. Testing Three Distinct Response Types

| Condition | Recommended Result |
|---|---|
| Quota available | Process request, 2xx/4xx per business logic |
| Quota exhausted | `429 Too Many Requests` + `Retry-After` |
| Redis limiter error | `503` or fallback per policy, never disguised as quota exhausted |

If a downstream API returns `500` after the rate limiter admits a call, the counter has already consumed one slot. **Refunding quota** is a complex business decision prone to races if you simply run `DECR` on exceptions. Typically, admitted requests count as accepted attempts even when the business operation fails; if billing strictly by success, design a reservation/commit/refund flow with explicit idempotency.

## 22. Intentionally Reproducing Races in Broken Approaches

A valuable hands-on exercise is comparing:

**A. GET → SET counter:** use two threads and a `CountDownLatch` to force both to read `count=4` and write `count=5`. Expect two admissions even though only one slot remained.

**B. Separate INCR → EXPIRE:** in lab Redis, execute `INCR` and simulate an app crash before `EXPIRE`; observe `PTTL=-1`. This demonstrates key leakage.

**C. Lua fixed window:** 50 concurrent threads, strictly 10 admissions; key gets a TTL on the first request.

Never simulate crashes by killing production Redis or altering real customer counters. Every experiment must use an isolated namespace and a dedicated test Redis.

## 23. Measuring Performance of the Lua Rate Limiter

A short Lua script usually reduces round-trips because read/check/write/TTL execute in a single Redis request. However, Lua runs on the Redis event loop; **long scripts or O(N) commands block all other clients**.

### 23.1. Metrics to Measure

| Metric | Why It Matters |
|---|---|
| p50/p95/p99 `EVALSHA` duration | Latency cost of the limiter on the hot path |
| `rate_limit_allowed_total` | Requests admitted per policy |
| `rate_limit_rejected_total` | Quota pressure; cannot be inferred from accepted-only counters |
| `rate_limit_error_total` | Redis unavailable, NOPERM, script errors, timeouts |
| Active limiter keys | Number of subjects currently holding an active window |
| `used_memory` / memory per key | Key explosion by user/IP/route |
| SLOWLOG, command stats | Are Redis scripts causing slow commands? |
| CPU per Redis master | Is a hot key/slot overloading a shard? |
| API response p99 | Is the limiter affecting the SLO? |
| HTTP 429 rate | Did it spike unexpectedly after a policy rollout? |

Metric names in the table are **instrumentation suggestions**, not defaults automatically emitted by Spring Data Redis.

### 23.2. Why Local Benchmarks Are Not Enough

Suppose a script takes 0.2 ms on a laptop, while production Redis sits in another zone behind TLS, network RTT, gateways, JVM schedulers, connection pools, and container infrastructure. End-to-end latency can be much higher.

Benchmark with Redis versions, topology, payloads, connection pooling, traffic distributions, and peak concurrency representative of production. Do not run large load tests against production Redis without approval.

### 23.3. Always Keep Scripts Short

Avoid:

```lua
-- Anti-pattern: never write a rate limiter like this.
local keys = redis.call('KEYS', 'rl:*')
for _, key in ipairs(keys) do
    -- Iterating every user on every request: severe resource bottleneck.
end
```

A rate limiter must be O(1) or bounded by a small quota. With a sliding-window log, `ZREMRANGEBYSCORE` can remove multiple elements and cost grows with stale entries; bound admitted events and measure actual execution times.

## 24. TTL, Key Explosion, and Memory

With a 60-second per-user rate limit, keys ideally expire shortly after the last access in a window. Yet if one million distinct identities each send one request, Redis can create one million counter keys.

Estimate:

```text
Active subjects per minute ≈ 200,000
Live fixed-window keys ≈ 200,000
Actual memory/key = counter payload + key bytes + Redis metadata
```

Do not estimate RAM using `String.length()`. Use `MEMORY USAGE key`, `INFO memory`, `INFO keyspace`, and `DBSIZE` in a test environment with a representative key set.

### 24.1. Defending Against Unbounded Identity Creation

For unauthenticated endpoints, an attacker can vary `X-Forwarded-For` or arbitrary key strings if the gateway fails to validate sources. This is a **cardinality attack**:

```text
request-1 -> rl:ip:A
request-2 -> rl:ip:B
request-3 -> rl:ip:C
...
```

Mitigations:

- Normalize identity from trusted information.
- Block crude abuse at the edge before requests reach Redis.
- Set key/namespace/tenant caps and monitor key growth.
- Use short policy-driven TTLs; never create unbounded keys for unverified input.
- Add global/range limiters designed not to become single hot keys.

### 24.2. Do Not Use Key Count to Infer Request Volume

An active subject may hold multiple quota keys. Keys expire over time. `DBSIZE` includes unrelated Redis keys. Key count is not processed request volume; use dedicated application metrics/counters.

## 25. Data and Atomicity During Failover

Lua guarantees **atomic read/check/write on the chosen primary**, not that writes have replicated to the promoted replica. During Sentinel/Cluster failover, recent counter increments can be lost.

Example:

```text
Master A: count=4 --> script admits request, count=5
                         |
                 not yet replicated
                         |
                   A encounters failure
                         |
Replica B promoted to master with count=4
                         |
Next request can be admitted again
```

Redis `WAIT`, `WAITAOF`, or persistence can improve durability properties, **but do not turn a shared Redis limiter into a consensus-backed quota ledger**. Reserve strict transactional guards for high-stakes quotas on systems with matching commit/transaction semantics.

### 25.1. Rate Limiting Does Not Stop Every Attack

A distributed attacker using many IPs/accounts can stay below each identity's individual limit. Rate limiters must work alongside WAFs, authentication, abuse detection, concurrency limits, request size limits, and downstream cost caps.

A single very expensive request can cause overload even at 1 req/sec; in those cases, use **concurrency limiters**, job queues, resource-cost quotas, or other worker admission controls.

## 26. Logging, Monitoring, and Data Protection

Sample log:

```text
policy=reports-v1
subjectHash=4f9c...
decision=DENY
used=5
limit=5
retryAfterMs=29134
redisShard=slot-owner
requestId=...
```

Do not log raw emails, API key secrets, auth tokens, or sensitive request payloads solely for rate-limit diagnostics. Emit metrics by policy and tenant class rather than individual subjects if metric cardinality would explode.

A useful dashboard includes:

- Allowed/rejected/errors by route group.
- P99 Redis Lua latency and application p99.
- Active limiter keys; memory/evictions.
- Top N tenants by request volume (handled under privacy policies).
- Redis failover/topology change events.
- Fallback request volume when the limiter is unavailable.

When Redis enables eviction policies like `allkeys-lru`, rate-limit keys can be evicted before their TTL, causing **premature quota resets**. For critical quotas, isolate Redis deployments/namespaces and choose an appropriate memory policy; do not mix rate-limit state with freely evicted caches without assessing the impact.

## 27. Common Implementation Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| `GET` then `SET` counter | Lost updates under concurrency | Atomic Lua or proper primitive |
| Two separate `INCR` and `EXPIRE` commands | Crash in between leaves key without TTL | Lua `INCR` + `PEXPIRE` |
| `EXPIRE` on every request | TTL constantly resets; breaks fixed-window semantics | Set TTL only on key creation |
| Local Java `AtomicInteger` | Each instance enforces its own quota | Shared Redis counter |
| Untrusted `X-User-Id` header | Clients pick arbitrary keys to bypass limits | Trusted principal/API key ID |
| Raw email/API key in Redis key | Data leaks via Redis keys/logs | Opaque ID or HMAC |
| Counting denied calls when docs say accepted-only | Remaining/count breaks contract | Specify semantics clearly and test |
| All policies under `rl:{global}` | Hot slot/master bottleneck | Partition by subject, gateway layer |
| Two quotas via two separate scripts | Can consume one quota even when the other denies | Single same-slot script or explicit trade-off policy |
| Lua builds key names from arbitrary input | Violates Cluster key declaration/ACLs | Pass keys explicitly via `KEYS` |
| Time/window depends on skewed client clocks | Inconsistent windows across instances | TTL-on-first-hit or server `TIME` |
| Running script at wrong auth stage | Anonymous users share quota or clients spoof IDs | Determine identity and filter order carefully |
| Not checking Redis errors | Accidental fail-open/fail-closed | Explicit error policy and separate metrics |
| Retrying Lua after timeout without idempotency | One request may be counted twice | Define retry semantics |
| Treating Redis failover as an exact global quota | Counter writes can be lost | Analyze fault model and use a ledger if needed |
| Sliding ZSet with `member=userId` | Multiple requests by one user count as one | Unique request event ID |
| Unpruned sliding log | ZSet grows unboundedly | Atomic prune/count/add + TTL |
| Running `SMEMBERS`/`KEYS *` per request | Blocks Redis or returns huge payloads | O(1)/bounded Lua |
| Missing TTL/cleanup | Key explosion | TTL + monitoring |
| Redis eviction deletes limiter keys | Early quota reset | Dedicated memory policy/deployment |
| Fixing NOPERM by granting `+@all` | Breaks least privilege | Exact ACL commands + key pattern |
| Mocking only `RedisTemplate` in tests | Misses races and TTL bugs | Testcontainers and concurrency tests |
| Returning 429 on infrastructure failures | Clients mistake outage for quota exhaustion | Distinguish 429 vs 503/fallback |

## 28. Self-Guided Practical Labs

### Lab 1 — Fixed-Window Lua with 5 Calls/Minute

1. Start a standalone test Redis.
2. Save `fixed_window.lua` from Section 5.
3. Run `redis-cli --eval ... , 5 60000` six times.
4. Record the returned tuple each time.
5. Verify the sixth call is blocked and count remains `5`.
6. Check that `PTTL` is not extended by blocked requests.
7. After TTL expires, confirm a new request is admitted.

### Lab 2 — Comparing GET/SET, INCR/EXPIRE, and Lua

1. Write `GET`-then-`SET` code and force two threads to read the same count before writing.
2. Observe the lost update.
3. Run `INCR` without `EXPIRE` in lab Redis and verify `PTTL=-1`.
4. Replace with Lua; run the 50-request/limit-10 concurrency test.
5. Explain why script **atomicity** does not equal failover durability.

### Lab 3 — Spring Boot HTTP 429

1. Create `RateLimitService` and the demo controller.
2. Configure a valid authenticated test principal with an opaque subject ID.
3. Call the endpoint five times and expect quota to remain valid.
4. Call a sixth time and expect 429 with `Retry-After`.
5. Verify business logic does not execute when denied.
6. Change the limit in config and decide whether the policy suffix must change.

### Lab 4 — Client Hitting Multiple Spring Instances

1. Run two Spring Boot instances on different ports pointing to the **same test Redis**.
2. Alternate calls to A and B for the same subject.
3. Verify total quota still never exceeds 5 in the same window.
4. Demonstrate how separate local counters per instance allow doubling the quota.

### Lab 5 — Sliding-Window Log

1. Create `sliding_window.lua` with `TIME`, `ZREMRANGEBYSCORE`, `ZCARD`, and `ZADD`.
2. Send 5 requests near the end of an arbitrary interval.
3. Send 5 more requests immediately afterward.
4. Compare fixed-window vs sliding-window behavior.
5. Ensure each admitted request has a **unique eventId**.
6. Use `ZCARD`/`MEMORY USAGE` to observe memory growth with event count.

### Lab 6 — Redis Cluster

1. Use a test Cluster with multiple masters.
2. Check the hash slots of `rl:reports:{user42}:short` and `rl:reports:{user42}:long`.
3. Write a Lua script checking both counters before committing.
4. Try a pair of keys in different slots and observe the Cluster restriction.
5. Design key schemas with deliberate hash tags without funneling all subjects into one slot.

### Lab 7 — Least-Privilege ACLs

1. Create a test Redis ACL user restricted to key pattern `~rl:reports:*`.
2. Grant scripting, `GET`, `INCR`, `PEXPIRE`, `PTTL` as needed.
3. Run the Spring integration test successfully.
4. Test `FLUSHALL` via `ACL DRYRUN` on Redis 7+ and verify it is denied.
5. Revoke one required command to observe `NOPERM` and restore the minimal policy.

### Lab 8 — Failover and Fallback Policies

1. In a test Sentinel/Cluster setup, measure allowed/rejected counts before and after a controlled failover.
2. Observe timeout/connection errors and possible rolled-back counters.
3. Choose fail-open, fail-closed, or local fallback for a non-critical API.
4. Document the HTTP response and metric policy.
5. Explain why billing quotas should not rely solely on an async-replicated Redis counter.

## 29. Pre-Production Checklist for Rate Limiters

**Algorithm and Contract**

1. Which subject scopes the quota: user, API key, tenant, IP, or route?
2. Does identity come from a trusted authenticated source?
3. When does the fixed window begin? Are boundary bursts acceptable?
4. Does the counter track admitted or attempted requests?
5. Are sliding windows or token buckets needed?
6. Are limits and windows configurable, validated, and versioned?
7. Are 429, Retry-After, and remaining headers documented for API clients?

**Redis and Lua**

8. Do read/check/write/TTL execute in an atomic Lua script?
9. Do keys always have a TTL that is not wrongly extended on deny?
10. Is the script static, with working EVALSHA fallback?
11. Are O(N) scripts kept off the hot path?
12. Do Redis ACLs grant only required commands and key patterns?
13. On Cluster, are all script keys valid and same-slot where required?
14. Are global hot keys prevented from overloading one master?
15. Does Redis memory/eviction policy protect limiter keys?

**Correctness and Availability**

16. Are there real-Redis integration and concurrency tests?
17. Are expiration, corrupted counters, timeouts, and uncertain retries tested?
18. Is fail-open/fail-closed/fallback designed intentionally?
19. Are async replication/failover limitations accepted?
20. Do billable/critical business quotas have a stronger authority if needed?
21. Are there defenses against high-cardinality key explosions?
22. Is the limiter coordinated with WAF, auth, concurrency limits, and downstream quotas?

**Operations**

23. Are allowed/rejected/error counts and p99 Lua latency monitored?
24. Are there dashboards for active keys, memory, and hot slots?
25. Are alerts set for NOPERM, failover, script errors, and sudden 429 spikes?
26. Is there a cadence to review thresholds against real traffic?
27. Is there a runbook for changing policies without unintended quota resets?

## 30. Summary

A distributed Redis rate limiter commonly starts with a **counter with a TTL**. `INCR` alone is atomic, but separating `INCR` and `EXPIRE` opens a failure window if a worker crashes between commands. A short Lua script can **check the quota, increment the counter when allowed, set `PEXPIRE` on key creation, and return the remaining TTL** in one call from `StringRedisTemplate`. This provides a solid foundation for fixed-window rate limiting across multiple Spring Boot instances.

Fixed windows are simple but allow boundary bursts; when stricter enforcement is required, use a Sorted Set sliding-window log or a token bucket with matching semantics. Alongside the algorithm, establish **trusted identities**, HTTP 429/Retry-After responses, retry/timeout handling, multi-policy coordination, Redis Cluster hash slots, memory/eviction tuning, and real concurrency tests.

Finally, Redis Lua atomicity does not solve asynchronous failover or global quotas across independent Redis deployments. For ordinary APIs, small discrepancies are acceptable; for quotas affecting money or irreversible resources, protect decisions at an authoritative system with suitable transactional/consistency guarantees.

## References

- [Redis — INCR](https://redis.io/docs/latest/commands/incr/): atomic counters and rate limiter examples using INCR/EXPIRE/Lua.
- [Redis — EVAL](https://redis.io/docs/latest/commands/eval/): running Lua scripts on the Redis server.
- [Redis — PEXPIRE](https://redis.io/docs/latest/commands/pexpire/): TTL in milliseconds.
- [Redis — PTTL](https://redis.io/docs/latest/commands/pttl/): remaining time to live and -1/-2 values.
- [Redis — Rate Limiting](https://redis.io/docs/latest/develop/use-cases/rate-limiter/): rate limiter designs and trade-offs.
- [Redis — Rate limiting with Java and Spring](https://redis.io/tutorials/rate-limiting-in-java-spring-with-redis/): Java/Spring practical example with atomic Lua.
- [Redis — ZADD](https://redis.io/docs/latest/commands/zadd/): Sorted Sets for sliding-window logs.
- [Redis — ZREMRANGEBYSCORE](https://redis.io/docs/latest/commands/zremrangebyscore/): pruning events outside a rolling window.
- [Redis — TIME](https://redis.io/docs/latest/commands/time/): reading timestamps from the Redis server.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots and multi-key constraints.
- [Redis — Access Control Lists](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): command and key scopes for scripting users.
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html): `RedisScript` and `RedisTemplate.execute`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis access, serializers, and connection factories.
- [Spring Boot — Redis configuration](https://docs.spring.io/spring-boot/reference/data/nosql.html): connecting Spring Boot and Redis.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): Redis integration tests with containers.
- [HTTP Semantics — 429 Too Many Requests](https://www.rfc-editor.org/rfc/rfc6585#section-4): response when rate limits are exceeded.
