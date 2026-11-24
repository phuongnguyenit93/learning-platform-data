# Restarting from a failed step

In Spring Batch, a job can consist of multiple steps, and each step can process thousands or millions of items. If a step fails after earlier steps have completed, you usually do not need to re-run the entire workflow from the start. Spring Batch stores execution metadata and the status of each step to support **restarting from a failed step**.

Restarting creates a new `JobExecution` for the same `JobInstance`, after which the framework determines which steps have already completed, which step needs to run again, and what state needs to be restored. To make this process safe, the application must keep job identity stable, save checkpoints properly, and design readers/writers that can tolerate reprocessing uncommitted items.

## 1. Distinguishing JobInstance and JobExecution

This is the foundation for understanding restarts. `JobInstance` represents a logical unit of processing; `JobExecution` represents a specific run of that unit.

A JobInstance is identified by the job name and identifying `JobParameters`. When a job fails and is restarted, Spring Batch creates a new JobExecution belonging to the same JobInstance.

```text
Job: importOrdersJob
Identifying parameter: businessDate=2026-11-15
                  |
                  v
JobInstance: importOrdersJob / 2026-11-15
                  |
          +-------+--------+
          |                |
          v                v
   JobExecution #1   JobExecution #2
       FAILED          COMPLETED
```

The second run is not a new JobInstance. It is the next execution of the same logical unit of work.

| Concept | Meaning on restart |
|---|---|
| `JobInstance` | Remains unchanged if the job name and identifying parameters do not change. |
| `JobExecution` | Each run/restart creates a new execution with its own ID. |
| `StepExecution` | Each step execution has its own metadata; a restart can create a new StepExecution for the step that needs to run again. |
| `ExecutionContext` | Stores checkpoints and state needed to resume processing. |

If you change an identifying parameter, Spring Batch treats the request as a different JobInstance. Therefore, when you want to restart, you must use the exact job name and the exact identifying parameters from the original run.

## 2. What happens when a step fails?

Suppose an order-import job consists of three steps:

1. `validateFileStep`: validates the input file.
2. `importOrdersStep`: reads, processes, and writes orders.
3. `publishSummaryStep`: generates and sends a summary report.

If the import step fails, the statuses may look like this:

```text
importOrdersJob
    |
    +-- validateFileStep       COMPLETED
    |
    +-- importOrdersStep       FAILED
    |
    +-- publishSummaryStep     NOT STARTED
```

When restarting the same JobInstance, Spring Batch normally skips already-completed steps and resumes from the unfinished/failed step according to the flow and metadata state:

```text
importOrdersJob - restart
    |
    +-- validateFileStep       COMPLETED (does not run again by default)
    |
    +-- importOrdersStep       runs again from the appropriate checkpoint
    |
    +-- publishSummaryStep     runs after import completes
```

This behavior avoids repeating completed work. However, it depends on step and flow configuration. An already-completed step can be told to run again with `allowStartIfComplete(true)`, while `startLimit` can prevent a step from starting additional times.

Restarting is not blindly re-running the entire job. The framework relies on saved metadata to determine prior progress and what remains to be continued.

## 3. Conditions for a job to be restartable

Several important conditions must be met:

- The job must allow restarting; `preventRestart()` must not be configured if restarting is desired.
- The JobInstance must be in a restartable status, typically `FAILED` or `STOPPED`.
- No other execution of the same JobInstance may be currently running.
- The step to re-run must not exceed `startLimit`.
- The flow must have a valid path from the previous execution's state.
- Identifying JobParameters must point to the exact old JobInstance.
- JobRepository must persist metadata durably enough to restore state.
- Readers/writers must save and restore appropriate checkpoints if resuming from mid-step is desired.

`FAILED` and `STOPPED` statuses are typically restartable. A `COMPLETED` JobInstance cannot be re-run as a normal restart with the same identifying parameters. `ABANDONED` or `UNKNOWN` statuses must be handled carefully according to operational rules and the framework version; never manually alter metadata to force continuation.

## 4. Configuring a job to allow restarting

A job is normally restartable unless restartability is disabled. You can explicitly prevent restarting with `preventRestart()`:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importOrdersStep,
        Step publishSummaryStep) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .start(validateFileStep)
            .next(importOrdersStep)
            .next(publishSummaryStep)
            .build();
}
```

The example above does not call `preventRestart()`, so the job remains restartable according to Spring Batch status and conditions.

If a job is designed to run only once and cannot safely resume, you can configure:

```java
return new JobBuilder("oneTimeExportJob", jobRepository)
        .start(exportStep)
        .preventRestart()
        .build();
```

Once `preventRestart()` is called, requests to restart the JobInstance will be rejected. Use this option only when business rules strictly forbid restarting and another error-handling procedure is in place.

## 5. Relaunching the same JobInstance

There are two common ways to request a restart: invoking `JobLauncher` again with the same identifying parameters, or using the operational API `JobOperator.restart` with the old execution ID.

### Using JobLauncher

Example initial job run:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders-20261115.csv", true)
        .toJobParameters();

JobExecution firstExecution = jobLauncher.run(importOrdersJob, parameters);
```

After the execution fails and the root cause is resolved, invoke the same job again with the same identifying parameters:

```java
JobExecution restartExecution = jobLauncher.run(importOrdersJob, parameters);
```

Spring Batch recognizes the same JobInstance and creates a new JobExecution if the status allows restarting. If the prior run already completed, the same parameters typically result in `JobInstanceAlreadyCompleteException`.

### Using JobOperator

In operational workflows, you often already have the JobExecution ID of the failed run. `JobOperator` provides an API to restart by ID:

```java
long newExecutionId = jobOperator.restart(failedExecutionId);
```

The API can throw administrative exceptions such as execution not found, non-restartable, or invalid parameters. Verify status and operational permissions before calling it.

`JobOperator.restart` uses the metadata of the prior execution to determine the job and parameters to restart. This is a good fit for admin consoles or controlled operational workflows.

## 6. JobParameters must remain stable on restart

Suppose `importOrdersJob` uses business date and input file as identifying parameters:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "data/orders-20261115.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

When restarting, keep the identifying values unchanged:

| Parameter | Identifying | On restart |
|---|---:|---|
| `businessDate` | Yes | Keep the original instance's business date. |
| `inputFile` | Yes | Keep the original input file/batch identifier. |
| `requestedBy` | No | Does not affect JobInstance identity, though changing it can affect auditing or application logic. |

Do not add a timestamp or new UUID as an identifying parameter when your goal is to restart. Doing so creates a new JobInstance instead of resuming the failed one.

Even for non-identifying parameters, be careful when changing values between executions. If a processor or writer depends on that parameter, changing it can make the restart process the same JobInstance with different logic. Keep all parameters affecting business outcomes stable.

## 7. Do COMPLETED steps run again?

By default, when a job restarts, steps that already completed in the previous execution do not run again. This avoids repeating finished work.

If a completed step needs to run again on every job restart, you can configure `allowStartIfComplete(true)`:

```java
@Bean
Step refreshReferenceDataStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet refreshTasklet = (contribution, chunkContext) -> {
        // Sync reference data according to the application's policy.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("refreshReferenceDataStep", jobRepository)
            .tasklet(refreshTasklet, transactionManager)
            .allowStartIfComplete(true)
            .build();
}
```

On restart, this step can execute again even if the previous execution was `COMPLETED`. That is useful for preparation steps that must re-run to guarantee current input preconditions.

Do not enable this option for every step. If a step sends payments, sends emails, generates final files, or updates non-idempotent data, re-running it can produce duplicate side effects.

## 8. startLimit limits how many times a step starts

`startLimit` caps how many times a step is permitted to start. By default, a step typically has a very large limit; you can set a lower limit to protect resources or business logic.

```java
@Bean
Step fragileExternalCallStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        // Call an external system according to the application's policy.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("fragileExternalCallStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .startLimit(3)
            .build();
}
```

If the step reaches the limit, a subsequent restart may be rejected with `StartLimitExceededException`. Distinguish `startLimit` from retry limit:

| Configuration | Scope |
|---|---|
| `retryLimit` | Number of times an operation/item is retried under the retry policy within a step execution. |
| `startLimit` | Number of times a step is allowed to start across executions. |
| `skipLimit` | Total number of items/errors allowed to be skipped within a step execution under the skip policy. |

If you want to restart a failed step, do not set `startLimit` too low compared to the number of operational attempts that might be needed. Conversely, a limit can be helpful when a step creates hard-to-reverse or expensive side effects.

## 9. Restarting from a checkpoint in a chunk-oriented step

A major strength of Spring Batch is checkpoint support. In a chunk-oriented step, readers and writers can implement `ItemStream` to save state in `ExecutionContext`.

For example, a file reader saves the read position. After each chunk commit, the read state is updated. If the next chunk fails, a restart can resume from the last committed checkpoint.

```text
Read and write chunk 1 -> COMMIT -> checkpoint 1
Read and write chunk 2 -> COMMIT -> checkpoint 2
Read chunk 3           -> error, ROLLBACK

Restart:
  restore checkpoint 2
  re-read the uncommitted part of chunk 3
  continue chunk 4...
```

The recovery point is the durably saved state, not the last Java statement executed before the process died. Items in an uncommitted chunk may be read and processed again.

Many built-in readers such as `FlatFileItemReader`, `JdbcPagingItemReader`, or other `ItemStream`-capable readers can save state. When writing a custom reader, implement `ItemStream`/`ItemStreamReader` if checkpoint support is needed.

## 10. ItemStream and ExecutionContext

The `ItemStream` lifecycle includes these key methods:

- `open(ExecutionContext)`: opens resources and restores saved state.
- `update(ExecutionContext)`: updates the state to be checkpointed.
- `close()`: releases resources.

Illustrative custom reader saving its read position:

```java
public class NumberReader implements ItemStreamReader<Long> {

    private long current;
    private final long max;

    public NumberReader(long max) {
        this.max = max;
    }

    @Override
    public void open(ExecutionContext context) {
        current = context.containsKey("numberReader.current")
                ? context.getLong("numberReader.current")
                : 0L;
    }

    @Override
    public Long read() {
        if (current >= max) {
            return null;
        }
        current++;
        return current;
    }

    @Override
    public void update(ExecutionContext context) {
        context.putLong("numberReader.current", current);
    }

    @Override
    public void close() {
        // Close resources if the reader opened any.
    }
}
```

This is a simple example of saving state. Real-world readers must pay attention to transaction boundaries, how the framework calls `update`, source data stability, and thread safety. Do not store open resource objects such as `InputStream` or `ResultSet` in ExecutionContext; store only enough information to reopen and continue.

## 11. Restarting with a file reader

With `FlatFileItemReader`, enable state saving and give the reader a stable name:

```java
@Bean
@StepScope
FlatFileItemReader<OrderInput> orderReader(
        @Value("#{jobParameters['inputFile']}") String inputFile) {

    return new FlatFileItemReaderBuilder<OrderInput>()
            .name("orderReader")
            .resource(new FileSystemResource(inputFile))
            .encoding("UTF-8")
            .linesToSkip(1)
            .delimited()
            .names("orderId", "customerId", "amount")
            .fieldSetMapper(fieldSet -> new OrderInput(
                    fieldSet.readString("orderId"),
                    fieldSet.readString("customerId"),
                    fieldSet.readBigDecimal("amount")))
            .saveState(true)
            .build();
}
```

`@StepScope` allows resolving the file path from JobParameters at step execution time. `saveState(true)` lets the reader persist its read position.

Important condition: the file must keep the same content and line order between the initial run and the restart. If a file at the same path is replaced with different content, the old checkpoint may point to a position that no longer corresponds to the same data. For large or critical files, store immutable files keyed by batch ID or checksum.

## 12. Restarting with a database reader

With `JdbcPagingItemReader`, use a stable order and a unique sort key so checkpoints remain meaningful. For example:

```java
@Bean
@StepScope
JdbcPagingItemReader<OrderInput> orderPagingReader(
        DataSource dataSource,
        @Value("#{jobParameters['businessDate']}") String businessDate) {

    return new JdbcPagingItemReaderBuilder<OrderInput>()
            .name("orderPagingReader")
            .dataSource(dataSource)
            .selectClause("select order_id, customer_id, amount")
            .fromClause("from orders")
            .whereClause("where business_date = :businessDate")
            .parameterValues(Map.of("businessDate", businessDate))
            .sortKeys(Map.of("order_id", Order.ASCENDING))
            .rowMapper((rs, rowNum) -> new OrderInput(
                    rs.getString("order_id"),
                    rs.getString("customer_id"),
                    rs.getBigDecimal("amount")))
            .pageSize(500)
            .saveState(true)
            .build();
}
```

For stable restarts:

- `order_id` must establish a unique order in the result set, or a secondary key must be added to ensure uniqueness.
- The `businessDate` filter condition must stay the same.
- The dataset should not change in ways that shift page boundaries while the job runs.
- If data can change, use a snapshot, batch ID, or watermark to fix the scope.

Cursor readers and paging readers have different checkpoint semantics. Consult the specific implementation and database/driver behavior rather than assuming all readers recover in the exact same way.

## 13. Tasklet steps and restarting

Tasklet steps can also be restarted. However, custom tasklets must manage state and side effects appropriately.

If a tasklet performs a single operation and the transaction can roll back all changes, restarting can re-run that operation. But if the tasklet calls an external API, creates files, or sends emails, a database transaction cannot automatically undo those side effects.

Example of a tasklet storing state in Step ExecutionContext:

```java
@Bean
Step prepareExportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager) {

    Tasklet tasklet = (contribution, chunkContext) -> {
        ExecutionContext context = contribution.getStepExecution()
                .getExecutionContext();

        String exportReference = context.containsKey("exportReference")
                ? context.getString("exportReference")
                : UUID.randomUUID().toString();

        context.putString("exportReference", exportReference);

        // Use the stable exportReference for the next task.
        return RepeatStatus.FINISHED;
    };

    return new StepBuilder("prepareExportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

The example illustrates persisting a reference; generating a UUID inside a tasklet is only safe if the value is saved and restored according to transaction/restart semantics, and not regenerated on every call once present. For external side effects, a dedicated idempotency mechanism is recommended.

If a tasklet returns `RepeatStatus.CONTINUABLE`, it can be invoked multiple times within the same step execution. Checkpoints must be updated consistently so each invocation resumes the unfinished work accurately.

## 14. allowStartIfComplete and re-running completed steps

By default, completed steps do not run again when restarting a job. `allowStartIfComplete(true)` changes this behavior.

Use it when a step performs preparation or synchronization that must be re-executed before a failed step, such as:

- Refreshing reproducible reference data.
- Checking current input preconditions.
- Regenerating an intermediate file that can be safely overwritten.
- Preparing environment conditions needed by the next step.

Do not use it with steps that create non-idempotent transactions, such as:

- Sending money or recording payments.
- Sending emails/notifications without a deduplication key.
- Creating a new order on every run.
- Publishing events without a deduplication mechanism.

If you need to re-run a completed step for a new business request, consider creating a new JobInstance with an identifying parameter representing the new run rather than using `allowStartIfComplete` to alter restart semantics.

## 15. startLimit and restartability of failed steps

`startLimit` controls how many times a step is allowed to start. If set too low, the step may not be able to restart after several failures.

For example:

```java
return new StepBuilder("loadExternalDataStep", jobRepository)
        .tasklet(loadTasklet, transactionManager)
        .startLimit(2)
        .build();
```

With this limit, the step can start at most twice under the framework's start-limit rules. Once the limit is exhausted, the next restart attempt may throw `StartLimitExceededException`.

Choose the limit based on actual recoverability, cost, and step side effects. If a step can safely restart after fixing the root cause, the limit should allow a reasonable number of operational attempts.

## 16. Flows and conditional transitions on restart

Restarts also depend on flow structure. A job can use `ExitStatus` to branch to different steps. On restart, the framework continues according to the flow and saved metadata, so you must understand which steps transitions can lead to.

For example:

```java
@Bean
Job importJob(
        JobRepository jobRepository,
        Step validateStep,
        Step importStep,
        Step warningStep,
        Step reportStep) {

    return new JobBuilder("importJob", jobRepository)
            .start(validateStep)
                .on("COMPLETED").to(importStep)
            .from(importStep)
                .on("COMPLETED_WITH_WARNINGS").to(warningStep)
            .from(importStep)
                .on("COMPLETED").to(reportStep)
            .from(warningStep)
                .on("*").to(reportStep)
            .from(reportStep)
                .on("*").end()
            .end()
            .build();
}
```

In conditional flows, ensure the step's `ExitStatus` is produced consistently on restart. If a step fails and is re-run, the new result might take a different branch than the previous run. Steps that already completed and are skipped on restart can still influence the flow based on saved metadata.

Do not rely on side effects in listeners to drive flow decisions without saving the outcome in appropriate metadata. If the flow requires a business result, represent it explicitly via ExitStatus or data in ExecutionContext.

## 17. Old StepExecutions and JobExecutions are preserved

Restarting does not overwrite old executions. JobRepository retains history so runs can be tracked.

For example:

```text
JobInstance: importOrdersJob / businessDate=2026-11-15
  |
  +-- JobExecution #101: FAILED
  |      +-- validateFileStep: COMPLETED
  |      +-- importOrdersStep: FAILED
  |
  +-- JobExecution #205: COMPLETED
         +-- importOrdersStep: COMPLETED
         +-- publishSummaryStep: COMPLETED
```

When investigating, look at the exact JobExecution ID and StepExecution ID. Do not look up only the latest status by job name if multiple JobInstances run concurrently.

`JobExplorer` supports reading metadata:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    System.out.println("Status: " + execution.getStatus());
    System.out.println("Exit: " + execution.getExitStatus());

    for (StepExecution stepExecution : execution.getStepExecutions()) {
        System.out.println(
                stepExecution.getStepName() + " -> " + stepExecution.getStatus());
    }
}
```

`JobExplorer` is well suited for monitoring history. `JobOperator` supports operational actions such as restart/stop via the configured API. Do not directly update metadata tables to force an execution into a desired status.

## 18. Common pitfalls when restarting

| Issue | Common cause | Mitigation |
|---|---|---|
| Unintended new JobInstance created | Adding a timestamp/UUID or changing an identifying parameter. | Reuse the exact identifying parameters on restart. |
| `JobInstanceAlreadyCompleteException` | Instance is already complete; invoked with the same identity as if restarting. | Determine whether this is a new run request or needs another admin action. |
| `JobExecutionAlreadyRunningException` | Previous execution is still running. | Check actual status before sending another request. |
| `JobRestartException` | Job/step disallows restart or status is unsuitable. | Check `preventRestart`, metadata, flow, and step configuration. |
| `StartLimitExceededException` | Step exhausted its start limit. | Review start limit policy and operational procedures. |
| Completed step did not run again | Default behavior skips completed steps. | Enable `allowStartIfComplete(true)` only if the step is safe to re-run. |
| Reader reads from wrong position | State not saved, reader name changed, or data source changed. | Use ItemStream, stable names, and immutable input. |
| Duplicate data written | Uncommitted chunk reprocessed or non-transactional side effect repeated. | Use unique keys, upserts, idempotency keys, or outbox. |
| Metadata missing after process restart | Non-durable repository used or metadata deleted. | Use a durable JobRepository and preserve metadata schema. |
| Restart takes wrong branch | Flow transitions or ExitStatus not designed for restarts. | Check status and outcome of each step in the prior execution. |

## 19. JobRepository must store metadata durably

Restarts are only reliable when execution metadata is stored durably. If the application uses an in-memory-only repository, state can be lost when the JVM stops. The framework then lacks sufficient information to know which steps completed or how far the reader progressed.

In environments requiring restarts across application restarts, use a database-backed JobRepository with the Spring Batch schema matching your version. Nodes/workers must access a consistent repository if participating in a distributed process.

Do not delete metadata of a JobInstance/JobExecution that still needs restarting. Deleting metadata can erase checkpoints, failure history, and relationships between execution attempts. If old data cleanup is needed, enforce an explicit retention policy and delete only executions past operational/audit retention windows.

## 20. Transaction boundaries and committed data

Restarting does not roll back chunks that already committed before the step failed. For example, a step successfully wrote 20 chunks and then failed on chunk 21. After restarting, the first 20 chunks still exist; the framework resumes from the last committed checkpoint if the reader supports it.

This also means the writer must be designed not to write duplicates when uncommitted items are reprocessed. A database transaction only protects resources participating in that transaction. If a processor/writer already sent an email or called an external API before rollback, the side effect may already have occurred.

Common safeguards:

- Unique business key constraints on target tables.
- Upsert or merge with explicit rules.
- Idempotency keys for external APIs.
- Outbox pattern to emit events after the data transaction commits.
- Processing status tables keyed by batch ID/item ID.
- Reconciliation processes for side effects with ambiguous outcomes.

## 21. Restarting with partitioning

With partitioning, each worker step has its own `StepExecution` and `ExecutionContext`. When one partition fails, other partitions that have completed or committed do not roll back automatically.

```text
managerStep
  |
  +-- partition0: COMPLETED
  +-- partition1: FAILED
  +-- partition2: COMPLETED
  +-- partition3: COMPLETED
```

On restart, the framework can skip completed partitions and resume unfinished partitions based on metadata. This requires:

- Stable partition names.
- Unchanged data ranges for each partition within the same JobInstance.
- A Partitioner that recreates or supplies the exact partition identities.
- Worker readers saving their own checkpoints.
- Writers capable of tolerating reprocessing of uncommitted items.

If the partitioner re-slices ranges differently from the first run, old metadata may no longer match the current work. Fix the batch input, partition names, and data boundaries throughout the restart lifecycle.

## 22. Operational workflow for restarting from a failed step

When a job fails, operators should follow a controlled sequence:

1. **Look up the JobExecution:** retrieve ID, JobInstance, parameters, BatchStatus, and ExitStatus.
2. **Identify the failed step:** examine StepExecution, last exception, timestamp, and counters.
3. **Check completed steps:** determine which steps will be skipped on restart and which have `allowStartIfComplete`.
4. **Identify the checkpoint:** check whether the reader/writer saved state and where the last checkpoint stands.
5. **Inspect committed data:** determine which chunks committed and what non-transactional side effects may have occurred.
6. **Resolve the root cause:** fix data, restore services, adjust configuration, or release locks.
7. **Verify parameters:** preserve identifying values and all parameters affecting business results.
8. **Check restart conditions:** `preventRestart`, start limit, execution status, and flow.
9. **Trigger the restart:** use JobOperator or JobLauncher according to application procedures.
10. **Monitor the new execution:** verify the failed step completes, subsequent steps run properly, and output data has no duplicates.
11. **Record audit trail:** preserve links between the old execution, new execution, and remediation cause.

Do not repeatedly restart before the root cause is addressed. If the error is deterministic bad data or a broken schema, restarting only repeats the failure. If the error was transient infrastructure, verify the system has recovered before re-running.

## 23. Testing restartability

A job that needs restartability should have integration tests simulating a failure after several chunks have committed:

- Run the job with deterministic JobParameters.
- Configure a test writer or processor to throw an exception on a specific item/chunk.
- Verify the first JobExecution finishes as `FAILED`.
- Verify chunks prior to the failure committed and the checkpoint was saved.
- Fix the failure condition in the test.
- Restart the same JobInstance with the old identifying parameters.
- Verify already-completed steps do not run again by default.
- Verify the failed step resumes from the appropriate checkpoint.
- Verify output data has no duplicates and subsequent steps execute.

Test `allowStartIfComplete`, `startLimit`, and `preventRestart` options individually if the application uses them. For custom readers, test `open`, `update`, and state restoration after creating a new reader instance.

Unit tests that only check processor or reader logic are usually insufficient to prove restartability. Integration tests with a real JobRepository and transaction manager are needed to verify metadata and actual commit boundaries.

## 24. Key takeaways

- Restarting creates a new `JobExecution` for the same `JobInstance`; no new instance is created if identifying parameters remain unchanged.
- On restart, `COMPLETED` steps are normally skipped; failed/unfinished steps re-execute according to the flow and metadata.
- `preventRestart()` disables restarting; `allowStartIfComplete(true)` allows re-running completed steps; `startLimit` limits step start attempts.
- `retryLimit`, `skipLimit`, and `startLimit` are three distinct limits.
- Reader/writer checkpoints are saved via `ExecutionContext`; uncommitted chunks may be read and processed again.
- Readers must support `ItemStream`/state saving and source data must remain stable between the first run and the restart.
- Keep identifying JobParameters and all parameters affecting business outcomes unchanged.
- JobRepository must persist metadata durably to support restarts after JVM shutdown.
- Committed chunks do not automatically roll back when a step fails; writers must be idempotent to prevent duplicate writes.
- Non-transactional side effects like emails, HTTP requests, or message publishing require idempotency/outbox/reconciliation.
- With partitioning, partition names and data ranges must stay stable; committed partitions do not automatically roll back when another partition fails.
- Use JobExplorer to investigate metadata and JobOperator to perform restart actions according to operational procedures.

Restarting from a failed step is a recovery capability grounded in metadata and checkpoints, not an arbitrary re-run operation. Keep job identity stable, ensure steps are permitted to re-run under the right policy, persist reader/writer state, and control side effects of committed data. When done right, the job can resume from the unfinished portion while preserving history, consistency, and auditability.
