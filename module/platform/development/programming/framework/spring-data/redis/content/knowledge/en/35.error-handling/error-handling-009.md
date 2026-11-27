# Preserving Error Causes and Limiting Sensitive Data in Logs

## 1. The Problem: Handling Redis Errors While Keeping Diagnostics Clear and Data Safe

A Spring Boot application uses Spring Data Redis to read caches, store sessions, run Hash operations, and consume messages. When Redis disconnects or a serializer hits malformed data, a technical failure can traverse multiple layers:

```text
Lettuce / Redis connection
          |
          | RedisCommandTimeoutException or I/O error
          v
Spring Data Redis
          |
          | Exception translation / wrapping
          v
Repository / Service
          |
          | CacheAccessException
          v
REST Controller / Reactive handler
          |
          v
HTTP error + telemetry
```

Along this path, two requirements are often mistakenly treated as contradictory:

1. **Preserving the error cause:** higher-layer exceptions must stay linked to the original failure so engineers can diagnose connection drops, timeouts, serializers, wrong data types, or failed Redis commands.
2. **Limiting sensitive data in logs:** never write passwords, tokens, session IDs, full Redis keys, values, command payloads, or user details into logs solely for debugging.

Consider two flawed approaches:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    throw new RuntimeException("Redis error");
}
```

The snippet above drops the **cause** by failing to pass `ex` into the new exception.

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    log.error("Redis failed, key={}, value={}, exception={}",
            key, value, ex.getMessage(), ex);
    throw ex;
}
```

The second snippet risks leaking sensitive information. Redis keys often embed emails, phone numbers, user IDs, or session identifiers. Values can hold personal data. Even `ex.getMessage()` or a **full stack trace** from a driver can embed keys, commands, connection URLs, or arguments.

**Core principle:** keep the original error object inside the **exception's `cause` chain**, yet **never blindly dump full exceptions, raw messages, and business payloads into logs**. Logs should emit curated, controlled attributes.

This lesson belongs to the **Error Handling** chapter of **Spring Data Redis**. Its goal is to implement error handling that is diagnosable, data-safe, and consistent across `RedisTemplate`, reactive Redis, listeners, and REST APIs.

## 2. Separating Error Cause, Error Message, and Log-Safe Fields

A Java exception contains several parts:

```text
Class/type:        RedisConnectionFailureException
Message:           May contain server address / command content
Cause:             Lower-level error, such as an I/O exception
Suppressed:        Secondary errors during resource cleanup
Stack trace:       Call locations across Java classes
Context:           Operation name, request ID, duration, retry count
```

These parts do not share the same safety profile.

| Component | Diagnostic Value | Risk When Written to Logs |
|---|---|---|
| Exception class | Identifies technical failure group | Generally lower than payloads |
| Cause class | Identifies low-level failure | Generally lower than raw messages |
| Exception message | May contain detailed driver context | Can expose keys, URIs, commands, or user data |
| Full stack trace | Shows execution path | Can print exception messages, suppressed exceptions, and infrastructure details |
| Redis key | Pinpoints failing resource | Can contain PII or tokens |
| Redis value | Reveals processed content | Very likely to hold sensitive data |
| Raw Redis command | Useful for protocol debugging | Can include payloads, passwords, script arguments |
| Allowlisted operation name | Identifies failing feature | Usually safe if drawn from an allowlist |
| Error category | Groups failures for alerting | Usually safe |
| Internal trace ID | Correlates processing steps | Usually safe if generated and managed properly |
| Timing / duration | Measures timeouts and latency | Usually safe |
| Retry attempt | Shows how many retries occurred | Usually safe |

**Preserving an exception** does not mean **permission to dump the entire exception to every log sink**. Diagnostic details can remain in the runtime `cause` chain, inside tightly controlled observability channels, or in restricted-access debugging environments.

### 2.1. A Redis Key Itself Can Be Sensitive Data

Examples:

```text
session:7f3c88b7a0e94c7ba...
user:lan@example.com:profile
password-reset:one-time-token
auth:bearer:eyJ...
tenant:acme:customer:8490...
```

Even when the value is `true`, the key name reveals identity, session state, or tokens. Never assume "keys are just metadata so logging them is fine."

### 2.2. Stack Traces Are Not Safe by Default

A familiar line:

```java
log.error("Redis failed", ex);
```

usually makes the logging framework print the exception class, message, cause chain, and stack trace. If an exception message carries a connection string or payload data, that data goes straight into centralized logs.

In production, **avoid logging full throwables as a blanket rule** for every Redis exception. If stack traces are truly required, audit what the library embeds in messages and route them to access-controlled diagnostic channels or sanitized extractors.

## 3. Spring Data Redis Exception Translation

Spring Data Redis runs on top of Redis drivers, commonly **Lettuce**. Driver errors can map to Spring Data Redis exceptions and Spring's **`DataAccessException`** hierarchy.

Common categories:

| Failure Group | Application-Layer Signal | Handling Meaning |
|---|---|---|
| Cannot connect to Redis | `RedisConnectionFailureException` or connection cause | Redis or network temporarily unreachable |
| Timeout | `QueryTimeoutException` or driver timeout cause | Command received no reply within budget |
| Command or server error | Appropriate `RedisSystemException`/`DataAccessException` | Inspect command, permissions, config, server state |
| Serialization/deserialization error | `SerializationException` or related cause | Likely schema mismatch or incompatible bytes |
| Wrong Redis type | Wrapped command error such as `WRONGTYPE` | Inspect schema/type; do not treat as cache miss |
| Auth/ACL failure | Driver/server error, possibly translated | Configuration or permissions must be fixed |
| Key not found | `GET` returns `null`/`Mono.empty()` | **Not an exception** |

Exact exception types depend on Spring Data Redis version, driver, and command. Therefore, **never rely purely on matching an error message substring** for classification:

```java
if (ex.getMessage().contains("timeout")) {
    // Fragile: message wording changes or may be null.
}
```

Classify primarily by exception **type** and structured library attributes, while preserving the original `cause` when wrapping.

### 3.1. A Valid Cause Chain

```text
CacheAccessException: "Redis read failed"
    caused by RedisConnectionFailureException
        caused by RedisCommandTimeoutException
```

The service-layer exception carries a **safe, stable message**, while technical root causes remain intact in `getCause()` for appropriate internal handlers.

### 3.2. Never Lose the Cause by Constructing Exceptions from Messages Alone

Wrong:

```java
catch (DataAccessException ex) {
    throw new IllegalStateException(ex.getMessage());
}
```

Because:

- The new exception's `getCause()` is `null`.
- The original type is replaced by hard-to-classify text.
- The original message may carry sensitive details up into higher-layer logs or responses.

Better:

```java
catch (DataAccessException ex) {
    throw new CacheAccessException(
            RedisFailureCategory.OTHER_REDIS_ERROR,
            ex
    );
}
```

The new exception preserves **`ex` itself as `cause`**, rather than merely copying its text.

## 4. Designing Business Exceptions with Safe Messages and Original Causes

### 4.1. Categorizing Failures into a Finite Enum

```java
package com.example.redis.errors;

public enum RedisFailureCategory {
    CONNECTION,
    TIMEOUT,
    SERIALIZATION,
    OTHER_REDIS_ERROR
}
```

This is an **application-defined enum**, not a Spring exception. Finite values keep dashboards from using raw error messages as metric labels.

### 4.2. Wrapper Exception Preserving the Original Cause

```java
package com.example.redis.errors;

public final class CacheAccessException extends RuntimeException {

    private final RedisFailureCategory category;
    private final String safeOperation;

    public CacheAccessException(
            String safeOperation,
            RedisFailureCategory category,
            Throwable originalCause) {

        // Wrapper message is static and contains no keys or values.
        super("Redis dependency operation failed", originalCause);

        this.safeOperation = safeOperation;
        this.category = category;
    }

    public RedisFailureCategory category() {
        return category;
    }

    public String safeOperation() {
        return safeOperation;
    }
}
```

Here, `safeOperation` must come from a **code allowlist**, such as:

```text
product_cache_read
product_cache_write
session_lookup
```

Never populate `safeOperation` from request paths, Redis key names, user input, or dynamic Redis commands. Naming a field "safe" does not make it safe if its input is uncontrolled.

Usage example:

```java
throw new CacheAccessException(
        "product_cache_read",
        RedisFailureCategory.CONNECTION,
        originalException
);
```

Outcome:

- Public wrapper message stays tightly constrained.
- Higher layers can inspect `category` and `safeOperation`.
- `getCause()` returns the original exception; the cause chain stays intact.

## 5. Building a RedisTemplate Service Without Logging Sensitive Data

Suppose the app reads JSON stored under a Redis key containing a product ID. In business code, IDs carry meaning, yet logs do not need the full key.

### 5.1. Read Path with Error Classification

```java
package com.example.redis.errors;

import java.util.Optional;

import org.springframework.dao.DataAccessException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheReader {

    private final StringRedisTemplate redis;

    public ProductCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Optional<String> read(long productId) {
        if (productId <= 0) {
            throw new IllegalArgumentException(
                    "productId must be positive"
            );
        }

        String key = "product:detail:v3:" + productId;

        try {
            String value = redis.opsForValue().get(key);
            return Optional.ofNullable(value);

        } catch (DataAccessException | SerializationException ex) {
            throw new CacheAccessException(
                    "product_cache_read",
                    categorize(ex),
                    ex
            );
        }
    }

    private static RedisFailureCategory categorize(RuntimeException ex) {
        if (ex instanceof RedisConnectionFailureException) {
            return RedisFailureCategory.CONNECTION;
        }

        if (ex instanceof QueryTimeoutException) {
            return RedisFailureCategory.TIMEOUT;
        }

        if (ex instanceof SerializationException) {
            return RedisFailureCategory.SERIALIZATION;
        }

        return RedisFailureCategory.OTHER_REDIS_ERROR;
    }
}
```

Here:

1. `GET` returning `null` for a missing key maps to `Optional.empty()`.
2. Connection, command, or serialization failures are wrapped in `CacheAccessException`.
3. **The original exception is passed as `cause`**.
4. The service **never logs full keys, values, or raw throwables**.
5. The API boundary logs once using safe fields.

Some Redis errors may stem from programming bugs or exceptions outside these caught types. Avoid `catch (Exception)` if it risks swallowing all errors. If more library exceptions must be caught, classify specific types so code bugs are not hidden.

### 5.2. Serializer Errors Must Preserve Cause Without Leaking Payloads

If Redis holds JSON incompatible with the model:

```java
ProductProfile value = jsonTemplate
        .opsForValue()
        .get("profile:v3:42");
```

the serializer throws a decoding failure. Never do:

```java
log.warn("Invalid redis value: {}", rawJson);
```

Instead, log the error category and schema version:

```text
event=redis_operation_failed
operation=profile_cache_read
category=SERIALIZATION
schemaVersion=3
exceptionClass=SerializationException
```

This pinpoints the problem without pushing user JSON into logs.

**Do not treat serializer errors as cache misses by default.** Swallowing them can silently overwrite valid caches or mask a schema-breaking deployment.

## 6. Log Only at the Appropriate Handling Boundary

A common anti-pattern is logging the exact same failure at every layer:

```text
Redis Driver        -> log error
Repository          -> log error + throw
Service             -> log error + throw
Controller Advice   -> log error
API Gateway         -> log error
```

One Redis failure generates multiple stack traces, which:

- Inflates logging cost.
- Multiplies places where sensitive data may leak.
- Skewed error counts make incidents harder to quantify.
- Easily triggers **log storms** during a system-wide Redis outage.

A practical rule:

- **Lower layers** preserve exceptions, attach **safe** context if needed, and propagate.
- **Decision layers** handling fallbacks/retries apply policy and record metrics.
- **Boundary layers** log the failure event once in a controlled format.
- Intermediate layers avoid pointlessly repeating stack traces.

Example:

```text
Repository -> CacheAccessException(original cause)
        |
        v
Service -> decides to propagate
        |
        v
ControllerAdvice -> logs safe event once
        |
        v
Response -> generic error code + errorId
```

If an error is fully absorbed by a fallback, the boundary never sees an exception; in that case the fallback layer must record metrics and bounded safe logs so the Redis outage does not vanish from visibility.

## 7. Safe Logging at the API Layer: Keep Cause, Do Not Print Raw Throwables

### 7.1. Standardize Error Responses

Never return raw Redis exception messages to clients:

```java
return ResponseEntity.status(500).body(ex.getMessage());
```

Messages can reveal infrastructure details or another request's data. Instead, return a stable error code and a log-correlation ID.

```json
{
  "code": "REDIS_DEPENDENCY_UNAVAILABLE",
  "message": "Service temporarily unavailable",
  "errorId": "93acbfbb-36a0-4ca0-aefa-e1d24a06c9bc"
}
```

This illustrates response structure; generate a unique `errorId` per error event in real requests.

### 7.2. ControllerAdvice Logging Only Controlled Fields

```java
package com.example.redis.errors;

import java.util.UUID;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RedisErrorAdvice {

    private static final Logger log =
            LoggerFactory.getLogger(RedisErrorAdvice.class);

    public record ApiError(
            String code,
            String message,
            String errorId
    ) {
    }

    @ExceptionHandler(CacheAccessException.class)
    public ResponseEntity<ApiError> handle(CacheAccessException ex) {

        String errorId = UUID.randomUUID().toString();
        Throwable root = rootCause(ex);

        // Intentionally DO NOT pass ex as the final log argument.
        // Preserves cause in the object without dumping raw messages.
        log.warn(
                "event=redis_dependency_failure"
                + " operation={} category={} exceptionType={}"
                + " rootCauseType={} errorId={}",
                ex.safeOperation(),
                ex.category(),
                ex.getCause().getClass().getName(),
                root.getClass().getName(),
                errorId
        );

        ApiError body = new ApiError(
                "REDIS_DEPENDENCY_UNAVAILABLE",
                "Service temporarily unavailable",
                errorId
        );

        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(body);
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;

        // Cause chains normally do not cycle; cap iterations
        // to guard against malformed Throwable self-references.
        for (int i = 0; i < 32; i++) {
            Throwable next = current.getCause();

            if (next == null || next == current) {
                break;
            }

            current = next;
        }

        return current;
    }
}
```

Important properties:

- `ex.getCause()` stays intact inside `CacheAccessException`.
- Logging uses allowlisted `operation`, category, and class names.
- Logging **omits Redis keys, values, queries, and exception messages**.
- Logging **does not pass `ex` as SLF4J's trailing `Throwable` argument**, so raw cause chains are not printed automatically.
- The HTTP response leaks no exception classes, Redis hosts, keys, or stack traces.
- `errorId` correlates the client response with the log record.

Not every Redis error should return 503. HTTP 503 in this example suits a read path that strictly depends on Redis with no fallback. Pick status codes matching the failure and API contract; never turn input validation failures into "Redis unavailable."

### 7.3. Why Preserve the Full Cause If Stack Traces Aren't Logged?

The cause chain supports:

- Internal retry/fallback classification logic.
- Security-compliant collection inside controlled diagnostic environments.
- Accurate library error categorization.
- Tests verifying wrappers do not drop root exceptions.
- Authorized debugging in application sessions.

To add more detail safely, emit **structured safe metadata**: exception type, operation, duration, phase, node role, retry count, component, and error ID. Send full throwables to dedicated logs only after auditing driver/serializer messages for sensitive data.

## 8. Rules for What May and May Not Be Logged

A clear logging policy stops teams from reinventing decisions on every endpoint.

### 8.1. Prefer Allowlisted Safe Fields

Example:

```text
event             = redis_dependency_failure
operation         = session_lookup
category          = TIMEOUT
component         = auth-service
redisCommandClass = GET
durationMs        = 803
attempt           = 2
exceptionType     = QueryTimeoutException
rootCauseType     = RedisCommandTimeoutException
errorId           = 93acbfbb-36a0-4ca0-aefa-e1d24a06c9bc
```

Fields such as `operation`, `component`, and `redisCommandClass` should come from **enums or allowlists**. `durationMs` and `attempt` are bounded numeric telemetry.

`rootCauseType` tells engineers the root failure group without broadcasting driver `getMessage()` strings.

### 8.2. Do Not Log These by Default

- Passwords, access tokens, session tokens, refresh tokens, API keys.
- Redis URIs containing usernames/passwords or auth parameters.
- Redis keys embedding emails, phone numbers, tenant IDs, or user identifiers.
- Complete Redis commands, especially `SET`, `HSET`, Lua arguments, `AUTH`.
- Redis values: JSON, serialized objects, Hash fields, Stream payloads.
- Pub/Sub message contents.
- Redis responses used in authorization decisions.
- Raw `ex.getMessage()`, `ex.toString()`, or unverified library stack traces.
- Payloads an application tried to write that Redis rejected.
- Full HTTP request/response bodies inside Redis error logs.

Even masking some characters with `***` can fall short when formats vary, payloads are encoded, or exceptions repeat sensitive data in multiple places.

### 8.3. Log Namespace Names Instead of Full Keys

Instead of:

```text
key=session:eyJhbGciOiJIUzI1Ni...
```

log:

```text
namespace=session
operation=session_lookup
```

Namespaces must come from code constants or finite mapping tables, never concatenated directly from user-supplied strings.

If correlating one logical key across logs is truly necessary, consider a **controlled pseudonymous identifier**:

```text
keyFingerprint=HMAC-SHA256(secret, rawKey) [truncated sufficiently]
```

HMAC with a managed secret resists brute-force guessing far better than unkeyed SHA-256 on small ID spaces. Still:

- Fingerprints can still act as linkable identifiers over time; enforce retention and access controls.
- Never hardcode secrets in code or logs.
- Never use fingerprints for authentication.
- Never put high-cardinality fingerprints into metric tags.
- Usually namespace plus error ID suffices; few failures truly need a key fingerprint.

### 8.4. Sanitize Redis Endpoints Too

Host/port helps pinpoint a failing replica or shard, yet full connection URLs often embed credentials.

Prefer normalized node identifiers:

```text
redisNodeRole=replica
redisNodeAlias=cache-node-2
```

instead of printing `redis://username:password@host:port` into logs.

## 9. Diagnosing Root Causes Without Relying on Exception Messages

### 9.1. Group by Type

The application layer can produce:

```java
new CacheAccessException(
        "profile_cache_read",
        RedisFailureCategory.SERIALIZATION,
        serializationException
);
```

During investigation:

```text
operation=profile_cache_read
category=SERIALIZATION
rootCauseType=JsonMappingException
schemaVersion=3
```

That tells developers to inspect schema, serializer format, and version rollout without ever seeing real profile data.

### 9.2. Do Not Infer Everything Solely from Root-Cause Class

The exact same I/O exception class can stem from:

- Temporarily overloaded Redis server.
- Network disconnect.
- Overly tight timeout.
- Connection closed during failover.
- Congested client pool or event loop.

Exception class is the initial signal, not the complete diagnosis. Pair it with telemetry:

```text
client latency p95/p99
Redis INFO stats
connection failures
pool pending
server role/topology
retry attempts
time window
deployment version
```

Capture these under controlled labels. Avoid turning on raw command logging just to guess at bottlenecks.

### 9.3. Keep Safe Error Context Immutable Across Layers

A wrapper exception can carry:

```text
safeOperation = product_cache_read
category = TIMEOUT
```

Passing up through layers, never re-wrap repeatedly with messages containing keys:

```java
throw new RuntimeException(
        "Failed to read " + key + " because " + ex.getMessage(),
        ex
);
```

Even though the cause remains, the new wrapper message leaks the key whenever anything calls `toString()` or prints the stack.

Keep wrapper messages static, attach structured context, or control output at the boundary.

## 10. Distinguishing Cache Misses from Redis Errors

A serious design flaw:

```java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
```

This turns every failure into "key absent":

```text
Redis GET returns null        -> valid MISS
Redis connection timeout      -> also returns null
Broken serializer             -> also returns null
AUTH/ACL error                -> also returns null
```

Consequences:

- Application is blind to Redis failures.
- Cache miss ratio inflates falsely.
- Database can overload on fallback.
- Data corruption bugs stay hidden.
- Cause chains disappear for analysis.

Clearer outcomes:

```text
CACHE_HIT
CACHE_MISS
CACHE_ERROR_CONNECTION
CACHE_ERROR_TIMEOUT
CACHE_ERROR_SERIALIZATION
```

Model these states explicitly, or let `null`/`Optional.empty()` represent misses while errors propagate as exceptions.

**Never treat `SerializationException` as a miss by default** when Redis may hold schema-mismatched bytes requiring investigation.

## 11. Safe Fallbacks When Redis Is Cache-Only

Not every Redis error must fail the API. If an **authoritative source** holds the data, you can read from it when Redis disconnects.

Logic flow:

```text
GET cache
   |
   +-- Hit --------> Return cached value
   |
   +-- Miss -------> Read database -> Optionally repopulate cache
   |
   +-- Redis down -> Read database (controlled fallback)
   |
   +-- Serializer error -> Report error / quarantine per policy
```

Design requirements:

- Fall back only for permitted error groups, such as connectivity loss.
- Never silently treat permission errors or serializer mismatches as cache misses.
- Emit `redis_fallback_total` metrics broken down by failure category.
- Enforce concurrency/rate limits on fallbacks so a Redis outage does not crush the database.
- Enforce an overall API timeout.
- If the fallback also fails, preserve **both the Redis error and the source error** without logging payloads.

### 11.1. Preserving Both Causes When Fallback Also Fails

Example custom exception:

```java
package com.example.redis.errors;

public final class CacheFallbackException extends RuntimeException {

    public CacheFallbackException(
            Throwable sourceFailure,
            Throwable redisFailure) {

        super(
                "Both cache and authoritative source failed",
                sourceFailure
        );

        // Database error is the primary cause of the fallback failure.
        // Redis error is attached as suppressed for diagnostics.
        addSuppressed(redisFailure);
    }
}
```

Conceptual code:

```java
try {
    return readFromRedis();
} catch (RedisConnectionFailureException redisFailure) {
    try {
        return readFromDatabase();
    } catch (RuntimeException sourceFailure) {
        throw new CacheFallbackException(
                sourceFailure,
                redisFailure
        );
    }
}
```

Here `cause` holds the authoritative source error, while the Redis failure sits in `getSuppressed()`. Neither error is lost, and the wrapper message exposes no user data.

**Note:** logging `CacheFallbackException` as a full throwable also prints suppressed exceptions and their messages. Boundary safe-logging rules still apply.

### 11.2. Do Not Fall Back for Authoritative Redis Data Without a Backup Source

Some applications use Redis as the sole store for state (counters, locks, sessions, Stream pending entries). If Redis fails, you cannot invent records from a non-existent database.

Enable fallbacks only when a real backup source exists and consistency rules are clearly defined.

## 12. Reactor and ReactiveRedisTemplate: Preserving Cause via onErrorMap

Spring Data Redis Reactive uses `Mono` and `Flux`. Redis errors travel via `onError` signals.

### 12.1. Using onErrorMap with the Original Exception

Example:

```java
package com.example.redis.errors;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReactiveProfileCacheReader {

    private final ReactiveStringRedisTemplate redis;

    public ReactiveProfileCacheReader(
            ReactiveStringRedisTemplate redis) {
        this.redis = redis;
    }

    public Mono<String> read(long userId) {
        String key = "profile:cache:v3:" + userId;

        return redis.opsForValue()
                .get(key)
                .onErrorMap(
                        DataAccessException.class,
                        ex -> new CacheAccessException(
                                "profile_cache_read",
                                RedisFailureCategory.OTHER_REDIS_ERROR,
                                ex
                        )
                )
                .onErrorMap(
                        SerializationException.class,
                        ex -> new CacheAccessException(
                                "profile_cache_read",
                                RedisFailureCategory.SERIALIZATION,
                                ex
                        )
                );
    }
}
```

`onErrorMap` wraps the error **while keeping `ex` as `cause`**. In real applications, apply a type classifier for `DataAccessException` rather than mapping all of them to `OTHER_REDIS_ERROR`.

**Important distinctions:**

- `Mono.empty()` represents no data, not an error signal.
- `onErrorMap` does not trigger on `Mono.empty()`.
- `onErrorResume` substitutes another Publisher when an explicit fallback policy applies.
- `onErrorComplete` swallows errors; never use it casually to turn Redis outages into empty completions.

### 12.2. onErrorResume Can Mask Incidents Without Telemetry

Risky snippet:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(ex -> Mono.empty());
```

Every error turns into a miss, including broken serializers and access-control errors. Clients see no outage, and operations teams see no error metrics.

Better—restrict fallback by exception type:

```java
return redis.opsForValue()
        .get(key)
        .onErrorResume(
                RedisConnectionFailureException.class,
                ex -> {
                    // Emit safe fallback metric/log; do not log key.
                    return authoritativeSource.read(userId);
                }
        );
```

`authoritativeSource.read(userId)` is an application-provided Publisher that must enforce its own load limits and error policies.

This example requires importing `RedisConnectionFailureException` from Spring Data Redis and defining `authoritativeSource`. If an earlier layer already wrapped the Redis exception in `CacheAccessException`, apply fallback at the right **position in the chain** or match the wrapper rather than expecting the raw exception type.

### 12.3. Avoid Duplicate Logging in doOnError and the Boundary

A chain like:

```java
return redis.opsForValue()
        .get(key)
        .doOnError(ex -> log.error("Redis error", ex))
        .onErrorMap(ex -> new CacheAccessException(
                "profile_cache_read",
                RedisFailureCategory.OTHER_REDIS_ERROR,
                ex
        ));
```

logs a raw throwable at the service and logs again at the API boundary. Emit only safe metrics/telemetry in the service, leaving the single structured failure log to the boundary.

### 12.4. Reactor Context and Trace IDs

In WebFlux, execution hops across threads. Never assume `ThreadLocal` or MDC propagates across operators unless context propagation is explicitly configured.

For correlation:

- Use tracing (e.g., OpenTelemetry) or `Reactor Context` per your stack configuration.
- Avoid putting user tokens, Redis keys, or payloads in trace baggage.
- If accepting a request ID from a client HTTP header, validate format and max length; never treat arbitrary client strings as log-safe fields.
- Never embed trace/baggage values carrying secrets into exception messages.

## 13. Redis Streams, Pub/Sub, and Listeners: Errors Must Not Disappear Silently

Not all Redis operations happen inside HTTP requests.

### 13.1. Pub/Sub Listeners

A `MessageListener` receives raw byte payloads:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    try {
        process(message.getBody());
    } catch (RuntimeException ex) {
        // Record error safely; do not log raw body.
        recordSafeFailure(
                "pubsub_message_process",
                ex.getClass().getName()
        );
    }
}
```

**Never log `new String(message.getBody())`** when payloads can carry user data.

Standard Redis Pub/Sub has no replay or ACK. If a listener fails after receiving a message, logging and preserving the cause will not replay the message. For critical delivery, choose a durable delivery mechanism.

### 13.2. Redis Streams Consumer Groups

With Streams, entries stay pending until ACKed. When errors happen:

```text
XREADGROUP -> receive entry
        |
        v
Business processing
        |
      Error
        |
        v
Do not XACK
        |
        v
Retry/reclaim per policy
```

Logs should include:

```text
streamAlias=orders_events
consumerGroup=billing
failureCategory=DOWNSTREAM_TIMEOUT
deliveryAttempt=3
```

Be careful with `RecordId`, stream keys, and payloads. If stream IDs are safe in your system, they can serve as correlation IDs; if IDs link directly to sensitive data or guessable ranges, review policy. **Never log an entire Hash/`MapRecord`** merely because parsing failed.

### 13.3. Stream Payload Decoding Failures

When a consumer cannot decode an entry, apply a clear policy:

- Leave the entry pending for bounded retries if the failure is transient.
- If the payload is permanently invalid, move it to a dead-letter stream/queue before ACKing the original entry.
- Record safe event identifiers and error codes.
- Never copy raw payloads into unrestricted logs or unsecured dead-letter sinks.
- Apply the same sensitive-data protections to dead-letter storage as to the source stream.

Recording "deserialization failed" while keeping the cause helps operators distinguish schema mismatches from Redis timeouts—using **error type/category**, not by dumping the body.

## 14. Redis Pipelines, Transactions, and Lua: Failures Can Hold Sensitive Context

### 14.1. Pipeline

With `RedisTemplate.executePipelined(...)`, the app sends multiple commands and collects replies afterward. Errors can arise when reading replies or deserializing results.

Never log the entire list of commands/arguments when a batch fails:

```text
Batch 500 operations
Operation 237 failed
```

Instead record:

```text
operation=batch_profile_cache_fill
batchSize=500
failureCategory=SERIALIZATION
exceptionType=SerializationException
```

If a specific key must be identified, use an error ID and a restricted inspection tool in an authorized environment rather than pushing all keys and values to central logs.

### 14.2. MULTI/EXEC

In Redis transactions, distinguish:

- Commands not sent successfully.
- `EXEC` ran yet the application missed the response.
- Error decoding replies.
- `WATCH` conflict aborting execution.

A network failure after `EXEC` does not prove "no commands ran." **Preserve the cause chain** for analysis, while basing retries on idempotency and transaction semantics rather than exception names alone.

### 14.3. Lua Scripts

Lua scripts may accept arguments holding tokens, payloads, or sensitive keys. On script failure, raw error text may cite script names or command details.

Never log full script text and all `KEYS`/`ARGV` by default. Log:

```text
scriptAlias=atomic_cache_update_v2
failureCategory=OTHER_REDIS_ERROR
redisOperation=EVAL
```

Define `scriptAlias` statically in code. When inspecting script source, version-controlled source code is a better reference than production logs.

## 15. Retries: Preserve Causes and Avoid Creating New Business Bugs

A Redis timeout can occur **after Redis already executed the command** yet before the client receives the reply.

Example:

```text
Client                  Redis
   |                      |
   | INCR counter ------->|
   |                      | counter increments by 1
   |    [network timeout] |
   |                      |
   | Retry INCR --------->|
   |                      | counter increments again
```

If the application simply catches `QueryTimeoutException` and retries every command, `INCR` can execute twice.

### 15.1. Separating Reads and Writes

| Operation | Retry Risk After Timeout |
|---|---|
| `GET` | Usually safer on side effects; still adds load |
| `HGET` | Primarily read-only; needs timeout/rate limits |
| `SET` same value | May be value-idempotent; check TTL/concurrent writers |
| `INCR` | Can increment twice |
| `LPUSH` | Can insert duplicate elements |
| `XADD` | Can append duplicate entries |
| Lua script with writes | Depends on script logic |
| `XACK` | May have already ACKed before reply dropped; verify state |

**Preserving the error cause does not mean retrying is always right.** Classify command semantics and add operation IDs/idempotency where needed.

### 15.2. Bounded Retries

A practical retry policy:

- Retries only identified transient error categories.
- Caps attempt counts.
- Uses backoff/jitter to avoid retry storms.
- Enforces an overall request timeout.
- Stops retrying immediately on config/serializer/schema errors.
- Logs `attempt` and `failureCategory` instead of printing raw stack traces every attempt.
- Engages circuit breakers/bulkheads during full Redis outages.

If all retries fail, keep the technical cause inside the wrapper for internal handling. At the API boundary, never leak the raw underlying message in responses.

## 16. Log-Pipeline Redaction Does Not Replace Safety at the Source

Some systems configure filters in Logback, logging agents, or log collectors to mask secret strings. That provides defense in depth, yet fails if code logs entire Redis values.

Example payload:

```json
{
  "accessToken": "secret",
  "profile": {
    "phone": "...",
    "email": "..."
  }
}
```

A filter scanning for `"password="` misses `"accessToken"` and JSON PII fields. Data can slip through via:

- JSON escaping.
- Base64 encoding.
- Serializer exception messages.
- Nested fields.
- Concatenated prefixes.
- Log formats differing from test cases.

### 16.1. Prefer Allowlist Logging

Instead of:

```java
log.warn("Redis call failed: {}", requestObject);
```

use:

```java
log.warn(
        "Redis call failed operation={} category={}",
        "profile_cache_read",
        RedisFailureCategory.SERIALIZATION
);
```

An allowlist of permitted fields simplifies security reviews and retention compliance.

### 16.2. If Logging Partial Data Is Unavoidable

Define explicitly:

- Which diagnostic need requires that field?
- Does the field contain personal or secret data?
- Can an alias, bucket, or fingerprint substitute?
- Who has read access to the logs?
- How long are the logs retained?
- Are length limits and encoding sanitization applied?
- Is there a plan to remove or reduce verbosity after resolving the issue?

Never dump entire payloads just to save minutes debugging a rare error.

## 17. Protecting Metrics and Tracing from Sensitive Data

Omitting secrets from SLF4J is not enough if the same data flows into metrics or tracing.

### 17.1. Metric Labels Must Have Bounded Cardinality

Good:

```text
redis_operation_failures_total{
  operation="product_cache_read",
  category="TIMEOUT",
  component="catalog"
}
```

Bad:

```text
redis_operation_failures_total{
  key="user:lan@example.com:profile",
  exception_message="GET ...",
  request_id="per-request-uuid"
}
```

Labels like full Redis keys or request IDs leak sensitive data and trigger **cardinality explosions** that exhaust metric server RAM and storage.

### 17.2. Trace Spans

Record safe span attributes:

```text
db.system=redis
db.operation.name=GET
app.redis.operation=product_cache_read
error.type=TIMEOUT
```

Audit and control:

- Raw statements and command arguments.
- Full keys and values.
- Whether exception events automatically attach messages and stack traces.
- Connection URLs containing credentials.
- Trace baggage carrying personal data.

Some auto-instrumentation libraries attach exception messages/stack traces automatically. Ensure your safety policy covers **tracing exporters**, not only loggers.

### 17.3. Correlation IDs

Correlation IDs connect:

```text
HTTP request errorId
        |
        +--> redis operation metric
        |
        +--> database fallback span
        |
        +--> API response
```

Generate random internal IDs or use tracing-issued trace IDs. When accepting an ID from a client, validate its format and length before logging. Never use a user's access token as a correlation ID.

## 18. Observing Redis Incidents Without Logging Payloads

Combine application telemetry with Redis server metrics.

### 18.1. Useful Telemetry

| Metric | Question |
|---|---|
| Client connection failures | Is Redis losing connectivity? |
| Command timeouts | When did timeouts spike? |
| Retry attempts | Are retries amplifying load? |
| Operation latency p95/p99 | Do errors coincide with latency spikes? |
| Error category | Connection / timeout / serialization / command |
| Redis CPU / memory / network | Is the server overloaded? |
| Client pending commands | Are commands backing up in the driver? |
| Connection pool acquisition time | Is there pool contention? |
| Replica role/lag | Are topology or replication glitches occurring? |
| Schema/serializer version | Do errors correlate with a new rollout? |

Diagnostic Redis commands in authorized environments:

```redis
INFO stats
INFO commandstats
INFO memory
INFO clients
SLOWLOG GET 10
LATENCY LATEST
```

**Caution:** `SLOWLOG` can capture command names and arguments per Redis behavior; if values hold sensitive data, treat `SLOWLOG` output as sensitive too. Never ship raw slowlogs into low-restriction dashboards.

Never enable `MONITOR` casually in production: it adds severe performance overhead and exposes commands/arguments.

### 18.2. Separating Client Timeouts from Server Execution Time

An API can time out at 800 ms even when Redis executed the command in a few milliseconds:

```text
Client queue / pool wait
       |
Network send
       |
Redis execution
       |
Network receive
       |
Deserialize
```

`SLOWLOG` reflects primarily server-side command execution, excluding client wait stages. Measure both client-side latency and server-side metrics.

Do not log raw commands to diagnose queue latency when pending-command, pool-wait, and p99 metrics already tell the story.

## 19. A Cross-Layer Error-Handling Pattern

Clear division of responsibilities:

```text
Redis client / serializer
         |
         | throws original exception
         v
Repository / Redis adapter
         |
         | classify error type
         | wrap with safe context + original cause
         v
Business service
         |
         +-- If Redis is cache-only and error is permitted:
         |      bounded fallback + safe metrics
         |
         +-- If Redis is mandatory source:
         |      propagate
         v
ControllerAdvice / reactive global error handler
         |
         | log 1 safe event
         | no raw key/value/message/stack
         v
HTTP response
         |
         | generic code + errorId
         v
Client
```

This pattern balances:

- **Diagnosability:** cause chains remain intact across all layers.
- **Security:** logs emit only finite, permitted fields.
- **Operations:** metrics and error IDs pinpoint frequency and location.
- **Correctness:** misses stay distinct from errors; fallbacks and retries are conditional.
- **Reliability:** avoids log storms and hides nothing during Redis outages.

### 19.1. Division of Responsibilities

| Component | Should Do | Should Not Do |
|---|---|---|
| Redis adapter | Wrap cause, attach operation/category | Print full keys/values or swallow errors |
| Service | Decide fallback/retry per business rules | Blindly retry all writes |
| Global error handler | Standardize error codes, log safely once | Return `ex.getMessage()` to clients |
| Metrics | Count by finite error categories | Use key/userId/message as labels |
| Tracing | Link requests and dependencies | Emit raw Redis statements/secrets |
| Log collector | Retention, access control, extra redaction | Act as the sole protection mechanism |
| SRE / Operations | Investigate via metrics and secure channels | Leave `MONITOR`/raw command logs enabled indefinitely |

## 20. Common Design Mistakes

### Mistake 1: Dropping the Cause When Wrapping Exceptions

```java
throw new RuntimeException("Cache failed");
```

The real cause vanishes. Use a constructor accepting `cause`:

```java
throw new CacheAccessException(
        "cache_read",
        RedisFailureCategory.OTHER_REDIS_ERROR,
        ex
);
```

### Mistake 2: Concatenating the Original Message into the Wrapper

```java
throw new RuntimeException("Failed: " + ex.getMessage(), ex);
```

Even with `cause` intact, the wrapper message leaks Redis details. Keep wrapper messages safe.

### Mistake 3: Logging Full Keys and Values on Failure

Keys can carry tokens or user IDs; values can carry PII. Prefer fixed namespaces/operations.

### Mistake 4: Logging Full Throwables by Default

```java
log.error("Redis error", ex);
```

May print sensitive messages. Restrict to controlled sinks after auditing driver/serializer output.

### Mistake 5: Turning All Errors into Null

```java
catch (Exception ex) {
    return null;
}
```

Hides timeouts, auth failures, `WRONGTYPE`, and serializer mismatches. Keep cache misses distinct from failures.

### Mistake 6: Logging the Same Error at Every Layer

Produces duplicate lines and log storms, skewing incident counts. Pick one clean logging boundary.

### Mistake 7: Returning Exception Messages in APIs

Exposes Redis addresses, keys, or commands. Return safe error codes and correlation IDs.

### Mistake 8: Storing Secrets in Custom Exception Fields

Exceptions may be logged automatically elsewhere. Never include raw payloads, passwords, or tokens in a wrapper's `getMessage()`/`toString()`.

### Mistake 9: Using Exception Messages as Metric Labels

Causes unbounded cardinality and data leaks. Categorize with enums.

### Mistake 10: Treating Redis Timeouts as Unexecuted Commands

Write commands may have run before the reply dropped; non-idempotent retries risk duplicate mutations.

### Mistake 11: Falling Back on Serialization Errors

Schema failures needing investigation get hidden as cache misses. Fall back only on permitted error groups.

### Mistake 12: Logging Raw Pub/Sub or Stream Message Bodies

Payloads may carry PII or tokens. Log controlled event types and error codes.

### Mistake 13: Relying on Regex Redaction Alone

Data appears in nested JSON, escaped strings, binary, and cause chains. Minimize sensitive data at log creation time.

### Mistake 14: Overlooking Tracing Auto-Instrumentation

Trace exporters may capture exception messages or statements automatically. Enforce the same safety policy on tracing as on logging.

### Mistake 15: Trusting Arbitrary Client Request IDs in Logs

Oversized or malformed headers break log parsing or enable log injection. Validate format/length or use server-generated IDs.

### Mistake 16: Logging Full Redis Connection URIs

URIs can embed credentials. Log controlled roles/aliases rather than usernames/passwords.

### Mistake 17: Dumping Entire SLOWLOG/MONITOR Output

These outputs may capture command arguments. Restrict access and redact appropriately.

### Mistake 18: Not Recording Successful Fallbacks

The API returns 200 while Redis is down for hours. Emit fallback metrics and alerts, not only error logs on failed requests.

### Mistake 19: Relying Only on the Outer Exception Name Without Cause

Wrappers obscure lower-level causes. Keep cause chains and classify per library contracts.

### Mistake 20: Removing All Diagnostics to Prevent Leaks

You do not have to choose between "dump everything" and "log nothing." Operation, category, exception class, error ID, duration, and retry count give strong signals with minimal exposure.

## 21. Hands-On Exercises

### Exercise A: Preserving Cause

Create a root exception:

```java
RuntimeException original =
        new RuntimeException("secret-value-from-driver");
```

Wrap properly:

```java
CacheAccessException wrapped = new CacheAccessException(
        "product_cache_read",
        RedisFailureCategory.OTHER_REDIS_ERROR,
        original
);
```

Verify in a unit test or debugger:

```java
assertSame(original, wrapped.getCause());
```

Compare with `new RuntimeException("Redis error")` and observe that the link to `original` is lost.

**Takeaway:** keep wrapper messages safe and pass `cause` as a separate parameter.

### Exercise B: Sensitive Data in Logs

Suppose a Redis key holds a test session token:

```text
session:demo-secret-token-123
```

Compare two designs **in a test environment**:

```java
log.warn("Redis key {} failed", key);
```

versus:

```java
log.warn(
        "Redis failed operation={} category={}",
        "session_lookup",
        RedisFailureCategory.CONNECTION
);
```

Identify which line leaks the token and why. Never use real tokens.

### Exercise C: Distinguishing Miss from Error

Simulate three scenarios:

1. Redis returns `null` because the key is absent.
2. Redis throws `RedisConnectionFailureException`.
3. Serializer throws `SerializationException`.

Expected:

```text
Case 1 -> valid cache miss.
Case 2 -> connection failure, cause preserved.
Case 3 -> serialization failure, cause preserved.
```

Do not collapse all three into `Optional.empty()`.

### Exercise D: HTTP Error Response

Construct a `CacheAccessException` whose cause holds a fake secret message. Invoke the handler and verify:

- The HTTP response does not contain the cause's message.
- Logs contain only operation/category/exception type/error ID.
- `wrapped.getCause()` still points to the original exception.
- No raw keys/values appear in log output.

### Exercise E: Two-Source Fallback Failure

Simulate:

```text
Redis connection error
        |
        v
Database fallback error
```

Use `CacheFallbackException` with the database failure as `cause` and Redis failure as `suppressed`. Confirm both errors remain attached to the exception object while responses/logs emit only safe fields.

### Exercise F: Reactive Error Signal

Given a simulated `Mono.error(original)`, use `onErrorMap` to wrap with cause intact and verify subscribers receive `CacheAccessException`.

Compare with:

```java
.onErrorResume(ex -> Mono.empty())
```

and explain why the second hides Redis failures.

### Exercise G: Log Storms During Outage

Simulate a Redis outage failing 1,000 concurrent requests. Design:

- Metric counters recording every error by category.
- Log sampling/rate limiting so 1,000 full stack traces are not emitted.
- Alerting based on error rate and latency.
- An error ID per failed request for API correlation.
- Never logging full keys/values even when debug mode is enabled.

Note that log sampling **does not reduce metric counter accuracy** when metrics are incremented at the right layer.

## 22. Self-Check Questions

**1. Why is `throw new RuntimeException(ex.getMessage())` wrong when preserving causes?**

Because the new exception has no link to the original cause, and the original message may leak sensitive data.

**2. Is `log.error("Redis failed", ex)` always safe if you don't log keys directly?**

No. Exception messages and stack traces can carry sensitive details added by drivers or serializers.

**3. How should exceptions be wrapped to preserve cause?**

Use a constructor taking `Throwable cause`, e.g., `new CacheAccessException("cache_read", category, ex)`.

**4. Is `GET` returning `null` the same as a Redis timeout?**

No. `null` normally signals a missing key; a timeout is an error needing separate classification.

**5. Which fields are helpful to log without payloads?**

Allowlisted operation, error category, exception class, root-cause class, duration, retry attempt, and internal error ID.

**6. Why avoid raw keys in metric labels?**

Keys can contain sensitive data and each unique key creates distinct tag values, exploding cardinality.

**7. Should serializer errors automatically fall back like cache misses?**

Not by default. They may indicate schema bugs or incompatible data and require deliberate handling.

**8. Is retrying `INCR` after a timeout guaranteed safe?**

No. Redis may have incremented before the timeout, causing retries to increment twice.

**9. If a database fallback also fails, can both errors be preserved?**

Yes. Keep the primary fallback failure as `cause` and attach the Redis failure via `addSuppressed` or a structured error model, without dumping raw messages to logs.

**10. Why is collector-level regex redaction alone insufficient?**

Because data appears in varied encodings, nested JSON, and unexpected exception messages. Control data at the point logs are created.

**11. In WebFlux, does a `ThreadLocal` MDC always preserve trace IDs across operators?**

No. Use proper context propagation or `Reactor Context`, and keep secrets out of baggage.

**12. Can you log only an error ID and drop the cause?**

You shouldn't. Error IDs aid correlation, yet dropping the cause during wrapping blocks classification and deeper diagnosis.

**13. In Redis Streams, should a handler log the payload and `XACK` on error just to move on?**

No. Payloads can be sensitive; ACK only after completion or durable error handling (such as DLQ routing).

**14. If an API returns 200 via fallback, must Redis failures still be recorded?**

Yes. Emit safe metrics/logs so Redis degradation is detected even while the API remains up.

**15. Why are exception class and root-cause class still insufficient to blame the Redis server?**

Because timeouts or I/O errors can originate from networks, client queues, pools, or failovers; combine client and server telemetry.

## 23. Key Takeaways

- **Preserve root errors via `cause` or `suppressed`**, never by copying `ex.getMessage()` alone.
- **Never assume logging raw throwables is safe**: messages and stack traces can embed Redis keys, values, commands, URIs, or sensitive data.
- **Classify errors by type/category**, logging allowlisted operations, exception classes, root-cause classes, durations, and error IDs.
- **A cache miss is not a Redis error.** Never swallow timeouts or serialization exceptions into `null`/`Mono.empty()` without explicit policy.
- **Fall back only for eligible errors** under load limits; if the fallback also fails, preserve both causes without leaking secrets in responses.
- **Reactive `onErrorMap` must keep the original cause**; careless `onErrorResume`/`onErrorComplete` hides outages.
- **Retries and timeouts do not prove writes did not run**; evaluate idempotency for `INCR`, `XADD`, Lua, and other mutations.
- **Logs, metrics, and traces all need data controls.** Never put raw Redis keys or exception messages into metric labels or trace attributes.
- **Minimize data at the source, log once at the boundary**, and combine with metrics/sampling to prevent log storms.
- **HTTP responses should expose only safe error codes and error IDs**, never internal Redis details.

### References

- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- [Spring Data Redis — Scripting](https://docs.spring.io/spring-data/redis/reference/redis/scripting.html).
- [Spring Framework — DataAccessException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- [Spring Data Redis — RedisConnectionFailureException](https://docs.spring.io/spring-data/redis/reference/api/java/org/springframework/data/redis/RedisConnectionFailureException.html).
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html).
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
- [OWASP — Sensitive Data Exposure](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html#data-to-exclude).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
