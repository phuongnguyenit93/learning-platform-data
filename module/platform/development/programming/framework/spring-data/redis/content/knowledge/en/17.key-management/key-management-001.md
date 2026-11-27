# Checking Existence, Data Type, and Renaming Keys in Spring Data Redis

## 1. Why Is Key Management Needed?

Redis stores data as **key–value** pairs. Each key has a name, a Redis data type, and optionally a time-to-live (TTL). In a Spring application, besides reading and writing values, you sometimes need to know whether a key exists, determine the type of data stored under the key, or move data to a new key name.

For example, a system might store `user:42:status` to represent user status. When changing the naming convention to `profile:42:status`, you need to understand exactly how renaming affects the old key, the target key, and the TTL. Similarly, if the code expects a Redis Hash but the key actually contains a String, a Hash read operation can fail with a `WRONGTYPE` error.

This lesson focuses on three groups of **keyspace** operations:

- **Checking existence**: Redis `EXISTS`, Spring Data Redis `hasKey(...)`.
- **Determining data type**: Redis `TYPE`, Spring Data Redis `type(...)`.
- **Renaming**: Redis `RENAME` / `RENAMENX`, Spring Data Redis `rename(...)` / `renameIfAbsent(...)`.

These are operations on the **key**, not data type conversions or transformations of the value's contents.

## 2. Understanding Redis Commands Before Using Spring

| Need | Redis CLI | Result Meaning |
|---|---|---|
| Does a key exist? | `EXISTS key` | `1` if it exists, `0` if not; multi-key form returns the count of existing keys |
| What type does the key store? | `TYPE key` | `string`, `hash`, `list`, `set`, `zset`, `stream`, or `none` |
| Rename, allowing target replacement | `RENAME old new` | Returns `OK` on success; if target exists, target data is replaced |
| Rename only when target does not exist | `RENAMENX old new` | `1` if renamed, `0` if target already exists |

Try this in a test Redis instance:

```redis
SET demo:user:42:state "ACTIVE"
EXISTS demo:user:42:state
# (integer) 1

TYPE demo:user:42:state
# string

TYPE demo:user:999:state
# none

RENAME demo:user:42:state demo:profile:42:state
# OK

EXISTS demo:user:42:state
# (integer) 0

EXISTS demo:profile:42:state
# (integer) 1

GET demo:profile:42:state
# "ACTIVE"
```

`RENAME` moves **the same value** from the old name to the new name: after it succeeds, the source key no longer exists. Redis does not create an extra copy to keep both names.

In the case where you want to preserve the target key if it already exists:

```redis
SET demo:source "new-value"
SET demo:target "existing-value"

RENAMENX demo:source demo:target
# (integer) 0

GET demo:source
# "new-value"

GET demo:target
# "existing-value"
```

If the source does not exist, `RENAME` and `RENAMENX` return an error instead of creating data. Therefore, you need to distinguish three cases: source is missing, target already exists, and the command executed successfully.

## 3. Spring Boot Configuration and API Mapping

For a Spring Boot application using Spring Data Redis, declare the dependency:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
}
```

Example Redis connection configuration on a development machine:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Spring Boot auto-configures `StringRedisTemplate` when the connection configuration and appropriate dependency are present. This template is suitable for working with string keys that are easy to read in `redis-cli`. Use the same key serialization rule across components that write, read, and rename; a key written with a different serializer may have a different byte representation even though it looks the same on the Java side.

Common API mapping:

| Spring Data Redis | Return Type | Corresponding Redis Command | Notes |
|---|---|---|---|
| `stringRedisTemplate.hasKey(key)` | `Boolean` | `EXISTS` | May be `null` in a pipeline/transaction context |
| `stringRedisTemplate.type(key)` | `DataType` | `TYPE` | `DataType.NONE` for a non-existent key in normal calls |
| `stringRedisTemplate.rename(oldKey, newKey)` | `void` | `RENAME` | **Overwrites** the target key if it already exists |
| `stringRedisTemplate.renameIfAbsent(oldKey, newKey)` | `Boolean` | `RENAMENX` | `true` when renamed; `false` when target already exists; may be `null` in pipeline/transaction |

Here, `DataType` is `org.springframework.data.redis.connection.DataType`, representing the **actual Redis type** under a key. It is not the `Class<?>` of the Java object serialized into Redis by the application.

## 4. Building a Key Management Service

The example below assumes the methods are called synchronously in the normal way, not inside a Redis pipeline or transaction. Because the API returns a boxed `Boolean`, avoid auto-unboxing without accounting for the possibility of `null`.

```java
package com.example.redis;

import org.springframework.data.redis.connection.DataType;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisKeyManagementService {

    private final StringRedisTemplate redisTemplate;

    public RedisKeyManagementService(StringRedisTemplate redisTemplate) {
        this.redisTemplate = redisTemplate;
    }

    /** Returns true if the key exists when Redis processes the command. */
    public boolean exists(String key) {
        requireKey(key);
        return Boolean.TRUE.equals(redisTemplate.hasKey(key));
    }

    /** Returns DataType.NONE if the key does not exist at the time of inspection. */
    public DataType typeOf(String key) {
        requireKey(key);
        return redisTemplate.type(key);
    }

    /** Renames and replaces the entire target key if the target already exists. */
    public void renameReplacingTarget(String sourceKey, String targetKey) {
        requireDistinctKeys(sourceKey, targetKey);
        redisTemplate.rename(sourceKey, targetKey);
    }

    /** Renames only when the target key does not exist yet. */
    public boolean renameIfTargetAbsent(String sourceKey, String targetKey) {
        requireDistinctKeys(sourceKey, targetKey);
        return Boolean.TRUE.equals(
                redisTemplate.renameIfAbsent(sourceKey, targetKey)
        );
    }

    private static void requireKey(String key) {
        if (key == null || key.isBlank()) {
            throw new IllegalArgumentException("Redis key must not be blank");
        }
    }

    private static void requireDistinctKeys(String sourceKey, String targetKey) {
        requireKey(sourceKey);
        requireKey(targetKey);
        if (sourceKey.equals(targetKey)) {
            throw new IllegalArgumentException(
                    "Source and target Redis keys must be different"
            );
        }
    }
}
```

In this example, disallowing blank key names is an **application rule** to prevent accidental calls, not a mandatory Redis limitation. In multi-tenant or multi-feature systems, business code must also enforce prefixes and access permissions rather than arbitrarily accepting another tenant's key name.

If a system uses `RedisTemplate<String, MyObject>` instead of `StringRedisTemplate`, the same keyspace operations are still available on `RedisTemplate`. The point to check is the **key serializer**. For example, a key using a JDK serializer will not be stored by Redis as the plain UTF-8 string seen in Java; `redis-cli EXISTS my:key` may return `0` even though the application can read it with its matching serializer.

## 5. Checking Whether a Key Exists: hasKey

Suppose application code stores session state:

```java
String sessionKey = "demo:session:7";
redisTemplate.opsForValue().set(sessionKey, "ACTIVE");

boolean present = keyService.exists(sessionKey);  // true
boolean absent = keyService.exists("demo:session:missing"); // false
```

`hasKey` only tells you whether the key **existed at the moment Redis processed the command**. It does not guarantee the key will still exist when the next command runs: its TTL might expire, or another client might delete, overwrite, or rename the key between the two commands.

Therefore, avoid the following reasoning pattern to guarantee that a subsequent operation will succeed:

```java
// Two separate commands; state can change in between.
if (keyService.exists(sourceKey)) {
    keyService.renameReplacingTarget(sourceKey, targetKey);
}
```

The example above can still fail if the source is deleted before `RENAME`. When you only need to read a value, use the appropriate read operation directly (and handle the missing result); you do not always need to call `hasKey` first. When you need conditional renaming based on the **target's** state, use `renameIfAbsent` so Redis checks and renames in **a single atomic command**.

Note: `Boolean.TRUE.equals(...)` returns `false` when Spring receives `null`. This pattern avoids a `NullPointerException` in synchronous calls, but **you should not use the return value of these methods to draw immediate business conclusions inside a pipeline/transaction**, because `null` may simply mean the result has not been materialized yet. Process the returned results after the pipeline or transaction completes.

## 6. Checking the Redis Type: type

Common types and their corresponding operation APIs:

| `TYPE` in Redis | `DataType` in Spring | Spring Data Redis Example |
|---|---|---|
| `string` | `DataType.STRING` | `opsForValue()` |
| `hash` | `DataType.HASH` | `opsForHash()` |
| `list` | `DataType.LIST` | `opsForList()` |
| `set` | `DataType.SET` | `opsForSet()` |
| `zset` | `DataType.ZSET` | `opsForZSet()` |
| `stream` | `DataType.STREAM` | `opsForStream()` |
| `none` | `DataType.NONE` | Key does not exist |

Create a sample Hash key:

```java
String key = "demo:user:42";
redisTemplate.opsForHash().put(key, "name", "Linh");
redisTemplate.opsForHash().put(key, "role", "reader");

DataType dataType = keyService.typeOf(key);
System.out.println(dataType); // HASH

DataType missingType = keyService.typeOf("demo:user:missing");
System.out.println(missingType); // NONE
```

A case requiring schema validation:

```java
DataType actual = keyService.typeOf("demo:user:42");

if (actual == DataType.NONE) {
    // Key does not exist yet: handle the missing-data case.
} else if (actual != DataType.HASH) {
    throw new IllegalStateException(
            "Expected Redis HASH but found " + actual
    );
} else {
    // Can be operated on as a HASH, subject to state at the time of the call.
}
```

If you call `opsForHash()` on a key that actually holds a String, Redis typically returns the error `WRONGTYPE Operation against a key holding the wrong kind of value`. `type(...)` helps with diagnostics and precondition checks, though it does not completely eliminate concurrent changes between commands.

Redis `TYPE` describes **the storage type of the value in Redis**. For example, a Java object serialized to JSON and written via `opsForValue().set(...)` is still a Redis `string`; it does not automatically become a Redis `hash` just because the JSON contains multiple fields.

## 7. Renaming with Overwrite: rename

`rename(source, target)` maps to `RENAME`:

- After it succeeds, **the source disappears**, and the target points to the source's previous data.
- If the target already exists, **the target's old data is replaced**. Do not call this when the target value must be preserved.
- **The source's data type stays the same**: a Redis Hash remains a Hash under the new name.
- **The source's TTL is preserved on the new name**; if the target previously had its own TTL, that TTL no longer applies because the old target value was replaced.
- If the source does not exist, Redis returns an error; Spring usually translates the error into an exception in the `DataAccessException` hierarchy.

Example run with test data:

```java
String oldKey = "demo:account:42:legacy";
String newKey = "demo:account:42:current";

redisTemplate.opsForValue().set(oldKey, "ACTIVE");
redisTemplate.opsForValue().set(newKey, "STALE");

keyService.renameReplacingTarget(oldKey, newKey);

// oldKey no longer exists; newKey holds "ACTIVE".
// The previous "STALE" value at newKey has been replaced.
```

You can directly observe the TTL before and after renaming:

```redis
SET demo:otp:old "123456" EX 120
TTL demo:otp:old
# A positive number of seconds, up to nearly 120

RENAME demo:otp:old demo:otp:new
# OK

TTL demo:otp:old
# (integer) -2  (key does not exist)

TTL demo:otp:new
# Remaining positive seconds from the original expiration
```

When `TTL` returns `-1`, the key exists without an expiration; `-2` means the key does not exist. Remaining TTL always decreases over time, so you should not test by expecting the exact same number of seconds before and after the operation.

`RENAME` is an atomic operation in Redis for the scope of that single command. However, business steps before and after `RENAME` (such as updating another database record) do **not automatically** become part of a distributed transaction.

## 8. Safe Renaming When Target Does Not Exist: renameIfAbsent

If overwriting the target is not allowed, use `renameIfAbsent(source, target)`, which corresponds to `RENAMENX`:

```java
String draft = "demo:report:42:draft";
String published = "demo:report:42:published";

redisTemplate.opsForValue().set(draft, "draft-content");
redisTemplate.opsForValue().set(published, "approved-content");

boolean renamed = keyService.renameIfTargetAbsent(draft, published);

System.out.println(renamed); // false because published already exists
// draft still holds "draft-content"; published holds "approved-content".
```

When the target does not exist, the success result is `true`, the source disappears, and the new target contains the content and TTL from the source.

Why not combine two commands yourself?

```java
// Does not guarantee avoiding overwrites under concurrency.
if (!keyService.exists(targetKey)) {
    keyService.renameReplacingTarget(sourceKey, targetKey);
}
```

Between the check and `RENAME`, another process might create `targetKey`. Then `RENAME` would still overwrite it. `RENAMENX` solves the **target does not exist yet** condition in a single operation on Redis.

Even though `RENAMENX` is atomic, if the source disappears before Redis receives the command, the operation can still fail. The application must decide whether to retry, report missing data, or treat this as a normal case. Do not treat every exception during renaming as "target already exists"; that case is represented by `false` in normal calls.

## 9. Redis Cluster, Keys with TTL, and Naming Conventions

### Limitations in Redis Cluster

In Redis Cluster, `RENAME` and `RENAMENX` require both keys to be in **the same hash slot**. Keys in different slots can cause a `CROSSSLOT` error.

Hash tags in key names help route related keys to the same slot:

```text
profile:{user:42}:draft
profile:{user:42}:active
```

The two names above share the `{user:42}` part, so their slot is computed from the same tag content. Use hash tags intentionally; designing tags that are too broad can cause uneven data distribution across shards. Outside Redis Cluster, this same-slot rule is not an issue for standalone Redis.

### TTL and Key Lifecycle

- A key may expire between `hasKey` and `type` / `rename`.
- `RENAME` moves the **source's** TTL to the target name; the target's previous TTL is not kept if the target is replaced.
- Checking `EXISTS` after TTL expiration checks current state, not proof that the data was never written.
- If a workflow needs to "transition state" simultaneously with multiple conditions on the value's content, consider an appropriate atomic command or a Lua script instead of combining multiple independent checks.

### Namespaces and Data Safety

Use structured key names, such as `app:entity:id:purpose`, to avoid collisions between features. In multi-tenant applications, validate both **source and target keys** before renaming. Do not expose an HTTP API that lets clients pass two arbitrary Redis keys, because the operation could overwrite another user's data.

## 10. Common Pitfalls and How to Handle Them

| Symptom | Common Cause | How to Handle |
|---|---|---|
| `hasKey` returns `false` even though you thought it was written | Wrong prefix, different Redis database, different serializer, or key TTL expired | Check key generation, connection configuration, and TTL |
| `type` returns `DataType.NONE` | Key does not exist at the time of the call | Handle the missing-data case |
| `WRONGTYPE` when using `opsForHash` or `opsForValue` | Value type in Redis differs from what the read API expects | Determine actual `TYPE` and standardize schema/key namespace |
| `rename` causes data loss at the target | `RENAME` allows overwriting | Use `renameIfAbsent` if the target must be preserved |
| `renameIfAbsent` returns `false` | Target already exists | Keep existing data and decide how business logic handles the conflict |
| Rename throws an error when source is missing | Key expired, was deleted, or was renamed earlier | Handle missing-source error; do not assume by default that it is a target conflict |
| Redis Cluster reports `CROSSSLOT` | Source and target are in two different slots | Design keys in the same hash slot, consider hash tags |
| Redis CLI cannot find a key that Spring can read | Key serializer is not CLI-string compatible | Use or verify the same serializer, typically `StringRedisTemplate` for string examples |
| `Boolean` result is `null` in a pipeline/transaction | Result is not available yet at call time | Read results after the pipeline/transaction completes |

## 11. When to Choose Which Operation?

- Choose **`hasKey`** when you genuinely need an existence answer at the moment of inspection, such as for displaying status or aiding diagnostics. Do not use it as a synchronization lock for a separate subsequent command.
- Choose **`type`** when you need to distinguish Redis String, Hash, List, Set, Sorted Set, or Stream, especially when inspecting legacy data or diagnosing `WRONGTYPE`. With well-designed keys, data types should remain stable per namespace.
- Choose **`rename`** when **replacing the target key** is intentional and controlled; understand that the source no longer exists after success.
- Choose **`renameIfAbsent`** when the target value must be preserved if it already exists. This is the atomic way to check target non-existence and rename.

These methods help manage key names and types clearly in Spring Data Redis. Good design also requires consistent key naming conventions, consistent serializers, TTL policies, and handling concurrency across multiple clients.
