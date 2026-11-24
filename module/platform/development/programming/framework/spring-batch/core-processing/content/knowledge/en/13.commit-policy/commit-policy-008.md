# Large commits reduce transaction overhead in Spring Batch

In chunk-oriented processing, Spring Batch gathers multiple items into a chunk and processes and commits them within the same transaction. The chunk size value (often called the commit interval) determines how many input items are processed before each commit. Increasing this value means the job usually needs fewer transactions to process the same amount of data, thereby reducing the cost of starting, completing, and recording transactions.

However, large chunks are not always faster. Transactions last longer, hold locks and connections longer, use more memory, and when an error occurs, the rollback scope or the amount of work that has to be reprocessed can be larger. You need to choose the commit interval based on actual measurements and the characteristics of the reader, processor, writer, database, and recovery requirements.

## 1. Commit interval and chunk size

A chunk is a group of items read, processed, and written as one transactional unit. With Spring Batch 5, you can configure the chunk size using `chunk(size, transactionManager)`:

```java
@Bean
Step importOrdersStep(JobRepository jobRepository,
                      PlatformTransactionManager transactionManager,
                      ItemReader<Order> reader,
                      ItemProcessor<Order, OrderEntity> processor,
                      ItemWriter<OrderEntity> writer) {
    return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, OrderEntity>chunk(1000, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

In the example, `1000` is the maximum number of input items gathered into one chunk before committing. Spring Batch reads and processes the chunk's items, passes the remaining outputs to the writer, and then commits the transaction. If the source ends before reaching 1000 items, the last chunk is still processed with the remaining items.

The commit interval is not the number of transactions for the whole job. With a regular chunk step, each chunk has its own transaction. A job has multiple steps, and each step can have multiple chunk transactions.

```text
Chunk 1: item 1..1000       -> transaction 1 -> COMMIT
Chunk 2: item 1001..2000   -> transaction 2 -> COMMIT
Chunk 3: item 2001..3000   -> transaction 3 -> COMMIT
...
```

## 2. Why do transactions create overhead?

A transaction has costs beyond the time spent executing business statements. Depending on the database and transaction manager, these costs may include:

- Beginning the transaction and setting up working state.
- Performing transaction management operations and resource synchronization.
- Flushing changes from the ORM or persistence context down to the database.
- Writing the transaction log/redo log and ensuring durability on commit.
- Sending the commit request through the driver and waiting for database confirmation.
- Updating step metadata and execution context in Spring Batch.
- Releasing locks, connections, or transaction resources after commit.

Some costs are fixed or nearly fixed per transaction, not linearly dependent on the number of items in the chunk. When each chunk has only one or a few items, these costs occur frequently. If you gather more items into the same transaction, the per-transaction cost is amortized across more items.

For example, suppose a job processes one million items with no retries:

| Commit interval | Approximate chunks/transactions |
| ---: | ---: |
| 10 | 100,000 |
| 100 | 10,000 |
| 1,000 | 1,000 |
| 5,000 | 200 |

The figures above are just the calculation `ceil(totalItems / chunkSize)` for a successful run. Retry, skip, partitioning, flows, or restarts can make the actual count differ.

If transaction overhead is the bottleneck, increasing the chunk size can significantly reduce the number of commits and metadata updates. But if the time spent processing each item or queries inside the writer takes up almost all the time, reducing the number of transactions may improve total time only slightly.

## 3. A simple cost model

You can picture the running time of a job as the total item processing time plus the cost incurred per chunk:

\[
T(C) \approx N \cdot t_{item} + \left\lceil\frac{N}{C}\right\rceil \cdot t_{tx} + T_{other}
\]

Where:

- `N` is the total number of items.
- `C` is the commit interval/chunk size.
- `t_item` is the average processing time for one item.
- `t_tx` is the average cost associated with one chunk transaction.
- `T_other` includes read/write costs, queries, network, scheduling, and other parts.

When increasing `C`, the transaction term decreases because there are fewer chunks. This model helps explain the trend, not serve as an exact prediction formula. In reality, `t_tx` can increase as transactions grow larger due to lock duration, flushing many entities, log volume, index maintenance, or contention. `T_other` can also change depending on the batch size the writer sends to the database.

Therefore, you should not choose chunk size simply by finding the largest number. The goal is to find the region where throughput increases significantly while transactions stay within resource and recoverability limits.

## 4. Comparing small chunks and large chunks

| Aspect | Small chunk | Large chunk |
| --- | --- | --- |
| Number of transactions | Many | Fewer |
| Commit/metadata overhead | Higher due to frequent commits | Amortized over more items |
| Lock hold time | Usually shorter | Can be longer |
| Connections and transaction resources | Released more frequently | May be held longer during the chunk |
| Memory for items in progress | Usually less | Usually more |
| Rollback scope | Fewer items | Can be more items |
| Checkpoint frequency | More frequent | Less frequent |
| Recovery time after error | May have less work to re-read | May have to reprocess a large uncommitted chunk |
| Throughput | May be limited by commit overhead | Can be better if overhead is the bottleneck and resources are sufficient |

Small chunks are useful when items are large, transactions need to be short, or fine-grained recovery is required. Large chunks are useful when commit cost is significant, the writer supports batch writing, and the database can handle large transactions without causing excessive lock contention or log pressure.

## 5. Example of increasing commit interval

Suppose a step imports 500,000 orders. Initially, the commit interval is 50:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(50, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

In a successful run, the approximate number of chunks is:

\[
500.000 / 50 = 10.000\text{ chunks}
\]

If increased to 500:

```java
return new StepBuilder("importOrdersStep", jobRepository)
    .<Order, OrderEntity>chunk(500, transactionManager)
    .reader(orderReader)
    .processor(orderProcessor)
    .writer(orderWriter)
    .build();
```

The approximate number of chunks drops to 1,000. If each transaction has significant overhead, this change can reduce overall time. The actual outcome also depends on whether the writer uses batch insert/update, the processing time per order, indexes, constraints, and concurrent load on the database.

When changing chunk size, check the output data and the `readCount`, `writeCount`, `filterCount`, and `skipCount` counters to confirm the number of processed items did not change unexpectedly.

## 6. Increasing chunk size can improve writer batching

Some writers write data more efficiently when they receive many items in a single call. For example, a JDBC writer can send batch statements instead of making one round trip per item. When a chunk is larger, a single writer call can contain more items and make better use of batching.

However, two concepts must be distinguished:

- **Chunk size/commit interval:** the number of items gathered in one chunk transaction.
- **Database/JDBC batch size:** the number of statements or parameter sets that the driver/database executes as one batch.

The two values are related but not necessarily identical. A chunk of 2,000 items does not guarantee the driver sends exactly a single batch; the writer, ORM, driver, or batch configuration may split it into smaller batches. Conversely, a custom writer may group data into batches independently of how Spring Batch splits transactions.

Example with `JdbcBatchItemWriter`:

```java
@Bean
JdbcBatchItemWriter<OrderEntity> orderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<OrderEntity>()
        .dataSource(dataSource)
        .sql("""
            insert into imported_order(order_id, amount)
            values (:id, :amount)
            """)
        .beanMapped()
        .build();
}
```

The writer receives items in the chunk and performs batch updates as supported by the implementation. Increasing chunk size can reduce the number of writer calls, but you need to measure with the actual driver/database. You also need to ensure the writer uses the same datasource and transaction manager as the step if you want write operations to participate in the chunk transaction.

## 7. Memory trade-offs

During chunk processing, the framework must keep the items being collected and their corresponding outputs until the writer finishes. The larger the chunk, the more objects usually need to be kept in memory.

If each item only contains a few small fields, increasing from 100 to 500 may be negligible. But if items contain large payloads, nested lists, file contents, or complex JPA object graphs, a chunk of 10,000 can create significant heap pressure.

Signs to watch for:

- Heap usage grows with chunk size.
- Frequent garbage collection or long pauses.
- OutOfMemoryError when processing large chunks.
- Persistence context holding too many unflushed/uncleared entities.
- Writer creating extra copies of collections or objects, multiplying memory usage.

With a JPA writer, consider the persistence context and how entities are flushed/cleared. Increasing chunk size without controlling the number of managed entities can cause memory to grow sharply. If the writer uses JDBC batching, the footprint can differ; measure using data close to production sizes.

## 8. Lock, connection, and transaction log trade-offs

Large transactions can hold locks longer because changes are held until commit. This can increase:

- The time other transactions have to wait for locks.
- The likelihood of deadlocks when multiple jobs or requests update the same data.
- The volume of undo/redo or transaction log that must be retained before commit.
- The time spent flushing indexes and constraints at the end of a chunk.
- Connection hold time in the pool and pressure on the connection pool.

Therefore, a single job may be faster with a large chunk while the overall system becomes slower because online requests have to wait for locks or run out of connections. Evaluate in the context of concurrent load, not just batch run time when the database is idle.

If a transaction is close to hitting the timeout, increasing chunk size can make timeout errors happen more often. Adjusting the timeout should only be done after understanding processing time and locks; increasing the timeout does not solve deadlocks, contention, or unbounded transactions.

## 9. Rollback and restartability trade-offs

Spring Batch normally saves metadata and execution context at commit boundaries. When chunks are larger, there are fewer checkpoints. If an error occurs mid-chunk, the current chunk has not committed and the reader may have to continue from the previous chunk's checkpoint.

For example, with 1,000 items per chunk:

```text
Chunk 1: item 1..1000      -> COMMIT
Chunk 2: item 1001..2000   -> error at item 1900

Restart from checkpoint:
  Continue from the committed position after chunk 1
  May re-read/reprocess the portion belonging to chunk 2
```

If the chunk size is 100, the scope of uncommitted items is usually smaller. This does not mean all 1,000 items are guaranteed to be re-executed across every reader and fault-tolerance configuration; the exact behavior depends on buffering, reader state, retry, and the failure point. But sparser checkpoints can increase the amount of work needing recovery.

The writer and business operations need to tolerate re-execution. Changes in the same database transaction will roll back if the chunk has not committed; side effects outside the transaction such as sending emails, calling APIs, or publishing messages may have already occurred and require idempotency/outbox.

## 10. Large chunks do not replace good writer design

If the writer executes a separate SQL statement for each item, increasing chunk size may reduce the number of commits while keeping the same number of SQL round trips. To improve throughput, check whether the writer can use batch insert/update, bulk load, or set-based operations.

For example, instead of running many lookup queries for the same kind of data in the processor, you can:

- Read reference data in batches.
- Use joins or set-based queries where appropriate.
- Use JDBC batching or bulk loading for writes.
- Avoid N+1 queries in the processor.
- Keep only necessary fields in the item rather than loading the entire object graph.

Chunk size is only one of the performance tuning knobs. It does not by itself make slow queries, O(n²) algorithms, per-item network calls, or non-batched writers efficient.

## 11. Commit policy and determining chunk boundaries

In the normal case, the application uses an item-count commit interval via `.chunk(size, transactionManager)`. Spring Batch also has the `CompletionPolicy` concept to determine when a chunk completes according to another policy, for example based on item count or a combined condition.

When using a custom completion policy, clearly define the chunk termination condition and test how it interacts with transaction timeout, data sources, and the writer. A time-based policy can help limit chunk length when reading speed varies, but also makes the number of items in each chunk non-fixed.

Do not choose a complex policy if a fixed commit interval meets requirements. Simpler configurations are easier to measure, easier to explain, and more predictable on restart.

## 12. Measuring before and after increasing chunk size

Measure a baseline before making changes. Useful metrics include:

| Metric | What to observe |
| --- | --- |
| Total job/step time | Time from start to completion. |
| Throughput | Number of items processed per second or per minute. |
| Commit count | Number of commits of the step. |
| Transaction duration | Average time, p95/p99, and longest transaction if measurable. |
| Database CPU/I/O | Database load while the job runs. |
| Lock wait/deadlock | Impact on other jobs and online workloads. |
| Connection pool | Connections in use, waiting, and timeouts. |
| Heap/GC | Additional memory due to chunks and object buffering. |
| Rollback/retry/skip | Error frequency and recovery cost. |
| Writer throughput | Write time and number of statements/round trips. |

Compare the same data set, the same database configuration, the same concurrent load, and the same application version. Run enough repetitions to avoid drawing conclusions from a single measurement affected by caches, warm-up, or background load.

## 13. Process for tuning the commit interval

A practical process can be carried out step by step:

1. **Measure baseline:** record the current chunk size, total items, commit count, step duration, throughput, heap, lock wait, and connection usage.
2. **Identify bottlenecks:** check whether time is spent in commit, reading, processing, writing, network, or queries. If the processor calls a slow API per item, increasing chunk size may not solve it.
3. **Increase in steps:** for example try 100, 250, 500, then 1,000 rather than jumping immediately to a very large value.
4. **Re-measure:** compare throughput and resources after each change.
5. **Test errors and restart:** simulate errors mid-chunk, confirm rollback, checkpoints, and reprocessability.
6. **Test under concurrent load:** observe locks, deadlocks, and impact on other workloads.
7. **Choose a stable region:** prefer a value that achieves good throughput while keeping transaction duration, heap, and recoverability within operational limits.

Example benchmark table (illustrative figures, not default Spring Batch results):

| Chunk size | Job time | Throughput | Peak heap | Transaction p95 |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 12 minutes | 694 items/s | 450 MB | 180 ms |
| 250 | 9 minutes | 926 items/s | 510 MB | 310 ms |
| 500 | 8 minutes | 1,042 items/s | 620 MB | 560 ms |
| 1,000 | 7.8 minutes | 1,068 items/s | 880 MB | 1,050 ms |
| 2,000 | 8.5 minutes | 980 items/s | 1,400 MB | 2,200 ms |

In this hypothetical example, increasing from 100 to 500 improves throughput clearly. From 500 to 1,000 gives only a slight increase while heap and transaction time rise sharply. At 2,000, performance drops due to high transaction cost and resource pressure. A suitable value could be 500 or 1,000 depending on operational limits and recovery requirements.

## 14. Example of logging commit count and processing time

`StepExecution` provides counters such as `readCount`, `writeCount`, `commitCount`, and `rollbackCount`. You can use listeners or metrics to log step/chunk times and combine them with database figures.

Example of reading counters after the step finishes:

```java
public class StepMetricsListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(StepMetricsListener.class);

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
            "step={}, read={}, write={}, commits={}, rollbacks={}, status={}",
            stepExecution.getStepName(),
            stepExecution.getReadCount(),
            stepExecution.getWriteCount(),
            stepExecution.getCommitCount(),
            stepExecution.getRollbackCount(),
            stepExecution.getStatus()
        );
        return null;
    }
}
```

Registering the listener with the step:

```java
.listener(new StepMetricsListener())
```

`commitCount` is a useful metric for comparing the number of commits across configurations. It does not replace measuring commit time or database queries. If you want to know which transaction is slow, you need metrics from the transaction manager, database monitoring, tracing, or appropriate instrumentation.

## 15. Situations where chunks should be kept small

Large chunks are not a good choice when:

- Each item has a large object graph or holds many resources.
- The writer updates rows with high contention against online transactions.
- Transactions may exceed the timeout or hold locks too long.
- The job needs frequent checkpoints because the source is hard to re-read.
- Errors occur frequently and reprocessing a large chunk is too costly.
- Business requirements require committing item by item or in small groups.
- An external source has offsets/acks that are hard to synchronize with database transactions.

In these cases, smaller chunks can provide better stability and recoverability, even though the commit count increases.

## 16. Common mistakes when increasing commit interval

**Increasing too fast without benchmarking:** can make transactions long, increasing lock waits or heap usage. Increase in steps and measure.

**Looking only at total job time:** the job may be faster while slowing down the database or online APIs. Measure under concurrent load.

**Confusing chunk size with JDBC batch size:** the two configurations are different. Check how many statements the writer and driver actually send in each batch.

**Ignoring transaction timeout:** large chunks can take longer to process than the timeout limit. Check actual processing time and transaction attributes.

**Not checking heap:** large chunks hold more items/outputs and can cause GC pressure or OOM.

**Not testing restart:** sparser checkpoints can force many uncommitted items to be re-read/reprocessed. Verify reader state and writer idempotency.

**Assuming everything rolls back:** HTTP, email, files, and brokers do not automatically participate in database transactions. Use an outbox or compensation/idempotency mechanisms.

**Increasing chunk size to hide an inefficient writer:** N+1 queries or one API call per item remain bottlenecks. Optimize algorithms and batching separately.

## 17. How to choose commit interval for production

Start from business requirements and resource limits. If the job is mainly constrained by commit overhead, try increasing chunk size to reduce the number of transactions. If the job is constrained by queries, network, or processor CPU, address that bottleneck first. For writers that can batch write, choose a chunk size compatible with batching capability and database payload limits.

After each change, check throughput, transaction duration, lock wait, heap, connection pool, and commit count. Simulate errors to confirm rollback and restart still work; ensure the writer can safely reprocess if a chunk has not committed. Set an upper bound so transactions do not exceed the timeout or impact other workloads.

Large commits help reduce transaction overhead because the same volume of items is processed through fewer transactions and fewer commits. The benefit is only sustainable when the chunk size fits the database capacity, memory, writer, and recovery requirements. Measuring step by step and choosing a stable value will help increase throughput while maintaining the consistency and operability of Spring Batch jobs.
