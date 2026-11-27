# Batching Commands to Control Memory and Latency

In Spring Data Redis, **pipelining** allows a client to send multiple Redis commands consecutively without waiting for each command's response before sending the next one. Instead of sequentially issuing `SET key1 ...`, waiting for the reply, then issuing `SET key2 ...`, the client can send an entire group of commands and read the replies afterward. The primary benefit is reducing **network round-trip** overhead when operating on many independent keys.

However, sending more commands in a single pipeline does not mean better performance. The client must hold input data and results, while Redis must receive/process the commands and may buffer unsent or unread responses. An enormous pipeline can spike memory usage, prolong the completion time of a batch, cause timeouts, and inflict high latency on other requests.

The practical solution is to **split the list of operations into bounded batches**. Each batch has limits on command count, payload byte volume, and concurrency; finish and consume each batch's results before moving to the next group. This lesson focuses on implementing this strategy with `RedisTemplate.executePipelined(...)` in Spring Data Redis.

## 1. How does a pipeline reduce round trips?

Suppose an application needs to write 2,000 keys to Redis. With synchronous per-command calls:

~~~text
Application                     Redis
    | ---- SET k1 -------------> |
    | <--- reply k1 ------------ |
    | ---- SET k2 -------------> |
    | <--- reply k2 ------------ |
    |                ...         |
    | ---- SET k2000 ----------> |
    | <--- reply k2000 --------- |
~~~

Each command incurs a send-request and receive-response cycle before the next command starts. If the connection round-trip time is 2 ms, sequential network waits alone can contribute significantly to total time; there are also command execution, serialization, and scheduling costs.

When pipelining in batches of 200 commands:

~~~text
Application                     Redis
    | ---- SET k1 -------------> |
    | ---- SET k2 -------------> |
    | ---- SET k3 -------------> |
    |           ...              |
    | ---- SET k200 -----------> |
    | <--- replies ------------- |
    |                            |
    | ---- SET k201 -----------> |
    |           ...              |
    | <--- replies ------------- |
~~~

In practice the driver may coalesce data across multiple socket writes, yet the application **does not wait for individual responses between commands of a pipeline**. Thus, total round-trip cost per batch is usually lower than calling one command at a time.

Approximate cost model:

~~~text
Sequential calls:
    T ≈ N × (RTT + per-command processing time)

Batched pipeline:
    T ≈ num_batches × per-batch round-trip cost
        + total Redis command processing time
        + encode/decode + data transfer + result processing cost

num_batches = ceil(N / batch_size)
~~~

This is an intuitive formula, not a speed guarantee. Redis still has to process every command; large payloads, slow networks, overloaded Redis CPU, or massive reply volumes can negate expected pipeline advantages.

## 2. Why is an oversized pipeline dangerous?

A pipeline consumes memory in at least three places:

| Consumer | Held resources | Risk when batch is too large |
| --- | --- | --- |
| **Java Client** | Input objects, serialized bytes, returned `List<Object>` results | Heap growth, frequent GC, `OutOfMemoryError` |
| **Redis Server** | Command input buffers, connection output buffers, executing data | Memory pressure, latency spikes, possible connection closure per buffer limits |
| **Network/Driver** | Unflushed bytes and unread responses in flight | Slow send/read, timeouts, long-held connections |

Consider two pipelines that both have 1,000 commands yet behave very differently:

- 1,000 `SET` commands writing values of a few dozen bytes each.
- 1,000 `GET` commands where each reply contains a value of roughly 1 MiB.

The second case can generate around **1 GiB** in response payload alone, not counting Java objects, metadata, and temporary copies in memory. Therefore, limiting **command count** alone is not enough; you must also account for **data size** and transfer direction.

In Spring Data Redis, `executePipelined(...)` returns the list of results after the pipeline completes. An application can inadvertently hold this entire list in memory if it sends a large batch. For queries reading many values, this is often the first bottleneck to examine.

### A pipeline is not a transaction

Pipelining is an optimization for transmitting commands and collecting results. It **does not** automatically guarantee that all commands succeed or none run. For example, if a batch has 100 `SET` commands, a network failure or command error does not mean the 100 commands were rolled back.

`MULTI/EXEC` is a separate Redis transaction mechanism; using it also requires understanding error handling and that there is no general rollback for execution-time errors. Do not add `MULTI` merely to make a pipeline "safe" when business logic does not actually need a transaction.

## 3. Choosing two limits: command count and byte volume

To protect both the client and Redis, check two budgets when building a batch:

1. **`maxCommands`**: maximum number of commands placed into one `executePipelined` call.
2. **`maxPayloadBytes`**: maximum estimated total key/value bytes of commands in the batch.

For instance, with a small-string write workload, you might start testing with:

~~~text
maxCommands     = 250
maxPayloadBytes = 512 KiB
~~~

These numbers are only **starting parameters for benchmarking**, not a universal optimum. If each value is several MiB, one command already exceeds the byte threshold; if all values are tiny, the command count limit is usually hit first.

Decision flow when adding a new command:

~~~text
                        Next command
                              |
                              v
                        Estimate bytes
                              |
                              v
                  Does current batch have data?
                         /          \
                        No          Yes
                        |            |
                        |            v
                        |   Adding exceeds budget?
                        |        /          \
                        |      Yes           No
                        |       |             |
                        |       v             |
                        |  Send current batch |
                        |  and free memory    |
                        |       |             |
                        +-------+-------------+
                                |
                                v
                        Add command to batch
                                |
                                v
                     Did batch reach a limit?
                            /        \
                          Yes         No
                           |          |
                           v          v
                      Send batch  Read next command
~~~

The byte limit is usually an **estimated payload** of keys and values before Redis protocol encoding. It excludes RESP framing overhead, command names, serializer inputs, Java objects, or responses. For `GET` operations, returned value size is not necessarily known ahead of time; use real data-size statistics to budget read pipelines.

If a single command exceeds `maxPayloadBytes`, you can send that command alone in a single-element batch or reject it if the system disallows oversized values. You cannot split a single `SET` command into arbitrary smaller commands and preserve the same semantics.

## 4. Using `executePipelined` in Spring Data Redis

Spring Data Redis offers two common approaches:

- `RedisCallback`: uses `RedisConnection` and low-level Redis commands directly.
- `SessionCallback`: operates via the `RedisOperations` API using the template's serializers and a connection context retained across the callback.

The key requirement is that commands of **one batch** must be sent within the callback scope managed by `executePipelined`. Do not open a pipeline manually outside and try to continue it on a different connection.

Short example with `StringRedisTemplate`:

~~~java
import java.util.List;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class SimplePipelineExample {

    private final StringRedisTemplate redis;

    public SimplePipelineExample(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> writeOneBatch() {
        return redis.executePipelined((SessionCallback<Object>) operations -> {
            operations.opsForValue().set("demo:a", "one");
            operations.opsForValue().set("demo:b", "two");
            operations.opsForValue().set("demo:c", "three");
            return null;
        });
    }
}
~~~

`executePipelined` returns `List<Object>` in the order commands were sent in the pipeline. The direct return value **from the callback must be `null`**; command results are obtained from the list returned by Spring Data Redis after closing the pipeline.

Inside the callback, do not rely on the return value of `operations.opsForValue().get(...)` to drive business branching as if it were the real Redis value. During pipelining, command results are usually not yet available; they are collected at the end of the pipeline. If you need to inspect a value before deciding the next command, split into **two phases**: read the first batch's results, process them in Java, and then issue the next batch.

In an application with custom `RedisSerializer`s, `SessionCallback` helps avoid manually encoding keys/values into bytes with the wrong format. Conversely, `RedisCallback` is useful when direct byte-level and low-level command control is needed.

## 5. Complete example: pipeline writer batching by command count and bytes

Suppose an application receives a stream of `Entry(key, value)` records to write into Redis. The goal is to handle a very large data source **without loading every record into a single `List`**.

The code below uses Java 21 and Spring Data Redis. `StringRedisTemplate` encodes keys/values using UTF-8 by default; the example uses that same convention to estimate byte counts and write raw bytes via the connection.

~~~java
package com.example.redis.pipeline;

import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;
import java.util.Objects;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class BatchingRedisWriter {

    private static final int MAX_COMMANDS = 250;
    private static final long MAX_PAYLOAD_BYTES = 512L * 1024;

    private final StringRedisTemplate redis;

    public BatchingRedisWriter(StringRedisTemplate redis) {
        this.redis = Objects.requireNonNull(redis);
    }

    public record Entry(String key, String value) {
    }

    public record WriteStats(int commands, int batches) {
    }

    private record EncodedEntry(byte[] key, byte[] value) {
        long payloadBytes() {
            return (long) key.length + value.length;
        }
    }

    public WriteStats write(Iterator<Entry> source) {
        Objects.requireNonNull(source);

        List<EncodedEntry> batch = new ArrayList<>(MAX_COMMANDS);
        long pendingBytes = 0;
        int commands = 0;
        int batches = 0;

        while (source.hasNext()) {
            Entry entry = Objects.requireNonNull(source.next());
            byte[] key = Objects.requireNonNull(entry.key())
                .getBytes(StandardCharsets.UTF_8);
            byte[] value = Objects.requireNonNull(entry.value())
                .getBytes(StandardCharsets.UTF_8);
            EncodedEntry next = new EncodedEntry(key, value);
            long nextBytes = next.payloadBytes();

            // Flush the current batch before adding an entry that exceeds limits.
            if (!batch.isEmpty()
                    && (batch.size() >= MAX_COMMANDS
                    || pendingBytes + nextBytes > MAX_PAYLOAD_BYTES)) {
                flush(batch);
                batches++;
                batch.clear();
                pendingBytes = 0;
            }

            batch.add(next);
            pendingBytes += nextBytes;
            commands++;

            // Handle the case where the batch hits a threshold or one command is very large.
            if (batch.size() >= MAX_COMMANDS
                    || pendingBytes >= MAX_PAYLOAD_BYTES) {
                flush(batch);
                batches++;
                batch.clear();
                pendingBytes = 0;
            }
        }

        // Flush any remaining entries when the source is exhausted.
        if (!batch.isEmpty()) {
            flush(batch);
            batches++;
        }

        return new WriteStats(commands, batches);
    }

    private void flush(List<EncodedEntry> batch) {
        List<Object> replies =
            redis.executePipelined((RedisCallback<Object>) connection -> {
                for (EncodedEntry entry : batch) {
                    connection.stringCommands().set(
                        entry.key(), entry.value()
                    );
                }
                return null;
            });

        if (replies.size() != batch.size()) {
            throw new IllegalStateException(
                "Unexpected pipeline reply count: " + replies.size()
                + " for " + batch.size() + " commands"
            );
        }

        // In a real application, also inspect errors/reply values
        // per command type; matching reply count alone does not guarantee
        // every operation succeeded.
    }
}
~~~

Usage:

~~~java
List<BatchingRedisWriter.Entry> smallInput = List.of(
    new BatchingRedisWriter.Entry("demo:batch:1", "A"),
    new BatchingRedisWriter.Entry("demo:batch:2", "B"),
    new BatchingRedisWriter.Entry("demo:batch:3", "C")
);

BatchingRedisWriter writer = new BatchingRedisWriter(redisTemplate);
BatchingRedisWriter.WriteStats stats =
    writer.write(smallInput.iterator());

System.out.println(stats.commands()); // 3
System.out.println(stats.batches());  // 1
~~~

`redisTemplate` in the example is a Spring-managed `StringRedisTemplate`. With real data, pass an iterator reading from a file, API, or cursor of another source instead of materializing an entire `List` up front.

### Execution flow and memory bounds

~~~text
      Iterator<Entry> from input source
                     |
                     v
            Encode key/value UTF-8
                     |
                     v
       Bounded List<EncodedEntry>
          250 commands or 512 KiB
                     |
                     v
         executePipelined(batch)
                     |
                     v
          Receive and process replies
                     |
                     v
           clear() buffer list
                     |
                     v
               Next batch
~~~

The code intentionally **sends batches sequentially**. Until `executePipelined` returns, the loop does not start sending a new batch. This creates a form of **natural backpressure**: the input source is not consumed faster than the current pipeline can complete. Only one batch of data and its result list need to reside in memory at a time inside the method.

Boundaries of the example to note:

- `MAX_COMMANDS` and `MAX_PAYLOAD_BYTES` are starting values for benchmarking, not universal defaults.
- `pendingBytes` counts only encoded keys and values; it excludes Redis protocol overhead, Java heap overhead, and driver buffers.
- An oversized single item is sent in its own single-command batch; if a hard per-request limit is required, add input validation.
- `write` returns **commands sent along the normal path** and executed batch count, not proof of an atomic commit. If a pipeline fails after some commands reached Redis, reconcile actual state.
- With a `StringRedisTemplate` configured with a non-default UTF-8 serializer, align encoding inside `RedisCallback` with the actual serializer or switch to `SessionCallback`.
- For read commands, also bound **estimated response size**, since returned data bytes can far exceed sent key sizes.

## 6. Batching GET operations: response memory matters more than request payload

For small-value `SET`s, each command's reply is typically tiny. For `GET`, a single reply can hold an entire large value.

Example reading 10,000 keys in one pipeline:

~~~java
List<Object> results =
    redis.executePipelined((SessionCallback<Object>) operations -> {
        for (String key : keys) {
            operations.opsForValue().get(key);
        }
        return null;
    });
~~~

If `keys` has 10,000 keys and each value is 100 KiB, response payload alone approaches 1 GiB. Each value may also exist as byte arrays, `String`s, and intermediate objects during decoding; actual heap usage can be much higher.

To reduce peak memory, split the key list into small chunks, process each chunk's results, and release references to those results before moving to the next chunk:

~~~java
public void readInChunks(
        List<String> keys,
        StringRedisTemplate redis,
        java.util.function.BiConsumer<String, String> consumer) {

    final int chunkSize = 40; // Adjust according to actual value size.

    for (int start = 0; start < keys.size(); start += chunkSize) {
        int end = Math.min(start + chunkSize, keys.size());
        List<String> chunk = keys.subList(start, end);

        List<Object> values =
            redis.executePipelined((SessionCallback<Object>) operations -> {
                for (String key : chunk) {
                    operations.opsForValue().get(key);
                }
                return null;
            });

        // Pipeline results follow sent command order.
        for (int i = 0; i < chunk.size(); i++) {
            String value = (String) values.get(i);
            consumer.accept(chunk.get(i), value);
        }

        // Do not retain 'values' in a giant accumulated result collection.
    }
}
~~~

This example fits when `StringRedisTemplate` handles string values and each `GET` returns `String` or `null` if the key does not exist. With other serializers, data types, and commands, element types in `List<Object>` can vary; the application must interpret replies according to the issued commands.

`chunkSize = 40` is merely an example. If each value is a tiny 1 KiB, you can test larger chunks; if each value is several MiB, even a 40-item chunk can be too large. When response sizes are unpredictable, enforce data limits at the model layer and choose batch sizes conservatively.

### Why process immediately after each batch?

Suppose code reads in chunks yet appends every reply into one `List<Object> allResults`: Java memory still grows to the size of **the entire dataset**, even though the pipeline was split. Batching only lowers peak memory when result lifetimes stay short: process, write to a destination, or aggregate a small metric, then drop references.

If `consumer` itself buffers every value elsewhere, memory still grows. Hence not only the pipeline, but also the **data sink** must use streaming or bounded buffering.

## 7. How does batch size affect latency?

Batch size is a trade-off:

| Batch | Strengths | Drawbacks |
| --- | --- | --- |
| Too small, e.g., 1–5 commands | Low memory footprint per batch | Nearly like single calls; low round-trip savings |
| Moderate, tuned to workload measurements | Reduces network trips while keeping responses and processing bounded | Must be monitored and adjusted with traffic |
| Very large, tens of thousands of commands or more | Fewer pipeline calls on application side | Peak memory, response buffers, timeouts, fairness, and batch latency can degrade |

**Throughput** and **latency** are not the same quantity:

- *Throughput*: commands/records completed per second.
- *Batch latency*: time from starting to send a batch until all results are received.
- *Per-item waiting time*: an item may have to wait for other items in the same batch to finish before the application processes it.
- *Tail latency*: high percentiles, such as p95/p99, showing abnormally slow batches.

A large batch sometimes raises throughput while also forcing an interactive request to wait longer. If Redis serves both background imports and online APIs, do not let an importer continuously send huge pipelines that monopolize Redis resources.

### There is no single optimal number for every system

Batch size depends on:

- Network latency and distance from the application to Redis.
- Key/value sizes, `GET`-to-`SET` ratio, and response volume.
- Serialization/deserialization cost on the JVM.
- CPU, RAM, buffers, and configuration of the Redis server.
- Redis driver (Lettuce/Jedis), pool, connection count, and concurrency level.
- Redis standalone, Sentinel, or Cluster; routing across nodes changes costs.
- Concurrent online requests and background-task priority.

Benchmark with the actual data shapes, network, and deployment topology rather than copying a "best default" from someone else's example.

## 8. Controlling the number of concurrent pipelines

Limiting commands/bytes per batch is not enough if the application lets 100 requests simultaneously create 100 large pipelines. Then many batches exist across different connections, buffers, and heap regions at once.

Two layers of limits should be combined:

1. **Per-batch size**, such as `maxCommands` and `maxPayloadBytes`.
2. **Concurrent batches in flight**, such as worker count or a semaphore for import tasks.

If using a background queue with 4 workers, each sending one batch sequentially, active pipelines are bounded by those workers. For an HTTP endpoint that can receive hundreds of requests, explicitly bound concurrency when a request triggers bulk operations.

Illustration with `Semaphore`:

~~~java
import java.util.concurrent.Semaphore;

public final class LimitedImportService {
    private final BatchingRedisWriter writer;
    private final Semaphore permits = new Semaphore(4);

    public LimitedImportService(BatchingRedisWriter writer) {
        this.writer = writer;
    }

    public BatchingRedisWriter.WriteStats importEntries(
            java.util.Iterator<BatchingRedisWriter.Entry> entries)
            throws InterruptedException {

        permits.acquire();
        try {
            return writer.write(entries);
        } finally {
            permits.release();
        }
    }
}
~~~

This example allows at most four concurrent `importEntries(...)` executions **within one JVM instance**. If the service runs across multiple pods or instances, each instance holds its own `Semaphore`: system-wide throttling requires coordination at the appropriate layer. Waiting on a permit also needs a timeout or cancellation semantics if the call path has strict SLAs.

A semaphore bounds **concurrent import executions**, not directly the number of connections or bytes in flight; actual counts also depend on the driver/pool and other Redis operations in the application.

## 9. Flushing, network buffering, and response handling

At a low level, pipelining consists of: enabling pipeline mode on the connection, sending a sequence of commands, flushing bytes to the network per driver mechanics, reading results, and closing the pipeline. Spring Data Redis's `executePipelined` manages that lifecycle for each callback.

In some Lettuce configurations, pipeline flush policies can be tuned to reduce socket writes. However, flushing behavior depends on the Spring Data Redis version, Lettuce version, and connection type. Do not assume a specific flush option is always present or has the exact same effect across every driver.

**Flush policy and batch size solve two different problems:**

- **Flush policy** determines when the driver pushes bytes to the network while a pipeline is open.
- **Batch size** determines total commands/bytes held in one application unit of work.

Even when the driver optimizes flushing, a pipeline with too many `GET` commands still receives the corresponding volume of replies; bytes and memory do not disappear simply from fewer flushes.

For error responses, `executePipelined` can throw a driver/template exception or return command results that must be interpreted per command and configuration. A pipeline returning the expected element count **is not proof** that every command succeeded. If business logic requires confirming each operation, inspect the corresponding results and maintain an explicit error-handling strategy.

## 10. Error handling and per-batch retries

Batching creates a convenient boundary for logging, checkpointing, and retrying. However, because a pipeline is not a transaction, a failed batch may have **part of its commands already processed by Redis**.

Example:

~~~text
Batch 1 (250 SET) → returned full results
Batch 2 (250 SET) → client timeout after sending commands
Batch 3           → not sent yet
~~~

For Batch 2, the application **cannot conclude** that Redis wrote no keys. The server may have processed some or all commands before the replies were lost. If retrying the entire batch, safety depends on operation type:

| Operation | Retry after uncertain outcome | Explanation |
| --- | --- | --- |
| `SET key value` with same value | Often retryable if it won't clobber newer state | Rewriting the same value is idempotent in value, though it may refresh TTL or overwrite concurrent data |
| `DEL key` | Usually safe when goal is simply key absence | Deleted-key count in reply may differ across attempts |
| `INCR` / `DECR` | Unsafe to retry blindly | May increment/decrement twice |
| `LPUSH` / `RPUSH` | Unsafe without deduplication | May insert duplicate elements |
| `SADD key member` | Idempotent for Set membership | But "newly added vs. already present" reply may differ |
| `SET` with TTL | Re-evaluate expiration point on retry | Rewriting may reset the TTL countdown |

When synchronizing a large dataset, design for:

- **Stable IDs** per record, avoiding generating new IDs on each retry.
- **Per-batch checkpoints** recorded only after sufficient completion evidence.
- **Bounded retries**, exponential backoff, and investigable error logging.
- **State reconciliation** for operations with uncertain outcomes, especially counter updates.
- **Business-level idempotency**, using transactions/scripts or duplicate-detection mechanisms when needed.

Do not treat `List<Object>` returned from a pipeline as an atomic multi-command commit log. Characterize accurately what guarantees each operation provides.

## 11. Pipelines and time-to-live (TTL)

If values are stored with a TTL, ensure each command uses proper expiration semantics. Two commands:

~~~redis
SET session:42 payload
EXPIRE session:42 60
~~~

placed consecutively in the same pipeline **do not form an atomic operation**. If the application fails or the connection drops after `SET` reaches Redis but before `EXPIRE` executes, the key can persist without the intended TTL.

When data and TTL must be set together, prefer a single Redis command supporting expiration:

~~~redis
SET session:42 payload EX 60
~~~

In the high-level Spring Data Redis API, use:

~~~java
redis.opsForValue().set(
    "session:42",
    "payload",
    java.time.Duration.ofSeconds(60)
);
~~~

When using `SessionCallback` inside a pipeline, queue `opsForValue().set(key, value, duration)` operations so each key is written with its expiration:

~~~java
redis.executePipelined((SessionCallback<Object>) operations -> {
    operations.opsForValue().set(
        "session:43", "payload-43",
        java.time.Duration.ofSeconds(60)
    );
    operations.opsForValue().set(
        "session:44", "payload-44",
        java.time.Duration.ofSeconds(60)
    );
    return null;
});
~~~

Each `SET` carries its own TTL, while the batch as a whole is still not a transaction. On retry, expiration times may shift because re-running the write establishes a new TTL; ensure this matches business requirements.

## 12. Benchmarking before choosing batch size

Instead of raising batch size until throughput looks high, compare multiple configurations on the **same workload** while observing both the client and Redis.

Example experiment plan:

| Run | Command limit | Payload limit | Concurrent batches |
| --- | ---: | ---: | ---: |
| A | 25 | 128 KiB | 1 |
| B | 100 | 256 KiB | 1 |
| C | 250 | 512 KiB | 1 |
| D | 500 | 1 MiB | 1 |
| E | 250 | 512 KiB | 4 |

These numbers serve as a **benchmarking plan**, not fixed recommendations. Each run should use the same command mix, key/value size distribution, API concurrency level, and a sufficiently steady measurement duration.

Metrics worth tracking:

| Metric | Why it matters |
| --- | --- |
| Commands/second and records/second | Measures actual throughput |
| Batch latency p50/p95/p99 | Detects abnormally slow batches |
| JVM heap before/after batch and GC pauses | Observes memory and object allocation cost |
| Sent/received payload bytes per batch | Checks against byte budget |
| Redis CPU and memory | Monitors server load |
| Redis client input/output buffers | Detects accumulation when client reads slowly |
| Timeouts, connection resets, retry counts | Spots batch configs exceeding system capacity |
| Latency of online APIs sharing Redis | Checks impact of background pipelines on other workloads |

On Redis, `INFO` and `CLIENT LIST` provide useful diagnostic data. Fields in `CLIENT LIST` can include `qbuf` (query buffer) and `omem` (output buffer memory) depending on version. Application heap metrics should come from Micrometer/JVM metrics or an appropriate profiler rather than being inferred solely from batch size.

Example timing measurement at the Java layer:

~~~java
long start = System.nanoTime();
List<Object> replies = redis.executePipelined(
    (SessionCallback<Object>) operations -> {
        for (String key : keysInOneBatch) {
            operations.opsForValue().get(key);
        }
        return null;
    }
);
long elapsedNanos = System.nanoTime() - start;

System.out.printf(
    "commands=%d, replies=%d, batchMs=%.2f%n",
    keysInOneBatch.size(),
    replies.size(),
    elapsedNanos / 1_000_000.0
);
~~~

This is **application-observed** time, including callback execution, command sending, reply receiving, and response conversion; it is not a Redis-server-only measurement. To compute p95/p99, record many measurements into metrics/histograms rather than drawing conclusions from one run.

If large batches increase throughput while pushing online API p99 latency or memory usage over budget, reduce batch size, reduce pipeline concurrency, or isolate resources for background tasks.

## 13. Integration testing with real Redis

Mocking `RedisTemplate` only proves the callback was invoked. To verify that batching actually writes all data and connections complete cleanly after `executePipelined`, you need a real Redis test instance. Example using JUnit 5, Spring Boot, AssertJ, and Testcontainers.

Illustrative dependencies (Gradle Groovy when versions are managed by the Spring Boot BOM/plugin):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-redis'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
}
~~~

The test below creates 620 keys, enough to cross multiple batches under a 250-command limit:

~~~java
package com.example.redis.pipeline;

import java.util.ArrayList;
import java.util.List;
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

@Testcontainers
@SpringBootTest(classes = BatchingRedisWriterTest.TestApp.class)
class BatchingRedisWriterTest {

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
            "spring.data.redis.port", () -> REDIS.getMappedPort(6379)
        );
    }

    @Autowired
    StringRedisTemplate redis;

    @Test
    void splitsWritesIntoBoundedPipelines() {
        String prefix = "it:pipeline:" + UUID.randomUUID() + ":";
        List<BatchingRedisWriter.Entry> entries = new ArrayList<>();

        for (int i = 0; i < 620; i++) {
            entries.add(new BatchingRedisWriter.Entry(
                prefix + i, "value-" + i
            ));
        }

        BatchingRedisWriter writer = new BatchingRedisWriter(redis);

        try {
            BatchingRedisWriter.WriteStats stats =
                writer.write(entries.iterator());

            assertThat(stats.commands()).isEqualTo(620);
            assertThat(stats.batches()).isEqualTo(3);

            for (int i = 0; i < 620; i++) {
                assertThat(redis.opsForValue().get(prefix + i))
                    .isEqualTo("value-" + i);
            }
        } finally {
            // Clean up only keys created by the test; avoid FLUSHALL/FLUSHDB.
            for (int i = 0; i < 620; i++) {
                redis.delete(prefix + i);
            }
        }
    }
}
~~~

In the test data, each key/value is only a few dozen bytes, so the 250-command threshold is reached before 512 KiB: 620 commands are sent across three batches of sizes 250, 250, and 120.

The test requires Docker or a compatible container runtime. In projects that already provide a dedicated Redis for integration tests, that infrastructure can be used. To test the byte limit, generate values sized to force batches to close on `MAX_PAYLOAD_BYTES` before reaching `MAX_COMMANDS`.

The test verifies final data read back from Redis and the batch count reported by the chunking algorithm. It does not replace benchmarks for throughput, memory, tail latency, or impact on other workloads.

## 14. Common design mistakes

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| JVM heap spikes during `GET` pipeline | Creating too many large replies in one `List<Object>` | Reduce batch size; process and release replies per batch |
| Heap still grows despite batching | Entire input or `allResults` kept in memory | Use iterators/streams and a non-accumulating consumer |
| Pipeline is faster but API p99 worsens | Background pipelines too big or too many running concurrently | Reduce batch size/concurrency; measure shared-workload latency |
| Small pipeline is no faster than single calls | Too many round trips across batches | Increase batch size gradually based on measurements |
| Only 200 commands yet payload still huge | Limiting command count only | Add byte limits and account for response sizes |
| Timeout after sending batch then retry doubles counts | Non-idempotent commands may have executed | Reconcile, deduplicate, or design safe retries |
| `SET` succeeds yet key lacks TTL | Splitting `SET` and `EXPIRE` into two non-atomic commands | Use `SET` with expiration in one command |
| `GET` result inside callback is `null` | Command is still pipelined | Read results after `executePipelined` |
| Command results mapped to wrong keys | Command-to-response mapping order not preserved | Keep each batch's input list to align by index |
| Single-command batch exceeds byte budget | Individual item is huge | Enforce a separate max-value limit or handle singletons per policy |
| Connections reset under heavy load | Output buffer/memory/timeouts or network failures, depending on cause | Check Redis/client metrics; reduce pressure; handle retries |
| Pipeline behaves unexpectedly on Cluster | Routing/connections to different nodes | Check driver, topology, hash slots, and command emission model |

## 15. Considerations for Redis Cluster and mixed command types

Redis Cluster distributes keys across multiple hash slots and nodes. For single-key commands like `GET` and `SET`, a cluster-aware driver may have to route commands to the appropriate nodes. A pipeline sending to keys residing on multiple nodes does not necessarily share the same send/receive model as a pipeline on a single standalone Redis server.

Do not assume command ordering across **different nodes** creates a cross-node transaction. Multi-key commands like `MGET`, `MSET`, or set operations may require keys to reside in the same hash slot, depending on command/topology. For large cluster workloads, explicitly verify the Redis driver's pipelining capabilities and how data is distributed.

A batch mixing `GET`, `SET`, `INCR`, and `DEL` also returns different result types. `List<Object>` must be decoded in **exact command order**; do not cast every element to `String` just because the template is typed as `StringRedisTemplate`.

When data needs processing with dedicated atomic semantics, use the appropriate command. For example, incrementing a counter needs `INCR` instead of reading `GET` and writing `SET` in the same pipeline: pipelining does not protect read-modify-write sequences against changes by other clients.

## 16. Bringing batching into a production service

A large import or sync workflow typically has three parts:

~~~text
       Data source
       File / DB / API
             |
             v
       Iterator/stream
             |
             v
       Validate + serialize
             |
             v
       Bounded batch collector
       count + payload bytes
             |
             v
       executePipelined
             |
             v
       Read results + metrics
             |
             +------> Error: log/checkpoint/controlled retry
             |
             v
       Release batch memory
             |
             v
       Loop until source ends
~~~

Clearly define:

- **Latency target:** is this a background batch import or direct commands serving an HTTP request?
- **Memory budget:** max Java heap, largest response size, and tolerable Redis buffers.
- **Concurrency budget:** how many pipelines are allowed simultaneously in one JVM and across the whole system?
- **Error boundary:** retry the whole batch or per record? Which commands are idempotent?
- **Data format:** are serializers, TTLs, encodings, and key identifiers used consistently?
- **Measurements:** throughput, p95/p99 latency, heap/GC, Redis CPU/buffers, errors, and retries.

If an ingestion task only needs a few dozen infrequent commands, regular `RedisTemplate` calls may be simple enough. Pipelining fits best when there are enough independent commands and network round trips are a significant cost; benchmark results should determine how large a batch should be.

## 17. Summary

Pipelining in Spring Data Redis reduces per-command response wait times, but an unbounded pipeline shifts pressure onto **client memory, Redis output buffers, the network, and full-batch processing time**.

A sustainable strategy splits work into bounded batches by **command count, byte volume, and concurrency**, consumes replies as soon as each batch completes, and avoids accumulating all results in Java. For large reads, response budgets matter more than input key counts. For writes, consider retries, idempotency, and commands requiring atomic TTLs.

`RedisTemplate.executePipelined(...)` is a tool for transmitting grouped commands; it does not provide full-batch rollback or an automatic batch-size optimizer for every workload. Measure throughput alongside tail latency, heap, and Redis buffers, then tune batches to match real operational requirements.
