# Commit policy and restart checkpoint

In Spring Batch, the commit policy decides when a group of items is considered complete and that group's transaction is committed. A restart checkpoint is the state saved at a commit boundary, helping the Job continue from the unfinished part of the work after being stopped or failing.

The two concepts are tightly coupled. The commit policy determines how often checkpoints are created; checkpoints record the progress that the reader, writer, or Tasklet needs to recover. If designed incorrectly, the Job may have to re-read a lot of data, duplicate side effects, or miss items on restart.

## 1. Commit policy in chunk-oriented processing

A chunk-oriented Step reads items from an ItemReader, processes them through an ItemProcessor, and then writes a group of items using an ItemWriter. Spring Batch gathers items into chunks and executes each chunk within a single transaction.

~~~text
ItemReader
    |
    v
ItemProcessor
    |
    v
Gather items into a chunk
    |
    v
ItemWriter
    |
    v
Update state / checkpoint
    |
    v
Commit transaction
    |
    v
Next chunk
~~~

**Commit policy** is the rule that determines when the current chunk ends. The most common approach is committing by item count, often called chunk size or commit interval.

For example, with a chunk size of 100:

- The Step reads and processes up to about 100 items for one chunk.
- The writer receives the items that passed through the processor in that chunk.
- After writing succeeds and necessary state is updated, the transaction is committed.
- The Step begins the next chunk.

The last chunk may contain fewer than 100 items if the reader has run out of data. If the processor filters items by returning null, the number of items the writer receives may be smaller than the number read in the chunk.

### Declaring commit interval in Java

With Spring Batch 5 and later:

~~~java
@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
~~~

The value 100 is the commit interval. In older XML configurations, the commit-interval attribute was used to represent the same idea. The specific API depends on the Spring Batch version, but the goal remains defining the chunk and transaction boundary.

## 2. Commit policy is more than just a number

Committing by count is a common choice because it is easy to understand and allows predicting the item volume in a transaction. However, Spring Batch also supports CompletionPolicy to determine when a chunk completes according to a rule.

With SimpleCompletionPolicy, a chunk ends after the configured number of processing iterations:

~~~java
SimpleCompletionPolicy completionPolicy =
        new SimpleCompletionPolicy(100);

return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(completionPolicy, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .build();
~~~

This is an equivalent declaration in meaning to a chunk size of 100. Using CompletionPolicy is useful when you want to separate the chunk completion rule from configuring the reader, processor, and writer.

A custom CompletionPolicy can be based on application conditions, such as item count, elapsed time, or a data threshold. However, the policy is checked inside the processing loop; it is not a timer that can immediately interrupt an item being processed or cancel a running query.

Do not confuse CompletionPolicy with transaction timeout:

| Mechanism | Role |
| --- | --- |
| Chunk size / CompletionPolicy | Decides when the chunk ends and the chunk transaction is completed |
| TransactionAttribute timeout | Limits how long a transaction is allowed to exist |
| Query timeout | Limits the execution time of a SQL statement |
| Job deadline | Limits the total time of a Job workflow if the application implements such a mechanism |

The commit policy decides the chunk size or termination condition. Transaction timeout protects the transaction from existing for too long. The two configurations complement each other.

## 3. Why does a commit create a checkpoint?

Spring Batch needs to know which part of the work has been committed successfully so it can continue after a failure. In a chunk-oriented Step, checkpoints are usually stored together with the StepExecution metadata in the JobRepository.

ExecutionContext is a key-value state storage area for JobExecution or StepExecution. Components supporting ItemStream can use ExecutionContext to store progress such as:

- Current position in a file.
- Number of lines or items read.
- Next page to query.
- Last key processed.
- State needed to reopen a resource.

The ItemStream lifecycle consists of three important methods:

- open(ExecutionContext): restores state when the resource is opened.
- update(ExecutionContext): writes current state into ExecutionContext.
- close(): releases resources when the Step ends.

In chunk processing, Spring Batch invokes the stream state update mechanism at chunk boundaries so checkpoints are saved in metadata. With a configuration sharing the same transaction manager and the same database for business data and metadata, written data and checkpoints can be committed in the same transaction.

~~~text
Current chunk
    |
    +-- Reader reads items
    +-- Processor processes
    +-- Writer writes data
    +-- ItemStream.update(context)
    +-- JobRepository saves ExecutionContext
    |
    v
Commit transaction
    |
    v
New checkpoint is durable
~~~

A checkpoint represents progress saved at a commit boundary. If the chunk's transaction rolls back, that chunk's checkpoint is not considered complete.

## 4. Restart restores from the nearest checkpoint

Suppose a Job reads a file of 1,000 lines with a chunk size of 100. After the first three chunks commit, the application hits an error while processing the fourth chunk.

~~~text
File: 1 ---------------------------------------- 1000

Chunk 1: lines 1-100      -> COMMIT
Chunk 2: lines 101-200    -> COMMIT
Chunk 3: lines 201-300    -> COMMIT
Chunk 4: lines 301-400    -> ERROR / ROLLBACK
Chunk 5: lines 401-500    -> not run yet

Saved checkpoint: after line 300
~~~

When restarting the same JobInstance, a reader capable of restoring state will continue from the checkpoint after line 300. The fourth chunk is read and processed again. Chunks 1, 2, and 3 that already committed do not need to be reprocessed when the reader and Step are configured properly for restart.

This does not mean Spring Batch stores a copy of every item in the chunk. The reader or processing component must save enough information to reconstruct the necessary position or state. For example, a file reader saves the read position, a paging reader saves the key or page, and a custom reader needs to implement the corresponding mechanism itself.

### JobInstance and JobExecution on restart

Restart uses the same Job name and the same identifying JobParameters to locate the existing JobInstance. Spring Batch creates a new JobExecution for the next attempt and restores state from the previous execution's metadata.

~~~text
Job: importOrders
    |
    +-- JobInstance A
            |
            +-- JobExecution #1: FAILED
            |       Checkpoint: chunk 3 committed
            |
            +-- JobExecution #2: STARTED -> COMPLETED
                    Resume from saved checkpoint
~~~

If you change identifying parameters, Spring Batch may create a new JobInstance. The new instance does not use the old instance's checkpoint. Therefore, do not add a new identifying timestamp or UUID when the goal is to restart.

## 5. ItemStream and how state is saved

Readers and writers that have state needing recovery usually implement ItemStream. Many built-in Spring Batch components already support this mechanism.

For example, FlatFileItemReader can save its read position to continue after a restart. When configuring the reader with a builder, set a stable name:

~~~java
@Bean
public FlatFileItemReader<OrderInput> orderReader(
        Resource inputResource) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputResource)
            .delimited()
            .names("orderId", "customerCode", "quantity", "unitPrice")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
~~~

The reader name helps generate stable state keys in the ExecutionContext. saveState(true) enables saving the reader's state. For components supporting restart, you should not change the name arbitrarily between runs if you want to restore the same checkpoint.

Some components can be configured with saveState(false). When disabled, the component does not save its own checkpoint; a restart may not continue at the exact position and may have to re-read from the beginning or rely on another application mechanism. Only disable saving state when an appropriate recovery strategy is in place and the consequences are understood.

### Example of a custom ItemStreamReader

A custom reader needs to save the next position to read. The example below illustrates a simple reader using a provided list:

~~~java
public class IndexedOrderReader
        implements ItemReader<OrderInput>, ItemStream {

    private static final String INDEX_KEY =
            "indexedOrderReader.nextIndex";

    private final List<OrderInput> items;
    private int nextIndex;

    public IndexedOrderReader(List<OrderInput> items) {
        this.items = items;
    }

    @Override
    public void open(ExecutionContext executionContext) {
        nextIndex = executionContext.containsKey(INDEX_KEY)
                ? executionContext.getInt(INDEX_KEY)
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
    public void update(ExecutionContext executionContext) {
        executionContext.putInt(INDEX_KEY, nextIndex);
    }

    @Override
    public void close() {
        // Release resources if the reader opened any.
    }
}
~~~

The example shows three things that need to be done:

1. When opening the reader, restore nextIndex from ExecutionContext.
2. When reading an item, increment nextIndex to point to the next item.
3. When updating the stream, save nextIndex into ExecutionContext.

In real applications, do not load all data into a List like in the example if the source can be large. The reader should access files, databases, or APIs in a resource-bounded way. Keys in ExecutionContext must be unique per stream, and saved data must have types supported by the JobRepository's serialization mechanism.

## 6. Checkpoints must be consistent with committed data

A checkpoint is only useful when it accurately reflects the progress of committed data. Consider two operations:

- Writing business data.
- Saving the next position in ExecutionContext.

If the two operations participate in the same transaction, they can commit together or roll back together. This is the most favorable way to prevent checkpoints from getting ahead of the data.

~~~text
One chunk transaction
    |
    +-- write business data
    |
    +-- save checkpoint
    |
    +-- COMMIT together
~~~

If business data and metadata reside in two separate databases with two independent transaction managers, you cannot assume the two operations are atomic. What can happen:

- Business data commits but checkpoint does not commit: restart may reprocess items.
- Checkpoint commits but business data rolls back: restart may skip items that were not written.

In the case of split databases, you need recovery strategies like an idempotent writer, business keys, an outbox, staging, or distributed transactions if true atomicity is strictly required. Simply placing both operations in the same Java method does not make them a single transaction.

## 7. Commit policy affects checkpoint frequency

Chunk size determines how many items are normally processed between two commits. Because checkpoints are saved at chunk boundaries, chunk size also affects how frequently progress is saved.

| Chunk size | Commit/checkpoint frequency | Consequence on error |
| --- | --- | --- |
| Small | More frequent | Fewer items may have to be re-read and reprocessed |
| Large | Less frequent | More items may belong to an uncommitted chunk |

For example, with the same 10,000-item source:

- Chunk size 100 creates about 100 chunks.
- Chunk size 500 creates about 20 chunks.
- Chunk size 1,000 creates about 10 chunks.

These are theoretical chunk counts if there are no skips or factors altering item counts. Small chunks generate more metadata writes and commits. Large chunks reduce commit frequency but can make transactions long, increase memory, and increase the amount of work that must be redone when a chunk fails.

Do not choose chunk size based solely on speed. Balance throughput, memory, transaction duration, checkpoint frequency, and restart cost.

## 8. Retry, skip, and checkpoints

Retry and skip affect how a chunk is completed:

- **Retry** retries a failed operation according to the retry policy. If the transaction rolls back, the item or chunk may be reprocessed depending on where the error occurred.
- **Skip** allows skipping an item or error belonging to a configured category. The skip count is recorded and the chunk can still commit if the policy allows.
- **Rollback** discards the uncommitted changes of the current transaction.

For example:

~~~text
Chunk size = 4

Chunk 1: [1, 2, 3, 4] -> written successfully -> COMMIT
Chunk 2: [5, 6, 7, 8] -> item 6 fails
    |
    +-- retry if transient error
    |
    +-- skip if error belongs to allowed group
    |
    +-- fail if cannot be handled
~~~

If item 6 is skipped and the chunk completes, the chunk's checkpoint is committed along with the skip state. On restart, the reader does not need to reprocess the item confirmed as skipped under that checkpoint. If the chunk rolls back, the new checkpoint state is not confirmed; items may be read again.

Do not assume every exception causes a rollback or every skip causes a rollback. Behavior depends on exception type, rollback classifier, retry/skip configuration, and error timing. Test policies with the actual reader/writer types.

## 9. Restart and Step status

When restarting a Job, Spring Batch examines the status of Steps:

- Already completed Steps are usually skipped during restart.
- Failed or stopped Steps can be re-executed if the Job allows restart.
- A Step with allowStartIfComplete(true) can be re-run even if already completed, depending on flow and configuration.
- startLimit limits the number of times a Step is allowed to start.

Restarting does not mean the entire Job runs again from the beginning. Spring Batch uses metadata to determine which Steps have completed and which Steps need to continue.

For example:

~~~text
Job: dailyImport

Step 1: prepareInput       COMPLETED
Step 2: importRecords      FAILED
Step 3: publishResult      not run yet

Restart:
Step 1: usually skipped
Step 2: re-executed from saved checkpoint
Step 3: runs after Step 2 completes
~~~

If Step 1 must run again on every restart, you can consider allowStartIfComplete(true). But use it only when the preparation operation is safe to re-execute. For example, creating a directory or checking a file can be idempotent; deleting processed data or sending notifications can create unintended side effects.

## 10. Tasklet checkpoints

A custom Tasklet does not automatically have fine-grained checkpoints like a reader implementing ItemStream. If a Tasklet splits work into multiple passes and returns CONTINUABLE, the application can save progress in ExecutionContext:

~~~java
@Bean
public Step processPagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PageService pageService) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context =
                contribution.getStepExecution().getExecutionContext();

        int nextPage = context.getInt("nextPage", 0);
        boolean hasMore = pageService.processPage(nextPage);

        if (hasMore) {
            context.putInt("nextPage", nextPage + 1);
            return RepeatStatus.CONTINUABLE;
        }

        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("processPagesStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
~~~

The example illustrates how to save a position. In a real application, ensure page data and checkpoints are committed consistently. If the service writes data to a resource outside the Step's transaction manager, checkpoints may fall out of sync with business results.

For a Tasklet that performs only a single operation, a dedicated checkpoint may not be needed if the operation fits entirely within one transaction and can roll back completely. If the Tasklet calls APIs, writes files, or processes multiple already-committed parts, idempotency or durable state is needed to restart safely.

## 11. When do checkpoints not work as expected?

### Reader does not save state

A custom reader that only implements ItemReader without implementing ItemStream will not automatically save its read position in ExecutionContext. On restart, the reader may start over from the beginning or need a dedicated recovery mechanism.

### Disabling saveState

Some readers/writers have a saveState option. If disabled, that component does not save checkpoints. Verify the reason before using this configuration.

### Unstable or duplicate stream names

Reader/writer names may be used to generate keys in ExecutionContext. Duplicate names can cause key conflicts; renaming between deployments can prevent the component from finding old state. Use clear, stable names.

### Storing unsuitable objects in ExecutionContext

ExecutionContext is saved to the metadata repository and may have to be serialized. Store only small, durable data with supported types. Avoid storing connections, streams, service objects, or large object graphs.

### Source data changes between runs

Line-number or offset checkpoints may no longer be valid if a file is replaced or database rows are inserted/deleted before the read position. Use immutable inputs, snapshots, versions, or appropriate keyset checkpoints.

### Side effects outside the transaction

If an API or file has been updated while the database transaction rolls back, a restart may repeat the side effect. Use idempotency keys, an outbox, or reconciliation mechanisms.

### Using multiple databases without a shared transaction

Business data and checkpoints can commit out of sync. Design recovery for out-of-sync states instead of relying on an assumption of atomicity.

## 12. Offset-based vs. key-based checkpoints

Not every data source can store an item count to recover.

### Offset or item count

For immutable files, the reader can store the next line number or byte position. On restart, the reader reopens the file and seeks to the saved position. This is easy to understand but depends on the file not changing.

### Keyset checkpoint

For databases, you can save the last processed key:

~~~sql
SELECT order_id, created_at, total_amount
FROM orders
WHERE order_id > :lastProcessedOrderId
ORDER BY order_id ASC
FETCH FIRST 100 ROWS ONLY;
~~~

After the chunk commits, the checkpoint saves lastProcessedOrderId. The next pass queries records with IDs greater than the saved key.

Keyset checkpoints fit when keys are stable and query order is deterministic. If the business order is created_at, you may need to store both created_at and order_id as a composite key. The query condition must compare in the same order:

~~~sql
WHERE created_at > :lastCreatedAt
   OR (created_at = :lastCreatedAt AND order_id > :lastOrderId)
ORDER BY created_at, order_id
~~~

If source data can be updated while the Job runs, define a snapshot or watermark to avoid new records slipping into an already-processed range.

## 13. Observing checkpoints and commit history

JobRepository stores metadata for JobExecution, StepExecution, and ExecutionContext. You can use JobExplorer to view status rather than reading internal tables directly.

Example:

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

Counts help observe progress but do not replace the reader's checkpoint. For example, readCount is not necessarily the exact position for recovery if there are skips, retries, filters, or complex reader logic.

ExecutionContext is where components store recovery state. Do not try to infer the restart position solely from writeCount or commitCount if the reader needs another key or offset.

Do not update metadata directly to fix checkpoints. Tables are tightly related and ExecutionContext data may be serialized with a specific mechanism. Manual edits can cause the reader to recover incorrectly or corrupt Job history.

## 14. Designing safe commit policies and checkpoints

When designing a Step, clearly determine:

1. How many items should a chunk include to balance throughput, memory, and transaction duration?
2. Is the commit policy based on item count or a custom CompletionPolicy?
3. Does the reader or writer have state that needs to be saved via ItemStream?
4. What offset, page, key, or version does ExecutionContext need to store?
5. Do business data and checkpoints share the same transaction manager?
6. When a chunk rolls back, can the reader safely re-read the same items?
7. Do retry and skip alter the checkpoint or the number of items to process?
8. Is the input immutable between the first run and restart?
9. Are side effects outside the transaction idempotent?
10. Does a COMPLETED Step need to re-run on restart or not?

A good checkpoint must represent committed data, be reconstructible after the process restarts, and not depend on state that exists only in memory.

## 15. Common mistakes

### Choosing an overly large chunk size

Fewer commits, but transactions run long, memory grows, and many items may have to be reprocessed when a chunk fails. Measure performance and restart cost.

### Thinking checkpoints are saved after every item

Normally, chunk checkpoints are saved at commit boundaries. If the process stops mid-chunk, the uncommitted part may have to be re-read and reprocessed.

### Custom reader not implementing ItemStream

Without open/update to restore state, the reader cannot save its read position itself. Implement ItemStream or use a built-in reader that supports restart.

### Disabling saveState while still expecting restart to continue

When saveState is disabled, the component does not save the corresponding checkpoint. Put another recovery mechanism in place before disabling it.

### Changing input while keeping the old checkpoint

Offsets or last keys may point to the wrong position if the file/database has changed. Use input versions, file IDs, or stable snapshots.

### Saving checkpoints and business data in two independent transactions

The two sides can commit out of sync. Design idempotency, an outbox, or distributed transactions if requirements call for it.

### Using ExecutionContext as a business data store

ExecutionContext is meant for execution state needed for recovery. Do not store full items, large payloads, or long-term business data in it.

### Changing identifying parameters on restart

New identifying parameters can create a new JobInstance and ignore the old checkpoint. Keep the Job name and identifying parameters unchanged when restarting the same instance.

### Assuming a COMPLETED Step will always re-run

Completed Steps are normally skipped on restart. Enable allowStartIfComplete only when there is a clear requirement and the operation is safe to re-run.

## Conclusion

The commit policy determines the chunk completion and transaction boundary; the restart checkpoint saves state at commit boundaries so Spring Batch can continue from unfinished work. Chunk size or CompletionPolicy determines commit frequency, while ItemStream and ExecutionContext provide the mechanism to save/restore read positions or processing state. For safe restarts, checkpoints must be consistent with committed data, inputs need to be stable, identifying parameters must be kept unchanged, and side effects need to be idempotent. When metadata and business data reside in independent transactions, recovery mechanisms must be designed for out-of-sync commits.
