# Launch Exceptions and Validation Errors

`JobLauncher` is the component that receives a Job together with `JobParameters` and asks Spring Batch to start execution. During launch, the framework has to validate the parameters, identify the `JobInstance`, check the previous run history, create a `JobExecution`, and hand the work to the executor. Each step can raise errors with different causes.

Understanding launch exceptions and validation errors correctly helps you distinguish an invalid launch request, a Job that is already running, a JobInstance that has already completed, a restart request that is not allowed, and an error that occurs inside a Step. These cases need to be handled differently; if you lump them all into one generic error, the system has a hard time responding accurately and may unintentionally run the work twice.

## 1. The lifecycle of a Job launch request

A launch request typically goes through the following steps:

1. The application receives a request from a scheduler, REST API, command line, or another component.
2. The application converts the input data into `JobParameters` with appropriate data types.
3. `JobLauncher` validates the parameters using the `JobParametersValidator` configured for the Job.
4. `JobRepository` identifies the JobInstance based on the Job name and the identifying parameters.
5. The repository checks the execution history to determine whether the Job is running, has completed, or can be restarted.
6. If valid, the repository creates a new `JobExecution`.
7. `JobLauncher` hands the execution to the executor to start running the Job.
8. The Job executes the Steps and updates the status, exit status, and metadata in the repository.

```text
Scheduler / REST / CLI
          |
          v
  Create JobParameters
          |
          v
   JobParametersValidator
          |
          v
      JobRepository
          |
          +-- Identify JobInstance
          |
          +-- Check previous executions
          |
          +-- Create JobExecution
          |
          v
      JobLauncher
          |
          v
        Executor
          |
          v
       Job / Steps
```

Errors can occur before a `JobExecution` exists, for example when the validator rejects the parameters or the repository detects that the JobInstance has already completed. Errors can also occur after the JobExecution is created, for example when the executor does not accept the task or a Step fails during processing. You need to determine which stage the error belongs to before deciding whether to return the error to the caller, retry, or restart.

## 2. Common exceptions when calling JobLauncher

The `JobLauncher.run(job, jobParameters)` method declares the following main checked exceptions:

| Exception | Common cause | How to handle |
|---|---|---|
| `JobParametersInvalidException` | Parameters are missing, invalid, or violate the validator's rules. | Return an input error and ask for the parameters to be corrected. |
| `JobExecutionAlreadyRunningException` | The corresponding JobInstance has a running execution. | Check the current execution; do not launch a duplicate. |
| `JobInstanceAlreadyCompleteException` | The corresponding JobInstance has already completed. | Determine whether the caller wants to restart, run new business work, or deliberately rerun. |
| `JobRestartException` | The JobInstance cannot be restarted given its current state or configuration. | Check restartability, the previous state, and the Step's policy. |

Besides these checked exceptions, the application can also encounter infrastructure errors such as an inaccessible database, transaction errors, or the executor rejecting a task. For example, `TaskRejectedException` can appear when the thread pool is full or shutting down. This is an infrastructure/orchestration error, not a JobParameters validation error.

The exceptions above reflect different problems. You should not catch them all and return the same "Batch failed" message. Specific information helps the caller decide whether to fix the request, wait for the running execution, create a new JobInstance, or ask for operational support.

## 3. JobParametersInvalidException and validation

`JobParametersInvalidException` is used when the launch parameters do not meet the Job's requirements. Validation should take place before the Job performs any business side effects, to avoid starting a process with a wrong business date, a missing input file, or an invalid selection.

Spring Batch provides the `JobParametersValidator` interface:

```java
public interface JobParametersValidator {
    void validate(JobParameters parameters)
            throws JobParametersInvalidException;
}
```

The validator receives `JobParameters`. If the parameters are valid, the method ends normally. If they are not valid, the validator throws `JobParametersInvalidException` with enough information for the caller to know what needs to be fixed.

### Types of rules to check

Validation can check:

- Whether required parameters exist.
- Whether the parameter name is in the allowed list.
- Whether the value has the right format, value domain, or basic business rule.
- Whether the parameters are compatible with each other, for example `startDate` must not be after `endDate`.
- Whether a run mode requires additional parameters, for example `reprocess=true` must be accompanied by `sourceBatchId`.

Keep the validator fast, deterministic, and with few side effects. Checks that need to access external systems, read large files, or query data that can change over time are usually better suited to a separate preflight step in the Job. A validator should not send emails, write business data, or perform irreversible operations.

## 4. Using DefaultJobParametersValidator

`DefaultJobParametersValidator` is suitable when you need to declare a list of required parameters and optional parameters. For example, an import Job needs `inputFile` and `businessDate`; `requestedBy` and `dryRun` are optional.

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
            new String[] {"inputFile", "businessDate"},
            new String[] {"requestedBy", "dryRun"}
    );
}
```

Attach the validator to the Job:

```java
@Bean
Job importOrdersJob(
        JobRepository jobRepository,
        Step importOrdersStep,
        JobParametersValidator importParametersValidator) {

    return new JobBuilder("importOrdersJob", jobRepository)
            .validator(importParametersValidator)
            .start(importOrdersStep)
            .build();
}
```

In this example, `inputFile` and `businessDate` must be present. `requestedBy` and `dryRun` may or may not be present. Parameters outside the allowed list will be rejected by the validator. If you need to check data types or relationships between values, add a custom validator.

`DefaultJobParametersValidator` mainly handles rules about parameter names and presence. It does not replace all business validation. For example, whether a date string has the correct ISO format or whether the end date is after the start date needs to be checked with separate logic.

## 5. Writing a custom JobParametersValidator

When you need to check formats and relationships between parameters, you can implement `JobParametersValidator`.

An example of a Job that receives a file name and a business date as strings:

```java
public class ImportParametersValidator implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String inputFile = parameters.getString("inputFile");
        String businessDate = parameters.getString("businessDate");

        if (inputFile == null || inputFile.isBlank()) {
            throw new JobParametersInvalidException(
                    "Required parameter 'inputFile' is missing");
        }

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "Required parameter 'businessDate' is missing");
        }

        try {
            LocalDate.parse(businessDate);
        } catch (DateTimeParseException exception) {
            throw new JobParametersInvalidException(
                    "Parameter 'businessDate' must use ISO date format (yyyy-MM-dd)");
        }
    }
}
```

Register the validator:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new ImportParametersValidator();
}
```

The code needs the corresponding Java imports such as `LocalDate` and `DateTimeParseException`. In Spring Batch 5, `JobParameters` supports typed parameters; if the application passes a `LocalDate` directly, you can use the type-correct read API instead of converting through a string. The example uses a string here to make the input-format rule explicit.

A good validator should name the parameter and the rule that was violated. You should not return a vague message such as "Invalid parameters". At the same time, avoid putting sensitive parameter values into the exception message, because the message may be written to logs or metadata.

## 6. Distinguishing validation errors from parameter conversion errors

Validation takes place after the application already has `JobParameters`. However, input data from the command line, a REST request, or a configuration file usually has to be converted into parameter types beforehand.

For example, if the API receives `businessDate="15-11-2026"` but the converter or binding code requires a different format, a parse error can occur before `JobLauncher` is called. In that case, `JobParametersValidator` may not have run yet.

You should distinguish the stages:

| Stage | Example error | Appropriate place to handle it |
|---|---|---|
| Receiving the request | A JSON field is missing or has the wrong data type. | Controller/request validation. |
| Parameter conversion | A date string cannot be parsed into a date type. | Converter or the input mapping layer. |
| Job validation | `inputFile` is missing, the business date violates a rule. | `JobParametersValidator`. |
| Instance state check | The instance is running or has completed. | `JobLauncher`/`JobRepository` and the orchestration logic. |
| Step execution | A file cannot be read, a database timeout, a business error. | Reader, processor, writer, Tasklet, and fault-tolerance policy. |

Separating these layers lets the API return appropriate input errors, and does not force the validator to handle data that has not yet been converted into `JobParameters`.

## 7. JobExecutionAlreadyRunningException

`JobExecutionAlreadyRunningException` occurs when the corresponding JobInstance already has a running execution. This case typically appears when a scheduler sends duplicate requests, a user clicks the launch button multiple times, or multiple applications try to launch a Job with the same identifying parameters.

For example:

```text
Job: dailySettlementJob
Identifying parameter: businessDate=2026-11-15

Request A --> JobExecution 5001 --> STARTED
Request B --> same JobInstance --> JobExecutionAlreadyRunningException
```

How to handle it:

1. Look up the active execution using `JobExplorer` or an operations screen.
2. Determine whether the new request is a duplicate or a different business request.
3. If it is a duplicate, return the ID of the running execution or a message with the current status.
4. If it is truly a new business run, determine a new identifying parameter according to business rules.
5. If the metadata says it is running but the process has died, investigate the process state, the database, and transactions before carrying out a recovery procedure.

You should not delete the JobExecution record or change the `STATUS` in the metadata table yourself to bypass the exception. Doing so can cause two processes to handle the same JobInstance or cause the checkpoint to no longer reflect the actual data.

To reduce duplicate requests, the application can use an idempotency key at the API, a distributed lock, or a scheduler coordination mechanism. However, the unique constraints and transactions of the JobRepository remain an important layer of protection at the metadata level.

## 8. JobInstanceAlreadyCompleteException

`JobInstanceAlreadyCompleteException` occurs when the JobInstance identified by the Job name and identifying parameters has already completed. Spring Batch does not create a new execution for the same completed instance through the usual launch route.

For example, `dailySettlementJob` has completed with `businessDate=2026-11-15`. If you send the exact Job name and the same identifying parameters again, the framework recognizes it as the same JobInstance and rejects the launch.

Before handling the exception, determine the intent:

- **Want to continue a failed run:** use the same JobInstance identity and restart according to Spring Batch's policy.
- **Want to run a new business batch:** pass a new identifying parameter according to business rules, for example a different business date or a new batch code.
- **Want to deliberately rerun the same business data:** you need to design a clear rerun identifier, such as `run.id` or `reprocessVersion`, and also ensure that the business operations are idempotent and reconcilable.

You should not add a random timestamp to every launch on your own just to avoid the exception. If every retry creates a new JobInstance, Spring Batch cannot recognize it as a restart of the old run, and the earlier checkpoint may not be used.

`allowStartIfComplete(true)` is a Step option that allows a completed Step to be run again in an appropriate Job restart. It does not by itself allow re-launching a `COMPLETED` JobInstance by calling `JobLauncher.run` with the exact old identity.

## 9. JobRestartException

`JobRestartException` indicates that a restart request is not accepted given the current state or configuration. Some causes may include:

- The Job is configured not to restart, for example using `preventRestart()`.
- The previous execution is in a state unsuitable for continuing, such as `ABANDONED` or `UNKNOWN`.
- The Step state or the start-limit policy means the rerun cannot continue in the requested way.
- Inconsistent metadata or restart conditions.

An example of a Job that does not allow restart:

```java
@Bean
Job oneTimeExportJob(
        JobRepository jobRepository,
        Step exportStep) {

    return new JobBuilder("oneTimeExportJob", jobRepository)
            .preventRestart()
            .start(exportStep)
            .build();
}
```

Use `preventRestart()` only when the business truly does not allow continuing a stopped or failed execution. If the Job needs to recover after an infrastructure failure, a restartable design is usually more appropriate, along with a reader/writer that supports checkpoints and idempotent operations.

When you encounter `JobRestartException`, look at the previous JobExecution, BatchStatus, ExitStatus, failure exception, StepExecution state, start limit, and restart configuration. You should not delete old metadata before determining its effect on the data that has already been processed.

## 10. Identifying parameters and the decision to create a JobInstance

Spring Batch distinguishes identifying and non-identifying JobParameters. The Job name together with the identifying parameters identifies the JobInstance. Non-identifying parameters can carry operational information such as the requester or a logging label without changing the business identity.

For example:

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFile", "orders-2026-11-15.csv", true)
        .addString("requestedBy", "scheduler", false)
        .toJobParameters();
```

In the example, `businessDate` and `inputFile` take part in identifying the JobInstance. `requestedBy` is only operational information. If a new launch uses the same Job name and the same identifying parameters, it points to the same JobInstance.

### Restart and a new run are two different intents

When a Job fails midway, a restart usually needs to keep the JobInstance identity so that Spring Batch can link the new run to the previous history and checkpoint.

When you want to create a new business run, you can use `JobParametersIncrementer`, such as `RunIdIncrementer`:

```java
@Bean
Job monthlyReportJob(
        JobRepository jobRepository,
        Step reportStep) {

    return new JobBuilder("monthlyReportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

An incrementer typically adds or increments an identifying parameter such as `run.id`. It is appropriate when each run is regarded as a new JobInstance. Do not use an incrementer to hide a JobInstance that is running or to replace restarting a failed Job.

## 11. Infrastructure errors when launching

Not every error during a `JobLauncher.run` call is a parameter or instance-state error. Some errors can come from the infrastructure:

### TaskRejectedException

With a launcher that uses a `TaskExecutor`, the executor can reject a task when the thread pool has reached its limit, the queue is full, or the executor is shutting down. This is a sign that the processing capacity or the executor lifecycle needs to be checked.

How to handle it includes limiting the rate of accepting requests, configuring an appropriate pool/queue, monitoring the number of running tasks, and handling the executor shutdown situation. You should not retry continuously and immediately if the system is still overloaded; that can make the queue heavier.

### JobRepository or database errors

If the database that stores metadata is inaccessible, the JobLauncher may not be able to create or update the JobExecution. Common errors include timeouts, lost connections, missing permissions, a wrong schema, a missing sequence, or an optimistic locking conflict.

Check the datasource, transaction manager, repository schema, access permissions, and database logs. If it is unclear whether the JobExecution has been created, query the repository before resending the launch to avoid creating a duplicate request.

### Job configuration or registry errors

If the application gets a Job by name from a `JobRegistry` or a similar registration mechanism, a nonexistent Job name can cause a lookup error before the launcher is called. This is a configuration/lookup error, different from `JobParametersInvalidException`.

Check the requested Job name, the Job registration configuration, and the running environment. You should not turn a "Job not found" error into a parameter validation error.

## 12. Distinguishing launch exceptions from errors in a Step

One easy point of confusion is that `JobLauncher.run` can return a `JobExecution` with the `FAILED` status when an error occurs during Job execution. That is different from the launcher throwing a checked exception before or during the task hand-off.

For example:

```java
JobExecution execution = jobLauncher.run(importOrdersJob, parameters);

BatchStatus status = execution.getStatus();
ExitStatus exitStatus = execution.getExitStatus();
```

For errors that occur in the reader, processor, writer, or Tasklet, Spring Batch usually records the error into the execution, updates `BatchStatus`/`ExitStatus`, and stores the failure exception. The application must look at the returned status or query the execution afterward to learn the result.

With an asynchronous launcher, `run` can return while the Job is only in the `STARTING` or `STARTED` state; the work continues on the executor. The status at the time of receiving the response is not yet the final result. You need to monitor it using `JobExplorer`, events, or the application's status API.

Therefore:

- An exception from the validator or the repository usually indicates that the launch request was rejected.
- A `JobExecution` with `FAILED` usually indicates that the Job has started and the error occurred within the execution.
- `STARTING` or `STARTED` means there is no final result yet.
- `COMPLETED` needs to be read together with `ExitStatus` and the business result.

You should not rely solely on `jobLauncher.run` not throwing an exception to conclude that the Job succeeded.

## 13. Handling exceptions in the layer that calls JobLauncher

The layer that calls the launcher should classify the specific checked exceptions. The following example illustrates an orchestration service:

```java
@Service
public class BatchLaunchService {

    private final JobLauncher jobLauncher;
    private final Job importOrdersJob;

    public BatchLaunchService(
            JobLauncher jobLauncher,
            @Qualifier("importOrdersJob") Job importOrdersJob) {
        this.jobLauncher = jobLauncher;
        this.importOrdersJob = importOrdersJob;
    }

    public JobExecution launch(JobParameters parameters)
            throws JobParametersInvalidException,
                   JobExecutionAlreadyRunningException,
                   JobInstanceAlreadyCompleteException,
                   JobRestartException {

        return jobLauncher.run(importOrdersJob, parameters);
    }
}
```

The service can let the specific exception propagate up to the controller or calling layer, where there is enough context to decide how to respond. If the service catches the exception, preserve the cause and convert it into a clearly typed result; avoid just logging and returning `null`.

### Example of mapping errors to an HTTP response

With a REST API, you can map errors according to the meaning of the request:

```java
try {
    JobExecution execution = jobLauncher.run(job, parameters);
    return ResponseEntity.accepted().body(execution.getId());
} catch (JobParametersInvalidException exception) {
    return ResponseEntity.badRequest().body("Invalid Job parameters");
} catch (JobExecutionAlreadyRunningException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance is already running");
} catch (JobInstanceAlreadyCompleteException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance has already completed");
} catch (JobRestartException exception) {
    return ResponseEntity.status(HttpStatus.CONFLICT)
            .body("This JobInstance cannot be restarted");
}
```

This is a conceptual-level mapping example; a real controller needs to declare an appropriate return type and log the exception according to the application's policy. HTTP `202 Accepted` is appropriate when the request has been accepted for asynchronous processing. If the launcher runs synchronously and a final result is already available, the response can reflect the actual status according to the API contract.

Do not return the raw stack trace, SQL, internal paths, or sensitive content of JobParameters to the client. The client only needs a stable error code and guidance on how to handle it; technical details should go in controlled logs.

## 14. How do synchronous and asynchronous execution affect launching?

`JobLauncher` can use a synchronous or asynchronous executor.

### Synchronous

With a synchronous executor such as `SyncTaskExecutor`, the task runs on the calling thread. The launch method usually returns only after the Job finishes executing. This is easy to understand in a small application or on the command line, but the request may wait a long time if the Job processes a lot of data.

### Asynchronous

With an asynchronous executor, the launcher hands the task to another thread and returns early. The caller receives a `JobExecution` that may still be running. You need a mechanism for looking up status, notifying completion, and handling errors after the original request has ended.

When running asynchronously, an error that occurs in a Step cannot be returned as an HTTP exception of a launch request that has already ended. It is recorded in the JobExecution; the application needs to provide an endpoint or observability mechanism so users can see the result.

## 15. Retrying a launch, restarting a Job, and creating a new JobInstance

These three operations are not the same:

| Operation | Purpose | Identity |
|---|---|---|
| Retrying the launch request | Resending the request because of a network error or a timeout on the caller's side. | Needs idempotency so it does not create or run duplicates. |
| Restarting a Job | Continuing a JobInstance that failed or stopped, according to Spring Batch's policy. | Keep the JobInstance identity. |
| Creating a new JobInstance | Starting a new business batch or a reprocess with its own identity. | Use a new identifying parameter. |

For example, a caller sends a request but times out before receiving the response. You cannot conclude that the Job has not run. Before resending, the caller should use an idempotency key or look up the JobExecution by business key to determine whether the previous request was accepted.

If the Job fails after some chunks have committed, a restart can continue from the checkpoint if the reader/writer supports restart and the side effects are designed safely. If you create a new JobInstance with `run.id` instead of restarting, the work may run again from the beginning and create duplicate data if there is no control.

## 16. Logging and diagnosing launch errors

When logging a launch request, include enough information to link the request, JobInstance, and JobExecution:

- Job name.
- Request code or idempotency key.
- Business key and the non-sensitive identifying parameters.
- JobExecution ID if it has been created.
- Exception class and the root cause.
- BatchStatus, ExitStatus, and the time the error occurred if the execution already exists.

Do not log secrets, tokens, passwords, or the entire payload if the payload contains personal data. You can mask sensitive values and log only the parameters needed for diagnosis.

When investigating, follow this order:

1. Determine whether the error occurred before or after the JobExecution was created.
2. Check the Job name and the identifying JobParameters.
3. If the validator rejected it, look at the parameter name and the rule that was violated.
4. If the instance is running or has completed, look up the previous JobExecution.
5. If a restart was rejected, check the BatchStatus, restartability, start limit, and Step state.
6. If it is an infrastructure error, check the executor, datasource, transactions, and repository schema.
7. If the execution has started but failed, read the failure exception and the log of the corresponding Step.

## 17. Common mistakes

### Catching every exception and returning the same error code

This leaves the caller not knowing whether to fix the parameters, wait for the current Job, or request a new run. Classify the main launch exceptions and keep the cause information.

### Using random parameters to dodge JobInstanceAlreadyCompleteException

Adding a timestamp or UUID to every request continuously creates new JobInstances, loses the ability to recognize restarts, and can process data twice. Create a new identity only when the business truly requires a new run.

### Treating JobParametersValidator as the place to check everything

A validator is suited to fast, deterministic checks on JobParameters. Checking large files, calling APIs, or locking resources should live in a preflight step or a business component that has appropriate timeout and error handling mechanisms.

### Thinking that run() returning means the Job succeeded

An asynchronous launcher can return while the Job is still running. Even with a synchronous launcher, a Job can end with `BatchStatus.FAILED` without the Step error turning into an exception at the caller. Always check the execution status.

### Modifying metadata yourself to relaunch

Deleting an execution or changing `STATUS` directly in the `BATCH_*` tables can break the metadata relationships and checkpoints. Use an operational API or a designed recovery procedure after determining the actual business data.

### Unlimited retries when the executor or database is overloaded

Unbounded retries can increase load and create additional duplicate requests. Use backoff, retry limits, capacity monitoring, and an idempotency mechanism.

## 18. A process for designing safe validation and launching

When building an endpoint or scheduler that launches a Job, you can apply the following sequence:

1. Determine the business key and the identifying parameters to distinguish JobInstances.
2. Convert the request into typed `JobParameters`; handle parse errors right at the mapping layer.
3. Use `JobParametersValidator` to check required parameters, format, and basic relationships.
4. Let the JobRepository check the JobInstance state and previous executions.
5. Classify the launch exceptions so the caller receives appropriate guidance.
6. Record the JobExecution ID and return a clear acceptance status.
7. Monitor the execution after launch, especially when using an asynchronous executor.
8. Design retry/restart separately, ensuring business operations can be rerun safely.
9. Check logs, metadata, and target data before carrying out a manual recovery procedure.

A good design lets validation reject wrong requests before side effects are created, the JobRepository prevents conflicting runs, and the execution status helps the caller track the result after the Job starts.

## Conclusion

Launch exceptions in Spring Batch reflect different problems at the stages of receiving parameters, identifying the JobInstance, checking the restart state, or handing the task to the executor. `JobParametersValidator` helps check required parameters and input rules before the Job executes. `JobExecutionAlreadyRunningException`, `JobInstanceAlreadyCompleteException`, and `JobRestartException` need to be handled according to the actual state of the JobInstance. After launch, check the `JobExecution` and its statuses to distinguish a Job that was rejected from launching from a Job that started but failed in a Step.
