# Tracking Child Job Status

In Spring Batch, `JobStep` allows a parent job to launch another job as a step in a workflow. This organization is useful when a large workflow consists of multiple child jobs with distinct responsibilities, such as a parent job orchestrating data import, reconciliation, and report generation. When using `JobStep`, you need to track status at multiple levels: the child job's `JobExecution`, `JobStep`'s `StepExecution` in the parent job, and the parent job's own `JobExecution`.

These status levels are related to each other, yet they are not the same object. Understanding that relationship accurately helps the application monitor properly, handle failures, restart, and decide the next flow branch.

## 1. What is JobStep?

`JobStep` is a type of step responsible for launching another `Job`. The job containing `JobStep` is called the parent job; the job launched from that step is the child job.

For example, an end-of-day order processing workflow can be organized as follows:

```text
dailyOrderJob (parent job)
        |
        v
   validateInputStep
        |
        v
   importChildJobStep --------> importOrdersJob (child job)
        |                              |
        |                              +-- readOrdersStep
        |                              +-- writeOrdersStep
        |                              +-- validateResultStep
        v
   reconcileChildJobStep -----> reconcileOrdersJob (child job)
        |
        v
   publishReportStep
```

In the diagram, `importChildJobStep` is a `StepExecution` belonging to the parent job. When this step runs, it uses `JobLauncher` to launch `importOrdersJob`. The child job has its own `JobExecution` and `StepExecution`s.

`JobStep` helps reuse existing jobs, split a large workflow into independently operable units, and keep each child job with its own metadata, status, listeners, and execution history.

## 2. Which Statuses Need to Be Tracked?

When a `JobStep` runs, distinguish at least three objects:

| Object | Belongs To | Role |
|---|---|---|
| Child `JobExecution` | Child job | Status of the child job execution run, including steps inside the child job. |
| Parent `StepExecution` | Parent job | Status of the step launching the child job. |
| Parent `JobExecution` | Parent job | Overall status of the parent job run. |

Example:

```text
Parent JobExecution: dailyOrderJob
  |
  +-- StepExecution: validateInputStep       COMPLETED
  |
  +-- StepExecution: importChildJobStep      COMPLETED
  |       |
  |       +-- Child JobExecution: importOrdersJob
  |               +-- readOrdersStep         COMPLETED
  |               +-- writeOrdersStep        COMPLETED
  |               +-- validateResultStep     COMPLETED
  |
  +-- StepExecution: publishReportStep       STARTED
```

When the child job completes, `JobStep` records the outcome of the child run during execution of the parent step. The parent job then continues according to the configured flow. If the child job fails, `JobStep` normally fails and affects the parent job status, unless the parent job's flow has a branch handling that outcome.

Do not look at a single status alone and conclude the entire workflow succeeded. Clarify whether the status refers to the child job, the step launching the child job, or the parent job.

## 3. BatchStatus and ExitStatus

Spring Batch uses two important status concepts:

- `BatchStatus`: execution lifecycle status, such as `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, `STOPPING`, `STOPPED`, `ABANDONED`, or `UNKNOWN`.
- `ExitStatus`: result code of a job or step, which can be `COMPLETED`, `FAILED`, `STOPPED`, or a custom code defined by the application.

`BatchStatus` is commonly used to know whether an execution is running, finished, or failed. `ExitStatus` is heavily used in flow control, listeners, and business outcome reporting.

For example, a child job can finish technically yet return a custom exit code:

```java
return new ExitStatus("COMPLETED_WITH_WARNINGS");
```

In that case, distinguish:

| Value | Meaning |
|---|---|
| `BatchStatus.COMPLETED` | The `JobExecution` ended successfully according to the framework's execution status. |
| `ExitStatus("COMPLETED_WITH_WARNINGS")` | Custom exit outcome indicating business warnings. |

`JobStep` can propagate the child job's `ExitStatus` result to the parent step according to its execution mechanism. The parent step and parent job status also depend on how `JobStep` handles the result and the declared flow transitions. Therefore, if the application needs to distinguish complete success from success with warnings, design explicit exit codes and verify status propagation behavior on your Spring Batch version.

## 4. Declaring a JobStep

In Spring Batch 5 and later, you can build a `JobStep` using `StepBuilder` with the child job, launcher, and parameters extractor:

```java
@Bean
Step importChildJobStep(
        JobRepository jobRepository,
        JobLauncher jobLauncher,
        Job importOrdersJob,
        JobParametersExtractor childParametersExtractor) {

    return new StepBuilder("importChildJobStep", jobRepository)
            .job(importOrdersJob)
            .launcher(jobLauncher)
            .parametersExtractor(childParametersExtractor)
            .build();
}
```

Components:

- `jobRepository`: stores metadata for the step belonging to the parent job.
- `jobLauncher`: launches the child job.
- `importOrdersJob`: definition of the invoked job.
- `JobParametersExtractor`: creates the `JobParameters` set passed to the child job based on the parent job's execution information.

`JobStep` does not automatically mean all `JobParameters` of the parent job are always passed intact to the child job. Configure the extractor to explicitly define which parameters to forward and which values to pull from execution context.

## 5. JobParameters of the Child Job

The child job has its own identity. The child job's `JobInstance` is determined by the child job name and the identifying `JobParameters` provided by the extractor.

For example, the parent job runs with:

```text
Parent job parameters:
  businessDate = 2026-11-15
  sourceSystem = ERP
  requestedBy  = scheduler
```

The child job may only need two identifying parameters:

```text
Child job parameters:
  businessDate = 2026-11-15   identifying = true
  sourceSystem = ERP          identifying = true
```

If a subsequent parent job run re-launches the same child job with the same identifying parameters, Spring Batch will recognize the same `JobInstance` of the child job. This is critical for restarts. If you automatically add a fresh UUID on every call, each call creates a different `JobInstance` and is no longer a restart of the same instance.

### Using DefaultJobParametersExtractor

`DefaultJobParametersExtractor` helps retrieve specified keys from the parent step's `JobParameters` or `ExecutionContext` to create `JobParameters` for the child job. Example:

```java
@Bean
JobParametersExtractor childParametersExtractor() {
    DefaultJobParametersExtractor extractor =
            new DefaultJobParametersExtractor();
    extractor.setKeys(new String[]{"businessDate", "sourceSystem"});
    return extractor;
}
```

Keys must be provided in the source the extractor reads, and types/values must fit the child job. If you need more complex mapping rules, you can implement a custom `JobParametersExtractor`.

Define clearly which parameters are identifying for the child job. Non-identifying parameters can be used to record the requester or trace information without changing the identity of the child `JobInstance`.

## 6. Where Is Child JobExecution Created and Stored?

When `JobStep` calls `JobLauncher`, the launcher registers and executes the child job through the `JobRepository` that the launcher uses. The child job has its own `JobInstance` and `JobExecution`, along with `StepExecution`s for its internal steps.

Typically, the parent job and child job share the Spring Batch application's single `JobRepository`. In that case, parent and child metadata are stored in the corresponding metadata tables and can be queried via `JobExplorer`.

```text
JobRepository
  |
  +-- Parent JobInstance
  |      +-- Parent JobExecution
  |              +-- Parent StepExecution: importChildJobStep
  |
  +-- Child JobInstance
         +-- Child JobExecution
                 +-- Child StepExecution: readOrdersStep
                 +-- Child StepExecution: writeOrdersStep
```

The parent `StepExecution` is not the child `JobExecution`. Having `JobStep` launch the child job does not turn the steps inside the child job into direct steps of the parent job. They are stored under the child `JobExecution`.

If the application configures multiple `JobRepository` instances or multiple datasources, identify clearly which repository `JobLauncher` uses and where child job metadata is stored. When parent and child use different repositories, monitoring and operations must query the corresponding repository.

## 7. Tracking the Child Job with JobExplorer

`JobExplorer` is the API for reading execution metadata. It is suitable for building monitoring dashboards or services that query child job status.

If you know the child `JobExecution` ID, you can look it up directly:

```java
@Service
public class ChildJobStatusService {

    private final JobExplorer jobExplorer;

    public ChildJobStatusService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

From `JobExecution`, you can read:

```java
JobExecution execution = jobExplorer.getJobExecution(executionId);

if (execution != null) {
    BatchStatus status = execution.getStatus();
    ExitStatus exitStatus = execution.getExitStatus();
    var startTime = execution.getStartTime();
    var endTime = execution.getEndTime();
}
```

The exact time type of the getters depends on the Spring Batch version; the example above illustrates the fields to monitor. You can also read `failureExceptions`, `stepExecutions`, and `jobParameters` to display causes or progress.

If you do not yet know the execution ID, you can search `JobInstance`s of the child job by name:

```java
List<JobInstance> instances = jobExplorer.getJobInstances(
        "importOrdersJob", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
            jobExplorer.getJobExecutions(instance);

    for (JobExecution execution : executions) {
        System.out.println(
                execution.getId() + " : " + execution.getStatus());
    }
}
```

This is how to look up history by job name. In a real system, filter by identifying parameters or a business batch code to pinpoint the exact child `JobInstance`, rather than simply taking a few recent instances and guessing which execution belongs to the parent run.

## 8. How to Link Parent StepExecution with Child JobExecution?

To monitor a nested workflow, the system needs to know which child execution was launched from the parent `JobStep`. A reliable approach is to record the linking identifier in metadata or a business monitoring table.

Do not assume every version or configuration of `JobStep` provides a ready-made public API to retrieve the child `JobExecution` ID from the parent `StepExecution`. If the monitoring dashboard needs a direct link, design explicit recording for it.

Several implementation approaches:

- Use a child job listener to record the child `JobExecution` ID together with parent job/step identity if parent info is passed in.
- Put the parent execution ID or parent step execution ID into the child `JobParameters` as non-identifying parameters for tracing.
- Use a separate orchestration table storing parent execution ID, parent step execution ID, child execution ID, child job name, and batch reference.
- When launching the child job via a custom service, store the ID returned from `JobLauncher` in an appropriate metadata mechanism.

For example, the parent execution ID can be passed to the child job for traceability:

```java
JobParameters childParameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("sourceSystem", sourceSystem, true)
        .addLong("parentExecutionId", parentExecutionId, false)
        .toJobParameters();
```

`parentExecutionId` here is non-identifying because it only serves operational correlation. If it were marked identifying, the same processing period launched from a new parent execution could create a new child `JobInstance`, changing restart semantics.

When using default `JobStep`, check how the extractor obtains parameters and how listeners are called to pass/record parent info. If you need to store the child ID accurately, you can wrap the launch with a dedicated orchestration component or use custom listeners/metadata suited to your architecture.

## 9. How Does Child Job Failure Affect the Parent?

When the child job ends with `BatchStatus.FAILED`, `JobStep` normally cannot treat the parent step as completed successfully. The child's failure outcome is reflected onto `JobStep`, and the parent flow continues according to error-handling configuration.

Simple flow example:

```java
@Bean
Job dailyOrderJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importChildJobStep,
        Step publishReportStep) {

    return new JobBuilder("dailyOrderJob", jobRepository)
            .start(validateInputStep)
            .next(importChildJobStep)
            .next(publishReportStep)
            .build();
}
```

If `importChildJobStep` fails, the default sequential flow does not continue to `publishReportStep` as a normal successful step. The parent job may end as `FAILED`.

If intentional error handling is needed, declare branches based on `ExitStatus`:

```java
@Bean
Job dailyOrderJob(
        JobRepository jobRepository,
        Step validateInputStep,
        Step importChildJobStep,
        Step publishReportStep,
        Step recordImportFailureStep) {

    return new JobBuilder("dailyOrderJob", jobRepository)
            .start(validateInputStep)
            .next(importChildJobStep)
                .on("COMPLETED").to(publishReportStep)
            .from(importChildJobStep)
                .on("FAILED").to(recordImportFailureStep)
            .from(publishReportStep)
                .on("*").end()
            .from(recordImportFailureStep)
                .on("*").fail()
            .end()
            .build();
}
```

The example illustrates a flow branching on exit code. In a real application, configure all necessary transitions and clearly define the final status of the parent job. Do not end the parent job with `COMPLETED` if the child job failed and business rules require the entire workflow to be treated as failed.

## 10. Tracking Progress Inside the Child Job

The child `JobExecution` has its own set of `StepExecution`s. To see which step the child job is on, read `getStepExecutions()` from the child `JobExecution` or use `JobExplorer` to query metadata.

Example of building progress information:

```java
JobExecution childExecution = jobExplorer.getJobExecution(childExecutionId);

if (childExecution != null) {
    for (StepExecution stepExecution : childExecution.getStepExecutions()) {
        System.out.printf(
                "%s: %s, read=%d, write=%d, skip=%d%n",
                stepExecution.getStepName(),
                stepExecution.getStatus(),
                stepExecution.getReadCount(),
                stepExecution.getWriteCount(),
                stepExecution.getSkipCount());
    }
}
```

Counters such as `readCount`, `writeCount`, `filterCount`, `skipCount`, `commitCount`, and `rollbackCount` help understand processing progress. They are metrics of each `StepExecution`, not necessarily the total number of business records successfully applied across every external system.

If the child job has multiple steps, the monitoring dashboard should display:

- Child job name and `JobExecution` ID.
- `BatchStatus` and `ExitStatus`.
- Current step or list of steps with statuses.
- Start time, end time, and duration.
- Read, write, filter, skip, and rollback item counts.
- Exception or error info permitted for display.
- Parent execution/step ID so operators can trace back to the parent job.

## 11. JobExecutionListener and StepExecutionListener

Listeners help log or emit information when a job/step starts and finishes. With the parent-child model, you can attach a listener to the child job to record child execution results and a listener to `JobStep` to track parent step status.

Example listener for the child job:

```java
@Component
public class ChildJobExecutionListener implements JobExecutionListener {

    @Override
    public void beforeJob(JobExecution jobExecution) {
        // Log child execution started.
        log.info("Child job {} execution {} started",
                jobExecution.getJobInstance().getJobName(),
                jobExecution.getId());
    }

    @Override
    public void afterJob(JobExecution jobExecution) {
        // Log status and exit code after child job ends.
        log.info("Child job execution {} ended with status {} and exit {}",
                jobExecution.getId(),
                jobExecution.getStatus(),
                jobExecution.getExitStatus().getExitCode());
    }
}
```

Listeners can record metrics, audit entries, or update monitoring tables. Keep listeners short and avoid letting logging/monitoring errors alter the job's business outcome unless that is an intentional requirement.

For parent `JobStep`, `StepExecutionListener` can record the timing and status of the step launching the child job. If you need to store the child execution ID, the child job listener or a custom orchestration mechanism must record that ID explicitly.

## 12. How Do JobExplorer and JobOperator Differ?

These two APIs are often used in operational tooling, yet have different roles:

| Component | Role |
|---|---|
| `JobExplorer` | Reads and queries metadata such as `JobInstance`, `JobExecution`, and `StepExecution`. |
| `JobOperator` | Provides administrative operations such as start, restart, stop, and execution info lookup per supported API version. |
| `JobRepository` | Stores metadata and is used by the framework during execution. |
| `JobLauncher` | Launches a job with `JobParameters`. |

For status monitoring screens, `JobExplorer` is usually the right query entry point. For operational actions like requesting a stop or restarting a child job, use an administrative API like `JobOperator` according to your application configuration.

Do not update metadata tables directly to force a child job to `COMPLETED`, `FAILED`, or `STOPPED`. Manual metadata edits can corrupt relationships between `JobInstance`, `JobExecution`, `StepExecution`, and parent-child state.

## 13. Restarting When the Child Job Fails

One benefit of `JobStep` is that the child job has its own execution history and restart mechanism. When the child job fails, you can address the root cause and then restart the parent job or execute a child restart procedure suited to the design.

Common flow:

```text
Parent JobExecution #1
   |
   +-- importChildJobStep -> FAILED
             |
             v
       Child JobExecution #1 -> FAILED

After resolving the root cause:

Parent JobExecution #2 (restart parent JobInstance)
   |
   +-- importChildJobStep -> re-launches child job
             |
             v
       Child JobExecution #2 -> COMPLETED
```

For the child job to restart the right `JobInstance`, the extractor must provide the same identifying parameters used previously. If identifying parameters change, the child job will create a new `JobInstance`.

Conditions to verify:

- Does the child job allow restart or is it configured with `preventRestart()`?
- What state is the child `JobInstance` in?
- Has the failed step exceeded `startLimit` or does it have special restart configuration?
- Do the child job's reader/writer save checkpoints and support recovery?
- Are already-committed operations or external side effects safe when re-run?
- Is the parent `JobStep` allowed to start again per the step's configuration?

If the child job is already `COMPLETED` yet the parent `JobStep` did not record completion due to the process stopping at a sensitive moment, a restart may attempt to launch the same child `JobInstance` and hit `JobInstanceAlreadyCompleteException`. In that case, inspect metadata of both parent and child before deciding how to proceed. Do not add a new run ID just to bypass the error if the business genuinely needs to continue the same processing unit.

## 14. Synchronous and Asynchronous Child Job Execution

`JobStep` usually needs to know the child job's execution outcome to complete the parent's `StepExecution`. Therefore, how `JobLauncher` is configured directly affects status tracking.

With a synchronous launcher, the `run` call waits for the child job to finish before returning. `JobStep` can use the final outcome to determine the parent step's status.

With an asynchronous launcher, `run` may return while the child job is still running. If an asynchronous launcher is used directly in `JobStep` without additional coordination, the parent step risks finishing before the child job actually completes or failing to reflect the true final status.

Therefore, for a standard `JobStep`, use a synchronous launcher so the parent step waits for the child job to finish. If the business requirement is to launch a child job in the background and let the parent continue immediately, design a dedicated asynchronous orchestration model: store the child execution ID, have a waiting/reconciliation state, and mark the parent stage complete only when business conditions are met.

## 15. Child Job Status May Differ from Business Outcome

A child job can finish `COMPLETED` even if it skipped some items or filtered some records. This can be completely valid if the job is designed to tolerate invalid data within allowed limits.

Example:

```text
Child JobExecution: COMPLETED
  readCount   = 10,000
  writeCount  = 9,970
  filterCount = 20
  skipCount   = 10
```

`COMPLETED` only indicates that the job finished under configured execution rules. It does not mean all 10,000 items were written successfully. If the parent needs to decide whether to continue based on skip rate, the child job should emit a custom `ExitStatus` or store business results for the parent to inspect.

For example, the child job can set exit code `COMPLETED_WITH_WARNINGS` when skipped records exceed a warning threshold. The parent flow can route based on that exit code.

## 16. Example of Tracking Child Status with a Monitoring Table

In a system with many child jobs, you can create a dedicated monitoring table to link parent and child. A simple structure might include:

| Column | Purpose |
|---|---|
| `parent_execution_id` | Parent job's `JobExecution` ID. |
| `parent_step_execution_id` | `StepExecution` ID containing `JobStep`. |
| `child_job_name` | Child job name. |
| `child_execution_id` | Child job's `JobExecution` ID. |
| `business_reference` | Batch code or business period. |
| `child_status` | Latest status of the child execution. |
| `started_at` / `ended_at` | Start and end timestamps. |

This table can be updated by a listener or orchestration component. `JobRepository` remains Spring Batch's authoritative metadata source; the monitoring table simply supplements business-appropriate relationships and display data.

When updating status in the monitoring table, store the child execution ID and update timestamp. Avoid storing only a status string without an execution identifier, because a single child `JobInstance` can have multiple `JobExecution`s across restarts.

## 17. Common Mistakes When Tracking JobStep

| Issue | Common Cause | Resolution |
|---|---|---|
| Parent step reports `FAILED` without knowing where the child errored | Looking only at Parent `StepExecution`, not querying child `JobExecution` and child steps. | Use `JobExplorer` to read the child execution and step executions. |
| Cannot find child execution | Not saving child execution ID or querying the wrong `JobRepository`/`JobInstance`. | Record linking IDs or query by child job name and identifying parameters. |
| Child job treated as a new instance on every parent restart | Extractor adds changing identifying parameters. | Keep identifying parameters unchanged for the same logical processing unit. |
| Child job reports already completed on parent restart | Child `JobInstance` is already `COMPLETED` while parent step has not recorded the final result. | Reconcile parent/child metadata and handle according to actual state; do not delete metadata arbitrarily. |
| Parent completes while child is still running | Using an async launcher without wait/monitoring mechanisms. | Use a synchronous launcher for standard `JobStep` or build dedicated async orchestration. |
| Parent reports `COMPLETED` despite child skips | Child job completed by `BatchStatus` yet had skipped data errors. | Check counters and business `ExitStatus`; define custom result codes if needed. |
| Cannot restart child | Child job has `preventRestart`, step exceeded `startLimit`, or status disallows it. | Inspect restart configuration and child `JobInstance` metadata. |
| Parent flow takes the wrong branch | Confusing `BatchStatus` with `ExitStatus` or missing transitions. | Check `JobStep`'s actual exit code and flow configuration. |
| Cannot trace parent-child relationship | Not passing parent ID or lacking a linking table. | Add parent reference to child parameters as non-identifying or use dedicated monitoring metadata. |

## 18. Operational Procedure When a Child Job Has Issues

When `JobStep` fails or the monitoring screen shows an abnormal child job, follow this sequence:

1. **Identify parent execution:** retrieve the parent job's `JobExecution` ID and the step execution corresponding to `JobStep`.
2. **Identify child job:** check the child job name and parameter set generated by the extractor.
3. **Look up child execution:** use `JobExplorer` or the linking table to get the exact child `JobExecution` ID.
4. **Read detailed status:** inspect `BatchStatus`, `ExitStatus`, timestamps, failure exceptions, and `StepExecution`s inside the child.
5. **Assess business data:** check read/write/skip counts, committed chunks, and external side effects.
6. **Resolve root cause:** fix input data, restore services, or release locked resources.
7. **Check restart conditions:** verify that child `JobInstance`, identifying parameters, restart policy, and parent `JobStep` all allow re-running.
8. **Restart in a controlled manner:** re-launch the parent or child per the designed operational procedure, using the exact identity when resuming the same processing unit.
9. **Monitor both levels:** confirm the new child `JobExecution` completes and parent `StepExecution`/`JobExecution` receive the appropriate outcome.

Do not simply edit status in metadata tables or delete child executions so the parent can proceed. That can destroy history and cause the framework to re-run already-processed data.

## 19. Key Takeaways

- `JobStep` launches a child job as a step in a parent job.
- The child job has its own `JobInstance`, `JobExecution`, and `StepExecution`s; `JobStep` has a `StepExecution` belonging to the parent job.
- Distinguish child `BatchStatus`, child `ExitStatus`, parent `StepExecution`, and parent `JobExecution`.
- `JobParametersExtractor` decides which parameters are passed to the child job; identifying parameters determine the child `JobInstance`.
- `JobExplorer` is used to query child executions and internal steps; `JobOperator` supports administrative operations per configured API.
- If a direct link between parent and child execution is needed, record the child execution ID explicitly via listeners, parameters, or a monitoring table.
- Child failure normally causes `JobStep` to fail; the parent flow decides the next processing branch.
- Child `COMPLETED` does not guarantee every item was written; inspect counters and business `ExitStatus`.
- A standard `JobStep` should usually use a synchronous `JobLauncher` to wait for the child job result.
- On restart, use the exact identifying parameters of the child `JobInstance` and check both parent and child metadata.

When building monitoring screens or operational procedures for `JobStep`, remember that parent and child are two independent executions linked by orchestration. Properly tracking the child `JobExecution`, individual child step statuses, and parent `JobStep` results enables accurate failure detection, correct flow control, and safe restarts.
