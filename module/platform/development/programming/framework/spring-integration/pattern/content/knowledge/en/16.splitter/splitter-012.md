# Distinguishing Splitter from Chunking

## 1. The Problem: How Should a 1,250-Line Batch Be Divided?

A system receives one message containing **1,250 order lines** requiring inventory checks, shipping calculation, and persistence. The team proposes two approaches:

- **Approach A:** split the message into 1,250 messages, each carrying **one order line** for independent processing.
- **Approach B:** partition the list into **chunks of at most 100 lines**, sending 13 messages sequentially, each carrying a group of lines.

Both are described as "breaking things down," yet the **unit of work**, **message count**, **retry/transaction boundaries**, **result aggregation**, and **concurrency** differ fundamentally.

In Enterprise Integration Patterns (EIP), **Splitter** is the pattern converting **one composite message** into **multiple child messages**. **Chunking** is a strategy that **divides data into blocks bounded by size, count, or time** to control memory, load, I/O, or transactions. A system can use **Splitter to emit chunks**, or **split item by item without chunking**. Therefore, they are **not mutually exclusive patterns**.

This lesson belongs to the **Splitter** chapter of the **SPRING_INTEGRATION_PATTERN** module. The module focuses on implementing Enterprise Integration Patterns with Spring Integration to build loosely coupled, extensible message flows, practicing **Router, Filter, Transformer, Splitter, Aggregator, Gateway, retry, error channel, and correlation**, while testing and monitoring processing branches.

**After this lesson, you will be able to:** distinguish Splitter from chunking and Spring Batch chunk-oriented processing; write flows splitting by item or by chunk; compute message boundaries, correlation, and group sizes; decide when to use Aggregator, queues, or brokers; handle empty batches, partial failures, duplicates, and load testing.

## 2. Two Concepts Seen Through Two Different Questions

**Splitter asks:** "Into which child messages can one message representing multiple entities be decomposed?"

**Chunking asks:** "How much data is optimal to read, process, transmit, or commit at once?"

| Aspect | Splitter (EIP) | Chunking |
|---|---|---|
| Goal | Turn one composite message into a stream of child messages | Bound data volume within one unit of work |
| Output unit | **Message** (payload + headers) | **Chunk** (group of items; may or may not become a message) |
| Items per output | May be one item or a group | Typically multiple items, capped by a limit |
| Architectural role | Messaging endpoint/pattern | Partitioning algorithm, I/O/batching/transaction strategy |
| Common metadata | `correlationId`, `sequenceNumber`, `sequenceSize` | `batchId`, `chunkIndex`, `startOffset`, `itemCount` |
| Transaction guarantees | Does not create transactions for every item | System-dependent; **Spring Batch chunk step** defines commit boundaries |
| Typical tools | Spring Integration `@Splitter`, Java DSL `split()` | Java loops, stream partitioning, Spring Batch, custom Transformer + Splitter |
| Recombining results | Often paired with Aggregator | Depends on whether chunks/items must be merged |
| Typical scenario | Handling each `OrderLine` independently | Writing 100 DB rows/batch or calling API with 100 items/request |

**Key takeaway:** Splitter defines **how messages are emitted**, while chunking defines **work unit size**. A Splitter can emit messages containing 100-item lists; in doing so it distributes **chunks**, yet each chunk message still carries **100 items** rather than spawning 100 child messages.

## 3. Two Diagrams for the Same Shipment

### Splitter Emitting One Message per Line

~~~mermaid
flowchart LR
    IN["OrderBatch (1,250 lines)"] --> SPLIT{"Splitter"}
    SPLIT --> A["Message: line 1"]
    SPLIT --> B["Message: line 2"]
    SPLIT --> C["..."]
    SPLIT --> D["Message: line 1,250"]
    A --> W["Line processors"]
    B --> W
    C --> W
    D --> W
~~~

One parent message breaks into **1,250 child messages**. Downstream can process, retry, or route each item by `sku` or `warehouse`. To assemble a single order result, design **correlation and a release strategy**.

### Partitioning into Chunks, Then Emitting One Message per Chunk

~~~mermaid
flowchart LR
    IN["OrderBatch (1,250 lines)"] --> PART["Chunker: max 100 lines per chunk"]
    PART --> SPLIT{"Splitter"}
    SPLIT --> A["Chunk 0: lines 1–100"]
    SPLIT --> B["Chunk 1: lines 101–200"]
    SPLIT --> C["..."]
    SPLIT --> D["Chunk 12: lines 1,201–1,250"]
    A --> W["Batch processors"]
    B --> W
    C --> W
    D --> W
~~~

After chunking there are **13 data groups**; after Splitter there are **13 messages**, not 1,250. A worker can send each chunk as **one bulk API call**, one DB batch write, or iterate through items inside the chunk itself.

**Never assume "fewer messages" always equals "faster."** Bulk APIs can be more efficient, yet a large failing chunk often forces retrying many items unless per-item error reporting exists. The decision depends on consumer capability, item independence, and atomicity requirements.

## 4. Calculating Chunk Size and Count

For `N` items partitioned with maximum size `K > 0`:

\[
\text{chunkCount} =
\left\lceil \frac{N}{K} \right\rceil
\]

For example, `N = 1,250` and `K = 100`:

- The first 12 chunks hold 100 items each.
- The final chunk holds 50 items.
- Total: **13 chunks**.

Never use integer division `N / K` and drop the remainder; doing so drops the final chunk.

| N items | K max/chunk | Chunk Count | Final Chunk Size |
|---:|---:|---:|---:|
| 0 | 100 | 0 | None |
| 1 | 100 | 1 | 1 |
| 100 | 100 | 1 | 100 |
| 101 | 100 | 2 | 1 |
| 1,250 | 100 | 13 | 50 |
| 1,250 | 500 | 3 | 250 |

**Chunk size** is not **thread count**, **partition count**, or **`sequenceSize`** of a Splitter in every topology. If your list is partitioned into 13 chunks and each chunk is later split into 100 items, **two levels of division** exist with distinct correlation semantics.

## 5. Data Model for the Java Examples

We use Java 17+ to model a batch and its order lines:

~~~java
record OrderLine(
    String lineId,
    String sku,
    int quantity
) {}

record OrderBatch(
    String batchId,
    List<OrderLine> lines
) {}

record LineChunk(
    String batchId,
    int chunkIndex,          // 0-based
    int expectedChunks,
    List<OrderLine> lines
) {}
~~~

Invariants to validate **before Splitter**:

- `batchId` must be present and stable across retries/replays.
- `lines` must not be `null`; if empty, define an explicit completion policy.
- Each `lineId` must be stable and unique within the batch when domain rules require.
- `quantity`, `sku`, and related fields must meet contract rules; validate upfront or per item depending on requirements.
- `chunkIndex` identifies the data group's position, **not** proof that the chunk succeeded.

In production, if the list is huge, holding the entire batch's `List<OrderLine>` in RAM becomes a memory issue. Later sections clearly separate **splitting an in-RAM list** from **reading pages/chunks incrementally from external sources**.

## 6. Standard Splitter: One Message per Item

Spring Integration provides `@Splitter` on a method returning a collection/iterable of elements. Example:

~~~java
@MessageEndpoint
class OrderLineSplitter {

    @Splitter(
        inputChannel = "orders.batches",
        outputChannel = "orders.lines")
    public List<OrderLine> split(OrderBatch batch) {
        if (batch == null || batch.lines() == null) {
            throw new IllegalArgumentException("MISSING_LINES");
        }
        return batch.lines();
    }
}
~~~

The inbound message carries `OrderBatch`; outputs carry `OrderLine`. Spring Integration can attach sequence/correlation headers to child messages; exact behavior depends on Splitter type, `applySequence` configuration, and whether total element count is known.

**What Splitter does not do on its own:**

1. Does not dispatch each item to a separate process or run in parallel automatically.
2. Does not commit a separate transaction for each child message.
3. Does not aggregate results back into an `OrderResult` automatically.
4. Does not guarantee exactly-once processing on broker redeliveries.
5. Does not turn a massive materialized in-RAM list into durable streaming.

If the output channel is `DirectChannel`, downstream runs synchronously on the upstream thread; 1,250 dispatches can tie up the sending thread for a long time. With `ExecutorChannel`, queues, or brokers, those components govern concurrency and backpressure.

## 7. Java DSL: Splitting Individual OrderLines

You can write the same flow with Java DSL instead of `@Splitter`:

~~~java
@Configuration
@EnableIntegration
class PerLineFlow {

    @Bean
    IntegrationFlow splitIntoLines() {
        return IntegrationFlow.from("orders.batches")
            .split(OrderBatch.class, OrderBatch::lines)
            .channel("orders.lines")
            .get();
    }
}
~~~

This is an **alternative** to section 6's annotation; do not register both consuming `orders.batches` unless intentionally building a multi-subscriber topology. In practice, wire a real consumer to `orders.lines`, such as a handler applying business rules by `lineId`.

What the `orders.lines` handler receives:

~~~text
Message 1: payload = OrderLine(L-1, SKU-A, 2)
Message 2: payload = OrderLine(L-2, SKU-B, 1)
Message 3: payload = OrderLine(L-3, SKU-C, 5)
...
~~~

To retain `batchId` on every item after splitting, **never rely solely on inferring backwards from `OrderLine`**. Use an application-managed header or define `OrderLineWork(batchId,lineId,...)` as the child payload. Stable business metadata benefits replays, error handling, and idempotency.

## 8. Pure Java Chunker: Partitioning a List Before Emitting Messages

Chunking does not have to be a separate EIP component. We can write a **pure, I/O-free** partitioning function:

~~~java
final class OrderChunker {

    List<LineChunk> partition(OrderBatch batch, int chunkSize) {
        if (batch == null || batch.batchId() == null
                || batch.batchId().isBlank()
                || batch.lines() == null) {
            throw new IllegalArgumentException("INVALID_BATCH");
        }
        if (chunkSize <= 0 || chunkSize > 1_000) {
            throw new IllegalArgumentException("INVALID_CHUNK_SIZE");
        }
        List<OrderLine> lines = batch.lines();
        if (lines.isEmpty()) {
            return List.of();
        }

        int expectedChunks =
            1 + (lines.size() - 1) / chunkSize;
        List<LineChunk> chunks = new ArrayList<>(expectedChunks);

        for (int start = 0, chunkIndex = 0;
             start < lines.size();
             chunkIndex++) {
            int end = start + Math.min(
                chunkSize, lines.size() - start);
            chunks.add(new LineChunk(
                batch.batchId(),
                chunkIndex,
                expectedChunks,
                List.copyOf(lines.subList(start, end))));
            start = end;
        }
        return List.copyOf(chunks);
    }
}
~~~

Code notes:

- `chunkSize <= 0` must be rejected; never let the loop stall or divide by zero.
- Uses `1 + (size - 1)/chunkSize` on non-empty lists to compute chunk count without floating-point math.
- `end` never exceeds `lines.size()`; the final chunk may be smaller than `chunkSize`.
- `List.copyOf` snapshots **element references**; if item objects themselves are mutable, it does not deep-clone them.
- `chunkIndex` and `expectedChunks` live in the **payload** so they survive transports where Spring headers get stripped or altered.

This chunker targets **lists already in RAM**. It returns the full list of chunks, adding overhead proportional to items/chunks. It does **not** make unbounded inputs feasible. For millions of rows, use paging, managed cursors/iterators, and bounded pipelines.

## 9. Java DSL: Transformer Builds Chunks, Splitter Emits Each Chunk

To send **13 chunk messages** instead of 1,250 line messages, combine **Transformer + Splitter**:

~~~java
@Configuration
@EnableIntegration
class ChunkedOrderFlow {

    @Bean
    OrderChunker orderChunker() {
        return new OrderChunker();
    }

    @Bean
    IntegrationFlow splitIntoChunks(OrderChunker chunker) {
        return IntegrationFlow.from("orders.batches")
            .transform(OrderBatch.class,
                batch -> chunker.partition(batch, 100))
            .split()
            .channel("orders.chunks")
            .get();
    }
}
~~~

This is a **different** topology from section 7's per-item flow. The Transformer converts `OrderBatch` into `List<LineChunk>`. The Splitter then emits **one message per `LineChunk`**.

At the `orders.chunks` consumer, each message carries one **group**:

~~~java
@MessageEndpoint
class ChunkConsumer {

    private final BulkLineService bulkLineService;

    ChunkConsumer(BulkLineService bulkLineService) {
        this.bulkLineService = bulkLineService;
    }

    @ServiceActivator(inputChannel = "orders.chunks")
    public void handle(LineChunk chunk) {
        bulkLineService.process(
            chunk.batchId(),
            chunk.chunkIndex(),
            chunk.lines());
    }
}
~~~

`BulkLineService` is an application abstraction, not a built-in Spring Integration class; provide an appropriate bean. If it calls a bulk API or writes chunks to a database, configure **transactions/acks/retries** at that boundary.

**Caution:** the `void` handler above is a **terminal consumer** that emits no `ChunkResult`. If a Gateway needs a summary for the entire batch, emit a **result message** per chunk into a suitable Aggregator; you cannot attach an Aggregator after a `void` handler and expect data to gather.

## 10. Chunking Is More Than "Evenly Slicing a List"

Beyond fixed-item-count chunking, multiple strategies exist:

| Chunk Type | Emission Trigger | Use Case |
|---|---|---|
| **Count-based** | Reaches 100 items | Bulk insert 100 records |
| **Byte-size-based** | Total size ~1 MiB without exceeding limit | APIs/brokers with request-size caps |
| **Time-window** | Accumulate for 2 seconds or until count met | Telemetry and micro-batching |
| **Key-based** | Group by `tenantId`/`warehouseId` before slicing | Avoid mixing domains or permissions |
| **Offset/page-based** | 500 records per DB page | High-volume exports/imports |
| **Transactional** | Items per commit in a step | Spring Batch chunk-oriented processing |

A **byte-based** chunk cannot be sized from `List.size()` alone: per-item payload sizes vary, requiring serialized measurement plus header/protocol overhead. A **time-based** chunk may be empty or smaller than the limit when its window closes.

**Never confuse a "chunk" with a broker "partition."** A partition is typically a log/broker distribution and ordering unit, whereas a chunk groups items for one execution unit. A partition can carry countless chunks over time; a chunk can also be routed to a partition by key.

## 11. How Splitter Differs from Batching and Aggregator

A common confusion: **splitter** and **batching** both deal with multiple items, tempting people to treat them as identical. In fact, they can move data in opposite directions:

~~~mermaid
flowchart LR
    B["One batch message"] --> S["Splitter"]
    S --> M1["Item message 1"]
    S --> M2["Item message 2"]
    S --> MN["Item message N"]
    M1 --> A["Aggregator / batching"]
    M2 --> A
    MN --> A
    A --> R["One result/group message"]
~~~

- **Splitter**: one composite message into many messages.
- **Aggregator**: many messages into one group/reply via correlation + release strategy.
- **Batcher/chunker**: creates bounded data groups for efficient processing/writing/sending; can use an Aggregator when **collecting messages arriving over time**, or a partitioning function when **a `List` already exists**.
- **Resequencer**: orders messages by sequence when ordering is needed; not synonymous with a chunker.

If the inbound source is **one message containing 1,250 items**, chunker + Splitter fits. If the inbound source is **1,250 independent messages arriving from a broker**, consider an **Aggregator releasing by count/time** to form chunks; do not build one huge batch message just to split it back into chunks.

The dividing line is **the initial data boundary**: whether data already sits inside one composite message or arrives as discrete messages.

## 12. Spring Batch Chunk-Oriented Processing Is a Distinct Concept

**Spring Batch** provides **chunk-oriented processing**: reading items via `ItemReader`, transforming via `ItemProcessor`, collecting a chunk of items, writing via `ItemWriter`, and committing the transaction per step config.

~~~mermaid
flowchart LR
    R["ItemReader"] --> P["ItemProcessor"]
    P --> C["Chunk: up to 100 items"]
    C --> W["ItemWriter"]
    W --> COMMIT["Commit transaction"]
    COMMIT -.->|"Continue"| R
~~~

Conceptual example using a Spring Batch version supporting `StepBuilder` and a chunk transaction manager:

~~~java
@Bean
Step importLines(JobRepository jobRepository,
                 PlatformTransactionManager tx,
                 ItemReader<OrderLine> reader,
                 ItemProcessor<OrderLine, OrderLine> processor,
                 ItemWriter<OrderLine> writer) {
    return new StepBuilder("importLines", jobRepository)
        .<OrderLine, OrderLine>chunk(100, tx)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
~~~

This is a **Spring Batch** example, not `IntegrationFlow.split()` syntax. `JobRepository`, transaction manager, reader, processor, and writer must be wired to run. Here, **chunk size ties directly to the step's commit interval**; Spring Batch handles retries, skips, and restarts/checkpoints with its own policies.

Quick comparison:

| Requirement | Spring Integration Splitter | Spring Batch Chunk Step |
|---|---|---|
| Receive a message and fan out across handlers/channels | Ideal | Not its primary purpose |
| Split a `List` payload into individual messages | Ideal | Not default behavior |
| Bulk read-process-write with transactions and restarts | Must build yourself | Core use case |
| Asynchronous event workflows, routers, and brokers | Natural fit in Spring Integration | Can integrate, yet different abstraction |
| Commit DB every 100 items per step | Not built in | Configured via chunk-oriented step |

**A Splitter emitting 100 messages does not mean Spring Batch commits every 100 messages.** Conversely, Spring Batch processing a 100-item chunk does not mean 100 EIP messages were emitted.

## 13. Splitter Correlation and Sequence Headers

In Spring Integration, Splitters often attach metadata so child messages can be **recombined**. Key headers:

| Header | Meaning | Note |
|---|---|---|
| `correlationId` | Identifies messages sharing the same source/scope | Do not casually reuse as business batch ID |
| `sequenceNumber` | Child message's position in sequence | Does not dictate completion time |
| `sequenceSize` | Expected total elements, **when known** | Iterators/streams may not know count upfront |
| `MessageHeaders.ID` | Specific message's ID | May change on reply/redelivery |
| `batchId` (custom) | Stable business key for the batch | Used for idempotency/tracing |
| `chunkIndex` (custom) | Chunk position within the batch | Used for per-chunk replay/checkpoints |

`applySequence` controls sequence metadata attachment. With sized collections, Splitter usually has enough info to set sequence size; with unknown-length iterators/streams, **never assume the Aggregator receives a positive, accurate sequence size** across all configs/versions.

**Never use `sequenceNumber` as a durable business `lineId`.** If a producer adds/removes an item or reorders the List on retry, positions shift. A dedicated `lineId` preserves stable identity across replays.

Conceptual example:

~~~text
Original: OrderBatch(batchId=B-101, lines=[L1,L2,L3])

Child 1: payload=L1, sequenceNumber=1, sequenceSize=3
Child 2: payload=L2, sequenceNumber=2, sequenceSize=3
Child 3: payload=L3, sequenceNumber=3, sequenceSize=3

Group linked by the split invocation's correlationId.
~~~

This illustrates metadata when sequencing is enabled and count is known upfront; **do not hard-code** exact correlation ID generation formats across all splitter types.

## 14. Two-Level Split: Chunk First, Item Second

A pipeline may need **chunks for distribution**, then **per-item splits for parallel worker execution**:

~~~mermaid
flowchart TD
    O["Batch B-101: 1,250 lines"] --> C["Chunker: 13 chunks"]
    C --> S1{"Chunk-level Splitter"}
    S1 --> C0["Chunk 0: 100 lines"]
    S1 --> C1["Chunk 1: 100 lines"]
    S1 --> C12["Chunk 12: 50 lines"]
    C0 --> S2["Item-level Splitter"]
    C1 --> S2
    C12 --> S2
    S2 --> ITEM["Line work + handler"]
    ITEM --> G["Chunk-level result / batch-level result"]
~~~

At least **two relationships** exist here:

1. `batchId` links all chunks of a batch.
2. `chunkIndex` + `lineId` links items to their chunk for retries and aggregation.

If the nested Splitter generates fresh `correlationId`/`sequenceNumber`/`sequenceSize`, standard headers may reflect **only the innermost split** or change depending on header-handling rules. **Never rely on a single flat trio of sequence headers to represent both levels** without testing your exact topology.

When two Aggregator tiers are needed, design an explicit contract:

~~~text
LineResult(batchId, chunkIndex, lineId, outcome)
      ↓
ChunkResult(batchId, chunkIndex, itemsProcessed, outcome)
      ↓
BatchResult(batchId, chunksProcessed, overallOutcome)
~~~

These fields provide **business correlation**; Spring Integration headers remain useful for in-JVM endpoints. Especially across brokers, payload IDs restore group meaning if header mappers drop sequence metadata.

## 15. Streaming, Iterators, and Memory Limits

For huge item counts, `List<OrderLine> lines` above can exhaust memory **even before Splitter begins**.

Comparison:

| Option | Memory on Message-Producing Side | Risk |
|---|---|---|
| Materialize 1M items into a List, then split | Very high | OOM, GC pauses |
| Page DB in 500-item slices and emit chunks | Bounded by page/queue | Needs cursor, snapshot, and retry management |
| Splitter-supported Iterator/Stream | Lazy under right conditions | Resource closing, unknown size, backpressure |
| Bounded queue/broker between producer and workers | Bounds in-flight work | Rejections, timeouts, redeliveries |

**`Iterable`/`Iterator`/`Stream` does not equal durable streaming.** An Iterator may hold open DB cursors, file handles, or transactions; slow consumers keep those resources open. Specify resource ownership, connection lifetimes, and failure recovery.

A safer pattern for large exports:

~~~text
DB page 1 (500 records)
    → validate → chunk/split → bounded channel → workers
DB page 2 (500 records)
    → read next only when capacity allows
...
checkpoint = last committed page/key
~~~

Capping page size does not bound memory on its own if a producer keeps reading pages into an unbounded internal queue. Bound **both the read source and queued in-flight messages**.

## 16. Throughput and Backpressure: Why Chunk Size Must Be Measured

Let:

- `L`: items to process.
- `K`: max items per chunk.
- `H`: fixed overhead per message/API call.
- `C`: processing cost per item.

A simplified model ignoring concurrency and other overheads:

\[
T(K) \approx
\left\lceil \frac{L}{K} \right\rceil H + L C
\]

As `K` grows, paying overhead `H` happens fewer times. Yet gains can be erased by **huge payloads, serialization cost, timeouts, contention, whole-chunk retries on single failures**, or API/broker limits.

**Qualitative example:**

- Sending 1,250 single requests to a bulk-friendly API incurs excessive round-trips.
- Sending 13 requests of 100 items cuts call count, yet one failure affects 100 items.
- Sending one 1,250-item request may blow size limits or timeouts despite minimal call overhead.

**Backpressure** must materialize via bounded queues, rejections, poll/receive rates, or ingress throttling. A Splitter can emit child messages far faster than downstream drains them, even at very low inbound message rates.

When choosing chunk size, measure p95/p99 latency, payload bytes, queue depth, error rate, retry amplification, memory/GC, and throughput **per item**, not only per message.

## 17. Processing Order: Split Order Differs from Completion Order

With an ordered `List`, Splitter emits messages in element order. Yet across executors/brokers/parallel consumers, **completion order is not guaranteed**:

~~~text
Emitted:     line-1 → line-2 → line-3
Completed:   line-2 → line-3 → line-1
~~~

The same holds for chunks:

~~~text
Emitted:     chunk-0 → chunk-1 → chunk-2
Completed:   chunk-1 → chunk-0 → chunk-2
~~~

If business rules demand sequential updates per SKU or account:

- Partition by an appropriate key so the same entity runs on one sequential lane.
- Attach business versions/sequences to reject stale updates.
- Use a Resequencer or coordinator if output order truly must be restored.
- Never rely on Splitter's `sequenceNumber` to enforce transaction commit order.

**Chunk index is not commit order.** If chunk 4 succeeds while chunk 3 is still retrying, checkpoints must track gaps/partial completion instead of taking the highest index and assuming earlier chunks finished.

## 18. How Single-Item Errors and Chunk Errors Differ

Suppose a 100-line chunk has only line 37 with a nonexistent `sku`:

| Design | Default Failure Blast Radius | Decision Needed |
|---|---|---|
| Split one message per item | One line fails; other lines can proceed | Item retry, line rejection, group completion |
| Chunk into 100-item messages | Bulk consumer call may fail the whole chunk | Retry whole chunk or isolate per-item errors |
| Spring Batch chunk step with transactions | Rolls back chunk per step transaction/policy | Retry/skip/rollback and commit interval |
| Split then Aggregator | One child fails to produce a result | Group timeout, partial release, or failure result |

**Never equate "chunk sent" with "all 100 items succeeded."** A bulk service may return mixed outcomes:

~~~json
{
  "batchId": "B-101",
  "chunkIndex": 2,
  "processed": 100,
  "succeeded": 98,
  "failed": [
    {"lineId": "L-237", "reasonCode": "UNKNOWN_SKU"},
    {"lineId": "L-286", "reasonCode": "OUT_OF_STOCK"}
  ]
}
~~~

Your design must choose one semantic:

1. **All-or-nothing chunk:** one item error fails and rolls back the whole chunk when side effects share one transaction.
2. **Partial success:** worker returns per-item outcomes; retry only eligible failed items.
3. **Dead-letter/quarantine:** route unprocessable items or chunks for investigation with reason codes.
4. **Compensation:** when non-rollbackable side effects occurred, run compensating actions.

Never retry permanent validation errors endlessly; the same invalid SKU will keep failing regardless of chunk size.

## 19. Retries, Idempotency, and Duplication Risk

Message brokers typically support **at-least-once** delivery; unacknowledged messages can be redelivered. Splitter itself **does not make the flow exactly-once**.

A chunk that wrote 70/100 rows before failing may be redelivered. If the worker reprocesses the whole chunk:

~~~text
Attempt 1: chunk-02 → 70 lines applied side effects, 30 incomplete
Attempt 2: chunk-02 → reads from the start again
Risk: first 70 lines written or billed twice
~~~

When designing idempotency:

- Batch/chunk keys **identify the work unit**, yet may not suffice when bulk APIs allow partial success.
- Keys by `(batchId, lineId, operation)` usually protect per-line side effects better.
- When retrying an entire chunk, each line handler must know whether it already succeeded.
- Never use `MessageHeaders.ID` as the sole idempotency key: redeliveries can mint new message IDs.
- With DB + broker, consider transactions/outbox/inbox and durable processing state.

When retrying the same batch after **editing contents**, distinguish **`batchRevision`/`version`**. If `batchId` stays the same while the item list changes, `chunkIndex=2` may hold different items than before. Define explicit semantics: immutable batches, or `batchVersion`/manifest hashes for replayability.

## 20. Under What Conditions Does Aggregator Combine Results?

After a Splitter, an Aggregator needs both a correlation key and a rule for **when enough results arrived to release**.

~~~mermaid
flowchart LR
    S["Splitter → N children"] --> W["Workers"]
    W --> RES["N results"]
    RES --> AG{"Aggregator"}
    AG --> OUT["BatchResult"]
~~~

One option is relying on Splitter sequence metadata when element count is known and **every child produces exactly one result**. Yet real flows introduce:

- A child discarded by a Filter, producing no result.
- A `void` handler causing side effects without replying.
- Iterators/streams leaving `sequenceSize` unknown upfront.
- Retried children producing duplicate results.
- Children returning failure outcomes that are **conclusive**, shifting the batch to `FAILED`/`PARTIAL`.
- Children arriving after deadlines or post-release.

To guarantee reliable completion, persist a manifest upfront:

~~~text
BatchManifest(
    batchId=B-101,
    expectedChunkIds=[0,1,2,...,12],
    deadline=...,
    version=1
)
~~~

The Aggregator/coordinator reconciles against the manifest for **which chunks produced outcomes**, rather than trusting arrival counts blindly. At high volume, avoid holding huge ID lists in RAM; use persisted counters/bitsets/keyed status rows.

**Do not blindly attach `sequenceSize=13` onto lower-tier items** if items were split out of chunks and follow a different release strategy. Define **two group levels** and distinct metadata for nested splits.

## 21. Empty Batches and `null`: Never Assume Completion

If an `OrderBatch` has `lines=[]`:

- Section 8's chunker returns an empty list, creating zero chunks.
- A Splitter on an empty collection may **emit zero child messages**, depending on endpoint/config.
- A Gateway waiting for a downstream reply may **never receive one**.
- An Aggregator receiving zero messages never magically knows "the batch had 0 items and finished."

If empty batches are valid, emit a **dedicated** terminal outcome such as `BatchResult(batchId, processed=0, status=EMPTY)` before invoking the Splitter. If empty batches violate the contract, reject immediately with `EMPTY_BATCH`.

**`null` is not an empty collection.** `lines=null` may indicate a malformed payload or missing deserialized field. Never coerce `null` to an empty list and report success without an approved rule.

With time-window chunking, empty windows may be skipped or emit tick/empty-window messages per monitoring requirements. Do not assume the two semantics are equivalent.

## 22. Correlation and Header Propagation Across Brokers

When Splitter outputs cross Kafka/AMQP/HTTP:

1. **Header mappers** govern which Spring metadata converts into native headers.
2. `correlationId`/sequence headers may change type, rename, or drop.
3. `replyChannel`/`errorChannel` may be in-JVM objects that cannot serialize as remote addresses.
4. Out-of-process consumers do not automatically share the origin process's `GroupStore`/sequence state.
5. Brokers have their own ack, redelivery, partitioning/ordering, and payload-size limits.

A wire contract for chunks should carry explicit application fields:

~~~json
{
  "batchId": "B-101",
  "batchVersion": 1,
  "chunkIndex": 2,
  "expectedChunks": 13,
  "lines": [
    {"lineId": "L-201", "sku": "SKU-01", "quantity": 1},
    {"lineId": "L-202", "sku": "SKU-02", "quantity": 2}
  ]
}
~~~

This is a compact chunk example; `expectedChunks` comes from the locked batch manifest, not from counting whatever messages arrived at a consumer. If a producer changes chunk size mid-batch without versioning, indices and expected counts collide. Designs must enforce **immutable batches or revisions**.

Never equate `message sent to broker` with `business item committed`; track matching metrics/statuses/acks.

## 23. Unit Tests: Proving Chunker Neither Drops Nor Duplicates Items

A pure Java unit test for `OrderChunker`:

~~~java
@Test
void partitions1250ItemsInto13ChunksWithoutLoss() {
    List<OrderLine> lines = IntStream.rangeClosed(1, 1_250)
        .mapToObj(i -> new OrderLine(
            "L-" + i, "SKU-" + i, 1))
        .toList();

    List<LineChunk> chunks = new OrderChunker()
        .partition(new OrderBatch("B-101", lines), 100);

    assertEquals(13, chunks.size());
    assertEquals(100, chunks.get(0).lines().size());
    assertEquals(50, chunks.get(12).lines().size());
    assertEquals(13, chunks.get(12).expectedChunks());
    assertEquals(12, chunks.get(12).chunkIndex());

    List<String> allIds = chunks.stream()
        .flatMap(chunk -> chunk.lines().stream())
        .map(OrderLine::lineId)
        .toList();

    assertEquals(1_250, allIds.size());
    assertEquals(1_250, new HashSet<>(allIds).size());
    assertEquals(lines.stream().map(OrderLine::lineId).toList(), allIds);
}

@Test
void rejectsZeroChunkSize() {
    OrderBatch batch = new OrderBatch(
        "B-102", List.of(new OrderLine("L-1", "SKU-A", 1)));

    assertThrows(IllegalArgumentException.class,
        () -> new OrderChunker().partition(batch, 0));
}

@Test
void treatsEmptyBatchExplicitly() {
    List<LineChunk> chunks = new OrderChunker()
        .partition(new OrderBatch("B-EMPTY", List.of()), 100);
    assertTrue(chunks.isEmpty());
}
~~~

These tests use JUnit 5 and Java Streams (imports omitted). Unit tests verify exact chunk sizing, ordering, and zero missing/duplicate `lineId` values on unique inputs. They **do not yet** prove Spring Integration emits the exact message count or that brokers never redeliver.

Add property-based tests across many `N` and `K`: total elements across chunks must equal `N`, every chunk is non-empty when `N > 0` and **at most size `K`**, and indices increment contiguously from 0.

## 24. Integration Tests: Actual Message Count Emitted by Splitter

In a Spring test context, replace `orders.chunks` with a test-only `QueueChannel` and send an `OrderBatch` to `ChunkedOrderFlow`; do not concurrently run production consumers on the same channel.

~~~java
@Autowired
ApplicationContext context;

@Test
void sendsOneMessagePerChunk() {
    MessageChannel input = context.getBean(
        "orders.batches", MessageChannel.class);
    PollableChannel output = context.getBean(
        "orders.chunks", PollableChannel.class);

    List<OrderLine> lines = IntStream.rangeClosed(1, 205)
        .mapToObj(i -> new OrderLine(
            "L-" + i, "SKU-" + i, 1))
        .toList();

    assertTrue(input.send(new GenericMessage<>(
        new OrderBatch("B-205", lines))));

    List<LineChunk> received = new ArrayList<>();
    for (int i = 0; i < 3; i++) {
        Message<?> message = output.receive(1_000);
        assertNotNull(message);
        received.add((LineChunk) message.getPayload());
    }

    assertNull(output.receive(0));
    assertEquals(List.of(100, 100, 5),
        received.stream().map(c -> c.lines().size()).toList());
    assertTrue(received.stream()
        .allMatch(c -> c.batchId().equals("B-205")));
}
~~~

If the flow dispatches asynchronously, **receive order may differ from `chunkIndex` order**; sort by `chunkIndex` before comparing sizes, or assert order-independent collections. This example assumes no executor/broker is attached and requests dispatch directly.

### Minimum Integration Test Matrix

| Test | Input / Config | What to Prove |
|---|---|---|
| Per-item split | 205-item batch | **205** `OrderLine` child messages |
| Chunked split | 205-item batch, K=100 | **3** `LineChunk` child messages |
| Smaller final chunk | 205, K=100 | Final chunk contains 5 items |
| Exact boundary | 200, K=100 | Exactly 2 chunks, no empty third chunk |
| Empty batch | 0 items | Terminal outcome or rejection per contract |
| Invalid K | K=0 or negative | Validation error, never hangs |
| Single invalid item | One bad `sku` | Error/partial success per policy |
| Single failing chunk | Bulk service timeout | Retry scope verified, no double side effects |
| Parallel workers | Chunk 2 finishes before chunk 1 | Group still reaches accurate conclusion |
| Correlation | Split → process → Aggregator | Never cross-mixes different batches |
| Duplicate delivery | Chunk 2 redelivered | Idempotency by batch/chunk/line |
| Restart while pending | Broker + durable store | Recovery per designed guarantees |
| Backpressure | Bounded queue and slow workers | Intentional block/reject, no OOM |
| Header mapping | Chunk crosses out-of-JVM transport | Business ID/version remain intact |

## 25. Observing Performance and Processing Progress

Counting messages alone is not enough: **13 chunk messages** and **1,250 item messages** can represent the exact same workload.

| Suggested Metric | What It Reveals |
|---|---|
| `batch.received.count` | Inbound batches |
| `batch.item.count` | Total items requested for processing |
| `split.child.message.count` | Child messages emitted |
| `chunk.size.items` | Distribution of item counts per chunk |
| `chunk.size.bytes` | Serialized payload sizes |
| `chunk.process.duration` | P50/P95/P99 latency per chunk |
| `item.process.duration` | Per-item latency |
| `chunk.retry.count` | Extra load from chunk retries |
| `item.failure.count` by reason | Business data quality |
| `queue.depth` and `queue.oldest.age` | Backlog and backpressure |
| `batch.pending.chunks` | Chunks still awaiting outcomes |
| `batch.completed.count` by outcome | Final outcomes: success/partial/failed |

These are **suggested metrics**, not guaranteed built-ins in Spring Integration. With Micrometer/observation, keep tag cardinality bounded (`flow`, `operation`, `outcome`, `sizeBand`); never put `batchId` or `lineId` into metric tags.

To trace a specific batch, use structured logs/tracing with `batchId`, `batchVersion`, `chunkIndex`, `lineId`, and correlation context while avoiding sensitive payloads. Compare **items processed per second**, not just `messages sent per second`, when benchmarking before/after chunking.

## 26. Hands-On Exercise: Choosing the Right Granularity for 1,250 Lines

Build an **OrderLineImport** application with three variants:

1. **Per-item Splitter:** accept an `OrderBatch` with 1,250 lines and emit 1,250 `OrderLine` messages to `orders.lines`.
2. **Chunked Splitter:** use `OrderChunker.partition(batch,100)` and emit 13 `LineChunk` messages to `orders.chunks`.
3. **Chunk-oriented Spring Batch:** configure a Job/Step reading items and committing every 100 items with a transaction manager, without assuming those steps emit child EIP messages.
4. **Load comparison:** measure elapsed time, queue depth, memory, p95 latency, bulk API call count, and retry count.
5. **Intentional error:** give line 237 an invalid SKU; test per-item rejection, bulk partial success, and chunk rollback.
6. **Retry:** replay the chunk containing line 237 and prove the other 99 lines incur no duplicate side effects.
7. **Correlation:** create `ChunkResult` and `BatchResult`, keep `batchId` stable, and handle a chunk returning no result.
8. **Empty batch:** decide whether to fail or emit `BatchResult(status=EMPTY)` before splitting.
9. **Broker boundary:** send `LineChunk` over Kafka/AMQP with a selective header mapper; verify `batchVersion` and payload limits.
10. **Tune K:** test 10, 100, and 500, weighing overhead savings against retry amplification, payload size, and throughput.

**Completion criteria:** explain why 1,250 item messages differ from 13 chunk messages; verify the final chunk keeps all 50 trailing items; prevent duplicates on retry; design an Aggregator/completion path; measure backpressure; and know when to choose a Spring Batch chunk step instead of adding only a Splitter.

## 27. Common Mistakes

**"Splitter and chunking are two names for the same pattern."** False. Splitter is **message fan-out**; chunking is **bounded data grouping**, which can be combined with Splitter.

**"Setting K=100 makes Splitter commit every 100 messages."** False. Transactions/commit intervals belong to the execution/transaction manager, not Splitter message counts.

**"13 chunk messages mean only 13 items were processed."** False. Each chunk holds many items; measure both message and item counts.

**"Larger chunk sizes are always faster."** Not always. Larger chunks can exceed payload limits, trigger timeouts, spike memory, and amplify retries.

**"If a chunk fails, none of its items caused side effects."** False when operations do not share a single transaction or the bulk API allows partial success.

**"`sequenceNumber` is a durable `lineId`."** False. Sequence ordinals shift across sorting, retries, or nested splits; use business IDs.

**"A Splitter supporting `Iterable` automatically provides backpressure and recovery."** False. You still need bounded pipelines, resource management, and checkpoints/durability.

**"Aggregator always knows when enough messages arrived."** False with unknown sequence sizes, lost children, Filter drops, or duplicates; define explicit release/timeout/failure policies.

**"Sending an empty batch through Splitter makes Gateway automatically receive a result."** Not by default. Emit an explicit terminal outcome.

**"Reusing one `correlationId` across all split levels works fine."** It can cross-mix groups. Model batch/chunk/line identities explicitly and test headers at every tier.

## 28. Key Takeaways

**Splitter** in Spring Integration turns **one composite message into multiple child messages** and can attach **sequence/correlation metadata** for downstream coordination. **Chunking** is **dividing data into bounded groups** to optimize I/O, memory, throughput, or transactions. You can **split item by item**, **partition into chunks then split per chunk**, or **gather discrete messages into chunks with an Aggregator/batcher**.

Choose the processing unit based on **per-item independence, bulk capabilities, retry scope, idempotency, memory bounds, transactions, ordering, and completion semantics**. If you need **chunk-oriented read-process-write with commit/restart**, consider Spring Batch; if you need **message fan-out, routing, and coordination with Gateway/Filter/Transformer/Aggregator**, use Spring Integration with explicit correlation and error handling.

Distinguishing these layers cleanly makes message flows far easier to scale without confusing **"splitting work up"** with **"processed successfully."**

### References

- Spring Integration Reference, **Splitter**: https://docs.spring.io/spring-integration/reference/splitter.html
- Spring Integration Reference, **Aggregator**: https://docs.spring.io/spring-integration/reference/aggregator.html
- Spring Batch Reference, **Chunk-oriented Processing**: https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html
- Enterprise Integration Patterns, **Splitter**: https://www.enterpriseintegrationpatterns.com/patterns/messaging/Sequencer.html
