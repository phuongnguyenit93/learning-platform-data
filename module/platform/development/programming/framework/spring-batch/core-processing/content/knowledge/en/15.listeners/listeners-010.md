# Listeners Must Not Mask the Primary Error

In Spring Batch, listeners let applications observe and react to events across the job, step, chunk, and item lifecycles. For example, `ItemWriteListener` can log when the writer fails, `SkipListener` can persist skipped record details, and `StepExecutionListener` can summarize metrics after a step ends.

Listeners run close to the main processing flow. Consequently, an error raised inside a listener can occur at the exact moment the reader, processor, writer, or step is already handling another failure. If a listener throws a new exception inside an error-handling callback, the new exception can obscure the original root cause. Operators end up seeing an audit/logging error instead of the database, data, or business error that caused the job to fail.

The core principle is **never let a secondary error in a listener mask the primary error**. A listener must preserve the original exception, attach diagnostic details safely, and have a clear policy for the operations it performs. For side effects that must succeed, place them in the business flow with appropriate transactions and retries rather than relying on observation callbacks.

## Primary Error vs. Secondary Error in Batch Processing

Suppose `ItemWriter` writes a chunk to the database and the database throws `DeadlockLoserDataAccessException`. Spring Batch receives this error to roll back the transaction, retry, or mark the step failed according to configuration.

During error handling, `ItemWriteListener.onWriteError` is invoked to write an audit record. If the audit service also fails and the listener throws `RuntimeException("Cannot write audit")`, logs or failure status may focus on the listener's exception. The original cause—the deadlock—becomes obscured or hard to trace.

```text
ItemWriter writes chunk
        |
        v
Database throws deadlock error  <- primary error
        |
        v
onWriteError(exception, chunk)
        |
        v
Listener writes audit
        |
        +---- audit succeeds: preserve writer error
        |
        +---- audit fails: secondary error
                    |
                    v
           Attach secondary error to original error
           via addSuppressed(...)
                    |
                    v
           Let framework handle writer error
```

The two errors have different roles:

| Error Type | Examples | How to Handle |
| --- | --- | --- |
| Primary error (primary exception) | Writer deadlock, invalid data in processor, reader connection loss | Preserve it so Spring Batch can apply rollback, retry, skip, or mark failure |
| Secondary error (secondary exception) | Audit write failure, metrics backend unresponsive, error-notification failure | Record it as supplemental without replacing the primary error, unless business rules explicitly make the listener operation mandatory |

Not every listener error is secondary. If a listener performs a mandatory check deciding whether data may be processed, its failure may be the primary error of that operation. What must be avoided is accidentally replacing an already-occurred exception with another exception while handling the failure.

## Listener Callbacks and When Errors Occur

Spring Batch provides several listener types. Understand which callbacks run before/after the main operation and which run when an exception occurs.

| Listener | Related Callbacks | Purpose |
| --- | --- | --- |
| `ItemReadListener` | `beforeRead`, `afterRead`, `onReadError` | Observe individual item reads and read errors |
| `ItemProcessListener` | `beforeProcess`, `afterProcess`, `onProcessError` | Observe transformations and processor errors |
| `ItemWriteListener` | `beforeWrite`, `afterWrite`, `onWriteError` | Observe chunk writes and writer errors |
| `SkipListener` | `onSkipInRead`, `onSkipInProcess`, `onSkipInWrite` | Record the final item skipped under the skip policy |
| `ChunkListener` | `beforeChunk`, `afterChunk`, `afterChunkError` | Observe the chunk lifecycle |
| `StepExecutionListener` | `beforeStep`, `afterStep` | Pre- and post-step handling, reading or updating exit status |
| `JobExecutionListener` | `beforeJob`, `afterJob` | Pre- and post-job execution handling |

Callbacks do not share the same transaction boundary. For instance, `afterChunk` runs after the chunk has committed; an error in this callback cannot roll back already-committed data. Conversely, some item callbacks execute inside chunk processing and their errors can fail the chunk depending on invocation point and transaction mechanics.

Therefore, do not treat every listener as a hook with identical rollback capabilities. When implementing one, determine when the callback runs, how the framework handles its errors, and whether listener side effects can be repeated.

## Why Error Listeners Must Preserve the Original Exception

Callbacks such as `onReadError`, `onProcessError`, and `onWriteError` are invoked when the primary operation has already thrown an exception. The callback receives that exception to log, emit metrics, or record diagnostics.

If the callback throws another exception itself, several problems can occur:

- Stack traces show the audit or logging failure instead of the reader/processor/writer failure.
- Retry/skip classification is no longer based on the original exception as intended.
- The skip policy may not see the exact exception type the application configured.
- Root causes become difficult to find in logs when jobs run across multiple nodes.
- A transient secondary error in an observability system can disrupt core processing.

Example to avoid:

```java
@Override
public void onWriteError(Exception exception, Chunk<? extends Order> items) {
    auditService.recordFailure(items);
    throw new IllegalStateException("Could not record write failure");
}
```

If `recordFailure` throws an exception, the listener exits before finishing with the original information. If the listener goes on to throw `IllegalStateException`, the new exception can become what the framework observes from this callback.

An error listener should attempt to record secondary failures while preserving the passed-in exception. If secondary recording fails, attach the secondary exception to the original error using `Throwable.addSuppressed(...)` and let processing continue with the original exception.

## Safe Pattern: Recording Secondary Errors with addSuppressed

Java provides `Throwable.addSuppressed(Throwable)` to attach a secondary exception to a primary exception. When the stack trace is printed, suppressed exceptions still appear alongside the original error.

Example with `ItemWriteListener`:

```java
public class OrderWriteListener implements ItemWriteListener<Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderWriteListener.class);

    private final FailureAuditService auditService;

    public OrderWriteListener(FailureAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onWriteError(
            Exception primaryException,
            Chunk<? extends Order> items) {

        try {
            auditService.recordWriteFailure(items, primaryException);
        } catch (RuntimeException auditException) {
            primaryException.addSuppressed(auditException);
            log.error(
                    "Could not record write failure; preserving the original writer exception",
                    auditException);
        }
    }
}
```

In the example:

- `primaryException` is the exception thrown by the writer.
- The listener attempts to write an audit record to supplement information.
- If auditing fails, the audit exception is attached to the original exception.
- The listener does not throw the audit exception outward to replace the writer error.
- Spring Batch continues handling the writer error according to retry, skip, or rollback settings.

Catch only the exception types the listener expects to handle, typically `RuntimeException` from an audit service. Do not catch `Throwable` broadly, as that can swallow critical JVM errors such as `OutOfMemoryError`.

### Using a helper to standardize handling

If multiple listeners record audits, create a shared helper:

```java
public final class ListenerFailureSupport {

    private static final Logger log =
            LoggerFactory.getLogger(ListenerFailureSupport.class);

    private ListenerFailureSupport() {
    }

    public static void runSafely(
            Throwable primaryException,
            String operation,
            Runnable action) {

        try {
            action.run();
        } catch (RuntimeException secondaryException) {
            primaryException.addSuppressed(secondaryException);
            log.error(
                    "Listener operation '{}' failed; primary exception is preserved",
                    operation,
                    secondaryException);
        }
    }
}
```

A listener can call the helper:

```java
@Override
public void onProcessError(OrderInput item, Exception primaryException) {
    ListenerFailureSupport.runSafely(
            primaryException,
            "record-process-failure",
            () -> auditService.recordProcessFailure(item, primaryException));
}
```

The helper keeps secondary error-handling rules consistent across listeners. It does not replace Spring Batch's logging/monitoring; it adds diagnostic context if recording the failure itself fails.

## Do Not Mask Errors by Catching and Ignoring Them

Another dangerous practice is catching an exception inside a listener or tasklet and merely logging it:

```java
try {
    writer.write(chunk);
} catch (Exception ex) {
    log.error("Write failed", ex);
    // Does not rethrow exception
}
```

If the exception is swallowed and the method returns normally, Spring Batch may treat the operation as successful, continue updating metadata, and commit the transaction along the current flow. The step can then finish even though data was not fully written.

Inside a listener—especially error callbacks—do not re-invoke the writer yourself or turn an error into a successful result. Listeners observe errors; the framework and fault-tolerance configuration coordinate retries and skips. If a primary error cannot be recovered, let it propagate to the framework.

If you need to translate an exception into another business exception type, preserve the original cause:

```java
throw new BatchProcessingException(
        "Could not process order " + orderId,
        originalException);
```

Do this only where exception classification is intentional. Never wrap the original error in an exception from an audit or logging operation.

## Distinguishing Error Callbacks and SkipListener

`onReadError`, `onProcessError`, and `onWriteError` are called when the respective operation encounters an exception. If the step is configured with retry, an error can be retried multiple times; error callbacks may be called for each failed attempt.

`SkipListener` has a different purpose: it receives notifications when an item is actually skipped under the skip policy—that is, when the application decides to skip the item after applying retry/skip rules.

| Callback | Timing/Meaning | Appropriate Use |
| --- | --- | --- |
| `onProcessError` | Processor throws an exception | Diagnose a failed processing attempt; may run again during retries |
| `onWriteError` | Writer throws an exception | Record a failed chunk write attempt; distinguish retries from final failures |
| `onSkipInProcess` | Item is skipped after applying skip policy | Persist the final rejection record or audit the skip decision |
| `onSkipInWrite` | Item is skipped in the write phase | Record the unwritten item after the skip policy accepts the skip |

If the goal is to save one rejection record once an item is definitively skipped, `SkipListener` is usually better suited than writing a final error record in every `onProcessError`. If writing audits in error callbacks, avoid creating duplicate audit records for the same item across retries.

`SkipListener` methods can be invoked close to chunk commit time per the Spring Batch lifecycle. If the listener writes the reject record to the same transactional resource, the record can commit with the chunk. If writing to an external system, that side effect does not automatically roll back and still requires idempotency.

## Retries Can Invoke Listeners Multiple Times

A transient error can be retried. For instance, the writer hits a deadlock on the first attempt and succeeds on the second. `onWriteError` may have run on the first attempt even though the chunk ultimately completes.

If the listener sends an email or creates a ticket on every `onWriteError`, the system can generate multiple alerts for a transient issue that recovered on retry.

Distinguish:

- **Attempt failure:** a single read/process/write attempt failed.
- **Final skip:** an item was skipped after exhausting retries or per the skip policy.
- **Step failure:** the step could not complete and moved to a failed state.

Pick the callback matching what you want to record. To measure retry attempt counts, error callbacks are appropriate. To record rejections for finally skipped items, use `SkipListener`. To send a summary alert about step failure, consider `StepExecutionListener` or `JobExecutionListener` using the final status.

When creating audit records, use an idempotent key such as job execution ID, step execution ID, item business key, and event type. If the callback is invoked again, that key prevents duplicate records.

## Transaction Boundaries of Listeners

A listener failure can happen before, during, or after the main transaction. Know callback timing to understand the consequences.

| Callback | Relative Position | Consequences to Note |
| --- | --- | --- |
| `beforeChunk` | After chunk transaction starts, before chunk processing | Callback error can fail the chunk and roll back the transaction |
| `afterWrite` | After writer call during chunk processing | Callback error can fail the current chunk before commit |
| `afterChunk` | After chunk has committed | Callback error cannot roll back the committed chunk; side effects must be idempotent |
| `afterChunkError` | Chunk error/rollback path | Must not replace the original exception with a secondary recording error |
| `afterStep` | When step finishes main processing | Not suitable for business writes requiring the same transaction as chunks |
| `afterJob` | After job execution ends | Suitable for summaries/notifications; do not treat as step transactions |

Exact transaction details and how the framework handles exceptions for each callback depend on listener type and Spring Batch version. A safe rule is never to rely on a post-commit callback to roll back already-committed data, and never to assume listener lifecycles share a transaction with every business operation.

### Specifically with afterChunk

`afterChunk` is called after the chunk transaction has committed. If the listener fails while emitting post-commit metrics or notifications, the written chunk data remains persisted. Retrying or restarting the step after a listener error may re-encounter chunks or subsequent steps depending on saved checkpoints and state.

Therefore, `afterChunk` should perform lightweight, safely repeatable observation tasks. If an important event must be published corresponding to newly committed data, consider a transactional outbox rather than publishing directly in a post-commit callback.

### Specifically with afterStep

`StepExecutionListener.afterStep` returns an `ExitStatus` and can supplement or alter the exit code to drive flow control. In Spring Batch's lifecycle, exceptions thrown from `afterStep` are recorded by the framework as callback errors; do not rely on throwing an exception here to roll back already-committed chunks or guarantee the step transitions to failed in the desired manner.

If post-step checks need to steer the job flow, return an explicit `ExitStatus` and configure matching transitions. Example:

```java
public class ValidationSummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        if (stepExecution.getFilterCount() > 1_000) {
            return new ExitStatus("FILTER_LIMIT_EXCEEDED");
        }
        return null;
    }
}
```

The flow can handle that exit code:

```java
return new JobBuilder("importJob", jobRepository)
        .start(importStep)
            .on("FILTER_LIMIT_EXCEEDED").fail()
        .from(importStep)
            .on("*").to(summaryStep)
        .end()
        .build();
```

This illustrates routing the flow by exit code; configure transitions properly for all remaining job states. If a check is a mandatory business rule before writing data, validate in a tasklet/processor or a dedicated validation step rather than waiting until `afterStep`.

## Observation Listeners vs. Business-Action Listeners

A listener should have a small, predictable responsibility. You can categorize work by criticality:

| Work Type | Examples | Design Approach |
| --- | --- | --- |
| Observation | Timing logs, incrementing metrics, tracing execution IDs | Avoid failing the job simply because an observability backend is temporarily unavailable |
| Error diagnostics | Recording exception, item key, and step ID | Preserve original exception; attach recording failures as suppressed or send to fallback channel |
| Mandatory audit | Recording skip decisions or auditable business changes | Use proper transactions/resources, idempotency, and clear failure rules |
| Business operation | Updating status, creating data, sending critical commands | Place in a tasklet/processor/writer or business service coordinated by transactions |
| Flow control | Choosing an exit code after a step | Return an explicit `ExitStatus` and declare transitions |

If a listener must perform a data change that the job cannot skip, consider moving that change into a writer or tasklet. Its exception then becomes a business operation error, managed cleanly via transactions and fault tolerance.

Do not use `afterJob` to perform a mandatory database update and assume that update will roll back with the job. Steps may have already committed earlier, and job listeners run at a different lifecycle stage.

## Recording Error Audits Without Replacing the Primary Error

An audit record should store enough information to trace issues without embedding entire payloads or secrets.

Commonly useful fields:

- Job name and `jobExecutionId`.
- Step name and `stepExecutionId`.
- Callback type or processing phase.
- Item business key or chunk identifier if available.
- Class name of the primary exception and sanitized message.
- Correlation ID or trace ID.
- Timestamp and attempt number if tracked by the application.

Do not log full entities, tokens, credentials, or personal data just for debugging. If the audit database is unavailable, record the secondary error as a suppressed exception and via a fallback logger/monitor, while preserving the primary exception for Spring Batch.

Example of a processor error listener:

```java
public class OrderProcessListener
        implements ItemProcessListener<OrderInput, Order> {

    private static final Logger log =
            LoggerFactory.getLogger(OrderProcessListener.class);

    private final FailureAuditService auditService;

    public OrderProcessListener(FailureAuditService auditService) {
        this.auditService = auditService;
    }

    @Override
    public void onProcessError(OrderInput item, Exception primaryException) {
        try {
            auditService.recordProcessFailure(
                    item.orderId(),
                    primaryException.getClass().getName(),
                    primaryException.getMessage());
        } catch (RuntimeException auditException) {
            primaryException.addSuppressed(auditException);
            log.error(
                    "Failure audit unavailable for order {}; original processing error is preserved",
                    item.orderId(),
                    auditException);
        }
    }
}
```

The listener does not rethrow `primaryException` because the framework already holds that exception and will continue handling it after the callback. The listener simply ensures the audit error does not replace the original exception.

## When Must a Listener Failure Fail the Job?

There are cases where a listener error cannot be treated as secondary. For instance, a listener enforces a security check or mandatory audit before allowing the next step. If that operation fails, the application may need to stop the job.

Clarify the contract:

1. If the listener only records metrics or logs, failures should usually fail-open: record the secondary error and keep the primary flow intact.
2. If auditing is a mandatory requirement, use a business operation with explicit transactions and exception policies; do not rely on error callbacks for mandatory auditing.
3. If listener results control post-step flow, return a specific `ExitStatus` and configure transitions.
4. If a callback runs after commit, define recovery behavior because committed data cannot roll back.

Do not automatically swallow every listener exception. Fail-open is only appropriate for auxiliary tasks that do not determine business data correctness. For mandatory work, make those errors a transparent part of the main processing flow.

## Logging Exceptions Properly

Listener logs should help find root causes without adding noise.

- Log the original exception with its stack trace where the framework or error handler is responsible for logging.
- If a secondary error occurs, log it with job/step execution IDs and clearly state it occurred inside the listener.
- Avoid logging the same stack trace repeatedly in every callback if the framework already logs it completely.
- Do not log full payloads or sensitive data.
- Use structured logging to filter by job name, step name, execution ID, business key, and correlation ID.
- Keep suppressed exceptions when passing errors to final handlers so both the primary cause and secondary failures can be diagnosed.

Structured logging example:

```java
log.error(
        "Listener audit failed: jobExecutionId={}, stepExecutionId={}, itemKey={}",
        jobExecutionId,
        stepExecutionId,
        itemKey,
        auditException);
```

Messages should clearly distinguish `primaryException` and `auditException`. This is especially important when multiple jobs run concurrently across multiple nodes.

## Listeners and Retry, Skip, and Rollback

Listeners can be invoked multiple times depending on callback position and fault-tolerance policy. Avoid letting listener actions create duplicate side effects.

| Scenario | Expected Behavior |
| --- | --- |
| Processor fails and is retried | `onProcessError` can be called on failed attempts; do not create duplicate final audits per attempt if only one reject record is wanted |
| Writer fails and chunk rolls back | `onWriteError` observes the error; listener side effects outside the transaction may still persist |
| Item is finally skipped | `SkipListener` is suited for recording the final skip decision |
| Chunk commits then `afterChunk` fails | Chunk business data has committed; the listener cannot roll it back |
| Step finishes then `afterStep` fails | Cannot roll back previously committed chunks; use exit status/flow or proper business handling |

If a listener writes audits in the same database transaction, verify it genuinely uses the same transaction manager and resource. If the listener sends emails, HTTP requests, or messages, database transactions do not automatically retract those side effects.

For side effects requiring reliable post-commit delivery, a transactional outbox is usually better: write the event to an outbox table within the business transaction, then have an independent publisher send events and retry using a stable event ID.

## Testing That Listeners Do Not Mask Primary Errors

Test both the success case of the listener and the case where the listener itself fails.

### Error callbacks and secondary audit errors

Create a writer or processor that throws a known exception. Make the audit service inside the listener also throw an exception. Verify:

- The original exception remains the exception handled by the framework.
- The audit exception appears in `getSuppressed()` of the original exception if attached with `addSuppressed`.
- Retry/skip policies still see the right primary exception type.
- Logs clearly show the audit error is a secondary failure.

Helper unit test example:

```java
@Test
void keepsPrimaryExceptionWhenListenerActionFails() {
    RuntimeException primary = new RuntimeException("database deadlock");
    RuntimeException secondary = new RuntimeException("audit database unavailable");

    ListenerFailureSupport.runSafely(
            primary,
            "record-failure",
            () -> { throw secondary; });

    assertEquals("database deadlock", primary.getMessage());
    assertEquals(1, primary.getSuppressed().length);
    assertSame(secondary, primary.getSuppressed()[0]);
}
```

### Post-commit listeners

Have `afterChunk` throw a controlled error after chunk commit. Verify committed business data remains persisted and restart/investigation workflows handle the step state appropriately. This test prevents assuming post-commit callback errors can roll back a chunk.

### SkipListener

Trigger an item skipped under policy and verify the skip audit is recorded exactly once per application contract. Test retries prior to skipping to ensure error callbacks do not generate duplicate rejection records.

### afterStep and ExitStatus

Test that the listener returns a custom exit code and the job flow routes properly. If the callback has a secondary error, confirm logging/monitoring policies do not lose the step's primary error state.

### External side effects outside transactions

Simulate a listener sending a message successfully before the chunk or step fails. Verify the message does not roll back automatically and consumers/outbox have proper idempotency mechanisms.

## Common Design Mistakes

### Throwing a new exception inside an onError callback

Audit or notification failures replace the reader/processor/writer exception. Preserve the original exception and attach the secondary error with `addSuppressed`.

### Swallowing the main operation's exception

Catching an exception and only logging it can lead the framework to consider the chunk/tasklet successful. Let primary errors propagate to Spring Batch when the operation cannot complete properly.

### Writing final audits on every retry attempt

Error callbacks can be called repeatedly. Use attempt metrics per try; use `SkipListener` or an idempotent key for the final skip decision.

### Using afterChunk for mandatory business operations

This callback runs after commit. If the operation fails, committed chunk data cannot roll back. Use a writer/outbox or a subsequent step with explicit retries.

### Throwing an exception in afterStep expecting the step to become FAILED automatically

Do not rely on exceptions from this callback to alter status as desired. Use an explicit `ExitStatus` with configured transitions, or move mandatory checks into a business step.

### Making a listener do too much

A listener calling multiple APIs, writing multiple databases, or executing heavy business logic increases failure modes and blurs transaction boundaries. Keep listeners small; move business logic to appropriate services/tasklets/writers.

### Logging whole items or unfiltered exception messages

Payloads can contain sensitive data and bloat logs. Log business keys, execution IDs, and sanitized error info.

## Implementation Principles

When writing production listeners, align on these principles:

1. Clarify whether a callback is for observation, auditing, business operation, or flow control.
2. Distinguish primary exceptions of reader/processor/writer from secondary exceptions of the listener.
3. Inside error callbacks, never throw a new audit error that replaces the original exception.
4. Attach secondary errors to the primary exception with `addSuppressed` and log with context.
5. Do not catch and ignore exceptions from the primary operation.
6. Design audits and notifications to be idempotent because listeners can be invoked again.
7. Use `SkipListener` for final skip decisions instead of treating every attempt error as a skip.
8. Understand transaction boundaries; `afterChunk` runs after commit and cannot roll back the chunk.
9. Use `ExitStatus` with flow transitions when steering post-step outcomes.
10. Put mandatory business operations inside tasklets/processors/writers or an outbox with explicit transactions.
11. Test listeners when the audit/metrics/notification service itself fails.

## Key Takeaways

Listeners help observe and react to the job, step, chunk, and item lifecycles, yet secondary listener errors must never mask the primary exception. Inside `onReadError`, `onProcessError`, or `onWriteError`, preserve the passed-in exception; if auditing fails, attach the secondary exception via `addSuppressed` and log with context instead of throwing a new exception. Distinguish attempt errors from actually skipped items, know which callbacks run before versus after commit, and design side effects with idempotency. For mandatory business work, use tasklet/writer transactions or a transactional outbox; for post-step flow control, return an explicit `ExitStatus` and configure transitions rather than relying on callback exceptions to alter status.
