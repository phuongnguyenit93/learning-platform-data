# Completed Jobs and Re-launch Behavior

In Spring Batch, calling `JobLauncher` with a Job and a set of `JobParameters` does not mean the system always creates a completely new run. Spring Batch first identifies the corresponding `JobInstance` based on the Job name and the identifying parameters. After that, the instance's historical state decides whether the call is accepted, treated as a restart, or rejected.

The important case is when the JobInstance already has an execution that ended with `COMPLETED`. When the application launches the same Job again with the same identifying parameters, Spring Batch normally throws `JobInstanceAlreadyCompleteException`. A completed JobInstance is regarded as a unit of work that has been fully processed; to process a new unit of work, you need to create a new JobInstance with a different set of identifying parameters.

To understand this behavior correctly, you need to distinguish three operations:

- **Launching a new JobInstance:** uses a Job name and a set of identifying JobParameters that have never been run.
- **Restarting a JobInstance:** runs the same unit of work again after the previous execution failed or was stopped, if the configuration allows it.
- **Re-launching a JobInstance that is already COMPLETED:** not treated as a valid restart; Spring Batch rejects the call with the same identity.

## 1. JobLauncher determines the run before executing

`JobLauncher` receives a `Job` object and `JobParameters`, and then asks Spring Batch to launch the Job. During this process, the `JobRepository` is used to find or create the `JobInstance`, check previous executions, and create a new `JobExecution` if the launch is valid.

```text
Application
   |
   | Job + JobParameters
   v
JobLauncher
   |
   v
JobRepository
   |
   +--> Identify JobInstance from Job name + identifying parameters
   |
   +--> Check existing JobExecutions
   |
   +--> Decide:
          - Create a new JobInstance and launch
          - Create a new JobExecution to restart
          - Reject the call
```

A `JobLauncher.run(job, parameters)` call does not automatically add a unique parameter for each call. If the identifying JobParameters do not change, the calls still target the same JobInstance, even when a non-identifying parameter changes.

## 2. Why can't a COMPLETED Job be launched again with the same parameters?

Spring Batch regards a JobInstance as a logical unit of work. Once the JobInstance has completed, the goal of that unit of work has been achieved according to the configured flow and policy. Running the same instance again could cause business data to be processed twice, produce duplicate reports, or cause unwanted side effects.

For example, the Job `dailySalesJob` aggregates revenue for one day. The `businessDate` parameter is an identifying parameter:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

jobLauncher.run(dailySalesJob, parameters);
```

Suppose the first run has completed:

```text
Job: dailySalesJob
JobInstance: businessDate=2026-11-15
JobExecution #1: COMPLETED
```

If the application calls again with the exact Job name and the same identifying parameter `businessDate=2026-11-15`, Spring Batch finds the completed JobInstance and refuses to create a new run for that instance:

```text
jobLauncher.run(dailySalesJob, sameParameters)
             |
             v
JobInstance is already COMPLETED
             |
             v
JobInstanceAlreadyCompleteException
```

This behavior protects the consistency of the batch process. If the application wants to aggregate the 16th, that is a different unit of work and needs to pass `businessDate=2026-11-16`, which creates a new JobInstance.

## 3. Factors that decide whether a launch is allowed

The JobInstance identity is determined by the Job name and the JobParameters that have the identifying flag. Non-identifying parameters do not change the identity.

| History of the corresponding JobInstance | Common behavior when calling JobLauncher with the same identifying parameters |
|---|---|
| Does not exist yet | Creates a new JobInstance and JobExecution, then runs the Job. |
| Has a running execution | Rejected, usually with `JobExecutionAlreadyRunningException`. |
| Previous execution is `COMPLETED` | Rejected, usually with `JobInstanceAlreadyCompleteException`. |
| Previous execution is `FAILED` | A new JobExecution can be created to restart if the Job allows restart. |
| Previous execution is `STOPPED` | Can be restarted if the state and configuration allow it. |
| The Job does not allow restart after an incomplete run | May be rejected with `JobRestartException`. |

These results are determined per JobInstance. If you change only a non-identifying parameter, Spring Batch still considers it the same JobInstance and still applies the rule based on that instance's history.

## 4. Distinguishing a restart after FAILED from a launch after COMPLETED

A restart continues a logical unit of work that has not completed. When a JobExecution fails, the application can launch the same Job again with the same identifying parameters. If the Job and the Steps allow restart, Spring Batch creates a new JobExecution for the same JobInstance.

```text
JobInstance: businessDate=2026-11-15
       |
       +--> JobExecution #1: FAILED
       |
       +--> JobExecution #2: COMPLETED
```

In this example, JobExecution #2 is a new attempt of the same JobInstance. The metadata of the first run is retained. Spring Batch can skip Steps that have completed and resume the failed Step from an appropriate checkpoint, depending on the configuration and the state-saving capability of each component.

Conversely, if JobExecution #1 is already `COMPLETED`, there is no unfinished work left to restart. A launch with the same identifying parameters will be rejected:

```text
JobInstance: businessDate=2026-11-15
       |
       +--> JobExecution #1: COMPLETED
       |
       +--> Launch with the same identifying parameters
                |
                +--> JobInstanceAlreadyCompleteException
```

If the business requires re-running data that has already been completed, you need to make it clear that this is a new processing run under business policy, and create a new JobInstance with an appropriate identifying parameter.

## 5. How do identifying and non-identifying parameters affect this?

`JobParameters` can contain both identifying and non-identifying parameters. Only the identifying parameters are used to build the key of the JobInstance.

```java
JobParameters firstCall = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();

JobParameters secondCall = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("requestedBy", "admin", false)
        .toJobParameters();
```

The two parameter sets above have different `requestedBy` values but still have the same JobInstance identity because `businessDate` is an identifying parameter and has the same value. If the first run is already `COMPLETED`, the second call is still rejected. Changing the requester only adds input metadata; it does not create a new unit of work.

If you need a new processing run for the same business date, you can add an identifying parameter that represents the processing run or the reprocessing version:

```java
JobParameters reprocessParameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addLong("reprocessVersion", 2L, true)
        .toJobParameters();
```

With this parameter set, `reprocessVersion=2` takes part in the identity and creates a JobInstance different from the instance that has only `businessDate=2026-11-15`. Only do this when the business truly allows reprocessing. The Steps need a mechanism to avoid duplicate writes, or must overwrite the old results according to clearly defined rules.

You should not add a new identifying timestamp or UUID for every call just to dodge `JobInstanceAlreadyCompleteException`. That approach turns every call into a new JobInstance, which can remove the ability to detect duplicate runs and cause data to be processed repeatedly without control.

## 6. How to deliberately create a new JobInstance

There are several common ways to create a new JobInstance after the previous instance has completed.

### Use a new business parameter

This is the most natural approach when the unit of work changes. For example, a Job that processes revenue by day:

```java
JobParameters day15 = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .toJobParameters();

JobParameters day16 = new JobParametersBuilder()
        .addString("businessDate", "2026-11-16", true)
        .toJobParameters();
```

The two parameter sets create two separate JobInstances. Each instance can be monitored, completed, and restarted independently.

### Use a version parameter or a reprocessing run code

If the business allows re-running the same data period as new work, you can add an identifying parameter such as `reprocessVersion`, `correctionBatchId`, or a reprocessing request code. This value must be managed through a business process to avoid unintentionally creating duplicate instances.

### Use JobParametersIncrementer

Spring Batch provides `JobParametersIncrementer` to generate the parameter set for the next JobInstance. One built-in option is `RunIdIncrementer`, which typically uses an incrementing `run.id` parameter.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.launch.support.RunIdIncrementer;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class DailySalesJobConfig {

    @Bean
    public Job dailySalesJob(
            JobRepository jobRepository,
            Step aggregateSalesStep) {

        return new JobBuilder("dailySalesJob", jobRepository)
                .incrementer(new RunIdIncrementer())
                .start(aggregateSalesStep)
                .build();
    }
}
```

When using an incrementer, each subsequent parameter set can carry a new `run.id` and therefore create a new JobInstance. This mechanism is useful for Jobs where the concept of a "next run" makes sense. However, incrementing `run.id` does not by itself guarantee business safety: the Job can still reprocess the same data. The application needs to clearly define which data is allowed to be re-run and how to manage the results of each run.

With `JobOperator`, you can request to launch the next instance of a Job that has an incrementer:

```java
jobOperator.startNextInstance("dailySalesJob");
```

`startNextInstance` uses the Job's `JobParametersIncrementer` to get the next parameter set. If the Job does not configure an appropriate incrementer, this operation cannot create the next parameter set on its own.

## 7. Common exceptions when re-launching

`JobLauncher.run` can reject a call if the JobInstance history does not allow launching. Common exceptions include:

| Exception | Common cause | How to handle |
|---|---|---|
| `JobInstanceAlreadyCompleteException` | The JobInstance with the corresponding identifying parameters is already `COMPLETED`. | If you only need a restart, re-check the request because the instance is already done. If you need a new processing run, create a new JobInstance with appropriate identifying parameters. |
| `JobExecutionAlreadyRunningException` | A JobExecution of the same JobInstance is running. | Check the current execution; avoid sending additional duplicate launches. |
| `JobRestartException` | The instance cannot be restarted, for example the Job is configured not to restart or the previous state does not allow it. | Check the restart configuration and the metadata state; only create a new instance if the business determines it is new work. |
| `JobParametersInvalidException` | The JobParameters set is invalid according to the Job's validator. | Add or fix the input parameters according to the Job's rules. |

You should not catch all exceptions and silently create random parameters to retry. That can hide the fact that the Job is running, has completed, or is in a state that cannot be restarted. The application should distinguish errors caused by duplicate calls, errors caused by the instance state, and errors caused by parameter data.

## 8. Example of handling the result when calling JobLauncher

The example below illustrates catching the already-completed JobInstance case separately. The other exceptions are declared so the calling layer handles them according to the application's policy.

```java
import org.springframework.batch.core.Job;
import org.springframework.batch.core.JobExecution;
import org.springframework.batch.core.JobParameters;
import org.springframework.batch.core.launch.JobLauncher;
import org.springframework.batch.core.repository.JobExecutionAlreadyRunningException;
import org.springframework.batch.core.repository.JobInstanceAlreadyCompleteException;
import org.springframework.batch.core.repository.JobRestartException;
import org.springframework.batch.core.JobParametersInvalidException;
import org.springframework.stereotype.Service;

@Service
public class DailySalesLauncher {

    private final JobLauncher jobLauncher;
    private final Job dailySalesJob;

    public DailySalesLauncher(JobLauncher jobLauncher, Job dailySalesJob) {
        this.jobLauncher = jobLauncher;
        this.dailySalesJob = dailySalesJob;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobExecutionAlreadyRunningException,
                   JobRestartException,
                   JobParametersInvalidException {
        try {
            return jobLauncher.run(dailySalesJob, parameters);
        } catch (JobInstanceAlreadyCompleteException ex) {
            // The instance has completed: do not create a new identifying parameter automatically.
            throw ex;
        }
    }
}
```

In a real application, the calling layer can convert the exception into an API response, notify the operator, or write a structured log. If the launcher is configured asynchronously, the returned `JobExecution` may still be in the `STARTING` or `STARTED` state; you must not treat that state as the final result.

## 9. JobLauncher does not decide the data re-run policy

`JobLauncher` coordinates launching based on metadata and Spring Batch's rules. It does not know whether a reprocessing request is permitted from a business perspective. That decision belongs to the application.

Before creating a new JobInstance for data that has already completed, you need to determine:

1. Why the re-run is needed: has the input data changed, does the previous result need correcting, or did a user simply send a duplicate request?
2. Will the old result be kept, replaced, or marked as no longer valid?
3. Can the Writer write duplicates or send duplicate notifications?
4. Is a reprocessing request code needed for traceability and to prevent repeated sending?
5. Can the Steps run independently of data that was processed earlier?

If the Job updates business data, you should design the write operations to be idempotent or to use an appropriate business key. If the Job creates files, sends emails, or calls external services, you need a mechanism to control side effects when creating a new JobInstance for the same source data.

## 10. Easily confused situations

| Situation | Correct result to understand |
|---|---|
| Re-calling a COMPLETED Job with the same Job name and identifying parameters | Rejected with `JobInstanceAlreadyCompleteException`. |
| Changing only a non-identifying parameter after the Job is COMPLETED | Still the same JobInstance; the call is still rejected. |
| Changing the identifying parameter to a different data date | Creates a new JobInstance. |
| Re-calling the Job after FAILED with the same identifying parameters | Can restart with a new JobExecution if the Job allows it. |
| Re-calling while the current execution is still running | Rejected to avoid running the same instance twice. |
| Incrementing `run.id` after the Job is COMPLETED | Creates a new JobInstance; the Job may reprocess the data and needs a clear business policy. |
| Adding a new UUID for every call | Every call may become a new instance, losing the ability to detect duplicate requests. |

## Conclusion

When a JobInstance has ended with `COMPLETED`, Spring Batch does not let `JobLauncher` run the same Job again with the same identifying JobParameters. This is a mechanism that protects a logical unit of work from being processed twice. If the previous run was `FAILED` or `STOPPED`, the application can restart the same JobInstance with a new JobExecution when the configuration allows it. If you need to perform a new processing run after completion, create a new JobInstance with identifying parameters that have business meaning, or use an appropriate incrementer. Creating a new instance needs to be accompanied by a data and side-effect control policy to avoid duplicate writes.
