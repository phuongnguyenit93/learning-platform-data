# Recovery after retry exhaustion

In Spring Batch, retry lets you re-attempt an operation when encountering a recoverable error, such as a deadlock or transient connection error. However, retries always have a limit. When allowed attempts are exhausted and the operation still fails, the application must decide how to proceed. This is **recovery after retry exhaustion**.

Recovery does not mean retrying forever. Depending on the error type and business requirements, Spring Batch can discard the item under a skip policy, record the failed item for later handling, or fail the step so operators can fix the cause and restart. Choosing the right branch prevents lost data, duplicate writes, or masked system failures.

## 1. Retry and retry exhaustion

In chunk processing, the reader fetches items, the processor transforms them, and the writer persists results. If an operation raises an exception classified as retryable, Spring Batch can retry according to the configured retry policy.

For example, a writer updating the database encounters a deadlock. The database may pick one transaction as a victim and roll it back. This error can be transient: retrying after a pause may allow the transaction to succeed.

```text
Item / chunk processed
          |
          v
       Writer
          |
          +---- Deadlock exception
                    |
                    v
                 Retry
                    |
             +------+------+
             |             |
          Success      Still failing
             |             |
             v             v
          Commit      Retry further
                           |
                           v
                  Retry limit exhausted
                           |
                           v
                     Recovery path
```

**Retry exhaustion** occurs when an operation still throws an error after using up all allowed attempts. From this point on, the retry policy stops retrying; the exception passes to the next handling stage of the fault-tolerant step.

In Spring Batch, the next branch is typically:

- If the exception is allowed by the skip policy and `skipLimit` is not exceeded, the item may be skipped; `SkipListener` can record the failure.
- If the exception is not skippable or the skip limit is exceeded, the exception fails the chunk/step.
- If the application uses a separate retry/recovery abstraction, that abstraction's recovery callback can perform a fallback action as designed.

Not every failure after retries can be recovered automatically. Distinguish transient errors, data errors, and configuration/infrastructure failures.

## 2. Configuring retry in Spring Batch

For a chunk-oriented step, retry configuration normally goes into the fault-tolerant section of the step builder.

```java
@Bean
Step updateOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<OrderInput> reader,
        ItemProcessor<OrderInput, Order> processor,
        ItemWriter<Order> writer) {

    return new StepBuilder("updateOrdersStep", jobRepository)
            .<OrderInput, Order>chunk(100, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .faultTolerant()
            .retry(DeadlockLoserDataAccessException.class)
            .retryLimit(3)
            .build();
}
```

In this example, the step retries only the specified deadlock exception. Do not retry every `Exception`, because errors like malformed data, missing required columns, or broken SQL will not vanish after a few attempts.

`retryLimit` sets the limit for the retry policy. When reading the API/docs of your Spring Batch and Spring Retry versions, confirm how the policy counts calls (initial attempt vs. retries) so you do not confuse total attempts with additional retries. In operations, log actual attempt numbers rather than guessing from configuration names.

### Choosing retryable exceptions

Errors typically considered for retry if transient in nature:

- Deadlocks or lock acquisition failures.
- Certain recoverable database connection glitches.
- Timeouts when calling external services, if the operation can be resent safely.
- Transient failures from storage systems or message brokers.

Errors normally not suited for retry:

- Invalid data or violations of deterministic business rules.
- Wrong SQL/schema or missing columns.
- Missing required input files.
- Access denied due to misconfiguration.
- Unrecoverable programming bugs.

If an exception has multiple causes, classify explicitly by specific exception or cause chain. A general exception like `DataAccessException` covers both transient errors and errors unfixable by retrying.

## 3. Recovery after retry exhaustion in a fault-tolerant step

In Spring Batch chunk processing, retry and skip are often configured together. When an operation exhausts retries, the framework checks the exception against the skip policy. If the exception is skippable, the item can be skipped and the chunk continues. Otherwise, the step fails.

Example allowing deadlock retries, and if still failing after retries, skipping the item per business policy:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skip(DeadlockLoserDataAccessException.class)
        .skipLimit(20)
        .build();
```

This example illustrates a conditional choice: once deadlock retries are exhausted, the deadlock exception is also skipped if the skip budget permits. Only do this if business rules tolerate bypassing that item and reconciliation exists. If deadlocks indicate an overloaded database or widespread contention, skipping items one by one can mask a system outage; in that case, let the step fail.

The key distinction is that retry policy and skip policy answer two different questions:

- Retry policy: should this exception be retried, and at most how many times?
- Skip policy: once an item cannot be processed, is it permissible to discard it so the step can continue?

If the exception is not skippable, exhausting retries lets the exception propagate out and fail the step. That is also a valid recovery decision: halt to preserve data trustworthiness and wait for intervention.

## 4. When should you skip after retry exhaustion?

Skipping fits when a faulty item can be isolated without corrupting the outcomes of remaining items. Examples:

- An order with an invalid reference code.
- A malformed file line while other lines are independent.
- A record failing a business condition defined as discardable.

Skipping usually does not fit when the error indicates the entire target system is unavailable. For example, the writer cannot write because the database lost connectivity. Skipping items while the database is down can leave most data unwritten while the job finishes anyway.

Before allowing an exception to be skipped after retries, verify:

1. Is the item independent of other items?
2. Does skipping the item violate a business obligation?
3. Can the failed item be recorded for fixing and later reprocessing?
4. Is the exception specific to one item, or a sign of a systemic failure?
5. Can the offending item be identified accurately, especially when errors arise in a chunk writer?

If you cannot answer these clearly, letting the step fail is usually safer.

## 5. Recording items after retry exhaustion with SkipListener

When an item is skipped, `SkipListener` is the right place to capture error details and business keys for reconciliation.

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    private final RejectedOrderService rejectedOrderService;

    public OrderSkipListener(RejectedOrderService rejectedOrderService) {
        this.rejectedOrderService = rejectedOrderService;
    }

    @Override
    public void onSkipInRead(Throwable throwable) {
        rejectedOrderService.recordReadFailure(
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        rejectedOrderService.recordRejectedOrder(
                item.orderId(),
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        rejectedOrderService.recordWriteFailure(
                item.orderId(),
                throwable.getClass().getSimpleName(),
                throwable.getMessage());
    }
}
```

Register the listener on the step:

```java
return new StepBuilder("importOrdersStep", jobRepository)
        .<OrderInput, Order>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(50)
        .listener(orderSkipListener)
        .build();
```

The listener provides phase-specific information:

- `onSkipInRead`: the reader failed before creating an item; the callback receives only the exception.
- `onSkipInProcess`: provides the input item and the exception from the processor.
- `onSkipInWrite`: provides the output item and the exception from the writer.

For writer errors, the framework may need to isolate the failing item in the chunk. Not every writer or exception allows identifying the exact offending item cleanly.

### Ensuring error recording does not create new errors

If `RejectedOrderService` writes to the same database and chunk transaction, writing the reject record participates in that transaction. If the listener sends messages or calls external APIs, side effects do not roll back automatically with the database transaction.

Use deduplication keys, such as `(job_execution_id, step_execution_id, item_id, error_type)`, or an outbox if notifications are required. Do not let an item retried/skipped multiple times generate duplicate error records without distinguishing history from unique records.

## 6. Recovery using a dead-letter or rejected-record store

A common option is persisting unprocessable items into a quarantine/rejected store for later correction or reprocessing. This is not automatic Spring Batch behavior; the application must build the storage and operational workflow.

A rejected-item table might store:

| Field | Purpose |
|---|---|
| `batch_id` | Business batch identifier. |
| `job_execution_id` | Execution that recorded the error. |
| `step_execution_id` | Step where the error occurred. |
| `item_key` | Business key of the item. |
| `payload_reference` | Path or key to source data if the payload is large. |
| `exception_type` | Final error type after retries. |
| `error_message` | Sanitized error details. |
| `attempt_count` | Attempt count recorded if tracked by the application. |
| `recovery_status` | Status such as `PENDING`, `REPROCESSED`, `RESOLVED`. |
| `created_at` | Timestamp recorded. |

For sensitive data, avoid storing full payloads or credentials in error tables. Store reference keys to an access-controlled data store instead.

A typical reprocessing workflow for rejected items includes:

1. Filter items in `PENDING` status.
2. Identify and fix the root cause if necessary.
3. Create a reprocessing batch with a distinct identifier or feed items into a recovery job.
4. Record the new success/failure result while retaining prior failure history.
5. Mark the item as reprocessed in a consistent transaction.

Do not delete the initial error trail once recovery succeeds; that history is valuable for auditing and data quality analysis.

## 7. Recovery with RetryListener and callbacks

In the Spring Retry ecosystem, `RetryListener` lets you observe the retry lifecycle—opening context, receiving notification on each failure, and closing context upon completion. It is useful for logging attempts, emitting metrics, or attaching correlation IDs.

```java
public class LoggingRetryListener implements RetryListener {

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        // Record a failed retry attempt.
        log.warn("Retry attempt failed: {}", throwable.toString());
    }
}
```

Specific callback APIs and listener registration depend on the Spring Retry/Spring Batch versions in use. In a Spring Batch fault-tolerant step, register listeners using the mechanisms supported by the builder/step. Do not confuse a `RetryListener` used for observing retries with a recovery callback authorized to substitute an alternative result.

When using `RetryTemplate` directly inside a service, Spring Retry supports `RecoveryCallback` to define a result when the retry policy runs out of attempts:

```java
RetryTemplate retryTemplate = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(1000)
        .retryOn(TransientDataAccessException.class)
        .build();

OrderResult result = retryTemplate.execute(
        context -> orderGateway.submit(order),
        context -> recoveryService.recordPending(order, context.getLastThrowable()));
```

This snippet demonstrates standalone Spring Retry usage: once retries are exhausted, the recovery callback records a request for deferred processing and returns an `OrderResult` per application contract. If the recovery callback cannot produce a valid result, it should throw an exception so the error propagates to the caller.

Do not arbitrarily wrap an entire `ItemProcessor` or `ItemWriter` in a separate `RetryTemplate` if the step already has a Spring Batch retry policy. Two overlapping retry layers can raise actual attempts higher than expected, complicate timing calculations, and trigger repeated side effects.

## 8. Backoff after each retry

Immediate repeated retries can overload an already stressed system further. Backoff introduces a pause between attempts, giving services/databases time to recover.

Common strategies:

- **Fixed backoff:** waits the same duration every time.
- **Exponential backoff:** increases the wait time progressively across attempts.
- **Exponential backoff with jitter:** adds randomness so multiple workers do not retry at the exact same instant.

Example configuring a policy in a fault-tolerant step:

```java
ExponentialBackOffPolicy backOffPolicy = new ExponentialBackOffPolicy();
backOffPolicy.setInitialInterval(500L);
backOffPolicy.setMultiplier(2.0);
backOffPolicy.setMaxInterval(5000L);

return new StepBuilder("callPartnerStep", jobRepository)
        .<PartnerRequest, PartnerResponse>chunk(50, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .backOffPolicy(backOffPolicy)
        .build();
```

Backoff duration must fit within the job's time budget and service timeouts. With multiple partitions, consider jitter or concurrency limits to prevent retry storms.

## 9. When retries are exhausted and the exception is not skippable

If the exception does not belong to the skip policy or the skip limit has been exceeded, the step typically ends as `FAILED`. This is a vital recovery path: stop processing, persist metadata, raise alerts, and await remediation.

Example of a step that retries deadlocks only, without allowing skip:

```java
return new StepBuilder("criticalBalanceStep", jobRepository)
        .<BalanceInput, BalanceUpdate>chunk(100, transactionManager)
        .reader(balanceReader)
        .processor(balanceProcessor)
        .writer(balanceWriter)
        .faultTolerant()
        .retry(DeadlockLoserDataAccessException.class)
        .retryLimit(3)
        .build();
```

If deadlocks persist after retries are exhausted, the exception fails the step. Uncommitted chunk transaction data rolls back per the transaction manager. Previously committed chunks remain effective.

Afterward, operators should:

1. Inspect the JobExecution/StepExecution and final exception.
2. Identify the cause of the deadlock or lock contention.
3. Verify committed chunks and any non-transactional side effects.
4. Fix the root cause, such as tuning indexes, reordering updates, or lowering concurrency.
5. Restart the same JobInstance using the exact identifying JobParameters if the job is restartable.
6. Confirm the reader/writer have checkpoints and can safely reprocess items.

Do not change identifying JobParameters just to bypass an existing `JobInstance` error when your goal is restarting. Changing identifying parameters creates a separate logical processing unit.

## 10. Recovery at the Job flow level

Beyond per-item recovery, a job can include a dedicated step to record or handle failures when the main step fails. The flow can route based on step `ExitStatus`.

Example:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step recordFailureStep,
        Step publishSuccessStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("FAILED").to(recordFailureStep)
            .from(importStep)
                .on("COMPLETED").to(publishSuccessStep)
            .from(recordFailureStep)
                .on("COMPLETED").fail()
            .from(publishSuccessStep)
                .on("*").end()
            .end()
            .build();
}
```

In this example, when `importStep` fails after retry exhaustion, the flow runs `recordFailureStep` to persist details or send alerts. After recording succeeds, the flow still ends the job in failure via `.fail()`, since data import is incomplete.

If a recovery step genuinely remedies the error and business rules allow treating the entire workflow as complete, you can design a completion transition. However, understand that routing the flow to a recovery branch does not automatically turn the failed import step into `COMPLETED`. Preserve the original error details and define the job's final status/ExitStatus explicitly.

A recovery step can fail too. In that event, preserve both the original error and the recovery error so operators know both the primary operation and remediation failed.

## 11. Recovery by restarting after fixing the root cause

Retry takes place inside a single execution. Restart means relaunching a failed or stopped JobInstance in a permitted way, creating a new `JobExecution`.

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
   |
   +-- JobExecution #1
   |      +-- importStep: FAILED (retry exhausted)
   |
   +-- JobExecution #2 (restart after remediation)
          +-- importStep: resumes from checkpoint
```

Restart fits when the root cause has been fixed, such as:

- The partner service is back online.
- The database cleared locks or queries were optimized.
- The input file was corrected and is managed as the same batch input per business rules.
- Connection configuration was fixed.

On restart, reuse the exact identifying parameters to match the same JobInstance. Also verify that input data and checkpoints remain compatible. If you replace a file at the same path with different contents, old checkpoints may no longer match.

Do not restart immediately before fixing the root cause. Doing so only repeats the same error, wastes resources, and risks duplicate side effects.

## 12. Readers, processors, and writers must be recovery-safe

After retry exhaustion, depending on skip or restart choices, an item may be re-read, reprocessed, or rewritten. Thus, recovery must consider the entire pipeline.

### Reader

- Support checkpoints if restart is needed.
- Use stable data sources across runs.
- Do not lose items when transactions roll back or when acknowledging messages.
- Maintain deterministic ordering and pagination keys.

### Processor

- Prefer deterministic logic without side effects.
- Do not generate new UUIDs or timestamps on every call if they affect identity/outcomes.
- When looking up external data, use fixed snapshots/versions if reproducible results are needed.
- Avoid mutating shared mutable state under concurrent execution.

### Writer

- Use unique keys or idempotency keys to guard against duplicate writes.
- Clearly identify which resources participate in transactions.
- Do not assume HTTP calls, emails, or message publishes roll back alongside the database.
- Provide reconciliation or outbox mechanisms for external side effects.

A deterministic processor is not enough to guarantee safe recovery if the writer still inserts duplicates or an external system receives duplicate requests.

## 13. Recovery when calling APIs or external systems

Timeout errors when calling APIs pose a tricky issue: the client does not know for certain whether the server processed the request. For instance, a partner received a payment creation request, yet the response was lost in transit. Retrying with a new request lacking a deduplication key can create two payments.

Common safeguards:

- Use an idempotency key stable across batch ID and item ID.
- Persist request/response states in the database.
- Use an outbox to write events in the same transaction as business data so a publisher delivers them under control.
- On timeout, query transaction status via business reference before resending.
- Distinguish errors guaranteed not to have been processed from ambiguous outcomes.

Example creating a stable key:

```java
String idempotencyKey = batchId + ":" + order.orderId();
partnerClient.submit(order, idempotencyKey);
```

The key must stay identical across retries and restarts of the same business request. Never generate a fresh key on every call.

## 14. Retry exhaustion in partitioning

With partitioning, each worker step can have its own retry behavior. When an item's retries run out, the worker may skip the item if policy permits or fail. The manager step then aggregates partition statuses per coordination mechanics.

```text
managerStep
  |
  +-- partition0: COMPLETED
  +-- partition1: FAILED (retry exhausted)
  +-- partition2: COMPLETED
  +-- partition3: COMPLETED
```

Already-completed partitions and committed chunks do not automatically roll back when partition1 fails. On restart, Spring Batch can re-run incomplete partitions according to metadata. Keep partition names/ranges stable and writers idempotent so side effects are not duplicated.

If partitions fail due to a shared systemic error like database unavailable, letting other partitions keep retrying can worsen load. You may need concurrency caps, backoff, and controlled shutdown rather than letting every worker retry endlessly.

## 15. Observing retries and recovery

To understand why an item entered recovery, record:

- Job name, JobExecution ID, and StepExecution ID.
- Partition name if applicable.
- Item/business key or source position.
- Exception type and final cause.
- Actual attempt count and backoff wait times.
- Final action: retry succeeded, skipped, written as rejected item, or step failed.
- Correlation ID/idempotency key for external requests.

Use `RetryListener` to observe attempts and `SkipListener` to record bypassed items. `StepExecutionListener` or `JobExecutionListener` can summarize outcomes after the step/job completes.

Do not log sensitive payloads or full stack traces on every retry attempt. Log exception type, business key, and correlation ID; store detailed diagnostic data in access-controlled locations.

## 16. Testing recovery after retry exhaustion

Tests should verify both success and failure paths:

1. First call fails, subsequent retry succeeds: item is written properly and not skipped.
2. All attempts fail, exception is skippable: item is recorded as skipped exactly once per listener semantics and step continues.
3. All attempts fail, exception is non-skippable: chunk rolls back and step ends `FAILED`.
4. `skipLimit` exceeded: step fails even though the exception is skippable.
5. Recovery callback or rejected-record writer fails: recovery error surfaces clearly without hiding the original error.
6. Restart after remediation: reader resumes from checkpoint and data is not written twice.
7. API timeout after server accepted request: idempotency key prevents duplicate side effects.

Mocks can simulate transient exceptions and assert invocation counts. For transactions/restarts, write integration tests with a real JobRepository and test database to confirm actual metadata, commits, rollbacks, and StepExecutions.

## 17. Common mistakes when handling retry exhaustion

| Issue | Common cause | Remedy |
|---|---|---|
| Retrying endlessly without recovering | Retrying unrecoverable errors or lacking suitable limits. | Retry only transient exceptions and set limits. |
| Item lost after retry exhaustion | No skip/rejected-record path and errors handled improperly. | Let step fail or persist items to quarantine per business rules. |
| Job COMPLETED while database is down | Infrastructure exceptions included in overly broad skip config. | Narrow skippable exceptions; systemic outages should fail the step. |
| Duplicate error records after retry | Listener/recovery has non-idempotent side effects. | Use deduplication keys and proper transactions/outbox. |
| Recovery callback returns dummy data | Attempting to mask errors with invalid default values. | Return fallbacks only when explicitly defined by business rules; otherwise throw exceptions. |
| Restart creates a new JobInstance | Identifying JobParameters changed. | Reuse exact identifying parameters on restart. |
| Restart reads wrong data | Source file or dataset mutated. | Keep inputs immutable; use batch IDs/versions/snapshots. |
| Concurrent workers retrying cause overload | Lacking backoff/jitter or excessive concurrency. | Bound workers, increase backoff, and control downstream load. |
| RetryTemplate and step retry overlap | Two retry layers running together without accounting for total attempts. | Pick one primary retry layer or compute total calls explicitly. |

## 18. Operational workflow when retries are exhausted

When a step fails after retry exhaustion, operators can follow this sequence:

1. **Locate execution:** find the relevant JobExecution, StepExecution, and partition.
2. **Read final error:** check exception, cause chain, attempt counts, and timestamp.
3. **Classify error:** transient, data error, configuration error, or systemic error.
4. **Inspect transactions:** identify committed chunks, rolled-back chunks, and external side effects that may have happened.
5. **Inspect recovery path:** was the item skipped, stored as rejected, or did the step fail completely?
6. **Fix root cause:** fix data, restore services, tune queries, or release locks.
7. **Choose continuation path:** reprocess rejected items separately, restart the same JobInstance, or start a new batch per business rules.
8. **Check idempotency:** ensure database writes and API calls do not produce duplicate results.
9. **Monitor next execution:** confirm status, counters, output data, and error lists.
10. **Keep audit trail:** retain initial error history alongside recovery outcomes for reconciliation.

Do not bump `retryLimit` or `skipLimit` merely to push a job through. If the root cause remains unresolved, raising limits usually prolongs failure time and undermines output data reliability.

## 19. Key takeaways

- Retry exhaustion occurs when an operation still fails after all permitted attempts.
- After retry exhaustion, Spring Batch applies the skip policy; the item may be skipped if allowed and within budget, otherwise the step fails.
- Retry policy decides whether to try again; skip policy decides whether to discard an item after failure.
- Skip only item-level errors that business rules permit discarding with proper recording/reconciliation.
- Use `SkipListener` to persist details of skipped items; `StepExecution` counters provide only aggregate counts.
- Dead-letter/rejected stores are application-designed mechanisms, not automatically created by configuring retry.
- `RetryListener` aids retry observation; Spring Retry's `RecoveryCallback` can define fallback actions once a retry policy exhausts attempts.
- For unskippable errors, failing the step and restarting after fixing the cause is a valid recovery path.
- Restart uses the same identifying JobParameters to resume the same JobInstance; avoid introducing unintended new IDs.
- Readers need checkpoints, processors need determinism, and writers need idempotency for safe recovery.
- External API calls need stable idempotency keys, outboxes, or status reconciliation when timeouts yield ambiguous outcomes.
- In partitioning, each worker maintains its own state; committed partitions do not roll back automatically when another partition fails.
- Backoff and concurrency limits help prevent retry storms when downstream systems are overloaded.

Recovery after retry exhaustion is a decision about data correctness, not merely a way to keep a job running. Clearly define which errors are retried, which can be skipped, when items must be quarantined, and when to halt and restart after remediation. When these branches are designed together with checkpoints, transactions, and idempotency, Spring Batch can recover in a controlled manner while preserving traceability and reconciliation.
