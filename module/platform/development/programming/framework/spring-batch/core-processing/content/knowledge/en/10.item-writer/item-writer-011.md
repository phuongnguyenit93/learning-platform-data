# Writer Restart State

In Spring Batch, a writer may need to save state so it can continue writing at the right position after a Step fails and is restarted. This state is usually stored in the Step ExecutionContext through the ItemStream contract. When the Job reruns the same JobInstance, Spring Batch reopens the writer with the saved ExecutionContext so the writer restores the state corresponding to the most recent checkpoint.

This mechanism is especially important for writers writing to files, cursors, or a data destination with a write position that needs to continue. For a writer writing to a database within a transaction, committed data is usually the source of truth and may not need a separate pointer. Regardless of the writer type used, the saved state must match the durably written data.

## 1. Why Does a Writer Need Restart State?

A chunk-oriented Step usually reads and writes data in groups. Suppose a Step processes 1,000 orders with a commit interval of 100:

~~~text
Chunk 1: write orders 1-100    -> commit
Chunk 2: write orders 101-200  -> commit
Chunk 3: write orders 201-300  -> commit
Chunk 4: write orders 301-400  -> error
~~~

If chunks 1, 2, and 3 committed, but chunk 4 failed, on restart the Job needs to continue from a point consistent with the committed state. For a reader, the checkpoint indicates the next read position. For a writer, restart state can indicate the confirmed output position or state.

Examples:

- A file writer needs to know where to continue writing and avoid rewriting already-committed data.
- A writer calling a target system may need to know the last confirmed record code or key.
- A database writer can rely on transactions and unique keys to ensure committed data is not duplicated.

Reader checkpoints and writer restart state are related but are not the same thing. The reader stores input source state; the writer stores output destination state if the implementation needs it. Both states must describe the same committed processing boundary.

## 2. ItemStream and the Writer Lifecycle

ItemWriter<T> only defines the chunk write operation. If a writer needs to open resources or save state for restart, it can implement ItemStreamWriter<T>, which combines ItemWriter<T> and ItemStream.

The ItemStream contract consists of three callbacks:

~~~java
public interface ItemStream {
    void open(ExecutionContext executionContext);
    void update(ExecutionContext executionContext);
    void close();
}
~~~

In the actual API, the methods may declare ItemStreamException. The meaning of each callback:

- **open(ExecutionContext):** called when the Step starts. The writer opens resources and reads saved state if this is a restart.
- **update(ExecutionContext):** called when the framework prepares to save state at a chunk boundary. The writer writes necessary information into the ExecutionContext.
- **close():** called when the Step ends to close files, cursors, or release resources.

General lifecycle:

~~~text
Step starts
    |
    v
writer.open(saved ExecutionContext)
    |
    v
Read and process chunk
    |
    v
writer.write(chunk)
    |
    v
writer.update(ExecutionContext)
    |
    v
JobRepository saves checkpoint
    |
    v
Commit chunk transaction
    |
    v
Repeat with next chunk
    |
    v
writer.close()
~~~

The framework manages when to call the callbacks. The writer should not call update() itself or write ExecutionContext into JobRepository on its own.

## 3. Where Does ExecutionContext Store Restart State?

Spring Batch has two ExecutionContext scopes:

- **Step ExecutionContext** belongs to a StepExecution. This is the usual place for a reader or writer to store state specific to the Step.
- **Job ExecutionContext** belongs to a JobExecution. It is suitable for sharing small metadata between Steps within the same Job run.

A writer's restart state usually belongs in the Step ExecutionContext because the write position is state specific to the writer in that Step.

With a JDBC JobRepository, this data is stored in the metadata repository, usually in the BATCH_STEP_EXECUTION_CONTEXT table. When the Step is restarted, Spring Batch reloads the saved ExecutionContext and passes it to the writer via open().

ExecutionContext should contain small information needed for recovery, such as:

- Byte offset or committed write position.
- Sequence number of the last confirmed record.
- Paging key or last processed ID.
- File name or version code of the output.
- A marker needed to resume the write operation.

Do not store whole chunks, large business lists, passwords, API tokens, or private keys in ExecutionContext. The metadata repository is not a business data store or a secret manager.

## 4. Writer Name and saveState

Many built-in Spring Batch writers have an option to save state. For example, FlatFileItemWriter can store the information needed to continue writing a file after restart.

~~~java
@Bean
@StepScope
FlatFileItemWriter<Order> orderFileWriter(
        @Value("#{jobParameters['outputFile']}") String outputFile) {

    return new FlatFileItemWriterBuilder<Order>()
            .name("orderFileWriter")
            .resource(new FileSystemResource(outputFile))
            .lineAggregator(order ->
                    order.getId() + "," + order.getAmount())
            .saveState(true)
            .build();
}
~~~

Important details:

- **name("orderFileWriter")** sets a stable name for the writer. This name is used to build state keys in ExecutionContext.
- **saveState(true)** instructs the writer to save state for restart.
- **resource(...)** identifies the target file. On restart, the writer must open the right file or the right output corresponding to the execution.
- **lineAggregator(...)** converts each item into a line of text.

If the writer saves state, keep the writer name stable across deployments. Changing the name arbitrarily can cause the writer not to find the saved state keys and fail to recover the right position.

If saveState is disabled or you use a writer that does not support ItemStream, Spring Batch cannot restore that writer's internal state. In that case, the application must accept rewriting from the start or provide a safe recovery mechanism of its own.

## 5. FlatFileItemWriter Restores the Write Position

FlatFileItemWriter is a typical example of a writer with restart state. It manages the file resource and stores the information needed to continue writing by checkpoint.

Suppose the output file has three committed chunks:

~~~text
orders-export.csv
  order 1
  order 2
  ...
  order 300
~~~

The next chunk hits an error before committing. On restart, the writer needs to restore the write position matching the saved state, avoiding appending data from a wrong position or recreating lines that already committed.

Do not think that simply turning on append mode gives you safe restart. Append only dictates how to open the file; restart also needs appropriate state, a stable writer name, and an existing-file handling policy aligned with the Job lifecycle.

When configuring a file writer, decide clearly:

- Whether a new file is created for each JobInstance or an existing file is reused.
- On restart, whether the writer continues the old file or recreates the entire output.
- Whether the file can be overwritten by another JobInstance.
- At what point the file is published to other systems.
- How incomplete files are handled after a Job fails.

If multiple JobInstances write to a fixed path, they can overwrite or mix data. Create a path tied to a business key or JobInstance, and only publish the file when the Step completes according to the process.

## 6. Writer Checkpoint Must Match Committed Data

The most important aspect of restart state is consistency between metadata state and output data.

For example, suppose a writer stores lastWrittenId = 300 in ExecutionContext. This value is only meaningful if data up to ID 300 has actually been durably written under the same commit boundary.

If metadata says data was written up to ID 300 but the target data only has up to ID 250, restart may skip 251-300. Conversely, if the target data was written up to 350 but the checkpoint is only 300, restart may write 301-350 twice.

For a database writer, the simple and reliable approach is usually to let the written data and the checkpoint metadata participate in the same transaction when possible. If they use two separate databases or two separate transaction managers, do not assume by default that the two places will commit or roll back atomically.

For files or external APIs, a database transaction does not automatically undo already-written data. You need separate mechanisms such as transactional buffering, idempotency keys, staging, outbox, or compensation.

## 7. Does a Database Writer Always Need Its Own Restart State?

Not every writer needs a separate restart pointer.

For example, JdbcBatchItemWriter writes a chunk's items into the same database and participates in the Step's transaction. If the transaction rolls back, the write statements in the chunk are rolled back. If the transaction commits, the business data already exists durably.

~~~java
@Bean
JdbcBatchItemWriter<Order> orderDatabaseWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<Order>()
            .dataSource(dataSource)
            .sql("""
                insert into orders (id, amount)
                values (:id, :amount)
                """)
            .beanMapped()
            .build();
}
~~~

In this model, the writer usually does not need to store a `lastWrittenId` variable on its own to decide where to write next. The reader checkpoint and the database transaction manage most of the processing state.

However, a database writer still needs to account for:

- Whether JobRepository and business data share a transaction resource.
- Whether retry or restart can execute the same item again.
- Whether a primary key or unique constraint prevents duplicate records.
- Whether upsert or business-state checks are needed before writing.
- Whether side effects outside the database are triggered in the same operation.

If the metadata repository and the business database are separate, out-of-sync state can occur. Designing an idempotent writer helps handle these cases more safely.

## 8. Writing a Custom Writer with Restart State

A custom writer needs to implement ItemStreamWriter when there is state to restore. In principle, the writer does three things:

1. open() reads the old checkpoint and restores the resource or position.
2. write() writes the chunk to the destination.
3. update() puts the state corresponding to the written output into ExecutionContext.

Structural pattern:

~~~java
public class RestartableOrderWriter
        implements ItemStreamWriter<Order> {

    private static final String LAST_ID_KEY =
            "restartableOrderWriter.lastId";

    private final OrderSink sink;
    private long lastCommittedId;

    public RestartableOrderWriter(OrderSink sink) {
        this.sink = sink;
    }

    @Override
    public void open(ExecutionContext context) {
        lastCommittedId = context.containsKey(LAST_ID_KEY)
                ? context.getLong(LAST_ID_KEY)
                : 0L;

        sink.openAfter(lastCommittedId);
    }

    @Override
    public void write(Chunk<? extends Order> chunk) throws Exception {
        sink.write(chunk);
    }

    @Override
    public void update(ExecutionContext context) {
        long position = sink.positionForCheckpoint();
        context.putLong(LAST_ID_KEY, position);
    }

    @Override
    public void close() {
        sink.close();
    }
}
~~~

OrderSink here is an illustrative abstraction for a write destination capable of restoring its position. An actual implementation must clearly define which position positionForCheckpoint() represents and how to ensure that position matches the committed data.

This is not a writer that can be used directly without implementing OrderSink and transaction semantics. For a database target in the same transaction, positionForCheckpoint() must reflect the write state committed together with the metadata. For a file or external service, additional mechanisms such as buffering, truncate/restore, idempotency, or reconciliation are needed to handle partially written data.

Do not simply increment an in-memory variable, write that variable into ExecutionContext, and treat it as a safe checkpoint. If the chunk rolls back, the in-memory state may already have advanced even though the target data was not committed. A custom writer must handle rollback within the same execution as well, not just restart after a process restarts.

## 9. Writer State and Rollback Within the Same Execution

Restart after a JobExecution fails is one case. Rollback and retry right inside the same execution is another case.

Example:

~~~text
write(chunk 1) -> succeeds
update state   -> prepares checkpoint
commit         -> succeeds

write(chunk 2) -> partially written
exception      -> transaction rolls back
retry chunk 2  -> framework may call write again
~~~

If the writer already changed internal state during the failed write, the retry may use the wrong state. Therefore, in-memory state must be restored or recomputed consistently with the transaction.

Some principles:

- Only checkpoint state corresponding to confirmed output.
- Do not treat mutable state inside the writer as the sole source of truth.
- For databases, prefer letting a transaction manage both business writes and metadata when possible.
- For files, use a writer with transactional buffering and restart support already provided by Spring Batch if suitable.
- For external systems, design idempotent operations or operations that can be reconciled on retry.
- Test rollback within the same execution, not just restart after a process failure.

ItemStream.update() is called within the chunk-management flow; it does not mean data has already been committed successfully at the moment the callback is invoked. The chunk's transaction can still roll back. Therefore, updating state in ExecutionContext must participate in the repository's transaction mechanism and be designed alongside the data destination.

## 10. How Do JobRepository and Transaction Manager Affect This?

JobRepository stores ExecutionContext and other metadata. The Step's transaction manager coordinates the chunk transaction. How these two components are configured affects the consistency between checkpoints and business data.

The favorable case is when business data and the metadata repository use the same suitable transaction resource. In that case, business data and checkpoints can commit or roll back together.

If they use two different databases:

~~~text
Step transaction
    |
    +--> Business database
    |
    +--> JobRepository database
~~~

The two places do not automatically become a single atomic transaction just because they are used together in one Step. One side can commit while the other has not committed or encounters an error.

When using multiple transaction managers or resources, evaluate:

- Whether a distributed transaction coordinator is needed.
- Whether eventual consistency is acceptable.
- Whether the writer is idempotent.
- Whether business data can be reconciled against checkpoints.
- Whether output can be recovered from staging or an immutable source.

Do not update the BATCH_STEP_EXECUTION_CONTEXT table directly to fix a writer position. Let Spring Batch and JobRepository manage state through the corresponding lifecycle and APIs.

## 11. Restarting the Same JobInstance

Spring Batch restarts a JobInstance by creating a new JobExecution when the previous execution failed or was stopped and the status allows restart. Steps that already completed are usually skipped; Steps that need to rerun restore reader and writer state if the components support ItemStream.

Example:

~~~text
JobInstance: exportOrders, businessDate=2026-11-15

JobExecution 101:
  exportOrdersStep
    chunk 1 -> commit
    chunk 2 -> commit
    chunk 3 -> writer error
  status = FAILED

JobExecution 108 (restart):
  exportOrdersStep
    reader.open(saved reader state)
    writer.open(saved writer state)
    continues from committed checkpoint
~~~

To restart properly:

- Keep the identifying JobParameters of the JobInstance to continue unchanged.
- Keep the Step name and stateful reader/writer names unchanged.
- Ensure the file or data destination to continue still exists.
- Do not change the source or destination in a way that makes the old checkpoint meaningless.
- Ensure the writer does not create duplicates when a chunk is retried or the Step is restarted.

If you change identifying JobParameters, Spring Batch creates a new JobInstance. The new Job does not automatically use the old instance's writer state.

## 12. File Output and File Management Policy on Restart

For file writers, the file position is an important part of restart state. You need to decide whether output is a separate file per JobInstance or a shared file.

An easy-to-manage model:

~~~text
/data/batch/output/
    export-2026-11-15-job-101.csv
    export-2026-11-16-job-105.csv
~~~

Each JobInstance writes a separate file. After the Step completes, a separate publish step can rename or move the file into a directory monitored by the consuming system.

Things to consider:

- Do not delete an incomplete output file if the Job still needs to restart from it.
- Do not let another JobInstance overwrite a file currently being restarted.
- Define when a file is considered complete.
- If recreating the file from scratch, ensure the Step and entire process can rerun safely.
- Clean up old files after the Job no longer needs restart and the retention period has passed.

Do not rely on a fixed file name such as orders.csv if multiple runs can be concurrent or output history needs to be kept. Naming files by business key or JobInstance helps reduce conflicts.

## 13. Writers Calling APIs or Message Brokers

When a writer calls an API or sends a message, the destination usually does not participate in Spring Batch's database transaction. If the API received the request but the application loses connection before receiving the response, the writer does not know for sure whether the operation succeeded.

If the chunk is retried, the same request may be sent again. Restart state alone does not resolve this ambiguity.

Commonly used mechanisms:

- **Idempotency key:** send a stable key per business item or chunk so the receiving system recognizes repeated requests.
- **Transactional outbox:** write the message to be published into the database in the same business transaction, then a separate process sends the message.
- **Inbox/deduplication:** the receiving side stores processed message IDs to drop redeliveries.
- **Reconciliation:** reconcile output state after a timeout or undetermined error.
- **Compensation:** perform a compensating action if an effect that already occurred cannot be rolled back.

If the writer sends one message per item, the idempotency key should be tied to the item's business identifier. If sending one message for the whole chunk, the key should stably identify the chunk or batch.

## 14. Multiple Writers or Composite Writers

CompositeItemWriter can coordinate multiple delegate writers receiving the same chunk. If a delegate has restart state, you need to ensure the delegate's ItemStream lifecycle is registered properly so open(), update(), and close() are called.

Example:

~~~java
@Bean
CompositeItemWriter<Order> orderCompositeWriter(
        JdbcBatchItemWriter<Order> databaseWriter,
        FlatFileItemWriter<Order> fileWriter) {

    return new CompositeItemWriterBuilder<Order>()
            .delegates(databaseWriter, fileWriter)
            .build();
}
~~~

In an actual configuration, check the Spring Batch version and the stream registration mechanism of composites/delegates. Do not assume every delegate automatically has its lifecycle managed across all nesting styles.

If the database writer and the file writer do not participate in the same atomic transaction, one destination may have written successfully while the other failed. On restart, the two delegates can be in two different states. You need to design idempotency, staging, or a separate Step to produce the secondary output from committed data.

## 15. Testing Writer Restart State

Testing a writer needs to cover the state lifecycle, rollback, and restart. Verifying only that write() writes the right data for one chunk is not enough for a stateful writer.

Scenarios to verify:

| Scenario | What to verify |
|---|---|
| First run | open() receives an empty context and the writer starts at the right position |
| After a successful chunk | update() saves state matching the committed output |
| Restart | open() restores the saved state |
| Writer fails mid-chunk | transaction rolls back according to configuration |
| Retry within same execution | writer does not use in-memory state that advanced wrongly |
| Restart after process failure | No duplicate writes or skipped data |
| Source/target file modified | Job detects or handles per policy |
| Delegate writer | Each stream's lifecycle is called properly |
| Secrets/logs | Do not write credentials to ExecutionContext or logs |

With FlatFileItemWriter, you can use an integration test that runs the Job the first time, simulates an error in a later chunk, then restarts the same JobInstance and verifies the final file has the exact lines, with no duplicates or omissions.

With a database writer, check both data and checkpoint metadata after commit/rollback. If JobRepository and the business database differ, also test the scenario where one commits and the other hits an error to determine recoverability.

## 16. Common Mistakes When Designing Restart State

**Not setting a stable writer name.** The writer may not find the right state key in ExecutionContext after restart. Set a stable name that is unique within the Step's scope.

**Disabling saveState when restart is needed.** A built-in writer that does not save state cannot restore the write position on its own. Enable saveState or implement your own mechanism.

**Thinking append means safe restart.** Append only decides how to open the file; you need state and a policy for handling partially written portions.

**Saving state before target data is durable.** Metadata can get ahead of the data and cause restart to skip items. Synchronize checkpoints with transactions or use idempotency/reconciliation.

**Only testing restart after a process dies.** Rollback and retry within the same execution can also make in-memory state diverge from the committed checkpoint.

**Using an in-memory counter as the source of truth.** A counter can advance even when a chunk rolls back. State must be derived from confirmed output or restored on rollback.

**Assuming every write destination is transactional.** Files, APIs, and brokers do not automatically roll back with the database. Design separate recovery.

**Changing files or sources between two runs.** Old checkpoints may point to a different position. Use a stable source/target version or detect changes before restarting.

## 17. Process for Designing a Writer with Restart State

When implementing a writer, answer these questions:

1. Does the write destination store durable state and support transactions?
2. Does the writer need to store its own position or state?
3. What state is sufficient to continue without storing large business data?
4. Is the state stored in the Step ExecutionContext?
5. Does the writer implement ItemStreamWriter and manage open/update/close properly?
6. Is the writer name stable across deployments?
7. Can chunk rollback or retry within the same execution make in-memory state wrong?
8. Do JobRepository and the business sink share the same transaction resource?
9. If writing files/APIs/messages, what is the idempotency or recovery mechanism?
10. Do tests cover restart, rollback, retry, and output data?

With built-in writers such as FlatFileItemWriter, use the saveState and lifecycle mechanisms provided by the framework. With database writers, prefer transactions and data constraints to ensure write operations are safe on rerun. With custom writers or destinations outside a transaction, design state around committed checkpoints and have a mechanism to handle effects that occurred but were not confirmed.

A writer's restart state is reliable only when it accurately describes the durable output state. ItemStream provides the lifecycle to save and restore state; JobRepository stores checkpoints; transactions and idempotency protect data during rollback, retry, or restart. Combining these mechanisms properly helps the writer continue work without duplicating or missing items.

