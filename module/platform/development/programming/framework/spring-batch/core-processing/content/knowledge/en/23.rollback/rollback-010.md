# Cleanup After Rollback in Spring Batch

In chunk-oriented processing, Spring Batch executes a group of items inside a transaction. If an error occurs and the transaction rolls back, changes belonging to resources managed by the transaction manager are undone. However, rollback does not automatically clear all in-memory state, close every resource opened by the application, or retract emails, HTTP requests, or messages already sent to external systems.

Therefore, after a rollback, distinguish three tasks: **undoing transactional data**, **releasing temporary resources**, and **handling effects outside the transaction**. Each task has its own mechanism. Proper cleanup lets a step retry or restart without leaving temporary files, stale buffers, leaked connections, or duplicate side effects.

## 1. What Does Rollback Actually Undo?

A chunk normally has its own transaction boundary. When a transaction rolls back, the database undoes operations that participated in that transaction, such as inserts/updates through JdbcTemplate or JPA repositories sharing the step's datasource and transaction manager.

Example:

```text
Chunk 1: BEGIN -> write A, B -> COMMIT
Chunk 2: BEGIN -> write C, D -> exception -> ROLLBACK

Result in the same database transaction:
  A, B: remain intact because chunk 1 committed
  C, D: chunk 2 changes are undone
```

Rollback only affects resources enlisted in the corresponding transaction. It does not automatically:

- Reset Java objects or fields inside singleton beans to pre-chunk values.
- Delete files created by the application or restore written file contents.
- Retract HTTP requests already processed by another service.
- Undo sent emails or SMS messages.
- Delete messages already published to a broker.
- Restore offsets or consumption state of a queue source not participating in the transaction.

Hence, before writing cleanup logic, identify which state was rolled back by the database and which state lies outside the transaction.

## 2. Distinguishing Rollback, Cleanup, and Compensation

Three concepts are often confused:

| Concept | Goal | Example |
| --- | --- | --- |
| Rollback | Undo changes belonging to an uncommitted transaction. | Database aborts write statements of a failing chunk. |
| Cleanup | Release resources or remove temporary data no longer needed. | Close streams, delete staging files after a job finishes. |
| Compensation | Execute a counterbalancing business action to address effects outside the transaction. | Issue a refund after a payment transaction cannot proceed. |

Cleanup is not a manual way to reverse everything rollback missed. If an external API already created a transaction, deleting a log file or resetting an in-memory field cannot undo that transaction. You need a meaningful business compensation action or an idempotent/outbox design to govern side effects.

## 3. Resource Lifecycle of ItemStream

Readers and writers that need to open, persist state, and close resources can implement ItemStream. This interface has three main callbacks:

- open(ExecutionContext): opens or restores resource state when the step starts.
- update(ExecutionContext): writes state needed for checkpointing.
- close(): releases resources when the step ends.

A component implementing ItemStreamReader or ItemStreamWriter can use those callbacks to manage files, cursors, buffers, or read/write positions.

```java
public class ResourceAwareReader implements ItemStreamReader<String> {

    private BufferedReader reader;

    @Override
    public void open(ExecutionContext context) throws ItemStreamException {
        try {
            reader = Files.newBufferedReader(Path.of("input.txt"));
        } catch (IOException ex) {
            throw new ItemStreamException("Cannot open input", ex);
        }
    }

    @Override
    public String read() throws Exception {
        return reader.readLine();
    }

    @Override
    public void update(ExecutionContext context) {
        // Save checkpoint if reader needs restart support.
    }

    @Override
    public void close() throws ItemStreamException {
        if (reader != null) {
            try {
                reader.close();
            } catch (IOException ex) {
                throw new ItemStreamException("Cannot close input", ex);
            } finally {
                reader = null;
            }
        }
    }
}
```

The example above only illustrates the resource lifecycle; a production reader must persist and restore read position in ExecutionContext if restarts are needed. Spring Batch invokes the ItemStream lifecycle throughout the step lifecycle, including when a step terminates after normal errors. However, no Java callback is guaranteed to run if the process is killed abruptly, loses power, or crashes the JVM. OS resources must be reclaimed safely when the process exits, and temporary files need a separate sweep for leftovers.

Do not open files or connections in the constructor of a singleton bean. Use open() to initialize per-execution resources and close() to release them.

## 4. close() Is Not a Callback After Every Rollback

ItemStream.close() belongs to the step lifecycle, not a callback invoked after every chunk rollback. A step can roll back one chunk, retry, and keep processing subsequent chunks before finishing. Closing the reader or writer inside close() after the first rollback would prevent the step from continuing normally.

Choose callbacks matching the scope needing cleanup:

| Scope | Appropriate Mechanism |
| --- | --- |
| Each successful chunk | ChunkListener.afterChunk() to record after chunk completion. |
| A chunk hitting an error/rollback | ChunkListener.afterChunkError() to observe the error and clean transient state tied to that chunk attempt. |
| Whole step ending | ItemStream.close() to close resources; StepExecutionListener.afterStep() for post-processing by step status. |
| Job ending | JobExecutionListener.afterJob() for job-scoped finalization. |
| Non-transactional effects needing offset | Dedicated compensation/outbox workflow with state and idempotency. |

Do not use close() to delete checkpoints or input files needed for restart. close() should only release open resources; decisions to keep or delete temporary data must depend on execution status and restart policy.

## 5. Using ChunkListener to Observe Rollback

ChunkListener provides chunk-level callbacks. afterChunkError() is invoked when a chunk fails and the chunk's transaction has rolled back under step processing rules. This callback is useful for logging, metrics, or clearing temporary buffers created specifically for that chunk attempt.

```java
public class ImportChunkListener implements ChunkListener {

    private static final Logger log =
        LoggerFactory.getLogger(ImportChunkListener.class);

    @Override
    public void beforeChunk(ChunkContext context) {
        log.debug("Starting chunk");
    }

    @Override
    public void afterChunk(ChunkContext context) {
        log.debug("Chunk committed");
    }

    @Override
    public void afterChunkError(ChunkContext context) {
        log.warn("Chunk rolled back; inspect transient state");
    }
}
```

Registering the listener with the step:

```java
return new StepBuilder("importStep", jobRepository)
    .<InputRecord, OutputRecord>chunk(100, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .listener(new ImportChunkListener())
    .build();
```

afterChunkError() fits cleaning transient chunk-scoped state if the application explicitly manages that state. Do not use this callback to delete already-committed business data, send emails, blindly call compensating APIs, or erase checkpoints. A chunk may be retried; error callbacks can fire on an intermediate attempt that is not the final failure of the step.

If a listener records metrics outside the transaction, those metrics may increment even when a later retry succeeds. Distinguish metrics counting rollback occurrences from final skipped items or step failures.

## 6. Cleaning Up In-Memory State After Rollback

Database rollback does not revert fields on Java objects. If a processor, writer, or listener holds a buffer inside a singleton bean, buffer contents can survive rollback and get reused on the next attempt.

Unsafe example:

```java
public class BufferedWriter implements ItemWriter<Record> {

    private final List<Record> pending = new ArrayList<>();

    @Override
    public void write(Chunk<? extends Record> chunk) {
        pending.addAll(chunk.getItems());
        repository.saveAll(pending);
        pending.clear();
    }
}
```

If saveAll() or downstream processing fails before pending.clear() runs, the buffer may still hold items from the failed chunk. When the writer is invoked again, old items may be written redundantly alongside new ones.

Prefer writing without chunk-spanning mutable state:

```java
public class StatelessWriter implements ItemWriter<Record> {

    private final RecordRepository repository;

    @Override
    public void write(Chunk<? extends Record> chunk) {
        repository.saveAll(chunk.getItems());
    }
}
```

If you genuinely need a dedicated buffer, allocate it per execution/chunk, clear it in a finally block or an explicitly designed rollback hook, and never share mutable state across workers. finally cleans memory for the current call, yet cannot reverse non-transactional side effects.

In multi-threaded or partitioned steps, singleton beans can be accessed concurrently by multiple threads. Chunk-level mutable state should live in appropriately scoped objects or be deliberately synchronized; avoid using a global list to accumulate items.

## 7. Cleaning Up Temporary and Output Files

File writes do not automatically join database transactions. If an application writes directly to the final file and the chunk rolls back, written data may remain in the file. For important output files, use a staging workflow:

1. Create a temporary file scoped to the job/step execution.
2. Write data to the staging file.
3. Save checkpoints or write positions if restarts are needed.
4. Publish the final file only after the step/job completes successfully.
5. If execution fails and will no longer be restarted, remove staging files per retention policy.

Example step-level finalization:

```java
public class StagingFileListener implements StepExecutionListener {

    private final Path stagingFile;

    public StagingFileListener(Path stagingFile) {
        this.stagingFile = stagingFile;
    }

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED) {
            publishStagingFile(stagingFile);
        }
        // When FAILED, can keep file for restart or delete per policy.
        return null;
    }
}
```

publishStagingFile() is an application operation, such as renaming the file within the same filesystem. Check atomic-move preconditions supported by the filesystem. If the file serves as input for restarts, do not delete it simply because the current step failed. For outputs preserved for diagnosis, move them to a quarantine directory instead of deleting.

With FlatFileItemWriter, prefer using the built-in writer with a stable name and appropriate saveState settings to leverage Spring Batch's transaction-aware writing and restart state. If implementing a custom file writer, you must explicitly design content rollback, write-position recovery, and duplicate-write prevention.

## 8. Cleaning Up Database Resources and Connections

When using JdbcCursorItemReader, JdbcPagingItemReader, or JPA readers/writers, let Spring Batch and Spring transaction infrastructure manage resources along the component lifecycle. Do not manually close connections obtained from a transaction-bound datasource while a chunk is still active.

Rules to remember:

- Use JdbcTemplate or repositories configured with the matching datasource/transaction manager.
- Do not store Connection, ResultSet, or EntityManager in static fields.
- If opening resources manually, close them in ItemStream.close() or try-with-resources once usage scope ends.
- Do not close resources managed by the transaction manager before the transaction finishes.
- If a writer uses a different datasource, know whether it has a separate transaction; step rollback does not roll back that datasource automatically.

You do not need to manually delete database rows that were rolled back. The transaction manager handles that for transactional resources. If data still appears, verify whether the write operations used the same transaction manager and datasource before writing manual cleanup deletes.

## 9. Message Queues and Acknowledgements After Rollback

For readers consuming messages from queues, database rollback does not necessarily return messages to the queue. That depends on the broker, session/acknowledgement mode, and whether the broker transaction is coordinated with the database transaction.

In some transactional queue setups, messages remain within the broker transaction and can be redelivered when the transaction rolls back. Spring Batch offers the readerIsTransactionalQueue() option in fault-tolerant step configuration when the reader pulls items from a transactional queue; this option adjusts how the framework buffers read items because the queue transaction itself manages message redelivery.

Illustrative configuration example:

```java
return new StepBuilder("consumeEventsStep", jobRepository)
    .<Event, EventResult>chunk(50, transactionManager)
    .reader(eventReader)
    .processor(eventProcessor)
    .writer(eventWriter)
    .faultTolerant()
    .readerIsTransactionalQueue()
    .build();
```

Use this option only when the reader genuinely reads from a transactional queue with appropriate rollback/redelivery semantics. It does not automatically create distributed transactions across arbitrary brokers and databases. If a message was acked/committed at the broker while the database transaction rolled back, the message may not be redelivered; if the message is redelivered, the consumer may receive the same event again. Use inbox/idempotency keys and reconciliation to ensure safe replay.

## 10. Non-Transactional Side Effects Cannot Be Cleaned Up by Rollback

A processor or writer may call APIs, send emails, or publish messages. If that operation succeeds and the chunk transaction then rolls back, the external system does not know the database rolled back and will not retract the effect.

Example:

```text
Processor calls payment API -> charge succeeds
          |
          v
Writer writes database -> error
          |
          v
Chunk rollback
          |
          v
Payment has still been executed
```

Do not call charge APIs directly inside the processor expecting afterChunkError() to undo them. If the payment service supports idempotency keys, use a stable business-derived key so retries do not create a second charge. If an already-created transaction must be cancelled, invoke a separate compensation API and persist compensation state.

For emails or messages, a safer pattern is recording the send intent in an outbox within the same transaction as business data. After the transaction commits, a separate dispatcher sends events and updates status. Consumers also need idempotency because messages may be sent again if the dispatcher crashes between publishing and recording completion.

## 11. Transactional Outbox to Avoid Manual Cleanup

An outbox separates recording business intent from executing side effects:

```text
Chunk transaction
    |
    +-- Write business data
    |
    +-- Write outbox event (PENDING)
    |
    +-- COMMIT
             |
             v
      Outbox dispatcher
             |
             +-- Send API/message
             |
             +-- Mark SENT
```

If the chunk rolls back, both business data and the outbox event roll back when they share the same database transaction. There is no need for a cleanup job deleting unsent events from a failed chunk because that event never committed.

If the dispatcher sends successfully yet stops before marking SENT, the event may be resent. Target consumers/APIs must recognize eventId to avoid repeating effects. An outbox provides at-least-once delivery semantics in many implementations, not system-wide exactly-once guarantees.

## 12. Using afterStep for Finalization

StepExecutionListener.afterStep() is called when the step completes. It is an appropriate place for post-processing based on final status, such as publishing staging files on success or logging summary metrics.

```java
public class StepFinalizationListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getStatus() == BatchStatus.COMPLETED) {
            // Publish completed artifact.
        } else if (stepExecution.getStatus() == BatchStatus.FAILED) {
            // Record failed status; keep artifact if restart is needed.
        }
        return null;
    }
}
```

Do not treat afterStep() as a guaranteed place to compensate every side effect. The callback executes when a step finishes normally under Spring Batch's lifecycle, yet cannot run if the JVM is killed abruptly. Furthermore, a FAILED step can still be restarted; deleting all files or checkpoints inside afterStep() can destroy resumability.

Distinguish cleaning up open resources from cleaning up durable artifacts. Close streams in ItemStream.close(); decide staging file deletion based on terminal state, restart policy, and retention rules.

## 13. Cleanup When a Step Is Restarted

After a rollback, the job may retry the chunk within the same execution or fail and be restarted as a new JobExecution. Cleanup must never delete state that the restart needs.

For readers implementing ItemStream, update(ExecutionContext) saves checkpoints at chunk boundaries. When a chunk rolls back, the latest durable checkpoint remains the recovery point. The reader reopens with the saved context to continue from the right position.

Principles:

- Preserve the last committed checkpoint.
- Do not delete input files, tokens, or source data needed by the reader to restart.
- Clear in-memory buffers of the failed pass, but do not erase already-committed durable data.
- Scope staging filenames to JobInstance/JobExecution to distinguish runs.
- If the source file changes, verify checksums or source identifiers before resuming from an old checkpoint.
- Ensure the writer is idempotent in case uncommitted items are reprocessed.

If an execution is marked terminal and will no longer be restarted, a separate cleanup task can delete temporary artifacts after a retention period. This approach is safer than deleting everything immediately when afterStep() sees FAILED.

## 14. Compensation for Business Actions Executed Externally

When a side effect has occurred and cannot be rolled back, determine whether it can be compensated at the business level. For example:

- A captured payment can be refunded.
- A reservation can be cancelled.
- A message already applied by a consumer may need a corrective event.
- A published file may need to be marked invalid and replaced by a new version.

Compensation does not necessarily restore the system to the exact prior state. It typically creates a new business action to balance the earlier effect. Therefore, persist the original transaction identifier, compensation status, attempt count, and final outcome.

A compensation workflow should:

1. Have a stable identifier linked to the original effect.
2. Be retryable without producing duplicate compensation.
3. Persist PENDING, COMPLETED, or FAILED status in durable storage.
4. Alert when compensation exceeds attempt limits or requires manual intervention.
5. Never run compensation solely because of a chunk rollback unless the external side effect is actually confirmed to have occurred.

You cannot write one generic finally block to undo every API. Each external service needs its own compensation contract and idempotency rules.

## 15. Testing Cleanup After Rollback

Use integration tests against a real test database to verify transaction rollback, alongside separate tests for non-transactional resources.

A basic scenario:

1. The first chunk writes data and commits successfully.
2. The next chunk writes several items and then the writer throws an exception.
3. The step ends in FAILED if no suitable retry/skip applies.
4. The database retains only data from the previously committed chunk.
5. Open resources close per lifecycle when the step ends.
6. Temporary buffers do not carry stale items into subsequent runs.

Example writer intentionally failing on the second call:

```java
public class FailingWriter implements ItemWriter<Order> {

    private final JdbcTemplate jdbcTemplate;
    private int calls;

    public FailingWriter(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Override
    public void write(Chunk<? extends Order> chunk) {
        calls++;
        for (Order order : chunk) {
            jdbcTemplate.update(
                "insert into imported_order(order_id) values (?)",
                order.getId()
            );
        }

        if (calls == 2) {
            throw new IllegalStateException("Simulated failure");
        }
    }
}
```

For the test to prove rollback, JdbcTemplate must use the same datasource and transaction manager as the step. Do not wrap the entire test method in an outer transaction that rolls back the step's committed chunks when the test ends. After the job fails, query the database to verify the first chunk's data remains and the second chunk's data was undone.

Additional tests should verify:

- afterChunkError() is invoked when the chunk rolls back.
- ItemStream.close() releases streams/connections after the step terminates per lifecycle.
- The reader restores its checkpoint after restart.
- Staging files are retained or deleted per policy.
- APIs/messages executed outside the transaction are not assumed to have rolled back.
- Idempotency prevents duplicate side effects when chunks or jobs rerun.

## 16. Common Mistakes During Post-Rollback Cleanup

**Deleting committed data to "clean the chunk":** rollback only undoes uncommitted transactions. Extra deletes can wipe out data from earlier successful chunks.

**Closing the reader inside afterChunkError():** the step may retry and keep using the reader. Closing resources there breaks the lifecycle; use close() when the step ends.

**Relying on finally to reverse API calls:** finally only executes code inside the current process and cannot roll back external services. Use idempotency or compensation.

**Deleting checkpoints when a step is FAILED:** the job may be restarted. Keep context and source data needed for the last committed checkpoint.

**Keeping mutable buffers in singletons:** items from a rolled-back chunk may linger in the buffer and get re-written. Avoid chunk-level state or clean it in the proper thread-safe scope.

**Assuming files roll back with the database:** files are separate resources. Use staging, transaction-aware writers, or separate publish/cleanup logic.

**Treating afterStep as guaranteed to run every time:** the JVM may be killed before the callback. Leftover cleanup tasks should be re-runnable and scan execution state.

**Assuming queue messages always redeliver:** acknowledgement and transactions depend on the broker. Verify transactional queue configuration, ack modes, and idempotency.

**Cleaning up immediately upon seeing FAILED:** FAILED can be a restartable state. Delete artifacts only once execution is confirmed no longer needing recovery.

## 17. Production Workflow for Designing Cleanup

First, inventory every resource the step uses: databases, files, streams, caches, queues, APIs, and in-memory buffers. For each resource, identify whether it participates in the chunk transaction, who owns its lifecycle, and how it recovers after rollback.

Next, let the transaction manager undo transactional database operations. Use ItemStream.open/update/close to manage resources and checkpoints. Use ChunkListener.afterChunkError() for observation or temporary chunk-scoped cleanup; use afterStep()/afterJob() for terminal-state finalization. Never delete data needed for restarts.

For files and object storage, use staging and publish artifacts only when the step/job succeeds. For queues, verify ack/redelivery semantics. For APIs, emails, and messages, use outboxes, idempotency, or compensation instead of assuming database rollback retracts effects.

Finally, test mid-chunk failures, rollbacks, retries, restarts, and process interruptions. Cleanup should be idempotent so it can rerun if the application stops mid-way. Monitor leftover staging artifacts, resource leaks, message redeliveries, and pending compensations so operations can detect and resolve incomplete cleanups.

Cleanup after rollback is about managing each kind of state properly after a chunk fails. Database transactions undo their own data automatically; ItemStream closes resources per lifecycle; listeners aid error observation; and external side effects require outboxes, idempotency, or compensation. Separating these boundaries clearly enables steps to retry and restart without losing checkpoints, leaking resources, or creating duplicate business effects.
