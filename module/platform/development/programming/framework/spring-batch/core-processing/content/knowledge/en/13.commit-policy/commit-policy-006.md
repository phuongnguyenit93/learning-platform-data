# Trade-off between small commits and large commits

In Spring Batch, a chunk-oriented step usually gathers multiple items into a chunk, reads and processes them, calls the writer, and then commits the transaction. The number of items gathered before each commit is usually configured with the **chunk size**, also called the **commit interval**. Choosing small or large commits directly affects throughput, lock hold time, memory usage, transaction cost, and recoverability when errors occur.

Small commits keep transactions short and limit the number of items that must be rolled back when a chunk fails. In return, the application has to perform more transactions and more commits. Large commits reduce the number of commits and can make better use of batch writes, but transactions run longer, hold resources longer, and may have to reprocess a larger group of items when an error occurs.

There is no single commit interval suitable for every job. The value should be chosen based on the data size, the characteristics of the reader/writer, the database, recovery requirements, and measurements on a representative workload.

## 1. Commit interval in chunk-oriented processing

With a chunk-oriented step, Spring Batch reads a group of items, passes each item through the processor if there is one, and then sends the output items to the writer. When the chunk completes successfully, the transaction is committed and the step starts the next chunk.

For example, with a chunk size of 100:

1. The reader reads at most 100 items for the current chunk.
2. The processor transforms or filters each item.
3. The writer writes the remaining output items.
4. If the chunk succeeds, the transaction commits.
5. The step continues reading the next group.

In Spring Batch 5, you can configure it with `StepBuilder`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, OrderRecord> processor,
        ItemWriter<OrderRecord> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, OrderRecord>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

The argument `100` is the commit interval. Older Spring Batch versions may use a different step configuration API, but the meaning of the commit interval remains the number of input items gathered in a chunk before the commit.

The last chunk can be smaller than the configured value when the reader runs out of data. In addition, the number of items the writer receives can be lower than the number the reader read because the processor can return `null` to filter an item or some items may be skipped according to policy.

## 2. What is a small commit?

A small commit means each transaction processes a relatively small group of items, for example 10, 25, or 50 items. If the chunk size is 20 and the job has 10,000 input items, with no filter or skip, the step will run about 500 chunks and about 500 successful commits.

```text
Chunk size = 20

Transaction 1:  item 1  - 20    -> COMMIT
Transaction 2:  item 21 - 40    -> COMMIT
Transaction 3:  item 41 - 60    -> COMMIT
...
Transaction N:  last item group -> COMMIT
```

Each transaction holds a small scope of work. When a chunk fails and must roll back, the uncommitted changes in that chunk are undone if they belong to the same transaction. Earlier chunks that have committed are kept.

### Benefits of small commits

**Shorter transactions.** The database holds locks and transaction resources for a shorter period. This can reduce lock wait time and reduce the likelihood of multiple large transactions contending for the same data.

**Limited rollback scope.** If the current chunk fails, only the group of operations not yet committed in that transaction is rolled back. With a small chunk, the amount of data to redo is usually smaller.

**More frequent checkpoints.** When a chunk commits successfully, Spring Batch can save metadata and reader state at the commit boundary. Small chunks create more progress-saving points, so the span of work that must be re-read after a failure is usually shorter.

**Less temporary data in memory.** The reader and processor usually only need to hold the group of items being processed. Small chunks can reduce the object volume and temporary data that must be held in the heap.

**Suited to writes with variable latency.** If the writer has occasional long writes or the data has a high level of contention, small chunks can limit how long a transaction holds resources.

### Costs of small commits

**More commits.** Each transaction has the cost of starting, completing, synchronizing state, and communicating with the database. With a remote database, network latency and commit time can account for a significant share of the total job time.

**More metadata updates.** Spring Batch needs to update the step state and execution context at chunk boundaries. A chunk that is too small increases the number of metadata updates.

**Harder to take advantage of large batch writes.** Some writers and databases work more efficiently when they receive a group of many records. If the chunk is too small, the benefit of batch insert/update may shrink.

**More orchestration overhead.** For the same number of items, small chunks make the framework go through the transaction loop and chunk processing more times.

Committing item by item is an extreme case of the smallest commit. It can be useful when each item must be transactionally independent, but it usually creates a lot of overhead if the workload could be written in groups.

## 3. What is a large commit?

A large commit means each transaction covers a relatively large group of items, for example 500, 1,000, or 5,000 items. With 10,000 items and a chunk size of 1,000, if there is no filter or skip, the step only needs about 10 chunks instead of 500 chunks with size 20.

```text
Chunk size = 1,000

Transaction 1:  item 1      - 1,000  -> COMMIT
Transaction 2:  item 1,001  - 2,000  -> COMMIT
Transaction 3:  item 2,001  - 3,000  -> COMMIT
...
Transaction N:  last item group      -> COMMIT
```

Each commit completes a larger amount of work. This can improve throughput if the commit cost is significant and the target system supports batch writes.

### Benefits of large commits

**Fewer commits.** The fixed cost of a transaction and the round trip to the database is spread over more items. This is the clearest benefit when the database is remote or each commit has significant latency.

**Making use of batch writes.** The writer can send a large group of records in a single batch insert/update. Reducing the number of database calls can improve throughput.

**Fewer metadata updates.** Fewer chunks means fewer step state and checkpoint updates.

**Less orchestration overhead per item.** The framework processes fewer chunk units for the same data set.

### Costs of large commits

**Longer transactions.** Database locks and resources may be held longer. Long transactions can increase lock waits and deadlocks or affect online transactions that share the same data.

**Larger rollback scope.** If the writer fails near the end of a chunk, all operations in the chunk's transaction may be rolled back. A large group of items may have to be read and processed again.

**Higher memory usage.** The chunk holds more items before the writer completes. If each item has a large object graph or the processor creates a lot of temporary data, the heap and garbage collection pressure can increase.

**More pressure on the transaction log.** A large transaction can create a large volume of uncommitted changes, increasing the need for undo/redo or write-ahead log and affecting the database's recoverability. The details depend on the database management system.

**Easier to hit operational limits.** Large transactions can exceed the timeout, hold connections for a long time, increase resource wait time, or make the restart operation after a failure take longer.

## 4. Direct comparison of small and large commits

| Criterion | Small commit | Large commit |
|---|---|---|
| Number of commits | Many | Few |
| Transaction cost per item | May be higher | Usually lower when commit overhead is significant |
| Lock hold time | Usually shorter | May be longer |
| Rollback scope | Smaller | Larger |
| Distance between checkpoints | Shorter | Longer |
| Temporary data in memory | Usually less | May be more |
| Ability to use batch writes | May be limited if too small | May be better if the writer/database supports it |
| Transaction log pressure | Many small transactions | Fewer transactions but each may be large |
| Potential to affect other workloads | May reduce lock duration | May increase contention if locks are held long |
| Suitable for | Contended data, large items, need for small rollbacks | Batch writes, high commit overhead, ample resources |

The observations above are common tendencies, not guarantees for every workload. For example, small commits do not automatically make the job faster if the database is limited by the number of round trips; large commits also do not automatically increase throughput if the transaction causes lock contention or GC pressure.

## 5. Example of calculating the number of commits

Suppose the job needs to process 100,000 input items and has no filter or skip. The number of chunks is approximately the total number of items divided by the chunk size, rounded up.

| Chunk size | Estimated number of successful chunks/commits |
|---:|---:|
| 10 | 10,000 |
| 50 | 2,000 |
| 100 | 1,000 |
| 500 | 200 |
| 1,000 | 100 |
| 5,000 | 20 |

Reducing the chunk size from 1,000 to 100 increases the number of transactions by about 10 times in this example. That does not mean the run time increases exactly 10 times, because the time to read, process, and write data also accounts for part of the total time. But if each commit has a large fixed cost, the difference can be significant.

Conversely, increasing the chunk size from 100 to 5,000 reduces the number of commits but each transaction has 50 times more uncommitted data. You need to make sure the database, memory, and transaction time can withstand that level.

If the processor filters items, the number of items the writer receives will be lower than the number of input items. However, the commit interval is usually based on the number of items read to create the chunk, not the number of items the writer successfully writes. Therefore, you should not use `writeCount` alone to infer exactly how many chunks ran.

## 6. Throughput trade-off

Throughput is the number of items processed per unit of time. Chunk size affects throughput through two groups of costs:

1. **Per-item cost:** reading data, performing business processing, converting objects, and writing each record.
2. **Per-chunk/transaction cost:** starting the transaction, committing, updating metadata, calling the writer, and synchronizing state.

When the chunk is too small, the per-chunk cost is repeated many times. As the chunk grows, this cost is spread over more items. Therefore, throughput usually improves as you raise the chunk size from a value that is too small to a reasonable level.

However, past a certain point, the benefit may level off or decline. The database may be limited by I/O, lock contention, the transaction log, or batch statement capability. The JVM may see longer GC pauses from holding more objects. At that point, increasing the chunk size no longer brings benefits.

You can picture the common trend:

```text
Throughput
   ^
   |                 _________
   |              __/         \_
   |           __/               \_
   |        __/
   |     __/
   |____/____________________________> Chunk size
       too small     suitable      too large
```

This is only an illustration. The actual curve may rise steadily, reach a plateau, or decline at different thresholds depending on the workload and the database.

## 7. Lock and concurrency trade-off

A large transaction can hold locks longer because many write operations are in a single transaction. If the job updates records that online applications also access frequently, a long lock hold time can increase request wait times.

With many workers or partitions running concurrently, the effect can be more pronounced:

- Large chunks make each worker hold its transaction longer.
- Workers may contend for the same table or the same key range.
- Deadlocks can occur if transactions lock resources in different orders.
- Small chunks can release locks more frequently but increase the number of concurrent transactions.

Therefore, you need to consider both chunk size and concurrency. Don't increase the number of workers and the chunk size at the same time without measuring, because it is very hard to determine which factor causes the contention.

If possible, partition the data so that each worker writes a non-overlapping range, for example by tenant, business date, or ID range. Even so, aggregate tables or shared locks can still become contention points.

## 8. Rollback and restart trade-off

Suppose a job processes 1 million transactions. After 900,000 items have been committed, the next chunk fails.

- With a chunk size of 100, the current transaction's scope is only about 100 items.
- With a chunk size of 5,000, the current transaction's scope can be up to 5,000 items.

If the writer uses database transactions correctly, the failed chunk's uncommitted operations are rolled back. Earlier committed chunks remain. On restart, Spring Batch uses the `JobRepository` and `ExecutionContext` to continue from the appropriate checkpoint if the reader supports saving state.

Small chunks create checkpoints more frequently, so the amount of work not yet checkpointed is usually smaller. Large chunks put checkpoints farther apart, so more items may need to be re-read and reprocessed after a crash.

However, restart does not mean every operation happens only once. The reader can re-read the items of an uncommitted chunk. The writer can be called again. If the writer sends requests to a system outside the transaction, you need an idempotency key, a unique business key, or a transactional outbox to avoid duplicate side effects.

A job with many committed chunks is not a single transaction spanning the whole job. If the job fails at chunk 900, the chunks committed earlier are kept. If the business requires publishing all results only when all data has been processed, you can write to a staging table and then perform a publish/swap step after the job completes.

## 9. Memory and garbage collection trade-off

Chunk size affects the number of objects held simultaneously. If each input item takes an average of 4 KB in the heap and the processor creates an equivalent output object, a chunk of 100 items can hold a significantly smaller amount of data than a chunk of 5,000 items.

This is only an intuitive estimate: object headers, collections, references, reader/writer buffers, temporary data, and caches can make the real footprint much larger. You also need to check whether the processor keeps references to items after processing.

A large chunk can increase:

- The number of input/output objects existing at the same time.
- The size of the collection the writer receives.
- The JDBC batch or serializer buffers.
- The frequency and duration of garbage collection if the heap is under pressure.

If items have a large payload, a chunk of 1,000 items can use far more memory than 1,000 small IDs. Measure the heap and GC on representative data; don't choose the chunk size based only on the item count.

## 10. Transaction log and database limits

The database needs to track a transaction's changes to support commit, rollback, and recovery after failures. Depending on the database management system, a large transaction can produce a significant amount of undo/redo or write-ahead log and hold data versions longer.

A transaction that is too large can:

- Increase the amount of log that is not released until the transaction ends.
- Make rollback take a long time.
- Put pressure on log storage or the replication mechanism.
- Hold locks and data versions longer.
- Create a longer recovery time after a failure.

Smaller commits spread changes across many transactions, but increase the number of commits and the number of transaction metadata records. You need to measure on the specific database, because each database management system has different ways of managing logs and optimizing transactions.

## 11. Choosing the chunk size by writer characteristics

Not every writer has the same characteristics.

| Writer type | What to consider |
|---|---|
| `JdbcBatchItemWriter` | Can benefit from a sufficiently large write group; balance against transaction duration and the driver's batch size |
| Writer calling a stored procedure | Time per call, the amount of data the procedure processes, and rollback capability |
| Writer creating a file | Buffers, output size, and whether the file write participates in the transaction |
| Writer calling a REST API | Network latency, rate limits, timeouts, and idempotency; a database transaction cannot roll back a request that has been received |
| Writer sending messages | The broker's transaction mechanism, outbox, and the possibility of duplicate sends |

With a JDBC writer, the chunk size and the driver's batch size can interact. For example, a chunk size of 1,000 does not guarantee that the driver sends exactly a single batch; the writer or driver can split the batch according to its own configuration.

With a writer that calls a remote API, don't choose a large chunk just to reduce the number of commits if each item still creates a separate request and the transaction is held while waiting on the network. Consider grouping requests via a batch API, separating the message-sending step, or using an outbox.

## 12. A process for choosing the commit interval

You can choose the chunk size following this experimental process:

### Step 1: Determine the operational requirements

Clarify the desired completion time, the maximum data volume, memory limits, transaction timeout, the level of impact on online systems, and restart requirements.

### Step 2: Choose a moderate starting value

Choose a value such as 100 or 500 as a baseline. This is only a starting point for measuring, not a default value that is right for every system.

### Step 3: Run on representative data

Use data with item sizes, error distribution, and contention levels close to production. A data set that is too small or completely clean may not reveal the real costs.

### Step 4: Measure the metrics

Record:

- Total job time and items/second.
- Average time and percentiles of each chunk.
- Commit time and number of commits.
- Heap usage, allocation rate, and GC pauses.
- Lock wait, deadlocks, connection pool usage.
- Transaction log growth and database load.
- `rollbackCount`, retry count, skip count, and recovery time when testing failures.

### Step 5: Try controlled increases/decreases

Try 50, 100, 250, 500, 1,000 in turn, or levels that suit the workload. Change only one factor at a time to know the cause of the effect. You don't necessarily need to try every value.

### Step 6: Choose according to practical limits

Choose the value that achieves the required throughput while staying within the limits of memory, transaction duration, lock wait, and recoverability. If two values have close throughput, it is usually better to prefer the value with shorter transactions and more predictable operation.

### Step 7: Test with controlled failures

In the test environment, simulate a writer failure in the middle of a chunk and confirm that rollback, checkpoint, restart, and idempotency work correctly. Good performance when there are no errors is not enough to prove that the commit interval is appropriate.

## 13. Example tuning for two workloads

### Workload A: data import with low contention using JDBC batch

A job imports 500,000 records into a staging table. The database is mainly dedicated to batch, the writer uses batch insert, and the items are small.

A chunk size of 500 or 1,000 can be a reasonable test point because it reduces the number of commits and takes advantage of batch writes. If you increase it to 5,000 and throughput does not improve but transaction duration, heap, or log growth increases, keep the smaller value.

### Workload B: updating account balances shared with an online system

A job updates the balances of accounts that online requests may also update. Lock contention is the main risk.

A chunk size of 50 or 100 can be an initial test point to limit lock hold time. However, if chunks that are too small cause high commit overhead, you need to measure and try a larger level. You may need to partition by account or arrange a stable write order to reduce contention.

The two examples show that with the same framework, the commit policy depends on the nature of the workload and the target system.

## 14. Commit policy and transaction timeout

Chunk size is not a time limit for the transaction. A chunk of 100 items can take a few milliseconds if the writer is fast, but it can also take several minutes if the processor or writer waits on an external service.

Transaction timeout is a separate configuration of the transaction manager/transaction attribute. You need to ensure that normal chunk processing time falls within the timeout limit with some margin, while also handling the case where a chunk hangs on I/O.

If chunks often hit the timeout:

- Measure the reader, processor, and writer time separately.
- Determine whether an API call or slow query is made inside the transaction.
- Reduce the chunk size if a group is too large.
- Optimize queries and batch writes.
- Configure the timeout to suit operational requirements, not just raise the timeout to mask a bottleneck.

Raising the transaction timeout without understanding the cause can make transactions hold locks longer and make incidents harder to recover from.

## 15. Small or large commits when there are retries and skips?

Retry and skip change the actual cost of a chunk.

When the writer fails and the whole chunk is retried, a large chunk may have to redo more work. When a fault-tolerant step needs to isolate a faulty item within a chunk, the framework can roll back and then call the writer multiple times with smaller groups. If the original chunk is large, the process of identifying the faulty item can take many trial writes.

Small chunks usually limit the number of items affected by one error, but if errors appear frequently, the number of retries and transactions also increases. Therefore, you should not optimize the commit interval based only on the success path; measure with the real error rate.

The skip policy also needs to be designed per error type. Don't use skip to hide database errors or configuration errors. For invalid data that can be skipped, you need to record the faulty item and monitor the skip count to ensure the business result is acceptable.

## 16. A committed chunk does not make the whole job atomic

A common misunderstanding is that if each chunk is protected by a transaction, the whole job will be all-or-nothing. In reality, each chunk is its own transaction. When chunk 100 fails, chunks 1 through 99 that have committed remain.

If the business accepts partial results and can restart, this is a suitable model. If the business requires publishing all data only when all steps complete, you can use:

- **Staging table:** write data to a temporary area, validate it fully, and then publish to the main table.
- **Versioned data:** write a new version and switch the version pointer when the job completes.
- **Swap/rename:** create the new output and then replace the output in use after confirming success.
- **Compensation:** if multiple systems cannot be rolled back, design compensating operations to restore the business state.

Don't try to hold a single transaction for millions of items just to achieve all-or-nothing if that makes the database and application unable to operate stably.

## 17. Principles to remember

- The commit interval is the number of input items gathered in a chunk before the transaction commits.
- Small commits create more transactions and checkpoints, reduce the rollback scope, and usually reduce lock hold time; in return they increase commit overhead and metadata updates.
- Large commits reduce the number of commits, can increase throughput and make use of batch writes; in return transactions are long, use more memory, and roll back more items.
- The chunk size is not necessarily equal to the number of items the writer writes, because the processor can filter and the step can skip items.
- The last chunk can be smaller than the commit interval when the reader runs out of data.
- Committed chunks still exist if a later chunk fails; a chunk-oriented job is not a single atomic transaction.
- Transaction timeout is a separate configuration; a small chunk can still run long if an item performs slow I/O.
- A writer outside the transaction needs idempotency or a coordinating mechanism such as an outbox to avoid duplicate side effects on retry/restart.
- Measure throughput, chunk latency, commit time, heap/GC, lock wait, transaction log, and rollback before choosing a value.
- Experiment with representative data and simulated failures to confirm both performance and recoverability.

Choosing the commit interval is a problem of balancing the cost of transactions against the cost of holding a large transaction. The right value is the one that meets the required throughput within the limits of memory, the database, and recovery time, while keeping rollback/restart behavior predictable.
