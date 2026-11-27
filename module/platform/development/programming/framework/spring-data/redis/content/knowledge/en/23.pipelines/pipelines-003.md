# Using `executePipelined` with `RedisCallback` in Spring Data Redis

When an application needs to send hundreds or thousands of independent Redis commands, the time spent sending commands over the network can become a significant part of total latency. **Redis pipelining** lets the client send multiple commands consecutively and then collect responses in a batch, reducing the need to wait for a network round trip per command. Spring Data Redis provides `RedisTemplate.executePipelined(...)` to use this mechanism.

With the **`executePipelined(RedisCallback<?>)`** variant, developers work directly with `RedisConnection` inside the callback. This approach fits cases where you need exact control over the low-level Redis command sequence, understand byte serialization thoroughly, and explicitly match each response with its corresponding command.

Key points to remember from the start:

- **Pipelines optimize network exchange; they do not turn multiple commands into an atomic transaction.**
- `executePipelined` collects **results after the callback finishes**. Do not use the result of a command being queued into the pipeline to make decisions inside the callback.
- The callback passed to `executePipelined` **must return `null`**; the actual responses are in the `List<Object>` returned by the method.
- With `RedisCallback`, keys and values are sent through the low-level command interface as `byte[]`. You must use a serializer matching the existing data.
- Pipelines can reduce network latency, but overly large batches increase memory usage and can place unnecessary load on Redis or the client.

This article explains how pipelining works, how to call the API properly, how to decode responses, and the limits when applying it in production systems.

## 1. Why use a pipeline?

Suppose a request needs to read 100 cached values:

```text
cache:product:p001
cache:product:p002
...
cache:product:p100
```

If the application calls Redis sequentially with `GET`, each call waits for the result before sending the next command:

```text
Application                  Redis
    | --- GET p001 ----------> |
    | <--------- result -------|
    | --- GET p002 ----------> |
    | <--------- result -------|
    |            ...
    | --- GET p100 ----------> |
    | <--------- result -------|
```

If network round-trip latency is significant, total time can include many unnecessary waits, even though each `GET` command on Redis is very fast.

With a pipeline:

```text
Application                  Redis
    | --- GET p001 ----------> |
    | --- GET p002 ----------> |
    |            ...           |
    | --- GET p100 ----------> |
    | <-------- results -------|
```

The client sends commands in a batch without requiring each call to complete a network round trip before starting the next command. Redis processes the commands and produces responses; the driver collects the responses and returns them to Spring Data Redis.

The main benefit is **reducing waiting time caused by network round trips**. Pipelining does not make each `GET` command run faster computationally and does not eliminate the cost of data serialization, command execution, or storing results.

### 1.1. Distinguishing pipelining from multi-key commands

For multiple read commands of the same kind, Redis also offers commands like `MGET`. For example:

```redis
MGET cache:product:p001 cache:product:p002 cache:product:p003
```

`MGET` is **one command** fetching multiple keys, which can be a simpler choice than pipelining multiple `GET`s when it meets the requirements. In Spring Data Redis, you can consider `opsForValue().multiGet(keys)`.

Pipelining is useful when you want to send **different kinds of commands** (`GET`, `INCR`, `SETEX`, `HGET`...), when you need a sequence of operations with no matching multi-key command, or when the low-level API needs per-key control.

In Redis Cluster, multi-key commands such as `MGET` must follow hash-slot rules; pipelining across multiple nodes also depends on the driver's routing capabilities and cluster configuration. Therefore, do not assume the two approaches are always interchangeable in every environment.

## 2. The `executePipelined` API and the role of `RedisCallback`

`RedisTemplate` provides methods of the form:

```java
List<Object> executePipelined(RedisCallback<?> action);
```

Another variant lets you specify the serializer used when processing returned results:

```java
List<Object> executePipelined(
        RedisCallback<?> action,
        RedisSerializer<?> resultSerializer
);
```

Minimal form example:

```java
List<Object> results = stringRedisTemplate.executePipelined(
    (RedisCallback<Object>) connection -> {
        // Send Redis commands via connection.
        return null;
    }
);
```

Where:

| Component | Role |
|---|---|
| `StringRedisTemplate` | Template with String serializers, convenient for text keys/values |
| `executePipelined(...)` | Opens pipeline, executes callback, closes pipeline, and collects results |
| `RedisCallback<?>` | Allows working directly with `RedisConnection` |
| `RedisConnection` | Low-level interface for sending Redis commands, typically using `byte[]` |
| `return null` | The callback's return value is not used as the pipeline result |
| `List<Object>` | Responses returned by Spring Data Redis after the pipeline completes |

`RedisCallback` is a functional interface whose method receives `RedisConnection` and returns a callback-defined result. However, in **`executePipelined`**, the callback's return value must be `null` because Spring Data Redis uses the pipeline's list of responses as the final result.

If you want to execute a callback and receive a direct computed result from that callback, that is the purpose of `RedisTemplate.execute(...)`.

## 3. Minimal example: sending multiple `SET`s through a pipeline

Suppose you want to write three processing statuses:

```text
job:101:status = QUEUED
job:102:status = QUEUED
job:103:status = QUEUED
```

First, create a service with `StringRedisTemplate`:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class JobStatusBatchWriter {

    private final StringRedisTemplate redis;

    public JobStatusBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> markQueued() {
        RedisSerializer<String> serializer = redis.getStringSerializer();

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                connection.stringCommands().set(
                    serializer.serialize("job:101:status"),
                    serializer.serialize("QUEUED")
                );

                connection.stringCommands().set(
                    serializer.serialize("job:102:status"),
                    serializer.serialize("QUEUED")
                );

                connection.stringCommands().set(
                    serializer.serialize("job:103:status"),
                    serializer.serialize("QUEUED")
                );

                return null;
            }
        );
    }
}
```

The three `SET` commands are sent through the same pipeline managed by Spring Data Redis. After the callback finishes, the template closes the pipeline and returns the list of responses.

A normal `SET` command returns a success response. The exact representation in the list depends on the driver and result conversion step. Therefore, do not cast every element of `List<Object>` to `String` if the pipeline contains multiple command types.

### 3.1. Why do you have to serialize keys/values manually?

With the high-level API:

```java
redis.opsForValue().set("job:101:status", "QUEUED");
```

`StringRedisTemplate` automatically uses the serializer configured on the template to convert keys and values into bytes.

With `RedisCallback`, we call commands directly on `RedisConnection`:

```java
connection.stringCommands().set(
    byte[] key,
    byte[] value
);
```

Thus, **the application must provide properly formatted bytes itself**. In the example, `getStringSerializer()` performs the conversion for string keys/values.

If you arbitrarily use `String.getBytes()` where other parts of the project use a different serializer, keys written by the pipeline may be incompatible with keys read by a repository or `RedisTemplate`. The Java code looks similar, but the actual bytes in Redis differ.

Do not treat serializers as boilerplate decoration: they are part of the data storage contract.

## 4. Practical example: reading multiple keys in one pipeline

Problem: take a list of product IDs, read each product's cache, and return a `Map<String, String>` so callers know which value belongs to which product.

```java
package com.example.redis;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheBatchReader {

    private final StringRedisTemplate redis;

    public ProductCacheBatchReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public Map<String, String> findCachedProducts(List<String> ids) {
        Map<String, String> result = new LinkedHashMap<>();

        if (ids.isEmpty()) {
            return result;
        }

        RedisSerializer<String> serializer = redis.getStringSerializer();

        List<Object> replies = redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (String id : ids) {
                    byte[] key = serializer.serialize(
                        "cache:product:" + id
                    );

                    connection.stringCommands().get(key);
                }

                // Important: executePipelined requires the callback to return null.
                return null;
            }
        );

        if (replies.size() != ids.size()) {
            throw new IllegalStateException(
                "Response count does not match GET command count"
            );
        }

        for (int i = 0; i < ids.size(); i++) {
            // StringRedisTemplate processes GET results according to
            // the template's value serializer.
            String value = (String) replies.get(i);
            result.put(ids.get(i), value);
        }

        return result;
    }
}
```

How to call it:

```java
List<String> ids = List.of("p101", "p102", "p103");

Map<String, String> products =
        productCacheBatchReader.findCachedProducts(ids);

System.out.println(products.get("p101"));
System.out.println(products.get("p102"));
```

If key `cache:product:p102` does not exist, the corresponding value in the result can be `null`. The example keeps the `p102 -> null` entry to represent a cache miss; another API might put only present entries into the map, depending on business requirements.

### 4.1. Why can responses be matched by position?

Pipeline responses are collected by Redis/the driver in **the order commands were sent** on the corresponding connection. In the example, the `i`-th GET command corresponds to `ids.get(i)`. Hence we can map by index:

```text
Command sent                     Response received
--------------------------------------------------
GET cache:product:p101           replies[0]
GET cache:product:p102           replies[1]
GET cache:product:p103           replies[2]
```

Still, do not change the order or number of commands inside the callback without updating the result-mapping code. Adding a `PING` command between the GET commands shifts the response positions of all subsequent commands.

When mixing multiple command types, store a metadata list corresponding to each command so you know which response belongs to which operation.

### 4.2. Return values are not immediately available inside the callback

The following is a misconception:

```java
redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] raw = connection.stringCommands()
            .get("cache:product:p101".getBytes());

        // Do not rely on raw to decide the next command:
        // GET is being queued into the pipeline and does not have
        // a synchronous return result yet.

        return null;
    }
);
```

Because commands are queued into the pipeline, the direct return value from a low-level call inside the callback is usually not the final result for the application to process. **Results must be consumed outside the callback**, from the `List<Object>` returned by `executePipelined`.

If command B should only be sent when the actual result of command A satisfies a condition, those two commands have a **data dependency**. A simple pipeline is not suitable for branching mid-batch. In that case, split into read-then-write phases, or use Lua/Redis Functions, `WATCH`, and an appropriate mechanism if atomicity is required.

## 5. Writing multiple keys with TTL using `setEx`

Pipelines fit cases where multiple cache entries need to be written individually with a time-to-live applied to each.

Example storing temporary status messages for 300 seconds:

```java
package com.example.redis;

import java.util.List;
import java.util.Map;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class TemporaryStatusWriter {

    private final StringRedisTemplate redis;

    public TemporaryStatusWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeStatuses(Map<String, String> statuses) {
        RedisSerializer<String> serializer = redis.getStringSerializer();

        return redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (Map.Entry<String, String> entry : statuses.entrySet()) {
                    byte[] key = serializer.serialize(
                        "status:" + entry.getKey()
                    );
                    byte[] value = serializer.serialize(entry.getValue());

                    connection.stringCommands().setEx(
                        key,
                        300L,
                        value
                    );
                }
                return null;
            }
        );
    }
}
```

`setEx` writes the value and expiration in **one Redis command per key**, avoiding the gap created by sending `SET` and `EXPIRE` separately. However, the group of `setEx` commands in the pipeline **does not form a transaction**. If an error or connection drop occurs, some keys may be written successfully while others are not.

Example call:

```java
Map<String, String> statuses = Map.of(
    "task-1", "RUNNING",
    "task-2", "QUEUED",
    "task-3", "DONE"
);

temporaryStatusWriter.writeStatuses(statuses);
```

If the business requirement demands **all statuses be updated together or none changed**, a pipeline alone does not meet that requirement.

## 6. Mixed pipeline: `SET`, `INCR`, and `GET` returning different types

A pipeline can contain multiple types of commands:

```java
RedisSerializer<String> serializer = redis.getStringSerializer();

List<Object> results = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        byte[] key = serializer.serialize("demo:pipeline:counter");

        connection.stringCommands().set(
            key,
            serializer.serialize("10")
        );

        connection.stringCommands().incr(key);

        connection.stringCommands().get(key);

        return null;
    }
);
```

Redis processes the commands in order:

```text
SET demo:pipeline:counter 10
INCR demo:pipeline:counter
GET demo:pipeline:counter
```

If no other operation interleaves between these commands, `GET` sees `"11"`. However, a pipeline **does not guarantee that no operations from other clients interleave between commands**. For example, the final value could differ if another client modifies the key at the same time.

The result list contains responses by position:

| Position | Command | Common result type |
|---|---|---|
| `results.get(0)` | `SET` | Write confirmation result |
| `results.get(1)` | `INCR` | Incremented numeric value, typically represented as `Long` |
| `results.get(2)` | `GET` | Decoded value, typically `String` with `StringRedisTemplate` |

Because result types are mixed, **do not cast the entire list to `List<String>` or `List<Long>`**. Handle each position according to its command type and serializer.

If you need a condition like "only INCR when GET finds valid data," a pipeline is not the tool to enforce that condition. Design a server-side check-and-update or use an appropriate optimistic concurrency mechanism.

## 7. How does Spring Data Redis manage a pipeline?

Conceptually, the `executePipelined` flow can be expressed as:

```text
Caller
  |
  | redisTemplate.executePipelined(callback)
  v
RedisTemplate opens pipeline
  |
  | callback.doInRedis(connection)
  |   ├─ Send command 1
  |   ├─ Send command 2
  |   ├─ Send command 3
  |   └─ return null
  |
RedisTemplate closes pipeline and collects responses
  |
Decodes results using configured serializers
  |
  v
List<Object> returned to caller
```

The actual behavior beneath the connection layer depends on the Redis client (such as Lettuce or Jedis), but at the application API level, `executePipelined` is responsible for managing when results are collected.

### 7.1. Do not open or close the pipeline again inside the callback

When using:

```java
redis.executePipelined((RedisCallback<Object>) connection -> {
    // Send commands here.
    return null;
});
```

Spring Data Redis already manages the pipeline for this call.

Do not try to do:

```java
connection.openPipeline();
// send commands...
connection.closePipeline();
```

directly inside the `executePipelined` callback. Doing so mixes two pipeline management mechanisms and can cause result collection to behave unexpectedly.

If you use the `RedisConnection` API directly in a separate flow, opening/closing pipelines has its own rules, but that is not the flow illustrated here.

### 7.2. Do not retain `RedisConnection` for use after the callback

The `RedisConnection` inside `RedisCallback` belongs to the execution scope managed by Spring Data Redis. Do not store this connection in a service field, global variable, or pass it to another thread to continue calling after the callback finishes.

Complete all command-sending operations inside the callback, receive the response list from `executePipelined`, and process them outside the callback.

### 7.3. Do not treat the callback as an arbitrary asynchronous task

`executePipelined` is a synchronous call at the API level: the caller receives the result list after the pipelined commands have executed and responses have been collected. The benefit of pipelining lies mainly in how multiple commands are sent over the connection; it does not mean the service automatically runs in the background and returns a `CompletableFuture`.

If you need reactive APIs, Spring Data Redis provides dedicated reactive APIs for Redis; do not equate them with `RedisTemplate.executePipelined`.

## 8. Serializers: the most error-prone part when using `RedisCallback`

With `StringRedisTemplate`, a common pattern is:

```java
RedisSerializer<String> serializer =
        stringRedisTemplate.getStringSerializer();

byte[] key = serializer.serialize("cache:user:42");
byte[] value = serializer.serialize("ACTIVE");
```

Using the same serializer for keys and values makes sense when both are strings. If the application uses `RedisTemplate<String, UserProfile>` with a String key serializer and an object-encoding value serializer, the two serializers can differ:

```text
Key:
  "cache:user:42" -> StringRedisSerializer -> byte[]

Value:
  UserProfile(...) -> configured JSON/byte serializer -> byte[]
```

You cannot take arbitrary JSON string bytes and expect a `RedisTemplate` configured with a different serializer to automatically read them back as the right object.

### 8.1. Callback serialization flow differs from high-level APIs

Compare:

```java
redis.opsForValue().set("cache:user:42", "ACTIVE");
```

with:

```java
redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        connection.stringCommands().set(
            serializer.serialize("cache:user:42"),
            serializer.serialize("ACTIVE")
        );
        return null;
    }
);
```

In the second example, serialization of arguments **is the responsibility of the code inside the callback**.

### 8.2. Result deserialization

After the pipeline finishes, `RedisTemplate` processes read results based on its configured serializers; for instance:

- Redis Strings read via `GET` typically use the value serializer.
- Commands involving Redis Hashes may require corresponding hash key/hash value serializers.
- Numeric commands and write statuses typically return their own result types, and should not be treated as raw string bytes to be parsed into arbitrary objects.

In some cases you can specify a serializer for results:

```java
List<Object> values = redis.executePipelined(
    (RedisCallback<Object>) connection -> {
        // GETs using low-level Redis commands.
        return null;
    },
    redis.getStringSerializer()
);
```

Passing a result serializer is appropriate when the read data is stored in the same format and the API allows it. Do not pass a single arbitrary serializer and expect it to interpret every mixed response type in the pipeline.

### 8.3. Symptoms of serializer mismatch

Suppose code outside the pipeline uses `StringRedisSerializer` as the key serializer, but the callback writes keys using a serializer with a different byte prefix:

```text
Outside:
  GET "cache:user:42" -> nil

Inside pipeline:
  SET <mismatched bytes> "ACTIVE" -> succeeded
```

Here the pipeline did write a key, but the key **does not have the same bytes** as the key used by `opsForValue().get(...)`. Redis distinguishes keys by exact bytes; similar-looking display names do not guarantee you are operating on the same key.

When `GET` outside the pipeline cannot read a written value, check the serializer, key prefix, selected database, and connection factory before assuming the pipeline did not execute.

## 9. Use `RedisCallback` or `SessionCallback`?

Spring Data Redis provides both `RedisCallback` and `SessionCallback`, serving different levels of abstraction.

| Criterion | `RedisCallback` | `SessionCallback` |
|---|---|---|
| Object received by callback | `RedisConnection` | `RedisOperations` |
| API level | Low-level, operates on Redis commands | Template-level, uses operations |
| Argument passing | Typically uses `byte[]` | Relies on `RedisTemplate`'s serializers |
| Best suited for | Direct command control, handling many low-level Redis commands | Grouping template-level operations on the same session |
| Pipeline | `executePipelined(RedisCallback<?>)` | Has `executePipelined(SessionCallback<?>)` variant |
| Risks to watch | Manual argument serialization, low-level command result handling | Distinguishing callback result from pipeline result and operations semantics |

For example, `SessionCallback` can use `opsForValue().get(...)` and the template's serializers directly. However, in this article the focus is **`executePipelined` with `RedisCallback`**, so it is essential to recognize the connection type and data conversion responsibilities.

Do not pick `SessionCallback` thinking pipelining automatically becomes a transaction, and do not pick `RedisCallback` thinking all commands will run atomically. Both approaches can pipeline commands; atomicity is a separate requirement.

## 10. A pipeline is not `MULTI`/`EXEC`

This is the most important distinction when applying pipelining to business logic.

**Pipeline:**

```text
Send command A
Send command B
Send command C
Collect replies A, B, C
```

Goal: reduce network wait time. Other clients' commands **can** interleave between A, B, and C.

**Redis transaction via `MULTI`/`EXEC`:**

```text
MULTI
A -> QUEUED
B -> QUEUED
C -> QUEUED
EXEC -> Redis executes the group in order, without interleaving
```

Goal: execute a group of commands without interleaving during the `EXEC` phase. However, Redis has no general rollback for commands that already ran if another command in the transaction encounters a runtime error.

| Property | Pipeline | `MULTI`/`EXEC` |
|---|---|---|
| Reduces round trips | Can | Can when sending grouped commands, depending on client |
| When commands execute | When Redis receives and processes the command | Commands are queued first, run at `EXEC` |
| Can other clients interleave between commands? | Yes | No while Redis executes the `EXEC` group |
| Command results immediately available to Java inside callback? | No, collected after pipeline | No, collected after `EXEC` |
| Automatic rollback on runtime command error? | No | No |
| Creates a transaction with PostgreSQL? | No | No |
| Best suited for | Many independent operations, reducing RTT | Needing a group of commands to run back-to-back |

If you need a condition like "read current value, check, then write" without race conditions, neither a plain pipeline nor `MULTI` alone is sufficient; you need `WATCH` or an appropriate Lua/Redis Function.

### 10.1. Why can't a pipeline protect read–modify–write?

Incorrect concurrency example:

```java
// Another request can modify the key between these commands.
String value = redis.opsForValue().get("counter:42");
long next = Long.parseLong(value) + 1;
redis.opsForValue().set("counter:42", Long.toString(next));
```

Putting `GET` and `SET` into a pipeline also does not solve having to **read the GET result before computing the SET value** in Java. The `GET` result is not available inside the callback to construct dependent commands.

If the operation is incrementing a counter, Redis already has `INCR`: it is an atomic command and is usually the right solution. If the condition is complex, consider a Lua/Redis Function or an optimistic concurrency mechanism.

## 11. Error handling and consistency limits

A pipeline with multiple commands has no **all-or-nothing** guarantee:

```text
SET cache:a A   -> may have succeeded
SET cache:b B   -> may have succeeded
SET cache:c C   -> may have failed or not run
```

If the connection drops or Redis returns an error, the application must not assume all three commands failed. Depending on the error and driver, it may receive an exception, an error reply in the batch, or insufficient results to know exactly which commands executed.

### 11.1. Handling rules

- For **regenerable caches**, design retries, skip failed entries, use TTLs, and reload from the primary data source.
- For **idempotent writes** like `SET key fixedValue`, retrying may be acceptable if it does not break business correctness.
- For **cumulative commands** like `INCR`, do not blindly retry after a timeout: the command may have incremented successfully while the response was lost, so retrying increments a second time.
- If multiple keys must be updated as one consistent unit, pipelining is insufficient; design a transaction/server-side atomic operation within what Redis supports.
- For data errors or Redis type errors like `WRONGTYPE`, re-running the same batch without fixing the cause will keep failing.

Example of retry semantics:

```text
Client sends INCR metrics:orders
Redis executes -> metrics:orders increases by 1
Network drops before response reaches client
Client does not know whether it executed
Client retries INCR -> metrics:orders may increase by 1 again
```

To ensure a request is counted only once, design an idempotency key or appropriate business mechanism; pipelining does not provide this feature automatically.

### 11.2. Pipelines do not guarantee Redis persistence

Even when `executePipelined` returns a list of successful responses, whether the data survives a crash/failover depends on Redis persistence, replication, and topology configuration. Pipelining primarily affects how commands are **sent and replies collected**, without changing data durability policies.

## 12. Batching to avoid oversized pipelines

Sending millions of commands in a single pipeline can significantly increase:

- Request buffering memory on the client/driver.
- Response buffer memory on the server while waiting for the client to read.
- Memory holding `List<Object>` when Spring Data Redis returns all results.
- Request latency and connection hold time.
- Likelihood of timeouts when responses are too large.

Usually you should **split large input lists into batches** and run multiple pipelines. There is no single optimal batch size for all systems; the choice depends on value size, round-trip time, Redis processing speed, connection limits, and the application's memory budget.

Example reading in batches of up to 200 keys at a time:

```java
public Map<String, String> findCachedProductsInBatches(
        List<String> productIds,
        ProductCacheBatchReader reader
) {
    final int batchSize = 200;
    Map<String, String> results = new LinkedHashMap<>();

    for (int start = 0; start < productIds.size(); start += batchSize) {
        int end = Math.min(start + batchSize, productIds.size());

        List<String> batch = productIds.subList(start, end);

        Map<String, String> partial = reader.findCachedProducts(batch);
        results.putAll(partial);
    }

    return results;
}
```

In this example, `findCachedProducts` is the method from section 4. Each batch makes one `executePipelined` call, limiting the number of responses kept in memory per execution. If the ID list contains duplicates, the `Map` keeps only one entry per key; if you need to preserve duplicate counts/positions, return a `List` aligned with the input.

### 12.1. There is no "magic batch size"

You can start with a few dozen or a few hundred commands per batch, then measure. Metrics to observe:

| Metric | What to watch |
|---|---|
| Request latency p50/p95/p99 | Does the pipeline reduce actual end-to-end latency? |
| Network RTT and throughput | Is waiting time dropping compared to individual calls? |
| Response size | Does each key return a few bytes or megabytes? |
| JVM heap and GC | Does the batch `List<Object>` increase memory pressure? |
| Redis memory/network output | Is the server accumulating large outgoing replies? |
| Timeouts, connection pool | Do batches hold connections too long or impact other requests? |
| Redis CPU | Does increased pipeline throughput overload the server? |

Evaluate on a realistic workload and environment, because pipelining can help substantially when network latency is significant, yet yield little benefit when commands are CPU-heavy or the server is already at capacity.

## 13. Redis Cluster and connection details

In Redis standalone, commands over one connection go to a single Redis server. With Redis Cluster, keys are partitioned across multiple hash slots and different nodes.

A pipeline containing keys belonging to multiple slots needs the driver to handle cluster routing. Redis clients with cluster pipelining capabilities differ in how they group commands by node, order collected responses, handle redirects, and enforce connection limits.

Therefore:

1. Check the pipelining capabilities of your specific Spring Data Redis and driver version in actual cluster mode.
2. Do not assume all keys in a pipeline are sent to a single server.
3. Do not infer that putting commands in the same pipeline provides an atomic transaction across multiple hash slots.
4. If you need multi-key commands or Lua scripts, obey the corresponding hash-slot/routing rules.
5. For large workloads, consider grouping keys by locality or designing key naming appropriately to reduce the number of nodes/connections used, when meaningful to the business domain.

Redis Cluster also has failover, redirects, and replication mechanisms that affect timing and errors. Pipelining does not replace retry/idempotency design.

## 14. When should you avoid `RedisCallback` pipelines?

Not every multi-command problem should use `executePipelined`:

**A single Redis command suffices.** If you need to increment an integer, use `INCR`; if you need to fetch multiple String keys, `MGET` can be used when suitable; if you want to write a value with a TTL, use `SET` with `EX/PX`. A single command is usually clearer.

**Later commands depend on earlier results.** Pipelines do not let you read intermediate results synchronously to branch inside the callback. If invariants must be guaranteed, use an appropriate atomic operation.

**You need commands without interleaving.** Consider Redis `MULTI`/`EXEC`; if conditional checks are also needed, use `WATCH` or a script. Pipelining alone does not provide this property.

**Large data and hard-to-control batches.** An oversized pipeline can cause memory pressure and timeouts. Partition the work or use an appropriate data structure/streaming approach.

**Business logic lives in JPA/RDBMS.** Sending Redis commands via a pipeline does not turn operations in PostgreSQL and Redis into a distributed transaction. You need an outbox, post-commit invalidation, or an appropriate coordination mechanism.

**You want simple code and automatic serializers.** If the operation count is small, `opsForValue()`, `opsForHash()`, and `opsForSet()` are usually clearer because the template handles serialization automatically.

## 15. Application example: reloading many cache entries after a DB query

Suppose the service layer just fetched a list of products from the primary database and wants to store them in Redis with a 10-minute TTL. Each product has an ID and a JSON payload normalized into a string.

```java
package com.example.redis;

public record CachedProduct(String id, String json) {
}
```

Batch cache writer service:

```java
package com.example.redis;

import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.serializer.RedisSerializer;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheWarmupService {

    private final StringRedisTemplate redis;

    public ProductCacheWarmupService(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public void warmUp(List<CachedProduct> products) {
        if (products.isEmpty()) {
            return;
        }

        RedisSerializer<String> serializer = redis.getStringSerializer();

        redis.executePipelined(
            (RedisCallback<Object>) connection -> {
                for (CachedProduct product : products) {
                    byte[] key = serializer.serialize(
                        "cache:product:" + product.id()
                    );

                    byte[] value = serializer.serialize(product.json());

                    // Each SETEX writes value and TTL in a single command.
                    connection.stringCommands().setEx(
                        key,
                        600L,
                        value
                    );
                }

                return null;
            }
        );
    }
}
```

Execution flow:

```text
DB query -> List<CachedProduct>
    |
    v
ProductCacheWarmupService.warmUp(products)
    |
    v
RedisTemplate.executePipelined
    |
    +-> SETEX cache:product:p101 600 <json-101>
    +-> SETEX cache:product:p102 600 <json-102>
    +-> SETEX cache:product:p103 600 <json-103>
    |
    v
Collect results and finish
```

The example uses a single pipeline for the whole input to keep the API illustration focused; for large counts, split into batches as in section 12.

It assumes `product.json()` is a **pre-built** JSON string. `StringRedisTemplate` only converts the string into bytes; it does not validate whether the JSON matches the `Product` schema. When reading it back, parse the JSON with the appropriate domain converter.

This is a good fit for pipelining because each cache entry can be written **independently**. If a partial write occurs and the connection drops, the system can still regenerate missing entries from the DB according to its cache policy.

## 16. Observing and experimenting with pipeline behavior

During development, you can create a set of test keys:

```redis
SET lab:pipe:a "A"
SET lab:pipe:b "B"
SET lab:pipe:c "C"
```

Call the batch reader service with the matching keys (adjusting the prefix in code accordingly), then compare the values in `List<Object>` or the map against CLI output:

```redis
GET lab:pipe:a
GET lab:pipe:b
GET lab:pipe:c
```

To observe a mixed pipeline, send `SET`, `INCR`, `GET` and then read back the key. What matters is not seeing them "run at the same time," but understanding **command order and response order**.

In a test environment, you can observe Redis command counts and latency to compare sequential calls versus pipelining. Avoid turning on high-overhead monitoring tools in production just to verify a simple example.

### 16.1. Common implementation pitfalls

| Symptom | Common cause | Resolution |
|---|---|---|
| Callback returns data but result is rejected | `executePipelined` requires callback to return `null` | Return `null`, process `List<Object>` outside |
| `GET` inside callback returns `null` | Command is being pipelined, final response not yet received | Read results from `executePipelined` |
| Reading outside pipeline does not see written key | Raw connection serializer differs from template | Use consistent serializer; inspect key bytes |
| `ClassCastException` when casting results | Pipeline has mixed Boolean/Long/String results | Map by position and per-command type |
| Results assigned to wrong IDs | Command order/count differs from input metadata | Maintain 1–1 mapping between commands and response positions |
| Large batch times out or spikes heap | Too many commands, large values, or large responses | Split into batches and measure latency/memory |
| Partial writes on error | Pipelines have no rollback | Handle retry/idempotency or use an appropriate transaction |
| Inconsistent `GET` results when other clients modify keys | Pipelines do not provide isolation | Use conditional read/write pattern or transaction if needed |
| Pipeline on Redis Cluster behaves differently from standalone | Driver routing and hash slots | Verify cluster support, optimize key placement |

## 17. Practical implementation principles

When choosing `executePipelined(RedisCallback<?>)` for a Spring Data Redis feature, verify the following:

1. **Identify independent commands.** If a later command needs an earlier command's result to decide, do not treat them as a simple pipeline.
2. **Standardize serializers.** When calling `RedisConnection` directly, always convert keys/values with serializers matching the system's data.
3. **Keep the callback simple.** Only prepare and send commands then `return null`; process results after the method returns.
4. **Preserve explicit ordering.** If using `List<Object>` to match results, retain the same command order or corresponding metadata.
5. **Bound batch size.** Split batches based on data size and benchmark measurements to avoid unbounded response accumulation.
6. **Design for partial failure.** Pipelines have no rollback, so write operations should be idempotent or have an appropriate recovery path.
7. **Pick the right tool for invariants.** A single atomic command, `MULTI`/`EXEC`, `WATCH`, Lua, or a DB transaction solves different requirements than pipelining.
8. **Measure end-to-end benefit.** Reducing RTT only pays off when overall latency and system resources genuinely improve.

## 18. Conclusion

`executePipelined` with `RedisCallback` is the direct way to **send a sequence of Redis commands via `RedisConnection` and receive responses in a batch** in Spring Data Redis. It is especially useful for batch `GET`, `SET`, `SETEX`, or many small independent operations when network round-trip cost is significant.

The three most important takeaways are:

- **The callback returns `null`**; results are retrieved from the `List<Object>` returned by `executePipelined`.
- **Commands inside `RedisCallback` use a byte-level API**, so key/value serialization must align with `RedisTemplate` and existing data.
- **Pipelines do not create atomic transactions or rollbacks**, and do not solve conditional read–modify–write operations.

When combined with a solid grasp of callbacks, serializers, response ordering, and batch sizing, pipelining helps Spring Data Redis handle many small operations efficiently while keeping a clear boundary between performance optimization and data consistency guarantees.
