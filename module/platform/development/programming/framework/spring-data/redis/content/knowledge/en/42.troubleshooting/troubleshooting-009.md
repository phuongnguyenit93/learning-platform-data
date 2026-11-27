# Transactions or Pipelines Returning Different Results from Regular Operations in Spring Data Redis

A confusing situation when using Spring Data Redis: the exact same `GET`, `INCR`, or `HGET` command, when called directly via `StringRedisTemplate`, returns a result immediately; however, when placed inside `executePipelined(...)` or between `multi()` and `exec()`, the result inside the callback is `null`. Sometimes the callback runs without errors, yet the outer result list has an unexpected type, a confusing order, or a transaction using `WATCH` does not update data. There are also cases where `@Transactional` is added, yet Redis still writes immediately, while the developer assumes all commands are in a single shared transaction with SQL.

In most cases, **Redis is not dropping results on its own**. The cause lies in **when Redis executes commands, how the driver receives replies, the RedisConnection mechanism, serializers, and Spring's connection binding**. Properly distinguishing the three paths — regular operations, pipelining, and transactions — helps avoid misreading `null` as "key does not exist", mishandling `EXEC` results, or accidentally issuing commands on a different connection.

This troubleshooting guide uses Spring Boot 3.x, Spring Data Redis 3.x, Java 17, and Redis 7.x as the example context. APIs, return types, and pipelining capabilities on Cluster may vary by Spring Data Redis/Lettuce/Jedis/Redis version; when upgrading versions, you must verify the **actual API contract**.

## 1. Typical Symptoms

Standalone execution example:

```java
String value = strings.opsForValue().get("diag:472:item");
System.out.println(value); // "READY" if the key exists and the serializer is correct
```

Inside a pipeline:

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "diag:472:item"
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    byte[] immediate = connection.stringCommands().get(key);

                    System.out.println(immediate); // Usually null
                    return null;                   // Required for pipeline callbacks
                });

System.out.println(replies); // Contains the GET command result after the pipeline completes
```

If the data exists, `replies` may contain `"READY"`, even though `immediate` inside the callback is `null`.

Inside a transaction:

```text
MULTI
GET diag:472:item
EXEC
```

Redis returns `QUEUED` for the `GET` command after `MULTI`; the actual value is only present in the **reply of EXEC**. Spring Data Redis may represent the temporary value inside the callback as `null`. If code relies on that temporary value to make business decisions, the result will be wrong.

### 1.1. Quick Identification Table

| Symptom | First Cause to Check |
|---|---|
| Normal `GET` has data, `GET` in pipeline returns `null` | Not reading the list returned from `executePipelined` |
| Pipeline callback returns `null` but outer list has data | Designed behavior: callback only enqueues/sends |
| `SET` inside `MULTI` is not visible in an immediately following `GET` | Write is `QUEUED`, not yet `EXEC`uted |
| `EXEC` returns a multi-element list | Each reply corresponds to a queued command |
| `EXEC` does not execute when using `WATCH` | Key was modified/expired/evicted before `EXEC` |
| Has `@Transactional` but Redis writes immediately | `setEnableTransactionSupport(true)` not enabled or not inside a Spring-managed transaction |
| Pipeline result is `byte[]`, String, or unexpected type | Raw `RedisCallback` vs `SessionCallback`; different serializer/result deserializer |
| `EXEC` has an error result even though an earlier command wrote | Redis transactions do not roll back runtime errors like SQL |
| Transaction/pipeline succeeds on Standalone but fails on Cluster | Routing/hash slot/driver support differences |
| Incorrect results when an exception occurs between `MULTI` and `EXEC` | Connection may remain in transactional state if not `DISCARD`ed |

## 2. Three Mechanisms, Three Result Retrieval Times

```text
A. Regular command
   Java -> GET key -----------------> Redis
   Java <- value -------------------- Redis
   -> GET method has the value immediately

B. Pipeline
   Java -> GET key1 ------+
          GET key2 ------+---------> Redis
          INCR count ----+
   Java <- replies [v1,v2,n] ------- Redis
   -> Values are in the result when the pipeline closes

C. Transaction
   Java -> MULTI -------------------> Redis
          SET key value -----------> QUEUED
          GET key -----------------> QUEUED
          EXEC --------------------> [status, value]
   -> Commands only execute on EXEC
```

| Property | Regular Command | Pipeline | Redis Transaction |
|---|---|---|---|
| Goal | Send one command and receive reply | Reduce round trips when there are many commands | Execute a group of commands without interleaving commands from other clients |
| When reply is visible | When method completes | After reading all pipeline replies | At `EXEC` |
| Group atomicity? | Per-command atomicity only | **No** | Non-interleaving execution when the command group is `EXEC`uted |
| Can read prior command result to branch next? | Yes | No while commands are still buffered | No between `MULTI` and `EXEC` |
| SQL-style rollback on a runtime command error? | No | No | **No** |
| Can have optimistic locking conflicts? | Not from `WATCH` by default | Not from pipeline | Yes, if using `WATCH` |
| Spring result | Value/Boolean/Long... | `List<Object>` via `executePipelined` | `List<Object>` via `exec` when used directly |

**Pipelines and transactions are two independent features.** They can be combined, but this easily causes confusion because one layer defers the replies of the other. If the only goal is to ensure multiple operations are atomic, pipelining does **not** replace transactions or Lua scripts.

## 3. Preparing an Observable Baseline

Suppose the application is injected with `StringRedisTemplate`:

```java
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisReadExample {

    private final StringRedisTemplate strings;

    public RedisReadExample(StringRedisTemplate strings) {
        this.strings = strings;
    }

    public String read(String key) {
        return strings.opsForValue().get(key);
    }
}
```

Create test data on Redis:

```redis
SET diag:472:first alpha
SET diag:472:second beta
SET diag:472:count 10
```

With the String serializer, regular results are:

```java
String first = strings.opsForValue().get("diag:472:first");
String second = strings.opsForValue().get("diag:472:second");
Long count = strings.opsForValue().increment("diag:472:count");

// first  = "alpha"
// second = "beta"
// count  = 11
```

This is the **baseline** for comparison. Diagnostic tests should use dedicated keys to avoid results being affected by other threads or tests. Do not use production Redis or `FLUSHALL` just to test a few commands.

## 4. How Does Pipelining Work?

**Pipelining** sends multiple commands without waiting for each individual reply. Redis processes the commands in the order received on the connection, while the client collects the replies afterward.

```text
App                                 Redis
 | --- GET k1 ---------------------> |
 | --- GET k2 ---------------------> |
 | --- INCR c ---------------------> |
 |                                  | GET k1
 |                                  | GET k2
 |                                  | INCR c
 | <--- "alpha" ------------------- |
 | <--- "beta" -------------------- |
 | <--- 11 ------------------------ |
```

In Spring Data Redis, `executePipelined(...)` opens a pipeline on the Redis connection, runs the callback to issue commands, and then reads and deserializes the replies. **The callback returns `null`; the list returned by the `executePipelined` method is the result to use.**

### 4.1. Safe Example Using SessionCallback

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> results = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations)
                    throws DataAccessException {

                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");

                // Do not return the result of a Redis command here.
                return null;
            }
        });

// results is typically ["alpha", "beta"]
```

Inside `SessionCallback`, `RedisOperations` uses the same session/connection within the callback. There is no need to open, close, or manually create a new connection for each operation.

### 4.2. Why Shouldn't You Write Conditionals Inside the Callback?

Wrong:

```java
strings.executePipelined(
        (org.springframework.data.redis.core.SessionCallback<Object>)
                operations -> {
                    Object value = operations.opsForValue()
                            .get("diag:472:first");
                    if ("alpha".equals(value)) {
                        operations.opsForValue()
                                .set("diag:472:status", "OK");
                    }
                    return null;
                });
```

Inside a pipeline, `value` is not guaranteed to be the real reply (it is usually `null`). The `if` branch does not execute even though Redis has the data. That is a bug of **depending on data that has not been returned yet**, not Redis reading incorrectly.

Fix this in one of three ways:

1. Read the key **before** the pipeline (if atomicity with subsequent writes is not required).
2. Use Lua for atomic read-check-write on the Redis server.
3. If CAS based on read data is required, use `WATCH`/`MULTI`/`EXEC` with business-conditioned retries.

Do not use a pipeline with a batch of `GET`s and then branch based on their results **right inside the same callback**.

## 5. Raw RedisCallback vs Template-Using SessionCallback

`executePipelined` accepts both `RedisCallback` and `SessionCallback`, but the two approaches have different abstraction levels.

### 5.1. RedisCallback: Working with RedisConnection and byte[]

```java
import java.nio.charset.StandardCharsets;
import java.util.List;
import org.springframework.data.redis.core.RedisCallback;

List<Object> results = strings.executePipelined(
        (RedisCallback<Object>) connection -> {
            byte[] a = "diag:472:first"
                    .getBytes(StandardCharsets.UTF_8);
            byte[] b = "diag:472:second"
                    .getBytes(StandardCharsets.UTF_8);

            // Immediate results inside a pipeline are usually null.
            byte[] queuedA = connection.stringCommands().get(a);
            byte[] queuedB = connection.stringCommands().get(b);

            // Do not treat queuedA/queuedB as real data.
            return null;
        });
```

This is a **connection-level API**: arguments are bytes. If the key was previously written using `JdkSerializationRedisSerializer`, the `UTF-8` bytes above will not find the physical key. You must use a serializer compatible with the writer.

### 5.2. SessionCallback: Using RedisOperations

```java
List<Object> results = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");
                return null;
            }
        });
```

When using `StringRedisTemplate`, value/key operations follow the configured String serializer. This is generally easier to use when working at the object level without manually passing byte arrays.

### 5.3. The Callback Must Return null

The `executePipelined` API requires the callback to return `null`. A non-null callback return value does **not** become the return value of `executePipelined`; some versions check for it and throw an error. The result list is built from the replies collected after the pipeline.

Do not write:

```java
return operations.opsForValue().get(key); // Violates the pipeline callback contract
```

Instead:

```java
operations.opsForValue().get(key);
return null;
```

Then process `List<Object>` outside.

## 6. Why Does the Pipeline Result List Differ from Single-Call Results?

`RedisTemplate` receives a series of raw Redis replies and deserializes them according to the serializer configuration. Each command has a **different reply type**.

| Redis Command | Server Reply | Common Java Type After Spring Conversion |
|---|---|---|
| `GET key` | Bulk String or nil | `String`/DTO or `null` if key does not exist |
| `INCR key` | Integer | `Long` |
| `EXISTS key` | Integer (key count) | Boolean or Long depending on abstraction/overload |
| `SET key value` | Status reply `OK` | Boolean/status-converted value depending on API |
| `HGETALL key` | Fields/values | Map decoded according to hash serializers |
| `LRANGE key a b` | Array of bulk strings | List of deserialized data |
| `TTL key` | Integer | Long/Duration depending on API |
| `ZADD` | Integer | Boolean/Long depending on method |

Do not cast `results.get(i)` to always be a `String`. If a pipeline contains both `GET` and `INCR`, one reply may be a String and another a Long.

### 6.1. Order in the Result List

On a single connection, Redis returns replies in the order commands were sent. However, **how Spring Data Redis converts status/transaction replies and nested collections** depends on the command/adapter. In tests you must:

1. Know exactly which commands the callback issued.
2. Know what server reply format each command produces.
3. Verify the serializer being used.
4. Not add/remove commands in the callback while still hardcoding old indices.

A minimal test with two `GET`s avoids many conversion variations:

```java
List<Object> result = strings.executePipelined(
        new SessionCallback<Object>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("diag:472:first");
                operations.opsForValue().get("diag:472:second");
                return null;
            }
        });

// With the two prepared String keys, result = ["alpha", "beta"].
```

### 6.2. Do Not Confuse Real null with Deferred null

Two different situations:

```text
Inside pipeline callback:
  immediateReply = null
  -> Cannot conclude yet whether the Redis key exists.

After executePipelined:
  results = [null]
  -> The GET command actually received a nil reply (or conversion needs checking).
```

To diagnose a missing key, check `EXISTS`/`TYPE`/`GET` with a **regular operation outside the pipeline** on the exact DB/node and serializer. Do not apply that same rule to every collection type when the Redis key is a Hash/Stream.

## 7. Serializers: A Silent Cause of Unexpected Results

`StringRedisTemplate` uses String serializers for key/value/hash for String usage. An unconfigured `RedisTemplate<Object,Object>` may use JDK serialization by Spring Data Redis default; project templates may also override serializers.

```text
Java key       -- keySerializer ------> Redis key bytes
Java value     -- valueSerializer ----> Redis value bytes
Redis reply    -- resultSerializer ---> Java output
```

When running a pipeline or transaction, Spring needs to deserialize the **set of replies**. According to the documentation, RedisTemplate uses value, hash-key, and hash-value serializers for appropriate result types; the API also provides an overload for a dedicated **result serializer**.

### 7.1. Signs of Mismatch

For example, actual data in Redis:

```redis
SET diag:472:first alpha
```

`StringRedisTemplate` reads `"alpha"`. However, a `RedisTemplate` using JDK serializer for values may attempt to deserialize the ASCII bytes `alpha` as a Java serialized object and throw `SerializationException`.

Similarly, using raw `RedisConnection.get` with a String key when the writer's key serializer is JDK may return nil because the **key bytes differ**, not because the value was lost.

### 7.2. Choosing the Right Result Serializer When Needed

RedisOperations has an overload:

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>)
                connection -> {
                    byte[] key = "diag:472:first"
                            .getBytes(java.nio.charset.StandardCharsets.UTF_8);
                    connection.stringCommands().get(key);
                    return null;
                },
        org.springframework.data.redis.serializer
                .StringRedisSerializer.UTF_8);
```

This snippet illustrates choosing a dedicated serializer for String values; constant/factory method names may vary across versions, so for broad compatibility in Spring Data Redis 3.x, you can pass `new StringRedisSerializer()`.

```java
List<Object> replies = strings.executePipelined(
        (org.springframework.data.redis.core.RedisCallback<Object>) c -> {
            c.stringCommands().get(
                    "diag:472:first".getBytes(
                            java.nio.charset.StandardCharsets.UTF_8));
            return null;
        },
        new org.springframework.data.redis.serializer.StringRedisSerializer());
```

**Note:** The serializer passed into the overload is used for appropriate value replies/collections. Numeric and boolean/status replies have their own conversion mechanisms; do not expect a String serializer to turn every response into a String.

### 7.3. Hash Results Need Hash Serializers

If a pipeline contains:

```java
operations.opsForHash().entries("diag:472:profile");
```

the Hash key and Hash field are two different levels. Spring uses `hashKeySerializer` and `hashValueSerializer` to interpret fields/values. When forcing a specialized result serializer, you must understand how it affects Hash fields and values according to the API overload. Do not misread JSON/JDK-serialized `byte[]` and think Redis returned wrong data.

### 7.4. Golden Tests Help Confirm the Wire Contract

A good test:

1. Writes String/Hash using the template used in production.
2. Uses Redis CLI or raw byte API to verify key bytes/value format.
3. Runs the same command normally.
4. Runs the equivalent pipeline/transaction.
5. Compares the **semantic value after deserialization** rather than just `Object.toString()`.

When changing serializers during a rolling deploy, save fixtures from the old version to detect compatibility breaks.

## 8. Redis Transactions: MULTI, EXEC, DISCARD, WATCH

A Redis transaction uses:

```redis
MULTI
SET diag:472:tx after
GET diag:472:tx
EXEC
```

Redis responses:

```text
MULTI            -> OK
SET ...          -> QUEUED
GET ...          -> QUEUED
EXEC             -> [OK, "after"]
```

Before `EXEC`, commands are only **queued**. Redis processes the queued commands sequentially, without allowing commands from other clients to interleave during that transaction's `EXEC`.

**Not equivalent to SQL rollback:** Redis does not automatically revert writes already performed when another command in the list fails at execution time.

### 8.1. Commands Called Inside a Transaction May Return null

```java
operations.multi();
Object queued = operations.opsForValue().get("diag:472:tx");
// queued may be null; the actual reply is in operations.exec().
List<Object> replies = operations.exec();
```

Do not write:

```java
operations.multi();
String value = (String) operations.opsForValue().get(key);
if (value == null) {
    // Wrong: cannot treat this as a cache miss.
}
operations.exec();
```

The query inside the transaction was `QUEUED`, not returning fresh data to Java.

## 9. Using SessionCallback to Keep the Same RedisConnection

Spring Data Redis explicitly states that `RedisTemplate` **does not guarantee** multiple separate method calls will always use the same connection for a transaction. `SessionCallback` allows multiple `RedisOperations` within the same session/connection.

Example:

```java
import java.util.List;
import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

List<Object> replies = strings.execute(
        new SessionCallback<List<Object>>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public List<Object> execute(RedisOperations ops)
                    throws DataAccessException {

                ops.multi();
                boolean transactionOpen = true;
                try {
                    ops.opsForValue().set("diag:472:tx", "after");

                    // The value here is not the real GET reply yet:
                    Object queued = ops.opsForValue()
                            .get("diag:472:tx");

                    List<Object> result = ops.exec();
                    transactionOpen = false;
                    return result;
                } catch (RuntimeException failure) {
                    if (transactionOpen) {
                        try {
                            ops.discard();
                        } catch (RuntimeException cleanupError) {
                            failure.addSuppressed(cleanupError);
                        }
                    }
                    throw failure;
                }
            }
        });

// replies contains the replies for SET and GET after EXEC.
// Use the String serializer and check each element by command type.
```

Here the `queued` variable is only to illustrate the phenomenon; do not use it as current data. If you only need to write `SET` and then read the result, calling `GET` **after `EXEC` outside the transaction** is usually easier to understand.

### 9.1. Why Must You DISCARD on Error?

Suppose:

```text
MULTI    -> OK
SET ...  -> QUEUED
Network timeout before EXEC
```

The connection may remain in an unfinished transaction state. If the connection is returned to the pool without cleanup, subsequent commands risk being queued or exhibiting unexpected behavior. Therefore, Spring Data Redis documentation recommends calling `DISCARD` when an exception occurs between `MULTI` and `EXEC`.

However, if the connection is already dead, `DISCARD` may also fail; you need to close/evict the connection via the driver/pool mechanism instead of just swallowing the error. And if a timeout occurs **after `EXEC` has already reached Redis**, the client may not know whether the transaction executed; `DISCARD` is not a way to roll back writes that already ran.

### 9.2. Do Not Call MULTI on One Template and EXEC on Another Connection

Dangerous pattern:

```java
strings.multi();
strings.opsForValue().set(key, "new");
List<Object> values = strings.exec();
```

Without proper connection binding, multiple independent template methods are not guaranteed to use the exact same connection. Use `SessionCallback` or properly configured transaction support integration; do not assume a sequence of method calls always pins the same connection.

## 10. @Transactional Does Not Automatically Enable Redis Transactions

A common misconception:

```java
@Transactional
public void update() {
    databaseRepository.save(entity);
    redisTemplate.opsForValue().set(key, "new");
}
```

**By default, `RedisTemplate` does not automatically participate in Spring-managed transactions.** Annotations may manage JDBC/JPA, while Redis still sends `SET` immediately if Redis transaction support is not enabled. A SQL rollback does not automatically revert a `SET` that already succeeded.

### 10.1. Enabling Transaction Support on the Template

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.core.StringRedisTemplate;

@Configuration(proxyBeanMethods = false)
public class RedisTxConfiguration {

    @Bean
    public StringRedisTemplate stringRedisTemplate(
            RedisConnectionFactory factory) {

        StringRedisTemplate template =
                new StringRedisTemplate(factory);
        template.setEnableTransactionSupport(true);
        return template;
    }
}
```

Prerequisites:

- There is an **active Spring-managed transaction**.
- An appropriate `PlatformTransactionManager` is configured, such as a JDBC transaction manager.
- The call goes through the proper proxy/transaction boundary (self-invocation `this.method()` can bypass `@Transactional` in Spring proxy mode).
- This template is the **exact bean** the application uses; do not enable it on a different template and expect all Redis operations to participate automatically.

Spring Data Redis **does not provide a dedicated Redis PlatformTransactionManager**; it participates in the transaction manager already used by the application via connection binding/transaction synchronization.

### 10.2. Read-Only Commands in a Spring-Managed Transaction

This is the most easily misunderstood point:

```java
@Transactional
public String example() {
    strings.opsForValue().set("diag:472:managed", "updated");
    return strings.opsForValue().get("diag:472:managed");
}
```

With Redis transaction support enabled, **writes** are queued to execute at commit time. **Read-only commands** may be routed by Spring Data Redis to **another non-transactional connection** to reply immediately. That reading connection **does not see uncommitted writes**.

Therefore, the method may return **the old value or null**, even if the transaction later commits properly. This differs from the "read your writes" expectation inside a SQL transaction.

Do not treat this as proof that `SET` failed. If business logic needs to make decisions based on the new value in the same atomic operation:

- Use Lua for read-check-write.
- Or read before the transaction and use `WATCH` to protect optimistic consistency.
- Or redesign to read only after the Redis transaction completes.

### 10.3. Redis and JDBC Commit Is Not a Distributed XA Transaction

When Redis participates in a Spring-managed transaction, Spring can coordinate callbacks, but that **does not create an atomic commit across Redis and a SQL database**. One resource may commit while the other fails.

If business logic requires synchronizing SQL and Redis, typically:

1. Choose SQL as the authoritative data source.
2. Write changes inside the SQL transaction.
3. Emit an outbox event in the same SQL transaction.
4. Have a worker update Redis with idempotency/retry/reconciliation.

Do not use `@Transactional` as a guarantee that the database and Redis can never go out of sync.

## 11. WATCH: Why Does EXEC Update Nothing?

`WATCH` implements optimistic locking: it monitors one or more keys; if a key is modified by another client (or expires/is evicted according to Redis version semantics), `EXEC` will **abort** the transaction.

```text
Client A                            Client B
  | WATCH counter                     |
  | GET counter -> "10"                |
  |                                   | SET counter "99"
  | MULTI                             |
  | SET counter "11"                  |
  | EXEC -> aborted                   |
  |                                   |
  +-- A's update must not be treated as successful.
```

Redis returns a **nil/Null reply for EXEC** on a WATCH conflict; the Spring abstraction may represent the failure via a `null` result or a result form that must be checked per version/driver. Do not assume an empty result means a committed transaction.

### 11.1. Reading Before MULTI on the Same Session

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

Boolean changed = strings.execute(
        new SessionCallback<Boolean>() {
            @Override
            @SuppressWarnings({"rawtypes", "unchecked"})
            public Boolean execute(RedisOperations ops) {

                String key = "diag:472:cas";
                ops.watch(key);

                boolean transactionOpen = false;
                try {
                    // GET before MULTI: reads the current value.
                    String current = (String) ops.opsForValue().get(key);
                    if (!"old".equals(current)) {
                        ops.unwatch();
                        return false;
                    }

                    ops.multi();
                    transactionOpen = true;
                    ops.opsForValue().set(key, "new");

                    List<Object> outcome = ops.exec();
                    transactionOpen = false;

                    // WATCH conflict -> transaction did not commit.
                    return outcome != null && !outcome.isEmpty();
                } catch (RuntimeException error) {
                    if (transactionOpen) {
                        try {
                            ops.discard();
                        } catch (RuntimeException cleanupError) {
                            error.addSuppressed(cleanupError);
                        }
                    } else {
                        try {
                            ops.unwatch();
                        } catch (RuntimeException cleanupError) {
                            error.addSuppressed(cleanupError);
                        }
                    }
                    throw error;
                }
            }
        });
```

This is a simple CAS example; when multiple clients contend, the application must decide to **retry** with a bounded number of attempts, appropriate backoff, and business-level idempotency. `WATCH` does not let Java read the reply of a `GET` that was QUEUED after `MULTI`.

### 11.2. WATCH and Expiration

A key expiring or being evicted while being `WATCH`ed can cause `EXEC` to abort. Redis versions prior to 6.0.9 differ in whether expiration counts as a modification for WATCH. When comparing behavior between test and prod, identify the actual Redis version and TTL.

### 11.3. Do Not Use WATCH Inside a Pipeline as an Immediate Value Read

A WATCH-CAS requires:

1. `WATCH`.
2. `GET` receiving a **real reply before deciding**.
3. Checking the condition on the client.
4. `MULTI`/queued writes.
5. `EXEC`.

If you put everything into a pipeline and read `GET` inside the callback, the result is deferred, so you cannot make the right decision at step 3. Lua is usually simpler for updates that depend only on Redis data.

## 12. Redis Transactions Have Two Very Different Error Types

### 12.1. Queue-Time Errors

For example, a syntactically invalid command:

```redis
MULTI
SET mykey             # Missing argument; Redis reports error when queuing
SET otherkey ok
EXEC
```

In modern Redis, a queue-time error marks the transaction as invalid; `EXEC` refuses to run the entire queue. When debugging Java, do not look only at the `EXEC` result and ignore exceptions thrown while preparing commands.

### 12.2. Errors During EXEC

```redis
SET diag:472:number hello
MULTI
SET diag:472:before ok
INCR diag:472:number
SET diag:472:after ok
EXEC
```

At `EXEC`, `INCR` fails because the value `hello` is not an integer. However, the other commands in the transaction may **still have executed**. Redis does not roll back `SET before` or `SET after` because one command failed at runtime.

This is a critical difference from SQL transactions:

| Case | Redis Transaction |
|---|---|
 `DISCARD` before EXEC | Discards all unexecuted commands |
| Syntax error before EXEC | Transaction may be aborted before running |
| WATCH conflict | Does not execute queued commands |
| One command fails at runtime in EXEC | Does not roll back other commands that executed |
| Disconnection before EXEC | Queue not yet EXECed, typically no effects |
| Disconnection during/right after EXEC | Client may not know whether transaction ran |

**Do not treat `DISCARD` as "ROLLBACK already-committed Redis writes".** After `EXEC`, DISCARD cannot reverse state.

## 13. Combining Pipelines with MULTI/EXEC

Spring Data Redis allows some forms of `executePipelined(SessionCallback)` containing `MULTI`/`EXEC`. This is a case with **two layers of reply deferral**:

```text
Java callback -> MULTI
              -> SET key A     (Redis QUEUED)
              -> GET key       (Redis QUEUED)
              -> EXEC          (Redis returns an array of replies)
Pipeline close -> Java reads the list of replies
```

When using them together:

- Do not expect `ops.exec()` inside the callback to immediately return a list like a regular transaction outside a pipeline.
- Do not assume `executePipelined` will always flatten `EXEC` results into the same structure as a non-transactional pipeline; check your Spring Data Redis/driver version.
- Do not send more commands after the transaction in the same callback and guess result indices without knowing the reply shape.
- Do not use this combination for steps that need to **take the output of EXEC and decide the next command within the same callback**.

### 13.1. When Should You Avoid Combining Them?

If the goal is:

1. **Higher throughput only** when sending many independent commands: use a plain pipeline.
2. **Non-interleaved execution of writes on a single Redis node:** use `SessionCallback` + `MULTI/EXEC`.
3. **Atomic read-branch-write:** use Lua or WATCH-CAS.
4. **Both throughput and transactional grouping:** consider pipeline+transaction, but add tests for result shape and failure handling.

Do not use pipeline+transaction as a default optimization without benchmarking round trips, connection behavior, and the results you need.

## 14. When @Transactional Meets a Different RedisTemplate

An application may inject:

```text
redisTemplate (RedisTemplate<Object,Object>)
stringRedisTemplate (StringRedisTemplate)
customCacheTemplate (RedisTemplate<String,DTO>)
```

If you only enable `setEnableTransactionSupport(true)` on `stringRedisTemplate`, the remaining templates do not participate by default. The outcome can be:

```text
Template A: queued write, EXECed at commit
Template B: immediate write, already completed
Template C: different serializer, sees different key or deserialization fails
```

Diagnostic procedure:

1. Identify the actual **bean name/class** injected.
2. Identify the connection factory used by each template.
3. Identify which templates have transaction support enabled.
4. Check the active transaction manager and propagation.
5. Check serializers/key bytes.
6. Compare behavior inside the same session and outside the session.

Do not look only at the name `RedisTemplate` and conclude it behaves identically to `StringRedisTemplate`.

## 15. Connections, Threads, and Transaction Lifecycle

Spring-managed Redis transactions use connection binding attached to a **thread-bound transaction** in the imperative model. Bugs can appear when offloading work to another thread:

```java
@Transactional
public void updateInTwoThreads() {
    strings.opsForValue().set("diag:472:one", "A");

    CompletableFuture.runAsync(() ->
            strings.opsForValue().set("diag:472:two", "B"));
}
```

The `runAsync` task runs on another thread and **does not automatically inherit the transaction context** bound by Spring to the calling thread. Write B may run outside transaction A. This is a propagation bug, not pipelining.

Similarly, `@Async`, schedulers, and custom Executors can split scope. Do not share a single Redis transaction/session across arbitrary threads; choose a connection/session with a clear lifecycle or design a different unit of work.

### 15.1. Connection Pools and Stuck Transaction State

If code enters `MULTI` and hits an exception before `EXEC` without calling `DISCARD`, reusing that connection can cause:

- New commands receiving unexpected responses because the connection is still in transaction state.
- Operation results being deferred.
- Unexpected errors or queuing.
- Side effects getting bundled into the wrong transaction.

Good policy:

1. Use `SessionCallback` to manage the same connection.
2. Clean up with `DISCARD` when a transaction is incomplete.
3. Do not manually close connections managed by the template inside the callback.
4. When a connection suffers a severe failure, let the driver/pool evict the unhealthy connection.
5. Test exception paths, not just happy paths.

## 16. Lettuce and Jedis Differ in Certain Capabilities

Spring Data Redis can run with Lettuce or Jedis. Same `RedisTemplate` API, yet:

- Connection/pooling management and auto-flush behavior can differ.
- Redis Cluster pipelining depends on the driver and the range of commands supported per Spring Data Redis version.
- Commands that do not support cross-slot may fail even though standalone succeeds.
- Retries/timeouts/read-from-replica can make **when data becomes visible** differ.

Lettuce provides `PipeliningFlushPolicy`, allowing control over batch flushing in some Spring Data Redis versions. Illustrative example:

```java
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.connection.lettuce
        .LettuceConnection.PipeliningFlushPolicy;

// Illustrating API in supported versions only:
LettuceConnectionFactory factory = ...;
factory.setPipeliningFlushPolicy(
        PipeliningFlushPolicy.buffered(3));
```

Flush policy affects sending commands; **it does not turn a pipeline into a transaction**. When debugging, pin the driver/configuration and use appropriate integration tests; do not infer behavior from a different adapter.

### 16.1. Do Not Equate Pipeline with MGET

`MGET key1 key2` is **one Redis command** returning an array. A pipeline of `GET key1` and `GET key2` is **two commands**; they may return the same data under normal conditions, but semantics/ACL/Cluster restrictions differ.

With Cluster:

- `MGET` on keys in different slots can fail with `CROSSSLOT`.
- Two individual `GET`s may route to two masters depending on the driver.
- Pipelining across multiple nodes has driver-specific support/limitations.

Do not look only at Java's `List<Object>` and conclude "it's the same operation".

## 17. Redis Cluster: Why Do Individual Commands Run While Transactions Fail?

Redis Cluster partitions keys across **16,384 hash slots**. Multi-key transactions or Lua scripts require the same slot.

```text
diag:472:order:{913}:state
diag:472:order:{913}:total
                 |
             hash tag {913}
                 |
              same slot

diag:472:order:{914}:state
                 |
             different slot
```

If a transaction includes keys in different slots, Redis may return `CROSSSLOT` or the driver may reject/not support grouping. Use hash tags intentionally for data needing atomic multi-key operations; do not put the entire system under one hash tag as that creates a hot slot.

### 17.1. Cluster Checklist

1. Is the Redis connection actually Standalone, Sentinel, or Cluster?
2. Are the keys in `MULTI/EXEC` in the same slot?
3. Are you using the same `StringRedisSerializer` for keys?
4. Is there a cross-slot command not supported by the driver?
5. Did Redis Cluster topology/slot mapping just change?
6. Does the client follow `MOVED`/`ASK` redirects and retry properly?
7. Are Standalone tests masking Cluster failures?

If a pipeline returns different results per node, check read preference. A `GET` reading a replica may see staler data than the master due to asynchronous replication; that is the consistency model, not necessarily a serialization bug.

## 18. Reactive Redis Does Not Share Thread-Bound Assumptions

`ReactiveRedisTemplate`/`ReactiveStringRedisTemplate` returns Publishers. In reactive code:

```java
Mono<String> mono =
        reactiveStrings.opsForValue().get("diag:472:first");
```

`mono` is not yet a `String`. The command is issued upon subscription; a `StepVerifier` or subscriber receives the value:

```java
StepVerifier.create(
        reactiveStrings.opsForValue().get("diag:472:first"))
    .expectNext("alpha")
    .verifyComplete();
```

Do not compare `Mono<String>` directly to `String` or call `subscribe()` and immediately assert an external variable: that is an **async sequencing** bug.

### 18.1. Imperative @Transactional Does Not Automatically Cover Reactive Chains

Spring reactive transactions use **Reactor Context**, not the same default ThreadLocal as imperative transaction managers. A method mixing JDBC `@Transactional`, `RedisTemplate`, and `ReactiveRedisTemplate` does not automatically create a consistent transaction across all resources.

To group reactive Redis operations on a single connection/session, you must use the API/session support provided by your **reactive Spring Data Redis version** and verify against real Redis. Do not copy `RedisTemplate.multi()/exec()` verbatim to reactive and assume identical semantics.

### 18.2. Pipelining Differs from Reactive Flux Concurrency

Using `flatMap` across many Redis commands concurrently can increase concurrency, but it is not equivalent to `executePipelined` using one controlled connection/batch. Completion order of multiple Publishers can differ from emission order, and `collectList()` can buffer a very large amount of data. Use `concatMap` or appropriate ordering when business logic requires it, bound concurrency, and measure network usage.

## 19. Timeouts: Unknown Outcome Does Not Mean the Command Didn't Run

A transaction:

```text
Java -------- MULTI/SET/EXEC -------> Redis
Java <--- timeout / connection lost --+
Redis already executed EXEC, but reply did not reach Java
```

From the client's perspective, the result is an **unknown outcome**. Automatically retrying the entire transaction can execute writes twice. With `INCR`, the counter can increment twice; with `LPUSH`, a message can be pushed twice. Never interpret a timeout exception as "Redis definitely did not write".

The solution depends on business requirements:

- Use a `requestId`/idempotency key when operations have side effects.
- Choose idempotent commands where possible (e.g., `SET key sameValue` is not like `INCR`).
- Log transaction IDs and perform reconciliation.
- Bound retry counts and backoff.
- When needing an exactly-once effect across Redis and another DB, design an authoritative ledger/outbox rather than just retrying Redis.

### 19.1. Avoid Retrying After a null Result Inside a Callback

`null` inside a pipeline/transaction callback is **normal behavior**, not a signal to retry. Retrying based on it can multiply unintended requests/commands.

Only evaluate retries after receiving the final reply or an explicit exception at the transaction/pipeline boundary, along with an idempotency policy.

## 20. ACLs and Command Permissions When Moving to Pipelines/Transactions

A service with `+get +set ~app:*` permissions runs regular commands fine, but adding transactions may require:

```text
+multi
+exec
+discard
+watch
+unwatch
```

If using Lua instead of transactions, `EVAL`/`EVALSHA` and the commands executed by the script may be needed. Command/key permissions are still checked by Redis ACLs; pipelining does not bypass ACLs.

### 20.1. Diagnosing NOPERM

Distinguish between:

- `NOPERM` immediately when queuing a command inside a transaction.
- `NOPERM` on `MULTI`/`EXEC` because the account lacks those commands.
- `NOPERM` on a key pattern because the key serializer/prefix changed.
- `NOPERM` for auxiliary driver/health commands.

Do not open `+@all ~*` just because migrating to pipelines/transactions caused an error. Use `ACL LOG` and, on Redis 7+, `ACL DRYRUN` in a controlled environment to identify the exact permissions to add.

## 21. Step-by-Step Diagnostic Table

When noticing results differ from regular operations, follow this procedure:

### Step 1 — Record the Environment

```text
Spring Boot version:
Spring Data Redis version:
Client: Lettuce / Jedis:
Redis server version:
Topology: Standalone / Sentinel / Cluster:
Template bean:
Connection factory:
Key / value / hash serializers:
setEnableTransactionSupport:
Active @Transactional / PlatformTransactionManager:
```

Without this information, it is easy to guess wrong because defaults/overloads change by version.

### Step 2 — Run a Single Command as a Baseline

On test Redis / test namespace:

```java
String expected = strings.opsForValue().get("diag:472:first");
```

If the baseline is already wrong, check **key existence, Redis type, serializer, TTL, host/DB/slot** before concluding the pipeline/transaction is broken.

### Step 3 — Confirm Commands Were Actually Enqueued

In a pipeline, the callback must issue commands and `return null`. In a transaction, you must see `multi`, queued commands, and then `exec`. If an exception occurs before `exec`, check `DISCARD` cleanup.

### Step 4 — Observe Results at the Right Boundary

```text
Pipeline      -> result of executePipelined(...)
Manual TX     -> result of operations.exec()
Managed TX    -> after transaction completion, read outside transaction
Reactive      -> subscribe/StepVerifier completed
```

Do not take a temporary variable assigned inside the callback as the final result.

### Step 5 — Check Result Types

Log the **class and index** of each element in a test list (avoid logging sensitive payloads):

```java
for (int i = 0; i < replies.size(); i++) {
    Object item = replies.get(i);
    System.out.printf(
            "reply[%d] type=%s%n",
            i,
            item == null ? "null" : item.getClass().getName());
}
```

If a reply is `byte[]`, do not print `toString()` directly (it prints the Java array identity string). Use the corresponding serializer or a hex dump **on lab data**, never printing customer sessions/tokens.

### Step 6 — Compare Physical State on Redis

```redis
TYPE diag:472:first
GET diag:472:first
TYPE diag:472:count
GET diag:472:count
PTTL diag:472:first
```

If the key is a Hash, use `HGET`/`HGETALL` instead of `GET`. In Cluster, the CLI must connect to the right node/route, e.g., using `redis-cli -c` when redirects are needed.

### Step 7 — Check Concurrent Environment

For WATCH conflicts, check other writers, expiration/eviction, and retries. For pipelines, check whether commands depend on one another and whether the pipeline runs concurrently with other clients. Pipelines **do not block** other clients from interleaving between commands.

### Step 8 — Write a Minimal Reproducing Integration Test

A test with **two fixed String keys and one `GET`/`INCR`** usually isolates bugs much faster than an entire business flow in a controller. Once semantics are understood, expand to multi-element pipelines/batches.

## 22. Observing Redis/Driver Without Heavy Impact

Observation commands suitable for operational accounts:

```bash
redis-cli -h 127.0.0.1 -p 6379 INFO server
redis-cli -h 127.0.0.1 -p 6379 INFO clients
redis-cli -h 127.0.0.1 -p 6379 INFO commandstats
redis-cli -h 127.0.0.1 -p 6379 SLOWLOG GET 10
redis-cli -h 127.0.0.1 -p 6379 LATENCY LATEST
```

`SLOWLOG` reflects the time Redis spent executing the command; it **does not include full network latency or Java deserialization time**. A large pipeline can cause the JVM to consume substantial memory buffering replies, even if individual Redis command times are low.

### 22.1. Use MONITOR Carefully

`MONITOR` streams commands continuously, which can add overhead and expose sensitive key names/payloads/metadata. Do not leave it enabled on production just to find the cause of a `null`. If needed, use lab Redis, limit duration, and use test data.

### 22.2. Driver Logs and Traces

When needed:

- Enable appropriate logging for Spring Data Redis/Lettuce/Jedis in test environments.
- Record start/end timestamps of pipelines and `EXEC`.
- Attach trace IDs to requests and Redis command batches.
- Log connection endpoints/nodes and topology events, never credentials.
- Measure command count/batch, reply count, and deserialization duration.

Do not equate a "command queued" log with "Redis executed and replied successfully".

## 23. Testcontainers: Testing All Three Paths Against Real Redis

Mocking RedisTemplate cannot verify server-side transaction/pipeline semantics. With Testcontainers, you can reproduce `null`, reply lists, `WATCH` conflicts, and serializer types directly on test Redis.

### 23.1. Gradle Dependencies

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
```

### 23.2. Redis Container and Spring Properties

```java
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

@SpringBootTest
@Testcontainers
class RedisTxPipelineIntegrationTest {

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
}
```

Place tests in a class with a valid Spring Boot application context. The Redis image is for lab use only; pin/version it according to CI policy. Testcontainers requires Docker or a compatible container runtime.

### 23.3. Test 1 — Baseline vs Pipeline Result

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

@Autowired
StringRedisTemplate strings;

@Test
void pipelineReturnsRepliesAfterCallback() {
    String id = UUID.randomUUID().toString();
    String a = "it:472:" + id + ":a";
    String b = "it:472:" + id + ":b";

    strings.opsForValue().set(a, "alpha");
    strings.opsForValue().set(b, "beta");

    try {
        assertThat(strings.opsForValue().get(a)).isEqualTo("alpha");

        List<Object> replies = strings.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        Object immediateA = ops.opsForValue().get(a);
                        Object immediateB = ops.opsForValue().get(b);
                        assertThat(immediateA).isNull();
                        assertThat(immediateB).isNull();
                        return null;
                    }
                });

        assertThat(replies).containsExactly("alpha", "beta");
    } finally {
        strings.delete(a);
        strings.delete(b);
    }
}
```

This test intentionally asserts `null` **inside the callback** and accurate data **outside the callback**. This is behavior to understand, not a bug.

### 23.4. Test 2 — Manual Transaction Results

```java
import static org.assertj.core.api.Assertions.assertThat;
import java.util.List;

@Test
void execReturnsQueuedCommandReplies() {
    String key = "it:472:" + UUID.randomUUID();
    try {
        List<Object> replies = strings.execute(
                new SessionCallback<List<Object>>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public List<Object> execute(RedisOperations ops) {
                        ops.multi();
                        boolean active = true;
                        try {
                            ops.opsForValue().set(key, "new");
                            Object inside = ops.opsForValue().get(key);
                            assertThat(inside).isNull();

                            List<Object> outcome = ops.exec();
                            active = false;
                            return outcome;
                        } catch (RuntimeException e) {
                            if (active) {
                                try {
                                    ops.discard();
                                } catch (RuntimeException ignored) {
                                    // Connection error should still let the test fail
                                    // with the original root cause.
                                }
                            }
                            throw e;
                        }
                    }
                });

        assertThat(replies).hasSize(2);
        assertThat(replies.get(1)).isEqualTo("new");
        assertThat(strings.opsForValue().get(key)).isEqualTo("new");
    } finally {
        strings.delete(key);
    }
}
```

Do not force `replies.get(0)` of `SET` to a fixed status type without verifying the API/version; asserting `GET` and post-commit data is more useful.

### 23.5. Test 3 — WATCH Conflict

On a dedicated test Redis:

1. Client A uses `SessionCallback` to call `WATCH key` and read the old value.
2. Synchronize with Client B using `CountDownLatch` so B modifies the key after A has called WATCH.
3. Client A calls `MULTI`, queues a SET, and calls `EXEC`.
4. Verify A does **not** overwrite B's value.
5. Read the EXEC/collision result according to the Spring/driver version.

**Do not use fixed sleeps** to "hope B writes at the right time". Latches/barriers make conflicts reliably reproducible; use two independent Redis connections in the test. The test must have timeouts and cleanup so CI does not hang.

### 23.6. Test 4 — Runtime Errors Do Not Roll Back

1. Set a String key `number` to `"not-a-number"`.
2. Inside `MULTI`, queue `SET before ok`, `INCR number`, and `SET after ok`.
3. `EXEC`.
4. Observe the `INCR` error and the state of `before`/`after`.
5. Explain why Redis transactions lack SQL-style rollback.

Depending on the client abstraction, Redis errors in EXEC may appear inside `List<Object>` or be thrown as exceptions. Do not design tests relying solely on an exception type without knowing the adapter version.

### 23.7. Test 5 — Serialization and Replies

1. Write data with `StringRedisTemplate` and read via pipeline with the String serializer.
2. Write a JSON DTO with a typed JSON template.
3. Verify pipeline result deserialization for key/value/hash.
4. Use the wrong serializer to reproduce the exception.
5. Use the `executePipelined(..., resultSerializer)` overload and prove the result is correct once the matching format is chosen.

### 23.8. Test 6 — Managed @Transactional

1. Create a `StringRedisTemplate` with `setEnableTransactionSupport(true)`.
2. Use a real `PlatformTransactionManager` and `TransactionTemplate`/Spring proxy.
3. Write to Redis inside the transaction, then read before commit using a non-transactional connection.
4. After commit, read the value again.
5. Intentionally roll back and confirm queued Redis writes are not executed if the transaction does not reach commit.
6. Emphasize that the test does not prove atomic commit between Redis and SQL.

## 24. Cost Analysis: Pipelining Is Not Always Faster

Pipelining reduces round trips, yet still has costs:

- Redis must receive/process the commands.
- Redis may need to buffer many replies while the client hasn't read them yet.
- Spring Data Redis must hold a `List<Object>` containing many results.
- The JVM may allocate many byte arrays, Strings/DTOs, and trigger GC.
- An overly large batch can increase memory and cause latency spikes.
- When an O(N) script/command is inside a batch, pipelining does not make that command less CPU-intensive.

For example, a batch of 100,000 large-value GETs easily exhausts Redis/client RAM. Instead of growing batches indefinitely, use:

1. Moderate batch sizes validated by experiment.
2. Measure throughput and p95/p99, not just average.
3. Limit payload bytes/responses.
4. Clean up resources and handle errors per batch.
5. If replies are not needed, choose an appropriate API to avoid collecting unused data, depending on the Spring Data Redis version.

### 24.1. Pipelining Does Not Guarantee a Consistent Snapshot

A pipeline:

```text
GET account:balance
GET account:status
```

does not automatically guarantee the two values represent **the same point in time** if other writers can update between commands. If you need a consistent view under Redis semantics, use transactions/Lua or an appropriate versioned data design. Pipelining is only an optimization for transmitting commands/replies.

## 25. Error and Fix Matrix

| Symptom | Likely Cause | How to Confirm | How to Fix |
|---|---|---|---|
| `null` from `get` inside pipeline callback | Reply is deferred | `executePipelined` returns a list with data | Read results outside callback |
| Pipeline callback returns an object and API errors | Callback must return null | Check `executePipelined` contract | `return null` |
| Pipeline list has `Long` instead of `String` | Command is `INCR`/`TTL` | Print type of each reply in lab | Use `Number`/appropriate type |
| Pipeline list is undecoded bytes | Raw RedisCallback or wrong serializer | Compare bytes and template serializers | Use the right result serializer |
| `GET` after `MULTI` is null | Command only QUEUED | `EXEC` returns GET reply | Read from EXEC result |
| `GET` inside @Transactional sees old value | Write deferred, read on different connection | Read again after commit | Do not expect read-your-writes |
| @Transactional present but Redis writes immediately | Transaction support not enabled | Inspect bean/config | `setEnableTransactionSupport(true)` and manager |
| Tx commands on different connections | Disjoint template calls | Use SessionCallback | Bind connection to same session |
| EXEC aborts | WATCH conflict | Two-connection test | Bounded retry and idempotency |
| Transaction does not roll back after WRONGTYPE | Runtime error inside EXEC | Read state after EXEC | Choose Lua/validation and compensation |
| Connection appears stuck in MULTI | Missing DISCARD after exception | Inspect lifecycle/logs | Cleanup/evict failed connection |
| Standalone MGET works but multi-key fails | Cross-slot Redis Cluster | `CLUSTER KEYSLOT` | Same-slot key design |
| Cluster pipeline unsupported for command | Driver/version limitation | Compare Lettuce/Jedis/standalone | Choose compatible API/driver/topology |
| Only some keys return null | Different key bytes/prefix/serializer | Raw Redis CLI/serialization | Read matching key bytes |
| Redis client NOPERM after enabling tx | Missing MULTI/EXEC/WATCH or key rule | ACL LOG/DRYRUN | Grant minimal commands |
| Timeout then retry doubles counter | EXEC may have run while reply lost | Request ID/reconcile | Idempotency, bounded retry |
| Reactive test passes intermittently | Didn't subscribe/wait for Publisher | StepVerifier | Use reactive test properly |
| Pipeline batch spikes memory | Buffering many replies | JVM/Redis memory metrics | Split batches, limit value size |

## 26. Diagnostic Exercises

### Exercise 1 — Null Inside Callback Is Not a Cache Miss

1. Write `SET it:472:a alpha`.
2. Read with `StringRedisTemplate.opsForValue().get`, confirming `"alpha"`.
3. Call the same command inside `executePipelined`, print the immediately returned value.
4. Print the list returned by `executePipelined` outside the callback.
5. Explain the difference in when replies are received.

### Exercise 2 — Choosing SessionCallback vs RedisCallback

1. Write a two-GET pipeline using `SessionCallback`.
2. Write the equivalent pipeline using `RedisCallback` with UTF-8 `byte[]`.
3. Test with a key stored under a different serializer.
4. Compare `List<Object>` and how decoding works.
5. Document when to use template-level vs connection-level callbacks.

### Exercise 3 — MULTI/EXEC Does Not Return Values Immediately

1. Inside a `SessionCallback`, call `multi()`.
2. Queue `SET` and `GET` on the same key.
3. Record the result of `get()` inside the callback.
4. Call `exec()` and inspect replies.
5. Read the key again outside the transaction.
6. Try `discard()` before `exec()` in another transaction to see queued writes do not run.

### Exercise 4 — @Transactional and Read-Your-Writes

1. Enable Redis transaction support on the right template.
2. Register a transaction manager.
3. Write and read the same key inside one transactional method.
4. Read again after commit.
5. Explain why read-only Redis commands can use a different connection.
6. Try rolling back before commit and confirm queued writes do not execute.

### Exercise 5 — Controlled WATCH Conflict

1. Client A WATCHes a key and reads the current value.
2. Client B modifies the key.
3. Client A calls MULTI, queues SET, and calls EXEC.
4. Observe the transaction aborting and the key retaining B's value.
5. Write bounded retry and compare with Lua CAS.

### Exercise 6 — Runtime Errors Do Not Roll Back

1. Set key `number="hello"`.
2. Transaction queues `SET before ok`, `INCR number`, `SET after ok`.
3. Call EXEC.
4. Inspect actual state and error reply/exception.
5. Explain the difference between queue-time and execution-time errors.

### Exercise 7 — Pipeline Combined with Transaction

1. Use `executePipelined(SessionCallback)` with `multi()/exec()` on test Redis.
2. Record the callback return and the pipeline replies list.
3. Compare with a non-pipelined `execute(SessionCallback)` transaction.
4. Check nested/flat result shape for your Spring Data Redis version.
5. Do not hardcode indices without verifying the reply mapping.

### Exercise 8 — Redis Cluster and Serialization

1. Use a Redis Cluster lab with multiple masters.
2. Create two keys with the same hash tag and two keys with different hash tags.
3. Compare single `GET`, `MGET`, and multi-key transactions.
4. Check `CLUSTER KEYSLOT` and connection routing.
5. Change the key serializer in the lab and observe how the slot changes.

### Exercise 9 — Timeouts and Retries

1. Simulate lost response errors from Redis in a test environment.
2. Use `INCR` to see side effects may already have occurred.
3. Retry non-idempotently and observe the counter incrementing again.
4. Design a request ID/ledger suitable for business requirements.
5. Classify exceptions into retryable, non-retryable, and unknown outcome.

## 27. Production Debugging Checklist

**Results and semantics**

1. Is this a regular command, pipeline, manual transaction, or managed @Transactional?
2. Is the code reading a command's value inside a callback while the reply is still deferred?
3. Are results retrieved from the proper `executePipelined` or `exec` call?
4. Does the pipeline callback `return null`?
5. Is the code relying on an index in `List<Object>` after commands in the callback changed?
6. Are `Long`/`String`/`byte[]`/`Map` types checked properly per command?

**Connections and serialization**

7. Are you using the same `SessionCallback`/connection for MULTI/EXEC?
8. Which template is actually injected, and which factory does it use?
9. Is transaction support enabled on the **exact template**?
10. Is there an active Spring-managed transaction and appropriate transaction manager?
11. Is there a thread hop losing thread-bound context?
12. Is there DISCARD cleanup on exceptions between MULTI and EXEC?
13. Are key/value/hash serializers and the result serializer consistent?

**Data correctness**

14. Are WATCH conflicts detected and handled?
15. Are queue-time errors distinguished from execution-time errors?
16. Have you avoided assuming Redis transactions roll back like SQL?
17. Are you accounting for unknown outcomes on timeouts around EXEC?
18. Is there an atomic read-check-write requirement that pipelining cannot satisfy?
19. Are Redis replica lag and key expiration considered when debugging?

**Topology and operations**

20. Is the Redis Standalone/Sentinel/Cluster topology accurate?
21. Do multi-command keys share the same slot when required?
22. Does the driver/Lettuce/Jedis/Spring version support that pipeline pattern?
23. Does the Redis ACL user have MULTI/EXEC/WATCH and inner command permissions?
24. Are there real-Redis integration tests covering positive and negative cases?
25. Are batch size, memory, timeouts, p99, and command/reply counts measured?

## 28. Conclusion

In Spring Data Redis, **`null` inside a pipeline or transaction callback usually just reflects "the reply is not ready yet"**, not necessarily that the Redis key does not exist. Pipelines collect replies into `executePipelined(...)`; Redis transactions queue commands between `MULTI` and `EXEC` and return final replies at `EXEC`; `SessionCallback` helps retain one connection across the entire operation sequence.

When results outside the callback are still wrong, inspect **serializers**, reply types, command order, `@Transactional`/transaction support, connection binding, and `WATCH` conflicts. Do not confuse pipelining with atomicity, do not expect Redis transactions to roll back runtime errors like SQL, and do not infer Redis did not execute just because the client timed out.

The most effective diagnostic method is building a **single regular-command baseline on test Redis**, placing the same command inside a pipeline/transaction, reading replies at the proper boundary, inspecting the actual keys/values, and then adding integration tests for WATCH, serializers, Cluster, and exception paths. Most "Redis returned a different result" bugs become explainable and testable semantic differences.

## References

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, `RedisCallback`/`SessionCallback`, results, and serializers.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI/EXEC`, connection binding, and `@Transactional`.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): templates, RedisConnection, and serialization.
- [Spring Data Redis — RedisOperations API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/RedisOperations.html): SessionCallback, pipelines, transactions, and EXEC.
- [Spring Data Redis — RedisTemplate API](https://docs.spring.io/spring-data/redis/reference/3.5/api/java/org/springframework/data/redis/core/RedisTemplate.html): `executePipelined` overloads and serializers.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): `MULTI`, `EXEC`, `DISCARD`, `WATCH`, and errors/rollback.
- [Redis — MULTI](https://redis.io/docs/latest/commands/multi/): queuing Redis commands.
- [Redis — EXEC](https://redis.io/docs/latest/commands/exec/): executing transactions and replies.
- [Redis — WATCH](https://redis.io/docs/latest/commands/watch/): optimistic locking.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): reducing network round trips.
- [Redis — ACL](https://redis.io/docs/latest/operate/oss_and_stack/management/security/acl/): command permissions and key patterns.
- [Redis — Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, multi-key operations, and routing.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/core/release/reference/testing.html): testing reactive publishers.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): integration testing with real Redis.
