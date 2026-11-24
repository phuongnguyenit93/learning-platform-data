# Updating Context Before Commit

In Spring Batch, `ExecutionContext` stores the state needed to track or restore a Job/Step execution. With chunk-oriented processing, an important example is the reader's current position: after a chunk is written successfully, the next restart needs to know where to resume reading.

Spring Batch coordinates updating `ExecutionContext` with the chunk's transaction. Components implementing `ItemStream` are invoked through the `update(ExecutionContext)` callback to write their internal state into the context. The framework persists the context and Step metadata before the chunk transaction commits. When metadata and business data participate in the same appropriate transaction, the checkpoint and the chunk's data changes are committed as a consistent unit.

This ordering helps avoid two dangerous situations: business data is committed while the checkpoint is not yet saved, causing restart to read and write duplicates; or the checkpoint is saved while the business data is not yet committed, causing restart to skip data that was not written. Therefore, updating the context before commit is an important part of Spring Batch's restartability and consistency.

## 1. What State Is ExecutionContext Used to Store?

`ExecutionContext` is a key/value storage area bound to an execution. It is suitable for small information that needs to survive across metadata updates, especially checkpoints to resume work after a Step is interrupted.

Examples of state that can be stored:

- The last line or position read from a file.
- The last ID processed when reading data in order.
- The next page to read from a paginated API.
- A key or batch ID that a subsequent Step needs to use.
- Minimal internal state that needs to be restored on restart.

Do not use ExecutionContext as a place to store all business data or the item list of a Job. Store keys, positions, offsets, or lightweight information; the main data still resides in the database, file, or appropriate source/target system.

### Step ExecutionContext and Job ExecutionContext

Spring Batch has two commonly used context scopes:

| Context | Scope | Use case |
|---|---|---|
| `StepExecution.getExecutionContext()` | One Step execution | Private checkpoint of a reader/writer or Tasklet within that Step. |
| `JobExecution.getExecutionContext()` | One Job execution | Small data that needs to be shared between Steps within the same JobExecution. |

A reader's checkpoint should generally reside in the Step ExecutionContext because it is tied to that Step's read position. If one Step prepares a batch ID for the next Step to use, that ID can be stored in the Job ExecutionContext.

The two contexts have different lifecycles and purposes. Do not place a reader checkpoint in the Job context just because you want to read it in multiple places; doing so may cause different Step executions or other Steps to share state inappropriately.

## 2. Why Must the Context Be Updated Before Commit?

Suppose a chunk processes 100 orders. The reader has read items 1 through 100, and the writer writes those orders to the database. At the same time, the reader needs to save a checkpoint indicating that this portion of data has been processed so a restart resumes from item 101.

If business data is committed first and the checkpoint is saved afterward in a separate transaction, the process could stop between the two operations:

```text
Write 100 orders
       |
       v
COMMIT business data
       |
       X  Process stops
       |
       v
Save checkpoint = 100 (did not happen)
```

On restart, metadata still indicates the old position. The reader may re-read items 1–100 and the writer may write duplicates.

The opposite situation is also dangerous. If the checkpoint is committed before the business data in an independent transaction, the process could stop after the checkpoint has advanced to 100 but before the orders are committed. The restart will begin from item 101, causing items 1–100 to be skipped even though the target data was never saved.

The goal is to update the checkpoint and write business data within the same transaction boundary when possible:

```text
Start chunk transaction
       |
       v
Reader reads items 1–100
       |
       v
Processor processes items
       |
       v
Writer writes business data
       |
       v
ItemStream.update(context)
       |
       v
JobRepository saves Step ExecutionContext
       |
       v
COMMIT transaction
       |
       +--> Both data and checkpoint are confirmed together
```

When business data and the metadata repository participate in the same properly managed transaction, commit confirms both. If the transaction rolls back, both the business changes and the checkpoint update in that transaction are reverted. On restart, the framework uses the last committed checkpoint.

This is why the stream update callback is called before the chunk transaction commits. It provides the opportunity for the reader's state to be saved together with the chunk's write results.

## 3. ItemStream Lifecycle and the update Callback

Readers/writers that need to save and restore state can implement `ItemStream` or extended interfaces such as `ItemStreamReader` and `ItemStreamWriter`.

Three main callbacks:

| Callback | When called | Responsibility |
|---|---|---|
| `open(ExecutionContext)` | When the stream is opened in the Step lifecycle | Restores saved state or initializes new state. |
| `update(ExecutionContext)` | At the state update point before commit | Writes the stream's current state into ExecutionContext. |
| `close()` | When the stream ends its lifecycle | Closes files, cursors, or resources in use. |

Abbreviated contract:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext)
            throws ItemStreamException;

    void update(ExecutionContext executionContext)
            throws ItemStreamException;

    void close() throws ItemStreamException;
}
```

In a chunk Step, Spring Batch manages the lifecycle of registered streams. After the chunk finishes processing and before the transaction commits, the framework calls `update` so the stream puts the state to be saved into the context. The repository then saves the context according to JobRepository's mechanism.

`update` does not mean every item creates a commit. The callback is called at the chunk/transaction stream update point, not to commit each item individually. Commit interval and CompletionPolicy still determine chunk boundaries.

## 4. Example of a Reader Saving a Checkpoint

Suppose a custom reader reads a list of orders by position. The reader needs to save the next item index so that on restart it can continue from the committed position.

```java
public class CheckpointingOrderReader
        implements ItemStreamReader<OrderInput> {

    private static final String INDEX_KEY = "orders.reader.current.index";

    private int currentIndex;

    @Override
    public void open(ExecutionContext context) {
        currentIndex = context.getInt(INDEX_KEY, 0);
        openSourceAt(currentIndex);
    }

    @Override
    public OrderInput read() {
        OrderInput item = readNext();
        if (item != null) {
            currentIndex++;
        }
        return item;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putInt(INDEX_KEY, currentIndex);
    }

    @Override
    public void close() {
        closeSource();
    }

    private void openSourceAt(int index) {
        // Open the data source at the position to restore.
    }

    private OrderInput readNext() {
        // Read the next item from the data source.
        return null;
    }

    private void closeSource() {
        // Close the corresponding file, cursor, or resource.
    }
}
```

This is an illustrative skeleton; `readNext()` and the source management methods must be implemented according to the actual data type. The key points are:

1. `open` retrieves the committed checkpoint from ExecutionContext.
2. `read` updates the in-memory state as items are read.
3. `update` copies the current state into ExecutionContext before commit.
4. If the chunk commits successfully, the new checkpoint is saved.
5. If the chunk rolls back, that chunk's checkpoint is not considered a committed checkpoint when the repository and data share the transaction.

With a custom reader, ensure the saved position can be restored accurately. If the data source changes order between two runs, a simple line index may not be enough; use a stable ordering or an appropriate business key.

## 5. Configuring a Stateful Reader in a Step

When a reader implements `ItemStream`, the Step needs to manage its lifecycle to invoke `open`, `update`, and `close`. Standard Spring Batch readers are usually registered automatically when configured directly in a Step.

Example with a standard file reader:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "customerId", "amount")
            .targetType(OrderInput.class)
            .saveState(true)
            .build();
}
```

Standard stateful readers usually have a `saveState` option; enable it and set a stable reader name so metadata is saved properly. `@StepScope` allows the reader to receive JobParameters of the running execution and creates the instance within the Step scope.

When wrapping a stateful reader inside a delegate or decorator, ensure the inner stream is also registered with the Step. If the framework does not automatically detect the delegate, you can register the stream explicitly using `.stream(...)` on the appropriate Step builder.

Do not create a new reader on every `read` call or hold checkpoint state in a field of a singleton shared across multiple executions. The state of a run must be tied to the exact StepExecution.

## 6. Updating Step ExecutionContext in a Tasklet

A Tasklet can also write state to Step ExecutionContext. For example, a Tasklet performing a preparation pass can save a staging code for the next Step to read:

```java
.tasklet((contribution, chunkContext) -> {
    StepExecution stepExecution = contribution.getStepExecution();
    ExecutionContext context = stepExecution.getExecutionContext();

    String stagingBatchId = stagingService.prepareBatch();
    context.putString("staging.batch.id", stagingBatchId);

    return RepeatStatus.FINISHED;
}, transactionManager)
```

With TaskletStep, the framework also manages the transaction of the Tasklet invocation and updates metadata according to the Step lifecycle. If the Tasklet returns `CONTINUABLE`, subsequent invocations can update the context multiple times. Update the checkpoint consistently with the completed portion of work.

If the next Step needs to read this value, it can obtain it from Job ExecutionContext or use the promotion mechanism from Step ExecutionContext to Job ExecutionContext, depending on how the Job is organized. Do not assume every Step automatically sees the previous Step's Step context.

## 7. How Are Step ExecutionContext and Job ExecutionContext Saved?

With JDBC JobRepository, Spring Batch stores the two contexts in separate metadata tables:

| Table | Content |
|---|---|
| `BATCH_STEP_EXECUTION_CONTEXT` | ExecutionContext belonging to a StepExecution, usually containing reader/writer checkpoints. |
| `BATCH_JOB_EXECUTION_CONTEXT` | ExecutionContext belonging to a JobExecution, used for data shared between Steps. |

When a chunk completes, JobRepository saves the StepExecution's context along with related metadata. For the Job-level context, the framework saves it at corresponding JobExecution update points. The serialization method depends on the serializer configuration and Spring Batch version.

Values put into ExecutionContext must be serializable by the configured mechanism. Prefer simple data types such as `String`, numbers, appropriately represented dates, or serializable objects with a stable structure. Avoid storing objects containing connections, streams, large entity graphs, or non-serializable resources.

Key names should be stable and namespaced, for example `orders.reader.current.index`, to avoid collisions with keys of other readers or components. When changing checkpoint structure between application versions, consider compatibility with old JobExecutions that may still restart.

## 8. What Happens When a Chunk Rolls Back?

Suppose chunk size is 100. The reader reads items 1–100, the processor processes them, and the writer writes to the database. Before commit, the stream updates the checkpoint to 100. If the transaction commits successfully, both the data and the new checkpoint are confirmed.

If the writer throws an exception before commit:

```text
Chunk starts
  |
  +--> Reader reads items 1–100
  +--> Processor processes
  +--> Writer writes data
  +--> ItemStream.update: checkpoint = 100
  +--> JobRepository updates context
  +--> Writer/transaction encounters error
  +--> ROLLBACK

The last committed checkpoint remains the checkpoint before this chunk.
```

When the Job restarts, the reader restores the most recently committed checkpoint and reprocesses the unfinished portion. This is the desired behavior: the framework does not treat a rolled-back chunk as complete just because the reader already read those items in memory.

However, this behavior only guarantees consistency when metadata updates and business data actually participate in the same appropriate transaction. If JobRepository and the writer use two independent datasources or two independent transaction managers, a normal JDBC transaction cannot automatically guarantee atomic commit/rollback for both. In that case, XA/JTA is needed if the system requires distributed transactions, or checkpoint/idempotency and reconciliation must be designed to handle the gap between the two resources.

## 9. Why Not Update the Checkpoint After Commit?

If the application saves the checkpoint manually after the chunk has already committed, there is a time gap between the two operations:

```text
Writer writes data
       |
       v
COMMIT data
       |
       X  Process crash
       |
       v
Save checkpoint
```

When the process crashes at point `X`, the data has been written, but the checkpoint has not changed. Restart may re-read the same items. If the writer is not idempotent, the system may create duplicate records or repeat side effects.

Spring Batch calls `ItemStream.update` before commit so the checkpoint can participate in the same transaction as the chunk data. Do not build your own "commit data first, update checkpoint later" mechanism using two independent operations.

Conversely, saving the checkpoint in a separate transaction before the data is committed can create a situation where the checkpoint advances while the data has not yet been written. The goal is not merely "writing the context earlier", but **writing the context before commit within the same appropriate transaction boundary**.

## 10. When Metadata and Business Data Use Different Transaction Managers

In a simple application, the metadata repository and business data may share a single database and transaction manager. In that case, context updates, StepExecution updates, and chunk data writes can participate in the same transaction.

In large systems, metadata and business data may reside in two different databases. If two independent transaction managers are used, committing the business database is not automatically atomic with committing metadata. What can happen:

- Business data commits successfully, but metadata rolls back or is not updated.
- Metadata checkpoint is saved, but business data rolls back.
- One resource loses connection while the other commits.

Design options:

- Use distributed/XA transactions when requirements and infrastructure allow.
- Design idempotent writers so re-writing the same business key does not create wrong data.
- Use processing status and reconciliation to detect gaps between metadata and business data.
- Store business checkpoints in the same database as the target data if a clear local commit boundary is needed.
- Use outbox/inbox for cross-system side effects.

Do not assume a single `PlatformTransactionManager` manages multiple databases simply because they are called in the same Step. Clearly identify which resources actually participate in the transaction.

## 11. Checkpoint Must Reflect Committed Work

A checkpoint is a statement of progress: "all data before this position has been processed according to the application's guarantee level." Therefore, the checkpoint value must be updated at the right time.

Example with a paginated reader:

```java
int pageToRead = context.getInt("next.page", 0);
Page<OrderInput> page = service.fetchPage(pageToRead);

// Read and process items of the current page.
// Only set next.page after the corresponding portion of work
// is included in the commit transaction by design.
context.putInt("next.page", pageToRead + 1);
```

This code snippet illustrates the principle; in practice, context update logic should reside in `ItemStream.update` or an appropriate checkpointing mechanism so the framework persists it before commit. Do not update `next.page` immediately upon sending the request if that page has not been written successfully.

For database data, using an ascending key or stable cursor is usually safer than an offset if source data can change while the Job runs. If offset paging is used and records are added/deleted between two reads, some items may be duplicated or missed.

## 12. In-Memory State and Saved Checkpoint

While the Step runs, the reader may have incremented an index in an internal field. `update` copies that value into ExecutionContext at the update point. However, in-memory state does not equal a durably committed checkpoint.

Distinguish:

- **State in the reader:** current state of the reader object in the running process.
- **In-memory ExecutionContext:** key/value pairs updated in the current execution.
- **Committed checkpoint:** context durably saved along with a successful transaction and restorable on restart.

If the transaction rolls back, do not treat the context value currently in the object as the final checkpoint. On restart, Spring Batch restores the context saved in JobRepository. Custom readers need a way to recover in-memory state suitable for rollback/retry within the same execution, or rely on buffering and the framework's retry mechanism.

## 13. saveState and Standard Readers/Writers

Many standard Spring Batch readers/writers support saving state. For example, `FlatFileItemReader` can save the read position for restart. Depending on the reader, `saveState(true)` can be configured or is enabled by default.

When `saveState` is turned off, the reader will not save its internal checkpoint. This can be suitable if the data source does not need restart or the reader is designed to be stateless, though it may cause the Step to re-read from the beginning after restart.

Some notes:

- Set a stable stream/reader name so keys in ExecutionContext are stable.
- Ensure the reader can reopen the source at the saved position.
- Do not change source data order between runs and restarts if the checkpoint depends on position.
- With delegate streams, register the lifecycle properly so `update` is called.
- If the reader is used in a multi-threaded Step, verify its thread safety and checkpointing mechanism.

## 14. Storing Multiple Context Values and Key Management

A Step may have multiple streams or components writing to ExecutionContext. Name keys clearly and avoid collisions:

```java
ExecutionContext context = stepExecution.getExecutionContext();

context.putLong("orders.reader.last.id", lastOrderId);
context.putInt("orders.reader.page", currentPage);
context.putString("orders.batch.status", "PREPARED");
```

Use namespaces by component or business domain. Do not overwrite keys managed by another reader. Do not store sensitive info such as passwords, tokens, or private keys in the context because metadata can be queried by anyone with permission to read JobRepository.

When changing keys or data types between application versions, consider old JobExecutions that may restart. You may need to support reading both old and new keys during a transition period or mark old executions as no longer restartable per operational procedure.

## 15. Monitoring and Diagnosing Checkpoints

When a Job restarts at the wrong position or processes duplicate data, check:

1. Which `JobInstance` and `JobExecution` is being restarted.
2. What status the previous `StepExecution` had.
3. Which checkpoint keys were saved in Step ExecutionContext.
4. Whether the reader actually implements `ItemStream` and has `saveState` enabled.
5. Whether the `update` callback is invoked during the Step lifecycle.
6. Whether the metadata repository and business writer share the same transaction boundary.
7. Whether the data source has a stable order between the two runs.
8. Whether the writer can write duplicates if items are re-read.

You can read the context via `JobExplorer` to inspect saved metadata. Do not edit serialized strings directly in the `BATCH_STEP_EXECUTION_CONTEXT` table to force a reader to another position. Changing a checkpoint should be done via APIs or designed recovery procedures and must reconcile business data first.

## 16. Common Mistakes

### Updating checkpoint after writer commits

If the process stops between committing data and saving context, restart may re-read already written items. Let Spring Batch update the stream before commit and keep metadata in the appropriate transaction.

### Updating checkpoint before data is written

If the checkpoint is saved independently before business data, a crash can cause restart to skip uncommitted items. The checkpoint must stay synchronized with committed work.

### Reader does not implement ItemStream

A custom reader that does not save state will not have checkpoints automatically. Implement `ItemStreamReader` or register an appropriate stream and implement `open`, `update`, and `close`.

### Not registering delegate stream

An outer wrapper reader can hide a delegate implementing `ItemStream`. If the delegate does not have its lifecycle managed by the framework, `update` will not be called. Register the stream explicitly when needed.

### Using unstable checkpoint keys

Renaming a reader or key can make old contexts unreadable. Keep names stable or have a compatibility strategy when upgrading.

### Using offset on a changing data source

If source data is added/deleted between a run and a restart, an offset can point to a different position. Use stable ordering, business keys, or appropriate snapshots.

### Assuming two transaction managers commit atomically

Metadata and business data in two independent databases are not automatically committed/rolled back as a single transaction. XA or idempotency and reconciliation design is needed.

### Storing too much data in the context

The context is serialized and stored as metadata. Storing large lists or complex objects bloats metadata, increases read/write costs, and complicates serializer upgrades. Store only checkpoints and necessary info.

## 17. Procedure for Implementing Context Updates Before Commit

When building a stateful reader or writer, you can follow this sequence:

1. Identify the minimal state needed to restore, e.g., current index, last processed ID, or next page.
2. Choose Step ExecutionContext for Step-specific checkpoints.
3. Implement `ItemStream` or use a standard stateful reader/writer.
4. In `open`, restore state from the saved ExecutionContext.
5. In `read`/`write`, update internal state according to actual progress.
6. In `update`, copy state into ExecutionContext for Spring Batch to save before commit.
7. Ensure the metadata repository and business data use an appropriate transaction boundary if atomic commit is required.
8. Test successful commit, rollback, process crash, and restart scenarios.
9. Verify that the writer is idempotent or has business keys to protect when the source must be re-read.
10. Monitor context size and maintain key/data type compatibility across upgrades.

| Scenario | Expected result |
|---|---|
| Chunk commits successfully | Business data and new checkpoint are confirmed. |
| Chunk rolls back before commit | Previously committed checkpoint remains the restart mark. |
| Process stops after commit | Restart uses the new checkpoint saved with the chunk. |
| Process stops before commit | Restart does not treat the uncommitted chunk as finished. |
| Reader does not support state | Need to redesign the reader or accept re-reading per policy. |
| Metadata and business data in different transactions | XA or idempotency/reconciliation mechanism is needed. |

## Conclusion

Spring Batch calls `ItemStream.update(ExecutionContext)` before the chunk transaction commits so reader/writer state can be saved alongside chunk processing results. When business data and metadata participate in the same appropriate transaction, the checkpoint is confirmed only when the chunk commits; on rollback, that chunk's checkpoint does not become a committed restart mark. Store checkpoints in Step ExecutionContext, restore via `open`, update via `update`, keep keys stable, and ensure the writer is safe when re-run. If metadata and business data reside in independent transaction managers, additional XA, idempotency, or reconciliation must be designed since a regular transaction cannot guarantee atomicity across multiple resources.
