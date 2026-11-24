# Parent Job and Child Job

In Spring Batch, one Job can orchestrate another Job through `JobStep`. The Job acting as the orchestrator is called the **parent job**; the Job launched inside a Step of the parent is called the **child job**. This organization allows splitting a large batch workflow into smaller Jobs that can be reused and tracked with separate executions.

For example, a parent job handling an end-of-day settlement workflow can sequentially launch a transaction import child job, a reconciliation child job, and a report generation child job. Each child job remains an independent Spring Batch Job with its own name, JobParameters, JobInstance, JobExecution, and Steps.

## 1. What are Parent Job and Child Job?

The parent job is the Job that orchestrates the overall workflow. A special Step in the parent, called `JobStep`, launches the child job using `JobLauncher`.

The child job is the Job invoked from `JobStep`. It can be defined like an ordinary Job and can also be launched independently from a scheduler, an API, or another parent job.

Workflow example:

```text
monthEndParentJob
        |
        v
  prepareBatchStep
        |
        v
  importTransactionsJobStep
        |       \
        |        +--> importTransactionsJob (child job)
        |                  |
        |                  +--> readTransactionsStep
        |                  +--> validateTransactionsStep
        |                  +--> persistTransactionsStep
        |
        v
  reconcileAccountsJobStep
        |       \
        |        +--> reconcileAccountsJob (child job)
        |                  |
        |                  +--> calculateBalancesStep
        |                  +--> compareLedgerStep
        |
        v
  generateReportStep
        |
        v
       End
```

The parent job does not directly invoke methods of individual Steps inside the child job. It launches the child job as a unit of work via `JobStep`. As a result, the child job can maintain its own structure and execution metadata.

## 2. When Should You Use a Child Job?

A child job is useful when a workflow has groups of work that are relatively independent, reusable, or require separate tracking.

Common cases:

- **Workflow reuse:** multiple parent jobs need to run the same import or reconciliation workflow already defined as a child job.
- **Modularizing a large workflow:** each child job handles a business domain, making configuration and operations easier to manage.
- **Separate execution tracking:** the child job has its own JobExecution, StepExecution, and history in `JobRepository`.
- **Independent execution:** the child job can be run separately for testing, re-operation, or serving another flow.
- **Separating processing policies:** the child job can have its own chunk size, retry, skip, listener, and restart policy.

Do not create a child job just to split a Job into many small parts if those parts do not need independent boundaries. If the tasks are simply sequential Steps in the same workflow, a single Job with multiple Steps is usually simpler.

## 3. How Does JobStep Connect Parent and Child Jobs?

`JobStep` is a type of Step used to launch another Job. When the parent job reaches `JobStep`, Spring Batch uses `JobLauncher` to launch the child job and uses `JobParametersExtractor` to create `JobParameters` for the child from the parent's execution.

Key components:

- **Parent Job:** defines the overall flow.
- **JobStep:** represents the point in the parent flow where the child job is launched.
- **Child Job:** the Job executed by `JobStep`.
- **JobLauncher:** performs the call to launch the child job.
- **JobParametersExtractor:** transfers or extracts parameters from the parent execution to create parameters for the child job.
- **JobRepository:** stores metadata of both parent and child executions.

In Spring Batch 5, you can declare a `JobStep` using `JobStepBuilder`:

```java
@Bean
Step importTransactionsJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importTransactionsJob,
        JobParametersExtractor childJobParametersExtractor) {

    return new JobStepBuilder(new StepBuilder(
            "importTransactionsJobStep", jobRepository))
            .job(importTransactionsJob)
            .launcher(jobLauncher)
            .parametersExtractor(childJobParametersExtractor)
            .build();
}
```

This `JobStep` is placed into the parent flow like a regular Step. When executed, it launches `importTransactionsJob` using `JobLauncher` and the parameters produced by the extractor.

## 4. Configuring JobParametersExtractor

Parent and child are two independent Jobs, so you must explicitly define which parameters the child receives. `JobParametersExtractor` is responsible for creating the child's `JobParameters` from the `JobStep`'s `StepExecution`.

You can use `DefaultJobParametersExtractor` when transferring existing keys meets your needs:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();

    extractor.setKeys(new String[] {
            "businessDate",
            "batchId",
            "sourceSystem"
    });

    return extractor;
}
```

The key list represents the values to pass to the child. Values can be taken from execution data supported by the extractor, such as the parent's `JobParameters` or `StepExecution`'s `ExecutionContext` according to the implementation's contract. If you need complex mapping, key renaming, additional parameter creation, or precise control of identifying flags, you can implement a custom `JobParametersExtractor`.

Do not assume that all `JobParameters` of the parent must be passed down to the child. The child should only receive the parameters it genuinely needs for its work. Explicit passing helps avoid implicit coupling and reduces the risk of two parents unintentionally creating the same child `JobInstance`.

### Passing Data Generated in a Parent Step

If the parent generates `batchId` in a Step before `JobStep`, you can store that value in `StepExecutionContext` or `JobExecutionContext`, and configure the extractor to pick up the corresponding key to build `JobParameters` for the child.

Data flow example:

```text
Parent prepareBatchStep
        |
        +--> creates batchId = BATCH-20261115-01
        |
        v
Parent JobExecutionContext
        |
        v
JobParametersExtractor
        |
        v
Child JobParameters
  batchId=BATCH-20261115-01
  businessDate=2026-11-15
```

For large data, pass only an identifier such as `batchId`, a file path, or a snapshot ID. Actual data should be stored in a database, file, or object storage; never put an entire list of records into `JobParameters`.

## 5. Defining a Child Job as an Independent Job

A child job is declared like an ordinary Job and may contain one or more Steps:

```java
@Bean
Job importTransactionsJob(
        JobRepository jobRepository,
        Step readTransactionsStep,
        Step validateTransactionsStep,
        Step persistTransactionsStep) {

    return new JobBuilder("importTransactionsJob", jobRepository)
            .start(readTransactionsStep)
            .next(validateTransactionsStep)
            .next(persistTransactionsStep)
            .build();
}
```

The child job can use chunk-oriented Steps, Tasklet Steps, listeners, retry/skip, and `ExecutionContext` like any other Job. Being called from a parent does not change how it is defined internally.

The parent job can declare a sequence of Steps in which `JobStep` serves as one link:

```java
@Bean
Job monthEndParentJob(
        JobRepository jobRepository,
        Step prepareBatchStep,
        Step importTransactionsJobStep,
        Step reconcileAccountsJobStep,
        Step generateReportStep) {

    return new JobBuilder("monthEndParentJob", jobRepository)
            .start(prepareBatchStep)
            .next(importTransactionsJobStep)
            .next(reconcileAccountsJobStep)
            .next(generateReportStep)
            .build();
}
```

In this flow, the parent runs `prepareBatchStep`, then launches the import child, then the reconcile child, and finally generates the report if previous Steps complete according to the normal flow.

## 6. Parent and Child Have Separate JobInstance and JobExecution

The parent job and child job do not share a single `JobInstance`. Each Job has its own name, and a `JobInstance` is identified by the Job name together with the identifying `JobParameters` of that Job itself.

Example:

```text
Parent:
  monthEndParentJob
  businessDate=2026-11-15
      -> Parent JobInstance P1
      -> Parent JobExecution P-E1

Child:
  importTransactionsJob
  businessDate=2026-11-15
  batchId=BATCH-20261115-01
      -> Child JobInstance C1
      -> Child JobExecution C-E1
```

`JobStep` in the parent has its own `StepExecution` to record the child invocation. The child has its own `JobExecution` and `StepExecution`s. `JobRepository` stores these metadata separately, but they can be queried to correlate the orchestration process.

Important consequence: if two different parent jobs launch the same child job with the same identifying parameters, they may target the same child `JobInstance`. If the child is currently running, the later launch may be rejected because an execution is already running. If the child has already completed, launching with the same identifying parameters may be rejected because the instance is already complete. Therefore, design child identity according to the exact unit of work to be performed.

If each parent batch needs an independent child execution, include a stable business batch identifier in the child's identifying parameters. That identifier must remain unchanged across restarts of the same parent; do not generate a new UUID on every retry.

## 7. Parent JobParameters and Child JobParameters

The parent's `JobParameters` do not automatically become all of the child's `JobParameters` under a universal business rule. `JobStep` uses an extractor to create child parameters. You need to decide:

- Which parameters are inherited from the parent?
- Which parameters are taken from `JobExecutionContext` or `StepExecutionContext`?
- Which values are identifying for the child?
- Does the child need its own parameters that do not exist on the parent?
- Which values must remain immutable across restarts?

For example, the parent has `requestedBy`, `businessDate`, and `batchId`. The import child may only need `businessDate`, `batchId`, and `sourceSystem`. `requestedBy` may not be needed if the child does not record the requester.

The identifying flag is evaluated according to the child job's definition. A parameter that is identifying on the parent does not necessarily play the same role on the child if a custom extractor creates new `JobParameters`. Clearly define the child identity to avoid accidentally merging distinct runs into the same instance or creating a new instance on restart.

## 8. ExecutionContext Between Parent and Child Is Not Automatically Shared

Parent and child have separate `JobExecution`s, so the parent's `JobExecutionContext` is not an automatically shared map with the child. Passing data to the child requires an intentional mechanism:

1. The parent stores values to share in `JobParameters` or `ExecutionContext`.
2. `JobParametersExtractor` retrieves selected keys from the parent's execution.
3. The extractor creates `JobParameters` for the child.
4. The child reads the parameters via `JobParameters` or `@StepScope`.
5. If the child produces results for the parent to use later, the child saves them in a database or persistent data store keyed by a shared reference.

For example, the child generates a report and saves `reportLocation` to a results table keyed by `batchId`. After `JobStep` completes, the next Step of the parent queries that table by `batchId`. This approach is much clearer than trying to share internal objects or contexts directly between two `JobExecution`s.

## 9. Child Job Success, Failure, and Parent Status

`JobStep` observes the child job's execution outcome and reflects that outcome onto the parent's `StepExecution`. If the child completes successfully, `JobStep` can complete and the parent flow moves to the next Step. If the child fails, `JobStep` normally fails as well and the parent job stops at that point, unless the parent flow has a transition handling the corresponding outcome.

```text
Parent Job
    |
    v
Child JobStep
    |
    +---- Child COMPLETED ---> Parent JobStep COMPLETED
    |                                  |
    |                                  v
    |                            Next Parent Step
    |
    +---- Child FAILED -------> Parent JobStep FAILED
                                       |
                                       v
                                Parent Job FAILED
```

You can declare conditional flows based on `JobStep`'s `ExitStatus`, just like other Steps. For example, a failed import child can transition to a Step that records the failed batch or performs compensation. Distinguish between `BatchStatus` and `ExitStatus`: `BatchStatus` describes execution state; `ExitStatus` is the result code used in flow transitions.

## 10. Restarting Parent Job and Child Job

Parent and child have separate execution histories. When the parent fails at `JobStep`, check both the parent `StepExecution` status and the child `JobExecution` status to determine how to restart safely.

### Child Failed

If the child job fails, you can fix the root cause and then restart the parent job with the same identifying `JobParameters`. When the parent resumes at `JobStep`, the child can be re-launched with the same identifying parameters to restart the child `JobInstance`, provided the child allows restart and necessary metadata remains intact.

### Child Already Completed

A scenario requiring attention is when the child has completed, but the parent was stopped or encountered an issue before the parent's `JobStep` was recorded as completed. When the parent restarts, `JobStep` may attempt to launch the child with the same identifying parameters. A child `JobInstance` that is already `COMPLETED` cannot be restarted like a failed instance; re-launching may be rejected because the instance is already complete.

Therefore, design and test the scenario of an interruption occurring between child completion and parent `JobStep` completion. You may need a mechanism to reconcile the existing child `JobExecution` to confirm the child succeeded and allow the parent to proceed, or an appropriate orchestration/recovery strategy. Do not solve this by automatically adding a new timestamp to identifying parameters, because that could create a new child `JobInstance` and re-execute the entire task.

### Child Committed Partially Then Failed

If the child uses chunk processing, already-committed chunks are preserved. When restarting the child with the same `JobInstance`, a reader supporting checkpointing can resume from the saved state. Side effects outside transactions require idempotency because they may already have occurred before the error was recorded.

### Already-Completed Steps in the Parent

When restarting the parent with the same `JobInstance`, Steps that are already `COMPLETED` are normally skipped. An already-completed `JobStep` will not run again unless configured with `allowStartIfComplete(true)`. Enable that option only when repeated child invocation is safe and intentional.

## 11. Idempotency and Side Effects of Child Jobs

Child jobs often process large business datasets or call external systems. A parent restart or child retry can cause part of the work to be executed again. Therefore, the child must be designed to be idempotent around its business identifier.

Some measures:

- Use `batchId`, `sourceFileId`, or a stable business key to identify the same piece of work.
- Use unique constraints or upserts to avoid writing duplicate records.
- Use an idempotency key when calling APIs to create transactions or send requests to partner systems.
- Store status and confirmation codes from the target system to reconcile when responses are lost.
- Write events to be emitted into a transactional outbox and have a safely retryable publisher handle delivery.
- Separate preparation, execution, and confirmation operations into Steps with durable outputs.

Do not assume the parent job and child job are inside the same transaction. The parent `JobStep`'s transaction and the chunk transactions inside the child do not form a distributed transaction spanning both Jobs. Data already committed in the child can still persist if the parent fails afterward.

## 12. Does the Child Job Run Synchronously or Asynchronously?

`JobStep` uses `JobLauncher` to launch the child job. How `JobLauncher` executes depends on the launcher and executor configuration. With a synchronous launcher, the call typically waits for the child to finish before `JobStep` completes. If using an asynchronous launcher, understand the returned status and how the parent tracks the running child.

If the business requirement is that the parent must wait for the child to finish before running the next Step, ensure the launch and orchestration mechanism actually provides that waiting behavior. Do not simply configure an asynchronous executor and assume the parent automatically synchronizes the result.

If the goal is to launch multiple independent Jobs in parallel and aggregate results afterward, you may need a different orchestration model than sequential `JobStep`s, such as partitioning, remote orchestration, or a Job managing the states of child executions. Choose the implementation based on synchronization requirements, concurrency limits, and recoverability.

## 13. Monitoring Parent and Child in JobRepository

`JobRepository` stores separate metadata for each `JobInstance`, `JobExecution`, and `StepExecution`. When investigating a parent-child workflow, track:

- Parent `JobInstance` ID and Parent `JobExecution` ID.
- `JobStep` name and `StepExecution` ID in the parent.
- Child job name, Child `JobInstance` ID, and Child `JobExecution` ID.
- Child `JobParameters`, especially identifying parameters.
- Status of each Step inside the child.
- Start time, end time, exception, and `ExitStatus`.
- Shared business identifier such as `batchId` to correlate logs and data between both Jobs.

You can use `JobExplorer` to read `JobExecution` and `StepExecution` information for monitoring dashboards. Logs should record the parent execution ID, child execution ID, and business key so the entire workflow can be traced.

Do not directly modify the `BATCH_*` metadata tables to force the child or parent to change status. Metadata contains the history and checkpoints the framework needs for restart. Use appropriate APIs and operational procedures instead.

## 14. When to Use JobStep vs. Multiple Steps in One Job?

| Need | Suitable Organization |
|---|---|
| Parts are sequential steps of the same workflow, no separate Job identity needed | Multiple Steps in the same Job |
| A sub-workflow is reused by multiple parents | Child job via `JobStep` |
| Want the child to have its own `JobInstance`, `JobExecution`, and history | Child job via `JobStep` |
| Only need branching based on Step outcome | Flow transitions within the same Job |
| Need to split large data into parts processed in parallel | Partitioning or an appropriate parallel processing model |
| Need to orchestrate multiple independent Jobs and track status asynchronously | Orchestration with dedicated state management |

`JobStep` introduces an extra layer of metadata and requires designing `JobParametersExtractor`. If you do not need a separate identity or lifecycle for the sub-workflow, adding a Step in the same Job is usually easier to understand and operate.

## 15. Common Mistakes When Designing Parent-Child Jobs

**Assuming a child job is just another Step:** the child has its own `JobInstance`, `JobExecution`, and `StepExecution`s. `JobStep` is the parent's Step used to launch an independent Job.

**Not configuring JobParametersExtractor:** the child may miss required parameters or receive parameters out of business scope.

**Passing all parent parameters down to the child:** creates implicit coupling and can make the child's identity incorrect. Pass only the keys the child actually needs.

**Not designing identifying parameters for the child:** multiple parents may unintentionally target the same child `JobInstance`, or a new business run may be treated as an already-completed old instance.

**Generating a new timestamp on every restart:** the child becomes a new `JobInstance` and may reprocess from the beginning instead of restarting the old instance.

**Assuming parent's ExecutionContext is shared with the child:** two `JobExecution`s have separate contexts. Pass data through `JobParameters` or a persistent data store.

**Assuming the entire parent-child lies in one transaction:** Step/chunk transactions are separate; data already committed in the child does not automatically roll back when the parent fails.

**Ignoring the case where child completes but parent has not recorded Step completion:** test recovery at this boundary and have a way to reconcile executions.

**Using JobStep for every small group of tasks:** if only a simple sequence of Steps is needed, a single Job with multiple Steps may be less complex.

## Conclusion

The parent job orchestrates the overall workflow; the child job is an independent Job launched from `JobStep`. `JobStep` uses `JobLauncher` and `JobParametersExtractor` to pass required parameters to the child. Parent and child have separate `JobInstance`, `JobExecution`, `StepExecution`, and `ExecutionContext`; data is shared only through parameters or an explicitly designed data store. On restart, keep identifying parameters stable, check child status, and design idempotency for side effects. Use a child job when reusability, independent lifecycle, or separate execution history is needed; if you only need sequential steps in one workflow, multiple Steps in the same Job are usually the simpler choice.
