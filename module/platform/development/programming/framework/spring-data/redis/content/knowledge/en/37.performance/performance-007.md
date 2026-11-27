# Balancing Command Batch Size Against Memory and Response Time

In **Spring Data Redis**, performance optimization often starts with the question: *"Should we group multiple Redis operations into a single round to reduce network exchanges?"* The answer is usually **yes, but larger is not always better**.

If you send 1,000 `GET` commands one by one, the client waits through too many network round trips. If you group 1,000 commands into one pipeline, per-command waiting drops sharply. At the same time, however, Redis and the application must buffer more commands and responses; the batch can occupy a connection for longer; failures become harder to isolate; early-arriving requests have to wait for the rest of the batch to assemble; and tail latency (*p95/p99*) can degrade.

What you need to optimize is not **the largest possible batch size**, but **the balance point between throughput, memory, wait time, concurrency limits, and recoverability**.

This lesson explains how to choose batch sizes for pipelining, `MGET`/`MSET`, batch processing, `SCAN`, Redis Streams, and Lua in Spring Data Redis applications, providing Java examples, quantitative models, benchmarking practices, and pitfalls to avoid.

## 1. "Command Batching" Has Several Different Meanings

The same word *batch* can describe Redis mechanisms with very different semantics.

| Mechanism | What Does the Group Contain? | Primary Goal | Atomic for the Whole Group? |
|---|---|---|---|
| Multiple sequential Java calls | N calls to `GET`/`SET` | Simple to write, easy to isolate errors | No |
| **Pipelining** | N commands sent without waiting for each reply | Reduce round trips | **No** |
| **Multi-key command** | `MGET`, `MSET`, and commands accepting multiple keys | Reduce commands/round trips | Depends on command and Cluster limits |
| **`MULTI`/`EXEC`** | N commands queued into a transaction | Prevent other clients from interleaving during EXEC | Per Redis transaction semantics; no runtime error rollback |
| **Lua script** | N Redis operations executed in one script | Atomic check/update and fewer network trips | Script executes atomically, **no auto-rollback** on runtime error |
| **`SCAN COUNT`** | Work hint per scan iteration | Bound work per scan step | No; not a snapshot |
| **Redis Streams `COUNT`** | Max messages requested in one read | Balance throughput and processing time | Does not guarantee whole batch succeeds |
| **Application-level batch** | N requests/items accumulated before sending | Reduce I/O/scheduling overhead | Depends on underlying command and protocol |

For example: `batchSize = 100` in a `StreamMessageListenerContainer` is not equivalent to "pipelining 100 SETs" or a Lua script touching 100 keys. Each has distinct limits on memory, latency, and recovery.

**Principle:** before tuning batch size, state clearly **what the batch unit is**, when the batch flushes, how large the returned data can grow, and what happens on partial failure.

## 2. Three Competing Objectives

Optimizing batch size simultaneously affects:

1. **Throughput:** operations or records processed per second.
2. **Latency:** time from request arrival until result delivery; distinguish average from p95/p99.
3. **Memory:** command buffers, response buffers, Java objects, serializer buffers, connection buffers, and stored Redis data.

Three additional constraints must not be ignored:

- **Correctness:** is the final state valid; are operations lost, duplicated, or reordered?
- **Fairness:** does a long batch block lower-latency or critical requests?
- **Recoverability:** if a timeout or client crash occurs mid-batch, can you tell what ran so retries stay safe?

Example:

```text
Small batch:
  + Flushes quickly, minimal waiting in assembly queues.
  + Easier error isolation, less memory held per turn.
  - More round trips and more flushes.
  - Lower throughput when network RTT is significant.

Large batch:
  + Amortizes round trips, reduces flushes, can raise throughput.
  - Buffers many requests/replies, raising peak memory.
  - Increases batch formation wait and p99.
  - If downstream is slow, large groups hold connections longer.
  - Mid-batch failures yield ambiguous outcomes or heavy reprocessing.
```

There is no default batch size optimal across all networks, command types, and value sizes.

## 3. Why Can Batching Reduce Round Trips?

Suppose a Redis connection has estimated round-trip time (*RTT*) `R` and average server command execution time `C`. Calling commands synchronously one by one:

\[
T_{\text{sequential}}(N) \approx N(R+C)
\]

If N commands are pipelined and replies return in one batch, a simplified model is:

\[
T_{\text{pipeline}}(N) \approx R + NC + T_{\text{transfer}} + T_{\text{client}}
\]

Thus, **RTT cost is amortized across the commands in each flush**. However, transfer, serialization, queueing, and Redis server load remain.

In an idealized model, average cost per operation for batch size B can be written as:

\[
t_{\text{avg}}(B) \approx \frac{R}{B} + C + D(B)
\]

Where `D(B)` captures extra costs of transfer, decoding, queueing, flushing, and contention.

This is an **explanatory model**, not a precise formula for application latency. It helps visualize the trade-off: as B increases, `R/B` shrinks, while `D(B)` can grow.

### An Illustrative Calculation Only

Assume `R = 0.8 ms` and `C = 0.06 ms` per command, ignoring other costs:

| Batch Size B | Estimated `R/B + C` / command |
|---:|---:|
| 1 | 0.860 ms |
| 10 | 0.140 ms |
| 50 | 0.076 ms |
| 200 | 0.064 ms |
| 1,000 | 0.0608 ms |

The biggest gain appears moving from B = 1 to B = 10 or 50. Going from 200 to 1,000 saves very little RTT per command in the model. In practice, huge batches can degrade memory and tail latency far more than that tiny savings.

**Do not treat numbers in this table as real Redis benchmarks.** Actual Redis, serializers, networks, and command mixes yield different results.

## 4. Batch Formation Wait Time Is Also Latency

There are two styles of batching:

- **Pre-formed batch:** a service already has 500 IDs from a single request and batches the reads. No waiting for other requests is needed.
- **Cross-request micro-batching:** an aggregator waits until 500 items arrive from multiple requests or until a max wait timeout before flushing.

The second case introduces **batch formation delay**.

Suppose requests arrive steadily at 1,000 operations/second, and the aggregator flushes only when B items accumulate with no max wait timeout. Under roughly uniform arrivals, average wait time to fill a batch is approximately:

\[
W_{\text{formation}} \approx \frac{B-1}{2\lambda}
\]

where `λ` is arrivals per second.

| B | Avg Wait to Fill Batch at 1,000 op/s |
|---:|---:|
| 1 | 0 ms |
| 10 | 4.5 ms |
| 50 | 24.5 ms |
| 200 | 99.5 ms |
| 1,000 | 499.5 ms |

This is an idealized model illustrating the risk, **not a substitute for measured data**. Traffic bursts, rate swings, multiple workers, and flush timeouts alter wait distributions.

An HTTP service requiring p99 below 100 ms cannot rely solely on "wait until 1,000 items accumulate before sending" when traffic is low or uneven. In most cases, you must bound **item count B, byte limit S, and maximum wait time W**.

## 5. Memory Grows with Both Command and Result Sizes

While a pipeline is active, data resides simultaneously in multiple places:

```text
Java application:
    request objects / input collections
    serialized keys/values
    command queue / futures
    reply buffers
    deserialized List<Object> / DTOs

Network / Redis client:
    outbound command bytes
    inbound response bytes
    connection buffers

Redis server:
    client input/output buffers
    command/reply bookkeeping
    the dataset itself in keyspace
```

Therefore, do not calculate only key/value sizes inside Redis. An `MGET` reading 5,000 values forces the JVM to retain the result list and deserialized object copies even if Redis itself has ample memory.

A rough estimate for **concurrently in-flight payloads**:

\[
M_{\text{payload}} \approx B \times (S_{\text{request}} + S_{\text{reply}}) \times F
\]

Where:

- `B`: commands/items per batch;
- `S_request`: average request bytes/item;
- `S_reply`: average reply bytes/item;
- `F`: number of concurrently in-flight batches.

Illustrative example only:

```text
B = 2,000
request payload per item ≈ 2 KiB
response payload per item ≈ 4 KiB
F = 4 in-flight batches

Total payload bytes roughly:
  2,000 × (2 + 4) KiB × 4
  = 48,000 KiB
  ≈ 46.9 MiB
```

That 46.9 MiB **excludes** Java object headers, collection overhead, intermediate serializer buffers, protocol headers, socket buffers, heap fragmentation, and copies. Actual peak memory can be substantially higher.

Especially if every Spring HTTP request opens its own pipeline while hundreds of requests execute concurrently, **moderate per-request batch sizes can still produce huge aggregate memory usage**.

## 6. Total Data Volume Matters More Than Command Count Alone

Two batches both containing 200 commands can behave completely differently:

```text
Batch A:
  200 GET commands, each reply 16 bytes
  -> roughly 3.2 KiB reply payload (excluding protocol)

Batch B:
  200 GET commands, each reply 2 MiB
  -> roughly 400 MiB reply payload
```

If you only configure `maxBatchCommands = 200`, Batch B can blow past memory and network budgets.

Consider together:

- **Max commands/items per batch.**
- **Max serialized bytes per batch**, tracking request bytes and estimated reply bytes separately.
- **Max wait time** so low traffic does not stall indefinitely.
- **Max in-flight batches** to prevent unbounded queues.
- **Result buffer size** or consuming replies chunk by chunk.
- **Max processing time** per batch when commands are CPU/server-heavy.

When reading values with widely varying sizes, you may need value-size histograms and byte thresholds; response size cannot be accurately inferred from key count alone.

## 7. Batch Size and Tail Latency p95/p99

Throughput gains are often reported in operations/second, yet user requests experience **end-to-end latency**:

```text
T_request
  = time waiting to join a batch
  + time waiting for an in-flight slot
  + serialization time
  + network send / Redis execution time
  + time receiving and deserializing replies
  + result mapping / business logic time
```

When batches grow large:

1. Early requests wait longer for more items to arrive.
2. One oversized item delays the entire group.
3. A connection executing a long batch makes other callers wait.
4. Garbage collection rises when allocating large `List<Object>`/DTOs all at once.
5. Retrying a large batch after timeout causes traffic spikes or duplicate side effects.
6. P99 can worsen even while average throughput rises.

**Metric to measure:** time from when the user/request generates the operation until its result returns, **not just `executePipelined` duration**. Measuring only after flush hides batch formation delay—often the dominant contributor to p99.

## 8. Defining Batch Size Correctly by Spring Data Redis API

With `StringRedisTemplate` or `RedisTemplate`, common grouping mechanisms include:

| API | Batch Unit | Characteristics |
|---|---|---|
| `opsForValue().multiGet(keys)` | Keys per multi-key read | Multi-key API returning a result collection |
| `opsForValue().multiSet(values)` | Key/value pairs | Multi-key API |
| `executePipelined(callback)` | Commands issued by callback | Multiple Redis commands, replies collected into a List |
| `execute(SessionCallback)` with `multi/exec` | Commands in transaction | Connection-scoped transaction control |
| `scan(ScanOptions.count(n))` | `COUNT` hint per `SCAN` step | Not a fixed element count |
| `opsForStream().read(options.count(n), ...)` | Records requested per read | Not a pending/ACK limit |
| `StreamMessageListenerContainerOptions.batchSize(n)` | Records per poll | Listener still processes and ACKs individually |
| `execute(RedisScript<T>, keys, args...)` | Keys and logic in one script | Server-side execution, not pipelining |
| Reactive `bufferTimeout(B,W)` | Publisher items buffered before emitting a batch | Does not automatically enforce Redis atomicity |

Some APIs vary in overloads or details across Spring Data Redis versions. What matters is **understanding the actual Redis commands generated** and never applying pipelining rules blindly to Streams or Lua.

## 9. Reading Multiple Keys with MGET: Convenient Yet Bounded

If one request needs 100 independent product names, 100 `GET`s can be replaced by one `MGET` on standalone Redis:

```java
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public class ProductNameLookup {
    private final StringRedisTemplate redis;

    public ProductNameLookup(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> findNames(List<String> keys) {
        if (keys.isEmpty()) {
            return List.of();
        }
        return redis.opsForValue().multiGet(keys);
    }
}
```

Key notes:

- Results are returned **in input key order** per the `MGET` contract.
- Missing keys correspond to `null` elements in the list; verify the API contract and handle misses.
- `multiGet` may materialize all replies in memory at once.
- `MGET` does not turn a series of GETs into a multi-writer transactional snapshot beyond single-command Redis server semantics.
- In **Redis Cluster**, multi-key commands have hash-slot restrictions; drivers/APIs may split commands by node/slot in some setups, yet **never assume a cross-slot MGET is atomic or universally supported**. Test against your target topology.

Reading 50,000 keys in one `multiGet` can trigger severe memory peaks and latency. For large inputs, split into smaller chunks and release results chunk by chunk.

## 10. Splitting MGET Into Bounded Chunks

Chunked reading pattern:

```java
import java.util.ArrayList;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;

public final class ChunkedMultiGet {

    private final StringRedisTemplate redis;

    public ChunkedMultiGet(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<String> getInChunks(
            List<String> keys,
            int maxKeysPerBatch) {

        if (maxKeysPerBatch <= 0) {
            throw new IllegalArgumentException(
                    "maxKeysPerBatch must be positive");
        }

        List<String> output = new ArrayList<>(keys.size());

        for (int offset = 0; offset < keys.size();
                offset += maxKeysPerBatch) {

            int end = Math.min(keys.size(),
                    offset + maxKeysPerBatch);

            List<String> chunk = keys.subList(offset, end);
            List<String> values =
                    redis.opsForValue().multiGet(chunk);

            if (values == null) {
                throw new IllegalStateException(
                        "MGET returned null batch result");
            }

            output.addAll(values);
        }

        return output;
    }
}
```

This version **only bounds keys per Redis call**, while still accumulating the entire `output` list in the JVM. If the goal is limiting peak memory, a better approach is **consuming each chunk and releasing it immediately** rather than returning one List containing all data.

### Processing Each Chunk Without Retaining All Replies

```java
public void processInChunks(
        List<String> keys,
        int batchSize,
        java.util.function.BiConsumer<String, String> consumer) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize");
    }

    for (int i = 0; i < keys.size(); i += batchSize) {
        int end = Math.min(keys.size(), i + batchSize);
        List<String> slice = keys.subList(i, end);

        List<String> values = redis.opsForValue().multiGet(slice);

        if (values == null || values.size() != slice.size()) {
            throw new IllegalStateException("Unexpected MGET result");
        }

        for (int j = 0; j < slice.size(); j++) {
            consumer.accept(slice.get(j), values.get(j));
        }
    }
}
```

Ensure `consumer` itself does not retain all values in another List/cache, otherwise memory still grows.

When inputs are massive or streamed from a database, **avoid materializing the entire key list upfront**; fetch keys page by page, process one chunk, and move to the next page.

## 11. Pipelining in Spring Data Redis

Spring Data Redis provides `executePipelined`. Example when 100 independent GETs are needed without relying on multi-key semantics:

```java
import java.util.List;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;
import org.springframework.data.redis.core.StringRedisTemplate;

public class PipelinedReader {

    private final StringRedisTemplate redis;

    public PipelinedReader(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public List<Object> getAll(List<String> keys) {
        if (keys.isEmpty()) {
            return List.of();
        }

        return redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        for (String key : keys) {
                            ops.opsForValue().get(key);
                        }

                        // Callback must return null. Replies are collected afterward.
                        return null;
                    }
                });
    }
}
```

Inside a pipeline:

- `get` calls inside the callback **do not immediately return String values** like a synchronous GET.
- `executePipelined` collects replies into `List<Object>` once the pipeline executes and completes reading.
- Validate reply count and ordering against sent commands.
- Serialization and result deserialization can allocate many objects on the heap.
- An error in one pipelined command does not roll back earlier successful commands.
- Redis Cluster routing/pipelining behavior depends on the driver; test on your actual topology.

### Watch the Size of the Reply List

`executePipelined` returns **the complete reply list for the submitted pipeline**. Sending 50,000 GETs for large values forces the JVM to retain all results simultaneously.

To cap peak memory, rather than one 50,000-command pipeline, split into moderate pipelines and **consume/finish each pipeline** before starting the next. Never submit one giant callback expecting the driver to stream partial results lazily to Java.

## 12. Chunked Pipelining Instead of One Unbounded Batch

```java
import java.util.List;
import java.util.function.BiConsumer;
import org.springframework.data.redis.core.RedisOperations;
import org.springframework.data.redis.core.SessionCallback;

public void processWithPipelines(
        List<String> keys,
        int batchSize,
        BiConsumer<String, Object> consumer) {

    if (batchSize <= 0) {
        throw new IllegalArgumentException("batchSize");
    }

    for (int i = 0; i < keys.size(); i += batchSize) {
        int end = Math.min(keys.size(), i + batchSize);
        List<String> chunk = keys.subList(i, end);

        List<Object> replies = redis.executePipelined(
                new SessionCallback<Object>() {
                    @Override
                    @SuppressWarnings({"rawtypes", "unchecked"})
                    public Object execute(RedisOperations ops) {
                        for (String key : chunk) {
                            ops.opsForValue().get(key);
                        }
                        return null;
                    }
                });

        if (replies.size() != chunk.size()) {
            throw new IllegalStateException(
                    "Pipeline reply count mismatch");
        }

        for (int j = 0; j < chunk.size(); j++) {
            consumer.accept(chunk.get(j), replies.get(j));
        }
    }
}
```

This example assumes replies correspond directly to ordered GET commands; for transactions, scripts, or errors with complex replies, define the contract explicitly.

Chunking limits how many replies live in memory at once. However:

- The input `List<String> keys` still sits in memory.
- A slow `consumer` prolongs the end-to-end request.
- If the third chunk fails, the first two chunks have already executed.
- You may need progress checkpoints (offset, last processed ID) to retry safely.
- Do not launch hundreds of concurrent pipelines simply because each chunk is small.

**Batch size limit and in-flight limit are two separate knobs.** If each batch has 200 commands yet 1,000 batches run concurrently, in-flight command volume is still massive.

## 13. MGET vs Pipeline: Which Should You Choose?

| Criterion | `MGET` | Pipeline of Multiple `GET`s |
|---|---|---|
| Logical Redis command | Single multi-key read | N independent GET commands |
| Round trips | Usually minimal when command is valid | Eliminates per-GET waiting via pipelining |
| Result | One list returning values | One reply per command, assembled on client |
| Error handling | Error at multi-key command level | Per-GET or per-route errors possible |
| Redis Cluster | Multi-key slot constraints; test driver behavior | Individual GETs can route to appropriate nodes |
| Atomic snapshot | Single-command semantics within valid server scope | No cross-pipeline snapshot or atomicity |
| Memory footprint | One potentially large value list | Reply list and command buffers can be large |
| Best suited when | Keys share valid scope and only values are needed | Mixed command types or independent keys/routes |

You cannot conclude `MGET` is always faster than pipelining or vice versa from command count alone. Measure with **your real Redis topology, key placement, and value sizes**.

When reading keys across multiple Redis Cluster slots, **grouping by hash slot** or sending independent GETs via a cluster-aware client can be more suitable. However, grouping by slot scrambles input order; map replies back to input keys/IDs explicitly instead of assuming positional alignment after reordering.

## 14. Writing Multiple Keys: Batch Size and Partial Success Risk

Suppose you need to update 10,000 cache entries. Splitting into 100 batches of 100 `SET`s captures pipelining benefits.

Suppose batch 60 times out:

```text
Batches 1..59: received success replies
Batch 60: reply lost / unknown how many commands executed
Batches 61..100: not yet sent
```

You cannot assume "all cache entries still hold old values" or "no SET in batch 60 executed." Retry safety depends on each command's semantics:

- `SET key value` with the same value is generally idempotent on final state, though TTL may reset or another writer may have intervened.
- `INCR`/`DECR` have cumulative side effects; retrying can double-increment/decrement.
- `LPUSH`/`XADD` can insert duplicate elements/events on retry.
- `DEL` is usually idempotent on final state, though returned deleted counts will differ.
- Lua scripts with side effects do not become idempotent simply by being atomic.

When writing cache from a database source, use **version fields** or invalidation/reconciliation to guard against stale overwrites. When writing business events, use operation IDs/outbox patterns or reliable deduplication.

## 15. Pipelining Is Not MULTI/EXEC

Distinguish two grouping patterns:

```text
Pipeline:
  SET A
  SET B
  SET C
  -> send multiple commands to save round trips
  -> commands are independent with respect to atomicity

Transaction:
  MULTI
  SET A
  SET B
  SET C
  EXEC
  -> commands inside EXEC run without other client commands interleaving
```

Spring Data Redis uses:

- `executePipelined(...)` for pipelining.
- `SessionCallback` + `multi()`/`exec()` for Redis transactions.
- `RedisScript`/`DefaultRedisScript` for server-side logic.

Never call `executePipelined` in a method named `atomicBatchUpdate` without genuine atomicity guarantees. Even `MULTI/EXEC` **does not roll back runtime errors** like SQL transactions do.

### Large Batches Inside Transactions Have Downsides

An `EXEC` containing tens of thousands of commands can keep Redis busy through a long batch execution, raising latency for other clients. Large transactions also consume queueing and buffer memory before execution.

If business logic genuinely demands atomicity over 50,000 updates, re-evaluate the data model and invariant scope: stuffing everything into a huge Redis transaction or script can break latency SLAs for unrelated requests.

## 16. Do Not Confuse batchSize with Lettuce Flush Policy

With Lettuce, configuration options may control **when pipelined commands are flushed to the socket**. Client options and API details vary by version; certain Spring Data Redis/Lettuce versions let you choose flush policies rather than flushing every single command.

Distinguish between:

- Commands submitted inside your `executePipelined` callback.
- Commands buffered by the client before flushing to the connection.
- Bytes written to the socket per flush.
- Replies buffered by the client before converting to Java objects.
- Batches executed concurrently by the application.

For example, the application chunks by 200 commands while the driver flushes according to its own policy; total network behavior cannot be deduced solely from `200`.

When tuning Lettuce options:

1. Verify your driver version and supported APIs.
2. Measure actual commands/flush and latency instead of guessing.
3. Monitor outbound queue memory when flushing is deferred.
4. Ensure errors/shutdowns do not strand buffered commands.
5. Never treat flush policies as a substitute for in-flight limits or transaction guarantees.

## 17. HGETALL and Large-Result Commands Are Also "Batches"

A single command can still return a huge volume of data:

```text
HGETALL profile:huge
SMEMBERS wishlist:huge
ZRANGE ranking:global 0 -1
LRANGE tasks:all 0 -1
XRANGE events:all - +
```

Each command forces Redis to build a massive response and the client to deserialize every element. So "just one command means low memory" is false.

Alternatives:

| Large Query | Ways to Reduce Peak |
|---|---|
| `HGETALL` on a large Hash | `HMGET` target fields or cursor-based `HSCAN` |
| `SMEMBERS` on a large Set | `SSCAN` for chunked processing |
| `ZRANGE 0 -1` on a giant ZSet | Bounded ranges split by score/rank |
| `LRANGE 0 -1` on a very long List | Small ranges or proper queue design |
| `XRANGE - +` full stream | `XRANGE ... COUNT n` with offset |
| `MGET` tens of thousands of values | Split keys into bounded batches |
| Full-keyspace read pipeline | Split pipelines and consume reply chunks |

**The goal is bounding returned data**, not just bounding command count.

## 18. SCAN COUNT Is a Hint, Not a Fixed Page Size

Redis `SCAN` takes a cursor and `COUNT`:

```bash
redis-cli SCAN 0 MATCH 'cache:product:*' COUNT 100
```

In Spring Data Redis:

```java
import org.springframework.data.redis.core.Cursor;
import org.springframework.data.redis.core.ScanOptions;

ScanOptions options =
        ScanOptions.scanOptions()
                .match("cache:product:*")
                .count(100)
                .build();

try (Cursor<String> cursor = redis.scan(options)) {
    while (cursor.hasNext()) {
        String key = cursor.next();
        // Process each key; do not retain all keys in a giant List.
    }
}
```

**`COUNT 100` is only a hint for work per scan step**; Redis may return fewer or more keys. Cursor `0` signals completion of the full scan, **not** an iteration returning 0 elements.

Key properties to remember:

- `SCAN` can return duplicate keys while the keyspace mutates.
- There is no consistent snapshot across Redis.
- Raising `COUNT` can cut scan round trips while increasing per-call processing/response time.
- `MATCH` filters by pattern; Redis still traverses slots/buckets rather than using an index.
- In Redis Cluster, `SCAN` on one node does not scan the entire cluster.
- Close the Cursor when finished to release connection resources.

Tests for `SCAN` should assert **correct handling of potential duplicates** and bounded time/memory, not that every step returns exactly 100 keys.

## 19. Application Scan Pagination Does Not Mean Stable Pagination

If a UI needs "page 1, page 2, page 3" over continuously changing data, `SCAN` does not provide **stable ordering and snapshot paging** like a database query with proper snapshot mechanics.

Therefore, do not expose raw Redis SCAN cursors as business pagination without understanding their properties:

- Keys can be added or removed between iterations.
- A key can appear more than once.
- Ordering carries no business meaning.
- Returned batch lengths vary.
- Cursors are tied to scan state, topology, and client context.

`SCAN` fits **best-effort maintenance/inventory**, not "products sorted by newest." When stable paging is needed, choose a structure or database designed for it, such as a ZSet with explicit score tie-breaking or SQL.

## 20. Redis Streams COUNT and Listener batchSize

With Redis Streams, `COUNT` caps entries requested per read:

```bash
redis-cli XREAD COUNT 100 STREAMS orders:events 0-0
```

In a consumer group:

```bash
redis-cli XREADGROUP GROUP orders-workers worker-1 COUNT 100 STREAMS orders:events '>'
```

In Spring Data Redis:

```java
import java.time.Duration;
import org.springframework.data.redis.stream.StreamMessageListenerContainerOptions;

var options = StreamMessageListenerContainerOptions
        .<String, org.springframework.data.redis.connection.stream.MapRecord
                <String, String, String>>builder()
        .batchSize(100)
        .pollTimeout(Duration.ofSeconds(2))
        .executor(taskExecutor)
        .build();
```

`taskExecutor` is an application-configured executor bean. This snippet shows options only; the container must still be created, registered with listeners, and started/stopped per lifecycle.

Distinguish carefully:

- `batchSize(100)` controls records per **poll**.
- It does not automatically cap the **Pending Entries List (PEL)** at 100 messages.
- It does not guarantee the listener processes 100 messages in one business transaction.
- It does not automatically execute `XACK` upon valid completion.
- If listeners are slow, large batches leave delivered messages waiting longer for processing.
- If a worker crashes, unACKed messages remain pending and require reclaiming.

### Impact Table for Streams batchSize

| Small Batch | Large Batch |
|---|---|
| Reacts promptly to new messages given suitable flush/poll | Fewer read polls under heavy backlog |
| Fewer messages delivered per poll | Can create more unACKed pending messages |
| Easier to isolate failing messages | Must track which messages succeeded |
| Callbacks triggered in smaller chunks | Large read can tie up handlers longer |
| Fits heavy/heterogeneous messages | Fits small messages, fast handlers, and high volume |

Never raise `batchSize` to fix a growing PEL caused by consumers failing to ACK. That is a **recovery, idempotency, and downstream throughput** problem, not a poll-size problem.

## 21. Lua Scripts Also Have a "Batch Size" and Blocking Risk

A Lua script can execute hundreds of Redis commands server-side, saving round trips and making check-then-write logic atomic.

Example:

```lua
-- KEYS[1] = counter key
-- ARGV[1] = increment step

local current = redis.call('INCRBY', KEYS[1], ARGV[1])
return current
```

For incrementing a counter, **a single `INCRBY` suffices**; wrapping a single command in Lua adds no new atomicity benefit.

Lua makes sense when combining multiple steps, such as a version check and conditional update:

```lua
-- KEYS[1] = value key
-- ARGV[1] = expected string
-- ARGV[2] = new string

local current = redis.call('GET', KEYS[1])

if current == ARGV[1] then
    redis.call('SET', KEYS[1], ARGV[2])
    return 1
end

return 0
```

However, **packing too many operations into one script** keeps Redis busy executing the script, forcing other client commands to wait. Complex checks, tens of thousands of keys, or long loops can degrade p99 across the entire Redis instance/primary.

Lua scripts do not natively yield/chunk midway like pipelined batches, because splitting could break desired global atomicity. Keep **invariant scopes small** so scripts stay brief; if processing a massive dataset, redesign the data architecture instead of building a "mega-script" over everything.

### Two Pitfalls When Testing Large Lua Batches

1. A script failing mid-way after writes **does not roll back** writes that already executed before the runtime error.
2. A client timeout after `EVAL` does not prove the script did not run; retrying can duplicate side effects.

In Redis Cluster, keys touched by a script must obey hash-slot rules. A passing standalone test does not prove a multi-key script works on Cluster.

## 22. Redis Cluster Complicates Batch Selection

Redis Cluster maps every key to one of **16,384 hash slots**. Multi-key commands have slot restrictions; independent commands in a pipeline must be routed by a cluster-aware client to the right primaries.

```text
Application has 300 GETs:
  100 keys -> slot/node A
  100 keys -> slot/node B
  100 keys -> slot/node C
```

Connecting to one node and sending `MGET` across all keys returns `CROSSSLOT`. If a cluster-aware client sends independent `GET`s, it routes by slot, though each node's speed and buffering can differ.

Factors to consider:

- **Multi-key commands:** keys must satisfy hash-slot constraints and client/server support.
- **Pipelining:** multi-node routing changes buffer and latency behavior compared to standalone.
- **Lua/MULTI:** atomicity scope does not span multiple Redis primaries.
- **Hot slots:** overly broad hash tags funnel too many keys into one slot/node.
- **Failover/resharding:** `MOVED`/`ASK` and timeouts can occur mid-batch.
- **Read preference:** reading replicas risks stale data relative to the primary.
- **Node memory:** servers enforce per-node memory/buffer limits; balanced client batches do not guarantee balanced primary load.

Using hash tags like `cart:{user-42}:items` and `cart:{user-42}:total` co-locates those keys in the same slot when multi-key operations are required. Never apply `{global}` across all keys, as that defeats sharding.

### Response Time Is Governed by the Slowest Node

When an assembled batch awaits replies from multiple nodes, end-to-end latency is driven by **the slowest responding node**, even when other nodes respond quickly. Measure per-node/slot latency and response size, not only cluster-wide averages.

## 23. Concurrency Limits Matter as Much as Batch Limits

Suppose each pipeline carries 100 commands and returns 50 KiB of replies on average. With 10 concurrent pipelines:

```text
100 × 10 = 1,000 commands involved
50 KiB × 10 = 500 KiB reply payload (illustrative)
```

Scaling up to 1,000 in-flight pipelines:

```text
100 × 1,000 = 100,000 commands
50 KiB × 1,000 ≈ 48.8 MiB reply payload
```

That excludes protocol framing, metadata, futures, Java objects, and client/server buffers. Pushing throughput by opening unbounded pipelines causes runaway memory and latency.

A practical policy:

```text
maxCommandsPerBatch = 100
maxEstimatedBytesPerBatch = 1 MiB
maxInFlightBatches = 8
maxWaitBeforeFlush = 5 ms
```

These numbers are **conceptual examples**, not unified defaults supplied by Spring Data Redis. Several of these limits must be implemented at the application/queue layer.

Include **backpressure**: when in-flight batches hit the cap, new requests wait in a **bounded** queue, get rejected per contract, or throttle upstream. Never let Java queues grow unboundedly during a Redis outage.

## 24. Count-and-Time Buffering in Reactive Pipelines

Project Reactor can group items with `bufferTimeout(maxSize, maxTime)`:

```java
import java.time.Duration;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

Flux<String> sourceKeys = Flux.fromIterable(keys);

Flux<List<String>> batches = sourceKeys
        .bufferTimeout(100, Duration.ofMillis(10));
```

Here a batch emits when **100 keys accumulate** or when **the operator max wait time elapses**. There is no Redis I/O in this snippet yet; `bufferTimeout` only groups elements at the Reactor layer.

With `ReactiveStringRedisTemplate`:

```java
import org.springframework.data.redis.core.ReactiveStringRedisTemplate;

Flux<List<String>> results = Flux.fromIterable(keys)
        .bufferTimeout(100, Duration.ofMillis(10))
        .flatMap(
                batch -> reactiveRedis.opsForValue().multiGet(batch),
                4);
```

`reactiveRedis` is a configured `ReactiveStringRedisTemplate` bean. `flatMap(..., 4)` bounds **inner publisher concurrency** at an illustrative limit of 4; it does not bound total memory of input `keys` or ensure in-flight batches stay within a byte budget. If results must preserve input batch order, consider `concatMap` or appropriate re-ordering.

**Practical note:** `multiGet` may return a `List` containing `null` elements for missing keys per the API contract; do not feed `null`s directly into `Flux.just`/`Flux.fromIterable` without handling them. Also verify multi-key slot rules if Redis is deployed as a Cluster.

### Never Call block() in WebFlux Just to Force Batching

A reactive service should not do:

```java
List<String> values =
        reactiveRedis.opsForValue()
                .multiGet(batch)
                .block();
```

on the WebFlux event loop. `.block()` turns execution into synchronous waiting and can throw errors on non-blocking threads. Return `Mono`/`Flux` and compose pipelines for framework subscription.

## 25. Why Does Micro-Batching Need a Byte Budget?

`bufferTimeout(100, 10 ms)` bounds item count and wait time, **not total serialized bytes**. One 10 MiB item can still make a 100-item batch huge.

When payloads vary in size, the application should:

- Estimate bytes before enqueuing.
- Reject or separately route items exceeding a single-item limit.
- Flush the batch right before breaching the byte budget.
- Cap in-flight batches.
- Enforce max wait time for early arrivals.
- Define handling for oversized items (dedicated path, valid chunking, or rejection).

### Pseudocode for a Batch Aggregator

```text
batch = []
batchBytes = 0
firstEnqueuedAt = none

for each incomingItem:
    itemBytes = estimateSerializedSize(incomingItem)

    if itemBytes > MAX_SINGLE_ITEM_BYTES:
        rejectOrRouteSeparately(incomingItem)
        continue

    if batch not empty and (
        batch.size >= MAX_ITEMS or
        batchBytes + itemBytes > MAX_BATCH_BYTES
    ):
        submitWithInFlightLimit(batch)
        batch = []
        batchBytes = 0

    add incomingItem to batch
    batchBytes += itemBytes

    if now - firstEnqueuedAt >= MAX_WAIT:
        submitWithInFlightLimit(batch)
        batch = []
        batchBytes = 0
```

In a real implementation, you need a monotonic timer/clock, thread safety, shutdown flushing, and queue overflow handling; this pseudocode only highlights **flushing whenever any bound is reached**.

Never estimate `itemBytes` purely from Java character count when the Redis wire format uses UTF-8, JSON, compression, or binary protocols; wire bytes can differ significantly.

## 26. Oversized Batches Can Cause Head-of-Line Blocking

A slow batch of thousands of operations keeps a connection or server busy, forcing later requests to wait.

```text
Connection / Redis server:
  [Batch A: 5,000 cmds]   [Urgent GET]   [Batch B]
         slow               waiting
```

Mitigations:

1. Split long batches into shorter chunks.
2. Bound both command count and byte size per batch.
3. Separate critical traffic (interactive GETs) from background bulk jobs if infrastructure/policy permits.
4. Tune concurrency rather than funneling every command onto a single connection.
5. Measure p95/p99 per workload, not only bulk job throughput.
6. Avoid giant Lua scripts or `EXEC` blocks that stall other clients noticeably.
7. Propagate request deadlines so batchers drop expired work instead of wasting capacity.

If Redis Server is already CPU-bound or memory-bound, reducing round trips via pipelining may no longer raise throughput; it only lengthens queues.

## 27. When Should Batch Size Be Small?

Prefer small batches or no batching delay when:

- Requests have tight deadlines and sparse arrival rates.
- Values/replies are large or have highly skewed size distributions.
- Redis nodes already exhibit high p99 latency.
- Commands have side effects hard to retry/make idempotent.
- Multiple failure domains exist, e.g., cluster routing across nodes.
- Per-item error isolation is required for detailed reporting.
- Lua scripts or transactions run CPU/server-heavy logic.
- Applications run with tight JVM heap or strict container memory limits.
- Downstream databases/consumers are slow and need crisp backpressure.

A sound approach is starting with small batches as a baseline, measuring, and increasing in controlled steps. Never chase peak throughput once tail latency or memory budgets are breached.

## 28. When Can Larger Batch Sizes Help?

Larger batches can help when:

- A large input set is already present in one place, incurring zero formation wait.
- RTT to Redis is significantly larger than command execution time.
- Individual commands are small, simple, independent, and chunk-safe.
- Redis/server/network have ample headroom.
- The application consumes replies chunk by chunk without retaining everything.
- Partial failures have clear retry/idempotency strategies.
- Batches run in background jobs with separate deadlines from interactive traffic.
- Monitoring tracks p99, peak memory, and in-flight batch limits.

Even then, step sizes up gradually and stop where throughput flattens while memory or p99 begins climbing noticeably.

## 29. What Questions Must Benchmarks Answer?

A useful benchmark specifies:

- **Workload:** 100% GET, 100% SET, mixed GET/SET, Hash/ZSet command mixes, or Streams.
- **Data:** key counts, payload bytes, hit/miss ratio, cache TTL, hot-key distribution.
- **Network:** actual RTT and bandwidth to Redis, same or cross network zone.
- **Topology:** standalone, Sentinel, Redis Cluster; whether replica reads are enabled.
- **Client:** Spring Data Redis version, Lettuce version, serializer, connection config.
- **Batch parameters:** command count, bytes, max wait, and in-flight cap.
- **Concurrency:** concurrent requests/threads/publishers.
- **Timing:** warm-up, steady-state, and sample duration.
- **Results:** throughput, p50/p95/p99, error rate, peak memory, and correctness.
- **Measurement units:** HTTP requests, Redis commands, or processed records.

Never report 100,000 Redis commands/s as "100,000 user requests/s" if each user request issues 20 commands.

## 30. Designing a Controlled Experiment Matrix

An experiment can explore configurations such as the following (**not default recommendations**):

| Config | Max Commands | Max Bytes | Max Wait | Max In-Flight |
|---|---:|---:|---:|---:|
| A — baseline | 1 | 64 KiB | 0 ms | 4 |
| B — small | 20 | 256 KiB | 2 ms | 4 |
| C — medium | 100 | 1 MiB | 5 ms | 8 |
| D — large | 500 | 4 MiB | 10 ms | 8 |
| E — very large | 2,000 | 16 MiB | 20 ms | 8 |

For each configuration, record:

```text
throughput_ops_sec
throughput_http_requests_sec
latency_p50_ms
latency_p95_ms
latency_p99_ms
batch_formation_wait_p99_ms
batch_fill_ratio
batch_bytes_p95
batch_bytes_p99
inflight_batch_max
pending_queue_depth_max
jvm_heap_used_peak
jvm_gc_pause_p99
redis_command_latency_p99
redis_memory_used
redis_cpu
timeout_rate
retry_rate
error_rate
```

If stepping from C to E raises throughput by just 2% while p99 jumps from 40 ms to 180 ms and heap peak doubles, E is unlikely to suit an HTTP API with a 100 ms p99 SLO.

Run multiple trials to filter out warm-up, GC, and CI variance. For production-like tests, sustain load long enough to expose memory buildup or queue saturation rather than running a 10-second burst on an empty system.

## 31. Measuring End-to-End Latency in Java

A simple measurement:

```java
long started = System.nanoTime();

try {
    List<Object> replies = redis.executePipelined(callback);
    processReplies(replies);
} finally {
    long elapsedNanos = System.nanoTime() - started;
    recordLatencyNanos(elapsedNanos);
}
```

`recordLatencyNanos` is an application-implemented metric recorder. `System.nanoTime()` measures elapsed durations, not wall-clock timestamps across time zones.

However, the snippet above measures only from calling the Redis pipeline. If a request sat in a **batch queue** beforehand, stamp the start time **the moment the item enters the queue**:

```text
item.receivedAtNanos
    |
    +--> wait for batch formation
    |
    +--> wait for in-flight permit
    |
    +--> Redis command
    |
    +--> deserialize
    |
    +--> business result ready
    |
item.completedAtNanos

Latency E2E = completed - received
```

Distinguish per-item latency from whole-batch latency. Recording only a timer around a 100-item batch hides the fact that the first item waited much longer than the last item.

### Monitoring with Micrometer

Spring Boot apps can use Micrometer/Actuator to export histogram timers and percentiles per registry config. When tagging:

- Operation type: GET, SET, MGET, pipeline, Streams poll.
- Batch size bucket: small/medium/large—do not emit a unique tag per exact count.
- Namespace or logical service name.
- Success/error/timeout.
- Redis topology or node role if telemetry supports it.
- Payload size bucket.

**Do not put Redis keys containing user IDs/tokens into metric tags**, which explodes cardinality and leaks sensitive data. Measure bytes and counts with histograms/summaries rather than per-key time series.

## 32. Little's Law and In-Flight Work

A useful queueing identity in steady state is **Little's Law**:

\[
L = \lambda W
\]

Where:

- `L`: average requests/operations in the system;
- `λ`: average arrival/completion rate;
- `W`: average time spent in the system.

If a system processes around 20,000 operations/s with an average end-to-end time of 50 ms, average in-flight operations will be near:

\[
L = 20\,000 \times 0.05 = 1\,000
\]

This does not mean Redis executes 1,000 commands in parallel; it represents **total work waiting or executing across the measured boundary**.

When batch formation delay increases, `W` increases, so `L` and buffering needs grow even if throughput stays flat. That explains why enlarging batches sometimes triggers a negative feedback loop on memory: larger batch → longer wait → more in-flight requests → deeper queues → higher latency.

Little's Law is a reasoning tool, not an exact predictor under traffic bursts or unstable overload.

## 33. Backpressure and Safe Load Shedding

When the batcher queue fills up, the application has three main choices:

1. **Backpressure:** signal upstream to slow down per contract.
2. **Bounded queue + reject:** reject or return an appropriate error once limits are hit.
3. **Load shedding/priority:** protect critical requests and drop non-essential work.

What never to do is hold an unbounded `ConcurrentLinkedQueue` and keep accepting requests while Redis stalls. JVM memory will exhaust before Redis recovers.

When consuming from Redis Streams, backpressure also involves **ACK/PEL lag**, not just Java queues. When pausing new batch reads, ensure already-delivered unACKed messages still recover cleanly if a worker crashes.

With reactive operators, `flatMap(..., concurrency)` bounds concurrent inner publishers, yet does not automatically enforce byte budgets, upstream subscription demand, or eager upstream producers. Observe queueing across the full pipeline.

## 34. When Not to Increase Pipelining to "Fix" Issues

### Failure A: Redis Server CPU Is Already Near Saturation

If Redis CPU is the bottleneck, batching cuts network overhead without **making the server process commands significantly faster**. Large batches lengthen queues and can worsen p99. Optimize commands/algorithms, payloads, or scale/shard appropriately.

### Failure B: Network Bandwidth Is Bottlenecked by Large Values

Pipelining does not erase bytes on the wire. If transferring 10 GiB of values, grouping GETs does not shrink total payload size. Shrink data, project needed fields, or revise caching strategies.

### Failure C: Too Many Results Held on the Heap

A giant pipeline returning `List<Object>` can drive up GC pauses. Chunk and process incrementally without accumulating results into another list.

### Failure D: Workload Has a Hot Key

A hot key/slot in Redis Cluster creates a single-node bottleneck. Increasing client batch size will not distribute one giant ZSet across multiple primaries. Re-evaluate the data model or key sharding for your use case.

### Failure E: Each Command Requires an Atomic Condition

For "check stock then decrement," pipelining `GET` and `DECR` is unsafe under concurrency. Use atomic commands or Lua/transactions before benchmarking.

### Failure F: Redis Streams Pending Grows Due to Missing ACKs

Raising `batchSize` does not fix consumers receiving messages without ACKing. Inspect the PEL, error handling, idempotency, and worker reclaiming.

### Failure G: Connection Timeouts and Unbounded Retries

Large batches plus unbounded timeout retries amplify load and duplicate side effects. Enforce retry budgets and command idempotency classification.

## 35. Case Study: Bulk Cache Warm-Up

An application must warm 200,000 product cache entries from a database before a campaign.

Requirements:

- Source of truth lives in the database; Redis is only a cache.
- Each product entry has a TTL.
- Warm-up runs in the background without materially impacting HTTP traffic.
- Each product payload is 1–10 KiB.
- Retries for incomplete entries are allowed given proper versioning/TTL.

One design:

```text
Database cursor (pages of 200-500 rows)
        |
        v
Serialize product DTOs
        |
        v
Bounded pipeline chunks
  max items = 100
  max estimated bytes = 512 KiB
  max in-flight = 2
        |
        v
Redis SET with TTL
        |
        v
Metrics + progress checkpoint
```

Do not load 200,000 rows into one `List<Product>` and fire a 200,000-SET pipeline. Even if Redis accepts it, the JVM holds massive input/reply buffers, triggers GC spikes, and hurts interactive request latency.

Measure:

- Background throughput.
- Redis memory/CPU and eviction rate.
- Interactive user traffic GET/SET p99 during warm-up.
- Retried or skipped item count.
- Cache freshness/source version if data changes during warm-up.

If source data changes mid-run, a warm-up job reading an old version and calling `SET` after a newer update can make the cache stale. Batch size does not solve this race; use TTLs, version-aware writes, or invalidation.

## 36. Case Study: Looking Up Multiple User Permissions

A service reads permissions for 5 users per HTTP request with a very tight p99 target.

Two approaches:

```text
A: 5 sequential GETs
B: 1 MGET (if key placement/command is valid)
C: pipeline 5 GETs via cluster-aware driver
```

Data volume is small and all 5 keys are already known within one request, so batching cuts RTT with **zero batch formation wait**. This is a great fit for `multiGet` or pipelining.

However, permissions are security-sensitive data; stale reads or Redis failure fallbacks must be evaluated strictly. Never read stale replicas just for throughput when permissions were just revoked.

If a request only needs 5 keys, there is no reason to wait to "accumulate 100 user keys" across different HTTP requests if that pushes p99 upward. Cross-request micro-batching only makes sense when measured gains are large and latency SLAs allow it.

## 37. Case Study: Redis Streams Consumer

A worker processes search-index update events:

```text
XREADGROUP COUNT B
    |
    v
Deserialize B records
    |
    v
Process each record
    |
    +--> success -> XACK
    |
    +--> failure -> leave pending/retry/DLQ
```

With `B=10`, polling is frequent yet local backlog stays small. With `B=500`, polling drops under deep backlogs, yet hundreds of messages are delivered and held pending processing/ACK.

Measure:

- Average and p99 processing time per event.
- Poll count and time blocked.
- PEL size and oldest pending idle time.
- **ACKed** throughput, not just read throughput from Redis.
- Reclaim/duplicate count.
- JVM heap when message payloads are large.
- End-to-end event lag from `XADD` to business completion.

Do not assume `COUNT` tells Redis to wait until B messages exist before returning; stream read commands have specific semantics for returned records and `BLOCK` timeouts. "Waiting for a full batch" is typically application-side buffering, not a universal property of Redis Streams `COUNT`.

## 38. Case Study: Updating 50,000 ZSet Scores

A job updates scores for many users:

```text
ZINCRBY leaderboard:weekly:{game-1} delta user-id
```

Putting 50,000 `ZINCRBY` commands into one pipeline reduces round trips, yet brings risks:

- One hot ZSet key lives on one Redis primary and does not scale by member count.
- The client buffers many commands/replies.
- On timeout after partial execution, retrying `ZINCRBY` can double-increment scores.
- Long background bulk updates can inflate p99 for leaderboard read requests.
- Partial failures do not roll back like an SQL transaction.

If each event has an operation ID and requires deduplication, design idempotency first, then split into small checkpointed chunks. If all scores can **be replaced by absolute versioned values**, a conditional `ZADD` strategy may be safer to retry—while still guarding against out-of-order batches overwriting newer versions with older ones.

Do not pick pipeline size purely from user count; measure ZSet command cost, hot-key pressure, and memory.

## 39. Pragmatic Batch Sizing Strategy

An implementation workflow:

1. **Clarify semantics:** pipeline, multi-key, Streams, SCAN, or Lua? Is atomicity required?
2. **Define SLOs:** end-to-end p95/p99, minimum throughput, memory limit.
3. **Measure B=1 baseline** on a production-equivalent workload.
4. **Estimate payload size distribution**, especially p95/p99 bytes/item.
5. **Start with low caps** on max items and max bytes.
6. **Set max wait time** if cross-request batching is used.
7. **Set max in-flight and queue capacity** so memory has a deterministic ceiling.
8. **Benchmark multiple values of B**, not one "rule of thumb."
9. **Measure p99 and peak memory** under heavy load, not just averages.
10. **Verify correctness and partial failures** under timeouts and Redis restarts/failovers.
11. **Pick the balance point**, rejecting max-throughput batch sizes that violate SLOs.
12. **Monitor and adjust** as command mix, payload distribution, or traffic shifts.

If workloads swing dramatically by hour, **adaptive batching** based on queue depth/latency and memory pressure can be considered. However, adaptive controllers need upper/lower bounds and stability testing; a controller that enlarges batches when throughput drops can worsen congestion.

## 40. Pre-Production Batching Checklist

- [ ] Every batch has a clearly defined unit (commands, bytes, records, key count).
- [ ] Atomicity semantics are understood; pipelining is never used as a transaction substitute.
- [ ] Limits exist for max items, serialized bytes, max wait, and max in-flight.
- [ ] Oversized items and queue backpressure are handled explicitly.
- [ ] Budgets cover JVM heap, reply lists, network buffers, and Redis client buffers.
- [ ] Replies map accurately back to inputs; cache misses and errors are handled.
- [ ] Pipelines/chunks have clear partial-failure and retry policies.
- [ ] Side effects like `INCR`/`XADD`/`ZINCRBY` have idempotency where needed.
- [ ] On Redis Cluster, multi-key commands and Lua obey hash-slot rules.
- [ ] When using `SCAN`, `COUNT` is treated as a hint and cursors are not treated as snapshots.
- [ ] When using Streams, ACK throughput, PEL, and recovery are measured—not just poll rate.
- [ ] Histograms capture p50/p95/p99 from batch queue entry to completion.
- [ ] Metrics track bytes/batch, batch fill ratio, queue wait, retries, and peak memory.
- [ ] Benchmarks use production-equivalent data, serializers, network, and topology.
- [ ] Bulk jobs cannot push interactive traffic past SLOs.
- [ ] Configuration rollback thresholds exist if p99 or memory breaches limits.

## 41. Self-Check Questions

**1. Why can pipelining 1,000 SETs be faster than 1,000 sequential SETs?**  
Because it removes per-command round-trip wait time, though total command work, network bytes, and buffer memory remain.

**2. Why can a large batch increase p99 even while improving throughput?**  
Because batch formation delay, queueing, reply deserialization, head-of-line blocking, and GC pauses can all grow.

**3. Does `executePipelined` make a group of SETs atomic?**  
No. It is an I/O optimization with no implicit transaction or rollback.

**4. Why can two batches of 100 GETs use vastly different memory?**  
Value/reply sizes differ; command count alone cannot predict byte volume.

**5. What limits are needed beyond maxBatchSize?**  
Max bytes, max wait time, max in-flight batches, and bounded queues/backpressure.

**6. Does `SCAN COUNT 100` guarantee exactly 100 keys per step?**  
No. `COUNT` is a hint; each iteration can return more or fewer than 100, including 0.

**7. Does Stream listener `batchSize=100` cap the PEL at 100 messages?**  
No. The PEL can grow whenever delivered messages are not ACKed.

**8. Why must latency be measured from batch queue entry?**  
Measuring only Redis execution misses formation wait, which can be the largest delay.

**9. Does `MGET` automatically work across all multi-slot keys in Redis Cluster?**  
Do not assume so. Multi-key slot constraints and driver behavior must be verified/tested.

**10. If a `ZINCRBY` ran before the client timed out, is retrying guaranteed safe?**  
No. Retrying without idempotency can add the delta twice.

**11. How can a huge Lua script affect unrelated requests?**  
While Redis executes the script, other client commands wait; node p99 can spike.

**12. Why can chunked MGET still consume huge memory?**  
If the application collects every chunk's results into one large List, peak memory still scales with total output.

**13. Does a Redis CPU-bound workload always benefit from larger batches?**  
No. Cutting network overhead does not remove a CPU bottleneck; queueing can worsen.

**14. What does Little's Law help explain?**  
At constant throughput, when time in the system increases, waiting/in-flight items increase too, driving up buffer demand.

**15. Should you pick the batch size with the highest throughput or the one meeting overall SLOs?**  
Pick the configuration delivering needed throughput **within p99, memory, error budget, and correctness limits**.

## 42. Conclusion

**Batching is not an end in itself; it trades network round-trip cost for buffering and wait time.** In Spring Data Redis, larger groups can raise throughput when RTT is the bottleneck, yet can push memory, GC, queue wait, and p99 past budget.

To choose wisely:

- Keep clear distinctions: **pipeline ≠ transaction**, `SCAN COUNT ≠ fixed page size`, `Streams COUNT ≠ ACK guarantee`.
- Track **both item count and total bytes**, not command count alone.
- Measure **end-to-end latency**, including batch formation wait.
- Bound **in-flight batches** and queues rather than letting backlogs grow unchecked.
- Verify **partial failures, idempotency, and Redis Cluster constraints**.
- Scale batch sizes using real measurements and stop at the SLO sweet spot—not the maximum Redis will tolerate.

The right decision question is: **"If we increase items per batch 5x, how much does throughput rise, how much does p99 rise, how many in-flight bytes increase, and how will we recover if a batch fails?"** A sound performance decision answers all four.

## References

- [Spring Data Redis — Pipelining](https://docs.spring.io/spring-data/redis/reference/redis/pipelining.html): `executePipelined`, callbacks, and return values.
- [Spring Data Redis — RedisTemplate](https://docs.spring.io/spring-data/redis/reference/redis/template.html): Redis operations and serializers.
- [Spring Data Redis — Transactions](https://docs.spring.io/spring-data/redis/reference/redis/transactions.html): `MULTI`/`EXEC`, `SessionCallback`, and Redis transactions.
- [Spring Data Redis — Redis Streams](https://docs.spring.io/spring-data/redis/reference/redis/redis-streams.html): `COUNT`, listener containers, ACK, and pending entries.
- [Spring Data Redis — Reactive Redis](https://docs.spring.io/spring-data/redis/reference/redis/reactive.html): reactive APIs and publishers.
- [Redis — Pipelining](https://redis.io/docs/latest/develop/using-commands/pipelining/): round-trip optimization and resource limits.
- [Redis — Transactions](https://redis.io/docs/latest/develop/using-commands/transactions/): transaction semantics and lack of runtime error rollback.
- [Redis — SCAN](https://redis.io/docs/latest/commands/scan/): cursor, COUNT hint, and keyspace mutations.
- [Redis — MGET](https://redis.io/docs/latest/commands/mget/): returning values in key order.
- [Redis — XREADGROUP](https://redis.io/docs/latest/commands/xreadgroup/): COUNT, consumer groups, and pending messages.
- [Redis — Scripting](https://redis.io/docs/latest/develop/programmability/eval-intro/): Lua atomicity and script limitations.
- [Redis — Cluster Specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/): hash slots, multi-key constraints, and failover.
- [Redis — Key Eviction](https://redis.io/docs/latest/develop/reference/eviction/): memory limits, TTL, and eviction.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): `Flux`, batching, concurrency, and backpressure.
