# Avoiding Unintended New Instances

In Spring Batch, a JobInstance represents one logical processing run of a Job over a specific data scope. Spring Batch identifies an instance based on the **Job name and the JobParameters marked identifying**. Therefore, even a small change in the parameters can make the framework understand that the application is requesting a new piece of work.

This is especially important on restart. If a Job fails but the next launch accidentally passes a new timestamp or UUID as identifying, Spring Batch creates a different JobInstance. The new instance does not inherit the history and checkpoints of the failed instance, so the intended restart process does not take place.

This lesson explains how to avoid creating unintended new JobInstances, how to distinguish a restart from a new business processing run, and how to control JobParameters at the place where the Job is launched.

## 1. How is a JobInstance identified?

Spring Batch uses two components to identify a JobInstance:

~~~text
JobInstance = Job name + identifying JobParameters
~~~

The Job name identifies the Job definition. The identifying JobParameters identify the scope of work the instance represents. Each JobParameter has a name, a value, a data type, and an identifying flag:

- **identifying = true**: the parameter takes part in identifying the JobInstance.
- **identifying = false**: the parameter is passed to the JobExecution but does not change the JobInstance identity.

For example, a daily order import Job can use businessDate as an identifying parameter. Every launch with the same Job name and the same businessDate points to the same JobInstance, as long as the other identifying parameters are also the same.

~~~text
Job: dailyOrderImport
    |
    +-- JobInstance: businessDate=2026-11-15
    |       |
    |       +-- JobExecution #1: FAILED
    |       |
    |       +-- JobExecution #2: COMPLETED
    |
    +-- JobInstance: businessDate=2026-11-16
            |
            +-- JobExecution #1: COMPLETED
~~~

In the diagram, the first two JobExecutions belong to the same JobInstance because they process the same business date. The instance for 16/11/2026 is a different instance because businessDate has changed.

Do not equate a JobLauncher call with a JobInstance. Multiple JobExecutions can belong to the same JobInstance, for example when the Job is restarted after a failure. Conversely, two JobLauncher calls can create two different JobInstances if the identifying parameters differ.

## 2. Identifying and non-identifying parameters

The choice of identifying flag must reflect the business meaning of the parameter. A parameter is identifying when changing its value means the Job is processing a different data scope or a different business run.

| Parameter | Commonly used marking | Reason |
| --- | --- | --- |
| businessDate | Identifying | Each day is a separate data scope |
| inputFileId | Identifying | Each immutable input file represents one dataset |
| tenantId | Identifying | Each tenant's data is a separate scope |
| dataRevision | Identifying | Each data version needs to be processed separately |
| requestedBy | Non-identifying | Records who requested the run |
| requestId or correlationId | Non-identifying | Tracks the request and links logs |
| requestedAt | Non-identifying | Records the time of the request |
| notificationEmail | Non-identifying | Used only for notifications |

This is a convention based on semantics, not a hard list. For example, dryRun should be identifying if this mode changes the result or the way of processing and the two modes need to be managed as two different processing runs. If a parameter seems to be only for audit but changes the data read or written, it needs to take part in the instance identity.

### Declare the identifying flag explicitly

Pass the identifying flag explicitly when creating JobParameters:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-file-2026-11-15", true)
        .addLong("tenantId", 42L, true)
        .addString("requestedBy", "scheduler", false)
        .addString("requestId", "request-8f31", false)
        .toJobParameters();
~~~

In the example:

- businessDate, inputFileId, and tenantId identify the JobInstance.
- requestedBy and requestId can still be read in the Job or Step, but changing these values does not create a new instance.

The JobParametersBuilder overloads may provide default values for the identifying flag. To avoid relying on defaults or confusion when upgrading the framework, use the overload with a boolean parameter and explicitly declare true or false for each value.

## 3. Timestamps and UUIDs can accidentally create new instances

A common mistake is adding the current time to JobParameters for convenient tracking:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("startedAt", Instant.now().toString(), true)
        .toJobParameters();
~~~

Because startedAt is identifying, each call has a different value. Spring Batch treats each request as a new JobInstance, even when businessDate is unchanged and the Job is being restarted after a failure.

A UUID or random number causes a similar problem if marked identifying:

~~~java
// Each call creates a different instance identity.
parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("runId", UUID.randomUUID().toString(), true)
        .toJobParameters();
~~~

If the timestamp or UUID only serves tracing, leave them non-identifying or record them in a separate audit/log system:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", businessDate, true)
        .addString("startedAt", Instant.now().toString(), false)
        .addString("requestId", UUID.randomUUID().toString(), false)
        .toJobParameters();
~~~

Only mark a value as identifying if changing that value truly means a new business scope. Do not use a timestamp or UUID as a convenient way to force Spring Batch to create a new instance.

Note: non-identifying does not mean the parameter is discarded. The Job can still read it. Therefore, do not let business logic depend on a non-identifying value if changing that value could make the processing result different. If it changes the data processed or a result that must be managed separately, consider including it in the instance identity.

## 4. Use stable JobParameters on launch and restart

Suppose a Job imports data by day. The application can create the parameter set from stable business keys:

~~~java
public JobParameters buildParameters(
        LocalDate businessDate,
        String inputFileId,
        String requestedBy) {

    return new JobParametersBuilder()
            .addString("businessDate", businessDate.toString(), true)
            .addString("inputFileId", inputFileId, true)
            .addString("requestedBy", requestedBy, false)
            .toJobParameters();
}
~~~

Launch the Job:

~~~java
JobParameters parameters = buildParameters(
        LocalDate.of(2026, 11, 15),
        "orders-file-2026-11-15",
        "scheduler"
);

JobExecution execution = jobLauncher.run(dailyOrderImport, parameters);
~~~

When this instance needs to be restarted, the application must recreate the same Job name and the same identifying values:

~~~java
JobParameters restartParameters = buildParameters(
        LocalDate.of(2026, 11, 15),
        "orders-file-2026-11-15",
        "scheduler"
);

JobExecution restartedExecution =
        jobLauncher.run(dailyOrderImport, restartParameters);
~~~

If the previous execution failed or stopped and the Job allows restart, Spring Batch can create a new JobExecution for the same JobInstance. The stored metadata and checkpoints are used through the restart mechanism of the Job and the Step components.

In practice, you do not necessarily have to call JobLauncher again yourself to restart. You can use JobOperator or an operations tool provided by the application. Whichever API you use, keep to the intent: restart the old execution with the same instance identity, instead of creating a new set of identifying parameters.

## 5. How do same and different parameters affect the outcome?

Suppose the Job is named dailyOrderImport and uses only businessDate as the identifying parameter:

| Call | businessDate (identifying) | requestedBy (non-identifying) | Identity |
| --- | --- | --- | --- |
| A | 2026-11-15 | scheduler | Instance A |
| B | 2026-11-15 | operator | Still instance A |
| C | 2026-11-16 | scheduler | New instance |
| D | 2026-11-15 | scheduler, with a new non-identifying startedAt | Still instance A |

The cases above show that:

- Changing an identifying parameter produces a different instance identity.
- Changing a non-identifying parameter does not change the identity.
- Keeping all identifying parameters unchanged does not mean the call is always allowed to run. The outcome also depends on the current state of the JobInstance and the Job's restartability.

For example, if instance A is already COMPLETED, launching again with the same identifying parameters is usually rejected with JobInstanceAlreadyCompleteException. If the previous execution is running, a duplicate request is usually rejected with JobExecutionAlreadyRunningException. If the previous execution is FAILED or STOPPED and the Job allows restart, Spring Batch can create the next JobExecution for the same instance.

If you change an identifying parameter to dodge JobInstanceAlreadyCompleteException, the framework will create a new JobInstance. That can make the Job reprocess the same data without the old instance's checkpoint. Only do this when the business truly requires a new logical processing run and an appropriate strategy against duplicate writes is in place.

## 6. The Job name also takes part in identifying the instance

JobParameters are not the only factor determining identity. The Job name is also part of the identity.

For example, two launches with the same businessDate and inputFileId but different Job names create two different JobInstances:

~~~text
Job name: dailyOrderImport
businessDate: 2026-11-15
inputFileId: orders-2026-11-15
        |
        v
JobInstance A

Job name: dailyOrderReconciliation
businessDate: 2026-11-15
inputFileId: orders-2026-11-15
        |
        v
JobInstance B
~~~

Do not create a dynamic Job name by concatenating a timestamp, UUID, hostname, or the name of the person running it if the intent is to restart the same Job. Keep the Job name stable according to the process definition. Renaming a Job can make the repository treat it as a different definition and not find the old instance.

When renaming a Job during deployment, consider the metadata history and the restart strategy for old executions. Do not rename merely to rerun a completed instance.

## 7. Values and data types must be normalized

Two parameters that look the same to a human may still not be considered the same identifying parameter if the stored type or value differs.

For example:

| Call | Parameter name | Type | Displayed value |
| --- | --- | --- | --- |
| A | tenantId | Long | 42 |
| B | tenantId | String | "42" |

The data type is part of the JobParameter. Do not pass a code as a number at one time and as a string at another if the two runs must point to the same instance.

Dates and times also need consistent formatting:

- Use a standard date format, such as ISO-8601 for the business date.
- Specify the time zone explicitly if identification is based on a point in time.
- Normalize upper/lower case if the business code is case-insensitive.
- Avoid using an absolute path at one time and a relative path at another for the same file.
- Use an immutable file ID or version instead of relying only on a file name that can be replaced.

Spring Batch does not read the file content to determine the JobInstance identity. If the file at the same path has its content replaced but the JobParameters do not change, the repository still recognizes the same instance. If the content change means a new import, pass a file ID, revision, or checksum appropriate to the business process.

## 8. RunIdIncrementer and startNextInstance

RunIdIncrementer is used when the application deliberately wants to create a new JobInstance for the next run. The incrementer typically increments the identifying parameter run.id based on the previous parameter set.

Example Job configuration:

~~~java
@Bean
public Job dailyOrderImport(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("dailyOrderImport", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(importOrdersStep)
            .build();
}
~~~

When using JobOperator.startNextInstance with a Job configured with an incrementer, Spring Batch asks the incrementer to create the JobParameters set for the next instance. The new run.id value changes the instance identity.

This is appropriate when the business wants each next run to be a new logical processing run. However, it is not a mechanism for restarting a failed execution. If startNextInstance is used in place of restart, the application can create a new instance and skip the old instance's checkpoint.

Distinguishing the two intents:

| Need | Approach |
| --- | --- |
| Continue a JobInstance that is FAILED or STOPPED | Restart the old execution with the same identifying parameters, via JobOperator.restart or the corresponding restart flow |
| Run a new business scope | Create new identifying parameters reflecting the new scope |
| Deliberately run the next instance by sequence number | Use an incrementer and startNextInstance when that is the business rule |
| Only record who requested or when it was requested | Use non-identifying parameters or audit/logs |

JobLauncher.run(job, parameters) uses the parameter set the application passes in. Do not assume that configuring RunIdIncrementer will automatically increment run.id every time JobLauncher.run is called. The incrementer is used in flows requesting the next instance that apply the incrementer, such as startNextInstance.

## 9. When should you deliberately create a new instance?

There are business cases that truly need to rerun the same type of Job on the same date or the same dataset. For example:

- The input file is corrected and released as a new revision.
- A tenant's data is requested to be reprocessed after the conversion rules change.
- An operator requests an independent re-reconciliation after handling an incident.
- A data period has multiple approved versions and needs separate history.

In those cases, add an identifying parameter with business meaning, such as dataRevision or reprocessVersion:

~~~java
JobParameters parameters = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("inputFileId", "orders-2026-11-15", true)
        .addLong("reprocessVersion", 2L, true)
        .addString("requestedBy", "operations", false)
        .toJobParameters();
~~~

The reprocessVersion value must be managed deliberately, be traceable, and be explainable. Avoid creating a random UUID just to dodge the COMPLETED state. Each new instance can redo side effects such as writing data, sending messages, or calling APIs; therefore the writer and business services need an idempotency policy, business keys, or a reconciliation mechanism.

If the goal is only to recover a failed run, do not create a new revision. Restart the old instance to take advantage of the stored state and checkpoints.

## 10. JobParametersValidator does not determine instance identity

JobParametersValidator checks whether parameters are valid before the Job runs. For example, a validator can require that businessDate and inputFileId be present, or check the date format.

A validator does not decide which parameters are identifying. The identifying flag lives on each JobParameter and is used by the JobRepository to identify the JobInstance.

Example of validating required parameters:

~~~java
public class OrderImportParametersValidator
        implements JobParametersValidator {

    @Override
    public void validate(JobParameters parameters)
            throws JobParametersInvalidException {

        String businessDate = parameters.getString("businessDate");
        String inputFileId = parameters.getString("inputFileId");

        if (businessDate == null || businessDate.isBlank()) {
            throw new JobParametersInvalidException(
                    "businessDate is required");
        }

        if (inputFileId == null || inputFileId.isBlank()) {
            throw new JobParametersInvalidException(
                    "inputFileId is required");
        }
    }
}
~~~

You can attach the validator to the Job:

~~~java
return new JobBuilder("dailyOrderImport", jobRepository)
        .validator(new OrderImportParametersValidator())
        .start(importOrdersStep)
        .build();
~~~

Validation helps detect missing or wrongly formatted parameters early. Marking identifying must still be designed at the place where JobParameters are created. These two responsibilities complement each other but do not replace each other.

## 11. Investigating the cause when an unintended JobInstance appears

When you see multiple JobInstances for the same business scope, trace the actual data passed into JobLauncher or JobOperator.

### Record the identity before launching

At the orchestration layer, you can log the Job name along with the chosen identifying parameters:

~~~java
log.info(
        "Launching job={}, businessDate={}, inputFileId={}, tenantId={}",
        job.getName(),
        parameters.getString("businessDate"),
        parameters.getString("inputFileId"),
        parameters.getLong("tenantId")
);

JobExecution execution = jobLauncher.run(job, parameters);
~~~

Do not log passwords, access tokens, or sensitive data. Only log the identifying values needed to explain why the repository chose that instance.

### Cross-check the metadata

JobExplorer can be used to look up JobInstances by Job name and see the JobExecutions belonging to each instance. For example:

~~~java
List<JobInstance> instances =
        jobExplorer.getJobInstances("dailyOrderImport", 0, 20);

for (JobInstance instance : instances) {
    List<JobExecution> executions =
            jobExplorer.getJobExecutions(instance);

    log.info(
            "instanceId={}, jobName={}, executionCount={}",
            instance.getInstanceId(),
            instance.getJobName(),
            executions.size()
    );
}
~~~

When investigating, compare the Job name, parameter names, values, and identifying types between executions. You can use SQL metadata queries to help investigate, but prefer JobExplorer in application code to avoid depending directly on the internal table structure.

A JobInstance with multiple JobExecutions usually indicates there have been executions or restarts over the same scope. Multiple JobInstances for the same business date may stem from an identifying timestamp, a UUID, run.id, a dynamic Job name, or another identifying value that changes.

## 12. Common mistakes

### Adding a timestamp to the identifying parameters

Each call with a new timestamp creates a new instance. If the timestamp is only for audit, mark it non-identifying or write it to a log.

### Creating a new UUID for every launch

A random UUID in identifying form gives each call a different identity, destroying the meaning of restart. Only use an identifying ID when it represents an independent business request that must be processed as its own instance.

### Using RunIdIncrementer for the restart flow

The incrementer is designed to request the next instance. When you need to restart a failed instance, use the restart flow with the original identifying parameters.

### Thinking that changing requestedBy creates a new instance

If requestedBy is non-identifying, changing the value does not create a new instance. If changing the requester implies a new business process, you need to redefine the parameter's meaning and the identity model.

### Using unstable default parameters

A launch layer may add a time, a sequence number, or a random value by itself without the caller noticing. Centralize the creation of JobParameters in one place with a clear convention and log the identifying values before launching.

### Changing the format or data type

One call using tenantId as a Long and another as a String, or dates with different formats, can create a different identity. Normalize the type and value representation at the launch boundary.

### Using a dynamic Job name

A Job name that changes by date, hostname, or the person running it changes the instance identity. Keep the Job name stable and put variable information into JobParameters with the appropriate flag.

### Deleting metadata to rerun

Directly deleting rows in BATCH_JOB_INSTANCE or BATCH_JOB_EXECUTION can break foreign key relationships, checkpoints, and operational history. Use the restart API or a controlled reprocessing process instead of manually editing metadata.

## 13. Process for designing safe JobParameters

When building a Job launch flow, determine the instance identity before writing code:

1. **Determine the business scope:** which date, file, tenant, data period, or revision does an instance represent?
2. **Choose identifying parameters:** only put in here the values that change the processing scope.
3. **Mark explicitly:** use the overload with a boolean to declare identifying true or false.
4. **Normalize types and values:** unify date format, ID type, upper/lower case, and the representation of files.
5. **Separate operational data:** requestedBy, requestId, and requestedAt are usually non-identifying if they do not change the business.
6. **Create parameters in one place:** avoid multiple layers adding a timestamp or UUID to the parameter set themselves.
7. **Keep the parameter set on restart:** store or accurately recreate the identifying values of the original run.
8. **Only create new instances deliberately:** use a new business revision or business key when you truly need a separate processing run.
9. **Protect side effects:** design idempotent writers and services so reprocessing does not create duplicate data.
10. **Monitor metadata:** use JobExplorer and logs to explain the identity and execution history.

## Conclusion

Avoid creating unintended new JobInstances by controlling the Job name and the identifying JobParameters. Use stable business keys to identify the processing scope, mark timestamps and UUIDs non-identifying when they only serve audit, normalize data types, and keep the identifying parameters unchanged on restart. Only create a new instance when there is a clearly defined new business request, while protecting data from duplicate side effects.
