# Identifying and Non-Identifying Parameters

In Spring Batch, every Job launch receives a set of `JobParameters`. Each parameter has a name, a value, a data type, and a property indicating whether it takes part in identifying the logical run. This property is called **identifying** or **non-identifying**.

This distinction determines whether Spring Batch treats two launches as the same `JobInstance` or as two different instances. Therefore, identifying parameters need to accurately reflect the business unit of work; non-identifying parameters suit auxiliary information that does not change the identity of the work. A wrong choice can make a Job impossible to restart, accidentally create a new instance, or process data twice.

## 1. What do JobParameters contain?

`JobParameters` is the collection of parameters passed to a Job when calling `JobLauncher.run(job, parameters)`. For example, a reconciliation Job might receive the reconciliation date, the input file ID, the person who requested the run, and the address to receive notifications.

Each parameter has these components:

- **Name:** the key the Job uses to access the value, for example `businessDate`.
- **Value:** the input data, for example `2026-11-15`.
- **Data type:** string, long integer, floating-point number, date, or a type supported by Spring Batch in the version in use.
- **Identifying flag:** indicates whether the parameter takes part in identifying the `JobInstance`.

You can create parameters with `JobParametersBuilder`:

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", LocalDate.of(2026, 11, 15), true)
        .addString("sourceFile", "settlement-20261115-v2.csv", true)
        .addLong("requestedBy", 1024L, false)
        .addString("notificationEmail", "ops@example.com", false)
        .toJobParameters();
```

In the calls above, the last boolean argument is the identifying flag:

- `true`: the parameter takes part in identifying the JobInstance.
- `false`: the parameter is stored with the execution but does not take part in identifying the JobInstance.

The example uses the overload with a boolean flag so that the intent of each parameter is clear in the code. The specific types and overloads may differ by Spring Batch version; use the API that corresponds to your project's version.

## 2. What are identifying parameters?

Identifying parameters are the values that identify a business run unit. Spring Batch combines the Job name with the entire set of identifying parameters to identify the `JobInstance`.

Suppose the Job `dailySettlementJob` runs reconciliation by day. If `businessDate` is an identifying parameter, two launches with different dates create two JobInstances:

```text
dailySettlementJob
    + businessDate=2026-11-15
        -> JobInstance A

dailySettlementJob
    + businessDate=2026-11-16
        -> JobInstance B
```

If the Job receives multiple identifying parameters, the entire combination of values is used to distinguish instances. For example, both `businessDate` and `sourceFileVersion` are identifying:

| businessDate | sourceFileVersion | JobInstance |
|---|---|---|
| 2026-11-15 | v1 | Instance A |
| 2026-11-15 | v2 | Instance B |
| 2026-11-16 | v1 | Instance C |

Changing any identifying parameter, or adding or removing an identifying parameter, can produce a different instance identity. Therefore, choose values that precisely describe the data scope or business period to be processed.

Common identifying parameters:

- The business date or period of a report, reconciliation, or fee calculation.
- The file ID or immutable version of the input file.
- The batch ID of the data batch from the source system.
- The data scope, such as the tenant code or the date range to process, if that scope changes the content of the work.
- A processing-run ID issued by the business when it allows rerunning the same period as a new piece of work.

An identifying parameter should have a clear business meaning. Do not mark a value as identifying merely to create a unique key for each API call.

## 3. What are non-identifying parameters?

Non-identifying parameters are still inputs to the Job and can still be stored in the metadata of each JobExecution. The difference is that they do not take part in identifying the `JobInstance`.

For example, `requestedBy` records the operator who requested the Job and `notificationEmail` indicates where to send notifications. If these two values change but the identifying parameters do not, Spring Batch still considers the launch to belong to the same JobInstance.

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", sourceFile, true)
        .addLong("requestedBy", operatorId, false)
        .addString("notificationEmail", email, false)
        .toJobParameters();
```

Non-identifying parameters are typically suited to:

- The person or system that requested the Job run.
- The address to receive operational notifications.
- A tracking label, ticket number, or request-recording information.
- Report presentation options that do not change the business data being processed.

However, not all information that seems auxiliary should be non-identifying. If a parameter changes the computed data, the business rules, the set of records read, or the side effects produced, it can affect consistency on restart. In that case, you need to include it in the identity or store an immutable snapshot attached to the JobInstance.

## 4. Comparing identifying and non-identifying

| Criterion | Identifying | Non-identifying |
|---|---|---|
| Takes part in identifying the JobInstance | Yes | No |
| Accessible to the Job during execution | Yes | Yes |
| Stored in the execution metadata | Yes | Yes |
| Does changing the value create a different JobInstance? | Yes | No |
| Typical role | Identifies the business unit of work | Adds information to an execution |
| Examples | Reconciliation date, file ID, and data version | Requester, notification email, ticket number |

The point to remember is that the identifying flag does not determine whether a parameter is used in the Job. Both types can be read in a Step. The flag only determines whether the parameter takes part in identifying the JobInstance.

## 5. When are two launches considered the same JobInstance?

Two launches target the same JobInstance when they have the same Job name and the same set of identifying parameters. The values of non-identifying parameters do not change that identity.

For example, the first launch:

```java
JobParameters firstRun = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", "settlement-v2.csv", true)
        .addLong("requestedBy", 100L, false)
        .toJobParameters();
```

The second launch:

```java
JobParameters secondRun = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("sourceFile", "settlement-v2.csv", true)
        .addLong("requestedBy", 200L, false)
        .toJobParameters();
```

The two launches have the same Job name, the same `businessDate`, and the same `sourceFile`. Even though `requestedBy` differs, they still target the same JobInstance.

Conversely, if `sourceFile` changes from `settlement-v2.csv` to `settlement-v3.csv` and this parameter is identifying, the new launch creates a different JobInstance.

## 6. Impact on restart

Spring Batch distinguishes `JobInstance` from `JobExecution`:

- `JobInstance` represents a logical run, identified by the Job name and the identifying parameters.
- `JobExecution` is one specific execution of a JobInstance.

A JobInstance can have multiple JobExecutions when a previous execution failed or was stopped and then restarted.

```text
Job: dailySettlementJob
Identifying parameters:
  businessDate=2026-11-15
  sourceFile=settlement-v2.csv
                  |
                  v
             JobInstance
                  |
          +-------+-------+
          |               |
          v               v
    JobExecution 1   JobExecution 2
       FAILED          COMPLETED
          |               ^
          +--- restart ---+
```

To restart a failed JobInstance, the application needs to launch the Job with the same Job name and the same identifying parameters. Spring Batch looks up that instance in the `JobRepository` and checks the previous state. If the Job and Step allow restart, the framework creates a new JobExecution for the same instance.

Some common results:

| Previous state | Result when launching with the same identifying parameters |
|---|---|
| No JobInstance yet | Creates a new JobInstance and JobExecution |
| An execution is currently running | May receive `JobExecutionAlreadyRunningException` |
| Already `COMPLETED` | May receive `JobInstanceAlreadyCompleteException` |
| `FAILED` or `STOPPED` | Can restart if the configuration allows |
| Job configured as non-restartable | May receive `JobRestartException` |

If you add a new timestamp or UUID as an identifying parameter on every retry, Spring Batch creates a new JobInstance. The new Job may start again from the beginning instead of continuing from the failed instance's checkpoint. This is a common design mistake when a system automatically retries a launch request.

### Can non-identifying parameters change on restart?

In terms of identity, non-identifying parameters can differ without creating a new JobInstance. However, changing them between executions must be considered carefully. Each JobExecution has its own set of JobParameters; therefore, a restart can receive new non-identifying values while still belonging to the same JobInstance.

This is only safe if the change does not give the previously committed portion and the continued processing portion different business meanings. For example, changing the requester or the notification address usually does not affect settlement data. Conversely, changing the exchange rate, the fee calculation rule, or the data filtering mode can make the results of a JobInstance inconsistent.

If a value affects the business result, keep it stable across restarts. You can mark it identifying, or store an immutable snapshot of the input configuration per JobInstance and reference only that snapshot in every execution.

## 7. Choosing the parameter type through business examples

### End-of-day fee calculation Job

Suppose a Job calculates fees for all accounts for one day. `businessDate` needs to be identifying because each day is a different unit of work. If the input is a versioned data snapshot, `snapshotId` should also be identifying.

```java
JobParameters parameters = new JobParametersBuilder()
        .addLocalDate("businessDate", businessDate, true)
        .addString("snapshotId", snapshotId, true)
        .addLong("requestedBy", operatorId, false)
        .toJobParameters();
```

### File import Job

If each file is imported exactly once, the file ID or the checksum of the file content can be identifying. Use the file name only if that name is stable and uniquely represents the content. If the same file name can be overwritten with different content, the file name alone is not enough to identify the data source.

```java
JobParameters parameters = new JobParametersBuilder()
        .addString("fileId", fileId, true)
        .addString("fileChecksum", checksum, true)
        .addString("submittedBy", username, false)
        .toJobParameters();
```

### Report generation Job with presentation options

If `outputFormat` only changes how the report is exported while the aggregated business data stays the same, you can consider making it non-identifying. But if each format is stored as an independent artifact and needs to be tracked separately, treating the format as identifying can be reasonable. The decision depends on the definition of a run in the business.

There is no hard rule for every parameter name. Decide up front on the question: "If this value changes, do I want Spring Batch to treat this as a different logical run?"

## 8. Accessing both types of parameters in a Step

Both identifying and non-identifying parameters can be accessed in a Step. For example, a Tasklet takes the business date and the requester from `ChunkContext`:

```java
@Bean
@StepScope
Tasklet settlementTasklet() {
    return (contribution, chunkContext) -> {
        Map<String, Object> parameters = chunkContext
                .getStepContext()
                .getJobParameters();

        LocalDate businessDate = (LocalDate) parameters.get("businessDate");
        Long requestedBy = (Long) parameters.get("requestedBy");

        // Process data by businessDate and record requestedBy.
        return RepeatStatus.FINISHED;
    };
}
```

In the example, both values are read as inputs. The identifying flag does not change how the Tasklet accesses them. `@StepScope` lets the bean receive the values of the current run instead of fixing the parameters at application startup time.

When using `@Value` to late-bind a parameter, you need to declare the bean with an appropriate scope:

```java
@Bean
@StepScope
FlatFileItemReader<SettlementInput> settlementReader(
        @Value("#{jobParameters['sourceFile']}") String sourceFile) {

    return new FlatFileItemReaderBuilder<SettlementInput>()
            .name("settlementReader")
            .resource(new FileSystemResource(sourceFile))
            .delimited()
            .names("accountId", "amount")
            .targetType(SettlementInput.class)
            .build();
}
```

## 9. Rules for designing identifying parameters

For a Job to have predictable behavior, apply the following principles:

1. **Define the unit of work first:** determine which day, file, period, tenant, or data batch one JobInstance corresponds to.
2. **Choose a stable business key:** use a code or value that does not change throughout a run and its restarts.
3. **Put factors that change the result into the identity or a snapshot:** do not let a restart silently use different business rules.
4. **Keep operational information non-identifying:** the requester, ticket, or notification address usually does not need to create a new instance.
5. **Do not create a new UUID for each retry:** if you need idempotency, use a stable request ID across resubmissions.
6. **Do not accidentally make all parameters non-identifying:** when there is no identifying parameter, the same Job name may always map to the same JobInstance, even for different business runs.
7. **Validate before launching:** check required parameters, data types, value ranges, and consistency between values.

### When there is no natural business parameter

A Job may need to run many times independently but have no natural date, file ID, or business key. In that case, you can use a deliberately issued run-identifying parameter, or a `JobParametersIncrementer` such as `RunIdIncrementer` in the process of creating the next instance.

Example:

```java
@Bean
Job adHocReportJob(JobRepository jobRepository, Step reportStep) {
    return new JobBuilder("adHocReportJob", jobRepository)
            .incrementer(new RunIdIncrementer())
            .start(reportStep)
            .build();
}
```

The incrementer helps create a new identifying parameter for the next JobInstance when using a mechanism such as `JobOperator.startNextInstance()`. It does not automatically change parameters in a direct `JobLauncher.run(job, parameters)` call. More importantly, a new `run.id` creates a new instance; it is not a way to restart a failed instance.

## 10. Common mistakes

**Marking every parameter as identifying:** auxiliary information such as the requester or notification email produces many unnecessary JobInstances. Looking up history and handling restarts becomes confusing.

**Marking every parameter as non-identifying:** runs for different days or files can be grouped into the same JobInstance. Once the instance has completed, the next launch can be rejected even though the business wants to process a new period.

**Adding a new timestamp on every retry:** each call creates a different instance, leading to reprocessing from the beginning instead of restarting the previous execution.

**Changing business input but keeping the same identity:** a restart can continue with a different dataset or rules, making results inconsistent.

**Confusing non-identifying with not stored:** non-identifying parameters are still part of the JobParameters stored for the execution and can be accessed by the Job.

**Putting secrets into parameters:** JobParameters can be stored in the JobRepository. Do not put a password, access token, or secret directly into the metadata.

**Passing a large payload:** JobParameters should contain keys, ranges, or references to data. Large files and lists of records should be stored in an appropriate data source.

## Conclusion

Identifying parameters, together with the Job name, identify the JobInstance; non-identifying parameters provide additional data to an execution but do not change the instance identity. Both types can be used inside a Step and are stored in the metadata. Mark as identifying the values that identify the business unit of work, keep them stable across restarts, and use non-identifying for auxiliary information. This design lets Spring Batch accurately distinguish a new run from a restart, limits duplicate processing, and keeps results consistent across multiple executions.
