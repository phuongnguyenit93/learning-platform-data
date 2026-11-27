# Composing Multiple Writes with Appropriate Concurrency

> **Chapter:** Reactive access  
> **Module:** `SPRING_DATA_MONGODB` — using Spring Data MongoDB to connect, map documents, and operate on data via `MongoTemplate` or repositories; practicing query design, aggregation, indexes, transactions, reactive access, testing, and data performance diagnostics.  
> **Goal:** Distinguish dependent vs independent writes; build write pipelines using `Mono`/`Flux`, `then`, `flatMap`, `concatMap`, and `flatMapSequential`; pick concurrency limits aligned with connections, database capacity, and memory; handle per-item errors, partial success, retries/idempotency, and write concerns; understand why **writes inside the same MongoDB transaction must not run concurrently**; and measure and verify with `StepVerifier` against real test MongoDB.

## 1. Problem: When Writing 10,000 Records, Should All Run Concurrently?

An API receives a batch of inventory intake events, each needing to be persisted to MongoDB with its own business ID. Using WebFlux and `ReactiveMongoRepository`, the following code looks natural:

~~~java
return Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)));
~~~

However, `flatMap` **subscribes eagerly to many inner Publishers** and interleaves emissions as they finish. Without deliberate concurrency bounds, the number of active in-flight operations depends on operator defaults and the source—not a self-regulating backpressure protocol tuned to MongoDB load that your application controls.

Real-world scenarios have **different needs**:

1. Independent events with unique keys: can write **with bounded concurrency**.
2. Two commands mutating the same order in sequence `PENDING → APPROVED → SHIPPED`: must enforce **per-order sequencing** or conditional/versioned updates.
3. Updating an order and inserting an outbox record in **one transaction**: must execute **sequentially within the same session**.
4. Bulk-importing hundreds of thousands of documents: evaluate **batching/bulk writes** rather than one network request per document.
5. One item failing with duplicate key: decide whether to **abort the whole stream**, **report per-item status**, or **reconcile idempotency**.

Thus, the real question is not “Is reactive faster because it's parallel?” but:

> **How many writes can stay in flight concurrently while staying business-correct, avoiding database overload, and handling failures safely?**

### 1.1. Three Concepts Never to Equate

| Concept | Meaning | Example |
| --- | --- | --- |
| **Concurrent writes** | Multiple operations in-flight simultaneously | `flatMap(write, 8)` |
| **Parallel threads** | Multiple CPU threads running simultaneously | `parallel().runOn(...)` |
| **Atomic transaction** | Group of writes committing/aborting as one unit | `TransactionalOperator` / reactive `@Transactional` |

**Concurrency does not require one thread per operation.** The Reactive MongoDB Driver uses async I/O, keeping multiple requests in flight without `boundedElastic` or `parallel()`. And **a transaction does not permit concurrent writes inside that transaction**.

~~~mermaid
flowchart TD
    A["Flux<WriteCommand>"] --> B{"Any state/ordering dependency?"}
    B -->|"No, independent"| C["flatMap(write, concurrency=N)"]
    B -->|"Yes, per ID"| D["Sequential per key + concurrent across keys"]
    B -->|"Same MongoDB transaction"| E["then/flatMap sequentially inside session"]
    C --> F["Bound pool, resources, retries"]
    D --> F
    E --> G["commit/abort whole transaction"]
    F --> H["Per-item / batch outcomes"]
~~~

## 2. When Do Reactive Writes Execute?

`ReactiveMongoTemplate` and `ReactiveMongoRepository` return **Publishers**: typically `Mono<T>` for single results or `Flux<T>` for multi-item streams. For standard reactive CRUD APIs, the publisher describes async work, and real I/O occurs upon **subscription**.

~~~java
Mono<WriteJob> operation = repository.insert(job);
// Creates the publisher; does not mean an ACK was received from MongoDB yet.
~~~

Without a subscriber, the application normally **has not performed the write**.

### 2.1. Each Subscription Can Trigger Another Write

~~~java
Mono<WriteJob> operation = repository.insert(job);

// Two subscriptions can trigger two insert executions.
// The second attempt may hit a duplicate _id.
operation.subscribe();
operation.subscribe();
~~~

This snippet is an **anti-pattern**. Inside services, **never call `subscribe()`** discarding the returned Publisher: doing so detaches the operation from error handling, transaction context, and the caller's lifecycle.

### 2.2. Proper Pipeline: Return the Publisher to the Caller

~~~java
public Mono<WriteJob> create(WriteJob job) {
    return repository.insert(job);
}
~~~

In WebFlux, controllers return `Mono<ResponseEntity<...>>` or `Flux<...>` for the framework to subscribe. In background consumers, the subscriber must tie cleanly to consumer lifecycle and acknowledgment—never fire off unmonitored `subscribe()` calls.

### 2.3. `map` Does Not “Await” a Nested `Mono`

Wrong:

~~~java
Flux<Mono<WriteJob>> nested = Flux.fromIterable(commands)
    .map(command -> repository.insert(toDocument(command)));
// This is a Flux emitting PUBLISHERS, not a Flux<WriteJob>.
~~~

Right:

~~~java
Flux<WriteJob> writes = Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)), 8);
~~~

`map` performs synchronous **T → R** transformations. When a mapper returns `Mono<R>`/`Flux<R>` that must be subscribed to, use `flatMap`, `concatMap`, or an appropriate flattening operator.

## 3. Data Model Used in This Lesson

Java examples live in package `com.example.reactivewrites`. Use an **isolated test collection**; `mongosh` scripts are strictly for study, never production.

### 3.1. Each Command Carries a Business Key

~~~java
// WriteCommand.java
package com.example.reactivewrites;

public record WriteCommand(
    String id,
    String tenantId,
    String payload
) {
}
~~~

`id` must stay **stable across retries**, such as an upstream event ID or an idempotency key. Never generate a brand-new UUID on each retry if business rules forbid duplicate inserts.

### 3.2. MongoDB Entity

~~~java
// WriteJob.java
package com.example.reactivewrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "write_jobs_reactive_011")
public class WriteJob {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String payload;
    private String status;

    @Field("created_at")
    private Instant createdAt;

    protected WriteJob() {}

    public WriteJob(
            String id, String tenantId, String payload,
            String status, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.payload = payload;
        this.status = status;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getPayload() { return payload; }
    public String getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
}
~~~

`@MongoId(FieldType.STRING)` ensures `_id` is stored as a string per lesson conventions, avoiding surprises with ObjectId auto-conversion when IDs take special formats.

### 3.3. Reactive Repository

~~~java
// WriteJobRepository.java
package com.example.reactivewrites;

import org.springframework.data.mongodb.repository.ReactiveMongoRepository;

public interface WriteJobRepository
        extends ReactiveMongoRepository<WriteJob, String> {
}
~~~

MongoDB maintains a unique index on `_id`. If a client sends the same `id` a second time, `insert` is rejected with a duplicate key error (unless the first never persisted or rolled back). This underpins idempotency, though applications must still verify whether **the repeated request carries identical payload semantics**.

### 3.4. `mongosh` Fixture

~~~javascript
use spring_data_mongodb_lab

db.createCollection("write_jobs_reactive_011");
db.write_jobs_reactive_011.createIndex(
  { tenant_id: 1, status: 1, created_at: -1 },
  { name: "ix_tenant_status_created" }
);

db.write_jobs_reactive_011.insertMany([
  {
    _id: "j011-01", tenant_id: "t01",
    payload: "A", status: "NEW",
    created_at: ISODate("2026-11-01T00:00:00Z")
  },
  {
    _id: "j011-02", tenant_id: "t01",
    payload: "B", status: "NEW",
    created_at: ISODate("2026-11-01T00:01:00Z")
  },
  {
    _id: "j011-03", tenant_id: "t02",
    payload: "C", status: "NEW",
    created_at: ISODate("2026-11-01T00:02:00Z")
  }
]);
~~~

Existing IDs are for querying or updating the fixture; when testing inserts from Java, pick fresh IDs like `import-011-001`. Do not re-run `insertMany` on identical IDs; duplicate key errors are expected behavior, not a Reactor bug.

### 3.5. Factory Converting Command to Entity

~~~java
import java.time.Instant;

private static WriteJob toDocument(WriteCommand command) {
    if (command.id() == null || command.id().isBlank()) {
        throw new IllegalArgumentException("id is required");
    }
    if (command.tenantId() == null
            || command.tenantId().isBlank()) {
        throw new IllegalArgumentException("tenantId is required");
    }
    return new WriteJob(
        command.id(), command.tenantId(), command.payload(),
        "NEW", Instant.now()
    );
}
~~~

In production, take the tenant from the security context and authorize access; never trust an arbitrary client-supplied `tenantId`. If creation timestamps must stay **stable across retries**, pass `createdAt` from the original command instead of calling `Instant.now()` repeatedly, as this affects request-fingerprint reconciliation on duplicates.

## 4. Chaining Two Dependent Writes: `flatMap` and `then`

Suppose we must insert `WriteJob` first and then transition **that exact document** from `NEW` to `READY`.

### 4.1. Using the Prior Write's Result as Input to the Next

~~~java
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

public Mono<WriteJob> insertThenMarkReady(WriteJob job) {
    return repository.insert(job)
        .flatMap(inserted -> {
            Query query = Query.query(
                Criteria.where("id").is(inserted.getId())
                    .and("tenantId").is(inserted.getTenantId())
                    .and("status").is("NEW")
            );

            return template.updateFirst(
                query,
                new Update().set("status", "READY"),
                WriteJob.class
            ).flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new IllegalStateException(
                            "Unexpected state after insert"));
                }
                return template.findById(
                    inserted.getId(), WriteJob.class
                );
            });
        });
}
~~~

Here `repository` is `WriteJobRepository` and `template` is `ReactiveMongoTemplate` injected into a service. `flatMap` guarantees the update **subscribes only after `insert` emits**.

**Atomicity note:** chaining with `flatMap` does not put two writes inside a transaction. If `insert` succeeds and `update` fails, the document remains in `NEW`. For all-or-nothing across writes, use a proper transaction, or design a single-document conditional operation from the start.

### 4.2. Using `then` When You Don't Need the Previous Step's Value

~~~java
Mono<Void> first = writeAuditFor(job);
Mono<Void> second = publishOutboxRecordFor(job);

Mono<Void> ordered = first.then(second);
// second is subscribed only after first completes successfully.
~~~

`then(other)` **ignores upstream `onNext` values** and waits for upstream to **complete successfully** before subscribing to `other`. If upstream emits `onError`, `other` is never subscribed.

To defer **constructing the second Publisher** if its factory has work to run later:

~~~java
Mono<Void> ordered = writeAuditFor(job)
    .then(Mono.defer(() -> publishOutboxRecordFor(job)));
~~~

In pure Reactor/`ReactiveMongoTemplate` code, constructing a publisher usually triggers no I/O, yet **factory methods can still contain synchronous side effects**. `Mono.defer` keeps construction and subscription boundaries clean.

### 4.3. `thenReturn` and `thenMany`

~~~java
Mono<String> confirmation = repository.insert(job)
    .thenReturn(job.getId());

Flux<WriteJob> afterSetup = ensureImportMarker()
    .thenMany(Flux.fromIterable(batch)
        .flatMap(repository::insert, 4));
~~~

`thenReturn` discards the insert result and emits the ID after completion. `thenMany` waits for the setup step to finish before subscribing to the multi-item stream.

**Never use `thenReturn("SUCCESS")` as a promise that the whole workflow committed if external side effects run afterward or write concern is weak.** Success reflects only the operation's actual acknowledgment.

## 5. `Mono.when` and `Mono.zip`: Composing Independent Operations

Two writes targeting **unrelated keys** and **not sharing a transaction** can execute concurrently.

### 5.1. `Mono.when` Waits for Both to Complete

~~~java
Mono<Void> both = Mono.when(
    repository.insert(jobA).then(),
    repository.insert(jobB).then()
);
~~~

`Mono.when` subscribes to all sources and completes when **every one** completes successfully. However:

- If source B errors, A may **already be persisted**.
- By default, `Mono.when` emits the error and cancels siblings; **cancellation never rolls back writes already processed by the server**.
- There is no all-or-nothing atomicity between A and B.

Therefore, `Mono.when` fits only when **writes are truly independent**, partial completion is acceptable, and recovery policies exist.

### 5.2. `Mono.zip` When Values from Both Are Needed

~~~java
Mono<reactor.util.function.Tuple2<WriteJob, WriteJob>> pair =
    Mono.zip(
        repository.insert(jobA),
        repository.insert(jobB)
    );

Mono<String> summary = pair.map(tuple ->
    tuple.getT1().getId() + "," + tuple.getT2().getId()
);
~~~

`zip` combines **results**; it does not create a transaction. If either source completes empty (e.g., `Mono<Void>`), `zip` completes empty and cancels the sibling. **Never pass `Mono<Void>`s to `Mono.zip(Mono<Void>, Mono<Void>)`** to wait for two operations; use `Mono.when` when only completion is needed.

### 5.3. Never Use `when` Where Business Ordering Matters

Wrong:

~~~java
// No insert -> update ordering.
Mono.when(
    repository.insert(job),
    template.updateFirst(query, update, WriteJob.class)
);
~~~

The update can execute before the insert; `matchedCount=0` is not a Reactive Driver bug, just a **pipeline race**. Use `insert.flatMap(...)` or `insert.then(update...)`.

## 6. Three Choices for Processing a `Flux` of Commands

Assume `commands` is `Flux<WriteCommand>` and each item invokes:

~~~java
Mono<WriteJob> writeOne(WriteCommand command) {
    return repository.insert(toDocument(command));
}
~~~

### 6.1. `concatMap` — Strict Sequence Within the Flux

~~~java
Flux<WriteJob> result = commands
    .concatMap(this::writeOne);
~~~

`concatMap` waits for each inner Publisher to **complete** before subscribing to the next. When each inner is a write `Mono`:

~~~text
write(A) ─── ACK
                write(B) ── ACK
                              write(C) ─── ACK
~~~

Pros: preserves both **execution/subscription order** and **output order**; avoids overlapping writes within this pipeline. Cons: write latencies accumulate serially, lowering throughput for independent tasks.

### 6.2. `flatMap(..., N)` — Up to N Concurrent Inner Publishers

~~~java
int concurrency = 8;

Flux<WriteJob> result = commands
    .flatMap(this::writeOne, concurrency);
~~~

`flatMap` keeps up to **N active inner subscriptions** in flight and emits results as each finishes:

~~~text
write(A) ───────── ACK A
write(B) ── ACK B
write(C) ───── ACK C

Downstream receives: B, C, A (order may differ from source).
~~~

**N bounds concurrency only for this single pipeline, not total MongoDB writes across the service/cluster.** If 30 HTTP requests arrive concurrently, each running `flatMap(..., 8)`, up to **240 inner writes** can run simultaneously—before counting other pods or services.

### 6.3. `flatMapSequential(..., N)` — Concurrent Execution with Source-Ordered Emissions

~~~java
Flux<WriteJob> result = commands
    .flatMapSequential(this::writeOne, 8);
~~~

This subscribes eagerly to multiple inner Publishers like `flatMap`, while **buffering early completions** to emit downstream in source order.

> **Crucial:** `flatMapSequential` preserves **downstream `onNext` order**; it **does not guarantee MongoDB writes execute in order**.

If A and B mutate the same document into different states, `flatMapSequential` can still let B hit the DB before A. When DB write ordering matters, use `concatMap`, per-key partitioning, or optimistic locking.

### 6.4. Comparison Table

| Operator | Concurrent Inner Writes | Output Emission Order | DB Write Execution Order |
| --- | --- | --- | --- |
| `concatMap` | 1 per pipeline | Source order | **Sequential** |
| `flatMap(mapper, N)` | Up to N | Completion order | Unordered |
| `flatMapSequential(mapper, N)` | Up to N | Source order | **Unordered** |
| `merge` | Multiple sources concurrently | Completion order | Unordered |
| `Mono.when` | Sources subscribed together | Completion only | Unordered |
| `then` | Upstream then downstream | N/A | **Dependency-ordered** |

### 6.5. `flatMapSequential` Buffers Early Results

If an early item stalls while later items finish fast, `flatMapSequential` **retains early results in memory** until the stalled item emits, increasing memory and tail latency. Use it only when callers require **source-ordered output** for genuinely independent writes.

## 7. Picking Concurrency Without Magic Numbers

There is no universal magic N like 16, 32, or 256. The right limit depends on:

- MongoDB Driver connection pool size and max simultaneous connections.
- Network RTT and average/p95 write latency.
- Index count, shard count, replica lag, and write concern (`majority` waits longer).
- Document size, journal/WAL overhead, lock contention, and hot spots.
- Producer emission rate and application heap limits.
- Number of concurrent requests/consumer instances system-wide.

### 7.1. Start Small and Bounded

~~~java
int concurrency = 8; // Experimental STARTING point, not a universal default.

return commands.flatMap(this::writeOne, concurrency);
~~~

Benchmark before and after on representative data and topology before scaling up. Once p95/p99 latency climbs, pool wait queues grow, or secondary lag rises, raising N further actually **reduces** throughput.

### 7.2. Rough Model: Little's Law

At steady throughput and average latency:

\[
L \approx \lambda \times W
\]

where `L` is average in-flight requests, `λ` is completed writes/second, and `W` is average write latency in seconds.

Illustrative simulation:

~~~text
Target:           400 writes/second
Average latency:  20 ms = 0.02 s
Average in-flight ≈ 400 × 0.02 = 8
~~~

This is an **average in-flight estimate**, not a guarantee that `N=8` meets your SLO. Real workloads suffer tail latency, bursts, pool contention, and concurrent clients—always benchmark before finalizing N.

### 7.3. Computing System-Wide Concurrency

Consider:

~~~text
20 concurrent WebFlux requests
× 8 writes/request
= 160 active inner writes
~~~

Across three worker instances, cluster-wide load multiplies further. Thus `flatMap`'s limit is **purely local**, not an instance-wide rate limit or cluster admission control. When ingress is bursty, add a **bounded semaphore, queue, or bulkhead** or cap consumer concurrency at ingest to enforce global ceilings.

### 7.4. Never Add `parallel()` / `subscribeOn(boundedElastic)` by Habit

~~~java
// Unnecessary just for calling reactive MongoDB APIs:
commands.parallel()
    .runOn(reactor.core.scheduler.Schedulers.parallel())
    .flatMap(this::writeOne);
~~~

`parallel()` targets CPU-bound parallelizable work. Reactive MongoDB I/O is non-blocking; extra scheduler hops complicate code and tracing without making the DB write faster.

`Schedulers.boundedElastic()` exists to **isolate blocking APIs** lacking reactive alternatives. Never wrap `repository.insert(...)` inside `Mono.fromCallable(...).subscribeOn(boundedElastic)` as if it were blocking.

## 8. Sequential Per Key, Concurrent Across Keys

Suppose an application processes orders where mutations on **the same order** must stay sequential, while **different orders** can update concurrently without cross-order dependencies.

Example:

~~~text
order-01: PENDING → APPROVED → SHIPPED  (must be sequential)
order-02: PENDING → CANCELLED          (independent of order-01)
order-03: PENDING → APPROVED           (independent of order-01 and 02)
~~~

### 8.1. Global `concatMap`: Correct Yet Potentially Slow

~~~java
Flux<OrderMutation> mutations = sourceOfMutations();

Flux<MutationResult> results = mutations
    .concatMap(this::applyMutation);
~~~

Every order serializes globally even when unrelated. This is clean and safe at modest throughput or until independence is proven.

### 8.2. `groupBy` Combined with `concatMap` and `flatMap`

~~~java
int activeKeyGroups = 8;

Flux<MutationResult> results = mutations
    .groupBy(OrderMutation::orderId)
    .flatMap(
        group -> group.concatMap(this::applyMutation),
        activeKeyGroups
    );
~~~

Assumed types:

~~~java
record OrderMutation(
    String orderId,
    String tenantId,
    String newState
) {}

record MutationResult(
    String orderId,
    String appliedState
) {}

Mono<MutationResult> applyMutation(OrderMutation command) {
    // Verify status/tenant/version and perform an atomic update.
    // Return Mono<MutationResult> after DB acknowledgment.
    return writeOrderState(command);
}
~~~

**Mechanism:**

- `groupBy(OrderMutation::orderId)` splits the stream into `GroupedFlux` instances per order ID.
- Each group applies `concatMap`, so **events for the same order subscribe sequentially**.
- `flatMap(..., 8)` drains up to eight **active groups** concurrently across orders.

**Serious caveat:** `groupBy` is unsuitable for **unbounded streams with unbounded key cardinality**. It retains group state and queues; when active keys exceed outer concurrency, unconsumed groups can stall the stream or cause backpressure deadlocks. Use it only on bounded key cardinality, or route through **a fixed number of hash partitions**, keyed consumers, or a message broker.

### 8.3. Bounded Partitions for High Key Cardinality

An ingest service can hash `orderId` across **K fixed partitions**, running `concatMap` per partition concurrently. Account for:

- Message broker partition ordering across multiple consumer instances.
- Whether retries or consumer rebalances reorder items.
- Hash distribution uniformity when scaling K.
- Hot keys overloading one partition.

Design sketch:

~~~text
hash(orderId) % 8
     |
     +-- partition 0: concatMap(write)
     +-- partition 1: concatMap(write)
     ...
     +-- partition 7: concatMap(write)

Partitions are consumed concurrently; each partition preserves FIFO.
~~~

Never treat in-process `groupBy` as a distributed lock: two service instances can still touch the same order concurrently. Even with per-key local sequencing, always enforce **atomic conditional updates**, `@Version` optimistic locking, and idempotency in MongoDB.

### 8.4. Atomic Updates Are the Final Line of Defense

~~~java
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import reactor.core.publisher.Mono;

Mono<MutationResult> applyMutation(OrderMutation command) {
    Query eligible = Query.query(
        Criteria.where("id").is(command.orderId())
            .and("tenantId").is(command.tenantId())
            .and("state").is("PENDING")
    );

    return reactiveMongoTemplate.updateFirst(
        eligible,
        new Update().set("state", command.newState()),
        OrderDocument.class
    ).flatMap(result -> {
        if (result.getMatchedCount() != 1) {
            return Mono.error(
                new IllegalStateException(
                    "Order missing, wrong tenant or state changed"));
        }
        return Mono.just(new MutationResult(
            command.orderId(), command.newState()
        ));
    });
}
~~~

`OrderDocument` from section 18 maps to the orders collection; here the condition illustrates transitioning from `PENDING`. For transitions like `APPROVED → SHIPPED`, pass and check each command's expected state rather than hardcoding `PENDING`.

Atomic conditional updates catch concurrent races **even across multiple service instances**, whereas `concatMap` only orders **a single local stream**.

## 9. Backpressure Does Not Replace Write Concurrency Caps

Reactive Streams lets consumers regulate upstream via `request(n)`. Yet upstream backpressure does not guarantee MongoDB has sufficient CPU, connections, and journal I/O for arbitrary write bursts.

### 9.1. What `flatMap(..., N)` Controls

~~~java
Flux<WriteJob> stream = commands
    .flatMap(this::writeOne, 8);
~~~

`N` caps active inner Publishers **in this pipeline**. Reactor operators also have `prefetch` settings controlling upstream pulls and buffering. When mappers return `Mono`, reasoning is straightforward; when mappers return multi-item `Flux`es, monitor **inner item counts** too.

### 9.2. `limitRate` Only Shapes Demand

~~~java
commands
    .limitRate(64)
    .flatMap(this::writeOne, 8);
~~~

`limitRate` chunks upstream demand requests. It **neither bounds global concurrency across the app** nor acts as a durable queue. If the producer is a hot source emitting faster than consumers drain, inspect the producer's backpressure behavior directly.

### 9.3. `onBackpressureBuffer` Cannot Solve Infinite Overload

~~~java
// Risk: unbounded buffer if the producer consistently outpaces MongoDB.
// source.onBackpressureBuffer()
//       .flatMap(this::writeOne, 8);
~~~

An unbounded buffer merely **shifts congestion from MongoDB into JVM heap**. On hot sources, set explicit capacity bounds, overflow policies, and respect **no-lost-writes** semantics—never pick `DROP` just to save RAM for payment or ledger events.

### 9.4. Rate Limits and Concurrency Limits Are Orthogonal

| Limit | Example | Protects Against |
| --- | --- | --- |
| Concurrent in-flight | Max 8 active writes | Too many simultaneous operations |
| Rate per second | Max 300 writes/sec | Sustained bursts over time |
| Queue capacity | Max 5,000 queued events | Unbounded RAM/queue growth |
| Batch size | 200 docs/request | Excessive round trips or oversized payloads |
| Request deadline | 5s/API | Client wait times (**never guarantees write cancellation**) |

Sound designs set limits matching SLOs. An in-flight cap of 8 can still generate high throughput at 1 ms/write, or low throughput if `majority` writes take 500 ms.

### 9.5. Also Bound Ingress

Suppose a controller accepts a long `Flux<WriteCommand>`:

~~~java
public Flux<WriteJob> importCommands(Flux<WriteCommand> source) {
    return source.flatMap(this::writeOne, 8);
}
~~~

This bounds write concurrency inside the pipeline, yet the API also needs:

- Authentication, authorization, and tenant isolation.
- Body size limits, max command counts, or streaming quotas.
- Deadlines and client disconnect behavior.
- Per-tenant and per-instance active job caps.
- Clear status contracts distinguishing `ACCEPTED` vs `PERSISTED` vs `PROCESSING`.

Never equate “client finished uploading JSON” with “MongoDB acknowledged all writes.”

## 10. When to Choose Batch Inserts or Bulk Operations?

For 100,000 independent documents, issuing 100,000 separate `repository.insert` calls incurs massive round-trip overhead. Spring Data Reactive MongoDB supports **collection inserts** and **bulk operations** to cut round trips.

### 10.1. Batch Insert with `ReactiveMongoTemplate.insert`

~~~java
import java.util.List;
import reactor.core.publisher.Flux;

Flux<WriteJob> insertBatch(List<WriteJob> docs) {
    return reactiveMongoTemplate.insert(docs, WriteJob.class);
}
~~~

This issues a **batch insert** through the template; every document remains subject to `_id` uniqueness and validation. Error reporting and partial batch outcomes depend on driver, ordered mode, and config—it does not make the batch a transaction.

### 10.2. Chunking a Stream into Bounded Batches

~~~java
int batchSize = 200;

Mono<Void> writeAll = commands
    .map(command -> toDocument(command))
    .buffer(batchSize)
    .concatMap(batch ->
        reactiveMongoTemplate.insert(batch, WriteJob.class)
            .then()
    )
    .then();
~~~

Only **one batch write is subscribed** at a time due to `concatMap`, with up to 200 documents per batch. Choose `batchSize` respecting document sizes, BSON/request limits, and RAM.

### 10.3. Allowing Limited Concurrent Batches

~~~java
Mono<Void> writeAll = commands
    .map(command -> toDocument(command))
    .buffer(200)
    .flatMap(
        batch -> reactiveMongoTemplate
            .insert(batch, WriteJob.class)
            .then(),
        2  // At most 2 active batch Publishers.
    )
    .then();
~~~

**Clarification:** two concurrent batches **do not mean 400 individual single-document requests**. Each batch is one driver `insert(collection)` call (split across wire batches only if hitting byte caps), processed as batches on the server. `N × batchSize` represents **documents held in flight across active batches**, not connection counts.

### 10.4. `ReactiveBulkOperations` with Ordered/Unordered Modes

~~~java
import com.mongodb.bulk.BulkWriteResult;
import org.springframework.data.mongodb.core.BulkOperations;
import reactor.core.publisher.Mono;

Mono<BulkWriteResult> bulkInsert(List<WriteJob> docs) {
    return reactiveMongoTemplate
        .bulkOps(
            BulkOperations.BulkMode.UNORDERED,
            WriteJob.class
        )
        .insert(docs)
        .execute();
}
~~~

`BulkMode.ORDERED` executes operations sequentially and stops on the first failure; `UNORDERED` lets the server/driver execute in arbitrary order and continue past individual errors. **Unordered mode does not provide batch atomicity or exactly-once guarantees.**

When using bulk operations:

- Duplicate errors can leave **a subset of documents inserted**.
- `BulkWriteResult` and exceptions carry success/failure details depending on write concern and driver.
- Never rely on result ordering for business logic under `UNORDERED`.
- Bulk operations skip certain entity lifecycle callbacks, events, and version checks compared to repository `save`; check Spring Data docs for your version.

### 10.5. Modern `bulkWrite` in MongoDB 8.0+

Newer Spring Data MongoDB versions introduce `bulkWrite(...)`, and MongoDB 8.0+ supports bulk writes spanning **multiple collections in one request**, differing from traditional single-collection `bulkOps(...)`.

**Never confuse “one bulk request” with “a multi-document transaction.”** Cross-collection commit/abort atomicity still requires an explicit transaction/session; bundling into one wire request is not all-or-nothing.

### 10.6. Time-Bounded Batching: `bufferTimeout`

When inputs arrive steadily or in small trickles:

~~~java
Flux<List<WriteJob>> batches = commands
    .map(command -> toDocument(command))
    .bufferTimeout(
        200,
        java.time.Duration.ofMillis(250)
    );

Mono<Void> done = batches
    .flatMap(
        batch -> bulkInsert(batch).then(),
        2
    )
    .then();
~~~

The pipeline flushes a batch whenever 200 items accumulate or 250 ms elapse (subject to Reactor timing/demand rules). The timeout reduces **partial-batch latency**; it is not a durability flush or database journal timeout.

### 10.7. Operation Selection Table

| Scenario | Suitable API / Operator | Warning |
| --- | --- | --- |
| Single document needing saved entity | `repository.insert` | Duplicate ID / write acknowledgment |
| Small number of independent documents | `flatMap(insert, N)` | Out-of-order results and partial success |
| Large volume in one collection | `template.insert(List, Class)` or `bulkOps` | Batch limits and per-item failures |
| Mixed insert/update/delete in one collection | `bulkOps(ORDERED/UNORDERED)` | Not atomic across the whole batch |
| Multi-collection bulk on server 8.0+ | `bulkWrite` API if version supports | Still not a transaction |
| Sequential dependent writes | `concatMap`, `then` | Ordering does not imply atomicity |
| Two collections must commit/abort together | Reactive transaction, **sequential** writes | Never run parallel writes in one transaction |

## 11. Mid-Stream Failures: Stream Stops, Yet Earlier Writes May Persist

Consider:

~~~java
return Flux.fromIterable(commands)
    .flatMap(this::writeOne, 8);
~~~

If command #7 fails with a duplicate key error:

1. Other commands **may already have been persisted by the server**.
2. `flatMap` propagates the error downstream by default and cancels remaining in-flight inner streams.
3. Cancellation stops client consumption; it **does not roll back** writes already received by the server.
4. In-flight writes hit by network/timeout errors may have an unknown server state.

**Never conclude “because the Flux errored, all 8 in-flight writes rolled back.”**

### 11.1. When Does Fail-Fast Make Sense?

If an import job requires **halting further submissions** on any error, fail-fast fits—provided you record partial outcomes and support reconciliation/resume. If business rules require all-or-nothing, fail-fast **never replaces a transaction**.

### 11.2. `onErrorResume` Outside vs Inside the Mapper

**Outside**:

~~~java
Flux<WriteJob> result = commands
    .flatMap(this::writeOne, 8)
    .onErrorResume(ex -> Flux.empty());
~~~

This is normally a **dangerous pattern**: one error halts the main stream, `onErrorResume` swallows it and completes empty, while earlier items already committed—leaving zero reporting on failed or `UNKNOWN` items.

**Per item**:

~~~java
Flux<WriteOutcome> report = commands.flatMap(
    command -> writeWithOutcome(command),
    8
);
~~~

`writeWithOutcome` turns **classified per-item failures** into `WriteOutcome` values rather than failing the outer stream, allowing remaining items to proceed. Use this **only when items are genuinely independent** without batch-level atomicity.

### 11.3. `flatMapDelayError` and Its Limits

Reactor offers `flatMapDelayError` to **defer emitting errors** until other inner streams finish within bounds. While handy for collecting results despite per-item errors:

- It does not create a transaction.
- It does not turn ambiguous errors into definite non-writes.
- It does not generate a per-command status report on its own.

When APIs must report outcomes per command, **an explicit `WriteOutcome` wrapper** is far cleaner than unpacking a composite exception.

### 11.4. Never Use `onErrorContinue` to “Skip Failing Items”

`onErrorContinue` alters upstream operator error propagation with subtle semantics; not all reactive MongoDB write operators recover cleanly under it.

Keep error handling **inside each command's inner Publisher** via targeted `onErrorResume`, or break batches into persistent stateful jobs.

## 12. Designing Per-Item Results (`WriteOutcome`)

When callers must know which items inserted, already existed, conflicted, or ended uncertain, returning raw `Flux<WriteJob>` is insufficient.

### 12.1. Outcome Statuses

~~~java
// WriteOutcome.java
package com.example.reactivewrites;

public record WriteOutcome(
    String id,
    Status status,
    String detail
) {
    public enum Status {
        INSERTED,
        ALREADY_PRESENT,
        CONFLICT,
        UNKNOWN
    }

    public static WriteOutcome inserted(String id) {
        return new WriteOutcome(id, Status.INSERTED, "acknowledged");
    }
    public static WriteOutcome existing(String id) {
        return new WriteOutcome(id, Status.ALREADY_PRESENT, "same payload");
    }
    public static WriteOutcome conflict(String id) {
        return new WriteOutcome(id, Status.CONFLICT, "payload mismatch");
    }
    public static WriteOutcome unknown(String id) {
        return new WriteOutcome(id, Status.UNKNOWN, "reconciliation needed");
    }
}
~~~

`UNKNOWN` does not mean confirmed failure: it means **insufficient confirmation**, common on dropped connections or unmet write concerns.

### 12.2. Reconciling Duplicates on Insert

~~~java
import org.springframework.dao.DuplicateKeyException;
import reactor.core.publisher.Mono;

Mono<WriteOutcome> writeWithOutcome(WriteCommand command) {
    WriteJob desired = toDocument(command);

    return repository.insert(desired)
        .map(saved -> WriteOutcome.inserted(saved.getId()))
        .onErrorResume(DuplicateKeyException.class, error ->
            repository.findById(command.id())
                .map(existing -> {
                    boolean same =
                        command.tenantId().equals(existing.getTenantId())
                        && java.util.Objects.equals(
                            command.payload(), existing.getPayload());

                    return same
                        ? WriteOutcome.existing(command.id())
                        : WriteOutcome.conflict(command.id());
                })
                .switchIfEmpty(
                    Mono.just(WriteOutcome.unknown(command.id()))
                )
        );
}
~~~

This example illustrates duplicate `_id` for the same command. In collections with **other unique indexes**, a `DuplicateKeyException` can come from a different constraint than `_id`, making `findById(command.id())` alone insufficient. Identify the violated index and compare the **full request fingerprint** (tenant, operation type, normalized payload, version, etc.).

If reconciliation reads from a lagging secondary, `findById` may miss newly written data; configure read concern/read preference fitting your reconciliation policy and report `UNKNOWN` whenever evidence is inconclusive.

### 12.3. Never Blanket-Map Every Error to `UNKNOWN`

~~~java
// Avoid without classifying errors:
// .onErrorResume(Exception.class, ex ->
//     Mono.just(WriteOutcome.unknown(command.id())))
~~~

Validation failures, bad field mappings, tenant permission errors, server selection timeouts, and programming bugs should not all be treated identically. Define clear buckets:

- **Definite conflict:** payload mismatch or business constraint violation.
- **Recoverable transient:** safe to retry up to a limit.
- **Unknown outcome:** server may have committed; needs reconciliation.
- **Fatal/system error:** halt job and alert operators rather than completing silently.

### 12.4. Preserving Input Order in Outcomes

~~~java
Flux<WriteOutcome> outcomes =
    Flux.fromIterable(commands)
        .flatMapSequential(this::writeWithOutcome, 8);
~~~

Here `WriteOutcome` emissions match input order **even while inserts run concurrently**. That works because commands are independent; if commands mutate the same ID sequentially, enforce per-key ordering or conditional updates.

### 12.5. Avoid Unbounded `collectList()`

~~~java
Mono<List<WriteOutcome>> all = outcomes.collectList();
~~~

`collectList()` holds every outcome in heap. Fine for small fixed API batches (e.g., 100 commands); for 10 million items or unbounded streams, **stream outcomes, paginate/batch, or persist job status to the DB**.

## 13. Retries: Classifying Errors and Preserving Idempotency

### 13.1. Driver Retryable Writes vs Application Retries

The MongoDB Java Driver supports **retryable writes** for eligible operations on supported topologies. Reactor's `retryWhen` at the app layer **re-subscribes**, which does not always carry identical session/transaction identity across every failure mode.

~~~java
import reactor.util.retry.Retry;
import java.time.Duration;

Mono<WriteJob> writeWithLimitedRetry(WriteCommand command) {
    return Mono.defer(() ->
        repository.insert(toDocument(command))
    ).retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientAndSafeToRetry)
    );
}
~~~

`isTransientAndSafeToRetry(Throwable)` is a **project-defined policy function** inspecting exception types, error labels, operation kind, and reconciliation safety—never replace it with `ex -> true`. Duplicate key and validation errors are **not** transient retry candidates.

### 13.2. Retrying with a Fresh ID Risks Double Writes

Wrong:

~~~java
// Anti-pattern: generating a new ID on every retry:
// return repository.insert(new WriteJob(
//     UUID.randomUUID().toString(), ...));
~~~

If the first write hit MongoDB and its ACK was lost, retrying with a new ID inserts **a second document**. Generate a stable ID **before starting the request**, reuse it across all retries, and reconcile existing contents before assuming success.

### 13.3. `timeout` Stops Waiting in the Pipeline, Never Undoes MongoDB

~~~java
Mono<WriteJob> boundedWait = repository.insert(job)
    .timeout(Duration.ofSeconds(3));
~~~

Once 3 seconds pass, Reactor cancels the subscription and emits a timeout. Yet **the in-flight write may already have reached the primary and committed/replicated**. Never report “not written” solely from `TimeoutException`.

Endpoints can return `202 Accepted / processing` or a reconcilable status per contract, reserving `201 Created` for confirmed acknowledgments.

### 13.4. `$inc` and Non-Idempotent Updates

~~~java
Mono<com.mongodb.client.result.UpdateResult> decrementStock(
        String productId, int amount) {
    return reactiveMongoTemplate.updateFirst(
        Query.query(Criteria.where("id").is(productId)),
        new Update().inc("stock", -amount),
        ProductStock.class
    );
}
~~~

**Never** blindly retry this workflow after a timeout: retrying as a fresh operation deducts stock **twice** if the first write succeeded.

Instead, store a **unique reservation ID**, enforce state/version guards, or maintain a ledger/transaction per operation so retries check prior application before mutating again.

### 13.5. Retries Do Not Replace Source Throttling

If 8 in-flight writes fail due to driver connection pool timeouts, retrying all 8 immediately creates a **retry storm**. Combine:

- Exponential backoff + jitter (only when safe to retry).
- Max attempts and deadline caps.
- Instance-wide concurrency limits.
- Circuit breakers/bulkheads when the cluster degrades.
- Idempotency and reconciliation.
- Metrics for retries, latency, and error labels.

## 14. MongoDB Transactions: Operations Sharing a Session Must Be Sequential

This is the **most important concurrency boundary**.

> The MongoDB Java Reactive Streams Driver **does not support running multiple operations concurrently within the same transaction**. Spring Data's `ReactiveMongoTransactionManager` binds a `ClientSession` to Reactor Context; sharing that context does **not** make `flatMap(..., 8)` or `Mono.when(...)` safe inside a transaction.

### 14.1. Anti-Pattern: Concurrent Writes Inside a Transaction

~~~java
// DO NOT DO THIS:
Mono<Void> invalid = Flux.fromIterable(commands)
    .flatMap(command -> repository.insert(toDocument(command)), 8)
    .then()
    .as(transactionalOperator::transactional);
~~~

Inner Publishers share one transactional session from Reactor Context and fire concurrently, violating driver constraints and causing session/transaction errors or unsupported behavior.

### 14.2. Right Way When All Items Must Commit/Abort Together

~~~java
Mono<Void> atomicBatch = Flux.fromIterable(commands)
    .concatMap(command -> repository.insert(toDocument(command)))
    .then()
    .as(transactionalOperator::transactional);
~~~

`concatMap` completes each write before subscribing to the next. `TransactionalOperator` wraps the entire chain in the reactive transaction context when repositories/templates share the reactive database factory.

**However**, a giant transaction across 100,000 commands is poor design: resource consumption, snapshot retention, and timeout risks climb. Keep atomic batches reasonably small or scope transactions per aggregate.

### 14.3. Running Multiple **Separate** Transactions Concurrently

Suppose many independent orders each need two **sequential** atomic writes:

~~~java
Mono<Void> processOneOrderAtomically(OrderCommand command) {
    return updateOrder(command)
        .then(insertOutbox(command))
        .as(transactionalOperator::transactional);
}

Flux<Void> jobs = Flux.fromIterable(orderCommands)
    .flatMap(command -> processOneOrderAtomically(command), 4);

Mono<Void> allDone = jobs.then();
~~~

Each inner subscription opens **its own transaction** provided **no outer transaction is active** (or propagation is configured explicitly). Up to four order workflows run concurrently, **while the two writes inside each transaction run sequentially**.

Note that `flatMap` over `Mono<Void>` emits no `onNext` values, only completion/error; `jobs.then()` awaits completion of all workflows. To emit per-order results, emit an `OrderOutcome` after commit rather than zipping `Mono<Void>`s.

### 14.4. Be Very Careful with Outer Transactions

If a caller adds:

~~~java
@Transactional(transactionManager = "reactiveMongoTransactionManager")
public Mono<Void> processAll(List<OrderCommand> commands) {
    return Flux.fromIterable(commands)
        .flatMap(this::processOneOrderAtomically, 4)
        .then();
}
~~~

the inner transactional operators **join the outer transaction** under default `PROPAGATION_REQUIRED`, causing concurrent writes inside one shared session. Never wrap an outer transaction when intending **separate per-item transactions**.

When isolation is required, configure transaction propagation explicitly, audit session/context lifecycles, and test thoroughly. Never raise concurrency blindly ignoring transaction boundaries.

### 14.5. Transactions and Per-Item Error Handling

Inside an atomic transaction, catching a failure on one item and mapping it to `WriteOutcome.CONFLICT` so the flow completes normally **inside the transactional operator** can cause prior writes in that transaction to commit unless the server already aborted.

Rules:

- For **all-or-nothing**: let errors propagate so the transaction aborts; never swallow errors inside the transaction boundary.
- For **per-item partial success**: do not wrap all items in one shared transaction; use separate small transactions or independent writes.
- For **retrying a transaction body**: check for `TransientTransactionError` and ensure the entire body is idempotent with no external side effects.
- For **retrying commit** on `UnknownTransactionCommitResult`: rely on driver/session commit-retry mechanics rather than re-running the body as a brand-new command.

## 15. Configuring Reactive Transactions in Spring

### 15.1. Transaction Manager Bean

~~~java
// ReactiveTransactionConfig.java
package com.example.reactivewrites;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.mongodb.ReactiveMongoDatabaseFactory;
import org.springframework.data.mongodb.ReactiveMongoTransactionManager;
import org.springframework.transaction.reactive.TransactionalOperator;

@Configuration
public class ReactiveTransactionConfig {

    @Bean
    ReactiveMongoTransactionManager reactiveMongoTransactionManager(
            ReactiveMongoDatabaseFactory factory) {
        return new ReactiveMongoTransactionManager(factory);
    }

    @Bean
    TransactionalOperator transactionalOperator(
            ReactiveMongoTransactionManager manager) {
        return TransactionalOperator.create(manager);
    }
}
~~~

MongoDB must run as a **replica set or transaction-capable sharded deployment**; standalone servers cannot run multi-document transactions. Ensure `ReactiveMongoTemplate` and repositories share the same `ReactiveMongoDatabaseFactory`.

### 15.2. Reactive Service Using `@Transactional`

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import reactor.core.publisher.Mono;

@Service
public class OrderWriteService {
    private final ReactiveMongoTemplate mongo;

    public OrderWriteService(ReactiveMongoTemplate mongo) {
        this.mongo = mongo;
    }

    @Transactional(
        transactionManager = "reactiveMongoTransactionManager"
    )
    public Mono<Void> approveAndPublish(OrderCommand command) {
        return updateOrder(command)
            .then(insertOutbox(command))
            .then();
    }
}
~~~

`updateOrder` and `insertOutbox` are reactive methods with concrete MongoDB commands defined in section 18. When `@Transactional` is intercepted **via a Spring proxy**, the transaction wraps the Publisher's subscription and commit/abort lifecycle—not just the Java method assembly call.

### 15.3. Never Call `subscribe()` Inside a Transactional Method

~~~java
// DO NOT DO THIS:
@Transactional
public Mono<Void> broken(OrderCommand command) {
    updateOrder(command).subscribe();    // Chain detached from transaction.
    insertOutbox(command).subscribe();   // No explicit ordering.
    return Mono.empty();
}
~~~

Inner `subscribe` calls create separate subscribers/contexts disconnected from the returned Publisher's completion and errors. Even if the DB happens to write, the transaction interceptor cannot manage those writes as one unit. **Always return a single fully composed publisher**.

### 15.4. Never Call `block()` on the WebFlux Event Loop

~~~java
// DO NOT DO THIS on a reactive thread:
// reactiveMongoTemplate.insert(job).block();
~~~

`block()` stalls threads and risks starvation; adding `Schedulers.boundedElastic` recklessly will not fix transaction/reactive context propagation either. Use `then`, `flatMap`, and reactive transaction operators/managers.

### 15.5. Cancellation and Commit Ambiguity

If a client disconnects while a transaction is committing, Publisher cancellation **does not prove MongoDB aborted**. The commit may finish even though the client missed the ACK. High-value workflows require stable IDs and status reconciliation rather than equating HTTP disconnect with rollback.

## 16. Designing Concurrency Scope by Business Level

### 16.1. Three Typical Tiers

~~~text
LEVEL A: within one aggregate
  -> sequential / conditional update / small transaction.

LEVEL B: across independent aggregates
  -> bounded flatMap(..., N).

LEVEL C: whole instance / multi-instance cluster
  -> bounded ingress, queue/consumer concurrency, quotas, metrics.
~~~

A Level B `flatMap(..., N)` does not replace Level C bounds. A Level A transaction does not serialize unrelated orders.

### 16.2. Practical Decision Checklist

Before picking an operator, answer:

1. If writes A and B arrive out of order, does business state break?
2. If A succeeds and B fails, is that partial state acceptable?
3. If a command retries after a timeout, could it double-apply?
4. Do operations share a `ClientSession` / transaction?
5. How many requests/consumers run **concurrently across the whole system**?
6. If MongoDB slows down 10x, how large will queues and heap grow?
7. Does the caller expect responses in **input order**, completion order, or doesn't care?

### 16.3. Recommendation Matrix

| Characteristic | Preferred Design |
| --- | --- |
| Independent inserts, unique keys | `flatMap(insert, N)`, bounded ingress |
| Response must match input order while writes stay independent | `flatMapSequential(insert, N)` |
| Same document, ordered state transitions | Per-key `concatMap` + atomic condition |
| Write 2 depends on write 1 | `flatMap`/`then` |
| All writes must commit/abort together | Transaction + **sequential operators** |
| Two independent writes must both finish | `Mono.when`, accepting partial failure |
| Need values from two independent writes | `Mono.zip` with non-empty `Mono<T>`s |
| High-volume single collection | `buffer` + `template.insert`/`bulkOps` |
| Bulk operations allowing partial failures | Per-item outcome reporting + idempotency |
| Many tenants/jobs/processes | Global queues, partitions, admission control |

### 16.4. Concurrency Is an Operational Setting, Not a Hardcoded Constant

Externalize concurrency settings into properties:

~~~properties
app.mongo-write.max-in-flight-per-worker=8
app.mongo-write.batch-size=200
app.mongo-write.active-batches=2
~~~

These are **custom application properties**, not built-in Spring Data MongoDB keys. Bind and validate them via `@ConfigurationProperties` with sane min/max bounds; passing `0` or huge values to operators does not self-heal.

## 17. End-to-End Example: Independent Import with Per-Item Outcomes

An app accepts a stream of `WriteCommand`s, writes up to eight concurrently, preserves **input order in responses**, and classifies duplicates as existing vs conflict.

### 17.1. Complete Import Service

~~~java
// WriteImportService.java
package com.example.reactivewrites;

import java.time.Instant;
import java.util.Objects;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class WriteImportService {
    private final WriteJobRepository repository;

    public WriteImportService(WriteJobRepository repository) {
        this.repository = repository;
    }

    public Flux<WriteOutcome> importIndependent(
            Flux<WriteCommand> commands) {
        return commands.flatMapSequential(
            this::insertOrReconcile,
            8
        );
    }

    private Mono<WriteOutcome> insertOrReconcile(
            WriteCommand command) {
        return Mono.defer(() -> {
            validate(command);

            WriteJob desired = new WriteJob(
                command.id(),
                command.tenantId(),
                command.payload(),
                "NEW",
                Instant.now()
            );

            return repository.insert(desired)
                .map(saved ->
                    WriteOutcome.inserted(saved.getId()))
                .onErrorResume(
                    DuplicateKeyException.class,
                    error -> repository.findById(command.id())
                        .map(existing -> sameRequest(
                            existing, command)
                                ? WriteOutcome.existing(command.id())
                                : WriteOutcome.conflict(command.id()))
                        .switchIfEmpty(Mono.just(
                            WriteOutcome.unknown(command.id())))
                );
        });
    }

    private static boolean sameRequest(
            WriteJob existing, WriteCommand command) {
        return command.tenantId().equals(existing.getTenantId())
            && Objects.equals(
                command.payload(), existing.getPayload());
    }

    private static void validate(WriteCommand command) {
        if (command == null ||
                command.id() == null || command.id().isBlank() ||
                command.tenantId() == null ||
                command.tenantId().isBlank()) {
            throw new IllegalArgumentException(
                "id and tenantId are required");
        }
    }
}
~~~

This uses `WriteJobRepository` and `WriteOutcome` from sections 3 and 12, capping **concurrency at 8** for independent inserts while `flatMapSequential` keeps response ordering aligned with input.

**Explicit scope limits:** this demo omits authorization, max request sizes, global admission control, transient network/write-concern retries, and full request fingerprinting. `Instant.now()` also shifts across retries; if timestamps belong to fingerprints, carry a stable timestamp from the original request. This is not a copy-paste production endpoint.

### 17.2. Why Does `validate` Live Inside `Mono.defer`?

`Mono.defer` ensures validation and entity instantiation occur when each inner Publisher subscribes, avoiding synchronous side effects during mapper invocation. Validation exceptions become **reactive `onError`** signals on the inner flow.

If validation failures should produce a per-item `REJECTED` outcome without aborting the stream, define `REJECTED` and handle **only that specific validation exception**—never convert arbitrary framework `IllegalArgumentException`s indiscriminately.

### 17.3. WebFlux Controller Accepting Streaming Requests

~~~java
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/imports")
public class WriteImportController {
    private final WriteImportService service;

    public WriteImportController(WriteImportService service) {
        this.service = service;
    }

    @PostMapping(
        path = "/jobs",
        consumes = MediaType.APPLICATION_NDJSON_VALUE,
        produces = MediaType.APPLICATION_NDJSON_VALUE
    )
    public Flux<WriteOutcome> importJobs(
            @RequestBody Flux<WriteCommand> commands) {
        // Streaming contract: each item can be written independently.
        // Ingress quotas/authorization must be enforced at the gateway/service.
        return service.importIndependent(commands);
    }
}
~~~

**This streaming endpoint allows partial progress**, not an atomic batch, and lacks quotas/security. To enforce **“over 500 items means zero items written,”** count/validate input **before subscribing to writes** (e.g., materialize up to 501 items and reject beforehand, backed by gateway byte/request limits). Derive the tenant from the security context rather than trusting a body field.

In streaming endpoints allowing partial progress, document clearly that earlier items persist even if later items fail quota—meaning **the response is not an atomic batch**.

### 17.4. Safer Batch Controller Validating Count Before Writing

~~~java
@PostMapping(path = "/jobs/batch")
public Mono<java.util.List<WriteOutcome>> importBatch(
        @RequestBody Flux<WriteCommand> commands) {

    return commands.take(501).collectList()
        .flatMap(all -> {
            if (all.size() > 500) {
                return Mono.error(
                    new IllegalArgumentException(
                        "Maximum 500 commands"));
            }
            // Start writing ONLY AFTER checking the batch size.
            return service.importIndependent(
                Flux.fromIterable(all)
            ).collectList();
        });
}
~~~

This method is an **alternative** inside the same controller, not an endorsement of unbounded `collectList`. It buffers at most 501 commands at this layer, though you still need **max request bytes**, HTTP timeouts, and clear overload handling. And remember: checking size beforehand **still does not make the writes atomic**; the service still writes items independently with possible partial success.

## 18. Small Transaction Example: Updating Order and Inserting Outbox Sequentially

Each order approval executes two writes requiring atomicity. Different orders can run concurrently in **separate transactions**, while each transaction executes **sequentially**.

### 18.1. Self-Contained Domain Model

~~~java
// OrderCommand.java
package com.example.reactivewrites;

public record OrderCommand(
    String id,
    String tenantId
) {}
~~~

~~~java
// OrderDocument.java
package com.example.reactivewrites;

import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "orders_reactive_011")
public class OrderDocument {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    private String state;

    protected OrderDocument() {}

    public OrderDocument(
            String id, String tenantId, String state) {
        this.id = id;
        this.tenantId = tenantId;
        this.state = state;
    }

    public String getId() { return id; }
    public String getTenantId() { return tenantId; }
    public String getState() { return state; }
}
~~~

~~~java
// OutboxEvent.java
package com.example.reactivewrites;

import java.time.Instant;
import org.springframework.data.mongodb.core.mapping.Document;
import org.springframework.data.mongodb.core.mapping.Field;
import org.springframework.data.mongodb.core.mapping.FieldType;
import org.springframework.data.mongodb.core.mapping.MongoId;

@Document(collection = "outbox_reactive_011")
public class OutboxEvent {
    @MongoId(FieldType.STRING)
    private String id;

    @Field("tenant_id")
    private String tenantId;

    @Field("order_id")
    private String orderId;

    private String eventType;
    private Instant createdAt;

    protected OutboxEvent() {}

    public OutboxEvent(
            String id, String tenantId, String orderId,
            String eventType, Instant createdAt) {
        this.id = id;
        this.tenantId = tenantId;
        this.orderId = orderId;
        this.eventType = eventType;
        this.createdAt = createdAt;
    }

    public String getId() { return id; }
    public String getOrderId() { return orderId; }
}
~~~

### 18.2. Reactive Service with `TransactionalOperator`

~~~java
// ReactiveOrderWorkflow.java
package com.example.reactivewrites;

import java.time.Instant;
import java.util.List;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class ReactiveOrderWorkflow {
    private final ReactiveMongoTemplate template;
    private final TransactionalOperator transactions;

    public ReactiveOrderWorkflow(
            ReactiveMongoTemplate template,
            TransactionalOperator transactions) {
        this.template = template;
        this.transactions = transactions;
    }

    public Mono<Void> approveOne(OrderCommand command) {
        return Mono.defer(() -> {
            Query pending = Query.query(
                Criteria.where("id").is(command.id())
                    .and("tenantId").is(command.tenantId())
                    .and("state").is("PENDING")
            );

            Mono<Void> update = template.updateFirst(
                pending,
                new Update().set("state", "APPROVED"),
                OrderDocument.class
            ).flatMap(result -> {
                if (result.getMatchedCount() != 1) {
                    return Mono.error(
                        new IllegalStateException(
                            "Order not eligible"));
                }
                return Mono.<Void>empty();
            });

            Mono<Void> outbox = Mono.defer(() ->
                template.insert(new OutboxEvent(
                    "approved:" + command.id(),
                    command.tenantId(),
                    command.id(),
                    "OrderApproved",
                    Instant.now()
                )).then()
            );

            return update
                .then(outbox)
                .as(transactions::transactional);
        });
    }

    public Mono<Void> approveManyIndependent(
            List<OrderCommand> commands) {
        // Call from a place with NO outer transaction.
        return Flux.fromIterable(commands)
            .flatMap(this::approveOne, 4)
            .then();
    }
}
~~~

**What exactly is guaranteed?**

- Inside each inner flow, `update` finishes before `outbox` is subscribed.
- `TransactionalOperator` manages commit/abort for **that flow** when it starts its own transaction.
- `approveManyIndependent` allows up to four **order transaction flows** concurrently.
- If one flow errors, the error propagates and cancels sibling flows. **Already-committed sibling transactions do not roll back**.
- The method requires callers **not to wrap it in an outer reactive transaction**, which would merge all four into one shared session.

If the requirement is “all orders in the list commit or roll back together,” **never** use `approveManyIndependent`: run a single transaction with **sequential** operations over a bounded list, or revise the business contract.

### 18.3. Why Not Insert the Outbox Using `Mono.when`?

Wrong:

~~~java
// Violates ordering and can violate same-session transaction limits.
return Mono.when(
    updateOrder(command),
    insertOutbox(command)
).as(transactions::transactional);
~~~

If the order update doesn't match, the outbox insert can still execute; furthermore, inside a transaction the driver forbids parallel operations on the same session. Right way:

~~~java
return updateOrder(command)
    .then(insertOutbox(command))
    .as(transactions::transactional);
~~~

Never call detached `subscribe()` or `parallel()` inside a transaction.

## 19. Observing Pipeline Performance and Health

### 19.1. Key Metrics

| Metric | Purpose |
| --- | --- |
| Active inner write subscriptions | Shows how many pipeline writes are currently in flight |
| Acknowledged writes/sec | Real acknowledged write throughput |
| Latency p50/p95/p99 | Spots tail latency, journal/replication stalls |
| MongoDB connection pool checked-out/waiting | Detects pool saturation |
| Retry count, duplicate key count | Separates data conflicts from transient errors |
| Write concern errors/timeouts | Tracks cluster durability and availability |
| Buffer/queue depth | Flags backlogs and OOM risks |
| Partial success / `UNKNOWN` outcomes | Measures reconciliation workload |
| Transaction commit/abort/conflict rates | Measures contention in atomic workflows |
| Secondary lag / write ticket pressure | Pinpoints MongoDB server bottlenecks |

Never look solely at WebFlux pod CPU. A low-CPU service can still flood MongoDB wait queues and send p99 soaring.

### 19.2. Measuring In-Flight Subscriptions at the Reactive Layer

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

Flux<WriteJob> output = commands.flatMap(
    command -> Mono.defer(() -> {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        return writeOne(command)
            .doFinally(signal -> active.decrementAndGet());
    }),
    8
);
~~~

This counts **subscribed inner Publishers**, not exact MongoDB server threads, sockets, or disk I/O. In production, export metrics via Micrometer using low-cardinality tags (never tag with unbounded order or tenant IDs).

### 19.3. Never Watch Per-Request Counts Ignoring Concurrent Requests

Creating a new `AtomicInteger` per HTTP request measures only that single request. To observe pressure **across the entire service instance**, use shared meters/limiters with clear lifecycles alongside connection pool and MongoDB server stats.

### 19.4. Benchmarking Options on Representative Data

Compare:

~~~text
A: concatMap, concurrency = 1
B: flatMap, concurrency = 4
C: flatMap, concurrency = 8
D: flatMap, concurrency = 16
E: buffer(200) + 2 active bulk requests
~~~

Hold workload, document size, index count, write concern, topology, and input volume constant; record **throughput, p95/p99, CPU, RAM, pool wait, DB latency, and error rate**. Raising concurrency often increases throughput up to a knee and degrades beyond saturation.

Never compare benchmarks run on an empty unindexed database against production setups with unique indexes, `majority` writes, and secondary lag.

## 20. Unit-Testing Operators with `StepVerifier` Before Touching MongoDB

Pure Reactor tests verify inner concurrency bounds, ordering, and error propagation without stressing MongoDB—followed by real MongoDB integration tests for persistence behavior.

### 20.1. Verifying `flatMap` Does Not Exceed Concurrency

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveOperatorConcurrencyTest {

    @Test
    void flatMapLimitsActiveInnerPublishers() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        Flux<Integer> writes = Flux.range(1, 12)
            .flatMap(number -> Mono.defer(() -> {
                int now = active.incrementAndGet();
                maximum.accumulateAndGet(now, Math::max);

                return Mono.delay(Duration.ofMillis(25))
                    .map(tick -> {
                        // Only use error-free Mono.delay in unit tests:
                        // decrement counter BEFORE emitting onNext/completion.
                        active.decrementAndGet();
                        return number;
                    });
            }), 3);

        StepVerifier.create(writes.collectList())
            .assertNext(result -> {
                assertThat(result).hasSize(12);
                assertThat(result).containsExactlyInAnyOrder(
                    1, 2, 3, 4, 5, 6,
                    7, 8, 9, 10, 11, 12
                );
            })
            .verifyComplete();

        assertThat(maximum.get()).isLessThanOrEqualTo(3);
    }
}
~~~

This tests **active inner Publishers** on simulated publishers, not MongoDB. Because the test uses an error-free `Mono.delay`, it decrements the counter right before emission to avoid race assertions after terminal signals. On real Publishers that can error or cancel, clean up in `doFinally`/Micrometer as in section 19.2. Never rigidly assert `maximum == 3` in case CI scheduling stalls; assert that the cap is never exceeded.

### 20.2. Testing `concatMap` Order Preservation

~~~java
@Test
void concatMapKeepsSourceOrder() {
    Flux<Integer> flow = Flux.just(1, 2, 3)
        .concatMap(i ->
            Mono.delay(Duration.ofMillis(20L * (4 - i)))
                .thenReturn(i)
        );

    StepVerifier.create(flow)
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

Each inner Publisher subscribes only after the previous one completes. Even though 1 delays longer than 3, output stays `1, 2, 3`.

### 20.3. Testing `flatMapSequential` Output Order Without Assuming Write Order

~~~java
@Test
void flatMapSequentialKeepsEmissionOrder() {
    Flux<Integer> flow = Flux.just(1, 2, 3)
        .flatMapSequential(
            i -> Mono.delay(
                    Duration.ofMillis(20L * (4 - i)))
                .thenReturn(i),
            3
        );

    StepVerifier.create(flow)
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

This proves **emission order** only. Even though item 3 finishes before item 1, Reactor holds 3 until its turn. Never treat this test as proof that three writes to the **same document** executed sequentially.

### 20.4. Testing That Errors Do Not Equal Rollback

~~~java
@Test
void oneErrorStopsStreamButDoesNotUndoOtherEffects() {
    java.util.List<Integer> completed =
        new java.util.concurrent.CopyOnWriteArrayList<>();

    Flux<Integer> flow = Flux.just(1, 2, 3)
        .concatMap(i -> {
            if (i == 2) {
                return Mono.<Integer>error(
                    new IllegalStateException("item 2 failed"));
            }
            return Mono.just(i)
                .doOnNext(completed::add);
        });

    StepVerifier.create(flow)
        .expectNext(1)
        .expectError(IllegalStateException.class)
        .verify();

    assertThat(completed).containsExactly(1);
}
~~~

This simulates in-memory side effects, showing item 1 completed before item 2 failed; it **does not** simulate MongoDB rollbacks or `flatMap` network races. Real persistence requires MongoDB integration tests.

## 21. Integration Testing Against Real MongoDB

Unit tests mocking `ReactiveMongoRepository` cannot verify field mapping, unique indexes, write acknowledgments, bulk failures, or transaction sessions. Run integration tests against a dedicated test MongoDB or Testcontainers instance.

### 21.1. Test Prerequisites

- Dedicated test MongoDB, never production.
- Spring Boot with the reactive MongoDB starter, Reactor Test, and test framework.
- Entities and repositories within context scan scope.
- Isolated fixture IDs/tenants and scoped cleanup after tests.
- Avoid parallel tests colliding on the same keys/collections without isolation.
- For transactions, run a **replica set**; a single-node replica set verifies basic commit/abort, though not multi-node failover.
- Create required collections and indexes **before** starting transactions.

### 21.2. Testing Concurrent Independent Inserts

~~~java
package com.example.reactivewrites;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;
import java.util.stream.IntStream;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

@DataMongoTest
class ConcurrentMongoWritesTest {
    private static final String TENANT = "it-reactive-011";

    @Autowired WriteJobRepository repository;
    @Autowired ReactiveMongoTemplate template;

    @AfterEach
    void cleanup() {
        Query scope = Query.query(
            Criteria.where("tenantId").is(TENANT)
        );
        StepVerifier.create(
            template.remove(scope, WriteJob.class)
                .then()
        ).verifyComplete();
    }

    @Test
    void insertsIndependentJobsWithBoundedConcurrency() {
        List<WriteJob> docs = IntStream.range(0, 12)
            .mapToObj(i -> new WriteJob(
                "it-rw011-" + i,
                TENANT,
                "payload-" + i,
                "NEW",
                Instant.parse("2026-11-01T00:00:00Z")
            ))
            .toList();

        StepVerifier.create(
            Flux.fromIterable(docs)
                .flatMap(repository::insert, 3)
                .collectList()
        )
          .assertNext(saved -> {
              assertThat(saved).hasSize(12);
              assertThat(saved)
                  .extracting(WriteJob::getId)
                  .containsExactlyInAnyOrderElementsOf(
                      docs.stream()
                          .map(WriteJob::getId)
                          .toList()
                  );
          })
          .verifyComplete();

        StepVerifier.create(
            template.count(
                Query.query(
                    Criteria.where("tenantId").is(TENANT)
                ),
                WriteJob.class
            )
        )
          .expectNext(12L)
          .verifyComplete();
    }
}
~~~

**What this proves:** all 12 writes were acknowledged and exist under the right tenant in the test DB. It **does not directly measure** in-flight network requests; combine with section 20.1's `AtomicInteger` test and driver metrics to verify operator concurrency.

### 21.3. Testing Partial Success Without a Transaction

Add to the same class:

~~~java
@Test
void duplicateAfterFirstInsertDoesNotUndoFirstInsert() {
    String id = "it-rw011-duplicate";

    WriteJob first = new WriteJob(
        id, TENANT, "first", "NEW", Instant.now()
    );
    WriteJob duplicate = new WriteJob(
        id, TENANT, "different", "NEW", Instant.now()
    );

    // concatMap makes test execution order deterministic.
    StepVerifier.create(
        Flux.just(first, duplicate)
            .concatMap(repository::insert)
    )
      .assertNext(saved ->
          assertThat(saved.getPayload()).isEqualTo("first"))
      .expectError(
          org.springframework.dao.DuplicateKeyException.class
      )
      .verify();

    // The document from the first insert still exists.
    StepVerifier.create(repository.findById(id))
        .assertNext(saved ->
            assertThat(saved.getPayload()).isEqualTo("first"))
        .verifyComplete();
}
~~~

Without an enclosing transaction, the second item's duplicate-key failure **does not undo** the first item. This is why batch imports need explicit partial-progress and idempotency contracts.

### 21.4. Integration Testing Reactive Transaction Commit and Abort

Using `ReactiveTransactionConfig` and `ReactiveOrderWorkflow` from sections 15 and 18:

~~~java
package com.example.reactivewrites;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.mongo.DataMongoTest;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.data.mongodb.core.ReactiveMongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

@DataMongoTest
@Import({
    ReactiveTransactionConfig.class,
    ReactiveOrderWorkflow.class
})
class ReactiveOrderTransactionTest {
    private static final String TENANT = "it-tx-reactive-011";

    @Autowired ReactiveMongoTemplate template;
    @Autowired ReactiveOrderWorkflow workflow;

    private Mono<Void> ensureCollections() {
        return template.collectionExists(OrderDocument.class)
            .flatMap(exists -> exists
                ? Mono.<Void>empty()
                : template.createCollection(OrderDocument.class).then()
            )
            .then(template.collectionExists(OutboxEvent.class)
                .flatMap(exists -> exists
                    ? Mono.<Void>empty()
                    : template.createCollection(OutboxEvent.class).then()
                )
            );
    }

    private Mono<Void> clearFixture(String id) {
        Query order = Query.query(Criteria.where("id").is(id));
        Query event = Query.query(
            Criteria.where("id").is("approved:" + id)
        );

        return template.remove(order, OrderDocument.class)
            .then(template.remove(event, OutboxEvent.class))
            .then();
    }

    @Test
    void commitsOrderAndOutboxTogether() {
        String id = "it-tx011-commit";

        Mono<Void> scenario = ensureCollections()
            .then(clearFixture(id))
            .then(template.insert(new OrderDocument(
                id, TENANT, "PENDING"
            )))
            .then(workflow.approveOne(
                new OrderCommand(id, TENANT)
            ));

        StepVerifier.create(scenario).verifyComplete();

        StepVerifier.create(
            template.findById(id, OrderDocument.class)
        )
          .assertNext(order ->
              assertThat(order.getState())
                  .isEqualTo("APPROVED"))
          .verifyComplete();

        StepVerifier.create(
            template.findById("approved:" + id, OutboxEvent.class)
        )
          .expectNextCount(1)
          .verifyComplete();

        StepVerifier.create(clearFixture(id)).verifyComplete();
    }

    @Test
    void duplicateOutboxAbortsOrderStateChange() {
        String id = "it-tx011-abort";

        Mono<Void> prepare = ensureCollections()
            .then(clearFixture(id))
            .then(template.insert(new OrderDocument(
                id, TENANT, "PENDING"
            )))
            .then(template.insert(new OutboxEvent(
                "approved:" + id,
                TENANT, id, "PREEXISTING",
                Instant.parse("2026-11-01T00:00:00Z")
            )))
            .then();

        StepVerifier.create(prepare).verifyComplete();

        StepVerifier.create(workflow.approveOne(
            new OrderCommand(id, TENANT)
        ))
          .expectError(DuplicateKeyException.class)
          .verify();

        StepVerifier.create(
            template.findById(id, OrderDocument.class)
        )
          .assertNext(order ->
              assertThat(order.getState())
                  .isEqualTo("PENDING"))
          .verifyComplete();

        StepVerifier.create(
            template.findById("approved:" + id, OutboxEvent.class)
        )
          .assertNext(event ->
              assertThat(event.getOrderId()).isEqualTo(id))
          .verifyComplete();

        StepVerifier.create(clearFixture(id)).verifyComplete();
    }
}
~~~

Rollback test behavior: the transaction updates the order to `APPROVED` inside the session and then tries to insert a colliding outbox `_id`; the second write fails, aborting the transaction so **the order remains `PENDING`**. The preexisting outbox stays untouched because it was inserted **before the transaction**.

**Conditions to reproduce cleanly:**

- The test DB is a transaction-capable replica set.
- All operations inside `approveOne` use the reactive template bound to the factory/session managed by `TransactionalOperator`.
- Collections exist prior to starting the transaction.
- Fixtures are isolated from concurrent tests.
- Transaction write concern and driver settings align; `expectError` may need adjusting if a Spring Data version wraps duplicate errors differently, though **persisted state** is the essential check.

### 21.5. Limits of Integration Tests

A single-node replica set verifies basic **atomic commit/abort**, yet does not test:

- Elections, failover, and rollbacks under weak write concerns.
- Multi-node `majority` durability.
- Connection pool saturation across 30 instances.
- Races across distributed workers.
- Bulk behavior on 1 million documents under real load.

Test those with dedicated benchmarks and chaos tests in an authorized staging environment—never on production or shared test instances.

## 22. Common Pitfalls

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `Flux<Mono<WriteJob>>` with no writes | Used `map` producing nested Publishers | `flatMap`/`concatMap` |
| Service returns success before writes finish | Called `subscribe()` manually and returned early | Return the composed Publisher to the caller |
| `flatMapSequential` outputs in order, yet DB state is wrong | Only orders downstream emission | Serialize per-key writes / conditional updates |
| Updates to the same order execute out of order | `flatMap` interleaves inner streams | Per-key `concatMap`, version guards |
| `Mono.when(insert, update)` causes update to miss | Dependent operations subscribed concurrently | Chain dependency with `then`/`flatMap` |
| `Mono.zip(Mono<Void>, Mono<Void>)` emits nothing | Both sources complete empty | Use `Mono.when` when only completion matters |
| Pipeline fails yet some documents persisted | Errors never roll back independent writes | Report partial outcomes / idempotency, or use transactions |
| Assuming cancellation equals rollback | MongoDB may already have processed in-flight writes | Record `UNKNOWN` and reconcile |
| Retrying after timeout duplicates documents | Fresh ID generated per attempt | Keep stable ID + request fingerprint |
| Retrying `$inc` applies twice | Non-idempotent update | Use reservation/ledger/state guard before retrying |
| `N = 8` yet DB still sees 500 concurrent writes | `8` bounds one pipeline, not concurrent requests/pods | Global admission/consumer concurrency caps |
| `onBackpressureBuffer()` causes OOM | Unbounded buffer | Bounded queue and explicit overflow policy |
| `limitRate` doesn't relieve MongoDB congestion | Shapes demand only, not DB capacity | Tune concurrency, load, and queue bounds |
| `parallel()` fails to speed up Mongo writes | Reactive I/O doesn't benefit from CPU parallel threads | Profile DB/pool; use bounded `flatMap` |
| `flatMap(..., 8)` in a transaction throws session error | Driver forbids parallel ops in one transaction | Use `concatMap`/`then` inside transactions |
| Outer reactive transaction + inner `flatMap` transactions fail | Inner flows join shared outer session | Avoid outer transaction; configure propagation/session scope |
| `UNORDERED` bulk leaves partial data | Unordered is not atomic | Report per-item outcomes and retry safely |
| Bulk skips entity lifecycle callbacks | Bulk uses different lifecycle semantics than repository `save` | Consult docs for your API version |
| Unbounded `groupBy` hangs on millions of keys | High cardinality + low outer concurrency | Use bounded partitions or keyed queues |
| Client disconnects leaving uncertain writes | Cancellation ≠ guaranteed undo | Idempotency and reconciliation |
| Transaction test fails on standalone MongoDB | Transactions require replica set / sharded cluster | Run a test replica set |
| Mock unit tests pass yet DB writes fail | Mocks lack real constraints and transactions | Add real MongoDB integration tests |

## 23. Checklist for Designing a Reactive Write Pipeline

1. **Classify the write:** independent, ordered per key, or transactional together.
2. **Pick operators by semantics**, not guessing “`flatMap` is faster.”
3. **Use `concatMap` for dependencies and ordering**, especially inside transactions.
4. **Use `flatMap(..., N)`** with bounded concurrency for independent writes.
5. **Use `flatMapSequential` only for source-ordered output**, never to enforce DB write ordering.
6. **Never execute concurrent operations inside one MongoDB transaction**.
7. **Run separate transactions concurrently** only when no outer transaction shares a session.
8. **Keep IDs and idempotency keys stable** across all retries.
9. **Separate duplicate, conflict, unknown outcome, and fatal system errors**.
10. **Never call `subscribe()` or `block()` inside WebFlux services**.
11. **Enforce instance-wide and ingress limits**, not only single-`Flux` concurrency.
12. **Consider batch/bulk for large volumes**, bounding batch size and active batches.
13. **Never mistake batching or unordered bulk for atomicity**; handle partial success.
14. **Bound backpressure queues explicitly** rather than buffering infinitely in heap.
15. **Match write concerns and timeouts to business needs**, remembering timeouts/cancels never undo server writes.
16. **Include tenant and state/version checks in queries**, never relying on local ordering as a distributed lock.
17. **Measure pool wait, p95/p99, retries, and backlog** before increasing N.
18. **Test ordering, concurrency, and errors with `StepVerifier`**.
19. **Test unique indexes, partial success, and transaction rollbacks against real MongoDB**.
20. **Verify client-disconnect and consumer-rebalance paths** to preserve reconciliation.

## 24. Practice Exercises and Answers

### Exercise 1 — Pick an Operator for 20 Independent Inserts

You have 20 `WriteCommand`s with distinct `_id`s that can write independently. You want at most four operations in flight and don't care about response order.

**Answer:**

~~~java
Flux<WriteJob> written = Flux.fromIterable(commands)
    .flatMap(c -> repository.insert(toDocument(c)), 4);
~~~

### Exercise 2 — Preserving Input Order in Output

Still 20 independent inserts, yet the report must preserve command order.

**Answer:** Use `flatMapSequential(mapper, 4)`. It preserves **emission order** without serializing database writes.

### Exercise 3 — Two Updates on the Same Order

Update A transitions `PENDING → APPROVED`, and update B transitions `APPROVED → SHIPPED`. Can `flatMapSequential` guarantee A hits the DB before B?

**Answer:** No. Use per-order `concatMap` or `A.then(B)` and check expected state in the update filter. `flatMapSequential` only orders returned emissions.

### Exercise 4 — Two Writes in One Transaction

An order update and an outbox insert must commit or abort together. Is `Mono.when` valid?

**Answer:** No. Within the same MongoDB transaction, the driver does not support parallel writes; chain sequentially with `update.then(insert).as(tx::transactional)`.

### Exercise 5 — Multiple Independent Transactions

You have 50 independent orders, each performing two sequential writes inside its own transaction. Can four orders run concurrently?

**Answer:** Yes, provided no outer transaction is active and each inner flow opens its own session/transaction:

~~~java
Flux.fromIterable(orderCommands)
    .flatMap(cmd -> processOneOrderAtomically(cmd), 4)
    .then();
~~~

### Exercise 6 — Outer Transaction Hazard

If the outer method also carries reactive `@Transactional` and calls `flatMap(cmd -> processOneOrderAtomically(cmd), 4)`, what can happen?

**Answer:** Inner flows can join **the same outer transaction** under `REQUIRED`, running concurrent writes inside one shared session—which the driver does not support. Configure propagation and session scopes properly.

### Exercise 7 — `zip` with `Mono<Void>`

You want to wait for two value-less writes to complete. Use `Mono.zip(monoVoidA, monoVoidB)` or `Mono.when`?

**Answer:** `Mono.when`. `zip` expects every source to emit a value; `Mono<Void>` completes without emitting values, causing unexpected empty completion.

### Exercise 8 — Partial Failure

`flatMap(insert, 8)` hits a duplicate key on one item. Could other items already be inserted?

**Answer:** Yes. Fail-fast and cancellation never roll back independent writes already processed by MongoDB. Report outcomes and enforce idempotency, or use a transaction if atomicity is required.

### Exercise 9 — `onErrorResume` at the End

Why can `flux.flatMap(write, 8).onErrorResume(e -> Flux.empty())` be dangerous?

**Answer:** It hides errors, drops per-item failure reporting, and lets the API return completion even though partial writes exist in the DB. Handle classified errors **per item** or surface explicit failed/unknown job status.

### Exercise 10 — Retrying with a Fresh ID

The first insert hits a socket timeout, and the retry generates a new UUID. What is the risk?

**Answer:** The first attempt may have persisted; the second creates a duplicate document. Keep a stable business ID and reconcile.

### Exercise 11 — `$inc`

An inventory decrement using `$inc: -1` times out. Should you immediately retry it as a new operation?

**Answer:** Not by default. The first attempt may already have applied; use a reservation/ledger ID, state guard, or transaction with clear semantics before retrying.

### Exercise 12 — Batch Choice

You have 100,000 small documents for one collection. Choose between `flatMap(insert, 1024)` and `buffer(200)` + bulk with bounded active batches.

**Answer:** Try **bounded batching/bulk** and measure. Arbitrary concurrency 1024 can saturate pools, spike RAM, and hurt p99. Never assume bulk is always faster without benchmarking real data.

### Exercise 13 — `UNORDERED`

An unordered bulk operation hits a duplicate key on one document. Are all documents rolled back?

**Answer:** No. Other operations may still succeed; unordered mode is not a multi-document transaction.

### Exercise 14 — Keyed `groupBy`

Why can `source.groupBy(orderId).flatMap(g -> g.concatMap(write), 8)` fail on millions of keys in an unbounded stream?

**Answer:** Unbounded groups retain state and buffers; unconsumed groups stall or backpressure the stream when outer concurrency is low. Use bounded partitions or cardinality-controlled queues.

### Exercise 15 — Backpressure

Does `limitRate(64)` guarantee at most 64 active MongoDB writes across the system?

**Answer:** No. It shapes upstream demand requests; write concurrency requires `flatMap(..., N)` and ingress controls across all pipelines and instances.

### Exercise 16 — `parallel()`

`ReactiveMongoRepository` already returns non-blocking `Mono`s. Do you need `parallel().runOn(Schedulers.parallel())` to “truly run concurrently”?

**Answer:** No. Bounded `flatMap` already keeps multiple non-blocking I/O operations in flight without a CPU parallel scheduler. Profile bottlenecks before adding schedulers.

### Exercise 17 — Cancellation

A client sends 200 commands and disconnects HTTP after 100 results. Are the remaining 100 commands guaranteed not to be written?

**Answer:** No. Writes already in flight may have reached the server and committed/replicated. API contracts must expose job IDs and reconciliation.

### Exercise 18 — Testing Concurrency

A `StepVerifier` test observes 12 emitted items. Does that prove concurrency N never exceeded 3?

**Answer:** Not yet. Measure peak active inner subscriptions using an `AtomicInteger` in tests or appropriate metrics; observing 12 final items says nothing about peak concurrency.

### Exercise 19 — Testing Transactions

To prove an order update and outbox insert roll back together when the outbox `_id` collides, what must the test do?

**Answer:** Use a **test replica set**, seed the colliding outbox first, subscribe to the transactional service, expect the error, and **read the order back** verifying it stayed `PENDING` while the preexisting outbox remained unchanged.

### Exercise 20 — Picking `N = 8`

One pod serves 40 concurrent HTTP requests, each running `flatMap(write, 8)`. Roughly how many inner writes can be active in the pod?

**Answer:** Around **320** if every request has enough items and no shared admission control exists. While that doesn't mean 320 sockets, it shows why N bounds one pipeline rather than capping the whole pod or cluster.

## Reference Documentation

- [Project Reactor — Which Operator Do I Need?](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html): choosing `flatMap`, `concatMap`, `flatMapSequential`, `then`, `when`, `zip`, `collectList`.
- [Project Reactor — `Flux` API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `flatMap(mapper, concurrency)`, `flatMapSequential`, `concatMap`, `groupBy`, `bufferTimeout`, and backpressure behavior.
- [Project Reactor — Error Handling](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `onErrorResume`, `retryWhen`, `onErrorContinue`, and error propagation.
- [Project Reactor — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, virtual time, and Publisher verification.
- [Spring Data MongoDB — Reactive MongoDB Support](https://docs.spring.io/spring-data/mongodb/reference/mongodb/reactive-mongo.html): reactive repositories/template, I/O, and Publisher composition.
- [Spring Data MongoDB — Saving, Updating, and Removing Documents](https://docs.spring.io/spring-data/mongodb/reference/mongodb/template-crud-operations.html): reactive inserts, batches, `bulkOps`/`bulkWrite`, mapping, and lifecycle differences.
- [Spring Data MongoDB — Client Sessions & Transactions](https://docs.spring.io/spring-data/mongodb/reference/mongodb/client-session-transactions.html): `ReactiveMongoTransactionManager`, `TransactionalOperator`, session/transaction context.
- [Spring Data MongoDB — `ReactiveMongoTemplate` API](https://docs.spring.io/spring-data/mongodb/docs/current/api/org/springframework/data/mongodb/core/ReactiveMongoTemplate.html): `insert`, `updateFirst`, `bulkOps`, and reactive transaction operations.
- [MongoDB Java Reactive Streams Driver — Transactions](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/crud/transactions/): **parallel operations are not supported within one transaction**, session and commit semantics.
- [MongoDB Java Reactive Streams Driver — Write Data](https://www.mongodb.com/docs/languages/java/reactive-streams-driver/current/write/): insert/update/bulk APIs and Publisher contracts.
- [MongoDB Manual — Bulk Write Operations](https://www.mongodb.com/docs/manual/core/bulk-write-operations/): ordered/unordered semantics and partial completion.
- [MongoDB Manual — Transactions](https://www.mongodb.com/docs/manual/core/transactions/): atomicity, isolation, and operational constraints.
- [MongoDB Manual — Retryable Writes](https://www.mongodb.com/docs/manual/core/retryable-writes/): retryable-write behavior and topology requirements.
- [MongoDB Manual — Write Concern](https://www.mongodb.com/docs/manual/reference/write-concern/): acknowledgment, majority/journal durability, timeouts, and unknown outcomes.
- [MongoDB Manual — Connection Pool Options](https://www.mongodb.com/docs/drivers/java/reactive-streams/current/connection/specify-connection-options/connection-pools/): pool capacity, max wait time, and latency under load.
