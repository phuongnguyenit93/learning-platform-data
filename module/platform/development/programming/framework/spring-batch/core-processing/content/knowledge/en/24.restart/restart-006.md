# Restarting with writer state

In Spring Batch, restarting does not only require knowing how far the reader has read. The writer may also need to restore state to continue writing at the right position after a step fails or the process stops abruptly. For example, a file-export writer needs to know how many lines have been written; a writer producing a sequential format may need to restore an offset; a custom writer may need to know the last committed sequence.

Spring Batch supports this through `ItemStream` and `ExecutionContext`. A stateful writer can reopen from a saved checkpoint, update state at commit points, and close resources when the step finishes. Many built-in writers, notably `FlatFileItemWriter`, already support state saving. For custom writers, the application must explicitly design the lifecycle, transaction boundaries, and state recovery strategy.

Crucially, writer state must describe **the output that has been durably confirmed**. If state advances before output commits, a restart may skip unwritten data. If output is written without saving state, a restart may write duplicates. Writer state must therefore be coordinated with step transactions and checkpoints.

## Reader checkpoints and writer state

In a chunk-oriented step, both the reader and writer may need to save state, but they answer two different questions:

| Component | Question answered by state | Example |
| --- | --- | --- |
| Reader | Which item needs to be read next? | File line number, page number, last read key |
| Writer | How far has output been written? | Lines written, byte offset, last committed sequence |

Reader state prevents skipping input; writer state helps resume output at the right position. Safe job restarts require both sides to align. If the reader resumes at item 501 while the writer writes from the start of the file, output may be duplicated. Conversely, if the writer resumes at line 501 while the reader re-reads from the first item, data may be lost or corrupted.

In a chunk step, the high-level flow is as follows:

```text
                Step starts / restarts
                         |
                         v
        Reader.open(step ExecutionContext)
        Writer.open(step ExecutionContext)
                         |
                         v
                 Read and process chunk
                         |
                         v
                    Writer.write
                         |
                         v
            Reader/Writer.update(context)
                         |
                         v
          Save StepExecution and ExecutionContext
                         |
                         v
                      COMMIT
                         |
                         v
             New checkpoint is now durable
```

This is a conceptual model. Spring Batch coordinates the `ItemStream` lifecycle and persists metadata according to the step's transaction/repository configuration. Internal details may vary by writer type and framework version.

## ItemStream: the contract for saving and restoring writer state

`ItemStream` provides three primary callbacks:

```java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
```

In Spring Batch, actual method signatures may declare `ItemStreamException`; the simplified snippet above highlights each callback's role.

| Callback | Timing and purpose |
| --- | --- |
| `open(context)` | Restore saved state when the step starts or restarts; open output resources |
| `write(chunk)` | Write the output of the current chunk |
| `update(context)` | Put current state into `ExecutionContext` at checkpoints |
| `close()` | Close files, streams, connections, or resources owned by the writer |

`ItemWriter` itself does not have to save state. A stateful writer can implement `ItemStreamWriter<T>` or combine `ItemWriter<T>` and `ItemStream`. Built-in writers generally implement the proper contract.

In a chunk-oriented step, Spring Batch manages streams registered with the step. Direct readers and writers are typically registered automatically when they implement `ItemStream`. If a writer is wrapped in a delegate/composite or created via an adapter, verify that delegate streams are registered and the `open/update/close` lifecycle is invoked. Additional streams can be registered using `.stream(...)` on the step when needed.

## ExecutionContext and writer checkpoints

Writer state is usually stored in the step `ExecutionContext`, managed by `JobRepository`. With a JDBC repository, step context is persisted in metadata, typically in the `BATCH_STEP_EXECUTION_CONTEXT` table.

Appropriate values to store include:

- Number of lines written successfully.
- Committed byte offset or record sequence.
- ID of the current output segment.
- Resource name or object key of the output.
- A small version/checksum to verify the resumed output matches the expected version.

Example state key managed by a writer:

```java
private static final String WRITTEN_COUNT_KEY =
        "orderFileWriter.current.count";
```

Key names must remain stable across deployments while old executions may still restart. Namespace keys by the writer name to avoid collisions with other readers or writers.

Do not store entire outputs, payloads, or item lists in the context. Store only the position or reference needed to resume. Large contexts increase serialization cost, database I/O, and restart latency.

## FlatFileItemWriter supports restart

`FlatFileItemWriter` is a common example of a stateful writer. It writes items as lines via a `LineAggregator` and can save the number of lines written into `ExecutionContext` to resume the file after a restart.

Example Spring Batch 5 configuration:

```java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .encoding("UTF-8")
            .lineAggregator(order -> String.join(
                    ",",
                    order.orderId(),
                    order.customerId(),
                    order.amount().toPlainString()))
            .saveState(true)
            .headerCallback(writer ->
                    writer.write("orderId,customerId,amount"))
            .build();
}
```

In this example:

- `.name("orderFileWriter")` sets a stable name for the writer to key state in context.
- `.resource(...)` specifies the target file.
- `.lineAggregator(...)` converts each `Order` into a line.
- `.saveState(true)` enables state saving to support restarts.
- The header is written according to the writer's lifecycle; on restart, the writer recognizes the file already exists and resumes in the right state.

`outputFile` must remain stable for the same logical job execution. If each restart generates a new path with a different timestamp or UUID, the writer may create a new file instead of resuming the prior execution's file.

In production, handle CSV quoting/escaping properly. The `String.join` example above only illustrates field mapping; it does not escape commas, quotes, or newlines inside values.

### Why must the writer name stay stable?

Writers use their name to store and look up state in `ExecutionContext`. If you rename `orderFileWriter` to `orderExportWriter` while old executions still need restarting, the new writer may look up a different key and fail to restore the previous position.

Keep names stable across deployments while restartable executions exist. If you must change names or state formats, plan a migration or drain old executions before deploying.

### SaveState

`saveState(true)` allows the writer to persist state to the execution context. For writers that support restarts, configure this option explicitly to state intent and avoid accidentally disabling state.

If `saveState(false)` is set, the writer does not save its internal checkpoint. When the step restarts, the writer may not know where to resume. Depending on file and output configuration, this can overwrite from the beginning, append at the wrong position, or fail to recover cleanly. Only disable state when the application has another recovery mechanism and has tested that behavior.

### The file must still exist on restart

Execution context only stores state, not file contents. If the file was deleted, moved, or replaced after the step failed, the writer cannot reconstruct already-committed output solely from a line count checkpoint.

Retain the output file of a failed execution for as long as restarts are permitted. If consumers expect a final filename, write to a temporary file tied to the logical execution and only publish/rename after the job succeeds. Rename behavior and atomicity depend on the filesystem or object storage.

## How does a writer restart work?

Suppose the writer wrote and committed two chunks to a file:

```text
orders-output.csv
  Header
  O-001
  O-002
  O-003
  O-004

Writer checkpoint: 4 data lines committed
```

Then the next chunk fails. When restarting the same `JobInstance`, Spring Batch restores the saved step context. `FlatFileItemWriter.open(context)` reads the writer's state, identifies the number of lines written, and reopens the resource according to its restart mechanism. The writer continues with new output rather than rewriting already-committed lines.

```text
First run:
  Chunk 1 -> write O-001, O-002 -> COMMIT
  Chunk 2 -> write O-003, O-004 -> COMMIT
  Chunk 3 -> error -> ROLLBACK

Restart:
  Reader restores input checkpoint
  Writer restores output checkpoint = 4 lines
  Reprocess uncommitted portion
  Append remaining lines
```

The desired result is a final file with the proper header and each output item appearing the expected number of times per business rules. Writer state locates already-written output; reader checkpoints identify which input remains to be reprocessed.

## Writer state and transaction boundaries

Writer state must be updated alongside chunk checkpoints. In a successful chunk, the writer writes output, `ItemStream.update` writes state to context, the repository saves metadata, and the transaction commits. On rollback, state metadata of the uncommitted chunk does not become a new durable checkpoint.

However, distinguish **state in the database** from **actual side effects on the output resource**. With a JDBC writer sharing the step's datasource/transaction manager, business data and checkpoints can commit/roll back in the same transaction. With files or message brokers, a JDBC transaction does not automatically cover all I/O operations; built-in writers must handle buffering/repositioning properly or the application must add idempotency/reconciliation.

| Writer target | State/checkpoint | Considerations on rollback/restart |
| --- | --- | --- |
| `FlatFileItemWriter` | Line count/file state in context | Use transaction/restart-capable writer; keep file and path stable |
| JDBC sharing transaction resource | Typically relies on database commit and step checkpoint | Business rows and metadata can commit/roll back together |
| JDBC on separate datasource | May have independent transactions | Use unique keys, upserts, or ledgers to handle re-writes |
| Message broker | Offset/sequence/event ID depending on writer | Messages may already be received by the broker even if chunk rolls back |
| Custom writer | Application-defined in `ExecutionContext` | Must synchronize state with output commit and handle rollbacks explicitly |

## JDBC writers usually do not need separate writer state

`JdbcBatchItemWriter` usually does not need to store line positions or offsets like a file writer. It writes data to the database using batch SQL. Safe restartability primarily relies on step transactions, reader checkpoints, and SQL/business key design.

For example:

```java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO orders(order_id, customer_id, amount)
                    VALUES (:orderId, :customerId, :amount)
                    """)
            .beanMapped()
            .build();
}
```

If the writer and `JobRepository` share the same transactional resource and transaction manager, uncommitted inserts of a chunk roll back alongside the checkpoint. On restart, the reader re-reads items from the uncommitted chunk and the writer executes the inserts again.

If the database committed while metadata/checkpoints in another resource did not, the same items may be written again. Use unique constraints on business keys, upserts, or ledger tables to prevent duplicates. Do not add a writer counter to context when the database already has proper transactional/idempotency mechanisms.

## Custom writers must implement ItemStream

If a writer manages file positions, sequences, or output state itself, it can implement `ItemStreamWriter<T>`. The writer must:

1. Restore state in `open(context)`.
2. Write the chunk in `write(chunk)`.
3. Update the checkpoint in context during `update(context)`.
4. Close resources in `close()`.

Illustrative skeleton for a sequential writer:

```java
public class SequenceItemWriter<T> implements ItemStreamWriter<T> {

    private static final String LAST_SEQUENCE_KEY =
            "sequenceWriter.lastCommittedSequence";

    private long lastCommittedSequence;

    @Override
    public void open(ExecutionContext context) {
        lastCommittedSequence = context.getLong(LAST_SEQUENCE_KEY, 0L);
        openOutputAt(lastCommittedSequence);
    }

    @Override
    public void write(Chunk<? extends T> chunk) {
        // Write items to output following the next sequence.
        // The sink must support appropriate transaction/rollback semantics or idempotency.
        writeChunkToSink(chunk);
    }

    @Override
    public void update(ExecutionContext context) {
        // Save the sequence confirmed committed by the sink per sink contract.
        context.putLong(LAST_SEQUENCE_KEY, lastCommittedSequence);
    }

    @Override
    public void close() {
        closeOutput();
    }
}
```

`openOutputAt`, `writeChunkToSink`, and `closeOutput` are illustrative application-implemented methods. This is a lifecycle skeleton, not a complete copy-pasteable writer. In particular, `lastCommittedSequence` must only be updated after output is actually confirmed under the transaction contract. If `write` mutates a field before commit and the chunk rolls back, the writer must restore in-memory state or use a transaction-aware sink; merely saving values in `ExecutionContext` will not roll back external side effects.

### Avoid advancing in-memory state ahead of the checkpoint

A common bug is incrementing a counter in `write()` and keeping that counter even when the transaction rolls back. When the chunk is retried in the same process, the in-memory counter may have advanced even though output did not commit. The writer can then skip sequences or write at misaligned positions.

Design options:

- Use built-in writers that already manage transactions/state such as `FlatFileItemWriter` when appropriate.
- Use a transactional sink and confirm state only after commit.
- Separate `committedState` and `pendingState`, restoring pending state on rollback via appropriate transaction synchronization.
- Design writes to be idempotent by sequence/business key so replay is safe.
- If the output does not support rollback, write staging output and publish after the step/job completes.

Do not implement a stateful writer using only a mutable counter without defining rollback behavior.

## Registering writer streams in a step

When a writer is passed directly to `.writer(...)` and implements `ItemStream`, Spring Batch can normally manage that stream's lifecycle. However, with delegates nested inside `CompositeItemWriter`, adapters, or custom wrappers, ensure inner streams are invoked.

Example with a composite writer:

```java
@Bean
CompositeItemWriter<Order> compositeOrderWriter(
        JdbcBatchItemWriter<Order> databaseWriter,
        FlatFileItemWriter<Order> fileWriter) throws Exception {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
```

When using a composite, check whether your Spring Batch implementation/version forwards the `ItemStream` lifecycle to delegates. If the wrapper does not automatically register delegate streams, register them explicitly on the step:

```java
return new StepBuilder("exportOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(orderReader)
        .writer(compositeOrderWriter)
        .stream(fileWriter)
        .build();
```

Registering the stream ensures the delegate writer receives `open`, `update`, and `close` to save/restore state. Failing to register a required stream can cause a file writer to work on the first run but lack a valid checkpoint on restart.

## Multiple writers and multiple output targets

A single chunk may be written to both a database and a file via `CompositeItemWriter`. On restart, each delegate may have different state requirements:

- Database writers rely on transactions and idempotency.
- File writers need to store line counts/write positions.
- Message writers need event IDs/sequences and acknowledgements.

Writers must be initialized, have state updated, and be closed following the proper lifecycle. A failure in one delegate can roll back the chunk under the step's transaction, while side effects already written by another delegate to an external resource may still remain.

For example, database commits and file output without a shared atomic transaction can drift out of sync. This requires staging files, an outbox, or a reconciliation process. A composite writer does not automatically create a distributed transaction across all targets.

## File paths and JobParameters on restart

Writers often obtain resources from `JobParameters`. If the output path changes on every execution, a restart may write to a new file instead of resuming the old file.

Example stable parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("outputFile", "/batch/output/orders-2026-11-15.csv", true)
        .toJobParameters();
```

When restarting the same `JobInstance`, reuse the identifying parameters and the same output path. If every business run must produce a new file, intentionally create a new logical run with a business-meaningful identifying parameter and define clearly how old files are handled.

Do not use a new timestamp or UUID on restart just to create a different file. Doing so can create a new `JobInstance` and break the link to the saved writer checkpoint.

If the output path is a non-identifying parameter, ensure the restart still passes the original value. Having the same identifying parameters with a different output path can cause the job to resume with the old checkpoint while writing to a different resource, resulting in an incomplete file. Either make the path an identifying parameter or store/verify a stable path in context.

## Writer state and restarting with existing files

On restart, writers must distinguish:

- Fresh run with no state: apply new-file creation or existing-file handling policy per configuration.
- Restart run with state: reopen the created file and continue from the checkpoint.
- File deleted or replaced: state no longer matches the resource; fail with an error or recover via an explicit procedure.

Do not enable `append` mechanically. Appending can suit certain streams, but if a checkpoint already saved a line count and the file contains prior output, improper appending can create duplicates. Use the writer's restart-state mechanism and test on the actual filesystem.

If the output file will be consumed downstream, avoid letting consumers read an incomplete file. Write to a temporary execution-scoped file, then rename or publish a manifest after the step/job succeeds. If the job fails, retain the temporary file long enough for restarts or clean it up according to retention policies.

## Writer restarts and exactly-once

Writer state helps restore the output position, but does not automatically guarantee exactly-once across all systems. Exactly-once depends on coordinating transactions across business data, metadata, and output targets.

Several scenarios:

| Scenario | Risk | Mitigation |
| --- | --- | --- |
| File written successfully but checkpoint not committed | Restart may rewrite output | Transaction-aware writer, consistent file state, or staging/publish |
| Database commits together with checkpoint | Both changes can commit/roll back together | Share appropriate datasource/transaction manager |
| Database separate from repository | One commits while the other rolls back | Unique keys, upserts, ledgers, and reconciliation |
| Message received by broker before chunk rolls back | Message may be sent again | Stable event ID and idempotent consumer; consider outbox |
| Writer calls API before commit | API already processed despite chunk rollback | Idempotency key or move side effect to a later step |

Do not describe a writer as exactly-once merely because it implements `ItemStream`. `ItemStream` manages state save/restore; side-effect correctness also depends on resource and transaction semantics.

## Writer state in partitioned or parallel steps

When a step runs concurrently across partitions or multiple flows, each execution may need isolated writer state. Do not let multiple workers concurrently write and update a single state key or a single file without synchronization.

Principles:

- Use step-scoped writers or separate writer instances per partition when appropriate.
- Name state keys uniquely per partition if the component manages context keys itself.
- Each partition should write to its own output resource, then merge in a subsequent step if needed.
- If multiple partitions write to the same database table, use business keys and appropriate transaction isolation.
- Do not share mutable counters across writers on multiple threads unless thread-safe.
- When aggregating outputs, publish only after all required partitions complete.

If multiple partitions write to a single file, a dedicated synchronization design is required; `FlatFileItemWriter` must not be assumed to be a thread-safe writer shared by all workers. Splitting files by partition is usually easier to restart and reconcile.

## Common pitfalls

### Checkpointing only the reader while ignoring writer state

The reader resumes at the right position, but a file writer may overwrite from the beginning or lose track of output position. Use an `ItemStream`-capable writer or design idempotent output.

### Renaming the writer across deployments

Keys in `ExecutionContext` may change and the writer fails to find old state. Keep names stable while executions remain restartable.

### Setting `saveState(false)` while still expecting the writer to resume

The writer does not save internal state; restarts may not continue from the right position. Disable only when another tested mechanism is in place.

### Changing the output path on restart

The writer may create a new file while applying the old checkpoint or fail to find the file to resume. Use a stable path for the same logical execution.

### Forgetting to register delegate ItemStreams

A writer wrapped in a composite/wrapper may not receive lifecycle callbacks if delegate streams are not forwarded or registered. Verify `open/update/close` are actually invoked.

### Incrementing counters in write without restoring on rollback

In-memory state may advance ahead of durable checkpoints. Use transaction-aware sinks, committed/pending state, or idempotency.

### Assuming database writers always need dedicated state

`JdbcBatchItemWriter` typically relies on transactions and business keys. Adding unnecessary state complicates the design without solving duplicates across two resources.

### Assuming ItemStream guarantees exactly-once

ItemStream only manages the state lifecycle. Files, messages, and APIs can still incur non-transactional side effects; idempotency or outboxes are required.

### Deleting output files after a job fails

Writer state still references the lost output. Retain resources during the restart window or intentionally reset the job/output per business procedures.

## Testing restarts with writer state

The most important test simulates a run that commits partial output, fails, and restarts the same logical job. The test must verify both output and metadata.

### Testing FlatFileItemWriter

An integration test can perform:

1. Generate input spanning multiple chunks.
2. Use `FlatFileItemWriter` writing to a temporary file with `.saveState(true)` and a stable name.
3. Let the first few chunks commit.
4. Fail the step on a subsequent chunk with a controlled error.
5. Verify the file contains output from the committed chunks.
6. Restart with the same identifying `JobParameters` and the same output path.
7. Verify the writer restores state and writes the remaining output.
8. Read the final file, verifying headers, line count, order, and zero duplicate/missing records.

Tests should use a deterministic failure fixture rather than random timing. Use a processor test double that throws an exception on a specific business key during the first run, then allows success on restart.

### Testing writer state via ItemStream

For custom writers, verify:

- `open` reads saved state keys.
- `update` writes the exact committed position to context.
- State keys do not collide with other components.
- Rollbacks do not advance in-memory state beyond the checkpoint.
- Restart uses the same writer name/key and restores the right position.
- The target resource exists and matches the expected version.

Do not unit test only `open` and `update`; run integration tests to confirm the repository persists context and transaction rollbacks do not save checkpoints of failed chunks.

### Testing JDBC writers

For JDBC writers, tests must confirm transaction and idempotency behavior:

- Failed chunks roll back uncommitted inserts when sharing the transactional resource.
- Previously committed chunks remain intact.
- Restart creates no duplicates by business key.
- When metadata and business databases are separate, simulate one-sided commit failure to verify ledger/upsert replay handling.

### Testing delegates/composites

If using a composite writer, verify all stateful delegates are opened, updated, and closed. Run once and restart to ensure delegate writers neither restart from scratch nor append at wrong positions.

## Example verifying metadata and output

`JobExplorer` can query saved `JobExecution` and `StepExecution`; `JdbcTemplate` or file APIs can inspect actual output.

```java
JobExecution persisted = jobExplorer.getJobExecution(executionId);
assertNotNull(persisted);

StepExecution stepExecution = persisted.getStepExecutions()
        .stream()
        .filter(step -> step.getStepName().equals("exportOrdersStep"))
        .findFirst()
        .orElseThrow();

assertEquals(BatchStatus.COMPLETED, stepExecution.getStatus());
assertEquals(expectedWriteCount, stepExecution.getWriteCount());
```

Then read the file and compare the list of order IDs against expected output. `writeCount` is only a metadata counter; it does not replace checking actual file contents. If the writer writes to a database, query the target table and verify business keys/values.

In restart tests, keep identifying parameters identical between the initial run and the restart. For separate independent tests, generate a distinct `testRunId` to avoid `JobInstanceAlreadyCompleteException`. Clean up files and business data separately; clean up batch metadata with appropriate utilities without deleting executions needed by restart tests.

## Diagnostic steps when a writer fails to resume properly

If a restart creates duplicate files, misses lines, or writes at the wrong position, check in order:

1. Does the writer implement `ItemStream` or use a stateful built-in implementation?
2. Is `saveState` enabled?
3. Did the writer name stay identical across the run and restart?
4. Are delegate streams registered in the step?
5. Did the job restart use the same identifying parameters?
6. Is the output resource path identical to the first run?
7. Does the file/output resource still exist and match the expected version?
8. Are checkpoints saved in the same transaction commit or in an independent resource?
9. Did any non-transactional side effects occur before rollback?
10. Was in-memory writer state properly restored after rollback within the same process?

Do not directly edit serialized `ExecutionContext` in `BATCH_*` tables to force a writer to resume. Identify the root cause, use APIs/metadata to observe, and apply controlled restart or output-reset procedures.

## Writer state design principles

When designing a restartable writer, align on:

1. Does the writer genuinely need its own state, or are target transactions/idempotency sufficient?
2. Does the state describe how far output has committed?
3. Does the writer implement `ItemStream` and have its full lifecycle managed by the step?
4. Are the writer name and context keys stable across deployments?
5. Is `saveState` enabled when restarting is needed?
6. Are output paths/resources stable and retained during the restart window?
7. Are state updates consistent with output transactions?
8. Does rollback restore both in-memory state and output resources?
9. Can the writer be safely re-invoked after retry/restart?
10. Do composites/delegates/partitions register streams and isolate state properly?
11. Do integration tests verify final output has neither gaps nor duplicates?

Prefer built-in restartable writers when appropriate. For custom writers, design committed state, pending state, and transaction semantics before implementing. If the output does not support rollback, use staging, idempotency, or a separate publish workflow for safe recovery.

## Summary

Restarting with writer state enables writers to restore committed output positions via `ItemStream` and step `ExecutionContext`. `open` reads state, `write` writes chunks, `update` saves checkpoints, and `close` releases resources. `FlatFileItemWriter` supports state with a stable writer name and `saveState(true)`; keep output paths and files intact during the restart window. JDBC writers typically rely on transactions plus business keys/idempotency instead of a separate offset. With custom or composite writers, register all streams properly and ensure in-memory state does not advance ahead of output commits. Writer state alone does not guarantee exactly-once for files, messages, or APIs; transaction-aware sinks, idempotency, outboxes, or staging/publish are needed. Test by committing partial output, failing the step, restarting with the same identifying parameters, and verifying the final output has neither gaps nor duplicates.
