# Restarting from a chunk checkpoint

In Spring Batch, a chunk-oriented Step typically processes data in groups of items within separate transactions. After a chunk is successfully written and its transaction commits, Spring Batch saves execution state to record how far the reader has progressed. This saved state at the commit boundary is called a **checkpoint**.

If a Job fails or the process stops mid-run, a restart can use the most recent checkpoint to resume from the unfinished portion of data. As a result, the Step does not have to reprocess the entire input from the beginning. This mechanism works properly only when the reader supports saving and restoring state, the Job is restarted within the same JobInstance, and the source data still aligns with the saved checkpoint.

## 1. How are chunks and checkpoints related?

Chunk-oriented processing reads items from an ItemReader, processes them with an ItemProcessor, and writes a group of items with an ItemWriter. Each chunk typically runs inside one transaction:

~~~text
Chunk 1
  |
  +-- Reader reads items
  +-- Processor processes items
  +-- Writer writes data
  +-- Save reader state / ExecutionContext
  |
  +-- COMMIT
  |
  v
Chunk 2
  |
  +-- Reader reads next items
  +-- Processor processes items
  +-- Writer writes data
  +-- Save reader state / ExecutionContext
  |
  +-- COMMIT
~~~

A checkpoint is recovery state saved at a commit boundary. For a reader that supports restart, the state typically describes the next position to read, such as:

- Number of lines read in a file.
- Byte offset or next record position.
- Next page in a paging reader.
- Last key read in an ordered query.
- A token or offset that the data source supports resuming from.

A checkpoint is not a copy of all items in the chunk. It is just enough information for the reader to reopen the source and resume from the appropriate position.

## 2. Example of restarting after a chunk fails

Suppose a Job reads a 1,000-line file with a chunk size of 100:

~~~text
Chunk 1: lines 1-100      -> COMMIT
Chunk 2: lines 101-200    -> COMMIT
Chunk 3: lines 201-300    -> COMMIT
Chunk 4: lines 301-400    -> error -> ROLLBACK
Chunk 5: lines 401-500    -> not run yet

Latest durable checkpoint: after line 300
~~~

When chunk 4 fails, changes in that chunk's transaction are rolled back according to the transaction policy. The checkpoint committed after chunk 3 remains intact. When restarting the same JobInstance, the reader can restore the position after line 300 and re-read from line 301 onward.

Already-committed chunks 1, 2, and 3 do not need to be reprocessed when the Step, reader, and transaction are configured properly. The failed chunk is executed again because the checkpoint has not advanced past it.

This is a key principle: **restarting resumes from the most recently committed checkpoint, not from the last item the reader returned before the process stopped**.

## 3. JobInstance and restart conditions

Spring Batch distinguishes between JobInstance and JobExecution:

| Concept | Meaning |
| --- | --- |
| JobInstance | A logical processing run, identified by Job name and identifying JobParameters |
| JobExecution | A specific run attempt of a JobInstance |
| StepExecution | A specific execution of a Step within a JobExecution |

Restarting creates a new JobExecution belonging to the same JobInstance. Therefore, you must preserve the Job name and the identifying JobParameters of the run you want to resume.

Example initial run:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("inputFileId", "orders-2026-11-15", true)
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();
~~~

The restart must use the exact same identifying values:

~~~java
JobExecution restartedExecution =
        jobLauncher.run(importOrdersJob, parameters);
~~~

If you add a new identifying timestamp or UUID, Spring Batch may create a new JobInstance. The new instance does not use the old instance's checkpoint and may start processing the input from the beginning.

Restart is normally only available when the prior JobExecution ended in a restartable status, such as FAILED or STOPPED, and the Job is not configured with **preventRestart()**. A COMPLETED JobInstance usually cannot be re-run with the same identifying parameters.

## 4. Where does ExecutionContext store checkpoints?

Spring Batch uses ExecutionContext to store key-value state needed to resume a Job or Step. There are two common scopes:

- **JobExecutionContext:** state attached to the entire JobExecution.
- **StepExecutionContext:** state attached to a specific StepExecution.

A reader's checkpoint in a chunk Step normally lives in StepExecutionContext. JobRepository persists metadata for JobExecution, StepExecution, and ExecutionContext so it can be restored on restart.

For example, a reader may store:

~~~java
executionContext.putLong("lastProcessedOrderId", 125000L);
executionContext.putInt("nextPage", 26);
~~~

Keys should be stable and descriptive. Store only small, serializable data necessary for recovery. Do not store connections, stream objects, service objects, entire item lists, or large payloads in ExecutionContext.

Do not try to infer the checkpoint solely from readCount, writeCount, or commitCount. Those counters help observe progress, but they are not always sufficient for a reader to reconstruct the exact position, especially with filtering, skipping, retrying, or complex reader logic.

## 5. ItemStream provides the save and restore mechanism

Readers and writers that need to save state typically implement ItemStream. The lifecycle consists of three methods:

- open(ExecutionContext): reads saved state to restore the resource.
- update(ExecutionContext): writes current state into ExecutionContext.
- close(): releases resources when the Step ends.

In chunk processing, Spring Batch invokes the state-update mechanism on streams at chunk boundaries before committing. When the transaction commits successfully, the corresponding checkpoint is persisted durably according to the JobRepository and transaction manager configuration.

~~~text
ItemStream.open(context)
       |
       v
Read / process a chunk
       |
       v
ItemStream.update(context)
       |
       v
JobRepository saves StepExecutionContext
       |
       v
COMMIT transaction
       |
       v
New checkpoint takes effect
~~~

If the transaction rolls back, the incomplete chunk's checkpoint is not treated as a committed checkpoint. The reader will be restored from the most recently saved successful state.

### Readers must be registered as streams

Built-in readers configured through StepBuilder are usually recognized and have their ItemStream lifecycle managed by the framework. If a reader is wrapped in a decorator, composite, or created indirectly, ensure the delegate stream is properly registered. If open, update, and close are not invoked, checkpoints may not be saved even if the class implements ItemStream.

## 6. Restarting with FlatFileItemReader

FlatFileItemReader supports saving read state. When using the builder, give it a stable name and enable saveState:

~~~java
@Bean
@StepScope
public FlatFileItemReader<OrderInput> orderFileReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderFileReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerCode", "quantity", "unitPrice")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

`name("orderFileReader")` creates a stable namespace for the reader's state keys in ExecutionContext. `saveState(true)` allows the reader to save progress for restarting.

When the Step runs the first time, the reader opens the file and updates its read position per chunk. On restart, the reader reads back the saved state and resumes from the corresponding position.

### Input files must remain stable

Line-based or file-position checkpoints only make sense when the input is unchanged between the first run and the restart. If the file is replaced, or lines are inserted or deleted before the checkpoint position, the reader may miss or double-read data.

Use batch-immutable files, filenames or input IDs with versions, checksums, or identifying metadata. If the input file has changed, treat it as a new business processing run with appropriate JobParameters instead of applying an old checkpoint to different content.

## 7. Restarting with JdbcPagingItemReader

With a database paging reader, checkpoints typically tie to page state and sort keys. Queries need a stable order so the reader resumes at the right position.

For example:

~~~java
@Bean
@StepScope
public JdbcPagingItemReader<Order> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<Order>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause(
                    "select order_id, customer_code, total_amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .parameterValues(Map.of("businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper(new OrderRowMapper())
            .pageSize(100)
            .saveState(true)
            .build();
}
~~~

In the example, `order_id` is a stable sort key and must establish a unique order for the dataset being read. If the sort key is not unique, records with identical values may be paginated inconsistently. Use a composite key or a unique key as a tie-breaker.

### Source data changing while the Job runs

Even with a stable sort key, inserting or deleting records within the query range can affect paging. For example, if a new record is inserted before the saved position, offset/page checkpoints may no longer represent the same dataset.

Ways to mitigate risk:

- Read from a snapshot or a dataset frozen for the batch.
- Use a fixed watermark or cutoff, such as `created_at <= :batchCutoff`.
- Use keyset pagination with a unique key and a `key > lastKey` condition.
- Store the version or ID of the input dataset in JobParameters.
- Ensure filter conditions do not change between the initial run and the restart.

## 8. Custom ItemStreamReader saving checkpoints itself

If building a custom reader, implement ItemStream and save enough state to restore the position. The example below uses an item index for illustration:

~~~java
public class IndexedOrderReader
        implements ItemStreamReader<OrderInput> {

    private static final String NEXT_INDEX =
            "indexedOrderReader.nextIndex";

    private final List<OrderInput> items;
    private int nextIndex;

    public IndexedOrderReader(List<OrderInput> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext context) {
        nextIndex = context.containsKey(NEXT_INDEX)
                ? context.getInt(NEXT_INDEX)
                : 0;
    }

    @Override
    public OrderInput read() {
        if (nextIndex >= items.size()) {
            return null;
        }

        return items.get(nextIndex++);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(NEXT_INDEX, nextIndex);
    }

    @Override
    public void close() {
        // Close resources if the reader holds files or connections.
    }
}
~~~

This example shows:

1. `open` restores `nextIndex` from the checkpoint.
2. `read` returns the next item and increments the internal position.
3. `update` saves the next position into ExecutionContext.
4. `close` releases resources.

In a real application, do not load a large dataset into a `List` as in this illustration. The reader should store an offset, page, key, or token supported by the data source. The ExecutionContext key must be unique to the reader within the Step.

A custom reader must also be registered in the Step as an ItemStream. If the reader is wrapped by a decorator that does not forward the ItemStream lifecycle, explicitly register the delegate stream so checkpointing works.

## 9. saveState and readers that do not support restart

Many readers/writers have a `saveState` option. When enabled, the component saves state to ExecutionContext. When disabled with `saveState(false)`, the component does not save its own checkpoint.

For example:

~~~java
new FlatFileItemReaderBuilder<OrderInput>()
        .name("orderFileReader")
        .resource(inputFile)
        .delimited()
        .names("orderId", "quantity")
        .targetType(OrderInput.class)
        .saveState(false)
        .build();
~~~

With `saveState(false)`, you cannot expect the reader to automatically resume from its old position after a restart. The reader may start from the beginning or require another recovery mechanism provided by the application.

Only disable `saveState` when:

- The reader does not need to resume because the Step is designed to re-run completely safely.
- The data source has an independent checkpoint mechanism.
- The application manages the read position itself using another durable state store.

If a reader has state but does not save it, the Step may restart from the wrong position and produce duplicate or missing data.

## 10. Chunk size affects checkpoints

Checkpoints are usually saved at chunk boundaries, so chunk size affects how often progress is saved and how much work may need to be re-read.

| Chunk size | Commit/checkpoint frequency | Impact on error |
| --- | --- | --- |
| Small | More frequent | Fewer uncommitted items may have to be reprocessed |
| Large | Less frequent | More items may belong to an uncommitted chunk |

For example, with 10,000 items:

- Chunk size 100 produces roughly 100 chunks.
- Chunk size 500 produces roughly 20 chunks.
- Chunk size 1,000 produces roughly 10 chunks.

These are theoretical chunk counts assuming no filtering, skipping, or factors altering item counts. Small chunks increase commits and metadata writes. Large chunks can improve throughput but create long transactions, hold more items in memory, and increase rework when a chunk fails.

Do not choose chunk size solely based on commit count. Balance throughput, transaction duration, memory, checkpoint frequency, and restart cost.

## 11. Checkpoints and transactions must stay consistent

For safe restarts, checkpoints must reflect committed business data. In a common setup, business data and JobRepository metadata participate in the same transaction or are coordinated in a way that ensures consistency.

~~~text
One chunk transaction
    |
    +-- Writer writes business data
    |
    +-- ItemStream.update(context)
    |
    +-- JobRepository saves checkpoint
    |
    +-- COMMIT
~~~

If business data commits but the checkpoint does not, a restart may re-read items and write duplicates. If the checkpoint commits but business data rolls back, the reader may skip unwritten items.

This risk must be considered when:

- JobRepository and business data reside in two separate databases.
- Two independent transaction managers are used.
- The reader/writer writes to systems outside the Step's transaction.
- Metadata is updated through a separate transaction.

Do not assume two operations are atomic merely because they are called in the same Java method. Without a shared transaction, design idempotent writers, unique business keys, inbox/outbox patterns, staging, or reconciliation mechanisms.

## 12. Retry, skip, and checkpoints

Retry and skip affect how a chunk completes:

- **Retry:** retries a failing operation per the retry policy. The chunk may roll back before the framework retries.
- **Skip:** skips an exception allowed by policy; the chunk can continue and commit if still valid.
- **Rollback:** discards uncommitted changes of the current transaction.

For example:

~~~text
Chunk 1: items 1-100 -> COMMIT
Chunk 2: items 101-200 -> error at item 145
       |
       +-- Retry: retry per retry policy
       |
       +-- Skip: skip failing item if policy allows
       |
       +-- Fail: roll back chunk and fail Step
~~~

If chunk 2 rolls back and the Step fails, the latest checkpoint remains after item 100. On restart, the reader can re-read from item 101. If item 145 is skipped and chunk 2 completes, the chunk's checkpoint commits along with the skip state.

Do not infer the restart position solely from `readCount`. With filtering, skipping, retrying, or writer errors, the number of items read can differ from the checkpoint position and the number of items written. The reader must restore from the state it saved itself.

## 13. COMPLETED Steps vs. FAILED Steps

Restarting a Job does not mean all Steps start over from the beginning:

- Already-COMPLETED Steps are typically skipped.
- FAILED or STOPPED Steps can be executed again if the Job allows restarting.
- A failed chunk Step can recover from the most recently saved checkpoint.
- `allowStartIfComplete(true)` allows an already-completed Step to run again on restart.

For example:

~~~text
First run:
  prepareInputStep  -> COMPLETED
  importOrdersStep  -> FAILED (checkpoint after chunk 3)
  publishReportStep -> not run yet

Restart:
  prepareInputStep  -> skipped
  importOrdersStep  -> resumes after chunk 3 checkpoint
  publishReportStep -> runs after import completes
~~~

If you need to restart the same JobInstance, keep the Job name and identifying JobParameters unchanged. If identifying parameters change, Spring Batch may create a new instance and will not use the old checkpoint.

## 14. Checkpoints in a partitioned Step

With partitioning, each worker StepExecution has its own ExecutionContext. Each partition has its own checkpoint so it can resume its slice of data.

For example:

~~~text
Master Step
  |
  +-- partition0: COMPLETED
  |       own checkpoint
  |
  +-- partition1: FAILED
  |       checkpoint after chunk 4
  |
  +-- partition2: COMPLETED
          own checkpoint
~~~

On restart, Spring Batch can skip completed partitions and re-execute the failed partition from its worker checkpoint if configuration and metadata remain stable.

For this mechanism to work:

- Partition names must be stable.
- The Partitioner must recreate the exact ranges from the initial run.
- Worker readers must save their own checkpoints.
- Do not alter partition mappings while old JobInstances still need restarting.
- Partition side effects must be idempotent because the last chunk may be re-executed.

If the Partitioner relies on changing source data, a restart may generate different ranges. Use an input snapshot, watermark, or data-identifying parameter to ensure consistent partition mapping.

## 15. Side effects and item reprocessing

A database transaction rollback does not automatically undo external side effects such as:

- Calling a REST API.
- Sending emails or notifications.
- Publishing messages to another broker.
- Writing or moving files.
- Calling a payment service.

For example, a processor or writer sent a request to an external system and then the database transaction rolled back. When restarting from the checkpoint, the item may be reprocessed and the request sent a second time.

Ways to mitigate risk:

- Use a stable idempotency key derived from the business key or item ID.
- Use unique constraints to prevent duplicate data writes.
- Use an outbox to record message-publishing requests in the same database transaction.
- Record operation status in a durable store.
- Isolate side effects into a separate Step after primary data commits.
- Use compensation if business rules allow it and direct rollback is impossible.

Do not assume checkpoints automatically guarantee exactly-once across all external systems. A checkpoint only tracks Step progress; side effects require their own consistency mechanisms.

## 16. Observing checkpoints and restart history

JobExplorer lets you query JobExecution and StepExecution to inspect execution state:

~~~java
JobExecution execution =
        jobExplorer.getJobExecution(jobExecutionId);

if (execution != null) {
    for (StepExecution stepExecution : execution.getStepExecutions()) {
        log.info(
                "step={}, status={}, read={}, write={}, commits={}, rollbacks={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getCommitCount(),
                stepExecution.getRollbackCount());
    }
}
~~~

When investigating a restart, examine:

- JobInstance ID and identifying JobParameters.
- Whether the previous JobExecution was FAILED or STOPPED.
- Which StepExecution failed.
- Commit count and rollback count.
- Whether the reader saved ExecutionContext.
- Checkpoint keys and saved values.
- Whether the input file, snapshot, or query filter still matches the initial run.
- Whether any non-transactional side effects occurred.

Read count, write count, and commit count help understand progress, but do not replace checkpoint contents. If you need to inspect ExecutionContext, use the appropriate API or admin tool; never manually edit serialized metadata in JobRepository.

## 17. Common pitfalls

### Reader does not implement ItemStream

If a custom reader does not save state, Spring Batch has no position to restore. Implement ItemStream or use a built-in reader that supports restart.

### Disabling saveState while expecting restart to resume

With `saveState(false)`, the reader does not save its own checkpoint. Another recovery mechanism is needed before disabling it.

### Renaming the reader between runs

The reader name may be used to construct keys in ExecutionContext. Renaming it can prevent the reader from finding the old checkpoint. Keep names stable across the lifecycle of JobInstances that need restarting.

### Replacing the input file while keeping the old checkpoint

Line-based or offset-based checkpoints can point to the wrong position if the file changes. Use an input ID/version or create a new JobInstance for the new dataset.

### Paging query without a unique sort key

Unstable ordering can cause pagination to duplicate or drop items. Use `ORDER BY` with a unique key or composite key.

### Confusing readCount with the checkpoint

Filtering, skipping, and retrying cause the read count to differ from the resume position. Use the reader's ExecutionContext instead of computing positions from counters.

### Checkpoint and business data committing independently

The two sides can drift apart on restart, leading to dropped or duplicate writes. Use a shared transaction if appropriate, or design idempotency and reconciliation.

### Assuming all items in a failed chunk are lost

Uncommitted chunks are reprocessed from the most recent checkpoint. That chunk's data may be read and processed again, while committed chunks remain intact.

### Failing to protect non-transactional side effects

APIs, messages, or files may have been created before rollback. Use idempotency keys, outboxes, or compensation.

### Changing identifying JobParameters on restart

New parameters can create a different JobInstance and ignore the old checkpoint. Keep the Job name and identifying parameters unchanged when resuming a prior instance.

## 18. Procedure for designing chunk checkpoint restarts

When building a Step that needs restarting, determine:

1. Does the reader support ItemStream and save state?
2. Is `saveState` enabled and does the reader have a stable name?
3. Does the checkpoint describe an offset, page, sort key, or token?
4. Is the input immutable or versioned/watermarked throughout the run?
5. Is the chunk size balanced for transaction duration and restart cost?
6. Do JobRepository and business data have consistent transaction boundaries?
7. How do retry, skip, and rollback affect the reader position?
8. Is the writer idempotent when a chunk is re-executed?
9. Does restarting the Job preserve the JobInstance and identifying parameters?
10. Do individual partitions or resources need separate recovery?
11. Are logs and metadata sufficient to locate the latest checkpoint?

Test by intentionally stopping the Job after several committed chunks, injecting an error in the next chunk, and restarting with the same JobParameters. Verify that committed chunks are not written twice, the uncommitted chunk is reprocessed, and the reader resumes from the exact checkpoint. Also test scenarios where input changes and where writers cause non-transactional side effects.

## Conclusion

Restarting from a chunk checkpoint enables Spring Batch to resume a chunk-oriented Step from saved state at the most recent commit boundary. ItemStream and ExecutionContext provide the mechanism to save/restore reader positions; JobRepository persists metadata so a new JobExecution of the same JobInstance can continue. For accurate restarts, readers must support state saving, names and inputs must remain stable, queries need deterministic ordering, checkpoints must stay consistent with committed data, and side effects must be idempotent. Uncommitted chunks may be reprocessed, while already-committed chunks are preserved according to completed transactions.
