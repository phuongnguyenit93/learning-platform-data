# New JobParameters and new instances

In Spring Batch, it is essential to distinguish between resuming an unfinished job and launching a new business processing run. Both operations may use the same `Job` definition, yet they produce different outcomes in metadata.

A `JobInstance` represents a logical business run identified by the job name and identifying `JobParameters`. A `JobExecution` represents a specific execution attempt of that instance. When an execution fails or stops and is restarted, Spring Batch creates a new `JobExecution` for the same `JobInstance`. When the set of identifying parameters changes, Spring Batch creates a new `JobInstance`.

This is the foundational rule for knowing when to keep parameters unchanged to restart and when to supply new parameters to start a different instance.

## 1. JobInstance and JobExecution

A job can run many times. Spring Batch uses `JobInstance` to identify a logical business run, and `JobExecution` to record each execution attempt of that instance.

```text
Job: dailyOrderImport

JobInstance A
  identifying parameters:
    businessDate = 2026-11-15
    region       = NORTH

  JobExecution #1 -> FAILED
  JobExecution #2 -> COMPLETED  (restart same instance)

JobInstance B
  identifying parameters:
    businessDate = 2026-11-16
    region       = NORTH

  JobExecution #3 -> STARTED / COMPLETED
```

In this example, execution #2 resumes instance A's work because identifying parameters did not change. A new business date creates instance B because `businessDate` changed.

To remember:

- `JobInstance` = job name + identifying `JobParameters`.
- `JobExecution` = a specific run attempt of a `JobInstance`.
- A `JobInstance` can have multiple `JobExecution`s due to restarts.
- Each `JobExecution` has its own status, timestamps, exit status, and metadata.

## 2. Identifying JobParameters determine the instance

Not every parameter participates in identifying a `JobInstance`. Each `JobParameter` has an `identifying` attribute. Parameters with `identifying` set to `true` are used to identify the instance; parameters with `identifying` set to `false` do not alter instance identity.

In Spring Batch 5, you can specify this attribute explicitly when building parameters:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

Here, `businessDate` and `region` are identifying parameters. `requestedBy` is a non-identifying parameter, so changing its value does not create a new `JobInstance`.

Overloads in `JobParametersBuilder` that omit the identifying flag may have API/version-specific defaults. When expressing intent explicitly, especially for production jobs, pass the identifying flag explicitly.

### Which parameters should be identifying?

A parameter should be identifying if it alters the dataset or business meaning of the processing run. For example:

| Parameter | Usually identifying? | Reason |
|---|---|---|
| `businessDate` | Yes | Identifies the date of data to process |
| `tenantId` or `region` | Yes | Identifies the data scope |
| `sourceFileId` or `inputBatchId` | Yes | Identifies the input source of the import |
| `fromDate`, `toDate` | Yes | Identifies the data interval |
| `requestedBy` | Usually no | Audit metadata about the requester |
| `traceId` | Usually no | Used to trace a launch attempt, does not define business data |
| `notificationEmail` | Depends on domain | Identifying only if it changes the defined processing outcome |

Do not mark a parameter identifying merely to dodge already-complete errors. If a parameter affects the data or business outcome, include it in identity. If it is purely observational metadata, keep it non-identifying.

## 3. Restarting the same JobInstance with identical parameters

When a job execution fails or stops and the instance is restartable, relaunch the same job with the same set of identifying parameters. Spring Batch locates the old `JobInstance` and creates a new `JobExecution` to continue.

Example initial launch:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, parameters);
```

Suppose the execution fails at step `importOrders`. After fixing the root cause, relaunch the job with the exact same `businessDate` and `region`:

```java
JobParameters restartParameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, restartParameters);
```

Because the identity is unchanged, this becomes a new execution of the same `JobInstance`, provided the prior status permits restarting. Spring Batch uses saved metadata and checkpoints to determine which steps already completed and which step needs to re-run.

Do not add a new timestamp or identifying `run.id` when your goal is to restart. Doing so creates a new `JobInstance` and ignores the failed instance's checkpoints.

## 4. When is a new JobInstance needed?

Create a new instance when you want to process an independent business run, such as:

- Importing data for a different business date.
- Running the same job for another tenant or region.
- Processing a different input file.
- Intentionally re-running a completed batch as a new logical processing run.
- Running a backfill with a different date range or scope.

To create a new instance, change at least one identifying parameter or use an incrementer that produces a new set of identifying parameters.

Example new business date:

```java
JobParameters nextBusinessDay = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("region", "NORTH", true)
    .toJobParameters();

jobLauncher.run(orderImportJob, nextBusinessDay);
```

Because `businessDate` differs, Spring Batch creates a separate `JobInstance`. The old instance retains the previous day's execution history.

## 5. What happens when relaunching with the same identifying parameters?

Behavior depends on the current state of the `JobInstance` and its prior executions.

| Previous instance/execution state | Launching with the same identifying parameters |
|---|---|
| Never run before | Creates the first `JobInstance` and `JobExecution` |
| Execution currently running | Typically rejected because the job instance is already running |
| Execution failed and restart is allowed | Creates a new `JobExecution` for the same instance |
| Execution stopped and restart is allowed | Can create a new execution to resume |
| Instance already completed | Typically throws `JobInstanceAlreadyCompleteException` |
| Step/job exceeded start limit or configured non-restartable | Launch may be rejected |

Therefore, identical parameters do not mean starting from scratch every time. For a completed instance, Spring Batch blocks duplicate launches with the same identity to prevent accidentally reprocessing the same business run.

If you need to re-run already-completed data, decide whether it is a new instance with a new identifying parameter or an explicitly designed reprocessing workflow. Never edit metadata directly in JobRepository to force a job to re-run.

## 6. Non-identifying parameters do not create a new instance

You can pass additional metadata that does not participate in identity:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("region", "NORTH", true)
    .addString("requestedBy", "operator-42", false)
    .addString("traceId", "trace-a1b2", false)
    .toJobParameters();
```

The `requestedBy` and `traceId` parameters do not create a new instance. They can be useful for auditing or tracing a launch attempt.

Do not let a non-identifying parameter change the data scope or processing rules. If `sourceFile` changes while marked non-identifying, the job could be treated as the same instance even though the input changed. This makes metadata, restarts, and data correctness confusing.

Rule of thumb: if changing a parameter can cause the same JobInstance to process a different dataset or produce a different business outcome, that parameter should be identifying.

## 7. Using RunIdIncrementer to create the next instance

`JobParametersIncrementer` builds the next parameter set from the current parameter set. `RunIdIncrementer` is a built-in implementation commonly used to increment a `run.id` parameter whenever a next instance is requested.

```java
@Bean
Job orderImportJob(
        JobRepository jobRepository,
        Step importOrdersStep) {

    return new JobBuilder("orderImportJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(importOrdersStep)
        .build();
}
```

With `RunIdIncrementer`, subsequent parameters receive an incremented `run.id`. `run.id` acts as an identifying parameter to create a new `JobInstance`.

Example:

| Run | businessDate | run.id | Instance |
|---|---|---:|---|
| 1 | 2026-11-15 | 1 | Instance A |
| 2 | 2026-11-15 | 2 | Instance B |
| 3 | 2026-11-15 | 3 | Instance C |

This example creates three separate instances for the same business date. Use this approach only when you genuinely want a new processing run. If instance A fails and needs restarting, reuse A's parameters instead of incrementing `run.id`.

## 8. Custom JobParametersIncrementer

When `run.id` does not capture business meaning, you can write a custom incrementer. For example, a job processing reconciliation cycles might increment `cycle` or pick the next business date.

```java
public class ReconciliationIncrementer implements JobParametersIncrementer {

    @Override
    public JobParameters getNext(JobParameters parameters) {
        String currentCycle = parameters == null
            ? null
            : parameters.getString("cycle");

        long nextCycle = currentCycle == null
            ? 1L
            : Long.parseLong(currentCycle) + 1L;

        return new JobParametersBuilder(parameters == null
                ? new JobParameters()
                : parameters)
            .addString("cycle", Long.toString(nextCycle), true)
            .toJobParameters();
    }
}
```

The incrementer receives current parameters and returns parameters for the next instance. In this example, `cycle` is identifying, so each value creates a different instance.

When writing an incrementer, ensure:

- The result always yields a new identity when requesting the next instance.
- Other required identifying parameters such as tenant or region are preserved.
- Audit details are not accidentally turned into identifying parameters.
- Null input parameters or missing keys are handled cleanly.
- The increment rule is deterministic and aligns with business rules.

Do not arbitrarily use the current timestamp if it can cause collisions or make it hard for operators to tell which instance corresponds to which business run.

## 9. startNextInstance via JobOperator

When a job is configured with a `JobParametersIncrementer`, `JobOperator.startNextInstance(jobName)` can ask Spring Batch to generate the next parameters and launch the next instance.

```java
long executionId = jobOperator.startNextInstance("orderImportJob");
```

`JobOperator` finds the latest instance of the job, invokes the configured incrementer to build the next parameters, and launches the new instance. This is helpful for periodic jobs or workflows requiring a "start next" operational command.

This method creates the next instance according to the incrementer; it does not restart a failed instance. When a restart is needed, relaunch using the old instance's identifying parameters or use the appropriate restart operation via JobOperator with the known execution ID.

## 10. Distinguishing restart, start new, and start next

Three actions are frequently confused:

| Action | Parameters | Result |
|---|---|---|
| Restart failed instance | Keep identifying parameters unchanged | Creates a new JobExecution for the same JobInstance |
| Start new instance | Change an identifying parameter | Creates a new JobInstance |
| Start next instance | Invoke incrementer to build next parameters | Creates a new JobInstance per incrementer rules |

For example:

- The import job for the 15th failed: re-run the 15th with the same identifying parameters to restart.
- The import job for the 15th completed, now import the 16th: change `businessDate` to create a new instance.
- The job needs a subsequent run with `run.id`: use an incrementer or `startNextInstance`.

Do not substitute one action for another solely to bypass a JobRepository status check. Choosing the right semantics keeps history and checkpoints accurately aligned with business intent.

## 11. Complete example with businessDate and run.id

The job below processes daily data. `businessDate` identifies the business data, while `requestedBy` is strictly for auditing.

```java
@Bean
Job dailyImportJob(
        JobRepository jobRepository,
        Step dailyImportStep) {

    return new JobBuilder("dailyImportJob", jobRepository)
        .start(dailyImportStep)
        .build();
}

JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();

jobLauncher.run(dailyImportJob, parameters);
```

When an execution fails, reuse `businessDate=2026-11-15` to restart. For the next day, the 16th, change the identifying parameter:

```java
JobParameters nextDay = new JobParametersBuilder()
    .addString("businessDate", "2026-11-16", true)
    .addString("requestedBy", "scheduler", false)
    .toJobParameters();
```

If business rules permit re-running the same date as a brand-new instance, you can add an identifying `run.id` or `reprocessVersion`. Document the reprocess reason clearly and ensure writers enforce an appropriate idempotency/upsert policy.

## 12. JobParameters and input data uniqueness

Identifying parameters should stably describe the input dataset of an instance. For example, if a job reads files, you can use `sourceFileId` or a batch ID issued by the upstream system.

Do not rely solely on a filename if the same path can be overwritten with different contents. Two files sharing a name with different contents could be treated as the same instance. Use an immutable file ID, checksum, or source version as an identifying parameter.

For date-range jobs, define timezones and boundary conventions clearly. `fromDate=2026-11-01` and `toDate=2026-11-15` must have stable semantics, such as a half-open interval `[from, to)`, so restarting does not inadvertently shift the data.

## 13. Restarting and checkpoints do not depend on incrementers

An incrementer builds parameters for a new instance. It does not save reader positions, restore chunks, or decide which steps completed.

Restartability depends on:

- JobRepository persisting metadata for JobInstance, JobExecution, and StepExecution.
- Readers or tasklets saving appropriate checkpoints in `ExecutionContext`.
- Step names and job structure remaining stable enough to match old metadata.
- The JobInstance being in a restartable status.
- Writers and external side effects being safe when portions of work re-execute.

If a reader does not save state or the input source changed, restarting may read from the wrong position or process duplicates. Identifying parameters pick the right instance; checkpoints resume at the right progress. Both mechanisms complement each other.

## 14. Identifying parameters and concurrency

JobRepository guards instance creation so that launching the same job twice with identical identifying parameters does not accidentally create two independent JobInstances. If an instance is already running, a duplicate launch is typically rejected with an appropriate status error.

If you need two concurrent runs for the same date covering different business scopes, add an identifying parameter representing the actual scope, such as `tenantId`, `sourceBatchId`, or `reprocessVersion`. Do not add a random value unless it represents a managed business distinction.

When passing different non-identifying parameters for launches of the same instance, be careful: they do not create a new identity. Do not rely on them to alter input or processing logic in ways that make restarts non-reproducible.

## 15. Validating JobParameters before launch

Jobs should validate required parameters before starting processing. Use `DefaultJobParametersValidator` or a custom validator to check keys, types, and relationships between values.

Example validator requiring `businessDate` and `region`:

```java
@Bean
JobParametersValidator importParametersValidator() {
    return new DefaultJobParametersValidator(
        new String[] { "businessDate", "region" },
        new String[] { "requestedBy", "traceId" }
    );
}
```

Register the validator on the job:

```java
return new JobBuilder("dailyImportJob", jobRepository)
    .validator(importParametersValidator)
    .start(dailyImportStep)
    .build();
```

Validators catch missing parameters before readers or writers cause side effects. For dates, quantities, or intervals, validate formats and business rules in the validator or a dedicated validation step.

## 16. Common pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Adding an identifying timestamp when intending to restart | Creates a new JobInstance, losing link to old checkpoints | Preserve identifying parameters of the failed instance |
| Relaunching a COMPLETED instance with the same parameters | `JobInstanceAlreadyCompleteException` | Create a new identity if a new business run is genuinely needed |
| Marking an input parameter non-identifying | Two different datasets may be treated as the same instance | Mark every parameter altering data scope as identifying |
| Using `run.id` on every restart | Creates a new instance instead of resuming the old instance | Increment `run.id` only when a new instance is desired |
| Thinking incrementers store checkpoints | Step progress cannot be restored | Use ExecutionContext/ItemStream for checkpoints |
| Adding random identifying parameters | Hard to trace, creates unnecessary instances | Use stable, meaningful business keys |
| Arbitrarily renaming jobs or steps | Old metadata is hard to restart under the new structure | Keep names stable or plan migrations |
| Using non-identifying parameters to swap data sources | Restart may run against different input | Include source identity in identifying parameters |

## 17. Procedure for deciding between restart and new instance

When operating jobs, answer in order:

1. Is this the same business processing run or a brand-new one?
2. If it is the same run, identify the exact original identifying parameters.
3. Check the JobInstance status and latest execution in JobRepository.
4. If the execution failed/stopped and is restartable, relaunch with the same identifying parameters.
5. If processing new input or a new business period, update the corresponding identifying parameter.
6. If a new instance is needed for already-completed input, use a meaningful identifying version/reprocess key or configured incrementer.
7. Verify checkpoints, input snapshots, and writer idempotency before restarting/reprocessing.
8. Audit the reason for creating a new instance to distinguish scheduled runs from intentional reruns.

## 18. Testing identity and restarts

Integration tests should use a real `JobRepository` or equivalent test configuration to verify identity semantics.

Required scenarios:

1. First launch with identifying parameters: creates one JobInstance and JobExecution.
2. Launching the same identifying parameters while running: duplicate launch is rejected.
3. Failing an execution and launching with the same identifying parameters: creates a new JobExecution for the same JobInstance if restart is permitted.
4. Changing an identifying parameter: creates a new JobInstance.
5. Changing only a non-identifying parameter: does not create a new JobInstance.
6. Relaunching a completed instance with the same identifying parameters: verify rejection per completed-instance rules.
7. Using an incrementer: verify the identifying parameter increments and a new instance is created.
8. Restarting a checkpointed reader: verify resuming from the committed position.
9. Reprocessing a new instance: verify the writer causes no unintended duplicate side effects.

Inspect `JobInstance` ID, `JobExecution` ID, saved parameters, step statuses, and output data. Checking job status alone is insufficient to prove identity was handled properly.

## Conclusion

A `JobInstance` is identified by the job name and identifying `JobParameters`; each launch or restart is a `JobExecution` belonging to that instance. To restart unfinished work, preserve identifying parameters and let Spring Batch use saved metadata/checkpoints. To start a new business run, change an identifying parameter or use `JobParametersIncrementer` to generate the next parameter set.

Choose identifying parameters based on data scope and business meaning. Use non-identifying parameters for audit/tracing metadata that does not alter results. `RunIdIncrementer` and `startNextInstance` are suited for launching the next instance; they do not replace restarts. Combine stable identity, durable checkpoints, and idempotent writers to operate jobs safely.
