# Sequential flow between steps

In Spring Batch, a Job is typically divided into multiple `Step`s, with each Step responsible for a portion of the work. **Sequential flow** is a way of organizing a Job so that Steps are executed one after another in a declared order. For example, a data import Job may validate the file first, import the records next, and finally generate a report.

Sequential flow helps break a large process into units that are easy to understand, monitor, and recover. Each Step has its own execution state in `JobRepository`. If a Step fails, the Job can stop there; after resolving the root cause, the Job can be restarted according to Spring Batch's restart rules.

## 1. What is sequential flow?

Sequential flow describes the order of Steps in a Job. A subsequent Step is executed only when the control flow reaches that Step. A simple Job may consist of three Steps:

```text
customerImportJob
        |
        v
  validateFileStep
        |
        v
  importCustomersStep
        |
        v
  generateReportStep
        |
        v
       End
```

In this example:

1. `validateFileStep` checks the input file and required conditions.
2. `importCustomersStep` reads, processes, and writes customer data.
3. `generateReportStep` summarizes the import results and generates a report.

Splitting into multiple Steps gives each part its own configuration, transaction, listeners, counters, and error policy. It also allows Spring Batch to persist the completion status of each Step to support restart.

## 2. Declaring a Step sequence with `start()` and `next()`

For a Job with a linear flow, Spring Batch provides a concise builder API. `start(step)` specifies the first Step; each call to `next(step)` appends the next Step to the sequence.

Example with Spring Batch 5:

```java
@Bean
Job customerImportJob(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importCustomersStep,
        Step generateReportStep) {

    return new JobBuilder("customerImportJob", jobRepository)
            .start(validateFileStep)
            .next(importCustomersStep)
            .next(generateReportStep)
            .build();
}
```

The order of `next()` calls is the declared execution order. Spring Batch runs `validateFileStep` first, then `importCustomersStep`, and finally `generateReportStep` if the flow continues normally.

`JobBuilder` takes `JobRepository` to store Job and Step metadata. The Steps passed to the builder are typically defined as separate beans, which helps reuse dependencies and keeps configuration clear.

## 3. Defining each Step in the Job

Each Step can use a Tasklet or chunk-oriented processing. Sequential flow does not require all Steps to be of the same type.

### File validation Step using a Tasklet

```java
@Bean
Step validateFileStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ValidateFileTasklet tasklet) {

    return new StepBuilder("validateFileStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

The Tasklet can check file existence, header structure, business date, or checksum. If the input is invalid, the Tasklet can throw an exception so the Step fails and prevents downstream Steps from running.

### Import Step using chunk processing

```java
@Bean
Step importCustomersStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        ItemReader<CustomerInput> reader,
        ItemProcessor<CustomerInput, Customer> processor,
        ItemWriter<Customer> writer) {

    return new StepBuilder("importCustomersStep", jobRepository)
            .<CustomerInput, Customer>chunk(500, transactionManager)
            .reader(reader)
            .processor(processor)
            .writer(writer)
            .build();
}
```

This Step reads and processes up to 500 items in a chunk, then writes them and commits the transaction. If the file has a large volume of data, the Step can create multiple chunks before completing.

### Report generation Step using a Tasklet

```java
@Bean
Step generateReportStep(
        JobRepository jobRepository,
        PlatformTransactionManager transactionManager,
        GenerateReportTasklet tasklet) {

    return new StepBuilder("generateReportStep", jobRepository)
            .tasklet(tasklet, transactionManager)
            .build();
}
```

The final Step can aggregate statistics, generate an output file, or save the completion status for the import batch.

## 4. In what order are Steps executed?

With the chain `.start(A).next(B).next(C)`, the Job starts at A. If A completes successfully, the flow moves to B; if B completes successfully, the flow moves to C. When C completes, the Job finishes.

```text
START
  |
  v
 Step A
  |
  | completed
  v
 Step B
  |
  | completed
  v
 Step C
  |
  | completed
  v
 END
```

In a basic sequential Job, if a Step fails (`BatchStatus.FAILED`), the Job typically stops at that Step and subsequent Steps are not executed. For example, if `importCustomersStep` fails, `generateReportStep` will not run in that JobExecution.

Do not interpret `.next(stepB)` as "always run B regardless of A's outcome". `.next()` declares the linear order of the flow; whether a Step finishes successfully so the Job can continue still depends on the execution result. If you need branching based on outcomes, declare a conditional flow.

## 5. Step order is not bean initialization order

Steps are typically declared as Spring beans, but the declaration order of `@Bean` methods, the order Spring initializes beans, or the `@Order` annotation does not determine the Job flow.

Execution order is determined by the Job builder or flow definition:

```java
return new JobBuilder("myJob", jobRepository)
        .start(stepA)
        .next(stepB)
        .next(stepC)
        .build();
```

Even if `stepC` is initialized before `stepA`, the Job still runs A, B, and C in the declared sequence. If you want to change the order, you must change the flow definition.

## 6. Sequential flow is not a single transaction

A Job composed of multiple Steps does not mean the entire Job runs inside one large database transaction. Each Step manages transactions according to its own processing type and configuration:

- For a TaskletStep, each Tasklet invocation is managed within the transaction of that invocation.
- For a chunk-oriented Step, transactions are typically committed per chunk.
- When a Step completes, execution metadata is updated in `JobRepository`.

For example:

```text
validateFileStep
   transaction -> commit
        |
        v
importCustomersStep
   chunk 1 -> commit
   chunk 2 -> commit
   chunk 3 -> rollback (error)
        |
        v
JobExecution FAILED
```

In this example, the validation Step's transaction committed and the first two chunks of the import Step also committed. When the third chunk rolls back, previously committed changes are not automatically undone just because the Job failed.

If the business logic needs to undo the effects of earlier Steps when a later Step fails, you must design a compensation mechanism, intermediate states, or a saga workflow. Do not expect Spring Batch to automatically roll back all Job data as a single transaction.

## 7. Passing data between Steps

Sequential Steps often need to use results from a preceding Step. There are several ways to pass data, depending on data size and lifecycle.

### Use JobExecutionContext for small data

A Step can write intermediate results into `JobExecutionContext` for the next Step to read. For example, the validation Step stores the file version:

```java
@Component
public class ValidateFileTasklet implements Tasklet {

    @Override
    public RepeatStatus execute(
            StepContribution contribution,
            ChunkContext chunkContext) {

        JobExecution jobExecution = contribution
                .getStepExecution()
                .getJobExecution();

        jobExecution.getExecutionContext()
                .putString("validatedFileVersion", "v3");

        return RepeatStatus.FINISHED;
    }
}
```

The next Step can read the value using `@StepScope` and SpEL:

```java
@Bean
@StepScope
Tasklet importTasklet(
        @Value("#{jobExecutionContext['validatedFileVersion']}") String version,
        CustomerImportService importService) {

    return (contribution, chunkContext) -> {
        importService.importVersion(version);
        return RepeatStatus.FINISHED;
    };
}
```

If data is created in `StepExecutionContext`, you can use `ExecutionContextPromotionListener` to promote the keys to share up to `JobExecutionContext` when the Step completes. `JobExecutionContext` is suitable for small metadata, reference IDs, or intermediate results; do not store entire large datasets in the context.

### Use a database or file for large data

If the first Step produces millions of records for the next Step to process, store them in a staging table, file, or object storage. `JobExecutionContext` only needs to hold an identifier such as `stagingBatchId` or a file path. The next Step uses that identifier to read the data.

For example:

```text
validateFileStep
      |
      +--> save batchId to JobExecutionContext
      |
      v
importCustomersStep
      |
      +--> read staging data by batchId
      |
      v
generateReportStep
      |
      +--> aggregate by batchId
```

### JobParameters as shared input

If Steps all need a business date, file ID, or data range supplied by the caller when launching the Job, use `JobParameters`. These values describe the work to be run; `ExecutionContext` is for state or data generated during execution.

## 8. Restarting when a Step in the sequence fails

Spring Batch persists `JobInstance`, `JobExecution`, and `StepExecution` in `JobRepository`. When a `JobInstance` fails and is restarted with the same identifying `JobParameters`, the framework uses the persisted state to decide which Steps need to execute.

Normally, Steps that are already `COMPLETED` are skipped on restart. A failed Step can be re-executed if the Job allows restart and the Step's execution limit has not been exceeded. For example:

```text
First run:

validateFileStep       COMPLETED
        |
        v
importCustomersStep   FAILED
        |
        v
generateReportStep    not run yet

Restart same JobInstance:

validateFileStep       skipped
        |
        v
importCustomersStep   re-run/resume from checkpoint
        |
        v
generateReportStep    runs when import Step completes
```

For a chunk-oriented Step, a reader that supports state persistence can restore its checkpoint from `StepExecutionContext`. Committed chunks are preserved; the uncommitted portion may need to be reprocessed depending on reader and transaction state.

If you want a completed Step to run again every time the Job restarts, you can configure `allowStartIfComplete(true)` on that Step. Enable this only when the task can be repeated safely. For example, a Step that sends emails or creates non-idempotent transactions could cause duplicate side effects if re-run.

`startLimit(n)` can limit how many times a Step may be started within the same `JobInstance`. This configuration should be considered when a Step is expensive or unlimited retries are inappropriate.

## 9. Failed Steps and transition conditions

The `.start().next()` chain fits linear workflows. When you need to choose the next Step based on an outcome, you can define a flow based on `ExitStatus`.

For example, if validation succeeds then import; if it fails then transition to a Step that records the rejected file:

```java
@Bean
Job customerImportFlow(
        JobRepository jobRepository,
        Step validateFileStep,
        Step importCustomersStep,
        Step rejectFileStep) {

    return new JobBuilder("customerImportFlow", jobRepository)
            .start(validateFileStep)
                .on("COMPLETED").to(importCustomersStep)
            .from(validateFileStep)
                .on("FAILED").to(rejectFileStep)
            .end()
            .build();
}
```

This is a `FlowJob` with explicitly declared transitions. `on("COMPLETED")` and `on("FAILED")` match the Step's exit code. When building a real-world flow, you must account for all possible statuses and the behavior when no transition matches.

`BatchStatus` and `ExitStatus` are related but not identical:

- `BatchStatus` describes the execution lifecycle status such as `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`.
- `ExitStatus` describes the outcome code used in flow transitions, which may contain standard values or custom codes.

If a Step completes technically but needs to branch based on a business outcome, you can set a custom `ExitStatus` via a listener or appropriate logic and declare the corresponding transition. Do not use a custom code to hide a genuine error state.

## 10. Step ordering and business dependencies

When designing a Step sequence, each Step should have clear inputs and outputs. A downstream Step should depend only on data that the preceding Step has created and durably persisted.

Example of a reconciliation workflow:

| Step | Task | Output for next Step |
|---|---|---|
| `loadTransactionsStep` | Load source transactions into staging | `batchId` and load status |
| `validateTransactionsStep` | Check format, duplicate keys, and required fields | Valid/error counts, validation status |
| `reconcileTransactionsStep` | Reconcile against the target system | Reconciliation results table |
| `generateReconciliationReportStep` | Generate report and save results | Report path, completion status |

If an intermediate Step fails, subsequent Steps should not run with unready data. Step ordering must reflect actual dependencies, not merely alphabetical order or configuration file order.

Keep Steps relatively independent so they are easy to restart and change. If a single Step loads data, validates, reconciles, and generates reports all at once, splitting it into Steps with clear boundaries makes error isolation and operations much easier.

## 11. What happens if a Step has no data?

A Step can complete successfully even if there are no items to process. For example, the reader returns `null` on the first call because the file is empty. The Step may finish with `BatchStatus.COMPLETED` and `readCount` equal to 0.

If business rules require data to exist, a preceding validation Step should check this condition and fail the Job or set an appropriate `ExitStatus`. Do not assume that an import Step with zero items will automatically cause a reporting Step to be skipped.

In a basic sequential chain, if a Step completes normally, the next Step can still run even if the previous Step processed 0 items. If you want behavior to change based on item count, use explicit flow conditions, a listener, or persisted state data to decide.

## 12. Step names and stable metadata

A `Step` has a name stored in `JobRepository` metadata. The Step name is used to identify the `StepExecution` and support restart. Therefore:

- Give Steps clear, stable, business-meaningful names.
- Avoid dynamic names that change with timestamps or per-run data.
- Do not arbitrarily rename Steps in a Job that has execution history needing restart.
- Do not use the same Step name for two different pieces of work in the same Job flow.

When changing Job structure or Step names while an old `JobInstance` still needs to be restarted, you must consider metadata compatibility and procedures for handling existing executions.

## 13. Monitoring a multi-Step Job

`JobExplorer`, `JobRepository`, and listeners can help monitor the status of a Job and each Step. Key information to observe includes:

- `JobInstance` ID, `JobExecution` ID, and identifying `JobParameters`.
- Step order and the status of each `StepExecution`.
- Start time, end time, and duration of each Step.
- Read count, write count, filter count, skip count, and rollback count for chunk Steps.
- The last exception if a Step failed.
- Checkpoint and restart state if the Step supports it.

Logs should include the `JobExecution` ID, `StepExecution` ID, and business batch ID so events can be correlated across Steps. If a downstream Step is slow, per-Step metrics help pinpoint whether the bottleneck is in data reading, processing, database writing, or a dependent service.

## 14. Common mistakes when building sequential flows

**Assuming `.next()` always runs the next Step even if the previous Step failed:** in a basic sequential flow, a failed Step usually stops the Job. If you need error-branch handling, define transitions based on `ExitStatus`.

**Confusing bean initialization order with execution order:** execution order is determined by `start()` and `next()` or the flow definition.

**Assuming the entire Job runs in a single transaction:** each Step and each chunk has its own transaction boundary. Previously committed changes remain if a later Step fails.

**Passing large data via ExecutionContext:** the context is meant for small metadata and checkpoints. Use a database or file for large datasets, then pass a reference key.

**Changing identifying JobParameters on restart:** new identifying parameters create a new `JobInstance` instead of restarting the old instance.

**Assuming a completed Step always re-runs on restart:** by default, a `COMPLETED` Step is usually skipped. Use `allowStartIfComplete(true)` only when needed and when the task is safe to repeat.

**Letting a downstream Step run when data is not ready:** validate input conditions and dependencies before transitioning to the next Step.

**Renaming Steps arbitrarily:** old metadata may no longer match the new flow, causing issues with restarts and historical investigation.

## Conclusion

Sequential flow organizes a Job into a sequence of Steps executed in the order declared with `.start(stepA).next(stepB).next(stepC)`. Each Step has its own status and transaction boundary; if a Step fails, a basic sequential Job stops and later Steps do not run. When restarting the same `JobInstance`, completed Steps are typically skipped, while the remaining Steps rely on metadata and checkpoints. Small data between Steps can be passed through `JobExecutionContext`; large data should be stored in a database or file with a reference key passed along. When branching by outcome is needed, use Flow transitions based on `ExitStatus` rather than treating the `.next()` chain as an unconditional continuation.
