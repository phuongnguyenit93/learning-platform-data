# Fault-tolerant chunks and checkpoints

In Spring Batch, chunk-oriented processing divides data into groups of items. Each chunk is processed inside a transaction and is considered complete only when the required chunk operations succeed, metadata/checkpoints are updated, and the transaction commits. When the reader, processor, or writer encounters an error, the current transaction can roll back; Spring Batch applies retry/skip policies if the step is configured, while the previously committed checkpoint serves as a safe boundary for restarts.

A **checkpoint** is durable state indicating how far the step has processed. For readers and writers supporting `ItemStream`, Spring Batch persists state in the step's `ExecutionContext` at commit points. If the process stops unexpectedly, a restart can restore state from the committed checkpoint and continue the unfinished work.

Fault tolerance and checkpoints are closely linked: retry/skip determines how errors are handled in the current run; checkpoints determine which portion of progress has been durably confirmed upon transaction commit. Proper design ensures business data, metadata, reader state, and external side effects can recover consistently.

## Chunk transactions and checkpoints

A chunk step typically executes operations in this conceptual order:

1. Start the transaction for the chunk.
2. The reader fetches input items for the chunk.
3. The processor transforms, validates, or filters each item.
4. The writer writes accepted outputs.
5. `ItemStream` components update state in `ExecutionContext`.
6. Spring Batch updates `StepExecution` and persists the execution context via `JobRepository`.
7. The transaction commits.

```text
              Chunk transaction
                     |
                     v
                ItemReader
                     |
                     v
              ItemProcessor
                     |
                     v
                ItemWriter
                     |
                     v
           ItemStream.update(context)
                     |
                     v
       Save StepExecution / ExecutionContext
                     |
                     v
                   COMMIT
                     |
                     v
           New durable checkpoint
```

This diagram describes the lifecycle conceptually. Exact callback details and internal ordering may vary by step type and version, but the critical principle is that the checkpoint must represent committed data.

If the chunk commits successfully, business changes and the checkpoint participating in the same transactional resource can be saved together. If the chunk rolls back, uncommitted changes in that transaction are not retained and the durable checkpoint remains the previous one.

### Checkpoints are not in-memory state

A field in a reader such as `currentLine` exists only in the running object. If the JVM process stops, that variable is lost. Checkpoints in `ExecutionContext` are stored in the repository so they can be restored after the application restarts.

For example, a reader can store the next line number to read, the page number, or the last processed key. Never rely solely on an in-memory counter and assume Spring Batch automatically knows where to restart.

## What happens when a chunk encounters an exception?

Suppose the chunk size is 3. The reader supplies three orders; the processor handles the first two items and throws an exception on the third item.

```text
Current chunk: [O-1, O-2, O-3]

Reader       Processor          Writer
  |              |                 |
  |-- O-1 ------>|-- O-1'           |
  |-- O-2 ------>|-- O-2'           |
  |-- O-3 ------>|                 |
  |              |-- exception     |
  |              X                 |
                 |
                 v
          ROLLBACK chunk
                 |
                 v
     Previously committed checkpoint
      remains the recovery point
```

If the exception is not handled by a retry or skip policy:

- The current chunk's transaction rolls back per the rollback rules.
- The writer does not receive a complete chunk because processing stopped before the write phase.
- Database changes participating in the current transaction are rolled back.
- The previously committed checkpoint remains intact.
- The step typically ends as `FAILED`.
- Previously committed chunks are preserved.

If the exception is retried or skipped, the framework may perform additional processing attempts under fault-tolerance policies. The processor may be invoked again for the same item; a chunk may roll back before retrying or isolating the skipped item. Therefore, the processor must be safe to re-invoke.

## Rolling back the current chunk does not roll back the entire job

Each chunk has its own transaction. For example, a job processes 10,000 items with a chunk size of 100. If the first 20 chunks commit and chunk 21 hits an unrecoverable error, data from the first 20 chunks still exists.

| Processing portion | State after chunk 21 fails |
| --- | --- |
| Chunks 1–20 | Committed; business data and corresponding checkpoints remain |
| Chunk 21 | Current transaction rolls back if the error triggers rollback |
| Chunk 22 onward | Not yet processed |

This is the foundation for restarting from the last committed checkpoint. If business rules require publishing job results only when all items succeed, write to a staging table or temporary file and run a publish step after processing steps finish.

Do not treat a `JobExecution` as a single transaction. A `FAILED` status does not mean all business changes of the job rolled back.

## Checkpoints are stored in ExecutionContext

`ExecutionContext` is a key-value map attached to `StepExecution` or `JobExecution`. Readers and writers can use the step context to store state needed for restarts.

For readers, common values include:

- Current line position or file offset.
- Page number or next index.
- Last read/processed key in a deterministically ordered query.
- File name, version, or checksum of the data source.
- Small metadata required to resume reading the right source.

Example updating context:

```java
ExecutionContext context =
        stepExecution.getExecutionContext();

context.putLong("lastCommittedOrderId", lastCommittedOrderId);
context.putString("sourceVersion", sourceVersion);
```

Store only small values needed to resume progress. Do not store full item lists, entity graphs, file bytes, or large payloads in the context; those belong in a database, staging table, or object storage, while the context holds only IDs/URIs/versions.

## ItemStream and reader/writer lifecycle

`ItemStream` provides the lifecycle for components to save and restore state:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

Readers/writers needing state persistence can implement `ItemStream` or use built-in stream-capable implementations. The three methods serve these roles:

| Method | Role |
| --- | --- |
| `open(context)` | Restore state from execution context when the step starts or restarts |
| `update(context)` | Write current state to context at checkpoints |
| `close()` | Close handles and release resources |

In a chunk step, Spring Batch calls `update` at state-saving points in the chunk lifecycle. State is persisted along with metadata per transaction/repository configuration. Upon rollback, the durable checkpoint must not advance past uncommitted data.

### Custom reader example

The following example illustrates the idea of saving a resumption key. Querying and updating the key must be implemented so that state accurately reflects items belonging to committed chunks.

```java
public class OrderReader implements ItemStreamReader<OrderInput> {

    private long lastCommittedOrderId;

    @Override
    public void open(ExecutionContext context) {
        lastCommittedOrderId =
                context.getLong("lastCommittedOrderId", 0L);
    }

    @Override
    public OrderInput read() {
        return readNextOrderAfter(lastCommittedOrderId);
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("lastCommittedOrderId", lastCommittedOrderId);
    }

    @Override
    public void close() {
        // Close cursors/resources if the reader holds any.
    }
}
```

`readNextOrderAfter(...)` is an application-defined query. An actual reader must update state according to chunk processing/commit rules rather than simply incrementing an in-memory key and assuming it has committed. When using built-in readers, prefer their built-in checkpointing mechanisms instead of rewriting state management.

## Reader buffering on rollback

A regular reader may read data from a source that does not participate in transactions, such as a file or API. If a chunk rolls back, already-read items cannot naturally be pushed back to the file or API.

To support reprocessing, Spring Batch buffers read items in the chunk by default. When a rollback occurs, the framework can reuse buffered items instead of immediately asking the reader to re-read the source. This avoids dropping items simply because the source pointer has advanced.

Example:

```text
File source: O-1, O-2, O-3, O-4, O-5, ...

Reader reads O-1, O-2, O-3
          |
          v
    Processor fails
          |
          v
       ROLLBACK
          |
          v
Spring Batch reuses buffered items
during reprocessing/fault tolerance
```

This buffer is an in-process execution mechanism and does not replace durable checkpoints. When the JVM stops, the in-memory buffer is lost; restarts rely on state saved in `ExecutionContext` and the reader's restart capability.

Do not assume every reader behaves identically. Custom readers, transactional readers, and readers without `ItemStream` support can have different semantics. Check the contract of the reader in use.

## Readers from a transactional queue

Some readers read from transactional sources such as a JMS queue. When the transaction rolls back, received messages can be returned to the queue per resource semantics. In that case, Spring Batch's internal buffer may be inappropriate because the queue already has its own rollback/redelivery mechanism.

Spring Batch provides `readerIsTransactionalQueue()` on the fault-tolerant chunk builder to indicate that the reader pulls items from a transactional queue and does not need standard item buffering.

```java
@Bean
Step consumeMessagesStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderMessage> messageReader,
        ItemProcessor<OrderMessage, OrderEvent> processor,
        ItemWriter<OrderEvent> eventWriter) {

    return new StepBuilder("consumeMessagesStep", jobRepository)
            .<OrderMessage, OrderEvent>chunk(50, transactionManager)
            .reader(messageReader)
            .processor(processor)
            .writer(eventWriter)
            .faultTolerant()
            .readerIsTransactionalQueue()
            .build();
}
```

API names and transaction configuration must match your Spring Batch version and middleware. Enable `readerIsTransactionalQueue()` only when the read source genuinely has appropriate transactional semantics; do not use it for regular file or API readers.

For queues, verify that the transaction manager properly coordinates with the broker's session/connection. If the broker transaction and database transaction are two independent resources, a database rollback does not automatically return messages or vice versa. XA, outbox/inbox, or idempotent consumers may be required depending on requirements.

## Built-in readers and writers supporting checkpoints

Many built-in Spring Batch readers/writers already implement `ItemStream` and persist state. For example:

- `FlatFileItemReader` saves the file read position.
- `JdbcPagingItemReader` saves paging metadata needed to resume.
- `JdbcCursorItemReader` has its own state mechanism depending on configuration and restartability.
- `FlatFileItemWriter` saves write state to support restarts.

When configuring these components, assign stable names and check `saveState` per restart requirements.

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("${batch.input.orders}") Resource inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(inputFile)
            .delimited()
            .names("orderId", "amount")
            .fieldSetMapper(fields -> new OrderInput(
                    fields.readString("orderId"),
                    fields.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`saveState(true)` enables saving reader state to support restarts. Disabling state or using a reader without proper checkpointing can prevent the step from resuming at the old position after a JVM stop. Understand each reader's specific semantics; not every reader determines safe resumption positions the same way.

## Reader/writer names and stable state

Stateful components typically use their name to build keys in `ExecutionContext`. Names must be stable and unique within the appropriate scope.

Example:

```java
.name("orderReader")
```

Do not arbitrarily rename a reader while old job executions still need to restart, because state keys can change and the reader will not find the previous checkpoint. If two readers in the same step share the same name, state can collide or become hard to recover.

For custom `ItemStream` implementations, use clearly namespaced keys to avoid colliding with other components' keys. Maintain key and data type compatibility when deploying new versions while executions await restart.

## Fault tolerance: how do retry and skip affect checkpoints?

A fault-tolerant chunk step can handle exceptions via retry or skip. These policies determine how the current run continues, while checkpoints remain tied to transaction commits.

### Retry

Retry suits recoverable transient errors, such as deadlocks or lookup service timeouts.

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .retry(TransientLookupException.class)
        .retryLimit(3)
        .build();
```

If the processor is invoked again for the same item, any non-idempotent side effects can repeat. Keep processors focused on transformation; if calling external services is necessary, use idempotency keys or state-querying mechanisms.

Retry does not create a separate checkpoint commit for each attempt. The chunk advances to a new checkpoint only when the final chunk-processing transaction completes per the step lifecycle.

### Skip

Skip suits data errors that business rules allow bypassing:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .processor(orderProcessor)
        .writer(orderWriter)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .build();
```

When an exception is allowed to skip and within the limit, the failing item can be excluded from output and remaining items are written under fault-tolerance processing. The framework may roll back and reprocess/scan items in the chunk to isolate the failing item. Consequently, reader/processor may be re-invoked; side effects must be safe to repeat.

Skip does not mean the checkpoint advances as soon as an exception appears. The chunk checkpoint is still updated at the commit point. If `skipLimit` is exceeded, the step fails; the current chunk may roll back while previously committed chunks remain.

### Filtering

A processor returns `null` to filter a valid item that needs no output. Filtering is not an exception, does not trigger retry/skip, and does not consume `skipLimit`. `filterCount` is recorded separately on `StepExecution`.

| Processor result | Meaning | Checkpoint impact |
| --- | --- | --- |
| Returns object | Valid output | Passed to the chunk's writer |
| Returns `null` | Intentional filter | Item does not reach writer; chunk can still commit |
| Throws retryable exception | Transient error | Retried per policy; checkpoint advances only when chunk completes |
| Throws skippable exception | Error allowed to be skipped | Item is skipped per policy; checkpoint is saved once chunk completes |
| Throws unhandled exception | Error stopping step | Chunk rolls back; durable checkpoint remains at previous commit point |

## Commit interval and the scope of work to reprocess

The commit interval determines the maximum number of items in a chunk. Larger chunks generally reduce commit count and can improve batch write efficiency, but transactions last longer and more work must be reprocessed on rollback.

Smaller chunks generally:

- Commit more frequently.
- Create checkpoints more frequently.
- Reduce the number of items inside a rolled-back transaction.
- Increase transaction and repository metadata overhead.

Larger chunks generally:

- Reduce commit frequency.
- Can improve batch write throughput.
- Hold transactions and locks longer.
- Increase the volume of items needing re-reading/reprocessing on rollback or restart from a prior checkpoint.

For example, if the chunk size is 1,000 and the processor fails on the last item, much of that chunk may need reprocessing depending on reader/fault-tolerance behavior. With a chunk size of 100, transaction scope is smaller but commits are more frequent.

Choose the commit interval through real measurement: reader/processor/writer timings, lock duration, connection pool, throughput, memory, and restart requirements. There is no single optimal number for every job.

## Restarting after an unexpected process stop

Rollback within the same process and restarting after process death are two related but distinct scenarios.

### Error while the JVM is still running

If the processor throws an exception and the step handles it, the current transaction rolls back. The framework may continue with retry/skip or mark the step failed. Reader and processor may be invoked again in the same execution per policy.

### Unexpected JVM or host stop

If the process dies before commit, uncommitted database transactions are rolled back by the database when connections/sessions are released. Checkpoint metadata for the uncommitted chunk is not treated as a new progress marker. On restart, Spring Batch reads the checkpoint saved at the previous commit point.

```text
Chunk 1 -> COMMIT -> checkpoint 100
Chunk 2 -> COMMIT -> checkpoint 200
Chunk 3 -> processing -> process killed

Restart:
  restore checkpoint 200
  re-read/reprocess items after item 200
```

If the writer already caused side effects in an external system before the process died, those side effects can persist even though the database transaction did not commit. On restart, the same items may be sent again. Use idempotency keys, an outbox, or business-key reconciliation.

## Identifying JobParameters on restart

To restart the same logical job, preserve identifying parameters so Spring Batch locates the exact `JobInstance`. Restarting creates a new `JobExecution` for the same instance when status and configuration allow.

Example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("sourceFile", "orders-2026-11-15.csv", true)
        .toJobParameters();
```

On restart, reuse the exact same identifying values. Do not add a new identifying timestamp or UUID if the goal is to resume the failed execution; doing so creates a new `JobInstance` and may re-read data from the beginning.

If source file contents might change, verify version/checksum or use immutable resources. The same path with different contents can cause a restart to process a different dataset from the initial run.

## Business data and checkpoints must stay consistent

`JobRepository` stores batch metadata; the writer stores business data. When both share the same transactional resource and an appropriate transaction manager, business changes and chunk checkpoints can commit/roll back together.

If the writer writes business data to a different database from the repository, two local transactions are not automatically atomic. What can happen:

- Business data commits while checkpoint rolls back: restart may write the same items again.
- Checkpoint commits while business data has not committed: restart may skip unsaved items.

When resources are separated, design the writer to be idempotent using business keys, unique constraints, upserts, or a business processing ledger. If the job publishes messages, a transactional outbox persists events in the same business transaction so a publisher can resend safely.

Do not rely on checkpoints to prove external non-database side effects completed. Checkpoints only reflect state managed by the repository/transaction; files, APIs, and brokers require dedicated mechanisms.

## Designing an idempotent writer

During retry or restart, the same item may be sent to the writer multiple times. An idempotent writer ensures reapplying the same request causes no unintended extra business impact.

Several approaches:

- Use unique business keys and conditional insert/upsert.
- Record a processing ledger with a stable item key.
- Use idempotency keys for APIs.
- Attach stable event IDs to messages and deduplicate on the consumer.
- Use an outbox to decouple business data commit from message publishing.

PostgreSQL upsert example:

```sql
INSERT INTO processed_order (order_id, amount)
VALUES (:orderId, :amount)
ON CONFLICT (order_id)
DO UPDATE SET amount = EXCLUDED.amount;
```

Upsert is only appropriate if overwriting with the same `order_id` is valid business behavior. If newer data must not be overwritten, add a version or update-timestamp guard.

## Testing fault-tolerant chunks and checkpoints

Processor unit tests only prove logic returns outputs or throws exceptions. To test rollback/checkpoints, write integration tests with `JobRepository`, a transaction manager, and real or equivalent test resources.

Questions tests should answer:

1. Does a successful chunk persist both business data and checkpoint?
2. Does an unhandled processor exception roll back the current chunk?
3. Does data from previously committed chunks remain?
4. Does retry re-invoke the processor according to policy?
5. Does skip increment the right counters and let remaining items continue?
6. Does the reader restore state from the committed checkpoint?
7. Does restart use the same identifying parameters?
8. Does the writer avoid creating duplicates when items are reprocessed?

### Testing chunk rollback

Suppose chunk size is 2, with four inputs: the first two valid items and an invalid third item. The processor throws an exception on the third item, with no skip/retry policy. The writer writes to `processed_order` sharing the step's transaction manager.

```text
Chunk 1: O-1, O-2 -> writer -> COMMIT
Chunk 2: O-3 fails -> ROLLBACK
Expected result: only O-1, O-2 exist in the target table
```

Assertion example with `JobLauncherTestUtils`:

```java
@SpringBootTest
@SpringBatchTest
class FaultTolerantCheckpointTest {

    @Autowired
    private JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    @Qualifier("processorFailureJob")
    private Job processorFailureJob;

    @Autowired
    private JdbcTemplate jdbcTemplate;

    @BeforeEach
    void setUp() {
        jobLauncherTestUtils.setJob(processorFailureJob);
        jdbcTemplate.update("DELETE FROM processed_order");
    }

    @Test
    void keepsEarlierCommittedChunkAndRollsBackFailingChunk() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("testRunId", UUID.randomUUID().toString(), true)
                .toJobParameters();

        JobExecution execution =
                jobLauncherTestUtils.launchJob(parameters);

        assertEquals(BatchStatus.FAILED, execution.getStatus());

        List<String> ids = jdbcTemplate.queryForList(
                "SELECT order_id FROM processed_order ORDER BY order_id",
                String.class);

        assertEquals(List.of("O-1", "O-2"), ids);
    }
}
```

This is an illustrative test fixture. The test job needs reader, processor, and writer configured with proper data ordering/chunk size, and sharing the same transactional resource to assert database rollback as above.

### Testing retry

Create a processor or service stub that throws `TransientLookupException` a few times before succeeding. Verify:

- The processor is re-invoked according to the retry policy.
- The step completes if retry succeeds.
- Items are written only per the successful outcome.
- No duplicate side effects occur from failed attempts.

### Testing skip

Create an item causing `InvalidOrderException`, and configure `.skip(InvalidOrderException.class)` and `skipLimit`. Verify the bad item is not written, `processSkipCount` increments, and valid items are still written. Test exceeding the skip limit to verify the step fails.

### Testing restart from checkpoint

A restart test can:

1. Run the job with fixed identifying parameters.
2. Let several chunks commit and fail the step on a subsequent chunk.
3. Read saved `StepExecution` and `ExecutionContext` using `JobExplorer`.
4. Relaunch the same job with identical identifying parameters.
5. Verify the reader resumes from the committed checkpoint.
6. Reconcile business data to ensure committed chunks are not duplicated and uncommitted chunks are reprocessed.

Do not generate a new identifying UUID between the initial run and the restart. If test isolation is needed, generate a UUID once for that test and reuse the same value across the entire restart scenario.

### Inspecting metadata with JobExplorer

`JobExplorer` allows reading persisted metadata and execution context:

```java
JobExecution persisted = jobExplorer.getJobExecution(execution.getId());
assertNotNull(persisted);

StepExecution stepExecution = persisted.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("importOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.FAILED, stepExecution.getStatus());
assertTrue(stepExecution.getRollbackCount() > 0);
```

Step names and counter values depend on the fixture. Do not assert only `rollbackCount`; reconcile against real business data and the saved checkpoint. You can use `JobRepositoryTestUtils` to clean up test metadata, but clean up business data/files/messages separately and avoid deleting executions from concurrent tests.

## Common mistakes

### Thinking chunk rollback resets the entire job back to its initial state

Rollback applies only to the current transaction. Previously committed chunks remain. Restart design must rely on the last committed checkpoint.

### Storing checkpoints only in reader fields

In-memory fields are lost when the JVM stops. Use a reader supporting `ItemStream` or durable state persistence in `ExecutionContext`.

### Updating checkpoints independently before business data

Checkpoints can advance even when data has not committed, causing restarts to skip items. Update state in the checkpoint lifecycle and use an appropriate transactional resource.

### Assuming all readers need identical buffering

File/API readers and transactional queues have different semantics. Use `readerIsTransactionalQueue()` only when the source is genuinely transactional.

### Processor with non-idempotent side effects

Retries, skip scans, or restarts can invoke the processor multiple times. Never send messages or call APIs with repeated effects without idempotency.

### Using `saveState(false)` while still expecting restarts at the old position

Disabling state persistence prevents the reader from saving checkpoints via the built-in mechanism. Use it only when another restart mechanism exists or business rules accept re-reading from the start.

### Renaming a reader while old jobs still need restarting

Component names can be used to construct state keys. Arbitrary changes can prevent the reader from finding old checkpoints.

### Assuming Job FAILED means all business data rolled back

Committed chunks still remain. Check each step execution, checkpoint, and target data before deciding to restart or rerun from scratch.

### Testing only job status without verifying checkpoints

`FAILED` or `COMPLETED` does not prove the reader recovers properly. Tests must verify saved state and the actual resumption position.

## Design principles

When designing fault-tolerant chunks and checkpoints for production, define:

1. Chunk transaction boundaries and an appropriate commit interval.
2. Which exceptions retry, which skip, and which fail the step.
3. Whether the reader buffers items on rollback or the read source has its own transaction.
4. Whether readers/writers implement `ItemStream` and save required state.
5. That `ExecutionContext` holds small, stable, serializer-compatible checkpoints.
6. That reader/writer names and context keys stay stable across deployments.
7. That checkpoints advance only alongside committed business data.
8. That writers and processors are safe under retry/restart.
9. That non-transactional side effects have idempotency, an outbox, or reconciliation.
10. That restarts preserve identifying `JobParameters` and read the exact original data source.
11. That integration tests cover rollback, retry, skip, checkpoint, and restart.

With built-in readers/writers, prefer their built-in state management and configure `saveState` appropriately. With custom readers, implement `ItemStream` following its lifecycle and store only recoverable positions. Keep processors as pure as possible, writers idempotent, and transaction resources clearly configured.

## Key takeaways

Fault-tolerant chunks handle errors via retry/skip policies, while checkpoints store committed progress markers for restarts. In a successful chunk, Spring Batch writes outputs, updates `ItemStream` state, persists `ExecutionContext`/metadata, and commits the transaction. If a chunk rolls back, the durable checkpoint stays at the previous commit point; previously committed chunks are not rolled back. Non-transactional readers typically have items buffered by the framework for reprocessing along rollback paths; transactional queues can use `readerIsTransactionalQueue()` to rely on queue rollback. Keep state in `ExecutionContext` small and stable, preserve identifying parameters on restart, avoid non-idempotent side effects in processors, and ensure writers handle replay safely. Test transaction rollback, checkpoint metadata, and actual business data.
