# allowStartIfComplete

In Spring Batch, when a Job fails and is restarted for the same JobInstance, already-completed Steps are normally skipped. This mechanism avoids re-running parts of the workflow that already succeeded. However, there are cases where a `COMPLETED` Step still needs to run again when the Job restarts, such as a Step that generates intermediate data that must be refreshed before continuing subsequent Steps.

The `allowStartIfComplete` attribute lets you configure that behavior. When set to `allowStartIfComplete(true)`, Spring Batch can re-launch the Step even if the previous execution of that Step completed, provided the JobInstance is being restarted. This attribute does not mean the Step runs multiple times inside a single JobExecution, nor does it allow restarting a JobInstance that already completed successfully.

## 1. Default behavior when restarting a Job

Spring Batch persists Job and Step states in `JobRepository`. A JobInstance is identified by the Job name together with identifying JobParameters. When a Job fails or is stopped, restarting creates a new JobExecution for the same JobInstance.

By default, if a Step already has a StepExecution in `COMPLETED` status, Spring Batch will not run that Step again during a normal restart. Incomplete or failed Steps can re-execute depending on their status, restartability, and Step configuration.

Example Job with three Steps:

```text
First run:

prepareDataStep       COMPLETED
        |
        v
importDataStep        COMPLETED
        |
        v
generateReportStep   FAILED
        |
        v
      Job FAILED

Restart same JobInstance:

prepareDataStep       skipped (already COMPLETED)
        |
        v
importDataStep        skipped (already COMPLETED)
        |
        v
generateReportStep   runs again
```

The default behavior saves time and avoids repeating side effects. If the first two Steps already created accurate and durable data, there is no need to re-run them just because the report-generation Step hit an error.

## 2. What does `allowStartIfComplete` change?

When `allowStartIfComplete(true)` is enabled on a Step, Spring Batch allows that Step to be launched again during a JobInstance restart even if the Step's previous execution was `COMPLETED`.

For example, if `prepareDataStep` needs to run again to refresh intermediate data before `generateReportStep` continues, you can enable this attribute:

```java
@Bean
Step prepareDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        PrepareDataTasklet tasklet) {

    return new StepBuilder("prepareDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

If the Job fails at a later Step and is then restarted, `prepareDataStep` can execute again instead of being skipped. Subsequent Steps proceed along the flow after this Step completes.

This attribute is configured per Step. There is no need to enable it for every Step in a Job. Enable it only on Steps where re-running after completion is an intentional and safe requirement.

## 3. `allowStartIfComplete` does not mean "always run the Step"

The attribute name can easily mislead readers into thinking the Step will always run on every Job launch. In reality, it primarily governs the decision when a JobInstance is restarted and Spring Batch detects that the Step already completed in a prior execution.

| Scenario | Typical behavior |
|---|---|
| Launch a new JobInstance | Step runs normally per flow, whether the attribute is enabled or disabled |
| Step has never run in the JobInstance | Step runs when flow reaches the Step |
| Step previously `FAILED`, Job restarted | Step can re-execute under the restart policy |
| Step previously `COMPLETED`, Job restarted, attribute `false` | Step is normally skipped |
| Step previously `COMPLETED`, Job restarted, attribute `true` | Step is allowed to run again |
| JobInstance already `COMPLETED` and relaunched with same identifying parameters | Not a valid restart; typically rejected because JobInstance is already complete |

If you want to re-run the entire workflow as a new unit of business work after a Job has completed, create a new JobInstance using appropriate identifying JobParameters. `allowStartIfComplete` does not replace the JobInstance identification mechanism.

## 4. Configuring on a chunk-oriented Step

`allowStartIfComplete` can also be used with chunk-oriented Steps. For example, a Step that refreshes a staging table before an import Step continues:

```java
@Bean
Step refreshStagingStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<SourceRecord> reader,
        ItemWriter<StagingRecord> writer) {

    return new StepBuilder("refreshStagingStep", jobRepository)
            .<SourceRecord, StagingRecord>chunk(500, transactionManager)
            .reader(reader)
            .processor(this::toStagingRecord)
            .writer(writer)
            .allowStartIfComplete(true)
            .build();
}
```

In this example, if the Step completed but a subsequent Step failed, a restart can re-run `refreshStagingStep`. Design the writer to upsert, replace data scoped by `batchId`, or delete and reload a bounded range in an appropriate transaction. If the writer only inserts without deduplication, re-running the Step can produce duplicate data.

For checkpointed readers, understand the checkpoint data and how the reader initializes when the Step re-executes. Do not assume a reader always starts from the beginning or always resumes from the old position solely from the attribute name. Test restart behavior with the exact reader, `ItemStream`, and Spring Batch version used by your application.

## 5. Configuring on a Tasklet Step

With a Tasklet, you can set the attribute after configuring the tasklet:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        RefreshReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

A Tasklet might refresh reference data or prepare an input file. When re-running, the Tasklet must scope the data to refresh accurately and avoid duplicate side effects.

For example, if the Tasklet generates `summary.csv`, write to a temporary file tied to the batch ID, finish the content, and safely replace the target file. Do not append all data onto the old file on every restart if business rules require a single file.

## 6. Difference between `allowStartIfComplete` and `startLimit`

These two attributes often appear together in Step configuration, yet they control two distinct aspects:

- `allowStartIfComplete(true)` decides whether an already-`COMPLETED` Step is allowed to run again when the JobInstance restarts.
- `startLimit(n)` limits how many times the Step is allowed to start within a JobInstance.

Example:

```java
return new StepBuilder("refreshDataStep", jobRepository)
        .tasklet(tasklet, transactionManager)
        .allowStartIfComplete(true)
        .startLimit(3)
        .build();
```

In this example, the Step is allowed to run again even after completing, but total start attempts are capped by `startLimit(3)`. When the limit is exceeded, Spring Batch can throw `StartLimitExceededException` and block further starts of the Step.

| Criterion | `allowStartIfComplete` | `startLimit` |
|---|---|---|
| Question | Should a completed Step run again on restart? | How many times at most can the Step start? |
| Configuration type | Boolean | Positive integer |
| Goal | Control skipping of `COMPLETED` Steps | Prevent excessive start attempts |
| Example | Refresh data prepared by an earlier Step | Cap an expensive Step or one with finite attempts |

`startLimit` does not by itself allow re-running a completed Step; `allowStartIfComplete` does not place a cap on execution counts. When used together, account for restart re-runs when choosing the limit.

## 7. Difference from retry

Retry handles transient errors during a single Step or chunk execution. `allowStartIfComplete` governs whether to re-execute an already-completed Step when the JobInstance is later restarted.

For example:

- Writer hits a deadlock during a chunk: use a retry policy to retry the operation per fault-tolerance configuration.
- The Job finished `refreshDataStep`, then a later report Step failed: use `allowStartIfComplete(true)` if data must be refreshed before restarting the remaining Steps.

| Criterion | Retry | `allowStartIfComplete` |
|---|---|---|
| Scope | Retrying a failing operation/item/chunk | Re-executing a completed Step within a restarted JobInstance |
| Cause | Transiently recoverable exception | Step needs to run again despite previously finishing `COMPLETED` |
| Mechanism | Retry policy, retry limit, backoff | Step-level attribute |
| Unit of re-execution | Operation or retry unit inside a Step | Entire Step per Job flow and lifecycle |

Do not enable `allowStartIfComplete` as a substitute for retrying transient database or service errors. Nor should you raise retry limits to refresh an already-completed Step.

## 8. Difference from Job `restartable`

A Job can be configured as restartable or non-restartable. That is a Job-level decision, whereas `allowStartIfComplete` is a Step-level decision.

- A restartable Job allows an unfinished JobInstance to be relaunched after a failed or stopped status per framework rules.
- A non-restartable Job forbids restarting that instance after a failure.
- `allowStartIfComplete(true)` allows a completed Step to run again inside an actively restarting JobInstance.

If the Job is not restartable, enabling `allowStartIfComplete` on a Step does not make the Job restartable. If the Job is already `COMPLETED`, this attribute does not allow relaunching the same JobInstance either.

## 9. Choosing which Steps should enable this attribute

Enable it only for Steps whose output must be regenerated or re-validated when resuming a failed Job.

Potentially suitable cases:

- Refreshing a staging table keyed by a stable `batchId` before a subsequent Step reads it.
- Recomputing derived data that can be deterministically recalculated from an immutable source.
- Re-checking an external resource before proceeding, if the check causes no side effects.
- Regenerating an intermediate file from stable source data and safely overwriting it.
- Refreshing a temporary cache or snapshot that later Steps depend on.

Cases requiring caution or usually unsuitable:

- Sending emails, SMS, or notifications that could be duplicated.
- Processing payments, creating transactions, or transferring funds.
- Calling an API that creates new resources without an idempotency key.
- Deleting shared data outside the current batch scope.
- Updating irreversible business states.
- Producing files by appending to an old file without tracking what was already written.

If a Step creates side effects that cannot be safely repeated, leave the default behavior of skipping completed Steps and design a separate verification/reconciliation workflow if needed.

## 10. Idempotency is a critical requirement

When `allowStartIfComplete` is enabled, the Step can execute again after a prior run already committed. Operations must therefore be designed to re-run without corrupting state or duplicating side effects.

An idempotent operation can be repeated with the same business identity without producing unintended changes.

For example, instead of unconditionally inserting staging data:

```sql
INSERT INTO staging_customer(batch_id, customer_id, full_name)
VALUES (:batchId, :customerId, :fullName);
```

use a unique key on `(batch_id, customer_id)` combined with upsert, or delete and reload the batch scope inside a controlled transaction. Upsert syntax depends on the database, but the goal is that re-running the same unit of work creates no duplicate records.

For external services, use a stable idempotency key:

```java
String key = "refresh-customer-summary:" + batchId;

restClient.post()
        .uri("/customer-summaries/refresh")
        .header("Idempotency-Key", key)
        .body(new RefreshRequest(batchId))
        .retrieve()
        .toBodilessEntity();
```

This example only works if the target system genuinely supports and enforces idempotency keys. Do not generate a new key on every restart when the calls represent the exact same business action.

## 11. Transactions and committed data

`allowStartIfComplete` does not open a single transaction spanning the entire Job. When a Step completes, its Tasklet or chunk transactions commit according to configuration. If a later Step fails, the committed changes of the earlier Step remain in place.

When restarting and the earlier Step is permitted to run again, it executes inside a new transaction. That new transaction does not automatically delete or roll back changes from the previous run.

For example:

```text
First run:
  refreshStagingStep -> commits staging data
  importStep         -> commits several chunks
  reportStep         -> FAILED

Restart:
  refreshStagingStep -> runs again and commits again
  importStep         -> processed per state/checkpoint
  reportStep         -> runs again
```

If the refresh Step deletes and reloads staging, ensure the import Step on restart still reads the exact snapshot and is not impacted by unexpectedly altered data. If staging is shared with other Jobs, isolate by batch ID or version so one refresh does not mutate data for another workflow.

## 12. ExecutionContext and stale data when a Step re-runs

A Step can use `StepExecutionContext` to save checkpoints or intermediate state. When a Step re-executes during a restart, do not assume every key in context is empty or every old value is still valid.

Key principles:

- Initialize or overwrite keys owned by the Step before using them.
- Namespace key names to prevent collisions.
- Do not reuse old checkpoint values if the re-run is supposed to refresh from scratch.
- Keep batch/snapshot identifying values stable to reference the exact source data.
- Test actual contexts after restart with the readers and writers in use.

For example, a Tasklet can reset preparation step state:

```java
@Override
public RepeatStatus execute(
        StepContribution contribution,
        ChunkContext chunkContext) {

    ExecutionContext context = contribution
            .getStepExecution()
            .getExecutionContext();

    context.putLong("preparedRecordCount", 0L);
    context.putString("preparationStatus", "STARTED");

    long count = preparationService.rebuildCurrentBatch();

    context.putLong("preparedRecordCount", count);
    context.putString("preparationStatus", "COMPLETED");

    return RepeatStatus.FINISHED;
}
```

This is an illustrative example. Pay attention to when Spring Batch persists ExecutionContext according to Step lifecycle and transactions. If data must be consumed by the next Step, ensure it is durably saved before the Step ends rather than existing only in memory.

## 13. Complete Job example with a re-runnable Step

Suppose a Job has three Steps: refreshing reference data, importing data, and generating a report. If importing or reporting fails, business rules require refreshing reference data before continuing.

```java
@Bean
Job customerBatchJob(
        JobRepository jobRepository,
        Step refreshReferenceDataStep,
        Step importCustomersStep,
        Step generateReportStep) {

    return new JobBuilder("customerBatchJob", jobRepository)
            .start(refreshReferenceDataStep)
            .next(importCustomersStep)
            .next(generateReportStep)
            .build();
}

@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        RefreshReferenceDataTasklet tasklet) {

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

On the first run, if refresh and import complete while reporting fails, restarting the same JobInstance allows refresh to run again. The import Step can be skipped if already `COMPLETED`, or resume from its checkpoint if it had failed previously. Reporting executes again according to its status.

This is only the right choice if refreshing does not alter data already used by the import Step in an inconsistent way. If import must resume on the exact snapshot used before failure, save the snapshot/version and recreate that exact snapshot rather than simply reading the latest data.

## 14. Testing `allowStartIfComplete`

Write integration tests proving that a completed Step runs again when the JobInstance restarts, while another completed Step retains default behavior.

A test scenario:

1. `prepareStep` increments a durable counter or writes a versioned record.
2. `processStep` completes.
3. `finalStep` intentionally fails on the first run.
4. Verify the first JobExecution is `FAILED` and `prepareStep` ran once.
5. Relaunch the Job with the same identifying JobParameters.
6. Verify `prepareStep` runs a second time because `allowStartIfComplete(true)` is enabled.
7. Verify the `COMPLETED` Step without the attribute does not run again.
8. Verify the Job completes and output data is not duplicated.

Example test skeleton:

```java
@SpringBatchTest
@SpringJUnitConfig(BatchRestartTestConfiguration.class)
class AllowStartIfCompleteTest {

    @Autowired
    JobLauncherTestUtils jobLauncherTestUtils;

    @Autowired
    PreparationAuditRepository auditRepository;

    @Test
    void rerunsCompletedStepWhenJobIsRestarted() throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("batchId", "BATCH-100", true)
                .toJobParameters();

        JobExecution first = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.FAILED, first.getStatus());
        assertEquals(1, auditRepository.countByBatchId("BATCH-100"));

        JobExecution restarted = jobLauncherTestUtils.launchJob(parameters);
        assertEquals(BatchStatus.COMPLETED, restarted.getStatus());
        assertEquals(2, auditRepository.countByBatchId("BATCH-100"));
    }
}
```

This example assumes `finalStep` fails only on the first attempt, the audit repository records each `prepareStep` run, and the test shares the same JobRepository/database across both launches. In real tests, verify the new restart StepExecution, counters, and output data. Do not use `RunIdIncrementer` or add a new identifying parameter for the restart, as that creates a different JobInstance.

## 15. Testing when `allowStartIfComplete` is not enabled

Include a control test: configure a completed Step with default settings, fail a later Step, and restart the Job. Verify the completed Step does not run again.

The control test proves that:

- `allowStartIfComplete(true)` actually alters the configured Step's behavior.
- Other Steps remain unaffected.
- Job restart still uses the same JobInstance.
- The failed Step re-runs under normal restart behavior.

Do not merely assert call counts on an in-memory mock if your goal is testing transactions and restarts. Use a repository/database test to verify persisted state across both JobExecutions.

## 16. Interaction with flow transitions

`allowStartIfComplete` does not replace flow transitions. It only permits a completed Step to re-execute on restart; the flow still decides the next Step based on `.next()` configuration or `ExitStatus` transitions.

For example, if a Job has a conditional flow:

```java
return new JobBuilder("validationJob", jobRepository)
        .start(validateStep)
            .on("COMPLETED").to(importStep)
        .from(validateStep)
            .on("FAILED").to(rejectStep)
        .end()
        .build();
```

If `validateStep` has `allowStartIfComplete(true)` and the JobInstance restarts, the Step can run again; the new `ExitStatus` produced by that execution participates in driving the flow. Ensure transitions cover the statuses the Step may return after re-running.

If a Step finishes with a custom ExitStatus, do not assume it is equivalent to `COMPLETED` in every flow. Check transition conditions and listeners that modify ExitStatus.

## 17. Impact when a Step is in a split flow or partitioning

In Jobs with multiple flow branches or partitions, understand the scope of the configured Step. Each worker StepExecution maintains its own state; allowing a completed Step to run again can cause that portion of work to re-execute on Job restart, depending on flow configuration and partitioning mechanics.

With partitioning, do not enable this attribute blindly on worker Steps. Check which partitions completed, which failed, and whether partition names and checkpoints remain stable. If a completed worker runs again, the writer must be idempotent per partition or business key.

With split flows, Steps on different branches may have committed independently. If one branch fails and the Job restarts, completed Steps on other branches are normally skipped by default. Only enable `allowStartIfComplete` if that branch needs to regenerate its output and re-running is safe.

## 18. Monitoring Step re-runs

When `allowStartIfComplete` is enabled, monitor how many times a Step starts within a JobInstance so operators understand why a previously `COMPLETED` Step gained another StepExecution.

Useful details:

- JobInstance ID and JobExecution ID.
- Step name and StepExecution ID.
- Prior and current StepExecution statuses.
- Number of times the Step started in the JobInstance.
- Configured `allowStartIfComplete` and `startLimit`.
- Business key or batch ID of the refreshed data.
- Counts of created, updated, deleted, or replaced records.
- Re-run duration and final outcome.

Logs should distinguish "Step initial run" from "Step re-executed due to Job restart." You can use `StepExecution` and `JobExecution` metadata to correlate runs without manually overwriting `BATCH_*` tables.

## 19. Common mistakes

**Assuming the attribute makes the Step run on every launch:** it governs skipping completed Steps when a JobInstance restarts; a new JobInstance already runs the Step along the flow.

**Assuming a `COMPLETED` Job can be restarted:** a completed JobInstance cannot be run again solely because of `allowStartIfComplete`; a new JobInstance is required for a new business run.

**Enabling it for every Step:** can repeat payments, send duplicate notifications, insert duplicate data, or trigger irreversible side effects.

**Confusing it with retry:** retry handles errors within one execution; `allowStartIfComplete` lets a completed Step run again on Job restart.

**Confusing it with `startLimit`:** one permits re-running a completed Step; the other caps how many times a Step can start.

**Failing to design for idempotency:** the Step may write duplicates or repeat side effects when re-executed.

**Assuming ExecutionContext is empty:** the Step may depend on previously saved state. Initialize or overwrite Step-owned keys and test readers/checkpoints.

**Failing to freeze source data:** a Step refreshing data from a changing source can produce different results from the earlier run, leaving downstream Steps inconsistent.

**Skipping real restart tests:** unit testing the attribute alone does not prove behavior with JobRepository, StepExecution, and application transactions.

## Conclusion

`allowStartIfComplete(true)` allows a `COMPLETED` Step to execute again when a JobInstance is restarted. By default, Spring Batch skips completed Steps to avoid repeating work and side effects. This attribute is helpful when a Step produces intermediate data that must be refreshed before proceeding, but should only be enabled when output is regenerable and repeating the operation is safe. It differs from retry, `startLimit`, and Job restartability; it does not allow re-running an already-completed JobInstance. Design for idempotency, control source data and ExecutionContext, track each StepExecution, and test with two launches sharing the same identifying JobParameters to verify the Step re-runs as intended.
