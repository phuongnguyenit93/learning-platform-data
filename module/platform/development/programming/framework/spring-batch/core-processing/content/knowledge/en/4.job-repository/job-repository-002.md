# JobInstance, JobExecution, and StepExecution

Spring Batch distinguishes the definition of a batch process from each unit of work and each execution. The three objects `JobInstance`, `JobExecution`, and `StepExecution` describe three different levels of that process. Understanding the relationships among them correctly helps you design launch parameters, track history, handle errors, and restart a Job safely.

- `JobInstance` represents a logical unit of work of a Job, identified by the Job name and the identifying JobParameters.
- `JobExecution` represents a specific attempt to execute a JobInstance.
- `StepExecution` represents a specific execution of a Step within a JobExecution.

A Job can process many units of work, each unit may need several run attempts, and each attempt may execute many Steps. Spring Batch stores the metadata of these objects in the `JobRepository` so it can track history and support recovery.

## 1. The Big Picture of the Relationships

Suppose the application has a Job `dailySalesJob` that aggregates revenue by day. Each business date is a separate unit of work. The process has three Steps: validate input data, aggregate transactions, and publish the report.

```text
Job definition: dailySalesJob
        |
        +---------------------------------------+
        |                                       |
        v                                       v
JobInstance A                             JobInstance B
businessDate=2026-11-15                   businessDate=2026-11-16
        |                                       |
        v                                       v
JobExecution #101                         JobExecution #102
        |                                       |
        +--> StepExecution: validate             +--> StepExecution: validate
        +--> StepExecution: aggregate            +--> StepExecution: aggregate
        +--> StepExecution: publish             +--> StepExecution: publish
```

If the run for the 15th fails at the aggregation Step and is then restarted, the structure gains one more JobExecution for the very same JobInstance of the 15th:

```text
dailySalesJob
  |
  +--> JobInstance A: businessDate=2026-11-15
         |
         +--> JobExecution #101: FAILED
         |       validateInputStep       COMPLETED
         |       aggregateSalesStep      FAILED
         |
         +--> JobExecution #103: COMPLETED
                 aggregateSalesStep      COMPLETED
                 publishReportStep       COMPLETED
```

The JobInstance is still the same logical unit of work. The restart creates a new JobExecution, while the history of the previous run is retained. Spring Batch evaluates the Step status and the restart policy to decide which Steps need to run in the new execution.

## 2. JobInstance: A Logical Unit of Work

`JobInstance` is the combination of the Job's name and the identifying parameters (`identifying JobParameters`). It answers the question: **which logical work needs to be processed?**

For example, `dailySalesJob` processes revenue by day. If `businessDate` is an identifying parameter, two different days produce two JobInstances:

```text
Job name: dailySalesJob

businessDate=2026-11-15  --> JobInstance A
businessDate=2026-11-16  --> JobInstance B
```

The two JobInstances use the same Job definition but represent two different units of data. Each instance has its own identity in Spring Batch's metadata.

### How Do JobParameters Determine Identity?

When launching a Job, the application passes in `JobParameters`. Each parameter can be marked as identifying or non-identifying:

- Identifying parameters take part in determining the JobInstance.
- Non-identifying parameters can still be used as input data, but they do not change the JobInstance's identity.

For example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In the example above, `businessDate` is an identifying parameter, while `requestedBy` does not take part in identification. If you launch the same Job with the same `businessDate` but change `requestedBy`, Spring Batch still recognizes the same JobInstance.

Choosing identifying parameters needs to reflect the business unit that the Job processes. Some common examples:

| Job Type | Identifying Parameters That Can Be Used |
|---|---|
| Aggregating transactions by day | `businessDate` |
| Importing a specific file | `fileId` or the import batch code |
| Reconciliation by period | `settlementPeriod` |
| Generating a report by customer and period | `customerId` combined with `reportPeriod` |

If you choose too few identifying parameters, two different business jobs may be treated as the same JobInstance. If you add identifying parameters that arbitrarily change on every run, the same unit of data may be treated as new work and be processed repeatedly.

### What Happens When You Launch with the Same JobParameters?

Spring Batch checks the corresponding JobInstance in the `JobRepository` before creating a new execution. The result depends on the instance's history:

| JobInstance State | Common Behavior |
|---|---|
| Never been run | Creates a new JobInstance and JobExecution. |
| Has a running JobExecution | Rejects the duplicate launch, usually with `JobExecutionAlreadyRunningException`. |
| The previous JobExecution is `COMPLETED` | Does not allow running the same instance again as a new job, usually with `JobInstanceAlreadyCompleteException`. |
| The previous run is `FAILED` or `STOPPED` | A new JobExecution can be created to restart if the Job and its Steps allow it. |

These rules help prevent a unit of work from being launched in duplicate unintentionally. If the business really needs to process a new unit, provide the set of identifying parameters corresponding to the new unit.

## 3. JobExecution: An Attempt to Execute a JobInstance

`JobExecution` records a specific time Spring Batch tries to carry out a JobInstance. It answers the question: **how did this run go and what status did it end with?**

A JobInstance can have multiple JobExecutions when a previous run failed or was stopped and was later restarted:

```text
JobInstance: dailySalesJob / businessDate=2026-11-15
       |
       +--> JobExecution #101: FAILED
       |
       +--> JobExecution #103: COMPLETED
```

Each JobExecution has its own ID and stores information about that execution, such as:

- The creation time, start time, and end time.
- The `BatchStatus` such as `STARTING`, `STARTED`, `COMPLETED`, `FAILED`, or `STOPPED`.
- The `ExitStatus` describing the exit result code.
- The execution errors that were recorded.
- The `StepExecution`s that arose during the run.
- The Job-level `ExecutionContext`, used to store state needed for execution and restart.

A `JobExecution` belongs to one JobInstance. On restart, Spring Batch creates a new JobExecution instead of overwriting the history of the failed run. As a result, operators can compare attempts, view old errors, and determine which attempt completed.

### The JobExecution Lifecycle

A JobExecution usually passes through these statuses during launch and execution:

```text
STARTING --> STARTED
                |
                +--> COMPLETED
                |
                +--> FAILED
                |
                +--> STOPPING --> STOPPED
```

The common final statuses include:

| BatchStatus | Meaning |
|---|---|
| `COMPLETED` | The Job ended normally along the configured flow. |
| `FAILED` | The Job failed due to an error reflected on the execution. |
| `STOPPED` | The Job was stopped in a controlled way. It can be restarted if the configuration allows. |
| `ABANDONED` | The execution is marked as not to continue through the normal restart path. |
| `UNKNOWN` | The status cannot be determined with certainty; you need to check the metadata and the actual situation. |

`BatchStatus` differs from `ExitStatus`. `BatchStatus` represents the lifecycle status that Spring Batch manages; `ExitStatus` is the exit result code that can be used in flow control. The two values usually correspond in the default case, but they are not the same property.

## 4. StepExecution: One Execution of a Step

`StepExecution` records a specific execution of a Step within a JobExecution. It answers the question: **how much data did this Step process, how did it end, and what errors did it have?**

For example, the revenue aggregation Job has three Steps:

```text
JobExecution #101
       |
       +--> StepExecution: validateInputStep
       |
       +--> StepExecution: aggregateSalesStep
       |
       +--> StepExecution: publishReportStep
```

Each StepExecution stores separate information about that Step's run. The fields commonly used when monitoring include:

| Information | Meaning |
|---|---|
| Step name | The name of the Step that was executed. |
| `BatchStatus` | The execution status of the Step. |
| `ExitStatus` | The Step's exit result code; it can take part in choosing the next branch. |
| Start time / end time | The start and end times. |
| `readCount` | The number of records read. |
| `writeCount` | The number of records written. |
| `filterCount` | The number of records filtered out during processing. |
| `readSkipCount`, `processSkipCount`, `writeSkipCount` | The number of records skipped at each stage. |
| `commitCount`, `rollbackCount` | The number of commits and rollbacks recorded. |
| `ExecutionContext` | The Step's state, stored to support recovery on restart. |

These figures help locate where an error occurred. For example, if `readCount` increases but `writeCount` does not, it may suggest a problem in the Processor, Writer, or transaction; you need to read more logs and exceptions to conclude accurately.

### Which JobExecution Is a StepExecution Attached To?

A StepExecution belongs to the JobExecution that executed that Step. When a JobInstance is restarted, the new JobExecution will have StepExecutions corresponding to the Steps executed in the new run. The old StepExecutions remain attached to the old JobExecution, preserving history.

For a Step that completed in a previous run, Spring Batch usually skips that Step on restart if `allowStartIfComplete` is not enabled. A Step that is not re-run will not create a new execution in the current JobExecution. If a Step needs to run again on every restart, you can configure `allowStartIfComplete(true)` when it suits the business.

## 5. Distinguishing the Three Objects

| Criterion | `JobInstance` | `JobExecution` | `StepExecution` |
|---|---|---|---|
| Represents | A logical unit of work | An attempt to run a Job | An attempt to run a Step |
| Identified by / attached to | Job name + identifying JobParameters | A JobInstance and the run ID | A Step and the JobExecution that contains it |
| Quantity | A Job can have many instances | An instance can have many executions | A JobExecution has the executions of the Steps that were run |
| Notable data | Job name, JobKey, identifying parameters | Run times, BatchStatus, ExitStatus, errors, Job ExecutionContext | Step status, read/write/skip counters, Step ExecutionContext |
| Role on restart | Stays the same if restarting the same unit of work | Creates a new execution for the new attempt | Records the Steps executed in the new attempt |

A short way to remember:

- `JobInstance`: *which work needs to be processed?*
- `JobExecution`: *which attempt at running that work is this, and what was the result?*
- `StepExecution`: *how did each Step in that attempt perform?*

## 6. How Does JobRepository Store These Objects?

`JobRepository` is the component that manages Spring Batch's metadata. When a Job is launched and Steps execute, Spring Batch uses the repository to create or update information about JobInstance, JobExecution, StepExecution, and ExecutionContext.

With a database-based repository configuration, the default metadata schema has these familiar tables:

| Table | Main Contents |
|---|---|
| `BATCH_JOB_INSTANCE` | Identifying information of a JobInstance, including the Job name and JobKey. |
| `BATCH_JOB_EXECUTION` | The executions of a JobInstance and the status of each. |
| `BATCH_JOB_EXECUTION_PARAMS` | The JobParameters of an execution, including identifying-parameter information. |
| `BATCH_STEP_EXECUTION` | The metadata and counters of each StepExecution. |
| `BATCH_JOB_EXECUTION_CONTEXT` | The ExecutionContext at the JobExecution level. |
| `BATCH_STEP_EXECUTION_CONTEXT` | The ExecutionContext at the StepExecution level. |

These tables form a history that can be queried after the application restarts. They store **execution metadata**, not the main business data. For example, sales transaction records are stored in the application's business tables; the repository stores state showing which transaction-aggregation Job has run, which Step has completed, and where the checkpoint is.

In a production environment, you should use a persistent repository to support monitoring and restart. An in-memory repository usually cannot retain history across application shutdowns.

## 7. ExecutionContext at the Job and Step Levels

`ExecutionContext` is a key-value storage area that Spring Batch manages along with execution metadata. It is commonly used to hold the state needed when a Job or Step is restarted.

Spring Batch has two main scopes:

- **Job ExecutionContext:** attached to the JobExecution, suitable for state data that needs to be shared among Steps within the same Job run.
- **Step ExecutionContext:** attached to the StepExecution, suitable for the Step's own state, for example the current position of a reader.

With chunk-oriented processing, a reader can store its read position after each commit. If a run fails, a restart can use the stored information to continue from the appropriate checkpoint. The degree of recovery depends on whether the processing components support state saving and are configured correctly.

You should not put all business data into the ExecutionContext. The context should contain small state that is needed for orchestration or recovery. Large data and business data should still live in an appropriate storage system.

## 8. Example of Creating JobParameters, Launching, and Viewing Executions

The example below uses Spring Batch 5 or later. `businessDate` determines the unit of work; `requestedBy` only records the source of the request and does not take part in identification.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.JobParametersBuilder;
import org.springframework.batch.core.StepExecution;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.stereotype.Component;

@Component
public class DailySalesJobRunner {

    private final JobLauncher jobLauncher;
    private final Job dailySalesJob;

    public DailySalesJobRunner(
            JobLauncher jobLauncher,
            Job dailySalesJob) {
        this.jobLauncher = jobLauncher;
        this.dailySalesJob = dailySalesJob;
    }

    public void runForDate(String businessDate) throws Exception {
        JobParameters parameters = new JobParametersBuilder()
                .addString("businessDate", businessDate, true)
                .addString("requestedBy", "scheduler", false)
                .toJobParameters();

        JobExecution jobExecution =
                jobLauncher.run(dailySalesJob, parameters);

        System.out.println("JobInstance ID: "
                + jobExecution.getJobInstance().getInstanceId());
        System.out.println("JobExecution ID: " + jobExecution.getId());
        System.out.println("Job status: " + jobExecution.getStatus());

        for (StepExecution stepExecution : jobExecution.getStepExecutions()) {
            System.out.printf(
                    "Step=%s, status=%s, read=%d, write=%d, skips=%d%n",
                    stepExecution.getStepName(),
                    stepExecution.getStatus(),
                    stepExecution.getReadCount(),
                    stepExecution.getWriteCount(),
                    stepExecution.getSkipCount());
        }
    }
}
```

The code snippet illustrates how to read execution information after calling the launcher. If the `JobLauncher` runs synchronously, by the time `run` returns, the JobExecution usually has a final status. If you use an asynchronous launcher, the Job may still be running; the status read right after `run` may be `STARTING` or `STARTED`. In that case, you need to monitor the execution through an appropriate mechanism instead of treating the initial status as the final result.

`JobExecution` provides access to the JobInstance and the collection of StepExecutions of the run. In a real application, you can use these objects to write logs, display progress, or send information to a monitoring system.

## 9. Tracking History with JobExplorer

`JobExplorer` provides a read-only API to look up execution metadata stored in the `JobRepository`. It is a useful tool for administration pages or monitoring tasks that need to find JobInstances, JobExecutions, and StepExecutions without directly modifying metadata.

Common lookup operations include:

- Finding JobInstances by Job name and parameters.
- Getting the list of JobExecutions of a JobInstance.
- Getting a JobExecution by ID.
- Viewing the StepExecutions belonging to a JobExecution.
- Reading the ExecutionContext to investigate stored state.

Example of querying a JobExecution by ID:

```java
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.explore.JobExplorer;
import org.springframework.stereotype.Service;

@Service
public class BatchExecutionQueryService {

    private final JobExplorer jobExplorer;

    public BatchExecutionQueryService(JobExplorer jobExplorer) {
        this.jobExplorer = jobExplorer;
    }

    public JobExecution findExecution(long executionId) {
        return jobExplorer.getJobExecution(executionId);
    }
}
```

The lookup result can be `null` if there is no corresponding execution. `JobExplorer` serves history observation; control operations such as launching, stopping, or restarting belong to the corresponding orchestration APIs and should not be done by directly modifying the metadata tables.

## 10. Common Design Mistakes

| Problem | Consequence | How to Handle |
|---|---|---|
| Using the current time as an identifying parameter for every call | Every call may create a new JobInstance, so a restart does not reconnect to the old instance. | Choose identifying parameters that represent the business unit, such as the data date or the batch code. |
| Not marking identifying parameters correctly | Different jobs may be recognized as the same instance. | Review the business meaning and the identifying flag of each JobParameter. |
| Thinking JobExecution and JobInstance are the same | You may mistake a restart for new work or overwrite the meaning of history. | Keep the logical unit of work distinct from each run attempt. |
| Looking only at the JobExecution status | You do not know which Step failed or how many records were processed. | Look at the StepExecutions, counters, exceptions, and related logs. |
| Assuming FAILED will roll back all data | Chunks that have committed or Steps that completed earlier may still keep their changes. | Design idempotent restarts and check the data that has been processed. |
| Storing large business data in the ExecutionContext | Metadata becomes hard to manage and is not suitable as business storage. | Store only checkpoints and state needed for orchestration; main data lives in the business store. |
| Directly editing the BATCH_* tables to fix a status | This can make metadata inconsistent and cause restart errors. | Use the Spring Batch API and an appropriate operational procedure. |

## 11. Applying This When Investigating a Failed Job

When a Job fails, you can trace through the three levels in order:

1. **Identify the JobInstance.** Check the Job name and the identifying JobParameters to be sure you are looking at the right data date, batch code, or business period.
2. **Look at the JobExecutions.** Find the most recent run, its final status, run times, and exception. Compare with earlier runs to know whether this is a restart.
3. **Look at the StepExecutions.** Identify the failed Step, the Steps that completed, the number of records read/written/skipped, and the state of the ExecutionContext.
4. **Reconcile with business data.** Determine the portion of data that was committed before the error and assess the risk of duplicate writes when re-running.
5. **Decide on a restart.** Use exactly the same identifying JobParameters and confirm that the Job and Steps support restart. Check the checkpoint and the idempotency of write operations.

For example, `dailySalesJob` for the 15th has a first JobExecution that is `FAILED` at `aggregateSalesStep`. If the input data has been read and the first chunks have committed, the restart needs to continue from the checkpoint or ensure that repeated operations do not cause duplicates. When the Job completes, the JobInstance still represents the 15th, while the new JobExecution records the successful run.

## Conclusion

`JobInstance`, `JobExecution`, and `StepExecution` are three complementary levels of metadata in Spring Batch. A JobInstance identifies a logical unit of work by the Job name and identifying JobParameters. A JobExecution records each attempt to execute that unit. A StepExecution records the result and figures of each Step in a run. `JobRepository` stores this information along with the ExecutionContext to support monitoring, investigation, and restart. When the three levels are clearly distinguished, an application can manage many data periods, keep run history, and recover batch processes in a controlled way.
