# Small commits reduce rollback scope

In chunk-oriented processing, Spring Batch gathers multiple items into a chunk and processes that chunk within a single transaction. When the writer and business resources participate in the same transaction, the changes in the chunk are committed together. If an error causes the transaction to roll back, the uncommitted changes of the current chunk are undone.

The `commit interval` (often also called chunk size) determines the number of items the reader needs to read to form a chunk before Spring Batch writes and commits. Choosing a small chunk reduces the number of items inside a single transaction, thereby narrowing the scope of data that can be rolled back when an error occurs. In return, the system must perform more transactions and commits.

## 1. Chunk and commit boundary

A chunk is a processing unit consisting of items that are read, processed, and written within the same step transaction. When the chunk completes successfully, the transaction is committed. The step then continues with the next chunk.

```text
Chunk 1: read -> process -> write -> COMMIT
Chunk 2: read -> process -> write -> COMMIT
Chunk 3: read -> process -> write -> COMMIT
                         |
                         +-- if error before commit: ROLLBACK chunk 3
```

For example, with a commit interval of 100:

- Spring Batch reads and processes a group of at most 100 items for the chunk.
- The writer writes the output items of the chunk.
- If processing succeeds, the transaction commits.
- The step continues with the next group of items.

Committed chunks are separate transactional units. If chunk 8 fails, changes already committed in chunk 1 through chunk 7 normally persist. Spring Batch does not open a single transaction spanning the entire job to undo all data written from the beginning.

## 2. Commit interval controls transaction size

In Spring Batch 5, the commit interval is declared on the chunk builder:

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
}
```

With the value `50`, the step normally processes at most 50 input items for one chunk before writing and committing. The last chunk can be smaller if the data source has run out. If the processor filters items by returning `null`, the writer receives fewer items than the reader read.

You should not interpret the commit interval as the exact number of rows guaranteed to be written by the writer on each call. It is the size of the input item group that the chunk provider collects; filtering, skipping, and the last chunk can make the number of output items smaller.

## 3. Why do small chunks narrow the rollback scope?

Suppose a job imports 1,000 orders. Compare two configurations:

| Configuration | Estimated number of chunks | Max items in a chunk |
|---|---:|---:|
| Commit interval = 1,000 | 1 | 1,000 |
| Commit interval = 100 | 10 | 100 |
| Commit interval = 20 | 50 | 20 |

Suppose an error occurs while processing the last chunk:

```text
Commit interval = 1000
  [ 1,000 items currently in one transaction ]
  error before commit -> roll back up to the entire chunk

Commit interval = 100
  [100] COMMIT [100] COMMIT ... [100 in progress]
                                         error -> roll back current chunk
```

With a small chunk, fewer items are inside an uncommitted transaction. Therefore, the amount of data that needs to be rolled back or reprocessed is usually reduced. Earlier committed chunks are not rolled back just because a later chunk hits an error.

This is useful when:

- The writer performs multiple database operations in a single chunk.
- One faulty item can cause the entire current chunk to roll back.
- Long transactions hold locks or connections for a long time.
- The cost of reprocessing a chunk after an error is high.
- More frequent checkpoints are needed to restart from the most recent committed progress.

## 4. Example of an error in the middle of a large batch

Suppose the writer writes 100 orders in one transaction. It writes several records and then hits a constraint error on the 80th item. If the exception makes the transaction roll back, the database changes belonging to that transaction will be undone, including inserts that already succeeded before the error occurred.

With a commit interval of 100, up to 100 input items of the current chunk fall within the scope of the transaction being rolled back. With a commit interval of 10, an error in the chunk containing items 71–80 only affects the transaction of that group; the earlier committed chunks 1–10 through 61–70 are still preserved.

| Point of error | Commit interval 100 | Commit interval 10 |
|---|---|---|
| Current chunk | Items 1–100 | Items 71–80 |
| Changes in current transaction | Rolled back by transaction | Rolled back by transaction |
| Earlier committed chunks | None in this example | Items 1–70 remain committed |
| Volume to reprocess on restart | Up to 100 items | Usually at most 10 items in the current chunk |

This illustrates a local database transaction. If the writer has already called an external API or written to a system not participating in the transaction, external side effects may not roll back. Small chunks do not automatically guarantee that operations outside the database are undone.

## 5. Small commits and checkpoint/restart

At chunk boundaries, Spring Batch can save metadata and state needed for restart through `JobRepository` and `ExecutionContext`. When a chunk commits successfully, the committed progress can be used as a continuation point if the execution later fails.

```text
Chunk 1 -> process -> commit + checkpoint
Chunk 2 -> process -> commit + checkpoint
Chunk 3 -> process -> error before commit

Restart same JobInstance:
  restore state committed at chunk 2
  continue work from the corresponding checkpoint
```

Small chunks usually create checkpoints more frequently. When a job fails, the uncommitted work can be re-executed from the nearest checkpoint instead of having to reprocess a larger group.

Accurate restart capability depends on the reader/writer saving state, the JobRepository having durable metadata, the transaction manager, and how resources are coordinated. A reader that does not save state or a side effect outside the transaction may need its own recovery strategy.

You should not just reduce chunk size and assume restart is already safe. You need to determine what data has been committed, what reader state is saved, and which operations may be called again.

## 6. Trade-off: more transactions

Small chunks increase the number of transaction starts and commits. Each transaction has orchestration, logging, synchronization, and metadata update costs. If chunks are too small, overhead can account for a significant portion of the run time.

Example with 10,000 items:

| Commit interval | Estimated number of chunks | Main characteristics |
|---:|---:|---|
| 1 | 10,000 | Very short transactions but high overhead |
| 10 | 1,000 | Small rollback scope, increased commit count |
| 100 | 100 | Balanced across many workloads |
| 1,000 | 10 | Fewer commits but larger transactions |

These numbers only illustrate chunk counts when there is no filter/skip and the source has enough items. The right value depends on the processing time per item, the database, the writer, and concurrent load.

## 7. Impact on locks, connections, and memory

Long transactions can hold locks longer, hold connections longer, and increase the likelihood of contention with other transactions. Small chunks usually shorten the duration of a single transaction, helping reduce resource hold time and narrow rollback scope.

Small chunks also usually hold fewer items in memory. However, total memory usage still depends on the reader, processor, writer, caches, and retained object references.

There is no guarantee that reducing the commit interval always increases throughput. If the bottleneck is the network, an external API, CPU, or inefficient queries, changing chunk size may not solve the root cause. You need to measure processing time, commit time, lock wait, and connection usage to make a choice.

## 8. Commit interval and processor filter/skip

Chunks are formed based on input items, while the writer only receives the items remaining after the processor and skip policy.

Example with a commit interval of 5:

```text
Reader:      A  B  C  D  E
Processor:   A  B  null D  E
Writer:      [A, B, D, E]
Commit:      chunk transaction completes
```

If the processor returns `null`, the item is filtered and not sent to the writer. If the processor throws an exception accepted by the skip policy, that item is also not written. In both cases, the writer may receive a chunk smaller than the commit interval.

Therefore, the commit interval is not an exact limit on the number of records written successfully. When measuring data quality, track read count, write count, filter count, and skip count separately.

## 9. Choosing the commit interval by workload

There is no single chunk size suitable for every job. Consider the following factors:

1. **Cost per item:** a heavy processor or a writer executing many SQL statements may need smaller chunks to limit transaction time.
2. **Writer batching capability:** a JDBC batch writer usually makes good use of larger item groups, but this must be balanced against locks and rollback scope.
3. **Transaction timeout:** the chunk must complete within the time allowed by the transaction manager and database.
4. **Lock contention:** if the job contends for tables with an online application, small chunks can help shorten lock hold time.
5. **Memory:** large items or a processor creating large objects may require small chunks to limit the memory footprint.
6. **Restart and errors:** if reprocessing cost is high, more frequent checkpoints can be helpful.
7. **Throughput:** transactions/commits that are too frequent can reduce overall speed.
8. **Concurrent load:** many steps or partitions running simultaneously can increase the total number of transactions and pressure on the database.

You can start with a moderate value, such as 50 or 100, and then measure on data close to production. This is only a starting point for benchmarking, not a mandatory rule.

## 10. When should you use very small chunks?

A small commit interval, even equal to 1, may be suitable when:

- Each item is an independent write unit and needs to be committed immediately after processing.
- Processing time per item is long and you do not want to hold a transaction across multiple items.
- An item has a high probability of causing errors and the cost of rolling back a large group is significant.
- Database resources have high contention and short transactions are needed.
- Operational requirements prioritize fine-grained recoverability over maximum performance.

However, a commit interval of 1 means one transaction per item. With millions of records, the large number of transactions can degrade performance significantly. If possible, use larger chunks and handle errors with appropriate skip/retry.

## 11. When are large chunks more suitable?

Large chunks may be suitable when:

- The database and writer process batches efficiently.
- Each item is lightweight and transactions complete quickly.
- There are not many online transactions contending for resources.
- Transaction/commit overhead is the bottleneck.
- The system has enough memory and a wide enough transaction timeout.

Large chunks reduce the number of commits and usually improve throughput for database batch operations. However, transactions last longer, may hold locks longer, and on rollback will have to reprocess more items.

## 12. Small commits do not replace idempotency

Earlier committed chunks still persist when a later chunk fails. On restart, the job continues from the checkpoint if the reader supports it. But with side effects outside the transaction, an item may have already been processed in an external system even though the chunk's database transaction rolled back.

For example, the writer calls a shipping API for 10 orders; the API accepts 6 orders and then the request times out. A database transaction rollback cannot cancel the 6 requests already accepted by the shipping system. On retry, the writer may send those requests again.

To handle this safely:

- Use an idempotency key based on the order ID or business key.
- Write the request to an outbox within the database transaction and publish it after commit.
- Design the target API to recognize duplicate requests.
- Reconcile state after a timeout before resending.

Small chunks help reduce the rollback scope of the transaction they manage. They do not turn the entire pipeline into exactly-once and do not automatically roll back external side effects.

## 13. Relationship with skip, retry, and rollback

When fault tolerance is enabled, Spring Batch can roll back a chunk to retry or identify the item causing an error. Chunk size affects the number of items inside the processing unit needing recovery.

- **Retry:** transient errors can cause an operation to be retried. Small chunks usually limit the number of items involved in a recovery pass, though the exact number of re-invocations also depends on the retry policy and the reader/writer.
- **Skip:** faulty items are removed from the pipeline according to the skip policy. The writer receives the remaining items; the skip limit still needs to be set reasonably.
- **Rollback:** changes in an uncommitted chunk transaction are undone if the resources participate in that transaction.
- **Restart:** a new execution can continue from the committed checkpoint of the JobInstance if metadata and state are stored appropriately.

You should not catch exceptions in the writer and ignore them just to avoid rollback. Doing so can make Spring Batch treat the chunk as successful even though the data has not been fully written.

## 14. Transaction timeout and commit interval

Transaction timeout limits how long a transaction can exist according to the configuration of the transaction manager and database. An overly large chunk or a slow processor/writer can cause the transaction to exceed the timeout.

You can configure the timeout on the step:

```java
return new StepBuilder("importOrders", jobRepository)
    .<OrderRow, Order>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .transactionAttribute(new DefaultTransactionAttribute() {{
        setTimeout(120);
    }})
    .build();
```

The code snippet illustrates the idea of configuring transaction timeout (value in seconds); in production code, you should create and configure `DefaultTransactionAttribute` in a separate bean/method rather than using double-brace initialization. The database/driver timeout also needs to be compatible.

If chunks frequently exceed the timeout, you can reduce the commit interval, optimize queries, or reduce the processing time per item. Do not just increase the timeout without identifying the reason why transactions run long.

## 15. Example comparing two configurations

Suppose a job imports 5,000 transactions; each item needs validation and writing one record to the database.

**Configuration A: chunk 1,000**

```java
.<TransactionRow, Transaction>chunk(1000, transactionManager)
```

- About 5 transactions if there is no filter/skip.
- Each transaction processes a large group.
- Less commit overhead.
- An error in a chunk can require recovery for up to 1,000 input items belonging to the current transaction.

**Configuration B: chunk 100**

```java
.<TransactionRow, Transaction>chunk(100, transactionManager)
```

- About 50 transactions if there is no filter/skip.
- Shorter transactions across many workloads.
- Smaller rollback scope for a single chunk.
- Increased number of commits and metadata updates.

Choose a configuration by benchmarking with representative data, while checking run time, error rate, rollback count, lock wait, throughput, and restart capability.

## 16. Common mistakes when choosing commit interval

| Mistake | Consequence | How to handle |
|---|---|---|
| Choosing an overly large chunk just to reduce commit count | Long transactions, long locks, and wide rollback scope | Measure and reduce chunk if transactions drag on or recovery is expensive |
| Choosing chunk equal to 1 for every job | High transaction overhead, low throughput | Use a size suitable for the writer and workload |
| Assuming earlier chunks roll back if a later chunk fails | Misunderstanding transaction boundaries | Remember that each committed chunk is a separate transaction |
| Assuming commit interval equals the number of items the writer always receives | Wrong when there is filter, skip, or last chunk | Track read/write/filter/skip counts separately |
| Ignoring transaction timeout | Chunks may fail when running long | Measure chunk time and configure an appropriate timeout |
| Relying on small commits to protect external APIs | Side effects outside the transaction can still repeat | Use idempotency keys, outbox, or reconciliation |
| Not benchmarking under concurrent load | Choosing an unsuitable chunk for production | Test with concurrency and near-realistic data |

## 17. Process for choosing and tuning chunk size

When designing or optimizing a commit policy, you can follow this sequence:

1. Identify the transaction manager and datasource that the step uses.
2. Measure the average time and high percentiles of each chunk with representative data.
3. Track read, write, filter, and skip counts to understand the actual size of the writer input.
4. Observe lock wait, connection usage, transaction timeout, and commit time.
5. Choose a starting commit interval suited to rollback and throughput requirements.
6. Test with mid-chunk errors to confirm rollback and restart work properly.
7. Tune step by step and compare metrics instead of changing multiple factors at once.
8. Check side effects outside the transaction and ensure they are idempotent on retry/restart.

The commit interval is part of transaction design, not just a performance parameter. Choose it based on acceptable rollback scope, resource hold time, and the system's batch writing capability.

## Conclusion

The commit interval determines the chunk size and therefore affects the step's transaction scope. Small chunks limit the number of items inside an uncommitted transaction, usually helping reduce the amount of work that must be rolled back or reprocessed when an error occurs. Earlier committed chunks are still preserved when a later chunk fails.

In return, small chunks increase the number of transactions, commits, and metadata updates, which can reduce throughput. Balance recoverability, lock/connection hold time, memory, and performance by measuring on real workloads. For side effects outside the transaction, idempotency or an outbox is still needed; small commits by themselves do not guarantee exactly-once.
