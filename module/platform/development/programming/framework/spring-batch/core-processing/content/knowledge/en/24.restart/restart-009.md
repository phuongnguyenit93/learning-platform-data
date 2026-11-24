# Step startLimit

In Spring Batch, `startLimit` restricts how many times a Step is allowed to start within the same JobInstance. Each time the Step is launched, a new `StepExecution` is created. Once the start count reaches the limit, subsequent attempts to run the Step are rejected and Spring Batch throws `StartLimitExceededException`.

`startLimit` is useful for Steps with costly side effects or operations that should not run too many times, such as calling an external system, generating a handoff file, running a reconciliation procedure, or executing an operation allowed only a limited number of attempts. It is a Step-execution-level limit; it does not replace an item retry policy, nor is it a system-wide limit on Job launches.

## 1. What is startLimit?

A Job can be restarted after failing. In each JobExecution, a Step may be started again depending on its previous status and the restart policy. `startLimit(n)` sets the maximum number of times a Step is permitted to start for a single JobInstance.

Example configuration:

```java
return new StepBuilder("reconcileStep", jobRepository)
        .tasklet(reconcileTasklet, transactionManager)
        .startLimit(3)
        .build();
```

With `startLimit(3)`, the Step can start at most three times within that JobInstance. If the Step fails all three times and an operator keeps restarting the Job, the fourth start attempt is rejected.

The default `startLimit` is `Integer.MAX_VALUE`, meaning a very large limit if not explicitly configured. Omitting `startLimit` does not mean a Step cannot restart; the Job still applies its default restart mechanism and can resume after errors if other conditions allow.

## 2. How is startLimit counted?

Spring Batch tracks Step executions through `StepExecution` records persisted in `JobRepository`. When a Step starts, a corresponding StepExecution is created and metadata is saved. The start counter is evaluated within the scope of that JobInstance and Step.

Suppose `startLimit(2)` is configured:

```text
JobInstance: dailyReconciliation / businessDate=2026-11-15
  |
  +--> JobExecution #1
  |       reconcileStep starts: attempt 1
  |       reconcileStep = FAILED
  |
  +--> JobExecution #2 (restart same JobInstance)
  |       reconcileStep starts: attempt 2
  |       reconcileStep = FAILED
  |
  +--> JobExecution #3 (restart same JobInstance)
          reconcileStep is not started
          StartLimitExceededException
```

Key points:

- The limit includes the very first start, not extra restarts added after the first run.
- Failed or stopped start attempts still consume the limit.
- Restarting the same JobInstance continues using the Step's historical counter.
- A new JobInstance with different identifying JobParameters has its own execution history and its own Step counter.
- `startLimit` does not count items, chunks, or per-item retries.

Thus, `startLimit(1)` means the Step can only start once within a JobInstance. If the first attempt fails, that Step cannot be restarted again within the same instance.

## 3. Configuring startLimit for a Tasklet Step

In Spring Batch 5 and later, you can set `startLimit()` directly on the Step builder:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step externalReconciliationStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet reconciliationTasklet) {

    return new StepBuilder("externalReconciliationStep", jobRepository)
            .tasklet(reconciliationTasklet, transactionManager)
            .startLimit(3)
            .build();
}
```

In this example, the Tasklet may call an external reconciliation system. A limit of three prevents the same Step from being started indefinitely when the JobInstance is repeatedly restarted.

If the Tasklet performs an operation that might have completed before the application stopped, an idempotency key or status-check mechanism is needed. `startLimit` only caps start attempts; it does not determine whether the external operation succeeded.

## 4. Configuring startLimit for a chunk-oriented Step

`startLimit` also applies to chunk Steps. It limits how many times the Step is launched, not the number of chunks within each run:

```java
import org.springframework.batch.core.Step;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.item.ItemProcessor;
import org.springframework.batch.item.ItemReader;
import org.springframework.batch.item.ItemWriter;
import org.springframework.context.annotation.Bean;
import org.springframework.transaction.PlatformTransactionManager;

@Bean
public Step importOrdersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemProcessor<Order, ProcessedOrder> processor,
        ItemWriter<ProcessedOrder> writer) {

    return new StepBuilder("importOrdersStep", jobRepository)
            .<Order, ProcessedOrder>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .startLimit(2)
            .build();
}
```

The Step above can process many chunks per start. If processing 100,000 items with a commit interval of 500, the Step can commit 200 chunks in a single start. `startLimit(2)` does not limit the chunk count to 2; it limits the Step to starting at most twice within the JobInstance.

## 5. What happens when the limit is exceeded?

When a Step has reached its maximum number of starts, Spring Batch does not execute the Step again and throws `StartLimitExceededException`. This error is recorded during Job execution; the Job typically finishes as `FAILED` unless the flow explicitly handles the error outcome.

Example configuring a single attempt:

```java
return new JobBuilder("oneAttemptJob", jobRepository)
        .start(externalCallStep)
        .build();
```

Step:

```java
return new StepBuilder("externalCallStep", jobRepository)
        .tasklet(externalCallTasklet, transactionManager)
        .startLimit(1)
        .build();
```

If the first run of `externalCallStep` fails, restarting the Job with the same identifying parameters will not be able to start the Step again. The subsequent run may fail with `StartLimitExceededException` before the Tasklet is invoked.

Do not confuse `StartLimitExceededException` with item exceptions thrown by Reader, Processor, or Writer. This is a policy error at the Step-start level. Item retries cannot raise the Step limit or clear StepExecution history.

## 6. Distinguishing startLimit from retryLimit and skipLimit

These three limits operate at different levels:

| Configuration | Scope | What does it count? | When limit is exceeded |
|---|---|---|---|
| `startLimit(n)` | Step within a JobInstance | Number of times the Step is started | Step cannot start again; throws `StartLimitExceededException`. |
| `retryLimit(n)` | Fault-tolerant chunk processing | Number of retry attempts for an operation/item per retry policy | Exception is passed to skip policy if applicable; otherwise the Step fails. |
| `skipLimit(n)` | Step execution | Total failing items allowed to be skipped during read/process/write | Step fails when the next skip exceeds the limit. |

For example, a Step might have:

```java
return new StepBuilder("importStep", jobRepository)
        .<Order, ProcessedOrder>chunk(100, transactionManager)
        .reader(reader)
        .processor(processor)
        .writer(writer)
        .faultTolerant()
        .retry(TransientDataAccessException.class)
        .retryLimit(3)
        .skip(InvalidOrderException.class)
        .skipLimit(20)
        .startLimit(4)
        .build();
```

In this configuration:

- Each eligible item or operation can be retried according to the retry limit.
- Items with skippable business errors can be skipped, up to 20 skips.
- The entire Step can be started at most four times within the same JobInstance.

Retry and skip handle errors inside a single Step run. `startLimit` controls whether the Step is permitted to start a new execution at all.

## 7. Distinguishing startLimit from a Job run limit

`startLimit` does not cap how many times a Job is launched system-wide. It applies to a specific Step inside a single JobInstance.

For example:

- JobInstance A has `businessDate=2026-11-15`; the Step can start at most three times.
- JobInstance B has `businessDate=2026-11-16`; this is a different instance and has its own Step counter.
- If the scheduler launches the same JobParameters of instance A again, Spring Batch treats it as restarting/launching the same instance and applies instance A's `startLimit` history.
- If a new identifying parameter is added, a new JobInstance may be created and the Step gets a fresh start history.

If the requirement is to restrict a Step to running at most three times per day across all JobInstances, `startLimit` is not enough. You need a business counter or coordination table keyed by Step and date, with appropriate transactions/unique constraints.

Do not add a timestamp to identifying JobParameters just to bypass `startLimit`. That creates a new JobInstance and may reprocess business data instead of handling the limited run properly.

## 8. Relationship between startLimit and allowStartIfComplete

By default, when a Job restarts, Steps that are already `COMPLETED` are usually skipped. `allowStartIfComplete(true)` tells Spring Batch to run that Step again even if it completed in a prior JobExecution.

The two configurations have distinct roles:

- `startLimit(n)` caps the total number of times a Step can start.
- `allowStartIfComplete(true)` permits an already-completed Step to start again when the Job restarts.

For example:

```java
return new StepBuilder("refreshReferenceStep", jobRepository)
        .tasklet(refreshReferenceTasklet, transactionManager)
        .allowStartIfComplete(true)
        .startLimit(3)
        .build();
```

Suppose the Step completed on the first run, but a subsequent Step failed. On Job restart:

1. With `allowStartIfComplete(false)` (default), the completed Step is normally skipped and does not consume another start.
2. With `allowStartIfComplete(true)`, the Step runs again and that start counts toward the limit.
3. Once the Step has reached `startLimit`, it will not run again even with `allowStartIfComplete(true)`.

Therefore, both attributes must be considered together. Do not enable `allowStartIfComplete(true)` for a Step with non-idempotent side effects just to ensure it always re-runs.

## 9. startLimit and Job restarting

For a Step to restart, the Job must permit restarting. By default, a Job is restartable unless configured with `preventRestart()`. If a Job is configured as non-restartable, restarting is blocked at the Job level before Step `startLimit` policies come into play as expected.

```java
return new JobBuilder("dailyJob", jobRepository)
        .start(importStep)
        .next(reconcileStep)
        .build();
```

The Job does not call `.preventRestart()`, so it remains restartable based on status and metadata. Each Step can configure a different `startLimit`:

```java
importStep:      startLimit(5)
reconcileStep:   startLimit(2)
publishStep:     startLimit(1)
```

This is useful when Steps have different costs or side effects. An import Step may need multiple recovery attempts; a publish Step may only be allowed to start once because notifications or data handoffs require strict control.

If the Job is already `COMPLETED`, relaunching with the same identifying parameters is normally rejected because the JobInstance is finished. `startLimit` does not allow re-running a completed JobInstance. To reprocess business data, a new JobInstance with an identifying parameter expressing an intentional reprocess request is needed.

## 10. Practical scenario: Step calling an external system

Suppose a Step calls a payment reconciliation service. Each call may create a processing request at the external system. To limit Step starts within the same JobInstance, configure:

```java
return new StepBuilder("paymentReconciliationStep", jobRepository)
        .tasklet(paymentReconciliationTasklet, transactionManager)
        .startLimit(2)
        .build();
```

With a limit of two, the Step can start at most twice within the same JobInstance. However, if the first API call succeeded and the application crashed before Spring Batch recorded Step completion, a restart may call the API again. `startLimit(2)` only permits at most two starts; it does not know whether the first call succeeded on the external system.

To stay safe, send a stable idempotency key, such as `reconcile:<businessDate>:<accountGroup>`, on every call. The receiving system must store the key and return the previous result if the key was already processed. That way, a repeated call does not create a second reconciliation request.

If the external system does not support idempotency keys, store request IDs and statuses in a database/outbox, then query the outcome before resending. Distinguish a timeout (missing response) from a definitive failure; a timeout does not prove the external system did not execute the action.

## 11. Practical scenario: Step completed, but Job failed at a later Step

Suppose a Job has two Steps:

```text
dailyImportJob
   |
   v
importStep (startLimit=3)
   |
   v
publishStep (startLimit=1)
```

`importStep` completes, but `publishStep` fails. When restarting the Job:

- By default, the completed `importStep` is skipped.
- `publishStep` can be started again if still within its limit.
- If `importStep` has `allowStartIfComplete(true)`, it will run again and consume one more start.
- If `publishStep` has `startLimit(1)` and already started once and failed, a restart cannot start this Step again.

This is why limits should be set according to each Step's risk and recoverability, rather than copying a single `startLimit` value across every Step.

## 12. Tracking how many times a Step has started

`JobRepository` stores the `StepExecution` records belonging to each JobInstance. You can use `JobExplorer` to look up the JobInstance and its JobExecutions, then inspect StepExecutions by Step name to view history.

Conceptual example:

```java
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.batch.core.JobInstance;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.StepExecution;

public long countStepExecutions(
        JobExplorer jobExplorer,
        JobInstance jobInstance,
        String stepName) {

    long count = 0;
    for (JobExecution jobExecution :
            jobExplorer.getJobExecutions(jobInstance)) {
        count += jobExecution.getStepExecutions().stream()
                .filter(step -> step.getStepName().equals(stepName))
                .count();
    }
    return count;
}
```

This example illustrates aggregating a JobInstance's StepExecution history. When checking start counts in a real application, use the exact `JobExplorer` API of your Spring Batch version and account for all relevant historical executions. Do not manually edit `BATCH_STEP_EXECUTION` tables to reset counters.

Useful details to log or monitor:

- JobInstance ID and identifying JobParameters.
- Current JobExecution ID.
- Step name and StepExecution ID.
- Status, start/end times, and exceptions.
- Configured start limit for the Step.
- Count of historical StepExecutions for the Step in the JobInstance.

If you need to report limits across multiple JobInstances, record separate business metrics since `startLimit` applies per JobInstance.

## 13. Testing startLimit

Use integration tests with a persistent JobRepository in the test context to verify Spring Batch genuinely blocks starts exceeding the limit. Unit tests calling a Tasklet directly will not verify StepExecution counters and restart metadata.

A test scenario for `startLimit(2)`:

1. Create JobParameters with a fixed identifying key, e.g., `businessDate=2026-11-15`.
2. Launch the Job the first time; fail the Tasklet in a controlled way and verify the Step started for the first time.
3. Restart the same JobInstance with the same identifying parameters; fail the Tasklet again and verify the Step started for the second time.
4. Restart a third time with the same JobInstance.
5. Verify the Step is not invoked again, the new JobExecution fails, and failure exceptions contain `StartLimitExceededException`.

You can use `JobLauncherTestUtils` to launch the Job and `JobExplorer` to inspect history. Use a controllable stub service to trigger two failures without changing identifying JobParameters between restarts.

Example assertion on exception type after retrieving the corresponding JobExecution:

```java
assertTrue(jobExecution.getAllFailureExceptions().stream()
        .anyMatch(StartLimitExceededException.class::isInstance));
```

Depending on the launcher and how the test runs the Job, JobExecution may be returned with `FAILED` status rather than throwing the exception directly to the test caller. Inspect metadata via JobRepository/JobExplorer to confirm the error and the actual number of Tasklet invocations.

### Testing allowStartIfComplete

Another test should verify whether a completed Step re-runs:

- Configure Step A to complete and Step B to fail.
- Restart the same JobInstance.
- With Step A using defaults, verify A's Tasklet/Writer is not invoked again.
- With `allowStartIfComplete(true)`, verify A is invoked again if `startLimit` has not been reached.
- Once the start count reaches `startLimit`, verify A is not invoked further.

## 14. Choosing startLimit values

Do not set the same limit for every Step. The right value depends on the Step's recoverability and side effects:

| Step type | Considerations |
|---|---|
| File reading/importing with good checkpoints | Can allow multiple restarts; set a limit sufficient for operations. |
| Pure computation, no side effects | Can use a high or default limit if re-execution cost is acceptable. |
| External API calls with idempotency keys | Can allow several restarts, alongside request-level retry/backoff. |
| Sending files or messages without deduplication | Lower limit plus handoff status/idempotency before allowing re-runs. |
| Business task permitted to execute only once | May set `startLimit(1)`, but requires a manual handling procedure if the first attempt fails. |

A low limit prevents infinite loops, yet can also prevent a Job from self-recovering after transient infrastructure glitches. Treat `startLimit` as an operational guardrail, not a substitute for retries, timeouts, idempotency, or fixing root causes.

## 15. Common pitfalls

| Pitfall | Consequence | Resolution |
|---|---|---|
| Assuming `startLimit(3)` permits three restarts after the first run | Actually the limit includes the first start attempt. | Count total Step starts, including the initial run and all restarts. |
| Using `startLimit` to cap per-item retries | Does not control retry counts inside a chunk. | Use `retryLimit()` for retry policies. |
| Changing identifying JobParameters to bypass the limit | Creates a new JobInstance and can reprocess data. | Keep the same parameters on restart; create a new instance only for an explicit reprocess request. |
| Assuming `startLimit` knows whether an external API succeeded | Side effects may have happened before the Step recorded completion. | Use idempotency keys or persistent request state. |
| Enabling `allowStartIfComplete` without considering `startLimit` | Completed Steps may re-run until hitting the limit. | Evaluate both settings together and test restarts. |
| Treating `startLimit` as a system-wide limit | Each JobInstance maintains its own Step history. | Use a coordination table/unique constraint for global or daily limits. |
| Setting `startLimit` too low | Transient errors can block the Job from restarting. | Choose values based on SLA, operations, and recoverability. |
| Manually editing `BATCH_*` tables to reset limits | Metadata can lose consistency and break restarts. | Use Spring Batch APIs and controlled operational procedures. |

## Conclusion

`startLimit` caps how many times a Step is allowed to start within the same JobInstance. The limit counts both the initial run and subsequent restarts; once exceeded, Spring Batch refuses to start the Step and throws `StartLimitExceededException`. It differs from `retryLimit` and `skipLimit`: those two handle item errors inside a Step, whereas `startLimit` controls how many StepExecutions may be launched. Weigh `allowStartIfComplete(true)`, Job restart policies, side-effect idempotency, and operational procedures when the limit is exhausted. Test with multiple launches/restarts using the same identifying JobParameters and verify the Step does not execute beyond its configured limit.
