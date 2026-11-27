# Classifying Connection, Timeout, Command, and Serialization Errors

When a Spring Boot application works with Redis, an error observed at the service layer can originate from many places: failing to establish a TCP/TLS connection, an active connection dropping, a command running past its wait deadline, Redis rejecting a command due to the wrong data type or access permissions, or the application failing to convert a Java object into bytes stored in Redis. These situations **should not be handled with a generic `catch (Exception) { retry(); }`**, because each category has different causes, levels of certainty, and recovery strategies.

Spring Data Redis provides `RedisTemplate`, `StringRedisTemplate`, the reactive API, and the repository/cache layer on top of Redis drivers such as **Lettuce** or **Jedis**. An exception at the application layer does not necessarily have the exact same class name as the driver exception: Spring may perform **exception translation** into the `DataAccessException` hierarchy, while a serializer error may go through a different branch. Therefore, a well-operated system needs to inspect the **cause chain**, operation context, and telemetry data before drawing conclusions.

This lesson focuses on four error groups: **connection**, **timeout**, **command**, and **serialization**. In addition to identification, it proposes logging/metrics practices, bounded retry policies, treating Redis as a best-effort cache, distinguishing signals in Reactor, and practical testing examples. The code snippets use Java 21, Spring Boot 3.x, and Spring Data Redis; different driver or Spring versions may produce different concrete exception types, so do not rely solely on a single class name.

## 1. Viewing Errors by Layer in the Redis Call Path

A request from the application can pass through these steps:

~~~text
Controller / Scheduled job / Consumer
                  |
                  v
             Business service
                  |
                  v
     RedisTemplate / RedisCache / Repository
                  |
                  v
           Serializer / Mapper
                  |
                  v
        RedisConnectionFactory
                  |
                  v
             Lettuce / Jedis
                  |
           DNS, TCP, TLS, ACL
                  |
                  v
              Redis server
                  |
        Receive command and execute
                  |
                  v
             Redis response
                  |
                  v
          Deserialize result
                  |
                  v
            Business service
~~~

Depending on where the failure occurs, the symptoms differ:

- Cannot connect to Redis: usually a **connection failure**.
- Sent a command but timed out waiting for a response: usually a **command timeout**, though it is unknown whether the server already executed the command.
- Redis received the command and returned `-ERR WRONGTYPE` or `NOPERM`: a **command execution error**; simply reconnecting will not fix the payload or ACL.
- Redis returned valid bytes but Java cannot read the object due to a wrong serializer/schema: a **deserialization error**.

A single failure can involve multiple layers. For example, a Redis failover drops connections, in-flight calls end with timeouts, and subsequent commands receive `READONLY` because the client still points to the old replica. Therefore, **classification is a tool for deciding action**, not an assumption that every incident has only one root cause.

## 2. Quick Classification Table

| Group | Typical Symptoms | Common Causes | Priority Action |
| --- | --- | --- | --- |
| **Connection** | Cannot open socket, connection refused/reset, DNS/TLS error | Redis down, firewall, wrong host/port, pool exhausted, failover | Check endpoint, TLS, connectivity, and topology; bounded retry if transient |
| **Timeout** | Command does not return within deadline; request cancelled due to timeout | Network latency, overloaded Redis, slow commands, command queue, pool wait | Measure wait phase, command type, and likelihood of execution; do not blindly retry non-idempotent commands |
| **Command** | `WRONGTYPE`, `READONLY`, `NOAUTH`, `NOPERM`, `CROSSSLOT`, `ERR` | Wrong data, wrong command, missing permissions, stale topology, server limits | Fix key/schema/ACL/routing; only retry when analysis shows a transient error |
| **Serialization** | Cannot encode/decode key/value, JSON/class/version error | Different serializers, schema changes, corrupted data | Check serializer/schema/payload; fix data or run migration, avoid continuous retries |

Diagnostic example:

~~~text
GET cache:product:42
  |
  +-- Connection refused --------> CONNECTIVITY
  |
  +-- Command timed out ---------> TIMEOUT
  |
  +-- WRONGTYPE -----------------> COMMAND
  |
  +-- Bytes returned but bad JSON -> SERIALIZATION
  |
  +-- Redis returns nil ----------> CACHE MISS, NOT AN ERROR
~~~

The last point is crucial: **a missing key is not an exception**. With `StringRedisTemplate.opsForValue().get(key)`, a missing key typically returns `null`; with `ReactiveStringRedisTemplate`, the operation may complete with `Mono.empty()`. It should only be treated as an error if the application's **business logic** requires the key to exist, not as a Redis connection or command failure.

## 3. Common Exception Classes

When using Spring Data Redis, there are two groups of exceptions to know:

1. **Spring abstraction**, which typically surfaces from template or repository APIs after exception translation.
2. **Redis driver**, which is typically seen in `cause` or when calling Lettuce/Jedis directly.

Some notable classes:

| Class / Group | Layer | Usually Indicates |
| --- | --- | --- |
| `org.springframework.data.redis.RedisConnectionFailureException` | Spring Data Redis | Unable to establish or use a Redis connection |
| `org.springframework.dao.QueryTimeoutException` | Spring DAO | Data operation exceeded the applied timeout |
| `org.springframework.data.redis.RedisSystemException` | Spring Data Redis | Redis error not mapped to a more specialized DAO exception |
| `org.springframework.dao.InvalidDataAccessApiUsageException` | Spring DAO | Invalid API/command usage for the situation |
| `org.springframework.data.redis.serializer.SerializationException` | Spring Data Redis | Serialization or deserialization failure |
| `org.springframework.dao.DataAccessException` | Spring DAO | Base class of many translated data access exceptions |
| `io.lettuce.core.RedisConnectionException` | Lettuce | Connection establishment/usage error at the driver |
| `io.lettuce.core.RedisCommandTimeoutException` | Lettuce | Redis command exceeded timeout at the driver |
| `io.lettuce.core.RedisCommandExecutionException` | Lettuce | Server returned an error while executing a command |

These are **common examples**, not a mandatory one-to-one mapping table. Depending on the call path, Spring Data Redis/Jedis/Lettuce version, and specific error type, a server error may be translated into `RedisSystemException` or another `DataAccessException` subclass, with the driver exception wrapped inside.

### Exception Translation Does Not Change the Nature of the Error

Example cause chain structure:

~~~text
RedisSystemException
  └── RedisCommandExecutionException
        └── message: WRONGTYPE Operation against a key
                    holding the wrong kind of value
~~~

In another application, the same incident might be wrapped in a different class. If you only check:

~~~java
if (error.getClass() == RedisSystemException.class) {
    // Are all of these transient system errors?
}
~~~

it is very easy to misclassify a `WRONGTYPE` error as an infrastructure failure and retry forever. Instead, use the **high-level exception type, cause chain, and reliable Redis error code/message** to identify it.

Do not parse free-form stack trace strings as the sole classification method: messages can change across server/driver versions, get wrapped, or be truncated. For standard Redis error messages such as `WRONGTYPE` and `NOPERM`, you can use them as an **additional signal** after inspecting the cause type.

## 4. Connection Errors: Redis Cannot Communicate Reliably

### 4.1. Common Scenarios

- The Redis process is not running or is restarting.
- Wrong hostname, DNS cannot resolve, wrong port, firewall, or network policy blocking traffic.
- TCP connection reset because Redis/client/proxy closed the socket.
- Wrong TLS mode or certificate when the environment requires TLS.
- Redis failover: the old primary died, a replica was promoted, and the client is using an old endpoint/connection.
- The pool has no available connections or the application creates too many connections, sometimes manifesting as a timeout while acquiring a connection.
- A Sentinel/Cluster environment advertises Redis addresses that the application cannot reach across NAT/container networks.

A typical connection error may be represented by Spring as:

~~~text
org.springframework.data.redis.RedisConnectionFailureException:
Unable to connect to Redis
Caused by: io.lettuce.core.RedisConnectionException:
Unable to connect to redis.internal:6379
~~~

The `Unable to connect` message confirms that the Redis access layer failed, but it **does not prove that the Redis server is down**. You must distinguish server downtime from DNS, routing, TLS, ACL, and client resource exhaustion.

### 4.2. Non-Destructive Diagnosis

From the exact environment **where the application runs**, check:

~~~bash
# Can the domain name be resolved?
nslookup redis.internal

# Only to check if Redis is ready to accept commands if authorized.
redis-cli -h redis.internal -p 6379 PING

# If TLS is deployed, use the properly configured TLS connection method:
redis-cli --tls -h redis.internal -p 6379 PING
~~~

These commands are illustrative: use the proper port, TLS/ACL settings, and tools available in your environment. Do not put passwords on the command line or expose credentials in shared logs; prefer a secret manager and your infrastructure's secure authentication mechanisms.

On the Redis side, inspect server logs, node health, connected client counts, connection limits, and metrics. If running Sentinel/Cluster, check the **current role and topology**, not just whether an old Redis host responds.

### 4.3. Should You Retry?

A transient connection error may recover after reconnection, but retries must have:

- A finite number of attempts or deadline.
- Backoff and jitter so multiple instances do not flood Redis together after a restart.
- Separate timeouts for each attempt and for the overall request/job.
- Idempotency of the retried operation.
- Metrics to distinguish "retried and succeeded" from "no incident occurred."

Do not automatically turn every connection error into a "cache miss." If Redis stores balances or coordination locks, losing the connection may require **failing closed**: rejecting the operation rather than bypassing critical data. If Redis is only a regenerable cache, a controlled fallback to the database may be appropriate.

## 5. Timeout Errors: The Command Did Not Necessarily Fail on the Server

A timeout is an **observation boundary**: the caller did not receive a result within the allotted time. That does not necessarily mean Redis did not execute the command.

Distinguish at least four types of timeouts:

| Type | What Is Being Waited On? | Symptoms and Measurement Direction |
| --- | --- | --- |
| **Connect timeout** | Establishing TCP/TLS/connection to Redis | Check network, DNS, TLS, and endpoint |
| **Command timeout** | Command sent/queued by the driver without timely result | Check Redis latency, command, driver queue, and network |
| **Pool acquisition timeout** | Waiting to borrow a connection from the pool | Check pool size, concurrent requests, long-held connections |
| **Application deadline** | A sequence of operations or HTTP request exceeds SLA | Check total cost and per-layer timeouts |

In Spring, `QueryTimeoutException` can represent a command timeout after translation. In Lettuce, `RedisCommandTimeoutException` may appear in the cause. If accessing the driver directly, the error may surface without going through Spring DAO translation.

### Timeouts Do Not Have a Single Cause

For example:

~~~text
GET cache:big-value
        |
        +-- Driver waits in command queue
        |
        +-- Network is delayed
        |
        +-- Redis is running another expensive command
        |
        +-- Redis builds a large response, output buffer backs up
        |
        +-- Client reads/deserializes the response slowly
        |
        v
   Deadline expires before a result arrives
~~~

Do not immediately raise the timeout from 1 second to 60 seconds when you see a failure. If Redis is congested due to a high-complexity command, excessive pipelining, or low memory, increasing the timeout may simply cause more requests to wait longer and worsen the overload.

### Spring Boot Timeout Configuration

An illustrative configuration:

~~~yaml
spring:
  data:
    redis:
      host: redis.internal
      port: 6379
      connect-timeout: 2s
      timeout: 3s
~~~

`connect-timeout` controls the time to establish a connection, while `timeout` is the Redis operation timeout according to the corresponding Spring Boot/driver configuration. The values above are examples only; actual choices depend on the network, command types, and application SLA.

With Lettuce, you can configure the command timeout in Java:

~~~java
import java.time.Duration;
import org.springframework.data.redis.connection.lettuce.LettuceClientConfiguration;

LettuceClientConfiguration client =
    LettuceClientConfiguration.builder()
        .commandTimeout(Duration.ofSeconds(3))
        .build();
~~~

This snippet configures the client and needs to be combined with `RedisStandaloneConfiguration`, `RedisSentinelConfiguration`, or the appropriate connection factory type. If Spring Boot auto-configuration is already active, do not create a second inconsistent connection factory bean.

### Dangerous Consequences of Retrying

Suppose:

~~~text
Client sends INCR orders:count
          |
          v
Redis increments from 40 -> 41
          |
          v
Response is lost / arrives after deadline
          |
          v
Client sees timeout
          |
          v
Client retries INCR -> 42
~~~

The final result increments **twice**, even though the business intent was a single increment. Therefore, when timing out after a command may have been sent, treat the state as **unknown** and evaluate idempotency.

If the requirement is "mark a job as processed only once," use an idempotency key, a unique constraint, or a conditional operation where the data is stored. `retry(3)` does not guarantee this by itself.

## 6. Command Execution Errors: Redis Responded but Rejected the Operation

Redis can return an **error reply** for a command that was valid at the transport level but did not execute successfully. In Lettuce, some errors of this kind are represented by `RedisCommandExecutionException`.

Errors to recognize:

| Typical Redis Message | Context | Handling Direction |
| --- | --- | --- |
| `WRONGTYPE` | Calling a list/hash/set operation on a key storing another type | Check key conventions, namespaces, and data structures; do not blindly retry |
| `ERR unknown command` | Command not supported by Redis/version/plugin | Check Redis/module version and API usage |
| `ERR wrong number of arguments` | Sent wrong command arguments | Fix command construction or compatibility |
| `NOAUTH` / `WRONGPASS` | Unauthenticated or invalid credentials | Fix credentials/configuration; do not retry infinitely |
| `NOPERM` | ACL does not allow the user to execute the command/key | Grant proper permissions following least privilege; do not bypass ACL |
| `READONLY` | Writing to a replica that does not accept writes | Check node role and Sentinel/Cluster routing after failover |
| `CROSSSLOT` | Multi-key command across different slots in Cluster | Design appropriate hash slot/key layout |
| `MOVED` / `ASK` | Cluster needs redirection to another node/slot | Check cluster-aware driver and topology refresh |
| `BUSY` | Redis is executing a script or bounded blocking task | Investigate script/load; avoid aggressive retries |
| `OOM` | Redis rejects writes due to memory limit/policy | Check memory, eviction policy, and data size |
| `NOSCRIPT` | Script SHA is not yet in the node's script cache | Use a script evaluation mechanism with proper fallback |

Distinguish **command errors recoverable after a topology change** (e.g., `READONLY` during failover) from **errors requiring data or configuration fixes** (`WRONGTYPE`, `NOPERM`). Retrying the same invalid command repeatedly only adds load and obscures the root cause.

### 6.1. `WRONGTYPE` Example

A key has been stored as a String:

~~~redis
SET demo:wrongtype "hello"
~~~

But the application reads it as a Redis List:

~~~redis
LLEN demo:wrongtype
~~~

Redis returns an error like:

~~~text
WRONGTYPE Operation against a key holding the wrong kind of value
~~~

In Spring Data Redis:

~~~java
redis.opsForValue().set("demo:wrongtype", "hello");
Long size = redis.opsForList().size("demo:wrongtype");
~~~

The error is not caused by DNS or a slow Redis server; the existing key is of **type String**, whereas `LLEN` only works on a List. You must clarify why two components use the same key name while expecting different data types.

How to prevent it:

- Namespace keys by data type, e.g., `cache:product:42` and `queue:invoice:pending`.
- Never use a single key for two different Redis structures.
- Define serializer and schema contracts between producers and consumers.
- During migrations, perform a controlled key/version transition rather than overwriting the same key with a different type.

### 6.2. `READONLY` Errors and Failover

If the application pins an old host as primary while Sentinel has already promoted another node, a `SET` command on the old node—now a replica—will be rejected. The fix is to **update discovery/topology and reconnect to the new primary**, not to delete keys or change serializers.

With Redis Cluster, the client must support `MOVED`/`ASK` to route to the right hash slot. A `RedisStandaloneConfiguration` pointing to an arbitrary node cannot replace a cluster-aware configuration.

### 6.3. ACLs and Authentication

`NOAUTH` or `NOPERM` indicates a security/access-control configuration error. Never automatically fall back to a higher-privilege Redis account to "keep the system running" without security approval. You need to identify the proper Redis user, key pattern, and command categories required.

In logs, record only the **error category code, command family, and sanitized endpoint**. Do not log passwords, tokens, payloads containing personal data, or connection URIs with credentials.

### 6.4. Redis Script and Transaction Errors

A failing script or command may have already performed partial changes before encountering an error, depending on the script's content. Lua scripts run exclusively and sequentially on Redis while executing, but Redis **does not automatically roll back writes executed prior to an error inside a script**. Similarly, a Redis `MULTI/EXEC` transaction is not equivalent to a relational database rollback for all runtime errors.

Do not conclude that every command error means the data is completely untouched. When a multi-step operation fails, evaluate idempotency, state reconciliation, and compensation.

## 7. Serialization/Deserialization Errors

Redis stores keys and values as bytes. Spring Data Redis uses a `RedisSerializer` to convert Java objects into bytes before sending commands and to convert returned bytes back into Java objects after reading.

Example of two systems sharing the same Redis key while using different serializers:

~~~text
Service A:
  StringRedisTemplate
  "cache:user:42" → UTF-8 bytes of a JSON string

Service B:
  RedisTemplate<String, User>
  Value serializer is JDK serialization
  Reads same key → cannot deserialize into Java object
~~~

There is no Redis connection or command error here; the server returned the **exact bytes stored**, but client B **misinterpreted the format**.

### Common Causes

1. One service uses `StringRedisSerializer`, while another uses `JdkSerializationRedisSerializer` or a JSON serializer for the same namespace.
2. The JSON schema changed: field names, data types, enums, or date/time formats changed without migration.
3. Old data does not contain metadata required by the current serializer.
4. A Java class was moved to a different package or is no longer compatible with previously JDK-serialized values.
5. Changing the key serializer causes the application to query **a different byte key**, manifesting as a cache miss rather than necessarily throwing an exception.
6. A producer writes a payload with the wrong encoding or byte data that no longer matches the schema contract.
7. Jackson/`ObjectMapper` is missing a module for a specialized data type, or polymorphic type configuration is incompatible.

With many Spring Data Redis serializers, errors may be represented as `org.springframework.data.redis.serializer.SerializationException`, with a cause from Jackson, Java serialization, or another codec. If service code parses JSON manually outside `RedisTemplate`, the exception may come from the JSON library rather than Spring Data Redis.

### 7.1. Key Serializer and Value Serializer Are Two Separate Decisions

An illustrative configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;
import org.springframework.data.redis.serializer.GenericJackson2JsonRedisSerializer;

@Bean
RedisTemplate<String, Object> jsonRedisTemplate(
        RedisConnectionFactory factory) {
    RedisTemplate<String, Object> template = new RedisTemplate<>();
    template.setConnectionFactory(factory);
    template.setKeySerializer(new StringRedisSerializer());
    template.setHashKeySerializer(new StringRedisSerializer());
    template.setValueSerializer(
        new GenericJackson2JsonRedisSerializer()
    );
    template.setHashValueSerializer(
        new GenericJackson2JsonRedisSerializer()
    );
    template.afterPropertiesSet();
    return template;
}
~~~

This example uses a JSON serializer to illustrate key/value formatting; in production, choose an appropriate way to store type metadata, allowlist data types, version namespaces, and define a migration policy. Do not enable arbitrary type deserialization for payloads coming from untrusted sources.

Do not point a new JSON serializer configuration at millions of old keys stored with JDK serialization without a migration plan. Redis **does not know Java schemas**, so data compatibility is the application's responsibility.

### 7.2. Example Handling Unreadable Cache Values

If Redis is only a cache that can be refreshed from the database, you can choose a concrete strategy:

~~~text
GET cache:user:v2:42
        |
        v
Redis returns bytes
        |
        +-- Decode OK → use data
        |
        +-- SerializationException
                   |
                   v
          Record metric + log safe key identifier
                   |
                   v
          Determine whether this cache is
          completely regenerable?
                /          \
              Yes           No
               |             |
               v             v
       Controlled eviction  Report error and handle
       of corrupt key       migration/incident
               |
               v
        Load source data and re-cache
~~~

Do not automatically delete every key as soon as a deserialization error occurs. When Redis is the **primary data source** or the payload needs investigation, deleting the key can destroy evidence or irrecoverable data. Distinguish between a best-effort cache and persistent business state.

### 7.3. Migrating with Versioned Namespaces

One way to reduce collisions between old and new schemas:

~~~text
cache:user:v1:42   ← old JSON format
cache:user:v2:42   ← new JSON format
~~~

During transition:

1. The new application reads/writes `v2` using a consistent serializer.
2. If migration is needed, a separate job reads `v1` using the old serializer and converts it in a controlled way to `v2`.
3. Use TTLs or a deletion policy once you confirm no consumers of `v1` remain.
4. Monitor deserialization error counts and cache misses to detect post-deployment impact.

For cache data, versioned namespaces are usually simpler than trying to read both formats from the same key. For critical business data, migration requires additional reconciliation and integrity checks.

## 8. Classifying Errors at the Application Layer Using the Cause Chain

Not every application needs a complex classification system. However, for services with different retry, fallback, and metric requirements, a small class makes handling more consistent than matching error message strings inside every method.

The example below uses Spring Data Redis and **Lettuce**. If your project uses Jedis, replace the driver-specific detection with the corresponding exception types; Spring's `DataAccessException` types remain useful.

~~~java
package com.example.redis.error;

import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.Set;

import io.lettuce.core.RedisCommandExecutionException;
import io.lettuce.core.RedisCommandTimeoutException;
import io.lettuce.core.RedisConnectionException;
import org.springframework.dao.InvalidDataAccessApiUsageException;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.serializer.SerializationException;
import org.springframework.stereotype.Component;

@Component
public final class RedisFailureClassifier {

    public enum Kind {
        CONNECTION,
        TIMEOUT,
        COMMAND,
        SERIALIZATION,
        UNKNOWN
    }

    public Kind classify(Throwable error) {
        if (hasCause(error, SerializationException.class)) {
            return Kind.SERIALIZATION;
        }
        if (hasCause(error, QueryTimeoutException.class)
                || hasCause(
                    error, RedisCommandTimeoutException.class)) {
            return Kind.TIMEOUT;
        }
        if (hasCause(error, RedisConnectionFailureException.class)
                || hasCause(error, RedisConnectionException.class)) {
            return Kind.CONNECTION;
        }
        if (hasCause(
                    error, RedisCommandExecutionException.class)
                || hasCause(
                    error, InvalidDataAccessApiUsageException.class)) {
            return Kind.COMMAND;
        }
        return Kind.UNKNOWN;
    }

    private static boolean hasCause(
            Throwable error, Class<? extends Throwable> type) {
        Set<Throwable> visited = Collections.newSetFromMap(
            new IdentityHashMap<Throwable, Boolean>()
        );

        for (Throwable current = error;
             current != null && visited.add(current);
             current = current.getCause()) {
            if (type.isInstance(current)) {
                return true;
            }
        }
        return false;
    }
}
~~~

### What This Class Deliberately Does Not Do

- Does not treat **every** `RedisSystemException` as a command error: this class can wrap multiple situations where inspecting the cause is required.
- Does not treat **every** `RuntimeException` as a Redis error: a `NullPointerException` from buggy application code is not a Redis timeout.
- Does not automatically retry based on `Kind`: both the nature of the error and the **operation type** matter.
- Does not distinguish every TLS/DNS/pool error by subtype: doing so requires additional connection context and driver/infrastructure logs.
- Does not attempt to detect JSON errors when business code invokes `ObjectMapper` directly outside Spring's serializer; the layer performing JSON parsing needs its own classification policy.
- Does not use error messages as a stable API contract; when you need to identify `WRONGTYPE`/`NOPERM` at the command layer, you can extract the error code after confirming `RedisCommandExecutionException`.

Using `IdentityHashMap` in `hasCause` prevents an infinite loop if an unusual exception has a cyclic cause chain referencing itself. This is purely a read-only exception utility; it does not alter or swallow errors.

### Timeout During Connect Phase or Command Phase?

If a driver exception indicates connection failure with a timeout cause, automatic classification alone may not tell **when** the failure happened. Therefore, logs should include `operation=connect` or `operation=GET`, cache/service name, configured timeout, and a sanitized endpoint/topology.

Do not decide to retry a write command merely because the classifier returned `TIMEOUT`. A command may have already completed before the response was lost.

## 9. Handling Policy by Operation Type and Data Criticality

**Classifying an exception** and **making a business decision** are two distinct steps.

For example, when Redis holds a product cache:

- Connection failure: can read directly from the database if the cache is best-effort.
- Command timeout: can fall back, but must throttle the traffic hitting the database.
- `WRONGTYPE`: fix key naming/schema; do not retry forever.
- Serialization error: can fix/migrate the cache key, but never silently delete critical business data.

For example, when Redis holds an order counter acting as the source of truth:

- Connection error: no reliable value to return.
- Command timeout when sending `INCR`: unknown whether the counter incremented.
- Wrong key type: schema error requiring intervention; do not auto-reset the counter.
- Serialization error: protect the data and investigate; do not treat as an empty key.

A policy table:

| Data Type | CONNECTION / TIMEOUT | COMMAND | SERIALIZATION |
| --- | --- | --- | --- |
| Regenerable cache | Bounded fallback and record metric | Investigate schema/role; fall back only if permitted | Consider controlled eviction of corrupt key |
| Session/authentication | Must fail-safe per security policy; avoid granting access when Redis errors | Check ACL, role, and key schema | Never treat decode failure as a valid session |
| Business counter/ledger | May need to report unknown outcome and reconcile | Stop invalid operation instead of auto-fixing data | Preserve data, fix migration |
| Distributed lock | Never treat timeout as "definitely did not acquire lock" | Check primary/ACL/script | Token encoding must be consistent |
| Queue/Stream consumer | Preserve retry/ACK state per contract; do not blindly ACK | Investigate group, key type, ACL, slot | Never ACK an unprocessed message |

There is no single fallback right for every Redis usage. In some applications Redis is an **expendable cache**; in others Redis is a **critical coordination component**. Policy must be grounded in data preservation requirements and business correctness.

## 10. Error Handling in Synchronous Services

Example of a cache-aside service using `StringRedisTemplate`. If Redis is unreachable or times out, it loads data from the authoritative source. If a command or serialization error occurs, the service **does not mask the error as a fake cache miss**:

~~~java
package com.example.redis.error;

import java.util.Objects;
import java.util.function.Supplier;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.QueryTimeoutException;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductReadService {

    private static final Logger log =
        LoggerFactory.getLogger(ProductReadService.class);

    private final StringRedisTemplate redis;

    public ProductReadService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public String getOrLoad(
            String id, Supplier<String> loadFromDatabase) {
        Objects.requireNonNull(id);
        Objects.requireNonNull(loadFromDatabase);

        String key = "cache:product:v2:" + id;

        try {
            String hit = redis.opsForValue().get(key);
            if (hit != null) {
                return hit;
            }
        } catch (RedisConnectionFailureException
                 | QueryTimeoutException error) {
            log.warn(
                "Redis cache unavailable for product lookup, type={}",
                error.getClass().getSimpleName()
            );
            // Redis is a best-effort cache, not the primary source.
        }

        return Objects.requireNonNull(loadFromDatabase.get());
    }
}
~~~

This example intentionally only **reads the cache** and falls back without writing back to the cache. If you need to populate the cache after loading data, isolate Redis write errors so a cache outage does not break a successful database response, **only** in business flows where best-effort caching is allowed.

### Why Not Write `catch (Exception)`?

~~~java
// Anti-pattern: hides programming or data errors too.
try {
    return redis.opsForValue().get(key);
} catch (Exception error) {
    return database.get(key);
}
~~~

This snippet can hide schema bugs, `WRONGTYPE`, code null pointers, incompatible serializers, or misconfigured Redis ACLs. When the error persists, the database may absorb the entire load while nobody realizes the cache is broken for a fixable reason.

On the other hand, catching only the two exception types in the earlier example does not cover every driver/version. In applications with diverse failure modes, you can use `RedisFailureClassifier` in a dedicated adapter layer and fall back only for permitted `Kind` values, after verifying how your real stack translates driver errors. **Do not blindly widen catch blocks** just because you want every error to be "handled."

### Errors During Writes: Do Not Lose the Primary Source Result

Suppose a request updates the database successfully and then writes to the cache:

~~~java
database.updateProduct(product);
redis.opsForValue().set(cacheKey, serializedProduct);
~~~

If Redis times out, the HTTP response may fail even though the database already committed. A client retrying the HTTP request could create duplicate side effects, depending on the business logic. Recognize that **a database commit and a cache write are two independent resources**:

- With cache-aside, you can invalidate the cache or write best-effort after commit.
- You can use an outbox/event to update the cache asynchronously if consistency requirements need a durable mechanism.
- Do not assume a Redis `set` automatically rolls back along with a JDBC transaction just because they are in the same Java method.

## 11. Errors in Reactive Redis: Reactor Error, Empty, and Timeout

The `ReactiveStringRedisTemplate` API returns `Mono`/`Flux`. Exceptions are emitted as `onError` signals when the publisher is subscribed to, rather than necessarily being thrown when constructing the publisher.

For example:

~~~java
Mono<String> cached =
    reactiveRedis.opsForValue().get("cache:product:42");
~~~

At the moment `cached` is assigned, Redis has not necessarily been accessed yet. If the reactive API returns `Mono.empty()` when the key does not exist, that is **not** `onError`. Operators must distinguish:

| Signal | Meaning | Appropriate Operator |
| --- | --- | --- |
| `onNext(value)` | Key has a value | `map`, `flatMap` |
| `onComplete` without `onNext` | Key does not exist | `switchIfEmpty` or `defaultIfEmpty` |
| `onError(connectionError)` | Redis unreachable | `onErrorResume` per policy |
| `onError(timeoutError)` | Operation exceeded timeout | Consider deadline, retry/fallback |
| `onError(serializationError)` | Unable to decode data | Report error / controlled migration |

### 11.1. Falling Back Only for Acceptable Errors

Example of a reactive service reading a cache whose primary data source is synchronous JDBC. The JDBC work is offloaded to `Schedulers.boundedElastic()` so it does not block the event loop:

~~~java
package com.example.redis.error;

import java.util.Objects;

import org.springframework.data.redis.core.ReactiveStringRedisTemplate;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Service
public class ReactiveProductReadService {

    private final ReactiveStringRedisTemplate redis;
    private final RedisFailureClassifier classifier;
    private final ProductDatabaseReader database;

    public ReactiveProductReadService(
            ReactiveStringRedisTemplate redis,
            RedisFailureClassifier classifier,
            ProductDatabaseReader database) {
        this.redis = redis;
        this.classifier = classifier;
        this.database = database;
    }

    public Mono<String> load(String id) {
        Objects.requireNonNull(id);
        String key = "cache:product:v2:" + id;

        Mono<String> source = Mono.fromCallable(
                () -> database.loadProductJson(id)
            )
            .subscribeOn(Schedulers.boundedElastic());

        return redis.opsForValue()
            .get(key)
            .onErrorResume(error -> {
                RedisFailureClassifier.Kind kind =
                    classifier.classify(error);

                if (kind == RedisFailureClassifier.Kind.CONNECTION
                        || kind == RedisFailureClassifier.Kind.TIMEOUT) {
                    return source;
                }
                return Mono.error(error);
            })
            .switchIfEmpty(source);
    }
}
~~~

`ProductDatabaseReader` in this example is a business interface/service with method `String loadProductJson(String id)`, not a built-in Spring Data Redis API. If this method returns `null`, `Mono.fromCallable` will complete empty; the service contract should explicitly define missing data rather than arbitrarily treating it as a Redis error.

Both `onErrorResume` and `switchIfEmpty` subscribe to `source` only when needed. Although declared in a variable, `Mono.fromCallable` is a cold publisher: the database call is deferred until subscription time.

The code does not automatically write back to Redis after falling back. If you want to add cache population, treat it as a best-effort step or give it a separate policy, rather than using `then` in a way that discards the data value unintentionally.

### 11.2. A Reactor Timeout Is Not Necessarily a Redis Command Timeout

~~~java
Mono<String> value = reactiveRedis.opsForValue()
    .get("cache:key")
    .timeout(java.time.Duration.ofMillis(800));
~~~

`Mono.timeout(...)` enforces a deadline at the **Reactor pipeline** layer. When the deadline expires, Reactor may emit `java.util.concurrent.TimeoutException`. This is not necessarily Lettuce's `RedisCommandTimeoutException` or Spring's `QueryTimeoutException`.

The two timeouts can differ:

~~~text
Lettuce command timeout = 3 seconds
Reactor Mono.timeout    = 800 milliseconds

T0      Subscriber starts GET
T0+800  Reactor stops waiting and emits TimeoutException
T0+...  Command on Redis side may still have executed
~~~

Cancelling a subscription or emitting a timeout at the HTTP layer **provides no rollback guarantee** for an already-sent command. Especially when executing a write command such as `INCR` or `XADD`, do not blindly retry simply because Reactor timed out.

If the application wants to treat a Reactor timeout as a distinct deadline type, add `java.util.concurrent.TimeoutException` to the classifier with a clear name like `APPLICATION_TIMEOUT`, instead of lumping every context into Redis command timeout.

### 11.3. Reactive Retry Filtered by Operation Type

For a **cache read** operation, you can apply a bounded number of retries with backoff:

~~~java
import java.time.Duration;
import reactor.util.retry.Retry;

Mono<String> read = reactiveRedis.opsForValue()
    .get("cache:product:v2:42")
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(80))
            .maxBackoff(Duration.ofMillis(400))
            .filter(error -> {
                var kind = classifier.classify(error);
                return kind == RedisFailureClassifier.Kind.CONNECTION
                    || kind == RedisFailureClassifier.Kind.TIMEOUT;
            })
    )
    .switchIfEmpty(Mono.just("(missing)"));
~~~

`Retry.backoff(2, ...)` allows at most two retry attempts **after the initial attempt**. It includes jitter/backoff and does not retry command/serialization errors per the classifier. If all attempts fail, the stream continues emitting the error; the service can add a fallback outside `retryWhen` if business rules permit.

This pattern is more suitable for low-side-effect `GET` calls. Do not copy it verbatim for `INCR`, `LPUSH`, or `XADD` without idempotency protection.

In a WebFlux Controller, **return the `Mono` to the framework** so the framework subscribes; avoid calling `block()` on the event loop or manually calling `subscribe()` and detaching errors from the HTTP request lifecycle.

## 12. Retrying: Command Type Matters More Than Exception Name

Suppose every timeout is classified as `TIMEOUT`. We still cannot apply a single retry policy across all commands:

| Operation | Retry on Lost Response | Reason |
| --- | --- | --- |
| `GET key` | Usually safe for bounded retries | Re-reading does not increment/mutate state, though result may have changed |
| `EXISTS key` | Usually retryable | Key state may change between attempts |
| `SET key value` | Only conditionally safe | Writing the same value may be idempotent, yet can still affect TTL/overwrite newer changes |
| `DEL key` | Usually fine if goal is deleting key | Returned deleted count may differ |
| `SADD key member` | Idempotent for membership | Returned newly added count may differ |
| `INCR` / `DECR` | Do not blindly retry | First command may have already modified the counter |
| `LPUSH` / `RPUSH` | Do not blindly retry | May insert duplicate elements |
| `XADD stream * ...` | Do not blindly retry | May create another entry with a different Stream ID for the same logical event |
| `SET key token NX PX ttl` | Needs dedicated lock policy | Timeout may occur after the lock was already created |
| `MULTI/EXEC` | Needs business reconciliation | Connection timeout may happen at an ambiguous outcome boundary |
| Lua with side effects | Depends on script logic | Lua is atomic for script execution, not automatically idempotent on retry |

### Business Idempotency Key

For an operation like "record an event as processed," a stable `eventId` across retries combined with a uniqueness constraint where side effects are persisted can prevent duplicate application.

~~~text
eventId = evt-2001
      |
      +--> Redis command timeout
      |
      +--> Worker retries
               |
               v
        Check eventId where business state is updated
               |
         +-----+------+
         |            |
     Processed    Unprocessed
         |            |
         v            v
       Skip       Apply + write marker atomically
~~~

If the idempotency marker lives in Redis while the side effect lives in PostgreSQL, the two operations do not automatically commit atomically together. For critical business workflows, place the marker in the same transaction as the database side effect, or use an appropriate protocol/outbox.

Do not treat "re-send succeeded" as proof that the initial send definitely did not run. That is why retry policies must be reviewed per **semantic operation**, not just by exception class.

## 13. Separating Normal Result Signals from Error Signals

Not every "unexpected" result is an exception. Redis returns many values with normal semantics that applications easily misinterpret:

| API / Command | Result | Typical Meaning |
| --- | --- | --- |
| `opsForValue().get(missingKey)` | `null` in synchronous API | Key does not exist |
| Reactive `get(missingKey)` | `Mono.empty()` | No value to emit |
| `setIfAbsent(key, value)` | `Boolean.FALSE` | Key already exists, `NX` condition not satisfied |
| `delete(key)` | `0` | No keys deleted, key may already be absent |
| `getExpire(key)` | `-1` | Key exists without a TTL |
| `getExpire(key)` | `-2` | Key does not exist |
| `convertAndSend(channel, payload)` | May return `0` | No active subscribers per publish semantics; not a command error |
| Redis List `pop` on empty list | Absent value | No element available to pop |

Example of proper branching for a distributed lock:

~~~java
Boolean acquired = redis.opsForValue().setIfAbsent(
    "lock:job:daily",
    "owner-token",
    java.time.Duration.ofSeconds(30)
);

if (Boolean.TRUE.equals(acquired)) {
    // Lock acquired successfully.
} else if (Boolean.FALSE.equals(acquired)) {
    // Lock is held by someone else; this is normal contention.
} else {
    // In special execution modes such as pipeline/transaction,
    // the API may not provide an immediate result yet.
    // Do not assume null means the lock was acquired.
}
~~~

The snippet only illustrates result branching; a real lock also needs a unique owner token per acquisition and token-checked release. When using pipelines or transactions, interpreting `null` must follow the corresponding API contract rather than the same logic as a direct normal call.

Another mistake is classifying any `Mono.empty()` as "Redis down." When `GET` finds no data, the publisher completes normally; `onErrorResume` does not run. If fallback data needs to be loaded:

~~~java
Mono<String> value = reactiveRedis.opsForValue()
    .get("cache:product:42")
    .switchIfEmpty(Mono.defer(() -> loadFromDatabaseReactive("42")));
~~~

`loadFromDatabaseReactive` is an illustrative business method returning `Mono<String>`. `Mono.defer` defers creating the fallback source publisher until upstream is genuinely empty; if Redis fails, the error still flows through `onError` unless handled separately.

## 14. Diagnosing with Redis CLI and Controlled Metrics

When an incident occurs, collect evidence from the application toward Redis rather than randomly testing mutating commands. Some useful **read-only diagnostic** commands:

~~~bash
# Check whether the Redis instance responds:
redis-cli -h redis.internal -p 6379 PING

# Server and client state:
redis-cli -h redis.internal -p 6379 INFO server
redis-cli -h redis.internal -p 6379 INFO clients
redis-cli -h redis.internal -p 6379 INFO stats
redis-cli -h redis.internal -p 6379 INFO memory

# Command and latency information:
redis-cli -h redis.internal -p 6379 INFO commandstats
redis-cli -h redis.internal -p 6379 SLOWLOG GET 10
redis-cli -h redis.internal -p 6379 LATENCY LATEST
~~~

These commands require appropriate permissions. `SLOWLOG GET` may contain command names or arguments; restrict who can view the output and avoid pasting sensitive data into public logs/tickets. Do not run `MONITOR` continuously in production as it can add heavy overhead and expose command payloads.

For a test key or a key authorized for investigation:

~~~redis
TYPE cache:product:v2:42
TTL cache:product:v2:42
PTTL cache:product:v2:42
EXISTS cache:product:v2:42
~~~

`TYPE` helps diagnose `WRONGTYPE`. `TTL` and `PTTL` help diagnose missing or expired expirations. `EXISTS` is only a snapshot at the moment the command ran; the key can change immediately afterward.

### Which Metrics Should Be Watched for Each Error Group?

| Group | Metrics/Logs to Inspect | Question |
| --- | --- | --- |
| Connection | Connection failures, reconnects, TCP resets, DNS/TLS errors | Is the error at the network, driver, or Redis server? |
| Timeout | Command latency p50/p95/p99, queue depth, pool wait, timeout rate | Is congestion at connection, command, queue, or full request? |
| Command | Redis error code, command family, key namespace, Redis role/ACL | Is the command wrong type, unauthorized, or misrouted? |
| Serializer | Decode failure count, schema version, serializer ID, payload source | Do both components share the same byte/schema contract? |

Application-side metrics should also be broken down by **feature/cache name and operation type**, not just total Redis errors. If cache `GET` timeouts spike while queue `SET` remains healthy, the cause may be concentrated in heavy read workloads or pipeline construction.

### Should You Inspect Key Data Directly?

Only when authorized and the data is non-sensitive. Many Redis values contain sessions, access tokens, user data, or binary payloads that cannot be safely printed. When investigating serializer issues, create a **test key** with non-sensitive payload, or record redacted schema versions/hashes and metadata instead of dumping the entire value.

## 15. Actionable Logs and Metrics

A generic "Redis error" message is insufficient to distinguish the four error groups. Each record should include at least:

- `failure_kind`: connection, timeout, command, serialization, unknown.
- `operation`: GET, SET, HGET, XREADGROUP, EVAL... or command family.
- `cache_name` / `module` / `feature`: business area.
- `key_namespace`: e.g. `cache:product:v2`, **not every personal ID**.
- `driver`, `redis_mode`: Lettuce/Jedis, standalone/Sentinel/Cluster.
- `elapsed_ms`, configured timeout, attempt index, and result.
- Correlation ID or trace ID to link with HTTP/job logs.
- Outermost exception class and relevant lowest cause; stack trace when needed.

Example of logging without printing payloads:

~~~java
RedisFailureClassifier.Kind kind =
    classifier.classify(error);

log.warn(
    "Redis failure kind={} operation={} cache={} elapsedMs={} exception={}",
    kind,
    "GET",
    "product-v2",
    elapsedMs,
    error.getClass().getSimpleName(),
    error
);
~~~

The `log` variable represents a declared SLF4J logger, and `elapsedMs` is the duration measured in the service. The entry avoids putting full keys containing user IDs or values with personal data in the message. If stack traces might contain Redis URIs/credentials in a specific driver/version, apply redaction and log retention policies.

With Micrometer, you can track:

~~~text
redis.operation.failures{kind="timeout",operation="GET",cache="product"}
redis.operation.duration{operation="GET",cache="product"}
redis.fallback.count{reason="connection",cache="product"}
redis.retry.attempts{operation="GET",outcome="exhausted"}
redis.serialization.failures{cache="product",schema="v2"}
~~~

These are illustrative metric names; they do not appear automatically just by having Spring Data Redis. Your application or observability setup must instrument them. Never use key IDs or verbatim exception messages as tags because cardinality and sensitive data exposure can grow uncontrollably.

### Know That Execution Time Does Not Always Equal Redis Processing Time

An `elapsedMs` measured from the service can include serialization, pool/connection waiting, command queuing, network, and deserialization. It does not necessarily reflect the time the Redis server directly spent executing the command.

When analyzing timeouts, compare:

1. Latency observed from the application.
2. Redis slow log / latency events.
3. Driver queue or pool wait if metrics exist.
4. Network latency and packet loss.
5. Request/response payload sizes.

If the server slow log shows no slow commands while application timeouts rise, inspect the stages **outside Redis server command CPU execution**.

## 16. Testing Error Classification and Behavior Against Real Redis

To test the classifier, separate:

- **Unit tests**: construct exceptions of specific types and test the classifier without Redis.
- **Integration tests**: use a real Redis instance to trigger command errors or test cache misses; do not mock the Redis server if you want to verify command semantics.
- **Controlled fault-injection tests**: introduce network timeouts, disconnects, and failovers using dedicated infrastructure when needed; avoid running these against a shared Redis instance.

### 16.1. Unit Testing the Classifier

~~~java
package com.example.redis.error;

import io.lettuce.core.RedisCommandExecutionException;
import io.lettuce.core.RedisCommandTimeoutException;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.RedisConnectionFailureException;
import org.springframework.data.redis.serializer.SerializationException;

import static org.assertj.core.api.Assertions.assertThat;

class RedisFailureClassifierTest {

    private final RedisFailureClassifier classifier =
        new RedisFailureClassifier();

    @Test
    void classifiesConnectionFailure() {
        assertThat(classifier.classify(
            new RedisConnectionFailureException("connection refused")
        )).isEqualTo(
            RedisFailureClassifier.Kind.CONNECTION
        );
    }

    @Test
    void classifiesNestedCommandTimeout() {
        RuntimeException wrapped = new IllegalStateException(
            "redis operation failed",
            new RedisCommandTimeoutException("command timed out")
        );

        assertThat(classifier.classify(wrapped)).isEqualTo(
            RedisFailureClassifier.Kind.TIMEOUT
        );
    }

    @Test
    void classifiesWrongTypeCommandError() {
        RuntimeException wrapped = new IllegalStateException(
            "redis operation failed",
            new RedisCommandExecutionException(
                "WRONGTYPE Operation against a key"
            )
        );

        assertThat(classifier.classify(wrapped)).isEqualTo(
            RedisFailureClassifier.Kind.COMMAND
        );
    }

    @Test
    void classifiesSerializationFailure() {
        assertThat(classifier.classify(
            new SerializationException("invalid serialized value")
        )).isEqualTo(
            RedisFailureClassifier.Kind.SERIALIZATION
        );
    }

    @Test
    void unknownErrorIsNotAutomaticallyRedisFailure() {
        assertThat(classifier.classify(
            new IllegalStateException("business rule violation")
        )).isEqualTo(
            RedisFailureClassifier.Kind.UNKNOWN
        );
    }
}
~~~

These unit tests directly verify type/cause classification rules; they **do not prove** that Spring Data Redis translates every server error in every version into one exact class.

### 16.2. Integration Testing `WRONGTYPE` and Cache Misses

Gradle Groovy dependencies (Spring Boot manages compatible versions):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

Example with Redis 7.2 in Testcontainers:

~~~java
package com.example.redis.error;

import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@Testcontainers
@SpringBootTest(classes = RedisErrorIntegrationTest.TestApp.class)
class RedisErrorIntegrationTest {

    @SpringBootConfiguration
    @EnableAutoConfiguration
    static class TestApp {
    }

    @Container
    static final GenericContainer<?> REDIS =
        new GenericContainer<>(DockerImageName.parse("redis:7.2-alpine"))
            .withExposedPorts(6379);

    @DynamicPropertySource
    static void redisProps(DynamicPropertyRegistry registry) {
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add(
            "spring.data.redis.port",
            () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void missingKeyIsNotAnException() {
        String key = "it:missing:" + UUID.randomUUID();

        assertThat(redis.opsForValue().get(key)).isNull();
    }

    @Test
    void wrongTypeIsACommandFailure() {
        String key = "it:wrongtype:" + UUID.randomUUID();

        try {
            redis.opsForValue().set(key, "plain-string");

            assertThatThrownBy(
                () -> redis.opsForList().size(key)
            ).isInstanceOf(RuntimeException.class);
        } finally {
            redis.delete(key);
        }
    }
}
~~~

In the second test, the key is stored as a Redis String; the List size command is incompatible, so Redis returns a command error. The assertion checks for a runtime exception at the application layer because the exact subtype can vary by translator/driver. To verify the classifier against your actual configuration, you can catch the exception and check `RedisFailureClassifier` along with its cause in the exact versions your project uses.

The test does not run `FLUSHDB`/`FLUSHALL`, cleaning up only its UUID-scoped key. The test runner needs Docker or a compatible container environment.

### 16.3. Testing Serializer Errors Without a Redis Server

To verify that a Java deserializer rejects malformed payloads, you can test it directly:

~~~java
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;
import org.springframework.data.redis.serializer.SerializationException;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

class SerializerFailureTest {

    @Test
    void rejectsBytesThatAreNotJavaSerializedObject() {
        byte[] jsonBytes = """
            {"id":42,"name":"Example"}
            """.getBytes(StandardCharsets.UTF_8);

        JdkSerializationRedisSerializer serializer =
            new JdkSerializationRedisSerializer();

        assertThatThrownBy(() -> serializer.deserialize(jsonBytes))
            .isInstanceOf(SerializationException.class);
    }
}
~~~

This test demonstrates the difference between JSON bytes and Java object serialization; it does not recommend using JDK serialization for data from untrusted sources. In real systems, choose a serializer with a clear schema/version contract and controlled data types.

### 16.4. Avoid Simulating Timeouts with `Thread.sleep` in Tests

A unit test cannot prove that a Redis command timed out at the network/driver level simply by calling `Thread.sleep` in Java. If you need to test connection failures and command timeouts:

- Use a dedicated test Redis instance and a proxy/network fault injection tool (such as Toxiproxy) under controlled conditions.
- Configure connect timeout / command timeout appropriate for the scenario.
- Simulate disconnects or bounded delays to verify retry/fallback branches.
- Poll with a timeout to verify recovery state rather than asserting on a single hardcoded sleep interval.
- For write commands, verify business state after a timeout; do not assume the command did not run.

Never deliberately block Redis or trigger failovers on a production server just to reproduce errors for learning purposes.

## 17. Production Incident Response Workflow

When a Redis alert fires, follow a repeatable workflow instead of tweaking multiple settings at once.

### Step 1 — Determine Scope and Impact

- Does the error affect one feature or all Redis-related requests?
- Is only one pod failing or every instance?
- Is only `GET` failing, or also `SET`, `EVAL`, `XREADGROUP`?
- Did the incident start after a deployment, Redis failover, ACL change, or serializer configuration change?
- Is Redis an auxiliary cache or the store for critical data/coordination locks?

Incident scope dictates priority action. A decode error limited to `cache:user:v1` immediately after a deployment differs fundamentally from connection errors on all commands after a Redis primary restart.

### Step 2 — Classify Based on Evidence

~~~text
                    Redis failure observed
                           |
                           v
               Inspect exception/cause
                           |
          +----------------+-----------------+
          |                |                 |
          v                v                 v
      Connection        Timeout         Command error
          |                |                 |
          v                v                 v
     DNS/TCP/TLS/     Which command?   WRONGTYPE/ACL/
     server/role?     Where waiting?   READONLY/CROSSSLOT?
          |                |                 |
          +--------+-------+--------+--------+
                   |                |
                   v                v
         Check logs/metrics     Safe to retry?
                   |
                   v
          If byte decode fails
                   |
                   v
         Serialization/schema/serializer
~~~

If the group cannot be determined from the exception type and cause, record **UNKNOWN** and gather more evidence. Do not automatically categorize an unfamiliar error as a connection issue and retry endlessly.

### Step 3 — Diagnose the Right Layer

**For connection:**

1. From where the application runs, check DNS, routing, TCP/TLS, Redis endpoint, and credentials.
2. If using Sentinel/Cluster, query the actual current topology and roles.
3. Check Redis client counts, connection resets, and driver reconnects.
4. Check whether a failover, deployment, or network policy change occurred right when errors began.

**For timeout:**

1. Determine whether it is connect timeout, command timeout, pool wait, or application deadline.
2. Measure p95/p99 latency, queue depth, payload size, and concurrent request count.
3. Compare application-side latency with `SLOWLOG`/`LATENCY` from the server.
4. Evaluate retry impact per command, especially for non-idempotent writes.

**For command:**

1. Capture the Redis error code and command family.
2. Check `TYPE` on a test key, ACLs, node role, server version, slot routing, or Lua script.
3. Fix the root cause in schema/config/code instead of repeating an invalid command.
4. If the error is due to transient topology state, discover the new primary/slot before retrying.

**For serialization:**

1. Identify the key/value/hash serializers on both writer and reader sides.
2. Compare schema versions between old and new releases.
3. Attempt to decode a non-sensitive test payload using the actual serializer.
4. If it is a regenerable cache, consider versioned namespaces or controlled invalidation; if it is source data, preserve the data for migration.

### Step 4 — Recover with Minimal Blast Radius

Examples:

- Redis temporarily down while serving only cache: bounded fallback, reduce load on Redis, and warm cache gradually.
- `WRONGTYPE` in a single namespace: fix schema/key naming; do not wipe all of Redis.
- Changed ACLs: grant the exact required permissions; do not switch to a superuser account to bypass policy.
- Stale driver topology after failover: verify Sentinel/Cluster-aware configuration and reconnection.
- Old cache data cannot decode: use a `v2` namespace or migration, not `FLUSHALL` as a default measure.

### Step 5 — Reconcile State When Write Outcomes Are Uncertain

For read-only commands, retrying is usually simpler. For `INCR`, `XADD`, `SET NX`, inventory updates, lease tokens, or multi-command workflows, ask:

- Could Redis have executed the command before the timeout?
- Is there an idempotency key to detect duplicate commands?
- Is there a transaction/unique constraint where the side effect is stored?
- Can the true state be read back to confirm the outcome?
- If it cannot be determined, should the application surface an "unknown" status and hand off to reconciliation?

This step prevents situations where connectivity recovers while data ends up processed twice.

## 18. Common Scenario Reference Table

| Symptom | Priority Diagnosis | What Not to Do |
| --- | --- | --- |
| `Unable to connect to Redis` | Endpoint, DNS, port, firewall, TLS, role, and Redis health | Immediately conclude Redis server is dead without checking from the app pod |
| `RedisCommandTimeoutException` | Command latency, network, queue, payload, and driver timeout | Retry all write commands with zero delay |
| `WRONGTYPE` with `opsForList()` | Is the actual key a String/Hash/Set? | Delete production keys without understanding owner and schema |
| `READONLY You can't write against a read only replica` | Stale connection after failover or replica configuration | Increase timeout without updating routing |
| `NOPERM` | Redis ACL key patterns/command categories | Switch to an overly broad admin account |
| `NOAUTH` / `WRONGPASS` | Credentials, ACL, secret rotation, and TLS | Log passwords/URIs to debug |
| `CROSSSLOT` | Redis Cluster and hash slots of a multi-key command | Resend the exact same command to a random node |
| `NOSCRIPT` | Script cache on a new node or after restart | Treat as a broken serializer |
| `OOM command not allowed` | Redis maxmemory, eviction policy, data size | Keep increasing retries to push more load |
| JSON deserialize failure | Key bytes, serializer, class/schema version | Retry reading the exact same bytes infinitely |
| All cache reads miss after deployment | Key serializer or namespace may have changed | Treat every miss as a Redis connection failure |
| `Mono.empty()` from Redis GET | Key does not exist | Catch it like an exception or emit `null` in Reactor |
| Client timeout after `INCR` | Command state may be uncertain | Retry incrementing again without idempotency protection |
| Pub/Sub publish returns `0` | No subscribers listening per Redis semantics | Conclude Redis server is broken |
| Redis failover finished but API still errors | Driver reconnect/topology, NAT endpoints/ACL | Look only at Sentinel state and ignore app-side errors |
| Redis connection healthy but API p99 is high | Large serialization, pool wait, downstream, or command queue | Ping Redis alone and conclude there is no problem |

## 19. Sample Error Policy for a Multi-Feature Application

Suppose one service uses Redis as a product cache, Redis Streams to consume events, and a Redis lock to avoid duplicate job runs. You cannot use a single `RedisExceptionHandler` that says "if error, skip Redis."

A sensible policy split:

~~~text
                         Redis access
                              |
                              v
                        Classify failure
                              |
          +-------------------+--------------------+
          |                   |                    |
          v                   v                    v
    Product Cache         Streams Consumer       Distributed Lock
          |                   |                    |
          v                   v                    v
   Connection/timeout   Error before commit?  Acquire/renew unclear?
          |                   |                    |
          v                   v                    v
   Bounded fallback     Do not blindly ACK     Do not assume lock is
   + cache rebuild      + pending recovery     held or released
          |                   |                    |
          v                   v                    v
   Wrongtype/schema?    Payload error?        Timeout after SET NX?
          |                   |                    |
          v                   v                    v
   Fix key/migration    DLQ / schema policy    Use token/reconcile
   instead of retry     before ACK             + fencing if needed
~~~

For the cache, a network error may only degrade performance if an alternative data source exists. For Streams, an error before side effects succeed must preserve reprocessing capability rather than ACKing as if it succeeded. For locks, a timed-out acquire command may have already created the key; mishandling ownership state can allow two workers to operate simultaneously.

Thus, **the classifier provides the label**, while **the business policy decides the behavior**. A solid architecture typically has:

1. A Redis adapter that identifies errors and attaches metrics by category.
2. Separate policies for cache, queue/stream, lock, and critical data.
3. Operation-scoped bounded retries with jitter and concurrency limits.
4. Idempotency storage or transactional constraints for non-repeatable side effects.
5. Runbook documentation so operations teams know when to fall back, when to fail closed, and when to migrate.

## 20. Conclusion

Classifying Redis errors into **connection, timeout, command, and serialization** helps Spring Data Redis applications avoid the overly simplistic "on Redis error, retry" approach. The four categories demand different actions:

- **Connection:** check endpoint, network, TLS, pool, and topology; use bounded retries only when appropriate.
- **Timeout:** identify which stage expired, measure latency/queues, and accept that write commands may **have already executed** even though the client received no result.
- **Command:** inspect error codes such as `WRONGTYPE`, `NOPERM`, `READONLY`, or `CROSSSLOT`; fix data, permissions, or routing instead of retrying forever.
- **Serialization:** inspect serializers, schemas, legacy data, and migrations; do not turn unreadable payloads into cache misses uncontrollably.

With Spring Data Redis, exception translation may wrap Lettuce/Jedis exceptions inside `DataAccessException` or other types. Inspect the **cause chain, operation, and business context**, without relying absolutely on a single exception name. In reactive code, separate `Mono.empty()` from `onError` and remember that `Mono.timeout()` does not prove Redis rolled back a command.

Finally, **operation type** is just as important as **error type**: retrying `GET` is completely different from retrying `INCR` or `XADD`. When error policies are combined with idempotency, metrics, controlled testing, and proper consistency boundaries, applications can recover from Redis incidents without sacrificing data correctness.
