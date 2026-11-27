# Distinguishing Missing Keys from Data Access Errors

When a Java application queries Redis via **Spring Data Redis**, two situations may look alike at the business layer yet carry completely different meanings:

1. **Missing key:** Redis processed a valid command and confirmed that at that moment no matching value exists. This is usually a **cache miss** or a normal lookup result.
2. **Data access error:** the application could not complete or could not trust the query result due to a lost connection, timeout, missing permissions, wrong Redis data type, serialization failure, or another error. This is a **failure**, not proof that the key does not exist.

Confusing the two cases can lead to severe consequences. For example, a login-session verification API catches a Redis error and returns `null` as if the session did not exist; an access-rate-limit service permits an operation because "no blocking record was found"; or a cache-aside service continuously slams the database while Redis is degraded.

The goal of this lesson is to build an **explicit result contract** for Redis operations, recognize how commands represent "no data," classify errors in Spring Data Redis, and make retry, fallback, or fail decisions based on data criticality.

## 1. Result Model: Hit, Miss, and Failure

A cache read operation does not have only two states: "has value" and "no value."

| Observed Result | Meaning | Common Handling Direction |
|---|---|---|
| **HIT** | Command succeeded and has a valid value | Return value to caller |
| **MISS** | Command succeeded, but key/field is absent per command semantics | Read source of truth or return not found per contract |
| **ACCESS ERROR** | Redis could not return a reliable result | Classify error, bounded retry or controlled fallback |
| **INVALID VALUE** | Redis returned bytes/value, but the application cannot decode or accept it | Treat as data/serialization error; do not assume key is missing |
| **UNKNOWN OUTCOME** | For commands with side effects, the client lost the response and does not know whether the command ran | Reconcile or use idempotency; do not blindly retry |

The first two cases are **normal business outcomes** of a valid read command. The latter cases are **failure or uncertainty conditions** requiring explicit policies.

Decision flow for a typical `GET` operation:

```text
               Application calls Redis GET
                         |
                         v
                 Command completed?
                    /          \
                  Yes          No / error
                  |                 |
                  v                 v
           Redis returned value?  ACCESS ERROR
              /      \              |
            Yes      Nil             v
             |        |       Retry/fallback/fail
             v        v       per business rules
          Decode     MISS
             |
       +-----+-----+
       |           |
     Valid     Decode/schema error
       |           |
       v           v
      HIT     INVALID VALUE
```

**Do not collapse ACCESS ERROR or INVALID VALUE into MISS just to return `Optional.empty()`.** Doing so prevents callers from distinguishing "data genuinely does not exist" from "the system is failing."

## 2. How Does Redis Report "Does Not Exist"?

Redis has multiple data structures and commands. There is no universal rule that "a missing key always returns `null`."

### 2.1. GET on a Non-Existent String Key

Example in Redis CLI:

```bash
redis-cli DEL demo:product:42
redis-cli GET demo:product:42
```

After deletion, `GET` returns a Redis **nil/null bulk reply** (CLI typically displays `(nil)`). With a normal `StringRedisTemplate.opsForValue().get(...)` call, this reply becomes Java `null`.

```java
String value = stringRedisTemplate.opsForValue()
        .get("demo:product:42");

if (value == null) {
    // Redis GET returned nil during a normal call.
    // This is a cache miss, not an exception.
}
```

The "normal call" condition is important: inside a Spring Data Redis pipeline or transaction, the return value at command-queueing time can be `null` because **no actual reply exists yet**, not because the key is missing. A later section separates that case.

### 2.2. An Empty String Is Still an Existing Value

```bash
redis-cli SET demo:empty ""
redis-cli GET demo:empty
redis-cli EXISTS demo:empty
```

The key `demo:empty` exists and its value is the empty string. In Java:

```java
String value = stringRedisTemplate.opsForValue().get("demo:empty");

if ("".equals(value)) {
    // Value exists but is empty.
}
```

**`""` is different from `null`.** Do not use `value == null || value.isBlank()` to conclude a key does not exist if an empty string is a valid domain value.

Similarly, the string `"null"` or a JSON literal `null` stored as string content is not Redis nil. It may deserialize to Java `null` at the application layer, which is a different issue from Redis reporting a missing key.

### 2.3. GET on a Key of the Wrong Type Returns an Error

Create a Set instead of a String:

```bash
redis-cli SADD demo:wrong-type member-1
redis-cli GET demo:wrong-type
```

`GET` on a Set key causes a **WRONGTYPE** error, not a cache miss. If an application catches all exceptions and returns `null`, it hides the fact that Redis holds the wrong data type or that two modules wrote to the same namespace.

In Spring Data Redis, this error is typically surfaced via an exception from the Redis driver / Spring exception translation. The exact exception class can vary by command, driver, and version; classify based on error semantics rather than hardcoding a single message string.

### 2.4. MGET Has a Notable Difference

For Redis `MGET`, each element in the result can be nil **when the key does not exist or does not hold a String value**. Thus, a `null` position in `MGET` does not strictly prove the key is absent; it can also mask a wrong-type key.

```bash
redis-cli SET demo:a A
redis-cli SADD demo:b set-member
redis-cli MGET demo:a demo:b demo:absent
```

This example can return a value for `demo:a` while returning nil for both `demo:b` (wrong type for String `MGET`) and `demo:absent` (non-existent).

**Rule:** understand the semantics of the **specific command** before interpreting `null`. Do not apply single-key `GET` assumptions to all multi-key operations.

## 3. HGET, Collections, EXISTS, and TTL Also Have Distinct Semantics

### 3.1. HGET: Missing Hash or Missing Field?

```bash
redis-cli DEL demo:user:1
redis-cli HGET demo:user:1 email

redis-cli HSET demo:user:1 name "An"
redis-cli HGET demo:user:1 email
```

Both `HGET` calls can return nil:

- First call: **the hash key does not exist**.
- Second call: the hash exists, but **field `email` does not exist**.

If business logic needs to distinguish the two cases, design a separate check or appropriate data representation. `HGET` alone does not provide two different return codes for "missing hash" versus "missing field."

With Spring Data Redis:

```java
Object email = redisTemplate.opsForHash()
        .get("demo:user:1", "email");

// In a normal read context, null can mean either
// hash or field is absent. Do not assume the entire hash is missing.
```

Remember that serializers for hash keys and hash values may differ from the String value serializer. Valid bytes in Redis that fail to decode also produce a non-MISS error.

### 3.2. Empty Collections Are Not Exceptions

Several commands on missing keys return empty collections or zero per Redis rules:

| Command | Typical Result When Key Does Not Exist | Notes |
|---|---|---|
| `GET key` | nil | Wrong key type causes WRONGTYPE |
| `HGET key field` | nil | Does not distinguish missing hash from missing field |
| `EXISTS key` | 0 | Reflects only the moment of execution |
| `TTL key` | -2 | -1 means key exists with no expiry |
| `PTTL key` | -2 | Same as TTL but in milliseconds |
| `SCARD key` | 0 | Does not distinguish empty Set in domain terms |
| `SMEMBERS key` | empty set | An empty collection can be a successful result |
| `LLEN key` | 0 | Missing list or zero elements |
| `LRANGE key 0 -1` | empty list | Do not treat empty list as "Redis error" |
| `MGET key1 key2 ...` | nil at corresponding position | Nil can also mean non-String key |

Spring Data Redis example:

```java
Long size = stringRedisTemplate.opsForSet()
        .size("demo:missing-set");

if (Long.valueOf(0L).equals(size)) {
    // This is a valid zero count in a normal call.
}
```

Do not write a generic API rule saying "if the collection is empty, throw `RedisUnavailableException`." A missing Set in Redis can also be a normal business state.

### 3.3. TTL Helps Diagnose, Not Authenticate

```bash
redis-cli TTL demo:product:42
```

Redis uses typical values:

- **`-2`**: key does not exist at the time `TTL` runs.
- **`-1`**: key exists without an expiration.
- **`0` or positive number**: remaining time in seconds; milliseconds for `PTTL`.

So:

```text
GET key => nil
TTL key => -2
```

is a strong indication that the key was absent at both observation points. However, the two commands are **not atomic together**; a key can be added or expire between the two calls.

Do not use `TTL` as a source of truth for authentication state or inventory, and do not treat `TTL=-1` as a Redis connection error. It is a valid result: the key exists with no expiry.

## 4. Distinguishing Missing Keys from Errors with Redis CLI

On a test Redis instance, you can try:

```bash
# 1. Non-existent key
redis-cli DEL lesson:missing
redis-cli GET lesson:missing

# 2. Existing key containing a String
redis-cli SET lesson:value "READY"
redis-cli GET lesson:value

# 3. Existing key with wrong type
redis-cli SADD lesson:set member
redis-cli GET lesson:set

# 4. Check existence and TTL
redis-cli EXISTS lesson:value
redis-cli TTL lesson:value
redis-cli EXISTS lesson:missing
redis-cli TTL lesson:missing
```

Interpretation:

- `GET lesson:missing`: Redis succeeded and returned nil.
- `GET lesson:value`: Redis succeeded and returned the string `READY`.
- `GET lesson:set`: Redis returned a WRONGTYPE error.
- `EXISTS lesson:missing`: Redis returned `0`.
- `TTL lesson:missing`: Redis returned `-2`.
- `TTL lesson:value`: Redis returned `-1` if no `EXPIRE` was set.

When testing connection failures, **never break a shared Redis instance**. Test in an isolated environment—for example using an invalid endpoint or a test Redis stopped in a controlled way—and observe the client exception. A "connection refused/timeout" outcome must not be conflated with a nil reply returned by Redis.

## 5. Spring Data Redis: Does a Normal API Return Null or Throw an Exception?

A simple synchronous call:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class StatusCacheReader {

    private final StringRedisTemplate redis;

    public StatusCacheReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String readStatus(String orderId) {
        return redis.opsForValue()
                .get("cache:order:v1:" + orderId);
    }
}
```

In the context of a normal `GET` command:

1. If Redis returns a valid String value, the service returns the String.
2. If Redis confirms the key is absent, the service returns `null`.
3. If Redis is unreachable or rejects the command, the operation normally **throws an exception** rather than returning `null` as a substitute.
4. If the data cannot be deserialized cleanly by the configured serializer, the operation may fail with a serialization-related exception.

Spring Data Redis uses the Spring Data Access exception hierarchy, notably `org.springframework.dao.DataAccessException` and subtypes/exceptions translated from the driver. Connection failures, timeouts, rejected commands, type mismatches, and system errors should not be treated as the same thing as a business `MISS`.

### 5.1. Catching Access Errors at the Right Scope

```java
import org.springframework.dao.DataAccessException;

public String readStatusOrThrow(String orderId) {
    String key = "cache:order:v1:" + orderId;

    try {
        String value = redis.opsForValue().get(key);

        if (value == null) {
            // Miss confirmed by Redis in a normal GET call.
            return null;
        }

        return value;
    } catch (DataAccessException error) {
        // Do not convert exceptions into null.
        throw new CacheReadUnavailableException(
                "Cannot read order status cache", error);
    }
}
```

Illustrative custom exception:

```java
public class CacheReadUnavailableException extends RuntimeException {
    public CacheReadUnavailableException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

Note: some serialization or mapping errors may **not belong to every subtype of `DataAccessException`** across all versions/serializers. Handle those errors at the appropriate decoding boundary rather than using `catch (Exception) { return null; }` to lump everything into a miss.

### 5.2. Why Is Catch-All Returning Null Wrong?

Dangerous pattern:

```java
public String readStatusWrong(String orderId) {
    try {
        return redis.opsForValue().get("cache:order:" + orderId);
    } catch (Exception ignored) {
        return null; // Wrong: Redis outage is disguised as a missing key.
    }
}
```

The caller cannot know why `null` was returned:

- Key was never created.
- Key just expired via TTL.
- Redis lost connectivity.
- Command timed out.
- ACL denied access.
- Key has the wrong type or serializer cannot decode it.

The consequence can be an API falsely returning `404`, creating duplicate records, or bypassing a security check previously managed by Redis.

**No access exception is ever proof that a key does not exist simply because the error message contains the word `null` or `not found`.** Rely on the command contract and failure type.

## 6. An Explicit Result Contract: Hit, Miss, Error

In many applications, a repository method only needs to express **value present or value absent**, while errors propagate via exceptions. This approach is simple and often appropriate.

```java
import java.util.Optional;

public Optional<String> findCachedStatus(String orderId) {
    String key = "cache:order:v1:" + orderId;
    String result = redis.opsForValue().get(key);

    // Return Optional.empty only when GET completes and returns Redis nil.
    return Optional.ofNullable(result);
}
```

Contract:

- `Optional.of(value)`: Redis `GET` succeeded and returned a value.
- `Optional.empty()`: Redis `GET` succeeded and the key was absent.
- Exception: Redis/driver/serialization failed to provide a valid read result.

In a system needing auditing or multiple explicit failure modes, you can define an explicit result model:

```java
public enum CacheLookupStatus {
    HIT,
    MISS
}

public record CacheLookup<T>(
        CacheLookupStatus status,
        T value) {

    public static <T> CacheLookup<T> hit(T value) {
        if (value == null) {
            throw new IllegalArgumentException("Hit value cannot be null");
        }
        return new CacheLookup<>(CacheLookupStatus.HIT, value);
    }

    public static <T> CacheLookup<T> miss() {
        return new CacheLookup<>(CacheLookupStatus.MISS, null);
    }
}
```

Service:

```java
public CacheLookup<String> lookup(String orderId) {
    String key = "cache:order:v1:" + orderId;
    String value = redis.opsForValue().get(key);

    if (value == null) {
        return CacheLookup.miss();
    }

    return CacheLookup.hit(value);
}
```

**Access errors are still thrown**, not turned into `MISS`. If the API needs to return errors as a field on the result model, add a `FAILURE` status with a structured cause, never `MISS` for exceptions.

At the HTTP boundary, a Redis cache miss does not automatically mean returning `404`. **Cache MISS** merely means consulting the source database, not "the business resource does not exist."

## 7. Cache Miss and Business Not Found Are Different

Suppose the database stores products and Redis is only a cache.

```text
HTTP GET /products/p-100
          |
          v
Redis cache lookup
     +----+----+
     |         |
    HIT       MISS
     |         |
     v         v
Return DTO   Read database
                |
         +------+------+
         |             |
       Found       Not found
         |             |
         v             v
   Repopulate     Return 404 per
   cache & 200    API rules
```

If Redis is unavailable, the read path may have a **fail-open to database** policy for non-critical caches. However, this is a third branch—**ERROR**—not `MISS`:

```text
Redis ERROR
     |
     v
Log/metric cache access failure
     |
     v
Choose bounded source fallback or return 503
     |
     v
Do not claim "key does not exist"
```

If the database finds the product during the Redis error branch, the application can still return a valid result. Yet metrics must record **Redis unavailable**, not a normal cache miss.

### 7.1. Cache-Aside Service Pattern Distinguishing Errors

```java
import java.time.Duration;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
            LoggerFactory.getLogger(ProductReadService.class);

    private final StringRedisTemplate redis;
    private final ProductSource source;

    public ProductReadService(
            StringRedisTemplate redis, ProductSource source) {
        this.redis = redis;
        this.source = source;
    }

    public Optional<String> findProductJson(String id) {
        String key = "cache:product:v1:" + id;

        final String cached;
        try {
            cached = redis.opsForValue().get(key);
        } catch (DataAccessException error) {
            // Redis cache failed: falling back is a deliberate policy choice.
            log.warn("Redis cache read unavailable for product key", error);
            return source.findProductJson(id);
        }

        if (cached != null) {
            return Optional.of(cached);
        }

        // Redis confirmed a cache miss.
        Optional<String> fromSource = source.findProductJson(id);

        fromSource.ifPresent(json -> {
            try {
                redis.opsForValue().set(
                        key, json, Duration.ofMinutes(5));
            } catch (DataAccessException error) {
                // Separate policy for cache write: source was already read,
                // we can still return data if cache is purely an optimization.
                log.warn("Cannot populate product cache", error);
            }
        });

        return fromSource;
    }
}
```

Source data interface:

```java
import java.util.Optional;

public interface ProductSource {
    Optional<String> findProductJson(String id);
}
```

In this example:

- Cache hit returns the cached JSON immediately.
- Cache miss queries the database; the database decides "product not found."
- Redis read failure is **logged separately**, then fails open to the source per the illustrative policy.
- Redis write failure after reading the source does not have to fail the API because the cache is only an optimization.
- If the source also fails, do not silently turn a source failure into `Optional.empty()`.
- The cached JSON is assumed to be well-formed and schema-valid; add validation/deserialization if the application processes DTOs instead of returning raw Strings.

For high-traffic systems, during a Redis outage thousands of concurrent requests can fall back to the database simultaneously. Therefore, fail-open must be paired with **bulkheads, rate limits, circuit breakers, bounded retries, and source protection**; otherwise a Redis outage can cascade into a database outage.

## 8. When Must You Not Fail Open?

Not all Redis data is easily regenerable cache. Redis can store sessions, rate-limit counters, locks, nonces, anti-replay tokens, or short-lived business state.

| Data Stored in Redis | Redis Reports Key Missing | Redis Access Error |
|---|---|---|
| Product cache backed by database | Re-read source | Can fall back to source with limits |
| Login session | Invalid session or require re-authentication per policy | Do not grant access merely because lookup failed |
| Rate limit protecting sensitive endpoints | Apply appropriate counter initialization policy | Choose fail-closed or an alternative defense per threat model |
| Nonce / anti-replay token | Unused or expired per contract | Do not assume the request has never used the nonce |
| Distributed lock | Missing lock may permit acquisition attempt | Access error does not mean the lock is free |
| Inventory/reservation limits | Handle missing data per business invariants | Do not treat missing reply as sufficient stock |
| Idempotency key | No processing marker; may start operation per protocol | Do not retry side effects when outcome is uncertain |

A Redis error must never weaken an authentication boundary. For example, if a session cannot be read due to a connection timeout, you cannot infer that the request does not need login; for protected endpoints, the application normally must return an error or enforce authentication safely.

**Fail-open versus fail-closed is a decision driven by data semantics and threat model**, not a default feature for every `DataAccessException`.

## 9. Reactive Redis: Mono.empty() Differs from Mono.error()

In reactive Spring Data Redis, methods return `Mono<T>` or `Flux<T>` instead of synchronous values.

For an operation such as:

```java
Mono<String> result = reactiveRedisTemplate.opsForValue()
        .get("cache:product:v1:p-100");
```

In a normal call:

- **Value present:** the publisher emits `onNext(value)` then `onComplete`.
- **Key missing:** the publisher may terminate with `onComplete` without emitting a value—that is, `Mono.empty()`.
- **Redis failure:** the publisher emits `onError(error)`.

Reactor signal diagram:

```text
GET hit:
    onNext("READY") -> onComplete

GET miss:
    onComplete             (no onNext)

GET access error:
    onError(exception)     (no normal onComplete)
```

Thus, `Mono.empty()` from a normal reactive `GET` is the appropriate representation for a miss. As with synchronous APIs, check the exact contract of the command and serializer. Do not assume every `Flux.empty()` always equals a missing key: for collection commands, empty may be a valid empty-collection result.

### 9.1. switchIfEmpty Handles Only Empty Completions

```java
import reactor.core.publisher.Mono;

public Mono<String> findStatus(String id) {
    String key = "cache:order:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.defer(
                    () -> statusSource.loadFromDatabase(id)));
}
```

`statusSource.loadFromDatabase(id)` is a hypothetical reactive method returning `Mono<String>`; when the source has no record, it may return `Mono.empty()`.

Key points:

- `switchIfEmpty(...)` runs the fallback when Redis `GET` completes **with no value**.
- If Redis `GET` emits `onError`, `switchIfEmpty` **does not swallow the error**.
- `Mono.defer(...)` ensures the fallback publisher is created only when the miss branch actually happens.
- If you want to fall back when Redis errors, handle it in a separate error branch rather than expecting `switchIfEmpty` to catch it.

### 9.2. Wrong Approach: Turning Redis Errors into Empty

```java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .onErrorResume(error -> Mono.empty())
        .switchIfEmpty(statusSource.loadFromDatabase(id));
```

The code above collapses every exception (including programming/serializer bugs) into an empty result. Callers cannot tell misses from outages, hit/miss metrics are skewed, and the source path can be flooded.

Worse, if there is no `switchIfEmpty` source path, the API could report that a resource does not exist simply because Redis timed out.

### 9.3. If Intentionally Failing Open, Observe and Bound It

```java
import org.springframework.dao.DataAccessException;

public Mono<String> readStatusWithFallback(String id) {
    String key = "cache:order:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .switchIfEmpty(Mono.defer(
                    () -> statusSource.loadFromDatabase(id)))
            .onErrorResume(
                    DataAccessException.class,
                    error -> {
                        log.warn("Redis/source data access error", error);
                        return statusSource.loadFromDatabase(id);
                    });
}
```

This snippet is only for **illustrating operator structure**. Putting `onErrorResume` **after** `switchIfEmpty` can also catch `DataAccessException` from the database source, which could invoke the source twice. To fall back only on Redis errors, attach the error handler **directly on the Redis publisher before chaining the miss branch**, and separate metrics/operations:

```java
public Mono<String> readStatusSafely(String id) {
    String key = "cache:order:v1:" + id;

    Mono<String> cacheLookup = reactiveRedisTemplate
            .opsForValue()
            .get(key)
            .onErrorResume(
                    DataAccessException.class,
                    redisError -> {
                        log.warn("Redis read failure", redisError);
                        return Mono.empty();
                    });

    // Choose converting error to empty here ONLY when
    // business logic ALLOWS fail-open and separate metrics are recorded.
    return cacheLookup.switchIfEmpty(
            Mono.defer(() -> statusSource.loadFromDatabase(id)));
}
```

In production code, preserve the fallback reason via metrics/tracing or an explicit status result rather than letting downstream assume every empty signal was a miss. If downstream cannot distinguish a Redis failure from missing data at a critical decision point, use an explicit wrapper or let the error propagate.

### 9.4. Do Not Use defaultIfEmpty to Mask Errors

```java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .defaultIfEmpty("UNKNOWN");
```

`defaultIfEmpty` turns a **MISS** into a default value, while leaving `onError` unhandled. This may be fine if `UNKNOWN` is genuinely a domain default, yet dangerous if it causes an authorization layer to treat an "unknown" state as "allowed."

An empty string `Mono.just("")` is still an emitted value, distinct from `Mono.empty()`. A reactive flow has three separate states: value, empty completion, and error.

## 10. Java Optional, Null, and Exceptions: Which Contract to Choose?

For a service reading an object, a reasonable signature is:

```java
public Optional<ProductView> findById(String id);
```

If this is a **business repository**, `Optional.empty()` may mean the database was queried and no product exists. With a **cache repository**, however, `Optional.empty()` only means no entry was in the cache.

Identical signatures do not imply identical semantics. Name methods explicitly:

```java
Optional<ProductView> findInCache(String id);
Optional<ProductView> findInDatabase(String id);
```

Then the service composes them:

```java
public Optional<ProductView> findProduct(String id) {
    Optional<ProductView> cached = cache.findInCache(id);

    if (cached.isPresent()) {
        return cached;
    }

    return database.findInDatabase(id);
}
```

With this code, cache failures propagate as exceptions unless the cache method catches/falls back. The fail-open decision can be made in a dedicated layer aware of Redis outage risks.

If using a dedicated status result type, you can distinguish:

```text
CacheLookup.Hit(value)
CacheLookup.Miss
CacheLookup.Failure(cause)
```

Never use a single `Optional.empty()` to represent misses, network failures, and deserialization failures alike. Doing so forces every caller to guess what happened.

## 11. Serialization Errors Are Not Missing Keys

Spring Data Redis can serialize keys/values with String, JSON, JDK serialization, or custom codecs. Redis stores bytes; Spring Data Redis converts bytes back into Java objects.

```text
Redis GET key
      |
      v
Returns actual byte[]
      |
      v
RedisSerializer.deserialize(bytes)
      |
   +--+----------------------+
   |                         |
Decode succeeds          Decode fails
   |                         |
   v                         v
Valid value           Serialization/Schema error
```

Example:

- App v1 stored JSON with `price` as a string.
- App v2 expects `price` to be an incompatible object.
- Redis still returns bytes; the key still exists.
- Jackson/serializer cannot instantiate the corresponding `ProductView`.

If the application catches the exception and returns `Optional.empty()`, it loses track of a **data compatibility error**.

### 11.1. Classification Example When Manually Decoding JSON

```java
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

public ProductView decodeProduct(
        String redisJson, ObjectMapper mapper) {

    try {
        ProductView value =
                mapper.readValue(redisJson, ProductView.class);

        if (value == null) {
            throw new CachePayloadException(
                    "Cached product payload decoded to null");
        }

        return value;
    } catch (JsonProcessingException error) {
        throw new CachePayloadException(
                "Invalid cached product JSON", error);
    }
}
```

Custom exception:

```java
public class CachePayloadException extends RuntimeException {

    public CachePayloadException(String message) {
        super(message);
    }

    public CachePayloadException(
            String message, Throwable cause) {
        super(message, cause);
    }
}
```

When Redis returns the JSON string `"null"` as a payload, Jackson may decode it to Java `null`. That is **not a Redis GET nil**; here the code treats that value as violating the cache contract and throws a payload exception.

In a cache-aside application, an invalid payload can be a reason to **invalidate and reload data** when a reliable source of truth exists. However, record metrics, bound retries, and watch out for races: delete the key only with an appropriate mechanism when multiple writers update the cache, avoiding deleting a newer entry written by someone else after you read.

### 11.2. Different Key Serializers Cause "False Misses"

If one service uses `StringRedisTemplate` while another uses `RedisTemplate` with the default JDK/other key serializer, the two services may read **two different physical key names** even when passing the same Java String.

```text
Java key: "product:100"

String serializer:
  Redis key bytes = UTF-8("product:100")

Other serializer:
  Redis key bytes = different byte sequence
```

Then `GET` can return nil completely legitimately because **the physical key queried by one service is not the key written by the other**. To Redis, it is a true miss; to the system, the cause is a misconfigured namespace/serializer.

Inspect the serializers for key, value, hash key, hash value, and schema version. Do not assume "Redis lost data" when one application just changed its serializer or prefix.

## 12. Spring Cache: Absent Entry vs. Entry Containing Null

The Spring Cache abstraction can store a **null value represented via an internal sentinel**, depending on the provider and configuration. Hence, `null` at the Spring Cache layer does not map identically to raw Redis `GET`.

Example using `CacheManager`:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

public void inspectCache(CacheManager cacheManager) {
    Cache cache = cacheManager.getCache("productById");

    if (cache == null) {
        // Cache name does not exist or was not created,
        // depending on CacheManager configuration.
        return;
    }

    Cache.ValueWrapper wrapper = cache.get("p-100");

    if (wrapper == null) {
        // No entry per Cache.get(key) contract.
    } else {
        Object cached = wrapper.get();

        if (cached == null) {
            // There is a cached null entry, if the provider supports it.
        } else {
            // Entry exists with a value.
        }
    }
}
```

Three cases to separate:

1. `cacheManager.getCache(name) == null`: the cache name does not exist or was not created per configuration.
2. `cache.get(key) == null`: there is no entry in the cache.
3. `cache.get(key) != null` yet `wrapper.get() == null`: the cache provider is representing a cached null value.

A Redis connection failure during `cache.get(...)` is still a **failure**, not case 2.

### 12.1. @Cacheable with Null Values

```java
@Cacheable(
        cacheNames = "productById",
        key = "#p0",
        unless = "#result == null")
public ProductView findById(String id) {
    return database.findProductOrNull(id);
}
```

`unless = "#result == null"` prevents caching null results at the method level. On `RedisCacheManager`, you can also configure:

```java
RedisCacheConfiguration defaults =
        RedisCacheConfiguration.defaultCacheConfig()
                .disableCachingNullValues();
```

**Not caching nulls** fits when new data can appear quickly and you do not want to keep returning "absent" right after the database inserts a record. Conversely, if non-existent IDs are queried repeatedly, **negative caching** with a short TTL can help. The choice depends on the workload.

If the provider remains configured to cache nulls, understand that a cached-null entry can prevent the `@Cacheable` method from **running again** during the TTL. Do not confuse "method returned null from cache" with "Redis is disconnected."

### 12.2. CacheErrorHandler: Error Handling Does Not Mean Turning All Errors into Misses

Spring Cache lets you configure a `CacheErrorHandler` to govern get/put/evict/clear failures at the cache abstraction layer. Consider carefully:

- Ignoring **GET** errors lets the underlying method run again; suitable for pure optimization caches when the source is protected.
- Ignoring **PUT** errors lets the request return source data even if the cache was not populated.
- Ignoring **EVICT** errors after a database mutation can leave stale cached data served until TTL expiration.
- For caches holding permissions, sessions, or security conditions, ignoring errors can be unsafe.
- Emit separate metrics and logs for cache failures; do not count them as normal cache misses.

A broad error handler that swallows every exception hides serializer, configuration, and invalidation bugs. Do not enable it by default merely so the application "doesn't crash when Redis fails."

## 13. Negative Caching: Representing "Does Not Exist" as TTL-Bound Data

When the database confirms a record does not exist, the application can cache a **negative result** briefly to avoid querying the source repeatedly for the same ID.

Instead of relying on Redis nil, store an explicit object/sentinel:

```json
{
  "found": false,
  "checkedAtEpochMs": 1780000000000
}
```

Or:

```text
cache:product:v1:p-404 -> "NOT_FOUND" (TTL 15 seconds)
```

Crucially: `NOT_FOUND` is **an actual existing Redis value**. When `GET` returns `"NOT_FOUND"`, that is a cache HIT representing **business not found**, not a Redis miss.

Classification:

| Redis Response | Cache Interpretation | Business Interpretation |
|---|---|---|
| nil | MISS | Unknown whether the product exists |
| Valid product JSON | HIT-positive | Product exists |
| Sentinel `NOT_FOUND` | HIT-negative | Source previously confirmed absence |
| Exception | ERROR | Data status unknown |
| Invalid payload | INVALID VALUE | Cached entry cannot be trusted |

Constraints:

- Negative TTL should be short if entities can be created.
- When creating a new entity, delete or overwrite the negative entry.
- Never store a timeout, Redis error, or database error as a negative value.
- The sentinel must never collide with a valid domain value.
- For multi-tenant apps, keys must include the tenant ID if existence varies by tenant.
- If user-supplied IDs are unbounded, cap negative caching to prevent millions of junk keys.

**Never "write a NOT_FOUND sentinel when Redis times out"**: a timeout does not prove the authoritative data does not exist.

## 14. Does EXISTS + GET Eliminate Ambiguity?

You might think simply running:

```java
Boolean exists = stringRedisTemplate.hasKey(key);
String value = stringRedisTemplate.opsForValue().get(key);
```

distinguishes every case. However, the two commands are not atomic together.

```text
Request A                            Request B
    |                                    |
    +-- EXISTS key -> true               |
    |                               DEL key
    +-- GET key -> nil                   |
```

Or the reverse:

```text
Request A                            Request B
    |                                    |
    +-- EXISTS key -> false              |
    |                               SET key value
    +-- GET key -> value                 |
```

Thus, `EXISTS` is useful for point-in-time diagnostics but does not guarantee the state stays unchanged by the next `GET`. If you simply need to read a String value, **a single `GET` command is usually enough** to separate hit from miss under the contract.

### 14.1. When Conditional Consistency Is Required

If business rules require "create only if missing, and only one request may create it," do not write:

```text
EXISTS key
if false:
    SET key value
```

because of races. Use an appropriate Redis command like `SET key value NX` with a TTL if needed, or a Lua script to check-and-write server-side inside an atomic boundary.

Example:

```bash
redis-cli SET lock:order:42 unique-token NX PX 10000
```

This operation enforces one specific invariant (create the lock only if absent). It does not solve general transactional needs and does not make other multi-key reads/writes atomic.

### 14.2. Pipelines and Transactions Are Key Exceptions for Null

In Spring Data Redis's synchronous API, when executing inside a **Redis pipeline or transaction**, many operations return `null` at the moment Java invokes them because results have not been returned yet. Actual pipeline command results are collected after the pipeline finishes.

```text
Inside pipeline callback:
    GET key -> Java may see null right when queueing the command
    (no reply yet to conclude the key is missing)

After executePipelined:
    Result list contains the converted replies.
```

Therefore, do not write:

```java
// Wrong pseudocode if queueing commands inside a pipeline:
String result = operations.opsForValue().get(key);
if (result == null) {
    createMissingRecord();
}
```

because `null` at queue time does not mean Redis returned nil after execution. Similarly, commands queued inside `MULTI` must be evaluated via `EXEC`, not via temporary return values at queueing time.

**Before interpreting null from Spring Data Redis, know whether you are in normal execution, a pipeline, or a transaction.**

## 15. Which Errors Should Be Retried and Which Should Not?

Not all Redis access errors share the same handling plan.

| Error Type | Can Retry? | Notes |
|---|---|---|
| Timeout/connection failure on **idempotent GET** | Short retry with backoff possible | Excessive retries increase load and latency |
| Redis unavailable on cache-aside read | Database fallback possible | Must protect database from traffic storms |
| `WRONGTYPE` | Do not blindly retry | Fix schema, namespace, or data |
| ACL / `NOAUTH` / `NOPERM` | Do not retry as a network glitch | Fix configuration/permissions |
| Key/slot routing error in Redis Cluster | Driver may handle redirects | Do not treat all cross-slot errors as transient |
| Serialization/schema error | Do not blindly retry network | Check serializer/migration/payload |
| Missing key from `GET` | Not an error to retry | Cache miss or negative cache per policy |
| Timeout after `INCR` / side-effect write | Do not unconditionally retry | Outcome may have already succeeded |
| Redis replica read returns stale value | Retrying is not always enough | Consistency / read preference / version |
| Eviction/invalidation failure | May need compensation/reconcile | Avoid serving stale cache indefinitely |

### 15.1. Retry GET Only Within Budget

A pure `GET` is idempotent with respect to reads. It can be retried on transient failures, while respecting the overall API time budget:

```text
HTTP deadline:          800 ms
Redis GET timeout:      150 ms
Retry backoff:           50 ms
Database fallback:      400 ms
Response processing:     remaining budget
```

Numbers are illustrative. If Redis is in a total outage, retrying three times per request can cause connection storms and inflate latency; in that situation a circuit breaker / bounded fallback is usually more effective.

### 15.2. For Write Operations, Timeouts Can Yield Ambiguous Outcomes

```text
Client: INCR rate:login:failed
        |
        v
Redis executes INCR successfully
        |
        v
Connection drops before reply
        |
        v
Client receives timeout
```

If the client retries `INCR` as if the first command never ran, the counter increments twice. Thus, the lesson "distinguish missing from failure" also applies to **mutations**: an access error does not prove Redis remained unchanged.

Design operation IDs/idempotency, Lua scripts checking for duplicates, or reconciliation mechanisms when at-most-once business effects are required.

## 16. Redis Cluster and Replica Reads Complicate Diagnosis

In Redis Cluster:

- Keys have hash slots and primary owners.
- `MOVED`/`ASK` redirects can appear during topology changes.
- Multi-key commands have slot constraints.
- Losing connectivity to one node does not mean the whole Cluster lacks data.
- Reading from a replica can return stale state compared to the primary.

Example:

```text
T0: Primary A receives SET key=value.
T1: Replica A has not replicated yet.
T2: Client routes GET key to replica A.
T3: Replica A returns nil.
```

At `T3`, the nil reply is a valid read result **from that replica at that moment**, yet it does not prove the key is absent on the primary or in the authoritative data source. Hence, "Redis confirmed the key does not exist" must always be qualified by **the node/consistency policy used to read**.

If an application relies on Redis for sessions, distributed locks, or data needing read-your-writes, select the appropriate read target. Do not enable replica reads for critical security decisions without verifying consistency guarantees.

### 16.1. Distinguishing Cache Miss from Wrong Namespace

One service might use:

```text
Service A: cache:product:v1:p-100
Service B: cache:product:v2:p-100
```

Service B receives nil while Service A still has data. This is not a network bug; they are two distinct keys. Likewise, Redis Cluster hash tags, tenant prefixes, environment prefixes, and serializers all affect the physical key.

To investigate, record **namespaces and non-sensitive identifiers** rather than logging real session IDs/tokens. In production, avoid `KEYS *` to hunt for keys; inspect specific test keys or use bounded `SCAN` per topology.

## 17. Spring Session and Login Sessions: Never Treat Redis Errors as Expired Sessions

An application using Spring Session Data Redis stores login state in Redis. When a request carries a session cookie, the framework looks up the session by ID.

Separate:

1. Session ID does not exist or genuinely expired: the application can prompt for re-login.
2. Redis connection failure: the application has not determined whether the session is still valid.
3. Session payload fails deserialization: likely a version/migration bug, not a deleted session.
4. Replica lag: a node may not yet reflect session updates/revocations.

For protected endpoints, **never grant access merely because Redis is unavailable**. A system can fail closed or use a carefully designed backup authentication mechanism, but never turn a Redis timeout into "guest allowed everywhere."

In the UI, display a temporary outage message distinct from a re-login prompt. Clear classification tells operators whether users were genuinely logged out or session infrastructure is failing.

## 18. Observing Errors and Cache Misses via Metrics

If all failures get folded into a `cache_miss_total` chart, operators may see miss rates climb without realizing Redis has lost connectivity.

Track separate metrics:

| Metric | Meaning |
|---|---|
| `cache_lookup_hit_total` | Cache read succeeded with value |
| `cache_lookup_miss_total` | Cache read succeeded with no entry |
| `redis_read_error_total` | Error accessing Redis |
| `cache_payload_invalid_total` | Redis returned value that failed decoding/validation |
| `cache_fallback_to_source_total` | Source reads triggered by Redis errors |
| `cache_miss_source_load_total` | Source reads triggered by normal cache misses |
| `redis_command_latency` | Redis command latency grouped by command type |
| `redis_timeout_total` | Timeouts by command and endpoint |
| `redis_connection_failure_total` | Connection/reconnection failures |
| `cache_write_error_total` | Cache population or update failures |
| `cache_evict_error_total` | Invalidation failures risking stale data |
| `source_load_error_total` | Database/API source failures |
| `negative_cache_hit_total` | Lookups hitting cached not-found records |
| `cache_consistency_anomaly_total` | Inconsistencies detected via reconciliation |

Never put raw product IDs, session IDs, or full Redis keys into metric labels because cardinality can grow unboundedly and expose sensitive data. Instead, use cache name, command, error category, environment, and node/slot group where appropriate.

### 18.1. Monitoring Redis from the CLI

```bash
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli INFO clients
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

Questions to ask:

- Is Redis evicting keys before TTL due to memory pressure?
- Are client connections spiking or getting rejected?
- Are commands slow on the server or timing out in the client due to network?
- Are `GET` calls succeeding with higher misses, or are commands failing?
- Were serializers, namespaces, or cache versions changed near the onset of errors?

`INFO` and `SLOWLOG` do not directly explain business not-found results or application decoding errors; combine them with Java-side metrics and request tracing.

## 19. Real-World Scenario: Returning a False 404 During a Redis Outage

A product management API:

```java
@GetMapping("/products/{id}")
public ResponseEntity<?> getProduct(@PathVariable String id) {
    ProductView product = cacheService.find(id);

    if (product == null) {
        return ResponseEntity.notFound().build();
    }

    return ResponseEntity.ok(product);
}
```

If `cacheService.find` has `catch (Exception) { return null; }`, the API returns `404` even when Redis is timing out.

Problems:

- Customers are told "product does not exist" even though it exists in the database.
- Monitoring may miss the infrastructure outage because HTTP only shows 404s.
- Clients/CDNs may cache the false not-found response.
- Root-cause investigation is harder because exceptions were swallowed.

Clearer design:

```text
Cache hit -> return product 200

Cache miss -> query database
             |
             +-- found in database -> 200
             +-- absent in database -> 404

Redis error -> if cache is only an optimization:
               query database under load limits
               |
               +-- found in database -> 200
               +-- absent in database -> 404
               +-- database also errors -> 503/5xx per policy

Redis error -> if Redis is the required authoritative source:
               return appropriate error; do not infer missing
```

The key point is that **404 appears only when the authoritative source confirms the resource does not exist**, never merely because a cache lookup failed.

## 20. Real-World Scenario: Checking Key Existence Before Creating a Resource

A service has logic:

```java
Boolean exists = redisTemplate.hasKey(key);

if (Boolean.FALSE.equals(exists)) {
    // Create resource
}
```

In a normal call, `false` can confirm the key was absent at the moment of the check. However:

- `hasKey` can throw an exception if Redis fails.
- Inside a transaction/pipeline, the immediate return value can be `null` because the command is queued.
- A `false` result may already be stale by the time another request creates the key.
- If business rules allow only one resource creation, `EXISTS` followed by `SET` is not atomic.

Therefore:

```text
hasKey == false  -> Observed key absent at check time.
hasKey == true   -> Observed key present at check time.
hasKey throws    -> No evidence to make a decision.
hasKey == null inside pipeline/transaction
                 -> No immediate command result yet.
```

For the invariant "create only if absent," use `SET ... NX` or an appropriate Lua script; never treat `DataAccessException` as `false`.

## 21. Real-World Scenario: Invalidation Failure After a Database Write

Suppose code runs:

```text
1. UPDATE product in database succeeds.
2. DEL cache:product:v1:p-100 in Redis.
3. Redis DEL times out.
```

Now:

- The database has the new data.
- Redis may still hold the old version, or eviction succeeded without the client receiving the reply.
- If the service returns success without tracking invalidation failures, subsequent requests may read stale cache data.
- If retrying `DEL`, deletion is usually idempotent in effect, yet consider races: another request may have just repopulated the fresh value and then get deleted; usually more a performance hit than a consistency bug if the source is authoritative, though ordering matters.

An eviction failure is neither a "cache miss" nor "authoritative data does not exist." Use TTLs as a staleness bound where appropriate, event/outbox invalidation, or a reconciliation path for critical cases.

## 22. Testing Result Classification

A test suite should verify both **normal Redis results** and **failure paths**.

### 22.1. Synchronous Test Matrix

| Scenario | Result from Redis | Service Contract |
|---|---|---|
| GET existing key | `"READY"` | HIT, value `READY` |
| GET missing key | nil / Java `null` | MISS, no exception |
| GET key with empty string | `""` | HIT with empty value if valid |
| GET wrong-type key | WRONGTYPE | Failure, not MISS |
| Redis connection refused | Exception | Failure or explicit fallback |
| Redis timeout | Exception | Failure or explicit fallback |
| Wrong key serializer | Redis nil on another physical key | Detect config bug; do not equate to network failure |
| Corrupt JSON payload | Value bytes but decode fails | INVALID VALUE |
| Redis key has cached negative sentinel | Value `NOT_FOUND` | HIT-negative, not Redis miss |
| `HGET` missing field | nil | Field missing, not necessarily hash missing |
| `TTL` returns -1 | Key exists without expiry | Do not report missing |
| `TTL` returns -2 | Key absent at command time | Missing per TTL contract |
| `MGET` has null element | Nil at that position | Can be missing **or** wrong-type key |

### 22.2. Reactive: Verifying Signals with StepVerifier

For a `Mono<String>` method backed by `GET`, write contract tests:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

// Simulate Redis GET returning a value:
StepVerifier.create(Mono.just("READY"))
        .expectNext("READY")
        .verifyComplete();

// Simulate Redis GET miss:
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

// Simulate Redis GET error:
StepVerifier.create(
                Mono.<String>error(
                        new IllegalStateException("Redis unavailable")))
        .expectError(IllegalStateException.class)
        .verify();
```

These illustrate **Reactor signal types** and do not by themselves integration-test Spring Data Redis. For real verification, use a test Redis / connection factory and test timeout, `WRONGTYPE`, and serializer mismatch scenarios on concrete keys.

For a reactive service using `switchIfEmpty`, verify that fallback runs only when upstream completes empty. For `onErrorResume`, verify the error branch logs/records metrics and is not counted as a cache miss.

### 22.3. Testing Against Real Redis

An integration test workflow:

1. Start Redis in a test environment.
2. Call `GET` on a non-existent key; verify `MISS`.
3. Write an empty value; verify `HIT`, not `MISS`.
4. Write a Set to the same key and call `GET`; verify failure occurs.
5. Stop the test Redis or point to an invalid endpoint; verify connection failure is handled separately.
6. Use an incompatible serializer; verify payload errors do not become `MISS`.
7. Set a short TTL; verify an expired key is observed as a normal miss.
8. For reactive APIs, verify `Mono.empty()` and `Mono.error()` take distinct paths.
9. For `CacheManager`, test cached nulls (when supported by the provider) vs. absent entries.
10. Test fallback during a Redis outage under concurrent load to confirm the database is not overwhelmed.

You do not need destructive commands on production Redis to prove these principles.

## 23. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Fix |
|---|---|---|
| `catch (Exception) { return null; }` | Swallows Redis outages, falsely reports not-found | Classify exceptions; fall back only intentionally |
| `onErrorResume(e -> Mono.empty())` for all errors | Errors disguised as reactive misses | Fall back only when policy permits and record separate metrics |
| Treating `null` from pipeline/transaction as missing key | Creates bogus data because reply hasn't arrived | Read results after pipeline/`EXEC` |
| Assuming `MGET` null always means missing key | Misses wrong-type keys | Understand `MGET` contract, check schema |
| Assuming `HGET` null means entire hash is missing | Wrong conclusion about object | Distinguish hash vs. field if business logic requires |
| Treating empty Set/List as Redis failure | False errors on valid empty data | Understand per-command return types |
| Assuming `EXISTS` then `SET` is atomic | Multi-client race | Use `SET NX` / Lua |
| Treating `GET` returning `"null"` string as missing key | Confuses serialized payload with Redis nil | Separate cache payload from Redis reply |
| Converting serializer errors to `Optional.empty` | Hides deploy/schema bugs | Report INVALID VALUE, migrate/fall back |
| Returning HTTP 404 directly on Redis cache miss | Confuses cache with source of truth | Query source database |
| Letting requests bypass auth/rate limit when Redis errors | Can bypass security controls | Fail closed or use an evaluated backup mechanism |
| Sending all traffic to DB on Redis outage | Causes cache avalanche / overload | Circuit breakers / bulkheads / rate limits |
| Retrying `INCR` after timeout without checks | Duplicate side effects | Idempotency and unknown-outcome handling |
| Assuming replica nil means primary is missing | Reads stale state | Consistency policy / read primary when required |
| Not separating negative cache from miss | Wrong not-found semantics | Explicit sentinel/DTO/TTL |
| Logging every Redis key / session ID | Secret leakage, high metric cardinality | Log namespace/category, sanitize |
| Swallowing both cache get and evict errors | Prolonged stale data or security risks | Separate policies for read/write/invalidate |

## 24. Decision Flow for a Redis Lookup

```text
Need to read a key from Redis
             |
             v
Choose the right command and serializer
             |
             v
Execute command (do not confuse pipeline/transaction)
             |
       +-----+-------+------------------+
       |             |                  |
    Value          Nil/Empty          Exception
       |             |                  |
       v             v                  v
  Deserialize    Understand        ACCESS ERROR
       |         command contract       |
   +---+---+         |              +----+----+
   |       |         v              |         |
  OK      Fail      MISS         Cache-only  Security /
   |       |         |             read?     critical?
   v       v         |              |         |
  HIT   INVALID      |              v         v
        VALUE        |          Bounded     Fail closed /
                     |          fallback    explicit error
                     |
                     v
              Is Redis the
              source of truth?
                +----+----+
                |         |
               Yes        No
                |         |
                v         v
          Missing-domain Read database
          policy            |
                |       +---+---+
                |       |       |
                |     Found  Not found
                |       |       |
                v       v       v
             Domain   Return  Business
             result   value   not found
```

### Rules to Remember

1. **A miss is a successful read outcome**, not another name for an exception.
2. **Null/empty carries per-command and per-context semantics**: `GET`, `HGET`, `MGET`, collection operations, pipelines, and transactions differ.
3. **Redis reply, serializer, and business domain are three distinct layers**: a key can exist with an invalid payload, or a cache can contain a "not found" sentinel.
4. **A Redis failure does not prove source data is absent.** If a business 404 is needed, let the authoritative source confirm it.
5. **Fallbacks depend on business semantics**: cache-aside reads may fail open; authentication, idempotency, and safety checks usually must not.
6. **Retries require error classification and idempotency.** Write timeouts can leave ambiguous outcomes, while `WRONGTYPE`/serializer errors are not fixed by network retries.
7. **Monitoring must separate MISS, ACCESS ERROR, and INVALID VALUE** so infrastructure or migration issues are never hidden.

## 25. Conclusion

In **Spring Data Redis**, a non-existent key is normally represented as a **normal read result**: `GET` returns nil, `StringRedisTemplate.opsForValue().get` returns Java `null` in direct calls, and reactive `GET` completes with `Mono.empty()`. By contrast, **data access errors** flow through exceptions or `Mono.error()`; serializer failures, wrong Redis types, timeouts, and permission errors cannot be turned into "not found" without corrupting system semantics.

Correctness lies in **per-layer contracts**: knowing what the command returns, knowing what the serializer handles, knowing whether a cache miss must consult the database, and knowing whether a Redis error may fall back or must fail. Where Redis is purely a cache, controlled source fallback is viable. For sessions, authorization, locks, idempotency, and critical business state, prioritize safety and consistency.

**Core rule: never use "unable to read data" as proof that "data does not exist."**
