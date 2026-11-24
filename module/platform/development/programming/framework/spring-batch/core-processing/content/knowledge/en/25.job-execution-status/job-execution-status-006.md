# Status During Retry Recovery

In Spring Batch, an operation can be retried when encountering a transient error. If a retry succeeds, the step continues processing normally. If retries are exhausted and the error persists, the framework must follow the configured recovery branch: skip the item if the skip policy allows, or fail the step. When monitoring a job, you need to understand where and when status is reflected.

A common point of confusion is that Spring Batch has no standard `BatchStatus` named `RETRYING` or `RETRY_EXHAUSTED`. Retry attempts normally occur inside a running step execution. The final status of a step/job is only determined when processing ends or is stopped. To observe individual retry attempts, the application must add appropriate logging, listeners, or metrics.

## 1. Two Types of Status to Distinguish

Spring Batch uses two main concepts to represent execution outcomes:

- `BatchStatus`: the lifecycle state of `JobExecution` or `StepExecution`, indicating whether the execution is initializing, running, completed, failed, or stopped.
- `ExitStatus`: an outcome code used to describe how a step/job ended and to drive flow control. Beyond default codes, applications can create custom codes such as `COMPLETED_WITH_WARNINGS`.

These two values are related but not synonymous. For instance, a step can end with `BatchStatus.COMPLETED` and `ExitStatus` `COMPLETED_WITH_WARNINGS` when the job finishes processing but some items were skipped according to policy.

| Concept | Answers the question |
|---|---|
| `BatchStatus` | What lifecycle state is the execution currently in? |
| `ExitStatus` | What outcome code did the step/job finish with and which branch should the flow take? |

When monitoring retry recovery, inspect both. Looking only at `BatchStatus` can miss business information about warnings or excluded data.

## 2. Common BatchStatus Values

`BatchStatus` is a Spring Batch enum. Common values include:

| BatchStatus | General Meaning |
|---|---|
| `STARTING` | Execution is being initialized. |
| `STARTED` | Job or step is currently executing. |
| `STOPPING` | A stop request was received and the execution is entering the stopping process. |
| `STOPPED` | Execution stopped following a controlled stop request. |
| `COMPLETED` | Execution completed successfully at the framework level. |
| `FAILED` | Execution failed due to an unhandled error. |
| `ABANDONED` | Execution/step has been marked abandoned and will not continue via normal restart. |
| `UNKNOWN` | Framework cannot determine the final status with certainty. |

There is no `RETRYING` state in this list. When a writer encounters a deadlock and Spring Batch is retrying, `StepExecution` typically remains in `STARTED`; its parent `JobExecution` also typically remains `STARTED`. If the retry succeeds, the step can end `COMPLETED`. If the error escapes the step, the step ends `FAILED` and the job usually ends `FAILED` as well.

## 3. A Retry Attempt Is Not a New JobExecution

Retries in a fault-tolerant step normally take place inside the same step execution. For example, a writer hits a deadlock three times and succeeds on the next attempt. Those writer invocations do not create three new `JobExecution` or three new `StepExecution` records.

```text
JobExecution #501: STARTED
  |
  +-- StepExecution #802: STARTED
          |
          +-- writer attempt 1 -> deadlock
          +-- writer attempt 2 -> deadlock
          +-- writer attempt 3 -> success
          |
          +-- chunk commit
          |
          +-- StepExecution #802: COMPLETED
  |
  +-- JobExecution #501: COMPLETED
```

In this example, the framework tracks execution status at the job/step level; attempts are activities inside the step. `StepExecution` does not provide a dedicated standard counter named `retryCount` to store total retry attempts. If a dashboard needs attempt counts, the application must record them using its own observability mechanism.

## 4. Status When Retry Succeeds

Suppose a step writes data and encounters a transient error. The step is configured with retry for that exception type. If a subsequent attempt succeeds, the operation proceeds like a normal run.

```text
StepExecution: STARTED
      |
      v
Writer attempt 1 -> TransientDataAccessException
      |
      v
Retry
      |
      v
Writer attempt 2 -> success
      |
      v
Chunk commit
      |
      v
StepExecution: COMPLETED
```

Successful retries do not increment skip counts. Counters such as `readCount`, `writeCount`, and `commitCount` reflect processing/commit activity according to step semantics; they do not replace retry attempt metrics.

If the entire step finishes, the step's `BatchStatus` is `COMPLETED`. The job can continue to the next step and ultimately end `COMPLETED`, depending on the flow.

## 5. Status When Retries Are Exhausted and the Item Is Skipped

In Spring Batch, retry policy and skip policy are two independent decisions. An exception can be retried first; if retries are exhausted and the exception is also covered by the skip policy, the framework can skip the item as long as `skipLimit` has not been exceeded.

Example configuration:

```java
return new StepBuilder("publishOrdersStep", jobRepository)
        .<Order, PartnerRequest>chunk(50, transactionManager)
        .reader(orderReader)
        .processor(requestProcessor)
        .writer(partnerWriter)
        .faultTolerant()
        .retry(ResourceAccessException.class)
        .retryLimit(3)
        .skip(ResourceAccessException.class)
        .skipLimit(25)
        .listener(partnerSkipListener)
        .build();
```

Here, timeouts are retried within the limit. If they still fail, the skip policy can allow skipping the item. If the step goes on to complete and total skips do not exceed the limit, `StepExecution` can still finish `COMPLETED` while `skipCount` increases.

This does not mean the item was processed successfully. It means the step completed under the configured fault-tolerance policy. You must check skip counters and the list of failed items to evaluate the business outcome.

## 6. Status When Retries Are Exhausted and Not Skipped

If the exception is not covered by the skip policy, or the skip limit has been exceeded, the exception is not converted into a valid skip. It escapes chunk processing and the step fails.

```text
JobExecution: STARTED
  |
  +-- StepExecution: STARTED
          |
          +-- writer attempt 1 -> deadlock
          +-- writer attempt 2 -> deadlock
          +-- writer attempt 3 -> deadlock
          |
          +-- retry exhausted
          +-- non-skippable exception
          +-- chunk rollback
          +-- StepExecution: FAILED
  |
  +-- JobExecution: FAILED
```

In this situation, the step's `BatchStatus` is `FAILED`; the job usually also becomes `FAILED` unless the flow handles failures differently. The current transaction is rolled back by the transaction manager. Previously committed chunks remain intact.

There is no separate `RETRY_EXHAUSTED` status. To know retries were exhausted, inspect the final exception, attempt logs/metrics, and the step's final status.

## 7. Recovery Callback and Skip Policy Are Not the Same Thing

In the Spring ecosystem, the word “recovery” can refer to different mechanisms. Distinguish them:

- In a Spring Batch fault-tolerant step, the post-retry branch can go through the skip policy. If the exception is not skipped, the step fails.
- In Spring Retry, `RetryTemplate` can accept a `RecoveryCallback` to execute an alternative action when the retry policy exhausts attempts.
- `RetryListener` is used to observe the retry lifecycle; it does not automatically replace business recovery logic.

Example using Spring Retry directly:

```java
RetryTemplate retryTemplate = RetryTemplate.builder()
        .maxAttempts(3)
        .fixedBackoff(1000)
        .retryOn(TransientDataAccessException.class)
        .build();

PartnerResult result = retryTemplate.execute(
        context -> partnerClient.submit(request),
        context -> recoveryService.markPending(
                request,
                context.getLastThrowable()));
```

In this example, the recovery callback runs when `RetryTemplate` has exhausted attempts per policy. The callback returns an alternative result under the application contract. If the callback cannot produce a valid result, it should throw an exception so the caller recognizes the failure.

This is a standalone Spring Retry API. Do not confuse this callback with Spring Batch's skip policy or assume a fault-tolerant step automatically invokes an arbitrary callback after retry exhaustion.

## 8. Backoff Configuration Affects Time Spent in STARTED

Backoff introduces a wait interval between attempts. During the wait, the step is still executing; the status does not switch to a separate retry enum.

Example:

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

If a dashboard only reads `BatchStatus`, during backoff it will display `STARTED` even though the worker is waiting before the next attempt. Therefore, when detailed visibility is needed, add metrics such as attempt number, wait duration, last exception, and last retry timestamp.

## 9. Retry Has No Standard Counter in StepExecution

`StepExecution` has several standard counters such as:

- `readCount`
- `writeCount`
- `filterCount`
- `readSkipCount`
- `processSkipCount`
- `writeSkipCount`
- `skipCount`
- `commitCount`
- `rollbackCount`

These counters are not retry counts. An item can be retried multiple times and then succeed while `skipCount` remains 0. Conversely, an item can be skipped immediately without undergoing retry.

To track retries, record metrics or logs where retries occur. Depending on the API/version in use, Spring Retry provides `RetryListener`; Spring Batch also has corresponding listeners and callbacks in fault-tolerant processing. Verify your exact library version to register listeners with the matching signature.

Record at minimum:

- Job name, JobExecution ID, and StepExecution ID.
- Step name and partition name if applicable.
- Exception type and cause.
- Attempt number or total attempts.
- Start and end times of each attempt.
- Final outcome: success, skip, or step failed.
- Business key or correlation ID of the item.

## 10. Tracking Retries with RetryListener

Spring Retry's `RetryListener` lets you observe events in the retry lifecycle. A listener can be used to log or emit metrics when an attempt fails.

Conceptual example:

```java
public class RetryMetricsListener implements RetryListener {

    @Override
    public <T, E extends Throwable> void onError(
            RetryContext context,
            RetryCallback<T, E> callback,
            Throwable throwable) {

        // Increment retry failure metric and record exception type.
        retryMetrics.recordFailure(throwable.getClass().getSimpleName());
    }
}
```

Listener signatures vary across Spring Retry versions. The snippet illustrates the API for versions with matching callbacks; verify against your actual dependencies before copying into a project.

Listeners should focus on observation and avoid performing non-idempotent business operations. If a listener sends a notification on every retry, a prolonged outage can trigger an alert flood. Use aggregated metrics or alert only when thresholds are exceeded.

## 11. Tracking Recovered Items with SkipListener

If Spring Batch's recovery branch is skipping, `SkipListener` provides separate callbacks for read, process, and write.

```java
public class OrderSkipListener implements SkipListener<OrderInput, Order> {

    @Override
    public void onSkipInRead(Throwable throwable) {
        // Reader failed before producing an item.
    }

    @Override
    public void onSkipInProcess(OrderInput item, Throwable throwable) {
        // Record business key and failure cause.
    }

    @Override
    public void onSkipInWrite(Order item, Throwable throwable) {
        // Record business key of the output item that could not be written.
    }
}
```

After an item is skipped, the corresponding counters in `StepExecution` are updated. `SkipListener` captures item and exception details; counters aggregate totals.

If the listener writes to the database in the same transaction, ensure the write aligns with the chunk transaction. If sending messages or calling external APIs, database rollback cannot undo those side effects; use an outbox or idempotency key when necessary.

## 12. StepExecutionListener Reading Final Status

`StepExecutionListener.afterStep` can read status and counters after the step finishes. It is an appropriate place to log a summary or set a custom `ExitStatus` reflecting business outcomes.

```java
public class RetryRecoverySummaryListener implements StepExecutionListener {

    @Override
    public ExitStatus afterStep(StepExecution stepExecution) {
        log.info(
                "Step {}: batchStatus={}, exitStatus={}, " +
                "skipCount={}, rollbackCount={}",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getExitStatus().getExitCode(),
                stepExecution.getSkipCount(),
                stepExecution.getRollbackCount());

        if (stepExecution.getStatus() == BatchStatus.COMPLETED
                && stepExecution.getSkipCount() > 0) {
            return new ExitStatus("COMPLETED_WITH_WARNINGS");
        }

        return null;
    }
}
```

The listener returns `null` if no ExitStatus change is needed. If skips occurred and the step is still `COMPLETED`, for instance set exit code `COMPLETED_WITH_WARNINGS` so flows or dashboards distinguish outcomes with warnings.

Changing `ExitStatus` does not turn `BatchStatus.COMPLETED` into `FAILED`. The two statuses serve different purposes. If business rules require the job to fail when skips occur, design explicit flow/exit behavior and ensure final status reflects the requirement.

## 13. JobExecutionListener Reading Job Results

`JobExecutionListener.afterJob` is called when the job ends. It is suited for recording final status, duration, and summarizing step executions.

```java
public class JobStatusListener implements JobExecutionListener {

    @Override
    public void afterJob(JobExecution jobExecution) {
        log.info(
                "Job {} execution {} finished: status={}, exit={}",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());

        for (StepExecution step : jobExecution.getStepExecutions()) {
            log.info(
                    "Step {} status={} skips={} rollbacks={}",
                    step.getStepName(),
                    step.getStatus(),
                    step.getSkipCount(),
                    step.getRollbackCount());
        }
    }
}
```

The job listener does not observe individual retry attempts. It is only suited for summarizing outcomes after the job finishes. To know how many times a step retried before completing, you need metrics/logs at the retry boundary.

## 14. Status Across Different Recovery Scenarios

The table below summarizes typical step/job-level outcomes:

| Scenario | Step BatchStatus | Typical Job BatchStatus | Notes |
|---|---|---|---|
| Retry succeeds and all work completes | `COMPLETED` | `COMPLETED` | Retry attempts do not increment skip count. |
| Retries exhausted, item skipped, and step completes | `COMPLETED` | `COMPLETED` | Skip counter increases; ExitStatus can be customized. |
| Retries exhausted, non-skippable exception | `FAILED` | `FAILED` | Current chunk rolls back per transaction manager. |
| Retries exhausted, skip limit exceeded | `FAILED` | `FAILED` | Skip limit is the overall limit for the step. |
| Stop requested while step is running | May transition to stopped status | May transition to stopped status | Outcome depends on timing and how the step handles stopping. |
| Custom recovery callback returns valid fallback and caller completes | Depends on step | Depends on job | Callback does not dictate BatchStatus; returned result is handled by caller. |

These are generalized outcomes. Flow transitions, listeners, exception handlers, and application configuration can cause `ExitStatus` or final status to differ from simple examples.

## 15. Custom ExitStatus for Recovery Outcomes

A step may complete technically yet need to indicate that items were recovered via skipping. Custom ExitStatus can be used to route the flow.

Example:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step importStep,
        Step warningReportStep,
        Step successReportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(importStep)
                .on("COMPLETED_WITH_WARNINGS").to(warningReportStep)
            .from(importStep)
                .on("COMPLETED").to(successReportStep)
            .from(warningReportStep)
                .on("*").end()
            .from(successReportStep)
                .on("*").end()
            .end()
            .build();
}
```

A listener on `importStep` can set `COMPLETED_WITH_WARNINGS` when `skipCount` is greater than 0. The flow then runs the warning report. Declare remaining failure branches so the job does not inadvertently enter a success branch.

Do not change ExitStatus to `COMPLETED_WITH_WARNINGS` merely because retries happened. Successful retry is a normal recovery mechanism; if no items were skipped and no other warning condition applies, the step can end with `COMPLETED`.

## 16. Retry Recovery and Transaction Rollback

Retries are normally tied to chunk transactions. When the writer fails, the chunk transaction can roll back before the framework performs a retry according to policy. If a subsequent attempt succeeds, the chunk is written and committed. If retries are exhausted and the item is skipped, the framework continues under fault-tolerant semantics. If it cannot be skipped, the step fails.

```text
BEGIN chunk transaction
  read/process items
  write chunk -> transient exception
ROLLBACK (per fault-tolerance mechanism)

Retry attempt
  re-write
  +-- success -> commit
  +-- retries exhausted
          +-- skippable -> recovery/skip then continue
          +-- not skippable -> step FAILED
```

Previously committed chunks are not rolled back simply because the current chunk failed. External non-transactional side effects such as emails, HTTP requests, or published messages are also not automatically undone. Therefore, retry recovery must be designed with idempotency and reconciliation.

## 17. Status on Restart After Failed Retry Recovery

If a step ends `FAILED` after retry exhaustion, an operator can fix the root cause and restart the JobInstance. Restart creates a new JobExecution; the old execution remains in JobRepository.

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
  |
  +-- JobExecution #501: FAILED
  |      +-- importOrdersStep: FAILED
  |
  +-- JobExecution #602: COMPLETED (restart)
         +-- importOrdersStep: COMPLETED
```

When restarting:

- Reuse the same identifying JobParameters to continue the same JobInstance.
- Check whether completed steps are skipped by default or configured with `allowStartIfComplete`.
- Readers/writers must restore checkpoints from `ExecutionContext` if resuming from the exact position is required.
- Uncommitted items may be read/processed again.
- Writers and external integrations must be idempotent to prevent duplicate side effects.

Do not confuse retry attempts with restarts. Retries occur within the same step execution; restarts create a new JobExecution for the same JobInstance after the prior execution ended in a restartable state.

## 18. Querying Status and Counters with JobExplorer

`JobExplorer` is the API for reading metadata stored in JobRepository. It is suited for dashboards, monitoring APIs, or diagnostic tools.

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    log.info("Job status={}, exit={}",
            execution.getStatus(), execution.getExitStatus().getExitCode());

    for (StepExecution step : execution.getStepExecutions()) {
        log.info(
                "Step {}: status={}, readSkip={}, processSkip={}, " +
                "writeSkip={}, totalSkip={}, rollback={}",
                step.getStepName(),
                step.getStatus(),
                step.getReadSkipCount(),
                step.getProcessSkipCount(),
                step.getWriteSkipCount(),
                step.getSkipCount(),
                step.getRollbackCount());
    }
}
```

JobExplorer reads persisted status and counters. It is not a real-time event stream for individual retry attempts. If a dashboard needs to show “retrying attempt 2”, store separate observability state or pull metrics/logs from a retry listener.

While a job is running, metadata is updated according to the step/chunk and transaction lifecycle. Do not assume every internal retry is recorded as a separate metadata record.

## 19. Do Not Create a Custom Status Named RETRYING in BatchStatus

`BatchStatus` is a framework enum. An application cannot add a new enum value like `RETRYING` by declaring an `ExitStatus` or listener.

If the UI needs to show granular status, create a separate operational field/metric, for example:

```text
executionStatus = STARTED
activity        = RETRYING
attempt         = 2
lastException   = DeadlockLoserDataAccessException
nextAttemptAt   = 2026-11-15T15:35:00Z
```

In this model:

- `executionStatus` still comes from Spring Batch's BatchStatus.
- `activity` is an application-managed observability state.
- `attempt`, `lastException`, and `nextAttemptAt` are supplemental metrics/metadata.

Never overwrite BatchStatus in JobRepository with a custom string. Doing so can break framework lifecycle state and restart logic. When storing separate activity state, define its lifecycle and how it is cleared/reset once retries finish.

## 20. Common Mistakes When Monitoring Retry Recovery Status

| Issue | Common Cause | Resolution |
|---|---|---|
| Dashboard lacks `RETRYING` status | Spring Batch does not define this BatchStatus. | Display BatchStatus `STARTED` alongside a custom activity metric. |
| Step COMPLETED yet still has errors | Items were skipped within the limit. | Inspect skip counters, ExitStatus, and rejected-item store. |
| Retry succeeded yet skip count increased | Confusing retry count with skip count, or another item was skipped. | Record attempts separately and correlate by business key. |
| Retries exhausted yet step stays STARTED | Execution has not finished yet or worker is still processing/waiting for recovery. | Check logs, threads, timeouts, and final status once processing ends. |
| Step FAILED without knowing how many retries occurred | StepExecution has no standard retryCount. | Add RetryListener/logs/metrics. |
| Job COMPLETED despite unsent items | Exception was skipped or recovery returned fallback and step completed. | Define a warning ExitStatus and a pending-item handling process. |
| JobExplorer does not show individual attempts | JobExplorer reads execution metadata, not a retry event stream. | Use metrics/logs or a separate monitoring table. |
| Parent job status does not show child retry details | Retries happen inside child steps/jobs. | Monitor child executions and link to parent. |
| Restart treated as a new execution | Identifying JobParameters were changed. | Preserve identical identifying values on restart. |

## 21. Procedure for Investigating a Job with Retry Recovery

When a dashboard reports a long-running job or one that ended with warnings/failures, investigate in this order:

1. **Identify JobExecution:** obtain job name, execution ID, JobInstance, and identifying parameters.
2. **Identify StepExecution:** locate the running or failed step.
3. **Read BatchStatus and ExitStatus:** distinguish lifecycle from outcome/flow branch.
4. **Inspect retry logs/metrics:** look up attempts, exception types, backoff, and item/business key.
5. **Read skip counters:** inspect read/process/write skips and total skips.
6. **Check transactions:** identify committed chunks, rollbacks, and external non-transactional side effects.
7. **Determine recovery branch:** retry succeeded, skipped, fallback callback, or step failure.
8. **Assess business data:** inspect rejected/pending items and reconcile with external systems.
9. **Fix root cause:** resolve deadlocks, timeouts, bad data, or infrastructure errors.
10. **Restart if needed:** use exact identifying parameters and verify checkpoints/idempotency.
11. **Confirm final status:** monitor the new execution, ExitStatus, and output data.

Do not look solely at `STARTED` and conclude the job is hung. It may be actively processing, backing off between attempts, or waiting on a resource. Combine heartbeats, logs, thread dumps/metrics appropriate to operational permissions, and metadata update timestamps.

## 22. Key Takeaways

- Spring Batch has no default `BatchStatus.RETRYING` or `BatchStatus.RETRY_EXHAUSTED`.
- Retry attempts typically occur within the same `StepExecution`; no new JobExecution is created per attempt.
- While a step is retrying/backing off, BatchStatus usually remains `STARTED`.
- Successful retries can lead to a `COMPLETED` step/job without increasing skip counts.
- Exhausted retries with items skipped within limits can still result in a `COMPLETED` step/job, though skip counters increase.
- Exhausted retries with non-skippable exceptions, or exceeding skip limit, usually result in a `FAILED` step/job.
- `BatchStatus` describes lifecycle; `ExitStatus` describes outcome codes and can drive flow routing.
- `StepExecution` has no standard retry counter; observing attempts requires dedicated listeners, logs, or metrics.
- `SkipListener` records skipped items; `StepExecutionListener` and `JobExecutionListener` summarize final status.
- Spring Retry's `RecoveryCallback` differs from Spring Batch's skip policy.
- `JobExplorer` reads stored metadata but does not emit per-attempt retry events.
- Restart creates a new JobExecution for the same JobInstance; retry does not create a new execution.
- Writers and external integrations require idempotency/outbox/reconciliation so recovery does not produce duplicate side effects.

When displaying retry recovery status, use BatchStatus to represent the execution lifecycle, ExitStatus to represent the outcome, and separate metrics to track individual attempts. This separation lets dashboards accurately reflect whether a job is still running, recovered successfully, skipped items, or genuinely failed after exhausting retries.
