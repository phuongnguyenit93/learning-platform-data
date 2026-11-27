# Using executePipelined with SessionCallback

When a Spring application needs to read or write many Redis keys, calling one command at a time and waiting for each response can cause a great deal of network waiting. **Pipelining** allows sending a group of Redis commands consecutively and receiving results after the commands have been sent, thereby reducing *round-trip* cost in batch-processing tasks.

Spring Data Redis provides `RedisTemplate.executePipelined(...)`. When using the variant that accepts **`SessionCallback`**, the application can build a group of operations using the high-level `RedisOperations` API within the same session. This is a convenient way to use operations such as `opsForValue()`, `opsForHash()`, and `opsForSet()` while keeping an explicit pipeline scope.

The most important point: **`executePipelined` batches sending commands and receiving responses, but it does not automatically create an atomic transaction**. Commands can succeed or fail independently; the result of one command is not yet available to decide the next command inside the callback.

## 1. Why use a pipeline?

Suppose an API needs to read 300 status entries in Redis:

```java
for (String key : keys) {
    String value = stringRedisTemplate.opsForValue().get(key);
    // Process each result right here.
}
```

With sequential calls, the client has to perform many send-and-wait cycles:

```text
Application                          Redis
   | -------- GET key:1 ------------> |
   | <------- value:1 --------------- |
   | -------- GET key:2 ------------> |
   | <------- value:2 --------------- |
   | -------- GET key:3 ------------> |
   | <------- value:3 --------------- |
   |                ...                |
```

If one network round trip takes around 1 ms, 300 separate waits can add roughly 300 ms of waiting overhead in a simple model, before even counting Redis processing, serialization, connection pool overhead, and application work. This figure is **only an intuitive illustration**, not a prediction of real-world latency.

Pipelining changes the communication pattern:

```text
Application                          Redis
   | -------- GET key:1 ------------> |
   | -------- GET key:2 ------------> |
   | -------- GET key:3 ------------> |
   |                ...                |
   | <------- value:1 --------------- |
   | <------- value:2 --------------- |
   | <------- value:3 --------------- |
   |                ...                |
```

The client does not need to wait for the result of each command before sending the next one. As a result, pipelining can substantially improve total time when handling many independent commands, especially if network latency is significant.

However:

- Redis still has to **execute the commands**; pipelining does not turn 300 `GET`s into one `GET`.
- Response data still must travel across the network and undergo type conversion.
- An overly large pipeline can consume substantial memory on both the client and Redis.
- If a later command **must use an earlier command's result to decide**, you cannot write a plain pipeline as if the result were already available.

## 2. Role of SessionCallback in executePipelined

Spring Data Redis has two commonly used variants:

```java
redisTemplate.executePipelined(RedisCallback<?> callback);
redisTemplate.executePipelined(SessionCallback<?> callback);
```

Both create a pipeline scope, but they express operations differently:

| Call style | API inside callback | Appropriate when |
|---|---|---|
| `executePipelined(RedisCallback)` | Low-level `RedisConnection` | Direct command/serialization control is needed |
| `executePipelined(SessionCallback)` | Template-level `RedisOperations` | You want `opsForValue()`, `opsForHash()`, `opsForSet()` and configured serializers |

`SessionCallback` keeps the callback's operations within the same session/connection according to Spring Data Redis's mechanism. When a pipeline is open, commands executed via `RedisOperations` are directed into the pipeline stream.

Conceptual model:

```text
StringRedisTemplate.executePipelined(SessionCallback)
                 |
                 v
       Open pipeline for session
                 |
                 v
       Callback receives RedisOperations
                 |
       +---------+----------+
       |         |          |
       v         v          v
     GET A     GET B      GET C
       |         |          |
       +---------+----------+
                 |
                 v
       Callback must return null
                 |
                 v
       Flush/receive pipeline responses
                 |
                 v
       Deserialize and convert results
                 |
                 v
              List<Object>
```

### Rule on the return value

**The callback passed to `executePipelined` must return `null`.** The results of the pipelined commands are collected by Spring Data Redis and returned **by `executePipelined` itself**, not by the return value of `SessionCallback.execute(...)`.

```java
List<Object> replies = redisTemplate.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("profile:1");
                operations.opsForValue().get("profile:2");

                // Required: do not return a custom-computed value here.
                return null;
            }
        });
```

If the callback returns a non-`null` value, the pipeline API may reject the call with an exception because that value conflicts with the result-collection mechanism. Do not return a custom `List` built from queued commands.

## 3. Complete example: bulk reading with StringRedisTemplate

Suppose the application manages processing statuses for many orders. Each status is a string value at keys:

```text
order:1001:status -> "PAID"
order:1002:status -> "CREATED"
order:1003:status -> "SHIPPED"
```

We need to read 100–500 keys for an admin screen. Because the `GET` calls are independent of one another, this is a good fit for pipelining.

### 3.1. Service using executePipelined(SessionCallback)

```java
import java.util.ArrayList;
import java.util.List;

import org.springframework.dao.DataAccessException;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderStatusReader {

    private final StringRedisTemplate redis;

    public OrderStatusReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> loadStatuses(List<String> orderIds) {
        if (orderIds.isEmpty()) {
            return List.of();
        }

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    public Object execute(RedisOperations operations)
                            throws DataAccessException {

                        for (String orderId : orderIds) {
                            String key = "order:" + orderId + ":status";
                            operations.opsForValue().get(key);
                        }

                        // GET results will be gathered after the callback finishes.
                        return null;
                    }
                });

        if (replies.size() != orderIds.size()) {
            throw new IllegalStateException(
                    "Unexpected number of Redis pipeline replies");
        }

        List<String> statuses = new ArrayList<>(replies.size());
        for (Object reply : replies) {
            // StringRedisTemplate uses the string value serializer.
            // A non-existent key can produce a null result.
            statuses.add(reply == null ? null : (String) reply);
        }
        return statuses;
    }
}
```

Usage example:

```java
List<String> statuses = reader.loadStatuses(
        List.of("1001", "1002", "1003"));

// statuses[0] corresponds to order:1001:status
// statuses[1] corresponds to order:1002:status
// statuses[2] corresponds to order:1003:status
```

**Points to understand in the example:**

1. All commands are issued through the `operations` instance received by the callback.
2. No `GET` result is used to decide the next command.
3. The callback returns `null`.
4. The outer call `redis.executePipelined(...)` receives `List<Object>`.
5. Results are processed **in the order commands were queued**, so element `i` corresponds to ID `i`.
6. A missing key can return `null`; do not use `List.copyOf(replies)` if `null` elements must be preserved because `List.copyOf` rejects `null`.

In production applications, the ID list should be length-bounded, validated for access permissions, and follow consistent key-naming rules. If you want to return `Map<orderId, status>`, you can pair each ID with the reply at the same index. When IDs repeat, a `Map` will not preserve duplicate slots; decide whether to deduplicate before queuing or return a list matching the input.

### 3.2. Why not read results directly inside the callback?

The following approach does not work properly:

```java
redis.executePipelined(new SessionCallback<Object>() {
    @Override
    public Object execute(RedisOperations operations) {
        Object value = operations.opsForValue().get("order:1001:status");

        if ("PAID".equals(value)) {
            operations.opsForValue()
                    .set("order:1001:next", "SHIP");
        }
        return null;
    }
});
```

While the pipeline is open, the direct return value of `get(...)` is typically `null` because actual results are only collected after the pipeline is flushed/read. Hence, the condition check in this example does not reflect the value in Redis.

If you need to read and then decide a write, use two phases (pipeline read, process results, then pipeline writes) when a concurrency window is acceptable, or choose `WATCH`/Lua/an atomic command if the write condition must be protected against concurrent updates.

## 4. Writing multiple keys with TTL in one pipeline

Not just for reads, `executePipelined` is also useful when loading cache entries in bulk, such as populating values for 1,000 products.

```java
import java.time.Duration;
import java.util.List;

import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductCacheBatchWriter {

    private final StringRedisTemplate redis;

    public ProductCacheBatchWriter(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public record CacheEntry(String key, String jsonValue) {
    }

    public void writeBatch(List<CacheEntry> entries, Duration ttl) {
        if (entries.isEmpty()) {
            return;
        }
        if (ttl.isZero() || ttl.isNegative()) {
            throw new IllegalArgumentException("TTL must be positive");
        }

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    public Object execute(RedisOperations operations) {
                        for (CacheEntry entry : entries) {
                            operations.opsForValue().set(
                                    entry.key(),
                                    entry.jsonValue(),
                                    ttl);
                        }
                        return null;
                    }
                });

        if (replies.size() != entries.size()) {
            throw new IllegalStateException(
                    "Unexpected pipeline reply count");
        }

        // Check individual results per command/serializer semantics
        // if business logic needs confirmation that every command succeeded.
    }
}
```

Calling the service:

```java
writer.writeBatch(
        List.of(
                new ProductCacheBatchWriter.CacheEntry(
                        "product:101:summary", "{\"name\":\"A\"}"),
                new ProductCacheBatchWriter.CacheEntry(
                        "product:102:summary", "{\"name\":\"B\"}")
        ),
        Duration.ofMinutes(5));
```

The `opsForValue().set(key, value, Duration)` method sets both the value and TTL in a single suitable Redis command, avoiding the window where a key is written without a TTL when `SET` and `EXPIRE` are split into two separate commands.

**Do not interpret `replies.size() == entries.size()` as a guarantee that all writes succeeded.** That is only a structural check on the result count; individual responses and exceptions must be handled according to the actual command and driver semantics. Likewise, pipelining does not guarantee rollback: if one command in the group fails, earlier commands may already have taken effect.

### Keeping different TTLs per key

If each group of data has different freshness requirements, put the TTL in each entry:

```java
public record CacheEntry(
        String key,
        String jsonValue,
        Duration ttl) {
}
```

Then:

```java
for (CacheEntry entry : entries) {
    operations.opsForValue().set(
            entry.key(), entry.jsonValue(), entry.ttl());
}
```

Each command in the pipeline carries its own TTL. Batching commands does not force every key to share the same expiration. When warming a large cache, you can add **TTL jitter** to avoid many keys expiring at the exact same moment, as long as it stays within business staleness limits.

## 5. Reading multiple data types in the same SessionCallback

A pipeline can include operations of different types. For example, for an order you may need to read a status string, a metadata hash, and the remaining TTL:

```java
List<Object> replies = redis.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue()
                        .get("order:1001:status");

                operations.opsForHash()
                        .get("order:1001:metadata", "owner");

                operations.getExpire("order:1001:status");

                return null;
            }
        });
```

Logical order:

| Index | Command issued | Expected data |
|---:|---|---|
| 0 | `GET order:1001:status` | Status string or `null` |
| 1 | `HGET order:1001:metadata owner` | Hash value or `null` |
| 2 | `TTL order:1001:status` | Remaining time, with special values when key does not exist / has no TTL |

**Do not assume every element of `List<Object>` is a `String`.** Spring Data Redis uses serializers and conversion mechanisms appropriate to each operation; replies can be strings, numbers, lists, booleans, or `null`. To map results safely, know the command type at each position and use an explicit result structure.

For example, when results are used to construct a DTO, you can define a record class:

```java
public record OrderSnapshot(
        String status,
        String owner,
        Long ttlSeconds) {
}
```

After checking the response count/types, map `replies.get(0)`, `replies.get(1)`, and `replies.get(2)` into the appropriate fields. Verify how `getExpire` is converted in your Spring Data Redis version; avoid blind casting in a pipeline containing multiple command types.

### Be careful with response count

If a conditional branch inside the callback causes some commands not to be queued, the result list structure will differ from what was expected. Determine the command order and count before building the pipeline, or store metadata corresponding to each queued command:

```text
Queued command list:
  [ GET customer:1, GET customer:4, GET customer:9 ]

Reply list:
  [ value:1, value:4, null ]

Matched by index:
  customer:1 -> value:1
  customer:4 -> value:4
  customer:9 -> null
```

Do not interpret a `null` at any position as the entire pipeline failing: it may simply mean the key does not exist. Conversely, do not ignore an exception or error response just because other elements look valid.

## 6. Differences between executePipelined(SessionCallback) and RedisCallback

Both approaches can implement pipelining properly, but the developer's responsibilities differ.

### 6.1. SessionCallback with the high-level API

```java
List<Object> replies = stringRedisTemplate.executePipelined(
        new SessionCallback<Object>() {
            @Override
            public Object execute(RedisOperations operations) {
                operations.opsForValue().get("product:1:summary");
                operations.opsForValue().get("product:2:summary");
                return null;
            }
        });
```

Advantages:

- Leverages familiar `RedisOperations`.
- Uses the template's serializers for standard operations.
- Easy to combine multiple `opsFor...()` calls in the same session.
- Less need to work directly with byte arrays.

### 6.2. RedisCallback with low-level connection

```java
import java.nio.charset.StandardCharsets;
import org.springframework.data.redis.core.RedisCallback;

List<Object> replies = stringRedisTemplate.executePipelined(
        (RedisCallback<Object>) connection -> {
            connection.stringCommands().get(
                    "product:1:summary".getBytes(StandardCharsets.UTF_8));
            connection.stringCommands().get(
                    "product:2:summary".getBytes(StandardCharsets.UTF_8));
            return null;
        });
```

At the low level, the developer is responsible for key encoding, value encoding, command selection, and compatibility with application data. The connection API may vary slightly across Spring Data Redis versions; the snippet illustrates the command path using `RedisConnection`.

**Choose `SessionCallback` when you need a regular sequence of Redis commands through the template; choose `RedisCallback` when you need direct control over the connection or serialization.** There is no need to switch to the low-level API just to use pipelining.

## 7. Pipelines and Redis transactions solve two different problems

The terms *pipeline*, *session*, and *transaction* are easily mixed up, yet each solves a distinct problem:

| Mechanism | Goal | SQL-style rollback? | Guarantees atomic command group? |
|---|---|---|---|
| Individual `RedisTemplate` calls | Independent operations | No | No |
| `executePipelined(SessionCallback)` | Reduce waiting time when sending multiple commands | No | No |
| `MULTI`/`EXEC` | Queue then execute command group without interleaving other clients | No | Has execution-group boundary, but per-command runtime errors do not roll back |
| `WATCH` + `MULTI`/`EXEC` | Detect key changes before commit | No | Conditionally aborts transaction on conflict |
| Lua/Redis script | Execute server-side logic in one pass | Does not automatically roll back all side effects on script error | Script has non-interleaved server execution semantics |

Example of a pipeline writing two keys:

```text
SET order:1001:state READY
SADD ready-orders 1001
```

If the connection fails during sending/receiving, the application may end up not knowing how many commands Redis processed. Because a pipeline **is not a transaction**, you must not assume both changes always take effect together.

Conversely, with `MULTI`/`EXEC`, commands are grouped to execute within a Redis transaction boundary, yet a runtime error on one command inside `EXEC` may still not prevent other commands from executing. Scenarios with complex business logic require choosing the right tool rather than assuming pipelines or transactions solve everything.

### Do not combine MULTI/EXEC into a pipeline arbitrarily

In principle, Redis supports queuing transactions and pipelining in certain contexts, but nesting `multi()`/`exec()` inside `executePipelined(...)` complicates the result structure and makes error conditions harder to handle. Calling `exec()` while a pipeline is open does not always yield direct results the way a regular transactional `SessionCallback` does.

If the goal is to **reduce round trips for independent commands**, use a plain pipeline. If the goal is **atomicity when executing a command group**, design an explicit transaction or script. Only combine them when there is a specific reason and you understand how the driver/Spring Data Redis represents nested results.

## 8. Pipelines do not fit operations dependent on earlier results

Conceptually flawed example:

```java
redis.executePipelined(new SessionCallback<Object>() {
    @Override
    public Object execute(RedisOperations operations) {
        Long stock = operations.opsForValue()
                .increment("inventory:sku-1", 0);

        if (stock != null && stock > 0) {
            operations.opsForValue()
                    .decrement("inventory:sku-1", 1);
        }
        return null;
    }
});
```

Because queued command results are not yet available, the condition inside the callback does not reflect the stock in Redis. Furthermore, if split into two pipelines (read then write), another client can change the count in between, leading to a race condition.

Solutions:

- For read flows used for display: pipeline all reads, process results **after the pipeline finishes**, and then optionally pipeline write commands.
- For conditional update requirements: use an appropriate atomic Redis command, `WATCH`/`MULTI`/`EXEC`, or a Lua script.
- For consistency spanning beyond Redis: identify the source of truth and transactional mechanism in the appropriate system, using Redis as a cache or projection.

Pipelining optimizes **network communication**; it is not a control-flow language for data-dependent server execution.

## 9. Choosing batch sizes to avoid oversized pipelines

A pipeline of 100 commands may have reasonable overhead; a pipeline of millions of commands in a single callback can consume huge amounts of memory, prolong response times, and impact other applications sharing Redis.

Costs include:

1. **Redis-side memory:** responses of pipelined commands may need to be buffered before sending to the client.
2. **Application-side memory:** `List<Object>` holds all responses, plus deserialization and Java object construction costs.
3. **Network throughput:** many bytes still must be transmitted, even though wait cycles are fewer.
4. **Server processing time:** Redis still executes every command.
5. **p95/p99 latency:** an overly large batch can force other requests to wait for resources.
6. **Recoverability:** if a large batch fails partway through, the scope of operations needing reconciliation is also large.

Start with moderate batch sizes (such as 100, 250, or 500 commands per batch as a test baseline), then tune using real measurements. These **are not official Spring Data Redis limits**. The right size depends on value size, command count, network speed, Redis resources, serializer complexity, and system concurrency.

### Splitting a list into multiple pipelines

Example splitting a list of keys into batches of up to 250:

```java
import java.util.ArrayList;
import java.util.List;

public List<String> loadInBatches(
        List<String> orderIds,
        int batchSize) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize must be positive");
    }

    List<String> all = new ArrayList<>(orderIds.size());

    for (int start = 0; start < orderIds.size(); start += batchSize) {
        int end = Math.min(start + batchSize, orderIds.size());
        List<String> batch = orderIds.subList(start, end);

        all.addAll(loadStatuses(batch));
    }

    return all;
}
```

Here `loadStatuses(batch)` is the method using `executePipelined(SessionCallback)` shown earlier. Batching limits the number of commands and responses held simultaneously in memory during one pipeline.

For very large datasets, push each batch to a downstream consumer for processing rather than accumulating every reply into `all`. You should also limit the number of concurrently running pipelines so optimizing a single request does not overload Redis when thousands of requests arrive simultaneously.

## 10. Combining pipelining with the right Redis data type

Pipelining is not always necessary. If all data consists of independent string values and keys are known ahead of time, Redis offers server-side batch commands such as `MGET` and `MSET`, which may be more suitable.

Example:

```java
List<String> values =
        stringRedisTemplate.opsForValue().multiGet(
                List.of("product:1", "product:2", "product:3"));
```

Comparison:

| Scenario | Option to consider |
|---|---|
| Multiple `GET`s on string values | `multiGet`/`MGET` if suitable; or pipeline `GET` |
| Multiple string `SET`s of the same form | `multiSet` or pipeline `SET` |
| Multiple `SET`s needing individual TTLs | Pipeline `set(key, value, Duration)` |
| Reading multiple independent Redis Hashes | Pipeline Hash commands or design a read model |
| Sending mixed command types in a fixed order | `executePipelined(SessionCallback)` |
| Each step depends on the previous step's reply | Do not use a plain pipeline for conditionals |

**`MGET` applies only to Redis string values**; do not use it to arbitrarily read Redis Hashes managed by `@RedisHash` Repositories. Reading a set of Redis Hashes can use a pipeline with `HGETALL`/`HMGET` where appropriate, though dropping down to `RedisConnection` requires handling serialization and field mapping properly.

Server-side batch commands and pipelining also have different limitations on Redis Cluster when keys span multiple hash slots. Base your choice on data type, key distribution, and client/cluster configuration, not just lines of Java code.

## 11. SessionCallback in Redis Cluster

In Redis Cluster, keys are partitioned across **hash slots** and distributed over multiple nodes. In this environment:

- Do not assume all keys are served by a single node or a single physical connection in all client configurations.
- Pipelining capability across multiple nodes depends on Spring Data Redis, the driver (such as Lettuce), and the topology.
- When commands must participate in **the same transaction** or multi-key script, Redis Cluster typically requires keys to belong to the same hash slot.
- Pipelining independent commands across different slots does not create cluster-wide ordering or transaction atomicity guarantees.
- Slot migration, failover, and `MOVED`/`ASK` redirects can affect cost or how the driver processes results.

If a task involves only a single aggregate with multiple keys, you can use **hash tags**:

```text
order:{1001}:status
order:{1001}:items
order:{1001}:payment
```

The portion inside curly braces is the hash tag; keys sharing `{1001}` map to the same hash slot. This helps when business logic needs to perform multi-key operations on the same slot.

However, **do not put every key into one global hash tag** to "make pipelining easier," because doing so concentrates load onto a single slot/node and defeats Redis Cluster distribution.

In practice, measure and verify pipeline support in your driver and topology before assuming an example on a single Redis instance is optimal for a multi-node cluster.

## 12. Errors, retries, and idempotency

A pipeline may already have sent some commands before the application receives an error. If the connection is interrupted while sending or collecting responses, you cannot always conclude with certainty that Redis processed none of the commands.

Example:

```text
Pipeline:
  SET product:1:status READY
  INCR batch:processed
  LPUSH queue:ready product:1

Application loses connection before reading all responses.
```

If you resend the entire pipeline:

- `SET ... READY` can usually be repeated safely with the same value (assuming no concurrent updates or version ordering requirements).
- `INCR batch:processed` may increment a second time.
- `LPUSH queue:ready product:1` may insert a duplicate element.

Therefore, **pipelines are not idempotent by default**. Recovery must match the business semantics of each command.

Measures:

1. Prefer safely repeatable writes when business logic permits.
2. Attach an operation ID or event ID to prevent duplicate processing, using an appropriate atomic write/check mechanism.
3. For critical batches, persist enough state or checkpoints to reconcile after errors.
4. Distinguish deserialization/command errors from connection errors with uncertain outcomes.
5. If retrying, cap attempts and add backoff with jitter so many clients do not resend heavy load at once.
6. Do not rely on the element count in `List<Object>` as proof that all operations took effect.

Some commands fail due to wrong data types, ACL permissions, syntax errors, or cluster state. Other commands in the pipeline may still have executed. Spring Data Redis or the driver may report an error via a pipeline-level exception instead of returning a "clean" result list in all cases; applications must catch errors at the service boundary.

## 13. Observing and evaluating pipeline effectiveness

A pipeline can reduce network wait time while simultaneously increasing Redis load if the application starts sending more operations than before. For an accurate evaluation, compare **the same dataset, the same command count, and the same concurrency level** across sequential calls, pipelining, and specialized batch commands (if applicable).

| Metric | What to learn |
|---|---|
| Total batch processing time | Does the pipeline reduce actual wall-clock time? |
| API p50/p95/p99 latency | Are requests more stable or slowed down by large batches? |
| Redis command count per request | Pipelining does not itself reduce command count |
| Bytes sent/received | Is large payload size becoming a bottleneck? |
| Average and max batch size | Are there oversized batches or skewed distributions? |
| Command errors and retry rate | Are duplicate writes or partial errors occurring? |
| Redis and client CPU/memory | Are deserialization, output buffers, and loops too heavy? |

Some observation tools:

```bash
redis-cli INFO commandstats
redis-cli INFO stats
redis-cli INFO memory
redis-cli SLOWLOG GET 10
```

`INFO commandstats` shows command counts by type at the Redis instance scope. This metric does not by itself tell you how many round trips a specific request saved. `SLOWLOG` focuses on commands whose Redis-side processing time exceeded a threshold, excluding full network time or connection wait time.

On the Spring side, wrap `executePipelined` with a timer and record batch type, command count, data size, outcome, and latency. Avoid logging full Redis keys/values if they contain personal data or secrets.

### Comparison example

Suppose a batch of 500 keys has these illustrative characteristics:

| Approach | Logical Redis commands | Communication style |
|---|---:|---|
| 500 sequential `get` calls | 500 | Wait for each command's reply |
| One pipeline of 500 `GET`s | 500 | Send multiple commands, gather replies |
| One `MGET` of 500 string keys within supported scope | 1 | One command batching multiple keys |

No fixed latency numbers are guaranteed across the three approaches. `MGET` can be the natural choice for string values and compatible keys; pipelining is more flexible when mixed command types or per-key TTLs are needed. With Redis Cluster, multi-key `MGET` across slots requires checking client support and handling; do not assume every topology shares the same characteristics.

## 14. Real-world case: warming a product price cache

A service needs to warm the cache for 2,000 products before high traffic arrives. Each product has:

- A string key `product:<id>:price`.
- A serialized, version-controlled value.
- A TTL matching freshness requirements, potentially differing by product group.

Running individual sequential `SET`s causes many network waits. A single pipeline of 2,000 commands can increase memory pressure and processing time; the design can split into multiple batches, such as around 200 commands per batch, and then measure to adjust.

Flow:

```text
List of 2,000 records to load
                 |
                 v
       Batch by batchSize
                 |
          +------+------+
          |             |
        Batch 1       Batch 2      ... Batch N
          |             |
          v             v
    executePipelined executePipelined
      (SET + TTL)    (SET + TTL)
          |             |
          +------+------+
                 |
                 v
       Monitor command count, errors,
       total time, and latency
                 |
                 v
         Process results and continue
```

Operational decisions:

- Use `SET` with TTL in the same command when storing a cache value.
- Pace loading or add TTL jitter if many keys might expire simultaneously.
- Limit concurrent batches so Redis is not overwhelmed.
- Build a mechanism to identify which batches have been applied in case of connection errors.
- Do not use a large pipeline as a business commit boundary; for data requiring consistency, add versioning/idempotency or rely on the primary data source.

## 15. Common mistakes when using executePipelined

| Mistake | Impact | How to avoid |
|---|---|---|
| Callback returns a non-`null` value | `executePipelined` rejects the callback's return value | Always `return null` |
| Using `get(...)` result directly inside callback | Value has not been returned while pipeline is queuing | Process `List<Object>` after callback |
| Calling commands via another template or connection in callback | Easily breaks pipeline/session scope | Use the callback's `RedisOperations` |
| Assuming pipeline is a transaction | Partial changes may appear | Use `MULTI`/`EXEC` or an appropriate atomic mechanism when needed |
| Sending a gigantic pipeline | Increases memory and causes latency spikes | Split into bounded batches |
| Casting every response to `String` | Different command types return different result types | Map by command order and type |
| Ignoring `null` in results | Easy to confuse missing key with failed transaction | Distinguish missing values from exceptions |
| Retrying entire batch containing `INCR`/`LPUSH` | Causes duplicate effects | Design idempotency/reconciliation |
| Confusing `MGET` with Hash pipelining | Cannot read Redis Hashes with `MGET` | Pick the right Redis data type API |
| Assuming pipelining supports all multi-key operations on Redis Cluster | May hit slot/topology limits | Check driver support and key placement |

## 16. When to choose executePipelined(SessionCallback)?

```text
Are there multiple Redis commands in one task?
                  |
             +----+----+
             |         |
            No        Yes
             |         |
             v         v
      Normal command  Are the commands independent,
                     not needing earlier results?
                          |
                     +----+----+
                     |         |
                    Yes        No
                     |         |
                     v         v
                 Consider     Use conditional command,
                 MGET/MSET    WATCH/transaction,
                 if suitable  Lua, or two phases
                     |
                     v
            Need mixed command types,
            or per-key TTLs?
                     |
                +----+----+
                |         |
               Yes        No
                |         |
                v         v
         executePipelined  Consider server-side
         (SessionCallback) batch commands first
                |
                v
           Bound batches,
           measure latency, handle errors,
           retries, and idempotency
```

**Core takeaway:** `executePipelined(SessionCallback)` is a convenient choice when you need to issue multiple independent Redis commands via `RedisOperations` within the same session and collect results after the pipeline completes. The callback must return `null`; all responses are received in the outer `List<Object>`. Proper design distinguishes pipelines from transactions, maps responses by command, bounds batch size, and handles both partial errors and connection drops.
