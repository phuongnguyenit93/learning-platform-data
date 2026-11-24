# JobStep: Running a Child Job Inside a Step

In Spring Batch, a job is typically composed of multiple steps. When a large workflow needs to reuse an existing job, or needs to split a process into independent parts that can be operated separately, you can use `JobStep` to run a **child job as a step of a parent job**.

`JobStep` acts as a bridge between two orchestration levels: the parent job treats running the child job as a step; inside that step, `JobLauncher` launches the child job with a set of `JobParameters` created by `JobParametersExtractor`. The child job has its own lifecycle, `JobInstance`, `JobExecution`, and step executions in the metadata repository.

## 1. What is JobStep?

`JobStep` is an implementation of `Step` used to launch another `Job`. Instead of directly declaring a tasklet or chunk reader/processor/writer, this step delegates processing to a child job.

Example of an overall workflow:

```text
ParentJob: dailySettlement
    |
    v
PrepareStep
    |
    v
RunValidationJobStep  ----> ChildJob: validateOrders
    |                              |
    |                              +--> ReadOrdersStep
    |                              +--> ValidateStep
    |                              +--> SaveValidationResultStep
    |
    v
RunSettlementJobStep  ----> ChildJob: settlePayments
    |                              |
    |                              +--> LoadValidOrdersStep
    |                              +--> CalculateSettlementStep
    |                              +--> WriteSettlementStep
    |
    v
PublishReportStep
```

From the parent job's perspective, `RunValidationJobStep` and `RunSettlementJobStep` are ordinary steps in the flow. However, each step actually launches a child job that may contain its own steps, flows, listeners, and configuration.

`JobStep` is useful when you want to encapsulate a sub-workflow into a named job that can run independently or be invoked from multiple parent jobs. It does not automatically create additional parallel threads; running the child job still follows the `JobLauncher` configuration and the child job's flow.

## 2. When should you use JobStep?

Some suitable scenarios:

- **Workflow reuse:** multiple parent jobs need to run the same sub-workflow such as file validation, data normalization, or report generation.
- **Splitting business modules:** each team can own a child job with its own reader, processor, writer, and listeners.
- **Multi-level orchestration:** the parent job manages the order of major workflows, while each child job manages the details of its internal steps.
- **Independent operation:** the child job can be launched separately to process a unit of work or for investigation purposes.
- **Clear metadata management:** each child job has its own execution history, making it easier to observe status and errors at the sub-workflow level.

You should not use `JobStep` merely to group a few simple steps if a `Flow` is already clear enough. A child job has its own metadata and identity; this is helpful when independent operational boundaries are needed, but it adds responsibility around parameters, restarts, and monitoring.

## 3. How does JobStep differ from FlowStep?

`JobStep` and `FlowStep` both allow encapsulating multiple operations into a single unit in the parent job's flow, but their execution scopes differ.

| Criterion | `JobStep` | `FlowStep` |
| --- | --- | --- |
| Target invoked | Another `Job` | A `Flow` consisting of steps/transitions |
| Execution metadata | Child job has its own `JobInstance` and `JobExecution` | Steps in the flow run within the scope of the current job execution |
| Job parameters | Uses `JobParametersExtractor` to create parameters for the child job | Uses the current job's parameters; does not create a new job instance |
| Can run independently | The child job can be launched independently | A flow is typically used as part of a job |
| Suitable when | You need a sub-workflow with its own job identity and lifecycle | You only need to organize a flow of steps within the same job |

If you only want to reuse a sequence of steps within the same job execution, consider `Flow` or `FlowStep`. If you need a child job with its own name, parameters, history, and ability to run independently, `JobStep` is the better choice.

## 4. Configuring the Child Job

The child job is declared as an ordinary `Job` bean. Example of a child job for validating orders:

```java
@Bean
Job validateOrdersJob(JobRepository jobRepository,
                      Step readOrdersStep,
                      Step validateOrdersStep,
                      Step saveValidationResultStep) {
    return new JobBuilder("validateOrdersJob", jobRepository)
        .start(readOrdersStep)
        .next(validateOrdersStep)
        .next(saveValidationResultStep)
        .build();
}
```

A child job can use chunk steps, tasklet steps, flows, deciders, listeners, and other Spring Batch mechanisms just like an independent job. It has its own name, `validateOrdersJob`; this name participates in identifying the child job's `JobInstance`.

The child job's steps still use the `JobRepository` and transaction manager appropriate for the application's batch infrastructure. In many applications, the parent job and child job share the same metadata repository so that tracking and orchestration remain consistent.

## 5. Creating a JobStep with JobStepBuilder

In Spring Batch 5, you can create a `JobStep` using `JobStepBuilder`. The builder takes the parent step's `StepBuilder`, the child job, the launcher, and the parameter extractor:

```java
@Bean
Step validateOrdersJobStep(JobRepository jobRepository,
                           JobLauncher jobLauncher,
                           Job validateOrdersJob,
                           JobParametersExtractor childJobParametersExtractor) {
    return new JobStepBuilder(
            new StepBuilder("validateOrdersJobStep", jobRepository)
        )
        .job(validateOrdersJob)
        .launcher(jobLauncher)
        .parametersExtractor(childJobParametersExtractor)
        .build();
}
```

Key components:

- `StepBuilder("validateOrdersJobStep", jobRepository)` creates the step definition in the parent job.
- `.job(validateOrdersJob)` specifies the child job to run.
- `.launcher(jobLauncher)` provides the mechanism to launch the child job.
- `.parametersExtractor(...)` creates `JobParameters` for the child job run from the parent job's execution.
- `.build()` creates the `JobStep` for the parent job to use in its flow.

Builder APIs in older Spring Batch versions may differ. Use the configuration approach corresponding to your project's library version; the example above uses the Spring Batch 5 builder API.

## 6. JobLauncher and JobParametersExtractor

`JobStep` does not decide all parameters for the child job on its own. It calls `JobParametersExtractor` to build the parameter set, and then uses `JobLauncher` to launch the child job.

These two components have distinct responsibilities:

| Component | Responsibility |
| --- | --- |
| `JobLauncher` | Receives the child job and `JobParameters`, and creates the job execution request. |
| `JobParametersExtractor` | Extracts or builds `JobParameters` based on the parent job's execution. |
| Launcher's `JobRepository` | Stores the `JobInstance`, `JobExecution`, and metadata of the child job. |

If the child job needs the same business parameters as the parent job, you can forward those parameters. If the child job needs additional information computed in a previous step, you can place values into the parent job's `JobExecutionContext` and then extract them into parameters for the child job.

## 7. Using DefaultJobParametersExtractor

`DefaultJobParametersExtractor` is a built-in implementation for simple parameter-passing cases. You can configure the keys to retrieve from the execution context to supplement the child job:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    DefaultJobParametersExtractor extractor =
        new DefaultJobParametersExtractor();
    extractor.setKeys(new String[] {"businessDate", "region"});
    return extractor;
}
```

When using the default extractor, check the rules for passing the parent execution's job parameters and the configured keys according to the Spring Batch version in use. The required values must exist in the context at the right scope before `JobStep` invokes the extractor.

If the child job's parameters require special rules—such as type conversion, marking identifying/non-identifying flags, or combining multiple sources—you can implement a custom `JobParametersExtractor`.

## 8. Creating Parameters for the Child Job with a Custom Extractor

The example below assumes the parent job has stored `region` in `JobExecutionContext`. The extractor forwards the parent job's parameters and adds `region` as an identifying parameter of the child job:

```java
public class ChildJobParametersExtractor
        implements JobParametersExtractor {

    @Override
    public JobParameters getJobParameters(Job job, StepExecution stepExecution) {
        JobExecution parentExecution = stepExecution.getJobExecution();
        JobParametersBuilder builder =
            new JobParametersBuilder(parentExecution.getJobParameters());

        ExecutionContext parentContext = parentExecution.getExecutionContext();
        if (parentContext.containsKey("region")) {
            builder.addString("region", parentContext.getString("region"), true);
        }

        return builder.toJobParameters();
    }
}
```

Register the extractor:

```java
@Bean
JobParametersExtractor childJobParametersExtractor() {
    return new ChildJobParametersExtractor();
}
```

Here, `stepExecution` is the execution of the `JobStep` belonging to the parent job. From it, the extractor obtains the parent `JobExecution` and reads job parameters/context. If the context is missing a required key, the application should decide explicitly whether to throw a configuration error or use a default value; it should not silently produce wrong parameters.

Marking `region` as identifying is only an example. If the region is part of the identity of the child unit of work, marking it identifying makes sense. If it is only descriptive metadata, you can choose non-identifying. The decision must align with the semantics of the child `JobInstance`.

## 9. Passing Data from a Parent Step to the Child Job

A step before `JobStep` can produce data needed when launching the child job. For example, `PrepareStep` determines the processing region and promotes the value from step context to job context using `ExecutionContextPromotionListener`.

```java
@Bean
ExecutionContextPromotionListener promoteRegionListener() {
    ExecutionContextPromotionListener listener =
        new ExecutionContextPromotionListener();
    listener.setKeys(new String[] {"region"});
    listener.setStatuses(new String[] {"COMPLETED"});
    return listener;
}
```

Attach the listener to the preparation step:

```java
@Bean
Step prepareStep(JobRepository jobRepository,
                 PlatformTransactionManager transactionManager,
                 ExecutionContextPromotionListener promoteRegionListener) {
    return new StepBuilder("prepareStep", jobRepository)
        .tasklet((contribution, chunkContext) -> {
            contribution.getStepExecution()
                .getExecutionContext()
                .putString("region", "APAC");
            return RepeatStatus.FINISHED;
        }, transactionManager)
        .listener(promoteRegionListener)
        .build();
}
```

When `PrepareStep` finishes with exit status `COMPLETED`, the `region` key is promoted to `JobExecutionContext`. The custom extractor from the previous section can read that value to build parameters for the child job.

Data flow:

```text
PrepareStep
  StepExecutionContext: region=APAC
          |
          v
ExecutionContextPromotionListener
          |
          v
Parent JobExecutionContext: region=APAC
          |
          v
JobParametersExtractor
          |
          v
Child JobParameters: region=APAC
          |
          v
JobLauncher launches ChildJob
```

Promotion should only occur when the step ends in an accepted status. If the preparation step fails, the parent job normally does not proceed to `JobStep`, and an unpromoted value should not be treated as valid input for the child job.

## 10. Wiring the Child Job into the Parent Job

After declaring the child job and `JobStep`, the parent job can use this step just like any other step:

```java
@Bean
Job dailySettlementJob(JobRepository jobRepository,
                       Step prepareStep,
                       Step validateOrdersJobStep,
                       Step publishReportStep) {
    return new JobBuilder("dailySettlementJob", jobRepository)
        .start(prepareStep)
        .next(validateOrdersJobStep)
        .next(publishReportStep)
        .build();
}
```

When the parent job runs:

1. `PrepareStep` performs preparation work and may write data into the job context.
2. `validateOrdersJobStep` calls `JobLauncher` to launch `validateOrdersJob` with parameters built by the extractor.
3. The child job runs its steps according to its own flow.
4. When the child job finishes, `JobStep` reflects the child execution outcome onto the parent step's status/exit status.
5. If the child job completes successfully, the parent job's flow can proceed to `PublishReportStep`.

If the child job fails, `JobStep` fails and the parent job usually stops according to its configured flow. You can use parent job transitions to route different outcomes if `JobStep`'s exit status is designed appropriately.

## 11. Parent Job and Child Job Metadata

`JobStep` creates two levels of metadata:

- The parent job has a `JobInstance`, `JobExecution`, and a `StepExecution` for `JobStep`.
- The child job has its own `JobInstance`, `JobExecution`, and `StepExecution`s.

```text
Parent JobInstance
  |
  +-- Parent JobExecution
        |
        +-- PrepareStep / StepExecution
        |
        +-- JobStep / StepExecution
              |
              +-- Child JobInstance
                    |
                    +-- Child JobExecution
                          |
                          +-- ChildStepA / StepExecution
                          +-- ChildStepB / StepExecution
```

`JobStep` does not turn the child job's steps into direct steps of the parent job. The child job has an independent name and metadata, allowing parent and child executions to be queried separately.

In a common setup, parent and child share the same `JobRepository` so metadata is stored in the same system. When investigating an error, start from the parent `JobExecution`, locate the `StepExecution` of `JobStep`, and then query the corresponding child execution via metadata or logs containing the execution ID.

## 12. Child JobInstance and Identifying Parameters

`JobInstance` identity is determined by the job name and the identifying `JobParameters`. This rule applies independently to the child job.

For example, `validateOrdersJob` runs with:

```text
job name = validateOrdersJob
businessDate = 2026-11-15 (identifying)
region = APAC (identifying)
```

Two invocations of the child job with the same name and the same identifying parameters target the same `JobInstance`, even when launched from two different parent jobs. This can lead to situations where the child job has already completed or is currently running, and the subsequent invocation is rejected according to Spring Batch rules.

Choose identifying parameters according to the logical unit of work of the child job. If each date/region is a separate unit, `businessDate` and `region` can be identifying. If the child job must process separately per parent batch ID, you can add `parentBatchId` as an identifying parameter when it is genuinely part of the business identity.

Do not add a timestamp or random UUID solely to work around `JobInstanceAlreadyCompleteException`. Doing so can create multiple instances for the same unit of work and make restarts and reconciliation hard to control. Use a new run identifier only when the business logic genuinely requires a new independent processing run.

## 13. Restarting When the Child Job Fails

Suppose the parent job calls the child job `validateOrdersJob`. The child job processes the first two steps successfully, but the third step fails:

```text
ParentJobExecution: FAILED
  JobStep: FAILED
    ChildJobExecution 1: FAILED
      ChildStepA: COMPLETED
      ChildStepB: COMPLETED
      ChildStepC: FAILED
```

When restarting the parent job with the same identifying parameters, the parent job can re-run `JobStep` according to restart behavior. If the extractor produces the same identifying parameters for the child job, `JobLauncher` will find the same child `JobInstance`; because the previous execution failed and the child job allows restart, the child job can create a new `JobExecution` to resume based on its metadata.

This requires:

- The child job is configured to be restartable.
- The child `JobParameters` have the same identity as the previous run if you want to restart the same instance.
- The child job's reader/writer support checkpointing and safe reprocessing.
- The child job metadata is intact and compatible with the current code.
- The parent flow allows re-running `JobStep` after the previous step failure.

If the child job is already `COMPLETED`, re-running with the same identifying parameters is usually not a valid restart. Distinguish between resuming a failed child instance and asking the child job to process a new business unit.

## 14. When the Child Job Completes but the Parent Job Fails Afterward

A case to watch out for: the child job has completed, the parent's `JobStep` has completed, but a subsequent step in the parent fails.

```text
ParentJobExecution: FAILED
  PrepareStep: COMPLETED
  ChildJobStep: COMPLETED
    ChildJobExecution: COMPLETED
  PublishReportStep: FAILED
```

When restarting the parent job, the already-completed `ChildJobStep` is normally skipped under default restart behavior. If configuration allows re-running completed steps, `JobStep` may invoke the child job again with the same parameters, and the child instance is already `COMPLETED`; in that case, re-running may be rejected.

Therefore, clarify whether the child job needs to re-run when the parent resumes. If the child job only needs to run once per batch, keeping the completed step and resuming from the failed parent step is usually the desired behavior. If you intentionally need to re-run the child job, use new identifying parameters for a new unit of work or design a dedicated reprocessing workflow.

## 15. Child Job Status and Parent Job Flow

The child job's outcome affects `JobStep` in the parent job. When the child job completes, the parent step can complete and the flow continues. When the child job fails or stops, the parent step reflects the corresponding outcome and the parent flow can stop or branch depending on configuration.

Example illustrating transitions in the parent job:

```java
@Bean
Job parentJob(JobRepository jobRepository,
              Step validateChildJobStep,
              Step handleValidationFailureStep,
              Step continueStep) {
    return new JobBuilder("parentJob", jobRepository)
        .start(validateChildJobStep)
            .on("COMPLETED").to(continueStep)
        .from(validateChildJobStep)
            .on("FAILED").to(handleValidationFailureStep)
        .from(continueStep)
            .on("*").end()
        .from(handleValidationFailureStep)
            .on("*").fail()
        .end()
        .build();
}
```

Transition patterns match the step's exit code. If you need to handle custom statuses from the child job, determine the exit status returned by the child job and how `JobStep` propagates that outcome to the parent step. Do not look only at `BatchStatus` while ignoring `ExitStatus`.

## 16. Synchronous and Asynchronous JobLauncher

`JobStep` uses `JobLauncher` to launch the child job. With typical orchestration, a synchronous launcher lets `JobStep` receive the child job's final outcome before the parent flow continues.

If an asynchronous launcher is used, the call may return while the child execution is still running. In that case, the parent step cannot be designed as if the child completed immediately unless there is a mechanism to track and synchronize the result. Carefully consider how the launcher is configured and what orchestration requires; do not replace a synchronous launcher with an asynchronous one just to increase concurrency.

If the goal is to run multiple child jobs in parallel, design a parallel orchestration mechanism with explicit status tracking, resource limits, and error handling. `JobStep` itself is not a parallel execution configuration.

## 17. Transaction Boundaries Between Parent and Child Jobs

The parent `JobStep` and the child job's steps have separate transaction boundaries. The parent step's transaction does not wrap all chunks of the child job into a single transaction.

```text
Parent JobStep
  parent step transaction / launch operation
        |
        v
Child JobExecution
  ChildStepA: chunk transactions 1, 2, ...
  ChildStepB: chunk transactions 1, 2, ...
  ChildStepC: separate tasklet/chunk transaction
```

Chunks of the child job may already have committed before the child job fails. When the parent job fails, already-committed chunks of the child job are not automatically rolled back. Restarting the child job relies on the child execution's metadata and checkpoints.

If the child job writes business data and the parent job later fails, the child's committed data still persists. The parent job must be designed to resume from that state, or have a compensation/reprocessing workflow if business rules require it.

Similarly, side effects of the child job—such as sending emails or calling external APIs outside a transaction—are not undone just because the parent step fails. Apply idempotency and transactional outbox patterns where side effects occur.

## 18. JobStep and Child Job Reusability

One advantage of a child job is that it can be called from multiple parent jobs. For example, `validateOrdersJob` can be used in `dailySettlementJob`, `monthlyReconciliationJob`, and a data re-verification job.

However, reusability does not mean every parent can pass the same parameters. Define the child job's parameter contract:

- Required parameters, such as `businessDate` or `inputFile`.
- Identifying parameters used to identify the child unit of work.
- Non-identifying parameters used only for operational information.
- Default values or rules when parameters are missing.
- Context keys that the parent must provide.

A child job should validate required parameters early, for instance in an initial validation step. If a parent invokes the child job without `businessDate`, the error should be reported clearly rather than letting a later step fail with a confusing error.

## 19. Monitoring and Troubleshooting JobStep Errors

When a parent job fails at a `JobStep`, inspect both execution levels:

1. Parent `JobExecution` shows where the overall parent job failed.
2. Parent `StepExecution` of `JobStep` shows the status of the step that invoked the child job.
3. Child `JobExecution` shows which parameters the child job was launched with and how it ended.
4. Child `StepExecution`s identify which internal step failed and its last checkpoint.

Log the following details:

- Parent job name and parent execution ID.
- Parent `JobStep` name and step execution ID.
- Child job name and child execution ID.
- Child identifying parameters needed for reconciliation.
- Batch ID or business key of the unit of work.
- Exit status and failure exception at both levels.

Do not log the entire sensitive payload of `JobParameters` or `ExecutionContext`. Only log identifiers and fields necessary for traceability.

You can use `JobExplorer` to query parent/child executions and `JobOperator` to perform appropriate operational actions. Before restarting, verify that the child execution is no longer running on another node and that the child job can restart with the same identifying parameters.

## 20. Testing JobStep

You should test both that the child job is invoked with the right parameters and how the child's status affects the parent. An integration test can use `JobLauncherTestUtils` to run the parent job and then look up the child job's metadata using `JobExplorer`.

Cases to verify:

- The parent job runs successfully and the child job is launched.
- The child job receives the right parameters from the parent job parameters.
- Values promoted from step context to job context are properly passed by the extractor.
- When the child job completes, the parent `JobStep` completes and the parent flow proceeds.
- When the child job fails, the parent step/job reflects the failure properly.
- Restarting the parent after a child failure resumes the child instance with the appropriate identifying parameters.
- Restarting the parent after the child has already completed does not unintentionally re-run the child if unnecessary.
- Two different parent jobs calling the child job with the same parameters are handled according to expected `JobInstance` rules.

Example of verifying child execution:

```java
JobExecution parentExecution = jobLauncherTestUtils.launchJob(parentParameters);

assertThat(parentExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);

List<JobInstance> childInstances = jobExplorer.getJobInstances(
    "validateOrdersJob", 0, 10
);
assertThat(childInstances).isNotEmpty();

JobExecution childExecution = jobExplorer.getJobExecutions(
    childInstances.get(0)
).get(0);

assertThat(childExecution.getStatus()).isEqualTo(BatchStatus.COMPLETED);
```

This snippet is a conceptual example; in a test with multiple child instances, select the right instance by identifying parameters instead of taking the first element. You should also use a dedicated metadata database for tests and disable auto-launch if Spring Boot automatically runs jobs on context startup.

## 21. Common Mistakes When Using JobStep

**Not configuring JobParametersExtractor:** the child job may miss required parameters or receive incorrect ones. Declare the extractor explicitly and test the actual values.

**Confusing step context with job context:** data from a previous step must be promoted or passed via another mechanism before the extractor reads it. Do not assume the child job can automatically see the parent's step context.

**Duplicate child JobInstance:** multiple parent executions may produce the same child job name and identifying parameters. Design child job identity to match the unit of work.

**Using a random timestamp to avoid already-completed instance errors:** this creates unnecessary new instances and breaks restart semantics. Only use a new identifying parameter when it is a new logical unit of work.

**Assuming parent rollback rolls back the child:** the child job has its own transactions and execution; committed chunks in the child are not automatically rolled back when the parent fails.

**Using an asynchronous launcher without coordinating the result:** the parent may not wait for the child to complete as expected. Explicitly design synchronization/tracking if asynchronous execution is needed.

**Using JobStep instead of FlowStep for every case:** if you only need to organize steps within the same job, `Flow` can be simpler and avoids adding another `JobInstance`.

**Not tracking the child execution ID:** looking only at the parent `JobStep` is not enough to diagnose internal child steps. Log and query both levels of metadata.

**Child job not restartable or reader not saving checkpoints:** a parent restart cannot automatically make the child resume from the right position if the child job does not support restart.

## 22. Designing JobStep in Production

First, determine which workflows genuinely need to be independent child jobs. If you need reusability, separate operation, separate execution history, or a distinct parameter contract, extract it into a `Job`. If you only need to group steps within the same job execution, prefer `Flow`/`FlowStep`.

Next, clearly define the child job's parameter contract. Use `JobParametersExtractor` to forward parent parameters and required values from the job context. Choose identifying parameters based on the child job's logical unit of work; avoid random timestamps to dodge duplicate-instance errors.

Declare `JobStep` with a consistently configured launcher and repository. In typical orchestration, use a synchronous launcher so the parent flow receives the child's final outcome. Monitor both parent execution and child execution, and test restart at both levels.

Finally, remember that the child job has its own transaction boundaries. Chunks already committed by the child persist if the parent fails. Design idempotent writers, checkpointing readers, and reconciliation processes so the parent can resume safely. When job boundaries, parameters, and metadata are clearly defined, `JobStep` helps organize large batch workflows into reusable and independently operable child jobs.
