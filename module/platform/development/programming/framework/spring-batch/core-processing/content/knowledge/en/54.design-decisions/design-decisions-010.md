# Trading Off Throughput vs. Recoverability in Spring Batch

## 1. The Design Problem: Process Fast or Recover Easily?

A batch job must ingest millions of transactions during a nightly processing window. Increasing chunk size, batching SQL, and running multiple workers can make the job finish faster. However, if the JVM dies, a partition loses its connection, or a writer calling an external API times out, the system must know **what already completed, what must be reprocessed, and whether rerunning creates duplicate data**.

That is the trade-off between **throughput** (completing more work per unit time) and **recoverability** (resuming or recovering accurately after a failure). In Spring Batch, these two goals tie closely to commit intervals, transaction boundaries, `JobRepository`, `ExecutionContext`, `ItemStream`, retry/skip, idempotency, and concurrency.

```text
                        Batch Design
                             |
               +-------------+-------------+
               |                           |
      Increase throughput          Increase recoverability
               |                           |
       Fewer commits                  Frequent checkpoints
       Larger batch I/O               Shorter transactions
       Parallel processing            Immutable inputs
       Lower overhead                 Idempotent outputs
               |                           |
               +-------------+-------------+
                             |
                    Measure and choose
                  per SLA, failure risk,
                   actual replay cost
```

There is no single "fastest and always best-recovering" configuration for every workload. A job writing solely to one transactional database differs greatly from one calling payment APIs, exporting files to object storage, or coordinating multiple systems without a shared transaction.

**The goal of this lesson** is not to prescribe `chunkSize=100` or `chunkSize=1000`, but to establish a way to make decisions that are explainable, testable, and operable.

## 2. Metrics to Define Before Optimizing

| Metric | Question to Answer | How to Define |
|---|---|---|
| Throughput | How many units of work complete per second? | **Accepted/committed** records divided by actual runtime. |
| Makespan | How long does a batch take from start until results are usable? | Includes prep, processing, verification, and output publish. |
| RTO (*Recovery Time Objective*) | After an incident, how long at most to restore the job/service? | Error detection + investigation/decision + restart/replay + result verification. |
| RPO (*Recovery Point Objective*) | How much **unrecoverable** work loss is acceptable? | Defined by business rules, data sources, and reprocessability. |
| Replay window | On a crash, at most how much work may need re-execution? | Depends on commit interval, checkpoints, partitions, and side effects. |
| Duplicate tolerance | Is reprocessing the same input tolerable? | Defines idempotency/unique constraints or reconciliation mechanisms. |
| Failure rate | How frequently do incidents occur? | Measured from production, staging, or comparable workloads. |
| Per-item latency | How quickly must an individual item be visible/committed? | Driven by data freshness SLAs, not just whole-job throughput. |
| Cost | How much CPU, RAM, DB connections, and I/O can be spent? | Resource caps and impact on co-located systems. |

**RPO is not `chunkSize`.** With a durably stored immutable input source and a replay-safe writer, an uncommitted chunk may need reprocessing without causing **permanent data loss**. Conversely, a job triggering external side effects before saving checkpoints can leave ambiguous state even with chunk size 1.

In operations, keep these distinct:

- **Committed data:** outcomes durably confirmed by the target system.
- **Persisted checkpoint:** position/state a reader or writer can use on restart.
- **In-RAM processed data:** lost if the process crashes.
- **Out-of-transaction side effects:** may succeed even if batch metadata never recorded them.

When reporting throughput, pick a **consistent numerator**. `StepExecution.getReadCount()` reflects items reported read by the reader, `getWriteCount()` reflects framework item handling, and rows affected by custom SQL may differ. Processors returning `null` filter items; retries/skips repeat work. Never label every counter "committed records."

## 3. Where Does Spring Batch Persist Recovery State?

Spring Batch separates **business work** from **execution metadata**. With a JDBC `JobRepository`, metadata lives in the `BATCH_*` tables:

| Component | Role in Recovery |
|---|---|
| `JobInstance` | Logical job identity via job name and identifying `JobParameters`. |
| `JobExecution` | One run attempt of a job; restarts create a new execution under the same instance. |
| `StepExecution` | Step status, timings, and read/write/skip/commit/rollback counts. |
| Step-level `ExecutionContext` | State/checkpoints for readers, writers, or an active step. |
| Job-level `ExecutionContext` | Job-wide shared state, depending on design. |
| `ItemStream` | `open`, `update`, `close` contract to restore stateful reader/writer positions. |

```text
JobInstance(batchId=2026-11-16)
       |
       +-- JobExecution 501 -> FAILED
       |       |
       |       +-- StepExecution 801 -> FAILED, checkpoint A
       |
       +-- JobExecution 502 -> COMPLETED
               |
               +-- StepExecution 809 -> COMPLETED, resume from A
```

**Same `JobInstance` does not mean same `JobExecution`.** On a controlled restart after failure, the framework creates a new execution, checks completed steps, and reopens incomplete ones. `ExecutionContext` only helps if persisted properly and actually used by readers/writers. Code holding offsets in local variables loses them when the JVM dies.

The `BATCH_*` schema does not replace business tables, outboxes, or deduplication queues. A job with intact metadata but a non-idempotent writer still risks duplicates on restart.

## 4. What Trade-Offs Do Chunks, Transactions, and Checkpoints Create?

In a **chunk-oriented step**, Spring Batch reads and processes items, collects a chunk, passes it to the writer, and commits via `PlatformTransactionManager`. Example `chunk(100)`:

```text
Transaction / Chunk #1
  read + process items 1..100
  writer.write(chunk)
  ItemStream.update(executionContext)
  commit

Transaction / Chunk #2
  read + process items 101..200
  writer.write(chunk)
  ItemStream.update(executionContext)
  commit

Transaction / Chunk #3
  read + process items 201..300
  writer.write(chunk)
  -> crash before commit

After crash: results #1 and #2 committed; #3 may need replay.
```

In the standard model, the framework updates `ItemStream` state before commit so checkpoints align with the transaction boundary. **Atomicity between metadata and business data depends on transaction wiring and participating resources.** Never assume two separate databases or a writer calling HTTP will roll back together with `ExecutionContext`.

### 4.1. Small Chunks

Pros:

- Fewer in-flight items per transaction; usually less work to replay on a crash.
- Shorter row-lock hold times on database-write workloads.
- Smaller memory footprint for items buffered in a chunk.
- Completed items commit sooner, aiding low-latency freshness requirements.
- On an error late in a chunk, rollback and reprocessing scope is smaller.

Cons:

- Each tiny group pays full transaction begin/commit overhead repeatedly.
- JDBC batch writers cannot amortize batching well when chunks are too small.
- More frequent checkpoint/metadata updates, listener callbacks, and DB log flushes.
- Over millions of items, per-chunk logging itself can become a bottleneck.

### 4.2. Large Chunks

Pros:

- Amortizes transaction overhead over more items, often boosting throughput when fixed commit cost is high.
- Lets writers batch JDBC statements or bulk I/O.
- Fewer checkpoints/commits for the same input volume.

Cons:

- Long transactions, extended lock holds, and higher deadlock/timeout risk.
- More items and intermediate objects retained in memory; higher heap/GC pressure.
- On rollback or JVM crash, more uncommitted work must be reprocessed.
- Higher blast radius for replaying non-idempotent external side effects.
- Longer delay from reading an item until its output commits.

**A larger chunk does not automatically cut external API calls.** If a writer still makes one HTTP call per item, only Spring Batch's transaction count changes while HTTP call count stays virtually identical. Verify whether the writer actually supports bulk operations.

## 5. Quantitative Model: Throughput vs. Replay Cost

For a sequential workload assuming roughly steady per-item cost, an approximate estimator is:

\[
T_{run}(N,C) \approx N\,t_{item}
  + \left\lceil\frac{N}{C}\right\rceil t_{commit}
  + T_{startup} + T_{other}
\]

Where:

- `N` is the number of items to process.
- `C` is the chunk size.
- `t_item` is the average cost per item (read, process, write per model assumptions).
- `t_commit` is the relatively fixed per-chunk overhead (transaction, checkpoint, commit, partial round-trip).
- `T_other` captures remaining unmodeled time.

As **chunk size grows**, commit count roughly `ceil(N/C)` shrinks. Yet this formula is only intuitive: `t_item` and `t_commit` can shift with batch size, SQL payload size, caches, networking, locks, concurrency, and database behavior. They are **not true constants** across all values of `C`.

### 5.1. Example: 1 Million Items

Assume *for illustration* `t_item = 0.3 ms`, fixed per-chunk overhead `t_commit = 3 ms`, excluding other components:

| Chunk size C | Estimated chunks | Item cost | Fixed overhead | Estimated total |
|---|---:|---:|---:|---:|
| 1 | 1,000,000 | 300 s | 3,000 s | 3,300 s |
| 10 | 100,000 | 300 s | 300 s | 600 s |
| 100 | 10,000 | 300 s | 30 s | 330 s |
| 500 | 2,000 | 300 s | 6 s | 306 s |
| 2,000 | 500 | 300 s | 1.5 s | 301.5 s |

Here, jumping from 1 to 100 yields huge gains; jumping from 500 to 2,000 yields tiny arithmetic gains. If size 2,000 increases GC pauses, lock waits, or rollback work, real-world total runtime may actually be **slower** than 500.

### 5.2. Modeling Work to Replay After Failure

In a transaction of `C` items, if a crash strikes uniformly at random mid-chunk, completed-but-**uncommitted** work ranges from 0 up to nearly `C`. An intuitive approximation is:

\[
E[\text{items to replay per crash}] \approx \frac{C}{2}
\]

This assumption is **not a Spring Batch guarantee or statistic**. It only holds roughly when items take uniform time, crashes are independent of commit timing, and there are no complex retries/side effects. With huge files or slow outlier items, lost-work distributions can look totally different.

| Chunk size | Uncommitted work to replay (approx. bound) | Average assuming uniform mid-chunk crash |
|---|---:|---:|
| 10 | Up to ~10 items | ~5 items |
| 100 | Up to ~100 items | ~50 items |
| 500 | Up to ~500 items | ~250 items |
| 2,000 | Up to ~2,000 items | ~1,000 items |

For a job updating only the same transactional database, replay is mainly **lost time**. For a writer emitting external payments, messages, or files, replay creates **business risk** if those side effects occurred before a durable checkpoint committed. There, deduplication outweighs saving a few seconds of commit overhead.

### 5.3. Trade-Offs Must Include Failure Probability

A conceptual objective function is:

\[
E[T_{end\text{-}to\text{-}end}] \approx T_{run}
  + E[\text{number of failures}]\times
    (T_{detect} + T_{recover} + T_{replay})
\]

Never plug a guessed constant into `E[number of failures]`. On long jobs, crashes stem from OOMs, deadlocks, node evictions, remote API instability, or deploys; failure rates change with chunk size and concurrency. **Larger chunks can raise failure probability** by triggering OOMs or timeouts, so happy-path throughput alone cannot optimize expected completion time.

## 6. Finding a Suitable Chunk Size Range

For a new job, you can start probing values like `10, 50, 100, 250, 500, 1,000` depending on item size, DB, and SLAs. These are **suggested benchmark probes**, not Spring Batch rules.

Decision table:

| Workload Condition | Initial Leaning | What to Measure Before Choosing |
|---|---|---|
| Small items, JDBC batch writer, single transactional DB | Try medium/large chunks to cut commit overhead | DB round-trips, throughput, lock waits, checkpoint cost. |
| Large items, heavy intermediate data | Try small/medium chunks | Live heap set, GC pauses, OOM risk. |
| High data-error or retry rate | Avoid very large chunks up front | Rollbacks, retry calls, replay work, failure rate. |
| Writer calls external API per item | Prioritize idempotency and genuine API batching | Duplicate behavior, API latency/rate limits, failure ambiguity. |
| Strict low per-item latency SLA | Commit more frequently | End-to-end latency and DB load. |
| Running against a DB serving live OLTP traffic | Avoid long-locking transactions | p95/p99 lock waits, impact on OLTP. |
| File source not guaranteed immutable | Lock down snapshot/input before tuning | Checksum/object versions, restart tests. |
| Multi-worker partitioning | Tune jointly with concurrency and DB capacity | Total connections, contention, memory, partition skew. |

**How to decide:** pick the size that meets required throughput with **acceptable recovery cost**—not necessarily the single fastest run in one benchmark. If size 500 processes 10,000 items/s and size 2,000 processes 10,100 items/s while making rollbacks and restarts riskier, size 500 is the better operational choice.

## 7. Configuring Commit Interval in Spring Batch 5.x

Example with Java 17+, Spring Batch 5.2.x, and Spring Boot 3.x, using application-defined reader/processor/writer beans:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
class OrderBatchStepConfiguration {

    @Bean
    Step importOrdersStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<Order> orderReader,
            ItemProcessor<Order, NormalizedOrder> orderProcessor,
            ItemWriter<NormalizedOrder> orderWriter,
            @Value("${app.batch.import-orders.chunk-size:250}") int chunkSize) {

        if (chunkSize < 1) {
            throw new IllegalArgumentException("chunkSize must be positive");
        }

        return new StepBuilder("importOrdersStep", jobRepository)
                .<Order, NormalizedOrder>chunk(chunkSize, transactionManager)
                .reader(orderReader)
                .processor(orderProcessor)
                .writer(orderWriter)
                .build();
    }
}
```

This assumes `Order`, `NormalizedOrder`, and processing beans exist and use the right datasource/transaction manager. `app.batch.import-orders.chunk-size` is an **application-defined property** injected into the builder. In `application.yml`:

```yaml
app:
  batch:
    import-orders:
      chunk-size: 250
```

With this configuration, changing commit frequency does not automatically make `ItemReader` fetch more rows or alter the writer's SQL batch size. Fetch size, page size, JDBC batching, connection pools, and thread pools are separate tuning levers.

### 7.1. Avoid Changing Size Mid-Execution

Depending on design, changing configuration during a rollout or restart can affect checkpoints/replays. Record the chunk size used per execution in operational logs/metadata (allowed audit metadata) and maintain an explicit change policy. For critical restarts, test keeping the same config or intentional changes; never assume every reader/writer tolerates changing `chunkSize` between runs without side effects.

### 7.2. `commitInterval` Differs from `fetchSize` and `pageSize`

```text
chunkSize             -> items grouped per step transaction
JdbcCursor.fetchSize  -> hint to driver/database for row fetching
JdbcPaging.pageSize   -> rows per reader page
JDBC batch size       -> statements writer batches for executeBatch
partition gridSize    -> configured partition/worker task count
```

For example, a reader with `pageSize=1,000` in a step with `chunk(250)`: one reader page serves multiple chunks. That setup is valid when the sort key is stable, the reader supports state/restart, and the transaction manager is wired properly. Never force all numbers equal simply because they all end in *size*.

## 8. Proper Checkpointing: `ItemStream` and `ExecutionContext`

Stateful readers and writers must implement/honor the `ItemStream` contract:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

This signature **omits `throws`** for clarity; the real API throws `ItemStreamException`. `open` restores state, `update` writes state to the context, and `close` releases resources. In a standard step, Spring Batch manages this lifecycle once streams are properly registered.

Logical state after a committed chunk:

```text
input file revision: sha256:abc... (immutable)
reader checkpoint: 5000
business rows committed: 5000 (assuming no filter/skip)

Reader read further up to position 5200 when JVM crashed.

Restart: reopen checkpoint 5000, reprocess uncommitted portion.
```

**Checkpoints are meaningful only when the input source is reproducible.** An overwritten file, shifted paging row order, or non-unique query ordering can make an old offset point to different records. When that happens, even tiny chunks cannot save correctness.

### 8.1. File Readers

For `FlatFileItemReader`, consider:

- Give the reader/stream a unique `name` within the step to prevent context key collisions.
- `saveState=true` when progress persistence is needed and supported.
- Never swap files across restarts; record checksums/object versions or copy to immutable staging.
- Keep encoding, delimiters, schema version, and line-filtering rules fixed.
- If the reader is `@StepScope`, ensure identifying `JobParameters` resolve to the exact same file version.

### 8.2. JDBC Paging / Cursor

For paging readers, a unique and stable sort key prevents missing or duplicating records if the dataset mutates. If other services continuously insert/update the source, design a snapshot, cutoff ID, or claim/lease state. Large `pageSize` or small chunks do not automatically ensure snapshot consistency.

For cursor readers, cursor/connection durability depends on transaction isolation and the driver. If the process crashes, the in-RAM cursor vanishes; restart must re-execute the query and use the reader's state/reposition mechanism. Never treat a live database cursor as a durable checkpoint.

### 8.3. Delegate Streams

A `CompositeItemWriter` or custom reader wrapping an inner `ItemStream` delegate may require explicit registration with the step via `.stream(delegate)` if the framework cannot auto-detect nested streams. If the stream is never opened/updated, `ExecutionContext` will lack restart state even after chunks commit.

### 8.4. Stateless vs. Stateful Processors

A pure function processor `transform(input) -> output` replays cleanly because it holds no inter-item state. Processors using `AtomicLong`, mutable caches, or per-item external side effects create state that is hard to recover. When state is unavoidable, define how to persist and restore it, and handle re-invocations triggered by retries/rollbacks.

## 9. Transaction Boundaries: Committing in the Right Place Matters More Than Big Sizes

A simple model sharing **the same JDBC datasource and transaction manager**:

```text
Reader -> Processor -> JDBC Writer
               |         |
               +---- Transaction ----+
               |                     |
          business DB changes   checkpoint updates
               +---------- commit ---+
```

When all resources participate properly in one transaction, chunk rollback reverts both business DB changes and checkpoint updates to pre-commit state. However, sharing a datasource with `JobRepository` is not guaranteed by bean names alone; verify actual transaction, connection, and repository wiring.

### 9.1. Two Separate Datasources

If the writer writes to `businessDb` while metadata lives in `batchMetaDb`, a standard local transaction manager does not commit both atomically. A failure window exists:

```text
businessDb commit succeeds
           |
           X  process crash
           |
batchMetaDb has not saved new checkpoint
```

On restart, the reader may replay items whose business rows already committed. Safe designs require **idempotent writers, unique business keys, or reconciliation**, rather than assuming metadata and business DBs stay synchronized. Even if distributed transactions/XA are genuinely required, they carry operational costs and distinct failure modes—evaluate them architecturally rather than flipping a property.

### 9.2. Files, Object Storage, Messaging, and External APIs

A JDBC transaction cannot roll back an uploaded file, sent email, HTTP payment, or acknowledged broker message. Example:

```text
1. Processor receives order-42
2. Writer calls POST /payments with order-42
3. API returns success; remote side effect exists
4. JVM dies before checkpoint commits
5. Restart re-reads order-42
6. API called again -> risk of double impact
```

Here, **even chunk size 1 solves nothing**. You need a stable idempotency key honored by the target service, an outbox, or pre-replay status reconciliation.

### 9.3. Idempotent Output Is the Foundation of Recovery

PostgreSQL example using a unique key on `(business_date, order_id)`:

```sql
CREATE TABLE imported_order (
    business_date DATE NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    amount NUMERIC(14, 2) NOT NULL,
    PRIMARY KEY (business_date, order_id)
);

INSERT INTO imported_order (business_date, order_id, amount)
VALUES (:businessDate, :orderId, :amount)
ON CONFLICT (business_date, order_id)
DO NOTHING;
```

`DO NOTHING` is appropriate **only if business rules accept an already-existing record as complete**. If the same key arrives with a different `amount`, that is a data conflict requiring investigation—do not swallow it with `DO NOTHING`; compare values, use conditional updates, or raise a reconciliation error. Unique constraints stop duplicate inserts, not every form of workflow idempotency.

### 9.4. Outbox and Idempotent Consumers

When events must publish after database writes, use transactional outbox:

```text
Within the same business transaction:
  - Write business results
  - Write outbox(stable eventId, allowed payload)
Commit

Separate publisher:
  - Read outbox, emit message
  - Mark sent per safe rules

Consumer:
  - Deduplicate by eventId / idempotent processing
```

Outbox closes the inconsistency window between the business DB and event emission, though the publisher may still redeliver if it crashes after publishing before marking sent. **Consumers still need idempotency**; never promise absolute exactly-once from outbox alone.

## 10. Retry, Skip, and Rollback: Happy-Path Throughput Is Not Enough

Spring Batch supports fault-tolerant steps, retry, and skip where appropriate. When a chunk fails, the framework can roll back and reprocess part of the work. Larger chunks broaden the impacted work window, while actual retry attempts depend on exceptions, stateful retries, and writer behavior.

Spring Batch 5.x configuration example:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, NormalizedOrder>chunk(250, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

This is a configuration excerpt: `InvalidOrderException` is an application class; `TransientDataAccessException` is from Spring DAO. Real projects must classify exceptions precisely and test `skip/retry` across reader, processor, and writer phases rather than copying defaults. Retrying permanent errors simply wastes time with zero chance of success.

| Policy | Benefit | Cost / Risk |
|---|---|---|
| Retry transient errors | Avoids failing the whole job on brief glitches | Extends runtime, replays work, pressures failing services. |
| Exponential backoff | Prevents retry storms on overloaded external services | Increases elapsed time and recovery latency. |
| Skip isolated bad records | Keeps processing valid data | Can violate completeness rules if skip policy is flawed. |
| Fail fast on invalid schema/input | Protects data quality | Requires fixing input/contract before resuming. |
| Quarantine failing items | Preserves evidence for reconciliation | Needs dedicated storage, transactions, and idempotency. |

**A large skip limit does not mean better recoverability.** If a file has a broken schema, skipping millions of items and ending `COMPLETED` is a data failure even though the framework succeeded. Distinguish whole-input contract failures from isolated record defects.

### 10.1. Why Benchmark Failure Cases Too?

A job with 0% errors may fly at chunk size 2,000. Yet when 1% of records trigger retries or skips, large chunks roll back and re-invoke operations far more often, tanking throughput. When selecting chunk size, test both clean data and representative failing data.

## 11. Restart Semantics and Job Flow Design

Spring Batch normally skips `COMPLETED` steps when restarting the same `JobInstance`, unless `allowStartIfComplete(true)` is set. Incomplete steps must permit restarts and hold valid state.

Spring Batch 5.x example:

```java
@Bean
Job importJob(JobRepository jobRepository,
              Step validateInputStep,
              Step importOrdersStep,
              Step publishReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateInputStep)
            .next(importOrdersStep)
            .next(publishReportStep)
            .build();
}
```

| Step | Commonly Evaluated Policy | Reason |
|---|---|---|
| `validateInputStep` | Possibly `allowStartIfComplete(true)` if input immutability must be re-verified on every restart | Ensures unchanged input and valid schema/version. |
| `importOrdersStep` | Restartable, checkpointed reader and idempotent writer | Resumes unfinished portion. |
| `publishReportStep` | Typically runs once when results are ready; publish must be idempotent | Prevents emitting reports/files twice on crash restarts. |

`startLimit(n)` caps how many times a step may start; too low a limit can block a restart even when data is recoverable. `allowStartIfComplete(true)` must be chosen deliberately: it causes an already-completed step to **re-execute** on restart, making it unsafe for steps with non-idempotent side effects.

### 11.1. `JobParameters` Must Reflect One Logical Unit of Work

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("inputRevision", "sha256:example-fixed-revision", true)
        .addString("triggerSource", "scheduler", false)
        .toJobParameters();
```

The revision string above is illustrative. Identical identifying parameters map to the exact same logical job instance. Adding a fresh `run.id` on every failure just to bypass `JobExecutionAlreadyRunningException` or `JobInstanceAlreadyCompleteException` spawns a new instance, ignores checkpoints, and raises duplicate-import risk.

**Restart is not a fresh rerun from the beginning.** A completed job that must reprocess an entire input requires an explicit reprocessing workflow: result versioning, cleanup/reconciliation, idempotency, and business justification. Never conflate reprocessing with restarting a failed execution.

## 12. Concurrency: Adding Workers Does Not Automatically Improve Recovery

When a single-threaded step lacks throughput, consider multi-threaded steps, partitioning, or remote chunking. Each alters state scope and recovery risks.

### 12.1. Multi-Threaded Step

A step can execute chunks concurrently, provided readers, writers, and delegates are concurrency-safe. An `ItemReader` with a mutable cursor/state is unsafe across concurrent `read()` calls. `SynchronizedItemStreamReader` synchronizes reads in some setups, yet synchronization alone does not guarantee safe restart semantics under parallel execution: when items process and commit out of order, checkpoints may misrepresent completed work.

**Never share a mutable counter, buffer, or un-scoped MDC across concurrent step executions.** When state is necessary, define bean scopes and transaction boundaries explicitly.

### 12.2. Partitioning

Partitioning splits input into independent slices. Each worker typically owns its own `StepExecution` and `ExecutionContext`; if one partition fails, only that slice needs recovery per repository state.

```text
Manager step
    |
    +-- partition-0: IDs 1..100000     -> COMPLETED
    +-- partition-1: IDs 100001..200000 -> FAILED
    +-- partition-2: IDs 200001..300000 -> COMPLETED
```

For partitioning to genuinely boost recoverability:

- Each partition must cover a **disjoint** input range that remains deterministic on restart.
- Partitioned inputs must be immutable or pinned to a clear snapshot/cutoff.
- Worker writers must be idempotent, especially when message redelivery or worker crashes trigger re-execution.
- Avoid overly huge partitions (wide replay) or overly tiny partitions (high coordination overhead).
- Monitor aggregate throughput alongside DB connection pools, lock contention, and total worker memory.

### 12.3. Remote Chunking

Remote chunking dispatches chunks over messaging to remote worker processes. It can boost throughput while adding network boundaries, message acknowledgments, and redelivery edge cases. Examine broker delivery semantics, worker idempotency, and checkpoint commit rules. Never call remote chunking "exactly-once" merely because Spring Batch tracks `StepExecution`.

### 12.4. Amdahl's Law and Shared Bottlenecks

If 80% of time sits in a shared database writer and only 20% sits in a parallelizable processor, adding workers saturates quickly. Raising concurrency alongside large chunk sizes increases lock contention and DB connection starvation—worsening both recovery and throughput.

A sound benchmark varies **one dimension at a time**: optimize commit interval at fixed concurrency first, then test worker/partition counts, and finally validate under realistic production-like load.

## 13. Systems with Multiple Side Effects Need a Recovery Protocol

Suppose a job performs:

```text
read order -> normalize -> update database
                           -> send Kafka event
                           -> upload report to storage
```

Never bundle all three side effects inside one item writer expecting chunk transactions to roll everything back. A safer architecture separates:

1. **Ingest/stage** into a transactional database with unique business keys.
2. **Verify/validate** record counts, schemas, and totals; block publication if criteria fail.
3. **Publish** via outbox or a step using idempotency keys, atomic renames, or object versions.
4. **Reconcile** outcomes and persist durable publication state.

This separation may make single-job throughput look slightly lower due to extra verification steps, yet it **slashes incident recovery cost and severe data corruption**, raising overall SLA reliability.

### 13.1. Ambiguous Commit Outcomes on Network Failures

Sometimes the database commits right before the connection drops and before the app receives the ACK. If the framework treats the chunk as failed and retries, the writer receives the same items again. This underscores why unique keys, idempotency, and reconciliation are essential—never assume "no ACK received means DB did not commit."

### 13.2. Restarting After a Forced Kill

On normal handled Java exceptions, Spring Batch usually has a chance to persist `BatchStatus.FAILED`. When the JVM dies via `SIGKILL` or OOM-kill, the repository may still show `STARTED`; never blindly issue a restart. Verify the old process/worker is dead, inspect side effects and DB sessions, and follow **version-appropriate recovery procedures**.

In Spring Batch 6.x, `JobOperator.recover(JobExecution)` can recover an execution stuck in `STARTED` after an abrupt shutdown into a restartable state. In Spring Batch 5.x, resolving stuck executions requires controlled metadata handling per your version's docs. Never edit a single `STATUS` column with ad-hoc SQL, because `JobExecution`, `StepExecution`, exit status, optimistic lock versions, and contexts are interconnected.

Automated restarts should run only with **strong evidence** that no worker is alive and writers/idempotency are safe. An old `LAST_UPDATED` timestamp alone does not prove a job is dead; a long tasklet may not update metadata continuously.

## 14. Graceful Shutdown, Watchdogs, and Recoverability

On Kubernetes or host orchestrators, `SIGTERM` gives the application a window to shut down cleanly; `SIGKILL` skips JVM shutdown hooks entirely. `JobOperator.stop(...)` is a **cooperative stop request**, not an instant transition to `STOPPED`.

Example pod/container configuration with a grace period:

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: import-orders
spec:
  backoffLimit: 1
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 120
      containers:
        - name: batch
          image: example/import-orders:1.0
          resources:
            requests:
              memory: 512Mi
            limits:
              memory: 1Gi
```

Values are illustrative. A grace period only creates an **opportunity** for cleanup; it cannot make a chunk blocked on a 10-minute external API finish in 120 seconds. Once the grace period expires, the process is killed. Set bounded I/O timeouts, keep metadata in a persistent DB, wire readiness/termination hooks properly, and test stop procedures in staging.

**Kubernetes Job retries are not the same as Spring Batch job restarts.** A new Pod may boot with identical identifying parameters while the repository still shows `STARTED`. Using random IDs to force a fresh instance risks duplicate processing. Coordinate orchestration/scheduling and recovery across both layers.

## 15. Choosing Strategies by Workload Type

### 15.1. Ingestion Targeting a Single Transactional Database

Typical sensible strategy:

- Stable reader with stateful `ItemStream`.
- JDBC batch writer with unique business keys.
- Medium/large chunks if measurements confirm significant commit overhead.
- Consistent repository/transaction wiring verified.
- Restart tests executed after multiple committed chunks.

Here, throughput can take higher priority because replay is relatively cheap and side effects are primarily transactional.

### 15.2. Payments or Irreversible Operations

Typical sensible strategy:

- Target API idempotency keys or business-keyed ledgers.
- Never invoke irreversible side effects directly inside a long transaction without a confirmation protocol.
- Transaction/outbox/claim tables with reconcilable states.
- Backoff retries paired with explicit `PENDING`/`UNKNOWN` state handling.
- Small/medium chunk sizes shrink blast radius, though **never replace idempotency**.

Here, correctness and safe recovery outweigh marginal throughput gains.

### 15.3. Exporting Very Large Report Files

Typical sensible strategy:

- Write to temporary files or stably named multi-part segments.
- Checkpoint/manifest per segment, never publishing partial files.
- Once complete and verified, publish via atomic rename or object versioning as supported by storage.
- Chunk/segment size balancing memory, I/O throughput, and replay cost.

File appends do not roll back alongside DB transactions; specify truncate, resume, or regenerate behavior on restart. Never assume file `append` is exactly-once.

### 15.4. Historical Backfills

A multi-month backfill can partition by date or ID range, with independent outputs/idempotency per partition. Moderate partitions enable parallelism and isolated replays of failed slices. Ensure two workers never claim the same business date and source snapshots stay immutable.

### 15.5. Near-Real-Time ETL

If SLAs demand data visibility shortly after arrival, infrequent commits violate latency even when throughput is high. Use smaller chunks or item/time-bounded completion policies; benchmark p95/p99 latency rather than items/s alone.

## 16. Benchmarks Must Cover Recovery, Not Just the Happy Path

### 16.1. What Metrics Should You Capture?

| Group | Metric / Observation | Purpose |
|---|---|---|
| Throughput | Committed business rows/s, elapsed time, job duration | Measure real processing speed. |
| Batch counters | `readCount`, `writeCount`, `filterCount`, `skipCount` | Compare work volume and data quality. |
| Transactions | `commitCount`, `rollbackCount`, transaction duration | Observe overhead and retry/rollback frequency. |
| Resources | Heap, GC pauses, CPU, connection pool, I/O | Spot saturation as chunk/concurrency scales. |
| Database | Lock waits, deadlocks, query latency, log/fsync pressure | Measure load on DB and co-located apps. |
| Recovery | Detection time, restart delay, replay count, catch-up time | Evaluate real RTO under failures. |
| Correctness | Missing/duplicate records, wrong values, external side effects | Ensure performance never alters semantics. |
| Observability | Log events, metrics, correlation IDs | Sufficient forensic evidence without logging every item. |

In Spring Batch 5.x, inspect `StepExecution` stats after job completion:

```java
for (StepExecution step : jobExecution.getStepExecutions()) {
    System.out.printf(
            "step=%s status=%s read=%d write=%d "
                    + "commits=%d rollbacks=%d skips=%d%n",
            step.getStepName(),
            step.getStatus(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getCommitCount(),
            step.getRollbackCount(),
            step.getSkipCount());
}
```

This snippet assumes `JobExecution jobExecution` and `StepExecution` are imported. Never read an active object from an async `JobLauncher` and treat its counters as final; wait for completion or re-query the repository.

### 16.2. Suggested Benchmark Matrix

Test several chunk sizes on the same workload, then repeat across failure modes:

| Scenario | What to Observe | Conclusion to Draw |
|---|---|---|
| Happy path, single worker | Throughput, commit overhead | At what size do commit-reduction gains plateau? |
| 1% data errors | Retry/skip/rollback counts, elapsed time | Do large chunks inflate repeated work significantly? |
| Transient DB failures | Recovery time, backoff, deadlocks | Does the retry policy overload or respond too slowly? |
| Mid-chunk kill | Replay scope and committed data | Are checkpoints accurate and outputs idempotent? |
| Emit event/API then crash | Side-effect deduplication | Do ambiguous outcomes cause duplicate deliveries? |
| 4–8 partitions | Aggregate throughput, DB locks, RAM | Does concurrency genuinely scale or just add contention? |

Hold input, schema/indexes, JVM resources, transaction manager, connection pool, and log levels constant when comparing **chunk size alone**. Run warm-ups and multiple iterations, isolating benchmark changes from unrelated changes like new indexes or driver upgrades. On massive batches, benchmarking a few dozen items never reflects true commit scaling costs.

### 16.3. Choose by SLA Rather Than Naive Scores

Build a decision table:

| Option | Measured Throughput | Replay After Crash | Locks / Heap | Operational Assessment |
|---|---:|---|---|---|
| Chunk 50 | Lower | Small | Light | Fits if latency/recovery are top priorities. |
| Chunk 250 | Good | Moderate | Acceptable | Balanced candidate. |
| Chunk 1,000 | Slightly higher | Large | Potentially elevated | Pick only if gains matter and rollback/restart passed tests. |

Do not jump to conclusions from these labels; they are a **comparison frame**, and real numbers must be measured in a representative environment. For a payment system, a single duplicate transaction can be far worse than a job running a few minutes slower.

## 17. Testing Recoverability in Spring Batch

### 17.1. Controlled-Failure Integration Test

To verify restart semantics, use `@SpringBatchTest`, `@SpringBootTest`, `JobLauncherTestUtils`, a test datasource durable across the test lifecycle, and a processor/writer that intentionally fails after some chunks commit.

Procedure:

```text
1. Seed 1,000 immutable records into the test database.
2. Launch job with fixed businessDate and chunk size 100.
3. Let the first 2 chunks succeed; throw exception on chunk 3.
4. Verify first JobExecution is FAILED and committed output matches expectations.
5. Keep JobRepository and StepExecutionContext intact.
6. Disable failure injection and restart with identical identifying JobParameters.
7. Verify new JobExecution belongs to the same JobInstance.
8. Reconcile all 1,000 outputs: zero duplicates, zero omissions.
```

**Do not wipe metadata between the two launches** when testing restarts. Clearing metadata or supplying a new identifying `run.id` turns the test into running a separate instance. When filters/skips apply, compute expected output per business rules rather than assuming it equals `readCount`.

Assertion pattern (assuming job, launcher, and fixtures are configured):

```java
JobParameters params = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .addString("sourceRevision", "fixture-v1", true)
        .toJobParameters();

JobExecution failed = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.FAILED, failed.getStatus());

failureSwitch.disableFailure(); // Test-provided fault-injection switch.

JobExecution restarted = launcherTestUtils.launchJob(params);
assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
assertEquals(failed.getJobInstance().getInstanceId(),
             restarted.getJobInstance().getInstanceId());

// Add real DB assertions: exact record count, zero duplicates.
```

This is a **conceptual test pattern**: `failureSwitch` and job beans are supplied by the test. Whether the second `launchJob(params)` actually restarts depends on prior status and `JobRepository` config. When production uses `JobOperator.restart(...)`, test that operational API and its permissions too.

### 17.2. Separate-Process Crash Tests

Handled Java exceptions do not simulate `SIGKILL`. A realistic crash test should:

- Run the batch job in a **child process/container** separate from the JUnit runner JVM.
- Use a test database that persists across restarts; in-memory H2 inside the killed process will vanish.
- Wait for several chunks to commit, then kill the test process/container via orchestration tooling.
- Confirm the old process is dead and metadata may remain stuck in `STARTED`.
- Recover the execution following Spring Batch 5.x/6.x procedures.
- Restart with the same business identity and reconcile DB/file/API outputs.

Never invoke `Runtime.halt`, `System.exit`, or `kill -9` on the JVM hosting the test suite itself—that kills the test runner. For external side effects, explicitly test losing the success response after the remote system already executed it.

### 17.3. Independent Replay and Idempotency Tests

A unit/integration test can invoke the writer **twice with the exact same input** and assert final output is not doubled. This matters even when chunk checkpoints work. Add a case with the same business key but altered payload to verify whether the system catches conflicts or silently ignores new values.

### 17.4. Mutating-Source Tests

To protect reader restarts, run once, then modify the file or reorder paging input rows before restarting. The system should reject mismatched input revisions or preserve the original snapshot. If the job resumes at the old offset over mutated data, outputs can miss or duplicate records despite accurate metadata checkpoints.

## 18. Monitoring and Recovery Runbooks

A well-designed system helps operators detect issues early and recover safely—not merely try to make jobs "rarely fail."

Signals to monitor:

| Signal | Meaning |
|---|---|
| `jobName`, `jobInstanceId`, `jobExecutionId`, `stepExecutionId` | Distinguish individual runs and restarts. |
| Step `BatchStatus` and `ExitStatus` | Track execution outcomes and flow branches. |
| Read/write/filter/skip counts | Measure progress and data quality. |
| Commit/rollback counts | Spot transaction overhead and retry storms. |
| Last metadata update, heartbeats, worker liveness | Investigate stuck executions after crashes. |
| Heap/GC, DB locks, pool waits, queue backlogs | Separate oversized chunks from infra bottlenecks. |
| Writer duplicate/error counters | Track idempotency effectiveness and anomalous inputs. |
| Recovery time and retry/restart counts | Validate real-world SLOs/RTOs. |

After a crash, follow a runbook sequence:

1. Verify no worker/process is still processing the same input/partition.
2. Inspect `JobRepository` for `JobInstance`, executions, step statuses, and checkpoints.
3. Reconcile committed data and external side effects; identify ambiguous items.
4. Block overlapping scheduled runs and choose a controlled recovery action.
5. Recover stuck running metadata after a kill using version-appropriate procedures.
6. Restart **the exact same instance** and monitor to terminal status.
7. Reconcile outputs, handle any quarantine/duplicates, and document the incident.

**Never use a stale `LAST_UPDATED` timestamp as sole proof to auto-restart.** A step processing a huge chunk or blocked on I/O may not update metadata frequently while the process is still alive. Combine heartbeats, orchestrator liveness, and ownership checks.

## 19. Common Design Mistakes

| Symptom | Possible Cause | Remediation |
|---|---|---|
| Chunk size 1 yields very low throughput | Per-item commit/checkpoint; zero JDBC batching | Benchmark medium sizes; measure DB overhead and batch I/O. |
| Raising chunk from 250 to 2,000 adds zero speed | Commit savings saturated; bottleneck in processor/DB/network | Profile pipeline; pick stable plateau rather than max size. |
| Large size causes OOM / long GC | Retaining too many items/intermediate objects | Lower size, trim allocations, monitor live heap. |
| Job slows down with multiple workers | Lock contention, pool/DB saturation | Isolate concurrency benchmarks; tune partitions and transactions. |
| Restart inserts duplicate records | Non-idempotent writer or mutated source | Unique business keys, immutable inputs, reconciliation. |
| API called twice after network glitch | Side effect succeeded before checkpoint saved | API idempotency keys, outbox, or status reconciliation. |
| Job `FAILED` cannot restart | `preventRestart`, `startLimit`, invalid state, or another run active | Check flow config, statuses, and ownership. |
| Process killed while repo stays `STARTED` | No cleanup/metadata finalization callback ran | Verify process death; run version-specific recovery. |
| Job relaunched as a new instance instead of resuming | Adding random identifying `run.id`/timestamp to bypass errors | Preserve identifying business parameters and proper restart flow. |
| FlatFile reader resumes at wrong offset | File replaced or stream state unpersisted | Pin revision and configure `ItemStream`/`saveState` properly. |
| `COMPLETED` step reruns and resends emails | `allowStartIfComplete(true)` on a side-effecting step | Restrict policy or make publishing idempotent. |
| Retries amplify failure pressure | Retrying permanent errors or tiny backoffs | Classify exceptions, use exponential backoff, cap retries. |
| Throughput looks high yet data is missing | Measuring `readCount` instead of committed/reconciled output | Fix numerator and assert business outputs. |
| Exception tests pass, kill tests fail | Never tested crashes between commit and checkpoint or external side effects | Add separate-process crash tests with persistent DB. |
| Job auto-restarts while side effects remain unknown | Missing liveness checks and reconciliation | Block blind auto-retries; resolve ambiguous states first. |

## 20. Architectural Decision Framework

When designing a new job, ask these questions in order:

1. **Transaction scope:** does the writer target one DB, multiple DBs, or non-transactional services?
2. **Input immutability:** can the exact same byte/row snapshot be re-read after a restart?
3. **Output idempotency:** does running the same item twice still yield the right final state?
4. **SLA requirements:** what is the max job runtime and max recovery time after failure?
5. **Commit cost:** is transaction overhead actually a measured bottleneck?
6. **Replay tolerance:** how much uncommitted chunk work can be safely re-read/rewritten?
7. **Memory and database:** do large sizes breach heap, transaction timeouts, lock budgets, or JDBC limits?
8. **Bad data:** are retries/skips frequent? Is quarantine needed?
9. **Concurrency:** are partition boundaries stable and disjoint? Can a dead worker recover independently?
10. **Operations:** are there runbooks and real crash tests, or only happy-path integration tests?

If **inputs are unstable** or **writers are non-idempotent**, fix correctness before tuning chunk size or concurrency. Only after establishing a sound recovery protocol should you tune sizes for throughput within resource and RTO bounds.

### 20.1. Directional Guide, Not Rigid Rules

```text
Does the writer have external side effects?
    |
    +-- Yes -> Are idempotency/reconciliation in place?
    |            |
    |            +-- No  -> Redesign boundaries and outputs first.
    |            +-- Yes -> Benchmark sizes with failure scenarios.
    |
    +-- No  -> Is the input accurately replayable?
                 |
                 +-- No  -> Snapshot / pin revision first.
                 +-- Yes -> Benchmark commit interval and writer batching.

Then:
  - Measure throughput, locks, heap, errors/retries, replay time.
  - Pick a sweet-spot size and test restart with same JobInstance.
  - Validate the whole pipeline under realistic load/concurrency.
```

## 21. Practice Exercises

### Exercise 1 — Calculate Simple Model Trade-Offs

A job reads 2,000,000 items with an assumed 0.5 ms per-item cost and 5 ms/chunk commit overhead. Compute relative `T_run` for chunk sizes 1, 50, 200, and 1,000; estimate items replayed on a mid-chunk crash via `C/2`. Explain why the model omits GC/locking/retries and why you should not blindly pick the largest size from this table alone.

### Exercise 2 — Benchmark JDBC Writer

Build a step reading from staging, normalizing data, and writing to an output table with `JdbcBatchItemWriter`. Test sizes 10, 100, 250, and 500 on 100,000 items; record commit count, rows/s, heap, transaction waits, and p95 chunk duration. Build a comparison table, choose a balanced size, and justify it.

### Exercise 3 — Mid-Chunk Restart

Take a step with chunk size 250 and inject a failure on the third chunk after two chunks commit. Keep `JobRepository` and `ExecutionContext`, then restart with identical identifying parameters. Assert zero duplicate outputs, proper step resumption, and complete business keys.

### Exercise 4 — Out-of-Transaction Side Effects

Write a fake payment gateway that succeeds on the first call while returning a timeout to the client. Restart/retry the same input and observe the duplicate-charge risk. Add a stable idempotency key derived from the business transaction ID, verify zero duplicate charges, and assess how high chunk size can safely scale.

### Exercise 5 — Partitioning and Worker Crashes

Split one million items into four partitions with disjoint ID ranges; kill one worker mid-run in a separate process/container test. Confirm completed partitions do not rerun improperly, the failed partition resumes/replays safely, and final output has zero omissions or duplicates.

### Exercise 6 — Decision Record

Write a concise *architecture decision record* for a real job covering: throughput target, RTO/RPO, input type, transaction boundaries, idempotency strategy, benchmarked chunk size, tested failure scenarios, and runbook. Where measurements do not yet exist, mark items to verify rather than stating them as fact.

## 22. Principles to Remember

- **Throughput and recoverability are co-equal goals**—neither can be optimized via `chunkSize` alone.
- **Small chunks** pay higher transaction overhead while reducing uncommitted replay work and lock duration.
- **Large chunks** improve throughput when writers use batch I/O, yet increase heap usage, transaction duration, and replay blast radius.
- **Checkpoints must be durable and inputs replayable**; `ExecutionContext` cannot rescue mutated source data.
- **Idempotency determines replay safety**, especially when side effects fall outside Spring Batch transactions.
- **Retry, skip, and concurrency change performance dynamics**—benchmark failures and crashes, not just happy paths.
- **Restarting the same `JobInstance` differs from launching a new instance**; never add identifying `run.id`s to dodge old states while risking duplicates.
- **Real RTO** includes detection, recovery decisions, replay, and reconciliation; a job that runs faster on sunny days does not guarantee better RTO.
- **Pick a stable, benchmark-backed configuration** that preserves data integrity, eases troubleshooting, and meets end-to-end SLAs.

## 23. References

- [Spring Batch Reference — Chunk-oriented Processing](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing.html): item processing, chunking, and transaction model.
- [Spring Batch Reference — Commit Interval](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/commit-interval.html): transaction overhead and configuring commit intervals.
- [Spring Batch Reference — ItemStream](https://docs.spring.io/spring-batch/reference/readers-and-writers/item-stream.html): `open`, `update`, `close`, `ExecutionContext`, and checkpoints.
- [Spring Batch Reference — Configuring a Step for Restart](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/restart.html): `startLimit` and `allowStartIfComplete`.
- [Spring Batch Reference — Configuring Skip Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/configuring-skip.html): fault tolerance and skip behavior.
- [Spring Batch Reference — Retry Logic](https://docs.spring.io/spring-batch/reference/step/chunk-oriented-processing/retry-logic.html): retries in chunk processing.
- [Spring Batch Reference — Scaling and Parallel Processing](https://docs.spring.io/spring-batch/reference/scalability.html): multi-threaded steps, partitioning, and remote chunking.
- [Spring Batch Reference — Advanced Metadata Usage](https://docs.spring.io/spring-batch/reference/job/advanced-meta-data.html): `JobOperator`, statuses, and job operations.
- [Spring Batch 6.x API — JobOperator](https://docs.spring.io/spring-batch/reference/api/org/springframework/batch/core/launch/JobOperator.html): `recover` execution after abrupt shutdown in supported versions.
- [Spring Batch Reference — Monitoring and Metrics](https://docs.spring.io/spring-batch/reference/monitoring-and-metrics.html): job/step/chunk metrics and operational observability.

