# Rollback and Skip

In Spring Batch, rollback and skip are two distinct mechanisms that often collaborate when an item causes an error in a chunk-oriented step. Rollback undoes uncommitted changes of the current transaction. Skip allows the step to exclude a failing item from processing and continue with remaining items, provided the exception is skippable and the skip limit has not been exceeded.

Crucially, skip does not guarantee the current transaction stays intact. When an exception occurs, Spring Batch may roll back the chunk to restore a consistent state, then perform recovery to pinpoint the failing item and continue with valid data. Therefore, an item that is eventually skipped can still cause the initial chunk to roll back.

## 1. Rollback and Skip Solve Two Different Problems

Rollback is transaction manager behavior. When an uncommitted transaction encounters an error requiring rollback, changes belonging to that transaction are undone. Skip is Spring Batch's fault-tolerant data policy: the framework accepts discarding an item and continuing the step rather than failing the whole step.

| Mechanism | Purpose | Outcome |
|---|---|---|
| Rollback | Ensure uncommitted changes are not retained when a transaction fails | Undoes current transaction on managed resources |
| Skip | Allow discarding an item with a permitted error | Item is not written successfully; step may continue |

For example, a chunk has 10 orders. The processor finds that the 4th order has invalid data. If the exception is configured as skippable, Spring Batch can roll back the ongoing chunk execution, restore reader state, and rerun the necessary portion without sending the failing item to the writer. Remaining valid items can still be written and committed in a recovery chunk.

Rollback protects transaction consistency; skip decides whether a failing item may be discarded. The two mechanisms complement each other.

## 2. Chunk Transaction Boundaries

In chunk-oriented processing, Spring Batch processes a group of items within the step's transaction. The reader fetches items, the processor transforms each item, and the writer writes the group of output items. If the chunk completes, the transaction commits; if a rollbackable error occurs before commit, the transaction rolls back.

```text
Chunk transaction starts
        |
        v
     Reader
        |
        v
    Processor
        |
        v
     Writer
        |
        +-- all succeed --> COMMIT
        |
        +-- rollbackable error --> ROLLBACK
                                  |
                                  v
                              recovery
                                  |
                         skip / retry / fail
```

Previously committed chunks are separate transactions and do not roll back merely because a later chunk fails. Normal rollback affects only the currently open transaction on resources actually participating in that transaction.

For example, a step with `chunk(10, transactionManager)`: each group of up to 10 items is processed in one transaction. If the 5th chunk errors and rolls back, committed data from chunks 1 through 4 remains intact. Spring Batch can continue or end in failure depending on skip/retry policies.

## 3. Configuring Skip for Specific Exceptions

In Spring Batch 5, enable fault tolerance and declare skippable exceptions with `.skip(...)`. `skipLimit(...)` bounds the total number of items allowed to be skipped during the step execution.

```java
@Bean
Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderRow> reader,
        ItemProcessor<OrderRow, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("importOrders", jobRepository)
        .<OrderRow, Order>chunk(10, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .build();
}
```

In this example, `InvalidOrderException` represents a discardable data error. The step is permitted to skip up to 20 items under policy. Other exceptions are not automatically skipped; without retry or another handling policy, they can fail the step.

Only skip exceptions with clear business meaning. Avoid `.skip(Exception.class)` because an overly broad rule can hide programming bugs, connection failures, schema mismatches, or system misconfiguration.

## 4. How Is the Skip Limit Counted?

`skipLimit(n)` sets the total skip limit for a step execution. This limit is shared across errors occurring in the read, process, and write phases, rather than being a separate limit per phase.

For instance, with `.skipLimit(5)`: the step can tolerate up to five skipped items. When a sixth skip occurs, the step exceeds the limit and fails.

| Skipped Item Count | Behavior with `skipLimit(5)` |
|---:|---|
| 0–4 | Still within limit |
| 5 | Allowance used up, not yet exceeded |
| 6 | Limit exceeded; step fails |

The skip limit applies to one step execution, not a retry budget. An item retried several times that ultimately succeeds does not count as a skip simply because failed attempts occurred.

Set the skip limit based on data quality and business tolerances. If failing items exceed the threshold, the job should stop rather than publish incomplete results.

## 5. Skip in Read, Process, and Write

Spring Batch can skip errors arising in all three phases. How the failing item is identified and what data listeners receive differs.

| Phase | Example Error | Is Item Available to Record? |
|---|---|---|
| Read | CSV line cannot be parsed into an object | Typically no successfully read item; only the exception |
| Process | Missing order code or invalid data | Processor input item is available |
| Write | Unique constraint violation on write | Output item or chunk received by writer is available; recovery may need to isolate the failing item |

Example configuring skip for two error types:

```java
.faultTolerant()
.skip(MalformedInputException.class)
.skip(InvalidOrderException.class)
.skipLimit(50)
```

Do not reuse one generic exception across every phase if recovery differs. Clear classification clarifies which errors may be skipped and which listener should record them.

## 6. When Skipping Still Rolls Back the Chunk

An error in a chunk can roll back the transaction before Spring Batch completes recovery. After rollback, the framework may re-read/reprocess relevant data to isolate the failing item and discard it under the skip policy.

Example where the processor throws `InvalidOrderException` for one item:

```text
Initial chunk: A, B, C, D, E

Initial attempt:
  process A -> OK
  process B -> OK
  process C -> InvalidOrderException
  transaction -> ROLLBACK

Recovery:
  identify C as the failing item
  skip C per skip policy
  reprocess/continue with A, B, D, E per framework mechanism
  writer writes valid items
  recovery transaction commits
```

This is a conceptual description; how many times reader/processor/writer callbacks are re-invoked depends on the failing phase and fault-tolerance configuration. Do not assume every item in a chunk is read or processed strictly once.

Rollback during recovery ensures uncommitted database operations leave no partial state. Skipping then allows remaining valid data to be written.

## 7. Distinguishing Skip from Filtering with null

A processor can return `null` to intentionally filter an item. Filtering is not an exception and does not count as a skip.

```java
@Bean
ItemProcessor<OrderRow, Order> orderProcessor() {
    return row -> {
        if (row.cancelled()) {
            return null; // Filter: item is valid but excluded from output to be written
        }

        if (row.orderId() == null || row.orderId().isBlank()) {
            throw new InvalidOrderException("Order ID is required");
        }

        return toOrder(row);
    };
}
```

In this example, cancelled orders are filtered by business rule. Orders missing an ID throw an exception and are skipped only if the step configures `InvalidOrderException` as skippable.

| Handling | Meaning | Increments Skip Count? |
|---|---|---|
| Processor returns `null` | Intentional item filtering | No |
| Processor throws exception accepted by skip policy | Discard failing item via fault tolerance | Yes |
| Processor throws non-skippable exception | Step may fail | Not counted as a successful skip |

Do not use `null` to hide bad data, because skip metrics and audit trails will then misrepresent source data quality.

## 8. noRollback: Exceptions That Do Not Require Rollback

Spring Batch allows declaring exceptions that do not roll back the transaction using `.noRollback(...)` in fault-tolerant step configuration. This mechanism is useful when the exception represents a situation where prior operations in the transaction can still be safely retained.

```java
return new StepBuilder("processOrders", jobRepository)
    .<OrderRow, Order>chunk(10, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .skip(InvalidOrderException.class)
    .noRollback(InvalidOrderException.class)
    .skipLimit(20)
    .build();
```

`noRollback` adjusts rollback classification; it does not automatically make an exception skippable. To discard the item, you still must declare an appropriate skip policy. The two settings answer distinct questions: is the exception allowed to be discarded, and when the exception occurs must the transaction roll back?

Use `noRollback` only after understanding exactly which operations occurred before the exception. If the transaction already wrote partial business data without rolling back, inconsistent state may be left behind. An error arising in the processor before the writer writes data differs from an error occurring mid-way through a series of writes.

Do not apply `noRollback` broadly to all exceptions. Use specific exception types and verify with real transactions.

## 9. How Do Skip and Retry Work Together?

Retry re-attempts an operation likely to succeed if a transient error disappears. Skip accepts discarding the item once policy determines not to keep trying or the error belongs to an allowed skip category.

Example where a partner service occasionally times out:

```java
return new StepBuilder("enrichOrders", jobRepository)
    .<OrderRow, EnrichedOrder>chunk(20, transactionManager)
    .reader(reader)
    .processor(processor)
    .writer(writer)
    .faultTolerant()
    .retry(TransientPartnerException.class)
    .retryLimit(3)
    .skip(InvalidOrderException.class)
    .skipLimit(25)
    .build();
```

In this configuration, transient timeouts are retried up to the configured limit. `InvalidOrderException` data errors are skipped. If you also want partner errors to be skipped after retries are exhausted, explicitly add that exception to the skip policy and verify business rules allow discarding the item.

Do not assume every exception is automatically skipped once retries are exhausted. If the exception is not skippable, the step fails when recovery cannot proceed.

## 10. Writer Errors and Rolling Back the Entire Chunk

The writer typically receives a `Chunk` containing multiple items. If the writer throws an exception while writing, the chunk transaction can roll back. When fault tolerance is configured, Spring Batch can perform recovery to pinpoint the failing item, retry, or skip according to policy.

Example where the writer inserts multiple orders and one violates a unique constraint:

```text
Writer receives: [A, B, C, D]
  write A
  write B
  write C -> duplicate key exception

Transaction rollback:
  changes for A and B in transaction are undone

Recovery:
  identify failing item per fault-tolerance mechanism
  skip C if exception and skip limit allow
  re-write valid items
```

Do not assume the writer is invoked only once. During recovery, the writer may be called again with different chunks or subsets of items. Writers must be safe to re-invoke, especially if calling external APIs or producing side effects outside the database transaction.

## 11. SkipListener Recording Discarded Items

`SkipListener` provides phase-specific callbacks to record skipped items. It is the right place to persist reject records, log failure reasons, or update metrics per discarded item.

```java
public class OrderSkipListener implements SkipListener<OrderRow, Order> {

    private static final Logger log =
        LoggerFactory.getLogger(OrderSkipListener.class);

    @Override
    public void onSkipInRead(Throwable error) {
        log.warn("Input could not be read: {}", error.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderRow item, Throwable error) {
        log.warn("Skipping order {}: {}", item.orderId(), error.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable error) {
        log.warn("Skipping order {} during write: {}", item.orderId(), error.getMessage());
    }
}
```

Registering the listener:

```java
.faultTolerant()
.skip(InvalidOrderException.class)
.skipLimit(20)
.listener(orderSkipListener)
```

`onSkipInRead` receives no item because the reader could not produce a valid item. `onSkipInProcess` receives the processor's input item. `onSkipInWrite` receives the output item skipped during the write phase.

Spring Batch designs skip callbacks to notify when an item is genuinely skipped during recovery, rather than treating every exception occurrence as a final skip. Listeners should record carefully and avoid non-idempotent side effects.

## 12. Recording Reject Records and Transactions

Many systems persist failed records into a reject table so operators can investigate and reprocess them. This can be done in `SkipListener`, while minding transaction boundaries.

If the reject record is written to the same datasource and an appropriate transaction, the change can participate in the step's transaction according to how the listener is invoked. If writing to another database or external system, the operation may not roll back with the chunk.

Principles to follow:

- Record business key, data source, failing phase, exception type, and enough reason to investigate.
- Use unique keys or idempotency keys to avoid duplicate reject records during recovery/restart.
- Avoid storing full sensitive payloads unnecessarily.
- If reject records and skip state must commit consistently, check the actual transaction manager and datasource.
- Do not silently swallow reject-write errors; explicitly decide whether the job must stop or fall back if the reject store is unavailable.

For data requiring strict auditing, use an outbox or staging table within the same database transaction and handle notifications separately post-commit.

## 13. Rollback Does Not Undo Non-Transactional Side Effects

Rollback only affects resources participating in the transaction. If a processor or writer calls HTTP APIs, sends emails, publishes messages, or writes directly to files, a database transaction cannot automatically undo those actions.

For example, a writer sends payment requests for three orders. The first two are accepted by the external system, and the third times out. Rolling back the chunk's database transaction does not mean the first two payment requests were cancelled.

To avoid duplicate processing or state drift:

1. Use stable, business-derived idempotency keys for each external request.
2. Write outbound requests to an outbox within the database transaction, then dispatch post-commit.
3. For files, write to temporary files and publish only after the transaction/step completes by design.
4. Implement status reconciliation after timeouts since you do not know whether the external system accepted the request.
5. If an already-executed action must be reversed, design explicit compensation; database rollback does not replace compensation.

## 14. Impact of Rollback on Reader State and Checkpoints

Readers may persist read positions in `ExecutionContext`. When a chunk rolls back, Spring Batch needs to restore an appropriate state so uncommitted items are not missed. Readers supporting `ItemStream` and state persistence normally integrate with the framework's checkpointing mechanism.

Do not advance checkpoints to a new position before the corresponding data is committed. If the checkpoint moves ahead of business data, restarts may skip items. If data committed while the checkpoint stayed behind, items may be re-read; writers should be idempotent or use business keys to handle this safely.

For stateless readers or external sources that cannot roll back, design re-reading via stable keys, offsets, or cursors. Skip/retry does not automatically make arbitrary custom readers restartable.

## 15. Which Exceptions Roll Back and Which Are Skipped?

Skip policy and rollback classification are two independent configurations. An exception may be skippable yet still roll back the transaction before framework recovery. Conversely, `noRollback` configuration does not automatically permit skipping the exception.

| Skip Policy | Rollback Policy | General Meaning |
|---|---|---|
| Not skippable | Rollback | Exception rolls back chunk and step typically fails |
| Skippable | Rollback | Rollback/recovery may occur, then item is skipped and chunk continues if valid |
| Skippable | No rollback | Item can be skipped without rolling back transaction per classification; safe only if prior changes remain valid |
| Not skippable | No rollback | Not automatically skipped; step can still fail even if transaction does not roll back per classification |

This table states general principles; exact behavior depends on the phase where the exception arises, reader/writer, transaction manager, and fault-tolerance implementation. In particular, errors in the writer may require different recovery than errors in the processor.

## 16. When Should noRollback Be Used?

`noRollback` is not a default optimization for speed. Consider it only when the exception represents a scenario where keeping the current transaction's changes is valid under business rules and produces no partial data.

For example, a processor detects an item belonging to a group that should not be written and throws an exception classified for skip. If the processor made no database changes, skipping rollback may avoid unnecessary rollbacks in some designs. However, if writes already occurred earlier in the same transaction, verify that preserving those changes does not corrupt data.

Before using it, check:

- In which phase can the exception occur?
- Before the exception, what data did the transaction modify?
- Are those modifications valid if the item is skipped?
- Do reader/processor/writer have state needing rollback or restoration?
- In which transaction does the reject-recording listener participate?
- Do integration tests prove the database state after the exception is right?

## 17. Common Mistakes When Combining Rollback and Skip

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming skip means no rollback | Misunderstanding recovery; chunk changes may have been undone | Distinguish skip policy from transaction rollback |
| Skipping every `Exception` | Hides system failures and programming bugs | Skip only specific data exceptions |
| Assuming exhausted retries auto-skip | Step still fails if exception is not skippable | Declare skip explicitly when business rules permit |
| Using `noRollback` for unclassified write errors | Can preserve partial data | Configure specific exceptions only and test transactions |
| Non-idempotent reject record writes | Recovery/restart can create duplicate rejects | Use unique keys or an outbox |
| Sending emails/APIs in listener then chunk rolls back | External side effects persist | Dispatch post-commit or use idempotency |
| Swallowing exceptions in the writer | Framework does not know chunk failed for rollback/recovery | Propagate exceptions outward |
| Not monitoring skip counts | Job completes while data quality degrades | Track read/write/skip counts and error rates |

## 18. Testing Rollback and Skip

Tests must verify both batch status and committed data. Asserting only that `JobExecution` is `COMPLETED` is insufficient to prove rollback and skip work properly.

Scenarios to include:

1. Valid items: writer writes data and chunk commits.
2. Processor throws skippable exception: item is skipped, valid items are written.
3. Non-skippable exception: chunk rolls back and step fails.
4. Skip limit sufficient: step continues while skips stay within limit.
5. Skip limit exceeded: step fails and uncommitted chunk data rolls back.
6. Writer fails mid-chunk: verify database changes in the transaction roll back.
7. Combining retry and skip: transient error succeeds after retry, data error is skipped.
8. `noRollback`: verify exactly which changes are preserved and why that is safe.
9. SkipListener: reject records are written the right number of times without duplicates on recovery.
10. Non-transactional side effects: verify idempotency or compensation works when the chunk rolls back.

Integration tests should use `JobRepository`, a transaction manager, and a database compatible with the runtime environment. Use writers/processors simulating failures at deterministic points to observe commits/rollbacks and callbacks.

## 19. Production Workflow for Choosing Rollback and Skip

When an item causes an error, decide in sequence:

1. Determine whether the error is item-specific data badness or a systemic failure affecting many items.
2. If the error is transient, consider bounded retry before skipping.
3. If the item may be discarded under business rules, declare the specific exception skippable with an appropriate `skipLimit`.
4. If the item must not be discarded, let the step fail when retries cannot resolve the error.
5. Determine whether the transaction must roll back when the exception occurs; use `noRollback` only when keeping current changes is safe.
6. Record skipped items via `SkipListener` or an idempotent reject store.
7. Audit non-transactional side effects and design outbox/compensation where needed.
8. Monitor skip counts, rollbacks, retries, and per-step statuses to detect degrading source data or downstream dependencies.

## Conclusion

Rollback undoes uncommitted changes in the current transaction; skip allows Spring Batch to exclude a failing item and continue the step if the exception is permitted and `skipLimit` is not exceeded. During recovery, the initial chunk may have rolled back before the failing item was isolated and skipped. Thus, skip does not imply the transaction never rolls back.

Classify exceptions clearly, configure bounded skips, use `SkipListener` to record discarded items, and use `noRollback` only when changes prior to the exception remain valid. Rollback does not undo external side effects, so writers and external integrations still require idempotency, outboxes, or compensation for safe retries and restarts.
