# JobParametersIncrementer

`JobParametersIncrementer` is the mechanism that creates the `JobParameters` set for the **next JobInstance** of a job. It receives the parameters of the previous instance and returns new parameters, typically by incrementing an identifying value such as `run.id`, the business date, or a reprocessing version.

An incrementer is useful when the application needs to launch new instances periodically or in an ordered sequence. You need to distinguish this operation from restart: a restart continues the same JobInstance using the old identifying parameters, whereas an incrementer usually creates new identifying parameters to start a different JobInstance.

## 1. The role and contract of JobParametersIncrementer

`JobParametersIncrementer` is a Spring Batch interface with the method:

```java
public interface JobParametersIncrementer {
    JobParameters getNext(JobParameters parameters);
}
```

The `getNext` method receives the parameters of the previous run and returns the parameter set for the next run. When there is no previous instance, the input may be empty or null depending on the calling path; the implementation should handle the first-time initialization case explicitly.

An incrementer does not execute the job and does not store metadata by itself. It only creates parameters. It is the `JobLauncher` or `JobOperator` that requests the job's execution, while the `JobRepository` stores the JobInstance and JobExecution.

An example of the idea with a daily data aggregation job:

```text
Job: dailySettlement

Instance 1: businessDate=2026-11-14
Instance 2: businessDate=2026-11-15
Instance 3: businessDate=2026-11-16
```

Each parameter set has a different business date, so a different JobInstance is created if `businessDate` is an identifying parameter.

## 2. Configuring an incrementer for a job

You can attach an incrementer when building the job with `JobBuilder.incrementer(...)`. Spring Batch provides `RunIdIncrementer` for the common case of needing to increment a sequence number.

```java
@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep) {

    return new JobBuilder("dailySettlementJob", jobRepository)
        .incrementer(new RunIdIncrementer())
        .start(settlementStep)
        .build();
}
```

With this configuration, the job has a default incrementer for creating parameters for the next instance. Attaching an incrementer does not make every `JobLauncher.run(...)` call automatically increment parameters; how the job is called determines whether the incrementer is used.

## 3. How does RunIdIncrementer work?

`RunIdIncrementer` is a built-in implementation for incrementing a numeric parameter. By default, the key used is `run.id`. If the previous parameters do not yet have this key, the first value is typically `1`; each time the next parameter set is created, the value is incremented.

| Instance creation | `run.id` | Identity result |
|---|---:|---|
| First time | 1 | New JobInstance |
| Next time | 2 | New JobInstance |
| Next time | 3 | New JobInstance |

For example, you can configure the incrementer with a different key:

```java
RunIdIncrementer incrementer = new RunIdIncrementer();
incrementer.setKey("reprocessVersion");
```

In that case, the incrementer increments `reprocessVersion` instead of `run.id`. Only change the key name when there is a business reason or a clear convention; avoid having several different mechanisms increment parameters with overlapping meanings.

The parameter created by `RunIdIncrementer` is marked identifying in the standard implementation. Therefore, the incremented value changes the JobInstance identity and allows a new instance to be created even if the other parameters are kept unchanged.

## 4. Using JobOperator.startNextInstance()

An incrementer is typically used by `JobOperator.startNextInstance(jobName)`. This method asks Spring Batch to create the next parameters based on the incrementer attached to the job, and then launches the new instance.

```java
@Service
public class SettlementScheduler {

    private final JobOperator jobOperator;

    public SettlementScheduler(JobOperator jobOperator) {
        this.jobOperator = jobOperator;
    }

    public long startNextSettlement() throws Exception {
        return jobOperator.startNextInstance("dailySettlementJob");
    }
}
```

`startNextInstance` returns the execution ID so the application can track the JobExecution that was created. This method requires the job to be registered in the `JobRegistry` and the job to have a `JobParametersIncrementer` configured. Specific exceptions can arise when the job is not found, the parameters are invalid, the job is running, or the next instance cannot be created.

At the conceptual level, the process is:

```text
JobOperator.startNextInstance(jobName)
              |
              v
      Find job and incrementer
              |
              v
   Get parameters of the previous instance
              |
              v
      incrementer.getNext(previous)
              |
              v
      Create new parameters
              |
              v
        Launch new JobInstance
```

This is a suitable approach for a scheduler or an operations process that wants to request "run the next instance" without each caller computing the parameters itself.

## 5. Distinguishing startNextInstance, JobLauncher.run, and restart

These three operations serve different purposes:

| Operation | Parameters used | Desired outcome |
|---|---|---|
| `JobLauncher.run(job, parameters)` | The parameter set the caller passes in | Runs or requests to run the instance identified by those parameters themselves |
| `JobOperator.startNextInstance(jobName)` | Parameters created by the incrementer from the previous instance | Creates and runs the next JobInstance |
| Restart a failed/stopped execution | Keep the identifying parameters of the old JobInstance | Continues the same logical work, creating a new JobExecution |

For example, the job importing transactions for 15/11 failed midway. To continue processing exactly that dataset, restart the execution or call the launcher with the same identifying parameters according to the repository state. Do not increment `run.id` merely to get past the error; doing so would create a new JobInstance and may reprocess the data from the beginning.

Conversely, when the 15/11 job has completed and the schedule needs to process the next day, `startNextInstance` together with an incrementer can create the parameters for a new instance.

### JobLauncher.run does not call the incrementer automatically

The following code uses exactly the parameters the caller supplies:

```java
JobParameters parameters = new JobParametersBuilder()
    .addString("businessDate", "2026-11-15", true)
    .toJobParameters();

jobLauncher.run(dailySettlementJob, parameters);
```

Even though the job has been configured with `.incrementer(new RunIdIncrementer())`, the `run` call above does not add or increment `run.id` by itself. If the caller needs to create a new instance via `JobLauncher`, the caller must create a new set of identifying parameters itself or use a dedicated service that calls the incrementer with appropriate input.

## 6. Identifying parameters determine whether a new JobInstance is created

A JobInstance is identified by the job name and the identifying JobParameters. Therefore, the incrementer's output needs to change at least one identifying parameter if the goal is to create a new JobInstance.

For example:

```java
JobParameters next = new JobParametersBuilder(previous)
    .addLong("run.id", nextRunId, true)
    .toJobParameters();
```

The argument `true` marks `run.id` as identifying. If a parameter is added with identifying set to `false`, that value does not take part in identification and may not produce a new JobInstance. When designing a custom incrementer, check the identifying flag of the updated parameters explicitly.

Not every parameter should be incremented. Only increment the value that represents a new unit of work, such as the next business date or the reprocessing version. Keep the parameters needed to identify the processing scope unchanged, for example the data source code or the tenant, if the business requires it.

## 7. Writing a custom JobParametersIncrementer

`RunIdIncrementer` suits cases where only a sequence number is needed. If each next instance must use a business date, a reporting period, or a batch code computed by its own rule, implement `JobParametersIncrementer`.

The example below increments `businessDate` by one day. For the first run, where there is no previous date, the example uses the current date according to a `Clock` configured for the business time zone:

```java
public class BusinessDateIncrementer implements JobParametersIncrementer {

    private final Clock clock;

    public BusinessDateIncrementer(Clock clock) {
        this.clock = clock;
    }

    @Override
    public JobParameters getNext(JobParameters parameters) {
        JobParameters previous = parameters == null
            ? new JobParameters()
            : parameters;

        String previousDate = previous.getString("businessDate");
        LocalDate nextDate = previousDate == null
            ? LocalDate.now(clock)
            : LocalDate.parse(previousDate).plusDays(1);

        return new JobParametersBuilder(previous)
            .addString("businessDate", nextDate.toString(), true)
            .toJobParameters();
    }
}
```

Register the incrementer with the job:

```java
@Bean
JobParametersIncrementer businessDateIncrementer(Clock businessClock) {
    return new BusinessDateIncrementer(businessClock);
}

@Bean
Job dailySettlementJob(
        JobRepository jobRepository,
        Step settlementStep,
        JobParametersIncrementer businessDateIncrementer) {

    return new JobBuilder("dailySettlementJob", jobRepository)
        .incrementer(businessDateIncrementer)
        .start(settlementStep)
        .build();
}
```

In production, the `Clock` should be configured for the time zone of the business calendar. If working days skip weekends or holidays, do not use a simple `plusDays(1)`; get the next date from a business calendar or a managed calendar service.

A custom incrementer should also retain the old parameters needed for the next instance. `new JobParametersBuilder(previous)` copies the previous parameter set and then updates the `businessDate` key. Consider carefully if the previous parameter set has information that is only valid for the old run.

## 8. Principles for designing an incrementer

### The result must have business meaning

An incrementer should not increment a random value just to dodge the `JobInstanceAlreadyCompleteException` error. If you need to rerun the same data because of a business request, use an identifying parameter expressing a version or reprocessing code, and also record the reason and the rules for handling the existing data.

### Keep the necessary parameters

When creating new parameters, do not accidentally drop information needed to process the correct data scope. For example, a job that processes by tenant may need to keep `tenantId`; a report generation job may need to keep `reportType`. However, do not retain temporary parameters or secrets from the previous run.

### Do not put secrets into JobParameters

JobParameters are stored in metadata and may be displayed by admin tools or logs. Do not use an incrementer to copy passwords, access tokens, private keys, or credentials. Reference secrets through a secret manager or the application's secure configuration.

### Avoid depending on uncontrolled external state

An incrementer should compute its result from the previous parameters and a data source with clear rules. If it reads the system date, a business calendar, or an external sequence, you need to define the time zone, the cutoff point, and the retry behavior so the same request does not produce hard-to-predict results.

### Be careful with multiple concurrent callers

If two schedulers or operators call `startNextInstance` almost simultaneously, both may observe the same previous parameter set and compute the same next parameter set. The repository has mechanisms to protect uniqueness and state, but callers still need to handle conflicts under concurrent requests.

For processes requiring a strictly unique sequence number, coordinate launching with a lock, a queue, or an atomic sequence source. You can use a request ID/idempotency key to recognize resubmitted requests. Do not assume a custom incrementer is by itself a concurrency coordinator.

## 9. Common mistakes

| Mistake | Consequence | Remedy |
|---|---|---|
| Configuring an incrementer but calling `JobLauncher.run` with the old parameters | No new parameter is created automatically; an instance-already-completed error may occur | Use `JobOperator.startNextInstance` or create new parameters yourself |
| Using an incrementer to restart a failed execution | Creates a different JobInstance and does not continue the old instance's checkpoint | Restart with the old identifying parameters |
| The incremented parameter is not identifying | Does not create the new JobInstance identity as expected | Mark the new parameter as identifying |
| Dropping scope parameters such as tenant or report type | The new instance processes the wrong or incomplete data scope | Copy and update parameters deliberately |
| Incrementing a timestamp/UUID with no business meaning | Hard to trace and easy to create instances that duplicate data | Use a business key or a clear reprocessing version |
| Multiple callers request the next instance at once | May compute identical parameters and hit conflicts | Coordinate requests or provide an atomic sequence |
| The incrementer relies on a system date in the wrong time zone | Picks the wrong processing period at the day boundary | Use a Clock and a business calendar configured explicitly |
| Copying secrets into the new parameters | Secrets are stored in metadata or logs | Fetch credentials from a secret manager at execution time |

## 10. Testing JobParametersIncrementer

An incrementer is a component that can be tested independently. With `RunIdIncrementer`, test the empty-parameters case, the case where `run.id` already exists, and that other parameters are retained.

Example of testing a custom incrementer:

```java
@Test
void shouldIncrementBusinessDateAndPreserveTenant() {
    Clock clock = Clock.fixed(
        Instant.parse("2026-11-16T00:00:00Z"),
        ZoneOffset.UTC);

    JobParameters previous = new JobParametersBuilder()
        .addString("businessDate", "2026-11-15", true)
        .addString("tenantId", "tenant-42", true)
        .toJobParameters();

    JobParameters next = new BusinessDateIncrementer(clock).getNext(previous);

    assertEquals("2026-11-16", next.getString("businessDate"));
    assertEquals("tenant-42", next.getString("tenantId"));
    assertTrue(next.getParameters().get("businessDate").isIdentifying());
}
```

Besides unit tests, you should test the integration flow with the `JobRepository` and `JobOperator`: create the first instance, call `startNextInstance`, and confirm that the new instance has the expected identifying parameters and its own execution ID. Also test the cases where the previous job is running, the parameters are invalid, and two next-instance requests compete.

## 11. When should you use JobParametersIncrementer?

| Need | Suitable approach |
|---|---|
| Create sequential runs, each with a new `run.id` | `RunIdIncrementer` |
| Run the next business period | A custom incrementer based on date/period and a business calendar |
| Reprocess the same data under a new version | A custom incrementer or a service that creates a clear identifying version |
| Restart a failed job from the checkpoint | Use restart with the old JobInstance and identifying parameters |
| The caller specifies a particular parameter set itself | `JobLauncher.run(job, parameters)` |
| Multiple tenants with independent run schedules | Coordinate parameters per tenant; avoid relying on a single global sequence that does not distinguish tenants |

An incrementer is especially useful when the operations process has a clear concept of a "next instance". If the caller already knows exactly the date, batch code, or data scope to process, a service that creates the parameters explicitly may be easier to understand.

## Conclusion

`JobParametersIncrementer` creates the parameter set for the next JobInstance based on the previous instance's parameters. `RunIdIncrementer` provides a simple way to increment `run.id`, while a custom incrementer can apply rules by business date, reporting period, or reprocessing version. `JobOperator.startNextInstance` is the typical call path that uses a configured incrementer.

Clearly distinguish creating a new instance from restarting the same instance, make sure the incremented parameter is identifying, retain the necessary parameters, and coordinate concurrent requests. An incrementer only creates parameters; it does not replace the JobLauncher, the JobRepository, authorization, or the job's operational process.
