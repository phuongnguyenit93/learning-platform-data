# The DataAccessException Hierarchy in Redis Access

> **Module:** Spring Data Redis  
> **Chapter:** Error Handling  
> **Topic:** Classifying Redis access exceptions within Spring's `DataAccessException` hierarchy, understanding error translation from Lettuce/Jedis, identifying root causes, and building retry, fallback, HTTP handling, observability, and write-correctness safeguards.

## 1. Why Understand DataAccessException When Using Redis?

Consider a seemingly simple operation:

~~~java
String value = stringRedisTemplate.opsForValue()
        .get("product:101:name");
~~~

Behind this line of code lie multiple layers:

~~~mermaid
flowchart TD
    APP["Service / Controller"] --> TEMPLATE["Spring RedisTemplate"]
    TEMPLATE --> CONNECTION["Spring Data Redis connection"]
    CONNECTION --> DRIVER["Lettuce / Jedis"]
    DRIVER --> NETWORK["TCP, TLS, DNS, Network"]
    NETWORK --> REDIS["Redis server / Redis Cluster"]
    REDIS --> RESULT{"Result"}
    RESULT --> VALUE["Data or key does not exist"]
    RESULT --> ERROR["Server error, timeout, disconnect"]
    ERROR --> RAW["Driver exception"]
    RAW --> TRANSLATE["Spring exception translation"]
    TRANSLATE --> DAO["DataAccessException / subtype"]
    DAO --> HANDLE["Retry / fallback / fail / reconcile"]
~~~

Errors you can encounter:

- Redis server is down or unreachable.
- Redis command exceeds processing deadline.
- Key is a `list` while code calls `GET` for a String.
- Redis Cluster receives a multi-key command across different slots and reports `CROSSSLOT`.
- Wrong Redis ACL, user/password, or unauthorized command.
- Out of RAM or `maxmemory` policy causes writes to fail.
- Serializer cannot read legacy data.
- Code passes invalid Java arguments.
- Redis executed a write command but the response was lost.

These cases **do not share the same solution**. Retrying may help right as the network recovers, but it will not fix a wrong key type or a cross-slot multi-key command. With `INCR`, retrying after a timeout can even mutate data twice.

Therefore, treat the exception hierarchy as **input for decision-making**, not as an automatic mechanism to fix every Redis failure.

### 1.1. What Does DataAccessException Solve?

`org.springframework.dao.DataAccessException` is Spring's exception abstraction for data access errors. It is not limited to SQL. Spring Data modules and infrastructure components can translate driver/store errors into classes in this hierarchy.

Benefits:

1. **No direct driver coupling** in every service: code can catch Spring types instead of listing all Lettuce/Jedis exceptions.
2. **Categorization concepts** such as transient, non-transient, and recoverable.
3. **Preserves the root cause** via the cause chain for diagnosis.
4. **Supports shared policies** at the adapter, service, or API layer.
5. **Separates a valid cache miss from a data access failure.**

Limitations: not every Redis error translates into the exact same subtype across all versions. An error raised outside the Redis connection abstraction may remain a driver exception, serializer exception, or Java runtime exception.

## 2. Where Does DataAccessException Sit in the Java Exception Hierarchy?

`DataAccessException` is an **unchecked exception**: it extends `RuntimeException` via Spring's `NestedRuntimeException`. You are not forced to add `throws DataAccessException` to every method.

~~~text
java.lang.RuntimeException
  └─ org.springframework.core.NestedRuntimeException
      └─ org.springframework.dao.DataAccessException
          ├─ NonTransientDataAccessException
          ├─ TransientDataAccessException
          └─ RecoverableDataAccessException
~~~

This diagram shows the three main branches without listing every subclass in Spring Framework.

### 2.1. NonTransientDataAccessException

General interpretation: an error not expected to disappear simply by immediately re-executing the exact same operation.

Some subtypes in Spring DAO:

- `InvalidDataAccessApiUsageException`.
- `InvalidDataAccessResourceUsageException`.
- `NonTransientDataAccessResourceException`.
- `DataAccessResourceFailureException`.
- `PermissionDeniedDataAccessException`.
- `UncategorizedDataAccessException`.

**Important note:** the `NonTransient` branch name is how the framework classifies exceptions, not a physical law saying an error can never recover. A Redis connection failure may be caused by a brief network glitch even though Spring's exception type belongs to the non-transient resource error branch.

### 2.2. TransientDataAccessException

General interpretation: an error that may recover on a retry under appropriate conditions, though you must still consider operation idempotency.

Examples:

- `QueryTimeoutException`.
- `TransientDataAccessResourceException`.
- `ConcurrencyFailureException` and related subtypes.

**A transient exception does not mean you can retry a non-idempotent write.** Redis may have already executed `INCR` before the client received the timeout error.

### 2.3. RecoverableDataAccessException

Spring DAO has the `RecoverableDataAccessException` branch for situations where continuing requires a specific recovery step.

Do not assume every Redis connection drop is translated into this branch. In practice with Spring Data Redis, common errors are typically represented via `RedisConnectionFailureException`, `QueryTimeoutException`, or `RedisSystemException`.

### 2.4. Diagram of Redis-Relevant Subtypes

~~~text
DataAccessException
├─ NonTransientDataAccessException
│  ├─ NonTransientDataAccessResourceException
│  │  └─ DataAccessResourceFailureException
│  │      └─ RedisConnectionFailureException       [Spring Data Redis]
│  ├─ InvalidDataAccessApiUsageException
│  ├─ InvalidDataAccessResourceUsageException
│  ├─ PermissionDeniedDataAccessException
│  └─ UncategorizedDataAccessException
│      └─ RedisSystemException                    [Spring Data Redis]
├─ TransientDataAccessException
│  ├─ QueryTimeoutException
│  ├─ TransientDataAccessResourceException
│  └─ ConcurrencyFailureException
└─ RecoverableDataAccessException
~~~

This tree is **abbreviated**, focusing only on classes worth knowing when handling Redis. Other branches of `DataAccessException` also exist.

## 3. Most Common Redis Exceptions

### 3.1. RedisConnectionFailureException

Fully qualified name:

~~~java
org.springframework.data.redis.RedisConnectionFailureException
~~~

Indicates an error related to being unable to connect or maintain a Redis connection under Spring Data Redis translation. Commonly seen when:

- The Redis server is down.
- Hostname/port is wrong.
- Network is disconnected, dropping packets, or partitioned.
- TCP connect timeout occurs.
- Redis Cluster failover or connecting to an unavailable node.
- DNS, firewall, TLS, or related layers have issues.

An example message may be:

~~~text
RedisConnectionFailureException: Unable to connect to Redis
~~~

Message text is not a stable contract. Inspect the **cause** and actual connectivity to distinguish network failures from configuration issues.

In common versions, this exception extends `DataAccessResourceFailureException` in the non-transient resource errors branch.

### 3.2. RedisSystemException

Fully qualified name:

~~~java
org.springframework.data.redis.RedisSystemException
~~~

This is the Redis-specific exception for errors not categorized more specifically. It typically belongs to the `UncategorizedDataAccessException` branch.

An exception of this type can wrap:

- Redis command execution error.
- Redis server returning `WRONGTYPE`.
- Redis Cluster command or error reply.
- Redis driver error not mapped to a specific subtype by the converter.
- Errors on the Redis command execution path.

**Do not deduce that the Redis server is broken just because of the word "System."** The error may originate from the application's key schema or command usage.

### 3.3. QueryTimeoutException

Fully qualified name:

~~~java
org.springframework.dao.QueryTimeoutException
~~~

A subtype of `TransientDataAccessException` that can appear when the driver reports a Redis command timeout.

Possible causes:

- Overloaded Redis server.
- Heavy command or slow-running script.
- High network RTT.
- Driver command queue buildup.
- Client timeout configured too short.
- GC pauses or thread scheduling delays.
- Cluster topology/failover increasing latency.

Key takeaway: **a timeout only confirms the client did not receive a result on time; it does not prove Redis did not process the command.**

### 3.4. InvalidDataAccessApiUsageException

~~~java
org.springframework.dao.InvalidDataAccessApiUsageException
~~~

Indicates invalid API usage or an invalid data access operation according to the translator/framework.

Not all Redis server errors map to this class. For example, `WRONGTYPE` may be wrapped as `RedisSystemException` depending on driver/version.

When encountering usage errors, fix the code, parameters, data types, key schema, or unsupported operation; repeatedly retrying the same command usually does not help.

### 3.5. DataAccessResourceFailureException

~~~java
org.springframework.dao.DataAccessResourceFailureException
~~~

The resource error branch of Spring DAO; `RedisConnectionFailureException` belongs to this branch. If code catches it broadly, it may simultaneously catch resource errors from other datastores in the application.

If a policy applies only to Redis, prefer catching Redis-specific exceptions in a **Redis adapter** or explicitly identifying the dependency.

### 3.6. UncategorizedDataAccessException

~~~java
org.springframework.dao.UncategorizedDataAccessException
~~~

This branch is for data access errors that the translator did not recognize as a more specialized category. `RedisSystemException` usually belongs to this branch.

For this group, analyze the root cause instead of deciding retryability solely from the exception name.

### 3.7. PermissionDeniedDataAccessException

~~~java
org.springframework.dao.PermissionDeniedDataAccessException
~~~

Spring DAO has a permission error type. However, `NOAUTH`/`NOPERM` returned by Redis is not necessarily converted into this exact class by every Redis exception converter. You may receive `RedisSystemException` or a wrapped command execution error.

Do not write a catch block for `PermissionDeniedDataAccessException` and assume it covers all Redis ACL errors.

## 4. Identification and Handling Table by Subtype

| Spring Exception | Typical Context | Handling Direction |
|---|---|---|
| `RedisConnectionFailureException` | Connection lost, cannot reach Redis | Check health/network, bounded GET retry or fallback |
| `QueryTimeoutException` | Command waited past deadline | Check if command may have executed; safe read retries |
| `RedisSystemException` | Uncategorized Redis error | Check cause: WRONGTYPE, CROSSSLOT, ACL, OOM... |
| `InvalidDataAccessApiUsageException` | Invalid API/command/arguments | Fix code/input/configuration |
| `PermissionDeniedDataAccessException` if translated | Insufficient permissions | Fix ACL and credentials, do not blindly retry |
| `DataAccessResourceFailureException` | Resource access problem | Identify the exact datastore/operation |
| Generic `DataAccessException` | Translated error | Catch at shared boundary, do not treat all identically |
| Exception outside `DataAccessException` | Invalid argument, serializer, raw driver | Classify by actual cause |

A subtype is a **signal**, not a full description. Combine it with the Redis command, key type, possible committed effects, and business semantics.

## 5. Exception Translation Mechanism from Lettuce and Jedis

### 5.1. Driver and Spring Are Two Separate Layers

Spring Data Redis typically accesses Redis through a driver:

- **Lettuce:** Netty-based Redis client supporting synchronous/async/reactive APIs depending on usage.
- **Jedis:** Redis client with its own connection/API styles.

Lettuce has typical exception types:

~~~java
io.lettuce.core.RedisConnectionException
io.lettuce.core.RedisCommandTimeoutException
io.lettuce.core.RedisCommandExecutionException
io.lettuce.core.RedisException
~~~

Jedis also has connection and command exceptions under the `redis.clients.jedis.exceptions` package depending on version.

Spring Data Redis provides connection abstractions and exception translation to convert eligible errors into `DataAccessException`.

### 5.2. Illustrative Mapping Table

| Error Source | Possible Driver Exception | Usually Suitable Spring Exception |
|---|---|---|
| Connect failure | Lettuce `RedisConnectionException` | `RedisConnectionFailureException` |
| Redis command timeout | Lettuce `RedisCommandTimeoutException` | `QueryTimeoutException` |
| Server command error | Lettuce `RedisCommandExecutionException` | `RedisSystemException` or another class |
| Uncategorized Redis error | Lettuce `RedisException` | `RedisSystemException` |
| Code passes null key | `IllegalArgumentException` | May not translate to `DataAccessException` |
| JSON parse failure after GET | Jackson exception | Not a Redis connection exception by default |

This table is for **conceptual orientation**, not a strict guarantee across every Spring Data Redis/Lettuce/Jedis version. When building exception-type-based policies, observe the actual types produced by your stack.

### 5.3. Places Where Translation May Differ

- `RedisTemplate` and `StringRedisTemplate`.
- `ReactiveRedisTemplate`.
- Redis Repository.
- `RedisCacheManager` via Spring Cache.
- `RedisConnection` and low-level APIs.
- **Raw Lettuce/Jedis** calls directly from application code.
- Serialization/deserialization errors before/after a Redis command runs.

For example, if code directly calls Lettuce's `StatefulRedisConnection.sync().get(...)`, exceptions may remain in `io.lettuce.core`. Spring does not automatically translate arbitrary calls on an externally injected driver.

## 6. Distinguishing Cache Miss from Redis Failure

A common source of confusion:

~~~java
String value = stringRedisTemplate.opsForValue().get(key);
~~~

There are two distinct outcomes:

1. Redis is connected and the key does not exist: `value == null` is a valid result.
2. Redis is unreachable: the method may throw `RedisConnectionFailureException` or a related exception.

Do not catch every exception and return null:

~~~java
try {
    return redis.opsForValue().get(key);
} catch (Exception ex) {
    return null;
}
~~~

This erases signs that the system is failing and misleads the caller into confusing "Redis unavailable" with "data does not exist."

If Redis is only a **cache**, both cases may lead to reading the database, but they must have **separate logs/metrics**. If Redis is the authoritative source, treating errors as missing keys can cause business bugs.

### 6.1. An Adapter Modeling Three States

~~~java
public sealed interface CacheLookup
        permits CacheLookup.Hit,
                CacheLookup.Miss,
                CacheLookup.Unavailable {

    record Hit(String value) implements CacheLookup {}

    record Miss() implements CacheLookup {}

    record Unavailable(String reason) implements CacheLookup {}
}
~~~

The snippet above uses Java 17 sealed types and is an application-defined abstraction.

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RedisCacheLookup {

    private final StringRedisTemplate redis;

    public RedisCacheLookup(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public CacheLookup get(String key) {
        try {
            String value = redis.opsForValue().get(key);

            return value == null
                    ? new CacheLookup.Miss()
                    : new CacheLookup.Hit(value);

        } catch (RedisConnectionFailureException ex) {
            return new CacheLookup.Unavailable("CONNECTION");
        } catch (QueryTimeoutException ex) {
            return new CacheLookup.Unavailable("TIMEOUT");
        }
    }
}
~~~

Other errors like `RedisSystemException` continue to propagate because the code has not defined a policy for them. That is usually better than swallowing all errors as cache misses.

## 7. Why Does RedisSystemException Require Inspecting the Root Cause?

Suppose Redis holds a List:

~~~redis
LPUSH queue:tasks task-1 task-2
~~~

Yet the application reads it with the String API:

~~~java
String value = redis.opsForValue().get("queue:tasks");
~~~

The Redis server may return:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Depending on the converter, the Spring-layer exception may be `RedisSystemException`. However, the real issue is not that the Redis server is dying, but that **the application called the wrong operation for the key type**.

Run in a test environment:

~~~bash
redis-cli TYPE queue:tasks
redis-cli LRANGE queue:tasks 0 -1
~~~

If the key is a `list`, fix the code to read a List rather than retrying GET.

### 7.1. Extracting the Deepest Cause

`DataAccessException` inherits helpers from `NestedRuntimeException`:

~~~java
import org.springframework.dao.DataAccessException;

public void logRedisFailure(
        String operation, DataAccessException ex) {

    Throwable root = ex.getMostSpecificCause();

    log.warn(
            "Redis operation={}, springType={}, rootType={}",
            operation,
            ex.getClass().getSimpleName(),
            root.getClass().getSimpleName(),
            ex);
}
~~~

In this code, `log` is an application-declared logger. In production, inspect the cause chain and classify errors into metrics; avoid logging full stack traces tens of thousands of times per second during a Redis outage.

### 7.2. Do Not Rely Solely on the Exception Message

Fragile pattern:

~~~java
if (ex.getMessage().contains("WRONGTYPE")) {
    // Classify error.
}
~~~

Reasons not to scatter this across services:

- Messages can change across driver versions.
- The root error resides in the cause rather than the outer message.
- The message may be null.
- The message may contain internal details or sensitive values.

If a Redis error reply can only be recognized by text, centralize the mapping logic in a Redis adapter tested against your actual Redis/driver versions.

## 8. Common Redis Server Errors and Diagnosis

### 8.1. WRONGTYPE

Symptom:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

Check:

- The key's data type (`TYPE`).
- Is there a namespace collision between Redis String/Hash/List?
- Was the serializer/data model changed while reusing old keys?
- Did another service overwrite the key with a different data type?

Not fixed by increasing timeouts or retrying forever.

### 8.2. CROSSSLOT

In Redis Cluster:

~~~redis
MGET 'order:{o-101}:status' 'order:{o-202}:status'
~~~

If the two keys belong to different hash slots, the native multi-key command fails with:

~~~text
CROSSSLOT Keys in request don't hash to the same slot
~~~

Handling direction:

- Compute slots with `CLUSTER KEYSLOT`.
- If an atomic command is needed, design keys with the same hash tag.
- If the keys are independent, read using separate GETs / cluster-aware scatter depending on the API.
- Do not confuse driver `MOVED`/`ASK` routing with `CROSSSLOT`.
- Do not retry the exact same command that violates slot constraints.

Do not assume every Java `multiGet` throws CROSSSLOT because some clients split commands into multiple sub-requests; however, **native cross-slot MGET does not become atomic**.

### 8.3. NOAUTH and NOPERM

Redis may return:

~~~text
NOAUTH Authentication required
NOPERM this user has no permissions to run the command
~~~

Check:

- Are username/password or ACL tokens configured properly?
- Does the Redis ACL permit the command, key pattern, and channel pattern?
- Have secrets been rotated?
- Is the service connecting to the wrong environment?

The error may translate into `RedisSystemException` or another subtype depending on the converter. Do not assume every Redis ACL error becomes `PermissionDeniedDataAccessException`.

### 8.4. OOM and maxmemory

Redis may reject writes when out of memory:

~~~text
OOM command not allowed when used memory > 'maxmemory'
~~~

Inspect:

~~~bash
redis-cli INFO memory
redis-cli INFO stats
redis-cli CONFIG GET maxmemory
redis-cli CONFIG GET maxmemory-policy
~~~

Some managed Redis offerings block `CONFIG GET`; use the provider's control plane and metrics. Continuously retrying writes while Redis remains out of RAM can trigger a retry storm and worsen the incident.

### 8.5. Connection refused / DNS / TLS

If the root cause reports `Connection refused` or a TLS handshake failure, check connectivity first, not the key serializer.

Checkpoints:

- Endpoint and port.
- Container/Kubernetes Service/pod readiness.
- Firewall/network policy and DNS.
- TLS enabled/disabled and matching certificates.
- Whether Redis Cluster nodes advertise topology endpoints reachable from the client.
- Redis clients/connection limits.

### 8.6. TRYAGAIN, MOVED, and ASK

In Redis Cluster:

- `MOVED`: command sent to a node not owning the slot; cluster-aware clients typically update routing.
- `ASK`: temporary redirection during resharding.
- `TRYAGAIN`: temporary cluster condition that may warrant a retry.
- `CROSSSLOT`: command uses multiple keys in different slots; fix the data model/command.

Do not lump all of these into an unbounded retry loop.

## 9. Timeouts Are Especially Dangerous for Write Commands

### 9.1. A Timed-Out GET Command

~~~text
Client          Redis
  |-- GET key -->|
  |              | slow processing
  | x timeout    |
  |              | may send reply late
~~~

`GET` is a read command. A short retry or database fallback when used as a cache may be acceptable, depending on load and SLA.

### 9.2. An INCR Command May Have Executed

~~~text
Client                Redis
  |---- INCR count ---->|
  |                     | count: 10 -> 11
  |    reply lost       |
  | x QueryTimeout      |
  |---- retry INCR ---->|
  |                     | count: 11 -> 12
~~~

The application intended to increment once but actually incremented twice. Also be cautious with:

- `DECR` and `INCRBY`.
- `LPUSH`/`RPUSH`.
- `XADD *`.
- `PUBLISH`.
- State-mutating Lua scripts.
- `SET` when concurrent writers exist.
- External side effects triggered after receiving a Redis result.

### 9.3. Retry Table by Operation

| Operation | Retry After Timeout | Notes |
|---|---|---|
| `GET`/`HGET`/`EXISTS` | Usually safer | Read-only, bound attempts/backoff |
| `SET key sameValue` | Conditional | May overwrite a newer writer if ordering changes |
| `SET NX` | Needs read/reconciliation | Initial claim may have already succeeded |
| `INCR`/`DECR` | Do not blindly retry | Needs idempotency ID/script |
| `LPUSH` | Do not blindly retry | May create duplicate elements |
| `XADD *` | Do not blindly retry | Auto-generated ID may create a new entry |
| `PUBLISH` | Do not blindly retry if duplicates hurt | Subscribers may receive duplicates or be offline |
| `DEL`/`UNLINK` | Usually acceptable for cache | Consider concurrent recreate |
| `MGET` | Depends on client/cluster | Some high-level APIs scatter/gather |
| Lua write script | Depends on idempotency | Script may have run before timeout |

**Principle:** the exception class provides no guarantee about whether the side effect occurred.

### 9.4. TTL and Write Conditions Affect Idempotency

`SET key fixedValue` can look idempotent in final state when there is no contention. However, a late retry can overwrite a newer value:

~~~text
T1: Request A sends SET key=old -> timeout
T2: Request B SET key=new -> succeeds
T3: A retries SET key=old -> regresses data
~~~

Conditional writes, version checks, CAS/Lua, or an appropriate authoritative source are needed when data is critical.

## 10. Transient Classification Is Not a Retry Policy

An error belonging to `TransientDataAccessException` indicates it might be temporary, yet you still must ask:

1. Is the command a read or a write?
2. Could the command have executed before the client saw the exception?
3. Does retrying alter the business outcome?
4. Is Redis overloaded, so retrying makes things worse?
5. Is there an operation ID or idempotency key?
6. Is there a durable source to reconcile against?

Similarly, `RedisConnectionFailureException` belongs to the non-transient resource failure branch, yet the network might recover quickly. Do not filter with "only retry `TransientDataAccessException`" while ignoring command and system characteristics.

### 10.1. Bounded Retry

An illustrative helper for `GET`:

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;

public class RetryingRedisReader {

    private final StringRedisTemplate redis;

    public RetryingRedisReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getWithOneRetry(String key) {
        try {
            return redis.opsForValue().get(key);
        } catch (RedisConnectionFailureException |
                 QueryTimeoutException ex) {

            // Retry only a read-only GET.
            // Production needs backoff, metrics, and a circuit breaker.
            return redis.opsForValue().get(key);
        }
    }
}
~~~

This snippet retries once immediately for illustration only. Production requires:

- Exponential backoff and jitter.
- Total timeout budget for the whole request.
- Bounded retry attempts.
- Bulkheads and circuit breakers.
- Retry attempt metrics.
- Never retrying WRONGTYPE/CROSSSLOT/ACL/schema errors.

### 10.2. Why Are Retry Storms Dangerous?

Suppose every HTTP request gets 3 attempts at the gateway, 3 in the service, and 3 in the Redis adapter. Depending on how attempts are counted, one logical request can trigger many actual Redis commands. When Redis is overloaded, those retries push latency and CPU higher.

Each layer must know where retries are already handled to avoid stacking uncontrolled retries.

## 11. Fail-Open for Cache, Fail-Closed for Critical Data

### 11.1. Redis as a Cache Only

If Redis stores a copy from the database, connectivity/timeout errors can fall back:

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

public String getProductJson(String id) {
    String key = "cache:product:v1:" + id;

    try {
        String cached = redis.opsForValue().get(key);
        if (cached != null) {
            return cached;
        }
    } catch (RedisConnectionFailureException |
             QueryTimeoutException ex) {

        // Fall back provided the authoritative source can handle the load.
        return productSource.loadProductJson(id);
    }

    return productSource.loadProductJson(id);
}
~~~

`redis` is a `StringRedisTemplate`; `productSource` is an application dependency.

With this code:

- A cache miss leads to reading the source.
- A cache connection/timeout failure also leads to reading the source.
- `RedisSystemException`/serializer errors are not silently hidden.
- Separate metrics are needed for cache misses and cache errors.
- During a system-wide Redis outage, a database stampede can occur; concurrency limits are needed.

### 11.2. Redis as the Source of Truth

Suppose Redis stores critical quotas. A catch block like:

~~~java
catch (RedisConnectionFailureException ex) {
    return "UNLIMITED";
}
~~~

is **dangerous** if it allows operations to proceed without verifying quotas. You need fail-closed behavior or a backup source with reliable semantics.

Choose fail-open vs. fail-closed based on:

- Is there another authoritative source?
- Is stale data acceptable?
- What is the impact of returning a default?
- How much fallback load will a Redis outage generate?
- Can the incident be observed and alerted on?

### 11.3. Do Not Lump Redis Errors with Database Errors

Bad:

~~~java
try {
    String cached = redis.opsForValue().get(key);
    return cached == null ? database.load(id) : cached;
} catch (DataAccessException ex) {
    return "fallback";
}
~~~

If `database.load(id)` also throws `DataAccessException`, this catch can mistake a **database outage** for a Redis cache failure.

Scope the try/catch tightly around the Redis call or separate the Redis adapter from the authoritative source layer.

## 12. Spring Cache Abstraction and CacheErrorHandler

With:

~~~java
@Cacheable(cacheNames = "productDetails", key = "#id")
public ProductView findProduct(String id) {
    return repository.findById(id).orElseThrow();
}
~~~

When using `RedisCacheManager`, Redis GET/PUT can throw exceptions. **Do not assume `@Cacheable` automatically fails open** on every Redis error.

Spring Cache provides `CacheErrorHandler` to customize policies for:

- Cache get.
- Cache put.
- Cache evict.
- Cache clear.

### 12.1. Example Custom Fail-Open Policy for Cache GET/PUT

~~~java
import org.springframework.cache.Cache;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

public class ProductCacheErrorHandler implements CacheErrorHandler {

    private boolean canIgnore(RuntimeException ex) {
        return ex instanceof RedisConnectionFailureException
                || ex instanceof QueryTimeoutException;
    }

    @Override
    public void handleCacheGetError(
            RuntimeException ex, Cache cache, Object key) {
        if (canIgnore(ex)) {
            // Record metrics then let the source method execute.
            return;
        }
        throw ex;
    }

    @Override
    public void handleCachePutError(
            RuntimeException ex, Cache cache,
            Object key, Object value) {
        if (canIgnore(ex)) {
            // Cache put is best effort in this use case.
            return;
        }
        throw ex;
    }

    @Override
    public void handleCacheEvictError(
            RuntimeException ex, Cache cache, Object key) {
        // Do not ignore when stale data could violate SLA.
        throw ex;
    }

    @Override
    public void handleCacheClearError(
            RuntimeException ex, Cache cache) {
        throw ex;
    }
}
~~~

Example using the Spring Cache API. Real applications should emit actual metrics/logs instead of comments.

### 12.2. Why Is an Eviction Failure Different from a Cache GET Failure?

If the database updates a product's price but the old Redis cache key is not evicted:

~~~text
Database: price 100 -> 90
Redis: cached price = 100
Evict Redis: connection error
Next GET: returns 100 until TTL expires
~~~

If the system requires strict freshness, swallowing eviction errors can serve stale data to users. You need:

- A TTL safety net.
- Invalidation retry/outbox.
- Versioned keys or source data checks.
- A business verification path that reads the authoritative source.

`CacheErrorHandler` does not make a database transaction and Redis an atomic transaction.

### 12.3. Configuring CacheErrorHandler

One approach via `CachingConfigurer`:

~~~java
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.interceptor.CacheErrorHandler;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheErrorConfiguration implements CachingConfigurer {

    @Override
    public CacheErrorHandler errorHandler() {
        return new ProductCacheErrorHandler();
    }
}
~~~

Exact wiring depends on Spring Framework and the application's configuration setup. A handler at the Spring Cache layer **does not automatically apply** to direct `RedisTemplate` calls in other services.

## 13. ReactiveRedisTemplate: Exceptions Flow Through Mono/Flux

Reactive Redis APIs usually return `Mono<T>` or `Flux<T>`. I/O errors can surface when the publisher is **subscribed to** as a Reactor error signal.

~~~java
Mono<String> result = reactiveRedisTemplate
        .opsForValue()
        .get("cache:product:101");
~~~

A try/catch wrapping only the **creation** of the Mono will not catch Redis errors occurring later.

### 13.1. Fallback When Redis GET Fails

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import reactor.core.publisher.Mono;

public Mono<String> getProduct(String id) {
    String key = "cache:product:v1:" + id;

    return reactiveRedisTemplate.opsForValue()
            .get(key)
            .onErrorResume(
                    RedisConnectionFailureException.class,
                    ex -> productSource.loadProductJson(id))
            .onErrorResume(
                    QueryTimeoutException.class,
                    ex -> productSource.loadProductJson(id))
            .switchIfEmpty(Mono.defer(
                    () -> productSource.loadProductJson(id)));
}
~~~

This snippet uses `ReactiveStringRedisTemplate` and an application-defined reactive source.

- `onErrorResume`: handles the specified connection/timeout errors.
- `switchIfEmpty`: handles cache misses.
- Other exceptions propagate rather than being swallowed.
- If the fallback source fails, that new error must be handled at the appropriate layer.

### 13.2. RetryWhen with GET

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;

Mono<String> value = reactiveRedisTemplate
        .opsForValue()
        .get(key)
        .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                     .maxBackoff(Duration.ofSeconds(1))
                     .filter(ex ->
                             ex instanceof RedisConnectionFailureException
                             || ex instanceof QueryTimeoutException));
~~~

This is an illustrative policy for **read-only GET**. Wrapping an entire business pipeline with write side effects in `retryWhen` can re-execute non-idempotent steps.

### 13.3. doOnError Is Not Recovery

~~~java
return reactiveRedisTemplate.opsForValue()
        .get(key)
        .doOnError(ex -> log.warn("Redis read failed", ex));
~~~

`doOnError` only performs side effects such as logging; it **does not turn an error into success**. To fall back, use `onErrorResume` with a clear policy.

### 13.4. Do Not Call block() on the Event Loop

~~~java
String value = reactiveRedisTemplate.opsForValue()
        .get(key)
        .block();
~~~

On a WebFlux/Netty event loop, `block()` breaks the non-blocking model and can stall threads or throw errors. Pass `Mono`/`Flux` to the caller instead of forcing synchronous results in a request handler.

### 13.5. Synchronous Errors Before Subscription

A null key, invalid input, or invalid setup can cause a method to throw an exception immediately on invocation, before returning a `Mono`. Therefore separate:

- Validation at the method/controller boundary.
- Redis I/O error signals inside the reactive pipeline.
- Serialization/mapping errors needing their own policy.

## 14. @RestControllerAdvice: Returning Safe HTTP Errors

When Redis is a mandatory dependency for an endpoint, `@RestControllerAdvice` can return responses per the HTTP contract instead of leaking stack traces.

~~~java
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.RedisSystemException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class DataAccessApiExceptionHandler {

    @ExceptionHandler({
            RedisConnectionFailureException.class,
            QueryTimeoutException.class
    })
    public ResponseEntity<ProblemDetail> redisUnavailable(
            RuntimeException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Data dependency unavailable");
        problem.setDetail(
                "The request cannot be completed at this time.");

        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(problem);
    }

    @ExceptionHandler(RedisSystemException.class)
    public ResponseEntity<ProblemDetail> redisError(
            RedisSystemException ex) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        problem.setTitle("Data access error");
        problem.setDetail("Unexpected data operation failure.");

        return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(problem);
    }
}
~~~

This snippet illustrates Spring Framework 6+ and `ProblemDetail`. For applications using older framework versions, use an appropriate response model.

**Never unconditionally return `ex.getMessage()` to clients**, as it may expose hosts, Redis keys, topology, or other details.

### 14.1. Do Not Map Every DataAccessException to HTTP 503

A Redis `WRONGTYPE` error may stem from buggy code; `CROSSSLOT` from key design; `NOAUTH` from permission configuration. Returning 503 and telling clients to retry immediately can increase load without fixing the error.

HTTP status codes should reflect the endpoint contract:

- `503` when a dependency is temporarily unavailable.
- `500` for unhandled server/config/schema errors.
- `400` for invalid request input.
- `409` for a confirmed business conflict, not just because Redis returned a command error.
- `202` or a dedicated async response when an operation is in progress, if supported by the API.

Do not use the exception hierarchy as a replacement for validation and domain error models.

## 15. Repository, Template, and Serializer Failures

Spring Data Redis Repositories can execute multiple steps to save an entity:

- Convert the Java entity into a Redis Hash.
- Attach TTL per `@RedisHash` or `@TimeToLive`.
- Update secondary indexes.
- Create keyspace metadata.
- Send multiple Redis commands.

An exception from `repository.save(entity)` does not imply that **all preceding commands rolled back**. Redis has different semantics from an RDBMS.

### 15.1. Partial Side Effects Can Occur

Conceptual example:

~~~text
HSET product:101 ...                -> OK
SADD product:category:desk 101     -> TIMEOUT
repository.save(product)            -> exception
~~~

You cannot conclude that the `HSET` step did not happen. When indexes, caches, and critical resources must stay synchronized, you need idempotency, reconciliation, and appropriate transactional patterns.

### 15.2. Serializer Errors Are a Separate Group

Scenarios:

- Writer uses `StringRedisSerializer`, reader uses JDK serialization.
- Java package/class changed for a JDK-serialized value.
- New JSON schema version is incompatible with old code.
- Hash value was encoded with an unexpected serializer.

The error may be `SerializationFailedException` or another exception depending on the code path; it is not necessarily translated to `RedisConnectionFailureException`.

If `GET` returns bytes successfully but deserialization fails, retrying `GET` will read the exact same bad bytes. You must fix the format/version/migration or choose the right reader.

## 16. Redis Transactions and Pipelines: Exceptions Do Not Mean Rollback

### 16.1. Pipeline

Pipelining sends multiple commands without waiting for individual replies to reduce round-trip overhead. One command can succeed while a subsequent one fails.

~~~text
Pipeline:
  SET a 1      -> succeeds
  INCR b       -> WRONGTYPE error
  GET c        -> may return a result
~~~

An exception thrown while processing pipeline replies does not mean Redis undid `SET a 1`. When designing retries for a whole pipeline, evaluate the side effects of each command.

### 16.2. MULTI/EXEC

Redis `MULTI`/`EXEC` guarantees that queued commands execute sequentially per Redis semantics, but it **does not roll back** all previously succeeded commands when another command fails at runtime.

Example:

~~~redis
MULTI
SET counter:status active
INCR counter:status
EXEC
~~~

`SET` can succeed while `INCR` errors because `active` is not an integer. Do not treat Redis transactions like SQL transactions.

### 16.3. WATCH

`WATCH` provides optimistic locking. If watched keys are modified, `EXEC` may abort and the API represents the abort in its own way. Do not assume every `WATCH` abort becomes `OptimisticLockingFailureException` or a specific Spring subtype; inspect the API result.

### 16.4. Redis Cluster

Multi-key commands, transactions, and Lua scripts have hash slot restrictions. `CROSSSLOT` is a key-placement issue; retrying the same command will not solve it.

### 16.5. Lua/Redis Functions

Server-side scripts ensure steps inside the script execute atomically on a valid shard. However, a client timeout after a script **can be an ambiguous outcome**: the script may or may not have run. Use business operation IDs or conditional updates if retries must be safe.

## 17. A Redis Command Can Succeed Even When the Client Sees an Exception

This rule applies to every operation with side effects:

~~~mermaid
sequenceDiagram
    participant C as Spring service
    participant R as Redis
    C->>R: INCR counter
    R->>R: Value 10 becomes 11
    R--xC: Reply lost / timeout
    Note over C: QueryTimeoutException
    C->>R: Retry INCR counter
    R->>R: Value 11 becomes 12
    R-->>C: 12
~~~

When business requirements allow incrementing only once, design idempotency **where the side effect occurs**.

For example, Redis Lua can use an operation key:

~~~lua
-- KEYS[1]: counter key
-- KEYS[2]: idempotency record key
-- ARGV[1]: operation ID
-- ARGV[2]: TTL seconds

local exists = redis.call('GET', KEYS[2])
if exists then
    return tonumber(exists)
end

local result = redis.call('INCR', KEYS[1])
redis.call('SET', KEYS[2], result, 'EX', tonumber(ARGV[2]))
return result
~~~

When using Redis Cluster, `KEYS[1]` and `KEYS[2]` must map to the same hash slot. With this script, the operation ID is stored with a TTL, so once the TTL expires, idempotency protection ends. Design TTL and durability according to business needs.

This script is a **conceptual example**; it does not solve external database/payment side effects or Redis failover durability by itself.

## 18. Observability: Logs, Metrics, and Cause Chains

### 18.1. What Should Be Logged?

A Redis failure can be described by:

- Operation: GET, SET, INCR, EVAL, XREADGROUP...
- Key namespace/cache name, not necessarily the full key.
- Spring exception type.
- Root cause type.
- Redis error code if available.
- Latency and timeout threshold.
- Retry count.
- Redis node/Cluster context when needed.
- Circuit breaker/fallback decision.
- Request trace ID or business operation ID.

Never log Redis passwords, raw access tokens, session values, PII, or full user payloads. Apply redaction/sampling under high traffic.

### 18.2. Useful Metrics

| Suggested Metric | Purpose |
|---|---|
| `redis_operations_total` | Throughput by operation/outcome |
| `redis_errors_total` | Error count by type |
| `redis_command_latency` | P50/P95/P99 latency |
| `redis_retry_attempts_total` | Retry rate |
| `redis_fallback_total` | Cache fallback count |
| `redis_connection_failures_total` | Connection errors |
| `redis_command_timeouts_total` | Timeouts |
| `redis_serialization_failures_total` | Codec/schema mismatches |
| `redis_circuit_breaker_state` | Protection state |
| `redis_reconciliation_total` | Ambiguous operation outcomes |
| `redis_evicted_keys` | Evictions from Redis monitoring |

These metric names are **application-defined examples**; do not assume Micrometer/Spring Boot automatically generates all of them.

Do not use full keys, exception messages, or event IDs as metric labels because label cardinality will explode.

### 18.3. Redis CLI Diagnostics

~~~bash
redis-cli PING
redis-cli INFO server
redis-cli INFO clients
redis-cli INFO memory
redis-cli INFO stats
redis-cli INFO commandstats
redis-cli SLOWLOG GET 10
~~~

`SLOWLOG` tracks slow commands on Redis per the configured threshold; it does not measure client-side network wait. `INFO` on a single Redis Cluster node does not reflect the entire cluster. Managed Redis may restrict access to some commands.

## 19. An Error Triage Runbook

When the application logs an exception, work through these steps in order:

### Step 1. Confirm Where the Error Originated

Did the call come from:

- `RedisTemplate`/`StringRedisTemplate`?
- `ReactiveRedisTemplate`?
- `RedisCacheManager`/`@Cacheable`?
- Redis Repository?
- Raw Lettuce/Jedis?
- Serializer/Jackson?
- Business code after Redis returned a result?

### Step 2. Extract the Spring Type and Cause Type

Examples:

~~~text
Spring: RedisSystemException
Cause: RedisCommandExecutionException
Server reply: WRONGTYPE
~~~

Or:

~~~text
Spring: QueryTimeoutException
Cause: RedisCommandTimeoutException
Command: INCR
~~~

With the same Spring exception, handling can differ because the commands differ.

### Step 3. Identify Side Effects

- GET: read-only.
- SET: may overwrite.
- INCR: increments value, non-idempotent.
- XADD: appends event, may duplicate.
- PUBLISH: broadcasts message, may duplicate/be lost.
- Pipeline: a subset of commands may have succeeded.
- MULTI/EXEC: no SQL-style rollback.

### Step 4. Check for Non-Transient Causes

- WRONGTYPE: fix data type/schema.
- CROSSSLOT: fix hash tags/multi-key command.
- NOPERM: fix ACLs.
- OOM: adjust capacity/eviction.
- Serializer mismatch: fix codec/migration.

### Step 5. If Transient, Decide Whether Retrying Is Safe

- Bound attempts/backoff/jitter.
- Overall timeout.
- Circuit breaker/bulkhead.
- Idempotency for writes.
- Reconciliation when state is unknown.

### Step 6. Verify Final State in the Authoritative Source

When writing orders, payments, balances, or inventory, a Redis exception is not enough to conclude the business operation did not commit. Look up the business operation ID and durable state.

## 20. Testing Exception Handling

### 20.1. Unit Tests

Simulate each error type at the Redis adapter:

- `RedisConnectionFailureException`.
- `QueryTimeoutException`.
- `RedisSystemException` with the appropriate root cause if policy depends on it.
- Serializer exception.
- Key miss returning null.

Verify caller behavior:

- Does it fall back properly?
- Does it distinguish miss from unavailable?
- Does it avoid wrongly retrying writes?
- Does it propagate unsupported errors?
- Does it avoid hammering the source database?

### 20.2. Integration Tests

Use a Redis test instance/container or staging environment to test:

1. Connecting to a down endpoint.
2. Redis restarting mid-request.
3. `WRONGTYPE` on a key holding an unexpected type.
4. Serializer mismatch when reading legacy data.
5. Cluster `CROSSSLOT` if production uses Redis Cluster.
6. ACL `NOAUTH`/`NOPERM` in an isolated test environment.
7. Redis memory pressure under controlled conditions.
8. Reactive pipeline timeout/fallback.
9. `CacheErrorHandler` behavior.

Final exception types depend on driver/version, so tests should assert **business policy and data correctness**, not just exact message strings.

### 20.3. StepVerifier for Reactive Code

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> result = reactiveCacheGateway.get("product:101");

StepVerifier.create(result)
        .expectNext("fallback-data")
        .verifyComplete();
~~~

`reactiveCacheGateway` here is an application class implementing fallback; the test fixture defines the data and source. When errors should propagate, use `expectErrorMatches(...)` for the expected subtype.

### 20.4. Testing the "Write Executed but Reply Lost" Scenario

A mandatory test for sensitive business logic should simulate:

~~~text
Redis receives and runs INCR
Client times out before receiving the reply
Retry is triggered
Business outcome still increments only once (if required by contract)
~~~

A mock that always throws before sending the command does not prove this scenario. Test the idempotent operation protocol where side effects occur.

## 21. Common Mistakes

### 21.1. Catching DataAccessException and Returning Null for Everything

Wrong because it confuses connection failures with key misses and swallows mapping/schema errors.

### 21.2. Retrying Every TransientDataAccessException

Wrong for commands that may have caused side effects before timing out. Always evaluate the command and idempotency.

### 21.3. Assuming RedisConnectionFailureException Means the Server Is Definitely Dead

Not certain: it could be DNS, network, TLS, cluster topology, or client connectivity. Check the cause and metrics.

### 21.4. Treating RedisSystemException as Always a Temporary Infrastructure Error

Wrong: it can wrap `WRONGTYPE`, `CROSSSLOT`, `NOAUTH`/`NOPERM`, or invalid command usage.

### 21.5. Treating WRONGTYPE as Purely a Serializer Problem

Wrong: `WRONGTYPE` is a Redis data type mismatch; a serializer mismatch causes different decoding errors. Both can occur together when namespaces change.

### 21.6. Treating QueryTimeoutException as Proof a Write Failed

Wrong: Redis may have executed the command before the reply was lost.

### 21.7. Mapping Every DataAccessException to HTTP 503

Wrong: code bugs, ACL/schema issues, and business conflicts require different handling.

### 21.8. Assuming @Cacheable Automatically Fails Open

Not by default. `CacheErrorHandler` can be configured, yet get/put/evict need distinct policies.

### 21.9. Assuming try/catch Around Mono Creation Catches Redis I/O Errors

False for errors emitted at subscription time. Use Reactor error operators.

### 21.10. Assuming Pipelines or Transactions Fully Roll Back on Exception

Wrong: Redis has its own semantics; multiple commands may have already executed.

### 21.11. Dropping the Cause When Wrapping Exceptions

If you convert to a custom exception without keeping the cause, diagnosing driver/server errors becomes much harder.

### 21.12. Retry Storms When Redis Is Overloaded

Unbounded retries spike latency and CPU. Use backoff, jitter, circuit breakers, and concurrency limits.

## 22. Frequently Asked Questions

**Q1. Is DataAccessException a checked exception?**

No. It belongs to the `RuntimeException` hierarchy via `NestedRuntimeException`.

**Q2. Is DataAccessException only for relational databases?**

No. Spring Data Redis also uses this exception hierarchy for many Redis access errors.

**Q3. Is RedisConnectionFailureException a subtype of TransientDataAccessException?**

In the standard Spring Data Redis hierarchy, it extends `DataAccessResourceFailureException`, which is in the non-transient resource error branch. Yet the underlying disconnect may still recover; retry policy should not depend purely on branch labels.

**Q4. Does RedisSystemException mean the Redis process has a critical bug?**

Not necessarily. It is typically an uncategorized Redis-specific error that can wrap an application command error.

**Q5. Should QueryTimeoutException be retried automatically?**

For `GET`, a short retry may be safe; for `INCR`/`LPUSH`/`XADD`, idempotency/reconciliation is required first.

**Q6. Does GET on a missing key throw an exception?**

Normally Redis `GET` on a missing key returns nil; Spring's imperative template returns `null`, while the reactive API returns an empty publisher.

**Q7. Which class should I catch for WRONGTYPE?**

There is no guarantee of a single Spring class across all drivers/versions. Inspect the actual exception and root Redis error reply, then fix the type/schema.

**Q8. Can CROSSSLOT be fixed by increasing the Redis timeout?**

No. You must fix the multi-key operation/hash slots or use independent commands if atomicity is not needed.

**Q9. Should I catch raw Lettuce exceptions or DataAccessException?**

Through Spring Data Redis abstractions, prefer Spring exceptions once translated. When using a raw driver, handle driver exceptions in an adapter.

**Q10. If Redis is only a cache, can I swallow all errors?**

You should not. You can fail open in a controlled way for connectivity/timeouts; serialization, eviction, and schema errors need separate metrics/recovery so bad data is not served long-term.

**Q11. When does ReactiveRedisTemplate throw exceptions?**

Many Redis I/O errors are emitted when the publisher is subscribed to, as Reactor error signals. Input validation errors may be thrown synchronously earlier.

**Q12. Does CacheErrorHandler apply to direct RedisTemplate calls?**

No. It applies to the Spring Cache abstraction and its cache operations.

**Q13. Does MULTI/EXEC roll back prior commands when one command inside EXEC fails?**

Redis does not roll back already-executed commands like SQL. Understand transaction semantics and error results.

**Q14. Can Spring Retry be used with Redis?**

Yes, provided exception filters, backoff, timeouts, and retry limits are tailored to command semantics. Do not apply a single policy to all writes.

**Q15. Why do we need the root cause if we already have a Spring subtype?**

Because the translator may group multiple Redis server errors into `RedisSystemException`. The cause helps distinguish schema, permission, OOM, and cluster errors.

**Q16. Does Spring Boot automatically retry all Redis commands?**

Do not assume so. The driver may reconnect/reroute, but application-level retry and idempotency are separate responsibilities.

## 23. Redis Error Handling Implementation Checklist

1. **Identify the API:** `RedisTemplate`, `RedisCacheManager`, Repository, `ReactiveRedisTemplate`, or raw driver.
2. **Distinguish key misses from Redis unavailability.**
3. **Recognize subtypes:** `RedisConnectionFailureException`, `QueryTimeoutException`, `RedisSystemException`, and related DAO exceptions.
4. **Preserve the cause chain** when wrapping exceptions.
5. **Analyze the Redis command** before deciding to retry.
6. **Never blindly retry writes with side effects** such as `INCR`/`LPUSH`/`XADD`.
7. **Check key type/serializer** on `WRONGTYPE` or decoding failures.
8. **Check hash slots** on `CROSSSLOT` in a cluster.
9. **Check ACLs/credentials** when the server returns `NOAUTH`/`NOPERM`.
10. **Measure memory/capacity** on `OOM` or `maxclients`.
11. **Use bounded retries**, backoff, jitter, circuit breakers, and overall timeouts.
12. **Fall back only when business logic permits**, especially for caches with an authoritative source.
13. **Do not swallow cache invalidation errors** when strict freshness is required.
14. **Handle reactive error signals** and never block on the event loop.
15. **Do not assume transactions/pipelines fully roll back** after an exception.
16. **Use idempotency and reconciliation** when write outcomes are unclear.
17. **Test Redis outages, timeouts, `WRONGTYPE`, ACLs, Cluster, and serializer mismatches.**
18. **Emit structured logs/metrics** with redaction and bounded label cardinality.
19. **Avoid leaking internal messages** via HTTP error responses.
20. **Verify against your Spring Data Redis/driver versions** whenever tying policies to specific exception translations.

## 24. Summary

`DataAccessException` is Spring's unified exception hierarchy for data access errors. Spring Data Redis can translate errors from Lettuce/Jedis into subtypes such as:

- **`RedisConnectionFailureException`**: Redis connection/resource access errors.
- **`QueryTimeoutException`**: command timeouts on applicable translation paths.
- **`RedisSystemException`**: uncategorized Redis-specific errors.
- Other `DataAccessException` types depending on the API and version.

**The exception hierarchy is a classification tool, not an automatic retry policy.** When a Redis command times out, a write may already have occurred; when Redis reports `WRONGTYPE`/`CROSSSLOT`/`ACL`/`OOM`, retrying the exact same operation usually does not resolve the cause. For caches, falling back to the authoritative source may be allowed; for critical business data, protect idempotency, consistency, and reconciliation.

For Spring Boot, isolate Redis logic in clear adapters, record root causes/operations, design retries/fallbacks around command semantics, and properly handle differences among synchronous exceptions, Spring Cache errors, and Reactor error signals. This keeps Redis errors from silently turning into data corruption or duplicate writes.

## References

- Spring Framework — [DataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataAccessException.html).
- Spring Framework — [TransientDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/TransientDataAccessException.html).
- Spring Framework — [NonTransientDataAccessException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/NonTransientDataAccessException.html).
- Spring Framework — [QueryTimeoutException API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/QueryTimeoutException.html).
- Spring Data Redis — [RedisConnectionFailureException API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/RedisConnectionFailureException.html).
- Spring Data Redis — [RedisSystemException API](https://docs.spring.io/spring-data/redis/docs/current/api/org/springframework/data/redis/RedisSystemException.html).
- Spring Data Redis — [RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- Spring Data Redis — [Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html).
- Spring Framework — [Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html).
- Redis — [Command reference](https://redis.io/docs/latest/commands/).
- Redis — [Transactions](https://redis.io/docs/latest/develop/interact/transactions/).
- Redis — [Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/).
