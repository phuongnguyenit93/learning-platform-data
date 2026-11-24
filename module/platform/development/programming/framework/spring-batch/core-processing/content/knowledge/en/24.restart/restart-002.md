# Conditions for a job to be restartable

Spring Batch allows re-running a Job that failed or was stopped in a controlled manner, but restartability depends on JobInstance identity, the last execution status, the Job's restart configuration, and metadata persisted in JobRepository. Restarting creates a new JobExecution for the same JobInstance; the framework uses persisted status and checkpoints to decide which Steps need to re-run and which components need state restoration.

A Job cannot be restarted simply because the previous run logged an error. The Job must have ended in a restartable status, have no execution currently running, be configured as restartable, and have read/write components with sufficient state to resume safely. Understanding these conditions helps avoid accidentally creating a new JobInstance, re-running already-completed Steps, or duplicating data after an incident.

## 1. Distinguishing JobInstance and JobExecution

This is the foundational condition for understanding restart.

- **JobInstance** represents a logical processing unit with a specific set of identifying parameters.
- **JobExecution** represents a single execution attempt of a JobInstance. A JobInstance can have multiple JobExecutions if a previous run failed or was stopped and later restarted.

JobInstance identity is determined by the Job name and the JobParameters marked as identifying.

For example:

~~~text
Job name: importOrdersJob
Identifying parameters:
  businessDate = 2026-11-15
  sourceFileId = 8421

                    |
                    v
JobInstance: importOrdersJob / 2026-11-15 / 8421
                    |
          +---------+---------+
          |                   |
          v                   v
JobExecution 101       JobExecution 108
FAILED                 COMPLETED
(first run)            (restart run)
~~~

JobExecution 101 and 108 belong to the same JobInstance. Restart does not create a new JobInstance; it creates the next execution for the existing instance.

If you change an identifying JobParameter, Spring Batch treats it as a different JobInstance. That is appropriate when running a new unit of work, but not how you resume an old execution.

## 2. JobParameters conditions

When you want to restart, you must launch the exact same Job with the same identifying JobParameters that defined the original JobInstance.

Example initial run:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceFileId", 8421L, true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, parameters);
~~~

If the execution fails, calling JobLauncher again with the same Job name and the same identifying parameters will request a restart of that JobInstance, provided other status and configuration conditions allow it.

~~~java
JobParameters sameParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("sourceFileId", 8421L, true)
        .toJobParameters();

jobLauncher.run(importOrdersJob, sameParameters);
~~~

Do not add a new identifying parameter just to try re-running. For example, if the restart adds `run.id=2` or a new timestamp and that parameter is identifying, Spring Batch will create a new JobInstance instead of resuming the old one.

### Identifying and non-identifying parameters

JobParameters can be marked as identifying or non-identifying.

- Identifying parameters participate in forming JobInstance identity.
- Non-identifying parameters are stored with the execution but do not alter JobInstance identity.

Do not use non-identifying parameters to silently change the meaning of source or target data between restarts. Even if a parameter does not participate in instance identification, changing input values between two runs can still render the old checkpoint invalid. Keep inputs that affect the result stable throughout the JobInstance lifecycle.

## 3. JobExecution statuses that allow restart

Restart is typically performed after the previous JobExecution ended in FAILED or STOPPED status.

| BatchStatus of latest execution | Restartable? | Meaning |
|---|---|---|
| FAILED | Yes, if the Job is restartable and other conditions are valid | The Job ended due to an error |
| STOPPED | Yes, if the Job is restartable | The Job was stopped in a controlled manner |
| COMPLETED | No for the same JobInstance | The work is already finished |
| STARTING / STARTED | Cannot restart concurrently yet | An execution is still starting or running |
| STOPPING | Cannot restart immediately | Currently in the process of stopping |
| ABANDONED | Should not restart this execution | Execution was marked abandoned/not to be resumed |
| UNKNOWN | Cannot restart safely based on metadata state | Transaction or execution outcome is indeterminate |

Exact conditions also depend on the Spring Batch version, StepExecution statuses, and Job configuration. While an execution is running, the repository prevents another execution from launching for the same JobInstance to avoid concurrent processing of the same unit of work.

Common launch exceptions:

- JobExecutionAlreadyRunningException: The JobInstance currently has a running execution.
- JobInstanceAlreadyCompleteException: The JobInstance is already complete.
- JobRestartException: Cannot restart due to status or configuration.
- JobParametersInvalidException: JobParameters failed the validator.
- StartLimitExceededException: A Step exceeded its start limit.

Do not delete metadata or manually edit BatchStatus in the database just to bypass these exceptions. First determine which execution is running, what status it ended with, and why the repository rejected the restart.

## 4. Job must be configured as restartable

By default, a Job built with JobBuilder is restartable. You can explicitly disable restarting with preventRestart():

~~~java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(importOrdersStep)
            .preventRestart()
            .build();
}
~~~

When a Job is configured with preventRestart(), if a previous execution fails or stops, Spring Batch will not allow restarting the same JobInstance. To run again, the application must create a new JobInstance using new identifying parameters per business rules.

Use preventRestart() only when the Job truly cannot or must not continue from a previous execution. In most long-running batch processes, restartability is essential for recovering from errors.

If a Job needs to be restartable, do not call preventRestart() in its configuration.

## 5. JobRepository must persist metadata

JobRepository is where JobInstance, JobExecution, StepExecution, status, and ExecutionContext are stored. Restart relies on this metadata to know how far the previous run progressed.

With a JDBC JobRepository, common tables include:

| Metadata | Table |
|---|---|
| JobInstance | BATCH_JOB_INSTANCE |
| JobExecution | BATCH_JOB_EXECUTION |
| JobParameters | BATCH_JOB_EXECUTION_PARAMS |
| StepExecution | BATCH_STEP_EXECUTION |
| Job ExecutionContext | BATCH_JOB_EXECUTION_CONTEXT |
| Step ExecutionContext | BATCH_STEP_EXECUTION_CONTEXT |

Table names can vary depending on the configured table prefix and schema. JobRepository must be properly configured and the metadata schema must be initialized for the corresponding Spring Batch version.

If JobRepository cannot persist state, the framework cannot accurately recover the execution. Do not use a transient in-memory repository for Jobs that must restart across process restarts or across multiple nodes. For production environments, a durable repository with appropriate backup/retention is required.

Do not manually delete rows in `BATCH_*` tables or directly modify execution statuses to force a restart. Such edits can break links between JobInstance, JobExecution, StepExecution, and saved contexts.

## 6. Completed Steps are normally skipped on restart

When a Job has multiple Steps and one Step fails, restarting the same JobInstance normally skips Steps that have already completed, and resumes from the unfinished or failed Step.

For example:

~~~text
JobInstance: dailyImport

First execution:
  validateFileStep  -> COMPLETED
  importDataStep    -> FAILED
  createReportStep  -> NOT STARTED

Restart:
  validateFileStep  -> does not run again
  importDataStep    -> restarts from checkpoint
  createReportStep  -> runs after import completes
~~~

This behavior is important to avoid repeating already-finished stages. If an early Step sent notifications, created files, or updated external systems, skipping completed Steps helps prevent duplicate side effects.

If business logic requires re-running a completed Step when the Job restarts, you can configure allowStartIfComplete(true) on that Step. You must understand the impact of re-running it and ensure the operation is idempotent.

## 7. allowStartIfComplete for completed Steps

By default, a Step that is already COMPLETED in a JobInstance will not run again when the Job restarts. You can allow re-running with allowStartIfComplete(true):

~~~java
@Bean
Step rebuildSummaryStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        Tasklet rebuildSummaryTasklet) {

    return new StepBuilder("rebuildSummaryStep", jobRepository)
            .tasklet(rebuildSummaryTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
~~~

This option is useful when a Step generates reports or derived data that can be safely regenerated after a later Step fails.

Do not enable this option mechanically. If the Step sent payments, dispatched emails, created orders, or performed a non-idempotent side effect, re-running it can produce duplicate results.

Distinguish carefully:
- allowStartIfComplete(true) allows a completed Step to run again during an eligible restart.
- It does not make an already-COMPLETED JobInstance restartable.
- It does not override Job restartability or JobExecution status conditions.

## 8. startLimit restricts how many times a Step can start

A Step can be configured with a limit on start attempts using startLimit(n):

~~~java
@Bean
Step importDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<Order> reader,
        ItemWriter<Order> writer) {

    return new StepBuilder("importDataStep", jobRepository)
            .<Order, Order>chunk(100, transactionManager)
            .reader(reader)
            .writer(writer)
            .startLimit(3)
            .build();
}
~~~

With a limit of 3, the Step cannot be started more than the allowed number of times according to the Step metadata in the JobInstance. If repeated restarts cause the Step to exceed the limit, the framework may throw StartLimitExceededException.

startLimit is not a retry limit for individual items. A retry limit controls how many times an operation is retried; startLimit controls how many times a Step can be started over the lifetime of a JobInstance.

Set startLimit when there is a clear operational reason. If set too low, a Job may lose its chance to restart after a few brief infrastructure glitches. If no special limit is needed, use the framework default.

## 9. How do FAILED and STOPPED differ?

FAILED usually indicates that a Step or Job ended due to an exception or processing error. STOPPED usually is the terminal status after a Job was requested to stop in a controlled manner.

Both statuses can serve as starting points for a restart if the Job is restartable and metadata is valid.

Example of a controlled stop:

~~~text
JobExecution is STARTED
       |
       | stop requested
       v
JobExecution STOPPING
       |
       | framework stops at a safe point
       v
JobExecution STOPPED
       |
       | restart the same JobInstance
       v
New JobExecution
~~~

Do not restart while the execution is still STOPPING. Wait for the framework to finish stopping and for the repository to record the final status as STOPPED.

Controlled stopping is useful when pausing batch work for maintenance or resource prioritization. It allows the framework to save metadata and terminate the Step according to its lifecycle rather than abruptly killing the process.

## 10. ABANDONED and UNKNOWN are not normal restart points

ABANDONED indicates an execution has been marked as not to be continued. In a restart flow, an abandoned StepExecution is not automatically re-run like a failed Step. This status can be used when an operator decides to skip a Step or execution that should no longer proceed.

UNKNOWN indicates the framework could not safely determine the execution outcome, often due to errors while updating transactions or metadata. You should not automatically restart when you do not know whether business data committed.

When encountering these statuses:

1. Inspect logs and why the execution entered that status.
2. Reconcile metadata against committed business data.
3. Determine whether recovery is possible via an approved operational procedure or if a new JobInstance must be created.
4. Do not manually edit BatchStatus via SQL to force the framework to continue.

If a Step needs to be skipped, use an appropriate flow or administrative action and understand its impact on business outcomes. ABANDONED is an execution-lifecycle decision, not a substitute for item skipping.

## 11. Restart conditions for readers and writers

Even a restartable Job can fail to recover properly if the reader or writer does not save the necessary state.

Stateful components typically implement ItemStream or ItemStreamReader/ItemStreamWriter:

- open(ExecutionContext): restores saved state.
- update(ExecutionContext): puts the current checkpoint into the context.
- close(): releases resources.

Example configuring a built-in reader:

~~~java
@Bean
@StepScope
FlatFileItemReader<Order> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<Order>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .delimited()
            .names("id", "customerId", "amount")
            .targetType(Order.class)
            .saveState(true)
            .build();
}
~~~

saveState(true) lets the reader save the state needed for restart. The reader name must remain stable because the framework uses the component name to namespace keys in ExecutionContext.

If using custom readers/writers, implement the ItemStream lifecycle properly. If using delegates or composites, ensure stateful delegates are registered so the framework calls open, update, and close.

## 12. Source and target data must remain stable across restarts

A checkpoint only has meaning if the data it references remains unchanged.

For example, a reader saved position line 10,000 in an input file. If the file is replaced by another file before restart, position 10,000 no longer represents the same data. The Job may skip or misprocess records.

You must ensure:

- Input files are not modified during the JobInstance lifecycle.
- Database sources have a stable read order or an explicit snapshot/watermark.
- Query sorting is deterministic, typically based on a unique key.
- Partition boundaries do not change between restarts.
- Output files or target resources still exist if the writer needs to resume.
- Source version/checksum is verified on restart if data could change.

With databases, a reader paginating by ID needs stable ordering and appropriate filtering. If new data is inserted or records are deleted between runs, determine whether the Job should process the initial snapshot or current data.

## 13. Transactions and checkpoints must stay consistent

Spring Batch saves checkpoints along the chunk lifecycle. With database writers, written data and checkpoint metadata need appropriate transaction semantics so one does not get ahead of the other.

If business data and JobRepository share the same transactional resource in a proper configuration, changes can commit/roll back together. If they use two separate databases or two different local transaction managers, do not assume they form a single atomic transaction.

Situations that can arise:

- Business data committed, but the checkpoint was not saved.
- Checkpoint was saved, but a non-transactional write target did not confirm.
- A file or API received data, but the database transaction rolled back.

For safe restarts:

- Use a transaction manager that properly manages the business resource.
- Keep reader/writer checkpoints aligned with committed data.
- Use unique constraints, upserts, or idempotency keys when re-writes can occur.
- Use an outbox when messages must be emitted after the business transaction commits.
- Have a reconciliation process for non-transactional side effects.

Do not treat Job status as the sole proof of business data state. A FAILED Job may still have many earlier chunks that committed successfully.

## 14. Restarting a Job with JobLauncher or JobOperator

You can restart by invoking JobLauncher with the same identifying JobParameters after the prior execution ended in a restartable status.

~~~java
JobExecution execution =
        jobLauncher.run(importOrdersJob, sameIdentifyingParameters);
~~~

JobRepository checks the JobInstance and the previous execution status. If conditions are met, it creates a new JobExecution attached to the same JobInstance.

For administrative operations, JobOperator provides a restart method by JobExecution ID:

~~~java
long newExecutionId =
        jobOperator.restart(failedExecutionId);
~~~

Exact method signatures and exceptions follow the Spring Batch API version in use. JobOperator is commonly used by consoles or operational services to restart a failed or stopped execution.

Do not trigger parallel restarts for the same execution. JobRepository has safeguards to prevent the same JobInstance from running concurrently, but callers should still handle status exceptions and avoid infinite administrative retry loops.

## 15. RunIdIncrementer creates a new JobInstance

JobParametersIncrementer is commonly used to generate a new set of JobParameters for a new run. RunIdIncrementer is a popular example that increments a `run.id` parameter.

~~~java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step importStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importStep)
            .build();
}
~~~

Each identifying increment of `run.id` creates a new JobInstance. This is appropriate when you want to run work again as a new batch, but it is not a checkpoint restart of a failed JobInstance.

Distinguish two intents:

- **Restart:** keep identifying parameters to resume the same JobInstance.
- **New run:** create new identifying parameters, such as a new business date or run ID.

Do not automatically attach a new timestamp when an operator chooses to restart. If a scheduler always generates new parameters, each run can become a new JobInstance and bypass the failed run's checkpoint.

## 16. Flow control can affect restartability

Flow DSL determines the next Step and the final Job status. You must understand the difference between completing, failing, and stopping.

A flow that ends the Job in COMPLETED status completes the JobInstance. At that point, the same JobInstance cannot be restarted like a FAILED or STOPPED Job.

If you need to stop a Job to restart from a specific Step, use flow stop/restart mechanisms instead of ending the Job as COMPLETED. When designing flows, examine both BatchStatus and ExitStatus: ExitStatus can drive transitions, while BatchStatus reflects the lifecycle state JobRepository uses to manage executions.

Do not arbitrarily assign an ExitStatus and assume the Job has become restartable. Let the framework terminate the execution with the appropriate BatchStatus.

## 17. Conditions that make restarting unsafe

Even when JobRepository permits a restart, business outcomes can still be unsafe if data or side effects cannot be repeated.

Examples:

- The Writer sent an email, but the process stopped before the checkpoint was saved.
- An API created a transaction, but the response timed out, leaving the Job unaware of the outcome.
- An output file was written, but the checkpoint did not commit.
- A Reader used an offset on a file that had been modified.
- A completed Step was re-executed and produced duplicates.
- The Job used a new identifying parameter and created a different instance.
- Two databases committed independently and fell out of sync.

Safeguards:

- Design idempotent writers.
- Use business keys and unique constraints.
- Use idempotency keys for APIs.
- Write an outbox in the same business transaction.
- Use separate files per JobInstance and publish only on completion.
- Maintain source snapshots or versions.
- Reconcile data before restarting if non-transactional side effects occurred.

Framework restartability and business restart safety are related but distinct concerns. The framework can create a new execution with proper metadata, but the application must still ensure reprocessing neither duplicates nor drops data.

## 18. Procedure to determine whether a Job can restart

When a Job fails, check in order:

1. **Identify the JobInstance:** check the Job name and identifying JobParameters from the prior run.
2. **Check the latest execution:** confirm BatchStatus is FAILED or STOPPED and no execution is still running.
3. **Check restartability:** confirm the Job does not use preventRestart().
4. **Check Steps:** identify which Steps are completed, failed, stopped, or abandoned; check allowStartIfComplete and startLimit.
5. **Check JobRepository:** ensure metadata and ExecutionContext were persisted.
6. **Check component state:** readers/writers support ItemStream and state keys remain compatible.
7. **Check source/target:** files, queries, partition boundaries, and output resources still align with the checkpoint.
8. **Check transactions:** determine whether business data and checkpoints could be out of sync.
9. **Check idempotency:** verify retries/restarts will not cause duplicate side effects.
10. **Relaunch the right instance:** use the same identifying parameters or JobOperator.restart on the appropriate execution.

If a condition is unclear, do not repeatedly restart hoping it succeeds. Reconcile metadata against business data first, especially when the Job writes to systems outside the transaction.

## 19. Testing restart conditions

Restart must be tested with a real JobRepository and appropriate resources, not just unit tests for a single listener.

Important scenarios:

| Scenario | Expected verification |
|---|---|
| First Job run completes | Relaunching with the same identifying parameters is rejected because the instance is complete |
| Job fails | Restart creates a new JobExecution for the same JobInstance |
| Job stops in a controlled manner | Can restart after status transitions to STOPPED |
| Job is still running | Duplicate launch is rejected |
| Job uses preventRestart | Restart is rejected |
| Identifying parameter changes | Creates a new JobInstance |
| Adding a new run.id | Creates a new instance, does not resume old checkpoint |
| Step already completed | Skipped by default on restart |
| Step has allowStartIfComplete | Completed Step runs again as configured |
| Step exceeds startLimit | Cannot start again |
| Reader supports saveState | Resumes from saved checkpoint |
| Input changes | Job detects or handles per version policy |
| Non-idempotent Writer | Test exposes duplicate risk |
| Execution UNKNOWN/ABANDONED | Does not automatically restart like a FAILED execution |

A typical integration test: run the Job with enough data to complete several chunks, deliberately make the writer fail on a later chunk, verify the JobExecution is FAILED, then restart with the same identifying parameters and verify the final data has neither gaps nor duplicates.

You should also test abrupt process termination to understand metadata and transaction behavior in your deployment environment. A process kill can leave a different state than a controlled Job stop.

## 20. Common mistakes when restarting

**Adding a new parameter on restart.** JobLauncher creates a new JobInstance and ignores the old instance's checkpoint.

**Restarting a COMPLETED Job.** The JobInstance is already complete; a new run with new identifying parameters is required to reprocess.

**Job uses preventRestart().** The framework rejects restarting the same instance even if the previous execution FAILED.

**Execution is still running or STOPPING.** Wait for the status to reach a terminal state before restarting.

**Completed Step runs again unexpectedly.** Check allowStartIfComplete and the Step's side effects.

**Exceeding startLimit.** The Step cannot start again within the same JobInstance under the configured limit.

**Reader/writer does not save state.** The Job may start again without knowing the right position to resume from.

**Renaming components or ExecutionContext keys.** Old checkpoints can no longer be read correctly.

**Source data changed.** Offsets or last IDs no longer represent the same data.

**Editing metadata tables directly.** Can corrupt execution relationships and repository consistency.

**Assuming FAILED means the whole Job rolled back.** Previously committed chunks may still exist; restart must handle committed portions safely.

## 21. Designing a Job with restart capability

When building a Job, establish the restart conditions upfront:

- Choose stable identifying JobParameters to identify a unit of work.
- Keep the Job restartable if business rules allow continuing after errors.
- Do not use preventRestart() if recovering the same JobInstance is needed.
- Have JobRepository persist metadata durably.
- Use Step ExecutionContext and ItemStream for checkpoints.
- Keep Step, reader, writer names, and state keys stable across deployments.
- Decide whether completed Steps should run again.
- Set startLimit only when there is an explicit requirement.
- Keep source/target data stable or versioned/snapshotted.
- Design idempotent writers and recoverable side effects.
- Test FAILED, STOPPED, COMPLETED, restart, and process interruption scenarios.

A Job can be restarted when the same JobInstance is in a resumable state, the Job is configured as restartable, JobRepository stores sufficient metadata, and Steps/components can restore checkpoints. Restart creates a new JobExecution for the same instance; JobParameters with new identifying values create a different instance. By properly combining status, metadata, transactions, and idempotency, Spring Batch can resume work after an incident without arbitrary reprocessing or data corruption.

