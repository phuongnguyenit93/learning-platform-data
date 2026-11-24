# Output created once or multiple times

In Spring Batch, a job can read items, process them, and then write results to a database, file, message broker, or external API. A critical operational question in batch processing is: **is a business result created exactly once, or can it be created multiple times?**

You cannot answer this question merely by looking at how many times `ItemWriter.write()` is called. A chunk may roll back, a step may retry, a job may restart after a process crash, or a writer may successfully send output before an error occurs prior to saving the checkpoint. In such cases, the same item can pass through part of the pipeline multiple times.

Spring Batch provides checkpoints, transactions, and retries to control processing progress. These mechanisms help a job recover from failures, but they do not automatically guarantee that every external side effect occurs only once. To achieve a single business effect per output, you must design transaction boundaries, output identity, idempotency, and recovery mechanisms tailored to each write destination.

## "Once" can carry multiple meanings

Before designing, you need to distinguish technical execution counts from the final business outcome.

| Concept | Meaning |
| --- | --- |
| One call | A method such as `write()` or an API publish call is invoked once |
| One attempt | One execution of an operation; a retry creates a subsequent attempt |
| One commit | One transaction is committed successfully |
| One physical output | One row, file, message, or request is actually created/sent |
| One business effect | The final business state reflects only one logical processing |

A writer may be called multiple times while the database still ends up with a single row if unique keys and idempotent operations are used. Conversely, a writer may be called once in application logs, yet a message may already have been received by the broker before the client timed out, leaving the outcome status unknown.

Therefore, the practical goal is usually **one business effect**, even when the system must perform multiple technical attempts. This is an essential approach for batch jobs with retry and restart.

## Why can output be created multiple times?

A chunk-oriented step typically reads and processes a group of items, then invokes the writer within a transaction. When an error occurs, Spring Batch can roll back and re-execute part of the work according to configuration. Some side effects that already occurred before the error may not be rollbackable.

Common causes include:

- The writer already wrote/sent output, but the chunk transaction rolled back.
- The writer sent asynchronously and returned before knowing the result; the failure surfaced later.
- The broker received the message, but the acknowledgement was lost or timed out.
- The process died after the destination recorded the output, but before the checkpoint was committed.
- A job restart re-read items that had not yet been checkpointed.
- An operator launched a new `JobInstance` with the same input dataset and regenerated the output.
- A processor, listener, or service performed a side effect and was invoked again on retry.
- Two job executions processed the same input simultaneously because no claim/lock mechanism existed.

Example of a step processing 100 orders:

```text
Chunk 1: read 100 items
    |
    v
Processor processes items
    |
    v
Writer sends 100 messages
    |
    +--> broker receives messages
    |
    v
Error occurs before chunk progress is confirmed
    |
    v
Rollback / retry / restart
    |
    v
Same items are resent
```

If the broker does not participate in the same rollbackable transaction, the messages from the first attempt still exist. Resending creates duplicates. This is not necessarily a Spring Batch bug; it is a consequence of side effects sitting outside the managed transaction.

## Chunk transaction and checkpoint

In chunk processing, Spring Batch reads items, calls the processor if present, and passes valid outputs to the writer. After the chunk is processed, the framework updates progress and completes the transaction according to the step configuration.

Conceptual model:

```text
Chunk transaction
    |
    +--> read items
    +--> process items
    +--> writer.write(chunk)
    +--> update checkpoint / execution state
    |
    v
Commit
```

Exact callback details and metadata update timing depend on step type, transaction manager, and repository configuration. What matters is that business output and checkpoint are atomic only if they genuinely participate in the same transaction that can commit/roll back together.

### When business output and checkpoint share a transaction

If the writer writes to a database and `JobRepository` uses the same transactional resource with a properly configured transaction manager, the business write and metadata update can commit in the same transaction. When the transaction rolls back, both parts roll back; when it commits, both are confirmed together.

This is the favorable scenario for avoiding a failure window between business output and checkpoint. However, you must verify the actual configuration: using the same `DataSource` object or the same database is not enough on its own to prove two operations share a transaction. The transaction manager, connection binding, and repository configuration must cooperate properly.

### When business output and checkpoint use different resources

If the writer writes to database A while `JobRepository` writes to database B, or if the writer emits files/messages/HTTP calls, a single local transaction typically cannot atomically commit both resources.

Example:

```text
Business database                 JobRepository
       |                                |
       +--> write output                +--> write checkpoint
                \                      /
                 \                    /
                  Two independent resources
```

One resource may commit while the other fails. If output commits but the checkpoint is not saved, a restart can emit the output again. If the checkpoint is confirmed while output failed and the writer did not report the error properly, items may be skipped.

Do not infer atomicity merely from both operations being invoked in the same `write()` method or the same step.

## Restart can create output again

`JobRepository` stores `JobExecution`, `StepExecution`, and `ExecutionContext` so Spring Batch knows how far a job has progressed. When a job fails, restarting the same `JobInstance` can resume from the committed checkpoint.

However, a checkpoint only represents progress saved by the framework. If output was already accepted by an external destination before the checkpoint was confirmed, items may be reprocessed after restart.

Example:

1. Reader fetches item `O-100`.
2. Writer sends message `OrderProcessed(O-100)`.
3. Broker receives the message.
4. The process stops before the step persists the corresponding checkpoint.
5. The job is restarted and reads `O-100` again.
6. The writer sends the same message again.

The broker may contain two messages for the same business event. The consumer must deduplicate, or the producer must use an appropriate transactional mechanism.

### Restarting the same JobInstance vs launching a new JobInstance

These two situations are different:

- **Restart:** resumes a failed `JobInstance`, with the same identifying `JobParameters` and corresponding state.
- **New launch:** creates a new `JobInstance`, usually because identifying parameters changed or a new run identifier was supplied.

A job that completed successfully and is then launched again as a new instance can process all input from the beginning. Spring Batch cannot automatically know that this is an unwanted re-run if the batch's business identity is not modeled.

If an input set must only be processed once from a business perspective, include a `batchId`, source file ID, event ID, or business key to identify the processing run. Do not rely solely on `JobExecutionId`, because every execution gets a new ID.

## Retry within the same step

When a step is configured with fault tolerance, an exception can cause the processor or writer to be called again according to the retry policy. Retries can happen before the step fails completely.

Example:

```java
return new StepBuilder("publishStep", jobRepository)
        .<OrderEvent, OrderEvent>chunk(100, transactionManager)
        .reader(eventReader)
        .processor(eventProcessor)
        .writer(messageWriter)
        .faultTolerant()
        .retry(TransientBrokerException.class)
        .retryLimit(3)
        .build();
```

If the writer already sent part of the chunk and then threw an exception, Spring Batch can retry according to the step's retry semantics. Messages sent before the error may still remain on the broker. If the writer sent several records successfully before one record failed, retrying the whole operation can replay the previously succeeded records.

With a database writer participating in the chunk transaction, row writes in the rolled-back transaction can be re-executed without leaving duplicate rows. With files, message brokers, or HTTP APIs, side effects usually do not automatically roll back with the database transaction.

### The processor can also run again

The processor should focus on transformation and validation. If a processor sends emails, initiates payments, calls state-mutating APIs, or writes to a database outside the transaction, retries can repeat those side effects.

Do not place non-idempotent side effects in a processor just because `process()` looks like it is called once per item. In a fault-tolerant step, an item can be processed multiple times. Move side effects to the writer or a workflow with explicit idempotency/outbox handling.

### Listeners can also produce repeated side effects

Listeners such as `ItemWriteListener`, `ChunkListener`, and `StepExecutionListener` are useful for logging, metrics, and auditing. However, callbacks may be invoked across different retry, rollback, or restart paths. Do not use listeners to send critical notifications without idempotency or a durable event record.

Logging the same event multiple times is usually acceptable; creating an invoice, sending an email, or updating an external system multiple times may be unacceptable.

## Exactly-once, at-least-once, and at-most-once

When discussing whether output occurs once or multiple times, delivery semantics must be defined.

| Semantics | Characteristics | Consequences |
| --- | --- | --- |
| At-most-once | An output is attempted at most once per policy | Output may be lost if failure occurs before destination receipt |
| At-least-once | System retries until appropriate confirmation is received | Can produce duplicates; requires idempotency |
| Exactly-once effect | Despite multiple attempts, business effect is applied only once | Requires identity/deduplication or coordinated transactions |
| Exactly-once delivery | A message is delivered exactly once to the consumer | Very hard to guarantee end-to-end across crashes/retries; must clearly define broker scope |

In distributed systems, "exactly once" usually has meaning only within a specific transaction or broker scope. A Kafka transactional producer can provide exactly-once semantics for Kafka operations within its configured scope, but it does not automatically turn a database update and an HTTP call into a single transaction.

A practical target is at-least-once delivery combined with an idempotent consumer/writer, thereby achieving an exactly-once business effect within the controlled data boundary.

## Idempotency: multiple attempts, one result

An idempotent operation can be executed multiple times with the same input without changing the final state after the first execution.

Example status update:

```sql
UPDATE orders
SET status = 'PUBLISHED'
WHERE order_id = :orderId
  AND status <> 'PUBLISHED';
```

Re-running the statement does not create a second row. However, check business semantics: if each update fires a trigger/audit record or emits another event, secondary side effects may still repeat.

### Idempotency key

Each business output should have a stable identity, for example:

- `eventId` for a message.
- `paymentRequestId` for a payment command.
- `invoiceId` for an invoice.
- `sourceRecordId + operationType` for a batch result.
- `batchId + businessKey` for a batch's output.

The idempotency key must be generated beforehand or deterministically derived from durable data, then preserved across retries/restarts. Do not generate a fresh UUID every time the writer is called for the same logical output.

### Unique constraint to prevent duplicate inserts

A database unique constraint is a strong barrier preventing two executions from creating the same output:

```sql
CREATE TABLE processed_order (
    order_id VARCHAR(50) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL,
    result_code VARCHAR(30) NOT NULL
);
```

The writer can use an insert with conflict handling tailored to the database dialect. PostgreSQL example:

```sql
INSERT INTO processed_order(order_id, processed_at, result_code)
VALUES (:orderId, :processedAt, :resultCode)
ON CONFLICT (order_id) DO NOTHING;
```

`ON CONFLICT` is PostgreSQL-specific syntax. For Oracle, SQL Server, MySQL, or other databases, use the corresponding syntax/strategy. The unique constraint is the ultimate safeguard against race conditions; merely checking with `SELECT` before `INSERT` is not safe when two jobs run concurrently.

If a duplicate must be distinguished from an existing output with different content, read and compare a checksum/version or use a conditional upsert. Do not silently ignore all duplicates if they might indicate conflicting source data.

## Database writes: transactions and unique business keys

A database is the easiest place to achieve single output when the business writer and checkpoint participate in a suitable shared transaction. If that transaction rolls back, uncommitted rows do not exist; on retry, the insert executes again.

However, you must address these questions:

- Do the writer and `JobRepository` use the same transactional resource or different ones?
- Can multiple job instances process the same business key?
- Does the writer write to a different database than the repository?
- Are there triggers or stored procedures creating side effects outside the transaction?
- Does the unique key represent exactly one logical output, or only one input record?

Example `JdbcBatchItemWriter`:

```java
@Bean
JdbcBatchItemWriter<ProcessedOrder> processedOrderWriter(DataSource dataSource) {
    return new JdbcBatchItemWriterBuilder<ProcessedOrder>()
            .dataSource(dataSource)
            .sql("""
                    INSERT INTO processed_order(
                        order_id, processed_at, result_code)
                    VALUES (:orderId, :processedAt, :resultCode)
                    """)
            .beanMapped()
            .assertUpdates(false)
            .build();
}
```

This snippet illustrates mapping; if idempotency is needed, the SQL must have a unique constraint and appropriate duplicate policy. `assertUpdates(false)` only changes how the writer reacts to updated row counts; it does not automatically make an insert idempotent. Use dialect-appropriate SQL upsert/conflict-ignore clauses and verify results against business requirements.

### An upsert can overwrite newer results

A naive upsert can let an old retry overwrite data produced by a newer processing run. If the output carries a version or timestamp, update only when the incoming version qualifies. Idempotency must preserve semantics, not merely avoid duplicate key exceptions.

## Sending messages: acknowledgement does not mean exactly-once

When sending messages to Kafka, JMS, or RabbitMQ, the producer typically receives an acknowledgement/confirm according to broker semantics. If the acknowledgement fails to arrive due to a network timeout, the producer cannot be sure whether the broker received the message.

```text
Producer sends event
       |
       v
Broker receives and stores event
       |
       +--> acknowledgement lost on network
       |
       v
Producer timeout
       |
       v
Batch retries sending event
```

The broker may end up holding two copies. Therefore:

- Use a stable event ID across all attempts.
- Configure producer retry/idempotence according to broker capabilities.
- Wait for acknowledgement per policy before the writer returns.
- Have the consumer deduplicate event IDs in the same transaction as its business update.
- Do not treat producer acknowledgement as proof that the consumer has processed the event.

Kafka producer idempotence reduces duplicates caused by internal retries within a single producer session per Kafka semantics. It does not automatically prevent duplicates caused by a Spring Batch restart creating a new publish attempt for the same event.

## Transactional Outbox

Transactional outbox is a common pattern when a database transaction both updates business data and needs to emit a message. Instead of publishing directly inside that transaction, the application writes an outbox row in the same transaction as the business update.

```text
Business chunk transaction
    |
    +--> UPDATE orders
    +--> INSERT outbox_event (event_id, payload, PENDING)
    +--> COMMIT
             |
             v
       Outbox publisher step
             |
             +--> read/claim pending event
             +--> publish to broker
             +--> wait for acknowledgement
             +--> mark published
```

If the business transaction rolls back, the outbox row rolls back too. If it commits, the intent to emit the event is durably persisted. Temporary broker unavailability does not lose the event; the publisher can retry in a later execution.

### An outbox can still publish multiple times

Suppose the broker receives the message, but the publisher dies before updating `published_at`. The next run sees the row still pending and resends it. This is intentional at-least-once publishing.

So that the business effect occurs only once:

1. Keep `event_id` stable in the outbox row.
2. Have the consumer store processed event IDs in an inbox/processed-message table.
3. Have the consumer write the inbox record and business update in the same transaction.
4. Upon receiving a duplicate event, have the consumer skip the already-completed business effect and acknowledge per policy.

Outbox solves consistency between the business update and recording the intent to emit an event; inbox/idempotency solves duplicates on the consumer side.

## Inbox and consumer-side deduplication

A consumer can receive the same message multiple times due to broker redelivery or producer retry. The inbox pattern records processed message IDs to prevent repeated business updates.

Example schema:

```sql
CREATE TABLE processed_message (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

Consumer transaction processing:

```text
Begin transaction
    |
    +--> Insert eventId into processed_message
    |       |
    |       +--> new unique key: continue
    |       +--> already exists: skip business effect
    |
    +--> update business data
    |
Commit transaction
    |
Broker acknowledgement
```

If the business update fails, the transaction rolls back the inbox insert as well. The message is redelivered and can be processed again. If the inbox insert commits before the business update in a separate transaction, the system could mark an event processed even though the business effect never completed; avoid that design.

The deduplication table needs retention long enough to cover the replay window. Deleting inbox records too early allows a replayed old message to trigger the business effect again.

## File output and the possibility of creating files multiple times

File writers have different side effects than databases. The filesystem usually does not participate in the chunk's database transaction. Bytes may already be written to a file before a checkpoint commits; a restart might rewrite data or append/truncate the file depending on configuration.

When using `FlatFileItemWriter`, clearly determine:

- Is the output file newly created or appended?
- If the file already exists on a new launch, is it overwritten?
- When restarting the same execution, does the writer restore its position/checkpoint?
- Is the file published to consumers before the job completes?
- Can consumers read a partially written file?

### Write to a temporary file then publish

A safe pattern is writing to an execution-specific staging file, then publishing the file only when the job completes:

```text
Job starts
    |
    v
orders-batch-20261115.tmp
    |
    +--> write by chunk and checkpoint
    |
    v
Job completes and verifies file completeness
    |
    v
rename / publish as orders-batch-20261115.csv
```

Consumers read only files with the final name or a completion manifest. If the job restarts, it continues the temporary file of the same logical batch. If newly launched, use a new output identity or check the manifest so you do not accidentally overwrite an already published file.

Rename can be atomic within the same filesystem, though not every filesystem or object storage guarantees it. With object storage, you typically upload immutable objects and write a final manifest/marker last. Do not assume rename/marker operations are atomic if the storage backend does not support it.

### File names must have a stable identity

Do not use the current timestamp or a fresh random suffix on every retry if the same logical output needs to be resumed. Derive the output key from `batchId`, source version, or business date per contract. Separate the logical batch's identity from `JobExecutionId`, because restarts receive a new execution ID.

## HTTP APIs and external services

Calling an HTTP API in a writer can also create duplicates. For example, an invoice-creation API receives and processes the request, but the response is lost. The batch does not know the invoice was created and retries the request.

If the API supports an idempotency key:

```http
POST /invoices
Idempotency-Key: invoice:ORDER-100:2026-11
Content-Type: application/json
```

The server stores the result by key and returns the prior result when receiving a duplicate request within the retention window. The key must represent a single logical operation; do not generate a new key per attempt.

If the API does not support idempotency:

- Look for a lookup API by business key before re-creating, if the workflow allows it.
- Use a durable request/outbox table to track status and reconcile.
- Design the operation as PUT/upsert if semantics fit.
- Persist the response/reference upon success.
- Establish an operational procedure to investigate unknown outcomes after timeouts.

Do not blindly retry a resource-creating `POST` without understanding whether the API is idempotent. An HTTP timeout does not prove the server did not execute the request.

## Output consistency with multiple concurrent jobs

Even if a job never retries, two executions reading the same input can produce duplicate output. This is a concurrency and ownership problem.

Common mechanisms include:

- Unique constraints on business keys/output IDs.
- Claiming inputs via status or lease in the database.
- Partitioning input into disjoint sets.
- Locking by batch/business key when needed.
- Idempotent writers and consumers.
- Checking `JobInstance` identity and preventing duplicate launches per business batch.

Do not rely solely on checking "is the job currently running" at the scheduler layer when multiple nodes or multiple schedulers may exist. Claim decisions must be persisted in a shared resource with proper atomicity.

### Claiming inputs by status

One pattern transitions records from `READY` to `IN_PROGRESS` inside a claim transaction, attaching `batch_id`/owner and a lease. A worker processes only records claimed for that batch. After output completes, it updates status to `DONE`; if a worker dies, an expired lease allows recovery.

Leases do not eliminate duplicates completely: an old worker can still wake up after its lease expires and a new worker reclaims the work. Use fencing tokens/versions or idempotent output to prevent an old worker from writing invalid results.

## Processor, writer, and listener: where to place side effects?

Each component has a distinct role:

| Component | Appropriate role | Notes on repeated output |
| --- | --- | --- |
| `ItemReader` | Read items and restore position | Reader may re-read items after restart depending on checkpoint |
| `ItemProcessor` | Validation and transformation | May be invoked again; avoid non-idempotent side effects |
| `ItemWriter` | Write chunk output | May retry; design transactions/idempotency |
| `ItemWriteListener` | Observe write events | Do not assume callbacks are a once-only publishing hook |
| `ChunkListener` | Observe chunk boundaries | Side effects may repeat across rollbacks/retries |
| `StepExecutionListener` | Observe step lifecycle | `afterStep` is not a distributed commit hook |

Place business output in the writer or a stateful durable publishing step. The processor should produce output data rather than directly performing non-rollbackable actions.

Listeners fit metrics, logging, and deduplicable auditing. If you must send notifications after a business transaction commits, use an outbox or a durably backed after-commit mechanism; calling only in `afterStep` does not prevent repetition if the job is relaunched.

## Asynchronous writers and unconfirmed output

A writer may send messages or API calls asynchronously. If `write()` returns immediately after enqueuing futures without waiting for results, Spring Batch may consider the chunk complete while sends are still pending.

This creates two problems:

- A send fails after the checkpoint has advanced: output is lost from the batch's perspective.
- The process dies while futures are incomplete: outcome is unknown; it is unclear whether the broker received the messages.

If output is mandatory for the chunk, the writer must wait for acknowledgement/confirmation per policy before returning or use supported transaction/resource integration. When sending multiple messages in parallel, bound the number of in-flight futures and await all results; if some succeed before others fail, duplicates on retry must still be handled.

Do not swallow exceptions in callbacks or log and continue as if successful. Spring Batch can retry/fail only if the writer propagates the error outward.

## Skip can cause output not to be created

Retry focuses on trying again; skip allows omitting an item after exceeding policy thresholds. If an item is skipped in the writer, its corresponding output may not be created. That can be correct if bad data is rejected per business rules, but dangerous if the exception was actually a broker outage.

If using skip:

- Only skip errors that are acceptable to omit.
- Write a durable reject record with business key and reason.
- Monitor skip counts and alert when thresholds are exceeded.
- Do not skip transient broker errors just to make a job succeed.
- Maintain a process to fix data and replay rejected items.

`SkipListener` can record skipped items, but listener side effects also need idempotency and clear transaction boundaries.

## Exactly-once effect with a database writer

To achieve one business effect per logical output, you can combine:

1. A stable output ID.
2. A unique constraint or conditional upsert.
3. Business write and checkpoint in the same transaction when architecture supports it.
4. Input claiming to prevent multiple executions from overlapping.
5. Reconciliation to detect inputs without output or outputs without matching input.

For example, the output table has a unique `source_record_id`. When the writer is invoked again, a duplicate insert does not create a second row. If the output must be updated, use a version or compare-and-set so newer state is not overwritten.

Exactly-once effect is a property of the entire data pipeline, not a Spring Batch annotation or a single method.

## Verifying output after the job

A `COMPLETED` job does not by itself prove output is duplicate-free or complete. You must verify business invariants.

Examples:

- Every mandatory source record has exactly one output with the matching business key.
- No two outputs share the same `eventId` within the logical batch scope.
- `DONE` records plus `REJECTED` records equal claimed records, if that is the contract.
- Every outbox event requiring publication is in `PUBLISHED` state or an investigable error state.
- The final file has the expected manifest/checksum and record count.
- The consumer inbox shows each event ID produced only one business effect.

Reconciliation should rely on keys and durable state, not solely on comparing total read and written item counts. Filtering, skipping, retrying, and rejecting can legitimately cause those counters to differ by design.

## Example idempotent output design

Suppose a job produces one processing result per order. Construct the output key from `orderId` and the operation type:

```java
public record ProcessedOrder(
        String orderId,
        String operation,
        BigDecimal total,
        String resultCode) {

    public String outputId() {
        return operation + ":" + orderId;
    }
}
```

Place a unique constraint on `output_id` in the database:

```sql
CREATE TABLE order_output (
    output_id VARCHAR(120) PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,
    operation VARCHAR(50) NOT NULL,
    total DECIMAL(18, 2) NOT NULL,
    result_code VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);
```

The writer uses an insert/upsert statement tailored to the dialect. When the same output is retried, the database recognizes the same `output_id`. If the new content differs from what was already written, the application must decide whether that is a valid retry, a conflict, or a new version; do not overwrite unconditionally.

For messages, use the same `outputId` as the event ID or idempotency key. The consumer stores that key in its inbox before applying the business effect.

## Testing once-or-multiple output behavior

Tests must simulate failure windows, not just normal happy-path runs.

### Testing writer retry

Create a writer test double that counts invocations and fails deliberately. Verify Spring Batch retries the exact configured number of times. Simultaneously verify the output store holds only one logical result if the writer is designed to be idempotent.

### Testing rollback after output

Create a writer that sends a message successfully and then causes another operation in the chunk to fail. Verify the database rolls back while the out-of-transaction message may still exist. After restart/retry, verify duplicates are deduplicated via event ID.

### Testing crash between output and checkpoint

Simulate a process/job failure after the destination accepts output but before the checkpoint is confirmed. Restart the same `JobInstance` and verify the output does not produce a second business effect.

### Testing a new launch with the same input

Run a job to completion, then launch a new `JobInstance` with the same input/business batch. Verify unique business keys, batch claiming, or idempotency policies prevent duplicate output if business rules mandate once-only processing.

### Testing two concurrent executions

Launch two executions processing the same input dataset. Verify claims/unique constraints/locking prevent both executions from producing duplicate output. Test on a database whose concurrency behavior resembles production.

### Testing asynchronous acknowledgement

Make the producer future complete exceptionally after `write()` begins. Verify the writer awaits the result and throws the exception up to the step. Simulate the broker receiving a record while the acknowledgement is lost to test duplicate handling.

### Testing file restart

Have a job write part of a file and then fail. Restart the same execution and verify the file resumes at the exact checkpoint with no duplicate or missing lines. After the job completes, verify only the complete final file/manifest is visible to consumers.

### Testing outbox/inbox

Verify the following cases:

1. Business transaction rollback leaves no outbox event.
2. Business transaction commit persists the outbox event.
3. Broker receives message but publisher crashes before marking published, allowing resend.
4. Consumer receives duplicate events yet applies the business effect only once.
5. Inbox insert and business update roll back together when consumer processing fails.

### Testing reconciliation

After the job, query by business key to detect missing outputs, duplicates, unhandled rejects, and overdue pending outbox rows. Tests should not assert `BatchStatus.COMPLETED` alone.

## Common mistakes

### Thinking one write call means one output

The writer can be called again during retries or restarts. Design around logical output IDs and idempotency.

### Thinking Spring Batch guarantees exactly-once for every destination

Checkpoints and transactions only protect resources participating in the corresponding transaction. Files, brokers, and HTTP APIs typically do not roll back with the database.

### Sending messages without waiting for acknowledgement

The step may commit before discovering a send failed. Wait for results per policy or use appropriate transaction integration.

### Generating a fresh UUID on every attempt

Duplicates cannot be recognized because every send has a different ID. Keep IDs stable from the source or outbox.

### Retrying POST without an idempotency key

The server may create the resource again after a timeout. Use an idempotency key or reconcile unknown outcomes.

### Using a SELECT-then-INSERT check to prevent duplicates

Two executions can both see no row and both insert. Use unique constraints and handle conflicts atomically.

### Putting side effects in processors or listeners

Processors/listeners can be invoked multiple times. Keep transformations pure and move side effects into an idempotent writer/outbox.

### Swallowing exceptions so the step completes

The checkpoint may advance even though output was never created. Propagate errors or persist rejects durably per policy.

### Skipping broker errors

Events can be lost permanently. Retry/fail or retain events in an outbox.

### Launching a new JobInstance to "restart"

A new instance may reprocess all input from the start. Use proper restart semantics and business batch identity.

### Relying on JobExecutionId as an idempotency key

Execution IDs change on restart or new launch. Use a stable business identity.

### Skipping post-job output verification

`COMPLETED` status does not prove completeness or absence of duplicates. Reconcile by keys, event IDs, and state.

## Design principles

When you need to ensure output is created once from a business standpoint, determine:

1. Does "once" refer to method calls, message delivery, physical rows/files, or business effect?
2. Can the writer be invoked again due to retry, rollback, or restart?
3. Do business output and checkpoint share the same transaction/resource?
4. Does the destination support transactions or idempotency keys?
5. Does each logical output have a stable ID across all attempts?
6. Does the database have appropriate unique constraints or atomic upserts?
7. Does the message consumer have inbox/deduplication and an appropriate transaction?
8. Does file output have staging, a manifest, and post-completion publication?
9. Does the HTTP/API support idempotency keys or lookup/reconciliation?
10. Can two job executions process the same input concurrently?
11. Do processors/listeners have repeatable side effects?
12. Are retries, timeouts, and asynchronous acknowledgements bounded and observable?
13. Is there reconciliation for missing, duplicate, rejected, and pending outputs?
14. Have tests simulated rollbacks, crashes, restarts, new launches, and concurrent executions?

There is no single Spring Batch configuration flag that turns every output into exactly-once. Design per destination: use transactions and unique keys for databases, staging/manifests for files, stable event IDs with outbox/inbox for messages, and idempotency keys for APIs. Accept that operations may be attempted multiple times, and make the business effect identifiable and applied once. Test the failure windows between output acknowledgement, transaction commit, and checkpointing to prove behavior under retry/restart.

## Key takeaways

A single call to `write()` does not mean output was created only once. Retries, rollbacks, restarts, launching a new `JobInstance`, timeouts, and concurrent executions can all cause the same logical item to produce side effects multiple times. Spring Batch checkpoints help recover progress, yet are atomic with output only when both genuinely participate in the same transaction/resource. Databases can use unique constraints and upserts; files should write to staging and publish after completion; messages need stable event IDs, outbox/inbox, and consumer idempotency; HTTP APIs need idempotency keys or reconciliation. Keep pure transformations in the processor and controlled side effects in the writer, never swallow exceptions, and never send asynchronously and return before knowing the result per policy. The practical goal is one business effect despite multiple technical attempts; verify with reconciliation and tests covering rollbacks, crashes, retries, restarts, new launches, and concurrency.
