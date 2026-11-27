# Measuring Pipeline Effectiveness with Realistic Data Volumes

## 1. Why must pipeline benchmarks use realistic data?

In a Spring Boot application using Redis for caching, suppose a background job must read 10,000 keys. The sequential way to read them is typically:

```java
for (String key : keys) {
    String value = redisTemplate.opsForValue().get(key);
    process(value);
}
```

On every `GET`, the application waits for Redis to return the result before sending the next command. **Redis pipelining** lets you send multiple commands without waiting for each command's response:

```text
Without pipeline                       With pipeline

App                    Redis           App                    Redis
 | ---- GET k1 --------> |              | ---- GET k1 --------> |
 | <--- value1 --------- |              | ---- GET k2 --------> |
 | ---- GET k2 --------> |              | ---- GET k3 --------> |
 | <--- value2 --------- |              | <--- value1 --------- |
 | ---- GET k3 --------> |              | <--- value2 --------- |
 | <--- value3 --------- |              | <--- value3 --------- |
```

If measured across 10 keys of 5 bytes each, pipelining can show a dramatic speedup because most sequential time is network waiting. However, that **does not prove** pipelining achieves the same speedup when the application must receive 20,000 JSON values of 64 KiB each while Redis simultaneously serves other requests.

As data volume grows, cost shifts from network wait cycles to other factors: bandwidth, Redis CPU, response buffering memory, JSON decoding, Java object allocation, GC, and connection contention.

Therefore, to **measure pipeline effectiveness with realistic data volumes**, characterize the workload accurately, measure comprehensive metrics, and choose batch sizes from observed data instead of assuming "bigger pipeline = faster."

## 2. Which costs does a pipeline reduce?

### 2.1. Cost of each command round trip

A Redis command has several time components:

- Serializing the command from Java into bytes.
- Sending the command over TCP/TLS to Redis.
- Redis parsing and executing the command.
- Transferring the response over the network.
- Redis client reading the reply, decoding, and allocating Java objects.
- Application processing or retaining the result.

With many small commands called **sequentially**, waiting for a network round trip (*round-trip time*, RTT) can dominate total time. Pipelining sends multiple commands consecutively, reducing wait cycles before continuing to send.

An approximate view:

```text
Without pipeline:
  T ≈ N × RTT + processing_time + transfer_time + decoding_time

Pipeline in batches of B commands:
  T ≈ ceil(N / B) × RTT
      + processing_time
      + transfer_time
      + decoding_time
      + buffering_cost
```

This is only a **guiding model**, not a precise prediction formula. Network, Redis, and the application may overlap parts of the work.

### 2.2. What a pipeline does not do

| Common misconception | Accurate understanding |
|---|---|
| Pipelining turns 100 commands into one Redis operation | Redis still has to execute all of those commands |
| Pipelining means multi-core parallel processing | Queuing commands consecutively does not automatically parallelize Redis |
| Pipelining is a transaction | Pipelining does not automatically make a group of commands atomic |
| Pipelining reduces bytes transferred | Response payloads still must travel back to the application |
| Pipelining guarantees every command runs faster | The main gain comes from reducing network waits |
| Bigger batches are always better | Large batches can raise memory, GC, and latency |
| Results can be ignored during benchmarks | If the real app reads results, the benchmark must read them too |

If a later command depends on an earlier command's result—such as `GET balance` followed by deciding `DECRBY`—pure pipelining is insufficient to protect business invariants. In that case, consider atomic Redis commands, Lua, or `WATCH/MULTI/EXEC`.

## 3. Describing the data workload accurately

A benchmark should not have only two parameters: "command count" and "batch size." The following attributes typically determine real-world effectiveness:

| Attribute | What to record | Illustrative scenario |
|---|---|---|
| Command count | Total `GET`/`SET`/`HGET` calls | 1,000, 5,000, 20,000 |
| Distinct keys | Reading many keys vs. repeating hot keys | 5,000 unique keys |
| Value size | Bytes after serialization | 128 B, 2 KiB, 8 KiB |
| Size distribution | p50/p95/p99 of value sizes | Mostly small, a few large values |
| Operation mix | Read, write, or mixed | 80% `GET`, 20% `SET` |
| Serializer | String, JSON, JDK, or custom | `StringRedisSerializer` |
| Client count | Concurrent tasks/requests active | 1, 8, 32 |
| Network | Redis location and RTT | Local, same region, cross-region |
| Redis topology | Standalone, Sentinel, Cluster | Standalone |
| Memory | JVM heap and Redis `maxmemory` | Allocated budget |
| TTL | Do keys expire during the test? | 30 minutes |
| Batch size | Commands per pipeline | 20, 100, 500, 1,000 |

### 3.1. Byte size, not Java String length

`String.length()` does not tell you the exact bytes transmitted over Redis. Example:

```java
import java.nio.charset.StandardCharsets;

String text = "Vietnamese sample data";

int characters = text.length();
int utf8Bytes = text.getBytes(StandardCharsets.UTF_8).length;
```

Unicode characters can take multiple UTF-8 bytes. With JSON, size also depends on field names, nested values, type metadata, and the serializer.

If the application uses `Jackson2JsonRedisSerializer` or `GenericJackson2JsonRedisSerializer`, measure the **output size of that matching serializer**:

```java
byte[] payload = serializer.serialize(customer);
int bytes = payload.length;
```

For `GET` operations, count bytes of **returned values**. For `SET` operations, count bytes of **sent values**. For mixed read/write workloads, report each direction separately.

### 3.2. Same command count does not mean the same amount of work

Compare two tasks that both read 10,000 keys:

```text
Scenario A:
  10,000 × 200 bytes ≈ 1.91 MiB payload

Scenario B:
  10,000 × 64 KiB = 625 MiB payload
```

The command counts are equal, yet data volume differs by more than 300×. In A, RTT savings may account for most of the gain. In B, bandwidth, buffering, and data decoding may dominate the results.

Size distribution matters too. If most values are 1 KiB while 1% are 500 KiB, a batch hitting several large values can be noticeably slower or consume far more memory than another batch with the same command count.

## 4. Metrics to measure

### 4.1. Task completion time

Measure from starting to send commands until **all results are received and processed**:

```java
long started = System.nanoTime();

runWorkload();

long elapsedNanos = System.nanoTime() - started;
double elapsedMillis = elapsedNanos / 1_000_000.0;
```

`System.nanoTime()` is suitable for measuring elapsed durations within the same JVM. Do not subtract wall-clock system timestamps to measure short operations.

Distinguish the duration of **one pipeline batch**, **the entire job**, and **business request** latency.

### 4.2. Command throughput

```text
ops/s = successfully completed commands / execution seconds
```

For example, completing 20,000 commands in 2 seconds equals 10,000 commands/second. If errors or timeouts occur, separate failed commands; do not count every sent command as completed.

### 4.3. Byte throughput

```text
MiB/s payload =
    total payload bytes processed
    / (1,048,576 × execution seconds)
```

This metric helps reveal when bandwidth becomes the bottleneck. It does not equal raw NIC traffic because of Redis RESP framing, key names, TCP, TLS, and other overhead.

### 4.4. Latency percentiles

| Metric | Meaning |
|---|---|
| p50 | Half of samples have durations not exceeding this level |
| p95 | 95% of samples have durations not exceeding this level |
| p99 | 99% of samples have durations not exceeding this level |

State clearly whether percentiles are measured over **job runs**, **batches**, or **HTTP requests**. If a batch of 500 commands completes in 50 ms, dividing 50/500 = 0.1 ms is **not** the p99 of individual Redis commands.

### 4.5. Memory, CPU, and system impact

Measure concurrently:

- Peak heap and allocated objects in the JVM.
- GC pauses and GC frequency.
- Redis CPU and application CPU.
- Network bandwidth, connection counts, and driver buffers.
- p95/p99 of concurrent business requests sharing Redis.
- Error and timeout counts during the benchmark.

A setting that speeds up a background job by 15% while doubling the main API's p99 latency is unlikely to be optimal for the application.

## 5. Designing comparable experiments

You can test three approaches:

1. **Sequential:** issue each `GET` and wait for the result.
2. **Batched pipeline:** send `GET`s for the same key set in batches.
3. **MGET:** when reading many Redis Strings and topology permits, include `MGET` as a comparison point.

All approaches must perform **the same work**: same keys, same data, same serializer, and same level of result inspection/consumption. Do not compare an approach that decodes JSON against one that sends commands and discards replies.

An experimental matrix:

| Load tier | Payload/key | Keys/run | Batch sizes to test |
|---|---:|---:|---|
| Small | 128 B | 5,000 | 20, 100, 500, 1,000 |
| Medium | 2 KiB | 5,000 | 20, 100, 500, 1,000 |
| Large | 8 KiB | 5,000 | 20, 100, 500, 1,000 |
| Mixed | 128 B to 64 KiB | Per real distribution | 20, 100, 500 |

These are **suggested values for measurement**, not configurations proven fastest.

Process:

```text
Generate dataset and load into Redis
             |
             v
Warm up connections, JVM, and serializer
             |
             v
Run sequential/pipeline on the same key set
             |
             v
Repeat multiple runs, vary execution order
             |
             v
Measure elapsed, ops/s, MiB/s, p95, heap, CPU
             |
             v
Compare by payload, batch, concurrency, network
```

When measuring **read speed** alone, exclude data-preparation time from the measurement. **Write** benchmarks need a separate scenario to avoid mixing fundamentally different costs.

## 6. How does Spring Data Redis support pipelining?

`RedisTemplate` and `StringRedisTemplate` provide `executePipelined`. Example:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public List<Object> getBatch(
        StringRedisTemplate redis,
        List<String> keys) {

    return redis.executePipelined(
            (RedisCallback<Object>) connection -> {

                for (String key : keys) {
                    byte[] rawKey =
                            key.getBytes(StandardCharsets.UTF_8);

                    connection.stringCommands().get(rawKey);
                }

                // Command results are collected by executePipelined.
                return null;
            }
    );
}
```

In the example:

- Calling `connection.stringCommands().get(...)` queues a `GET` command into the pipeline.
- The callback returns `null`; query results are not returned directly from the callback.
- `executePipelined` returns `List<Object>` containing the command results in pipeline order.
- With default `StringRedisTemplate`, String values are decoded by the corresponding serializer.
- The result list may **reside in JVM memory simultaneously** before the application processes it.

The example assumes UTF-8-encoded keys per `StringRedisTemplate` defaults. If the application changes the key serializer, use that exact serializer when converting keys to `byte[]`.

### 6.1. Why split into batches?

Suppose we must read 5,000 keys, each value 32 KiB:

```text
5,000 × 32 KiB = 160,000 KiB ≈ 156.25 MiB payload
```

If sent all at once in a single `executePipelined`, the client may have to hold massive result data, plus Java objects and driver buffers.

Splitting with batch size 100 makes each batch roughly 3.125 MiB of payload before overhead; the program can process and release each batch's results before receiving the next batch.

However, **batch size is command count, not byte count**. A 100-command batch is light when values are 128 B, yet heavy when values are 1 MiB.

## 7. Java benchmark example in Spring Boot

The code below uses Java 21 and `StringRedisTemplate`. It prepares a set of keys with fixed-length payloads, then measures sequential reading vs. pipelined reading. `runExample()` only executes when invoked; do not auto-run it on production startup.

### 7.1. Seeding data and two read strategies

```java
package com.example.redis;

import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Random;
import java.util.UUID;
import java.util.function.LongSupplier;

import org.springframework.data.redis.core.RedisCallback;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class RedisPipelineBenchmark {

    private final StringRedisTemplate redis;

    public RedisPipelineBenchmark(StringRedisTemplate redis) {
        this.redis = redis;
    }

    private List<String> seed(
            String runId,
            int count,
            int valueBytes) {

        Random random = new Random(42);
        String alphabet = "abcdefghijklmnopqrstuvwxyz0123456789";
        List<String> keys = new ArrayList<>(count);

        for (int i = 0; i < count; i++) {
            char[] chars = new char[valueBytes];

            for (int j = 0; j < valueBytes; j++) {
                chars[j] = alphabet.charAt(
                        random.nextInt(alphabet.length())
                );
            }

            String key = "bench:pipeline:" + runId + ":" + i;

            redis.opsForValue().set(
                    key,
                    new String(chars),
                    Duration.ofMinutes(30)
            );
            keys.add(key);
        }

        return keys;
    }

    public long sequentialRead(List<String> keys) {
        long payloadBytes = 0;

        for (String key : keys) {
            String value = redis.opsForValue().get(key);

            if (value == null) {
                throw new IllegalStateException("Key not found: " + key);
            }

            payloadBytes += value
                    .getBytes(StandardCharsets.UTF_8).length;
        }

        return payloadBytes;
    }

    public long pipelineRead(
            List<String> keys,
            int batchSize) {

        if (batchSize <= 0) {
            throw new IllegalArgumentException(
                    "batchSize must be greater than 0"
            );
        }

        long payloadBytes = 0;

        for (int offset = 0; offset < keys.size();
                offset += batchSize) {

            // from/to remain effectively final inside the lambda below.
            final int from = offset;
            final int to = Math.min(
                    offset + batchSize,
                    keys.size()
            );

            List<Object> results = redis.executePipelined(
                    (RedisCallback<Object>) connection -> {

                        for (int i = from; i < to; i++) {
                            byte[] rawKey = keys.get(i)
                                    .getBytes(StandardCharsets.UTF_8);

                            connection.stringCommands().get(rawKey);
                        }

                        return null;
                    }
            );

            if (results.size() != to - from) {
                throw new IllegalStateException(
                        "Result count does not match command count"
                );
            }

            for (Object item : results) {
                if (!(item instanceof String value)) {
                    throw new IllegalStateException(
                            "Missing value or mismatched serializer"
                    );
                }

                payloadBytes += value
                        .getBytes(StandardCharsets.UTF_8).length;
            }
        }

        return payloadBytes;
    }

    public record Measurement(
            String method,
            int commands,
            long payloadBytes,
            double milliseconds,
            double opsPerSecond,
            double mebibytesPerSecond
    ) {
    }

    private static Measurement measure(
            String method,
            int commands,
            LongSupplier operation) {

        long started = System.nanoTime();
        long payloadBytes = operation.getAsLong();
        long elapsedNanos = System.nanoTime() - started;

        double seconds = elapsedNanos / 1_000_000_000.0;

        return new Measurement(
                method,
                commands,
                payloadBytes,
                elapsedNanos / 1_000_000.0,
                commands / seconds,
                payloadBytes / (1024.0 * 1024.0 * seconds)
        );
    }

    public List<Measurement> runExample() {
        int count = 5_000;
        int valueBytes = 2_048;

        List<String> keys = seed(
                UUID.randomUUID().toString(),
                count,
                valueBytes
        );

        // Warm up before recording official measurements.
        sequentialRead(keys);
        pipelineRead(keys, 100);

        return List.of(
                measure("sequential", count,
                        () -> sequentialRead(keys)),
                measure("pipeline-100", count,
                        () -> pipelineRead(keys, 100)),
                measure("pipeline-500", count,
                        () -> pipelineRead(keys, 500))
        );
    }
}
```

This is a **minimal measurement harness for illustration**, consisting of one measured read pass per strategy:

1. `seed` creates 5,000 keys, each holding 2,048 ASCII characters = 2,048 UTF-8 bytes.
2. Data is written **before** measurement with a 30-minute TTL.
3. `sequentialRead` waits for each result, verifies presence, and sums bytes.
4. `pipelineRead` uses `executePipelined` in batches, receiving and checking results per batch.
5. `measure` computes elapsed time, commands/second, and payload MiB/second.
6. `Measurement` results can be logged or exported as CSV for comparison.

Crucial conditions: keys must stay present throughout the run, Redis must not evict them under memory pressure, and both strategies must receive the same byte count. If using a custom serializer, adjust encoding/decoding accordingly.

When comparing with real JSON data, swap the example's `String` and serializer for your application's data types and serializer while ensuring both strategies perform equivalent work.

### 7.2. Why is this example not enough for production conclusions?

The snippet runs only one formal pass per approach. A rigorous benchmark requires:

- Warming each strategy sufficiently to eliminate connection initialization and JIT effects.
- Running many iterations after warm-up.
- Rotating execution order: sequential → pipeline 100 → pipeline 500, then pipeline 500 → sequential → pipeline 100.
- Testing multiple payload sizes, key counts, and client counts.
- Reporting percentiles of **task duration**, not just the fastest run.
- Checking JVM heap, GC, and impact on background requests.

Do not treat local machine numbers as reliable predictions for a Redis Cluster or TLS-enabled network.

## 8. Structuring a results table

You can create a table to record data after each test group:

| Payload | Strategy | Batch | Elapsed ms | Ops/s | MiB/s | Peak heap |
|---|---|---:|---|---|---|---|
| 128 B | Sequential | 1 | Measured | Measured | Measured | Measured |
| 128 B | Pipeline | 100 | Measured | Measured | Measured | Measured |
| 2 KiB | Sequential | 1 | Measured | Measured | Measured | Measured |
| 2 KiB | Pipeline | 100 | Measured | Measured | Measured | Measured |
| 2 KiB | Pipeline | 500 | Measured | Measured | Measured | Measured |
| 8 KiB | Pipeline | 100 | Measured | Measured | Measured | Measured |
| 8 KiB | Pipeline | 500 | Measured | Measured | Measured | Measured |

**Do not fill in fabricated figures as benchmark results.** Every value above must be measured in a clearly documented environment and library version.

Speedup can be computed from durations of the same workload:

```text
Speedup = elapsed_sequential / elapsed_pipeline
```

For a **hypothetical** example where a sequential task takes 4 seconds and pipelined takes 0.8 seconds, completion speed improved 5×. Do not publish claims like "pipelining is 5× faster" without the data, methodology, and test environment.

## 9. Choosing batch size using byte budgets and latency

### 9.1. Small batches: many network waits remain

With 5,000 keys and batch size 10, the application needs about 500 pipeline trips. On high-RTT networks, waiting cycles can still consume substantial time.

### 9.2. Large batches: increased buffer pressure

With 5,000 keys and batch size 5,000, a single `executePipelined` call may assemble every result in memory. If each value is 32 KiB, payload alone is around 156.25 MiB.

Actual memory also includes:

- Incoming data buffers in the driver.
- `String`, JSON, or `byte[]` objects.
- The `List<Object>` holding references.
- Copies created by business code.
- Other pipelines running concurrently.

A single huge batch can spike peak heap, GC pauses, and p99 latency of other requests.

### 9.3. Using a byte budget to pick a test starting point

Suppose a batch is allowed roughly 4 MiB of payload and average values are 8 KiB:

```text
4 MiB = 4096 KiB
4096 / 8 = 512 values
```

A batch around 500 can be a **starting point**. Yet if outlier values are huge, a 500-command batch can still far exceed 4 MiB.

Guiding formula:

```text
estimated_batch_size ≈ payload_budget / estimated_value_size
```

The formula **does not guarantee a hard byte cap**, because the client usually does not know `GET` response sizes before receiving them.

### 9.4. Concurrency also consumes memory

If each batch returns about 4 MiB of payload, 20 concurrent batches correspond to roughly 80 MiB **in payload alone**. In practice there is significant additional overhead.

Therefore, tune both **batch size** and **concurrent task count**. A configuration that works fine with one worker can be far too heavy with 50 workers running simultaneously.

## 10. Observing Redis and JVM resources

### 10.1. Redis side

These commands help observe state in a test environment:

```redis
INFO stats
INFO commandstats
INFO cpu
INFO memory
INFO clients
SLOWLOG GET 10
```

`INFO commandstats` provides command-processing statistics. `INFO memory` tracks Redis memory. `SLOWLOG` reflects slow Redis-side command execution time, **excluding full network transit or application processing time**.

A pipeline can cut Java end-to-end time while Redis per-command execution time stays nearly unchanged. Measure both sides.

### 10.2. Application side

Use Micrometer, Java Flight Recorder, and JVM metrics to monitor:

- Pipeline batch duration and overall job duration.
- Used heap, peak heap, and allocated objects.
- GC pauses and JVM CPU time.
- Connection counts, queues, waiting threads, and timeouts.
- p95/p99 of business APIs sharing Redis.

With JSON, decoding time can be substantial. Pipelining only reduces network waits; it does not make Java object allocation free.

### 10.3. Background jobs and online APIs running concurrently

Benchmarking an isolated job does not reveal system impact under load.

A realistic scenario:

```text
Background traffic: continuous GET/SET from API
Job:                read 5,000 keys via pipeline
Observe:            job speed + background API p95/p99 + Redis CPU/heap
```

If batch 2,000 speeds up the job by 5% while pushing background API p99 way up, batch 100 may be more suitable. The goal is **whole-system efficiency**, not just commands/second in a tight loop.

Do not run heavy load experiments on production Redis without safety bounds and a plan to stop and clean up test data.

## 11. Network, driver, and topology impact results

### 11.1. RTT and TLS

Pipelining shows the clearest gains when many small commands traverse a network with noticeable RTT. On localhost, each round trip is already tiny, so benefits can differ.

In your report, record:

```text
Redis version:
Spring Data Redis version:
Client: Lettuce/Jedis and version:
Standalone / Sentinel / Cluster:
TLS:
Network and RTT:
Connection pool:
Serializer:
Batch size:
Concurrent clients:
JVM heap:
Payload:
```

### 11.2. Lettuce and flushing

Spring Data Redis typically uses Lettuce. Lettuce manages connections and dispatches commands asynchronously; some versions/configurations allow tuning how commands are **flushed** inside pipelines.

Exact API names and support can vary across versions. Do not copy a flush setting from another project assuming it is universally optimal. When comparing, hold remaining parameters steady and document connection settings.

### 11.3. Redis Cluster

In Cluster, keys are distributed across multiple hash slots and nodes. Command routing, connection counts, and key distribution affect pipeline efficiency.

`MGET` is a multi-key command subject to slot constraints in Redis Cluster. Pipelining multiple `GET`s does not turn keys across different shards into a valid multi-key command or transaction.

If the real system runs Cluster, measure against a realistic topology and key distribution.

## 12. When is pipelining not the best choice?

### 12.1. A suitable multi-key command exists

When reading multiple Redis Strings:

```redis
MGET cache:1 cache:2 cache:3
```

For multiple fields of **the same Redis Hash**:

```redis
HMGET customer:42 name email city
```

`MGET` or `HMGET` can reduce command count and sometimes data transferred. Compare against pipelining when they fit the data requirements.

### 12.2. Later commands depend on earlier results

```text
GET stock
  |
  v
Check stock > 0
  |
  v
DECR stock
```

Pipelining does not turn this sequence into an atomic check-and-update. When conditions must be protected, consider atomic Redis commands, Lua scripts, or `WATCH/MULTI/EXEC`.

### 12.3. Values are too large

If one `GET` returns a 50 MiB JSON blob, packing 100 `GET` commands into a pipeline does not shrink the JSON. Revisit the data model, split objects, or read only needed fields.

### 12.4. Redis is already CPU- or network-saturated

If Redis CPU or bandwidth is already at its limit, sending commands faster may simply build queues and buffers. This can yield very little throughput gain while increasing latency for other requests.

### 12.5. The task has only a few small commands

With one or two commands, the overhead of organizing a pipeline may not be worth optimizing. Prefer simplicity until real measurements demonstrate a bottleneck.

## 13. Common mistakes when benchmarking pipelines

1. **Measuring only a few commands on localhost.** Results mostly reflect fixed overhead, not large data or production networks.
2. **Comparing ops/s alone.** Add MiB/s because a command can return a few bytes or several MiB.
3. **Counting characters instead of bytes.** Measure serialized bytes, especially with JSON and Unicode.
4. **Sequential decodes results while pipeline skips reading results.** Both strategies must process the same data volume.
5. **Including seed time when measuring GET speed.** Separate setup, warm-up, and formal measurement.
6. **Running only one pass.** Warm up thoroughly, repeat runs, and vary strategy order.
7. **One gigantic pipeline.** `executePipelined` can buffer massive results in memory; measure peak heap and bound batches.
8. **Misinterpreting p99.** Batch percentiles differ from per-request or per-command percentiles.
9. **Ignoring timeouts and missing results.** Verify result counts and processed bytes; track errors separately.
10. **Not measuring background traffic.** You might boost benchmark throughput while slowing down business APIs.
11. **Omitting client/serializer versions.** Results across different driver configs are hard to compare directly.
12. **Treating batch size as a byte cap.** A batch of 200 is 200 commands; total data still depends on values.

## 14. Practice exercises

### Exercise A: Hold command count steady, vary value size

Create 5,000 keys and measure three datasets:

```text
5,000 × 128 B
5,000 × 2 KiB
5,000 × 8 KiB
```

Keep batch size fixed at 100. For each dataset, compare sequential vs. pipelined. Record elapsed, ops/s, MiB/s, and peak heap. Identify when RTT savings become dominated by transfer/decoding costs.

### Exercise B: Hold payload steady, vary batch size

With 5,000 keys of 2 KiB each, test:

```text
Sequential
Pipeline batch 20
Pipeline batch 100
Pipeline batch 500
Pipeline batch 1000
```

Repeat across multiple passes, swap strategy order, and compute p50/p95 of **job duration**. Compare equal bytes processed and find where speedup plateaus.

### Exercise C: Mixed-size data

Create a dataset with mostly 1 KiB values, some 16 KiB values, and a few 64 KiB values. Test batch 100 and 500. Observe whether batches containing large values show greater time and heap variance.

### Exercise D: Measure background traffic

Maintain a steady rate of GET/SET requests while running the benchmark. Measure background request p95/p99 before, during, and after the job. Choose a configuration that keeps requests within their latency budget.

## 15. Self-check questions

**1. Why does pipelining speed things up noticeably when commands are small and RTT is high?**

Because the client avoids waiting a network round trip after every command. When Redis processing and payloads are small, RTT savings make up a large share of total time.

**2. Do two tasks both doing 10,000 GETs necessarily achieve the same speedup?**

No. Payload sizes, serializers, bandwidth, CPU, client count, and background load can all differ.

**3. Is batch 1,000 always better than batch 100?**

No. Larger batches reduce wait rounds but can increase buffers, heap, GC, and latency for other requests.

**4. Can you divide a batch's duration by its command count and call that the per-command p99?**

No. That is only an amortized mean, not the per-command latency distribution.

**5. Why measure MiB/s as well?**

Because ops/s does not show how much data was transferred and decoded. Workloads with the same command count can differ by hundreds of times in bytes.

**6. Is a local benchmark enough to pick a batch size for Cluster?**

No. Re-evaluate RTT, TLS, shards, connections, serializers, and concurrency under the real topology.

**7. Why measure background API p99 when tuning a pipeline job?**

Because a large pipeline can speed up the background job while hurting user-facing latency. Tuning must fit the entire system.

**8. When should you try MGET?**

When reading many Redis Strings and topology multi-key constraints allow it. It is an alternative worth benchmarking on the exact same workload.

## 16. Takeaways

- **Pipelining reduces network wait rounds**, yet does not make Redis commands or returned data disappear.
- **Realistic data volumes** include command count, post-serializer bytes, size distribution, access pattern, network, and concurrency.
- Spring Data Redis `executePipelined` can collect many results in memory; **split into batches and process batch by batch**.
- Evaluate **elapsed time, ops/s, MiB/s, properly scoped percentiles, heap/GC, and impact on background requests** together.
- Suitable batch sizes must come from **measurements under real resource limits**, not a generic universal number.

### References

- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/).
- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html).
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html).
- [Redis — INFO](https://redis.io/docs/latest/commands/info/).
- [Redis — SLOWLOG](https://redis.io/docs/latest/commands/slowlog/).
