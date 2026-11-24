# Retry and Recovery Logging in Spring Batch

## 1. Objectives and Real-World Scenarios

In a batch job, an error does not always fail the entire job right away. A database connection may time out for a few seconds, an external API may temporarily return 503, or a business record may be invalid and need to be skipped per policy. Spring Batch lets you configure **retry**, **skip**, and post-error handling, and also lets you **restart** a job after an execution fails or stops.

However, if you simply log a single `ERROR` line for every exception, operators struggle to distinguish:

- A transient error that was retried and succeeded on the next attempt.
- An item retried several times and then skipped per policy.
- Exhausted retries causing the step to become `FAILED` and requiring a job restart.
- A new batch execution restarting from an earlier execution.
- A single exception thrown repeatedly representing **one underlying issue**, not many independent bad records.

**Retry and recovery logging** must reflect the journey from *failed attempt* to *final outcome*, aiding investigation without generating thousands of false alarms.

After this lesson, you will be able to:

1. Distinguish retry, skip, recovery, and restart in Spring Batch Core Processing.
2. Pick the right listener to log each retry attempt, skip event, and step/job outcome.
3. Attach the IDs needed to correlate logs with `JobExecution` and `StepExecution`.
4. Configure a fault-tolerant chunk step and its listeners in Java.
5. Avoid duplicate logs, leaking sensitive data, or falsely logging that an error “recovered”.
6. Design tests for retry-then-succeed, retry-exhausted, skip, and restart scenarios.

Examples use Java 17+, Spring Boot 3.x, Spring Batch 5.x, Spring Retry, and SLF4J. Business fields are illustrated using payment record processing.

## 2. Distinguishing Retry, Recovery, Skip, and Restart

These concepts are related, yet **not synonymous**:

| Concept | Scope | What Happens | What to Log |
| --- | --- | --- | --- |
| **Retry** | A read, process, or write operation inside a step | Re-invokes the operation after a retryable exception | Transient error, exception type, failure count, step/execution |
| **Recovery** | Handling when retries are exhausted or a fallback succeeds | Selects an alternative path: skip, fallback, dead-letter, or designed failure | The path actually applied and the final outcome |
| **Skip** | One item in a fault-tolerant step | Accepts dropping the bad item if exception type and skip limit allow | Safe item key, read/process/write phase, exception class |
| **Restart** | One JobInstance across multiple JobExecutions | Launches a new execution of an incomplete instance | JobInstance ID stays constant; JobExecution ID changes |

Example of a writer calling a service to update order statuses:

```text
JobInstance  301 (businessDate = 2026-11-15)
  |
  +-- JobExecution 901
       |
       +-- StepExecution 5001
            |
            +-- write record P-17 -> timeout (attempt 1)
            +-- write record P-17 -> timeout (attempt 2)
            +-- write record P-17 -> succeeded (attempt 3)
            |
            +-- write record P-18 -> invalid data error
            +-- P-18 skipped per policy
            |
            +-- Step COMPLETED with recorded skips
```

The first two timeouts are **retryable** error events; they do not automatically mean the item ultimately failed. Item P-18 being skipped is a separate outcome event. In this example, the job can still end `COMPLETED` despite exceptions during processing.

### Recovery Is Not a Single Built-In Callback for Every Job

In Spring Retry, a `RetryTemplate` can be configured with a `RecoveryCallback` that runs when retries are exhausted. However, in a **Spring Batch chunk step**, the post-retry path depends on fault-tolerance configuration: an item may be skipped if the exception is skippable and `skipLimit` allows it, or the step may fail. Do not assume enabling `.retry(...)` provides a generic `recover()` callback or an automatic dead-letter queue.

Logs and documentation should therefore speak accurately: `retry.attempt_failed`, `item.skipped`, `fallback.applied`, or `step.failed`, matching the actual event. Use the word “recovered” only when there is evidence that an alternative handling path succeeded per business requirements.

## 3. Retry Lifecycle and Log Emission Points

An operation within a chunk can follow this conceptual flow:

```text
                       Execute read/process/write
                                  |
                             Succeeded?
                            /           \
                          Yes            No
                          |               |
                          v               v
                    Continue chunk    Exception
                                          |
                                          v
                                  Does retry apply?
                                    /           \
                                  Yes            No
                                  |               |
                                  v               v
                           Attempts left?    Is skip allowed?
                            /      \           /       \
                          Yes       No        Yes       No
                          |          |         |          |
                        Retry   Handle      Discard    Step FAILED
                                 after      item
                                retries     (skip)
                                    |
                           Skip / fallback / fail
```

This diagram shows the concept; actual behavior also depends on where the exception arises, transaction rollbacks, retry policy, and skip policy.

Useful observation points:

| Observation Point | API or Mechanism | What to Record |
| --- | --- | --- |
| Each failing attempt | `RetryListener.onError(...)` | Retry-loop failure event, exception type, retry count |
| Reader/processor/writer error | `ItemReadListener.onReadError`, `ItemProcessListener.onProcessError`, `ItemWriteListener.onWriteError` | Phase context where error occurred; avoid uncontrolled duplicate logging |
| An item is actually skipped | `SkipListener.onSkipInRead/Process/Write` | Phase-specific skip event, permitted key, cause |
| Chunk error or rollback | `ChunkListener.afterChunkError` and step metadata | Transaction/chunk context; do not prematurely conclude job FAILED |
| Step completes | `StepExecutionListener.afterStep` | `BatchStatus`, `ExitStatus`, read/write/filter/skip/rollback counts |
| Job finishes | `JobExecutionListener.afterJob` | Final execution outcome and correlation IDs |
| Job is restarted | Launcher/scheduler and JobRepository | New execution belonging to the existing JobInstance |

**Important:** `RetryListener.onError` is invoked whenever an attempt throws an exception, including the final attempt when no retries remain. Never log “retry succeeded” or “another attempt is coming” based solely on `onError`. Confirm success by observing subsequent outcomes or final statuses.

## 4. What Information Belongs in Retry and Recovery Logs

A structured log line should carry fields linking the event to a specific execution:

| Field | Meaning |
| --- | --- |
| `event` | Event type: `batch.retry.error`, `batch.item.skipped`, `batch.step.finished` |
| `jobName` | Job name |
| `jobInstanceId` | Business instance, preserved across restarts |
| `jobExecutionId` | Current execution attempt |
| `stepName` and `stepExecutionId` | Step currently executing |
| `businessDate` or `fileId` | Safe business key distinguishing datasets |
| `phase` | `READ`, `PROCESS`, `WRITE` |
| `retryFailureCount` | Failure count within the current RetryContext |
| `exceptionType` / `errorCode` | Classifiable error category |
| `itemKey` | Safe item ID; may be `NULL` when a read error prevents constructing an item |
| `outcome` | Final outcome: `SKIPPED`, `COMPLETED`, `FAILED`, `FALLBACK_APPLIED` |

Clearly distinguish **error count in RetryContext** from **total attempts across the entire job**. Retry counts are scoped to one retry cycle and can reset for another item/chunk/operation, or behave differently under stateful retry. Never sum arbitrary retry counts from logs to deduce exact physical invocation totals.

Sample logs:

```text
WARN  event=batch.retry.error job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 retryFailureCount=1 exceptionType=QueryTimeoutException

WARN  event=batch.retry.error job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 retryFailureCount=2 exceptionType=QueryTimeoutException

INFO  event=batch.item.skipped job=paymentImportJob jobExecutionId=901 step=chargeStep stepExecutionId=5001 phase=PROCESS itemKey=P-18 exceptionType=InvalidPaymentException

INFO  event=batch.step.finished job=paymentImportJob jobExecutionId=901 step=chargeStep status=COMPLETED readCount=120 writeCount=119 skipCount=1 rollbackCount=2
```

Numbers in these logs only illustrate formatting. Actual rollback counts depend on chunking, transactions, and error types; retry count does not have a fixed one-to-one mapping to `rollbackCount`.

## 5. Configuring a Fault-Tolerant Step

Suppose the system reads payment records. Transient database errors are retried; confirmed invalid business data can be skipped within limits.

Illustrative domain model:

```java
import java.math.BigDecimal;

public record PaymentRecord(
        String paymentId,
        BigDecimal amount) {
}

public class InvalidPaymentException extends RuntimeException {
    public InvalidPaymentException(String message) {
        super(message);
    }
}
```

Step configuration example in Spring Batch 5.x style:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.configuration.annotation.StepScope;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.transaction.PlatformTransactionManager;

@Configuration
public class PaymentStepConfiguration {

    @Bean
    Step chargeStep(
            JobRepository jobRepository,
            PlatformTransactionManager transactionManager,
            ItemReader<PaymentRecord> reader,
            ItemProcessor<PaymentRecord, PaymentRecord> processor,
            ItemWriter<PaymentRecord> writer,
            BatchRetryLogListener retryLogListener,
            BatchSkipLogListener skipLogListener,
            BatchStepLogListener stepLogListener) {

        return new StepBuilder("chargeStep", jobRepository)
            .<PaymentRecord, PaymentRecord>chunk(
                50, transactionManager
            )
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(TransientDataAccessException.class)
            .retryLimit(3)
            .skip(InvalidPaymentException.class)
            .skipLimit(5)
            .listener(retryLogListener)
            .listener(skipLogListener)
            .listener(stepLogListener)
            .build();
    }
}
```

This example assumes `ItemReader`, `ItemProcessor`, `ItemWriter`, and the listener beans defined in the following sections already exist. In real configuration, verify whether client/JDBC exceptions are translated to `TransientDataAccessException`; the framework applies retry policies only to exceptions matching configured rules.

In this configuration:

- `retry(TransientDataAccessException.class)` specifies the transient error hierarchy eligible for retries.
- `retryLimit(3)` caps the step's retry mechanism; verify actual call counts against your version and retry policy rather than inferring a number from logs.
- `skip(InvalidPaymentException.class)` permits discarding invalid business records when that exception occurs in an eligible stage.
- `skipLimit(5)` bounds total skips allowed in a single StepExecution; exceeding the limit typically fails the step.
- Listeners observe errors and outcomes without replacing retry/skip policies.

**Note on recovery:** An exception outside the skippable set can still make the step `FAILED` once retries are exhausted. There is no built-in logic automatically routing failed records to a dead-letter queue. To persist failed records for manual handling, design an explicit writer/skip sink accounting for transactions.

## 6. Logging Each Retry Attempt with RetryListener

Spring Batch integrates Spring Retry for fault tolerance. `org.springframework.retry.RetryListener` lets you observe callbacks inside the retry loop.

A stateless logging-only implementation:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.scope.context.StepContext;
import org.springframework.batch.core.scope.context.StepSynchronizationManager;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.RetryListener;
import org.springframework.stereotype.Component;

@Component
public class BatchRetryLogListener implements RetryListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchRetryLogListener.class);

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        StepContext stepContext =
            StepSynchronizationManager.getContext();

        if (stepContext == null) {
            log.warn(
                "event=batch.retry.error retryFailureCount={} " +
                "exceptionType={} step=unknown",
                context.getRetryCount(),
                throwable.getClass().getSimpleName()
            );
            return;
        }

        StepExecution step = stepContext.getStepExecution();

        log.warn(
            "event=batch.retry.error job={} jobInstanceId={} " +
            "jobExecutionId={} step={} stepExecutionId={} " +
            "retryFailureCount={} exceptionType={}",
            step.getJobExecution().getJobInstance().getJobName(),
            step.getJobExecution().getJobInstance().getInstanceId(),
            step.getJobExecutionId(),
            step.getStepName(),
            step.getId(),
            context.getRetryCount(),
            throwable.getClass().getSimpleName()
        );
    }
}
```

Here, `RetryContext.getRetryCount()` represents the failure count recorded by the context. In standard `RetryListener` behavior, `onError` fires after an attempt throws an exception; never treat this value as a durable counter across the entire StepExecution.

`StepSynchronizationManager.getContext()` retrieves step context on the current thread. It may be absent in unit tests invoking the listener directly, or in code running outside Spring Batch-managed scopes. The example handles a `null` context safely.

**Do not use RetryListener to make retry decisions.** Listeners should only observe; let the framework enforce retry/skip policies. A listener throwing an exception or calling slow external services can disrupt the step, so keep logging logic short and safe.

### Can You Log the Item Key Here?

A generic `RetryListener` does not directly receive `PaymentRecord` in its callback. Avoid casting `RetryCallback` or relying on undocumented internal structures to extract record keys. When item-level correlation is needed, add IDs inside the processor/writer with vetted data or log skip events where the listener receives the item. In multi-threaded processing, never store the “currently processing item” in a singleton bean field, as threads will overwrite it.

## 7. Logging Skip-Path Recovery with SkipListener

When an item is **actually skipped**, Spring Batch invokes `SkipListener` callbacks by phase. This is the right place to log discarded-item outcomes.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.SkipListener;
import org.springframework.stereotype.Component;

@Component
public class BatchSkipLogListener
        implements SkipListener<PaymentRecord, PaymentRecord> {

    private static final Logger log =
        LoggerFactory.getLogger(BatchSkipLogListener.class);

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Read errors may occur before a PaymentRecord is constructed.
        log.warn(
            "event=batch.item.skipped phase=READ " +
            "exceptionType={}",
            throwable.getClass().getSimpleName()
        );
    }

    @Override
    public void onSkipInProcess(
            PaymentRecord item,
            Throwable throwable) {

        log.warn(
            "event=batch.item.skipped phase=PROCESS " +
            "itemKey={} exceptionType={}",
            item.paymentId(),
            throwable.getClass().getSimpleName()
        );
    }

    @Override
    public void onSkipInWrite(
            PaymentRecord item,
            Throwable throwable) {

        log.warn(
            "event=batch.item.skipped phase=WRITE " +
            "itemKey={} exceptionType={}",
            item.paymentId(),
            throwable.getClass().getSimpleName()
        );
    }
}
```

In this example, `paymentId` is assumed to be a key permitted in logs. If raw keys contain personal data or sensitive info, substitute an internal reference token, a policy-compliant hash, or omit the field.

`onSkipInRead` has no item to identify because the failure can occur before the reader successfully maps an object. If file line numbers or source keys are needed, expose them from the reader or an adapter in an application-controlled manner.

An operational note: skip callbacks are designed to run near chunk completion and before commit. Never treat an emitted log line as proof that the surrounding data transaction ultimately committed. When recording skipped items must be **durable and transactionally consistent**, write to an error/outbox table inside the appropriate transaction and publish external events via retryable, idempotent delivery.

### Filter and Skip Are Different

A processor can return `null` to filter out records that do not need processing. Spring Batch increments `filterCount`, does not invoke `SkipListener` by default, and does not consume `skipLimit`. When business logic must distinguish “excluded intentionally” from “failed record”, design two separate outcome paths and corresponding log events.

## 8. Logging the Final Outcome in StepExecutionListener

After scanning many retry logs, the most important question is **how the step ultimately ended**. `StepExecution` holds the authoritative status and counters to answer that.

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.batch.core.ExitStatus;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.StepExecutionListener;
import org.springframework.stereotype.Component;

@Component
public class BatchStepLogListener implements StepExecutionListener {

    private static final Logger log =
        LoggerFactory.getLogger(BatchStepLogListener.class);

    @Override
    public ExitStatus afterStep(StepExecution step) {
        log.info(
            "event=batch.step.finished jobExecutionId={} " +
            "step={} stepExecutionId={} status={} exitCode={} " +
            "readCount={} writeCount={} filterCount={} " +
            "readSkipCount={} processSkipCount={} " +
            "writeSkipCount={} commitCount={} rollbackCount={}",
            step.getJobExecutionId(),
            step.getStepName(),
            step.getId(),
            step.getStatus(),
            step.getExitStatus().getExitCode(),
            step.getReadCount(),
            step.getWriteCount(),
            step.getFilterCount(),
            step.getReadSkipCount(),
            step.getProcessSkipCount(),
            step.getWriteSkipCount(),
            step.getCommitCount(),
            step.getRollbackCount()
        );

        // Do not alter the ExitStatus determined by Spring Batch.
        return null;
    }
}
```

To avoid misleadingly reporting a job as “succeeded”, inspect both `BatchStatus` and `ExitStatus`.

Meaningful counters:

| Field | Description |
| --- | --- |
| `readCount` | Items successfully read by the reader per step metadata |
| `writeCount` | Items written per Spring Batch statistics |
| `filterCount` | Items filtered out by the processor returning `null` |
| `readSkipCount` | Read errors skipped |
| `processSkipCount` | Process errors skipped |
| `writeSkipCount` | Write errors skipped |
| `commitCount` | Recorded transaction commits |
| `rollbackCount` | Recorded transaction rollbacks |

**There is no overall `StepExecution.getRetryCount()`** to tell you “the whole step retried N times”. Retry cycles must be measured with dedicated listeners/metrics if operations require transient-error or retry-attempt statistics. Even with retry metrics, define scope by operation and state, especially under stateful retries and rollbacks.

## 9. Recovery After Retries Are Exhausted: Different Paths Need Different Logs

When retries do not resolve an error, the system can respond in several ways.

### 9.1. Skip the Item If Policy Allows

For example, a business error belongs to the skippable category and `skipLimit` is not exceeded: the step skips that item and continues. `SkipListener` logs show the skip outcome; step logs show total skips and final status.

Never log “recovered” on the final `RetryListener.onError` while guessing the step will skip. Whether a skip happens depends on policies evaluated after the failure and remaining limits.

### 9.2. Custom Fallback or Dead-Letter Handling

Business requirements may dictate that after exceeding allowed external service calls, a record moves to a manual-review table or dead-letter queue.

This **does not happen automatically** just by configuring `.retry(...)`. You must implement an explicit fallback/dead-letter path, guarantee idempotency, and define what counts as “handled”.

When an alternative path succeeds, log:

```text
event=batch.recovery.applied
jobExecutionId=901
step=chargeStep
itemKey=P-18
strategy=QUARANTINE
outcome=COMMITTED
errorCode=REMOTE_TIMEOUT
```

These fields are application log conventions, not Spring Batch built-in attributes. Specifically, log `outcome=COMMITTED` only when backed by confirmation that the transaction committed, not immediately upon invoking a write API.

### 9.3. Step Fails and the Job Is Restarted

If retries exhaust and the exception is not skippable, the step can transition to `FAILED`. `StepExecutionListener.afterStep` and `JobExecutionListener.afterJob` log the final outcome. A subsequent run with the same identifying parameters creates a new JobExecution if the job is restartable.

```text
JobInstance 301
  JobExecution 901 -> FAILED
  JobExecution 902 -> COMPLETED (restart)

stepExecutionId and retry contexts belong to each individual execution.
```

A restart is different from a retry within the same execution. Never add up `RetryContext` counts across executions and call that an overall “item retry count” without defining a formal aggregation model.

## 10. Spring Retry's RecoveryCallback and Spring Batch

If the application uses `RetryTemplate` directly outside chunk fault tolerance, declare a `RecoveryCallback` to explicitly define handling when retries exhaust:

```java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.TransientDataAccessException;
import org.springframework.retry.support.RetryTemplate;

public class RemoteLookupService {

    private static final Logger log =
        LoggerFactory.getLogger(RemoteLookupService.class);

    private final RetryTemplate retryTemplate =
        RetryTemplate.builder()
            .maxAttempts(3)
            .retryOn(TransientDataAccessException.class)
            .build();

    public String lookupWithFallback(String paymentId) {
        return retryTemplate.execute(
            context -> requestRemoteStatus(paymentId),
            context -> {
                Throwable last = context.getLastThrowable();

                log.error(
                    "event=remote.lookup.recovered paymentKey={} " +
                    "strategy=MANUAL_REVIEW errorType={}",
                    paymentId,
                    last == null
                        ? "UNKNOWN"
                        : last.getClass().getSimpleName()
                );

                return "MANUAL_REVIEW";
            }
        );
    }

    private String requestRemoteStatus(String paymentId) {
        // TODO: Call real service; may throw a retryable exception.
        return "PAID";
    }
}
```

In this example, `MANUAL_REVIEW` is an **application-defined fallback result**; it does not mean the payment transaction succeeded. When used inside a Batch processor, verify that the returned value leads the writer to persist an appropriate state.

**Avoid uncontrolled nested retries.** If a `RetryTemplate` inside a processor retries up to 3 times while Spring Batch also retries the processor 3 times, a persistent outage can multiply outbound calls far beyond expectations. Clearly assign which layer owns retries, bound timeouts, and calculate worst-case call amplification.

## 11. Stateful Retry, Rollbacks, and Duplicate Logs

Spring Batch processes chunks inside transactions. Depending on failure location and policies, items/chunks can be reprocessed, transactions can roll back, readers can re-read data, or retry state can be tracked across passes.

Consequently, when reading logs:

- **One item can produce multiple error events** across attempts.
- **A chunk can roll back** after several operations inside it already ran.
- **Emitted logs generally do not roll back with batch transactions**.
- **A restart** can produce retry logs for items already attempted in the prior execution.
- `SkipListener` indicates an item was skipped per policy, yet does not by itself prove the bad record was durably saved outside the Batch repository.

This affects dashboards: never count `batch.retry.error` lines as “number of failed records” because one record can emit many lines. To know how many records were discarded, use step `skipCount` and rows persisted in an error table. For infrastructure stability, total retry errors remain a separate useful metric.

### Relationship with Idempotency

Writers that send emails, call payment APIs, or perform non-transactional writes must be designed so retries/restarts do not produce duplicate side effects. Logs cannot enforce idempotency. Use business keys, unique constraints, outboxes, or target-system status verification as appropriate.

For instance, an API may have processed a request even though the response timed out; if `RetryListener` logs a timeout and the step retries, the second call risks repeating the effect. Audits and idempotency keys determine safe recovery.

## 12. Classifying Log Levels

Not every transient error belongs at `ERROR`.

| Event | Recommended Level | Reason |
| --- | --- | --- |
| Attempt failed while retries remain | `DEBUG` or rate-limited `WARN` | Not yet a final failure |
| Sustained retries crossing alert threshold | `WARN` | Risks impacting SLA |
| Item skipped per policy | `INFO` or `WARN` depending on business severity | Intentional handling outcome |
| Fallback successfully applied | `INFO`/`WARN` | Must distinguish alternative path |
| Step/job ultimately `FAILED` | `ERROR` | Requires monitoring and investigation |
| Non-skippable sensitive data error | `ERROR` with standardized code | Avoid leaking payloads in logs |

Some environments prefer logging retry attempts at `DEBUG` while incrementing metrics and alerting only when retry rates cross thresholds. This reduces noise when transient errors happen frequently and self-heal.

### Limiting Excessive Logging in Large Batches

If a job reads one million records and 10% retry three times, logging full stack traces per attempt consumes significant resources. Better organization:

1. Log each error type with a short classifier field and correlation ID.
2. Restrict full stack traces to representative samples or the step's final failure.
3. Use counters/metrics to measure retry totals by job, step, error type, and outcome.
4. In `afterStep`, log read/write/skip/rollback totals.
5. When investigating a specific item, query the audit/error table using permitted keys.

Never use per-event unique `itemId` or `jobExecutionId` as time-series metric labels if your metrics backend cannot handle high cardinality. Keep those IDs in logs, traces, or audit tables.

## 13. Preventing Business Data Leaks in Logs

An exception thrown during CSV reading, SQL writing, or API calls may embed raw input strings inside its message. Logging like:

```java
log.error("Failed item: {}", paymentRecord, exception);
```

can inadvertently write account numbers, customer names, or payment data. A safer approach:

```java
log.error(
    "event=batch.item.failed paymentKey={} exceptionType={}",
    safePaymentKey,
    exception.getClass().getSimpleName()
);
```

When stack traces are needed, emit them on access-restricted channels with appropriate masking rules. Never log tokens, passwords, card details, full message bodies, or entire `JobParameters` unless explicitly vetted.

Timestamp fields should standardize on UTC or ISO-8601 with timezone offsets. In multi-scheduler/multi-worker systems, attach a trace ID or launch correlation ID to follow a request across services without relying on log line ordering.

## 14. Testing Retry and Recovery Events

A solid test suite combines unit tests mocking retry callbacks with integration tests running real steps using controlled data and exceptions. When testing logging, verify **event types and their relationship to final outcomes**, avoiding brittle full-string assertions that break on field renames.

### 14.1. Scenarios to Cover

| Scenario | Setup | What to Observe |
| --- | --- | --- |
| Immediate success | Writer/processor throws no errors | Zero `batch.retry.error` logs; step `COMPLETED` |
| Transient failure then success | Operation throws 1–2 times before succeeding | Attempt error logs present; item succeeds; not skipped |
| Retries exhausted and non-skippable | Always throws retryable exception with no valid recovery | Step `FAILED`; job ends with matching final status |
| Invalid record skipped | Throw `InvalidPaymentException` in processor with skip policy | `onSkipInProcess` fires; `processSkipCount` increments |
| Read error skipped | Reader throws configured skippable error | `onSkipInRead` fires; do not assume an item key exists |
| Write failure | Writer throws controlled error | Logs accurate phase and rollback/skip/fail outcome |
| Restart after failure | First execution `FAILED`, rerun with same identifying params | Same JobInstance ID, new JobExecution ID, fresh logs |
| Launcher rejects completed instance | Duplicate launch request with old params | No new retry/step callbacks; logged at launcher/coordinator |
| Dedicated fallback mechanism | RetryTemplate exhausts, RecoveryCallback returns fallback | Fallback log emitted and output carries fallback state |

### 14.2. Unit Testing RetryListener

`RetryListener` can be invoked directly to test error log formatting:

```java
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.dao.TransientDataAccessResourceException;
import org.springframework.retry.RetryCallback;
import org.springframework.retry.RetryContext;
import org.springframework.retry.context.RetryContextSupport;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class BatchRetryLogListenerTest {

    @Test
    void logsRetryFailureWithoutStepContext(CapturedOutput output) {
        BatchRetryLogListener listener =
            new BatchRetryLogListener();

        RetryContextSupport context =
            new RetryContextSupport(null);

        RuntimeException error =
            new TransientDataAccessResourceException("timeout");

        context.registerThrowable(error);

        RetryCallback<Void, RuntimeException> callback =
            retryContext -> null;

        listener.onError(context, callback, error);

        assertThat(output.getOut())
            .contains("event=batch.retry.error")
            .contains("exceptionType=TransientDataAccessResourceException")
            .contains("step=unknown");
    }
}
```

This is a pure listener unit test, so `StepSynchronizationManager.getContext()` is unset; the listener logs `step=unknown` by design. It verifies message formatting on error, **not** that the step's retry policy is wired properly.

### 14.3. Integration Testing with a Real Step

To test Spring Batch retry/skip behavior, use `spring-batch-test` with a test `JobRepository` and mock dependencies with controlled invocation counts. Use `AtomicInteger` so a writer throws a transient error on the first call and succeeds on the next. Isolate each test's metadata database or clean it carefully, and disable auto-run with `spring.batch.job.enabled=false`.

Assertions should cover:

- `BatchStatus`/`ExitStatus` of both step and job.
- `readCount`, `writeCount`, `filterCount`, `readSkipCount`, `processSkipCount`, `writeSkipCount`, and `rollbackCount` where meaningful.
- Call counts to mock dependencies proving retries occurred.
- Actual output data: zero duplicates from retries/rollbacks.
- Retry log events on transient failures; skip events only when items are actually skipped.
- New execution ID and preserved JobInstance ID on restart.

For concurrency-dependent tests, use synchronization primitives such as `CountDownLatch` rather than `Thread.sleep` guesses.

## 15. Recording Retries via Metrics and Error Tables

Logs help investigate individual executions, whereas managing large batch workloads requires trend aggregation. Define metrics or an error table with fields like:

```text
batch_retry_errors_total{
  job="paymentImportJob",
  step="chargeStep",
  exception="QueryTimeoutException"
}

batch_skipped_items_total{
  job="paymentImportJob",
  step="chargeStep",
  phase="PROCESS",
  reason="INVALID_AMOUNT"
}
```

These are **application-defined metric name examples**, not default metrics guaranteed by Spring Batch everywhere. Environment-specific metrics depend on installed versions and instrumentation.

When long-term tracking of each skipped item is required, write to an error table with business key, execution ID, processing step, reason code, and timestamp. Error-table writes must follow idempotency rules across step restarts and chunk rollbacks. Never deduce exact unique failed item counts by counting retry log lines.

A practical dashboard tracks `FAILED` step rate, skip counts, duration, top exceptions, and restarted execution counts. Alert on **final outcomes/SLA breaches**, then use retry/error logs to pinpoint root causes.

## 16. Common Logging Implementation Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| A transient error fires multiple `ERROR` alerts | Logging every attempt as a final error | Log attempts at an appropriate level; alert on step/job outcomes |
| Logs say “recovered” yet job ends `FAILED` | Treating `onError` or `close` as successful recovery | Log recovery only when the alternative path truly completes |
| No item logged on reader failure | `onSkipInRead` receives no item | Log phase/exception and add safe reader source location if available |
| Skip logged, yet error table lacks the row | Logs are non-transactional or external write failed | Use an error table/outbox, transactions, and reconciliation |
| Skip count is 0 though processor returned null | Confused filter with skip | Check `filterCount` and clarify policy design |
| Step has many retries yet low `rollbackCount` | Both counters track different events | Never infer retries from rollbacks or vice versa |
| Spring Batch + RetryTemplate multiply API calls | Nested retries | Assign one retry layer, cap max attempts and timeouts |
| Retry creates a different JobInstance | Restart used changed identifying params | Keep business keys stable on restart |
| Restart inflates total retry log count | Multiple JobExecutions under one instance | Aggregate per execution and per instance separately |
| Customer IDs leak into logs | Logging raw payloads or exception messages | Allowlist/redact fields and enforce log RBAC |
| Step log lacks failure details | Only logging read/write counts | Log BatchStatus, ExitStatus, and exception classification |
| `RetryListener` callbacks never fire | Listener not registered or exception not in retry policy | Inspect listener wiring and exception classifier |
| Retry count summed as failed item count | One item generates multiple attempts | Use skip counts or error tables to count items |

## 17. Hands-on Exercise

Build a job importing payment transactions from a file or database. Configure the step with chunk size 10, retry for transient network errors, and skip for malformed business records up to a limit.

Implementation requirements:

1. `RetryListener` logs every retry failure with step, `jobExecutionId`, `retryFailureCount`, and `exceptionType`.
2. `SkipListener` logs records skipped in read, process, or write phases; item keys must be hidden if sensitive.
3. `StepExecutionListener` logs the final outcome and read/write/filter/skip/rollback counters.
4. Exhausted retries must clearly surface `FAILED`, while errors retried to success must not be counted as skipped items.
5. On restart, logs must show the JobInstance ID preserved and a new JobExecution ID created.

Prepare four test datasets: all valid; transient network error once then recovers; malformed business record skipped; sustained network outage failing the step. Then inspect mock call counts, business output, Spring Batch metadata, and log messages.

Try adding a `RetryTemplate` with a `RecoveryCallback` returning `MANUAL_REVIEW`. Verify exactly when the callback runs, how fallback data is persisted to the target, and whether rollback policies could cause duplicate side effects.

## 18. Conclusion

Retry and recovery logging in Spring Batch must clearly distinguish **a failing attempt**, **an item skipped or handled via fallback**, and **whether the step/job ultimately succeeded or failed**. `RetryListener` observes individual exceptions in the retry loop; `SkipListener` records discarded-item events; `StepExecutionListener` and `JobExecutionListener` confirm final execution outcomes. Logs require correlation keys, error categories, phases, and proper counters while keeping log frequency and sensitive data under control. Separating in-execution retries from JobInstance restarts makes incident investigation and batch quality tracking far more accurate.
