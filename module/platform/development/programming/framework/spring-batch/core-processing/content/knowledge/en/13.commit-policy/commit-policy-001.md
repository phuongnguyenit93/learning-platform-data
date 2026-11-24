# Commit interval and the number of items per transaction

In Spring Batch, `commit-interval` determines the number of items a chunk aims to process before the chunk's transaction is committed. With a chunk-oriented Step, Spring Batch reads items, passes them through the processor, calls the writer, and updates the stream state within the same chunk processing boundary. When the chunk completes successfully, the transaction is committed; if an error makes the chunk fail, the current transaction may be rolled back.

For example, `commit-interval = 100` means the Step gathers up to about 100 input items for a chunk before committing. If the source has 250 items, in terms of data there will be two full chunks of 100 and a final chunk of 50 items. Therefore, the commit interval is the target size of a chunk and determines the commit frequency; it is not a guarantee that the writer always writes exactly that many items.

## 1. Chunks and transactions in Spring Batch

Chunk-oriented processing divides a large amount of data into small groups. Each group is read, processed, written, and committed as one transaction unit.

```text
ItemReader
    |
    v
Read items until the commit interval is reached or the data runs out
    |
    v
ItemProcessor (for each item)
    |
    v
ItemWriter (write the chunk's results)
    |
    v
Update stream state / ExecutionContext
    |
    v
Commit the chunk's transaction
```

Spring Batch repeats the cycle above until the reader reports that the data has run out or the Step ends. If a chunk encounters an exception, the transaction manager handles the rollback according to the configuration. Chunks that were committed earlier remain independent transactions and are not automatically rolled back together with the failed chunk.

The commit interval is usually configured with `chunk(size, transactionManager)`:

```java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

In this example, `100` is the commit interval. `PlatformTransactionManager` manages the transaction of each chunk according to the Step configuration. Write operations must participate in this transaction if you want the chunk's rollback to undo them.

## 2. How is the number of items in a transaction calculated?

Suppose the reader provides 250 items and the commit interval is 100. In terms of data, Spring Batch processes them as three chunks:

```text
Total input items:    250
Commit interval:      100

Chunk 1: item   1 - 100  -> process -> write -> commit
Chunk 2: item 101 - 200  -> process -> write -> commit
Chunk 3: item 201 - 250  -> process -> write -> commit
```

| Chunk | Input items | Item count | Result on success |
|---|---|---:|---|
| 1 | 1–100 | 100 | Commit transaction 1 |
| 2 | 101–200 | 100 | Commit transaction 2 |
| 3 | 201–250 | 50 | Commit transaction 3 |
| Total | 1–250 | 250 | 3 data groups |

The last chunk is allowed to have fewer items than the commit interval. When `ItemReader.read()` returns `null`, Spring Batch understands that the data source has ended and processes the remaining items as the last chunk. The framework does not discard the 50 items just because there are not yet 100 of them.

For a data source with a total of `N` items and a commit interval of `C`, the number of data chunks under the usual division is:

\[
\text{Number of data chunks} = \left\lceil \frac{N}{C} \right\rceil
\]

Examples:

| Total items (N) | Commit interval (C) | Data chunks |
|---:|---:|---|
| 240 | 100 | 100, 100, 40 |
| 300 | 100 | 100, 100, 100 |
| 75 | 100 | 75 |
| 1,050 | 250 | 250, 250, 250, 250, 50 |

The formula above describes the chunks that contain data. The actual transaction/commit figures in the metadata also depend on how the Step ends, retry, skip, rollback, and the callbacks that save state; you should not use the division alone to infer every `StepExecution` counter.

## 3. Commit interval is not the same as the number of items the writer writes

The commit interval mainly determines the size of the input chunk that the reader provides. The number of items passed to the writer can be smaller because the `ItemProcessor` can filter items by returning `null`.

For example, a chunk has 100 input items but the processor removes 8 items:

```text
Reader reads:                 100 items
Processor filters:              8 items
Results passed to the writer:  92 items
Chunk transaction:             still a chunk that processes 100 input items
```

| Metric | Count |
|---|---:|
| Items provided by the reader | 100 |
| Items filtered | 8 |
| Items received by the writer | 92 |

Filtering is not the same as skipping. Filtering is a normal business decision in the processor; skipping occurs when an exception of a type configured to be skipped is thrown. Retry can cause some operations to be performed again, and rollback can cause the current chunk to be processed again. Therefore, you cannot conclude that the commit interval has changed just because the writer receives fewer items.

## 4. Transaction boundaries and rollback

With a commit interval of 100, the 100 items of a chunk are normally in the same transaction. If the writer writes 70 items and then throws an exception on the next item, the outcome depends on the resource the writer uses:

- If all 70 write operations participate in the Step's transaction, the rollback can undo all uncommitted changes of the chunk.
- If the writer commits each item separately, uses a different transaction manager, or calls an external system, the changes already made may still persist.
- If the writer catches the exception and then returns normally, the framework may consider the chunk successful and commit it, even though some items were not written.

For example, a writer uses `JdbcTemplate` with the same `DataSource` that is managed by the transaction manager:

```java
public class OrderWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;

    public OrderWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        for (Order order : chunk) {
            jdbcTemplate.update(
                    "insert into imported_order(order_id, amount) values (?, ?)",
                    order.getId(),
                    order.getAmount()
            );
        }
    }
}
```

If the 71st insert fails and all inserts participate in the same transaction, the earlier inserts in the chunk are also rolled back. Chunk 1 and chunk 2, which were committed earlier, keep their results.

A transaction does not automatically roll back side effects on an HTTP API, files, email, or a message broker. For these destinations, you need to design idempotency, checkpoints, an outbox, or a dedicated recovery mechanism.

## 5. Commit interval affects checkpoints and restart

Readers and writers can implement `ItemStream` to save state into the `ExecutionContext`. Spring Batch updates the stream state at the chunk boundary and saves metadata together with the transaction processing according to the repository configuration.

With a commit interval of 100:

1. The reader reads the first chunk, and the processor and writer handle 100 items.
2. The chunk commits successfully; the corresponding checkpoint is saved.
3. The second chunk processes and commits the next 100 items.
4. The third chunk fails before the commit.
5. On restart, the reader restores the checkpoint of the last committed chunk and continues with the part that was not completed.

Therefore, the commit interval affects the distance between checkpoints. A large interval can increase the amount of data that must be reprocessed after a failure. A small interval creates checkpoints more frequently but increases the number of commits and the transaction cost.

The reader must support restart, and the data source needs a stable order/identifier so that the checkpoint is meaningful. Setting the commit interval alone does not automatically make an arbitrary reader restartable.

## 6. Commit interval and other batch sizes

Several other configurations also hold item-count values, but they control different layers. You should not set them all to the same number just because their names all contain the word "size".

| Configuration | Controls | Relationship to commit interval |
|---|---|---|
| Chunk size / commit interval | The number of items in a chunk before commit | Determines the Step's transaction boundary |
| Reader page size | The number of records the reader fetches in one page query | Can be greater than, less than, or equal to the commit interval |
| JDBC fetch size | A hint for the driver to fetch data from the database in batches | Mainly affects how data is fetched; does not directly determine commits |
| Writer batch size | The number of statements/items the writer groups into one write batch | Can be split into smaller parts inside a chunk transaction |
| Transaction timeout | The maximum time a transaction is allowed to run | Not an item count; an overly large chunk can make the transaction run long and exceed the timeout |

For example, the commit interval can be 500 while the database reader uses a page size of 200. The reader may need several pages to provide one chunk. Conversely, a reader may prefetch more rows than the current chunk but hand over each item to the framework one at a time according to its contract.

With `JdbcPagingItemReader`, the page size is usually chosen based on query performance and memory; it does not replace the commit interval. With `JdbcCursorItemReader`, the fetch size is a hint for the JDBC driver, not the number of items per transaction.

## 7. Choosing an appropriate commit interval

There is no single optimal commit interval for every Job. You need to balance the number of commits, transaction hold time, memory, throughput, and recoverability.

### Small interval

For example `chunk(20, transactionManager)`:

- Transactions are shorter and usually hold locks for a shorter time.
- Checkpoints are updated more frequently.
- On rollback, the group of items to be reprocessed is usually smaller.
- The number of transactions and commits increases, which can reduce throughput if the commit cost is high.
- Metadata and transaction management overhead grows with the number of chunks.

### Large interval

For example `chunk(1_000, transactionManager)`:

- Reduces the number of commits for the same amount of data.
- Can make better use of batch insert/update.
- Holds transactions and locks longer, increasing the risk of contention or timeouts.
- Holds more items in memory, especially when items have large object graphs.
- When a chunk rolls back, many items may have to be reprocessed.
- Checkpoints are sparser, so recovery after a failure may take longer.

| Factor | Small interval | Large interval |
|---|---|---|
| Commit frequency | High | Low |
| Duration of one transaction | Usually short | Usually long |
| Memory for a chunk | Lower | Higher |
| Items in a rolled-back chunk | Fewer | More |
| Commit/metadata overhead | Higher | Lower |
| Checkpoints | More frequent | Sparser |

Measure with data close to production. A larger interval is not necessarily faster if the database holds locks for a long time, connections are held for too long, or the writer does not handle batches efficiently.

## 8. Estimating the interval based on resources

Suppose each item takes an average of 2 KB in memory while in a chunk. With a commit interval of 500, the item payload alone may need about 1 MB, not counting object overhead, buffers, processor state, and auxiliary data. If the interval increases to 5,000, the corresponding payload may rise to about 10 MB.

This is only a rough estimate. Actual memory depends on object size, data structures, the number of items after the processor, the writer, and how the reader buffers data.

When evaluating an interval, you should measure:

- The time to read, process, and write one chunk.
- The commit time and the time connections/locks are held.
- The heap used when the chunk is at the target size.
- The number of rollbacks, retries, and skips.
- Throughput in items/second and the time of the whole Step.
- The recovery time after deliberately making a chunk fail.

Choose a moderate starting value, run it with representative data, and then adjust based on metrics. Avoid choosing an interval based only on the total item count or a single small benchmark.

## 9. Transaction attributes and the limits of commit interval

The commit interval is not the only configuration that affects transactions. The transaction manager, isolation level, propagation, timeout, and the resources participating in the transaction all matter.

For example, setting a transaction timeout for a Step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<Order, Order>chunk(500, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .transactionAttribute(transactionAttribute())
        .build();
```

`transactionAttribute()` can return a `DefaultTransactionAttribute` configured with an appropriate timeout or isolation. You need to choose a timeout long enough for the chunk under the expected load, while avoiding unnecessarily long transactions.

If a service called in the writer opens a `REQUIRES_NEW` transaction, the new transaction can commit independently of the chunk transaction. When the outer chunk rolls back, changes already committed in the independent transaction are not undone. This is a common reason why the number of items actually written differs from the expectation of chunk-level atomicity.

## 10. Monitoring item counts and commit counts

`StepExecution` stores counters that help observe the Step's activity:

| Counter | Meaning |
|---|---|
| `readCount` | Number of items read successfully |
| `writeCount` | Number of items written successfully |
| `filterCount` | Number of items filtered by the processor |
| `readSkipCount` | Number of items skipped due to errors while reading |
| `processSkipCount` | Number of items skipped due to errors while processing |
| `writeSkipCount` | Number of items skipped due to errors while writing |
| `commitCount` | Number of commits recorded for the Step |
| `rollbackCount` | Number of rollbacks recorded for the Step |

You can log these metrics after the Step finishes:

```java
public class StepMetricsListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "step={}, read={}, written={}, filtered={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getFilterCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount()
        );

        return stepExecution.getExitStatus();
    }
}
```

You should not infer the commit interval by taking `readCount / commitCount` in every case. Filters, skips, retries, rollbacks, the last chunk, and auxiliary transactions can make the counters differ. Look at the Step configuration together with the execution history to interpret the metrics.

## 11. Common misconceptions

**Believing the commit interval is the number of items the writer must write.** The processor can filter items and a skip policy can drop items. The writer may receive fewer items than were read.

**Believing the last chunk must be full-sized.** If the reader reports EOF before the threshold, the remaining items are still processed as a smaller chunk and committed if successful.

**Equating page size with commit interval.** The page size controls the number of rows the reader fetches per page; the commit interval controls the Step's chunks and transactions.

**Increasing the interval to always increase throughput.** A large chunk can make transactions run long and increase locks, memory, and rollback cost. You need to measure in a representative environment.

**Believing a transaction rolls back every side effect.** Rollback only applies to resources participating in that transaction. External files, APIs, and messages need a dedicated recovery mechanism.

**Using commitCount to infer the exact number of data chunks without considering errors.** Retry, skip, rollback, and Step termination can make the counters more complicated than dividing the total items by the interval.

## 12. How to determine the commit interval for a Step

First, determine the size and characteristics of the items, the read/write costs, the database's transaction limits, and the ability to roll back. Choose a moderate starting interval, for example 100 or 500, and then measure chunk time, commit latency, memory, lock wait, and throughput. If commit overhead takes up a lot of time and resources are still sufficient, try increasing the interval. If transactions are long, hold many locks, or rollbacks cause too much data to be reprocessed, try decreasing the interval.

When changing the interval, check both the reader and the writer: whether the page/fetch size is still appropriate, whether the writer batches efficiently, whether the stream saves checkpoints correctly, and whether the target system participates in the transaction. Don't just change a single number and conclude that performance has improved.

`commit-interval` is the way to control a Step's chunk size and commit frequency. Each successful chunk creates a transaction boundary; the last chunk can be smaller than the threshold, and the number of items the writer receives can differ from the number of items the reader provided. Understanding these differences helps you choose an appropriate interval, control rollback, and build a reliable restart process.
