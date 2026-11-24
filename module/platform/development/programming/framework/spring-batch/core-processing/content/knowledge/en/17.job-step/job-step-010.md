# Using JobStep for Independent Workflows

In Spring Batch, `JobStep` allows one Job to launch another Job as a Step in a Job flow. The outer Job acts as the orchestrator; the inner invoked Job is usually called the *child job*. This organization is useful when a large workflow consists of multiple independent batch workflows that can be reused or need to be managed with separate lifecycles.

For example, an end-of-day data aggregation Job can sequentially invoke an import Job, a reconciliation Job, and a report generation Job. Each child job still has its own Step structure, `JobParameters`, `JobInstance`, and `JobExecution`. The parent job tracks the child job invocation through a `JobStep`-type Step.

`JobStep` fits when you want to reuse an already-defined Job, separate responsibilities across workflows, or keep execution metadata of each workflow separate. It is not merely calling a Java method: `JobStep` uses `JobLauncher` and `JobRepository` to launch the child job through Spring Batch's mechanism.

## 1. What is JobStep?

`JobStep` is an implementation of `Step` whose role is to launch another Job. Inside the parent Job, `JobStep` appears like a normal Step; when this Step executes, it calls `JobLauncher` to run the child Job.

```text
Parent Job: dailySettlementJob
    |
    +--> Step: prepareSettlementStep
    |
    +--> JobStep: importTransactionsJobStep
    |       |
    |       +--> Child Job: importTransactionsJob
    |               +--> extractTransactionsStep
    |               +--> normalizeTransactionsStep
    |
    +--> JobStep: reconcileAccountsJobStep
    |       |
    |       +--> Child Job: reconcileAccountsJob
    |               +--> compareBalancesStep
    |               +--> recordDifferencesStep
    |
    +--> Step: publishSummaryStep
```

In the diagram, `dailySettlementJob` does not need to directly contain every detailed Step of the two sub-workflows. It simply declares two `JobStep`s to invoke the corresponding Jobs. Each child Job can be developed, tested, and reused independently.

A `JobStep` has these main components:

- The child Job to be launched.
- `JobLauncher` executing the launch request.
- `JobParametersExtractor` creating `JobParameters` for the child Job from the parent Job run's metadata.
- `JobRepository` storing metadata for the parent Step and the child Job's `JobExecution`s per repository configuration.

## 2. Parent Job and Child Job Have Separate Executions

The most important point when using `JobStep` is that the child Job is genuinely launched as a Job. It has its own `JobInstance` and `JobExecution`, rather than being extra Steps inside the parent Job's same `JobExecution`.

```text
Parent JobExecution #100
  |
  +-- StepExecution: prepareSettlementStep
  |
  +-- StepExecution: importTransactionsJobStep
        |
        +-- Child JobExecution #205
              |
              +-- StepExecution: extractTransactionsStep
              +-- StepExecution: normalizeTransactionsStep
```

Parent `JobExecution` stores the parent Job's history. `JobStep`'s `StepExecution` records that wrapper Step's execution. The child Job has its own `JobExecution` with its own `StepExecution`s.

Therefore, when investigating failures, distinguish three layers of metadata:

1. `JobExecution` of the parent Job.
2. `StepExecution` of `JobStep` in the parent Job.
3. `JobExecution` and `StepExecution` of the child Job.

The child Job also has its own `JobInstance`, determined by the child Job name and the identifying `JobParameters` passed in by `JobStep`. Two different parent Jobs can accidentally launch the same child `JobInstance` if they pass the same identifying parameter set for the same child Job.

## 3. Configuring JobStep in Java

In modern Spring Batch, you can use `JobStepBuilder` to create a Step that launches a child Job. Example:

```java
@Bean
public Step importTransactionsJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importTransactionsJob,
        JobParametersExtractor childParametersExtractor) {

    return new JobStepBuilder(new StepBuilder("importTransactionsJobStep", jobRepository))
            .job(importTransactionsJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

In this configuration:

- `new StepBuilder("importTransactionsJobStep", jobRepository)` creates the wrapper Step definition in the parent Job.
- `.job(importTransactionsJob)` specifies the child Job to run.
- `.launcher(jobLauncher)` supplies the component that launches the child Job.
- `.parametersExtractor(childParametersExtractor)` defines the `JobParameters` passed to the child Job.
- `.build()` builds the `JobStep` to register into the parent Job.

The child Job must be declared as an independent `Job` bean. `JobStep` only references and launches that Job; it does not create the child Steps itself.

Builder APIs can change across Spring Batch versions. For projects using a different version, use the builders/constructors matching your actual dependencies. The principle remains configuring the child Job, `JobLauncher`, and `JobParametersExtractor` for `JobStep`.

## 4. Passing JobParameters to the Child Job

The child Job typically needs inputs identical or related to the parent Job, such as business date, data source code, or file path. `JobParametersExtractor` decides which parameters are passed to the child Job.

Example configuring `DefaultJobParametersExtractor` to select keys to forward:

```java
@Bean
public JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor = new DefaultJobParametersExtractor();
    extractor.setKeys(new String[] {
            "businessDate",
            "sourceSystem",
            "inputFile"
    });
    return extractor;
}
```

Then `JobStep` uses this extractor when launching the child Job. Explicitly declare the keys the child Job needs rather than relying on an implicit assumption about passed parameters.

`DefaultJobParametersExtractor` is the standard implementation for extracting parameters from the parent execution's metadata by configured keys. If you need to rename keys, create new parameters, or apply different identifying rules, you can implement a custom `JobParametersExtractor`.

### Customizing Parameters for the Child Job

Sometimes the child Job needs different parameter names than the parent Job. For example, the parent Job uses `businessDate`, while the child Job requires `settlementDate`. You can implement a custom extractor:

```java
public class SettlementParametersExtractor implements JobParametersExtractor {

    @Override
    public JobParameters extractJobParameters(
            Job job,
            StepExecution stepExecution) {

        String businessDate = stepExecution.getJobExecution()
                .getJobParameters()
                .getString("businessDate");

        if (businessDate == null || businessDate.isBlank()) {
            throw new IllegalArgumentException("businessDate is required");
        }

        return new JobParametersBuilder()
                .addString("settlementDate", businessDate, true)
                .addString("parentJobName",
                        stepExecution.getJobExecution().getJobInstance().getJobName(), false)
                .toJobParameters();
    }
}
```

The `JobParametersExtractor` method receives the child Job and the parent `JobStep`'s `StepExecution`. From there, the extractor can read `JobParameters` or `ExecutionContext` of the parent execution to build the appropriate parameter set.

In this example, `settlementDate` is an identifying parameter of the child Job; `parentJobName` only serves traceability and is marked non-identifying. How parameters are marked must be based on the child Job's business semantics.

## 5. Child JobInstance and Parameter Identity

The child Job's `JobInstance` is determined by the child Job name and the identifying `JobParameters` generated by the extractor. The parent Job's `JobInstance` does not automatically become the child Job's `JobInstance`.

For example, the parent Job runs for date `2026-11-15` and the extractor passes `settlementDate=2026-11-15` to the child Job:

```text
Parent JobInstance: dailySettlementJob / businessDate=2026-11-15
        |
        +--> JobStep: importTransactionsJobStep
                 |
                 +--> Child JobInstance:
                        importTransactionsJob / settlementDate=2026-11-15
```

If two different parent Jobs both invoke `importTransactionsJob` with `settlementDate=2026-11-15` and no other identifying parameters, they will both target the same child `JobInstance`. If that `JobInstance` is already complete, the next launch may be rejected because the instance is complete. If it is currently running, an exception reporting an already-running execution may be thrown.

Decide clearly which logical unit of work the child Job represents:

- If the child Job must process exactly once per business date, only business date and related business keys should identify the instance.
- If the child Job must run separately per tenant or data source, include the tenant/source key in identifying parameters.
- If each parent invocation genuinely needs an independent child run, pass a stable business request ID for that request. Do not add a random timestamp merely to dodge duplicate-instance errors.

Restarts must preserve the child Job's identifying parameters to resume the same child `JobInstance`. Creating a new identifying parameter usually equates to creating a new logical unit of work, not restarting the old one.

## 6. JobStep and Parent Job Restart

`JobStep` has `StepExecution` metadata in the parent Job and launches the child Job using `JobLauncher`. If the child Job fails, the parent Job's `JobStep` execution does not complete normally either. When the parent Job is restarted, `JobStep` can execute again and request launching the child Job with the `JobParameters` produced by the extractor.

The outcome of the re-launch depends on the child `JobInstance` state:

- If the child Job failed and is restartable, `JobLauncher` can create a new `JobExecution` on the same child `JobInstance`.
- If the child Job is still running, a duplicate launch request may be rejected.
- If the child Job already completed with the same identifying parameters, re-running may be rejected because the `JobInstance` is already complete.
- If the extractor generates different identifying parameters, `JobLauncher` may create a new child `JobInstance`; this may be wrong if the goal was to restart the previous work.

Therefore, `JobParametersExtractor` must produce stable outputs across restarts of the parent Job. Do not use the parent's `JobExecutionId` as an identifying parameter for the child if the goal is to restart the old child `JobInstance`: the parent execution ID changes across restarts.

If the child Job already completed yet the parent Job failed later in another Step, when restarting the parent Job, the already-completed `JobStep` Step is normally skipped under Spring Batch restart rules. If `JobStep` is configured with `allowStartIfComplete(true)`, it may run again; in that case the child Job may reject it because `JobInstance` is already complete. Enable this option only when re-running behavior has been explicitly designed.

## 7. Configuring a Parent Job Calling Multiple Child Jobs

A parent Job can invoke multiple child Jobs sequentially using multiple `JobStep`s:

```java
@Bean
public Job dailySettlementJob(
        JobRepository jobRepository,
        Step prepareSettlementStep,
        Step importTransactionsJobStep,
        Step reconcileAccountsJobStep,
        Step publishSummaryStep) {

    return new JobBuilder("dailySettlementJob", jobRepository)
            .start(prepareSettlementStep)
            .next(importTransactionsJobStep)
            .next(reconcileAccountsJobStep)
            .next(publishSummaryStep)
            .build();
}
```

This flow allows extracting each sub-workflow into a separate Job while the parent Job maintains the overall orchestration order. If one `JobStep` fails, subsequent Steps of the parent Job do not continue along the default sequential flow.

You can use conditional transitions or deciders between `JobStep`s to choose a child Job based on the outcome of the previous workflow. For example, run the reconciliation Job only when the import Job completes with an appropriate exit code.

## 8. Tracking Child Job Status

`JobStep` is a Step in the parent Job, yet the child Job has its own `JobExecution`. When investigating or building a dashboard, display info from both parent `StepExecution` and child `JobExecution`.

Useful details include:

| Info | Meaning |
|---|---|
| Parent `JobExecution` ID | Run of the orchestrating Job |
| Parent `JobStep` `StepExecution` ID | Execution of the wrapper Step |
| Child `JobInstance` ID | Logical unit of work of the child Job |
| Child `JobExecution` ID | Specific run of the child Job |
| Child `BatchStatus` | Lifecycle status of the child Job |
| Child `ExitStatus` | Exit outcome of the child Job |

You can use `JobExplorer` to query child Job metadata by ID if the application stores or can retrieve the corresponding ID. When designing logging, record the child Job name, `JobInstance` ID, and `JobExecution` ID so operators can trace both levels.

Do not look solely at parent `JobStep` status while ignoring child `JobExecution`. If the child Job fails, the child execution provides details on which Step in the sub-workflow encountered the error.

## 9. Does JobStep Run Synchronously or Asynchronously?

`JobStep` uses `JobLauncher` to launch the child Job. Waiting behavior depends on the launcher's configuration. With a synchronous launcher, the call normally returns only after the child Job finishes; `JobStep` can rely on the final status to determine the parent Step's outcome.

If an asynchronous launcher is used, `run()` may return while the child Job is still running. In that case, carefully review how `JobStep` determines its outcome and how the parent flow waits for/observes the child execution. Do not assume the parent Step automatically waits for the child Job to finish simply because `JobLauncher` returns a `JobExecution`.

With a typical sequential `JobStep` structure, a synchronous launcher is the clearer and more common choice. If the goal is to launch a background child Job and let the parent Job continue immediately, design a dedicated asynchronous orchestration mechanism, store the child execution ID, and define how the parent awaits or receives results. Otherwise, the parent Job may transition forward while the child Job is not yet finished.

## 10. How Does JobStep Differ from Flow and Regular Steps?

The mechanisms below all help organize Jobs, yet their execution boundaries differ:

| Mechanism | Unit Invoked | Execution Metadata |
|---|---|---|
| Regular Step | Tasklet or chunk processing | `StepExecution` belonging to current `JobExecution` |
| Flow within a Job | A sequence/branch of Steps in the same Job flow | `StepExecution`s belonging to that Job's `JobExecution` |
| `JobStep` | Another Job launched via `JobLauncher` | Separate child `JobInstance` and `JobExecution`; parent has a wrapper `StepExecution` |
| Partitioning | Multiple processing partitions of one Step | Separate `StepExecution` per partition, attached to current Job's `JobExecution` |

Use a Flow when you only want to group and reuse an orchestration segment of Steps within the same Job. Use `JobStep` when you need to invoke an independent Job with its own `JobParameters`, `JobInstance`, `JobExecution`, and lifecycle.

Use partitioning when you need to split a dataset into multiple parts for parallel or distributed processing. Partitioning does not mean invoking an independent Job for each partition.

## 11. How Does JobStep Differ from Manually Calling JobLauncher in a Tasklet?

Technically, a Tasklet can inject `JobLauncher` and invoke another Job. However, if the goal is to model a child Job as a Step inside a parent Job, `JobStep` expresses that relationship clearly and integrates with Spring Batch's flow builder.

With `JobStep`, configuration explicitly declares the child Job, launcher, and parameters extractor. The framework manages the wrapper Step's lifecycle and performs the child Job launch via the `JobStep` mechanism.

If you manually invoke `JobLauncher` inside a Tasklet, the application must handle many more details itself, such as parameter extraction, exception classification, recording the child execution, status synchronization, and restarts. Manual invocation may fit a specialized integration, but should not be used merely to replace `JobStep` in a normal nested-Job flow.

## 12. Extracting Child Jobs for Reusability and Independent Management

One benefit of `JobStep` is that a child Job can be used from multiple parent Jobs or launched independently by another scheduler/API. For example, `importTransactionsJob` can be called from the end-of-day settlement Job, yet also run independently to re-import data from a specific source.

For safe reuse:

- Give the child Job a stable name that accurately describes its responsibility.
- Define clear `JobParameters`, including identifying parameters representing the business task.
- Do not depend on mutable fields of a parent Job or singleton beans to retrieve data.
- Pass data via `JobParameters` or store it in a shared repository/service.
- Design the child Job to be independently restartable and have idempotency rules for side effects.
- Avoid making the child Job depend on execution order or state that exists only in the parent Job's memory.

A well-reusable child Job should have a clear input/output contract. The parent Job only needs to know which parameters to pass and the meaning of the child Job's outcomes, without knowing every internal implementation detail.

## 13. Common Mistakes When Using JobStep

### Not Passing Enough JobParameters

The child Job needs `businessDate`, yet the extractor does not forward that key. The child Job may fail parameter validation or process wrong default data. Explicitly declare required keys and verify the actual parameter set produced.

### Unintended Duplicate Child JobInstance

Two different parent Jobs invoke the same child Job with the same identifying parameters. If the child Job already completed, the next call may be rejected. Design identifying parameters around business keys and decide explicitly whether to share the same `JobInstance`.

### Using Parent Execution ID as a Child Identifying Parameter

The parent `JobExecution` ID changes on restart. If passed as an identifying parameter, the child `JobInstance` can change across restarts and create unintended new work. Use stable business keys.

### Assuming JobStep and Child Job Share the Same StepExecution

The child Job has its own `JobExecution` and `StepExecution`s. When debugging, query the right metadata at either the parent or child level.

### Using an Asynchronous Launcher Without a Waiting Mechanism

`JobStep` may receive the `JobExecution` back while the child is still running if the launcher is asynchronous. The parent flow needs an explicit waiting or result-coordination mechanism.

### Configuring a Child Job Like a Regular Step

A child Job does not automatically become part of a parent Job merely because a `Job` bean exists. You must create a `JobStep` and register that `JobStep` in the parent Job's flow.

### Swallowing Child Job Errors

If the child Job fails, let that outcome reflect onto `JobStep` and the parent Job according to flow policy. Do not catch the exception and proceed as if the sub-workflow succeeded.

## 14. Testing JobStep

When testing `JobStep`, verify behavior of both parent and child:

- The parent Job launches the right child Job.
- `JobParametersExtractor` forwards all required keys and marks identifying flags properly.
- The child Job creates `JobInstance` and `JobExecution` with expected parameters.
- When the child Job succeeds, `JobStep` and the parent flow take the right forward branch.
- When the child Job fails, parent Step/Job reflect the appropriate outcome.
- When the parent Job restarts after a child failure, the child `JobInstance` is restarted with stable identifying parameters.
- When the child Job is already complete, repeated invocations follow duplicate/already-complete rules properly.
- Two parent Jobs do not accidentally collide on the same child `JobInstance` if business requires independent runs.

For example, an integration test can run the parent Job with a `businessDate` parameter, then use `JobExplorer` to inspect the child Job's metadata. Check both the child's `JobInstance` ID and `JobExecution` ID to confirm the nested Job relationship was created properly.

## 15. Common Misconceptions

**Treating JobStep as a Step containing multiple child Steps in the same JobExecution.** `JobStep` launches an independent Job with its own `JobInstance` and `JobExecution`.

**Assuming JobParameters are automatically passed intact.** Configure `JobParametersExtractor` to define the child Job's parameters.

**Assuming the child's JobInstance is the same as the parent's JobInstance.** The two Jobs have separate identities; child identity is based on the child Job name and passed identifying parameters.

**Using JobExecution ID as a business key for the child.** Execution ID changes across restarts. Use a stable business key if you want to resume the same logical work.

**Using JobStep just to group Steps in the same Job.** If you do not need a separate `JobExecution`, a Flow or standard Job flow structure may be simpler.

**Not tracking the child JobExecution.** Parent `StepExecution` is only a wrapper; the child's metadata reveals details of the Steps inside the child Job.

## 16. How to Design Independent Workflows Using JobStep

Extract a workflow into a child Job when it has a clear responsibility, defined inputs/outputs, and can be reused or operated independently. Inside the parent Job, create a `JobStep` pointing to the child Job, supplying `JobLauncher` and an explicit `JobParametersExtractor`. Choose identifying parameters based on stable business keys so the child `JobInstance` is not duplicated or altered unexpectedly on restart.

Track both parent `StepExecution` and child `JobExecution`, and inspect the child Job's status when investigating errors. Use `JobStep` when an independent Job boundary is needed; use `Flow` when you only need to organize Steps within the same Job, and use partitioning when you need to split the work of a single Step. This division enables assembling large workflows from small, reusable Jobs with clearly managed separate lifecycles.
